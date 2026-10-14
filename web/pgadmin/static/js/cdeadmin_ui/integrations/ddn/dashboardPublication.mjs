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
const unavailable = {value: 'Unavailable', unit: '', rate: ''};
function check(condition, message) { if(!condition) throw new Error(message); }
function records(runtime, files) {
  const parsed = runtime.parse(files['dashboard.ddn'], 'dashboard.ddn');
  check(parsed.imports.length === 0, 'Dashboard imports are not admitted.');
  const blocks = parsed.declarations.filter((item) => item.type === 'data');
  check(blocks.length === 1 && blocks[0].id === 'observations', 'Only observations data is admitted.');
  return {parsed, rows: blocks[0].children};
}
export function validatePublication(runtime, snapshot, scope, engine='firebird') {
  check(['firebird', 'postgresql', 'mysql', 'mariadb', 'duckdb', 'sqlite'].includes(engine), 'Unknown dashboard engine.');
  const bindings = engine === 'postgresql' ? postgresCounts : ['mysql', 'mariadb'].includes(engine) ? mysqlCounts : engine === 'duckdb' ? duckdbCounts : engine === 'sqlite' ? sqliteCounts : counts;
  check(bindings[scope], 'Unknown dashboard scope.');
  check(snapshot?.format === 'ddn-workspace@1', 'Unsupported dashboard format.');
  check(Object.keys(snapshot.files || {}).join() === 'dashboard.ddn', 'Use one dashboard.ddn file.');
  check(snapshot.entry === 'dashboard.ddn' && typeof snapshot.view === 'string', 'Invalid selected view.');
  const source = snapshot.files['dashboard.ddn'];
  check(typeof source === 'string' && new TextEncoder().encode(source).length <= 512 * 1024, 'Dashboard source exceeds its limit.');
  const {parsed, rows} = records(runtime, snapshot.files);
  check(engine === 'firebird' ? !['scratchrobin.postgresql.monitoring', 'scratchrobin.mysql.monitoring', 'scratchrobin.mariadb.monitoring', 'scratchrobin.duckdb.monitoring', 'scratchrobin.sqlite.monitoring'].includes(parsed.module) :
    parsed.module === `scratchrobin.${engine}.monitoring`, 'Wrong dashboard engine module.');
  check(parsed.declarations.every((item) => ['data', 'view', 'format'].includes(item.type)), 'Unsupported dashboard declaration.');
  const allowed = new Set(Object.entries(bindings[scope]).flatMap(([prefix, count]) =>
    Array.from({length: count}, (_, index) => `${prefix}_${index}`)));
  check(rows.length > 0 && rows.length <= (engine === 'firebird' ? allowed.size : 4096), 'Dashboard needs admitted metric records.');
  const seen = new Set();
  for(const row of rows) {
    check((allowed.has(row.id) || (engine === 'postgresql' && postgresDynamic(row.id, scope)) ||
      (engine === 'duckdb' && duckdbDynamic(row.id, scope)) ||
      (engine === 'sqlite' && sqliteDynamic(row.id, scope)) ||
      (['mysql', 'mariadb'].includes(engine) && mysqlDynamic(row.id, scope, engine))) && !seen.has(row.id), 'Unknown, duplicate or wrong-scope metric binding.');
    seen.add(row.id);
    check(row.type === 'object' && row.props.kind === 'record' && !row.children.length,
      'Only metric records are admitted.');
    check(Object.keys(row.props).sort().join() === 'kind,x_record' &&
      Object.keys(row.props.x_record || {}).sort().join() === 'rate,unit,value' &&
      Object.values(row.props.x_record).every((value) => typeof value === 'string'),
    'Metric records require string value, unit and rate fields.');
  }
  const workspace = runtime.createWorkspace(snapshot.files);
  try {
    const entries = workspace.entries();
    check(entries.some((entry) => entry.file === snapshot.entry && entry.views.some((view) => view.id === snapshot.view)),
      'Selected dashboard view does not exist.');
    for(const entry of entries) for(const view of entry.views) {
      check(workspace.validateDraft(entry.file, view.id).status === 'valid', 'Invalid dashboard view or binding.');
    }
    const result = workspace.replaceData('observations', rows.map((row) => ({key: row.id, ...unavailable})));
    check(result.committed, 'Dashboard metric replacement failed validation.');
    const layout = snapshot.layoutState || null;
    if(layout) {
      check(layout.format === 'ddn-layout-state@1' && layout.view === snapshot.view &&
        layout.positions && Object.keys(layout.positions).length <= 256 &&
        Object.values(layout.positions).every((point) => Array.isArray(point) && point.length === 2 &&
          point.every((value) => Number.isFinite(value) && Math.abs(value) <= 100000)),
      'Invalid dashboard layout positions.');
    }
    // The public snapshot API validates runtime appearance options as well.
    return workspace.snapshot(snapshot.entry, snapshot.view, snapshot.overrides || {}, layout);
  } finally { workspace.destroy(); }
}
export function bindPublication(runtime, snapshot, scope, liveFiles, engine='firebird') {
  const clean = validatePublication(runtime, snapshot, scope, engine);
  const wanted = records(runtime, clean.files).rows;
  const current = new Map(records(runtime, liveFiles).rows.map((row) => [row.id, row.props.x_record]));
  const workspace = runtime.createWorkspace(clean.files);
  try {
    const result = workspace.replaceData('observations', wanted.map((row) => ({
      key: row.id, ...(current.get(row.id) || unavailable),
    })));
    check(result.committed, 'Live metric refresh failed validation.');
    return {...clean, files: workspace.getFiles()};
  } finally { workspace.destroy(); }
}
