"""Exact-file DuckDB COPY and native reader script planning (DU-AUD-05).

Supports installed native formats (CSV, PARQUET, JSON), table COPY TO / FROM,
and native reader imports (read_csv / read_parquet / read_json for CTAS and
INSERT) with per-format typed options, partitioned output directories, Parquet
layout/KV/keyed encryption options, and strict filesystem root containment.
"""
from collections.abc import Mapping
import hashlib
import os
import re
import stat

from .duckdb_test_data import _quote

ADMITTED_FORMATS = frozenset({'CSV', 'PARQUET', 'JSON'})
ADMITTED_DIRECTIONS = frozenset({'from', 'to', 'reader_ctas', 'reader_insert'})

CSV_COMPRESSIONS = frozenset({'NONE', 'GZIP', 'ZSTD'})
JSON_COMPRESSIONS = frozenset({'NONE', 'GZIP', 'ZSTD'})
PARQUET_COMPRESSIONS = frozenset({'UNCOMPRESSED', 'SNAPPY', 'GZIP', 'ZSTD', 'BROTLI', 'LZ4'})
CSV_ENCODINGS = frozenset({'UTF-8', 'UTF-16', 'LATIN-1'})


def _sql_literal(value):
    if not isinstance(value, str) or '\x00' in value:
        raise ValueError('DuckDB COPY option string cannot contain NUL')
    return "'" + value.replace("'", "''") + "'"


def _bool_opt(options, key):
    val = options[key]
    if type(val) is not bool:
        raise ValueError(f'COPY option {key} must be boolean')
    return 'TRUE' if val else 'FALSE'


def _pos_int_opt(options, key):
    val = options[key]
    if type(val) is not int or val <= 0 or val > 2**62:
        raise ValueError(f'COPY option {key} must be a positive integer')
    return str(val)


def capabilities(connection=None):
    """Discover installed/loaded COPY and reader format capabilities on DuckDB 1.5.2."""
    own = False
    if connection is None:
        import duckdb
        connection = duckdb.connect()
        own = True
    try:
        ext_map = {
            str(r[0]).lower(): {'loaded': bool(r[1]), 'installed': bool(r[2]), 'mode': str(r[3])}
            for r in connection.execute(
                'SELECT extension_name, loaded, installed, install_mode FROM "system"."main".duckdb_extensions()'
            ).fetchall()
        }
        fn_set = {
            str(r[0]).lower()
            for r in connection.execute(
                'SELECT DISTINCT function_name FROM "system"."main".duckdb_functions()'
            ).fetchall()
        }
        formats = {
            'CSV': {
                'available': True,
                'reader_function': 'read_csv' if 'read_csv' in fn_set else None,
                'directions': ['from', 'to', 'reader_ctas', 'reader_insert'],
                'compressions': sorted(CSV_COMPRESSIONS),
                'encodings': sorted(CSV_ENCODINGS),
                'options': [
                    'header', 'delimiter', 'quote', 'escape', 'nullstr',
                    'dateformat', 'timestampformat', 'compression', 'encoding',
                    'auto_detect', 'ignore_errors', 'force_quote',
                    'partition_by', 'overwrite_or_ignore', 'write_partition_columns', 'filename_pattern',
                ],
            },
            'PARQUET': {
                'available': bool(ext_map.get('parquet', {}).get('loaded')) and 'read_parquet' in fn_set,
                'extension': ext_map.get('parquet', {'loaded': False, 'installed': False}),
                'reader_function': 'read_parquet' if 'read_parquet' in fn_set else None,
                'directions': ['from', 'to', 'reader_ctas', 'reader_insert'],
                'compressions': sorted(PARQUET_COMPRESSIONS),
                'options': [
                    'compression', 'row_group_size', 'row_group_size_bytes',
                    'field_ids', 'kv_metadata', 'encryption_key_name',
                    'union_by_name', 'hive_partitioning', 'filename',
                    'partition_by', 'overwrite_or_ignore', 'write_partition_columns', 'filename_pattern',
                ],
            },
            'JSON': {
                'available': bool(ext_map.get('json', {}).get('loaded')) and 'read_json' in fn_set,
                'extension': ext_map.get('json', {'loaded': False, 'installed': False}),
                'reader_function': 'read_json' if 'read_json' in fn_set else None,
                'directions': ['from', 'to', 'reader_ctas', 'reader_insert'],
                'compressions': sorted(JSON_COMPRESSIONS),
                'json_formats': ['NEWLINE_DELIMITED', 'ARRAY'],
                'options': [
                    'json_format', 'compression', 'dateformat', 'timestampformat',
                    'auto_detect', 'maximum_object_size',
                    'partition_by', 'overwrite_or_ignore', 'write_partition_columns', 'filename_pattern',
                ],
            },
        }
        return {
            'schema': 'scratchrobin.duckdb.copy-capabilities@1',
            'engine_id': 'duckdb',
            'formats': formats,
        }
    finally:
        if own:
            connection.close()


def _validate_contained_target(raw_value, root, *, direction, partitioned=False, overwrite=False):
    if not isinstance(raw_value, str) or not os.path.isabs(raw_value) or '\x00' in raw_value:
        raise ValueError('COPY requires an absolute native file path')
    if not isinstance(root, str) or not os.path.isabs(root):
        raise ValueError('DuckDB endpoint has no absolute filesystem root')
    root_path = os.path.realpath(root)
    resolved = os.path.realpath(raw_value)
    if os.path.commonpath((root_path, resolved)) != root_path or resolved == root_path and direction == 'to' and not partitioned:
        if os.path.commonpath((root_path, resolved)) != root_path:
            raise ValueError('COPY file escapes the registered filesystem root')
    if os.path.islink(raw_value):
        raise ValueError('COPY target cannot be a symbolic link')
    if direction in {'from', 'reader_ctas', 'reader_insert'}:
        if partitioned:
            if not os.path.isdir(resolved):
                raise ValueError('Partitioned reader import requires an existing contained directory')
        else:
            if not os.path.isfile(resolved) or not stat.S_ISREG(os.stat(resolved).st_mode):
                raise ValueError('COPY import requires an existing regular file, not a symlink')
    else:
        parent = os.path.dirname(resolved)
        if not os.path.isdir(parent):
            raise ValueError('COPY export requires an existing parent directory')
        if partitioned:
            if os.path.lexists(raw_value):
                if not os.path.isdir(resolved) or (os.listdir(resolved) and not overwrite):
                    raise ValueError(
                        'Partitioned COPY export requires an absent/empty directory or overwrite_or_ignore=true'
                    )
        elif os.path.lexists(raw_value) and not overwrite:
            raise ValueError('COPY export requires an existing parent and absent destination')
    return resolved


def _compile_copy_options(fmt, direction, options, table_columns):
    clauses = [f'FORMAT {fmt}']
    col_lookup = {c.lower(): c for c in table_columns}
    partitioned = False
    overwrite = False

    if fmt == 'CSV':
        allowed = {
            'header', 'delimiter', 'quote', 'escape', 'nullstr',
            'dateformat', 'timestampformat', 'compression', 'encoding',
            'auto_detect', 'ignore_errors', 'force_quote',
            'partition_by', 'overwrite_or_ignore', 'write_partition_columns', 'filename_pattern',
        }
        if set(options) - allowed:
            raise ValueError('Unsupported typed CSV COPY option')
        header = options.get('header', True)
        if type(header) is not bool:
            raise ValueError('CSV header must be boolean')
        clauses.append(f"HEADER {'TRUE' if header else 'FALSE'}")
        if 'delimiter' in options:
            delim = options['delimiter']
            if not isinstance(delim, str) or not (1 <= len(delim) <= 4) or '\x00' in delim:
                raise ValueError('CSV delimiter must be 1..4 characters')
            clauses.append(f'DELIMITER {_sql_literal(delim)}')
        for char_opt in ('quote', 'escape'):
            if char_opt in options:
                val = options[char_opt]
                if not isinstance(val, str) or len(val) > 1 or '\x00' in val:
                    raise ValueError(f'CSV {char_opt} must be at most 1 character')
                clauses.append(f'{char_opt.upper()} {_sql_literal(val)}')
        for str_opt in ('nullstr', 'dateformat', 'timestampformat'):
            if str_opt in options:
                val = options[str_opt]
                if not isinstance(val, str) or len(val) > 128:
                    raise ValueError(f'CSV {str_opt} must be bounded text')
                clauses.append(f'{str_opt.upper()} {_sql_literal(val)}')
        if 'compression' in options:
            comp = str(options['compression']).upper()
            if comp not in CSV_COMPRESSIONS:
                raise ValueError('Unsupported CSV compression codec')
            clauses.append(f'COMPRESSION {comp}')
        if 'encoding' in options:
            enc = str(options['encoding']).upper()
            if enc not in CSV_ENCODINGS:
                raise ValueError('Unsupported CSV character encoding')
            clauses.append(f'ENCODING {_sql_literal(enc)}')
        for b_opt in ('auto_detect', 'ignore_errors'):
            if b_opt in options:
                if direction == 'to':
                    raise ValueError(f'CSV {b_opt} applies only to import/reader directions')
                clauses.append(f'{b_opt.upper()} {_bool_opt(options, b_opt)}')
        if 'force_quote' in options:
            if direction != 'to':
                raise ValueError('CSV force_quote applies only to COPY TO')
            fq = options['force_quote']
            if not isinstance(fq, list) or not fq or not all(isinstance(c, str) and c.lower() in col_lookup for c in fq):
                raise ValueError('CSV force_quote must reference existing table columns')
            clauses.append('FORCE_QUOTE (' + ', '.join(_quote(col_lookup[c.lower()]) for c in fq) + ')')

    elif fmt == 'PARQUET':
        allowed = {
            'compression', 'row_group_size', 'row_group_size_bytes',
            'field_ids', 'kv_metadata', 'encryption_key_name',
            'union_by_name', 'hive_partitioning', 'filename',
            'partition_by', 'overwrite_or_ignore', 'write_partition_columns', 'filename_pattern',
        }
        if set(options) - allowed:
            raise ValueError('Unsupported typed PARQUET COPY option')
        if 'compression' in options:
            comp = str(options['compression']).upper()
            if comp not in PARQUET_COMPRESSIONS:
                raise ValueError('Unsupported PARQUET compression codec')
            clauses.append(f'COMPRESSION {comp}')
        for int_opt in ('row_group_size', 'row_group_size_bytes'):
            if int_opt in options:
                if direction != 'to':
                    raise ValueError(f'PARQUET {int_opt} applies only to COPY TO')
                clauses.append(f'{int_opt.upper()} {_pos_int_opt(options, int_opt)}')
        if 'field_ids' in options:
            if options['field_ids'] != 'AUTO':
                raise ValueError('PARQUET field_ids supports AUTO')
            clauses.append('FIELD_IDS AUTO')
        if 'kv_metadata' in options:
            if direction != 'to':
                raise ValueError('PARQUET kv_metadata applies only to COPY TO')
            kv = options['kv_metadata']
            if (not isinstance(kv, Mapping) or not kv or len(kv) > 64 or
                    not all(isinstance(k, str) and k and len(k) <= 256 and isinstance(v, str) and len(v) <= 4096
                            for k, v in kv.items())):
                raise ValueError('PARQUET kv_metadata requires 1..64 bounded string pairs')
            pairs = ', '.join(f'{_sql_literal(k)}: {_sql_literal(v)}' for k, v in kv.items())
            clauses.append(f'KV_METADATA {{{pairs}}}')
        if 'encryption_key_name' in options:
            key_name = options['encryption_key_name']
            if not isinstance(key_name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', key_name):
                raise ValueError('PARQUET encryption_key_name must be a valid registered key identifier')
            clauses.append(f"ENCRYPTION_CONFIG {{footer_key: {_sql_literal(key_name)}}}")
        for r_opt in ('union_by_name', 'hive_partitioning', 'filename'):
            if r_opt in options:
                if direction == 'to':
                    raise ValueError(f'PARQUET {r_opt} applies only to import/reader directions')
                clauses.append(f'{r_opt.upper()} {_bool_opt(options, r_opt)}')

    elif fmt == 'JSON':
        allowed = {
            'json_format', 'compression', 'dateformat', 'timestampformat',
            'auto_detect', 'maximum_object_size',
            'partition_by', 'overwrite_or_ignore', 'write_partition_columns', 'filename_pattern',
        }
        if set(options) - allowed:
            raise ValueError('Unsupported typed JSON COPY option')
        jfmt = str(options.get('json_format', 'NEWLINE_DELIMITED')).upper()
        if jfmt not in {'NEWLINE_DELIMITED', 'ARRAY'}:
            raise ValueError('JSON format must be NEWLINE_DELIMITED or ARRAY')
        if jfmt == 'ARRAY':
            clauses.append('ARRAY TRUE')
        if 'compression' in options:
            comp = str(options['compression']).upper()
            if comp not in JSON_COMPRESSIONS:
                raise ValueError('Unsupported JSON compression codec')
            clauses.append(f'COMPRESSION {comp}')
        for str_opt in ('dateformat', 'timestampformat'):
            if str_opt in options:
                val = options[str_opt]
                if not isinstance(val, str) or len(val) > 128:
                    raise ValueError(f'JSON {str_opt} must be bounded text')
                clauses.append(f'{str_opt.upper()} {_sql_literal(val)}')
        if 'auto_detect' in options:
            if direction == 'to':
                raise ValueError('JSON auto_detect applies only to import/reader directions')
            clauses.append(f"AUTO_DETECT {_bool_opt(options, 'auto_detect')}")
        if 'maximum_object_size' in options:
            if direction == 'to':
                raise ValueError('JSON maximum_object_size applies only to import/reader directions')
            clauses.append(f"MAXIMUM_OBJECT_SIZE {_pos_int_opt(options, 'maximum_object_size')}")

    if 'partition_by' in options:
        if direction != 'to':
            raise ValueError('PARTITION_BY applies only to COPY TO')
        parts = options['partition_by']
        if not isinstance(parts, list) or not parts or not all(
            isinstance(c, str) and c.lower() in col_lookup for c in parts
        ):
            raise ValueError('PARTITION_BY must select one or more existing columns on the target table')
        partitioned = True
        clauses.append('PARTITION_BY (' + ', '.join(_quote(col_lookup[c.lower()]) for c in parts) + ')')
    if 'overwrite_or_ignore' in options:
        if direction != 'to':
            raise ValueError('OVERWRITE_OR_IGNORE applies only to COPY TO')
        overwrite = bool(options['overwrite_or_ignore'])
        clauses.append(f"OVERWRITE_OR_IGNORE {_bool_opt(options, 'overwrite_or_ignore')}")
    if 'write_partition_columns' in options:
        if direction != 'to' or not partitioned:
            raise ValueError('WRITE_PARTITION_COLUMNS requires partitioned COPY TO')
        clauses.append(f"WRITE_PARTITION_COLUMNS {_bool_opt(options, 'write_partition_columns')}")
    if 'filename_pattern' in options:
        if direction != 'to' or not partitioned:
            raise ValueError('FILENAME_PATTERN requires partitioned COPY TO')
        pat = options['filename_pattern']
        if not isinstance(pat, str) or not re.fullmatch(r'[A-Za-z0-9_{}-]{1,128}', pat):
            raise ValueError('FILENAME_PATTERN must be a safe bounded filename pattern')
        clauses.append(f'FILENAME_PATTERN {_sql_literal(pat)}')

    return clauses, partitioned, overwrite


def _compile_reader_call(fmt, path_sql, options, partitioned_dir=False):
    fn = {'CSV': 'read_csv', 'PARQUET': 'read_parquet', 'JSON': 'read_json'}[fmt]
    args = [path_sql]
    if fmt == 'CSV':
        if 'header' in options:
            args.append(f"header = {'true' if options['header'] else 'false'}")
        if 'delimiter' in options:
            args.append(f"delim = {_sql_literal(options['delimiter'])}")
        if 'quote' in options:
            args.append(f"quote = {_sql_literal(options['quote'])}")
        if 'escape' in options:
            args.append(f"escape = {_sql_literal(options['escape'])}")
        if 'nullstr' in options:
            args.append(f"nullstr = {_sql_literal(options['nullstr'])}")
        if 'dateformat' in options:
            args.append(f"dateformat = {_sql_literal(options['dateformat'])}")
        if 'timestampformat' in options:
            args.append(f"timestampformat = {_sql_literal(options['timestampformat'])}")
        if 'compression' in options:
            args.append(f"compression = {_sql_literal(str(options['compression']).lower())}")
        if 'encoding' in options:
            args.append(f"encoding = {_sql_literal(options['encoding'])}")
        if 'auto_detect' in options:
            args.append(f"auto_detect = {'true' if options['auto_detect'] else 'false'}")
        if 'ignore_errors' in options:
            args.append(f"ignore_errors = {'true' if options['ignore_errors'] else 'false'}")
    elif fmt == 'PARQUET':
        for b_opt in ('union_by_name', 'hive_partitioning', 'filename'):
            if b_opt in options:
                args.append(f"{b_opt} = {'true' if options[b_opt] else 'false'}")
            elif b_opt == 'hive_partitioning' and partitioned_dir:
                args.append('hive_partitioning = true')
        if 'encryption_key_name' in options:
            args.append(f"encryption_config = {{footer_key: {_sql_literal(options['encryption_key_name'])}}}")
    elif fmt == 'JSON':
        jfmt = str(options.get('json_format', 'NEWLINE_DELIMITED')).upper()
        args.append(f"format = {_sql_literal('array' if jfmt == 'ARRAY' else 'newline_delimited')}")
        if 'compression' in options:
            args.append(f"compression = {_sql_literal(str(options['compression']).lower())}")
        if 'dateformat' in options:
            args.append(f"dateformat = {_sql_literal(options['dateformat'])}")
        if 'timestampformat' in options:
            args.append(f"timestampformat = {_sql_literal(options['timestampformat'])}")
        if 'auto_detect' in options:
            args.append(f"auto_detect = {'true' if options['auto_detect'] else 'false'}")
        if 'maximum_object_size' in options:
            args.append(f"maximum_object_size = {int(options['maximum_object_size'])}")
    return f'"system"."main".{fn}({", ".join(args)})'


def plan(model, request, root):
    allowed_keys = {'resource_id', 'direction', 'format', 'path', 'options', 'target_schema', 'target_table', 'partitioned_source'}
    if not isinstance(request, dict) or not {'direction', 'format', 'path'} <= set(request) or (
        set(request) - allowed_keys
    ):
        raise ValueError('Select one exact DuckDB table/target, direction and native file format')
    direction = request['direction']
    fmt = request['format']
    if direction not in ADMITTED_DIRECTIONS or fmt not in ADMITTED_FORMATS:
        raise ValueError('Select an admitted DuckDB COPY direction and format (CSV, PARQUET, JSON)')
    options = request.get('options') or {}
    if not isinstance(options, Mapping):
        raise ValueError('COPY options must be a typed options object')

    databases = [item for item in model['rows'].values() if item['kind'] == 'database' and item['system'] == 'false']
    if len(databases) != 1:
        raise ValueError('Select a persistent table in the exact registered DuckDB file')
    db_name = databases[0]['name']

    partitioned_source = bool(request.get('partitioned_source', False))
    if direction == 'reader_ctas':
        target_schema = request.get('target_schema', 'main')
        target_table = request.get('target_table')
        if (not isinstance(target_schema, str) or not target_schema.strip() or
                not isinstance(target_table, str) or not target_table.strip()):
            raise ValueError('Reader CTAS import requires target_schema and target_table')
        existing_tables = {
            (item['path'][1].lower(), item['path'][2].lower())
            for item in model['rows'].values()
            if item['kind'] in {'table', 'view'} and len(item['path']) == 3 and item['path'][0] == db_name
        }
        if (target_schema.strip().lower(), target_table.strip().lower()) in existing_tables:
            raise ValueError('Reader CTAS target table already exists; choose a new table name or reader_insert')
        identity = request.get('resource_id') or f'ctas:{db_name}.{target_schema}.{target_table}'
        target = '.'.join(_quote(part) for part in (db_name, target_schema.strip(), target_table.strip()))
        table_columns = []
    else:
        identity = request.get('resource_id')
        row = model['rows'].get(identity) if isinstance(identity, str) else None
        if (row is None or row['kind'] != 'table' or row['system'] != 'false' or
                len(row['path']) != 3 or row['path'][0] != db_name or
                row['native'].get('catalog_metadata', {}).get('temporary') is not False):
            raise ValueError('Select a persistent table in the exact registered DuckDB file')
        target = '.'.join(_quote(part) for part in row['path'])
        table_columns = [c['name'] for c in row['native'].get('columns', []) if isinstance(c, Mapping) and 'name' in c]

    clauses, partitioned_out, overwrite = _compile_copy_options(
        fmt, 'from' if direction.startswith('reader_') else direction, options, table_columns,
    )
    is_partitioned = partitioned_out if direction == 'to' else partitioned_source
    path = _validate_contained_target(
        request['path'], root, direction=direction, partitioned=is_partitioned, overwrite=overwrite,
    )

    if direction in {'reader_ctas', 'reader_insert'}:
        ext_glob = {'CSV': '*.csv', 'PARQUET': '*.parquet', 'JSON': '*.json'}[fmt]
        read_target = os.path.join(path, '**', ext_glob) if partitioned_source else path
        reader_sql = _compile_reader_call(fmt, _sql_literal(read_target), options, partitioned_dir=partitioned_source)
        if direction == 'reader_ctas':
            source = f'CREATE TABLE {target} AS SELECT * FROM {reader_sql};'
        else:
            source = f'INSERT INTO {target} BY NAME SELECT * FROM {reader_sql};'
    else:
        dir_kw = 'FROM' if direction == 'from' else 'TO'
        source = f"COPY {target} {dir_kw} {_sql_literal(path)} ({', '.join(clauses)});"

    import duckdb
    try:
        statements = duckdb.extract_statements(source)
    except duckdb.Error:
        raise ValueError('Native DuckDB parser rejected COPY / reader plan') from None
    expected_stmt_types = {
        'from': duckdb.StatementType.COPY,
        'to': duckdb.StatementType.COPY,
        'reader_ctas': duckdb.StatementType.CREATE,
        'reader_insert': duckdb.StatementType.INSERT,
    }
    if len(statements) != 1 or statements[0].type != expected_stmt_types[direction]:
        raise ValueError('Exactly one native COPY / reader statement is required')

    return {
        'format': 'scratchrobin.duckdb.copy-plan@1',
        'engine_id': 'duckdb',
        'resource_id': identity,
        'target': target,
        'direction': direction,
        'native_format': fmt,
        'path': path,
        'partitioned': is_partitioned,
        'options': dict(options),
        'source': source,
        'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'executed': False,
        'warnings': [
            'Preview only; open this script on the exact registered file in the shared Query Tool.',
            'Native file and transaction effects apply; SQL rollback does not remove exported files.',
        ],
    }
