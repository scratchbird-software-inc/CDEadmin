"""SQLite native EXPLAIN validation never executes submitted SQL."""

import sqlite3
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
