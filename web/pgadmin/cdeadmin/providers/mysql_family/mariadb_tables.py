"""MariaDB native table creation, alteration, generated/temporal/period columns,
partitioning hooks, engine-option validation and catalog pre-fill enrichment.
"""
from collections.abc import Mapping
from copy import deepcopy
import re

from ...sdk import RelationalClientError
from ...workspace.mysql_physical import safe_expression
from .mariadb_catalog import identifier as quote_identifier
from .mysql_table_options import default_sql

TEXT_OPTIONS = {
    'engine': 'ENGINE',
    'comment': 'COMMENT',
    'character_set': 'DEFAULT CHARACTER SET',
    'collation': 'DEFAULT COLLATE',
    'data_directory': 'DATA DIRECTORY',
    'index_directory': 'INDEX DIRECTORY',
    'connection': 'CONNECTION',
}

NUMBER_OPTIONS = {
    'auto_increment',
    'max_rows',
    'min_rows',
    'avg_row_length',
    'stats_sample_pages',
    'key_block_size',
    'encryption_key_id',
}

CHOICE_OPTIONS = {
    'row_format': {'DEFAULT', 'DYNAMIC', 'COMPRESSED', 'COMPACT', 'REDUNDANT', 'PAGE', 'FIXED'},
    'page_compressed': {'0', '1'},
    'page_compression_level': {str(i) for i in range(0, 10)},
    'encrypted': {'DEFAULT', 'YES', 'NO'},
    'transactional': {'DEFAULT', '0', '1'},
    'page_checksum': {'0', '1'},
    'stats_persistent': {'DEFAULT', '0', '1'},
    'stats_auto_recalc': {'DEFAULT', '0', '1'},
    'pack_keys': {'DEFAULT', '0', '1'},
    'checksum': {'0', '1'},
    'delay_key_write': {'0', '1'},
    'ietf_quotes': {'YES', 'NO'},
    'insert_method': {'NO', 'FIRST', 'LAST'},
}

CREATE_ONLY_OPTIONS = frozenset({'data_directory', 'index_directory'})

OPTION_KEYS = (
    set(TEXT_OPTIONS)
    | NUMBER_OPTIONS
    | set(CHOICE_OPTIONS)
    | {'charset', 'tablespace'}
)

TOP_LEVEL_CREATE_EXTRAS = frozenset({
    'mariadb_table_options',
    'temporary',
    'system_versioning',
    'system_time_period',
    'application_periods',
    'partition_method',
    'partition_expression',
    'system_time_interval',
    'system_time_limit',
    'partition_count',
    'partition_definitions',
})

ARIA_ONLY_OPTIONS = frozenset({'transactional', 'page_checksum'})
INNODB_ONLY_OPTIONS = frozenset({'page_compressed', 'page_compression_level'})
GENERATION_KINDS = ('NONE', 'VIRTUAL', 'PERSISTENT', 'STORED')
SYSTEM_TIME_ROLES = ('NONE', 'ROW_START', 'ROW_END')
PARTITION_METHODS = (
    'NONE',
    'RANGE',
    'RANGE COLUMNS',
    'LIST',
    'LIST COLUMNS',
    'HASH',
    'LINEAR HASH',
    'KEY',
    'LINEAR KEY',
    'SYSTEM_TIME',
)


def identifier(value):
    try:
        if isinstance(value, str):
            value.encode('utf8')
        return quote_identifier(value)
    except ValueError:
        raise RelationalClientError('Native MariaDB identifier must be nonempty text without NUL') from None


def _normalize_option_dict(raw):
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise RelationalClientError('MariaDB table options require an object')
    result = {}
    for key, value in raw.items():
        if key not in OPTION_KEYS:
            raise RelationalClientError(f'Unknown MariaDB table option: {key}')
        if value in (None, ''):
            continue
        canonical_key = 'character_set' if key == 'charset' else key
        if canonical_key in result and result[canonical_key] != value:
            raise RelationalClientError(f'Conflicting MariaDB {canonical_key} selections')
        if type(value) is bool and canonical_key in {'page_compressed', 'transactional', 'page_checksum', 'checksum', 'delay_key_write'}:
            value = '1' if value else '0'
        elif type(value) is int and canonical_key in {'page_compression_level', 'encryption_key_id', 'auto_increment', 'key_block_size'}:
            value = str(value)
        result[canonical_key] = value
    return result


def selected_options(container):
    base = _normalize_option_dict(container.get('mariadb_table_options', {}))
    for key in OPTION_KEYS & set(container):
        if container[key] in (None, ''):
            continue
        canonical_key = 'character_set' if key == 'charset' else key
        val = container[key]
        if type(val) is bool and canonical_key in {'page_compressed', 'transactional', 'page_checksum', 'checksum', 'delay_key_write'}:
            val = '1' if val else '0'
        elif type(val) is int and canonical_key in {'page_compression_level', 'encryption_key_id', 'auto_increment', 'key_block_size'}:
            val = str(val)
        if canonical_key in base and base[canonical_key] != val:
            raise RelationalClientError(f'Conflicting MariaDB {canonical_key} table options')
        base[canonical_key] = val
    return base


def validate_engine_combinations(options, *, is_alter=False, temporary=False, system_versioning=False, baseline_engine=None):
    if is_alter and (set(options) & CREATE_ONLY_OPTIONS):
        raise RelationalClientError(
            'DATA DIRECTORY and INDEX DIRECTORY are create-only in MariaDB; ALTER TABLE cannot change them'
        )
    if temporary and system_versioning:
        raise RelationalClientError('MariaDB temporary tables cannot use WITH SYSTEM VERSIONING')

    engine = options.get('engine') or baseline_engine
    engine_upper = str(engine).strip().upper() if isinstance(engine, str) and engine.strip() else None

    if system_versioning and engine_upper in {'MEMORY', 'CSV', 'BLACKHOLE', 'MERGE', 'MRG_MYISAM', 'SEQUENCE'}:
        raise RelationalClientError(f'MariaDB storage engine {engine} does not support system-versioned tables')

    if engine_upper is not None and engine_upper != 'ARIA':
        bad_aria = sorted(ARIA_ONLY_OPTIONS & set(options))
        if bad_aria:
            raise RelationalClientError(
                f"MariaDB option {', '.join(bad_aria).upper()} belongs to the Aria storage engine, not {engine}"
            )
        if options.get('row_format') == 'PAGE':
            raise RelationalClientError(f'ROW_FORMAT=PAGE belongs to the Aria storage engine, not {engine}')

    if engine_upper is not None and engine_upper != 'INNODB':
        bad_inno = sorted(INNODB_ONLY_OPTIONS & set(options))
        if bad_inno:
            raise RelationalClientError(
                f"MariaDB option {', '.join(bad_inno).upper()} belongs to InnoDB, not {engine}"
            )
        if options.get('row_format') in {'COMPRESSED', 'COMPACT', 'REDUNDANT'}:
            raise RelationalClientError(
                f"ROW_FORMAT={options['row_format']} belongs to InnoDB, not {engine}"
            )
        if 'tablespace' in options:
            raise RelationalClientError(f'TABLESPACE option belongs to InnoDB, not {engine}')

    if 'ietf_quotes' in options and engine_upper is not None and engine_upper != 'CSV':
        raise RelationalClientError(f'IETF_QUOTES belongs to the CSV storage engine, not {engine}')

    if 'page_compression_level' in options and options.get('page_compressed') == '0':
        raise RelationalClientError('PAGE_COMPRESSION_LEVEL requires PAGE_COMPRESSED=1')

    if 'encryption_key_id' in options and options.get('encrypted') == 'NO':
        raise RelationalClientError('ENCRYPTION_KEY_ID cannot be combined with ENCRYPTED=NO')


def compile_table_options(options, *, is_alter=False, temporary=False, system_versioning=False, baseline_engine=None):
    options = _normalize_option_dict(options)
    validate_engine_combinations(
        options,
        is_alter=is_alter,
        temporary=temporary,
        system_versioning=system_versioning,
        baseline_engine=baseline_engine,
    )
    clauses = []
    parameters = []
    for key, item in options.items():
        if key in {'engine', 'character_set', 'collation'}:
            if not isinstance(item, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}', item.strip()):
                raise RelationalClientError(f'MariaDB {key} requires a valid native identifier')
            clauses.append(f'{TEXT_OPTIONS[key]}={item.strip()}')
        elif key in TEXT_OPTIONS:
            if not isinstance(item, str) or '\x00' in item or len(item.encode('utf8')) > 16384:
                raise RelationalClientError(f'MariaDB {key} requires bounded UTF-8 text without NUL')
            clauses.append(f'{TEXT_OPTIONS[key]}=%s')
            parameters.append(item)
        elif key in NUMBER_OPTIONS:
            if key == 'stats_sample_pages' and item == 'DEFAULT':
                clauses.append('STATS_SAMPLE_PAGES=DEFAULT')
                continue
            if not isinstance(item, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,19})', item) or int(item) > 2**64 - 1:
                raise RelationalClientError(f'MariaDB {key} requires unsigned decimal text')
            if key == 'encryption_key_id' and not (1 <= int(item) <= 4294967295):
                raise RelationalClientError('MariaDB ENCRYPTION_KEY_ID must be between 1 and 4294967295')
            clauses.append(f'{key.upper()}={item}')
        elif key in CHOICE_OPTIONS:
            val_str = str(item).upper() if key not in {'page_compression_level'} else str(item)
            if val_str not in CHOICE_OPTIONS[key]:
                raise RelationalClientError(f'Select a supported MariaDB {key} value')
            clauses.append(f'{key.upper()}={val_str}')
        elif key == 'tablespace':
            clauses.append(f'TABLESPACE={identifier(item)}')
    if system_versioning and not is_alter:
        clauses.append('WITH SYSTEM VERSIONING')
    return (' ' + ' '.join(clauses) if clauses else ''), tuple(parameters)


def compile_column_clause(admin, column, base_column_fn=None):
    """Compile one MariaDB column definition including generated/temporal/invisible/comment clauses."""
    if not isinstance(column, Mapping):
        raise RelationalClientError('Column definition must be an object')
    allowed = {
        'name', 'type', 'nullable', 'default', 'unique', 'primary_key',
        'generation_kind', 'generation_expression',
        'generated_storage', 'generated_expression',
        'invisible',
        'system_time_role', 'system_period_role',
        'comment', '_id',
    }
    if set(column) - allowed:
        raise RelationalClientError('Unknown MariaDB column property: ' + ', '.join(sorted(set(column) - allowed)))

    raw_gen_kind = column.get('generated_storage') if column.get('generated_storage') not in (None, '') else column.get('generation_kind')
    gen_kind = str(raw_gen_kind or 'NONE').upper()
    if gen_kind not in GENERATION_KINDS:
        raise RelationalClientError('Column generation kind must be NONE, VIRTUAL, PERSISTENT or STORED')
    gen_expr = column.get('generated_expression') if column.get('generated_expression') not in (None, '') else column.get('generation_expression')

    raw_sys_role = column.get('system_period_role') if column.get('system_period_role') not in (None, '') else column.get('system_time_role')
    sys_role = str(raw_sys_role or 'NONE').upper()
    if sys_role not in SYSTEM_TIME_ROLES:
        raise RelationalClientError('Column system_time_role must be NONE, ROW_START or ROW_END')

    invisible = column.get('invisible', False)
    if type(invisible) is not bool:
        raise RelationalClientError('Column invisible flag must be boolean')

    if gen_kind != 'NONE' and sys_role != 'NONE':
        raise RelationalClientError('A column cannot combine generated expression and ROW START/END')
    if gen_kind != 'NONE':
        if column.get('default') not in (None, ''):
            raise RelationalClientError('Generated columns cannot declare a DEFAULT expression')
        expr = safe_expression(gen_expr, '', 'generated column expression')
        col_name = admin._identifier(column.get('name'))
        col_type = admin._safe_type(column.get('type'), 'Column type')
        parts = [col_name, f'{col_type} GENERATED ALWAYS AS ({expr}) {gen_kind}']
        if column.get('nullable') is False or column.get('primary_key') is True:
            parts.append('NOT NULL')
        if column.get('primary_key') is True:
            parts.append('PRIMARY KEY')
        elif column.get('unique') is True:
            parts.append('UNIQUE')
    elif sys_role != 'NONE':
        if column.get('default') not in (None, ''):
            raise RelationalClientError('System-time ROW START/END columns cannot declare a DEFAULT expression')
        col_name = admin._identifier(column.get('name'))
        col_type = admin._safe_type(column.get('type') or 'TIMESTAMP(6)', 'Column type')
        role_sql = 'ROW START' if sys_role == 'ROW_START' else 'ROW END'
        parts = [col_name, f'{col_type} GENERATED ALWAYS AS {role_sql}']
        if column.get('nullable') is False:
            parts.append('NOT NULL')
    else:
        if gen_expr not in (None, ''):
            raise RelationalClientError('Select VIRTUAL, PERSISTENT or STORED for a generated column expression')
        base_col = {k: v for k, v in column.items() if k in {'name', 'type', 'nullable', 'default', 'unique', 'primary_key'}}
        render_base = base_column_fn or getattr(admin, '_base_column_definition', None)
        if render_base is None:
            from ..relational_admin import RelationalAdministration
            render_base = lambda item: RelationalAdministration._column_definition(admin, item)
        parts = [render_base(base_col)]

    if invisible:
        parts.append('INVISIBLE')

    comment = column.get('comment')
    if comment not in (None, ''):
        if not isinstance(comment, str) or '\x00' in comment or len(comment.encode('utf8')) > 4096:
            raise RelationalClientError('Column comment requires bounded UTF-8 text without NUL')
        escaped = comment.replace('\\', '\\\\').replace("'", "''")
        parts.append(f"COMMENT '{escaped}'")

    return ' '.join(parts)


def compile_constraint_clause(admin, item, base_constraint_fn=None):
    if not isinstance(item, Mapping):
        raise RelationalClientError('Constraint definition must be an object')
    kind = str(item.get('kind', '')).upper()
    without_overlaps_period = (
        item.get('without_overlaps')
        if item.get('without_overlaps') not in (None, '')
        else item.get('without_overlaps_period')
    )
    base_item = {
        k: v for k, v in item.items()
        if k not in {'on_delete', 'on_update', 'without_overlaps', 'without_overlaps_period', '_id'}
    }
    if without_overlaps_period not in (None, ''):
        if kind not in {'PRIMARY KEY', 'UNIQUE'}:
            raise RelationalClientError('WITHOUT OVERLAPS is supported only on PRIMARY KEY and UNIQUE constraints')
        cols = base_item.get('columns')
        if not isinstance(cols, list) or not cols:
            raise RelationalClientError('Constraint columns are required before WITHOUT OVERLAPS')
        prefix = f"CONSTRAINT {admin._identifier(base_item['name'])} " if base_item.get('name') else ''
        col_sql = ', '.join(admin._identifier(c) for c in cols)
        source = f'{prefix}{kind} ({col_sql}, {identifier(without_overlaps_period)} WITHOUT OVERLAPS)'
    else:
        render_constraint = base_constraint_fn or getattr(admin, '_base_constraint_definition', None)
        if render_constraint is None:
            from ..relational_admin import RelationalAdministration
            render_constraint = lambda val: RelationalAdministration._constraint_definition(admin, val)
        source = render_constraint(base_item)

    for field in ('on_delete', 'on_update'):
        if item.get(field) in (None, ''):
            continue
        action = str(item[field]).upper()
        if kind != 'FOREIGN KEY' or action not in {'RESTRICT', 'CASCADE', 'SET NULL', 'NO ACTION'}:
            raise RelationalClientError('Select a MariaDB foreign-key action (RESTRICT, CASCADE, SET NULL, NO ACTION)')
        source += f" {field.replace('_', ' ').upper()} {action}"
    return source


def compile_period_clauses(options):
    if options in (None, '', [], {}):
        return []
    if isinstance(options, list):
        sys_period = None
        app_periods = options
    elif isinstance(options, Mapping):
        sys_period = options.get('system_time_period')
        if options.get('periods') is not None and options.get('application_periods') is not None and options['periods'] != options['application_periods']:
            raise RelationalClientError('Conflicting MariaDB application period definitions')
        app_periods = options.get('periods') if options.get('periods') is not None else (options.get('application_periods') or [])
    else:
        raise RelationalClientError('MariaDB period definitions must be a list or options object')

    clauses = []
    if sys_period not in (None, {}, ''):
        if not isinstance(sys_period, Mapping) or set(sys_period) - {'start_column', 'end_column'}:
            raise RelationalClientError('system_time_period requires start_column and end_column')
        start_col = sys_period.get('start_column')
        end_col = sys_period.get('end_column')
        if start_col or end_col:
            if not start_col or not end_col or start_col == end_col:
                raise RelationalClientError('PERIOD FOR SYSTEM_TIME requires distinct start and end column names')
            clauses.append(f'PERIOD FOR SYSTEM_TIME ({identifier(start_col)}, {identifier(end_col)})')

    if not isinstance(app_periods, list) or len(app_periods) > 32:
        raise RelationalClientError('application_periods must be a list of at most 32 period definitions')
    seen = set()
    for period in app_periods:
        if not isinstance(period, Mapping) or set(period) - {'name', 'start_column', 'end_column', '_id'}:
            raise RelationalClientError('Each application period requires name, start_column and end_column')
        p_name = period.get('name')
        s_col = period.get('start_column')
        e_col = period.get('end_column')
        if not p_name or str(p_name).upper() == 'SYSTEM_TIME':
            raise RelationalClientError('Application period name cannot be empty or SYSTEM_TIME')
        if p_name in seen or not s_col or not e_col or s_col == e_col:
            raise RelationalClientError('Application period requires unique name and distinct boundary columns')
        seen.add(p_name)
        clauses.append(f'PERIOD FOR {identifier(p_name)} ({identifier(s_col)}, {identifier(e_col)})')
    return clauses


def compile_partition_clause(options, *, system_versioning=False):
    if options in (None, '', {}):
        return ''
    if not isinstance(options, Mapping):
        raise RelationalClientError('MariaDB partition_by configuration must be an object')
    nested = options.get('partition_by')
    if nested is not None and not isinstance(nested, Mapping):
        raise RelationalClientError('MariaDB partition_by must be an object')
    is_direct_partition_obj = (
        nested is None
        and bool(options)
        and set(options) <= {'method', 'expression', 'columns', 'count', 'partitions', 'system_time_interval', 'system_time_limit'}
    )
    part_obj = dict(options) if is_direct_partition_obj else dict(nested or {})
    method = str(part_obj.get('method') or options.get('partition_method') or 'NONE').upper()
    expr_raw = part_obj.get('expression') if part_obj.get('expression') not in (None, '') else options.get('partition_expression')
    cols_raw = part_obj.get('columns') if part_obj.get('columns') not in (None, [], '') else options.get('partition_columns')
    count_raw = part_obj.get('count') if part_obj.get('count') not in (None, '') else options.get('partition_count')
    defs_raw = part_obj.get('partitions') if part_obj.get('partitions') is not None else options.get('partition_definitions')
    interval_raw = part_obj.get('system_time_interval') if part_obj.get('system_time_interval') not in (None, '') else options.get('system_time_interval')
    limit_raw = part_obj.get('system_time_limit') if part_obj.get('system_time_limit') not in (None, '') else options.get('system_time_limit')

    if method not in PARTITION_METHODS:
        raise RelationalClientError('Select a supported MariaDB PARTITION BY method')
    if method == 'NONE':
        for extra_name, extra_val in (
            ('partition_expression', expr_raw),
            ('partition_columns', cols_raw),
            ('system_time_interval', interval_raw),
            ('system_time_limit', limit_raw),
            ('partition_count', count_raw),
            ('partition_definitions', defs_raw),
        ):
            if extra_val not in (None, '', [], 0):
                raise RelationalClientError(f'{extra_name} requires selecting a MariaDB partition_method')
        return ''

    if method == 'SYSTEM_TIME':
        if not system_versioning:
            raise RelationalClientError('PARTITION BY SYSTEM_TIME requires WITH SYSTEM VERSIONING')
        header = 'PARTITION BY SYSTEM_TIME'
        if interval_raw not in (None, '') and limit_raw not in (None, ''):
            raise RelationalClientError('Specify either INTERVAL or LIMIT for PARTITION BY SYSTEM_TIME, not both')
        if interval_raw not in (None, ''):
            if not isinstance(interval_raw, str) or not re.fullmatch(
                r'[1-9][0-9]{0,8}\s+(?:MICROSECOND|SECOND|MINUTE|HOUR|DAY|WEEK|MONTH|QUARTER|YEAR)',
                interval_raw.strip(),
                re.I,
            ):
                raise RelationalClientError('SYSTEM_TIME INTERVAL requires e.g. "1 DAY" or "1 MONTH"')
            header += ' INTERVAL ' + interval_raw.strip().upper()
        elif limit_raw not in (None, ''):
            if type(limit_raw) is not int or not 1 <= limit_raw <= 2147483647:
                raise RelationalClientError('SYSTEM_TIME LIMIT requires a positive integer')
            header += f' LIMIT {limit_raw}'
    elif method in {'RANGE COLUMNS', 'LIST COLUMNS', 'KEY', 'LINEAR KEY'}:
        cols_input = cols_raw if cols_raw not in (None, [], '') else expr_raw
        cols = [c.strip() for c in str(cols_input or '').split(',') if c.strip()] if isinstance(cols_input, str) else cols_input
        if not isinstance(cols, list) or not cols:
            if method in {'KEY', 'LINEAR KEY'}:
                col_sql = ''
            else:
                raise RelationalClientError(f'{method} requires one or more column names')
        else:
            col_sql = ', '.join(identifier(c) for c in cols)
        header = f'PARTITION BY {method} ({col_sql})'
    else:
        expr = safe_expression(expr_raw, '', f'{method} partition expression')
        header = f'PARTITION BY {method} ({expr})'

    if count_raw not in (None, ''):
        if type(count_raw) is not int or not 1 <= count_raw <= 8192:
            raise RelationalClientError('partition_count must be an integer between 1 and 8192')
        header += f' PARTITIONS {count_raw}'

    defs = defs_raw or []
    if defs:
        if not isinstance(defs, list) or len(defs) > 1024:
            raise RelationalClientError('partition_definitions must be a bounded list')
        compiled_defs = []
        for row in defs:
            if not isinstance(row, Mapping) or set(row) - {'name', 'kind', 'bound', 'comment', '_id'}:
                raise RelationalClientError('Invalid MariaDB partition definition record')
            p_name = identifier(row.get('name'))
            bound = row.get('bound')
            if row.get('kind'):
                p_kind = str(row['kind']).upper()
            elif method == 'SYSTEM_TIME' and isinstance(bound, str) and bound.strip().upper() in {'HISTORY', 'CURRENT'}:
                p_kind = bound.strip().upper()
            elif method in {'LIST', 'LIST COLUMNS'}:
                p_kind = 'VALUES IN'
            else:
                p_kind = 'VALUES LESS THAN'
            if p_kind == 'HISTORY':
                if method != 'SYSTEM_TIME':
                    raise RelationalClientError('HISTORY partition kind belongs to PARTITION BY SYSTEM_TIME')
                clause = f'PARTITION {p_name} HISTORY'
            elif p_kind == 'CURRENT':
                if method != 'SYSTEM_TIME':
                    raise RelationalClientError('CURRENT partition kind belongs to PARTITION BY SYSTEM_TIME')
                clause = f'PARTITION {p_name} CURRENT'
            elif p_kind == 'DEFAULT':
                clause = f'PARTITION {p_name} DEFAULT'
            elif p_kind == 'VALUES LESS THAN':
                if not isinstance(bound, str) or not bound.strip():
                    raise RelationalClientError('VALUES LESS THAN partition requires a bound expression or MAXVALUE')
                bound_clean = 'MAXVALUE' if bound.strip().upper() == 'MAXVALUE' else '(' + safe_expression(bound, '', 'partition bound') + ')'
                clause = f'PARTITION {p_name} VALUES LESS THAN {bound_clean}'
            elif p_kind == 'VALUES IN':
                expr_in = safe_expression(bound, '', 'partition VALUES IN list')
                clause = f'PARTITION {p_name} VALUES IN ({expr_in})'
            else:
                raise RelationalClientError('Unsupported MariaDB partition definition kind')
            if row.get('comment') not in (None, ''):
                c_text = str(row['comment'])
                if '\x00' in c_text or len(c_text) > 1024:
                    raise RelationalClientError('Partition comment requires bounded text without NUL')
                escaped = c_text.replace('\\', '\\\\').replace("'", "''")
                clause += f" COMMENT = '{escaped}'"
            compiled_defs.append(clause)
        header += ' (' + ', '.join(compiled_defs) + ')'

    return ' ' + header


CATALOG_CREATE_OPTIONS = {
    'max_rows', 'min_rows', 'avg_row_length', 'row_format', 'stats_sample_pages',
    'stats_auto_recalc', 'key_block_size', 'stats_persistent', 'pack_keys',
    'checksum', 'delay_key_write', 'page_compressed', 'page_compression_level',
    'encrypted', 'encryption_key_id', 'transactional', 'page_checksum', 'ietf_quotes',
}


def parse_create_options(create_options_text, ddl_source=''):
    found = {}
    for key, item in re.findall(r'([A-Za-z_]+)=("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\S+)', create_options_text or ''):
        lower = key.lower()
        if lower not in CATALOG_CREATE_OPTIONS:
            continue
        if (item.startswith('"') and item.endswith('"')) or (item.startswith("'") and item.endswith("'")):
            item = item[1:-1]
        found[lower] = item.upper() if lower in {'row_format', 'encrypted', 'ietf_quotes'} else item
    if ddl_source:
        tail = ddl_source.rpartition('\n)')[2] if '\n)' in ddl_source else ''
        inc = re.search(r'\bAUTO_INCREMENT=(\d+)', tail, re.I)
        if inc:
            found['auto_increment'] = inc.group(1)
        tspace = re.search(r'\bTABLESPACE=`((?:``|[^`])+)`', tail, re.I)
        if tspace:
            found['tablespace'] = tspace.group(1).replace('``', '`')
    return found


def enrich_catalog_tables_and_children(optional, optional_records, resources, resource_key, add, server_mode=None):
    """Enrich MariaDB committed tables, columns and constraints for full family-editor reopen."""
    if server_mode is None:
        server_mode = resources.get('server:MariaDB', {}).get('native', {}).get('sql_mode') or ''
    else:
        server_mode = server_mode or ''
    table_facts = {}
    for row in optional(
        'SELECT t.TABLE_SCHEMA, t.TABLE_NAME, t.ENGINE, t.TABLE_COLLATION, c.CHARACTER_SET_NAME, '
        't.TABLE_COMMENT, t.CREATE_OPTIONS, t.TABLE_TYPE '
        'FROM information_schema.TABLES t '
        'LEFT JOIN information_schema.COLLATIONS c ON c.COLLATION_NAME = t.TABLE_COLLATION '
        "WHERE t.TABLE_TYPE IN ('BASE TABLE', 'SYSTEM VERSIONED') "
        "AND t.TABLE_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')"
    ):
        schema_name, table_name = str(row[0]), str(row[1])
        t_key = resource_key('table', [schema_name], table_name)
        if t_key not in resources:
            continue
        t_native = resources[t_key].setdefault('native', {})
        ddl = t_native.get('ddl') or ''
        parsed_opts = parse_create_options(row[6], ddl)
        sys_versioned = (
            str(row[7]).upper() == 'SYSTEM VERSIONED'
            or 'WITH SYSTEM VERSIONING' in ddl.upper()
            or 'system_versioned' in str(row[6] or '').lower()
        )
        t_native.update(
            engine=row[2],
            table_collation=row[3],
            table_character_set=row[4],
            table_comment=row[5],
            system_versioning=sys_versioned,
            table_options=parsed_opts,
        )
        table_facts[(schema_name, table_name)] = t_native

    for record in optional_records(
        'SELECT TABLE_SCHEMA, TABLE_NAME, PERIOD AS PERIOD_NAME, START_COLUMN_NAME, END_COLUMN_NAME '
        'FROM information_schema.PERIODS '
        "WHERE TABLE_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys') "
        'ORDER BY TABLE_SCHEMA, TABLE_NAME, PERIOD'
    ):
        t_key = resource_key('table', [record['table_schema']], record['table_name'])
        if t_key not in resources:
            continue
        t_native = resources[t_key].setdefault('native', {})
        if str(record['period_name']).upper() == 'SYSTEM_TIME':
            t_native['system_time_period'] = {
                'start_column': record['start_column_name'],
                'end_column': record['end_column_name'],
            }
            t_native['system_versioning'] = True
        else:
            t_native.setdefault('application_periods', []).append({
                'name': record['period_name'],
                'start_column': record['start_column_name'],
                'end_column': record['end_column_name'],
            })

    for record in optional_records(
        'SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, DATA_TYPE, '
        'IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY, EXTRA, GENERATION_EXPRESSION, COLUMN_COMMENT '
        'FROM information_schema.COLUMNS '
        "WHERE TABLE_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys') "
        'ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION'
    ):
        schema_name = record.get('table_schema')
        table_name = record.get('table_name')
        col_name = record.get('column_name')
        if not all(isinstance(v, str) for v in (schema_name, table_name, col_name)):
            continue
        c_key = resource_key('column', [schema_name, table_name], col_name)
        if c_key not in resources:
            continue
        c_native = resources[c_key].setdefault('native', {})
        extra_str = str(record.get('extra') or '')
        extra_upper = extra_str.upper()
        gen_kind = 'NONE'
        if 'PERSISTENT' in extra_upper or 'STORED GENERATED' in extra_upper:
            gen_kind = 'PERSISTENT'
        elif 'VIRTUAL GENERATED' in extra_upper or 'VIRTUAL' in extra_upper and record.get('generation_expression'):
            gen_kind = 'VIRTUAL'
        sys_role = (
            'ROW_START' if 'ROW START' in extra_upper
            else 'ROW_END' if 'ROW END' in extra_upper
            else 'NONE'
        )
        c_native.update(
            catalog_metadata=record,
            extra=extra_str,
            invisible='INVISIBLE' in extra_upper.split(),
            generation_kind=gen_kind,
            generation_expression=record.get('generation_expression') if gen_kind != 'NONE' else None,
            system_time_role=sys_role,
            column_comment=record.get('column_comment') or '',
            default_sql=(
                None if gen_kind != 'NONE' or sys_role != 'NONE'
                else default_sql(record.get('column_default'), record.get('data_type'), extra_str, server_mode)
            ),
            type_sql=str(record.get('column_type')) + (
                ' AUTO_INCREMENT' if 'auto_increment' in extra_str.lower() else ''
            ),
        )

    constraint_facts = {}
    for record in optional_records(
        'SELECT TABLE_SCHEMA, TABLE_NAME, CONSTRAINT_NAME, COLUMN_NAME, '
        'REFERENCED_TABLE_SCHEMA, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME '
        'FROM information_schema.KEY_COLUMN_USAGE '
        "WHERE TABLE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys') "
        'ORDER BY TABLE_SCHEMA, TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION'
    ):
        facts = constraint_facts.setdefault(
            (record['table_schema'], record['table_name'], record['constraint_name']),
            {'columns': []},
        )
        facts['columns'].append(record['column_name'])
        if record.get('referenced_table_name') is not None:
            facts['referenced_table'] = f"{record['referenced_table_schema']}.{record['referenced_table_name']}"
            facts.setdefault('referenced_columns', []).append(record['referenced_column_name'])

    for record in optional_records(
        'SELECT CONSTRAINT_SCHEMA, TABLE_NAME, CONSTRAINT_NAME, UPDATE_RULE, DELETE_RULE '
        'FROM information_schema.REFERENTIAL_CONSTRAINTS '
        "WHERE CONSTRAINT_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys')"
    ):
        constraint_facts.setdefault(
            (record['constraint_schema'], record['table_name'], record['constraint_name']),
            {},
        ).update(on_update=record['update_rule'], on_delete=record['delete_rule'])

    check_clauses = {
        (record['constraint_schema'], record['table_name'], record['constraint_name']): record['check_clause']
        for record in optional_records(
            'SELECT CONSTRAINT_SCHEMA, TABLE_NAME, CONSTRAINT_NAME, CHECK_CLAUSE '
            'FROM information_schema.CHECK_CONSTRAINTS '
            "WHERE CONSTRAINT_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys')"
        )
    }

    for record in optional_records(
        'SELECT TABLE_SCHEMA, TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE '
        'FROM information_schema.TABLE_CONSTRAINTS '
        "WHERE TABLE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys') "
        'ORDER BY TABLE_SCHEMA, TABLE_NAME, CONSTRAINT_NAME'
    ):
        native = {
            **record,
            'administration': {'allowed_operations': ['inspect', 'create', 'drop']},
            **constraint_facts.get((record['table_schema'], record['table_name'], record['constraint_name']), {}),
        }
        if record['constraint_type'] == 'CHECK':
            chk = check_clauses.get((record['table_schema'], record['table_name'], record['constraint_name']))
            if chk is not None:
                native['check_clause'] = chk
        add('constraint', [record['table_schema'], record['table_name']], record['constraint_name'], native)
