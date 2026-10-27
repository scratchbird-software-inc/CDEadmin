import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Table,TableBody,TableCell,TableHead,TableRow,TablePagination,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
const DEFAULT_OPTIONS=JSON.stringify({users:true,consistent:true,checksum:true,threads:4,compression:'zstd;level=1',timeout_seconds:3600},null,2);
export default function MySQLInstanceBackups({post,endpointUrl}) {
  const [options,setOptions]=useState(DEFAULT_OPTIONS);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[page,setPage]=useState(null),[files,setFiles]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[confirmation,setConfirmation]=useState('');
  const generation=useRef(0),downloads=useRef([]);
  useEffect(()=> {
    generation.current++;setOptions(DEFAULT_OPTIONS);setReview(null);setReceipt(null);setPage(null);setFiles(null);setError('');setConfirmation('');setBusy(false);
    return ()=>{generation.current++;downloads.current.splice(0).forEach(close=>close());};
  },[post,endpointUrl]);
  const run=async (action,request,accept)=> {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:'mysql_instance_backup_'+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native instance backup request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(()=> {
    if(!ACTIVE.has(receipt?.state))return;
    const token=generation.current;let pending=false,live=true;
    const timer=setInterval(async()=> {
      if(pending)return;pending=true;
      try {const value=await post({action:'mysql_instance_backup_status',request:{job_id:receipt.job_id}});if(live && token===generation.current)setReceipt(value);}
      catch(failure) {if(live && token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native backup status is unavailable');}
      finally {pending=false;}
    },1500);
    return ()=>{live=false;clearInterval(timer);};
  },[receipt?.job_id,receipt?.state,post]);
  const load=offset=>run('list',{offset,limit:25},setPage);
  const inspect=job=>run('status',{job_id:job.job_id},value=>{setReceipt(value);setFiles(null);setConfirmation('');});
  const download=row=> {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{job_id:receipt.job_id,path:row.path},
      {action:'mysql_instance_backup_download',prefix:'mysql-instance-backup',title:'Native instance backup file'}));}
    catch(failure) {setError(failure.message || 'Backup file download failed');}
  };
  return <Box sx={{p:2}}>
    <Alert severity="info">Create a native MySQL Shell instance dump containing its selected schemas, objects, data and optional accounts/roles/grants. System schemas excluded by MySQL Shell remain excluded. The utility can briefly pause writes to establish consistency. Output stays in a private directory on the application execution host. Account definitions can contain authentication material.</Alert>
    <Alert severity="info">Backup completion and file verification are separate from restored-data/definition verification, physical recovery and production cutover. Managed backup holds protect source archives until separately retired. Closing this view does not cancel a running job.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <TextField multiline minRows={6} fullWidth label="Native instance backup options" value={options} disabled={busy}
      helperText="Instance options include users, include_schemas, exclude_schemas, include_users and exclude_users, together with native schema-dump options. Optional system_state_tables select native system-table checkpoints; system_state_write_pause_confirmed:true acknowledges a server-wide read lock throughout the dump. The application assigns the private output path."
      onChange={event=>{setOptions(event.target.value);setReview(null);}} />
    <Button disabled={busy} onClick={()=>{try {const selected=JSON.parse(options);run('review',{options:selected},value=>{setReview(value);setReceipt(null);setFiles(null);});} catch(failure) {setError(failure.message);}}}>Review full-instance backup</Button>
    <Button disabled={busy} onClick={()=>load(0)}>Load instance backup jobs</Button>
    {review && <Box>
      {review.warnings.map(warning=><Alert severity="warning" key={warning}>{warning}</Alert>)}
      <Box component="pre" aria-label="Instance backup review" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify({source:review.source,options:review.options,execution_host:review.execution_host},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={()=>run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value=>{setReceipt(value);setReview(current=>({...current,state:value.state}));})}>Confirm and start instance backup</Button>
    </Box>}
    {page && <>
      <Table size="small" aria-label="Instance backup jobs"><TableHead><TableRow>{['Job','Source','State','Inspect'].map(label=><TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
        {page.jobs.map(job=><TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{job.source.server_uuid}</TableCell><TableCell>{job.state}</TableCell><TableCell><Button disabled={busy} onClick={()=>inspect(job)}>Inspect instance backup {job.job_id}</Button></TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={page.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={page.offset/25} onPageChange={(_event,next)=>load(next*25)} />
      {page.unavailable_job_ids?.length>0 && <Alert severity="warning">Some backup receipts are unavailable: {page.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={['completed','artifact_verified'].includes(receipt.state) ? 'success' : ['failed','unknown','native_returned_unverified'].includes(receipt.state) ? 'warning' : 'info'}>
        Instance backup {receipt.job_id}: {receipt.state}. Native dump reply acknowledged: {receipt.native_dump_acknowledged ? 'yes' : 'no'}.
        {receipt.state==='artifact_verified' && ' File acceptance does not change the original native reply.'}
        {receipt.artifact_removed && ' Backup files were removed; its receipt remains.'}
      </Alert>
      {receipt.native_error && <Alert severity="error">Native backup error {receipt.native_error.code ?? ''}: {receipt.native_error.message}</Alert>}
      {(receipt.result?.private_script_cleanup || receipt.private_script_cleanup)?.complete===false && <Alert severity="warning">Private execution-script cleanup is incomplete. <Button disabled={busy} onClick={()=>run('cleanup_script',{job_id:receipt.job_id},setReceipt)}>Retry private-script cleanup</Button></Alert>}
      <Button disabled={busy} onClick={()=>inspect(receipt)}>Refresh instance backup receipt</Button>
      {receipt.server_lock_owner && <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={()=>run('observe_source_locks',{job_id:receipt.job_id},setReceipt)}>Observe original source lock cleanup</Button>}
      {receipt.source_lock_cleanup_observation && <Alert severity={receipt.source_lock_cleanup_observation.released===true ? 'info' : 'warning'}>Original source lock cleanup: {receipt.source_lock_cleanup_observation.released===true ? 'confirmed' : 'unconfirmed'}. The original dump reply and file acceptance are unchanged.</Alert>}
      {receipt.utility_observation_unavailable && receipt.native_process_termination_confirmed!==true && <Alert severity="warning">The original utility reference is unavailable. This receipt cannot confirm cleanup or cancel that client. The original outcome is unchanged.</Alert>}
      {receipt.interrupted_utility_observation && <Alert severity={receipt.native_process_termination_confirmed===true ? 'info' : 'warning'}>Interrupted utility cleanup: {receipt.native_process_termination_confirmed===true ? 'confirmed' : 'unconfirmed'}. Original native acknowledgement is unchanged. Backup files still require independent verification.</Alert>}
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed' && !(receipt.state==='unknown' && receipt.durable_tool && receipt.native_process_termination_confirmed!==true)} onClick={()=>run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel instance backup</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state) || receipt.artifact_removed} onClick={()=>run('reconcile',{job_id:receipt.job_id},setReceipt)}>Verify instance backup files</Button>
      <Button disabled={busy || !receipt.result?.artifact || receipt.artifact_removed} onClick={()=>run('files',{job_id:receipt.job_id,offset:0,limit:100},setFiles)}>Load instance backup files</Button>
      <Button disabled={busy || !receipt.result?.artifact || receipt.artifact_removed} onClick={()=>run('pin',{job_id:receipt.job_id,pinned:!receipt.retention_pinned},setReceipt)}>{receipt.retention_pinned ? 'Unprotect instance backup from removal' : 'Protect instance backup from removal'}</Button>
      {files && <>
        <Table size="small" aria-label="Verified instance backup files"><TableHead><TableRow>{['File','Bytes','SHA256','Download'].map(label=><TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
          {files.files.map(row=><TableRow key={row.path}><TableCell>{row.path}</TableCell><TableCell>{row.size}</TableCell><TableCell>{row.sha256}</TableCell><TableCell><Button onClick={()=>download(row)}>Download {row.path}</Button></TableCell></TableRow>)}
        </TableBody></Table><TablePagination component="div" count={files.total} rowsPerPage={100} rowsPerPageOptions={[100]} page={files.offset/100} onPageChange={(_event,next)=>run('files',{job_id:receipt.job_id,offset:next*100,limit:100},setFiles)} />
      </>}
      {!receipt.artifact_removed && !ACTIVE.has(receipt.state) && <Box sx={{my:1,display:'flex',gap:1}}>
        <TextField size="small" label="Confirm instance backup job identity for removal" value={confirmation} onChange={event=>setConfirmation(event.target.value)} />
        <Button disabled={busy || confirmation!==receipt.job_id || receipt.retention_pinned} onClick={()=>run(receipt.artifact_removal ? 'removal_reconcile' : 'remove_artifact',{job_id:receipt.job_id,confirmation},value=>{setReceipt(value);setFiles(null);})}>{receipt.artifact_removal ? 'Reconcile instance backup removal' : 'Remove instance backup files'}</Button>
      </Box>}
      <Box component="details"><summary>Native instance backup observations</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
MySQLInstanceBackups.propTypes={post:PropTypes.func.isRequired,endpointUrl:PropTypes.string.isRequired};
