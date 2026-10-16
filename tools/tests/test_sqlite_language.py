"""SQLite native EXPLAIN validation never executes submitted SQL."""

import sqlite3
import pytest
from types import SimpleNamespace

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import PROFILE, create_provider


def test_sqlite_validator_distinguishes_syntax_from_context_and_preserves_transaction(tmp_path):
    context = SimpleNamespace(endpoint_id='endpoint', session_namespace='sqlite-test',
        pool_namespace='sqlite-test', cache_namespace='sqlite-test',
        provider_id=PROFILE.provider_id, profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version, provider_version='0.1.0')
    provider = create_provider(context, SimpleNamespace(require=lambda *_: None))
    route = {'database': str(tmp_path / 'language.sqlite'),
             'filesystem_root': str(tmp_path)}
    try:
        session = provider.open_session({'route': route})
        def check(source, script=False):
            return provider.validate_source_without_execution({
                'session_id': session['session_id'], 'language_profile': 'sqlite-sql',
                'source': source, 'script': script})
        create = check('CREATE TABLE never_executed(id INTEGER)')
        assert create['grammar_valid'] is True
        assert check('PRAGMA user_version=91')['grammar_valid'] is True
        assert provider._sessions[session['session_id']].handle.execute('PRAGMA user_version').fetchone() == (0,)
        with sqlite3.connect(route['database']) as observer:
            assert not observer.execute("SELECT 1 FROM sqlite_schema WHERE name='never_executed'").fetchall()
        assert check('SELEC 1')['grammar_valid'] is False
        assert check('SELECT * FROM absent')['grammar_valid'] is None
        assert check('SELECT ?')['grammar_valid'] is None
        handle = provider._sessions[session['session_id']].handle
        handle.execute('BEGIN')
        handle.execute('CREATE TABLE pending(id INTEGER)')
        assert check('SELECT * FROM pending')['grammar_valid'] is True
        assert handle.in_transaction
        handle.rollback()
        trigger = check('CREATE TRIGGER t AFTER INSERT ON pending BEGIN SELECT 1; END;',
                        script=True)
        assert trigger['grammar_valid'] is None and trigger['script_ready'] is True
        provider.close_session(session)
    finally:
        provider.close()


def test_preparation_suppresses_pragma_side_effects_and_preserves_authorization(tmp_path):
    from pgadmin.cdeadmin.providers.sqlite.provider import _create_client
    client = _create_client()
    handle = client.open_session({'route': {'database': str(tmp_path / 'protected.sqlite'),
        'filesystem_root': str(tmp_path)}})
    try:
        handle.execute('CREATE TABLE sensitive(id INT CHECK(id>0))')
        handle.commit()
        calls = []
        def policy(action, first, second, database, context):
            calls.append((action, first))
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and first == 'sensitive' else sqlite3.SQLITE_OK
        handle.set_authorizer(policy)
        for name in ('foreign_keys', 'ignore_check_constraints', 'recursive_triggers', 'writable_schema', 'trusted_schema'):
            before = handle.execute('PRAGMA ' + name).fetchone()[0]
            result = client.validate_parse_only(handle, '/* prepare only */ PRAGMA ' + name + '=' + str(1 - before))
            assert result['grammar_valid'] is True and result['pragma_preparation_suppressed'] is True
            assert handle.execute('PRAGMA ' + name).fetchone()[0] == before
            assert handle._cdeadmin_authorizer is policy
        assert client.validate_parse_only(handle, '-- comment\nEXPLAIN SELECT 1')['grammar_valid'] is True
        assert client.validate_parse_only(handle, 'PRAGMA foreign_keys=ON trailing garbage')['grammar_valid'] is False
        assert client.validate_parse_only(handle, 'SELECT * FROM sensitive')['grammar_valid'] is None
        with pytest.raises(sqlite3.DatabaseError):
            handle.execute('SELECT * FROM sensitive')
        handle.set_authorizer(None)
        handle.execute('BEGIN')
        handle.execute('INSERT INTO sensitive VALUES(1)')
        assert client.validate_parse_only(handle, 'PRAGMA ignore_check_constraints=ON')['grammar_valid'] is True
        with pytest.raises(sqlite3.IntegrityError):
            handle.execute('INSERT INTO sensitive VALUES(0)')
        assert handle.in_transaction
        with sqlite3.connect(tmp_path / 'protected.sqlite') as observer:
            assert observer.execute('SELECT count(*) FROM sensitive').fetchone() == (0,)
        handle.rollback()
        assert any(action == sqlite3.SQLITE_PRAGMA for action, _ in calls)
    finally:
        client.close_session(handle)
        client.close()
