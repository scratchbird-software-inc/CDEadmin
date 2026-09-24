#!/usr/bin/env python3
"""Binary edits through public provider validation/plan/apply contracts."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

if __package__:
    from . import cdeadmin_firebird_views_gate as base
else:
    import cdeadmin_firebird_views_gate as base


def provider_for(client, result):
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
        pool_namespace=str(uuid.uuid4()), session_namespace=str(uuid.uuid4()),
        cache_namespace=str(uuid.uuid4()),
        diagnostic_namespace=str(uuid.uuid4()),
        effective_permissions=frozenset({
            'network', 'secret_read', 'data_read', 'data_write',
            'administer', 'execute'}))
    return FirebirdProvider(context, SimpleNamespace(
        require=lambda *_args, **_kwargs: None), client)


def verify(connection, client, route, password, result):
    from pgadmin.cdeadmin.providers.firebird.grid_values import normalize_value
    from pgadmin.cdeadmin.visual_admin.provider import VisualAdminAccessError
    checks = result['binary_grid_checks'] = []
    provider = provider_for(client, result)
    admin = client.open_session({'route': route})

    def sql(handle, source):
        with handle.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []

    def observe():
        from pgadmin.cdeadmin.providers.firebird.grid_values import materialize
        handle = client.open_session({'route': route})
        try:
            # Consume BLOB streams while their cursor and attachment live.
            with handle.cursor() as cursor:
                cursor.execute('SELECT F, V, B FROM GB_BASE ORDER BY ID')
                return [tuple(materialize(value) for value in row)
                        for row in cursor]
        finally:
            client.close_session(handle)

    try:
        sql(admin, 'CREATE TABLE GB_BASE (ID INTEGER GENERATED ALWAYS AS '
            'IDENTITY PRIMARY KEY, F BINARY(4), V VARBINARY(256), '
            'B BLOB SUB_TYPE BINARY)')
        client.control_transaction(admin, 'commit')
        sql(admin, 'CREATE VIEW GB_VIEW AS SELECT * FROM GB_BASE')
        client.control_transaction(admin, 'commit')
        examples = [(b'', b'', b''), (b'\x00\xff\x7f\x00',
                    bytes(range(256)), bytes(range(256)) * 4096),
                    (None, None, None)]
        for kind, name in (('table', 'GB_BASE'), ('view', 'GB_VIEW')):
            for action in ('commit', 'rollback'):
                for index, example in enumerate(examples):
                    case = f'{kind}:{action}:{index}'
                    sid = provider.open_session({'route': route})['session_id']
                    request = {'_provider_route': route, 'session_id': sid,
                               'resource_kind': kind, 'target_resource': {
                                   'resource_kind': kind,
                                   'display_path': [name]}}

                    def mutate(operation, draft):
                        payload = {**request, 'operation_id': operation,
                                   'draft': draft}
                        validation = provider.validate_visual_admin(payload)
                        assert validation['valid'], validation
                        plan = provider.plan_visual_admin(payload)
                        assert plan['state'] == 'ready', plan
                        # Public plan/presentation contains no Python bytes.
                        json.dumps(plan)
                        application = {
                            'session_id': sid, 'plan_id': plan['plan_id'],
                            'plan_digest': plan['plan_digest']}
                        if operation == 'delete':
                            try:
                                provider.apply_visual_admin(application)
                            except VisualAdminAccessError as exc:
                                assert 'requires confirmation' in str(exc)
                            else:
                                raise AssertionError(
                                    'Unconfirmed deletion was admitted')
                            # Denied applications consume their plan. Re-read
                            # the row and acquire a fresh identity and plan.
                            refreshed = provider.read_visual_admin_rows(
                                request)
                            payload['draft']['selector'] = {
                                'identity_token': refreshed['rows'][-1][
                                    'identity_token']}
                            plan = provider.plan_visual_admin(payload)
                            application.update(plan_id=plan['plan_id'],
                                               plan_digest=plan['plan_digest'])
                            application['confirmed'] = True
                        receipt = provider.apply_visual_admin(application)
                        assert receipt['provider_result'][
                            'staged_in_provider_session']

                    try:
                        before = observe()
                        page = provider.read_visual_admin_rows(request)
                        assert [col['input_kind'] for col in page[
                            'columns']] == ['integer'] + ['binary'] * 3
                        values = dict(zip(('F', 'V', 'B'), example))
                        mutate('insert', {
                            'values': {key: normalize_value(value)
                                       for key, value in values.items()},
                            'options': {'identity_token': page[
                                'insert_identity_token']}})
                        page = provider.read_visual_admin_rows(request)
                        json.dumps(page)
                        expected = dict(values)
                        if expected['F'] is not None:
                            expected['F'] = expected['F'].ljust(4, b'\x00')
                        row = page['rows'][-1]
                        actual = {key: row['values'][key] for key in expected}
                        assert actual == {
                            key: normalize_value(value)
                            for key, value in expected.items()}
                        assert observe() == before
                        changed = {'F': b'\xff\x00\xfe\x01',
                                   'V': b'\x00', 'B': b'\xff\x00\xff'}
                        mutate('update', {
                            'selector': {'identity_token': row[
                                'identity_token']},
                            'changes': {key: normalize_value(value)
                                        for key, value in changed.items()}})
                        page = provider.read_visual_admin_rows(request)
                        assert {key: page['rows'][-1]['values'][key]
                                for key in changed} == {
                                    key: normalize_value(value)
                                    for key, value in changed.items()}
                        assert observe() == before
                        deleted = index == 1
                        if deleted:
                            mutate('delete', {
                                'selector': {'identity_token': page[
                                    'rows'][-1]['identity_token']},
                                'confirmation': 'provider-row-delete'})
                            assert observe() == before
                        provider.control_transaction({
                            'session_id': sid, 'action': action})
                        assert observe() == (before + [tuple(changed.values())]
                                             if action == 'commit' and
                                             not deleted else before)
                        checks.append({'case': case, 'passed': True,
                                       'delete_verified': deleted})
                    except Exception as exc:
                        checks.append({'case': case, 'passed': False})
                        result['failures'].append({
                            'case': case, 'message': str(exc).replace(
                                password, '<redacted>')})
                    finally:
                        provider.close_session({'session_id': sid})
    finally:
        client.close_session(admin)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; preserve previous evidence')
    result = base.run(extra_checks=verify)
    checks = result.get('binary_grid_checks', [])
    result['complete'] = (result['complete'] and len(checks) == 12 and
                          all(check['passed'] for check in checks))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
