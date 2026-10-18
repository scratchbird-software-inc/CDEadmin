"""Native comment review guards and transaction ownership under failures."""
from copy import deepcopy
from unittest.mock import patch

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION, _create_client, _resources
from pgadmin.cdeadmin.providers.duckdb.object_metadata import KINDS
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import catalog_for_engine


def request(resource, route, **draft):
    return {'resource_kind': resource['resource_kind'], 'operation_id': 'comment',
            'target_resource': resource, '_provider_route': route,
            'draft': {'comment': 'reviewed comment',
                      'confirmation': resource['display_name'], **draft}}


def test_metadata_form_is_reachable_and_multiline():
    catalog = ADMINISTRATION.catalog(catalog_for_engine('duckdb'))
    found = set()
    for obj in catalog['objects']:
        if obj['resource_kind'] not in KINDS:
            continue
        operation = next(row for row in obj['operations'] if row['operation_id'] == 'comment')
        assert operation['target_required'] and operation['confirmation_required']
        assert operation['form']['fields'][0]['control'] == 'multiline'
        found.add(obj['resource_kind'])
    assert found == KINDS


@pytest.fixture
def fixture(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path/'owned.duckdb'
    owner = duckdb.connect(str(path))
    owner.execute('CREATE TABLE t(id INT)')
    client = _create_client()
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    def target(connection=owner):
        return next(row for row in _resources(connection, {})
                    if row['resource_kind'] == 'table' and row['display_name'] == 't')
    try:
        yield owner, client, route, target
    finally:
        client.close()
        owner.close()


@pytest.mark.parametrize('draft', [
    {'confirmation': 'T'}, {'confirmation': None}, {'comment': None},
    {'comment': '\x00'}, {'clear_comment': 'true'},
    {'clear_comment': True, 'comment': 'would silently disappear'},
    {'source': 'DROP TABLE t'},
])
def test_invalid_intent_never_compiles(fixture, draft):
    _, _, route, target = fixture
    item = request(target(), route, **draft)
    assert ADMINISTRATION.validate(item)['errors']
    with pytest.raises(RelationalClientError):
        ADMINISTRATION.plan(item)


def test_recreated_object_refuses_the_original_oid(fixture):
    owner, client, route, target = fixture
    planned = ADMINISTRATION.plan(request(target(), route))
    owner.execute('DROP TABLE t')
    owner.execute('CREATE TABLE t(id INT)')
    with pytest.raises(RelationalClientError, match='changed since review') as failure:
        ADMINISTRATION.apply(client, planned)
    assert failure.value.native_dispatched is False
    assert owner.execute("SELECT comment FROM duckdb_tables() WHERE table_name='t'").fetchone() == (None,)


def test_uncertain_observation_preserves_borrowed_work_and_blocks_reuse(fixture):
    owner, client, route, target = fixture
    retained = client.open_session({'route': route})
    retained.execute('INSERT INTO t VALUES (42)')
    planned = ADMINISTRATION.plan(request(target(retained), route))
    original = _resources
    reads = 0
    def failing_read(*args, **kwargs):
        nonlocal reads
        reads += 1
        if reads == 2:
            raise OSError('native observation unavailable')
        return original(*args, **kwargs)
    with patch('pgadmin.cdeadmin.providers.duckdb.provider._resources', side_effect=failing_read):
        with pytest.raises(RelationalClientError) as failure:
            ADMINISTRATION.apply(client, planned, retained)
    assert failure.value.native_acknowledged is True
    assert client.describe_transaction(retained)['session_reuse_blocked']
    # No implicit rollback or commit of the caller's pending rows or metadata.
    assert retained.execute('SELECT id FROM t').fetchall() == [(42,)]
    assert owner.execute('SELECT id FROM t').fetchall() == []
    retained.rollback()
    assert owner.execute("SELECT comment FROM duckdb_tables() WHERE table_name='t'").fetchone() == (None,)


def test_changed_compiled_statement_is_not_dispatched(fixture):
    _, client, route, target = fixture
    planned = deepcopy(ADMINISTRATION.plan(request(target(), route)))
    planned['provider_payload']['compiled']['statements'][0]['source'] = 'DROP TABLE t'
    with pytest.raises(RelationalClientError, match='operation changed'):
        ADMINISTRATION.apply(client, planned)
    assert client._connections == []
