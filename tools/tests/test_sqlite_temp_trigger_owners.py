"""Native TEMP trigger namespace and attached-owner catalog reconciliation."""
import sqlite3

import pytest
import test_cdeadmin_relational_providers  # noqa: F401

from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.provider import _resources, _resource_id


@pytest.fixture
def connection():
    handle = sqlite3.connect(':memory:', factory=SQLiteConnection)
    handle.execute("ATTACH ':memory:' AS aux")
    for schema in ('main', 'aux', 'temp'):
        handle.execute('CREATE TABLE ' + schema + '.same(id INTEGER)')
    handle.execute('CREATE TABLE main.effects(id INTEGER)')
    try:yield handle
    finally:handle.close()


def trigger(handle, schema='aux', name='exact . " é'):
    quote = lambda value: '"' + value.replace('"', '""') + '"'
    handle.execute('CREATE TEMP TRIGGER ' + quote(name) + ' AFTER INSERT ON ' + quote(schema) +
        '.same BEGIN INSERT INTO effects VALUES (NEW.id); END')


@pytest.mark.parametrize('schema', ['main', 'aux', 'temp'])
def test_temp_namespace_is_stable_and_native_declared_owner_is_exact(connection, schema):
    name = 'exact . " é';trigger(connection, schema, name)
    connection.execute('INSERT INTO main.effects VALUES (42)')
    before = connection.in_transaction
    resources = _resources(connection, {})
    row = next(row for row in resources if row['resource_kind'] == 'trigger')
    assert row['resource_id'] == _resource_id('trigger', ['temp'], name)
    assert row['display_path'] == ['temp', name]
    observed = row['native']['owner_binding_observation']
    assert observed['available'] and observed['database'] == schema and observed['table'] == 'same'
    assert observed['existing_trigger_execution_observed'] is False
    owner = next(item for item in resources if item['resource_id'] == observed['resource_id'])
    assert owner['display_path'] == [schema, 'same']
    assert row['native']['navigator_parent_resource_id'] == owner['resource_id']
    assert [child['resource_id'] for child in owner['native']['triggers']] == [row['resource_id']]
    assert all(not item['native'].get('triggers') for item in resources
        if item['resource_kind'] == 'table' and item['display_name'] == 'same' and item is not owner)
    assert connection.in_transaction == before
    assert connection.execute('SELECT * FROM main.effects').fetchall() == [(42,)]
    assert connection.execute("SELECT count(*) FROM temp.sqlite_schema WHERE name LIKE '__scratchrobin_trigger_owner_%'").fetchone() == (0,)
    connection.execute('INSERT INTO ' + schema + '.same VALUES (73)')
    assert connection.execute('SELECT * FROM main.effects').fetchall() == [(42,), (73,)]


def test_persistent_and_temp_same_name_trigger_never_collapse_or_share_wrong_owner(connection):
    connection.execute('CREATE TRIGGER main.equal AFTER INSERT ON main.same BEGIN SELECT 1; END')
    trigger(connection, 'aux', 'equal')
    rows = _resources(connection, {})
    triggers = [row for row in rows if row['resource_kind'] == 'trigger']
    assert len(triggers) == len({row['resource_id'] for row in triggers}) == 2
    temporary = next(row for row in triggers if row['display_path'][0] == 'temp')
    assert temporary['native']['owner_binding_observation']['database'] == 'aux'
    main = next(row for row in rows if row['resource_kind'] == 'table' and row['display_path'] == ['main', 'same'])
    assert [child['resource_id'] for child in main['native']['triggers']] == [
        next(row for row in triggers if row['display_path'][0] == 'main')['resource_id']]


def test_unqualified_ambiguous_owner_is_explicit_and_never_attached_to_shadow(connection):
    connection.execute('CREATE TEMP TRIGGER ambiguous AFTER INSERT ON same BEGIN SELECT 1; END')
    rows = _resources(connection, {})
    row = next(row for row in rows if row['resource_kind'] == 'trigger')
    observation = row['native']['owner_binding_observation']
    assert observation['available'] is False
    assert observation['reason'] == 'unqualified_owner_has_multiple_native_candidates'
    assert {tuple(path) for path in observation['candidate_paths']} == {('main', 'same'), ('temp', 'same'), ('aux', 'same')}
    assert row['native']['navigator_parent_resource_id'] == _resource_id('attached-database', [], 'temp')
    assert all(not other['native'].get('triggers') for other in rows)


def test_prior_authorization_is_composed_and_restored_on_native_refusal(connection):
    trigger(connection)
    calls = []
    def policy(action, name, owner, database, context):
        calls.append(action)
        return sqlite3.SQLITE_DENY if action in {sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_CREATE_TEMP_TRIGGER} else sqlite3.SQLITE_OK
    connection.set_authorizer(policy)
    rows = _resources(connection, {})
    observation = next(row for row in rows if row['resource_kind'] == 'trigger')['native']['owner_binding_observation']
    assert not observation['available'] and observation['native_error_code'] == sqlite3.SQLITE_AUTH
    assert connection._cdeadmin_authorizer is policy
    assert sqlite3.SQLITE_CREATE_TRIGGER in calls or sqlite3.SQLITE_CREATE_TEMP_TRIGGER in calls
    assert connection.execute('SELECT count(*) FROM main.effects').fetchone() == (0,)


def test_plain_connections_keep_unobservable_authorizer_untouched():
    handle = sqlite3.connect(':memory:')
    handle.execute('CREATE TABLE owner(id INT)')
    handle.execute('CREATE TEMP TRIGGER owned AFTER INSERT ON main.owner BEGIN SELECT 1; END')
    seen = []
    def policy(*args):seen.append(args[0]);return sqlite3.SQLITE_OK
    handle.set_authorizer(policy)
    try:
        row = next(row for row in _resources(handle, {}) if row['resource_kind'] == 'trigger')
        assert row['native']['owner_binding_observation']['reason'] == 'connection_authorization_policy_unobservable'
        seen.clear();handle.execute('SELECT 9123').fetchone();assert seen
    finally:handle.close()


def test_header_comments_quoted_keywords_and_body_ddl_are_not_executed(connection):
    connection.execute('CREATE TEMP TRIGGER "ON . weird" /* ON fake.owner */ AFTER INSERT ON "aux"."same" '
        "BEGIN SELECT 'ON fake.owner; CREATE TABLE private(id)'; INSERT INTO effects VALUES (NEW.id); END")
    rows = _resources(connection, {})
    row = next(row for row in rows if row['resource_kind'] == 'trigger')
    assert row['native']['owner_binding_observation']['database'] == 'aux'
    assert connection.execute('SELECT count(*) FROM effects').fetchone() == (0,)


def test_retained_catalog_proxy_preserves_authorization_and_declared_owner(connection):
    from types import SimpleNamespace
    from pgadmin.cdeadmin.providers.embedded_session_catalog import sqlite_catalog
    trigger(connection)
    connection.execute('INSERT INTO main.effects VALUES (42)')
    client = SimpleNamespace(_uncertain=set())
    result = sqlite_catalog(client, connection, 'owned')
    row = next(row for row in result['resources'] if row['resource_kind'] == 'trigger')
    assert row['native']['owner_binding_observation']['database'] == 'aux'
    assert connection._cdeadmin_authorizer is None and not client._uncertain
    assert connection.in_transaction and connection.execute('SELECT * FROM effects').fetchall() == [(42,)]


def test_instead_of_trigger_owns_attached_view_and_never_invokes_its_function_during_capture(connection):
    calls = []
    connection.create_function('owned_probe', 1, lambda value: calls.append(value) or value)
    connection.execute('CREATE VIEW aux.projected AS SELECT id FROM same')
    connection.execute('CREATE TEMP TRIGGER view_trigger INSTEAD OF INSERT ON aux.projected BEGIN SELECT owned_probe(NEW.id); END')
    rows = _resources(connection, {})
    row = next(row for row in rows if row['resource_kind'] == 'trigger')
    binding = row['native']['owner_binding_observation']
    assert binding['available'] and binding['database'] == 'aux' and binding['table'] == 'projected'
    assert next(item for item in rows if item['resource_id'] == binding['resource_id'])['resource_kind'] == 'view'
    assert calls == []
    connection.execute('INSERT INTO aux.projected VALUES (73)')
    assert calls == [73]


def test_failed_authorizer_restoration_marks_retained_connection_uncertain(connection):
    from types import SimpleNamespace
    from pgadmin.cdeadmin.providers.embedded_session_catalog import sqlite_catalog
    from pgadmin.cdeadmin.sdk import RelationalClientError
    trigger(connection)
    connection.execute('INSERT INTO effects VALUES (42)')
    original = connection.set_authorizer
    def fail_restore(callback):
        if callback is None:raise RuntimeError('owned restoration failure')
        return original(callback)
    connection.set_authorizer = fail_restore
    client = SimpleNamespace(_uncertain=set())
    try:
        with pytest.raises(RelationalClientError, match='cleanup is unconfirmed'):
            sqlite_catalog(client, connection, 'owned')
        assert id(connection) in client._uncertain
        assert connection.in_transaction and connection.execute('SELECT * FROM effects').fetchall() == [(42,)]
    finally:original(None)
