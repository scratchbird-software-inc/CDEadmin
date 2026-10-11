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
const quote = (value) => JSON.stringify(String(value ?? 'Unavailable'));

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
  const table = rows.length ? rows : [{reason: 'No retained observations'}];
  const records = table.map((row, index) => `record r${index} ${quote(row.observed)} {
    x_record: {value: ${quote(row.exact)}, elapsed: ${quote(row.elapsed)}, epoch: ${quote(row.epoch)},
      coverage: ${quote(row.coverage)}, reason: ${quote(row.reason)} }; }`).join('\n');
  const points = rows.flatMap((row, index) => row.numeric == null ? [] : [
    `record p${index} ${quote(row.observed)} { x_record: {elapsed: ${row.elapsed}, value: ${row.numeric}}; }`,
  ]);
  const refs = rows.flatMap((row, index) => row.numeric == null ? [] : [`@points.p${index}`]);
  const chart = points.length ? `
    data points { ${points.join('\n')} }
    view chart "Retained observations — approximate chart, no interpolation" {
      data: [@points]; projection {kind: chart; profile: "chart.basic@1"; mark: point; x_type: number;
        records: [${refs.join(',')}]; x: "x_record.elapsed"; y: "x_record.value";
        width: 1000px; height: 400px; }
      publication {size: content; fit: none;}
    }` : '';
  return {'trends.ddn': `ddn "0.5"; module "scratchrobin.firebird.trends";
    data observations {${records}}
    ${chart}
    view detail "Exact retained values and gaps" {
      data: [@observations]; projection {kind: table; profile: "table.records@1";
        records: [${table.map((_, index) => `@observations.r${index}`).join(',')}];
        columns: [{key:"name",label:"Received (UTC)"}, {key:"x_record.elapsed",label:"Elapsed seconds"},
          {key:"x_record.value",label:"Exact value"}, {key:"x_record.reason",label:"Observation / gap"},
          {key:"x_record.coverage",label:"Coverage"}, {key:"x_record.epoch",label:"Epoch"}];
      } publication {size: content; fit: none;}
    }
    view trends ${quote(metric.label)} { data: [@observations];
      projection {kind: panels; profile: "panels.composed@1"; columns: 1;
        panels: [${points.length ? '{id:"chart",title:"Retained sample points",row:0,column:0,view:@chart},' : ''}
          {id:"detail",title:"Exact observations",row:${points.length ? 1 : 0},column:0,view:@detail}];
      } publication {size: content; fit: none;}
    }`};
}
