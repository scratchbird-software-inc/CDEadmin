"""MariaDB PREPARE validation without EXECUTE on an independently owned lease."""
from contextlib import contextmanager
import re
import time
from ..workspace.firebird_schema_plan import digest


def identity(connection, plan):
    if type(connection.server_status) is not int or connection.server_status & 1 or connection.autocommit is not True:
        raise ValueError('Native schema operations require an independently owned idle autocommit connection')
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT VERSION(),@@server_uid,DATABASE(),@@character_set_client')
        version, uid, database, charset = cursor.fetchone()
        if (str(version).split('-')[0] != '12.2.2' or uid != plan.get('server_uid') or
                database != plan.get('database') or charset != 'utf8mb4'):
            raise ValueError('Native MariaDB schema connection identity changed')
    finally: cursor.close()


@contextmanager
def prepared(cursor, operation):
    context = operation['context']
    charset = context.get('character_set_client')
    if not isinstance(charset, str) or not re.fullmatch(r'[A-Za-z0-9_]+', charset):
        raise ValueError('Exact native statement character set is required')
    cursor.execute('SELECT CHARACTER_SET_NAME FROM information_schema.CHARACTER_SETS WHERE CHARACTER_SET_NAME=?', (charset,))
    if cursor.fetchall() != [(charset,)]: raise ValueError('Native statement character set is unavailable')
    cursor.execute('SET SESSION sql_mode=?', (context['sql_mode'],))
    cursor.execute('SET SESSION collation_connection=?', (context['collation_connection'],))
    if 'time_zone' in context: cursor.execute('SET SESSION time_zone=?', (context['time_zone'],))
    if 'system_versioning_alter_history' in context:
        if context['system_versioning_alter_history'] != 'KEEP': raise ValueError('Native history alteration requires explicit KEEP policy')
        cursor.execute('SET SESSION system_versioning_alter_history=?', ('KEEP',))
    source = operation['source']
    cursor.execute('SELECT CONVERT(CONVERT(? USING '+charset+') USING utf8mb4)', (source,))
    if cursor.fetchone()[0] != source: raise ValueError('Native statement conversion would lose text')
    acquired = False
    try:
        # Connector/Python remains UTF-8. The native user variable carries the
        # original statement charset into PREPARE, including stored Latin-1 DDL.
        cursor.execute('SET @sr_mariadb_schema=CONVERT(? USING '+charset+')', (source,))
        cursor.execute('PREPARE sr_mariadb_schema FROM @sr_mariadb_schema'); acquired = True
        yield
    finally:
        if acquired: cursor.execute('DEALLOCATE PREPARE sr_mariadb_schema')
        cursor.execute('SET @sr_mariadb_schema=NULL')


def validate(connection, plan):
    operations = plan.get('operations')
    if (plan.get('format') != 'scratchrobin.mariadb.schema-plan@1' or not plan.get('ready_for_review') or
            not isinstance(operations, list) or not 1 <= len(operations) <= 32 or
            sum(len(row['source'].encode('utf8')) for row in operations) > 1024*1024 or
            plan.get('execution_sha256') != digest(operations)):
        raise ValueError('Native validation requires 1 to 32 exact unblocked statements within 1 MiB')
    identity(connection, plan)
    cursor = connection.cursor(); results = []; started = time.monotonic()
    try:
        cursor.execute('SET SESSION lock_wait_timeout=2')
        for index, operation in enumerate(operations):
            if time.monotonic()-started > 30: raise ValueError('Native validation exceeds 30 seconds')
            try:
                with prepared(cursor, operation): pass
                results.append({'index': index, 'resource_id': operation['resource_id'], 'accepted': True, 'validation_stage': 'prepared'})
            except Exception as error:
                code = getattr(error, 'errno', None)
                if code is None or code in {2006, 2013, 2055}: raise
                results.append({'index': index, 'resource_id': operation['resource_id'], 'accepted': False,
                    'validation_stage': 'rejected', 'error_code': code, 'error_type': type(error).__name__})
    finally: cursor.close()
    return {'native_grammar_validated': all(row['accepted'] for row in results), 'native_validation': results,
        'validation_mode': 'native-MariaDB-PREPARE-without-EXECUTE', 'executed': False, 'application_supported': False}
