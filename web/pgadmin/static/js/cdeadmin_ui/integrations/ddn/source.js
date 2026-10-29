// Encoder for the adopted notation. Parsing and validation belong to DDN.
export const DDN_CONTRACT = 'ddn-next-1';
export const DDN_FORMAT = 'ddn-source-workspace@1';
export const quoteText = value => {
  const text = String(value);
  if(/[\r\n\0]/.test(text)) throw new Error('DDN structural names cannot contain line breaks or NUL.');
  return '"' + text.replaceAll('"', '""') + '"';
};
const scalar = value => {
  if(typeof value === 'string') return quoteText(value);
  if(value === null || typeof value === 'boolean' || typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  throw new Error('Unsupported DDN scalar.');
};
const valueSource = (key, value, indent) => {
  const lead = ' '.repeat(indent) + key;
  if(Array.isArray(value)) return value.length ? lead + '\n' + value.map(row => valueSource('item', row, indent + 4)).join('') : lead + ' empty list\n';
  if(value && typeof value === 'object') return Object.keys(value).length ? lead + '\n' + properties(value, indent + 4) : lead + ' empty record\n';
  if(typeof value === 'string' && /[\r\n]/.test(value)) return lead + '\n' + value.split('\n').map(line => ' '.repeat(indent + 4) + line).join('\n') + '\n';
  return lead + ' ' + scalar(value) + '\n';
};
export const properties = (record, indent=8) => Object.entries(record).map(([key, value]) =>
  valueSource(key === 'item' || /[\s"']/.test(key) ? quoteText(key) : key, value, indent)).join('');
export const labelText = value => {
  const text=String(displayText(value));
  if(text.length<=1024)return text;
  let prefix=text.slice(0,1023);
  if(/[\uD800-\uDBFF]$/.test(prefix))prefix=prefix.slice(0,-1);
  return prefix+'…';
};
export const ref = (id, file) => ({id, ...(file ? {file} : {})});
export const declaration = (kind, id, role, record) => `${kind} ${quoteText(id)}${role ? ' as ' + quoteText(role) : ''}\n    with\n${properties({id, ...record})}\n`;
export const sourceHeader = module => `version ${DDN_CONTRACT}\n// ScratchRobin mapping: ${module}\n\n`;
export const displayText = value => typeof value==='string' && /[\r\n\0]/.test(value) ? JSON.stringify(value).slice(1,-1) : value;
const displayValues = value => Array.isArray(value) ? value.map(displayValues) : value && typeof value==='object' ? Object.fromEntries(Object.entries(value).map(([key,item])=>[key,displayValues(item)])) : displayText(value);
export const recordSource = (id,title,record,block='observations') => declaration('element',id,'record',
  {title:labelText(title),metadata:{x_record:{...displayValues(record),native_json:JSON.stringify(record)}},tags:[block]});
export const viewSource = (id, title, profile, options, records=[]) => declaration('view', id, profile,
  {title:labelText(title), ...(String(title).length>1024?{description:String(title)}:{}), selection: {include: []}, projection: {options: {...options, ...(records.length ? {records: records.map(row => typeof row === 'string' ? ref(row) : row)} : {})}}});
export const tableSource = (id, title, records, columns) => viewSource(id, title, 'table.records@1', {
  columns: columns.map((column, index) => ({id: 'c_' + index, path: column.key, label: column.label}))}, records);
export const dataSource = (id, columns, rows, extras={}) => declaration('data', id, null,
  {columns: columns.map(column => typeof column === 'string' ? {id: column, type: 'text'} : column), rows, ...extras});
export const sourceWorkspace = (files, entry, view) => ({format: DDN_FORMAT, files, entry, view});

export function observationTable(filename,view,title,rows,fields,moduleName,empty='No visible observations') {
  const captured=rows.length?rows:[{observation:empty}];
  const keys=rows.length?fields:['observation'];
  return {[filename]:sourceHeader(moduleName)+captured.map((row,index)=>recordSource('r'+index,
    String(row[keys[0]] ?? 'NULL'),Object.fromEntries(keys.map(key=>[key,String(row[key] ?? 'NULL')])))).join('')+
    tableSource(view,title,captured.map((_,index)=>'r'+index),keys.map(key=>({key:'metadata.x_record.'+key,label:key.replaceAll('_',' ')})))};
}
