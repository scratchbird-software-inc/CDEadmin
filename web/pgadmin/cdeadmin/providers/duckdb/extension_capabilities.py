"""Per-extension runtime state & capability discovery for DuckDB 1.5.2 (DU-AUD-08).

Distinguishes runtime states strictly:
- statically_linked_loaded: built into the DuckDB binary and active
- installed_loaded: dynamically installed on disk and loaded in this instance
- installed_not_loaded: present on disk (e.g. httpfs) and ready to LOAD
- not_installed: known extension name, not installed locally

Never conflates bundled C++ donor source or remote repository names with actual
installed/loaded runtime capabilities.
"""

BUNDLED_SOURCE_FAMILIES = {
    'autocomplete': {
        'source': 'extension/autocomplete/autocomplete_extension.cpp',
        'role': 'SQL parser autocomplete table function',
        'signature_functions': ('sql_auto_complete',),
        'signature_settings': (),
        'signature_types': (),
    },
    'core_functions': {
        'source': 'extension/core_functions/core_functions_extension.cpp',
        'role': 'Built-in scalar and aggregate function library',
        'signature_functions': ('sum', 'avg', 'list_value', 'struct_pack', 'regexp_matches'),
        'signature_settings': (),
        'signature_types': (),
    },
    'delta': {
        'source': 'extension/delta/src/delta_extension.cpp',
        'role': 'Delta Lake table scanner',
        'signature_functions': ('delta_scan',),
        'signature_settings': (),
        'signature_types': (),
    },
    'icu': {
        'source': 'extension/icu/icu_extension.cpp',
        'role': 'Locale collations, timezones, and calendar arithmetic',
        'signature_functions': ('icu_calendar_names', 'icu_sort_key', 'current_localtime'),
        'signature_settings': ('TimeZone', 'Calendar'),
        'signature_types': ('TIMESTAMP WITH TIME ZONE',),
    },
    'jemalloc': {
        'source': 'extension/jemalloc/jemalloc_extension.cpp',
        'role': 'Native memory allocator integration',
        'signature_functions': (),
        'signature_settings': ('allocator_background_threads', 'allocator_bulk_deallocation_flush_threshold'),
        'signature_types': (),
    },
    'json': {
        'source': 'extension/json/json_extension.cpp',
        'role': 'JSON logical type, reader/COPY format, and path extraction',
        'signature_functions': ('read_json', 'read_ndjson', 'to_json', 'json_extract', 'json_valid'),
        'signature_settings': (),
        'signature_types': ('JSON',),
    },
    'parquet': {
        'source': 'extension/parquet/parquet_extension.cpp',
        'role': 'Parquet columnar reader/COPY writer, metadata inspection, and key encryption',
        'signature_functions': ('read_parquet', 'parquet_metadata', 'parquet_schema', 'parquet_file_metadata', 'parquet_kv_metadata'),
        'signature_settings': ('binary_as_string',),
        'signature_types': (),
    },
    'tpcds': {
        'source': 'extension/tpcds/tpcds_extension.cpp',
        'role': 'TPC-DS benchmark schema/data generator and query catalog',
        'signature_functions': ('dsdgen', 'tpcds', 'tpcds_queries', 'tpcds_answers'),
        'signature_settings': (),
        'signature_types': (),
    },
    'tpch': {
        'source': 'extension/tpch/tpch_extension.cpp',
        'role': 'TPC-H benchmark schema/data generator and query catalog',
        'signature_functions': ('dbgen', 'tpch', 'tpch_queries', 'tpch_answers'),
        'signature_settings': (),
        'signature_types': (),
    },
    'httpfs': {
        'source': None,
        'role': 'HTTP/HTTPS and S3 remote file transport and secret bindings',
        'signature_functions': (),
        'signature_settings': ('http_timeout', 'http_retries', 'ca_cert_file', 'enable_server_cert_verification', 's3_region', 's3_endpoint'),
        'signature_types': (),
        'secret_types': ('http', 's3'),
        'attachment_protocols': ('http://', 'https://', 's3://'),
    },
    'sqlite_scanner': {
        'source': None,
        'role': 'Foreign SQLite database ATTACH (TYPE sqlite) and sqlite_scan',
        'signature_functions': ('sqlite_scan', 'sqlite_attach'),
        'signature_settings': ('sqlite_all_varchar',),
        'signature_types': (),
        'foreign_attach_type': 'sqlite',
    },
    'postgres_scanner': {
        'source': None,
        'role': 'Foreign PostgreSQL catalog ATTACH (TYPE postgres) and postgres_scan',
        'signature_functions': ('postgres_scan', 'postgres_attach', 'postgres_query'),
        'signature_settings': ('pg_experimental_filter_pushdown', 'pg_pages_per_task'),
        'signature_types': (),
        'foreign_attach_type': 'postgres',
    },
    'mysql_scanner': {
        'source': None,
        'role': 'Foreign MySQL/MariaDB catalog ATTACH (TYPE mysql) and mysql_scan',
        'signature_functions': ('mysql_scan', 'mysql_query'),
        'signature_settings': ('mysql_experimental_filter_pushdown',),
        'signature_types': (),
        'foreign_attach_type': 'mysql',
    },
}


def runtime_state_label(record):
    loaded = bool(record.get('loaded'))
    installed = bool(record.get('installed'))
    mode = str(record.get('install_mode') or '').upper()
    if mode == 'STATICALLY_LINKED' and loaded:
        return 'statically_linked_loaded'
    if installed and loaded:
        return 'installed_loaded'
    if installed and not loaded:
        return 'installed_not_loaded'
    return 'not_installed'


def discover_capabilities(handle, extension_rows=None):
    """Build live per-extension capability profiles from actual DuckDB 1.5.2 catalogs."""
    if extension_rows is None:
        from .extension_updates import inventory
        extension_rows = inventory(handle)
    fn_names = {
        str(r[0]).lower()
        for r in handle.execute(
            'SELECT DISTINCT function_name FROM "system"."main".duckdb_functions()'
        ).fetchall()
    }
    setting_names = {
        str(r[0]).lower()
        for r in handle.execute(
            'SELECT name FROM "system"."main".duckdb_settings()'
        ).fetchall()
    }
    type_names = {
        str(r[0]).upper()
        for r in handle.execute(
            'SELECT DISTINCT type_name FROM "system"."main".duckdb_types()'
        ).fetchall()
    }
    try:
        secret_types = {
            str(r[0]).lower()
            for r in handle.execute(
                'SELECT DISTINCT type FROM "system"."main".duckdb_secret_types()'
            ).fetchall()
        }
    except Exception:
        secret_types = set()
    try:
        collation_count = int(handle.execute(
            'SELECT COUNT(*) FROM pragma_collations()'
        ).fetchone()[0])
    except Exception:
        collation_count = 0

    profiles = []
    for ext in extension_rows:
        name = ext['extension_name']
        state = runtime_state_label(ext)
        spec = BUNDLED_SOURCE_FAMILIES.get(name, {})
        sig_fns = list(spec.get('signature_functions', ()))
        sig_settings = list(spec.get('signature_settings', ()))
        sig_types = list(spec.get('signature_types', ()))
        observed_fns = [fn for fn in sig_fns if fn.lower() in fn_names]
        observed_settings = [s for s in sig_settings if s.lower() in setting_names]
        observed_types = [t for t in sig_types if t.upper() in type_names]
        observed_secrets = [
            st for st in spec.get('secret_types', ()) if st.lower() in secret_types
        ]
        copy_formats = []
        if name == 'parquet' and ext['loaded']:
            copy_formats.append('PARQUET')
        elif name == 'json' and ext['loaded']:
            copy_formats.append('JSON')

        profiles.append({
            'extension_name': name,
            'aliases': list(ext.get('aliases') or ()),
            'runtime_state': state,
            'installed': bool(ext.get('installed')),
            'loaded': bool(ext.get('loaded')),
            'install_mode': ext.get('install_mode'),
            'extension_version': ext.get('extension_version') or '',
            'installed_from': ext.get('installed_from') or '',
            'description': ext.get('description') or '',
            'bundled_donor_source': spec.get('source'),
            'bundled_source_is_not_runtime_install': bool(spec.get('source')) and not ext.get('installed'),
            'role': spec.get('role') or ext.get('description') or 'DuckDB extension module',
            'capabilities': {
                'active_in_session': bool(ext.get('loaded')),
                'can_load_without_network': bool(ext.get('installed')) and not bool(ext.get('loaded')),
                'requires_install': not bool(ext.get('installed')),
                'observed_functions': observed_fns,
                'declared_functions': sig_fns,
                'observed_settings': observed_settings,
                'observed_types': observed_types,
                'observed_secret_types': observed_secrets,
                'copy_formats': copy_formats,
                'foreign_attach_type': spec.get('foreign_attach_type') if ext.get('loaded') else None,
                'declared_foreign_attach_type': spec.get('foreign_attach_type'),
                'attachment_protocols': list(spec.get('attachment_protocols', ())) if ext.get('loaded') else [],
                **({'icu_collation_count': collation_count} if name == 'icu' and ext.get('loaded') else {}),
            },
        })
    return {
        'schema': 'scratchrobin.duckdb.extension-capabilities@1',
        'profiles': profiles,
        'summary': {
            'total_known': len(profiles),
            'statically_linked_loaded': sum(1 for p in profiles if p['runtime_state'] == 'statically_linked_loaded'),
            'installed_loaded': sum(1 for p in profiles if p['runtime_state'] == 'installed_loaded'),
            'installed_not_loaded': sum(1 for p in profiles if p['runtime_state'] == 'installed_not_loaded'),
            'not_installed': sum(1 for p in profiles if p['runtime_state'] == 'not_installed'),
        },
    }
