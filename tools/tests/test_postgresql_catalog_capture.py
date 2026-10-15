"""Native PostgreSQL DDN envelopes preserve engine identity and exact facts."""
import json
from unittest.mock import Mock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.providers.postgresql.catalog_capture import capture
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog, compare_catalogs


def item(identity, **native):
    return {'resource_id': identity, 'resource_kind': 'relation',
            'display_name': 'Quoted " ü', 'display_path': ['db', 'schema', 'Quoted " ü'],
            'native': {'system_object': False, **native}}


def export(rows, engine='postgresql', **kwargs):
    return build_export(rows, endpoint_id='endpoint', target_id='postgresql-database:16384',
                        generation='g', engine=engine, **kwargs)


def test_postgresql_document_roundtrip_keeps_native_large_values_and_addresses():
    result = export([item('postgresql:pg_class:17000', oid=17000, catalog='pg_class',
                          definition='CREATE VIEW "Quoted \\" ü" AS SELECT 1', exact=2**100)])
    parsed = read_catalog(json.dumps(result['snapshot']), engine='postgresql')
    assert parsed['rows']['postgresql:pg_class:17000']['native']['exact'] == 2**100
    assert result['filename'] == 'postgresql-catalog.ddn'
    assert parsed['provenance']['mapping'] == 'scratchrobin.postgresql.catalog@1'
    assert parsed['rows']['postgresql:pg_class:17000']['uid'].startswith('postgresql:')
    compared = compare_catalogs(parsed, export([item('postgresql:pg_class:17000', oid=17000,
        catalog='pg_class', definition='CREATE VIEW "Quoted \\" ü" AS SELECT 1', exact=2**100)], native_model=True))
    assert compared['counts']['equal'] == 1


def test_engine_identity_cannot_be_relabelled_by_import():
    document = json.dumps(export([item('native')])['snapshot'])
    with pytest.raises(ValueError):
        read_catalog(document)
    pg = read_catalog(document, engine='postgresql')
    fb = export([item('native')], engine='firebird', native_model=True)
    with pytest.raises(ValueError):
        compare_catalogs(pg, fb)


def test_postgresql_views_preserve_all_pages_and_native_parent_scope():
    rows = [item('table')] + [item(f'column:{i}', navigator_parent_resource_id='table') for i in range(205)]
    rows += [item('unrelated')]
    result = export(rows, resource_id='table')
    parsed = read_catalog(json.dumps(result['snapshot']), engine='postgresql')
    assert len(parsed['rows']) == 206
    assert 'unrelated' not in parsed['rows']
    assert len(result['views']) == 3


@pytest.mark.parametrize('oid', [None, True, 0, -1, '16384', 2**32])
def test_capture_refuses_invalid_database_before_any_native_command(oid):
    connection = Mock()
    with pytest.raises(ValueError):
        capture(connection, oid)
    connection.execute.assert_not_called()


def test_capture_cannot_borrow_existing_transaction():
    connection = Mock()
    connection.info.transaction_status = 2
    with pytest.raises(ValueError, match='own idle'):
        capture(connection, 16384)
    connection.execute.assert_not_called()
