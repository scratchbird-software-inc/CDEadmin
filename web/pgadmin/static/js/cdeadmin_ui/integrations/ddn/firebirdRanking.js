import BigNumber from 'bignumber.js';

export const RANK_FIELDS = Object.freeze({
  table_details: ['record_seq_reads_per_second', 'record_idx_reads_per_second',
    'record_inserts_per_second', 'record_updates_per_second', 'record_deletes_per_second',
    'record_waits_per_second', 'record_conflicts_per_second', 'backversion_reads_per_second'],
  schema_counts: ['count'], user_counts: ['count'], wire_counts: ['count'],
  endpoint_databases: ['allocated_bytes', 'memory_used', 'user_attachments',
    'page_reads_per_second', 'page_writes_per_second', 'oldest_age_seconds'],
  version_distribution: ['count'],
});
const quote = (value) => JSON.stringify(String(value ?? 'Unavailable'));

export function fleetRankingSample(snapshot, engineMode=false) {
  const servers = engineMode ? snapshot?.servers || [] : [{
    server_id: snapshot?.navigation?.server_id, name: snapshot?.navigation?.name, aggregate: snapshot?.aggregate,
  }];
  const rows = servers.flatMap((server) => (server.aggregate?.ranked_databases || []).map((database) => ({
    ...database.metrics, table_name: `${server.name} [${server.server_id}] / ${database.name} [${database.target_id}]`,
  })));
  return {groups: {endpoint_databases: {status: 'available', values: {rows, truncated: false}}}};
}

export function fleetVersionSample(snapshot) {
  const counts = new Map();
  for(const server of snapshot?.servers || []) {
    const label = `${server.version || 'Unknown version'} / ${server.architecture || 'Unknown architecture'}`;
    counts.set(label, (counts.get(label) || 0) + 1);
  }
  return {groups: {version_distribution: {status: 'available', values: {
    rows: [...counts].map(([table_name, count]) => ({table_name, count: String(count)})),
  }}}};
}

export function rankingRows(rows, field) {
  return rows.flatMap((row, index) => {
    const raw = row[field];
    if(typeof raw !== 'string' || !/^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(raw)) return [];
    const exact = new BigNumber(raw);
    if(!exact.isFinite() || exact.isNegative()) return [];
    const numeric = exact.toNumber();
    const drawable = Number.isFinite(numeric) && numeric <= Number.MAX_SAFE_INTEGER &&
      !(numeric === 0 && !exact.isZero());
    const label = row.table_name ?? (row.kind ? `${row.kind} (system flag ${row.system_flag ?? 'unknown'})` :
      row.plugin ? `${row.plugin}: active=${row.active}, admin=${row.admin}` :
        `${row.transport}: encrypted=${row.encrypted ?? 'unknown'}`);
    return [{index, exact, raw, numeric: drawable ? numeric : null, label}];
  }).sort((a, b) => b.exact.comparedTo(a.exact) || a.index - b.index).slice(0, 20);
}

export function firebirdRankingFiles(sample, category, field) {
  if(!RANK_FIELDS[category]?.includes(field)) return null;
  const group = sample?.groups?.[category];
  const rows = rankingRows(group?.status === 'available' ? group.values?.rows || [] : [], field);
  const points = rows.filter((row) => row.numeric !== null);
  const records = rows.map((row, index) => `record r${index} ${quote(row.label)} {
    x_record: {exact:${quote(row.raw)},geometry:${quote(row.numeric === null ? 'Outside chart range' : 'Approximate')},
      value:${row.numeric === null ? 0 : row.numeric},label:${quote(row.label)}}; }`).join('\n');
  const chart = points.length ? `view bars "Top20 within captured coverage" {data:[@observations];
    projection {kind:chart;profile:"chart.basic@1";mark:bar;
      records:[${rows.flatMap((row, index) => row.numeric === null ? [] : [`@observations.r${index}`]).join(',')}];
      x:"x_record.label";y:"x_record.value";width:1000px;height:400px;}
    publication {size:content;fit:none;}}
  ` : '';
  return {'ranking.ddn': `ddn "0.5"; module "scratchrobin.firebird.ranking";
    data observations {${records || 'record empty "No comparable captured observations" {}'}}
    ${chart}
    view exact "Exact ranked observations" {data:[@observations];projection {kind:table;profile:"table.records@1";
      records:[${rows.length ? rows.map((_, index) => `@observations.r${index}`).join(',') : '@observations.empty'}];
      columns:[{key:"name",label:"Native category"},{key:"x_record.exact",label:"Exact value"},
        {key:"x_record.geometry",label:"Chart representation"}];} publication {size:content;fit:none;}}
    view ranking ${quote(field.replaceAll('_', ' ') + (group?.values?.truncated ? ' — capture truncated' : ' — captured observations'))} {
      data:[@observations];projection {kind:panels;profile:"panels.composed@1";columns:1;
        panels:[${points.length ? '{id:"bars",title:"Approximate bars",row:0,column:0,view:@bars},' : ''}
          {id:"exact",title:"Exact values",row:${points.length ? 1 : 0},column:0,view:@exact}];}
      publication {size:content;fit:none;}}
  `};
}
