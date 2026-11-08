"""A first start builds the SQLite configuration database in one transaction.

Without it SQLite commits every migration DDL statement on its own: 226 write
transactions and 904 syncs for the first build, 5.4 s at idle on a real disk
(performance review 2026-11-07). SQLite's file change counter (header bytes
24-27) counts committed write transactions, so it shows how the database was
built without depending on timing.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]

# create_app also stores a few rows after the build (desktop user, servers);
# a per-statement build commits more than 200 times.
MAXIMUM_FIRST_START_TRANSACTIONS = 10


def _start(directory, **environment):
    data = directory / 'data'
    for name in ('sessions', 'storage', 'azure'):
        (data / name).mkdir(parents=True, exist_ok=True)
    isolated = {
        'SERVER_MODE': False, 'TESTING': True, 'CONFIG_DATABASE_URI': '',
        'DATA_DIR': str(data), 'SQLITE_PATH': str(data / 'pgadmin4.db'),
        'CDEADMIN_OPERATION_STORE_PATH': str(data / 'operations.json'),
        'LOG_FILE': str(data / 'application.log'),
        'SESSION_DB_PATH': str(data / 'sessions'),
        'STORAGE_DIR': str(data / 'storage'),
        'AZURE_CREDENTIAL_CACHE_DIR': str(data / 'azure'),
        'KERBEROS_CCACHE_DIR': str(data / 'kerberos'),
    }
    (directory / 'config_local.py').write_text(''.join(
        f'{name} = {value!r}\n' for name, value in isolated.items()))
    script = ('import json, os\n'
              'import config\n'
              'owned = json.loads(os.environ["ISOLATED"])\n'
              'for name, value in owned.items():\n'
              '    setattr(config, name, value)\n'
              'import sys\n'
              'from pgadmin import create_app\n'
              'app = create_app()\n'
              'print(json.dumps({"migrate": "migrate" in app.extensions,\n'
              '                  "alembic": "alembic" in sys.modules}))\n')
    completed = subprocess.run(
        [sys.executable, '-c', script], cwd=directory, capture_output=True,
        text=True, timeout=300,
        env={**{name: value for name, value in os.environ.items()
                if name != 'FLASK_RUN_FROM_CLI'},
             **environment, 'ISOLATED': json.dumps(isolated),
             'PYTHONPATH': os.pathsep.join([str(directory),
                                            str(ROOT / 'web')])})
    assert completed.returncode == 0, completed.stderr[-2000:]
    return data / 'pgadmin4.db', json.loads(
        completed.stdout.strip().splitlines()[-1])


def test_first_start_builds_the_configuration_database_in_one_transaction(
        tmp_path):
    database, loaded = _start(tmp_path)
    assert loaded['migrate']
    header = database.read_bytes()[:100]
    changes = int.from_bytes(header[24:28], 'big')
    assert 1 <= changes <= MAXIMUM_FIRST_START_TRANSACTIONS, changes
    connection = sqlite3.connect(database)
    try:
        assert connection.execute('PRAGMA integrity_check').fetchone() == (
            'ok',)
        revision = connection.execute(
            'SELECT version_num FROM alembic_version').fetchall()
        assert len(revision) == 1
        tables = {name for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {'user', 'server', 'servergroup', 'version', 'keys'} <= tables
    finally:
        connection.close()


def test_migration_tooling_loads_only_when_a_migration_runs(tmp_path):
    # The first start migrated, so it registered Flask-Migrate (alembic).
    _database, first = _start(tmp_path)
    assert first == {'migrate': True, 'alembic': True}
    # A later start finds the schema current and does not load either.
    _database, later = _start(tmp_path)
    assert later == {'migrate': False, 'alembic': False}
    # Under the flask command line the `flask db` commands need it at once.
    _database, command_line = _start(tmp_path, FLASK_RUN_FROM_CLI='true')
    assert command_line['migrate'] is True
