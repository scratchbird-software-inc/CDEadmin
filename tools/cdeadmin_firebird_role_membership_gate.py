"""Qualify Firebird role membership through the native administration path."""

import argparse
import json
import warnings
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_firebird_local_fixture import run_local, _route_arguments
from pgadmin.cdeadmin.providers.firebird.provider import (
    ADMINISTRATION, _create_client,
)
from pgadmin.cdeadmin.providers.firebird.character_metadata import identifier
from pgadmin.cdeadmin.providers.firebird.error_diagnostics import status_codes
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def qualify(runtime_root, evidence_root):
    observations = []
    tasks = {}

    def check(native, connection, route, accounts, evidence, root):
        client = _create_client(SimpleNamespace(acquire_secret=None))
        role, member_role = 'Membership:ü"', 'Member:ü"'
        user, password = accounts['Srp'][0]

        def sql(source, parameters=(), handle=None):
            with (handle or connection).cursor() as cursor:
                cursor.execute(source, parameters)
                return cursor.fetchall() if cursor.description else []

        def state(member, kind, handle=None):
            return sql(
                'SELECT RDB$GRANT_OPTION, RDB$FIELD_NAME FROM '
                'RDB$USER_PRIVILEGES WHERE RDB$RELATION_NAME = ? '
                "AND RDB$PRIVILEGE = 'M' AND RDB$USER = ? "
                'AND RDB$USER_TYPE = ? AND RDB$OBJECT_TYPE = 13',
                (role, member, 8 if kind == 'USER' else 13), handle)

        def apply(operation, member, kind, handle=None, **options):
            draft = {'member': member, 'member_kind': kind, **options}
            if operation == 'revoke':
                draft['confirmation'] = role
            request = {
                '_provider_route': route, 'resource_kind': 'role',
                'operation_id': operation,
                'target_resource': {'resource_kind': 'role',
                                    'display_name': role}, 'draft': draft,
            }
            assert ADMINISTRATION.validate(request) == {'errors': []}
            plan = ADMINISTRATION.plan(request)
            receipt = ADMINISTRATION.apply(
                client, plan, connection=handle or connection)
            assert receipt['staged_in_provider_session'] is True
            tasks['visual_admin.role.' + operation] = {
                'live_execution': 'passed', 'statements': [
                    item['source'] for item in
                    plan['command_preview']['statements']],
            }

        try:
            sql('CREATE ROLE ' + identifier(role))
            sql('CREATE ROLE ' + identifier(member_role))
            connection.commit()
            for kind, member in (('USER', user), ('ROLE', member_role)):
                defaults = (False, True) if kind == 'USER' else (False,)
                for default in defaults:
                    for admin in (False, True):
                        options = {'default_role': default,
                                   'admin_option': admin}
                        apply('grant', member, kind, **options)
                        assert len(state(member, kind)) == 1
                        connection.rollback()
                        assert state(member, kind) == []
                        connection.commit()
                        apply('grant', member, kind, **options)
                        connection.commit()
                        current = state(member, kind)
                        assert len(current) == 1
                        assert current[0][0] == (2 if admin else 0)
                        assert bool(current[0][1]) is default
                        connection.commit()
                        apply('revoke', member, kind)
                        assert state(member, kind) == []
                        connection.rollback()
                        assert len(state(member, kind)) == 1
                        connection.commit()
                        apply('revoke', member, kind)
                        connection.commit()
                        assert state(member, kind) == []
                        connection.commit()
                        observations.append({
                            'member_kind': kind, 'default_role': default,
                            'admin_option': admin,
                            'grant_and_revoke_commit_rollback_verified': True,
                        })

            apply('grant', user, 'USER', default_role=True, admin_option=True)
            connection.commit()
            apply('revoke', user, 'USER', admin_option_only=True)
            connection.commit()
            current = state(user, 'USER')
            assert len(current) == 1 and current[0][0] == 0
            assert bool(current[0][1]) is True
            connection.commit()
            apply('revoke', user, 'USER', default_role=True)
            connection.commit()
            current = state(user, 'USER')
            assert len(current) == 1 and not current[0][1]
            connection.commit()
            apply('revoke', user, 'USER')
            connection.commit()
            assert state(user, 'USER') == []
            connection.commit()
            observations.append({'partial_revokes_preserve_membership': True})

            restricted = native.connect(password=password, **_route_arguments(
                {**route, 'user': user}, native))
            try:
                try:
                    apply('grant', member_role, 'ROLE', restricted)
                except RelationalClientError as error:
                    codes = list(status_codes(error))
                    assert codes, 'Native privilege denial was not retained'
                else:
                    raise AssertionError('Unprivileged membership grant')
                restricted.rollback()
                observations.append({
                    'operation': 'grant', 'permission_denied': True,
                    'native_status_codes': codes,
                })
                apply('grant', member_role, 'ROLE')
                connection.commit()
                with warnings.catch_warnings(record=True) as diagnostics:
                    warnings.simplefilter('always')
                    try:
                        apply('revoke', member_role, 'ROLE', restricted)
                    except RelationalClientError as error:
                        codes = list(status_codes(error))
                        assert codes, 'Native privilege denial was not retained'
                        restricted.rollback()
                    else:
                        # Firebird may return a warning for grants owned by a
                        # different grantor. Verify native state after commit.
                        assert any(isinstance(item.message, native.FirebirdWarning)
                                   for item in diagnostics), (
                                       'Missing native revoke diagnostic')
                        restricted.commit()
                assert len(state(member_role, 'ROLE')) == 1
                connection.commit()
                observations.append({
                    'operation': 'revoke', 'unauthorized_change_prevented': True,
                    'native_warning_count': len(diagnostics),
                })
            finally:
                restricted.close()
            apply('revoke', member_role, 'ROLE')
            connection.commit()
            assert state(member_role, 'ROLE') == []
            connection.commit()
        finally:
            client.close()

    result = run_local(runtime_root, evidence_root, check)
    result['schema'] = 'cdeadmin.firebird-role-membership-proof.v1'
    result['observations'] = observations
    result['task_evidence'] = tasks if result['complete'] else {}
    (evidence_root / 'summary.json').write_text(
        json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--evidence-root', required=True, type=Path)
    options = parser.parse_args()
    result = qualify(options.runtime_root.resolve(), options.evidence_root)
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
