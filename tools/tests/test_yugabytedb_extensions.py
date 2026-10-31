"""YugabyteDB YSQL extensions."""
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

TARGET = {'resource_id': 'extension:hstore', 'display_name': 'hstore',
          'display_path': ['hstore'], 'native': {
              'version': '1.5', 'schema': 'ext', 'relocatable': True,
              'comment': None, 'update_versions': ['1.5-yb-1.0',
                                                   '1.8-yb-1.0']}}


def plan(operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': 'extension', 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1', 'database': 'd'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_create():
    assert plan('create', {'name': 'hstore', 'schema': 'ext',
                           'version': '1.8-yb-1.0', 'cascade': True,
                           'comment': 'c'}) == [
        'CREATE EXTENSION "hstore" WITH SCHEMA "ext" VERSION \'1.8-yb-1.0\' '
        'CASCADE',
        'COMMENT ON EXTENSION "hstore" IS \'c\'']


def test_alter():
    assert plan('alter', {'version': '1.8-yb-1.0', 'schema': 'public',
                          'comment': 'x'}, TARGET) == [
        'ALTER EXTENSION "hstore" UPDATE TO \'1.8-yb-1.0\'',
        'ALTER EXTENSION "hstore" SET SCHEMA "public"',
        'COMMENT ON EXTENSION "hstore" IS \'x\'']


@pytest.mark.parametrize('draft, target, reason', [
    ({'version': '1.4'}, TARGET, 'no update path'),
    ({'schema': 'public'}, {**TARGET, 'native': {
        **TARGET['native'], 'relocatable': False}}, 'not relocatable'),
    ({'version': "1'; x"}, {**TARGET, 'native': {
        **TARGET['native'], 'update_versions': None}}, 'version name'),
    ({'cascade': True}, TARGET, 'cannot change in place'),
    ({'schema': 'ext'}, TARGET, 'nothing to change'),
])
def test_refusals(draft, target, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan('alter', draft, target)
