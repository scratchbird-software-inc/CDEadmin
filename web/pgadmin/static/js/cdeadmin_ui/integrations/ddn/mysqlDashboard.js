import {dashboardPanelFiles} from './dashboardPanels';

const hex = value => [...new TextEncoder().encode(String(value))].map(byte => byte.toString(16).padStart(2, '0')).join('');
const binding = (id, values) => Object.assign(values, {bindingId: id});
export function mysqlCurrentSample(snapshot, scope) {
  const last = snapshot?.samples?.at(-1), age = snapshot?.sample_age_seconds;
  return snapshot?.state === 'collecting' && Number.isFinite(age) && age >= 0 && age <= snapshot.stale_after_seconds &&
    ['available', 'partial'].includes(last?.status) && last.transaction_completed === true && last.scope === scope ? last : null;
}
export function mysqlDashboardFiles(snapshot, scope, engine='mysql') {
  const label = engine === 'mariadb' ? 'MariaDB' : 'MySQL';
  const identityKey = engine === 'mariadb' ? 'server_uid' : 'server_uuid';
  const last = snapshot?.samples?.at(-1), sample = mysqlCurrentSample(snapshot, scope);
  const panels = [{id: 'availability', title: `${label} observation and availability`, rows: [
    ['Collector', snapshot?.state], ['Probe', last?.status], ['Freshness', sample ? 'Current' : 'No current observation'],
    ['Heartbeat', snapshot?.heartbeat?.status || 'Disabled'], ['Sample age', snapshot?.sample_age_seconds, 'seconds'],
    ['Observed at', last?.ended_at], ['History', 'Volatile process window'],
    ['Native server identity', sample?.identity?.[identityKey]], ['Database', sample?.identity?.database_name],
  ]}];
  const identities = {status: 'variable_name', storage: 'engine', activity: 'processlist_id', replication: 'channel_name'};
  for(const name of ['status', 'settings', 'storage', 'activity', 'replication']) {
    const group = sample?.groups?.[name], values = group?.status === 'available' ? group.rows || [] : [];
    const seen = new Set();
    const rows = values.flatMap(row => {
      const identity = name === 'settings' ? 'settings' : row[identities[name]];
      if(identity == null || seen.has(String(identity))) return [];
      seen.add(String(identity));
      return Object.entries(row).map(([key, value]) => binding(`${engine}_${name}_${hex(identity)}_${hex(key)}`,
        [`${identity}: ${key}`, typeof value === 'object' && value !== null ? JSON.stringify(value) : value,
          name === 'storage' ? 'Native estimate; not filesystem usage' : group.scope,
          name === 'status' && key === 'variable_value' ? sample?.rates?.per_second?.[identity] ?? '' : '']));
    });
    panels.push({id: `native_${name}`, title: `${label} ${name}`, rows: [
      ['Source', group?.status || 'Unavailable', group?.scope || scope],
      ['Visibility', group?.visibility], ['Truncated', group?.truncated],
      ['Native observation time', group?.observed_at], ['Native observation age', group?.observation_age_seconds, 'seconds'], ...rows,
    ]});
  }
  return dashboardPanelFiles(panels, `${label} ${scope} dashboard`, `scratchrobin.${engine}.monitoring`);
}
export function mysqlFleetPublication(snapshot, limit=128, engine='mysql') {
  const label = engine === 'mariadb' ? 'MariaDB' : 'MySQL';
  const identityKey = engine === 'mariadb' ? 'server_uid' : 'server_uuid';
  let remaining = limit;
  const total = (snapshot?.servers || []).reduce((count, server) => count + 1 + (server.databases?.length || 0), 0);
  const panels = [{id: 'inventory', title: `Owner-registered ${label} inventory`, rows: [
    ['Registered endpoints', snapshot?.registered_endpoints], ['History', 'Volatile process window'],
    ['Identity basis', 'Registrations; aliases are not deduplicated and counters are not summed'],
  ]}];
  for(const server of snapshot?.servers || []) {
    if(remaining <= 0) break;
    const rows = [];
    const add = (current, target, label) => {
      const scope = target == null ? 'server' : 'database', sample = mysqlCurrentSample(current, scope);
      const id = `${engine}_fleet_${server.server_id}_${hex(target ?? 'server')}`;
      for(const [key, value] of Object.entries({name: label, collector: current?.state,
        freshness: sample ? 'Current observation' : 'Unavailable or stale', heartbeat: current?.heartbeat?.status,
        [identityKey]: sample?.identity?.[identityKey], observed_at: sample?.ended_at})) {
        rows.push(binding(`${id}_${hex(key)}`, [`${label}: ${key}`, value]));
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
  panels[0].rows.push(['Displayed scopes', limit - remaining], ['Omitted scopes; open separately from scope selector', total - limit + remaining]);
  const files = dashboardPanelFiles(panels, `${label} engine dashboard`, `scratchrobin.${engine}.monitoring`);
  if(new TextEncoder().encode(files['dashboard.ddn']).length > 512 * 1024 && limit > 1) return mysqlFleetPublication(snapshot, Math.max(1, Math.floor(limit / 2)), engine);
  return {files, pages: Array.from({length: Math.ceil(panels.length / 12)}, (_, index) => index ? `dashboard_page_${index + 1}` : 'dashboard')};
}
export const mysqlFleetFiles = (snapshot, engine='mysql') => mysqlFleetPublication(snapshot, 128, engine).files;
