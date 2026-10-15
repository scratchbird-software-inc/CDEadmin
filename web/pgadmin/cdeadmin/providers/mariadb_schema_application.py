"""Single native MariaDB object change with exact baseline and durable host receipts."""
import hashlib
from ..workspace.firebird_schema_plan import digest
from ..workspace.mariadb_schema_plan import compile_table, schema, address
from .mysql_family.mariadb_catalog import identifier
from .mariadb_schema_validation import identity, prepared
from ..workspace.mariadb_object_plan import compile_object
from .mysql_family.mariadb_catalog import capture


def observed(connection, database, kind, name):
    result=capture(connection,database)
    rows=[{'resource_id':row['resource_id'],'kind':row['resource_kind'],'name':row['display_name'],
        'path':row['display_path'],'system':'false' if row['native'].get('system_object') is False else 'true',
        'native':row['native']} for row in result['resources']]
    matches=[row for row in rows if row['kind']==kind and row['name']==name]
    if len(matches)>1:raise ValueError('Native named object identity is ambiguous')
    return (matches[0] if matches else None),rows


def apply_review(connection, record):
    cursor = None; advisory = None; dispatched = acknowledged = False
    result = {'state': 'not_dispatched', 'rediscovery_verified': False,
        'automatic_retry': False, 'transactional_rollback_available': False,
        'concurrent_external_ddl_fenced': False,
        'concurrency_warning': 'Cooperating advisory lock only. An exclusive external DDL maintenance window is required.'}
    try:
        plan = record['plan']; operations = plan['operations']
        if (plan.get('format') != 'scratchrobin.mariadb.schema-plan@1' or len(operations) != 1 or
                plan.get('execution_sha256') != digest(operations) or not plan.get('native_grammar_validated')):
            raise ValueError('Exact native-validated single-object plan is required')
        operation = operations[0]; key = operation['resource_id']
        before, after = record['baseline']['rows'].get(key), record['desired']['rows'][key]
        if any(operation.get(field) != value for field, value in [('kind', after['kind']), ('name', after['name']), ('database', plan['database'])]):
            raise ValueError('Reviewed operation target disagrees with its native identity')
        address(after,plan['database'])
        if before is not None:address(before,plan['database'])
        compiled = (compile_table(before,after,operation['operation'],operation['context'],plan['database']) if after['kind']=='table' else
            compile_object(before,after,operation['operation'],plan['database'],operation.get('trigger_order')))
        if (compiled != operation['source'] or
                operation['baseline_schema_sha256'] != (digest(schema(before)) if before is not None else None) or
                operation['desired_schema_sha256'] != digest(schema(after))):
            raise ValueError('Reviewed native statement or baseline changed')
        identity(connection, plan)
        cursor = connection.cursor()
        cursor.execute('SET SESSION lock_wait_timeout=2')
        cursor.execute('SET SESSION sql_quote_show_create=1')
        target = identifier(plan['database'])+'.'+identifier(operation['name'])
        lock = 'sr-maria-ddn:'+hashlib.sha256(target.encode('utf8')).hexdigest()[:48]
        cursor.execute('SELECT GET_LOCK(?,2)', (lock,))
        if cursor.fetchone()[0] != 1: raise ValueError('Native cooperating DDL lock is unavailable')
        advisory = lock
        current,rows=observed(connection,plan['database'],after['kind'],after['name'])
        if (before is None and current is not None) or (before is not None and
                (current is None or current['resource_id']!=key or schema(current)!=schema(before))):
            raise ValueError('Live native target changed since baseline')
        if after['kind']=='trigger' and operation.get('trigger_order_baseline') is not None:
            facts=after['native']['trigger_identity']
            grouping=tuple(facts.get(field) for field in ('database','table','timing','event'))
            siblings=[{'name':row['name'],'identity':row['native']['trigger_identity']} for row in sorted(rows,key=lambda row:row['name'])
                if row['kind']=='trigger' and tuple(row['native'].get('trigger_identity',{}).get(field)
                    for field in ('database','table','timing','event'))==grouping]
            if siblings!=operation['trigger_order_baseline']:
                raise ValueError('Live native trigger sibling order changed since review')
        with prepared(cursor, operation):
            dispatched = True
            cursor.execute('EXECUTE sr_mariadb_schema')
            acknowledged = True; result['state'] = 'committed'
        current,_rows=observed(connection,plan['database'],after['kind'],after['name'])
        result['rediscovery_verified'] = (current is None if operation['operation']=='drop' else
            current is not None and current['resource_id']==key and isinstance(current['native'].get('definition'),str))
        if current:
            result.update(native_definition=current['native'].get('definition'),
                desired_definition_exact_match=current['native'].get('definition')==after['native'].get('definition'),
                desired_schema_exact_match=schema(current)==schema(after))

    except Exception as error:
        result.update(state='committed' if acknowledged else 'unknown_outcome' if dispatched else 'not_dispatched',
            error_type=type(error).__name__, error_code=getattr(error, 'errno', None))
        if not dispatched and isinstance(error, ValueError): result['rejection_reason'] = str(error)
    finally:
        if cursor is not None:
            try:
                if advisory is not None:
                    cursor.execute('SELECT RELEASE_LOCK(?)', (advisory,)); cursor.fetchone()
            except Exception as error: result['cleanup_error_type'] = type(error).__name__
            try: cursor.close()
            except Exception as error: result['cleanup_error_type'] = type(error).__name__
    return result
