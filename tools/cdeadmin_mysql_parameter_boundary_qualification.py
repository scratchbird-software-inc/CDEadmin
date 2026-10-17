"""Native lexical parameter execution, ownership, exact values and wire gates."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]
import config  # noqa: E402,F401


def qualify(output):
    from mysql_qualification_support import server, _root_connection
    from cdeadmin_native_editor_gate import provider
    from cdeadmin_mysql_execution_gate import collect, qualify as wire_gate
    from cdeadmin_mysql_query_values_gate import qualify as values_gate
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents: raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    proof = {'complete': False, 'history_testing': 'not run', 'interfaces': [], 'failures': [],
        'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            'web/pgadmin/cdeadmin/data_studio/mysql_quoting.py',
            'web/pgadmin/cdeadmin/providers/native_editor.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_values.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_execution.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_connections.py',
            'web/pgadmin/cdeadmin/data_studio/language_tools.py',
            'tools/cdeadmin_mysql_execution_gate.py','tools/cdeadmin_mysql_query_values_gate.py',
            str(Path(__file__).relative_to(ROOT)))}}
    try:
        with server(output / 'fixture') as (route, _name, owned):
            root = _root_connection('mysql', route['port']); root.autocommit = True; oracle = root.cursor()
            try:
                for pure in (True, False):
                    label = 'pure' if pure else 'c'; database = 'sr_bind_' + secrets.token_hex(6)
                    instance = None; checks = []
                    try:
                        oracle.execute('CREATE DATABASE `' + database + '`')
                        oracle.execute('CREATE TABLE `' + database + '`.pending(id INT PRIMARY KEY)')
                        oracle.execute('INSERT INTO `' + database + '`.pending VALUES(1)')
                        instance, selected = provider('mysql', {**route, 'database': database, 'use_pure': pure})
                        session = instance.open_session({'route': selected}); handle = instance._sessions[session['session_id']].handle
                        client = instance.client; client.control_transaction(handle, 'autocommit_off')
                        work = handle.cursor()
                        def sql(source, params=()):
                            pages = collect(client, client.execute(handle, {'source': source, 'parameters': params}))
                            return [row for page in pages for row in page['payload']['rows']], pages[-1]['payload']
                        try:
                            work.execute('INSERT INTO pending VALUES(2)'); work.execute('SAVEPOINT sr_pending')
                            text = "quote' slash\\ NUL\x00 Unicode 雪😀"
                            for mode in ('', 'ANSI_QUOTES', 'NO_BACKSLASH_ESCAPES', 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES', ''):
                                work.execute('SET SESSION sql_mode=%s', (mode,))
                                cases = [
                                    ('quoted-positional', "SELECT '%s', %s", (text,), [('%s', text)]),
                                    ('quoted-named', "SELECT '%(hidden)s', %(value)s", {'value': text}, [('%(hidden)s', text)]),
                                    ('identifier', 'SELECT 1 AS `literal%s`, %s', (text,), [(1, text)]),
                                    ('block-comment', 'SELECT /* %s */ %s', (text,), [(text,)]),
                                    ('line-comment', 'SELECT %s # %s\r\n', (text,), [(text,)]),
                                    ('active-version-comment', 'SELECT /*!90700 %s, */ %s', (text, 17), [(text, 17)]),
                                    ('inactive-version-comment', 'SELECT /*!99999 %s, */ %s', (17,), [(17,)]),
                                    ('unversioned-comment', 'SELECT /*! %s, */ %s', (text, 17), [(text, 17)]),
                                    ('unicode-named-key', 'SELECT %(雪 value)s', {'雪 value': text}, [(text,)]),
                                    ('delimiter-word-value', 'SELECT %s', ('DELIMITER $$\nquoted value',), [('DELIMITER $$\nquoted value',)]),
                                    ('exact-integer-binary', 'SELECT CAST(%s AS CHAR),HEX(%s)', (
                                        {'encoding':'integer','data':'18446744073709551615'},
                                        {'encoding':'base64','data':'AP8='}), [('18446744073709551615','00FF')])]
                                if 'ANSI_QUOTES' in mode:
                                    cases.append(('ansi-identifier-backslash','SELECT 1 AS "back\\", %s',(text,),[(1,text)]))
                                for name, source, params, expected in cases:
                                    checked = instance.validate_source_without_execution({'session_id':session['session_id'],
                                        'language_profile':'mysql-sql','source':source})
                                    assert checked['grammar_valid'] is True, (name, checked)
                                    rows, result = sql(source, params)
                                    assert rows == expected and not result.get('error'), (name, result.get('error'))
                                    checks.append({'name':name,'mode':mode,'preflight_and_native_execution_agree':True})
                                for params in ((1, 2), {'wrong': 1}):
                                    source = 'INSERT INTO pending VALUES(' + ('%s' if isinstance(params,tuple) else '%(required)s') + ')'
                                    _rows, result = sql(source, params)
                                    assert result['error']['query_dispatch'] == 'not_started' and not result['session_reuse_blocked'], result
                                    assert id(handle) not in client._uncertain_sessions
                                    rows, following = sql('SELECT COUNT(*) FROM pending')
                                    assert rows == [(2,)] and not following['error']
                                    checks.append({'name':'binding-admission-preserves-session-and-pending-work','mode':mode})
                                rows, batch = sql('SELECT %s AS one; SELECT %s AS two', (17,18))
                                assert rows == [(17,), (18,)] and not batch['error']
                                checks.append({'name':'native-bound-batch-result-ownership','mode':mode})
                                _rows, refused = sql('SELECT %s FROM absent_relation', (17,))
                                assert refused['error']['errno'] == 1146 and not refused['session_reuse_blocked'], refused
                                rows, following = sql('SELECT COUNT(*) FROM pending')
                                assert rows == [(2,)] and not following['error']
                                checks.append({'name':'native-bound-refusal-keeps-session-usable','mode':mode})
                                oracle.execute('SELECT COUNT(*) FROM `' + database + '`.pending'); assert oracle.fetchone() == (1,)
                                work.execute('ROLLBACK TO SAVEPOINT sr_pending')
                            from pgadmin.cdeadmin.providers.mysql_family import mysql_values
                            original = mysql_values.bound_source; entered = threading.Event(); release = threading.Event()
                            def pause_after_conversion(*args, **kwargs):
                                encoded = original(*args, **kwargs); entered.set()
                                if not release.wait(10): raise TimeoutError('Owned binding-dispatch cancellation fence')
                                return encoded
                            with patch.object(mysql_values, 'bound_source', pause_after_conversion):
                                try:
                                    token = client.execute(handle, {'source':'INSERT INTO pending VALUES(%s)','parameters':(99,)})
                                    assert entered.wait(10)
                                    assert client.cancel(token) is True
                                    release.set(); cancelled = collect(client, token)[-1]['payload']
                                    assert cancelled['cancelled'] and cancelled['error']['query_dispatch'] == 'not_started'
                                    assert not cancelled['session_reuse_blocked']
                                finally: release.set()
                            rows, following = sql('SELECT COUNT(*) FROM pending')
                            assert rows == [(2,)] and not following['error']
                            work.execute('ROLLBACK TO SAVEPOINT sr_pending')
                            checks.append({'name':'native-cancel-after-conversion-prevents-user-dispatch','pending_work_preserved':True})
                            helper = client.open_session({'route':{**selected,'autocommit':True}})
                            try:
                                source = ('DELIMITER //\nCREATE PROCEDURE bound_program() BEGIN SELECT %s AS bound_value; END//\n'
                                          'DELIMITER ;\nCALL bound_program();')
                                pages = collect(client, client.execute(helper, {'source':source,'parameters':(text,)}))
                                assert not pages[-1]['payload']['error'], pages[-1]['payload']
                                assert [row for page in pages for row in page['payload']['rows']] == [(text,)]
                                pages = collect(client,client.execute(helper,{'source':'DROP PROCEDURE bound_program'}))
                                assert not pages[-1]['payload']['error']
                            finally: client.close_session(helper)
                            work.execute('ROLLBACK TO SAVEPOINT sr_pending')
                            oracle.execute('SELECT COUNT(*) FROM `' + database + '`.pending'); assert oracle.fetchone() == (1,)
                            checks.append({'name':'native-client-delimiter-bound-program-and-call-on-independent-session'})
                            client.control_transaction(handle, 'rollback')
                            rows, result = sql('SELECT COUNT(*) FROM pending'); assert rows == [(1,)] and not result['error']
                        finally: work.close()
                        proof['interfaces'].append({'label':label,'native_client':type(handle).__name__,
                            'driver_version':str(getattr(client.module,'__version__','unavailable')),
                            'checks':checks,'pending_work_and_savepoint_preserved':True})
                    except Exception as error:
                        proof['failures'].append({'interface':label,'group':'boundaries','error_type':type(error).__name__})
                        (output / ('failure-boundaries-' + label + '.log')).write_text(traceback.format_exc())
                    finally:
                        if instance is not None: instance.client.close()
                        oracle.execute('DROP DATABASE IF EXISTS `' + database + '`')
                    for name, gate in (('native-values',values_gate), ('native-wire',wire_gate)):
                        try:
                            result = gate({**route,'use_pure':pure},output / (name + '-' + label))
                            assert result['complete']
                        except Exception as error:
                            proof['failures'].append({'interface':label,'group':name,'error_type':type(error).__name__})
                            (output / ('failure-' + name + '-' + label + '.log')).write_text(traceback.format_exc())
            finally: oracle.close(); root.close()
        proof.update(complete=not proof['failures'] and owned['owned_server_stopped'],owned_server_stopped=owned['owned_server_stopped'])
    finally: (output / 'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    assert proof['complete'], proof['failures']
    return proof


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    qualify(parser.parse_args().evidence)
