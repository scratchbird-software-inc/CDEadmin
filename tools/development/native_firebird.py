"""Native embedded Firebird checks in an owned disposable database."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
import config  # Initialize the inherited import boundary before providers.


def run(evidence):
    import firebird.driver as native
    from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
    from pgadmin.cdeadmin.providers.firebird.provider import (
        _create_client, _database_create_arguments, _configure_client_library,
        _client_library_identity)
    _configure_client_library(native)
    evidence.mkdir(parents=True, exist_ok=False)
    route = {'attachment_mode': 'embedded', 'filesystem_root': str(evidence),
             'database': str(evidence / 'owned.fdb'), 'user': 'SYSDBA',
             'charset': 'UTF8'}
    client = _create_client(SimpleNamespace(require=lambda *_: True,
                            acquire_secret=lambda *_: None),
                            attachment_mode='embedded', profile=embedded.PROFILE,
                            administration=embedded.ADMINISTRATION)
    connection = None
    checks = []
    cleanup = False
    try:
        arguments = _database_create_arguments(route, route['database'],
                                               {'sql_dialect': 3}, native)
        connection = client.config.database_creator(**arguments)
        identity = _client_library_identity(native)
        assert identity['client_library_version'] == '5.0.4', identity
        with connection.cursor() as cursor:
            cursor.execute("SELECT RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION') FROM RDB$DATABASE")
            assert cursor.fetchone() == ('5.0.4',)
        connection.rollback()
        for name in ('editor', 'row_sql', 'templates', 'profiler'):
            result = {'check': name, 'status': 'failed'}
            try:
                import importlib
                module = importlib.import_module('tools.firebird_' + name + '_native')
                proof = module.qualify(connection, client, route) if name in ('editor', 'profiler') else module.qualify(connection)
                assert proof['passed'], proof
                result['status'] = 'passed'
            except Exception as error:
                result['error_type'] = type(error).__name__
                result['error'] = str(error)
            checks.append(result)
    finally:
        if connection is not None:
            if connection.main_transaction.is_active():
                connection.rollback()
            connection.drop_database()
            cleanup = not Path(route['database']).exists()
    receipt = {'complete': bool(checks) and all(c['status'] == 'passed' for c in checks)
               and cleanup, 'checks': checks, 'owned_database_removed': cleanup,
               'scope': 'native embedded editor, row SQL, templates and profiling'}
    (evidence / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['complete'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.evidence.resolve()))
