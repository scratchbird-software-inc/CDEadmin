import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';

const active=state => ['dispatching','active','publishing','cancel_requested'].includes(state);

export default function SQLiteCaptureExports({post,databaseTargetId,sessionId,captureId,endpointUrl,disabled}) {
  const [kind,setKind]=useState('changeset'),[timeout,setTimeoutSeconds]=useState(3600);
  const [receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[offset,setOffset]=useState(0);
  const [files,setFiles]=useState(null),[fileOffset,setFileOffset]=useState(0),[confirmed,setConfirmed]=useState(false),[remove,setRemove]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0),downloads=useRef([]),selection=useRef({sessionId,captureId});
  selection.current={sessionId,captureId};
  const call=(operation,fields={}) => post({action:'sqlite_capture_export_'+operation,request:{database_target_id:databaseTargetId,...fields}});
  useEffect(() => {
    generation.current++;setReceipt(null);setJobs(null);setFiles(null);setOffset(0);setFileOffset(0);setConfirmed(false);setRemove(false);setBusy(false);setError('');
    return () => {generation.current++;downloads.current.forEach(close => close());downloads.current=[];};
  },[databaseTargetId]);
  useEffect(() => {
    setConfirmed(false);
    setReceipt(current => current?.state==='reviewed' &&
      (current.source?.studio_session_id!==sessionId || current.source?.capture_id!==captureId) ? null : current);
  },[sessionId,captureId]);
  useEffect(() => {
    if(!receipt?.job_id || !active(receipt.state))return undefined;
    let alive=true,timer;
    const poll=async () => {
      try {
        const value=await call('status',{job_id:receipt.job_id});
        if(!alive)return;
        setReceipt(value);
        if(active(value.state))timer=setTimeout(poll,400);
      } catch(failure) {if(alive)setError(failure.response?.data?.errormsg || failure.message);}
    };
    timer=setTimeout(poll,400);
    return () => {alive=false;clearTimeout(timer);};
  },[post,databaseTargetId,receipt?.job_id,active(receipt?.state)]);
  const perform=async (operation,fields={}) => {
    const token=generation.current,current={sessionId,captureId};setBusy(true);setError('');
    try {
      const value=await call(operation,fields);
      if(token!==generation.current || operation==='review' &&
        (current.sessionId!==selection.current.sessionId || current.captureId!==selection.current.captureId))return;
      if(operation==='list')setJobs(value);
      else if(operation==='files')setFiles(value);
      else {setReceipt(value);setConfirmed(false);setRemove(false);setFiles(null);setFileOffset(0);}
    } catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===generation.current)setBusy(false);}
  };
  const download=path => {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{database_target_id:databaseTargetId,job_id:receipt.job_id,path},
      {action:'sqlite_capture_export_download',prefix:'sqlite-capture',title:'SQLite native capture download'}));}
    catch(failure) {setError(failure.message);}
  };
  const change=(setter,value) => {setter(value);setConfirmed(false);setReceipt(current => current?.state==='reviewed' ? null : current);};
  return <Box component="details" sx={{my:1}}><summary>SQLite capture exports and receipts</summary>
    <Alert severity="info">Export native table data changes from the selected capture. Pending SQL work stays pending. Changesets include old values for conflict handling; patchsets omit some old values. Neither format is a schema migration or a database backup. Export receipts and verified downloads remain available after the query connection closes.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <TextField select size="small" label="Native capture export format" value={kind} disabled={busy} onChange={event => change(setKind,event.target.value)}>
        <MenuItem value="changeset">Changeset</MenuItem><MenuItem value="patchset">Patchset</MenuItem>
      </TextField>
      <TextField size="small" type="number" label="Capture export maximum seconds" value={timeout ?? ''} disabled={busy}
        onChange={event => change(setTimeoutSeconds,event.target.value==='' ? null : Number(event.target.value))} />
      <Button disabled={busy || disabled || !captureId || !sessionId} onClick={() => perform('review',{session_id:sessionId,capture_id:captureId,kind,timeout_seconds:timeout})}>Review native capture export</Button>
      <Button disabled={busy} onClick={() => perform('list',{offset,limit:25})}>Load capture export receipts</Button>
    </Box>
    {jobs && <Box>
      <TextField select size="small" label="Retained capture export" value={jobs.jobs.some(item => item.job_id===receipt?.job_id) ? receipt.job_id : ''}
        onChange={event => perform('status',{job_id:event.target.value})} sx={{minWidth:380}}>
        {jobs.jobs.map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} — {item.state}</MenuItem>)}
      </TextField>
      <Button disabled={busy || offset===0} onClick={() => {setOffset(Math.max(0,offset-25));perform('list',{offset:Math.max(0,offset-25),limit:25});}}>Previous capture export receipts</Button>
      <Button disabled={busy || !jobs.more} onClick={() => {setOffset(offset+25);perform('list',{offset:offset+25,limit:25});}}>Next capture export receipts</Button>
    </Box>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={['completed','artifact_verified'].includes(receipt.state) ? 'success' : 'info'}>Capture export {receipt.job_id}: {receipt.state}. Automatic retry is disabled.</Alert>
      {receipt.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
      {receipt.error_message && <Alert severity="warning">{receipt.error_message}</Alert>}
      {receipt.state==='reviewed' && <>
        <FormControlLabel label="Confirm the reviewed native capture export" control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={busy || disabled || !confirmed} onClick={() => perform('start',{job_id:receipt.job_id,review_digest:receipt.review_digest,confirmed:true})}>Start reviewed capture export</Button>
      </>}
      {active(receipt.state) && <Button disabled={busy} onClick={() => perform('cancel',{job_id:receipt.job_id})}>Cancel native capture export</Button>}
      <Box role="status">Native export acknowledgement: {receipt.native_returned===true ? 'received' : 'unconfirmed'}. Written bytes: {receipt.native_returned_bytes || receipt.progress?.bytes_written || '0'}.</Box>
      {!active(receipt.state) && receipt.state!=='reviewed' && !receipt.artifact_removed && <Button disabled={busy} onClick={() => perform('reconcile',{job_id:receipt.job_id})}>Verify retained capture artifact</Button>}
      {receipt.partial_output && !receipt.artifact_removed && <Box>
        <Alert severity="warning">Inspected partial output is diagnostic only. A readable stream can be an incomplete prefix. Original export bytes and complete export remain unverified.</Alert>
        <Box>Partial bytes: {receipt.partial_output.size}. Native iterator reached stream end: {String(receipt.partial_output.observations.native_iterator_complete)}.</Box>
        <Button disabled={busy || !endpointUrl} onClick={() => download(receipt.partial_output.path)}>Download partial capture diagnostic</Button>
      </Box>}
      {['completed','artifact_verified'].includes(receipt.state) && !receipt.artifact_removed && <Button disabled={busy} onClick={() => perform('files',{job_id:receipt.job_id,offset:0,limit:25})}>Load verified capture files</Button>}
      {files && <Box>{files.files.map(row => <Box key={row.path}>{row.path} ({row.size} bytes) <Button disabled={busy || !endpointUrl || files.artifact_removed} onClick={() => download(row.path)}>Download {row.path}</Button></Box>)}
        <Button disabled={busy || fileOffset===0} onClick={() => {const next=Math.max(0,fileOffset-25);setFileOffset(next);perform('files',{job_id:receipt.job_id,offset:next,limit:25});}}>Previous capture files</Button>
        <Button disabled={busy || !files.more} onClick={() => {setFileOffset(fileOffset+25);perform('files',{job_id:receipt.job_id,offset:fileOffset+25,limit:25});}}>Next capture files</Button>
      </Box>}
      {!active(receipt.state) && !receipt.artifact_removed && <>
        <FormControlLabel label="Remove private files for this capture export; retain its receipt" control={<Checkbox checked={remove} disabled={busy} onChange={event => setRemove(event.target.checked)} />} />
        <Button disabled={busy || !remove} onClick={() => perform('remove_artifact',{job_id:receipt.job_id,confirmation:receipt.job_id})}>Remove capture export files</Button>
      </>}
      <Box component="details"><summary>Native capture export receipt</summary><Box component="pre" aria-label="SQLite capture export receipt" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
SQLiteCaptureExports.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string.isRequired,
  sessionId:PropTypes.string,captureId:PropTypes.string,endpointUrl:PropTypes.string,disabled:PropTypes.bool};
