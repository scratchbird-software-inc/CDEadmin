"""General DuckDB schema preservation & macro default reconstruction (DU-AUD-09..16).

Implements explicit, opt-in preservation adapters alongside the existing narrow
adapters in ``duckdb_schema_plan.py`` so every existing narrow refusal contract
remains untouched while admitting:
- ``rebuild-table-general`` (DU-AUD-09, DU-AUD-10, DU-AUD-11, DU-AUD-12,
  DU-AUD-13, DU-AUD-14, DU-AUD-15): combined column type conversions with
  explicit loss acknowledgement, default/nullability/explicit NOT NULL edits,
  column additions/drops/renames/reordering, PK/UNIQUE/CHECK/FK edits,
  self-referential FKs, multi-hop inbound-on-child DAGs, broadened deterministic
  generated columns + generated-on-generated chains, variadic & same-arity
  typed macro probing, co-updated views/macros, UNIQUE/expression/commented
  index replay on parent & inbound children, tag-loss acknowledgement, and
  compound sequence-default preservation without advancing generators.
- ``replace-macro-preserve-defaults`` (DU-AUD-16): reconstructs and preserves
  optional parameter defaults and typed signatures from captured ``source_ddl``
  across single- and multi-overload scalar/table macros with explicit
  ``metadata_reset_acknowledged`` confirmation.
"""

from __future__ import annotations

from collections import deque
from copy import deepcopy
import re

from .firebird_catalog_import import _equal
from .firebird_schema_plan import digest
from ..providers.duckdb.provider import _resource_id


_MAX_REBUILD_COLUMNS = 20_000

# Explicitly refused volatile, sequence, clock, or external-I/O functions in
# generated column expressions (DU-AUD-10).
_VOLATILE_OR_SIDE_EFFECT_FUNCTIONS = frozenset({
    'random', 'setseed', 'uuid', 'uuidv4', 'uuidv7', 'gen_random_uuid',
    'now', 'current_timestamp', 'current_date', 'current_time', 'localtime',
    'localtimestamp', 'transaction_timestamp', 'get_current_timestamp',
    'get_current_time', 'nextval', 'currval', 'error',
    'read_csv', 'read_csv_auto', 'read_parquet', 'read_json',
    'read_json_auto', 'read_blob', 'read_text', 'glob', 'parquet_scan',
    'sqlite_scan', 'postgres_scan', 'mysql_scan',
})

# Proven pure deterministic core scalar functions admitted in generated columns
# (DU-AUD-10).
_ADMITTED_DETERMINISTIC_FUNCTIONS = frozenset({
    'coalesce', 'ifnull', 'nullif', 'nvl',
    'lower', 'lcase', 'upper', 'ucase', 'trim', 'ltrim', 'rtrim',
    'length', 'strlen', 'char_length', 'character_length', 'octet_length',
    'bit_length', 'substr', 'substring', 'left', 'right', 'replace',
    'translate', 'reverse', 'repeat', 'concat', 'concat_ws', 'lpad', 'rpad',
    'strpos', 'instr', 'contains', 'prefix', 'suffix', 'starts_with',
    'ends_with', 'ascii', 'chr', 'nfc_normalize', 'strip_accents',
    'abs', 'round', 'ceil', 'ceiling', 'floor', 'trunc', 'sign', 'mod',
    'pow', 'power', 'sqrt', 'cbrt', 'ln', 'log', 'log10', 'log2', 'exp',
    'greatest', 'least', 'isnan', 'isinf', 'isfinite', 'even', 'factorial',
    'gcd', 'lcm',
    'date_part', 'datepart', 'date_trunc', 'datetrunc', 'date_diff',
    'datediff', 'date_sub', 'datesub', 'make_date', 'make_time',
    'make_timestamp', 'make_timestamptz', 'year', 'quarter', 'month', 'day',
    'dayofmonth', 'dayofweek', 'dayofyear', 'isodow', 'isoyear', 'week',
    'hour', 'minute', 'second', 'millisecond', 'microsecond', 'epoch',
    'epoch_ms', 'epoch_us', 'epoch_ns', 'strftime',
    'struct_pack', 'row', 'struct_extract', 'list_value', 'list_pack',
    'list_extract', 'list_element', 'array_extract', 'list_length', 'len',
    'list_contains', 'list_has', 'list_sort', 'list_reverse_sort',
    'list_distinct', 'list_reverse', 'map_extract', 'map_keys', 'map_values',
    'regexp_matches', 'regexp_replace', 'regexp_extract',
    'md5', 'sha256', 'hex', 'unhex', 'typeof', 'format',
})

_ADMITTED_CAST_TYPE_WORDS = frozenset({
    'boolean', 'bool', 'tinyint', 'smallint', 'integer', 'int', 'int4',
    'bigint', 'int8', 'utinyint', 'usmallint', 'uinteger', 'ubigint',
    'hugeint', 'uhugeint', 'real', 'float', 'float4', 'double', 'float8',
    'decimal', 'numeric', 'varchar', 'text', 'string', 'char', 'bpchar',
    'date', 'time', 'timetz', 'timestamp', 'timestamptz', 'uuid', 'json',
    'blob', 'bytea', 'bit', 'varbit', 'interval', 'struct', 'union', 'map',
    'list',
})


def _quote(value: str) -> str:
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('Native identifier must be nonempty text without NUL')
    return '"' + value.replace('"', '""') + '"'


def _tokenize_duckdb(sql: str):
    import duckdb
    encoded = sql.encode('utf8')
    try:
        raw = duckdb.tokenize(sql)
    except duckdb.Error:
        return None
    out = []
    for idx, (offset, kind) in enumerate(raw):
        end = raw[idx + 1][0] if idx + 1 < len(raw) else len(encoded)
        raw_word = encoded[offset:end].decode('utf8').strip()
        if not raw_word:
            continue
        unquoted = raw_word
        was_quoted = False
        if (kind == duckdb.token_type.identifier and len(raw_word) >= 2 and
                raw_word[0] == '"' and raw_word[-1] == '"'):
            unquoted = raw_word[1:-1].replace('""', '"')
            was_quoted = True
        folded = unquoted.casefold() if kind in {
            duckdb.token_type.keyword, duckdb.token_type.identifier
        } else unquoted
        out.append({
            'kind': str(kind),
            'raw': raw_word,
            'unquoted': unquoted,
            'folded': folded,
            'quoted': was_quoted,
            'offset': offset,
            'end': end,
        })
    if out and out[-1]['kind'] == 'token_type.operator' and out[-1]['raw'] == ';':
        out.pop()
    return out


def _split_top_level_commas(tokens: list[dict]) -> list[list[dict]] | None:
    parts, current, depth = [], [], 0
    for tok in tokens:
        raw = tok['raw']
        if tok['kind'] == 'token_type.operator' and raw in {'(', '['}:
            depth += 1
            current.append(tok)
        elif tok['kind'] == 'token_type.operator' and raw in {')', ']'}:
            depth -= 1
            if depth < 0:
                return None
            current.append(tok)
        elif tok['kind'] == 'token_type.operator' and raw == ',' and depth == 0:
            if not current:
                return None
            parts.append(current)
            current = []
        else:
            current.append(tok)
    if depth != 0:
        return None
    if current:
        parts.append(current)
    return parts


def parse_create_table_clauses(ddl: str) -> tuple[list[list[dict]], list[list[dict]]] | None:
    """Split a CREATE TABLE body into (column_clauses, table_constraint_clauses)."""
    if not isinstance(ddl, str) or not ddl.strip():
        return None
    tokens = _tokenize_duckdb(ddl)
    if not tokens:
        return None
    open_idx = next(
        (i for i, t in enumerate(tokens) if t['kind'] == 'token_type.operator' and t['raw'] == '('),
        None,
    )
    if open_idx is None or tokens[-1]['kind'] != 'token_type.operator' or tokens[-1]['raw'] != ')':
        return None
    inner = tokens[open_idx + 1:-1]
    if not inner:
        return None
    clauses = _split_top_level_commas(inner)
    if not clauses:
        return None
    col_clauses, con_clauses = [], []
    for clause in clauses:
        first = clause[0]
        if (first['kind'] == 'token_type.keyword' and not first['quoted'] and
                first['folded'] in {'constraint', 'primary', 'unique', 'check', 'foreign'}):
            con_clauses.append(clause)
        else:
            col_clauses.append(clause)
    return col_clauses, con_clauses


def _validate_cast_target_tokens(tokens: list[dict]) -> bool:
    if not tokens:
        return False
    depth = 0
    for tok in tokens:
        kind, raw, folded = tok['kind'], tok['raw'], tok['folded']
        if kind == 'token_type.operator':
            if raw in {'(', '['}:
                depth += 1
            elif raw in {')', ']'}:
                depth -= 1
                if depth < 0:
                    return False
            elif raw != ',':
                return False
        elif kind in {'token_type.keyword', 'token_type.identifier'}:
            if depth == 0 and folded not in _ADMITTED_CAST_TYPE_WORDS:
                return False
        elif kind == 'token_type.numeric_const':
            continue
        else:
            return False
    return depth == 0


def validate_general_generated_columns(ddl: str, columns: list[dict]) -> list[str]:
    """Validate generated columns (including deterministic core functions & topological chains).

    Returns topologically ordered generated column names (exact case from ``columns``).
    Raises ``ValueError`` with a descriptive native refusal reason on unsafe/cyclic/invalid
    generated expressions (DU-AUD-10).
    """
    parsed = parse_create_table_clauses(ddl)
    if parsed is None:
        raise ValueError('General table rebuild requires a parseable CREATE TABLE definition')
    col_clauses, _con_clauses = parsed
    by_folded = {}
    for col in columns:
        if not isinstance(col, dict) or not isinstance(col.get('name'), str):
            raise ValueError('General table rebuild requires complete column metadata')
        folded = col['name'].casefold()
        if folded in by_folded:
            raise ValueError('General table rebuild rejects case-colliding column names')
        by_folded[folded] = col['name']

    generated_expr_tokens: dict[str, list[dict]] = {}
    for clause in col_clauses:
        if clause[0]['kind'] not in {'token_type.identifier', 'token_type.keyword'}:
            raise ValueError('Column clause must begin with a column identifier')
        col_folded = clause[0]['unquoted'].casefold()
        if col_folded not in by_folded:
            raise ValueError(f"DDL column {clause[0]['unquoted']!r} is missing from desired column metadata")
        gen_idx = next(
            (
                i for i, tok in enumerate(clause[1:], 1)
                if tok['kind'] == 'token_type.keyword' and tok['folded'] == 'generated'
            ),
            None,
        )
        if gen_idx is None:
            continue
        # Expect GENERATED ALWAYS AS (<expr>) [VIRTUAL|STORED]
        pos = gen_idx + 1
        if (pos + 1 >= len(clause) or
                clause[pos]['folded'] != 'always' or
                clause[pos + 1]['folded'] != 'as'):
            raise ValueError(f"Generated column {by_folded[col_folded]!r} must use GENERATED ALWAYS AS (...)")
        expr = clause[pos + 2:]
        if expr and expr[-1]['kind'] == 'token_type.keyword' and expr[-1]['folded'] in {'virtual', 'stored'}:
            if expr[-1]['folded'] == 'stored':
                raise ValueError('DuckDB 1.5.2 does not support STORED generated columns; only VIRTUAL is supported')
            expr = expr[:-1]
        if len(expr) >= 2 and expr[0]['raw'] == '(' and expr[-1]['raw'] == ')':
            # Strip outer wrapper parentheses if balanced
            depth = 0
            wrapped = True
            for i, tok in enumerate(expr):
                if tok['raw'] == '(':
                    depth += 1
                elif tok['raw'] == ')':
                    depth -= 1
                    if depth == 0 and i < len(expr) - 1:
                        wrapped = False
                        break
            if wrapped and depth == 0:
                expr = expr[1:-1]
        if not expr:
            raise ValueError(f"Generated column {by_folded[col_folded]!r} has an empty expression")
        generated_expr_tokens[col_folded] = expr

    if not generated_expr_tokens:
        return []

    base_folded = set(by_folded) - set(generated_expr_tokens)
    if not base_folded:
        raise ValueError('Table with generated columns must retain at least one base column')

    deps: dict[str, set[str]] = {g: set() for g in generated_expr_tokens}

    def check_expr(owner_gen: str, toks: list[dict]) -> None:
        if not toks:
            raise ValueError(f"Generated column {by_folded[owner_gen]!r} has an invalid subexpression")
        i = 0
        while i < len(toks):
            tok = toks[i]
            kind, raw, folded = tok['kind'], tok['raw'], tok['folded']

            # CAST / TRY_CAST (expr AS type)
            if kind == 'token_type.keyword' and folded in {'cast', 'try_cast'}:
                if i + 1 >= len(toks) or toks[i + 1]['raw'] != '(':
                    raise ValueError(f"Malformed {folded.upper()} in generated column")
                depth, as_idx, close_idx = 1, None, None
                for j in range(i + 2, len(toks)):
                    if toks[j]['raw'] == '(':
                        depth += 1
                    elif toks[j]['raw'] == ')':
                        depth -= 1
                        if depth == 0:
                            close_idx = j
                            break
                    elif depth == 1 and toks[j]['kind'] == 'token_type.keyword' and toks[j]['folded'] == 'as':
                        if as_idx is not None:
                            raise ValueError(f"Multiple AS clauses in {folded.upper()}")
                        as_idx = j
                if as_idx is None or close_idx is None:
                    raise ValueError(f"Incomplete {folded.upper()} in generated column")
                check_expr(owner_gen, toks[i + 2:as_idx])
                if not _validate_cast_target_tokens(toks[as_idx + 1:close_idx]):
                    raise ValueError(f"Unsupported cast target type in generated column {by_folded[owner_gen]!r}")
                i = close_idx + 1
                continue

            # Postfix ::TYPE cast
            if kind == 'token_type.operator' and raw == '::':
                j = i + 1
                if j >= len(toks) or toks[j]['folded'] not in _ADMITTED_CAST_TYPE_WORDS:
                    raise ValueError(f"Unsupported :: cast target in generated column {by_folded[owner_gen]!r}")
                j += 1
                if j < len(toks) and toks[j]['raw'] == '(':
                    depth = 1
                    j += 1
                    while j < len(toks) and depth > 0:
                        if toks[j]['raw'] == '(':
                            depth += 1
                        elif toks[j]['raw'] == ')':
                            depth -= 1
                        j += 1
                    if depth != 0:
                        raise ValueError('Unclosed :: cast type parameters')
                while j + 1 < len(toks) and toks[j]['raw'] == '[' and toks[j + 1]['raw'] == ']':
                    j += 2
                i = j
                continue

            # Strip DuckDB catalog/schema qualification (`system.main.fn(` or `main.fn(`) before function calls
            if (kind in {'token_type.identifier', 'token_type.keyword'} and
                    folded in {'system', 'main'}):
                if (i + 4 < len(toks) and folded == 'system' and
                        toks[i + 1]['raw'] == '.' and toks[i + 2]['folded'] == 'main' and
                        toks[i + 3]['raw'] == '.' and
                        i + 5 < len(toks) and toks[i + 5]['raw'] == '('):
                    i += 4
                    tok = toks[i]
                    kind, raw, folded = tok['kind'], tok['raw'], tok['folded']
                elif (i + 2 < len(toks) and folded == 'main' and
                        toks[i + 1]['raw'] == '.' and
                        i + 3 < len(toks) and toks[i + 3]['raw'] == '('):
                    i += 2
                    tok = toks[i]
                    kind, raw, folded = tok['kind'], tok['raw'], tok['folded']

            # Function call: ident/keyword followed by '('
            if (kind in {'token_type.identifier', 'token_type.keyword'} and
                    i + 1 < len(toks) and toks[i + 1]['raw'] == '(' and
                    folded not in {'case', 'when', 'then', 'else', 'in', 'and', 'or', 'not', 'between'}):
                if folded in _VOLATILE_OR_SIDE_EFFECT_FUNCTIONS:
                    raise ValueError(
                        f"Generated column expression uses volatile, sequence, or side-effectful function: {folded}"
                    )
                if folded not in _ADMITTED_DETERMINISTIC_FUNCTIONS:
                    raise ValueError(
                        f"Generated column expression uses unverified function: {folded}"
                    )
                depth, close_idx = 1, None
                for j in range(i + 2, len(toks)):
                    if toks[j]['raw'] == '(':
                        depth += 1
                    elif toks[j]['raw'] == ')':
                        depth -= 1
                        if depth == 0:
                            close_idx = j
                            break
                if close_idx is None:
                    raise ValueError(f"Unclosed call to {folded}() in generated column")
                arg_slice = toks[i + 2:close_idx]
                if arg_slice:
                    # struct_pack(a := expr, b := expr) named arguments support
                    args = _split_top_level_commas(arg_slice)
                    if args is None:
                        raise ValueError(f"Malformed arguments in {folded}()")
                    for arg in args:
                        if (len(arg) >= 3 and arg[1]['kind'] == 'token_type.operator' and
                                arg[1]['raw'] == ':='):
                            check_expr(owner_gen, arg[2:])
                        else:
                            check_expr(owner_gen, arg)
                i = close_idx + 1
                continue

            # Column reference or keyword
            if kind == 'token_type.identifier':
                # Allow struct dot-field access (base_col.field_name)
                if i > 0 and toks[i - 1]['raw'] == '.':
                    i += 1
                    continue
                if folded in base_folded:
                    i += 1
                    continue
                if folded in generated_expr_tokens:
                    if folded == owner_gen:
                        raise ValueError(
                            f"Generated column {by_folded[owner_gen]!r} cannot reference itself"
                        )
                    deps[owner_gen].add(folded)
                    i += 1
                    continue
                raise ValueError(
                    f"Generated column {by_folded[owner_gen]!r} references unknown identifier {tok['unquoted']!r}"
                )

            if kind == 'token_type.keyword':
                if folded in _VOLATILE_OR_SIDE_EFFECT_FUNCTIONS:
                    raise ValueError(
                        f"Generated column expression uses volatile keyword/function: {folded}"
                    )
                if folded not in {
                    'true', 'false', 'null', 'case', 'when', 'then', 'else', 'end',
                    'and', 'or', 'not', 'is', 'distinct', 'from', 'in', 'between',
                    'like', 'ilike', 'escape',
                }:
                    # Could be a column whose name is a non-reserved keyword if quoted or unquoted
                    if folded in base_folded:
                        i += 1
                        continue
                    if folded in generated_expr_tokens:
                        if folded == owner_gen:
                            raise ValueError('Generated columns contain a dependency cycle')
                        deps[owner_gen].add(folded)
                        i += 1
                        continue
                    raise ValueError(
                        f"Generated column expression contains unsupported SQL keyword: {folded}"
                    )
                i += 1
                continue

            if kind == 'token_type.operator':
                if raw not in {
                    '(', ')', '[', ']', ',', '.', '+', '-', '*', '/', '//', '%', '^',
                    '||', '=', '==', '!=', '<>', '<', '<=', '>', '>=', '&', '|', '~',
                    '<<', '>>',
                }:
                    raise ValueError(f"Generated column expression uses unsupported operator: {raw}")
                i += 1
                continue

            if kind in {'token_type.numeric_const', 'token_type.string_const'}:
                i += 1
                continue

            raise ValueError(f"Generated column expression contains unsupported token: {raw}")

    for gen_col, expr_toks in generated_expr_tokens.items():
        check_expr(gen_col, expr_toks)

    # Topological sort of generated-on-generated dependencies (Kahn's algorithm)
    in_degree = {g: len(deps[g]) for g in generated_expr_tokens}
    dependents: dict[str, list[str]] = {g: [] for g in generated_expr_tokens}
    for g, reqs in deps.items():
        for req in reqs:
            dependents[req].append(g)

    queue = deque(sorted(g for g, d in in_degree.items() if d == 0))
    topo_order: list[str] = []
    while queue:
        cur = queue.popleft()
        topo_order.append(by_folded[cur])
        for nxt in sorted(dependents[cur]):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    if len(topo_order) != len(generated_expr_tokens):
        raise ValueError('Generated columns contain a dependency cycle')

    return topo_order


def extract_sequence_references(default_expr: str | None, default_schema: str) -> list[tuple[str, str]]:
    """Extract all (schema, sequence_name) references from any nextval(...) calls in a DEFAULT expression (DU-AUD-15)."""
    if not isinstance(default_expr, str) or not default_expr.strip():
        return []
    if '\x00' in default_expr or len(default_expr.encode('utf8')) > 8192:
        raise ValueError('Column default exceeds 8 KiB or contains NUL')
    if any(marker in default_expr for marker in (';', '--', '/*', '*/')):
        raise ValueError('Column default cannot contain statement separators or comments')
    tokens = _tokenize_duckdb(default_expr)
    if tokens is None:
        raise ValueError('Column default could not be tokenized by DuckDB')
    refs: list[tuple[str, str]] = []
    for idx, tok in enumerate(tokens):
        if tok['folded'] == 'currval':
            raise ValueError('Column default cannot depend on session-volatile currval()')
        if tok['folded'] == 'nextval' and idx + 1 < len(tokens) and tokens[idx + 1]['raw'] == '(':
            if (idx + 3 >= len(tokens) or tokens[idx + 2]['kind'] != 'token_type.string_const' or
                    tokens[idx + 3]['raw'] != ')'):
                raise ValueError('nextval() in column default requires a literal sequence name')
            raw_lit = tokens[idx + 2]['raw']
            if len(raw_lit) < 2 or raw_lit[0] != "'" or raw_lit[-1] != "'":
                raise ValueError('nextval() sequence literal must be single-quoted')
            seq_spec = raw_lit[1:-1].replace("''", "'").strip()
            parts = [
                p[1:-1].replace('""', '"') if len(p) >= 2 and p[0] == '"' and p[-1] == '"' else p
                for p in seq_spec.split('.')
            ]
            if len(parts) == 1 and parts[0]:
                refs.append((default_schema, parts[0]))
            elif len(parts) == 2 and all(parts):
                refs.append((parts[0], parts[1]))
            elif len(parts) == 3 and all(parts):
                refs.append((parts[1], parts[2]))
            else:
                raise ValueError(f"Unsupported sequence target in nextval(): {seq_spec!r}")
    return refs


def _validate_bounded_sql_expr(expr: str, label: str) -> str:
    if (not isinstance(expr, str) or not expr.strip() or '\x00' in expr or
            len(expr.encode('utf8')) > 8192 or
            any(marker in expr for marker in (';', '--', '/*', '*/'))):
        raise ValueError(f"{label} must be one bounded SQL expression without comments or semicolons")
    import duckdb
    probe = 'SELECT ' + expr.strip()
    try:
        stmts = duckdb.extract_statements(probe)
    except duckdb.Error:
        raise ValueError(f"Native DuckDB parser rejected {label}") from None
    if len(stmts) != 1 or stmts[0].type != duckdb.StatementType.SELECT:
        raise ValueError(f"{label} must parse as a single scalar SQL expression")
    return expr.strip()


def _replayed_index_allow_tags(index: dict, table_target: str, *, allow_tag_loss: bool, lost_tags: list[dict]) -> str:
    from .duckdb_schema_plan import _validated_index_ddl
    import duckdb
    ddl = index['native'].get('ddl')
    if not isinstance(ddl, str) or not ddl or len(ddl.encode('utf8')) > 1024 * 1024:
        raise ValueError('Independent index has no bounded native definition to preserve')
    encoded = ddl.encode('utf8')
    try:
        tokens = duckdb.tokenize(ddl)
    except duckdb.Error:
        raise ValueError('Independent index definition cannot be tokenized') from None
    on = next((number for number, (offset, kind) in enumerate(tokens)
        if kind == duckdb.token_type.keyword and
        encoded[offset:tokens[number + 1][0] if number + 1 < len(tokens) else len(encoded)]
            .decode('utf8').strip().casefold() == 'on'), None)
    opening = next((offset for offset, kind in tokens[on + 1:]
        if kind == duckdb.token_type.operator and encoded[offset:offset + 1] == b'('), None) if on is not None else None
    if opening is None:
        raise ValueError('Independent index expression cannot be reconstructed')
    metadata = index['native'].get('catalog_metadata', {})
    if metadata.get('primary') or type(metadata.get('unique')) is not bool:
        raise ValueError('Independent index has unsupported native metadata')
    tags = metadata.get('tags')
    if tags:
        if not allow_tag_loss:
            raise ValueError(
                'Rebuilding or replacing an object with native catalog tags loses C++/extension tags in DuckDB 1.5.2; set tag_loss_acknowledged=True'
            )
        lost_tags.append({'resource_id': index['resource_id'], 'kind': 'index', 'tags': deepcopy(tags)})
    source = (
        'CREATE ' + ('UNIQUE ' if metadata['unique'] else '') + 'INDEX ' +
        _quote(index['name']) + ' ON ' + table_target + encoded[opening:].decode('utf8')
    )
    return _validated_index_ddl(source, index['path'])


def _strip_self_fk_from_ddl(ddl: str, table_name: str, target_qualified: str, stage_qualified: str) -> str:
    """Build a staging CREATE TABLE statement without self-referential FK clauses."""
    parsed = parse_create_table_clauses(ddl)
    if parsed is None:
        raise ValueError('Self-referential table DDL could not be parsed for staging')
    encoded = ddl.encode('utf8')
    tokens = _tokenize_duckdb(ddl)
    open_idx = next(i for i, t in enumerate(tokens) if t['raw'] == '(')
    inner = tokens[open_idx + 1:-1]
    clauses = _split_top_level_commas(inner)
    kept_slices: list[str] = []
    t_fold = table_name.casefold()
    for clause in clauses:
        first = clause[0]
        if (first['kind'] == 'token_type.keyword' and not first['quoted'] and
                first['folded'] in {'constraint', 'foreign'}):
            ref_idx = next(
                (i for i, t in enumerate(clause) if t['kind'] == 'token_type.keyword' and t['folded'] == 'references'),
                None,
            )
            if ref_idx is not None and ref_idx + 1 < len(clause):
                # Check if target table of REFERENCES is self
                ref_parts = []
                k = ref_idx + 1
                while k < len(clause) and clause[k]['raw'] != '(':
                    if clause[k]['raw'] != '.':
                        ref_parts.append(clause[k]['unquoted'].casefold())
                    k += 1
                if ref_parts and ref_parts[-1] == t_fold:
                    continue
        else:
            # Inline REFERENCES same_table(...) on a column definition
            ref_idx = next(
                (i for i, t in enumerate(clause) if t['kind'] == 'token_type.keyword' and t['folded'] == 'references'),
                None,
            )
            if ref_idx is not None and ref_idx + 1 < len(clause):
                ref_parts = []
                k = ref_idx + 1
                while k < len(clause) and clause[k]['raw'] != '(':
                    if clause[k]['raw'] != '.':
                        ref_parts.append(clause[k]['unquoted'].casefold())
                    k += 1
                if ref_parts and ref_parts[-1] == t_fold:
                    # Strip REFERENCES ... (...) from column clause
                    close_idx = ref_idx + 1
                    while close_idx < len(clause) and clause[close_idx]['raw'] != ')':
                        close_idx += 1
                    prefix_text = encoded[clause[0]['offset']:clause[ref_idx]['offset']].decode('utf8').strip()
                    suffix_text = (
                        encoded[clause[close_idx]['end']:clause[-1]['end']].decode('utf8').strip()
                        if close_idx + 1 < len(clause) else ''
                    )
                    kept_slices.append((prefix_text + (' ' + suffix_text if suffix_text else '')).strip())
                    continue
        kept_slices.append(encoded[clause[0]['offset']:clause[-1]['end']].decode('utf8').strip())
    return 'CREATE TABLE ' + stage_qualified + ' (' + ', '.join(kept_slices) + ')'


def build_macro_probe_queries(macro_row: dict) -> list[str]:
    """Build DESCRIBE queries for scalar/table macros, including typed same-arity & variadic overloads (DU-AUD-13)."""
    qualified = '.'.join(_quote(part) for part in macro_row['path'])
    overloads = macro_row['native'].get('overloads') or []
    queries: list[str] = []
    for overload in overloads:
        if not isinstance(overload, dict):
            raise ValueError('Macro overload metadata is incomplete')
        meta = overload.get('catalog_metadata', {})
        fn_type = meta.get('function_type')
        if fn_type not in {'macro', 'table_macro'}:
            raise ValueError('Unsupported macro function_type')
        if meta.get('has_side_effects') is not False:
            raise ValueError('Macro with side effects cannot be probed during table rebuild')
        params = overload.get('parameters') or []
        arg_exprs = []
        for param in params:
            dtype = param.get('data_type') if isinstance(param, dict) else None
            if isinstance(dtype, str) and dtype.strip() and dtype.strip().upper() != 'ANY':
                arg_exprs.append(f'CAST(NULL AS {dtype.strip()})')
            else:
                arg_exprs.append('NULL')
        prefix = 'DESCRIBE SELECT * FROM ' if fn_type == 'table_macro' else 'DESCRIBE SELECT '
        queries.append(f"{prefix}{qualified}({', '.join(arg_exprs)})")
        varargs = meta.get('varargs')
        if varargs is not None:
            v_arg = (
                f'CAST(NULL AS {varargs.strip()})'
                if isinstance(varargs, str) and varargs.strip() and varargs.strip().upper() != 'ANY'
                else 'NULL'
            )
            queries.append(f"{prefix}{qualified}({', '.join([*arg_exprs, v_arg])})")
    return queries


def _topological_inbound_children(
    parent_row: dict,
    inbound_specs: list[dict],
    live: dict,
) -> list[dict]:
    """Validate and order multi-hop inbound-on-child DAGs root-first (detach runs reversed, restore runs forward)."""
    by_id: dict[str, dict] = {}
    for spec in inbound_specs:
        if (not isinstance(spec, dict) or
                not isinstance(spec.get('resource_id'), str) or
                not isinstance(spec.get('intermediate_ddl'), str) or
                set(spec) - {
                    'resource_id', 'intermediate_ddl', 'column_renames',
                    'column_conversions',
                }):
            raise ValueError('Each inbound_children item requires resource_id and intermediate_ddl')
        cid = spec['resource_id']
        if cid in by_id:
            raise ValueError('Inbound review repeats a child identity')
        if cid == parent_row['resource_id']:
            raise ValueError('Self-referential foreign keys belong on the rebuilt table itself, not inbound_children')
        by_id[cid] = spec

    # Build dependency graph among inbound children: edge U -> V if V has FK referencing U
    # (U is closer to parent_row; V is grandchild).
    parent_schema = tuple(parent_row['path'][:2])
    name_to_id: dict[str, str] = {}
    for cid in by_id:
        crow = live['rows'].get(cid)
        if crow is None or crow['kind'] != 'table':
            raise ValueError(f'Inbound child {cid!r} is absent from live catalog')
        if tuple(crow['path'][:2]) != parent_schema:
            raise ValueError('DuckDB 1.5.2 does not support foreign keys across schemas or catalogs')
        name_to_id[crow['name']] = cid

    deps: dict[str, set[str]] = {cid: set() for cid in by_id}
    reaches_root: dict[str, bool] = {cid: False for cid in by_id}
    for cid in by_id:
        crow = live['rows'][cid]
        fks = [
            c for c in crow['native'].get('constraints', [])
            if isinstance(c, dict) and c.get('constraint_type') == 'FOREIGN KEY'
        ]
        for fk in fks:
            ref = fk.get('referenced_table')
            if not isinstance(ref, str) or not ref:
                raise ValueError('Inbound child has malformed foreign key target')
            if '.' in ref:
                raise ValueError('DuckDB 1.5.2 does not support foreign keys across schemas or catalogs')
            if ref == crow['name']:
                continue
            if ref == parent_row['name']:
                reaches_root[cid] = True
            elif ref in name_to_id:
                deps[cid].add(name_to_id[ref])

    # Kahn's algorithm from parent_row outward (root-first order)
    in_deg = {cid: len(deps[cid]) for cid in by_id}
    children_of: dict[str, list[str]] = {cid: [] for cid in by_id}
    for cid, parents in deps.items():
        for p in parents:
            children_of[p].append(cid)

    queue = deque(sorted(cid for cid, d in in_deg.items() if d == 0))
    root_first: list[str] = []
    while queue:
        cur = queue.popleft()
        if not reaches_root[cur] and not any(reaches_root[p] for p in deps[cur]):
            raise ValueError(
                f"Inbound child {live['rows'][cur]['name']!r} does not depend on the rebuilt table"
            )
        reaches_root[cur] = True
        root_first.append(cur)
        for nxt in sorted(children_of[cur]):
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                queue.append(nxt)

    if len(root_first) != len(by_id):
        raise ValueError('Mutual foreign-key cycle among separate inbound tables cannot be ordered sequentially')

    return [by_id[cid] for cid in root_first]


def validate_general_table_rebuild(before, after, change, target, baseline, live, desired):
    """Plan a full safe staged whole-table transformation (`action: 'rebuild-table-general'`)."""
    from .duckdb_schema_plan import (
        _definition, _fk_parent_definition, _native_column_type,
        _validated_ddl, _validated_replayed_comment,
    )

    allowed_change_keys = {
        'action', 'complete_definition_confirmed', 'preserve_rows_confirmed',
        'drop_column_ids', 'discard_columns_confirmed',
        'column_renames', 'column_conversions', 'loss_acknowledged',
        'added_column_fills', 'tag_loss_acknowledged',
        'inbound_children', 'updated_views', 'updated_macros',
    }
    if (not isinstance(change, dict) or
            change.get('action') != 'rebuild-table-general' or
            set(change) - allowed_change_keys or
            change.get('complete_definition_confirmed') is not True or
            change.get('preserve_rows_confirmed') is not True):
        raise ValueError(
            'General table rebuild requires complete_definition_confirmed=True and preserve_rows_confirmed=True'
        )

    allow_tag_loss = change.get('tag_loss_acknowledged') is True
    lost_tags: list[dict] = []

    before_meta = before['native'].get('catalog_metadata', {})
    after_meta = after['native'].get('catalog_metadata', {})
    if before_meta.get('tags'):
        if not allow_tag_loss:
            raise ValueError(
                'Rebuilding or replacing an object with native catalog tags loses C++/extension tags in DuckDB 1.5.2; set tag_loss_acknowledged=True'
            )
        lost_tags.append({'resource_id': before['resource_id'], 'kind': 'table', 'tags': deepcopy(before_meta['tags'])})
    if after_meta.get('tags'):
        raise ValueError('DuckDB 1.5.2 SQL DDL cannot create native C++ catalog tags on rebuilt tables')

    # Never admit CREATE OR REPLACE TABLE (DU-AUD-09)
    desired_ddl = _validated_ddl(after['native'].get('ddl'), 'table', after['path'], replace=False)

    old_cols = before['native'].get('columns')
    new_cols = after['native'].get('columns')
    if (not isinstance(old_cols, list) or not isinstance(new_cols, list) or
            not 1 <= len(old_cols) <= _MAX_REBUILD_COLUMNS or
            not 1 <= len(new_cols) <= _MAX_REBUILD_COLUMNS):
        raise ValueError('General table rebuild requires bounded non-empty column metadata')

    for pos, col in enumerate(new_cols, 1):
        if (not isinstance(col, dict) or not isinstance(col.get('name'), str) or
                col.get('ordinal_position') != pos or type(col.get('nullable')) is not bool):
            raise ValueError('Desired columns must carry contiguous ordinal_position and Boolean nullable')
        _native_column_type(col.get('data_type'))

    old_by_name = {c['name']: c for c in old_cols}
    new_by_name = {c['name']: c for c in new_cols}
    if len(old_by_name) != len(old_cols) or len(new_by_name) != len(new_cols):
        raise ValueError('Duplicate column names in table rebuild')

    # Validate generated columns on both baseline and desired (DU-AUD-10)
    old_generated = set(validate_general_generated_columns(before['native'].get('ddl', ''), old_cols))
    new_generated_order = validate_general_generated_columns(desired_ddl, new_cols)
    new_generated = set(new_generated_order)

    # Column renames: old_name -> new_name
    renames = change.get('column_renames') or {}
    if not isinstance(renames, dict):
        raise ValueError('column_renames must map baseline column names to desired column names')
    reverse_renames: dict[str, str] = {}
    for old_n, new_n in renames.items():
        if (not isinstance(old_n, str) or not isinstance(new_n, str) or
                old_n not in old_by_name or new_n not in new_by_name or
                old_n == new_n or new_n in old_by_name or new_n in reverse_renames):
            raise ValueError('column_renames must map distinct existing baseline columns to new desired columns')
        reverse_renames[new_n] = old_n

    # Dropped columns check
    retained_old_names = {reverse_renames.get(name, name) for name in new_by_name if reverse_renames.get(name, name) in old_by_name}
    dropped_old_names = set(old_by_name) - retained_old_names
    expected_drop_ids = sorted(
        old_by_name[n]['resource_id'] for n in dropped_old_names
    )
    if dropped_old_names:
        if (change.get('discard_columns_confirmed') is not True or
                change.get('drop_column_ids') != expected_drop_ids):
            raise ValueError(
                'Dropping columns in general rebuild requires discard_columns_confirmed=True and exact sorted drop_column_ids'
            )
    elif 'drop_column_ids' in change or 'discard_columns_confirmed' in change:
        raise ValueError('Do not supply drop_column_ids when no columns are dropped')

    # Column conversions & type changes (DU-AUD-09)
    conversions = change.get('column_conversions') or {}
    if not isinstance(conversions, dict):
        raise ValueError('column_conversions must be a mapping of desired column name to SQL expression')
    fills = change.get('added_column_fills') or {}
    if not isinstance(fills, dict):
        raise ValueError('added_column_fills must be a mapping of added column name to SQL expression')
    for cname in conversions:
        if cname not in new_by_name or cname in new_generated:
            raise ValueError(f'column_conversions references unknown or generated column {cname!r}')
    for cname in fills:
        if cname not in new_by_name or cname in new_generated or reverse_renames.get(cname, cname) in old_by_name:
            raise ValueError(f'added_column_fills must target an added base column, got {cname!r}')

    select_pairs: list[tuple[str, str]] = []
    any_type_change = False
    sequence_refs: list[tuple[str, str]] = []
    schema_name = after['path'][1]

    for col in new_cols:
        cname = col['name']
        if cname in new_generated:
            continue
        default_expr = col.get('default')
        if default_expr is not None:
            _validate_bounded_sql_expr(default_expr, f"DEFAULT for column {cname!r}")
            sequence_refs.extend(extract_sequence_references(default_expr, schema_name))

        src_old_name = reverse_renames.get(cname, cname if cname in old_by_name else None)
        if src_old_name is not None and src_old_name not in old_generated:
            old_col = old_by_name[src_old_name]
            type_changed = old_col.get('data_type') != col.get('data_type')
            if type_changed:
                any_type_change = True
                if cname not in conversions or change.get('loss_acknowledged') is not True:
                    raise ValueError(
                        f"Column {cname!r} changes type ({old_col.get('data_type')} -> {col.get('data_type')}); "
                        "explicit column_conversions expression and loss_acknowledged=True are required"
                    )
            if cname in conversions:
                expr = _validate_bounded_sql_expr(conversions[cname], f"conversion for {cname!r}")
                select_pairs.append((cname, expr))
            else:
                select_pairs.append((cname, _quote(src_old_name)))
        else:
            # Added base column (or converted from former generated column)
            if cname in conversions:
                expr = _validate_bounded_sql_expr(conversions[cname], f"conversion for {cname!r}")
                select_pairs.append((cname, expr))
            elif cname in fills:
                expr = _validate_bounded_sql_expr(fills[cname], f"fill expression for {cname!r}")
                select_pairs.append((cname, expr))
            elif default_expr is not None:
                # If default references a sequence, only omit from INSERT when nullable is False and user wants sequence;
                # to avoid advancing sequences on existing rows, require explicit fill if NOT NULL + sequence default!
                if extract_sequence_references(default_expr, schema_name):
                    if col.get('nullable') is False:
                        raise ValueError(
                            f"Added NOT NULL column {cname!r} has a sequence default; provide added_column_fills to populate existing rows without advancing the sequence during staging"
                        )
                    select_pairs.append((cname, 'NULL'))
                else:
                    select_pairs.append((cname, default_expr))
            elif col.get('nullable') is False:
                raise ValueError(
                    f"Added NOT NULL column {cname!r} requires a DEFAULT or added_column_fills expression"
                )
            else:
                select_pairs.append((cname, 'NULL'))

    if not select_pairs:
        raise ValueError('General table rebuild requires at least one base column')
    if (conversions and not any_type_change and change.get('loss_acknowledged') is not True):
        raise ValueError('Custom column_conversions require loss_acknowledged=True')

    # Verify all referenced sequences exist in desired/live catalog (DU-AUD-15)
    catalog_name = after['path'][0]
    verified_seq_ids: list[str] = []
    for seq_schema, seq_name in sequence_refs:
        seq_id = _resource_id('sequence', [catalog_name, seq_schema], seq_name)
        if seq_id not in live['rows'] and seq_id not in desired['rows']:
            raise ValueError(f"Default expression references unobserved sequence {seq_schema}.{seq_name}")
        verified_seq_ids.append(seq_id)

    # Validate constraints & explicit NOT NULL / PRIMARY KEY invariants (DU-AUD-11)
    old_constraints = before['native'].get('constraints')
    new_constraints = after['native'].get('constraints')
    if not isinstance(old_constraints, list) or not isinstance(new_constraints, list):
        raise ValueError('General table rebuild requires complete constraint lists')

    pk_cons = [c for c in new_constraints if isinstance(c, dict) and c.get('constraint_type') == 'PRIMARY KEY']
    nn_cons = [c for c in new_constraints if isinstance(c, dict) and c.get('constraint_type') == 'NOT NULL']
    fk_cons = [c for c in new_constraints if isinstance(c, dict) and c.get('constraint_type') == 'FOREIGN KEY']
    uq_cons = [c for c in new_constraints if isinstance(c, dict) and c.get('constraint_type') == 'UNIQUE']
    ck_cons = [c for c in new_constraints if isinstance(c, dict) and c.get('constraint_type') == 'CHECK']

    if (len(pk_cons) > 1 or
            len(pk_cons) + len(nn_cons) + len(fk_cons) + len(uq_cons) + len(ck_cons) != len(new_constraints) or
            after_meta.get('has_primary_key') is not bool(pk_cons)):
        raise ValueError('Desired PRIMARY KEY / constraint metadata is inconsistent')

    pk_cols = pk_cons[0].get('column_names') if pk_cons else []
    if pk_cons and (not isinstance(pk_cols, list) or not pk_cols or len(set(pk_cols)) != len(pk_cols)):
        raise ValueError('Desired PRIMARY KEY must name distinct columns')

    expected_not_null_cols = {c['name'] for c in new_cols if c.get('nullable') is False}
    if not set(pk_cols) <= expected_not_null_cols:
        raise ValueError('Every PRIMARY KEY column must have nullable=False')
    observed_nn_cols = set()
    for nn in nn_cons:
        cnames = nn.get('column_names')
        if not isinstance(cnames, list) or len(cnames) != 1 or cnames[0] in observed_nn_cols:
            raise ValueError('Each NOT NULL constraint row must cover one distinct non-nullable column')
        observed_nn_cols.add(cnames[0])
    if observed_nn_cols != expected_not_null_cols:
        raise ValueError('Desired NOT NULL constraint rows must match all columns with nullable=False')

    # Outbound FK validation (including self-FK & cross-schema refusal — DU-AUD-12)
    fk_parents: dict[str, str] = {}
    self_fks = []
    for fk in fk_cons:
        ref_tbl = fk.get('referenced_table')
        if not isinstance(ref_tbl, str) or not ref_tbl:
            raise ValueError('Foreign key constraint requires referenced_table')
        if '.' in ref_tbl:
            raise ValueError('DuckDB 1.5.2 does not support foreign keys across schemas or catalogs')
        if ref_tbl == after['name']:
            self_fks.append(fk)
            continue
        parent_path = [catalog_name, schema_name, ref_tbl]
        parent_id = _resource_id('table', parent_path[:2], ref_tbl)
        p_rows = [m['rows'].get(parent_id) for m in (baseline, live, desired)]
        if (any(r is None or r['kind'] != 'table' or r['path'] != parent_path for r in p_rows) or
                any(not _equal(_fk_parent_definition(p_rows[0]), _fk_parent_definition(r)) for r in p_rows[1:])):
            raise ValueError(f'Outbound foreign-key parent {ref_tbl!r} is missing, cross-schema, or concurrently modified')
        fk_parents[parent_id] = digest(_fk_parent_definition(p_rows[0]))

    # Independent indexes on rebuilt parent (unchanged, added, modified, or dropped — DU-AUD-14)
    old_indexes = sorted(
        (r for r in live['rows'].values() if r['kind'] == 'index' and r.get('path', [])[:3] == before['path']),
        key=lambda r: r['resource_id'],
    )
    new_indexes = sorted(
        (r for r in desired['rows'].values() if r['kind'] == 'index' and r.get('path', [])[:3] == after['path']),
        key=lambda r: r['resource_id'],
    )
    for old_idx in old_indexes:
        if old_idx['resource_id'] not in {r['resource_id'] for r in new_indexes}:
            idx_tags = old_idx['native'].get('catalog_metadata', {}).get('tags')
            if idx_tags:
                if not allow_tag_loss:
                    raise ValueError(
                        'Rebuilding or replacing an object with native catalog tags loses C++/extension tags in DuckDB 1.5.2; set tag_loss_acknowledged=True'
                    )
                lost_tags.append({'resource_id': old_idx['resource_id'], 'kind': 'index', 'tags': deepcopy(idx_tags)})

    # Multi-hop inbound children DAG (DU-AUD-12 & DU-AUD-14)
    inbound_specs_raw = change.get('inbound_children') or []
    if not isinstance(inbound_specs_raw, list) or len(inbound_specs_raw) > 63:
        raise ValueError('inbound_children must be a list of at most 63 child specifications')
    ordered_inbound_specs = (
        _topological_inbound_children(before, inbound_specs_raw, live)
        if inbound_specs_raw else []
    )
    inbound_id_set = {s['resource_id'] for s in ordered_inbound_specs}

    # Check that no UNDECLARED table in the catalog holds an inbound FK to before or to any inbound child
    protected_names = {(before['path'][1], before['name'])} | {
        (live['rows'][cid]['path'][1], live['rows'][cid]['name']) for cid in inbound_id_set
    }
    for row in live['rows'].values():
        if row['kind'] != 'table' or row['resource_id'] == before['resource_id'] or row['resource_id'] in inbound_id_set:
            continue
        for c in row['native'].get('constraints', []):
            if c.get('constraint_type') == 'FOREIGN KEY':
                if (row['path'][1], c.get('referenced_table')) in protected_names:
                    raise ValueError(
                        f"Table {row['name']!r} has an inbound foreign key to a rebuilt table and must be included in inbound_children"
                    )

    # Build detach (leaf-first) and restore (root-first) plans for inbound children
    detach_plans: list[dict] = []
    restore_plans: list[dict] = []
    affected_inbound_rows_baseline: dict[str, dict] = {}
    affected_inbound_rows_desired: dict[str, dict] = {}

    for spec in ordered_inbound_specs:
        cid = spec['resource_id']
        c_base = baseline['rows'].get(cid)
        c_live = live['rows'].get(cid)
        c_des = desired['rows'].get(cid)
        if (c_base is None or c_live is None or c_des is None or
                not _equal(_definition(c_base), _definition(c_live))):
            raise ValueError(f'Inbound child {cid!r} changed since baseline or is missing')
        c_meta = c_live['native'].get('catalog_metadata', {})
        if c_meta.get('tags'):
            if not allow_tag_loss:
                raise ValueError(
                    'Rebuilding or replacing an object with native catalog tags loses C++/extension tags in DuckDB 1.5.2; set tag_loss_acknowledged=True'
                )
            lost_tags.append({'resource_id': cid, 'kind': 'table', 'tags': deepcopy(c_meta['tags'])})

        c_target = '.'.join(_quote(p) for p in c_live['path'])
        interim_ddl = _validated_ddl(spec['intermediate_ddl'], 'table', c_live['path'], replace=False)
        final_raw_ddl = c_des['native'].get('ddl') or ''
        # Qualify child restore DDL if captured unqualified
        if not re.match(r'^\s*CREATE\s+TABLE\s+' + re.escape(c_target), final_raw_ddl, re.I):
            unqual_m = re.match(
                r'^\s*CREATE\s+TABLE\s+(?:' + re.escape(c_live['name']) + '|' + re.escape(_quote(c_live['name'])) + r')(?=\s*\()',
                final_raw_ddl, re.I,
            )
            if unqual_m is None:
                raise ValueError(f"Inbound child {c_live['name']!r} desired DDL cannot be qualified")
            final_ddl = 'CREATE TABLE ' + c_target + final_raw_ddl[unqual_m.end():]
        else:
            final_ddl = final_raw_ddl
        final_ddl = _validated_ddl(final_ddl, 'table', c_des['path'], replace=False)

        c_old_cols = c_live['native'].get('columns') or []
        c_new_cols = c_des['native'].get('columns') or []
        c_old_gen = set(validate_general_generated_columns(c_live['native'].get('ddl', ''), c_old_cols))
        c_new_gen = set(validate_general_generated_columns(final_ddl, c_new_cols))
        for dc in c_new_cols:
            if dc.get('default') is not None:
                sequence_refs.extend(extract_sequence_references(dc['default'], c_des['path'][1]))

        # Secondary FK parents outside rebuild set
        for fk in c_des['native'].get('constraints', []):
            if fk.get('constraint_type') == 'FOREIGN KEY':
                rt = fk.get('referenced_table')
                if not rt or '.' in rt:
                    raise ValueError('DuckDB 1.5.2 does not support foreign keys across schemas or catalogs')
                if rt != c_des['name'] and (c_des['path'][1], rt) not in protected_names:
                    sec_id = _resource_id('table', c_des['path'][:2], rt)
                    sec_rows = [m['rows'].get(sec_id) for m in (baseline, live, desired)]
                    if (any(r is None or r['kind'] != 'table' for r in sec_rows) or
                            any(not _equal(_fk_parent_definition(sec_rows[0]), _fk_parent_definition(r)) for r in sec_rows[1:])):
                        raise ValueError(f'Secondary foreign-key parent {rt!r} is missing or modified')
                    fk_parents[sec_id] = digest(_fk_parent_definition(sec_rows[0]))

        s_detach = '__sr_inb_det_' + digest(interim_ddl + cid)[:16]
        s_restore = '__sr_inb_res_' + digest(final_ddl + cid)[:16]
        s_det_qual = '.'.join(_quote(p) for p in [*c_live['path'][:2], s_detach])
        s_res_qual = '.'.join(_quote(p) for p in [*c_des['path'][:2], s_restore])

        det_prefix = re.match(r'^\s*CREATE\s+TABLE\s+' + re.escape(c_target), interim_ddl, re.I)
        res_prefix = re.match(r'^\s*CREATE\s+TABLE\s+' + re.escape(c_target), final_ddl, re.I)
        det_create = 'CREATE TABLE ' + s_det_qual + interim_ddl[det_prefix.end():]
        res_create = 'CREATE TABLE ' + s_res_qual + final_ddl[res_prefix.end():]

        det_copy_cols = [_quote(c['name']) for c in c_old_cols if c['name'] not in c_old_gen]
        det_all_cols = ', '.join(_quote(c['name']) for c in c_old_cols)

        c_renames = spec.get('column_renames') or {}
        c_convs = spec.get('column_conversions') or {}
        c_rev_ren = {v: k for k, v in c_renames.items()}
        res_dst_cols, res_src_exprs = [], []
        for dc in c_new_cols:
            if dc['name'] in c_new_gen:
                continue
            res_dst_cols.append(_quote(dc['name']))
            if dc['name'] in c_convs:
                res_src_exprs.append(_validate_bounded_sql_expr(c_convs[dc['name']], f"child conversion {dc['name']!r}"))
            else:
                orig_n = c_rev_ren.get(dc['name'], dc['name'])
                res_src_exprs.append(_quote(orig_n))
        res_all_cols = ', '.join(_quote(c['name']) for c in c_new_cols)

        # Replay all child indexes (including UNIQUE, expression, and commented indexes! — DU-AUD-14)
        c_indexes = sorted(
            (r for r in desired['rows'].values() if r['kind'] == 'index' and r.get('path', [])[:3] == c_des['path']),
            key=lambda r: r['resource_id'],
        )
        c_index_sql = [
            _replayed_index_allow_tags(idx, c_target, allow_tag_loss=allow_tag_loss, lost_tags=lost_tags)
            for idx in c_indexes
        ]
        c_comment_sql = []
        for c_kind, c_tgt, c_txt in [
            ('table', c_target, c_des['native'].get('catalog_metadata', {}).get('comment')),
            *(('column', c_target + '.' + _quote(col['name']), col.get('comment')) for col in c_new_cols),
            *(
                ('index', '.'.join(_quote(p) for p in [idx['path'][0], idx['path'][1], idx['name']]),
                 idx['native'].get('catalog_metadata', {}).get('comment'))
                for idx in c_indexes
            ),
        ]:
            rep = _validated_replayed_comment(c_kind, c_tgt, c_txt)
            if rep is not None:
                c_comment_sql.append(rep)

        det_stmts = [
            det_create,
            f"INSERT INTO {s_det_qual} ({', '.join(det_copy_cols)}) SELECT {', '.join(det_copy_cols)} FROM {c_target}",
            f"DROP TABLE {c_target} RESTRICT",
            f"ALTER TABLE {s_det_qual} RENAME TO {_quote(c_live['name'])}",
        ]
        det_check = (
            f"SELECT count(*) FROM ((SELECT {det_all_cols} FROM {c_target} EXCEPT ALL SELECT {det_all_cols} FROM {s_det_qual}) "
            f"UNION ALL (SELECT {det_all_cols} FROM {s_det_qual} EXCEPT ALL SELECT {det_all_cols} FROM {c_target})) AS diff"
        )
        res_stmts = [
            res_create,
            f"INSERT INTO {s_res_qual} ({', '.join(res_dst_cols)}) SELECT {', '.join(res_src_exprs)} FROM {c_target}",
            f"DROP TABLE {c_target} RESTRICT",
            f"ALTER TABLE {s_res_qual} RENAME TO {_quote(c_des['name'])}",
            *c_index_sql,
            *c_comment_sql,
        ]
        res_check = f"SELECT abs((SELECT count(*) FROM {c_target}) - (SELECT count(*) FROM {s_res_qual}))"

        detach_plans.append({
            'child_resource_id': cid,
            'target': c_target,
            'stage_name': s_detach,
            'statements': det_stmts,
            'copy_check_index': 1,
            'data_check': det_check,
        })
        restore_plans.append({
            'child_resource_id': cid,
            'target': c_target,
            'stage_name': s_restore,
            'statements': res_stmts,
            'copy_check_index': 1,
            'data_check': res_check,
        })

        # Track baseline/desired rows for child and all its descendants
        for key, r in baseline['rows'].items():
            if key == cid or (r['kind'] in {'column', 'constraint', 'index'} and r.get('path', [])[:3] == c_live['path']):
                affected_inbound_rows_baseline[key] = r
        for key, r in desired['rows'].items():
            if key == cid or (r['kind'] in {'column', 'constraint', 'index'} and r.get('path', [])[:3] == c_des['path']):
                affected_inbound_rows_desired[key] = r

    # Detach leaf-first (reverse of root-first!)
    detach_plans.reverse()

    # Views & Macros preservation + co-updates (DU-AUD-13)
    updated_view_ids = set(change.get('updated_views') or [])
    updated_macro_specs = {
        item['resource_id']: item
        for item in (change.get('updated_macros') or [])
        if isinstance(item, dict) and isinstance(item.get('resource_id'), str)
    }

    preserved_views: list[dict] = []
    co_updated_view_ops: list[dict] = []
    for row in sorted(live['rows'].values(), key=lambda r: r['resource_id']):
        if row['kind'] != 'view' or row['system'] != 'false':
            continue
        if row['native'].get('catalog_metadata', {}).get('temporary'):
            raise ValueError('Temporary views cannot be preserved by an independent file migration')
        vid = row['resource_id']
        v_base = baseline['rows'].get(vid)
        v_des = desired['rows'].get(vid)
        if v_base is None or v_des is None or not _equal(_definition(v_base), _definition(row)):
            raise ValueError(f"View {row['name']!r} is missing or changed since baseline")
        if vid in updated_view_ids:
            v_tags = row['native'].get('catalog_metadata', {}).get('tags')
            if v_tags:
                if not allow_tag_loss:
                    raise ValueError(
                        'Rebuilding or replacing an object with native catalog tags loses C++/extension tags in DuckDB 1.5.2; set tag_loss_acknowledged=True'
                    )
                lost_tags.append({'resource_id': vid, 'kind': 'view', 'tags': deepcopy(v_tags)})
            v_target = '.'.join(_quote(p) for p in v_des['path'])
            v_ddl = _validated_ddl(v_des['native'].get('ddl'), 'view', v_des['path'], replace=True)
            v_replays = []
            vc = _validated_replayed_comment('view', v_target, v_des['native'].get('catalog_metadata', {}).get('comment'))
            if vc is not None:
                v_replays.append(vc)
            for vcol in v_des['native'].get('columns') or []:
                cc = _validated_replayed_comment('column', v_target + '.' + _quote(vcol['name']), vcol.get('comment'))
                if cc is not None:
                    v_replays.append(cc)
            co_updated_view_ops.append({
                'resource_id': vid,
                'target': v_target,
                'statements': [v_ddl, *v_replays],
            })
        else:
            if not _equal(_definition(v_des), _definition(row)):
                raise ValueError(
                    f"View {row['name']!r} changed in desired catalog; include its resource_id in updated_views"
                )
            preserved_views.append(row)

    preserved_macros: list[dict] = []
    co_updated_macro_ops: list[dict] = []
    for row in sorted(live['rows'].values(), key=lambda r: r['resource_id']):
        if row['kind'] != 'macro' or row['system'] != 'false':
            continue
        mid = row['resource_id']
        m_base = baseline['rows'].get(mid)
        m_des = desired['rows'].get(mid)
        if m_base is None or m_des is None or not _equal(_definition(m_base), _definition(row)):
            raise ValueError(f"Macro {row['name']!r} is missing or changed since baseline")
        if mid in updated_macro_specs:
            mspec = updated_macro_specs[mid]
            m_tags = row['native'].get('catalog_metadata', {}).get('tags')
            if m_tags:
                if not allow_tag_loss:
                    raise ValueError(
                        'Rebuilding or replacing an object with native catalog tags loses C++/extension tags in DuckDB 1.5.2; set tag_loss_acknowledged=True'
                    )
                lost_tags.append({'resource_id': mid, 'kind': 'macro', 'tags': deepcopy(m_tags)})
            m_target = '.'.join(_quote(p) for p in m_des['path'])
            m_sql = _validated_ddl(mspec.get('source'), 'macro', m_des['path'], replace=True)
            m_stmts = [m_sql]
            mc = _validated_replayed_comment('macro', m_target, m_des['native'].get('catalog_metadata', {}).get('comment'))
            if mc is not None:
                m_stmts.append(mc)
            co_updated_macro_ops.append({
                'resource_id': mid,
                'target': m_target,
                'statements': m_stmts,
                'probes': build_macro_probe_queries(m_des),
            })
        else:
            if not _equal(_definition(m_des), _definition(row)):
                raise ValueError(
                    f"Macro {row['name']!r} changed in desired catalog; include it in updated_macros"
                )
            # Validate probes can be constructed (supports variadic & same-arity typed overloads!)
            build_macro_probe_queries(row)
            preserved_macros.append(row)

    # Parent staging & swap statements
    stage_name = '__scratchrobin_gen_' + digest(desired_ddl)[:16]
    stage_path = [*after['path'][:2], stage_name]
    if _resource_id('table', stage_path[:2], stage_name) in live['rows']:
        raise ValueError('General rebuild staging table name collides with an existing table')
    stage_qual = '.'.join(_quote(p) for p in stage_path)

    dst_col_sql = ', '.join(_quote(c) for c, _ in select_pairs)
    src_expr_sql = ', '.join(e for _, e in select_pairs)

    if self_fks:
        # Self-FK safe pattern:
        # 1. Stage without self-FK so bulk INSERT SELECT succeeds in one batch,
        # 2. DROP original table,
        # 3. CREATE final table directly under final name (so DuckDB binds self-FK to final name, not stage!),
        # 4. Hierarchical level-by-level copy handled by executor hook, then DROP stage!
        stage_create = _strip_self_fk_from_ddl(desired_ddl, after['name'], target, stage_qual)
        _validated_ddl(stage_create, 'table', stage_path, replace=False)
        parent_core_stmts = [
            stage_create,
            f'INSERT INTO {stage_qual} ({dst_col_sql}) SELECT {src_expr_sql} FROM {target}',
            f'DROP TABLE {target} RESTRICT',
            desired_ddl,
        ]
        self_fk_spec = {
            'stage_qualified': stage_qual,
            'target_qualified': target,
            'base_columns': [c for c, _ in select_pairs],
            'self_fks': [
                {
                    'column_names': fk['column_names'],
                    'referenced_column_names': fk['referenced_column_names'],
                }
                for fk in self_fks
            ],
        }
    else:
        src_prefix = re.match(r'^\s*CREATE\s+TABLE\s+' + re.escape(target), desired_ddl, re.I)
        stage_create = 'CREATE TABLE ' + stage_qual + desired_ddl[src_prefix.end():]
        _validated_ddl(stage_create, 'table', stage_path, replace=False)
        parent_core_stmts = [
            stage_create,
            f'INSERT INTO {stage_qual} ({dst_col_sql}) SELECT {src_expr_sql} FROM {target}',
            f'DROP TABLE {target} RESTRICT',
            f'ALTER TABLE {stage_qual} RENAME TO {_quote(after["name"])}',
        ]
        self_fk_spec = None

    # Replay desired parent indexes & comments
    parent_tail_stmts: list[str] = []
    for idx in new_indexes:
        parent_tail_stmts.append(
            _replayed_index_allow_tags(idx, target, allow_tag_loss=allow_tag_loss, lost_tags=lost_tags)
        )
    for c_kind, c_tgt, c_txt in [
        ('table', target, after_meta.get('comment')),
        *(('column', target + '.' + _quote(col['name']), col.get('comment')) for col in new_cols),
        *(
            ('index', '.'.join(_quote(p) for p in [idx['path'][0], idx['path'][1], idx['name']]),
             idx['native'].get('catalog_metadata', {}).get('comment'))
            for idx in new_indexes
        ),
    ]:
        rep = _validated_replayed_comment(c_kind, c_tgt, c_txt)
        if rep is not None:
            parent_tail_stmts.append(rep)

    # Assemble complete statement sequence:
    # [detach leaf-first] -> [parent core] -> ([self-FK copy + DROP stage] if self_fk) -> [parent indexes/comments]
    # -> [restore root-first] -> [co-updated views] -> [co-updated macros]
    all_statements: list[str] = []
    detach_steps = []
    for dp in detach_plans:
        base_offset = len(all_statements)
        all_statements.extend(dp['statements'])
        detach_steps.append({**dp, 'copy_statement_index': base_offset + dp['copy_check_index']})

    parent_start_index = len(all_statements)
    all_statements.extend(parent_core_stmts)
    parent_stage_copy_index = parent_start_index + 1
    self_fk_trigger_index = (len(all_statements) - 1) if self_fk_spec is not None else None
    all_statements.extend(parent_tail_stmts)

    restore_steps = []
    for rp in restore_plans:
        base_offset = len(all_statements)
        all_statements.extend(rp['statements'])
        restore_steps.append({**rp, 'copy_statement_index': base_offset + rp['copy_check_index']})

    for vop in co_updated_view_ops:
        all_statements.extend(vop['statements'])
    for mop in co_updated_macro_ops:
        all_statements.extend(mop['statements'])

    # Validate every generated statement through DuckDB's native parser
    import duckdb
    for stmt in all_statements:
        try:
            parsed_stmt = duckdb.extract_statements(stmt)
        except duckdb.Error:
            raise ValueError(f'Native DuckDB parser rejected generated rebuild statement: {stmt[:120]}') from None
        if len(parsed_stmt) != 1:
            raise ValueError('Every rebuild step must be one exact DuckDB SQL statement')

    # Column and constraint tracking hashes for durable review
    old_col_rows = {
        r['resource_id']: r for r in baseline['rows'].values()
        if r['kind'] == 'column' and r.get('path', [])[:3] == before['path']
    }
    new_col_rows = {
        r['resource_id']: r for r in desired['rows'].values()
        if r['kind'] == 'column' and r.get('path', [])[:3] == after['path']
    }
    if {r['name']: r['native'].get('catalog_metadata') for r in new_col_rows.values()} != {
        c['name']: {k: v for k, v in c.items() if k not in {'resource_id', 'name'}}
        for c in new_cols
    }:
        raise ValueError('General rebuild child column rows differ from desired table columns')

    old_con_rows = {
        r['resource_id']: r for r in baseline['rows'].values()
        if r['kind'] == 'constraint' and r.get('path', [])[:3] == before['path']
    }
    new_con_rows = {
        r['resource_id']: r for r in desired['rows'].values()
        if r['kind'] == 'constraint' and r.get('path', [])[:3] == after['path']
    }
    if set(new_con_rows) != {c.get('resource_id') for c in new_constraints}:
        raise ValueError('General rebuild child constraint rows differ from desired table constraints')

    parent_stage_check = (
        f"SELECT abs((SELECT count(*) FROM {target}) - (SELECT count(*) FROM {stage_qual}))"
    )
    if not any_type_change and not conversions and not fills:
        # Exact multiset projection check for unchanged retained columns
        unchanged_pairs = [
            (dst, src) for dst, src in select_pairs
            if src.startswith('"') and src.endswith('"')
        ]
        if unchanged_pairs:
            dst_list = ', '.join(_quote(d) for d, _ in unchanged_pairs)
            src_list = ', '.join(s for _, s in unchanged_pairs)
            parent_stage_check = (
                f"SELECT count(*) FROM ((SELECT {src_list} FROM {target} EXCEPT ALL SELECT {dst_list} FROM {stage_qual}) "
                f"UNION ALL (SELECT {dst_list} FROM {stage_qual} EXCEPT ALL SELECT {src_list} FROM {target})) AS diff"
            )

    all_view_rows_base = {r['resource_id']: r for r in preserved_views}
    all_view_rows_des = {r['resource_id']: desired['rows'][r['resource_id']] for r in preserved_views}
    for vop in co_updated_view_ops:
        vid = vop['resource_id']
        all_view_rows_base[vid] = baseline['rows'][vid]
        all_view_rows_des[vid] = desired['rows'][vid]

    all_macro_rows_base = {r['resource_id']: r for r in preserved_macros}
    all_macro_rows_des = {r['resource_id']: desired['rows'][r['resource_id']] for r in preserved_macros}
    for mop in co_updated_macro_ops:
        mid = mop['resource_id']
        all_macro_rows_base[mid] = baseline['rows'][mid]
        all_macro_rows_des[mid] = desired['rows'][mid]

    # View child columns
    view_col_base, view_col_des = {}, {}
    for vid in set(all_view_rows_base) | set(all_view_rows_des):
        vpath = desired['rows'][vid]['path']
        for k, r in baseline['rows'].items():
            if r['kind'] == 'column' and r.get('path', [])[:3] == vpath:
                view_col_base[k] = digest(_definition(r))
        for k, r in desired['rows'].items():
            if r['kind'] == 'column' and r.get('path', [])[:3] == vpath:
                view_col_des[k] = digest(_definition(r))

    all_index_ids = sorted({r['resource_id'] for r in old_indexes} | {r['resource_id'] for r in new_indexes})

    source = ';\n'.join(s.rstrip().rstrip(';') for s in all_statements) + ';'
    return {
        'resource_id': after['resource_id'],
        'kind': 'table',
        'name': after['name'],
        'operation': 'rebuild',
        'general_rebuild': True,
        'target': target,
        'source': source,
        'statements': all_statements,
        'baseline_sha256': digest(_definition(before)),
        'desired_sha256': digest(_definition(after)),
        'original_source': desired_ddl,
        'stage_name': stage_name,
        'parent_stage_copy_index': parent_stage_copy_index,
        'parent_stage_check': parent_stage_check,
        'self_fk_spec': self_fk_spec,
        'self_fk_trigger_index': self_fk_trigger_index,
        'detach_steps': detach_steps,
        'restore_steps': restore_steps,
        'inbound_table_ids': [s['resource_id'] for s in ordered_inbound_specs],
        'affected_inbound_ids': sorted(set(affected_inbound_rows_baseline) | set(affected_inbound_rows_desired)),
        'baseline_inbound_sha256': {k: digest(_definition(r)) for k, r in affected_inbound_rows_baseline.items()},
        'desired_inbound_sha256': {k: digest(_definition(r)) for k, r in affected_inbound_rows_desired.items()},
        'affected_column_ids': sorted(set(old_col_rows) | set(new_col_rows)),
        'added_column_ids': sorted(set(new_col_rows) - set(old_col_rows)),
        'removed_column_ids': sorted(set(old_col_rows) - set(new_col_rows)),
        'converted_columns': sorted(conversions),
        'baseline_column_sha256': {k: digest(_definition(r)) for k, r in old_col_rows.items()},
        'desired_column_sha256': {k: digest(_definition(r)) for k, r in new_col_rows.items()},
        'affected_child_ids': sorted(set(old_con_rows) | set(new_con_rows)),
        'baseline_child_sha256': {k: digest(_definition(r)) for k, r in old_con_rows.items()},
        'desired_child_sha256': {k: digest(_definition(r)) for k, r in new_con_rows.items()},
        'affected_index_ids': all_index_ids,
        'added_index_ids': sorted({r['resource_id'] for r in new_indexes} - {r['resource_id'] for r in old_indexes}),
        'removed_index_ids': sorted({r['resource_id'] for r in old_indexes} - {r['resource_id'] for r in new_indexes}),
        'baseline_index_sha256': {r['resource_id']: digest(_definition(baseline['rows'][r['resource_id']])) for r in old_indexes},
        'desired_index_sha256': {r['resource_id']: digest(_definition(desired['rows'][r['resource_id']])) for r in new_indexes},
        'fk_parent_sha256': fk_parents,
        'preserved_view_ids': [r['resource_id'] for r in preserved_views],
        'co_updated_view_ids': [v['resource_id'] for v in co_updated_view_ops],
        'affected_view_ids': sorted(all_view_rows_base),
        'baseline_view_sha256': {k: digest(_definition(r)) for k, r in all_view_rows_base.items()},
        'desired_view_sha256': {k: digest(_definition(r)) for k, r in all_view_rows_des.items()},
        'affected_view_column_ids': sorted(set(view_col_base) | set(view_col_des)),
        'baseline_view_column_sha256': view_col_base,
        'desired_view_column_sha256': view_col_des,
        'preserved_macro_probes': {
            r['resource_id']: build_macro_probe_queries(r) for r in preserved_macros
        },
        'co_updated_macro_probes': {
            m['resource_id']: m['probes'] for m in co_updated_macro_ops
        },
        'affected_macro_ids': sorted(all_macro_rows_base),
        'baseline_macro_sha256': {k: digest(_definition(r)) for k, r in all_macro_rows_base.items()},
        'desired_macro_sha256': {k: digest(_definition(r)) for k, r in all_macro_rows_des.items()},
        'verify_macro_source': bool(co_updated_macro_ops),
        'sequence_references': [list(item) for item in sorted(set(sequence_refs))],
        'referenced_sequence_ids': sorted(set(verified_seq_ids)),
        'generated_column_order': new_generated_order,
        'acknowledged_lost_tags': lost_tags,
        'postcondition': {'constraints': new_constraints},
    }


# ---------------------------------------------------------------------------
# DU-AUD-16: Macro default-preserving & full signature replacement
# ---------------------------------------------------------------------------

def parse_macro_source_overloads(source_ddl: str) -> list[dict]:
    """Extract overload parameter signatures (with types and default expressions!) and bodies from captured ``source_ddl``."""
    if not isinstance(source_ddl, str) or not source_ddl.strip():
        raise ValueError(
            'Macro default-preserving replacement requires captured source_ddl baseline; '
            'function_oid or parameter names alone cannot reconstruct defaults'
        )
    encoded = source_ddl.encode('utf8')
    tokens = _tokenize_duckdb(source_ddl)
    if not tokens or len(tokens) < 6 or tokens[0]['folded'] != 'create':
        raise ValueError('Captured macro source_ddl is not a valid CREATE MACRO statement')
    start_paren = next(
        (i for i, t in enumerate(tokens) if t['kind'] == 'token_type.operator' and t['raw'] == '('),
        None,
    )
    if start_paren is None:
        raise ValueError('Captured macro source_ddl has no parameter list')

    def find_close(idx: int) -> int | None:
        if idx >= len(tokens) or tokens[idx]['raw'] != '(':
            return None
        depth = 0
        for j in range(idx, len(tokens)):
            if tokens[j]['raw'] == '(':
                depth += 1
            elif tokens[j]['raw'] == ')':
                depth -= 1
                if depth == 0:
                    return j
                if depth < 0:
                    return None
        return None

    overloads: list[dict] = []
    cur = start_paren
    while cur is not None:
        end_paren = find_close(cur)
        if end_paren is None or end_paren + 2 >= len(tokens) or tokens[end_paren + 1]['folded'] != 'as':
            raise ValueError('Malformed overload header in macro source_ddl')
        param_slice = tokens[cur + 1:end_paren]
        param_clauses = _split_top_level_commas(param_slice) if param_slice else []
        if param_clauses is None:
            raise ValueError('Malformed macro parameter list in source_ddl')
        parsed_params = []
        for pclause in param_clauses:
            if not pclause or pclause[0]['kind'] not in {'token_type.identifier', 'token_type.keyword'}:
                raise ValueError('Macro parameter must start with parameter name')
            pname = pclause[0]['unquoted']
            # Find default separator ':=' or keyword 'default' at depth 0
            def_sep_idx = None
            depth = 0
            for k, pt in enumerate(pclause[1:], 1):
                if pt['raw'] == '(':
                    depth += 1
                elif pt['raw'] == ')':
                    depth -= 1
                elif depth == 0 and (
                    (pt['kind'] == 'token_type.operator' and pt['raw'] in {':=', '='}) or
                    (pt['kind'] == 'token_type.keyword' and pt['folded'] == 'default')
                ):
                    def_sep_idx = k
                    break
            type_tokens = pclause[1:def_sep_idx] if def_sep_idx is not None else pclause[1:]
            def_tokens = pclause[def_sep_idx + 1:] if def_sep_idx is not None else []
            if def_sep_idx is not None and not def_tokens:
                raise ValueError(f'Empty parameter default expression for {pname!r}')
            ptype = (
                encoded[type_tokens[0]['offset']:type_tokens[-1]['end']].decode('utf8').strip()
                if type_tokens else None
            )
            pdefault = (
                encoded[def_tokens[0]['offset']:def_tokens[-1]['end']].decode('utf8').strip()
                if def_tokens else None
            )
            parsed_params.append({
                'name': pname,
                'data_type': ptype,
                'default': pdefault,
            })

        body_start = end_paren + 2
        next_boundary = None
        depth = 0
        for j in range(body_start, len(tokens)):
            if tokens[j]['raw'] == '(':
                depth += 1
            elif tokens[j]['raw'] == ')':
                depth -= 1
            elif tokens[j]['raw'] == ',' and depth == 0:
                cand_close = find_close(j + 1)
                if cand_close is not None and cand_close + 1 < len(tokens) and tokens[cand_close + 1]['folded'] == 'as':
                    next_boundary = j
                    break
        body_tokens = tokens[body_start:next_boundary]
        if not body_tokens:
            raise ValueError('Macro overload has empty body')
        is_table = body_tokens[0]['kind'] == 'token_type.keyword' and body_tokens[0]['folded'] == 'table'
        expr_tokens = body_tokens[1:] if is_table else body_tokens
        if not expr_tokens:
            raise ValueError('Table macro overload has empty query body')
        body_sql = encoded[expr_tokens[0]['offset']:expr_tokens[-1]['end']].decode('utf8').strip()
        overloads.append({
            'kind': 'table_macro' if is_table else 'macro',
            'parameters': parsed_params,
            'definition': body_sql,
        })
        cur = (next_boundary + 1) if next_boundary is not None else None
    return overloads


def normalize_macro_overloads_for_compare(overloads: list[dict]) -> list[tuple]:
    """Canonical token signature of macro overloads (body + parameter types + parameter defaults) for post-commit verification."""
    from .duckdb_schema_plan import _macro_body_tokens, _macro_tokens
    normalized = []
    for ov in overloads:
        params_norm = []
        for p in ov.get('parameters') or []:
            ptoks = _macro_tokens(p['data_type']) if p.get('data_type') else None
            dtoks = _macro_body_tokens(_macro_tokens(p['default'])) if p.get('default') is not None else None
            params_norm.append((
                str(p['name']).casefold(),
                tuple(ptoks) if ptoks else None,
                dtoks,
            ))
        btoks = _macro_tokens(ov.get('definition') or '')
        body_norm = _macro_body_tokens(btoks, table=(ov.get('kind') == 'table_macro')) if btoks else None
        normalized.append((ov.get('kind'), tuple(params_norm), body_norm))
    return sorted(normalized, key=repr)


def _format_macro_overload(ov: dict) -> str:
    param_parts = []
    for p in ov['parameters']:
        piece = _quote(p['name'])
        if p.get('data_type'):
            piece += ' ' + p['data_type'].strip()
        if p.get('default') is not None:
            piece += ' := ' + _validate_bounded_sql_expr(p['default'], f"macro default for {p['name']!r}")
        param_parts.append(piece)
    prefix = 'TABLE ' if ov['kind'] == 'table_macro' else ''
    body = ov['definition'].strip()
    if not body or '\x00' in body or len(body.encode('utf8')) > 8192:
        raise ValueError('Macro overload body must be non-empty and at most 8 KiB')
    return f"({', '.join(param_parts)}) AS {prefix}{body}"


def validate_macro_preserve_defaults(before, after, target, change):
    """Reconstruct and preserve macro parameter defaults & typed overloads from ``source_ddl`` (DU-AUD-16)."""
    from .duckdb_schema_plan import _validated_ddl, _validated_replayed_comment

    allowed = {
        'action', 'metadata_reset_acknowledged', 'overload_updates',
        'complete_signature_set_confirmed', 'tag_loss_acknowledged',
    }
    if (not isinstance(change, dict) or
            change.get('action') != 'replace-macro-preserve-defaults' or
            set(change) - allowed or
            change.get('metadata_reset_acknowledged') is not True):
        raise ValueError(
            'Macro default-preserving replacement requires metadata_reset_acknowledged=True'
        )

    before_tags = before['native'].get('catalog_metadata', {}).get('tags')
    lost_tags: list[dict] = []
    if before_tags:
        if change.get('tag_loss_acknowledged') is not True:
            raise ValueError(
                'Rebuilding or replacing an object with native catalog tags loses C++/extension tags in DuckDB 1.5.2; set tag_loss_acknowledged=True'
            )
        lost_tags.append({'resource_id': before['resource_id'], 'kind': 'macro', 'tags': deepcopy(before_tags)})

    parsed_baseline = parse_macro_source_overloads(before['native'].get('source_ddl'))
    updates = change.get('overload_updates')
    if not isinstance(updates, list) or not updates:
        raise ValueError('replace-macro-preserve-defaults requires non-empty overload_updates')

    working = deepcopy(parsed_baseline)
    added_or_removed = False
    to_remove: set[int] = set()
    to_append: list[dict] = []

    for upd in updates:
        if not isinstance(upd, dict):
            raise ValueError('Each overload_updates item must be a dict')
        op = upd.get('op', 'update')
        if op == 'update':
            idx = upd.get('overload_index')
            if type(idx) is not int or not 0 <= idx < len(working) or idx in to_remove:
                raise ValueError('overload_index must identify an existing baseline overload')
            cur_ov = working[idx]
            if 'definition' in upd:
                cur_ov['definition'] = str(upd['definition']).strip()
            if 'parameter_defaults' in upd:
                pdefs = upd['parameter_defaults']
                if not isinstance(pdefs, dict):
                    raise ValueError('parameter_defaults must be a dict of parameter name -> default expression or None')
                known = {p['name']: p for p in cur_ov['parameters']}
                for pname, pval in pdefs.items():
                    if pname not in known:
                        raise ValueError(f'Unknown parameter {pname!r} in parameter_defaults')
                    known[pname]['default'] = pval
            if 'parameters' in upd:
                # Merge explicit parameter list while preserving defaults from baseline unless overridden!
                old_defaults = {p['name']: p.get('default') for p in cur_ov['parameters']}
                old_types = {p['name']: p.get('data_type') for p in cur_ov['parameters']}
                new_params = []
                for p in upd['parameters']:
                    if not isinstance(p, dict) or not isinstance(p.get('name'), str):
                        raise ValueError('Each parameter entry requires a name')
                    pname = p['name']
                    new_params.append({
                        'name': pname,
                        'data_type': p['data_type'] if 'data_type' in p else old_types.get(pname),
                        'default': p['default'] if 'default' in p else old_defaults.get(pname),
                    })
                cur_ov['parameters'] = new_params
        elif op == 'add':
            added_or_removed = True
            kind = upd.get('kind', working[0]['kind'] if working else 'macro')
            if kind not in {'macro', 'table_macro'}:
                raise ValueError('Macro overload kind must be macro or table_macro')
            params = []
            for p in upd.get('parameters') or []:
                if not isinstance(p, dict) or not isinstance(p.get('name'), str):
                    raise ValueError('Added overload parameters must specify name')
                params.append({
                    'name': p['name'],
                    'data_type': p.get('data_type'),
                    'default': p.get('default'),
                })
            to_append.append({
                'kind': kind,
                'parameters': params,
                'definition': str(upd.get('definition') or '').strip(),
            })
        elif op == 'remove':
            added_or_removed = True
            idx = upd.get('overload_index')
            if type(idx) is not int or not 0 <= idx < len(working):
                raise ValueError('Removed overload_index is out of bounds')
            to_remove.add(idx)
        else:
            raise ValueError(f'Unsupported overload_updates op: {op!r}')

    if added_or_removed and change.get('complete_signature_set_confirmed') is not True:
        raise ValueError('Adding or removing macro overloads requires complete_signature_set_confirmed=True')

    final_overloads = [ov for i, ov in enumerate(working) if i not in to_remove] + to_append
    if not 1 <= len(final_overloads) <= 32:
        raise ValueError('Resulting macro must retain between 1 and 32 overloads')
    kinds = {ov['kind'] for ov in final_overloads}
    if len(kinds) != 1:
        raise ValueError('DuckDB 1.5.2 cannot mix scalar and table macro overloads under one name')
    if final_overloads == parsed_baseline and (
        before['native'].get('catalog_metadata', {}).get('comment') ==
        after['native'].get('catalog_metadata', {}).get('comment')
    ):
        raise ValueError('Macro replacement produced no observable signature, default, body, or comment change')

    desired_comment = after['native'].get('catalog_metadata', {}).get('comment')
    if desired_comment is not None and final_overloads[0]['kind'] == 'table_macro':
        raise ValueError('DuckDB 1.5.2 cannot comment on table macros')

    compiled = (
        'CREATE OR REPLACE MACRO ' + target + ' ' +
        ', '.join(_format_macro_overload(ov) for ov in final_overloads)
    )
    compiled = _validated_ddl(compiled, 'macro', after['path'], replace=True)
    comment_replay = _validated_replayed_comment('macro', target, desired_comment)

    return compiled, final_overloads, comment_replay, lost_tags
