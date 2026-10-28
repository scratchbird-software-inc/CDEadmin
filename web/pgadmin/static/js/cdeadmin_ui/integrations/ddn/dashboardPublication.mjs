import {METRIC_COLUMNS,metricChannel} from './dashboardPanels.js';
// Shared browser/host validation against the paired public DDN API.
export const COUNTER_FIELDS = Object.freeze({
  io: ['page_reads', 'page_writes', 'page_fetches', 'page_marks'],
  records: ['record_seq_reads', 'record_idx_reads', 'record_inserts', 'record_updates',
    'record_deletes', 'record_backouts', 'record_purges', 'record_expunges',
    'record_locks', 'record_waits', 'record_conflicts', 'backversion_reads',
    'fragment_reads', 'record_rpt_reads', 'record_imgc'],
  memory: ['memory_used', 'memory_allocated', 'max_memory_used', 'max_memory_allocated'],
});
const counts = {engine: {inventory: 8}, server: {status: 10, server: 6},
  database: {status: 10, database: 10, attachments: 6, transactions: 4,
    io: 4, records: 15, memory: 4, storage: 5, protection: 7}};
const postgresCounts = {engine: {inventory: 3}, server: {status: 13, databases: 3, activity: 10, locks: 3, replication: 4, io: 3, settings: 4},
  database: {status: 13, databases: 3, activity: 10, locks: 3, replication: 4, io: 3, settings: 4, tables: 3}};
const mysqlCounts = {engine: {inventory: 5}, server: {availability: 9, native_status: 5, native_settings: 5, native_storage: 5, native_activity: 5, native_replication: 5},
  database: {availability: 9, native_status: 5, native_settings: 5, native_storage: 5, native_activity: 5, native_replication: 5}};
const duckdbCounts = {engine: {inventory: 5}, server: {availability: 9, registrations: 3},
  database: {availability: 9, storage: 8, database: 3, extensions: 3, limitations: 2}};
const sqliteCounts = {engine: {inventory: 5}, server: {availability: 9, registrations: 3},
  database: {availability: 9, storage: 6, database: 4, limitations: 2}};
function sqliteDynamic(id, scope) {
  if(scope !== 'engine') return false;
  const match = /^sqlite_fleet_[1-9][0-9]*_[a-f0-9]{2,1024}_([a-f0-9]{2,128})$/.exec(id);
  if(!match) return false;
  return ['name', 'collector', 'freshness', 'heartbeat', 'target_id', 'observed_at']
    .some(field => [...new TextEncoder().encode(field)].map(byte => byte.toString(16).padStart(2, '0')).join('') === match[1]);
}
function duckdbDynamic(id, scope) {
  if(scope !== 'engine') return false;
  const match = /^duckdb_fleet_[1-9][0-9]*_[a-f0-9]{2,1024}_([a-f0-9]{2,128})$/.exec(id);
  if(!match) return false;
  return ['name', 'collector', 'freshness', 'heartbeat', 'target_id', 'observed_at']
    .some(field => [...new TextEncoder().encode(field)].map(byte => byte.toString(16).padStart(2, '0')).join('') === match[1]);
}
function mysqlDynamic(id, scope, engine='mysql') {
  const maria = engine === 'mariadb';
  if(!id.startsWith(engine + '_')) return false;
  if(maria) id = 'mysql_' + id.slice('mariadb_'.length);
  const hex = value => [...new TextEncoder().encode(value)].map(byte => byte.toString(16).padStart(2, '0')).join('');
  if(scope === 'engine') {
    const match = /^mysql_fleet_[1-9][0-9]*_[a-f0-9]{2,1024}_([a-f0-9]{2,128})$/.exec(id);
    return Boolean(match && ['name', 'collector', 'freshness', 'heartbeat', maria ? 'server_uid' : 'server_uuid', 'observed_at'].some(field => hex(field) === match[1]));
  }
  if(!maria && /^mysql_workload_summary_(?:[0-9]|1[01])$/.test(id)) return true;
  if(!maria && (/^mysql_alert_summary_[01]$/.test(id) ||
      /^mysql_alert_[a-f0-9]{2,128}_(?:state|condition|value|source|observed_at|action|delivery)$/.test(id))) return true;
  const workload = !maria && /^mysql_workload_(settings|consumers|instruments|epoch|digests)_([a-f0-9]{2,1024})_([a-f0-9]{2,128})$/.exec(id);
  if(workload) {
    const fields = {settings: ['performance_schema', 'digests_size', 'max_digest_length', 'stored_digest_length', 'slow_query_log', 'log_output', 'long_query_time'],
      consumers: ['name', 'enabled'], instruments: ['family', 'instrument_count', 'enabled_count', 'timed_count'],
      epoch: ['variable_name', 'variable_value'], digests: ['sum_timer_wait', 'count_star', 'sum_rows_examined']};
    return fields[workload[1]].some(field => hex(field) === workload[3]) &&
      (workload[1] !== 'settings' || workload[2] === hex('settings'));
  }
  const match = /^mysql_(status|settings|storage|activity|replication)_([a-f0-9]{2,1024})_([a-f0-9]{2,128})$/.exec(id);
  if(!match) return false;
  const fields = {status: ['variable_name', 'variable_value', ...(maria ? ['native_variable_name'] : [])],
    settings: ['max_connections', 'innodb_page_size', 'innodb_buffer_pool_size', 'read_only', ...(!maria ? ['super_read_only'] : []), 'event_scheduler'],
    storage: ['engine', 'tables_count', 'estimated_rows', 'data_bytes', 'index_bytes'],
    activity: ['processlist_id', 'processlist_user', 'processlist_db', 'processlist_command', 'processlist_time', 'processlist_state'],
    replication: maria ? ['channel_name', 'slave_io_running', 'slave_sql_running', 'last_io_errno', 'last_sql_errno', 'seconds_behind_master', 'gtid_io_pos'] : ['channel_name', 'service_state', 'last_error_number']};
  if(!fields[match[1]].some(field => hex(field) === match[3])) return false;
  if(match[1] === 'settings') return match[2] === hex('settings');
  if(match[1] !== 'status') return true;
  return ['Uptime', 'Uptime_since_flush_status', 'Threads_connected', 'Threads_running', 'Connections',
    'Aborted_connects', 'Aborted_clients', 'Questions', 'Com_select', 'Com_insert', 'Com_update', 'Com_delete',
    'Com_commit', 'Com_rollback', 'Bytes_received', 'Bytes_sent', 'Slow_queries', 'Created_tmp_tables',
    'Created_tmp_disk_tables', 'Innodb_buffer_pool_read_requests', 'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_pages_data', 'Innodb_buffer_pool_pages_dirty', 'Innodb_data_reads', 'Innodb_data_writes',
    'Innodb_row_lock_waits', 'Innodb_row_lock_time', 'Innodb_rows_read', 'Innodb_rows_inserted',
    'Innodb_rows_updated', 'Innodb_rows_deleted'].some(field => hex(field) === match[2]);
}
function postgresDynamic(id, scope) {
  const patterns = scope === 'engine' ? [
    /^server_[0-9]+_[a-f0-9]{2,1024}_([0-8])$/,
    /^fleetdb_[0-9]+_[a-f0-9]{2,1024}_[a-f0-9]{2,1024}_([0-8])$/,
  ] : [
    /^database_[0-9]+_[a-f0-9]{2,1024}_([0-9]|1[0-5])$/,
    /^replica_[0-9]+_[a-f0-9]{2,1024}_([0-9])$/,
    /^io_[a-f0-9]{2,1024}_([0-7])$/,
    /^(lock|setting)_[a-f0-9]{2,1024}_0$/,
    ...(scope === 'database' ? [/^table_[0-9]+_[a-f0-9]{2,1024}_([0-9]|1[01])$/] : []),
  ];
  return patterns.some(pattern => pattern.test(id));
}
function firebirdDynamic(id, scope) {
  const database = scope === 'engine' ? /^fleetdb_[0-9]+_[a-f0-9]{2,1024}_(?:[0-9]|1[0-2]|finding_[a-f0-9]{2,1024})$/ :
    /^database_[a-f0-9]{2,1024}_(?:[0-9]|1[0-3]|finding_[a-f0-9]{2,1024})$/;
  return scope === 'engine' ? database.test(id) || /^server_[0-9]+_[0-8]$/.test(id) ||
    /^aggregate_[0-9]+_(?:[0-9]|1[0-9])$/.test(id) :
    scope === 'server' && (database.test(id) || id === 'empty_0');
}
const unavailable = {value: 'Unavailable', unit: '', rate: ''};
function check(condition, message) { if(!condition) throw new Error(message); }
function sourceSet(snapshot) {
  return {entry:snapshot.entry,files:Object.entries(snapshot.files).map(([id,text])=>({id,text,revision:'publication',encoding:'utf-8',writable:true}))};
}
function records(libraries,snapshot) {
  const input=sourceSet(snapshot), parsed=libraries.language.decodeSources(input);
  check(parsed.syntaxValid && !parsed.diagnostics.some(item=>item.severity==='error'),'Invalid dashboard notation.');
  const all=libraries.model.listRecords(parsed.normalized);
  const sources=all.filter(item=>item.kind==='source');
  const datasets=all.filter(item=>item.kind==='data');
  check(sources.length===1 && sources[0].record.id==='metric_feed' && sources[0].record.mode==='host' && sources[0].record.update==='keyed','Only the collector host source is admitted.');
  check(datasets.length===1 && datasets[0].record.id==='observations','Only observations data is admitted.');
  const data=datasets[0].record;
  check(data.source?.id==='metric_feed' && (!data.source.file || data.source.file===snapshot.entry) && data.key?.join()==='id','Invalid metric source binding.');
  check(data.columns?.length===METRIC_COLUMNS.length && data.columns.every((column,index)=>column.id===METRIC_COLUMNS[index] && column.type==='text'),'Invalid metric schema.');
  check(Array.isArray(data.rows) && data.rows.length>0 && data.rows.length<=4096 && data.rows.every(row=>Array.isArray(row) && row.length===METRIC_COLUMNS.length && row.every(cell=>typeof cell==='string')),'Metric records require string value, unit and rate fields.');
  return {input,parsed,all,data,source:sources[0].record};
}
export async function validatePublication(libraries,snapshot,scope,engine='firebird') {
  check(['firebird','postgresql','mysql','mariadb','duckdb','sqlite'].includes(engine),'Unknown dashboard engine.');
  const bindings=engine==='postgresql'?postgresCounts:['mysql','mariadb'].includes(engine)?mysqlCounts:engine==='duckdb'?duckdbCounts:engine==='sqlite'?sqliteCounts:counts;
  check(bindings[scope],'Unknown dashboard scope.');
  check(snapshot && Object.keys(snapshot).sort().join()==='entry,files,format,view','Dashboard appearance belongs in authored source.');
  check(snapshot?.format==='ddn-source-workspace@1','Legacy dashboard source requires migration.');
  check(Object.keys(snapshot.files || {}).join()==='dashboard.ddn','Use one dashboard.ddn file.');
  check(snapshot.entry==='dashboard.ddn' && typeof snapshot.view==='string','Invalid selected view.');
  check(typeof snapshot.files['dashboard.ddn']==='string' && new TextEncoder().encode(snapshot.files['dashboard.ddn']).length<=512*1024,'Dashboard source exceeds its limit.');
  const {input,parsed,all,data,source}=records(libraries,snapshot);
  check(source.channel===metricChannel(`scratchrobin.${engine}.monitoring`),'Wrong dashboard engine source.');
  check(all.every(item=>['source','data','view','placement','appearance','publication','definition'].includes(item.kind)),'Unsupported dashboard declaration.');
  // A publication cannot smuggle extra providers or opaque native payloads.
  check(all.filter(item=>item.kind==='definition').length===0,'Dashboard definitions are not admitted.');
  const allowed=new Set(Object.entries(bindings[scope]).flatMap(([prefix,count])=>Array.from({length:count},(_,index)=>`${prefix}_${index}`)));
  const seen=new Set();
  for(const row of data.rows) {
    const id=row[0];
    check((allowed.has(id) || (engine==='firebird' && firebirdDynamic(id,scope)) || (engine==='postgresql' && postgresDynamic(id,scope)) ||
      (engine==='duckdb' && duckdbDynamic(id,scope)) || (engine==='sqlite' && sqliteDynamic(id,scope)) ||
      (['mysql','mariadb'].includes(engine) && mysqlDynamic(id,scope,engine))) && !seen.has(id),'Unknown, duplicate or wrong-scope metric binding.');
    seen.add(id);
  }
  check(all.some(item=>item.kind==='view' && item.ref.id===snapshot.view),'Selected dashboard view does not exist.');
  const api=libraries.viewer;
  const verifier=api.createVerifier(api.createBrowserRuntimeOptions?api.createBrowserRuntimeOptions():api.createCompleteRuntimeOptions());
  try {
    const verified=await verifier.verifySources(input,{level:'semantic',scope:{kind:'workarea'},purpose:'view'});
    check(verified.outcome==='valid' && verified.coverage.complete,'Invalid dashboard view or binding.');
  } finally {verifier.destroy();}
  const rows=data.rows.map(row=>[...row.slice(0,3),unavailable.value,unavailable.unit,unavailable.rate]);
  const patches=libraries.language.patchProperty(parsed,{file:snapshot.entry,id:'observations'},'rows',rows);
  const changed=libraries.language.applySourcePatches(input,patches);
  return {format:'ddn-source-workspace@1',entry:snapshot.entry,view:snapshot.view,files:Object.fromEntries(changed.files.map(file=>[file.id,file.text]))};
}
export async function bindPublication(libraries,snapshot,scope,liveFiles,engine='firebird') {
  const clean=await validatePublication(libraries,snapshot,scope,engine);
  const wanted=records(libraries,clean), current=records(libraries,{entry:'dashboard.ddn',files:liveFiles});
  const values=new Map(current.data.rows.map(row=>[row[0],row.slice(3)]));
  return {...clean,liveData:[{kind:'replace',source:wanted.source.channel,schema:wanted.data.columns,
    rows:wanted.data.rows.map(row=>[...row.slice(0,3),...(values.get(row[0]) || ['Unavailable','',''])])}]};
}
