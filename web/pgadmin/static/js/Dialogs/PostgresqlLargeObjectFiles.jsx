import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,MenuItem,Table,TableBody,TableCell,TableHead,TablePagination,TableRow,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';

const ACTIVE=new Set(['reviewing','dispatching','active','cancel_requested']);
const CHUNK=1024*1024;
const encode=bytes => {
  let result='';
  for(let offset=0;offset<bytes.length;offset+=8192)result+=String.fromCharCode(...bytes.subarray(offset,offset+8192));
  return btoa(result);
};
const checksum=async bytes => Array.from(new Uint8Array(await window.crypto.subtle.digest('SHA-256',bytes)),value => value.toString(16).padStart(2,'0')).join('');

export default function PostgresqlLargeObjectFiles({post,databaseTargetId,endpointUrl}) {
  const [operation,setOperation]=useState('import'),[oid,setOid]=useState('0'),[filename,setFilename]=useState('large-object.bin'),[file,setFile]=useState(null);
  const [receipt,setReceipt]=useState(null),[catalog,setCatalog]=useState(null),[page,setPage]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState(''),[removeConfirmation,setRemoveConfirmation]=useState('');
  const generation=useRef(0),stop=useRef(false),downloads=useRef([]);
  useEffect(() => {
    generation.current++;stop.current=true;setReceipt(null);setCatalog(null);setPage(0);setBusy(false);setError('');setFile(null);setOperation('import');setOid('0');setFilename('large-object.bin');setRemoveConfirmation('');
    return () => {generation.current++;stop.current=true;downloads.current.splice(0).forEach(close => close());};
  },[post,databaseTargetId]);
  const call=(action,request) => post({action:'postgresql_large_object_'+action,request:{...request,database_target_id:databaseTargetId}});
  const fail=failure => failure.response?.data?.errormsg || failure.message || 'Native file transfer failed';
  const run=async (action,request,accept=setReceipt) => {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await call(action,request);if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(fail(failure));}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(() => {
    if(!receipt || !ACTIVE.has(receipt.state))return;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const value=await post({action:'postgresql_large_object_status',request:{job_id:receipt.job_id,database_target_id:databaseTargetId}});if(live)setReceipt(value);}
      catch(failure) {if(live)setError(fail(failure));}
      finally {pending=false;}
    },1000);
    return () => {live=false;clearInterval(timer);};
  },[post,databaseTargetId,receipt?.job_id,receipt?.state]);
  const upload=async existing => {
    if(!file)return;
    const token=generation.current;stop.current=false;setBusy(true);setError('');
    try {
      let item=existing || await call('create',{options:{operation:'import',oid,length:String(file.size),filename:file.name}});
      if(token!==generation.current)return;
      if(item.options.length!==String(file.size) || item.options.filename!==file.name)throw new Error('Select the original file before resuming its upload.');
      setReceipt(item);
      // Revalidate an acknowledged prefix when resuming. A different file with
      // the same name/size must never be joined to previously staged bytes.
      for(let offset=0;offset<file.size;offset+=CHUNK) {
        if(stop.current || token!==generation.current)return;
        const bytes=new Uint8Array(await file.slice(offset,offset+CHUNK).arrayBuffer());
        const sha256=await checksum(bytes);
        if(stop.current || token!==generation.current)return;
        const acknowledged=await call('upload',{job_id:item.job_id,offset:String(offset),data_base64:encode(bytes),sha256});
        if(acknowledged.chunk_sha256!==sha256)throw new Error('File upload checksum acknowledgement differs.');
        if(token===generation.current)setReceipt(current => ({...current,uploaded_bytes:acknowledged.uploaded_bytes}));
      }
      if(!stop.current && token===generation.current) {
        item=await call('seal',{job_id:item.job_id});if(token===generation.current)setReceipt(item);
      }
    } catch(failure) {if(!stop.current && token===generation.current)setError(fail(failure));}
    finally {if(token===generation.current)setBusy(false);}
  };
  const cancel=async () => {
    stop.current=true;const token=generation.current;
    try {const value=await call('cancel',{job_id:receipt.job_id});if(token===generation.current)setReceipt(value);}
    catch(failure) {if(token===generation.current)setError(fail(failure));}
  };
  const load=next => run('list',{offset:next*25,limit:25},value => {setCatalog(value);setPage(next);});
  const download=() => {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{job_id:receipt.job_id,database_target_id:databaseTargetId},
      {action:'postgresql_large_object_download',prefix:'postgresql-lo',title:'PostgreSQL large-object file download'}));}
    catch(failure) {setError(fail(failure));}
  };
  return <Box sx={{p:1,overflow:'auto',flex:1}}>
    <Alert severity="info">Transfer complete binary files using a separate native PostgreSQL transaction. Imports create a new large object and verify its checksum before commit. Exports use a consistent native snapshot and a private application-host artifact.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <TextField select size="small" label="File operation" value={operation} disabled={busy} onChange={event => {setOperation(event.target.value);setOid(event.target.value==='import' ? '0' : '');}}>
        <MenuItem value="import">Import client file</MenuItem><MenuItem value="export">Export large object</MenuItem>
      </TextField>
      <TextField size="small" label="Large-object OID (import: 0 allocates)" value={oid} disabled={busy} onChange={event => setOid(event.target.value)} />
      {operation==='import' ? <>
        <Button component="label" disabled={busy}>Select binary file<input hidden type="file" aria-label="Binary file to import" onChange={event => setFile(event.target.files?.[0] || null)} /></Button>
        {file && <Box>{file.name} · {String(file.size)} bytes</Box>}
        <Button disabled={busy || !file} onClick={() => upload(null)}>Upload and review file</Button>
      </> : <>
        <TextField size="small" label="Download filename" value={filename} disabled={busy} onChange={event => setFilename(event.target.value)} />
        <Button disabled={busy} onClick={() => run('create',{options:{operation:'export',oid,filename}})}>Review native export</Button>
      </>}
      <Button disabled={busy} onClick={() => load(page)}>Load file transfer receipts</Button>
    </Box>
    {catalog && <>
      <Table size="small" aria-label="PostgreSQL file transfers"><TableHead><TableRow>{['File','Operation','State','Receipt'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead>
        <TableBody>{catalog.jobs.map(item => <TableRow key={item.job_id}><TableCell>{item.options.filename}</TableCell><TableCell>{item.options.operation}</TableCell><TableCell>{item.state}</TableCell>
          <TableCell><Button disabled={busy} onClick={() => run('status',{job_id:item.job_id})}>Inspect {item.job_id}</Button></TableCell></TableRow>)}</TableBody></Table>
      <TablePagination component="div" count={catalog.total} page={page} rowsPerPage={25} rowsPerPageOptions={[25]} onPageChange={(_event,next) => load(next)} />
    </>}
    {receipt && <Box>
      <Alert severity={receipt.state==='committed' ? 'success' : ['unknown','failed','not_dispatched'].includes(receipt.state) ? 'warning' : 'info'}>
        File transfer {receipt.job_id}: {receipt.state}. {receipt.uploaded_bytes && 'Uploaded '+receipt.uploaded_bytes+' bytes. '}
        {receipt.progress && receipt.progress.phase+' '+receipt.progress.bytes+' / '+receipt.progress.total+' bytes. '}{receipt.observation_blocker}
        {receipt.result && ' OID '+receipt.result.oid+'; SHA-256 '+receipt.result.sha256+'.'}
      </Alert>
      {receipt.state==='reviewed' && <>
        <ul>{receipt.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
        <Box component="pre" aria-label="Native file transfer review" sx={{whiteSpace:'pre-wrap',maxHeight:260,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box>
        <Button disabled={busy} onClick={() => run('start',{job_id:receipt.job_id,review_digest:receipt.review_digest,confirmed:true})}>Confirm and start native file transfer</Button>
      </>}
      <Button disabled={busy} onClick={() => run('status',{job_id:receipt.job_id})}>Refresh file transfer receipt</Button>
      {receipt.state==='unknown' && <Button disabled={busy} onClick={() => run('reconcile',{job_id:receipt.job_id})}>Reconcile native file transfer</Button>}
      {receipt.state==='uploading' && <Button disabled={busy || !file} onClick={() => upload(receipt)}>Resume file upload</Button>}
      {['uploading','reviewed',...ACTIVE].includes(receipt.state) && <Button onClick={cancel}>Cancel file transfer</Button>}
      {['committed','artifact_verified'].includes(receipt.state) && receipt.options.operation==='export' && receipt.artifact_available!==false && <Button onClick={download}>Download complete binary file</Button>}
      {!ACTIVE.has(receipt.state) && receipt.artifact_available!==false && <Box sx={{my:1,display:'flex',gap:1,flexWrap:'wrap'}}>
        <TextField size="small" label="Confirm transfer ID to remove application file" value={removeConfirmation} onChange={event => setRemoveConfirmation(event.target.value)} />
        <Button disabled={busy} onClick={() => run('remove_artifact',{job_id:receipt.job_id,confirmation:removeConfirmation})}>Remove application file</Button>
      </Box>}
      <Box component="details"><summary>File transfer receipt</summary><Box component="pre" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
PostgresqlLargeObjectFiles.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string.isRequired,endpointUrl:PropTypes.string.isRequired};
