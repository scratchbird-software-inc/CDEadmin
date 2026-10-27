"""Exercise native guideline persistence through authenticated reviewed jobs.

The caller owns disposable native topologies. No reference-engine tests or
metadata fixtures are used; native Shell methods create every guideline.
"""
import json


def qualify(context, peer, execute, http, options, sql):
    name = 'sr_' + context + '_routes'
    checks = []

    def run(method, arguments=(), *, read=False, guideline='', returned=True):
        value = execute(context + '.' + method, list(arguments), peer,
            inspection=read, expect_returned=returned, guideline=guideline)
        return value

    def result(value):
        assert value['result']['control']['observation_error'] is None, value
        return json.loads(value['result']['control']['result_json'])

    def guide(method, arguments=(), **kwargs):
        return run('guideline.' + method, arguments, guideline=kwargs.pop('name', name), **kwargs)

    run('list_routers', read=True)
    result(run('router_options', read=True))
    run('set_routing_option', ['stats_updates_frequency', 7])
    run('set_routing_option', ['stats_updates_frequency', None])
    created = result(run('create_routing_guideline', [name]))
    assert created['name'] == name and created['destinations'] and created['routes'], created
    assert result(run('get_routing_guideline', [name], read=True)) == created
    listed = result(run('routing_guidelines', read=True))
    assert name in str(listed['rows']) and listed['columns']
    guide('add_destination', ['sr_primary', '$.server.memberRole = PRIMARY'])
    guide('add_route', ['sr_read', '$.session.targetPort = $.router.port.ro', ['round-robin(sr_primary)'], {'enabled': False}])
    guide('set_route_option', ['sr_read', 'enabled', True])
    guide('set_destination_option', ['sr_primary', 'match', '$.server.memberRole = SECONDARY'])
    for method in ('destinations', 'routes'):
        table = result(guide(method, read=True))
        assert table['columns'] and table['rows'], table
    guide('show', read=True)
    current = result(guide('as_json', read=True))
    assert any(row['name'] == 'sr_read' and row['enabled'] is True for row in current['routes']), current
    run('set_routing_option', ['guideline', name])
    assert result(run('get_routing_guideline', read=True))['name'] == name
    # A native error is recorded as an error, never a successful local rewrite.
    invalid = guide('add_destination', ['invalid_rule', '$.server.missing = 1'], returned=False)
    assert invalid['native_operation_outcome'] == 'unknown', invalid
    assert invalid['native_error'] and invalid['native_error']['message'], invalid
    observed = http('reconcile', {'job_id': invalid['job_id']}, peer=peer)
    http('acknowledge', {'job_id': invalid['job_id'], 'observation_digest': observed['observation_digest'],
        'target_confirmation': invalid['target']['server_uuid']}, peer=peer)
    assert result(guide('as_json', read=True)) == current
    checks.append('native-default-create-edit-query-active-selection-and-native-expression-error')

    exported = result(guide('export', read=True))['guideline_export_json']
    assert json.loads(exported) == current
    copy_name = name + '_copy'
    assert result(guide('copy', [copy_name]))['name'] == copy_name
    renamed = copy_name + '_renamed'
    guide('rename', [renamed], name=copy_name)
    assert result(run('get_routing_guideline', [renamed], read=True))['name'] == renamed
    run('remove_routing_guideline', [renamed])
    # Edit/delete after review invalidates the captured native document.
    selected = options(context + '.guideline.set_route_option', ['sr_read', 'enabled', False], peer, guideline=name)
    stale = http('review', {'options': selected}, peer=peer)
    guide('set_route_option', ['sr_read', 'enabled', False])
    http('start', {key: stale[key] for key in ('job_id', 'review_digest')} | {'confirmed': True}, peer=peer, refused=True)
    guide('remove_route', ['sr_read'])
    guide('remove_destination', ['sr_primary'])
    # Native force import replaces the same name, using an application-owned
    # private file; the submitted document never selects an execution-host path.
    imported = result(run('import_routing_guideline', [json.loads(exported), {'force': True}]))
    assert imported == current, imported
    independent = sql(peer, 'SELECT CAST(guideline AS CHAR) AS document FROM '
        'mysql_innodb_cluster_metadata.routing_guidelines WHERE name=%s', (name,))
    assert len(independent) == 1 and json.loads(independent[0]['document']) == current, independent
    checks.append('native-file-export-private-file-force-import-exact-document-copy-rename-and-stale-review-refusal')
    return {'complete': True, 'checks': checks, 'native_document': current,
        'router_deployment_and_traffic_qualification': 'open; no Router process is created by this qualifier'}
