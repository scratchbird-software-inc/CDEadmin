"""Configuration upgrades preserve aliases and refuse lossy downgrades."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[2]
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'web/migrations/versions' / (name + '_.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_upgrade_preserves_existing_rows_and_downgrade_never_coalesces_aliases():
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        connection.execute(sa.text('CREATE TABLE cde_endpoint (id VARCHAR(36) PRIMARY KEY)'))
        connection.execute(sa.text("INSERT INTO cde_endpoint VALUES ('endpoint')"))
        original = load('cde_endpoint_database_targets_v1')
        upgraded = load('cde_registration_aliases_v1')
        with patch.object(original, 'op', operations): original.upgrade()
        connection.execute(sa.text("INSERT INTO cde_endpoint_database_target (id,endpoint_id,display_name,database,configuration,active) VALUES ('original','endpoint','Original','same.fdb','{}',1)"))
        with patch.object(upgraded, 'op', operations): upgraded.upgrade()
        row = connection.execute(sa.text('SELECT * FROM cde_endpoint_database_target')).mappings().one()
        assert row['id'] == 'original' and row['active'] == 1
        assert row['registration_credentials'] == 0 and row['registration_password'] is None
        connection.execute(sa.text("INSERT INTO cde_endpoint_database_target (id,endpoint_id,display_name,database,configuration,active) VALUES ('alias','endpoint','Alias','same.fdb','{}',0)"))
        with patch.object(upgraded, 'op', operations), pytest.raises(RuntimeError, match='aliases'):
            upgraded.downgrade()
        assert connection.execute(sa.text('SELECT COUNT(*) FROM cde_endpoint_database_target')).scalar() == 2
        connection.execute(sa.text("DELETE FROM cde_endpoint_database_target WHERE id='alias'"))
        connection.execute(sa.text("UPDATE cde_endpoint_database_target SET registration_credentials=1, registration_password='ciphertext'"))
        with patch.object(upgraded, 'op', operations), pytest.raises(RuntimeError, match='credentials'):
            upgraded.downgrade()
        connection.execute(sa.text('UPDATE cde_endpoint_database_target SET registration_credentials=0,registration_password=NULL'))
        with patch.object(upgraded, 'op', operations): upgraded.downgrade()
        assert 'registration_password' not in {item['name'] for item in sa.inspect(connection).get_columns('cde_endpoint_database_target')}
        assert connection.execute(sa.text('SELECT id, active FROM cde_endpoint_database_target')).all() == [('original', 1)]
    engine.dispose()
