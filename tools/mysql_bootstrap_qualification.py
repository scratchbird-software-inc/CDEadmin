"""Native configure_instance/bootstrap administration on disposable servers."""
import json


def qualify(execute, http, options, sql, login, output):
    proof = {'complete': False, 'checks': []}
    for peer, operation in enumerate(('instance.configure_cluster', 'instance.configure_replica_set')):
        user = 'sr_bootstrap_`雪_' + str(peer)
        password = "Private-bootstrap:'\\雪:" + str(peer)
        quoted = '`' + user.replace('`', '``') + '`@`%`'
        selected = options(operation, [{'clusterAdmin': quoted, 'clusterAdminPasswordExpiration': 'NEVER', 'restart': True}], peer)
        selected['account_password_mode'] = 'set'
        reviewed = http('review', {'options': selected}, peer=peer)
        assert password not in json.dumps(reviewed)
        assert reviewed['reviewed_seed']['account_state']['account'] == {'user': user, 'host': '%'}
        assert reviewed['reviewed_seed']['account_state']['exists'] is False
        value = execute(operation, [{'clusterAdmin': quoted, 'clusterAdminPasswordExpiration': 'NEVER', 'restart': True}], peer,
            account_password=password)
        assert value['result']['account_observation']['exists']
        assert login(peer, user, password)['identity'] == user+'@%'
        assert sql(peer, 'SELECT password_expired AS expired, password_lifetime AS lifetime FROM mysql.user WHERE User=%s AND Host=%s',
                   (user, '%')) == [{'expired': 'N', 'lifetime': 0}]
        # Existing native accounts reject a supplied bootstrap password.
        failed = execute(operation, [{'clusterAdmin': quoted}], peer, account_password='must-not-replace-existing-password', expect_returned=False)
        assert failed['native_error'] and failed['native_operation_outcome'] != 'returned'
        assert 'already exists' in failed['native_error']['message']
        assert login(peer, user, password)['identity'] == user+'@%'
        observed = http('reconcile', {'job_id': failed['job_id']}, peer=peer)
        acknowledged = http('acknowledge', {'job_id': failed['job_id'],
            'target_confirmation': failed['target']['server_uuid'], 'observation_digest': observed['observation_digest']}, peer=peer)
        assert acknowledged['native_operation_outcome'] == 'unknown' and acknowledged['target_state_acknowledged_at']
        preserved = execute(operation, [{'clusterAdmin': quoted}], peer)
        assert preserved['result']['account_observation']['exists']
        assert login(peer, user, password)['identity'] == user+'@%'
        omitted_host = execute(operation, [{'clusterAdmin': quoted.rsplit('@', 1)[0]}], peer)
        assert omitted_host['result']['account_observation']['account'] == {'user': user, 'host': '%'}
        assert login(peer, user, password)['identity'] == user+'@%'
        # Bind the reviewed account row and grants, including concurrent edits.
        review_options = options(operation, [{'clusterAdmin': quoted}], peer)
        reviewed = http('review', {'options': review_options}, peer=peer)
        sql(peer, 'ALTER USER '+quoted+' WITH MAX_USER_CONNECTIONS 7')
        http('start', {'job_id': reviewed['job_id'], 'review_digest': reviewed['review_digest'], 'confirmed': True}, peer=peer, refused=True)
        authentication = sql(peer, 'SELECT HEX(authentication_string) AS value FROM mysql.user WHERE User=%s AND Host=%s',
                             (user, '%'))[0]['value']
        assert authentication
        for path in (output/'app').rglob('*'):
            if not path.is_file() or path.suffix not in {'.json', '.py'}: continue
            text = path.read_text(errors='replace')
            assert authentication not in text, ('Native authentication material retained', path.name)
            assert password not in text and json.dumps(password, ensure_ascii=True)[1:-1] not in text, ('Private bootstrap password retained', path.name)
        proof['checks'].append(operation+'-native-create-private-password-login-expiration-existing-validation-and-stale-refusal')
    proof['complete'] = True
    return proof
