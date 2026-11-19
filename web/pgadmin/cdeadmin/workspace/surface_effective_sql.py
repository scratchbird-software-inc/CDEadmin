"""Render SQL Editor result adjustments as a read-only query preview."""
from __future__ import annotations

import math

import sqlparse
from sqlparse import tokens

from .data_surface_host import _quote_ident
from .mysql_test_data import literal as mysql_literal

_ENGINES = {'postgresql', 'sqlite', 'duckdb', 'mysql', 'mariadb', 'firebird'}
_TEXT_CAST = {
    'mysql': 'CHAR CHARACTER SET utf8mb4',
    'mariadb': 'CHAR CHARACTER SET utf8mb4',
    'firebird': 'VARCHAR(8191) CHARACTER SET UTF8',
}
_COMPARISONS = {'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<='}


def _literal(value, engine):
    if '\0' in value or len(value.encode('utf-8')) > 8191:
        raise ValueError('A filter value is too long or contains an unsupported character.')
    if engine in ('mysql', 'mariadb'):
        return mysql_literal(value, engine=engine)
    if engine == 'postgresql':
        return f"CONVERT_FROM(DECODE('{value.encode().hex()}', 'hex'), 'UTF8')"
    return "'" + value.replace("'", "''") + "'"


def _filter_sql(column, column_type, predicate, engine):
    op = str(predicate.get('op') or 'contains').lower()
    value = predicate.get('value')
    if op == 'is_null':
        return f'{column} IS NULL'
    if op == 'not_null':
        return f'{column} IS NOT NULL'
    if column_type not in {'text', 'number'}:
        raise ValueError('This field type supports only NULL filters in generated SQL.')

    if value is not None and type(value) not in (str, int, float, bool) and op != 'in':
        raise ValueError('This filter value cannot be represented as SQL.')
    needle = '' if value is None else str(value)
    text = f'CAST({column} AS {_TEXT_CAST.get(engine, "TEXT")})'
    if op in _COMPARISONS:
        try:
            numeric = float(needle)
        except ValueError:
            return f'{text} {_COMPARISONS[op]} {_literal(needle, engine)}'
        if column_type != 'number' or not math.isfinite(numeric):
            raise ValueError('A numeric comparison requires a numeric result column.')
        return f'{column} {_COMPARISONS[op]} {numeric!r}'

    folded = f'LOWER({text})'
    if op in ('eq', 'neq'):
        operator = '=' if op == 'eq' else '<>'
        return f'{folded} {operator} {_literal(needle.lower(), engine)}'
    if op == 'in':
        choices = ([str(item).strip().lower() for item in value] if isinstance(value, list)
                   else [part.strip().lower() for part in needle.split(',') if part.strip()])
        return (f'{folded} IN (' + ', '.join(_literal(item, engine) for item in choices) + ')'
                if choices else '1 = 0')
    if op in ('contains', 'starts_with', 'ends_with'):
        pattern = needle.lower().replace('!', '!!').replace('%', '!%').replace('_', '!_')
        if op != 'starts_with':
            pattern = '%' + pattern
        if op != 'ends_with':
            pattern += '%'
        return f"{folded} LIKE {_literal(pattern, engine)} ESCAPE '!'"
    raise ValueError('This result filter is unavailable in generated SQL.')


def _sort_sql(column, column_type, values, direction, engine):
    if column_type not in {'text', 'number', 'boolean'}:
        raise ValueError('This result column cannot be sorted equivalently in generated SQL.')
    if column_type == 'text':
        for value in values:
            if value is None:
                continue
            try:
                float(value)
            except (TypeError, ValueError):
                continue
            raise ValueError('Text columns with numeric-looking values use host-only sorting.')
        expression = f'LOWER(CAST({column} AS {_TEXT_CAST.get(engine, "TEXT")}))'
    else:
        expression = column
    # Match the host's NULL-first ascending and NULL-last descending policy.
    return (f'CASE WHEN {column} IS NULL THEN 0 ELSE 1 END {direction}',
            f'{expression} {direction}')


def read_only_select(source):
    """Return structural tokens for a single SELECT without DML or locking."""
    try:
        statements = sqlparse.parse(source)
        if len(statements) != 1 or statements[0].get_type() != 'SELECT':
            return []
        significant = [
            token for token in statements[0].flatten()
            if not (token.is_whitespace or token.ttype in tokens.Comment)
        ]
    except (sqlparse.exceptions.SQLParseError, RecursionError):
        return []
    if any(
        token.ttype in tokens.Keyword and token.normalized in {
            'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'INTO', 'FOR UPDATE', 'FOR SHARE', 'WITH LOCK',
        }
        for token in significant
    ):
        return []
    return significant


def _column_type(column, rows, engine):
    column_type = column.get('client_type', 'text')
    if engine == 'postgresql' and isinstance(column.get('source_type_code'), int):
        from psycopg import adapters
        type_info = adapters.types.get(column['source_type_code'])
        if type_info and type_info.name in ('int2', 'int4', 'int8', 'float4', 'float8', 'numeric', 'oid'):
            return 'number'
    if engine in ('mysql', 'mariadb') and isinstance(column.get('source_type_code'), int):
        if engine == 'mariadb':
            from mariadb.constants import FIELD_TYPE as native_type
        else:
            from mysql.connector.constants import FieldType as native_type
        if column['source_type_code'] in {
            native_type.TINY, native_type.SHORT, native_type.LONG, native_type.LONGLONG,
            native_type.INT24, native_type.FLOAT, native_type.DOUBLE,
            native_type.DECIMAL, native_type.NEWDECIMAL, native_type.YEAR,
        }:
            return 'number'
    if column_type == 'longtext':
        column_type = 'text'
    if column.get('native_type', '').upper() == 'DYNAMIC':
        observed = {type(row['values'].get(column['name'])) for row in rows} - {type(None)}
        if observed and observed <= {int, float}:
            return 'number'
        if observed and observed != {str}:
            return 'dynamic'
    return column_type


def build_effective_select(result, engine_id, *, client_sql_dialect=None):
    """Describe an effective SELECT, or explain why it cannot be generated."""
    source = result.statement_sql.strip()
    engine = 'firebird' if engine_id == 'firebird-embedded' else engine_id
    significant = read_only_select(source)
    if not significant or not result.columns:
        return {'sql': '', 'reason': 'The active result does not come from a wrappable SELECT statement.'}
    if result.staged_mutations:
        return {'sql': '', 'reason': 'Apply or discard staged row edits before generating SQL.'}
    buffer_limited = not result.complete_in_buffer or result.retrieval_limited
    if not (result.filters or result.sorts):
        return {'sql': source, 'buffer_limited': buffer_limited}

    if engine not in _ENGINES:
        return {'sql': '', 'reason': 'This SQL dialect does not support generated result queries.'}
    if engine == 'firebird' and client_sql_dialect not in (None, 3):
        return {'sql': '', 'reason': 'Generated result adjustments require Firebird SQL dialect 3.'}

    if any(token.normalized == ';' for token in significant[:-1]):
        return {'sql': '', 'reason': 'Only one SELECT statement can be wrapped.'}
    if significant[-1].normalized == ';':
        # Drop only the final delimiter, which may precede trailing comments.
        source = source[:-1].rstrip() if source.endswith(';') else ''
        if not source:
            return {'sql': '', 'reason': 'Remove trailing comments after the statement delimiter.'}

    adjusted_columns = {str(item.get('column') or '') for item in (*result.filters, *result.sorts)}
    column_map = {
        column['name']: (
            f'SR_COL_{index}',
            _column_type(column, result.raw_rows, engine) if column['name'] in adjusted_columns else None,
        )
        for index, column in enumerate(result.columns, 1)
    }
    aliases = ', '.join(column for column, _ in column_map.values())
    projection = ', '.join(
        f'{alias} AS {_quote_ident(name, engine)}' for name, (alias, _) in column_map.items()
    )
    # Pick a CTE name absent from the original statement to avoid shadowing a
    # table the user mentioned, including in a nested or quoted reference.
    relation = 'SR_RESULT_VIEW'
    while relation.lower() in source.lower():
        relation += '_Q'

    try:
        criteria = [
            _filter_sql(*column_map[predicate['column']], predicate, engine)
            for predicate in result.filters
        ]
        ordering = []
        for sort in result.sorts:
            name = sort['column']
            direction = 'DESC' if str(sort.get('direction') or sort.get('dir')).lower() == 'desc' else 'ASC'
            ordering.extend(_sort_sql(
                *column_map[name],
                (row['values'].get(name) for row in result.raw_rows),
                direction,
                engine,
            ))
    except (KeyError, TypeError):
        return {'sql': '', 'reason': 'An adjustment does not reference an active result column.'}
    except ValueError as error:
        return {'sql': '', 'reason': str(error)}

    cte_prefix = 'WITH '
    if significant[0].normalized == 'WITH':
        # Firebird forbids a second WITH inside a CTE. Add a sibling CTE that
        # reads the original top-level SELECT instead of nesting its WITH.
        head = []
        tail = []
        for token in sqlparse.parse(source)[0].tokens:
            if tail or token.ttype in tokens.DML and token.normalized == 'SELECT':
                tail.append(str(token))
            else:
                head.append(str(token))
        if not tail:
            return {'sql': '', 'reason': 'The original WITH SELECT cannot be wrapped.'}
        cte_prefix = ''.join(head) + '\n, '
        source = ''.join(tail)
    where = '\nWHERE ' + ' AND '.join(criteria) if criteria else ''
    order = '\nORDER BY ' + ', '.join(ordering) if ordering else ''
    return {
        'sql': f'{cte_prefix}{relation} ({aliases}) AS (\n{source}\n)\n'
               f'SELECT {projection}\nFROM {relation}{where}{order}',
        'native_comparison': True,
        'buffer_limited': buffer_limited,
    }
