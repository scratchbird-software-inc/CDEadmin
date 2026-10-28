import {recordSource,sourceHeader,tableSource,viewSource,ref} from './source.js';
import {COUNTER_FIELDS} from './dashboardPublication.mjs';
// Retained observations only. No native queries or persistence operations.
export const FIREBIRD_TREND_METRICS = Object.freeze([
  {id: 'io.page_reads', label: 'Page reads / second', scope: 'database', rate: true},
  {id: 'io.page_writes', label: 'Page writes / second', scope: 'database', rate: true},
  {id: 'records.record_inserts', label: 'Record inserts / second (not commits)', scope: 'database', rate: true},
  {id: 'records.record_updates', label: 'Record updates / second (not commits)', scope: 'database', rate: true},
  {id: 'records.record_deletes', label: 'Record deletes / second (not commits)', scope: 'database', rate: true},
  {id: 'attachments.user', label: 'Visible user attachments', scope: 'database'},
  {id: 'transactions.visible_total', label: 'Visible transactions', scope: 'database'},
  {id: 'memory.memory_used', label: 'Database memory used (bytes)', scope: 'database'},
  ...['page_fetches', 'page_marks'].map((field) => ({id: `io.${field}`,
    label: `${field.replaceAll('_', ' ')} / second`, scope: 'database', rate: true})),
  ...COUNTER_FIELDS.records.filter((field) => !['record_inserts', 'record_updates', 'record_deletes'].includes(field))
    .map((field) => ({id: `records.${field}`, label: `${field.replaceAll('_', ' ')} / second`, scope: 'database', rate: true})),
  ...COUNTER_FIELDS.memory.filter((field) => field !== 'memory_used').map((field) => ({id: `memory.${field}`,
    label: `${field.replaceAll('_', ' ')} (bytes)`, scope: 'database'})),
  ...['active_user', 'idle_user'].map((field) => ({id: `attachments.${field}`,
    label: `Visible ${field.replaceAll('_', ' ')} attachments`, scope: 'database'})),
  ...['active', 'read_only', 'oldest_age_seconds'].map((field) => ({id: `transactions.${field}`,
    label: `Visible transactions: ${field.replaceAll('_', ' ')}`, scope: 'database'})),
  ...[['allocated_bytes', 'Allocated database space (bytes)'],
    ['configured_cache_bytes', 'Configured page cache (bytes)'],
    ['next_minus_oit', 'Next minus OIT (transaction numbers)'],
    ['next_minus_oat', 'Next minus OAT (transaction numbers)'],
    ['next_minus_ost', 'Next minus OST (transaction numbers)']].map(([field, label]) =>
    ({id: `derived.${field}`, label, scope: 'database', derived: true})),
  {id: 'connection_count' , label: 'Service-visible attachments', scope: 'server'},
]);

export function trendObservations(snapshot, metricId, limit=120) {
  const metric = FIREBIRD_TREND_METRICS.find((item) => item.id === metricId);
  if(!metric || ![30, 120, 720].includes(limit)) throw new Error('Unsupported trend selection.');
  const samples = (snapshot?.samples || []).slice(-limit);
  return samples.map((sample) => {
    const [group, field] = metric.id.split('.');
    let exact = null, reason = '';
    if(sample.scope !== metric.scope) reason = 'wrong source scope';
    else if(!['available', 'partial'].includes(sample.status)) reason = 'source unavailable';
    else if(metric.rate) {
      if(sample.rates?.status !== 'available') reason = sample.rates?.reason || 'rate unavailable';
      else exact = sample.rates.per_second?.[metric.id] ?? null;
    } else if(metric.derived) {
      exact = sample.derived?.[field] ?? null;
    } else {
      const values = sample.groups?.[group];
      if(values?.status === 'available') exact = field ? values.values?.[field] : values.values;
    }
    const epoch = metric.rate ? sample.rates?.epoch : sample.source_epoch;
    const elapsed = sample.runtime_elapsed_seconds;
    const validDecimal = typeof exact === 'string' && /^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(exact);
    const numeric = validDecimal ? Number(exact) : NaN;
    if(!reason && exact == null) reason = 'metric unavailable';
    if(!reason && !epoch) reason = 'source epoch unavailable';
    if(!reason && (!Number.isFinite(elapsed) || elapsed < 0)) reason = 'monotonic time unavailable';
    if(!reason && (!Number.isFinite(numeric) || numeric > Number.MAX_SAFE_INTEGER ||
        (numeric === 0 && /[1-9]/.test(String(exact).split(/[eE]/)[0])))) reason = 'outside chart numeric range';
    return {exact: exact == null ? null : String(exact), numeric: reason ? null : numeric,
      elapsed, epoch, observed: sample.ended_at, coverage: sample.coverage,
      reason: reason || 'observed'};
  });
}

export function firebirdTrendFiles(snapshot, metricId, limit=120) {
  const rows = trendObservations(snapshot, metricId, limit);
  const metric = FIREBIRD_TREND_METRICS.find((item) => item.id === metricId);
  return retainedTrendFiles(rows, metric.label, 'scratchrobin.firebird.trends');
}

// Shared DDN presentation only. Native adapters own values, epochs and gaps.
export function retainedTrendFiles(rows,label,moduleName) {
  const table=rows.length?rows:[{reason:'No retained observations'}];
  const records=table.map((row,index)=>recordSource('r'+index,String(row.observed ?? 'Unavailable'),{
    value:String(row.exact ?? 'Unavailable'),elapsed:String(row.elapsed ?? 'Unavailable'),epoch:String(row.epoch ?? 'Unavailable'),
    coverage:String(row.coverage ?? 'Unavailable'),reason:String(row.reason ?? 'Unavailable')})).join('');
  const points=rows.flatMap((row,index)=>row.numeric==null?[]:[{id:'p'+index,row}]);
  const chart=points.length?points.map(({id,row})=>recordSource(id,String(row.observed),{elapsed:row.elapsed,value:row.numeric})).join('')+
    viewSource('chart','Retained observations — approximate chart, no interpolation','chart.basic@1',
      {mark:'point',x_type:'number',x:'metadata.x_record.elapsed',y:'metadata.x_record.value'},points.map(item=>item.id)):'';
  return {'trends.ddn':sourceHeader(moduleName)+records+chart+
    tableSource('detail','Exact retained values and gaps',table.map((_,index)=>'r'+index),[
      {key:'title',label:'Received (UTC)'},{key:'metadata.x_record.elapsed',label:'Elapsed seconds'},
      {key:'metadata.x_record.value',label:'Exact value'},{key:'metadata.x_record.reason',label:'Observation / gap'},
      {key:'metadata.x_record.coverage',label:'Coverage'},{key:'metadata.x_record.epoch',label:'Epoch'}])+
    viewSource('trends',label,'panels.composed@1',{columns:1,panels:[
      ...(points.length?[{target:ref('chart'),kind:'view',title:'Retained sample points',layout:{row:0,column:0}}]:[]),
      {target:ref('detail'),kind:'view',title:'Exact observations',layout:{row:points.length?1:0,column:0}}]})};
}
