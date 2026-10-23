export const NOTEBOOK_TYPE = 'cdeadmin.sql-notebook.v1';
export const NOTEBOOK_FORMAT = 'scratchrobin.sql-notebook@1';
export const NOTEBOOK_LIMIT = 2 * 1024 * 1024;
const credential = /-----BEGIN (?:ENCRYPTED |RSA |EC |OPENSSH )?PRIVATE KEY-----|\b[a-z][a-z0-9+.-]*:\/\/[^\s/]+:[^\s/@]+@|\b(?:password|passwd|access_token|refresh_token|client_secret|api_key)\s*[=:]\s*["']?[^\s"',;]+|\bIDENTIFIED\s+(?:WITH\s+\S+\s+)?(?:BY|AS)\b|\bSET\s+PASSWORD\b/i;
export const sensitiveColumn = /password|passwd|secret|token|private.?key|credential/i;
const clone = value => JSON.parse(JSON.stringify(value));
export function sameScope(left, right) {
  return left === null && right === null || !!left && !!right &&
    ['engine', 'endpoint_id', 'database_target_id'].every(key => left[key] === right[key]);
}
function exact(value, fields) {
  if(!value || Array.isArray(value) || typeof value !== 'object' ||
    Object.keys(value).sort().join('|') !== [...fields].sort().join('|')) throw new Error('Invalid notebook fields.');
}
function text(value, maximum, empty=false) {
  if(typeof value !== 'string' || value.length > maximum || value.includes('\0') || (!empty && !value.trim())) throw new Error('Invalid notebook text.');
  if(credential.test(value)) throw new Error('Remove credential material before storing or sharing a notebook.');
}
export function validateNotebook(value) {
  exact(value, ['format', 'scope', 'cells']);
  if(value.format !== NOTEBOOK_FORMAT) throw new Error('Unsupported notebook format.');
  if(value.scope !== null) {
    exact(value.scope, ['engine', 'endpoint_id', 'database_target_id']);
    if(value.scope.engine !== 'mysql') throw new Error('Select native MySQL.');
    text(value.scope.endpoint_id, 256); text(value.scope.database_target_id, 256);
  }
  if(!Array.isArray(value.cells) || value.cells.length > 200) throw new Error('Notebook requires at most 200 cells.');
  const ids = new Set();
  value.cells.forEach(cell => {
    if(!['note', 'sql'].includes(cell?.kind)) throw new Error('Invalid notebook cell.');
    exact(cell, cell.kind === 'sql' ? ['id', 'kind', 'source', 'snapshot'] : ['id', 'kind', 'source']);
    text(cell.id, 64); text(cell.source, 262144, true);
    if(ids.has(cell.id)) throw new Error('Duplicate notebook cell identity.');
    ids.add(cell.id);
    if(cell.kind !== 'sql' || cell.snapshot === null) return;
    const snapshot = cell.snapshot;
    exact(snapshot, ['columns', 'rows', 'captured_at', 'source', 'scope', 'limited']);
    text(snapshot.captured_at, 64); text(snapshot.source, 262144);
    if(snapshot.source !== cell.source || !sameScope(snapshot.scope, value.scope)) throw new Error('Snapshot differs from its executed SQL or connection scope.');
    if(snapshot.scope !== null) exact(snapshot.scope, ['engine', 'endpoint_id', 'database_target_id']);
    if(typeof snapshot.limited !== 'boolean' || !Array.isArray(snapshot.columns) || snapshot.columns.length < 1 || snapshot.columns.length > 128 || new Set(snapshot.columns).size !== snapshot.columns.length) throw new Error('Invalid snapshot columns.');
    snapshot.columns.forEach(name => text(name, 256));
    if(!Array.isArray(snapshot.rows) || snapshot.rows.length > 100) throw new Error('Retain at most 100 snapshot rows.');
    snapshot.rows.forEach(row => {
      if(!Array.isArray(row) || row.length !== snapshot.columns.length) throw new Error('Invalid snapshot row.');
      row.forEach(item => {if(item !== null) text(item, 8192, true);});
    });
  });
  if(new TextEncoder().encode(JSON.stringify(value)).length > NOTEBOOK_LIMIT) throw new Error('Notebook exceeds 2 MiB.');
  return clone(value);
}
export function newNotebook(scope=null) {return {format: NOTEBOOK_FORMAT, scope: clone(scope), cells: []};}
export function rebindNotebook(value, scope) {
  return validateNotebook({...value, scope, cells: value.cells.map(cell => cell.kind === 'sql' ? {...cell, snapshot: null} : cell)});
}
export function portableNotebook(value) {
  const checked = validateNotebook(value);
  return {...checked, scope: null, cells: checked.cells.map(cell => cell.snapshot ?
    {...cell, snapshot: {...cell.snapshot, scope: null}} : cell)};
}
export function retainedSnapshot(rendered, source, scope, policies) {
  const view = rendered?.view_model;
  if(!view || !Array.isArray(view.columns) || !Array.isArray(view.rows)) throw new Error('No tabular result page is available.');
  const selected = view.columns.map((column, index) => ({name: column.name, index, policy: policies[index] || 'omit'})).filter(column => column.policy !== 'omit');
  const snapshot = {columns: selected.map(column => column.name),
    rows: view.rows.slice(0, 100).map(row => selected.map(column => {
      if(column.policy === 'redact') return '[REDACTED]';
      const item = Array.isArray(row) ? row[column.index] : row[column.name];
      return item === null || item === undefined ? null : typeof item === 'string' ? item : JSON.stringify(item);
    })), captured_at: new Date().toISOString(), source, scope: clone(scope),
    limited: !!rendered.page?.next_cursor || !!rendered.page?.provider_continuation || !!rendered.sampling_applied ||
      view.rows.length > 100 || (rendered.page?.source_count ?? view.rows.length) > Math.min(view.rows.length, 100)};
  validateNotebook({format: NOTEBOOK_FORMAT, scope, cells: [{id: 'snapshot', kind: 'sql', source, snapshot}]});
  return snapshot;
}
export function notebookRequest(content, name, version, assetId) {
  if(typeof assetId !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,255}$/.test(assetId)) throw new Error('Invalid notebook asset identity.');
  return {asset_type: NOTEBOOK_TYPE, schema_name: NOTEBOOK_TYPE, schema_version: 1,
    name, path: `notebooks/${assetId}.json`, expected_version: version,
    content: validateNotebook(content), metadata: {}, resource_bindings: [],
    source_control_eligible: false};
}
