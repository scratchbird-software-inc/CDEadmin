import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import SQLiteCaptureExports from './SQLiteCaptureExports';
import SQLiteChangesetApply from './SQLiteChangesetApply';
import {Alert,Box,Button,Checkbox,FormControlLabel,Table,TableBody,TableCell,TableHead,TableRow,TextField,MenuItem} from '@mui/material';

export default function SQLiteNativeSessions({post,ensureSession,sessionId,databaseTargetId,endpointUrl,disabled,onBusyChange}) {
  const [inventory,setInventory]=useState(null),[capture,setCapture]=useState(null),[page,setPage]=useState(0);
  const [database,setDatabase]=useState('main'),[estimate,setEstimate]=useState(false),[rowids,setRowids]=useState(false);
  const [filterPattern,setFilterPattern]=useState('*'),[excludeFilter,setExcludeFilter]=useState(false);
  const [diffDatabase,setDiffDatabase]=useState(''),[diffTable,setDiffTable]=useState('');
  const [table,setTable]=useState(''),[allTables,setAllTables]=useState(false),[confirmClose,setConfirmClose]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const serial=useRef(0),previous=useRef(sessionId);
  useEffect(() => {
    if(previous.current && previous.current!==sessionId){serial.current++;setInventory(null);setCapture(null);setConfirmClose(false);setError('');setPage(0);setDiffDatabase('');setDiffTable('');}
    previous.current=sessionId;
  },[sessionId]);
  useEffect(() => () => {serial.current++;},[]);
  const run=async request => {
    const token=++serial.current;setBusy(true);onBusyChange(true);setError('');
    try {
      const active=sessionId || await ensureSession();
      const value=await post({action:'sqlite_native_sessions',session_id:active,database_target_id:databaseTargetId,request});
      if(token!==serial.current)return;
      if(value.captures){setInventory(value);setPage(value.offset/25);}
      if(value.capture){if(value.capture.capture_id!==capture?.capture_id){setDiffDatabase('');setDiffTable('');}setCapture(value.capture);setInventory(current => current && value.program ? {...current,program:value.program,native_context_initialized:true} : current);}
      if(value.closed){setCapture(null);setInventory(current => current ? {...current,captures:current.captures.filter(item => item.capture_id!==value.capture_id)} : current);}
      setConfirmClose(false);
    } catch(failure) {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {setBusy(false);onBusyChange(false);}
  };
  const blocked=disabled || busy;
  return <Box component="details" sx={{mt:1}}><summary>SQLite native captures</summary>
    <Alert severity="info">Native sessions capture table data changes on this query connection. Capture memory is lost when the connection closes. Schema changes and virtual tables have separate workflows. Tables without explicit primary keys need native rowid tracking. Independent preupdate hooks cannot share this connection with sessions.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={blocked} onClick={() => run({operation:'inventory',offset:page*25,limit:25})}>Inspect native captures</Button>
    {inventory && <>
      {!inventory.helper_available && <Alert severity="warning">{inventory.unavailable_reason}</Alert>}
      <Box component="details"><summary>SQLite native session API identity</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:180,overflow:'auto'}}>{JSON.stringify(inventory.program,null,2)}</Box></Box>
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <TextField multiline size="small" label="Capture native database name" value={database} disabled={blocked} onChange={event => setDatabase(event.target.value)} />
        <FormControlLabel label="Track changeset size estimate" control={<Checkbox checked={estimate} disabled={blocked} onChange={event => setEstimate(event.target.checked)} />} />
        <FormControlLabel label="Track tables through native rowids" control={<Checkbox checked={rowids} disabled={blocked} onChange={event => setRowids(event.target.checked)} />} />
        <Button disabled={blocked || !inventory.helper_available} onClick={() => run({operation:'open',database,estimate_size:estimate,track_rowids:rowids})}>Open native capture</Button>
      </Box>
      <Table size="small" aria-label="Native SQLite captures"><TableHead><TableRow>{['Capture','Database','Native memory bytes','Enabled','Inspect'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
        {inventory.captures.map(item => <TableRow key={item.capture_id}><TableCell>{item.capture_id}</TableCell><TableCell>{item.database}</TableCell><TableCell>{item.memory_bytes}</TableCell><TableCell>{String(item.enabled)}</TableCell><TableCell><Button disabled={blocked} onClick={() => run({operation:'status',capture_id:item.capture_id})}>Inspect capture {item.capture_id}</Button></TableCell></TableRow>)}
      </TableBody></Table>
      <Button disabled={blocked || page===0} onClick={() => run({operation:'inventory',offset:(page-1)*25,limit:25})}>Previous native captures</Button>
      <Button disabled={blocked || !inventory.more} onClick={() => run({operation:'inventory',offset:(page+1)*25,limit:25})}>Next native captures</Button>
    </>}
    {capture && <Box sx={{my:1}}>
      <Alert severity="info">Capture {capture.capture_id}: {capture.database}. Native memory bytes: {capture.memory_bytes}. Changeset estimate: {capture.estimate_size ? capture.changeset_estimate_bytes : 'disabled'}.</Alert>
      <Button disabled={blocked} onClick={() => run({operation:'status',capture_id:capture.capture_id})}>Refresh native capture</Button>
      <FormControlLabel label="Native capture enabled" control={<Checkbox checked={capture.enabled} disabled={blocked} onChange={event => run({operation:'configure',capture_id:capture.capture_id,enabled:event.target.checked})} />} />
      <FormControlLabel label="Record changes as indirect" control={<Checkbox checked={capture.indirect} disabled={blocked} onChange={event => run({operation:'configure',capture_id:capture.capture_id,indirect:event.target.checked})} />} />
      <FormControlLabel label="Capture size estimate enabled" control={<Checkbox checked={capture.estimate_size} disabled={blocked} onChange={event => run({operation:'object_config',capture_id:capture.capture_id,option:'estimate_size',value:event.target.checked})} />} />
      <FormControlLabel label="Capture native rowids enabled" control={<Checkbox checked={capture.track_rowids} disabled={blocked} onChange={event => run({operation:'object_config',capture_id:capture.capture_id,option:'track_rowids',value:event.target.checked})} />} />
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <TextField multiline size="small" label="Exact native capture table" value={table} disabled={blocked || allTables} onChange={event => setTable(event.target.value)} />
        <FormControlLabel label="All current and future native tables" control={<Checkbox checked={allTables} disabled={blocked} onChange={event => setAllTables(event.target.checked)} />} />
        <Button disabled={blocked} onClick={() => run({operation:'attach',capture_id:capture.capture_id,table_name:allTables ? null : table})}>Attach native capture tables</Button>
      </Box>
      <Box component="details" sx={{my:1}}><summary>Automatic native capture table filter</summary>
        <Alert severity="info">Use native SQLite case-sensitive GLOB matching for automatic attachment of new table names. Already attached tables keep being tracked. Clearing the predicate enables all future eligible table names; it does not detach tables or discard captured changes.</Alert>
        <TextField multiline size="small" label="Native capture GLOB pattern" value={filterPattern} disabled={blocked} onChange={event => setFilterPattern(event.target.value)} />
        <FormControlLabel label="Exclude matching native table names" control={<Checkbox checked={excludeFilter} disabled={blocked} onChange={event => setExcludeFilter(event.target.checked)} />} />
        <Button disabled={blocked} onClick={() => run({operation:'table_filter',capture_id:capture.capture_id,pattern:filterPattern,exclude:excludeFilter})}>Set automatic native table filter</Button>
        <Button disabled={blocked} onClick={() => run({operation:'table_filter',capture_id:capture.capture_id,pattern:null,exclude:false})}>Track all future native table names</Button>
        <Box component="pre" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(capture.table_filter || {configured:false},null,2)}</Box>
      </Box>
      <Box component="details" sx={{my:1}}><summary>Compare an attached source into this capture</summary>
        <Alert severity="info">Add the native difference from an attached source table to this capture database table. This changes capture memory and leaves both databases and pending transactions intact. Native schemas and primary keys must be compatible.</Alert>
        <TextField select size="small" label="Native diff source database" value={diffDatabase} disabled={blocked} onChange={event => setDiffDatabase(event.target.value)}>
          <MenuItem value="">Select source database</MenuItem>
          {(inventory?.databases || []).filter(item => item.name!==capture.database).map(item => <MenuItem key={item.name} value={item.name}>{item.name}</MenuItem>)}
        </TextField>
        <TextField multiline size="small" label="Exact native diff table" value={diffTable} disabled={blocked} onChange={event => setDiffTable(event.target.value)} />
        <Button disabled={blocked || !diffDatabase || !diffTable} onClick={() => run({operation:'diff',capture_id:capture.capture_id,source_database:diffDatabase,table_name:diffTable})}>Add native table difference to capture</Button>
      </Box>
      <FormControlLabel label="Discard this capture and any unexported changes" control={<Checkbox disabled={blocked} checked={confirmClose} onChange={event => setConfirmClose(event.target.checked)} />} />
      <Button disabled={blocked || !confirmClose} onClick={() => run({operation:'close',capture_id:capture.capture_id,confirmed:true})}>Close native capture</Button>
      <Box component="pre" aria-label="Native SQLite capture observations" sx={{whiteSpace:'pre-wrap',maxHeight:240,overflow:'auto'}}>{JSON.stringify(capture,null,2)}</Box>
    </Box>}
    <SQLiteCaptureExports post={post} databaseTargetId={databaseTargetId} sessionId={sessionId} captureId={capture?.capture_id} endpointUrl={endpointUrl} disabled={blocked} />
    <SQLiteChangesetApply post={post} databaseTargetId={databaseTargetId} sessionId={sessionId} ensureSession={ensureSession} endpointUrl={endpointUrl} disabled={blocked} />
  </Box>;
}
SQLiteNativeSessions.propTypes={post:PropTypes.func.isRequired,ensureSession:PropTypes.func.isRequired,sessionId:PropTypes.string,
  databaseTargetId:PropTypes.string.isRequired,endpointUrl:PropTypes.string,disabled:PropTypes.bool,onBusyChange:PropTypes.func.isRequired};
