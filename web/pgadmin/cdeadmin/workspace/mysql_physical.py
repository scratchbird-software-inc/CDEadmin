"""MySQL and MariaDB physical-schema edits from the diagram.

The normative description is docs/en_US/ddn_physical_schema_vocabulary.rst. MySQL and MariaDB
keep indexes, PRIMARY KEY, UNIQUE, CHECK and FOREIGN KEY inside the one native
``SHOW CREATE TABLE`` definition, so this module works the way the existing column and
foreign-key adapters do: it translates explicit vocabulary edits into exact native clauses of
the desired definition (plus explicit change intent), and ``mysql_schema_plan`` /
``mariadb_schema_plan`` turn the clause difference into one ``ALTER TABLE`` per table.

Nothing here executes SQL, invents ALGORITHM/LOCK hints or infers intent: a name change needs
``rename_from``, a deletion needs ``drop`` plus the exact name, and a missing key never clears or
removes anything.
"""
from copy import deepcopy
import json
import re
from . import physical_schema as vocab
from .mysql_relational_fields import tokens
from .mysql_table_clauses import table_layout

INDEX_WORDS = {'PRIMARY', 'UNIQUE', 'FULLTEXT', 'SPATIAL', 'KEY', 'INDEX'}
ACTIONS = {'mysql': set(vocab.ACTIONS), 'mariadb': set(vocab.ACTIONS) - {'SET DEFAULT'}}
DEFAULT_ACTION = {'mysql': 'NO ACTION', 'mariadb': 'RESTRICT'}
INTENT = {'mysql': 'mysql_change', 'mariadb': 'mariadb_change'}


def _identifier(engine):
    if engine == 'mariadb':
        from ..providers.mysql_family.mariadb_catalog import identifier
    else:
        from ..providers.mysql_family.mysql_catalog import identifier
    return identifier


def _parts(engine):
    if engine == 'mariadb':
        from .mariadb_schema_plan import parts
    else:
        from .mysql_schema_plan import parts
    return parts


def _unquote(token):
    return token[1:-1].replace(token[0] * 2, token[0])


def _is_identifier(token, mode):
    return token[0] == 'quoted' and (token[1][0] == '`' or token[1][0] == '"' and 'ANSI_QUOTES' in mode.split(','))


def _split(group, mode):
    """Top-level comma separation of a parenthesised list, quote and nesting aware."""
    return [part.strip() for part in table_layout(group, mode)['clauses']]


def _options(rest, mode):
    """Flatten executable-version comments (/*!80000 INVISIBLE */) into ordinary tokens."""
    result = []
    for token in rest:
        match = re.fullmatch(r'/\*[M!]?\d*\s*(.*?)\s*\*/', token[1], re.S) if token[0] == 'comment' else None
        if match is not None:
            result.extend(tokens(match.group(1), mode))
        else:
            result.append(token)
    return result


def describe(clause, mode):
    """Exact vocabulary facts of one native table clause (index, PRIMARY KEY, CHECK, FOREIGN KEY).

    ``describable`` is false when the clause carries anything the vocabulary cannot state
    (functional key parts, KEY_BLOCK_SIZE, WITH PARSER, comments...). Such objects may still be
    renamed, dropped and, for visibility, altered; they are never rebuilt from the vocabulary."""
    parsed = tokens(clause, mode)
    if not parsed or parsed[0][0] != 'word':
        raise ValueError('Unsupported native table clause')
    first = parsed[0][1].upper()
    if first in INDEX_WORDS:
        words, name, position = set(), None, 0
        while position < len(parsed) and parsed[position][0] != 'group':
            token = parsed[position]
            if token[0] == 'word' and token[1].upper() in INDEX_WORDS:
                words.add(token[1].upper())
            elif _is_identifier(token, mode) and name is None:
                name = _unquote(token[1])
            else:
                raise ValueError('Unsupported native index clause')
            position += 1
        if position >= len(parsed):
            raise ValueError('Native index clause lacks its key parts')
        result = {'kind': 'primary' if 'PRIMARY' in words else 'index', 'name': 'PRIMARY' if 'PRIMARY' in words else name,
                  'unique': 'UNIQUE' in words or 'PRIMARY' in words,
                  'index_type': 'FULLTEXT' if 'FULLTEXT' in words else 'SPATIAL' if 'SPATIAL' in words else None,
                  'columns': [], 'prefix_lengths': [], 'directions': [], 'expression_parts': False,
                  'method': None, 'visible': True, 'comment': None, 'extra': []}
        for part in _split(parsed[position][1], mode):
            bits = tokens(part, mode)
            if bits and _is_identifier(bits[0], mode):
                result['columns'].append(_unquote(bits[0][1]))
                rest = bits[1:]
                length = None
                if rest and rest[0][0] == 'group' and re.fullmatch(r'\(\s*[0-9]+\s*\)', rest[0][1]):
                    length = int(rest[0][1][1:-1])
                    rest = rest[1:]
                result['prefix_lengths'].append(length)
                direction = 'ASC'
                if rest and rest[0][0] == 'word' and rest[0][1].upper() in {'ASC', 'DESC'}:
                    direction = rest[0][1].upper()
                    rest = rest[1:]
                result['directions'].append(direction)
                if rest:
                    result['extra'].append(part)
            else:
                result['expression_parts'] = True
        options, i = _options(parsed[position + 1:], mode), 0
        while i < len(options):
            token = options[i]
            word = token[1].upper() if token[0] == 'word' else None
            if word == 'USING' and i + 1 < len(options) and options[i + 1][0] == 'word':
                result['method'] = options[i + 1][1].upper()
                i += 2
            elif word == 'COMMENT' and i + 1 < len(options) and options[i + 1][0] == 'quoted':
                result['comment'] = options[i + 1][1]
                i += 2
            elif word in {'INVISIBLE', 'IGNORED'}:
                result['visible'] = False
                i += 1
            elif word == 'VISIBLE':
                i += 1
            elif word == 'NOT' and i + 1 < len(options) and options[i + 1][1].upper() == 'IGNORED':
                i += 2
            else:
                result['extra'].append(token[1])
                i += 1
        result['describable'] = not (result['expression_parts'] or result['extra'] or result['comment'] is not None)
        return result
    if first == 'CONSTRAINT' and len(parsed) >= 4 and _is_identifier(parsed[1], mode):
        name, kind = _unquote(parsed[1][1]), parsed[2][1].upper()
        if kind == 'CHECK' and parsed[3][0] == 'group':
            trailing = ' '.join(token[1].upper() for token in _options(parsed[4:], mode) if token[0] == 'word')
            return {'kind': 'check', 'name': name, 'expression': parsed[3][1][1:-1], 'enforced': 'NOT ENFORCED' not in trailing,
                    'describable': trailing in ('', 'ENFORCED', 'NOT ENFORCED')}
        if kind == 'FOREIGN' and len(parsed) > 5 and parsed[3][1].upper() == 'KEY' and parsed[4][0] == 'group':
            reference = next((i for i, token in enumerate(parsed) if token[0] == 'word' and token[1].upper() == 'REFERENCES'), None)
            if reference is None:
                raise ValueError('Native foreign key lacks its referenced table')
            target, position = [], reference + 1
            while position < len(parsed) and parsed[position][0] != 'group':
                if _is_identifier(parsed[position], mode):
                    target.append(_unquote(parsed[position][1]))
                elif parsed[position][1] != '.':
                    raise ValueError('Native foreign-key parent requires exact quoted identity')
                position += 1
            if position >= len(parsed) or len(target) not in (1, 2):
                raise ValueError('Native foreign-key parent is ambiguous')
            result = {'kind': 'foreign-key', 'name': name, 'columns': [_unquote(p) for p in _names(parsed[4][1], mode)],
                      'ref_database': target[0] if len(target) == 2 else None, 'ref_table': target[-1],
                      'ref_columns': [_unquote(p) for p in _names(parsed[position][1], mode)],
                      'on_delete': None, 'on_update': None, 'match': None, 'describable': True}
            tail, i = _options(parsed[position + 1:], mode), 0
            while i < len(tail):
                word = tail[i][1].upper()
                if word == 'ON' and i + 1 < len(tail) and tail[i + 1][1].upper() in {'DELETE', 'UPDATE'}:
                    which, i, action = 'on_' + tail[i + 1][1].lower(), i + 2, []
                    while i < len(tail) and tail[i][1].upper() != 'ON':
                        action.append(tail[i][1].upper())
                        i += 1
                    result[which] = ' '.join(action)
                elif word == 'MATCH' and i + 1 < len(tail):
                    result['match'] = tail[i + 1][1].upper()
                    i += 2
                else:
                    result['describable'] = False
                    i += 1
            return result
    raise ValueError('Unsupported native table clause')


def _names(group, mode):
    names = []
    for part in _split(group, mode):
        bits = tokens(part, mode)
        if len(bits) != 1 or not _is_identifier(bits[0], mode):
            raise ValueError('Native foreign-key columns require exact quoted names')
        names.append(bits[0][1])
    return names


def values_of(found, engine):
    """The vocabulary a described clause states, in the shape the diagram stores."""
    kind = found['kind']
    if kind == 'check':
        return {'physical_kind': 'check', 'physical_name': found['name'], 'expression': found['expression'],
                **({'enforced': found['enforced']} if engine == 'mysql' else {})}
    if kind == 'foreign-key':
        return {'physical_kind': 'foreign-key', 'physical_name': found['name'], 'columns_json': vocab.encode(found['columns']),
                'referenced_columns_json': vocab.encode(found['ref_columns']),
                'on_delete': found['on_delete'] or DEFAULT_ACTION[engine], 'on_update': found['on_update'] or DEFAULT_ACTION[engine]}
    values = {'physical_kind': 'primary-key' if kind == 'primary' else 'unique' if found['unique'] else 'index',
              'physical_name': found['name']}
    if not found['expression_parts']:
        values['columns_json'] = vocab.encode(found['columns'])
        if any(length is not None for length in found['prefix_lengths']):
            values['prefix_lengths_json'] = json.dumps(found['prefix_lengths'], separators=(',', ':'))
        if 'DESC' in found['directions']:
            values['directions_json'] = vocab.encode(found['directions'])
    if values['physical_kind'] == 'index':
        values['unique'] = False
    if found['index_type']:
        values['index_type'] = found['index_type']
    if found['method'] in ('BTREE', 'HASH'):
        values['method'] = found['method']
    if kind != 'primary':
        values['visible'] = found['visible']
    return values


def table_values(name):
    return {'physical_name': name}


def column_values(name):
    return {'physical_name': name}


# --------------------------------------------------------------------------- forward

def forward(name, row_native, mode, engine):
    """Index/constraint children and foreign-key vocabularies of one native table definition.

    Returns ``(children, foreign_keys, warnings)``. A definition this module cannot separate
    publishes no physical vocabulary (a warning explains it); the diagram stays usable."""
    parse = _parts(engine)
    if not isinstance(row_native.get('definition'), str) or not row_native.get('definition'):
        return [], {}, []
    try:
        _layout, clauses, _order = parse({'name': name, 'native': row_native}, mode)
    except (ValueError, KeyError) as error:
        return [], {}, ['Physical vocabulary unavailable for ' + str(name) + ': ' + str(error)]
    children, foreign, warnings = [], {}, []
    for (kind, clause_name), clause in clauses.items():
        if kind in {'column', 'period'}:
            continue
        try:
            found = describe(clause, mode)
        except ValueError as error:
            warnings.append('Physical vocabulary unavailable for ' + str(clause_name) + ': ' + str(error))
            continue
        values = values_of(found, engine)
        if kind == 'foreign-key':
            foreign[clause_name] = {'values': values, 'found': found}
        else:
            children.append({'kind': values['physical_kind'], 'name': found['name'], 'role':
                'index' if values['physical_kind'] == 'index' else 'constraint', 'values': values, 'clause': clause})
    return children, foreign, warnings


# --------------------------------------------------------------------------- clause building

def safe_expression(text, mode, label='expression'):
    """Bounded text that cannot end the clause: balanced, no comments, no statement separator."""
    if not isinstance(text, str) or not text.strip() or len(text) > 4096 or '\x00' in text:
        raise ValueError('A ' + label + ' needs bounded non-empty text')
    def walk(source):
        parsed = tokens(source, mode)
        for index, (kind, value, start, _end) in enumerate(parsed):
            if kind == 'comment':
                raise ValueError('A ' + label + ' cannot contain comments')
            if kind == 'symbol' and value in {';', '#'}:
                raise ValueError('A ' + label + ' cannot contain a statement separator or comment')
            if kind == 'symbol' and value == '-' and index + 1 < len(parsed) and parsed[index + 1][1] == '-' and \
                    parsed[index + 1][2] == start + 1 and (parsed[index + 1][3] >= len(source) or source[parsed[index + 1][3]].isspace()):
                raise ValueError('A ' + label + ' cannot contain comments')
            if kind == 'group':
                walk(value[1:-1])
    walk(text)
    return text.strip()


def _one_clause(clause, mode):
    layout = table_layout('CREATE TABLE `x` (' + clause + ')', mode)
    if len(layout['clauses']) != 1 or layout['suffix'].strip():
        raise ValueError('The generated clause would not stay a single native table clause')
    return clause


def _column_list(quote, columns, available, label):
    if (not isinstance(columns, list) or not 1 <= len(columns) <= 32 or len(set(columns)) != len(columns) or
            any(not isinstance(name, str) or not 1 <= len(name) <= 64 for name in columns)):
        raise ValueError(label + ' need 1 to 32 distinct column names')
    missing = [name for name in columns if name not in available]
    if missing:
        raise ValueError(label + ' name columns that do not exist: ' + ', '.join(missing))
    return ', '.join(quote(name) for name in columns)


def build_index(kind, name, values, available, mode, engine):
    quote = _identifier(engine)
    columns = values.get('columns')
    text = _column_list(quote, columns, available, 'Index columns')
    count = len(columns)
    prefix = values.get('prefix_lengths') or [None] * count
    directions = values.get('directions') or ['ASC'] * count
    if len(prefix) != count or len(directions) != count:
        raise ValueError('Prefix lengths and directions need one entry per column')
    parts = [quote(column) + ('(' + str(length) + ')' if length else '') + (' DESC' if direction == 'DESC' else '')
             for column, length, direction in zip(columns, prefix, directions)]
    itype, method = values.get('index_type'), values.get('method')
    if method is not None and method not in ('BTREE', 'HASH'):
        raise ValueError('Index method must be BTREE or HASH')
    unique = kind in ('unique', 'primary-key') or bool(values.get('unique'))
    if kind == 'unique' and values.get('unique') is False:
        raise ValueError('A UNIQUE constraint cannot be edited to a non-unique index; drop it and add an index')
    if itype and (unique or method):
        raise ValueError(itype + ' indexes are neither unique nor USING-typed')
    if kind == 'primary-key':
        if name != 'PRIMARY':
            raise ValueError('A MySQL PRIMARY KEY is always named PRIMARY')
        if values.get('visible') is False:
            raise ValueError('A PRIMARY KEY cannot be invisible')
        head = 'PRIMARY KEY'
    else:
        if not isinstance(name, str) or not 1 <= len(name) <= 64 or name == 'PRIMARY' or name != name.rstrip() or '\x00' in name:
            raise ValueError('An index name needs 1 to 64 characters and cannot be PRIMARY')
        head = ('UNIQUE KEY ' if unique else (itype + ' KEY ' if itype else 'KEY ')) + quote(name)
    clause = head + ' (' + ', '.join(parts) + ')'
    if method:
        clause += ' USING ' + method
    if values.get('visible') is False:
        clause += ' IGNORED' if engine == 'mariadb' else ' INVISIBLE'
    return _one_clause(clause, mode)


def build_check(name, values, mode, engine):
    quote = _identifier(engine)
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or '\x00' in name:
        raise ValueError('A constraint name needs 1 to 64 characters')
    expression = safe_expression(values.get('expression'), mode)
    clause = 'CONSTRAINT ' + quote(name) + ' CHECK (' + expression + ')'
    if values.get('enforced') is False:
        if engine != 'mysql':
            raise ValueError('NOT ENFORCED CHECK constraints are a MySQL feature')
        clause += ' NOT ENFORCED'
    return _one_clause(clause, mode)


def build_foreign_key(name, values, target, available, target_columns, mode, engine):
    quote = _identifier(engine)
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or '\x00' in name:
        raise ValueError('A constraint name needs 1 to 64 characters')
    columns, referenced = values.get('columns'), values.get('referenced_columns')
    source = _column_list(quote, columns, available, 'Foreign-key columns')
    destination = _column_list(quote, referenced, target_columns, 'Referenced columns')
    if len(columns) != len(referenced):
        raise ValueError('Foreign-key and referenced column counts differ')
    delete, update = values.get('on_delete', DEFAULT_ACTION[engine]), values.get('on_update', DEFAULT_ACTION[engine])
    for action in (delete, update):
        if action not in ACTIONS[engine]:
            raise ValueError('Select a foreign-key action this engine supports: ' + ', '.join(sorted(ACTIONS[engine])))
    clause = ('CONSTRAINT ' + quote(name) + ' FOREIGN KEY (' + source + ') REFERENCES ' + '.'.join(quote(part) for part in target) +
              ' (' + destination + ') ON DELETE ' + delete + ' ON UPDATE ' + update)
    return _one_clause(clause, mode)


def set_visibility(clause, visible, mode, engine):
    """The same clause with only its visibility changed (valid for any index, however detailed)."""
    parsed = tokens(clause, mode)
    keep, i = [], 0
    while i < len(parsed):
        token = parsed[i]
        inner = re.fullmatch(r'/\*[M!]?\d*\s*(.*?)\s*\*/', token[1], re.S) if token[0] == 'comment' else None
        word = (inner.group(1) if inner else token[1]).upper().strip() if token[0] in {'word', 'comment'} else None
        if word in {'INVISIBLE', 'IGNORED', 'VISIBLE'}:
            keep.append((token[2], token[3]))
        elif word == 'NOT' and i + 1 < len(parsed) and parsed[i + 1][1].upper() == 'IGNORED':
            keep.append((token[2], parsed[i + 1][3]))
            i += 1
        i += 1
    for start, end in sorted(keep, reverse=True):
        clause = clause[:start] + clause[end:]
    clause = clause.rstrip()
    if not visible:
        clause += ' IGNORED' if engine == 'mariadb' else ' INVISIBLE'
    return clause


def rename_clause(clause, new, mode, engine):
    """The same clause under a new object name (the name token is the first quoted identifier)."""
    quote = _identifier(engine)
    if not isinstance(new, str) or not 1 <= len(new) <= 64 or new != new.rstrip() or '\x00' in new:
        raise ValueError('A native object name needs 1 to 64 characters')
    for token in tokens(clause, mode):
        if _is_identifier(token, mode):
            return clause[:token[2]] + quote(new) + clause[token[3]:]
    raise ValueError('Native clause lacks its object name')


# --------------------------------------------------------------------------- canonical comparison

def _normal_expression(text, mode):
    parsed = tokens(text, mode)
    if len(parsed) == 1 and parsed[0][0] == 'group':
        return _normal_expression(parsed[0][1][1:-1], mode)
    pieces = []
    for kind, value, _start, _end in parsed:
        if kind == 'group':
            pieces.append('(' + _normal_expression(value[1:-1], mode) + ')')
        elif _is_identifier((kind, value), mode):
            pieces.append(_unquote(value).lower())
        elif kind == 'word':
            pieces.append(value.lower())
        else:
            pieces.append(value)
    return ' '.join(pieces)


def canonical(key, clause, mode, engine, database, *, visibility=True):
    """A comparable form of a native clause that ignores formatting, defaulted and redundant text.

    Used to prove that the live definition already is the wanted one (convergence) and to
    recognise a pure rename or a visibility-only change. Unknown clause kinds compare by tokens."""
    kind = key[0]
    try:
        found = describe(clause, mode)
    except ValueError:
        return ('raw', ' '.join(token[1] for token in tokens(clause, mode)))
    if kind in {'index', 'primary'}:
        return ('index', found['kind'], found['unique'], found['index_type'], tuple(found['columns']),
                tuple(found['prefix_lengths']), tuple(found['directions']),
                None if found['method'] in (None, 'BTREE') else found['method'], found['comment'],
                tuple(found['extra']), found['visible'] if visibility else None,
                _expression_parts(clause, mode) if found['expression_parts'] else None)
    if kind == 'check':
        return ('check', _normal_expression(found['expression'], mode), found['enforced'])
    if kind == 'foreign-key':
        return ('foreign-key', tuple(found['columns']), found['ref_database'] if found['ref_database'] != database else None,
                found['ref_table'], tuple(found['ref_columns']), found['on_delete'] or DEFAULT_ACTION[engine],
                found['on_update'] or DEFAULT_ACTION[engine], found['match'] in (None, 'SIMPLE', 'NONE'))
    return ('raw', ' '.join(token[1] for token in tokens(clause, mode)))


def _expression_parts(clause, mode):
    parsed = tokens(clause, mode)
    group = next(token for token in parsed if token[0] == 'group')
    return tuple(_normal_expression(part, mode) for part in _split(group[1], mode))


def definition_map(row, mode, engine):
    parse = _parts(engine)
    layout, clauses, order = parse(row, mode)
    return layout, clauses, order


def _options_text(layout):
    """Table options without the volatile AUTO_INCREMENT counter."""
    return ' '.join(re.sub(r'\bAUTO_INCREMENT=\d+', '', layout['suffix'], flags=re.I).split())


def converged(before, after, current, mode, engine, database):
    """True when the live table already has the wanted definition (so a re-plan has nothing to do)."""
    intent = after['native'].get(INTENT[engine]) or {}
    if intent.get('action') == 'drop':
        return current is None
    if intent.get('rename_table'):
        return False
    if current is None:
        return False
    try:
        wanted_layout, wanted, _o = definition_map(after, mode, engine)
        live_layout, live, _o = definition_map(current, mode, engine)
    except (ValueError, KeyError):
        return False
    try:
        _l, origin, _o = definition_map(before, mode, engine) if before is not None else (None, {}, None)
    except (ValueError, KeyError):
        origin = {}
    # The server names the index it creates for a foreign key after that key, and re-creates it under the new
    # name when the key is renamed in the same ALTER TABLE: a plain index carrying such a name is not part of
    # what the review states, so it is compared on neither side.
    implicit = {key[1] for source in (wanted, live, origin) for key in source if key[0] == 'foreign-key'}

    def explicit(clauses):
        result = {}
        for key, clause in clauses.items():
            if key[0] == 'index' and key[1] in implicit:
                found = describe(clause, mode)
                if found['kind'] == 'index' and not found['unique'] and found['index_type'] is None:
                    continue
            result[key] = clause
        return result
    wanted, live = explicit(wanted), explicit(live)
    if wanted.keys() != live.keys() or _options_text(wanted_layout) != _options_text(live_layout):
        return False
    keyed = set()   # the server makes every PRIMARY KEY column NOT NULL, whatever the stated definition said
    for key, clause in wanted.items():
        if key[0] == 'primary':
            keyed = set(describe(clause, mode)['columns'])

    def column_text(key, clause):
        text = ' '.join(t[1] for t in tokens(clause, mode))
        if key[0] == 'column' and key[1] in keyed:
            text = ' '.join(re.sub(r'\bDEFAULT NULL\b', '', re.sub(r'\bNOT NULL\b', '', text, flags=re.I), flags=re.I).split()) + ' NOT NULL'
        return text
    for key, clause in wanted.items():
        if key[0] in {'column', 'period'}:
            if column_text(key, clause) != column_text(key, live[key]):
                return False
        elif canonical(key, clause, mode, engine, database) != canonical(key, live[key], mode, engine, database):
            return False
    return True


def renamed_table_converged(before, after, live_rows, mode, engine, database):
    """A reviewed table rename that already happened: the new name exists with the wanted definition."""
    intent = after['native'].get(INTENT[engine]) or {}
    new = intent.get('rename_table')
    if not new:
        return False
    for row in live_rows.values():
        if row['kind'] == 'table' and row['name'] == new:
            try:
                wanted_layout, wanted, _o = definition_map(before, mode, engine)
                live_layout, live, _o = definition_map(row, mode, engine)
            except (ValueError, KeyError):
                return False
            return wanted.keys() == live.keys() and _options_text(wanted_layout) == _options_text(live_layout) and all(
                canonical(key, wanted[key], mode, engine, database) == canonical(key, live[key], mode, engine, database)
                for key in wanted)
    return False


# --------------------------------------------------------------------------- alteration helpers (plan)

def index_operations(columns, desired, intent, mode, engine, database):
    """RENAME INDEX / ALTER INDEX clauses and the clause keys they settle.

    A pure rename (same definition under a new name, named in ``rename_indexes``) is a metadata-only
    RENAME INDEX; a clause that differs only by visibility is ALTER INDEX ... INVISIBLE|IGNORED.
    Every other difference stays a DROP plus ADD in the caller."""
    quote = _identifier(engine)
    renames = intent.get('rename_indexes', {})
    if not isinstance(renames, dict) or len(renames) > 128 or any(
            not isinstance(a, str) or not isinstance(b, str) or not 1 <= len(b) <= 64 for a, b in renames.items()):
        raise ValueError('Index rename intent requires exact baseline and desired index names')
    clauses, settled = [], set()
    for old, new in sorted(renames.items()):
        old_key, new_key = ('index', old), ('index', new)
        if old_key not in columns or old_key in desired or new_key in columns or new_key not in desired:
            raise ValueError('Index rename requires an existing baseline index and a new desired name')
        if canonical(old_key, columns[old_key], mode, engine, database) != canonical(new_key, desired[new_key], mode, engine, database):
            raise ValueError('An index rename cannot change its definition; review the replacement separately')
        clauses.append('RENAME INDEX ' + quote(old) + ' TO ' + quote(new))
        settled.update({old_key, new_key})
    for key in sorted(columns.keys() & desired.keys()):
        if key[0] != 'index' or columns[key] == desired[key]:
            continue
        if canonical(key, columns[key], mode, engine, database) == canonical(key, desired[key], mode, engine, database):
            settled.add(key)       # formatting only: the same native index
            continue
        if canonical(key, columns[key], mode, engine, database, visibility=False) != \
                canonical(key, desired[key], mode, engine, database, visibility=False):
            continue
        visible = describe(desired[key], mode)['visible']
        clauses.append('ALTER INDEX ' + quote(key[1]) + ' ' + (
            ('NOT IGNORED' if visible else 'IGNORED') if engine == 'mariadb' else ('VISIBLE' if visible else 'INVISIBLE')))
        settled.add(key)
    return clauses, settled


def table_rename(before, after, intent, mode, engine):
    """ALTER TABLE ... RENAME TO for an explicit ``rename_table`` intent, reviewed on its own."""
    quote = _identifier(engine)
    new = intent['rename_table']
    if set(intent) != {'rename_table'}:
        raise ValueError('Review a table rename separately from other edits to the same table')
    if (not isinstance(new, str) or not 1 <= len(new) <= 64 or new == before['name'] or new != new.rstrip() or
            any(char in new for char in '\x00/\\.')):
        raise ValueError('A table rename needs a distinct valid new name')
    if before['native'].get('definition') != after['native'].get('definition'):
        raise ValueError('Review a table rename separately from other edits to the same table')
    database = before['native']['database']
    return 'ALTER TABLE ' + quote(database) + '.' + quote(before['name']) + ' RENAME TO ' + quote(database) + '.' + quote(new)


def changes_of(columns, desired, intent, mode, engine, database):
    """What the alteration does, object by object; drives the plan's destructive flags."""
    steps = []
    renames = intent.get('rename_indexes', {}) if isinstance(intent, dict) else {}
    settled = {('index', name) for pair in renames.items() for name in pair}
    for key in sorted(columns.keys() | desired.keys()):
        if key[0] in {'column', 'period'} and key in desired and key in columns:
            continue
        label = {'primary': 'primary-key', 'index': 'index', 'check': 'check', 'foreign-key': 'foreign-key',
                 'column': 'column', 'period': 'period'}[key[0]]
        if key in columns and key not in desired:
            if key in settled:
                steps.append({'object': label, 'name': key[1], 'action': 'rename'})
            elif not (key[0] == 'column' and key[1] in (intent.get('rename_columns') or {})):
                steps.append({'object': label, 'name': key[1], 'action': 'drop', 'destructive': True})
        elif key in desired and key not in columns:
            if key in settled or key[0] == 'column' and key[1] in (intent.get('rename_columns') or {}).values():
                continue
            steps.append({'object': label, 'name': key[1], 'action': 'add'})
        elif key[0] not in {'column', 'period'} and columns[key] != desired[key]:
            same_but_visibility = (key[0] == 'index' and
                canonical(key, columns[key], mode, engine, database, visibility=False) ==
                canonical(key, desired[key], mode, engine, database, visibility=False))
            steps.append({'object': label, 'name': key[1], 'action': 'alter-visibility' if same_but_visibility else 'replace'})
    return steps


ORDERING_RULE = ('MySQL and MariaDB DDL commits each statement on its own. Each table change is one ALTER TABLE, so a table is '
                 'never left half-changed, and operations run in this order: creations, additions and in-place changes, foreign-key '
                 'additions and replacements (after the keys they need exist), table renames, then every drop of a column, key, '
                 'constraint or table, so that a failure part-way leaves the schema a superset of the old one.')


def plan_changes(before, after, mode, engine, database):
    parse = _parts(engine)
    _l, columns, _o = parse(before, mode)
    _l, desired, _o = parse(after, mode)
    return changes_of(columns, desired, after['native'].get(INTENT[engine]) or {}, mode, engine, database)


def annotate(operation, before, after, mode, engine, database):
    """Add the review facts every operation of this module's kind carries (destructive flag, exact confirmations)."""
    intent = after['native'].get(INTENT[engine]) or {}
    if operation['kind'] != 'table':
        return operation
    if operation['operation'] == 'drop':
        operation.update(destructive=True, confirmation=before['name'], changes=[
            {'object': 'table', 'name': before['name'], 'action': 'drop', 'destructive': True}])
    elif operation['operation'] == 'alter':
        if intent.get('rename_table'):
            operation.update(rename_to=intent['rename_table'], changes=[
                {'object': 'table', 'name': before['name'], 'action': 'rename', 'to': intent['rename_table']}])
        else:
            steps = plan_changes(before, after, mode, engine, database)
            operation['changes'] = steps
            drops = [step['name'] for step in steps if step.get('destructive')]
            if drops:
                operation.update(destructive=True, confirmation=drops)
    return operation


PHASES = {'additive': 0, 'alter': 1, 'foreign-key': 2, 'rename': 3, 'destructive': 4}


def phase(operation):
    """Ordering class of a plan operation (see the ordering rule in the vocabulary document)."""
    if operation['operation'] == 'create':
        return 'additive'
    if operation['operation'] == 'drop':
        return 'destructive'
    steps = operation.get('changes') or []
    if operation.get('rename_to'):
        return 'rename'
    if any(step.get('destructive') for step in steps):
        return 'destructive'
    if any(step['object'] == 'foreign-key' and step['action'] in {'add', 'replace'} for step in steps):
        return 'foreign-key'
    return 'alter'


def order_operations(operations):
    """Stable order that keeps a partial failure the cheapest to recover from.

    1. creations, 2. alterations that only add or change, 3. alterations that add or change a
    foreign key (so the parent keys they need exist), 4. table renames, 5. everything that drops
    data-bearing or constraint objects. Within a class the order is the resource order the plan
    already used. Each table is still one ALTER TABLE statement, so a table is never half-changed."""
    return sorted(operations, key=lambda item: PHASES[phase(item)])


# --------------------------------------------------------------------------- merge (diagram -> desired definition)

def _mentions(text, column, mode):
    wanted = column.lower()
    def walk(source):
        for kind, value, _s, _e in tokens(source, mode):
            if kind == 'group' and walk(value[1:-1]):
                return True
            if kind == 'word' and value.lower() == wanted:
                return True
            if _is_identifier((kind, value), mode) and _unquote(value).lower() == wanted:
                return True
        return False
    return walk(text)


def _covering(clauses, columns, mode, skip=()):
    """Some remaining key whose leading columns are exactly ``columns``."""
    for key, clause in clauses.items():
        if key[0] not in {'primary', 'index'} or key in skip:
            continue
        try:
            found = describe(clause, mode)
        except ValueError:
            continue
        if found['index_type'] == 'FULLTEXT' or found['expression_parts']:
            continue
        if found['columns'][:len(columns)] == columns:
            return True
    return False


def _key_of(kind, name):
    return ('primary', 'PRIMARY') if kind == 'primary-key' else ('check', name) if kind == 'check' else ('index', name)


def _resolve(row_physical):
    return vocab.normalize(row_physical or {})


def merge(old, row, live, current, *, kids_before, kids_after, edges_before, edges_after, drafts, mode, engine, database,
          all_drafts=None):
    """Desired native facts of one table after the diagram's physical-vocabulary edits.

    ``old``/``row`` are the baseline and edited diagram rows (``row['native']`` already carries any
    column edits). ``kids_*`` are the index/PRIMARY/UNIQUE/CHECK child rows, ``edges_*`` the foreign
    keys sourced at this table keyed by relationship uid, ``drafts`` the annotated new objects."""
    native = deepcopy(row['native'])
    if live.get('kind') != 'table':
        return native
    nothing = {}
    if not (drafts or (row.get('physical') or nothing) != (old.get('physical') or nothing) or
            any((field.get('_physical') or nothing) != ((old.get('fields', {}).get(uid) or nothing).get('_physical') or nothing)
                for uid, field in row.get('fields', {}).items()) or
            any((kid.get('physical') or nothing) != ((kids_before.get(rid) or nothing).get('physical') or nothing)
                for rid, kid in kids_after.items()) or
            any((edge.get('physical') or nothing) != ((edges_before.get(uid) or nothing).get('physical') or nothing)
                for uid, edge in edges_after.items())):
        return native   # no vocabulary edit: the definition is not even separated
    parse, quote, intent_key = _parts(engine), _identifier(engine), INTENT[engine]
    table = {'name': live['name'], 'native': native}
    layout, clauses, order = parse(table, mode)
    _bl, base, base_order = parse({'name': live['name'], 'native': old['native']}, mode)
    intent = deepcopy(native.get(intent_key) or {})
    if not isinstance(intent, dict):
        raise ValueError('Invalid native change intent')
    edited = False
    pending = []          # (description, key, new clause or None) applied after all guards
    other = False         # any non-table-level edit, to keep renames/drops separate
    table_rename = vocab.rename(old.get('physical'), row.get('physical'), 'table')
    table_drop = vocab.drop(old.get('physical'), row.get('physical'), old['name'], 'table')
    # ---- columns
    renames, drops = {}, []
    for uid, fields in row.get('fields', {}).items():
        original = old.get('fields', {}).get(uid)
        if original is None:
            continue
        before_p, after_p = original.get('_physical') or {}, fields.get('_physical') or {}
        label = 'column ' + str(original.get('_label'))
        pair = vocab.rename(before_p, after_p, label)
        if pair is not None:
            if pair[0] != original.get('_label'):
                raise ValueError('rename_from does not name the baseline column')
            if fields.get('_label') != original.get('_label'):
                raise ValueError('Rename a column either through its field title or through physical_name, not both')
            renames[pair[0]] = pair[1]
        if vocab.drop(before_p, after_p, original.get('_label'), label):
            drops.append(original['_label'])
    # ---- indexes and constraints
    for rid, kid in kids_after.items():
        before = kids_before.get(rid)
        if before is None:
            raise ValueError('An index or constraint has no baseline identity: ' + rid)
        before_p, after_p = before.get('physical') or {}, kid.get('physical') or {}
        baseline = _resolve(before_p)
        name, kind = baseline['physical_name'], baseline['physical_kind']
        label = {'primary-key': 'PRIMARY KEY', 'unique': 'UNIQUE constraint', 'check': 'CHECK constraint', 'index': 'index'}[kind] + ' ' + name
        key = _key_of(kind, name)
        if key not in base:
            raise ValueError('Baseline native clause is unavailable for ' + label)
        if vocab.drop(before_p, after_p, name, label):
            pending.append((label, key, None, 'drop'))
            continue
        pair = vocab.rename(before_p, after_p, label)
        changed = vocab.changes(before_p, after_p)
        changed.pop('physical_name', None)
        if 'physical_kind' in changed:
            raise ValueError('The physical kind of ' + label + ' cannot be edited')
        if pair is None and not changed:
            continue
        found = describe(base[key], mode)
        if kind == 'check':
            if set(changed) - {'expression', 'enforced'}:
                raise ValueError('A CHECK constraint accepts only expression and enforced edits')
            if not found['describable']:
                raise ValueError(label + ' carries native detail the vocabulary cannot state; edit it natively')
            values = {**values_of(found, engine), **changed}
            pending.append((label, key, build_check(pair[1] if pair else name, values, mode, engine), 'rename' if pair else 'replace'))
            continue
        if kind == 'primary-key' and pair:
            raise ValueError('A MySQL PRIMARY KEY is always named PRIMARY and cannot be renamed')
        if set(changed) == {'visible'} and pair is None:
            if kind == 'primary-key':
                raise ValueError('A PRIMARY KEY cannot be invisible')
            pending.append((label, key, set_visibility(base[key], changed['visible'], mode, engine), 'replace'))
            continue
        if pair and not changed:
            pending.append((label, key, rename_clause(base[key], pair[1], mode, engine), 'rename-index'))
            continue
        if not found['describable']:
            raise ValueError(label + ' carries native detail the vocabulary cannot state (functional key parts, comment or options); edit it natively')
        merged = {**vocab.normalize(values_of(found, engine)), **changed}
        if 'columns' in changed:
            if 'prefix_lengths' not in changed:
                merged.pop('prefix_lengths', None)
            if 'directions' not in changed:
                merged.pop('directions', None)
        if kind == 'index' and merged.get('unique') is True:
            kind_out = 'unique'
        else:
            kind_out = kind
        new_name = pair[1] if pair else name
        pending.append((label, key, build_index(kind_out, new_name, {k: v for k, v in merged.items() if v is not None}, set(order), mode, engine), 'rename' if pair else 'replace'))
    # ---- foreign keys
    for uid, edge in edges_after.items():
        before = edges_before.get(uid)
        if before is None:
            continue
        before_p, after_p = before.get('physical') or {}, edge.get('physical') or {}
        if not before_p and not after_p:
            continue
        baseline = _resolve(before_p)
        name = baseline.get('physical_name')
        if name is None:
            continue
        key = ('foreign-key', name)
        label = 'FOREIGN KEY ' + name
        if key not in base:
            raise ValueError('Baseline native clause is unavailable for ' + label)
        if vocab.drop(before_p, after_p, name, label):
            pending.append((label, key, None, 'drop'))
            continue
        pair = vocab.rename(before_p, after_p, label)
        changed = vocab.changes(before_p, after_p)
        changed.pop('physical_name', None)
        if 'physical_kind' in changed:
            raise ValueError('The physical kind of ' + label + ' cannot be edited')
        if pair is None and not changed:
            continue
        found = describe(base[key], mode)
        if not found['describable'] or found['match'] not in (None, 'SIMPLE', 'NONE'):
            raise ValueError(label + ' carries native detail the vocabulary cannot state; edit it natively')
        if pair is None:
            raise ValueError('MySQL and MariaDB cannot drop and re-add a foreign key of the same name in one ALTER TABLE '
                             'and foreign-key checks are never disabled; give the changed foreign key a new name with rename_from, '
                             'or review the drop and the new foreign key as two edits')
        target_row = _target(current, database, found)
        merged = {**{'columns': found['columns'], 'referenced_columns': found['ref_columns'],
                     'on_delete': found['on_delete'] or DEFAULT_ACTION[engine], 'on_update': found['on_update'] or DEFAULT_ACTION[engine]}, **changed}
        pending.append((label, key, build_foreign_key(
            pair[1], merged, [found['ref_database'] or database, found['ref_table']], set(order),
            _columns_of(target_row, mode, engine), mode, engine), 'rename'))
    # ---- drafts
    names = {key[1] for key in clauses if key[0] in {'index', 'check', 'foreign-key'}}
    added_primary = False
    for draft in drafts:
        values = vocab.normalize(draft['physical'], 'physical draft')
        vocab.draft_identity(engine, old['uid'], draft['uid'])
        kind, name = values.get('physical_kind'), values.get('physical_name')
        if kind is None or name is None or vocab.ROLE[kind] != draft['subject_kind']:
            raise ValueError('A physical draft needs physical_kind and physical_name that match its element role')
        if values.get('drop') or 'rename_from' in values:
            raise ValueError('A new object cannot carry drop or rename_from')
        if kind == 'foreign-key':
            endpoints = draft.get('endpoints') or {}
            target_row = current['rows'].get(endpoints.get('target'))
            if endpoints.get('source') != live['resource_id'] or target_row is None or target_row['kind'] != 'table':
                raise ValueError('A new foreign key needs this table as source and a visible table as target')
            if name in names:
                raise ValueError('A constraint named ' + name + ' already exists')
            target = [target_row['native']['database'], target_row['name']]
            clause = build_foreign_key(name, values, target, set(order), _columns_of(target_row, mode, engine), mode, engine)
            target_clauses = dict(parse({'name': target_row['name'], 'native': target_row['native']}, mode)[1])
            for sibling in (all_drafts or {}).get(target_row['resource_id'], []):
                # A key drafted on the target in the same review counts: it is ordered before the foreign key.
                wanted = vocab.normalize(sibling['physical'], 'physical draft')
                if wanted.get('physical_kind') in {'primary-key', 'unique', 'index'} and wanted.get('columns'):
                    target_clauses[('index', 'draft:' + wanted.get('physical_name', ''))] = build_index(
                        'index', wanted.get('physical_name', 'draft'), wanted, set(wanted['columns']), mode, engine)
            if not _covering(target_clauses, values['referenced_columns'], mode):
                raise ValueError('The referenced columns of ' + name + ' need an index (PRIMARY KEY or UNIQUE) on the target table')
            pending.append(('FOREIGN KEY ' + name, ('foreign-key', name), clause, 'add'))
        elif kind == 'check':
            if name in names:
                raise ValueError('A constraint named ' + name + ' already exists')
            pending.append(('CHECK constraint ' + name, ('check', name), build_check(name, values, mode, engine), 'add'))
        else:
            key = _key_of(kind, name)
            if kind == 'primary-key' and (('primary', 'PRIMARY') in clauses or added_primary):
                raise ValueError('The table already has a PRIMARY KEY; replace it instead of adding a second')
            added_primary = added_primary or kind == 'primary-key'
            if kind != 'primary-key' and name in names:
                raise ValueError('An index named ' + name + ' already exists')
            kind_out = 'unique' if kind == 'index' and values.get('unique') else kind
            pending.append((kind.title() + ' ' + name, key, build_index(kind_out, name, values, set(order), mode, engine), 'add'))
        if kind != 'primary-key':
            names.add(name)
    # ---- table level
    others = bool(pending or renames or drops)
    if table_drop:
        if others or intent:
            raise ValueError('Review a table drop separately from other edits to the same table')
        native[intent_key] = {'action': 'drop', 'confirmation': old['name']}
        return native
    if table_rename:
        if others or intent:
            raise ValueError('Review a table rename separately from other edits to the same table')
        new = table_rename[1]
        if (not 1 <= len(new) <= 64 or new != new.rstrip() or any(char in new for char in '\x00/\\.')):
            raise ValueError('A table rename needs a valid new table name')
        if any(item['kind'] in {'table', 'view', 'materialized-view'} and item['name'] == new for item in current['rows'].values()):
            raise ValueError('A relation named ' + new + ' already exists')
        native[intent_key] = {'rename_table': new}
        return native
    if renames:
        if pending or drops:
            raise ValueError('Review column renames separately from other physical edits to the same table')
        if len(renames) > 128 or len(set(renames.values())) != len(renames):
            raise ValueError('Column renames need distinct new names')
        from .mysql_relational_fields import rename_definition
        if intent.get('rename_columns') not in (None, renames):
            raise ValueError('Graphical and native column rename intent disagree')
        return rename_definition({'name': live['name'], 'native': old['native']}, native, renames, mode, engine=engine)
    # ---- apply pending clause edits
    remaining_drops = set()
    for label, key, clause, action in pending:
        if clause is None and action == 'drop':
            remaining_drops.add(key)
        current_clause = clauses.get(key)
        if current_clause not in (base.get(key), clause):
            raise ValueError('Graphical and native edits of ' + label + ' disagree; reconcile one source')
        if action in {'rename', 'rename-index'}:
            new_key = (key[0], describe_name(clause, mode))
            if new_key in clauses and new_key != key:
                raise ValueError('A native object named ' + new_key[1] + ' already exists')
            clauses.pop(key, None)
            clauses[new_key] = clause
            if action == 'rename-index':
                intent.setdefault('rename_indexes', {})[key[1]] = new_key[1]
        elif action == 'drop':
            clauses.pop(key, None)
        else:
            clauses[key] = clause
        edited = True
    for column in drops:
        key = ('column', column)
        if clauses.get(key) != base.get(key):
            raise ValueError('Graphical and native edits of column ' + column + ' disagree')
        for other_key, clause in clauses.items():
            if other_key[0] in {'index', 'primary', 'foreign-key', 'check'} and other_key not in remaining_drops and _mentions(
                    clause if other_key[0] != 'check' else describe(clause, mode)['expression'], column, mode) and other_key[0] != 'column':
                raise ValueError('Column ' + column + ' is used by ' + other_key[0] + ' ' + other_key[1] + '; drop that object in the same edit first')
        clauses.pop(key)
        intent.setdefault('drop_columns', [])
        if column not in intent['drop_columns']:
            intent['drop_columns'].append(column)
        edited = True
    if not edited:
        return native
    _check_dependencies(live, current, clauses, base, mode, engine, database)
    native['definition'] = layout['prefix'] + '(' + ','.join(clauses.values()) + ')' + layout['suffix']
    if intent:
        native[intent_key] = intent
    return native


def describe_name(clause, mode):
    found = describe(clause, mode)
    return found['name']


def _target(current, database, found):
    for item in current['rows'].values():
        if item['kind'] == 'table' and item['name'] == found['ref_table'] and item['native'].get('database') == (found['ref_database'] or database):
            return item
    raise ValueError('Referenced table ' + found['ref_table'] + ' is not in the captured database')


def _columns_of(row, mode, engine):
    return set(_parts(engine)({'name': row['name'], 'native': row['native']}, mode)[2])


def _check_dependencies(live, current, clauses, base, mode, engine, database):
    """Do not leave a foreign key without the key it needs, on either side of the relationship.

    Only dependencies the baseline satisfied and this edit would break are refused; the native
    server remains the authority for everything else."""
    parse = _parts(engine)
    for key, clause in clauses.items():
        if key[0] == 'foreign-key' and base.get(key) == clause:
            columns = describe(clause, mode)['columns']
            if _covering(base, columns, mode) and not _covering(clauses, columns, mode):
                raise ValueError('Foreign key ' + key[1] + ' needs an index on ' + ', '.join(columns) +
                                 '; the edit would remove the last index it depends on')
    for row in current['rows'].values():
        if row['kind'] != 'table':
            continue
        try:
            _l, other, _o = parse({'name': row['name'], 'native': row['native']}, mode)
        except (ValueError, KeyError):
            continue
        for key, clause in other.items():
            if key[0] != 'foreign-key' or (row['name'] == live['name'] and key not in clauses):
                continue
            found = describe(clause, mode)
            if found['ref_table'] == live['name'] and (found['ref_database'] or database) == database and \
                    _covering(base, found['ref_columns'], mode) and not _covering(clauses, found['ref_columns'], mode):
                raise ValueError("Foreign keys depend on this table's key: " + row['name'] + '.' + key[1] +
                                 ' references (' + ', '.join(found['ref_columns']) + '); change or drop the foreign key first')
