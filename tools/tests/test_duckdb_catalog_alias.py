"""Native SET ALIAS effects, original transactions and descendant identities."""
import pytest
from test_duckdb_attachment_actions import fixture, review, apply
from pgadmin.cdeadmin.providers.duckdb.attachments import action, catalogs
from pgadmin.cdeadmin.workspace.duckdb_editor_operations import compile_request


def rename(fixture, old, new, **values):
    client, handle, route, _ = fixture
    transport, request = compile_request('editor_attachment_review_rename',
        {'alias': old, 'new_alias': new, 'dependent_sql_confirmed': True, **values})
    assert transport == 'duckdb_attachments'
    return action(client, handle, route, request)


def attached(fixture):
    result = apply(fixture, review(fixture))
    assert result['rediscovery_verified']
    fixture[0].control_transaction(fixture[1], 'commit')
    return result['alias']


def test_alias_change_preserves_pending_work_file_and_refreshes_descendants(fixture):
    client, handle, route, other = fixture
    alias = attached(fixture); original_stat = other.stat()
    handle.execute('INSERT INTO pending VALUES (42)')
    new = 'renamed . " 雪'
    record = rename(fixture, alias, new)
    result = apply(fixture, record)
    assert result['state'] == 'acknowledged' and result['native_acknowledged'] and result['rediscovery_verified']
    assert not result['caller_transaction_decision_requested'] and not result['physical_file_renamed']
    assert not result['alias_restored_by_rollback'] and not result['stored_sql_rewritten']
    assert handle.execute('SELECT id FROM "renamed . "" 雪".main.data').fetchall() == [(7,)]
    assert handle.execute('SELECT id FROM pending').fetchall() == [(42,)]
    old_ids = result['invalidate_resource_ids']
    fresh = result['refreshed_descendant_identities']
    assert old_ids and fresh and not set(old_ids) & {r['resource_id'] for r in fresh}
    assert any(r['resource_kind'] == 'table' and r['display_path'] == [new, 'main', 'data'] for r in fresh)
    assert (other.stat().st_dev, other.stat().st_ino) == (original_stat.st_dev, original_stat.st_ino)
    assert apply(fixture, record) == result
    handle.rollback()
    assert handle.execute('SELECT id FROM pending').fetchall() == []
    assert new in [row['name'] for row in catalogs(handle)]
    assert alias not in [row['name'] for row in catalogs(handle)]


def test_changed_transaction_refuses_even_when_catalog_unchanged(fixture):
    client, handle, _, _ = fixture; alias = attached(fixture)
    record = rename(fixture, alias, 'next_alias')
    client.control_transaction(handle, 'commit')
    result = apply(fixture, record)
    assert result['state'] == 'refused' and not result['native_dispatched']
    assert alias in [row['name'] for row in catalogs(handle)]


def test_changed_native_metadata_refuses_before_alias_dispatch(fixture):
    _, handle, _, _ = fixture; alias = attached(fixture)
    record = rename(fixture, alias, 'next_alias')
    handle.execute('CREATE VIEW extra_view AS SELECT 1 AS value')
    result = apply(fixture, record)
    assert result['state'] == 'refused' and not result['native_dispatched']
    assert apply(fixture, record) == result


def test_primary_and_conflicting_or_internal_names_refuse(fixture):
    _, handle, _, _ = fixture; alias = attached(fixture)
    primary = handle.execute('SELECT current_database()').fetchone()[0]
    for old, new in [(primary, 'next_alias'), (alias, primary), (alias, 'TEMP'), (alias, alias.replace('extra', 'EXTRA'))]:
        with pytest.raises(ValueError): rename(fixture, old, new)
    with pytest.raises(ValueError, match='stored/external SQL'):
        rename(fixture, alias, 'next_alias', dependent_sql_confirmed=False)


def test_renamed_catalog_stored_sql_is_not_falsely_reported_as_rewritten(fixture):
    client, handle, _, _ = fixture
    # Create a view containing an explicitly qualified old catalog reference.
    result = apply(fixture, review(fixture, read_only=False)); alias = result['alias']
    handle.execute('CREATE VIEW "extra . "" é".main.v AS SELECT * FROM "extra . "" é".main.data')
    client.control_transaction(handle, 'commit')
    record = rename(fixture, alias, 'next_alias')
    result = apply(fixture, record)
    assert result['rediscovery_verified'] and not result['stored_sql_rewritten']
    assert result['alias_review']['external_or_dynamic_sql_dependencies'] == 'not-enumerable'
    stored_sql = handle.execute("SELECT sql FROM duckdb_views() WHERE database_name='next_alias' AND view_name='v'").fetchone()[0]
    assert alias.replace(chr(34), chr(34)*2) in stored_sql
    assert result['alias_review']['stored_sql_sources']
