"""Owned PostgreSQL 18.3 native editor identity and transaction qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web')]
import config
import psycopg
from psycopg import sql, Cursor
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row, dict_row
from tools.postgresql_qualification_support import server
from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProvider


def qualify(output):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Qualification evidence must be outside the source checkout')
    output.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'history_tests_executed': False, 'interfaces': [],
        'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), ROOT/'web/pgadmin/cdeadmin/providers/postgresql/editor_context.py',
                         ROOT/'web/pgadmin/cdeadmin/providers/postgresql/provider.py')}}
    try:
        with server(output/'fixture', initdb_options=('--locale=C', '--encoding=UTF8')) as (route, password, owned):
            arguments = dict(host=route['host'], port=route['port'], user=route['user'],
                dbname=route['database'], password=password, **route['connection_params'])
            with psycopg.connect(**arguments, autocommit=True) as observer:
                role = 'Role ü "' + secrets.token_hex(6)
                observer.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
                observer.execute(sql.SQL('GRANT {} TO postgres').format(sql.Identifier(role)))
                observer.execute(sql.SQL('CREATE SCHEMA {} AUTHORIZATION {}').format(sql.Identifier(role), sql.Identifier(role)))
                observer.execute('CREATE TABLE public.editor_context_keep(id integer)')
                observer.execute(sql.SQL('GRANT SELECT,INSERT ON public.editor_context_keep TO {}').format(sql.Identifier(role)))
                for autocommit, factory in ((True, tuple_row), (False, dict_row)):
                    with psycopg.connect(**arguments, autocommit=autocommit, row_factory=factory) as connection:
                        state = SimpleNamespace(connection=SimpleNamespace(conn=connection, connected=lambda: not connection.closed),
                            uncertain=False, attached=True, lock=threading.RLock())
                        provider = object.__new__(PostgreSQLProvider)
                        provider._sessions = {'owned': state}; provider._operations = {}; provider._state_lock = threading.RLock()
                        def context(): return provider._editor_context(state, '')
                        def execute(source):
                            with Cursor(connection, row_factory=tuple_row) as cursor:
                                cursor.execute(source)
                                return cursor.fetchone() if cursor.description else None
                        def transaction_context():
                            return (execute('SELECT pg_current_xact_id()::text')[0],
                                execute('SHOW search_path')[0], execute('SHOW standard_conforming_strings')[0],
                                execute('SHOW backslash_quote')[0])
                        request = {'session_id': 'owned', 'language_profile': 'postgresql-sql', 'source': r"SELECT 'it\'s'"}
                        first = context()
                        assert first['observation']['available'] and connection.info.transaction_status == TransactionStatus.IDLE
                        assert first['authenticated_principal'] == first['session_principal'] == first['effective_principal'] == 'postgres'
                        assert first['selected_role'] == 'none'
                        execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role))); connection.commit()
                        selected = context()
                        assert selected['authenticated_principal'] == selected['session_principal'] == 'postgres'
                        assert selected['effective_principal'] == selected['active_role'] == selected['selected_role'] == role
                        assert selected['search_path'] == first['search_path'] and role in selected['resolved_search_path']
                        assert selected['context_revision'] != first['context_revision'] and connection.info.transaction_status == TransactionStatus.IDLE
                        execute('BEGIN')
                        execute('INSERT INTO public.editor_context_keep VALUES(42)')
                        execute("SET LOCAL search_path=public; SET LOCAL standard_conforming_strings=off; SET LOCAL backslash_quote=off")
                        before = transaction_context()
                        pending = context()
                        assert pending['search_path'] == 'public' and pending['standard_conforming_strings'] == pending['backslash_quote'] == 'off'
                        assert pending['context_revision'] != selected['context_revision']
                        assert provider.validate_source_without_execution(request)['grammar_valid'] is False
                        assert transaction_context() == before
                        assert execute('SELECT count(*) FROM public.editor_context_keep')[0] == 1
                        assert observer.execute('SELECT count(*) FROM public.editor_context_keep').fetchone()[0] == 0
                        connection.rollback()
                        observer.execute('REVOKE EXECUTE ON FUNCTION pg_catalog.current_setting(text) FROM PUBLIC')
                        try:
                            # Enter a new user transaction after the native ACL
                            # change rather than assume its visibility mid-transaction.
                            execute('BEGIN')
                            execute('INSERT INTO public.editor_context_keep VALUES(42)')
                            execute("SET LOCAL search_path=public; SET LOCAL standard_conforming_strings=off; SET LOCAL backslash_quote=off")
                            before = transaction_context()
                            denied = context()
                            proof['permission_failure_observation'] = denied
                            assert denied['observation'] == {'available': False, 'reason': 'native-observation-failed', 'sqlstate': '42501'}
                            assert denied['effective_principal'] is None and denied['standard_conforming_strings'] is None
                            assert not state.uncertain and connection.info.transaction_status == TransactionStatus.INTRANS
                            assert transaction_context() == before
                            assert execute('SELECT count(*) FROM public.editor_context_keep')[0] == 1
                            unavailable = provider.validate_source_without_execution(request)
                            assert unavailable['grammar_valid'] is None and unavailable['diagnostics'][0]['code'] == 'SESSION_MODE_REQUIRED'
                        finally: observer.execute('GRANT EXECUTE ON FUNCTION pg_catalog.current_setting(text) TO PUBLIC')
                        assert transaction_context() == before
                        try: execute('SELECT 1/0')
                        except psycopg.errors.DivisionByZero: pass
                        aborted = context()
                        assert not aborted['observation']['available'] and connection.info.transaction_status == TransactionStatus.INERROR
                        assert not state.uncertain
                        connection.rollback()
                        assert context()['context_revision'] == selected['context_revision']
                        execute('RESET ROLE'); connection.commit()
                        assert context()['context_revision'] == first['context_revision']
                        execute(sql.SQL('SET SESSION AUTHORIZATION {}').format(sql.Identifier(role))); connection.commit()
                        authorization = context()
                        assert authorization['authenticated_principal'] == 'postgres'
                        assert authorization['session_principal'] == authorization['effective_principal'] == role
                        assert authorization['selected_role'] == 'none' and authorization['context_revision'] != first['context_revision']
                        execute('RESET SESSION AUTHORIZATION'); connection.commit()
                        assert context()['context_revision'] == first['context_revision']
                        proof['interfaces'].append({'autocommit': autocommit, 'row_factory': factory.__name__,
                            'role_and_session_authorization_observed': True, 'search_path_resolution_observed': True,
                            'pending_transaction_and_local_settings_preserved': True, 'native_permission_failure_isolated': True,
                            'aborted_transaction_not_repaired': True, 'idle_transaction_released': True})
        proof.update(complete=owned['owned_server_stopped'], owned_server_stopped=owned['owned_server_stopped'])
    finally: (output/'summary.json').write_text(json.dumps(proof, indent=2)+'\n')
    assert proof['complete'] and proof['owned_server_stopped']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    qualify(parser.parse_args().evidence)
