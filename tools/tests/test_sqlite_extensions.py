"""Native extension initialization, retained editor effects and refusal outcomes."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import uuid

import pytest

from pgadmin.cdeadmin.data_studio.models import StudioSession, DataStudioAccessError
from pgadmin.cdeadmin.data_studio.studio import DataStudioService
from pgadmin.cdeadmin.providers.sqlite.provider import create_provider, PROFILE
from pgadmin.cdeadmin.sdk import RelationalClientError
from tools.sqlite_extension_fixture import build


@pytest.fixture(scope='module')
def libraries(tmp_path_factory):
    headers = Path(os.environ.get('CDEADMIN_SQLITE_HEADERS', str(Path(__file__).resolve().parents[2] / '.native/sqlite')))
    if not (headers / 'sqlite3ext.h').is_file():
        pytest.skip('Native extension fixture requires CDEADMIN_SQLITE_HEADERS or provisioned .native/sqlite; absence is unqualified coverage')
    assert sqlite3.sqlite_version == '3.53.0'
    assert hasattr(sqlite3.Connection, 'load_extension'), 'Native loader binding required'
    root = tmp_path_factory.mktemp('native-extensions')
    source = Path(__file__).resolve().parents[1] / 'fixtures/sqlite_loadable_probe.c'
    result = {}
    for identity, definitions in [('success', []), ('partial', ['CDE_PROBE_PARTIAL_FAILURE']),
                                  ('custom', ['sqlite3_extension_init=sqlite3_custom_probe_init'])]:
        library = build(source, root / identity, headers, definitions=definitions)
        result[identity] = {'id': identity, 'path': str(library), 'sha256': hashlib.sha256(library.read_bytes()).hexdigest()}
        if identity == 'custom': result[identity]['entrypoint'] = 'sqlite3_custom_probe_init'
    return result


@pytest.fixture
def native(tmp_path, libraries, monkeypatch):
    import config
    manifest = tmp_path / 'approved.json'
    manifest.write_text(json.dumps({'format': 'scratchrobin.sqlite.extensions@1', 'extensions': list(libraries.values())}))
    monkeypatch.setattr(config, 'CDEADMIN_SQLITE_EXTENSION_MANIFEST', str(manifest))
    context = SimpleNamespace(endpoint_id=str(uuid.uuid4()), session_namespace=str(uuid.uuid4()),
        pool_namespace=str(uuid.uuid4()), cache_namespace=str(uuid.uuid4()), provider_id=PROFILE.provider_id,
        provider_version='0.1.0', profile_id=PROFILE.profile_id, profile_version=PROFILE.exact_version)
    permissions = SimpleNamespace(require=lambda *_args: None)
    provider = create_provider(context, permissions)
    opened = provider.open_session({'route': {'database': str(tmp_path / 'owned.sqlite'), 'filesystem_root': str(tmp_path)}})
    handle = provider._sessions[opened['session_id']].handle
    from pgadmin.cdeadmin.providers.sqlite import provider as provider_module
    binding = SimpleNamespace(instance=provider, manifest=json.loads(
        Path(provider_module.__file__).with_name('provider_manifest.json').read_text()))
    studio = DataStudioService(SimpleNamespace(resolve=lambda _context: binding))
    session = StudioSession(context.endpoint_id, PROFILE.language_profile, opened, None, None, None)
    studio._sessions[session.session_id] = session
    def action(operation, **options):
        return studio.sqlite_extension_action(context, session.session_id, {'operation': operation, **options})
    try:
        yield SimpleNamespace(action=action, connection=handle, provider=provider, studio=studio,
            context=context, session=session, manifest=manifest, permissions=permissions, libraries=libraries, binding=binding)
    finally:
        provider.close()


def test_native_load_updates_retained_editor_and_catalog_without_enabling_sql_loader(native):
    n = native
    assert n.action('inventory')['loader_available']
    review = n.action('review', extension_id='success')
    assert 'path' not in review['extension'] and not n.connection.in_transaction
    with pytest.raises(sqlite3.OperationalError, match='no such function'):
        n.connection.execute('SELECT cde_native_probe()')
    loaded = n.action('load', review_id=review['review_id'], confirmed=True)
    assert loaded['state'] == 'loaded' and loaded['loader_cleanup_confirmed']
    assert n.connection.execute('SELECT cde_native_probe()').fetchone() == ('native extension: 雪',)
    assert any(row[0] == 'cde_native_probe' for row in loaded['native_additions']['function_list'])
    assert not n.connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION)
    with pytest.raises(sqlite3.OperationalError, match='not authorized'):
        n.connection.execute("SELECT load_extension('never')")
    catalog = n.studio.session_catalog(n.context, n.session.session_id)
    assert any(row['native'].get('name') == 'cde_native_probe' for row in catalog['resources'])
    symbols = n.provider.complete({'session_id': n.session.provider_session['session_id']})['editor_context']['resources']
    assert any(row['display_path'] == ['cde_native_probe'] for row in symbols)
    with sqlite3.connect(':memory:') as independent:
        with pytest.raises(sqlite3.OperationalError, match='no such function'):
            independent.execute('SELECT cde_native_probe()')
    checked = n.studio.validate_source(n.context, n.session.session_id, 'SELECT cde_native_probe()')
    assert checked['grammar_valid'] is True
    assert n.action('load', review_id=review['review_id'], confirmed=True) == loaded
    directories = list(n.connection._cdeadmin_extension_directories)
    assert len(directories) == 1
    n.provider.close_session({'session_id': n.session.provider_session['session_id']})
    assert all(not Path(directory).exists() for directory in directories)


@pytest.mark.parametrize('reason', ['confirmation', 'approval_removed', 'changed_bytes', 'pending_work', 'permission', 'administration', 'foreign_session'])
def test_load_refused_before_native_dispatch_without_settling_work(native, reason, tmp_path):
    n = native
    review = n.action('review', extension_id='success')
    options = {'review_id': review['review_id'], 'confirmed': True}
    if reason == 'confirmation': options['confirmed'] = False
    elif reason == 'approval_removed': n.manifest.write_text('{"format":"scratchrobin.sqlite.extensions@1","extensions":[]}')
    elif reason == 'changed_bytes':
        changed = tmp_path / 'changed.so'; changed.write_bytes(b'not native code')
        entry = {**n.libraries['success'], 'path': str(changed)}
        n.manifest.write_text(json.dumps({'format': 'scratchrobin.sqlite.extensions@1', 'extensions': [entry]}))
    elif reason == 'pending_work':
        n.connection.execute('CREATE TABLE pending(value INTEGER)')
        n.connection.execute('INSERT INTO pending VALUES(9)'); n.connection.execute('SAVEPOINT retained')
    elif reason == 'permission':
        def deny(*_args): raise PermissionError('native operation denied')
        n.permissions.require = deny
    elif reason == 'administration':
        def deny(permission, *_args):
            if permission == 'administer': raise PermissionError('native administration denied')
        n.permissions.require = deny
    elif reason == 'foreign_session':
        other = StudioSession(n.context.endpoint_id, PROFILE.language_profile,
            n.provider.open_session({'route': {'database': ':memory:', 'allow_memory': True}}), None, None, None)
        n.studio._sessions[other.session_id] = other
        with pytest.raises(DataStudioAccessError, match='another or closed session'):
            n.studio.sqlite_extension_action(n.context, other.session_id, {'operation': 'load', **options})
        return
    with pytest.raises((DataStudioAccessError, PermissionError)):
        n.action('load', **options)
    assert not n.connection._cdeadmin_extension_directories
    assert not n.provider.client._uncertain
    assert not any(row[0] == 'cde_native_probe' for row in n.connection.execute('PRAGMA function_list'))
    if reason == 'pending_work':
        assert n.connection.in_transaction
        assert n.connection.execute('SELECT * FROM pending').fetchall() == [(9,)]
        n.connection.execute('ROLLBACK TO retained'); n.connection.rollback()


def test_actual_partial_native_initialization_is_unknown_and_never_replayed(native):
    n = native
    review = n.action('review', extension_id='partial')
    result = n.action('load', review_id=review['review_id'], confirmed=True)
    assert result['state'] == 'unknown_outcome' and result['loader_cleanup_confirmed']
    assert id(n.connection) in n.provider.client._uncertain
    # Do not invoke a function registered by an extension whose init failed:
    # the native engine may already have unloaded its machine code.
    assert any(row[0] == 'cde_native_probe' for row in n.connection.execute('PRAGMA function_list'))
    assert n.action('receipt', review_id=review['review_id']) == result
    with pytest.raises(RelationalClientError, match='unknown'):
        n.action('load', review_id=review['review_id'], confirmed=True)
    assert len(n.connection._cdeadmin_extension_directories) == 1


def test_operator_supplied_native_entrypoint_is_used(native):
    review = native.action('review', extension_id='custom')
    result = native.action('load', review_id=review['review_id'], confirmed=True)
    assert result['state'] == 'loaded'
    assert native.connection.execute('SELECT cde_native_probe()').fetchone() == ('native extension: 雪',)


def test_native_authorizer_denial_keeps_original_policy_and_no_load(native):
    n = native
    review = n.action('review', extension_id='success')
    def deny(action, *_args):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_PRAGMA else sqlite3.SQLITE_OK
    n.connection.set_authorizer(deny)
    with pytest.raises(sqlite3.DatabaseError):
        n.action('load', review_id=review['review_id'], confirmed=True)
    assert n.connection._cdeadmin_authorizer is deny
    assert not n.connection._cdeadmin_extension_directories
    assert n.action('receipt', review_id=review['review_id'])['state'] == 'reviewed'


@pytest.mark.parametrize('field', ['contract_version', 'provider_id', 'provider_version', 'profile_id', 'profile_version'])
def test_real_provider_manifest_identity_changes_still_block_retained_handle(native, field):
    native.binding.manifest['identity'][field] = 'changed'
    with pytest.raises(DataStudioAccessError, match='identity changed'):
        native.action('inventory')
    assert not native.connection._cdeadmin_extension_directories
