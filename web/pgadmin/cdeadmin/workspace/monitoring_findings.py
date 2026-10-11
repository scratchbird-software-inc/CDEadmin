"""Evidence-based policy findings; never execute remediation from a viewer."""


def findings(policy, sample, previous):
    result = []

    def add(code, value, threshold, reason):
        result.append({'code': code, 'severity': 'warning', 'value': value,
                       'threshold': threshold, 'reason': reason,
                       'sample_id': sample.get('sample_id'),
                       'observed_at': sample.get('ended_at')})

    def values(observation, group):
        item = observation.get('groups', {}).get(group, {})
        return item.get('values', {}) if item.get('status') == 'available' else {}

    if sample.get('status') not in ('available', 'partial'):
        return result
    age = values(sample, 'transactions').get('oldest_age_seconds')
    if (policy.max_transaction_age_seconds and isinstance(age, str) and age.isdigit()
            and int(age) > policy.max_transaction_age_seconds):
        add('old-transaction', age, policy.max_transaction_age_seconds,
            'Oldest visible transaction exceeds configured age')
    database = values(sample, 'database')
    crypt = database.get('crypt_state')
    if policy.expected_encryption_state is not None and crypt is not None and str(crypt) != str(policy.expected_encryption_state):
        add('unexpected-encryption', crypt, policy.expected_encryption_state,
            'Native database encryption state differs from policy')
    wire = values(sample, 'wire_counts')
    if policy.require_wire_encryption:
        for row in wire.get('rows', []):
            if (str(row.get('transport', '')).strip() == 'wire' and
                    row.get('encrypted') in (False, '0') and str(row.get('count', '')).isdigit() and
                    int(row['count']) > 0):
                add('unencrypted-wire', row['count'], 0,
                    'Visible unencrypted user wire attachments violate configured policy')
    rates = sample.get('rates', {})
    conflicts = rates.get('delta', {}).get('records.record_conflicts')
    if rates.get('status') == 'available' and isinstance(conflicts, str) and conflicts.isdigit() and int(conflicts) > 0:
        add('new-conflicts', conflicts, 0, 'Record conflicts observed during this counter interval')
    state = database.get('backup_state')
    now = sample.get('runtime_elapsed_seconds')
    if policy.max_backup_state_seconds and state not in (None, '0', 0) and isinstance(now, (int, float)):
        start = now
        for old in reversed(previous):
            if (old.get('status') not in ('available', 'partial') or
                    old.get('source_epoch') != sample.get('source_epoch') or
                    values(old, 'database').get('backup_state') != state or
                    not isinstance(old.get('runtime_elapsed_seconds'), (int, float))):
                break
            start = old['runtime_elapsed_seconds']
        duration = max(0, now - start)
        if duration > policy.max_backup_state_seconds:
            add('prolonged-backup-state', str(duration), policy.max_backup_state_seconds,
                'Nonzero backup state continuously observed for at least these seconds')
    return result
