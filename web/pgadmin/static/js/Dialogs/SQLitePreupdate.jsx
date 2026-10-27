import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,Table,TableBody,TableCell,TableHead,TableRow,TextField} from '@mui/material';

export default function SQLitePreupdate({post,ensureSession,sessionId,databaseTargetId,disabled,onBusyChange}) {
  const [inventory,setInventory]=useState(null),[status,setStatus]=useState(null),[events,setEvents]=useState([]),[more,setMore]=useState(false);
  const [maxEvents,setMaxEvents]=useState('1000'),[maxBytes,setMaxBytes]=useState('16777216'),[confirm,setConfirm]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const serial=useRef(0),previous=useRef(sessionId);
  useEffect(() => {
    if(previous.current && previous.current!==sessionId){serial.current++;setInventory(null);setStatus(null);setEvents([]);setMore(false);setConfirm(false);setError('');}
    previous.current=sessionId;
  },[sessionId]);
  useEffect(() => () => {serial.current++;},[]);
  const run=async request => {
    const token=++serial.current;setBusy(true);onBusyChange(true);setError('');
    try {
      const active=sessionId || await ensureSession();
      const value=await post({action:'sqlite_native_preupdate',session_id:active,database_target_id:databaseTargetId,request});
      if(token!==serial.current)return;
      if(request.operation==='inventory')setInventory(value);
      if(value.status)setStatus(value.status);
      if(value.events){setEvents(value.events);setMore(value.more);}
      if(['start','clear'].includes(request.operation)){setEvents([]);setMore(false);}
      setConfirm(false);
    } catch(failure) {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {setBusy(false);onBusyChange(false);}
  };
  const blocked=disabled || busy;
  const page=after => run({operation:'events',run_id:status.run_id,after_sequence:after,limit:25});
  return <Box component="details" sx={{mt:1}}><summary>SQLite before-change diagnostics</summary>
    <Alert severity="info">Native preupdate callbacks observe table changes before they happen, including changes later rolled back. These records do not prove commit. Retention is bounded; dropped observations are counted. Stop this hook before opening session captures. Schema changes, virtual tables and system tables have separate diagnostics.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={blocked} onClick={() => run({operation:'inventory'})}>Inspect native preupdate support</Button>
    {inventory && <>
      {!inventory.helper_available && <Alert severity="warning">{inventory.unavailable_reason}</Alert>}
      <Box component="details"><summary>SQLite native preupdate API identity</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:160,overflow:'auto'}}>{JSON.stringify(inventory.program,null,2)}</Box></Box>
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <TextField size="small" label="Maximum retained preupdate events" value={maxEvents} disabled={blocked || status?.enabled} onChange={event => setMaxEvents(event.target.value)} />
        <TextField size="small" label="Maximum retained preupdate JSON bytes" value={maxBytes} disabled={blocked || status?.enabled} onChange={event => setMaxBytes(event.target.value)} />
        <Button disabled={blocked || status?.enabled || !inventory.helper_available} onClick={() => run({operation:'start',max_events:Number(maxEvents),max_json_bytes:maxBytes})}>Start native preupdate observations</Button>
      </Box>
    </>}
    {status && <>
      <Alert severity={status.dropped_events!=='0' ? 'warning':'info'}>Preupdate hook: {status.enabled ? 'enabled':'stopped'}. Observed: {status.observed_events}. Retained: {status.retained_events}. Dropped: {status.dropped_events}. JSON bytes: {status.retained_json_bytes}.</Alert>
      <Button disabled={blocked} onClick={() => run({operation:'status'})}>Refresh native preupdate state</Button>
      <Button disabled={blocked || !status.enabled} onClick={() => run({operation:'stop',run_id:status.run_id})}>Stop native preupdate observations</Button>
      <Button disabled={blocked || !status.run_id} onClick={() => page('0')}>Load first native preupdate events</Button>
      <Button disabled={blocked || !more || !events.length} onClick={() => page(events.at(-1).sequence)}>Next native preupdate events</Button>
      <FormControlLabel label="Discard retained before-change observations" control={<Checkbox checked={confirm} disabled={blocked} onChange={event => setConfirm(event.target.checked)} />} />
      <Button disabled={blocked || !confirm || !status.run_id} onClick={() => run({operation:'clear',run_id:status.run_id,confirmed:true})}>Clear native preupdate observations</Button>
      <Table size="small" aria-label="Native SQLite before-change events"><TableHead><TableRow>{['Sequence','Operation','Database','Table','Trigger depth','Typed values'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
        {events.map(event => <TableRow key={event.sequence}><TableCell>{event.sequence}</TableCell><TableCell>{event.operation}</TableCell><TableCell>{typeof event.database==='string' ? event.database:JSON.stringify(event.database)}</TableCell><TableCell>{typeof event.table==='string' ? event.table:JSON.stringify(event.table)}</TableCell><TableCell>{event.depth}</TableCell><TableCell><details><summary>Inspect native event {event.sequence}</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:240,overflow:'auto'}}>{JSON.stringify(event,null,2)}</Box></details></TableCell></TableRow>)}
      </TableBody></Table>
      <Alert severity="info">Raw native rowid fields are undefined for WITHOUT ROWID tables, old rowid on INSERT, and new rowid on DELETE. Use the typed column values and the table definition when interpreting identities. Closing the connection releases observations.</Alert>
      <Box component="pre" aria-label="Native SQLite preupdate state" sx={{whiteSpace:'pre-wrap',maxHeight:180,overflow:'auto'}}>{JSON.stringify(status,null,2)}</Box>
    </>}
  </Box>;
}
SQLitePreupdate.propTypes={post:PropTypes.func.isRequired,ensureSession:PropTypes.func.isRequired,sessionId:PropTypes.string,
  databaseTargetId:PropTypes.string.isRequired,disabled:PropTypes.bool,onBusyChange:PropTypes.func.isRequired};
