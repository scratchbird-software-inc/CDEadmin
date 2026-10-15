import {retainedTrendFiles} from './firebirdTrends';

export const POSTGRESQL_TREND_METRICS = Object.freeze([
  {id: 'numbackends', label: 'Connected backends (includes collector)'},
  ...[['xact_commit', 'Commits'], ['xact_rollback', 'Rollbacks'],
    ['blks_read', 'Blocks read'], ['blks_hit', 'PostgreSQL buffer hits'],
    ['tup_returned', 'Tuples returned'], ['tup_fetched', 'Tuples fetched'],
    ['tup_inserted', 'Tuples inserted'], ['tup_updated', 'Tuples updated'],
    ['tup_deleted', 'Tuples deleted'], ['temp_files', 'Temporary files'],
    ['temp_bytes', 'Temporary bytes'], ['deadlocks', 'Deadlocks']]
    .map(([id, label]) => ({id, label: label + ' / second', rate: true})),
]);

export function postgresqlTrendDatabases(snapshot) {
  const choices = new Map();
  for (const sample of (snapshot?.samples || []).slice(-720)) {
    if (!sample.transaction_completed || !['available', 'partial'].includes(sample.status) ||
        sample.groups?.database?.status !== 'available') continue;
    for (const row of sample.groups.database.rows || []) {
      const id = String(row.datid);
      if (/^[1-9][0-9]*$/.test(id) && typeof row.datname === 'string') choices.set(id, row.datname);
    }
  }
  return [...choices].map(([id, name]) => ({id, name})).sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
}

export function postgresqlTrendObservations(snapshot, scope, databaseId, metricId, limit=120) {
  const metric = POSTGRESQL_TREND_METRICS.find(item => item.id === metricId);
  if (!metric || !['database', 'server'].includes(scope) || ![30, 120, 720].includes(limit)) {
    throw new Error('Unsupported PostgreSQL trend selection.');
  }
  return (snapshot?.samples || []).slice(-limit).map(sample => {
    let reason = '', exact = null;
    const group = sample.groups?.database;
    const row = group?.rows?.find(item => String(item.datid) === String(databaseId));
    if (sample.scope !== scope) reason = 'wrong source scope';
    else if (!sample.transaction_completed || !['available', 'partial'].includes(sample.status)) reason = 'source unavailable or transaction incomplete';
    else if (group?.status !== 'available') reason = 'database statistics unavailable';
    else if (!row) reason = 'selected database not observed';
    else if (metric.rate && row.rate_state !== 'available') reason = row.rate_state || 'rate baseline unavailable';
    else exact = metric.rate ? row.rates_per_second?.[metric.id] : row[metric.id];
    const epoch = sample.source_epoch && sample.identity?.postmaster_started_at ?
      JSON.stringify([sample.source_epoch, sample.identity.postmaster_started_at, String(databaseId), row?.stats_reset ?? null]) : null;
    const elapsed = sample.runtime_elapsed_seconds;
    const decimal = typeof exact === 'string' && /^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(exact);
    const numeric = decimal ? Number(exact) : NaN;
    if (!reason && exact == null) reason = 'metric unavailable';
    if (!reason && !epoch) reason = 'source epoch unavailable';
    if (!reason && (!Number.isFinite(elapsed) || elapsed < 0)) reason = 'monotonic time unavailable';
    if (!reason && (!Number.isFinite(numeric) || numeric > Number.MAX_SAFE_INTEGER ||
        (numeric === 0 && /[1-9]/.test(exact.split(/[eE]/)[0])))) reason = 'outside chart numeric range';
    return {exact: exact == null ? null : String(exact), numeric: reason ? null : numeric,
      elapsed, epoch, observed: sample.ended_at,
      coverage: group?.truncated ? 'limited inventory' : group?.visibility || 'unavailable',
      reason: reason || 'observed'};
  });
}

export function postgresqlTrendFiles(snapshot, scope, databaseId, metricId, limit=120) {
  const metric = POSTGRESQL_TREND_METRICS.find(item => item.id === metricId);
  return retainedTrendFiles(postgresqlTrendObservations(snapshot, scope, databaseId, metricId, limit),
    `PostgreSQL database OID ${databaseId || 'unselected'} — ${metric.label}`, 'scratchrobin.postgresql.trends');
}
