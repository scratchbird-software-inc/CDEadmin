import {dashboardPanelFiles} from './dashboardPanels.js';

const identity = value => [...new TextEncoder().encode(String(value ?? ''))].map(byte => byte.toString(16).padStart(2, '0')).join('') || '00';

export function postgresqlFleetFiles(fleet) {
  const panels = [{id: 'inventory', title: 'PostgreSQL owner registrations', rows: [
    ['Registered servers', fleet?.registered_endpoints, 'Registrations, not discovered cluster members'],
    ['Database inventory', 'Configured collectors, not the complete database catalog'],
    ['History', 'Volatile process buffer'],
  ]}];
  const observation = (id, title, snapshot, scope) => {
    const last = snapshot?.samples?.at(-1);
    const fresh = snapshot?.state === 'collecting' && Number.isFinite(snapshot?.sample_age_seconds) &&
      snapshot.sample_age_seconds >= 0 && Number.isFinite(snapshot?.stale_after_seconds) &&
      snapshot.sample_age_seconds <= snapshot.stale_after_seconds;
    const sample = fresh && last?.transaction_completed === true && last?.scope === scope &&
      ['available', 'partial'].includes(last.status) ? last : null;
    panels.push({id, title, rows: [
      ['Collection', snapshot?.state || 'Unknown'], ['Latest probe', last?.status || 'Not sampled'],
      ['Freshness', sample ? 'Current' : 'No current observation'],
      ['Sample age', snapshot?.sample_age_seconds, 'seconds'],
      ['Heartbeat', snapshot?.heartbeat?.status || 'Disabled'],
      ['Connection database', sample?.identity?.database],
      ['Statistics visibility', sample?.identity?.statistics_visibility],
      ['Recovery mode', sample?.identity?.in_recovery, 'Does not prove replication freshness'],
      ['Postmaster started', sample?.identity?.postmaster_started_at, 'UTC'],
    ]});
  };
  (fleet?.servers || []).forEach((server) => {
    observation(`server_${server.server_id}_${identity(server.name)}`, server.name, server.snapshot, 'server');
    (server.databases || []).forEach((database) => observation(
      `fleetdb_${server.server_id}_${identity(database.target_id)}_${identity(database.name)}`, `${server.name} / ${database.name}`, database.snapshot, 'database'));
  });
  return dashboardPanelFiles(panels, 'PostgreSQL engine dashboard', 'scratchrobin.postgresql.monitoring');
}

// Fixed native bindings only. Database names are values, never DDN identifiers.
const counters = [
  ['xact_commit', 'Commits', 'transactions'], ['xact_rollback', 'Rollbacks', 'transactions'],
  ['blks_read', 'Blocks read', 'blocks'], ['blks_hit', 'Buffer hits', 'PostgreSQL buffers, not OS cache'],
  ['tup_returned', 'Tuples returned', 'tuples'], ['tup_fetched', 'Tuples fetched', 'tuples'],
  ['tup_inserted', 'Tuples inserted', 'tuples'], ['tup_updated', 'Tuples updated', 'tuples'],
  ['tup_deleted', 'Tuples deleted', 'tuples'], ['temp_files', 'Temporary files', 'files'],
  ['temp_bytes', 'Temporary bytes', 'bytes'], ['deadlocks', 'Deadlocks', 'deadlocks'],
];

export function postgresqlDashboardFiles(snapshot, title='PostgreSQL dashboard', scope='database') {
  const last = snapshot?.samples?.at(-1);
  const fresh = snapshot?.state === 'collecting' && Number.isFinite(snapshot?.sample_age_seconds) &&
    snapshot.sample_age_seconds >= 0 && Number.isFinite(snapshot?.stale_after_seconds) &&
    snapshot.sample_age_seconds <= snapshot.stale_after_seconds;
  const sample = fresh && last?.transaction_completed === true && last?.scope === scope &&
    ['available', 'partial'].includes(last?.status) ? last : null;
  const groups = sample?.groups || {};
  const rows = (name) => groups[name]?.status === 'available' ? groups[name].rows || [] : [];
  const panels = [{id: 'status', title: 'Observation and availability', rows: [
    ['Collection', snapshot?.state || 'Unknown'], ['Latest probe', last?.status || 'Not sampled'],
    ['Observed at', last?.ended_at, 'UTC'], ['Last successful observation', last?.last_success_at, 'UTC'],
    ['Freshness', sample ? 'Current' : 'No current observation'],
    ['Sample age', snapshot?.sample_age_seconds, 'seconds'],
    ['Heartbeat', snapshot?.heartbeat?.status || 'Disabled'],
    ['Heartbeat age', snapshot?.heartbeat?.age_seconds, 'seconds'],
    ['History', 'Volatile process buffer'],
    ['Connection database', sample?.identity?.database],
    ['Statistics visibility', sample?.identity?.statistics_visibility],
    ['Postmaster started', sample?.identity?.postmaster_started_at, 'UTC'],
    ['Recovery mode', sample?.identity?.in_recovery, 'Not a replication freshness test'],
  ]}];
  const coverage = (name) => [
    ['Source', groups[name]?.status || 'Unavailable', groups[name]?.scope || ''],
    ['Visibility', groups[name]?.visibility],
    ['Truncated', groups[name]?.truncated, 'Limited groups are not complete inventories'],
  ];
  panels.push({id: 'databases', title: 'Database statistics coverage', rows: coverage('database')});
  rows('database').forEach((row) => panels.push({id: `database_${row.datid}_${identity(row.datname)}`, title: row.datname, rows: [
    ['Database OID', row.datid], ['Connected backends', row.numbackends, 'Includes this collector'],
    ['Statistics reset', row.stats_reset, 'UTC'], ['Rate baseline', row.rate_state],
    ...counters.map(([field, label, unit]) => [label, row[field], unit,
      row.rate_state === 'available' ? row.rates_per_second?.[field] : null]),
  ]}));
  const activity = rows('activity')[0];
  panels.push({id: 'activity', title: 'Activity — collector excluded', rows: [
    ...coverage('activity'),
    ...[['visible_backends', 'Visible backends'], ['active', 'Active'],
      ['idle_in_transaction', 'Idle in transaction'], ['aborted', 'Idle in aborted transaction'],
      ['lock_waiters', 'Lock waiters'], ['restricted_or_unavailable', 'Unknown or restricted state']]
      .map(([key, label]) => [label, activity?.[key], 'backends']),
    ['Oldest visible transaction', activity?.oldest_transaction_seconds, 'seconds'],
  ]});
  panels.push({id: 'locks', title: 'Locks — collector excluded', rows: coverage('locks')});
  rows('locks').forEach(row => panels.push({id: `lock_${identity(row.locktype + '/' + row.mode + '/' + row.granted)}`,
    title: 'Lock observation', rows: [[`${row.locktype} / ${row.mode} / ${row.granted ? 'granted' : 'waiting'}`, row.count, 'locks']]}));
  if(scope === 'database') {
    panels.push({id: 'tables', title: 'Table maintenance coverage', rows: coverage('tables')});
    rows('tables').forEach((row) => panels.push({id: `table_${row.relid}_${identity(row.schemaname + '.' + row.relname)}`,
      title: `${row.schemaname}.${row.relname}`, rows: [
        ['Relation OID', row.relid], ['Live tuples', row.n_live_tup, 'Estimate, not exact count'],
        ['Dead tuples', row.n_dead_tup, 'Estimate, not exact count'],
        ['Changes since analyze', row.n_mod_since_analyze, 'Estimate'],
        ...['vacuum', 'autovacuum', 'analyze', 'autoanalyze'].flatMap((name) => [
          [`Last ${name}`, row[`last_${name}`], 'UTC'], [`${name} count`, row[`${name}_count`], 'operations'],
        ]),
      ]}));
  }
  panels.push({id: 'replication', title: 'Replication — server scope', rows: [
    ...coverage('replication'), ['Interpretation', 'Availability does not prove replication freshness'],
  ]});
  rows('replication').forEach((row) => panels.push({id: `replica_${row.pid}_${identity(row.application_name)}`, title: row.application_name, rows: [
    ['Sender PID', row.pid], ['State', row.state], ['Synchronous state', row.sync_state],
    ...['sent_lsn', 'write_lsn', 'flush_lsn', 'replay_lsn'].map((name) => [name, row[name], 'Native position']),
    ...['write_lag', 'flush_lag', 'replay_lag'].map((name) => [name, row[name], 'Native interval; NULL is unknown']),
  ]}));
  panels.push({id: 'io', title: 'I/O — server scope', rows: coverage('io')});
  rows('io').forEach((row) => panels.push({id: `io_${identity(row.backend_type + '/' + row.object + '/' + row.context)}`,
    title: `${row.backend_type} / ${row.object} / ${row.context}`, rows: [
      ...['reads', 'writes', 'hits', 'evictions', 'fsyncs'].map((name) => [name, row[name], 'Native cumulative counter']),
      ['Bytes read', row.read_bytes, 'bytes'], ['Bytes written', row.write_bytes, 'bytes'],
      ['Statistics reset', row.stats_reset, 'UTC'],
    ]}));
  panels.push({id: 'settings', title: 'Settings — collector connection', rows: [
    ...coverage('settings'), ['Observed at', groups.settings?.observed_at, 'UTC; metadata sampling interval'],

  ]});
  rows('settings').forEach(row => panels.push({id: `setting_${identity(row.name)}`, title: 'Collector setting', rows: [[row.name, row.setting, row.unit || 'Native setting']]}));
  return dashboardPanelFiles(panels, title, 'scratchrobin.postgresql.monitoring');
}
