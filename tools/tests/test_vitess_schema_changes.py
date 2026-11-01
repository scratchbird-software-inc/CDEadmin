"""Vitess schema changes confirmed on every shard's primary (2026-11-01)."""
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

from pgadmin.cdeadmin.providers.vitess import control_plane  # noqa: E402
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

TABLE = {'resource_kind': 'table', 'display_name': 't',
         'display_path': ['ks', 't']}
INDEX = {'resource_kind': 'index', 'display_name': 'k',
         'display_path': ['ks', 't', 'k']}
SCHEMA = ('CREATE TABLE `t` (\n  `id` bigint NOT NULL,\n  `v` int,\n'
          '  PRIMARY KEY (`id`),\n  KEY `{index}` (`v`){hidden}\n'
          ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4{comment}')


def schema(index='k', hidden='', comment=''):
    return SCHEMA.format(index=index, hidden=hidden, comment=comment)


def action(kind, operation, draft, target):
    return control_plane.compile_action({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': target})['provider_action']['arguments']


def test_changes_run_through_apply_schema_on_the_keyspace():
    assert action('table', 'set_options', {'comment': "it's a\\b"},
                  TABLE) == [
        'ApplySchema', '--sql',
        "ALTER TABLE `t` COMMENT = 'it''s a\\\\b'", 'ks']
    assert action('index', 'rename', {'new_name': 'k 2'}, INDEX) == [
        'ApplySchema', '--sql', 'ALTER TABLE `t` RENAME INDEX `k` TO `k 2`',
        'ks']
    assert action('index', 'visibility', {'visibility': 'INVISIBLE'},
                  INDEX) == [
        'ApplySchema', '--sql', 'ALTER TABLE `t` ALTER INDEX `k` INVISIBLE',
        'ks']
    for draft in ({'comment': 'line\nbreak'}, {'comment': None}):
        with pytest.raises(RelationalClientError, match='comment'):
            action('table', 'set_options', draft, TABLE)
    with pytest.raises(RelationalClientError, match='index name'):
        action('index', 'rename', {'new_name': 'a`b'}, INDEX)


def plan(kind, operation, draft, target):
    return {'resource_kind': kind, 'operation_id': operation,
            'draft': draft, 'target_resource': target}


def shards(*schemas):
    return {f's{number}': {'tablet': f'c-{number}', 'schema': value}
            for number, value in enumerate(schemas)}


def test_confirmed_only_when_every_shard_shows_the_change():
    comment = plan('table', 'set_options', {'comment': "it's"}, TABLE)
    done = schema(comment=" COMMENT='it''s'")
    assert control_plane._schema_applied(comment, shards(done, done))
    assert not control_plane._schema_applied(comment, shards(done, schema()))
    assert not control_plane._schema_applied(comment, {
        **shards(done), 'x': {'error': '0 primary tablets'}})
    assert not control_plane._schema_applied(comment, {})
    rename = plan('index', 'rename', {'new_name': 'k2'}, INDEX)
    assert control_plane._schema_applied(
        rename, shards(schema('k2'), schema('k2')))
    assert not control_plane._schema_applied(
        rename, shards(schema('k2'), schema('k')))
    hide = plan('index', 'visibility', {'visibility': 'INVISIBLE'}, INDEX)
    hidden = schema(hidden=' /*!80000 INVISIBLE */')
    assert control_plane._schema_applied(hide, shards(hidden, hidden))
    assert not control_plane._schema_applied(hide, shards(hidden, schema()))
    show = plan('index', 'visibility', {'visibility': 'VISIBLE'}, INDEX)
    assert control_plane._schema_applied(show, shards(schema(), schema()))
    drop = plan('view', 'drop', {}, TABLE)
    assert control_plane._schema_applied(drop, shards(None, None))
    assert not control_plane._schema_applied(drop, shards(None, 'CREATE'))


def test_inspection_never_reruns_the_change(monkeypatch):
    calls = []

    def run(_route, arguments, timeout=None):
        calls.append(arguments[0])
        documents = {
            'FindAllShardsInKeyspace': '{"shards": {"-80": {}, "80-": {}}}',
            'GetTablets': ('[{"shard": "-80", "alias": {"cell": "c", '
                           '"uid": 1}}, {"shard": "80-", "alias": '
                           '{"cell": "c", "uid": 2}}]'),
            'GetSchema': '{"table_definitions": []}',
        }
        return {'stdout': documents[arguments[0]]}
    monkeypatch.setattr(control_plane, '_run', run)
    request = {'plan': plan('view', 'drop', {}, TABLE),
               'provider_payload': {'route': {}, 'compiled': {
                   'provider_action': {'arguments': [
                       'ApplySchema', '--sql', 'DROP VIEW `t`', 'ks']}}}}
    state = control_plane.post_validate_action(None, request)
    assert state['confirmed'] and 'ApplySchema' not in calls
    assert calls.count('GetSchema') == 2
