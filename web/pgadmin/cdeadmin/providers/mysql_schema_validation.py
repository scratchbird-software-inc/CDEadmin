"""Native PREPARE-only validation for server-compiled MySQL metadata previews."""
import time
from .mysql_statement_encoding import statement_context


def validate(connection,plan):
    if connection.in_transaction:raise ValueError('Validation requires an independently owned idle connection')
    if (plan.get('format')!='scratchrobin.mysql.schema-plan@1' or not plan.get('ready_for_review') or
        not isinstance(plan.get('operations'),list) or not 1<=len(plan['operations'])<=32 or
        sum(len(row['source'].encode('utf8')) for row in plan['operations'])>1024*1024):
        raise ValueError('Native validation requires 1 to 32 unblocked operations within 1 MiB')
    connection.autocommit=True
    cursor=connection.cursor();results=[];started=time.monotonic()
    try:
        cursor.execute('SELECT VERSION(), @@server_uuid, DATABASE()');identity=cursor.fetchone()
        if str(identity[0]).split('-')[0]!='9.7.0' or identity[1]!=plan['server_uuid'] or identity[2]!=plan['database']:
            raise ValueError('Native validation connection identity changed')
        cursor.execute('SET SESSION lock_wait_timeout=2')
        for index,operation in enumerate(plan['operations']):
            if time.monotonic()-started>30:raise ValueError('Native validation exceeds 30 seconds')
            context=operation['context']
            connection.sql_mode=context['sql_mode']
            if 'time_zone' in context:connection.time_zone=context['time_zone']
            prepared=False
            try:
                with statement_context(connection, cursor, operation['source'], context) as encoded:
                    cursor.execute('SET @sr_native_preview = %s',(encoded,))
                    cursor.execute('PREPARE sr_native_preview FROM @sr_native_preview');prepared=True
                results.append({'resource_id':operation['resource_id'],'index':index,'accepted':True,
                    'preparation_supported':True,'validation_stage':'prepared'})
            except Exception as error:
                code=getattr(error,'errno',None)
                if code is None or code in {2006,2013,2055}:raise
                # MySQL 9.7 parses the whole ALTER VIEW before its explicit
                # unsupported-preparation branch. Admit only this qualified path;
                # a 1295 on any other operation remains a validation failure.
                parsed_view=(code==1295 and operation.get('kind')=='view' and
                    operation.get('operation')=='alter' and operation['source'].lstrip().startswith('ALTER '))
                results.append({'resource_id':operation['resource_id'],'index':index,'accepted':parsed_view,
                    'preparation_supported':False,'validation_stage':'parse-only' if parsed_view else 'rejected',
                    'error_code':code,'sqlstate':getattr(error,'sqlstate',None),'error_type':type(error).__name__})
            finally:
                if prepared:cursor.execute('DEALLOCATE PREPARE sr_native_preview')
                cursor.execute('SET @sr_native_preview = NULL')
    finally:cursor.close()
    return {'native_grammar_validated':all(row['accepted'] for row in results),'native_validation':results,
        'validation_mode':'native-PREPARE-without-EXECUTE;view-ALTER-1295-parse-only','executed':False,'application_supported':False}
