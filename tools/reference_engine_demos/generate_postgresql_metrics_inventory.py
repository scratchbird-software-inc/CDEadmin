"""Independent PostgreSQL18.3 native statistics view/column inventory."""
from pathlib import Path
import re

from .generate_postgresql_dialect_inventory import sha256

EXTRA_VIEWS={'pg_locks','pg_prepared_xacts','pg_replication_slots','pg_settings','pg_backend_memory_contexts',
             'pg_shmem_allocations','pg_wait_events','pg_cursors','pg_prepared_statements'}
NUMERIC={'smallint','integer','bigint','real','double precision','numeric'}
IDENTIFIERS={'pid','leader_pid','datid','relid','index_relid','objid','objsubid','classid','oid','usesysid',
             'subid','client_port','sync_priority','timeline_id','receive_start_tli','received_tli','level',
             'current_locker_pid','current_child_table_relid','transaction','query_id','sender_port','off'}
REDACT={'query','statement','conninfo','ident'}


def metric(view,column,value_type):
    if column in IDENTIFIERS or column.endswith(('_pid','_oid','_tli')) or value_type not in NUMERIC|{'interval'}:
        return None
    if view in {'pg_locks','pg_stat_ssl','pg_stat_gssapi','pg_settings','pg_prepared_xacts','pg_wait_events','pg_cursors'}:
        return None
    unit='events'
    if value_type=='interval':unit='seconds'
    elif 'bytes' in column or column in {'size','allocated_size','safe_wal_size','backup_total','backup_streamed','wal_distance'}:unit='bytes'
    elif 'time' in column:unit='milliseconds'
    elif column in {'numbackends'}:unit='connections'
    elif any(token in column for token in ('blks','blocks','buffers')) or column in {'hits','evictions','reuses'}:unit='blocks'
    elif any(token in column for token in ('tup','row')) or column in {'n_mod_since_analyze','n_ins_since_vacuum'}:unit='rows'
    elif 'tablespaces' in column:unit='tablespaces'
    elif 'tables' in column or 'partitions' in column:unit='relations'
    elif 'lockers' in column:unit='backends'
    elif 'indexes' in column:unit='indexes'
    elif column in {'generic_plans','custom_plans'}:unit='plans'
    elif view=='pg_stat_archiver':unit='files'
    elif 'chunks' in column or 'contexts' in column:unit='allocations'
    elif column in {'reads','writes','writebacks','extends','fsyncs','flushes','truncates'}:unit='operations'
    gauge=(view.startswith('pg_stat_progress_') or view in {'pg_backend_memory_contexts','pg_shmem_allocations','pg_replication_slots','pg_stat_replication','pg_stat_wal_receiver'} or
           column in {'numbackends','n_live_tup','n_dead_tup'} or view=='pg_stat_recovery_prefetch' and column in {'wal_distance','block_distance','io_depth'})
    reset=('native_current_transaction_end' if view.startswith('pg_stat_xact_') else 'native_prepared_statement_lifetime' if view=='pg_prepared_statements' else
        'native_analyze' if column=='n_mod_since_analyze' else 'native_vacuum' if column=='n_ins_since_vacuum' else
        'current_native_state_or_operation' if gauge else 'native_statistics_reset_or_object_lifecycle')
    return {'unit':unit,'kind':'gauge' if gauge else 'counter',
        'reset_behavior':reset,
        'aggregation':'retain_native_row_dimensions; no cross-database or cross-reset sum'}


def generate(source,connection):
    from psycopg import Cursor
    from psycopg.rows import tuple_row
    from psycopg import sql
    source=Path(source);path=source/'src/backend/catalog/system_views.sql'
    source_views=set(re.findall(r'(?m)^CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(pg_[a-z_0-9]+)\s',path.read_text()))
    expected={name for name in source_views if name.startswith(('pg_stat_','pg_statio_')) or name in EXTRA_VIEWS}
    if not EXTRA_VIEWS.issubset(expected):raise RuntimeError('Native PostgreSQL diagnostic view source inventory is incomplete')
    if connection.info.transaction_status!=0:raise ValueError('Metrics inventory requires an owned idle connection')
    with Cursor(connection,row_factory=tuple_row) as query:
        query.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        try:
            query.execute('SHOW server_version_num')
            if str(query.fetchone()[0])!='180003':raise RuntimeError('Metrics inventory requires native PostgreSQL18.3')
            query.execute("SELECT c.relname,a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod),a.attnum "
                "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                "JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid WHERE n.nspname='pg_catalog' AND c.relkind='v' "
                "AND a.attnum>0 AND NOT a.attisdropped AND (c.relname ~ '^pg_(stat_|statio_)' OR c.relname=ANY(%s)) "
                "ORDER BY c.relname,a.attnum",(sorted(EXTRA_VIEWS),))
            rows=query.fetchall()
        finally:query.execute('ROLLBACK')
    observed={row[0] for row in rows}
    if observed!=expected:raise RuntimeError('Native PostgreSQL metrics views differ from the pinned source inventory: '+str(sorted(observed^expected)))
    endpoints={name:{'endpoint_id':name,'scope':'collector-session' if name in {'pg_backend_memory_contexts','pg_cursors','pg_prepared_statements'} or name.startswith('pg_stat_xact_') else
        'connection-database' if name.startswith(('pg_statio_','pg_stat_all_','pg_stat_sys_','pg_stat_user_')) else 'server',
        'source':'pg_catalog.'+name,'columns':[],'metrics':[]} for name in sorted(expected)}
    for view,column,value_type,ordinal in rows:
        item={'name':column,'value_type':value_type,'ordinal':int(ordinal),'redaction':'query_or_credential_text' if column in REDACT else 'none'}
        if view=='pg_settings' and column in {'setting','reset_val','boot_val'}:item['redaction']='string_settings_redacted; numeric_boolean_enum_preserved'
        classification=metric(view,column,value_type)
        if classification is not None:
            item['metric']=classification
            if value_type=='interval':item['wire_value_type']='native_interval_epoch_seconds_text'
        endpoints[view]['columns'].append(item)
    for view,item in endpoints.items():
        projections=[]
        for column in item['columns']:
            name=column['name'];identifier=sql.Identifier(name)
            if column['redaction']=='query_or_credential_text':expression=sql.SQL('NULL::text')
            elif view=='pg_settings' and name in {'setting','reset_val','boot_val'}:
                expression=sql.SQL("CASE WHEN vartype IN ('bool','integer','real','enum') THEN {}::text ELSE NULL::text END").format(identifier)
            elif column['value_type']=='interval' and column.get('metric'):
                expression=sql.SQL('extract(epoch FROM {})::text').format(identifier)
            else:expression=sql.SQL('{}::text').format(identifier)
            projections.append(sql.SQL('{} AS {}').format(expression,identifier))
        item['native_query']=sql.SQL('SELECT {} FROM pg_catalog.{}').format(sql.SQL(',').join(projections),sql.Identifier(view)).as_string(connection)
    return {'schema':'cdeadmin.engine-metrics-inventory.v1','inventory_id':'postgresql.metrics-inventory.18.3.v1','engine_id':'postgresql',
        'reference_version':'18.3','source_evidence':{'system_views_sha256':sha256(path),
            'monitoring_documentation_sha256':sha256(source/'doc/src/sgml/monitoring.sgml')},
        'completeness':{'source_views_exhausted':True,'runtime_catalogs_exhausted':True,'source_view_count':len(expected),
            'native_observation_count':len(rows),'scope':'Core pg_catalog statistics and diagnostic views of the observed18.3 installation; optional extension views require their own inventory.'},
        'endpoints':list(endpoints.values())}
