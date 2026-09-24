#!/usr/bin/env python3
"""Qualify scalar grid values through an owned native Firebird fixture."""
import argparse
from decimal import Decimal
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
    checks = result['scalar_grid_checks'] = []
    admin = client.open_session({'route': route})

    def sql(handle, source):
        with handle.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []

    def observe():
        handle = client.open_session({'route': route})
        try:
            return sql(handle, 'SELECT H, D, T, B FROM GS_BASE ORDER BY ID')
        finally:
            client.close_session(handle)

    try:
        sql(admin, 'CREATE TABLE GS_BASE (ID INTEGER GENERATED ALWAYS AS '
            'IDENTITY PRIMARY KEY, H INT128, D NUMERIC(38, 18), '
            'T VARCHAR(100), B BOOLEAN)')
        client.control_transaction(admin, 'commit')
        sql(admin, 'CREATE VIEW GS_VIEW AS SELECT * FROM GS_BASE')
        client.control_transaction(admin, 'commit')
        for kind, name in (('table', 'GS_BASE'), ('view', 'GS_VIEW')):
            for action in ('commit', 'rollback'):
                handle = client.open_session({'route': route})
                case = kind + ':' + action
                target = {'resource_kind': kind, 'resource_id': kind + name,
                          'display_path': [name], 'display_name': name}
                request = {'_provider_route': route, 'target_resource': target,
                           'session_id': 'scalars', 'resource_kind': kind}
                values = {'H': '170141183460469231731687303715884105727',
                          'D': '12345678901234567890.123456789012345678',
                          'T': 'null', 'B': False}
                try:
                    before = observe()
                    page = base.ADMINISTRATION.read_rows(
                        client, request, connection=handle)
                    hints = {c['name']: c.get('input_kind')
                             for c in page['columns']}
                    assert hints == {'ID': 'integer', 'H': 'integer',
                                     'D': 'decimal', 'T': 'text',
                                     'B': 'boolean'}, hints
                    plan = base.ADMINISTRATION.plan({
                        **request, 'operation_id': 'insert', 'draft': {
                            'values': values, 'options': {
                                'identity_token': page[
                                    'insert_identity_token']}}})
                    base.ADMINISTRATION.apply(client, plan, connection=handle)
                    page = base.ADMINISTRATION.read_rows(
                        client, request, connection=handle)
                    row = page['rows'][-1]
                    assert {k: row['values'][k] for k in values} == values
                    assert observe() == before
                    # UPDATE uses native original values in its concurrency
                    # predicate, not the normalized browser representations.
                    changes = {'H': '-170141183460469231731687303715884105728',
                               'D': '-0.123456789012345678',
                               'T': '0012', 'B': True}
                    plan = base.ADMINISTRATION.plan({
                        **request, 'operation_id': 'update', 'draft': {
                            'selector': {'identity_token': row[
                                'identity_token']}, 'changes': changes}})
                    base.ADMINISTRATION.apply(client, plan, connection=handle)
                    page = base.ADMINISTRATION.read_rows(
                        client, request, connection=handle)
                    assert {k: page['rows'][-1]['values'][k]
                            for k in changes} == changes
                    assert observe() == before
                    client.control_transaction(handle, action)
                    assert observe() == (before + [(
                        int(changes['H']), Decimal(changes['D']),
                        changes['T'], changes['B'])]
                        if action == 'commit' else before)
                    checks.append({'case': case, 'passed': True})
                except Exception as exc:
                    checks.append({'case': case, 'passed': False})
                    result['failures'].append({
                        'case': case, 'message': str(exc).replace(
                            password, '<redacted>')})
                finally:
                    client.close_session(handle)
    finally:
        client.close_session(admin)
    verify_composite(client, route, password, result)
    verify_table_permissions(client, route, password, result)


def verify_table_permissions(client, route, password, result):
    from pgadmin.cdeadmin.providers.firebird.character_metadata import literal
    checks = result['table_permission_checks'] = []
    secret = secrets.token_urlsafe(24)
    reader = base._create_client(SimpleNamespace(
        acquire_secret=lambda *_: base.SecretLease(secret)))
    admin = client.open_session({'route': route})

    def sql(handle, source):
        with handle.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []

    def request(name, selected_route, sid):
        return {'_provider_route': selected_route, 'session_id': sid,
                'resource_kind': 'table', 'target_resource': {
                    'resource_kind': 'table', 'display_path': [name]}}

    try:
        for source in (
                'CREATE TABLE GP_BASE (ID INTEGER GENERATED ALWAYS AS '
                'IDENTITY PRIMARY KEY, V INTEGER DEFAULT 7, '
                'C COMPUTED BY (V * 2))',
                'CREATE TABLE GP_KEYLESS (V INTEGER DEFAULT 7)',
                'CREATE USER GP_READER PASSWORD ' + literal(secret),
                'GRANT SELECT ON GP_BASE TO USER GP_READER'):
            sql(admin, source)
            client.control_transaction(admin, 'commit')
        for phase, command, expected_ops in (
                ('select', None, []),
                ('update', 'GRANT UPDATE(V) ON GP_BASE TO USER GP_READER',
                 ['update']),
                ('insert', 'GRANT INSERT ON GP_BASE TO USER GP_READER',
                 ['update', 'insert']),
                ('delete', 'GRANT DELETE ON GP_BASE TO USER GP_READER',
                 ['update', 'delete', 'insert']),
                ('revoke-update', 'REVOKE UPDATE(V) ON GP_BASE '
                 'FROM USER GP_READER', ['delete', 'insert']),
                ('revoke-insert', 'REVOKE INSERT ON GP_BASE '
                 'FROM USER GP_READER', ['delete']),
                ('revoke-delete', 'REVOKE DELETE ON GP_BASE '
                 'FROM USER GP_READER', [])):
            if command:
                sql(admin, command)
                client.control_transaction(admin, 'commit')
            user_route = {**route, 'user': 'GP_READER'}
            handle = reader.open_session({'route': user_route})
            try:
                page = base.ADMINISTRATION.read_rows(
                    reader, request('GP_BASE', user_route, phase),
                    connection=handle)
                assert page['row_operations'] == expected_ops, page
                columns = {c['name']: c for c in page['columns']}
                assert not columns['ID']['insertable']
                assert not columns['C']['insertable']
                assert not columns['C']['editable']
                assert columns['V']['editable'] == ('update' in expected_ops)
                assert columns['V']['insertable'] == ('insert' in expected_ops)
                checks.append({'case': phase, 'passed': True})
            finally:
                reader.close_session(handle)
        for name in ('GP_BASE', 'GP_KEYLESS'):
            for action in ('commit', 'rollback'):
                handle = client.open_session({'route': route})
                query = 'SELECT V FROM ' + name
                try:
                    before = sql(admin, query)
                    client.control_transaction(admin, 'rollback')
                    r = request(name, route, name + action)
                    page = base.ADMINISTRATION.read_rows(
                        client, r, connection=handle)
                    assert page['insert_default_values']
                    assert 'insert' in page['row_operations']
                    if name == 'GP_KEYLESS':
                        assert not page['editable']
                        assert page['row_operations'] == ['insert']
                    plan = base.ADMINISTRATION.plan({
                        **r, 'operation_id': 'insert',
                        'draft': {'values': {}}})
                    receipt = base.ADMINISTRATION.apply(
                        client, plan, connection=handle)
                    assert receipt['staged_in_provider_session']
                    assert sql(handle, query) == before + [(7,)]
                    assert sql(admin, query) == before
                    client.control_transaction(admin, 'rollback')
                    client.control_transaction(handle, action)
                    assert sql(admin, query) == (
                        before + [(7,)] if action == 'commit' else before)
                    client.control_transaction(admin, 'rollback')
                    checks.append({'case': name + ':' + action,
                                   'passed': True})
                finally:
                    client.close_session(handle)
    except Exception as exc:
        message = str(exc).replace(secret, '<redacted>').replace(
            password, '<redacted>')
        result['failures'].append({'case': 'table-permissions',
                                   'message': message})
    finally:
        client.close_session(admin)
    verify_provider_defaults(client, route, result)


def verify_provider_defaults(client, route, result):
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
    provider = FirebirdProvider(context, SimpleNamespace(
        require=lambda *_args, **_kwargs: None), client)
    checks = result['provider_default_checks'] = []
    for name in ('GP_BASE', 'GP_KEYLESS'):
        sid = provider.open_session({'route': route})['session_id']
        observer = client.open_session({'route': route})
        try:
            def count():
                with observer.cursor() as cursor:
                    cursor.execute('SELECT COUNT(*) FROM ' + name)
                    value = cursor.fetchone()[0]
                client.control_transaction(observer, 'rollback')
                return value
            before = count()
            request = {'_provider_route': route, 'session_id': sid,
                       'resource_kind': 'table', 'operation_id': 'insert',
                       'target_resource': {'resource_kind': 'table',
                                           'display_path': [name]},
                       'draft': {'values': {}}}
            page = provider.read_visual_admin_rows(request)
            assert page['operation_authority'] == 'firebird-native-preparation'
            assert page['insert_default_values']
            assert any(col.get('input_kind') == 'integer'
                       for col in page['columns'])
            validation = provider.validate_visual_admin(request)
            assert validation['valid'], validation
            plan = provider.plan_visual_admin(request)
            assert plan['state'] == 'ready', plan
            receipt = provider.apply_visual_admin({
                'session_id': sid, 'plan_id': plan['plan_id'],
                'plan_digest': plan['plan_digest']})
            assert receipt['provider_result']['staged_in_provider_session']
            assert count() == before
        finally:
            provider.close_session({'session_id': sid})
            client.close_session(observer)
        observer = client.open_session({'route': route})
        try:
            assert count() == before
            checks.append({'case': name, 'passed': True})
        finally:
            client.close_session(observer)


def verify_composite(client, route, password, result):
    from pgadmin.cdeadmin.providers.firebird.character_metadata import (
        identifier,
    )
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    checks = result['composite_grid_checks'] = []
    table, view = 'Grid " Keys', 'Grid " View'
    first, second, value = 'first " key', '次', 'value'
    first_alias, second_alias = 'first alias', 'second alias'
    q = identifier
    query = (f'SELECT {q(first)}, {q(second)}, {q(value)} FROM {q(table)} '
             f'ORDER BY {q(first)}, {q(second)}')

    def sql(handle, source, params=()):
        with handle.cursor() as cursor:
            cursor.execute(source, params)
            return cursor.fetchall() if cursor.description else []

    def observe():
        handle = client.open_session({'route': route})
        try:
            return sql(handle, query)
        finally:
            client.close_session(handle)

    admin = client.open_session({'route': route})
    try:
        sql(admin, f'CREATE TABLE {q(table)} ({q(first)} INTEGER, '
            f'{q(second)} VARCHAR(10), {q(value)} INTEGER, '
            f'PRIMARY KEY ({q(second)}, {q(first)}))')
        client.control_transaction(admin, 'commit')
        sql(admin, f'CREATE VIEW {q(view)} AS SELECT '
            f'{q(first)} AS {q(first_alias)}, '
            f'{q(second)} AS {q(second_alias)}, '
            f'{q(value)} FROM {q(table)}')
        client.control_transaction(admin, 'commit')
        for kind, name, first_name, second_name in (
                ('table', table, first, second),
                ('view', view, first_alias, second_alias)):
            for operation in ('update', 'delete'):
                for action in ('commit', 'rollback'):
                    case = f'{kind}:{operation}:{action}'
                    handle = client.open_session({'route': route})
                    try:
                        sql(admin, f'DELETE FROM {q(table)}')
                        for values in ((1, 'a', None), (1, 'b', 12),
                                       (2, 'a', 21)):
                            sql(admin, f'INSERT INTO {q(table)} VALUES '
                                '(?, ?, ?)', values)
                        client.control_transaction(admin, 'commit')
                        before = observe()
                        request = {'_provider_route': route,
                                   'session_id': 'composite',
                                   'resource_kind': kind,
                                   'target_resource': {'resource_kind': kind,
                                                       'display_path': [name]}}
                        page = base.ADMINISTRATION.read_rows(
                            client, request, connection=handle)
                        row = next(row for row in page['rows']
                                   if row['values'][first_name] == 1 and
                                   row['values'][second_name] == 'a')
                        token = row['identity_token']
                        identity = base.ADMINISTRATION._row_identities[token]
                        assert identity.key_columns == (
                            second_name, first_name)
                        task = {**request, 'operation_id': operation,
                                'draft': {'selector': {
                                    'identity_token': token},
                                          'changes': {value: '99'}}}
                        plan = base.ADMINISTRATION.plan(task)
                        base.ADMINISTRATION.apply(client, plan,
                                                  connection=handle)
                        pending = ([(1, 'a', 99)] + before[1:]
                                   if operation == 'update' else before[1:])
                        assert sql(handle, query) == pending
                        assert observe() == before
                        try:
                            base.ADMINISTRATION.plan(task)
                        except RelationalClientError:
                            pass
                        else:
                            raise AssertionError('row token replay admitted')
                        client.control_transaction(handle, action)
                        assert observe() == (pending if action == 'commit'
                                             else before)
                        checks.append({'case': case, 'passed': True})
                    except Exception as exc:
                        checks.append({'case': case, 'passed': False})
                        result['failures'].append({
                            'case': case, 'message': str(exc).replace(
                                password, '<redacted>')})
                    finally:
                        client.close_session(handle)
    finally:
        client.close_session(admin)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite evidence')
    result = base.run(extra_checks=verify)
    checks = result.get('scalar_grid_checks', [])
    composite = result.get('composite_grid_checks', [])
    permissions = result.get('table_permission_checks', [])
    defaults = result.get('provider_default_checks', [])
    result['complete'] = (result['complete'] and len(checks) == 4 and
                          all(check['passed'] for check in checks) and
                          len(composite) == 8 and
                          all(check['passed'] for check in composite) and
                          len(permissions) == 11 and
                          all(check['passed'] for check in permissions) and
                          len(defaults) == 2 and
                          all(check['passed'] for check in defaults))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
