import {recordSource,sourceHeader,tableSource,viewSource,ref} from './source.js';
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
  const table=rows.length?rows:[{label:'No comparable captured observations',raw:'Unavailable',numeric:null}];
  const records=table.map((row,index)=>recordSource('r'+index,row.label,{exact:row.raw,
    geometry:row.numeric===null?'Outside chart range':'Approximate',value:row.numeric ?? 0,label:row.label})).join('');
  const chart=points.length?viewSource('bars','Top20 within captured coverage','chart.basic@1',
    {mark:'bar',x:'metadata.x_record.label',y:'metadata.x_record.value'},rows.flatMap((row,index)=>row.numeric===null?[]:['r'+index])):'';
  return {'ranking.ddn':sourceHeader('scratchrobin.firebird.ranking')+records+chart+
    tableSource('exact','Exact ranked observations',table.map((_,index)=>'r'+index),[
      {key:'title',label:'Native category'},{key:'metadata.x_record.exact',label:'Exact value'},
      {key:'metadata.x_record.geometry',label:'Chart representation'}])+
    viewSource('ranking',field.replaceAll('_',' ')+(group?.values?.truncated?' — capture truncated':' — captured observations'),
      'panels.composed@1',{columns:1,panels:[...(points.length?[{target:ref('bars'),kind:'view',title:'Approximate bars',layout:{row:0,column:0}}]:[]),
        {target:ref('exact'),kind:'view',title:'Exact values',layout:{row:points.length?1:0,column:0}}]})};
}
