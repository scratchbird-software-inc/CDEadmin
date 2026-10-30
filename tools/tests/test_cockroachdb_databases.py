"""CockroachDB database compilation and its catalog facts."""
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools' / 'tests'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.cockroachdb.provider import (  # noqa: E402
    ADMINISTRATION, _annotate_catalog,
)
from pgadmin.cdeadmin.providers.distributed_sql import resource  # noqa: E402
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402
from test_postgresql_wire_catalog import Connection, Cursor  # noqa: E402

TARGET = {'resource_id': 'database:d', 'display_name': 'd',
          'display_path': ['d'],
          'native': {'owner': 'root', 'comment': 'c', 'settings': [
              {'name': 'timezone', 'value': 'UTC'},
              {'name': 'statement_timeout', 'value': '10s'}]}}


def plan(operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': 'database', 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_create():
    assert plan('create', {'name': 'd', 'owner': 'o', 'encoding': 'UTF8',
                           'comment': 'x', 'settings': [
                               {'name': 'timezone', 'value': 'UTC'}]}) == [
        'CREATE DATABASE "d" ENCODING = \'UTF8\' OWNER = "o"',
        'COMMENT ON DATABASE "d" IS \'x\'',
        'ALTER DATABASE "d" SET timezone = \'UTC\'']


def test_alter_diffs_settings_and_renames_last():
    assert plan('alter', {'owner': 'o', 'comment': '', 'name': 'e',
                          'settings': [{'name': 'timezone',
                                        'value': 'America/Toronto'}]},
                TARGET) == [
        'ALTER DATABASE "d" OWNER TO "o"',
        'COMMENT ON DATABASE "d" IS NULL',
        'ALTER DATABASE "d" SET timezone = \'America/Toronto\'',
        'ALTER DATABASE "d" RESET statement_timeout',
        'ALTER DATABASE "d" RENAME TO "e"']


@pytest.mark.parametrize('operation, draft, reason', [
    ('create', {'name': 'd', 'encoding': 'LATIN1'}, 'are UTF8'),
    ('create', {'name': 'd', 'connection_limit': 5}, 'unknown database'),
    ('alter', {'settings': [{'name': 'Bad Name', 'value': 'x'}]},
     'variable name'),
    ('alter', {'owner': 'root'}, 'nothing to change'),
])
def test_refusals(operation, draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan(operation, draft, TARGET)


def test_catalog_flags_the_system_database_and_carries_facts():
    values = [resource('database', [], 'system', 'g'),
              resource('database', [], 'app', 'g')]
    cursor = Cursor({
        'pg_encoding_to_char': [('app', 'root', 'UTF8', 'c'),
                                ('system', 'node', 'UTF8', None)],
        'SHOW DATABASES': [('app', None, [], None)],
        'SHOW DEFAULT SESSION VARIABLES': [('timezone', 'UTC', 'app')],
    })
    rows = {item['display_name']: item['native']
            for item in _annotate_catalog(Connection(cursor), values)}
    assert rows['system']['system_object'] is True
    assert (rows['app']['owner'], rows['app']['comment'],
            rows['app']['settings']) == (
        'root', 'c', [{'name': 'timezone', 'value': 'UTC'}])
