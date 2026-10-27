import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TextField} from '@mui/material';

export default function SQLiteNativeArrays({post,ensureSession,sessionId,databaseTargetId,disabled,onBusyChange,onLoad}) {
  const [inventory,setInventory]=useState(null),[selected,setSelected]=useState(null),[page,setPage]=useState(0);
  const [type,setType]=useState('int64'),[values,setValues]=useState('["9007199254740993"]');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[confirm,setConfirm]=useState(false);
  const serial=useRef(0),previous=useRef(sessionId);
  useEffect(() => {
    if(previous.current && previous.current!==sessionId){serial.current++;setInventory(null);setSelected(null);setConfirm(false);setError('');setPage(0);}
    previous.current=sessionId;
  },[sessionId]);
  useEffect(() => () => {serial.current++;},[]);
  const run=async request => {
    const token=++serial.current;setBusy(true);onBusyChange(true);setError('');
    try {
      const active=sessionId || await ensureSession();
      const result=await post({action:'sqlite_native_arrays',session_id:active,database_target_id:databaseTargetId,request});
      if(token!==serial.current)return;
      if(result.arrays){setInventory(result);setPage(result.offset/25);}
      if(result.array)setSelected(result.array);
      if(result.closed){setSelected(null);setInventory(current => current && {...current,arrays:current.arrays.filter(item => item.array_id!==result.array_id)});}
      setConfirm(false);
    } catch(failure) {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {setBusy(false);onBusyChange(false);}
  };
  const blocked=disabled || busy;
  const create=() => {
    try {const parsed=JSON.parse(values);run({operation:'create',type,values:parsed});}
    catch(failure){setError(failure.message);}
  };
  return <Box component="details" sx={{mt:1}}><summary>SQLite native arrays</summary>
    <Alert severity="info">Create typed array parameters for carray(:items) queries on this connection. Values are released when the connection closes. Use decimal strings for wide integers and base64 envelopes for blobs. TEXT arrays support NULL and empty strings; embedded zero bytes require BLOB arrays.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={blocked} onClick={() => run({operation:'inventory',offset:page*25,limit:25})}>Inspect native arrays</Button>
    {inventory && <>
      {!inventory.helper_available && <Alert severity="warning">{inventory.unavailable_reason}</Alert>}
      <Box component="details"><summary>SQLite native array API identity</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:180,overflow:'auto'}}>{JSON.stringify(inventory.program,null,2)}</Box></Box>
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <TextField select size="small" label="Native array type" value={type} disabled={blocked} onChange={event => setType(event.target.value)}>
          {['int32','int64','double','text','blob'].map(name => <MenuItem key={name} value={name}>{name}</MenuItem>)}
        </TextField>
        <TextField multiline minRows={3} size="small" label="Native array values (JSON)" value={values} disabled={blocked} onChange={event => setValues(event.target.value)} />
        <Button disabled={blocked || !inventory.helper_available} onClick={create}>Create native array</Button>
      </Box>
      <Table size="small" aria-label="Native SQLite arrays"><TableHead><TableRow>{['Array','Type','Elements','Native data bytes','Inspect'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
        {inventory.arrays.map(item => <TableRow key={item.array_id}><TableCell>{item.array_id}</TableCell><TableCell>{item.type_name}</TableCell><TableCell>{item.element_count}</TableCell><TableCell>{item.native_data_bytes}</TableCell><TableCell><Button disabled={blocked} onClick={() => run({operation:'status',array_id:item.array_id})}>Inspect array {item.array_id}</Button></TableCell></TableRow>)}
      </TableBody></Table>
      <Button disabled={blocked || page===0} onClick={() => run({operation:'inventory',offset:(page-1)*25,limit:25})}>Previous native arrays</Button>
      <Button disabled={blocked || !inventory.more} onClick={() => run({operation:'inventory',offset:(page+1)*25,limit:25})}>Next native arrays</Button>
    </>}
    {selected && <Box sx={{my:1}}>
      <Alert severity="info">Array {selected.array_id}: {selected.type_name}. Elements: {selected.element_count}. Native data bytes: {selected.native_data_bytes}.</Alert>
      <Button disabled={blocked} onClick={() => onLoad({source:'SELECT value, typeof(value) AS storage_class FROM carray(:items)',parameters:{items:selected.binding}})}>Use native array in editor</Button>
      <FormControlLabel label="Release this array and its parameter bindings" control={<Checkbox checked={confirm} disabled={blocked} onChange={event => setConfirm(event.target.checked)} />} />
      <Button disabled={blocked || !confirm} onClick={() => run({operation:'close',array_id:selected.array_id,confirmed:true})}>Close native array</Button>
    </Box>}
  </Box>;
}
SQLiteNativeArrays.propTypes={post:PropTypes.func.isRequired,ensureSession:PropTypes.func.isRequired,sessionId:PropTypes.string,
  databaseTargetId:PropTypes.string.isRequired,disabled:PropTypes.bool,onBusyChange:PropTypes.func.isRequired,onLoad:PropTypes.func.isRequired};
