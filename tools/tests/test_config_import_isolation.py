"""``import config`` loads the configuration, not the application.

Performance review 2026-11-07 (F6): config.py imported its platform helpers
from pgadmin.utils and its override loader from pgadmin.evaluate_config, so
every tool or test that only needed a configuration value imported the whole
pgadmin package (Flask, SQLAlchemy, every blueprint dependency) as well. The
helpers now live in web/platform_helpers.py and the loader in
web/config_overrides.py; pgadmin.utils re-exports the helpers.

A side effect, also checked here: pgadmin.model reads the configuration
database pool settings when it is imported. While config imported the
application, that happened before config_local had been applied, so an
override of those settings was ignored.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'web'


def _run(script, directory):
    completed = subprocess.run(
        [sys.executable, '-c', script], cwd=directory, capture_output=True,
        text=True, timeout=300,
        env={**{name: value for name, value in os.environ.items()
                if name not in ('FLASK_RUN_FROM_CLI',
                                'CONFIG_DISTRO_FILE_PATH')},
             'PYTHONPATH': str(WEB)})
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_importing_config_does_not_import_the_application(tmp_path):
    loaded = _run(
        'import json, sys\n'
        'import config\n'
        'print(json.dumps(sorted(name for name in sys.modules\n'
        '                        if name.split(".")[0] in\n'
        '                        ("pgadmin", "flask", "sqlalchemy"))))\n',
        tmp_path)
    assert loaded == []


def test_pgadmin_utils_still_provides_the_same_helpers(tmp_path):
    same = _run(
        'import json\n'
        'import config, platform_helpers\n'
        'import pgadmin.utils as utils\n'
        'helpers = platform_helpers\n'
        'print(json.dumps([getattr(utils, name) is getattr(helpers, name)\n'
        '                  for name in ("IS_WIN", "env", "fs_short_path")]\n'
        '                 + [config.env is platform_helpers.env]))\n',
        tmp_path)
    assert same == [True, True, True, True]


def test_the_model_reads_the_final_pool_settings(tmp_path):
    # Applied the way config_local values are: config_overrides applies
    # CONFIG_DISTRO_FILE_PATH before config_local, so a value set there
    # reaches config unless the developer's own config_local sets it too.
    distro = tmp_path / 'config_distro.py'
    distro.write_text('CONFIG_DATABASE_CONNECTION_POOL_SIZE = 7\n'
                      'CONFIG_DATABASE_CONNECTION_MAX_OVERFLOW = 11\n')
    completed = subprocess.run(
        [sys.executable, '-c',
         'import json\n'
         'import config\n'
         'from pgadmin.model import db\n'
         'print(json.dumps([config.CONFIG_DATABASE_CONNECTION_POOL_SIZE,\n'
         '                  config.CONFIG_DATABASE_CONNECTION_MAX_OVERFLOW,\n'
         '                  db._engine_options.get("pool_size"),\n'
         '                  db._engine_options.get("max_overflow")]))\n'],
        cwd=tmp_path, capture_output=True, text=True, timeout=300,
        env={**{name: value for name, value in os.environ.items()
                if name != 'FLASK_RUN_FROM_CLI'},
             'CONFIG_DISTRO_FILE_PATH': str(distro), 'PYTHONPATH': str(WEB)})
    assert completed.returncode == 0, completed.stderr[-2000:]
    configured_size, configured_overflow, size, overflow = json.loads(
        completed.stdout.strip().splitlines()[-1])
    assert (size, overflow) == (configured_size, configured_overflow)
