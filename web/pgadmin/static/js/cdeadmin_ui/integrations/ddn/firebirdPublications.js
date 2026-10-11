// Native publication membership only: this diagram never invents replica nodes or lag.
const quote = (value) => JSON.stringify(String(value ?? 'Unknown'));
export function firebirdPublicationFiles(sample) {
  const publications = sample?.groups?.publication_details;
  const memberships = sample?.groups?.publication_table_details;
  const pubs = new Map(), tables = new Map(), records = [], links = [];
  const node = (map, prefix, name, label) => {
    if(!map.has(name)) {
      const id = prefix + map.size;
      map.set(name, id);
      records.push(`record ${id} ${quote(label)} {}`);
    }
    return map.get(name);
  };
  for(const row of publications?.status === 'available' ? (publications.values?.rows || []).slice(0, 100) : []) {
    node(pubs, 'p', row.publication_name,
      `${row.publication_name}: active=${row.active_flag ?? 'unknown'}, auto-enable=${row.auto_enable ?? 'unknown'}`);
  }
  for(const [index, row] of (memberships?.status === 'available' ? (memberships.values?.rows || []).slice(0, 100) : []).entries()) {
    const pub = node(pubs, 'p', row.publication_name, `${row.publication_name}: attributes not captured`);
    const table = node(tables, 't', row.table_name, row.table_name);
    links.push(`relation m${index} "publication membership" @${pub} -> @${table} {kind:flow;}`);
  }
  if(!records.length) records.push(`record empty ${quote(
    publications?.status !== 'available' || memberships?.status !== 'available' ?
      'Publication sources unavailable' : 'No visible publications or memberships')} {}`);
  return {'publications.ddn': `ddn "0.5"; module "scratchrobin.firebird.publications";
    data topology {${records.join('\n')} ${links.join('\n')}}
    view publications "Observed publication membership — not replication health" {data:[@topology];
      publication {size:content;fit:none;}}
  `};
}
