import {retainedTrendFiles} from './firebirdTrends.js';

export const MYSQL_TREND_METRICS = Object.freeze([
  {id: 'Threads_connected', label: 'Server connections (includes collectors)'},
  {id: 'Threads_running', label: 'Server running threads'},
  ...['Questions', 'Com_select', 'Com_insert', 'Com_update', 'Com_delete', 'Com_commit', 'Com_rollback',
    'Bytes_received', 'Bytes_sent', 'Slow_queries', 'Innodb_row_lock_waits', 'Innodb_rows_read',
    'Innodb_rows_inserted', 'Innodb_rows_updated', 'Innodb_rows_deleted'].map(id => ({id, label: id + ' / second (server-wide)', rate: true})),
]);
export function mysqlTrendObservations(snapshot, scope, metricId, limit=120, engine='mysql') {
  const metric = MYSQL_TREND_METRICS.find(item => item.id === metricId);
  if(!metric || !['server', 'database'].includes(scope) || ![30, 120, 720].includes(limit)) throw new Error('Unsupported MySQL trend selection.');
  return (snapshot?.samples || []).slice(-limit).map(sample => {
    let exact = null, reason = '';
    const group = sample.groups?.status;
    if(sample.scope !== scope) reason = 'wrong source scope';
    else if(!sample.transaction_completed || !['available', 'partial'].includes(sample.status)) reason = 'source unavailable or transaction incomplete';
    else if(group?.status !== 'available') reason = 'global status unavailable';
    else if(metric.rate && sample.rates?.status !== 'available') reason = sample.rates?.reason || 'rate baseline unavailable';
    else exact = metric.rate ? sample.rates?.per_second?.[metricId] : group.rows?.find(row => row.variable_name === metricId)?.variable_value;
    if(!reason && exact == null) reason = sample.rates?.gaps?.[metricId] || 'metric unavailable';
    const identity = sample.identity?.[engine === 'mariadb' ? 'server_uid' : 'server_uuid'];
    const epoch = sample.source_epoch && identity ? JSON.stringify([sample.source_epoch, identity]) : null;
    const elapsed = sample.runtime_elapsed_seconds;
    const valid = typeof exact === 'string' && /^\d+(?:\.\d+)?$/.test(exact), numeric = valid ? Number(exact) : NaN;
    if(!reason && !epoch) reason = 'source epoch unavailable';
    if(!reason && (!Number.isFinite(elapsed) || elapsed < 0)) reason = 'monotonic time unavailable';
    if(!reason && (!Number.isFinite(numeric) || numeric > Number.MAX_SAFE_INTEGER ||
        (numeric === 0 && /[1-9]/.test(exact)))) reason = 'outside chart numeric range';
    return {exact: exact == null ? null : String(exact), numeric: reason ? null : numeric,
      elapsed, epoch, observed: sample.ended_at, coverage: 'Server-wide; permission-filtered', reason: reason || 'observed'};
  });
}
export function mysqlTrendFiles(snapshot, scope, metricId, limit=120, engine='mysql') {
  const metric = MYSQL_TREND_METRICS.find(item => item.id === metricId);
  return retainedTrendFiles(mysqlTrendObservations(snapshot, scope, metricId, limit, engine),
    `${engine === 'mariadb' ? 'MariaDB' : 'MySQL'} ${scope} collector — ${metric.label}`, `scratchrobin.${engine}.trends`);
}
