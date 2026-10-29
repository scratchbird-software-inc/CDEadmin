import {dashboardPanelFiles} from './dashboardPanels.js';

const hex = value => [...new TextEncoder().encode(String(value))]
  .map(byte => byte.toString(16).padStart(2, '0')).join('');
const bound = (id, row) => Object.assign(row, {bindingId: id});

export function sqliteCurrentSample(snapshot) {
  const latest = snapshot?.samples?.at(-1), age = snapshot?.sample_age_seconds;
  return snapshot?.state === 'collecting' && Number.isFinite(age) && age >= 0 &&
    age <= snapshot.stale_after_seconds && latest?.status === 'available' &&
    latest.scope === 'database' && latest.transaction_refresh?.status === 'completed' ? latest : null;
}

export function sqliteDashboardFiles(snapshot, scope='database') {
  const latest = snapshot?.samples?.at(-1), sample = sqliteCurrentSample(snapshot);
  const panels = [{id: 'availability', title: 'SQLite file and collector', rows: [
    ['Collector', snapshot?.state], ['Probe', latest?.status],
    ['Freshness', sample ? 'Current' : 'No current observation'],
    ['Heartbeat', snapshot?.heartbeat?.status || 'Disabled'],
    ['Sample age', snapshot?.sample_age_seconds, 'seconds'],
    ['Observed at', latest?.ended_at], ['History', 'Volatile process window'],
    ['Native database', sample?.identity?.database_name],
    ['Registered file target', sample?.identity?.target_id],
  ]}];
  if(scope === 'server') {
    const files = snapshot?.databases || [];
    panels.push({id: 'registrations', title: 'Registered files', rows: [
      ['Registered files', files.length],
      ['Collecting files', files.filter(file => file.snapshot?.state === 'collecting').length],
      ['Identity basis', 'File registrations; no remote server counters are inferred'],
    ]});
  }
  if(scope === 'database') {
    const storage = sample?.groups?.storage?.rows?.[0] || {};
    panels.push({id: 'storage', title: 'Native file storage', rows: [
      ['Page size', storage.page_size_bytes, 'bytes'],
      ['Page count', storage.page_count, 'pages'],
      ['Free-list pages', storage.freelist_pages, 'pages'],
      ['Logical size', storage.logical_size_bytes, 'bytes'],
      ['Free space', storage.free_space_bytes, 'bytes'],
      ['Main file size', storage.file_size_bytes, 'bytes; excludes sidecars'],
    ]});
    const database = sample?.groups?.database?.rows?.[0] || {};
    panels.push({id: 'database', title: 'Native database state', rows: [
      ['Journal mode', database.journal_mode],
      ['Schema version', database.schema_version],
      ['User version', database.user_version],
      ['Read-only route', database.read_only_route],
    ]});
    panels.push({id: 'limitations', title: 'Native observation limits', rows: [
      ['Other sessions', 'Temporary objects and session settings are not globally visible'],
      ['Server counters', 'No remote server load or global user-session metrics'],
    ]});
  }
  return dashboardPanelFiles(panels, `SQLite ${scope} dashboard`, 'scratchrobin.sqlite.monitoring');
}

export function sqliteFleetPublication(snapshot, limit=128) {
  let remaining = limit;
  const total = (snapshot?.servers || []).reduce((count, server) =>
    count + 1 + (server.databases?.length || 0), 0);
  const panels = [{id: 'inventory', title: 'Owner-registered SQLite files', rows: [
    ['Registered endpoints', snapshot?.registered_endpoints],
    ['History', 'Volatile process window'],
    ['Identity basis', 'File registrations; aliases are not deduplicated'],
    ['Displayed scopes', 0], ['Omitted scopes', 0],
  ]}];
  for(const server of snapshot?.servers || []) {
    if(remaining <= 0) break;
    const rows = [];
    const add = (current, target, label) => {
      const sample = sqliteCurrentSample(current);
      const id = `sqlite_fleet_${server.server_id}_${hex(target ?? 'server')}`;
      for(const [key, value] of Object.entries({name: label, collector: current?.state,
        freshness: sample ? 'Current observation' : 'Unavailable or stale',
        heartbeat: current?.heartbeat?.status, target_id: target,
        observed_at: sample?.ended_at})) {
        rows.push(bound(`${id}_${hex(key)}`, [`${label}: ${key}`, value]));
      }
      remaining--;
    };
    add(server.snapshot, null, server.name);
    for(const database of server.databases || []) {
      if(remaining <= 0) break;
      add(database.snapshot, database.target_id, database.name);
    }
    panels.push({id: `endpoint_${server.server_id}`, title: server.name, rows});
  }
  panels[0].rows[3][1] = limit - remaining;
  panels[0].rows[4][1] = total - limit + remaining;
  const files = dashboardPanelFiles(panels, 'SQLite engine dashboard', 'scratchrobin.sqlite.monitoring');
  if(new TextEncoder().encode(files['dashboard.ddn']).length > 512 * 1024 && limit > 1)
    return sqliteFleetPublication(snapshot, Math.max(1, Math.floor(limit / 2)));
  return {files, pages: Array.from({length: Math.ceil(panels.length / 12)}, (_, index) =>
    index ? `dashboard_page_${index + 1}` : 'dashboard')};
}
export const sqliteFleetFiles = snapshot => sqliteFleetPublication(snapshot).files;
