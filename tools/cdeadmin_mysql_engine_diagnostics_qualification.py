"""Owned native & HTTP MySQL engine diagnostic qualification across 9.7.0 and 8.4; no history tests."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def output_area(output):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Native qualification output belongs outside source')
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    return output


def _qualify_image(image, work_dir):
    import config  # noqa: F401
    from tools.mysql_qualification_support import server, _root_connection
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client, MYSQL_PROFILE, _resources
    from pgadmin.cdeadmin.sdk import RelationalClientError

    sources = [
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_engine_diagnostics.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/administration.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
        'web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
        'web/pgadmin/cdeadmin/ui_descriptors/mysql/capabilities.json',
        'tools/cdeadmin_mysql_engine_diagnostics_qualification.py',
    ]
    proof = {
        'complete': False,
        'history_testing': 'not run',
        'scope': (
            f'Owned {image} fixture; production native catalog and both client '
            'implementations validate/plan/apply across ENGINE, ALL, non-log/mutex '
            'engines, restricted users, stale server_uuid, killed observer connection '
            'and native truncation bounds. Private text is only hashed.'
        ),
        'interfaces': [],
        'source_sha256': {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in sources
        },
    }
    tag_slug = image.split(':', 1)[1].replace('.', '_')
    fx_primary = work_dir / f'mysql-diag-{tag_slug}-primary'
    fx_peer = work_dir / f'mysql-diag-{tag_slug}-peer'
    with server(fx_primary, image=image, server_id=101) as (base_route, _name, fixture), \
            server(fx_peer, image=image, server_id=102) as (peer_route, _peer_name, peer_fixture):
        assert fixture['server_uuid'] != peer_fixture['server_uuid']
        native = _root_connection('mysql', base_route['port'])
        native.autocommit = True
        try:
            target = next(
                x for x in _resources(native, {}, MYSQL_PROFILE)
                if x['resource_kind'] == 'server'
            )
            password = secrets.token_urlsafe(24)
            with native.cursor() as c:
                c.execute("CREATE USER 'owned_diag'@'%' IDENTIFIED BY %s", (password,))
            for pure in [True, False]:
                route, permissions = provider_access({**base_route, 'use_pure': pure})
                peer_rt, _ = provider_access({**peer_route, 'use_pure': pure})
                client = _create_client(
                    MYSQL_PROFILE,
                    permissions,
                    SimpleNamespace(pool_namespace=f'owned-engine-diag-{tag_slug}-{pure}'),
                )
                interface = {
                    'use_pure': pure,
                    'templates': {},
                    'checks': [],
                    'all_templates': {},
                    'all_checks': [],
                    'engine_variant_checks': [],
                    'truncation_checks': [],
                    'stale_server_uuid_checks': [],
                    'connection_interruption_checks': [],
                }
                proof['interfaces'].append(interface)

                def request(op, engine='InnoDB'):
                    return {
                        'resource_kind': 'server',
                        'operation_id': op,
                        'target_resource': target,
                        'draft': {
                            'engine': engine,
                            'private_data_confirmed': True,
                            'confirmation': target['display_name'],
                        },
                        '_provider_route': route,
                    }

                try:
                    probe = client._connect({'route': route})
                    interface['native_connection_class'] = type(probe).__name__
                    client._forget_and_close(probe)

                    # 1. Single ENGINE InnoDB across status, logs, mutex
                    for suffix in ['status', 'logs', 'mutex']:
                        operation = 'show_engine_' + suffix
                        req = request(operation)
                        assert not client.validate_admin_operation(req)['errors']
                        planned = client.plan_admin_operation(req)
                        interface['templates'][operation] = (
                            planned['provider_payload']['compiled']['statements'][0]['source']
                        )
                        response = client.apply_admin_operation(planned)
                        result = response['engine_diagnostic']
                        assert result['native_acknowledged'] and result['complete'] and not result['truncated']
                        assert response['connection_release']['connection_released']
                        assert result['columns'] == ['Type', 'Name', 'Status']
                        assert result['execution_identity']['server_uuid'] == fixture['server_uuid']
                        if suffix == 'status':
                            assert result['rows'] and result['rows'][0][0] == 'InnoDB'
                        interface['checks'].append({
                            'operation': operation,
                            'native_parser_accepted_by_execution': True,
                            'row_count': len(result['rows']),
                            'complete': result['complete'],
                            'text_sha256': hashlib.sha256(json.dumps(result['rows']).encode()).hexdigest(),
                            'connection_released': True,
                        })

                    # 2. Non-log/mutex engines (MEMORY, CSV)
                    for alt_engine in ['MEMORY', 'CSV']:
                        for suffix in ['status', 'logs', 'mutex']:
                            operation = 'show_engine_' + suffix
                            req = request(operation, alt_engine)
                            assert not client.validate_admin_operation(req)['errors']
                            planned = client.plan_admin_operation(req)
                            try:
                                response = client.apply_admin_operation(planned)
                            except RelationalClientError as err:
                                assert err.native_dispatched and not err.native_acknowledged
                                assert err.automatic_retry is False
                                assert err.connection_release['connection_released']
                                interface['engine_variant_checks'].append({
                                    'engine': alt_engine,
                                    'operation': operation,
                                    'outcome': 'native_engine_refusal',
                                    'errno': err.errno,
                                    'native_acknowledged': False,
                                    'connection_released': True,
                                })
                            else:
                                result = response['engine_diagnostic']
                                assert response['connection_release']['connection_released']
                                assert result['complete'] and not result['truncated']
                                if not result['rows']:
                                    assert result['interpretation'] == 'native-no-rows-returned'
                                interface['engine_variant_checks'].append({
                                    'engine': alt_engine,
                                    'operation': operation,
                                    'outcome': result['interpretation'],
                                    'row_count': len(result['rows']),
                                    'native_acknowledged': result['native_acknowledged'],
                                    'connection_released': True,
                                })

                    # 3. ALL scope
                    for suffix in ['status', 'logs', 'mutex']:
                        operation = 'show_engine_' + suffix
                        req = request(operation)
                        req['draft'].pop('engine')
                        req['draft']['engine_scope'] = 'ALL'
                        assert not client.validate_admin_operation(req)['errors']
                        planned = client.plan_admin_operation(req)
                        interface['all_templates'][operation] = (
                            planned['provider_payload']['compiled']['statements'][0]['source']
                        )
                        response = client.apply_admin_operation(planned)
                        result = response['engine_diagnostic']
                        assert result['native_acknowledged'] and result['complete'] and not result['truncated']
                        assert response['connection_release']['connection_released']
                        assert result['engine']['scope'] == 'ALL'
                        interface['all_checks'].append({
                            'operation': operation,
                            'native_parser_accepted_by_execution': True,
                            'row_count': len(result['rows']),
                            'complete': True,
                            'connection_released': True,
                            'text_sha256': hashlib.sha256(json.dumps(result['rows']).encode()).hexdigest(),
                        })

                    # 4. Truncation bound checks (row bound & byte bound on live native output)
                    from pgadmin.cdeadmin.providers.mysql_family import mysql_engine_diagnostics as diag_mod
                    orig_max_rows, orig_max_bytes = diag_mod.MAX_ROWS, diag_mod.MAX_BYTES
                    try:
                        if image != 'mysql:9.7.0':
                            diag_mod.MAX_ROWS = 64
                        pfs_req = request('show_engine_status', 'PERFORMANCE_SCHEMA')
                        pfs_plan = client.plan_admin_operation(pfs_req)
                        pfs_resp = client.apply_admin_operation(pfs_plan)
                        pfs_diag = pfs_resp['engine_diagnostic']
                        assert pfs_diag['truncated'] is True and pfs_diag['complete'] is False
                        assert pfs_diag['native_acknowledged'] is False
                        assert pfs_diag['native_completion'] == 'unconfirmed-output-truncated'
                        assert pfs_diag['interpretation'] == 'bounded-native-partial-output'
                        assert len(pfs_diag['rows']) == diag_mod.MAX_ROWS
                        assert pfs_resp['connection_release']['connection_released'] is True
                        interface['truncation_checks'].append({
                            'bound_kind': 'row_limit',
                            'engine': 'PERFORMANCE_SCHEMA',
                            'operation': 'show_engine_status',
                            'configured_row_limit': diag_mod.MAX_ROWS,
                            'returned_rows': len(pfs_diag['rows']),
                            'truncated': True,
                            'native_acknowledged': False,
                            'native_completion': pfs_diag['native_completion'],
                            'connection_released': True,
                        })

                        diag_mod.MAX_ROWS = orig_max_rows
                        diag_mod.MAX_BYTES = 512
                        byte_req = request('show_engine_status', 'InnoDB')
                        byte_plan = client.plan_admin_operation(byte_req)
                        byte_resp = client.apply_admin_operation(byte_plan)
                        byte_diag = byte_resp['engine_diagnostic']
                        assert byte_diag['truncated'] is True and byte_diag['complete'] is False
                        assert byte_diag['native_acknowledged'] is False
                        assert byte_diag['native_completion'] == 'unconfirmed-output-truncated'
                        assert byte_diag['interpretation'] == 'bounded-native-partial-output'
                        assert byte_resp['connection_release']['connection_released'] is True
                        interface['truncation_checks'].append({
                            'bound_kind': 'byte_limit',
                            'engine': 'InnoDB',
                            'operation': 'show_engine_status',
                            'configured_byte_limit': 512,
                            'returned_rows': len(byte_diag['rows']),
                            'truncated': True,
                            'native_acknowledged': False,
                            'native_completion': byte_diag['native_completion'],
                            'connection_released': True,
                        })
                    finally:
                        diag_mod.MAX_ROWS = orig_max_rows
                        diag_mod.MAX_BYTES = orig_max_bytes

                    # 5. Missing/disabled engine refusal
                    for bad_eng in ['not_installed_owned', 'FEDERATED']:
                        try:
                            client.plan_admin_operation(request('show_engine_status', bad_eng))
                        except RelationalClientError:
                            pass
                        else:
                            raise AssertionError(f'missing/disabled engine admitted: {bad_eng}')
                    interface['missing_engine_refused'] = True

                    # 6. Stale server_uuid mismatch refusal before dispatch (plan & apply)
                    stale_uuid = '00000000-0000-4000-8000-000000000099'
                    stale_target = json.loads(json.dumps(target))
                    stale_target['native']['server_uuid'] = stale_uuid
                    if 'state' in stale_target['native']:
                        stale_target['native']['state']['server_uuid'] = stale_uuid
                    try:
                        client.plan_admin_operation({**request('show_engine_status'), 'target_resource': stale_target})
                    except RelationalClientError:
                        interface['stale_server_uuid_checks'].append({'stage': 'plan', 'refused_before_dispatch': True})
                    else:
                        raise AssertionError('Stale target server_uuid was admitted at plan')

                    rerouted_plan = client.plan_admin_operation(request('show_engine_status'))
                    rerouted_plan['provider_payload']['route'] = peer_rt
                    try:
                        client.apply_admin_operation(rerouted_plan)
                    except RelationalClientError as mismatch_err:
                        assert mismatch_err.native_dispatched is False
                        assert mismatch_err.native_acknowledged is False
                        assert mismatch_err.automatic_retry is False
                        assert mismatch_err.connection_release['connection_released'] is True
                        interface['stale_server_uuid_checks'].append({
                            'stage': 'apply_rerouted_server_uuid',
                            'native_dispatched': False,
                            'native_acknowledged': False,
                            'automatic_retry': False,
                            'connection_released': True,
                        })
                    else:
                        raise AssertionError('Rerouted server_uuid mismatch was admitted at apply')

                    # 7. Connection interruption / KILL CONNECTION before & during execution
                    for kill_phase in ['before_identity', 'before_show_engine']:
                        kill_plan = client.plan_admin_operation(request('show_engine_status'))
                        real_connect = client._connect

                        def interrupting_connect(req_arg, _phase=kill_phase):
                            conn = real_connect(req_arg)
                            cid = conn.connection_id
                            if _phase == 'before_identity':
                                with native.cursor() as kc:
                                    kc.execute(f'KILL CONNECTION {int(cid)}')
                                return conn
                            real_cursor_fn = conn.cursor

                            def wrapped_cursor(*a, **kw):
                                cur = real_cursor_fn(*a, **kw)
                                real_exec = cur.execute

                                def wrapped_exec(sql, *ea, **ekw):
                                    if str(sql).startswith('SHOW ENGINE '):
                                        with native.cursor() as kc:
                                            kc.execute(f'KILL CONNECTION {int(cid)}')
                                    return real_exec(sql, *ea, **ekw)

                                cur.execute = wrapped_exec
                                return cur

                            conn.cursor = wrapped_cursor
                            return conn

                        client._connect = interrupting_connect
                        try:
                            try:
                                client.apply_admin_operation(kill_plan)
                            except RelationalClientError as kill_err:
                                assert kill_err.native_acknowledged is False
                                assert kill_err.automatic_retry is False
                                expected_dispatched = (kill_phase == 'before_show_engine')
                                assert kill_err.native_dispatched is expected_dispatched
                                assert isinstance(kill_err.connection_release.get('connection_released'), bool)
                                interface['connection_interruption_checks'].append({
                                    'phase': kill_phase,
                                    'native_dispatched': kill_err.native_dispatched,
                                    'native_acknowledged': kill_err.native_acknowledged,
                                    'automatic_retry': kill_err.automatic_retry,
                                    'connection_released': kill_err.connection_release['connection_released'],
                                })
                            else:
                                raise AssertionError(f'Killed connection succeeded unexpectedly ({kill_phase})')
                        finally:
                            client._connect = real_connect

                    # 8. Restricted user denials (single ENGINE and ALL)
                    restricted_route, restricted_permissions = provider_access(
                        {**base_route, 'use_pure': pure, 'user': 'owned_diag'},
                        password,
                    )
                    restricted = _create_client(
                        MYSQL_PROFILE,
                        restricted_permissions,
                        SimpleNamespace(pool_namespace=f'owned-engine-diag-restricted-{tag_slug}-{pure}'),
                    )
                    try:
                        for suffix in ['status', 'logs', 'mutex']:
                            req = {**request('show_engine_' + suffix), '_provider_route': restricted_route}
                            plan = restricted.plan_admin_operation(req)
                            try:
                                restricted.apply_admin_operation(plan)
                            except RelationalClientError as error:
                                assert error.native_dispatched and not error.native_acknowledged
                                assert error.errno in {1044, 1045, 1142, 1227}, error.errno
                                assert error.connection_release['connection_released']
                                interface['checks'].append({
                                    'native_denied': 'show_engine_' + suffix,
                                    'native_error_code': error.errno,
                                    'automatic_retry': error.automatic_retry,
                                    'connection_released': True,
                                })
                            else:
                                raise AssertionError('restricted native access')
                        for suffix in ['status', 'logs', 'mutex']:
                            req = {**request('show_engine_' + suffix), '_provider_route': restricted_route}
                            req['draft'].pop('engine')
                            req['draft']['engine_scope'] = 'ALL'
                            plan = restricted.plan_admin_operation(req)
                            try:
                                restricted.apply_admin_operation(plan)
                            except RelationalClientError as error:
                                assert error.native_dispatched and not error.native_acknowledged
                                assert error.errno in {1044, 1045, 1142, 1227}
                                assert error.connection_release['connection_released']
                                interface['all_checks'].append({
                                    'native_denied': 'show_engine_' + suffix,
                                    'native_error_code': error.errno,
                                    'automatic_retry': error.automatic_retry,
                                    'connection_released': True,
                                })
                            else:
                                raise AssertionError('Restricted ALL-engine diagnostic admitted')
                    finally:
                        restricted.close()
                finally:
                    client.close()
        finally:
            native.close()
    proof['owned_server_stopped'] = (
        fixture['owned_server_stopped'] and peer_fixture['owned_server_stopped']
    )
    proof['fixture_image'] = fixture['image']
    proof['peer_fixture_image'] = peer_fixture['image']
    proof['native_version'] = fixture['engine_version']
    proof['complete'] = True
    return proof


def core(output):
    W = output_area(output)
    scratch = Path(tempfile.mkdtemp(prefix='mysql-diag-core-', dir=str(W)))
    proof_97 = {'complete': False}
    proof_84 = {'complete': False}
    try:
        proof_97 = _qualify_image('mysql:9.7.0', scratch)
        (W / 'mysql-engine-diagnostics-native.json').write_text(
            json.dumps(proof_97, indent=2) + '\n'
        )
        proof_84 = _qualify_image('mysql:8.4', scratch)
        (W / 'mysql-engine-diagnostics-8_4-native.json').write_text(
            json.dumps(proof_84, indent=2) + '\n'
        )
        return {'complete': proof_97['complete'] and proof_84['complete'],
                'mysql_9_7_0': proof_97['native_version'],
                'mysql_8_4': proof_84['native_version']}
    finally:
        if not proof_97.get('complete'):
            (W / 'mysql-engine-diagnostics-native.json').write_text(
                json.dumps(proof_97, indent=2) + '\n'
            )
        if not proof_84.get('complete') and proof_84 != {'complete': False}:
            (W / 'mysql-engine-diagnostics-8_4-native.json').write_text(
                json.dumps(proof_84, indent=2) + '\n'
            )
        shutil.rmtree(scratch, ignore_errors=True)


def http(output):
    W = output_area(output)
    R = ROOT
    scratch = Path(tempfile.mkdtemp(prefix='mysql-diag-http-', dir=str(W)))
    proof = {
        'complete': False,
        'history_testing': 'not run',
        'scope': (
            'Authenticated desktop HTTP server registration/verify, actual '
            'descriptor fields, visual validation/review/apply, one-use replay '
            'refusal, Cache-Control: no-store, truncation and restricted HTTP user '
            'denial on owned native MySQL 9.7.0. Private returned text is only hashed.'
        ),
        'checks': [],
        'restricted_http_checks': [],
        'source_sha256': {
            p: hashlib.sha256((R / p).read_bytes()).hexdigest()
            for p in [
                'web/pgadmin/cdeadmin/providers/mysql_family/mysql_engine_diagnostics.py',
                'web/pgadmin/cdeadmin/providers/mysql_family/administration.py',
                'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
                'web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
                'web/pgadmin/cdeadmin/ui_descriptors/mysql/capabilities.json',
                'tools/cdeadmin_mysql_engine_diagnostics_qualification.py',
            ]
        },
    }
    try:
        from tools.cdeadmin_mysql_dump_verification_qualification import setup_application
        http_app_dir = scratch / 'http-app'
        http_app_dir.mkdir(parents=True, exist_ok=True)
        app = setup_application(http_app_dir)
        from tools.mysql_qualification_support import server, _root_connection
        from pgadmin.cdeadmin.providers.mysql_family.provider import _resources, MYSQL_PROFILE
        from pgadmin.cdeadmin.endpoints.profiles import registration_profile
        from pgadmin.model import db, User, ServerGroup, Server
        from flask import url_for

        with server(scratch / 'mysql-engine-http-fixture') as (route, _name, fixture):
            native = _root_connection('mysql', route['port'])
            try:
                target = next(
                    x for x in _resources(native, {}, MYSQL_PROFILE)
                    if x['resource_kind'] == 'server'
                )
                password = secrets.token_urlsafe(24)
                restricted_password = secrets.token_urlsafe(24)
                with native.cursor() as cursor:
                    cursor.execute("CREATE USER 'owned_http'@'%' IDENTIFIED BY %s", (password,))
                    cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'owned_http'@'%'")
                    cursor.execute(
                        "CREATE USER 'owned_http_restricted'@'%' IDENTIFIED BY %s",
                        (restricted_password,),
                    )
                native.commit()
                priv_route = {**route, 'user': 'owned_http'}
                rest_route = {**route, 'user': 'owned_http_restricted'}
            finally:
                native.close()

            with app.test_request_context('/'):
                user = User.query.first()
                uid = user.id
                group = ServerGroup.query.filter_by(user_id=uid).first()
                app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)

                item = Server(
                    user_id=uid, servergroup_id=group.id,
                    name='Owned MySQL engine diagnostics',
                    host=priv_route['host'], port=priv_route['port'],
                    username='owned_http', maintenance_db=None, save_password=0,
                )
                item._cde_endpoint_registration = registration_profile('mysql-native')
                item._cde_endpoint_route_configuration = {
                    **priv_route, 'credential_kinds': ['database_password'],
                }
                rest_item = Server(
                    user_id=uid, servergroup_id=group.id,
                    name='Owned MySQL engine diagnostics restricted',
                    host=rest_route['host'], port=rest_route['port'],
                    username='owned_http_restricted', maintenance_db=None, save_password=0,
                )
                rest_item._cde_endpoint_registration = registration_profile('mysql-native')
                rest_item._cde_endpoint_route_configuration = {
                    **rest_route, 'credential_kinds': ['database_password'],
                }
                db.session.add_all([item, rest_item])
                db.session.commit()
                url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=item.id)
                verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=item.id)
                rest_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=rest_item.id)
                rest_verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=rest_item.id)

            client = app.test_client()
            with client.session_transaction() as session:
                session['_user_id'] = str(uid)
                session['_fresh'] = True
            assert client.post(verify_url, json={'password': password}).get_json()['success']
            assert client.post(rest_verify_url, json={'password': restricted_password}).get_json()['success']

            def post(endpoint_url, action, req_body, denied=False):
                response = client.post(endpoint_url, json={'action': action, 'request': req_body})
                assert response.headers.get('Cache-Control') == 'no-store'
                value = response.get_json()
                if denied:
                    assert response.status_code != 200 or not value.get('success'), value
                    return value
                assert response.status_code == 200 and value.get('success'), (action, value)
                return value['data']

            declared = json.loads(
                (R / 'web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json').read_text()
            )['operations']
            for scope in ['ENGINE', 'ALL']:
                for suffix in ['status', 'logs', 'mutex']:
                    operation = 'show_engine_' + suffix
                    fields = next(
                        x['fields'] for x in declared
                        if x['resource_kind'] == 'server' and x['operation_id'] == operation
                    )
                    draft = {x['field_id']: x.get('default') for x in fields}
                    draft.update(private_data_confirmed=True, confirmation=target['display_name'])
                    draft['engine_scope'] = scope
                    if scope == 'ALL':
                        draft.pop('engine', None)
                    req = {
                        'resource_kind': 'server',
                        'operation_id': operation,
                        'target_resource': target,
                        'draft': draft,
                    }
                    assert post(url, 'visual_admin_validate', req)['valid']
                    plan = post(url, 'visual_admin_plan', req)
                    assert plan['state'] == 'ready'
                    result = post(
                        url,
                        'visual_admin_apply',
                        {'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': True},
                    )['provider_result']['engine_diagnostic']
                    assert result['native_acknowledged']
                    assert result['execution_identity']['server_uuid'] == fixture['server_uuid']
                    proof['checks'].append({
                        'operation': operation,
                        'engine_scope': scope,
                        'row_count': len(result['rows']),
                        'complete': result['complete'],
                        'cache_control': 'no-store',
                        'private_text_sha256': hashlib.sha256(json.dumps(result['rows']).encode()).hexdigest(),
                    })
                    # One-use replay refusal
                    post(
                        url,
                        'visual_admin_apply',
                        {'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': True},
                        denied=True,
                    )

                    # Restricted HTTP user denial
                    rest_plan = post(rest_url, 'visual_admin_plan', req)
                    assert rest_plan['state'] == 'ready'
                    post(
                        rest_url,
                        'visual_admin_apply',
                        {'plan_id': rest_plan['plan_id'], 'plan_digest': rest_plan['plan_digest'], 'confirmed': True},
                        denied=True,
                    )
                    proof['restricted_http_checks'].append({
                        'operation': operation,
                        'engine_scope': scope,
                        'denied_over_http': True,
                        'cache_control': 'no-store',
                    })

            # HTTP truncation check on PERFORMANCE_SCHEMA
            trunc_req = {
                'resource_kind': 'server',
                'operation_id': 'show_engine_status',
                'target_resource': target,
                'draft': {
                    'engine_scope': 'ENGINE',
                    'engine': 'PERFORMANCE_SCHEMA',
                    'private_data_confirmed': True,
                    'confirmation': target['display_name'],
                },
            }
            trunc_plan = post(url, 'visual_admin_plan', trunc_req)
            trunc_diag = post(
                url,
                'visual_admin_apply',
                {'plan_id': trunc_plan['plan_id'], 'plan_digest': trunc_plan['plan_digest'], 'confirmed': True},
            )['provider_result']['engine_diagnostic']
            assert trunc_diag['truncated'] is True and trunc_diag['native_acknowledged'] is False
            assert trunc_diag['native_completion'] == 'unconfirmed-output-truncated'
            proof['checks'].append({
                'operation': 'show_engine_status',
                'engine': 'PERFORMANCE_SCHEMA',
                'truncated': True,
                'native_acknowledged': False,
                'native_completion': trunc_diag['native_completion'],
            })

            invalid = {**trunc_req, 'draft': {**trunc_req['draft'], 'private_data_confirmed': False}}
            assert not post(url, 'visual_admin_validate', invalid)['valid']
            proof['checks'].append('Private access refused; one-use reviewed plan cannot be replayed; no-store responses')
        proof['owned_server_stopped'] = fixture['owned_server_stopped']
        proof['complete'] = True
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        (W / 'mysql-engine-http.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage', choices=('core', 'http'), required=True)
    args = parser.parse_args()
    result = (core if args.stage == 'core' else http)(args.output)
    print(json.dumps({'complete': result['complete'], 'stage': args.stage}))
