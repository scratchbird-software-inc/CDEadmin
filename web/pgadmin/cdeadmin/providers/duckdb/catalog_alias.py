"""Native alias observation fences and descendant invalidation receipts."""
import hashlib
import json


def snapshot(handle, alias):
    from .provider import _resources
    resources = _resources(handle, {'session_catalog': True})
    if len(resources) > 20000:
        raise ValueError('Alias review exceeds the native catalog identity budget')
    # Bind all visible object definitions, including SQL in other catalogs.
    # Native dependency tables do not enumerate every SQL/external reference.
    canonical = json.dumps(resources, sort_keys=True, default=str).encode('utf8')
    if len(canonical) > 8 * 1024 * 1024:
        raise ValueError('Alias review exceeds the native catalog byte budget')
    # Size/memory figures can change without a metadata change.
    stable = [{key: row[key] for key in ('resource_id', 'resource_kind', 'display_path')}
              | {'native': {key: value for key, value in row.get('native', {}).items()
                 if key not in {'database_size', 'block_size', 'total_blocks', 'used_blocks', 'free_blocks',
                                'wal_size', 'memory_usage', 'memory_limit'}}}
              for row in resources]
    dependencies = handle.execute('SELECT * FROM duckdb_dependencies() ORDER BY ALL').fetchall()
    if len(dependencies) > 20000:
        raise ValueError('Alias review exceeds the native dependency budget')
    digest = hashlib.sha256(json.dumps([stable, dependencies], sort_keys=True, default=str).encode()).hexdigest()
    selected = [row for row in resources if row.get('display_path', [None])[0] == alias]
    identities = [{key: row[key] for key in ('resource_id', 'resource_kind', 'display_path')} for row in selected]
    sql_sources = []
    for row in resources:
        native = row.get('native', {})
        for key in ('source_ddl', 'ddl', 'sql', 'macro_definition', 'definition'):
            source = native.get(key)
            if isinstance(source, str) and source:
                sql_sources.append({'resource_id': row['resource_id'], 'source_field': key,
                    'source_sha256': hashlib.sha256(source.encode()).hexdigest()})
    return {'catalog_digest': digest, 'transaction_id': str(handle.execute('SELECT current_transaction_id()').fetchone()[0]),
            'descendants': identities, 'stored_sql_sources': sql_sources,
            'native_dependency_rows': [[str(cell) if type(cell) is int else cell for cell in row] for row in dependencies],
            'external_or_dynamic_sql_dependencies': 'not-enumerable', 'stored_sql_rewritten': False}
