import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';

const active=state => ['dispatching','active','publishing','cancel_requested'].includes(state);
const CHUNK=262144;
const encode=bytes => {
  let output='';for(let offset=0;offset<bytes.length;offset+=8192)output+=String.fromCharCode(...bytes.subarray(offset,offset+8192));return btoa(output);
};
const checksum=async bytes => [...new Uint8Array(await window.crypto.subtle.digest('SHA-256',bytes))].map(value => value.toString(16).padStart(2,'0')).join('');

export default function SQLiteNativeUpload({post,databaseTargetId,endpointUrl,onSelected,disabled}) {
  const [file,setFile]=useState(null),[kind,setKind]=useState('auto'),[expected,setExpected]=useState(''),[timeout,setTimeoutSeconds]=useState(3600);
  const [catalog,setCatalog]=useState(null),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[offset,setOffset]=useState(0),[files,setFiles]=useState(null);
  const [busy,setBusy]=useState(false),[remove,setRemove]=useState(false),[error,setError]=useState('');
  const generation=useRef(0),stop=useRef(false),downloads=useRef([]);
  const call=(operation,fields={}) => post({action:'sqlite_changeset_upload_'+operation,request:{database_target_id:databaseTargetId,...fields}});
  useEffect(() => {
    generation.current++;stop.current=true;setFile(null);setCatalog(null);setReceipt(null);setJobs(null);setOffset(0);setFiles(null);setBusy(false);setRemove(false);setError('');
    return () => {generation.current++;stop.current=true;downloads.current.forEach(close => close());downloads.current=[];};
  },[databaseTargetId]);
  const perform=async (operation,fields={}) => {
    const token=generation.current;setBusy(true);setError('');
    try {
      const value=await call(operation,fields);if(token!==generation.current)return;
      if(operation==='catalog')setCatalog(value);else if(operation==='list')setJobs(value);else if(operation==='files')setFiles(value);
      else {setReceipt(value);setFiles(null);setRemove(false);}
    } catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===generation.current)setBusy(false);}
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
  const upload=async existing => {
    if(!file)return;
    const token=generation.current;stop.current=false;setBusy(true);setError('');
    try {
      if(!Number.isSafeInteger(file.size))throw new Error('The browser cannot represent this file length exactly.');
      let item=existing ? await call('status',{job_id:existing.job_id}) : await call('create',{options:{filename:file.name,length:String(file.size),kind,expected_sha256:expected || null,timeout_seconds:timeout}});
      if(token!==generation.current)return;
      setReceipt(item);setFiles(null);
      if(item.state!=='uploading')return;
      if(item.options.length!==String(file.size) || item.options.filename!==file.name)throw new Error('Choose the original file to resume this native upload.');
      const resumed=Number(item.uploaded_bytes);if(!Number.isSafeInteger(resumed))throw new Error('The browser cannot represent this upload offset exactly.');
      // Recheck the acknowledged prefix against the selected original file;
      // matching filename/length alone cannot establish a valid resume.
      let position=0;
      while(position<file.size && !stop.current && token===generation.current) {
        const end=Math.min(file.size,position+CHUNK,position<resumed ? resumed : file.size);
        const bytes=new Uint8Array(await file.slice(position,end).arrayBuffer());
        const hash=await checksum(bytes);
        if(token!==generation.current || stop.current)return;
        const acknowledged=await call('chunk',{job_id:item.job_id,chunk:{offset:String(position),data_base64:encode(bytes),sha256:hash}});
        if(token!==generation.current)return;
        if(acknowledged.chunk_sha256!==hash || acknowledged.uploaded_bytes!==String(Math.max(resumed,position+bytes.length)))throw new Error('Native upload chunk acknowledgement differs.');
        position+=bytes.length;item={...item,uploaded_bytes:acknowledged.uploaded_bytes};setReceipt(item);
      }
      if(token===generation.current && !stop.current && position===file.size)setReceipt(await call('seal',{job_id:item.job_id}));
    } catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===generation.current)setBusy(false);}
  };
  const download=path => {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{database_target_id:databaseTargetId,job_id:receipt.job_id,path},
      {action:'sqlite_changeset_upload_download',prefix:'sqlite-upload',title:'SQLite native input file download'}));}
    catch(failure) {setError(failure.message);}
  };
  const verified=['completed','artifact_verified'].includes(receipt?.state) && !receipt?.artifact_removed;
  return <Box component="details" sx={{my:1}}><summary>External SQLite changeset files</summary>
    <Alert severity="info">Upload a native changeset or patchset in bounded chunks. Validation checks the staged checksum and native stream structure. It does not modify this database. Applying the validated file requires a separate review and confirmation.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={() => perform('catalog')}>Inspect native upload support</Button>
    <Button disabled={busy} onClick={() => perform('list',{offset,limit:25})}>Load native upload receipts</Button>
    {catalog && !catalog.helper_available && <Alert severity="warning">{catalog.unavailable_reason}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <input type="file" aria-label="External native SQLite file" disabled={busy || active(receipt?.state)} onChange={event => setFile(event.target.files?.[0] || null)} />
      <TextField select size="small" label="Expected native input format" value={kind} disabled={busy} onChange={event => setKind(event.target.value)}>
        <MenuItem value="auto">Detect native format</MenuItem><MenuItem value="changeset">Changeset</MenuItem><MenuItem value="patchset">Patchset</MenuItem>
      </TextField>
      <TextField size="small" label="Expected producer SHA256 (optional)" value={expected} disabled={busy} onChange={event => setExpected(event.target.value)} />
      <TextField size="small" type="number" label="Native upload validation maximum seconds" value={timeout ?? ''} disabled={busy} onChange={event => setTimeoutSeconds(event.target.value==='' ? null : Number(event.target.value))} />
      <Button disabled={busy || !file || !catalog?.helper_available || active(receipt?.state)} onClick={() => upload()}>Upload and validate native file</Button>
    </Box>
    {busy && receipt?.state==='uploading' && <Button onClick={() => {stop.current=true;}}>Pause native file upload</Button>}
    {jobs && <Box>
      <TextField select size="small" label="Retained native upload" value={jobs.jobs.some(item => item.job_id===receipt?.job_id) ? receipt.job_id : ''} disabled={busy}
        onChange={event => perform('status',{job_id:event.target.value})} sx={{minWidth:420}}>
        {jobs.jobs.map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.options.filename} — {item.state} — {item.job_id}</MenuItem>)}
      </TextField>
      <Button disabled={busy || offset===0} onClick={() => {const next=Math.max(0,offset-25);setOffset(next);perform('list',{offset:next,limit:25});}}>Previous native upload receipts</Button>
      <Button disabled={busy || !jobs.more} onClick={() => {setOffset(offset+25);perform('list',{offset:offset+25,limit:25});}}>Next native upload receipts</Button>
    </Box>}
    {receipt && <Box>
      <Alert severity={verified ? 'success' : 'info'}>Native file intake {receipt.job_id}: {receipt.state}. Uploaded bytes: {receipt.uploaded_bytes} / {receipt.options.length}.</Alert>
      {receipt.error_message && <Alert severity="warning">{receipt.error_message}</Alert>}
      {receipt.state==='uploading' && <>
        <Button disabled={busy || !file} onClick={() => upload(receipt)}>Resume native file upload</Button>
        <Button disabled={busy || receipt.uploaded_bytes!==receipt.options.length} onClick={() => perform('seal',{job_id:receipt.job_id})}>Validate staged native file</Button>
      </>}
      {['uploading','reviewed'].includes(receipt.state) || active(receipt.state) ? <Button disabled={busy} onClick={() => perform('cancel',{job_id:receipt.job_id})}>Cancel native file intake</Button> : null}
      {verified && <>
        <Box>Validated native format: {receipt.result.artifact.native_kind}. Native records: {receipt.result.artifact.native_record_count}.</Box>
        <Button disabled={busy || disabled} onClick={() => onSelected(receipt)}>Use validated native file for apply</Button>
        <Button disabled={busy} onClick={() => perform('files',{job_id:receipt.job_id,offset:0,limit:25})}>Load validated upload files</Button>
      </>}
      {!active(receipt.state) && !['uploading','reviewed'].includes(receipt.state) && !receipt.artifact_removed && <Button disabled={busy} onClick={() => perform('reconcile',{job_id:receipt.job_id})}>Verify retained native upload</Button>}
      {files && files.files.map(row => <Box key={row.path}>{row.path} ({row.size} bytes) <Button disabled={busy || !endpointUrl || files.artifact_removed} onClick={() => download(row.path)}>Download input {row.path}</Button></Box>)}
      {receipt.partial_output && !receipt.artifact_removed && <Box><Alert severity="warning">Unsealed input is diagnostic only; native apply eligibility is unverified.</Alert>
        <Button disabled={busy || !endpointUrl} onClick={() => download(receipt.partial_output.path)}>Download native input diagnostic</Button></Box>}
      {!active(receipt.state) && !receipt.artifact_removed && <>
        <FormControlLabel label="Remove native upload files; retain the receipt" control={<Checkbox checked={remove} disabled={busy} onChange={event => setRemove(event.target.checked)} />} />
        <Button disabled={busy || !remove} onClick={() => perform('remove_artifact',{job_id:receipt.job_id,confirmation:receipt.job_id})}>Remove native upload files</Button>
      </>}
      <Box component="details"><summary>Native SQLite upload receipt</summary><Box component="pre" aria-label="Native SQLite upload receipt" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
SQLiteNativeUpload.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string.isRequired,endpointUrl:PropTypes.string,onSelected:PropTypes.func.isRequired,disabled:PropTypes.bool};
