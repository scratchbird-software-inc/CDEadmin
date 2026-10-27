import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';

const active=state => ['dispatching','active','publishing','cancel_requested'].includes(state);
const initial={database:'main',source_database:'',table_name:'',kind:'changeset',estimate_size:false,track_rowids:false,timeout_seconds:3600};

export default function SQLiteNativeDiff({post,databaseTargetId,sessionId,ensureSession,endpointUrl,onSelected,disabled}) {
  const [catalog,setCatalog]=useState(null),[tables,setTables]=useState(null),[options,setOptions]=useState(initial);
  const [receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[offset,setOffset]=useState(0),[files,setFiles]=useState(null);
  const [confirmed,setConfirmed]=useState(false),[remove,setRemove]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const serial=useRef(0),previous=useRef(sessionId),downloads=useRef([]);
  const call=(operation,fields={}) => post({action:'sqlite_changeset_diff_'+operation,request:{database_target_id:databaseTargetId,...fields}});
  useEffect(() => {
    serial.current++;setCatalog(null);setTables(null);setOptions(initial);setReceipt(null);setJobs(null);setFiles(null);setOffset(0);setConfirmed(false);setRemove(false);setBusy(false);setError('');
    return () => {serial.current++;downloads.current.forEach(close => close());downloads.current=[];};
  },[databaseTargetId]);
  useEffect(() => {
    if(previous.current && previous.current!==sessionId){
      serial.current++;setCatalog(null);setTables(null);setOptions(initial);setBusy(false);setConfirmed(false);
      setReceipt(current => current?.state==='reviewed' ? null : current);
    }
    previous.current=sessionId;
  },[sessionId]);
  const perform=async (operation,fields={}) => {
    const token=serial.current;setBusy(true);setError('');
    try {
      if(['catalog','tables','review'].includes(operation))fields={...fields,session_id:sessionId || await ensureSession?.()};
      const value=await call(operation,fields);if(token!==serial.current)return;
      if(operation==='catalog'){
        setCatalog(value);setOptions(current => ({...current,source_database:current.source_database || value.schemas.find(item => item.name!==current.database)?.name || ''}));
      } else if(operation==='tables')setTables(value);
      else if(operation==='list')setJobs(value);
      else if(operation==='files')setFiles(value);
      else {setReceipt(value);setConfirmed(false);setFiles(null);setRemove(false);}
    } catch(failure) {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===serial.current)setBusy(false);}
  };
  useEffect(() => {
    if(!receipt?.job_id || !active(receipt.state))return undefined;
    let alive=true,timer;
    const poll=async () => {
      try {const value=await call('status',{job_id:receipt.job_id});if(!alive)return;setReceipt(value);if(active(value.state))timer=setTimeout(poll,400);}
      catch(failure) {if(alive)setError(failure.response?.data?.errormsg || failure.message);}
    };
    timer=setTimeout(poll,400);return () => {alive=false;clearTimeout(timer);};
  },[post,databaseTargetId,receipt?.job_id,active(receipt?.state)]);
  const change=(name,value) => {
    setOptions(current => ({...current,[name]:value,...(name==='database' ? {table_name:''} : {})}));
    if(name==='database')setTables(null);
    setReceipt(current => current?.state==='reviewed' ? null : current);setConfirmed(false);
  };
  const download=path => {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{database_target_id:databaseTargetId,job_id:receipt.job_id,path},
      {action:'sqlite_changeset_diff_download',prefix:'sqlite-diff',title:'SQLite native table difference download'}));}
    catch(failure) {setError(failure.message);}
  };
  const blocked=busy || active(receipt?.state),verified=['completed','artifact_verified'].includes(receipt?.state) && !receipt?.artifact_removed;
  return <Box component="details" sx={{my:1}}><summary>SQLite managed table differences</summary>
    <Alert severity="info">Compare an attached source with a table on this query connection and export the native difference. Temporary and uncommitted data stay visible. Existing captures and SQL transactions remain owned by this session. Cancellation discards the comparison&apos;s private capture. Closing this viewer does not cancel a running job.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={blocked || disabled || !sessionId && !ensureSession} onClick={() => perform('catalog')}>Inspect retained table comparison support</Button>
    <Button disabled={busy} onClick={() => perform('list',{offset,limit:25})}>Load native comparison receipts</Button>
    {catalog && <>
      <Alert severity="info">{catalog.scope}. SQL transaction open: {String(catalog.transaction_open)}.</Alert>
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        {['database','source_database'].map(name => <TextField key={name} select size="small" label={name==='database' ? 'Native comparison destination schema' : 'Native comparison source schema'} value={options[name]} disabled={blocked || disabled} onChange={event => change(name,event.target.value)}>
          {catalog.schemas.map(schema => <MenuItem key={schema.name} value={schema.name}>{schema.name} — {schema.filename || 'connection-local'}</MenuItem>)}
        </TextField>)}
        <Button disabled={blocked || disabled} onClick={() => perform('tables',{database:options.database})}>Load native comparison tables</Button>
        <TextField select size="small" label="Exact native comparison table" value={options.table_name} disabled={blocked || disabled} onChange={event => change('table_name',event.target.value)}>
          <MenuItem value="">Select table</MenuItem>{tables?.tables.map(table => <MenuItem key={table.name} value={table.name}>{table.name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Native table difference format" value={options.kind} disabled={blocked || disabled} onChange={event => change('kind',event.target.value)}><MenuItem value="changeset">Changeset</MenuItem><MenuItem value="patchset">Patchset</MenuItem></TextField>
        <TextField size="small" type="number" label="Native comparison maximum seconds" value={options.timeout_seconds ?? ''} disabled={blocked || disabled} onChange={event => change('timeout_seconds',event.target.value==='' ? null : Number(event.target.value))} />
      </Box>
      <FormControlLabel label="Estimate private comparison capture size" control={<Checkbox checked={options.estimate_size} disabled={blocked || disabled} onChange={event => change('estimate_size',event.target.checked)} />} />
      <FormControlLabel label="Track native rowids for comparison" control={<Checkbox checked={options.track_rowids} disabled={blocked || disabled} onChange={event => change('track_rowids',event.target.checked)} />} />
      <Button disabled={blocked || disabled || !options.table_name || !options.source_database} onClick={() => perform('review',{options})}>Review native table comparison</Button>
    </>}
    {jobs && <Box>
      <TextField select size="small" label="Retained native table comparison" value={jobs.jobs.some(item => item.job_id===receipt?.job_id) ? receipt.job_id : ''} disabled={blocked} onChange={event => perform('status',{job_id:event.target.value})}>{jobs.jobs.map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} — {item.state}</MenuItem>)}</TextField>
      <Button disabled={busy || offset===0} onClick={() => {const next=Math.max(0,offset-25);setOffset(next);perform('list',{offset:next,limit:25});}}>Previous native comparison receipts</Button>
      <Button disabled={busy || !jobs.more} onClick={() => {setOffset(offset+25);perform('list',{offset:offset+25,limit:25});}}>Next native comparison receipts</Button>
    </Box>}
    {receipt && <Box>
      <Alert severity={verified ? 'success' : 'info'}>Native table comparison {receipt.job_id}: {receipt.state}. Automatic retry is disabled.</Alert>
      {receipt.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
      {receipt.error_message && <Alert severity="warning">{receipt.error_message}</Alert>}
      {receipt.progress && <Alert severity="info">Native VM progress callbacks: {receipt.progress.vm_progress_callbacks || '0'}. This count is not rows or a percentage.</Alert>}
      {receipt.state==='reviewed' && <><FormControlLabel label="Confirm disposable native table comparison" control={<Checkbox checked={confirmed} disabled={busy || disabled} onChange={event => setConfirmed(event.target.checked)} />} /><Button disabled={busy || disabled || !confirmed} onClick={() => perform('start',{job_id:receipt.job_id,review_digest:receipt.review_digest,confirmed:true})}>Start reviewed native table comparison</Button></>}
      {active(receipt.state) && <Button disabled={busy} onClick={() => perform('cancel',{job_id:receipt.job_id})}>Cancel native table comparison</Button>}
      {verified && <><Button disabled={busy || disabled} onClick={() => onSelected(receipt)}>Use native table difference for apply</Button><Button disabled={busy} onClick={() => perform('files',{job_id:receipt.job_id,offset:0,limit:25})}>Load native comparison files</Button></>}
      {!active(receipt.state) && receipt.state!=='reviewed' && !receipt.artifact_removed && <Button disabled={busy} onClick={() => perform('reconcile',{job_id:receipt.job_id})}>Verify retained native comparison</Button>}
      {files?.files.map(row => <Box key={row.path}>{row.path} ({row.size} bytes) <Button disabled={busy || !endpointUrl || files.artifact_removed} onClick={() => download(row.path)}>Download comparison {row.path}</Button></Box>)}
      {receipt.partial_output && !receipt.artifact_removed && <Button disabled={busy || !endpointUrl} onClick={() => download(receipt.partial_output.path)}>Download native comparison diagnostic</Button>}
      {!active(receipt.state) && !receipt.artifact_removed && <><FormControlLabel label="Remove native comparison files; retain receipt" control={<Checkbox checked={remove} disabled={busy} onChange={event => setRemove(event.target.checked)} />} /><Button disabled={busy || !remove} onClick={() => perform('remove_artifact',{job_id:receipt.job_id,confirmation:receipt.job_id})}>Remove native comparison files</Button></>}
      <Box component="details"><summary>Native SQLite table comparison receipt</summary><Box component="pre" aria-label="Native SQLite table comparison receipt" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
SQLiteNativeDiff.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string.isRequired,sessionId:PropTypes.string,ensureSession:PropTypes.func,endpointUrl:PropTypes.string,onSelected:PropTypes.func.isRequired,disabled:PropTypes.bool};
