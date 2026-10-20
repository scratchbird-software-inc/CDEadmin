import {useEffect,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';

const fresh=()=>({name:'',data_type:'',notNull:false,default:'',generated:'',storage:'virtual',check:'',collation:'',
  referenceTable:'',referenceColumn:'',on_update:'NO ACTION',on_delete:'NO ACTION',match:'',deferrable:false,initially:'IMMEDIATE',names:{}});
const constraintKinds={not_null:'NOT NULL',default:'Default',generated:'Generated',check:'CHECK',collation:'Collation',references:'Reference'};
const actions=['NO ACTION','RESTRICT','SET NULL','SET DEFAULT','CASCADE'];

export function structuredColumns(columns) {
  return columns.map(row=>({name:row.name,data_type:row.data_type,nullable:!row.notNull,
    ...(row.default ? {default:row.default}:{}),...(row.check ? {check:row.check}:{}),
    ...(row.collation ? {collation:row.collation}:{}),
    ...(row.generated ? {generated:{expression:row.generated,storage:row.storage}}:{}),
    ...(row.referenceTable ? {references:{table:row.referenceTable,...(row.referenceColumn ? {column:row.referenceColumn}:{}),
      on_update:row.on_update,on_delete:row.on_delete,...(row.match ? {match:row.match}:{}),
      deferrable:row.deferrable,initially:row.initially}}:{}),
    constraint_names:Object.fromEntries(Object.entries(row.names).filter(([,value])=>value))}));
}

export default function SQLiteColumnDesign({tables,objects,disabled,onGenerate}) {
  const [table,setTable]=useState(''),[columns,setColumns]=useState([fresh()]);
  useEffect(()=>{if(!tables.some(item=>item.resource_id===table))setTable(tables[0]?.resource_id || '');},[tables,table]);
  const change=(index,key,value)=>setColumns(current=>current.map((row,i)=>i===index ? {...row,[key]:value}:row));
  return <Box component="details" sx={{mt:1}}>
    <summary>Native column additions</summary>
    <Alert severity="info">Generate a DDN design from column properties, then preview and review it. Blank declared types create native untyped columns. SQLite checks existing rows during apply.</Alert>
    <TextField disabled={disabled} select size="small" label="Column addition table" value={table} sx={{minWidth:220}}
      onChange={event=>setTable(event.target.value)}>{tables.map(item=><MenuItem key={item.resource_id} value={item.resource_id}>{item.name}</MenuItem>)}</TextField>
    {columns.map((row,index)=><Box component="fieldset" key={index} disabled={disabled} sx={{mt:1}}>
      <legend>Column {index+1}</legend>
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap'}}>
        <TextField disabled={disabled} size="small" label={`Column ${index+1} name`} value={row.name} onChange={event=>change(index,'name',event.target.value)} />
        <TextField disabled={disabled} size="small" label={`Column ${index+1} declared type`} helperText="Blank means no declared type" value={row.data_type} onChange={event=>change(index,'data_type',event.target.value)} />
        <FormControlLabel label={`Column ${index+1} NOT NULL`} control={<Checkbox disabled={disabled} checked={row.notNull} onChange={event=>change(index,'notNull',event.target.checked)} />} />
        <TextField disabled={disabled} size="small" label={`Column ${index+1} default expression`} value={row.default} onChange={event=>change(index,'default',event.target.value)} />
        <TextField disabled={disabled} size="small" label={`Column ${index+1} collation`} value={row.collation} onChange={event=>change(index,'collation',event.target.value)} />
        <TextField disabled={disabled} size="small" label={`Column ${index+1} CHECK expression`} value={row.check} onChange={event=>change(index,'check',event.target.value)} />
        <TextField disabled={disabled} size="small" label={`Column ${index+1} generated expression`} value={row.generated} onChange={event=>change(index,'generated',event.target.value)} />
        <TextField disabled={disabled} select size="small" label={`Column ${index+1} generated storage`} value={row.storage} onChange={event=>change(index,'storage',event.target.value)}>
          <MenuItem value="virtual">Virtual</MenuItem><MenuItem value="stored">Stored</MenuItem>
        </TextField>
      </Box>
      <Box component="details" sx={{mt:1}}><summary>Column {index+1} reference</summary>
        <Box sx={{display:'flex',gap:1,flexWrap:'wrap'}}>
          <TextField disabled={disabled} select size="small" label={`Column ${index+1} referenced table`} value={row.referenceTable} sx={{minWidth:180}}
            onChange={event=>{change(index,'referenceTable',event.target.value);change(index,'referenceColumn','');}}>
            <MenuItem value="">No reference</MenuItem>{tables.map(item=><MenuItem key={item.resource_id} value={item.name}>{item.name}</MenuItem>)}
          </TextField>
          <TextField disabled={disabled} select size="small" label={`Column ${index+1} referenced column`} value={row.referenceColumn} sx={{minWidth:180}} onChange={event=>change(index,'referenceColumn',event.target.value)}>
            <MenuItem value="">Native primary key</MenuItem>{objects.filter(item=>item.kind==='column' && item.path?.[0]==='main' && item.path?.[1]===row.referenceTable).map(item=><MenuItem key={item.resource_id} value={item.name}>{item.name}</MenuItem>)}
          </TextField>
          {['on_update','on_delete'].map(key=><TextField disabled={disabled} key={key} select size="small" label={`Column ${index+1} ${key==='on_update' ? 'ON UPDATE':'ON DELETE'}`} value={row[key]} onChange={event=>change(index,key,event.target.value)}>
            {actions.map(action=><MenuItem key={action} value={action}>{action}</MenuItem>)}
          </TextField>)}
          <TextField disabled={disabled} size="small" label={`Column ${index+1} MATCH name`} value={row.match} onChange={event=>change(index,'match',event.target.value)} />
          <FormControlLabel label={`Column ${index+1} DEFERRABLE`} control={<Checkbox disabled={disabled} checked={row.deferrable} onChange={event=>change(index,'deferrable',event.target.checked)} />} />
          <TextField disabled={disabled} select size="small" label={`Column ${index+1} initial constraint timing`} value={row.initially} onChange={event=>change(index,'initially',event.target.value)}>
            <MenuItem value="IMMEDIATE">Immediate</MenuItem><MenuItem value="DEFERRED">Deferred</MenuItem>
          </TextField>
        </Box>
      </Box>
      <Box component="details" sx={{mt:1}}><summary>Column {index+1} constraint names</summary>
        <Box sx={{display:'flex',gap:1,flexWrap:'wrap'}}>{Object.entries(constraintKinds).map(([kind,label])=>
          <TextField disabled={disabled} key={kind} size="small" label={`Column ${index+1} ${label} constraint name`} value={row.names[kind] || ''}
            onChange={event=>change(index,'names',{...row.names,[kind]:event.target.value})} />)}</Box>
      </Box>
      <Button disabled={disabled || columns.length===1} onClick={()=>setColumns(current=>current.filter((_,i)=>i!==index))}>Remove column {index+1}</Button>
    </Box>)}
    <Button disabled={disabled || columns.length>=32} onClick={()=>setColumns(current=>[...current,fresh()])}>Add another native column</Button>
    <Button disabled={disabled || !table} onClick={()=>onGenerate(table,structuredColumns(columns))}>Generate column design</Button>
  </Box>;
}
SQLiteColumnDesign.propTypes={tables:PropTypes.array.isRequired,objects:PropTypes.array.isRequired,
  disabled:PropTypes.bool,onGenerate:PropTypes.func.isRequired};
