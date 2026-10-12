"""Single native DDL dispatch with table-lock revalidation and rediscovery."""
from ..workspace.firebird_schema_plan import digest
from ..workspace.mysql_schema_plan import address, alteration, creation, schema
from .mysql_family.mysql_catalog import identifier


def apply_review(connection, record):
    dispatched = acknowledged = locked = False
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
        if (before is not None and before['kind'] != 'table') or after['kind'] != 'table':
            raise ValueError('Only exact user table definitions are admitted')
        context = operation['context']
        target = identifier(database) + '.' + identifier(after['name'])
        if operation['operation'] == 'create' and before is None and not after['native'].get('mysql_change'):
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
        if context['character_set_client'] not in {'utf8mb4', 'utf8mb3', 'utf8'}:
            raise ValueError('Application needs an admitted UTF-8 encoding context')
        connection.autocommit = True
        connection.sql_mode = context['sql_mode']
        connection.set_charset_collation(charset=context['character_set_client'],
                                         collation=context['collation_connection'])
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
            cursor.execute('LOCK TABLES ' + target + ' WRITE')
            locked = True
            cursor.execute('SHOW CREATE TABLE ' + target)
            observed = cursor.fetchone()
            if not observed or digest({'definition': observed[1], 'definition_context': before['native'].get('definition_context')}) != operation['baseline_schema_sha256']:
                raise ValueError('Locked native table changed since review')
        dispatched = True
        cursor.execute(compiled)
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
