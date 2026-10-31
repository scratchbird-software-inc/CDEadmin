"""YugabyteDB YSQL databases."""
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

TARGET = {'resource_id': 'database:d', 'display_name': 'd',
          'display_path': ['d'], 'native': {
              'owner': 'o', 'connection_limit': -1,
              'allow_connections': True, 'comment': None,
              'settings': [{'name': 'work_mem', 'value': '8MB'}]}}


def compiled(operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': 'database', 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1', 'database': 'yugabyte'}})
    return planned['provider_payload']['compiled']


def test_create_runs_outside_a_transaction():
    result = compiled('create', {
        'name': 'd', 'owner': 'o', 'template': 'template0',
        'encoding': 'UTF8', 'locale_provider': 'icu', 'icu_locale': 'en-US',
        'collate': 'C', 'connection_limit': 5, 'colocation': True,
        'settings': [{'name': 'search_path', 'value': 'public, x'},
                     {'name': 'timezone', 'value': 'UTC'}]})
    assert [item['source'] for item in result['statements']] == [
        'CREATE DATABASE "d" OWNER "o" TEMPLATE "template0" ENCODING '
        "'UTF8' LOCALE_PROVIDER icu ICU_LOCALE 'en-US' LC_COLLATE 'C' "
        'CONNECTION LIMIT 5 COLOCATION = true',
        'ALTER DATABASE "d" SET search_path = public, x',
        'ALTER DATABASE "d" SET timezone = \'UTC\'']
    assert result['statements_outside_transaction'] is True


def test_alter():
    assert [item['source'] for item in compiled('alter', {
        'connection_limit': 3, 'allow_connections': False, 'comment': 'c',
        'settings': [], 'name': 'e'}, TARGET)['statements']] == [
        'ALTER DATABASE "d" CONNECTION LIMIT 3',
        'ALTER DATABASE "d" ALLOW_CONNECTIONS false',
        'COMMENT ON DATABASE "d" IS \'c\'',
        'ALTER DATABASE "d" RESET work_mem',
        'ALTER DATABASE "d" RENAME TO "e"']


@pytest.mark.parametrize('operation, draft, target, reason', [
    ('alter', {'is_template': True}, TARGET, 'cannot change in place'),
    ('alter', {'colocation': True}, TARGET, 'cannot change in place'),
    ('create', {'name': 'd', 'icu_locale': 'en-US'}, None, 'icu locale'),
    ('create', {'name': 'd', 'locale_provider': 'icu'}, None,
     'needs an ICU locale'),
    ('create', {'name': 'd', 'collate': "C'; x"}, None, 'locale name'),
    ('create', {'name': 'd', 'connection_limit': -2}, None, 'whole number'),
])
def test_refusals(operation, draft, target, reason):
    with pytest.raises(RelationalClientError, match=reason):
        compiled(operation, draft, target)
