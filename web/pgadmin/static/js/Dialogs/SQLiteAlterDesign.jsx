import {useEffect,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,MenuItem,TextField} from '@mui/material';

const actions=[['rename-table','Rename table'],['rename-column','Rename column'],
  ['drop-column','Remove column'],['drop-constraint','Remove named constraint'],
  ['drop-not-null','Remove NOT NULL'],['set-not-null','Set NOT NULL'],['add-check','Add CHECK']];

export default function SQLiteAlterDesign({tables,objects,disabled,onGenerate}) {
  const [table,setTable]=useState(''),[action,setAction]=useState('rename-table');
  const [column,setColumn]=useState(''),[name,setName]=useState(''),[expression,setExpression]=useState('');
  const [conflict,setConflict]=useState('');
  useEffect(()=>{if(!tables.some(row=>row.resource_id===table))setTable(tables[0]?.resource_id || '');},[tables,table]);
  const selected=tables.find(row=>row.resource_id===table);
  const columns=objects.filter(row=>row.kind==='column' && row.path?.[0]===selected?.path[0] && row.path?.[1]===selected?.name);
  const needsColumn=['rename-column','drop-column','drop-not-null','set-not-null'].includes(action);
  const needsName=['rename-table','rename-column','drop-constraint','add-check'].includes(action);
  const needsConflict=['set-not-null','add-check'].includes(action);
  useEffect(()=>{if(!columns.some(row=>row.name===column))setColumn(columns[0]?.name || '');},[columns,column]);
  return <Box component="details" sx={{mt:1}}><summary>Native table alterations</summary>
    <Alert severity="info">Generate the desired DDN with SQLite, then inspect and confirm the native statements. Column removal discards its data inside your transaction. Existing rows are checked during apply.</Alert>
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap'}}>
      <TextField select size="small" label="Native alteration table" value={table} disabled={disabled} sx={{minWidth:220}}
        onChange={event=>setTable(event.target.value)}>{tables.map(row=><MenuItem key={row.resource_id} value={row.resource_id}>{row.path.join(' / ')}</MenuItem>)}</TextField>
      <TextField select size="small" label="Native table alteration" value={action} disabled={disabled} sx={{minWidth:200}}
        onChange={event=>{setAction(event.target.value);setName('');setExpression('');setConflict('');}}>
        {actions.map(([value,label])=><MenuItem key={value} value={value}>{label}</MenuItem>)}
      </TextField>
      {needsColumn && <TextField select size="small" label="Native alteration column" value={column} disabled={disabled} sx={{minWidth:180}}
        onChange={event=>setColumn(event.target.value)}>{columns.map(row=><MenuItem key={row.resource_id} value={row.name}>{row.name}</MenuItem>)}</TextField>}
      {needsName && <TextField size="small" label={action==='drop-constraint' ? 'Native constraint name':action==='add-check' ? 'CHECK name (optional)':'New native name'}
        value={name} disabled={disabled} onChange={event=>setName(event.target.value)} />}
      {needsConflict && <TextField select size="small" label="Native constraint conflict policy" value={conflict} disabled={disabled} sx={{minWidth:200}}
        onChange={event=>setConflict(event.target.value)}><MenuItem value="">Native default</MenuItem>
        {['ROLLBACK','ABORT','FAIL','IGNORE','REPLACE'].map(value=><MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>}
    </Box>
    {action==='add-check' && <TextField fullWidth multiline label="Native CHECK expression" value={expression} disabled={disabled} sx={{mt:1}}
      onChange={event=>setExpression(event.target.value)} />}
    <Button disabled={disabled || !table || needsColumn && !column || needsName && action!=='add-check' && !name || action==='add-check' && !expression.trim()}
      onClick={()=>onGenerate({action,resource_id:table,...(needsColumn ? {column}:{}),
        ...(needsName && (action!=='add-check' || name) ? {name}:{}),...(needsConflict ? {conflict}:{}),
        ...(action==='add-check' ? {expression}:{})})}>Generate native alteration design</Button>
  </Box>;
}
SQLiteAlterDesign.propTypes={tables:PropTypes.array.isRequired,objects:PropTypes.array.isRequired,
  disabled:PropTypes.bool,onGenerate:PropTypes.func.isRequired};
