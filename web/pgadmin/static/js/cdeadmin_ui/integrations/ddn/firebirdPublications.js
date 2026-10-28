import {declaration,ref,sourceHeader,quoteText} from './source.js';
// Native publication membership only: this diagram never invents replica nodes or lag.
export function firebirdPublicationFiles(sample) {
  const publications = sample?.groups?.publication_details;
  const memberships = sample?.groups?.publication_table_details;
  const pubs = new Map(), tables = new Map(), records = [], links = [];
  const node = (map, prefix, name, label) => {
    if(!map.has(name)) {
      const id = prefix + map.size;
      map.set(name, id);
      records.push({id,source:declaration('element',id,'record',{title:String(label ?? 'Unknown')})});
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
    links.push({id:'m'+index,source:declaration('relation','m'+index,'flow',{title:'publication membership',endpoints:[{definition:ref(pub)},{definition:ref(table)}]})});
  }
  if(!records.length) records.push({id:'empty',source:declaration('element','empty','record',{title:
    publications?.status!=='available' || memberships?.status!=='available'?'Publication sources unavailable':'No visible publications or memberships'})});
  const definitions=[...records,...links];
  return {'publications.ddn':sourceHeader('scratchrobin.firebird.publications')+definitions.map(item=>item.source).join('')+
    declaration('view','publications','ddn@1',{title:'Observed publication membership — not replication health',
      selection:{include:definitions.map(item=>ref(item.id))},layout:{algorithm:'layered'}})+
    definitions.map(item=>'    use '+quoteText(item.id)+' named '+quoteText('appearance:'+item.id)+'\n').join('')};
}
