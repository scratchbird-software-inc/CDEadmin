#!/usr/bin/env python3
"""Verify view insertion and preservation of caller work on owned Firebird."""
import argparse
import json
from pathlib import Path
import secrets
from types import SimpleNamespace
import uuid

if __package__:
    from . import cdeadmin_firebird_views_gate as base
else:
    import cdeadmin_firebird_views_gate as base


def verify(connection, client, route, password, result):
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    from pgadmin.cdeadmin.providers.firebird.character_metadata import literal
    from pgadmin.cdeadmin.providers.firebird.error_diagnostics import (
        status_codes,
    )
    checks = result['view_insert_checks'] = []
    target = {'resource_kind': 'view', 'resource_id': 'view:VI_VIEW',
              'display_name': 'VI_VIEW', 'display_path': ['VI_VIEW']}
    admin = client.open_session({'route': route})

    def sql(handle, source, params=()):
        with handle.cursor() as cursor:
            cursor.execute(source, params)
            return cursor.fetchall() if cursor.description else []

    def observed():
        observer = client.open_session({'route': route})
        try:
            return sql(observer, 'SELECT ID, V FROM VI_BASE ORDER BY ID')
        finally:
            client.close_session(observer)

    def page(handle, driver=client, selected_route=route,
             sid='insert-session'):
        return base.ADMINISTRATION.read_rows(driver, {
            '_provider_route': selected_route, 'target_resource': target,
            'session_id': sid}, connection=handle)

    def request(p, values, selected_route=route, sid='insert-session'):
        return {'resource_kind': 'view', 'operation_id': 'insert',
                '_provider_route': selected_route, 'target_resource': target,
                'session_id': sid, 'draft': {'values': values, 'options': {
                    'identity_token': p['insert_identity_token']}}}

    try:
        for source in (
                'CREATE TABLE VI_BASE (ID INTEGER GENERATED ALWAYS AS '
                'IDENTITY PRIMARY KEY, V INTEGER DEFAULT 7 NOT NULL)',
                'CREATE VIEW VI_VIEW AS SELECT ID, V, V * 2 AS DOUBLED '
                'FROM VI_BASE', 'CREATE TABLE VI_PENDING (K INTEGER)',
                'CREATE TABLE VI_TEXT_BASE (ID INTEGER GENERATED ALWAYS AS '
                "IDENTITY PRIMARY KEY, V VARCHAR(40) DEFAULT 'fallback')",
                'CREATE VIEW VI_TEXT_VIEW AS SELECT ID, V FROM VI_TEXT_BASE'):
            sql(admin, source)
            client.control_transaction(admin, 'commit')
        for index, (mode, action) in enumerate(
                (mode, action) for mode in (
                    'explicit', 'defaults', 'null', 'computed',
                    'wrong-session', 'replay')
                for action in ('commit', 'rollback')):
            handle = client.open_session({'route': route})
            case = mode + ':' + action
            try:
                before = observed()
                sql(handle, 'INSERT INTO VI_PENDING VALUES (?)', (index,))
                transaction = handle.main_transaction.info.id
                p = page(handle)
                assert 'insert' in p['row_operations']
                assert p['insert_default_values'] is True
                assert next(col for col in p['columns']
                            if col['name'] == 'DOUBLED')['insertable'] is False
                values = ({} if mode == 'defaults' else
                          {'V': None} if mode == 'null' else
                          {'DOUBLED': 8} if mode == 'computed' else {'V': 21})
                r = request(p, values, sid=(
                    'different' if mode == 'wrong-session'
                    else 'insert-session'))
                codes = []
                try:
                    plan = base.ADMINISTRATION.plan(r)
                    if mode == 'replay':
                        try:
                            base.ADMINISTRATION.plan(r)
                        except RelationalClientError as exc:
                            assert 'unavailable or mismatched' in str(exc)
                        else:
                            raise AssertionError('Insert token replay')
                    receipt = base.ADMINISTRATION.apply(
                        client, plan, connection=handle)
                    assert receipt['staged_in_provider_session']
                    assert mode in {'explicit', 'defaults', 'replay'}
                    result['task_evidence']['visual_admin.view.insert'] = {
                        'live_execution': 'passed', 'statements': [
                            item['source'] for item in
                            plan['command_preview']['statements']]}
                except RelationalClientError as exc:
                    if mode == 'computed':
                        assert 'not admitted for insertion' in str(exc)
                    elif mode == 'wrong-session':
                        assert 'unavailable or mismatched' in str(exc)
                    elif mode == 'null':
                        codes = list(status_codes(exc))
                        assert 335544347 in codes, codes
                    else:
                        raise
                pending = sql(handle, 'SELECT ID, V FROM VI_BASE ORDER BY ID')
                if mode in {'explicit', 'defaults', 'replay'}:
                    assert pending[:-1] == before
                    assert pending[-1][1] == (7 if mode == 'defaults' else 21)
                    assert len(pending) == len(before) + 1
                else:
                    assert pending == before
                assert handle.main_transaction.info.id == transaction
                assert sql(handle, 'SELECT K FROM VI_PENDING WHERE K = ?',
                           (index,)) == [(index,)]
                assert observed() == before
                client.control_transaction(handle, action)
                assert observed() == (
                    pending if action == 'commit' else before)
                checks.append({'case': case, 'passed': True,
                               'native_status_codes': codes})
            except Exception as exc:
                checks.append({'case': case, 'passed': False})
                result['failures'].append({
                    'case': case, 'message': str(exc).replace(
                        password, '<redacted>')})
            finally:
                client.close_session(handle)
        text_checks = result['view_insert_text_checks'] = []
        original_target = target
        target = {'resource_kind': 'view', 'resource_id': 'view:VI_TEXT_VIEW',
                  'display_name': 'VI_TEXT_VIEW',
                  'display_path': ['VI_TEXT_VIEW']}
        for mode, values, expected in (
                ('omitted', {}, 'fallback'), ('empty', {'V': ''}, ''),
                ('null', {'V': None}, None)):
            for action in ('commit', 'rollback'):
                handle = client.open_session({'route': route})
                observer = client.open_session({'route': route})
                case = mode + ':' + action
                query = 'SELECT ID, V FROM VI_TEXT_BASE ORDER BY ID'
                try:
                    before = sql(observer, query)
                    client.control_transaction(observer, 'rollback')
                    sql(handle, 'INSERT INTO VI_PENDING VALUES (999)')
                    transaction = handle.main_transaction.info.id
                    p = page(handle)
                    assert 'insert' in p['row_operations']
                    plan = base.ADMINISTRATION.plan(request(p, values))
                    receipt = base.ADMINISTRATION.apply(
                        client, plan, connection=handle)
                    assert receipt['staged_in_provider_session']
                    pending = sql(handle, query)
                    assert pending[:-1] == before
                    assert pending[-1][1] == expected
                    assert len(pending) == len(before) + 1
                    assert handle.main_transaction.info.id == transaction
                    assert sql(handle, 'SELECT COUNT(*) FROM VI_PENDING '
                               'WHERE K = 999')[0][0] > 0
                    assert sql(observer, query) == before
                    client.control_transaction(observer, 'rollback')
                    client.control_transaction(handle, action)
                    assert sql(observer, query) == (
                        pending if action == 'commit' else before)
                    text_checks.append({'case': case, 'passed': True})
                except Exception as exc:
                    text_checks.append({'case': case, 'passed': False})
                    result['failures'].append({
                        'case': 'text:' + case,
                        'message': str(exc).replace(password, '<redacted>')})
                finally:
                    client.close_session(observer)
                    client.close_session(handle)
        target = original_target
        secret = secrets.token_urlsafe(24)
        reader = base._create_client(SimpleNamespace(
            acquire_secret=lambda *_: base.SecretLease(secret)))
        permissions = result['view_insert_permissions'] = []
        try:
            sql(admin, 'CREATE USER VI_READER PASSWORD ' + literal(secret))
            sql(admin, 'GRANT SELECT ON VI_VIEW TO USER VI_READER')
            client.control_transaction(admin, 'commit')
            for phase, command, allowed in (
                    ('select-only', None, False),
                    ('insert-only', 'GRANT INSERT ON VI_VIEW '
                     'TO USER VI_READER', True),
                    ('revoked', 'REVOKE INSERT ON VI_VIEW '
                     'FROM USER VI_READER', False)):
                if command:
                    sql(admin, command)
                    client.control_transaction(admin, 'commit')
                user_route = {**route, 'user': 'VI_READER'}
                handle = reader.open_session({'route': user_route})
                try:
                    p = page(handle, reader, user_route)
                    assert p['row_operations'] == (
                        ['insert'] if allowed else [])
                    assert all(not col['editable'] for col in p['columns'])
                    if allowed:
                        before = observed()
                        plan = base.ADMINISTRATION.plan(request(
                            p, {'V': 42}, user_route))
                        base.ADMINISTRATION.apply(reader, plan,
                                                  connection=handle)
                        assert observed() == before
                        reader.control_transaction(handle, 'rollback')
                        assert observed() == before
                    permissions.append({'phase': phase, 'passed': True})
                finally:
                    reader.close_session(handle)
        except Exception as exc:
            message = str(exc).replace(secret, '<redacted>')
            raise RuntimeError(message) from None
        if result.get('verify_provider'):
            from pgadmin.cdeadmin.core import EndpointContext
            from pgadmin.cdeadmin.providers.firebird.provider import (
                FirebirdProvider, PROFILE,
            )
            context = EndpointContext(
                endpoint_id=str(uuid.uuid4()), mode='legacy_native',
                experience_family='firebird', provider_id=PROFILE.provider_id,
                provider_version='0.1.0', profile_id=PROFILE.profile_id,
                profile_version=PROFILE.exact_version,
                runtime_verification_state='verified',
                verified_runtime_family='firebird',
                verified_runtime_version=result['engine_version'],
                target_adapter_id='firebird_wire-client',
                target_adapter_version='owned',
                pool_namespace=str(uuid.uuid4()),
                session_namespace=str(uuid.uuid4()),
                cache_namespace=str(uuid.uuid4()),
                diagnostic_namespace=str(uuid.uuid4()),
                effective_permissions=frozenset({
                    'network', 'secret_read', 'data_read', 'data_write',
                    'administer', 'execute'}))
            provider = FirebirdProvider(context, SimpleNamespace(
                require=lambda *_args, **_kwargs: None), client)
            for values in ({}, {'V': 31}):
                before = observed()
                sid = provider.open_session({'route': route})['session_id']
                try:
                    p = provider.read_visual_admin_rows({
                        '_provider_route': route, 'target_resource': target,
                        'session_id': sid})
                    spare = provider.read_visual_admin_rows({
                        '_provider_route': route, 'target_resource': target,
                        'session_id': sid})['insert_identity_token']
                    assert spare in base.ADMINISTRATION._row_identities
                    r = request(p, values, sid=sid)
                    validation = provider.validate_visual_admin(r)
                    assert validation['valid'], validation
                    plan = provider.plan_visual_admin(r)
                    assert plan['state'] == 'ready', plan
                    receipt = provider.apply_visual_admin({
                        'session_id': sid, 'plan_id': plan['plan_id'],
                        'plan_digest': plan['plan_digest']})
                    assert receipt['provider_result'][
                        'staged_in_provider_session']
                    assert spare not in base.ADMINISTRATION._row_identities
                    assert observed() == before
                finally:
                    provider.close_session({'session_id': sid})
                assert observed() == before
            result['provider_insert_passed'] = True
    finally:
        client.close_session(admin)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--bootstrap-contract', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite evidence')

    def checks(connection, client, route, password, result):
        result['verify_provider'] = not args.bootstrap_contract
        verify(connection, client, route, password, result)

    result = base.run(extra_checks=checks,
                      run_grid_boundaries=not args.bootstrap_contract)
    result['complete'] = (result['complete'] and
                          len(result.get('view_insert_checks', [])) == 12 and
                          all(c['passed'] for c in result[
                              'view_insert_checks'])
                          and len(result.get('view_insert_permissions', []))
                          == 3
                          and len(result.get('view_insert_text_checks', []))
                          == 6
                          and all(c['passed'] for c in result[
                              'view_insert_text_checks'])
                          and (args.bootstrap_contract or
                               result.get('provider_insert_passed') is True))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
