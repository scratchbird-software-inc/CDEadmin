"""Single native MariaDB table change with exact baseline and durable host receipts."""
import hashlib
from ..workspace.firebird_schema_plan import digest
from ..workspace.mariadb_schema_plan import compile_table, schema
from .mysql_family.mariadb_catalog import identifier
from .mariadb_schema_validation import identity, prepared


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
        compiled = compile_table(before, after, operation['operation'], operation['context'], plan['database'])
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
        # Use the exact recorded retrieval mode, not the current browser mode.
        cursor.execute('SET SESSION sql_mode=?', (operation['context']['sql_mode'],))
        cursor.execute('SET SESSION collation_connection=?', (operation['context']['collation_connection'],))
        try:
            cursor.execute('SHOW CREATE TABLE '+target); observed = cursor.fetchone()
        except Exception as error:
            if getattr(error, 'errno', None) != 1146: raise
            observed = None
        if (before is None and observed is not None) or (before is not None and
                (observed is None or observed[1] != before['native']['definition'])):
            raise ValueError('Live native target changed since baseline')
        with prepared(cursor, operation):
            dispatched = True
            cursor.execute('EXECUTE sr_mariadb_schema')
            acknowledged = True; result['state'] = 'committed'
        try:
            cursor.execute('SHOW CREATE TABLE '+target); observed = cursor.fetchone()
        except Exception as error:
            if operation['operation'] != 'drop' or getattr(error, 'errno', None) != 1146: raise
            observed = None
        result['rediscovery_verified'] = (observed is None if operation['operation'] == 'drop' else observed is not None)
        if observed:
            result.update(native_definition=observed[1], desired_definition_exact_match=observed[1] == after['native']['definition'])
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
