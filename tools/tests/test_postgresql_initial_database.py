"""Initial database selection must not guess or mutate endpoint state."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

PATH = (Path(__file__).resolve().parents[2] / 'web/pgadmin/cdeadmin'
        '/providers/postgresql/connection_target.py')
spec = importlib.util.spec_from_file_location('connection_target', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('maintenance,profile,targets,expected', [
    ('explicit', 'postgresql-native', [('child', True)], 'explicit'),
    (None, 'postgresql-native', [('demo', True)], 'demo'),
    ('', 'postgresql-native', [('demo', True)], 'demo'),
    (None, 'postgresql-native', [('demo', False)], None),
    (None, 'postgresql-native', [('a', True), ('b', True)], None),
    (None, 'postgresql-native', [('a', True), ('b', False)], 'a'),
    (None, 'postgresql-native', [], None),
    (None, 'firebird-native', [('demo', True)], None),
    (None, None, [], None),
])
def test_initial_database(maintenance, profile, targets, expected):
    server = NS(maintenance_db=maintenance, endpoint_profile=(NS(
        profile_id=profile, database_targets=[
            NS(database=name, active=active) for name, active in targets
        ]) if profile else None))
    assert module.initial_database(server) == expected
    assert server.maintenance_db == maintenance
