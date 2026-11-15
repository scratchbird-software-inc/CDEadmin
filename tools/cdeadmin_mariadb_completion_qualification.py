"""Qualify nonintrusive MariaDB completion on an owned 12.2.2 fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work = args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root), str(root / 'web'), str(root / 'tools')]
    import config  # noqa: F401
    from tools.mariadb_qualification_support import server, _root_connection
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client, MARIADB_PROFILE
    from pgadmin.cdeadmin.providers.native_editor import NativeEditorProvider

    paths = ['tools/cdeadmin_mariadb_completion_qualification.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_completion.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_installed.py',
        'web/pgadmin/cdeadmin/providers/native_editor.py']
    proof = {'complete': False, 'checks': [], 'history_testing': 'not run',
        'scope': 'Owned MariaDB12.2.2 production NativeEditorProvider completion; '
                 'independent diagnostics, pending work and savepoint checks. No authenticated HTTP claim.',
        'source_sha256': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}}
    try:
        with server(work / 'mariadb-completion-fixture') as (route, _name, _fixture):
            observer = _root_connection('mariadb', route['port'])
            observer.autocommit = True
            client = source = None
            try:
                cursor = observer.cursor()
                cursor.execute('CREATE DATABASE owned_completion')
                cursor.execute('CREATE TABLE owned_completion.pending_work(id INT) ENGINE=InnoDB')
                cursor.close()
                route, permissions = provider_access({**route, 'database': 'owned_completion'})
                client = _create_client(MARIADB_PROFILE, permissions,
                    SimpleNamespace(pool_namespace='owned-completion'))
                source = client.open_session({'route': route})
                source.autocommit = False
                cursor = source.cursor()
                cursor.execute('INSERT INTO pending_work VALUES (1)')
                cursor.execute('SAVEPOINT owned_before_completion')
                provider = SimpleNamespace(client=client, profile=MARIADB_PROFILE,
                    _editor_session=lambda request: source)
                for kind in ['warning', 'error', 'warning-again']:
                    if kind == 'error':
                        try:
                            cursor.execute('SELECT absent_owned_column FROM pending_work')
                        except Exception as error:
                            assert getattr(error, 'errno', None) == 1054
                        else:
                            raise AssertionError('Native column error was not raised')
                    else:
                        cursor.execute('SELECT 1/0')
                        assert cursor.fetchone() == (None,)
                    cursor.execute('SHOW WARNINGS')
                    before = cursor.fetchall()
                    assert before and before[0][1] == (1054 if kind == 'error' else 1365)
                    result = NativeEditorProvider.complete(provider, {})['editor_context']
                    cursor.execute('SHOW WARNINGS')
                    assert cursor.fetchall() == before
                    assert result['original_session_commands_sent'] == 0
                    assert result['original_diagnostics_preserved'] and not result['complete']
                    assert 'sql_mode' not in result['context']
                    assert any(row['display_name'] == 'pending_work' for row in result['resources'])
                    check = observer.cursor()
                    check.execute('SELECT COUNT(*) FROM owned_completion.pending_work')
                    assert check.fetchone() == (0,)
                    check.close()
                    cursor.execute('ROLLBACK TO SAVEPOINT owned_before_completion')
                    cursor.execute('SELECT COUNT(*) FROM pending_work')
                    assert cursor.fetchone() == (1,)
                    proof['checks'].append({'diagnostic_kind': kind,
                        'native_diagnostic_code': before[0][1],
                        'diagnostics_unchanged': True, 'savepoint_preserved': True,
                        'pending_work_uncommitted_and_preserved': True,
                        'committed_catalog_observed': True, 'scope_reported_incomplete': True})
                cursor.close()
                client.close_session(source)
                source = None
            finally:
                if client is not None:
                    client.close()
                observer.close()
        proof['fixture_cleanup'] = json.loads((work / 'mariadb-completion-fixture/fixture.json').read_text())
        assert proof['fixture_cleanup']['owned_server_stopped']
        proof['complete'] = True
    finally:
        (work / 'mariadb-completion-native.json').write_text(json.dumps(proof, indent=2) + '\n')
    print('MariaDB native completion passed', len(proof['checks']))


if __name__ == '__main__':
    main()
