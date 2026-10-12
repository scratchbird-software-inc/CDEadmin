"""Read-only projection of actual scoped operation audit records."""


def project_receipts(records, database=None):
    rows = []
    for record in records:
        if record.get('engine_id') != 'firebird':
            continue
        native = record.get('provider_result')
        native = native if isinstance(native, dict) else {}
        observed_database = native.get('database')
        if database is not None and observed_database != database:
            continue
        release = native.get('service_release')
        release = release if isinstance(release, dict) else {}
        rows.append({**{field: record.get(field) for field in (
            'operation_id', 'operation_kind', 'stage', 'unknown_outcome',
            'post_state_required', 'created_at', 'updated_at')},
            'database': observed_database,
            'server_completed': native.get('server_completed'),
            'service_handle_released': release.get('service_handle_released')})
    rows.sort(key=lambda row: str(row.get('updated_at') or row.get('created_at') or ''), reverse=True)
    return {'status': 'available', 'operation': 'receipts', 'rows': rows[:100],
            'limit': 100, 'truncated': len(rows) > 100,
            'coverage': 'local owner-scoped audit; not external backup history'}
