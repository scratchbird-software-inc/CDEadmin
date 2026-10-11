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
const unavailable = {value: 'Unavailable', unit: '', rate: ''};
function check(condition, message) { if(!condition) throw new Error(message); }
function records(runtime, files) {
  const parsed = runtime.parse(files['dashboard.ddn'], 'dashboard.ddn');
  check(parsed.imports.length === 0, 'Dashboard imports are not admitted.');
  const blocks = parsed.declarations.filter((item) => item.type === 'data');
  check(blocks.length === 1 && blocks[0].id === 'observations', 'Only observations data is admitted.');
  return {parsed, rows: blocks[0].children};
}
export function validatePublication(runtime, snapshot, scope) {
  check(counts[scope], 'Unknown dashboard scope.');
  check(snapshot?.format === 'ddn-workspace@1', 'Unsupported dashboard format.');
  check(Object.keys(snapshot.files || {}).join() === 'dashboard.ddn', 'Use one dashboard.ddn file.');
  check(snapshot.entry === 'dashboard.ddn' && typeof snapshot.view === 'string', 'Invalid selected view.');
  const source = snapshot.files['dashboard.ddn'];
  check(typeof source === 'string' && new TextEncoder().encode(source).length <= 512 * 1024, 'Dashboard source exceeds its limit.');
  const {parsed, rows} = records(runtime, snapshot.files);
  check(parsed.declarations.every((item) => ['data', 'view', 'format'].includes(item.type)), 'Unsupported dashboard declaration.');
  const allowed = new Set(Object.entries(counts[scope]).flatMap(([prefix, count]) =>
    Array.from({length: count}, (_, index) => `${prefix}_${index}`)));
  check(rows.length > 0 && rows.length <= allowed.size, 'Dashboard needs admitted metric records.');
  const seen = new Set();
  for(const row of rows) {
    check(allowed.has(row.id) && !seen.has(row.id), 'Unknown, duplicate or wrong-scope metric binding.');
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
export function bindPublication(runtime, snapshot, scope, liveFiles) {
  const clean = validatePublication(runtime, snapshot, scope);
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
