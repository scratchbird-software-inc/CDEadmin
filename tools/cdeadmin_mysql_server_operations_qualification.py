"""Qualify exact native MySQL configuration scopes and owned session control."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))
import config  # noqa: F401
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MYSQL_PROFILE, _resources


def qualify(options, output, descriptor_inputs=False):
    output.mkdir(parents=True, exist_ok=True)
    connection = mysql.connector.connect(**{**options, 'autocommit': True})
    recipient = mysql.connector.connect(**{**options, 'autocommit': True})
    cursor = connection.cursor()
    proof = {'passed': False, 'statements': {}, 'checks': []}
    root=Path(__file__).resolve().parents[1]
    proof.update(descriptor_inputs=descriptor_inputs,actual_operation_dialog_qualified=False,
        source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in (
            'web/pgadmin/cdeadmin/providers/mysql_server_operations.py',
            'web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
            str(Path(__file__).relative_to(root)))})
    if descriptor_inputs:
        from ui_descriptor_roundtrip import backend_draft,engine_operations,operation_draft
        declarations=engine_operations('mysql')
    worker = None
    variable = 'max_execution_time'
    cursor.execute('SELECT @@GLOBAL.max_execution_time')
    original = cursor.fetchone()[0]
    cursor.execute('SELECT @@GLOBAL.long_query_time')
    original_decimal = cursor.fetchone()[0]
    cursor.execute('SELECT VARIABLE_VALUE FROM performance_schema.persisted_variables WHERE VARIABLE_NAME=%s', (variable,))
    persisted = cursor.fetchone()
    def execute(kind, operation, draft, target):
        if descriptor_inputs:
            declaration=declarations[operation+'@'+kind]
            values={key:value for key,value in draft.items() if key!='value'}
            if 'value' in draft:
                value=draft['value'];mode=draft.get('value_type','AUTO')
                if mode=='AUTO':mode='BOOLEAN' if type(value) is bool else 'SAFE_INTEGER' if type(value) is int else 'TEXT'
                values.update(value_type=mode)
                values[{'BOOLEAN':'value_boolean','SAFE_INTEGER':'value_integer'}.get(mode,'value_text')]=value
            draft=backend_draft({'tabs':[{'fields':declaration['fields']}]},operation_draft(declaration,values,target['display_name']))
        request = {'resource_kind': kind, 'operation_id': operation, 'draft': draft,
                   'target_resource': target, '_provider_route': {'host': options.get('host', 'localhost')}}
        assert not MYSQL_ADMINISTRATION.validate(request)['errors']
        compiled = MYSQL_ADMINISTRATION._compile(request)['statements'][0]
        preview = MYSQL_ADMINISTRATION.plan(request)['command_preview']['statements'][0]
        if compiled['parameters']: assert preview['parameters_redacted'] and '<redacted>' in preview['source']
        cursor.execute(compiled['source'], compiled['parameters'] or None)
        from tools.mysql_task_evidence import record
        record(proof, request)
        proof['statements'].setdefault(operation, compiled['source'])
    try:
        cursor.execute('SELECT VERSION()')
        assert str(cursor.fetchone()[0]).split('-')[0] == '9.7.0'
        target = {'display_name': variable}
        execute('system-variable', 'set_global', {'value': '0.125', 'value_type': 'DECIMAL'}, {'display_name': 'long_query_time'})
        cursor.execute('SELECT @@GLOBAL.long_query_time')
        assert cursor.fetchone()[0] == 0.125
        cursor.execute('SET GLOBAL long_query_time=%s', (original_decimal,))
        execute('system-variable', 'set_global', {'value': int(original)+10000}, target)
        cursor.execute('SELECT @@GLOBAL.max_execution_time')
        assert cursor.fetchone()[0] == int(original)+10000
        execute('system-variable', 'set_persist_only', {'value': str(original), 'value_type': 'INTEGER'}, target)
        cursor.execute('SELECT @@GLOBAL.max_execution_time')
        assert cursor.fetchone()[0] == int(original)+10000
        cursor.execute('SELECT VARIABLE_VALUE FROM performance_schema.persisted_variables WHERE VARIABLE_NAME=%s', (variable,))
        assert cursor.fetchone()[0] == str(original)
        execute('system-variable', 'set_persist', {'value': original}, target)
        cursor.execute('SELECT @@GLOBAL.max_execution_time')
        assert cursor.fetchone()[0] == original
        execute('system-variable', 'reset_persist', {}, target)
        cursor.execute('SELECT COUNT(*) FROM performance_schema.persisted_variables WHERE VARIABLE_NAME=%s', (variable,))
        assert cursor.fetchone()[0] == 0
        owned = recipient.cursor()
        owned.execute('SELECT CONNECTION_ID()')
        process = str(owned.fetchone()[0])
        native_target = {'display_name': process, 'native': {'processlist_id': process}}
        errors, results = [], []
        def run_query():
            try:
                owned.execute('SELECT 1+SLEEP(20)')
                results.extend(owned.fetchall())
            except mysql.connector.Error as error:
                errors.append(error.errno)
        worker = threading.Thread(target=run_query)
        worker.start()
        for attempt in range(100):
            cursor.execute('SELECT PROCESSLIST_STATE FROM performance_schema.threads WHERE PROCESSLIST_ID=%s', (process,))
            state = cursor.fetchone()
            if state and state[0] == 'User sleep': break
            time.sleep(0.02)
        else: raise AssertionError('Owned native query never became active')
        execute('session', 'terminate_query', {}, native_target)
        worker.join(timeout=5)
        assert not worker.is_alive() and (errors == [1317] or (not errors and results == [(2,)])), (errors, results)
        proof['query_interruption'] = {'native_error_codes': errors, 'native_result': results}
        owned.execute('SELECT CONNECTION_ID()')
        assert str(owned.fetchone()[0]) == process
        resources = _resources(connection, {'route': {}}, MYSQL_PROFILE)
        configuration = [row for row in resources if row['resource_kind']=='system-variable']
        sessions = [row for row in resources if row['resource_kind']=='session']
        assert any(row['display_name']==variable for row in configuration)
        assert any(row['native'].get('processlist_id')==process and isinstance(row['native'].get('thread_id'),str) for row in sessions)
        execute('session', 'terminate_connection', {}, native_target)
        try: owned.execute('SELECT 1')
        except mysql.connector.Error as error: assert error.errno in {2006,2013,2055,4031}
        else: raise AssertionError('Killed owned native connection remained usable')
        owned.close()
        proof.update(passed=True, checks=['native generated operation plans', 'bound values redacted from preview', 'JSON-safe exact numeric casts preserve native variable input types',
            'SET GLOBAL current value', 'PERSIST_ONLY leaves current value unchanged', 'PERSIST current and persisted value',
            'RESET PERSIST selected override', 'KILL QUERY interrupts owned query and preserves attachment',
            'KILL CONNECTION disconnects only the owned test attachment', 'native variable and session catalog rediscovery'])
    finally:
        if worker is not None and worker.is_alive():
            recipient.close()
            worker.join(timeout=5)
        cursor.execute('SET GLOBAL long_query_time=%s', (original_decimal,))
        cursor.execute('SET GLOBAL max_execution_time=%s', (original,))
        if persisted is None: cursor.execute('RESET PERSIST IF EXISTS max_execution_time')
        else: cursor.execute('SET PERSIST_ONLY max_execution_time=%s', (int(persisted[0]),))
        cursor.close()
        recipient.close()
        connection.close()
        proof['original_configuration_restored'] = True
        (output/'summary.json').write_text(json.dumps(proof, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-json', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--descriptor-inputs',action='store_true')
    args = parser.parse_args()
    qualify(json.loads(args.connection_json.read_text()), args.output_root,args.descriptor_inputs)
