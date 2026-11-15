"""SQLite STRICT and WITHOUT ROWID on create (owner direction 2026-10-29:
surface every feature, filter per engine version). STRICT tables arrived in
SQLite 3.37.0 (https://www.sqlite.org/releaselog/3_37_0.html)."""
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.sqlite.provider import (  # noqa: E402
    ADMINISTRATION, _create_client,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402
from pgadmin.cdeadmin.ui_descriptors import UIDescriptorService  # noqa: E402
from ui_descriptor_roundtrip import backend_draft, resolved_form  # noqa: E402

STRICT_AVAILABLE = sqlite3.sqlite_version_info >= (3, 37, 0)


@pytest.fixture
def live(tmp_path):
    path = tmp_path / 'options.sqlite'
    route = {'database': str(path), 'filesystem_root': str(tmp_path),
             'timeout': .05}
    client = _create_client()
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        yield path, route, client, connection
    finally:
        connection.close()
        client.close()


def _plan(route, draft):
    return ADMINISTRATION.plan({
        'resource_kind': 'table', 'operation_id': 'create',
        'target_resource': None, '_provider_route': route, 'draft': draft})


def _draft(name, **options):
    form = resolved_form('sqlite', 'table')
    return backend_draft(form, {
        'variant': 'default', 'name': name, 'parent': 'main',
        'columns': [{'name': 'id', 'type': 'INTEGER', 'nullable': False,
                     'primary_key': True},
                    {'name': 'label', 'type': 'TEXT', 'nullable': True}],
        **options})


def test_descriptor_options_reach_native_create_through_facade(live):
    from pgadmin.cdeadmin.visual_admin.provider import ProviderVisualAdministration
    path, route, client, _connection = live
    facade = ProviderVisualAdministration(
        SimpleNamespace(endpoint_id='owned', mode='direct'),
        SimpleNamespace(require=lambda *_: None),
        'sqlite', sqlite3.sqlite_version, client)
    draft = _draft('facade_options', without_rowid=True,
                   strict=STRICT_AVAILABLE)
    request = dict(resource_kind='table', operation_id='create',
                   draft=draft, _provider_route=route)
    validated = facade.validate(request)
    assert validated['valid'], validated
    assert validated['draft']['without_rowid'] is True
    assert validated['draft']['strict'] is STRICT_AVAILABLE
    planned = client.plan_admin_operation({
        **request, 'draft': validated['draft']})
    assert client.apply_admin_operation(planned)['accepted']
    with closing(sqlite3.connect(path)) as observer:
        sql = observer.execute(
            "SELECT sql FROM sqlite_schema WHERE name='facade_options'"
        ).fetchone()[0]
    assert 'WITHOUT ROWID' in sql
    assert ('STRICT' in sql) is STRICT_AVAILABLE


def test_strict_version_gate_uses_descriptor_and_native_runtime(live):
    from pgadmin.cdeadmin.visual_admin.provider import ProviderVisualAdministration
    _path, route, client, _connection = live
    facade = ProviderVisualAdministration(
        SimpleNamespace(), SimpleNamespace(require=lambda *_: None),
        'sqlite', sqlite3.sqlite_version, client)
    result = facade.validate(dict(
        resource_kind='table', operation_id='create', _provider_route=route,
        draft=_draft('gated_strict', strict=True)))
    assert result['valid'] is STRICT_AVAILABLE
    if not STRICT_AVAILABLE:
        assert any(error['code'] == 'unsupported_version'
                   for error in result['errors'])


def _table_list(path, name):
    with closing(sqlite3.connect(path)) as observer:
        row = observer.execute(
            'SELECT wr, strict FROM pragma_table_list WHERE name=?',
            (name,)).fetchone()
    return {'without_rowid': bool(row[0]), 'strict': bool(row[1])}


def test_without_rowid_is_appended_and_created(live):
    path, route, client, connection = live
    planned = _plan(route, _draft('clustered', without_rowid=True))
    source = planned['command_preview']['statements'][0]['source']
    assert source.endswith(') WITHOUT ROWID')
    assert ADMINISTRATION.apply(client, planned, connection=connection)[
        'accepted']
    with closing(sqlite3.connect(path)) as observer:
        ddl = observer.execute(
            "SELECT sql FROM sqlite_schema WHERE name='clustered'"
        ).fetchone()[0]
    assert ddl.endswith('WITHOUT ROWID')


def test_unset_options_add_nothing(live):
    _path, route, _client, _connection = live
    planned = _plan(route, _draft('plain', strict=False))
    source = planned['command_preview']['statements'][0]['source']
    assert source.endswith(')')


def test_option_values_must_be_booleans(live):
    _path, route, _client, _connection = live
    with pytest.raises(RelationalClientError, match='strict must be true'):
        _plan(route, _draft('bad', strict='yes'))


@pytest.mark.skipif(not STRICT_AVAILABLE, reason='STRICT needs 3.37.0+')
def test_strict_and_without_rowid_together(live):
    path, route, client, connection = live
    planned = _plan(route, _draft('typed', strict=True, without_rowid=True))
    source = planned['command_preview']['statements'][0]['source']
    assert source.endswith(') WITHOUT ROWID, STRICT')
    assert ADMINISTRATION.apply(client, planned, connection=connection)[
        'accepted']
    assert _table_list(path, 'typed') == {
        'without_rowid': True, 'strict': True}


@pytest.mark.skipif(STRICT_AVAILABLE, reason='runtime has STRICT')
def test_strict_is_refused_natively_before_3_37(live):
    """Forced past the UI gate, the engine itself refuses STRICT."""
    _path, route, client, connection = live
    planned = _plan(route, _draft('typed', strict=True))
    with pytest.raises(Exception):
        result = ADMINISTRATION.apply(client, planned, connection=connection)
        assert result['accepted'], result


@pytest.mark.parametrize('version,available', [
    ('3.35.0', False), ('3.36.0', False), ('3.37.0', True),
    ('3.45.1', True), ('3.53.0', True)])
def test_strict_field_is_gated_by_version(version, available):
    bundle = UIDescriptorService().resolve_for_version('sqlite', version)
    fields = {field['field_id']: field
              for tab in bundle['forms']['table']['tabs']
              for field in tab['fields']}
    assert fields['strict']['available'] is available
    assert fields['without_rowid']['available'] is True
    if not available:
        assert '3.37.0' in fields['strict']['unavailable_reason']
