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
  if(engine === 'mysql') {
    const alertsCurrent = snapshot?.state === 'collecting' && Number.isFinite(snapshot?.sample_age_seconds) &&
      snapshot.sample_age_seconds >= 0 && snapshot.sample_age_seconds <= snapshot.stale_after_seconds;
    panels.push({id: 'alerts', title: 'MySQL alert findings', rows: [
      binding('mysql_alert_summary_0', ['Policy state', alertsCurrent ? 'Current collector evaluation' : 'Unavailable or stale']),
      binding('mysql_alert_summary_1', ['Storage', 'Volatile collection lease; administration is in collection policy']),
      ...(snapshot?.alerts?.rules || []).slice(0, 32).flatMap(item => {
        const event = snapshot.alerts.events?.filter(event => event.rule_id === item.rule.id).at(-1);
        return Object.entries({state: item.state, condition: item.condition, value: item.evidence?.value ?? 'Unavailable',
          source: item.evidence?.source, observed_at: item.evidence?.observed_at,
          action: snapshot.alert_catalog?.metrics?.find(metric => metric.id === item.rule.metric)?.action,
          delivery: event?.delivery?.state ?? 'No transition'}).map(([field, value]) =>
          binding(`mysql_alert_${hex(item.rule.id)}_${field}`, [`${item.rule.id}: ${field}`, alertsCurrent ? value : 'Unavailable']));
      }),
    ]});
    const digests = sample?.groups?.workload_digests;
    panels.push({id: 'workload', title: 'MySQL workload / instrumentation coverage', rows: [
      ...[
        ['Source', digests?.status || 'Unavailable'], ['Native timer unit', 'picoseconds'],
        ['Ranking', 'Top total latency; cumulative native counters'], ['Truncated', digests?.truncated],
        ['Observed at', digests?.observed_at], ['Observation age', digests?.observation_age_seconds, 'seconds'],
        ['Reset observation', sample?.workload_reset?.state], ['Reset coverage', 'Undetected native resets remain possible; no inferred rates'],
      ].map((row, index) => binding(`mysql_workload_summary_${index}`, row)),
      ...['workload_settings', 'workload_consumers', 'workload_instruments', 'workload_epoch'].flatMap((name, index) => {
        const group = sample?.groups?.[name];
        const kind = name.slice('workload_'.length);
        return [binding(`mysql_workload_summary_${8+index}`, [name, group?.status || 'Unavailable']),
          ...(group?.status === 'available' ? group.rows : []).flatMap(row => {
            const identity = kind === 'settings' ? 'settings' : row.name ?? row.family ?? row.variable_name;
            return Object.entries(row).map(([key, value]) => binding(`mysql_workload_${kind}_${hex(identity)}_${hex(key)}`,
              [`${name} ${identity}: ${key}`, typeof value === 'object' && value !== null ? JSON.stringify(value) : value]));
          })];
      }),
      ...(digests?.rows || []).slice(0, 10).flatMap(row => ['sum_timer_wait', 'count_star', 'sum_rows_examined'].map(key =>
        binding(`mysql_workload_digests_${hex(`${row.schema_name ?? ''}\u0000${row.digest ?? ''}`)}_${hex(key)}`,
          [`${row.schema_name ?? 'NULL'} / ${row.digest ?? 'overflow'}: ${key}`, row[key], key === 'sum_timer_wait' ? 'picoseconds' : 'count']))),
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
