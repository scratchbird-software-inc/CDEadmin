"""Passive fleet projection. Registrations are not physical-instance identity."""

from decimal import Decimal, InvalidOperation, localcontext


def observation(snapshot, scope):
    samples = snapshot.get('samples', [])
    sample = samples[-1] if samples else {}
    age = snapshot.get('sample_age_seconds')
    stale_after = snapshot.get('stale_after_seconds', 15)
    state = snapshot.get('state', 'unknown')
    fresh = (state == 'collecting' and age is not None and age <= stale_after)
    evidence = 'service_probe' if scope == 'server' else 'transaction_refresh'
    if state == 'authorization-denied':
        status = 'permission-limited'
    elif not sample:
        status = 'unknown'
    elif not fresh:
        status = 'stale'
    elif sample.get('error_type') == 'PermissionError':
        status = 'permission-limited'
    elif sample.get('status') == 'unavailable':
        status = 'failed'
    elif sample.get(evidence, {}).get('status') == 'completed':
        status = 'reachable'
    else:
        status = 'unknown'
    # A historical or unauthorized observation cannot populate current metrics.
    groups = sample.get('groups', {}) if status == 'reachable' else {}

    def value(name):
        group = groups.get(name, {})
        return group.get('values') if group.get('status') == 'available' else None

    database = value('database') or {}
    derived = sample.get('derived', {}) if status == 'reachable' else {}
    rates = sample.get('rates', {}) if status == 'reachable' else {}
    return {
        'status': status, 'collection_state': state, 'sample_age_seconds': age,
        'observed_at': sample.get('ended_at'),
        'coverage': sample.get('coverage') if status == 'reachable' else None,
        'version': value('version'), 'architecture': value('architecture'),
        'attached_databases': value('attached_databases'),
        'database_identity': {key: database.get(key) for key in ('guid', 'file_id')},
        'wire_counts': value('wire_counts'),
        'findings': (sample.get('findings', []) if status == 'reachable' else [{
            'code': 'scope-' + status, 'severity': 'warning',
            'reason': 'Current scope observation is ' + status,
            'observed_at': sample.get('ended_at'), 'value': None, 'threshold': None}]),
        'rate_window': {'ended_at': sample.get('started_at'),
                        'elapsed_seconds': rates.get('elapsed_seconds')}
                       if rates.get('status') == 'available' else None,
        'metrics': {
            'allocated_bytes': derived.get('allocated_bytes'),
            'memory_used': (value('memory') or {}).get('memory_used'),
            'user_attachments': (value('attachments') or {}).get('user'),
            'oldest_age_seconds': (value('transactions') or {}).get('oldest_age_seconds'),
            'crypt_state': database.get('crypt_state'),
            'replica_mode': database.get('replica_mode'),
            'page_reads_per_second': rates.get('per_second', {}).get('io.page_reads')
                if rates.get('status') == 'available' else None,
            'page_writes_per_second': rates.get('per_second', {}).get('io.page_writes')
                if rates.get('status') == 'available' else None,
        },
    }


def aggregate(databases):
    """Deduplicate only proven aliases within a registered endpoint.

    A GUID alone cannot distinguish copied databases. Unidentified observations
    stay in the matrix but cannot contribute to deduplicated totals.
    """
    unique = {}
    unidentified = 0
    for row in databases:
        identity = row.get('database_identity', {})
        key = (identity.get('guid'), identity.get('file_id'))
        if not all(key):
            unidentified += 1
            continue
        # Prefer broader visibility, then the newest observation for an alias.
        rank = (row.get('coverage') == 'database', -(row.get('sample_age_seconds') or 0))
        if key not in unique or rank > unique[key][0]:
            unique[key] = (rank, row)
    result = {'identity_basis': 'guid-and-file-id-within-registered-endpoint',
              'identified_databases': len(unique), 'unidentified_targets': unidentified,
              'alias_targets': len(databases) - unidentified - len(unique), 'metrics': {}}
    result['ranked_databases'] = [row for _, row in unique.values()]
    wire = dict.fromkeys(('encrypted', 'unencrypted', 'wire_unknown', 'local',
                          'transport_unknown'), 0)
    observed_wire = 0
    for _, row in unique.values():
        source = row.get('wire_counts')
        if not isinstance(source, dict) or source.get('truncated'):
            continue
        observed_wire += 1
        for entry in source.get('rows', []):
            transport = str(entry.get('transport', '')).strip()
            flag = entry.get('encrypted')
            kind = ('local' if transport == 'local' else
                    'transport_unknown' if transport != 'wire' else
                    'encrypted' if flag in (True, '1') else
                    'unencrypted' if flag in (False, '0') else 'wire_unknown')
            count = entry.get('count')
            if isinstance(count, str) and count.isdigit():
                wire[kind] += int(count)
    result['wire_security'] = {**{key: str(value) for key, value in wire.items()},
                               'observed_databases': observed_wire,
                               'identified_databases': len(unique)}
    encryption = dict.fromkeys(('0', '1', '2', '3', 'unknown'), 0)
    for _, row in unique.values():
        flag = row.get('metrics', {}).get('crypt_state')
        encryption[flag if flag in encryption else 'unknown'] += 1
    result['database_encryption'] = encryption
    for field in ('allocated_bytes', 'memory_used', 'user_attachments',
                  'page_reads_per_second', 'page_writes_per_second'):
        values = []
        windows = []
        for _, row in unique.values():
            raw = row.get('metrics', {}).get(field)
            if raw is None:
                continue
            try:
                value = Decimal(str(raw))
            except InvalidOperation:
                continue
            if value.is_finite() and value >= 0:
                values.append(value)
                if field.endswith('_per_second'):
                    windows.append(row.get('rate_window'))
        comparable = not windows or (all(window and window.get('ended_at') and
                                         window.get('elapsed_seconds') for window in windows) and
                                     all(window == windows[0] for window in windows))
        with localcontext() as context:
            context.prec = 128
            total = str(sum(values, Decimal(0))) if values and comparable else None
        result['metrics'][field] = {
            'value': total,
            'observed_databases': len(values), 'identified_databases': len(unique),
            'status': 'available' if total is not None else
                      'nonidentical-rate-windows' if values and not comparable else 'unavailable',
        }
    return result


def fleet_snapshot(registrations, read_snapshot):
    """read_snapshot reauthorizes each scope; no source factory is accepted."""
    rows = []
    totals = dict.fromkeys(('reachable', 'failed', 'unknown',
                           'permission-limited', 'stale'), 0)
    for server in registrations:
        sid = server['server_id']

        def read(target):
            try:
                return read_snapshot(sid, target)
            except PermissionError:
                return {'state': 'authorization-denied'}
            except Exception:
                # Configuration/authorization lookup failure is not evidence
                # of server unreachability. Do not expose exception details.
                return {'state': 'scope-unavailable'}

        result = observation(read(None), 'server')
        databases = []
        for target in server['databases']:
            detail = observation(read(target['target_id']), 'database')
            databases.append({**target, **detail})
        rows.append({**server, **result, 'databases': databases,
                     'aggregate': aggregate(databases),
                     'known_databases': len(databases),
                     'monitored_databases': sum(
                         item['collection_state'] == 'collecting'
                         for item in databases)})
        totals[result['status']] += 1
    return {'scope': 'engine', 'engine_id': 'firebird', 'servers': rows,
            'registered_endpoints': len(rows), 'status_counts': totals,
            'history': 'volatile', 'runtime_scope': 'this-process',
            'inventory_basis': 'owner-registrations-not-physical-instances'}
