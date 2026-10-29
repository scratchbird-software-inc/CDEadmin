import {declaration, dataSource, displayText, labelText, ref, sourceHeader, viewSource} from './source.js';

export const METRIC_COLUMNS = Object.freeze(['id','panel','measure','value','unit','rate']);
export const metricChannel = module => module + '.observations';

// All live values are provider data. The authored view, layout and labels are
// separate from a dedicated collector and never grant collection authority.
export function dashboardPanelFiles(panels, title, moduleName) {
  const seen = new Set();
  const rows = panels.flatMap(panel => panel.rows.map((row, index) => {
    const id = row.bindingId ?? `${panel.id}_${index}`;
    if(!/^[a-z][a-z0-9_]{0,2047}$/.test(id) || seen.has(id)) throw new Error('Invalid dashboard binding identity.');
    seen.add(id);
    return [id, panel.id, ...[row[0] ?? 'Unavailable',row[1] ?? 'Unavailable',row[2] ?? '',row[3] ?? ''].map(value=>displayText(String(value)))];
  }));
  const feed = declaration('source', 'metric_feed', 'host', {channel: metricChannel(moduleName), update: 'keyed'});
  const data = dataSource('observations', METRIC_COLUMNS, rows, {source: ref('metric_feed'), key: 'id'});
  const columns = [{id:'measure',label:'Measure'},{id:'value',label:'Value'},
    {id:'unit',label:'Unit / meaning'},{id:'rate',label:'Per second'}];
  const viewIds=new Map(),used=new Set();
  panels.forEach((panel,index)=>{let id=panel.id.length<=256?panel.id:'panel_long_'+index;while(used.has(id))id+='x';used.add(id);viewIds.set(panel.id,id);});
  const views = panels.map(panel => viewSource(viewIds.get(panel.id), panel.title, 'table.records@1', {
    columns, filter: [{key:'panel',op:'eq',value:panel.id}]}, ['observations'])).join('\n');
  const pages = [];
  for(let offset=0; offset<panels.length; offset+=12) {
    const page = panels.slice(offset, offset+12), number = pages.length+1;
    pages.push(viewSource(number === 1 ? 'dashboard' : `dashboard_page_${number}`,
      number === 1 ? title : `${title} — page ${number}`, 'panels.composed@1', {
        columns: 2, panels: page.map((panel,index) => ({target: ref(viewIds.get(panel.id)), kind: 'view', title: labelText(panel.title),
          layout: {row: Math.floor(index/2), column: index%2}}))}));
  }
  return {'dashboard.ddn': sourceHeader(moduleName) + feed + data + views + pages.join('\n')};
}
