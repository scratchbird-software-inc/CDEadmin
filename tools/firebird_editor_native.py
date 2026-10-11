"""Native comparison of original and whitespace-formatted Firebird source."""
import json
from pathlib import Path
import subprocess
import time


def qualify(connection, client, route):
    source = Path(__file__).resolve().parents[1] / 'web/pgadmin/static/js/cdeadmin_ui/editors/firebirdFormatting.js'
    cases = [
        "select q'{line 1\n'quoted'; -- literal}' from rdb$database",
        'select 1e+2 as "END""name", .5, x\'ABCD\' from rdb$database',
        "execute block returns (v varchar(40)) as begin v = ' a  b '; suspend; end",
        'select 1 -- preserve  comment\nfrom rdb$database /* preserve\ncomment */',
        "select case when 1 = 1 then 'yes' else 'no' end from rdb$database",
    ]
    runner = """
import {readFileSync} from 'node:fs';
const source = readFileSync(process.argv[1]);
const formatURL = 'data:text/javascript;base64,' + source.toString('base64');
const module = await import(formatURL);
const executionSource = readFileSync(process.argv[3], 'utf8').replace("'./firebirdFormatting'", JSON.stringify(formatURL));
const execution = await import('data:text/javascript;base64,' + Buffer.from(executionSource).toString('base64'));
const values = JSON.parse(process.argv[2]);
const script = 'SET SQL DIALECT 3; SET AUTO OFF; SET BAIL ON; INSERT INTO MUST_NOT_EXECUTE VALUES (1); COMMIT; SELECT 2 FROM RDB$DATABASE; SELECT 3 FROM RDB$DATABASE;';
process.stdout.write(JSON.stringify({formatted: values.map(value => module.formatFirebird(value)),
  prepared: execution.firebirdExecution(script, 'from-cursor', script.indexOf('SELECT 2') + 4)}));
"""
    process = subprocess.run(['node', '--input-type=module', '-e', runner, str(source), json.dumps(cases),
                              str(source.with_name('firebirdExecution.js'))],
                             capture_output=True, text=True, check=True, timeout=15)
    generated = json.loads(process.stdout)
    formatted = generated['formatted']
    for original, revised in zip(cases, formatted):
        with connection.cursor() as cursor:
            cursor.execute(original)
            before = cursor.fetchall()
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute(revised)
            after = cursor.fetchall()
        connection.rollback()
        assert before == after, (original, revised)
    handle = client.open_session({'route': route})
    try:
        with handle.cursor() as cursor:
            cursor.execute('CREATE TABLE EDITOR_KEEP (ID INTEGER)')
        handle.commit()
        with handle.cursor() as cursor:
            cursor.execute('INSERT INTO EDITOR_KEEP VALUES (1)')
        transaction_id = handle.main_transaction.info.id
        assert generated['prepared']['scriptMode'] is True
        query = client.submit_query(handle, {'source': generated['prepared']['source'], 'parameters': [],
            'output_policy': {'firebird_script': True}})
        deadline = time.monotonic() + 30
        while not query.done and time.monotonic() < deadline:
            time.sleep(.02)
        assert query.done, 'Prepared editor script timed out'
        result = client.describe_result(query)['payload']
        assert result['execution_state'] == 'succeeded', result
        assert not result['script']['had_errors'], result
        assert handle.main_transaction.info.id == transaction_id
        handle.rollback()
        with handle.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM EDITOR_KEEP')
            assert cursor.fetchone() == (0,)
        handle.rollback()
    finally:
        client.close_session(handle)
    return {'passed': True, 'native_cases': len(cases), 'formatted_source': formatted,
            'original_and_formatted_native_values_equal': True,
            'from_cursor_native_script_executed': True, 'prior_sql_and_commit_not_replayed': True,
            'pending_user_transaction_rollback_preserved': True}
