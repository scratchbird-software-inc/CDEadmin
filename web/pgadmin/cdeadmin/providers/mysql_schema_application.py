"""Single native DDL dispatch with table-lock revalidation and rediscovery."""
from ..workspace.firebird_schema_plan import digest
from ..workspace.mysql_schema_plan import address, alteration, creation, schema
from .mysql_family.mysql_catalog import identifier
from .mysql_statement_encoding import statement_context
import hashlib


def apply_review(connection, record):
    dispatched = acknowledged = locked = False
    advisory = None
    cursor = None
    result = {'state': 'not_dispatched', 'rediscovery_verified': False,
              'automatic_retry': False, 'transactional_rollback_available': False}
    try:
        if connection.in_transaction:
            raise ValueError('Application requires an independently owned idle connection')
        plan = record['plan']
        operations = plan['operations']
        if (plan.get('format') != 'scratchrobin.mysql.schema-plan@1' or len(operations) != 1 or
                plan['execution_sha256'] != digest(operations) or not plan.get('native_grammar_validated')):
            raise ValueError('Exact native-validated single-table plan is required')
        operation = operations[0]
        key = operation['resource_id']
        before, after = record['baseline']['rows'].get(key), record['desired']['rows'][key]
        database = plan['database']
        if before is not None:
            address(before, database)
        address(after, database)
        if after['kind'] not in {'table','view'} or (before is not None and before['kind'] != after['kind']):
            raise ValueError('Only exact user table/view definitions are admitted')
        context = operation['context']
        target = identifier(database) + '.' + identifier(after['name'])
        if after['kind']=='view':
            from ..workspace.mysql_view_plan import compile_view
            if (operation['operation']=='create') != (before is None):
                raise ValueError('Native view operation disagrees with baseline presence')
            compiled=compile_view(after,operation['operation'],database)
        elif operation['operation'] == 'create' and before is None and not after['native'].get('mysql_change'):
            compiled = creation(after, context['sql_mode'], database)
        elif operation['operation'] == 'alter' and before is not None:
            compiled = alteration(before, after, context['sql_mode'])
        elif operation['operation'] == 'drop' and before is not None and after['native'].get('mysql_change') == {
                'action': 'drop', 'confirmation': before['name']}:
            compiled = 'DROP TABLE ' + target
        else:
            raise ValueError('Unsupported native application operation')
        if (compiled != operation['source'] or
                (digest(schema(before)) if before is not None else None) != operation['baseline_schema_sha256'] or
                digest(schema(after)) != operation['desired_schema_sha256']):
            raise ValueError('Reviewed native statement or baseline fingerprint changed')
        connection.autocommit = True
        connection.sql_mode = context['sql_mode']
        connection.set_charset_collation(charset='utf8mb4', collation='utf8mb4_0900_ai_ci')
        cursor = connection.cursor()
        cursor.execute('SET SESSION lock_wait_timeout=2')
        cursor.execute('SET SESSION sql_quote_show_create=1')
        cursor.execute('SELECT VERSION(), @@server_uuid, DATABASE()')
        identity = cursor.fetchone()
        if str(identity[0]).split('-')[0] != '9.7.0' or identity[1] != plan['server_uuid'] or identity[2] != database:
            raise ValueError('Native application connection identity changed')
        if before is None:
            try:
                cursor.execute('SHOW CREATE TABLE ' + target)
                cursor.fetchone()
            except Exception as error:
                if getattr(error, 'errno', None) != 1146:
                    raise
            else:
                raise ValueError('Native creation target already exists')
        else:
            if after['kind']=='view':
                advisory='sr-ddn-view:'+hashlib.sha256(target.encode('utf8')).hexdigest()[:48]
                cursor.execute('SELECT GET_LOCK(%s,2)',(advisory,))
                if cursor.fetchone()[0]!=1:
                    advisory=None
                    raise ValueError('Native view advisory lock is unavailable')
                result['concurrent_external_ddl_fenced']=False
                result['concurrency_warning']='View baseline is observational; external DDL can change the view before dispatch'
            else:
                cursor.execute('LOCK TABLES ' + target + ' WRITE')
                locked = True
            cursor.execute('SHOW CREATE TABLE ' + target)
            observed = cursor.fetchone()
            if not observed or digest({'definition': observed[1], 'definition_context': before['native'].get('definition_context')}) != operation['baseline_schema_sha256']:
                raise ValueError('Locked native object changed since review')
            if after['kind']=='view' and (len(observed)<4 or any(
                    before['native'].get('definition_context',{}).get(field)!=observed[index]
                    for field,index in [('character_set_client',2),('collation_connection',3)])):
                raise ValueError('Locked native view creation context changed since review')
        with statement_context(connection, cursor, compiled, context) as encoded:
            dispatched = True
            cursor.execute(encoded)
            acknowledged = True
            result['state'] = 'committed'
        if operation['operation'] == 'drop':
            try:
                cursor.execute('SHOW CREATE TABLE ' + target)
                cursor.fetchone()
            except Exception as error:
                if getattr(error, 'errno', None) == 1146:
                    result['rediscovery_verified'] = True
                else:
                    raise
        else:
            cursor.execute('SHOW CREATE TABLE ' + target)
            observed = cursor.fetchone()
            if not observed:
                raise ValueError('Native rediscovery returned no table')
            result.update(rediscovery_verified=True, native_definition=observed[1],
                desired_definition_exact_match=observed[1] == after['native']['definition'])
    except Exception as error:
        # An error after dispatch may be a lost acknowledgement. Never infer
        # rollback or retry from a native error, broken link or process restart.
        result['state'] = 'committed' if acknowledged else 'unknown_outcome' if dispatched else 'not_dispatched'
        result.update(error_type=type(error).__name__, error_code=getattr(error, 'errno', None))
        if not dispatched and isinstance(error, ValueError):
            result['rejection_reason'] = str(error)
    finally:
        if cursor is not None:
            if advisory is not None:
                try:
                    cursor.execute('SELECT RELEASE_LOCK(%s)',(advisory,))
                    cursor.fetchone()
                except Exception as error:
                    result['cleanup_error_type']=type(error).__name__
            if locked:
                try:
                    cursor.execute('UNLOCK TABLES')
                except Exception as error:
                    result['cleanup_error_type'] = type(error).__name__
            try:
                cursor.close()
            except Exception as error:
                result['cleanup_error_type'] = type(error).__name__
    return result
