import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Table,TableBody,TableCell,TableHead,TableRow,TablePagination,TextField} from '@mui/material';
import MySQLInstanceAcceptance from './MySQLInstanceAcceptance';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
const DEFAULT_OPTIONS=JSON.stringify({load_users:false,checksum:true,threads:4,update_gtid_set:'off',timeout_seconds:3600},null,2);
export default function MySQLInstanceRestores({post}) {
  const [sources,setSources]=useState(null),[source,setSource]=useState(null),[backups,setBackups]=useState(null),[backup,setBackup]=useState(null);
  const [target,setTarget]=useState(null),[confirmation,setConfirmation]=useState(''),[options,setOptions]=useState(DEFAULT_OPTIONS);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[observation,setObservation]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const generation=useRef(0);
  useEffect(()=> {
    generation.current++;setSources(null);setSource(null);setBackups(null);setBackup(null);setTarget(null);setConfirmation('');setOptions(DEFAULT_OPTIONS);
    setReview(null);setReceipt(null);setJobs(null);setObservation(null);setBusy(false);setError('');
    return ()=>{generation.current++;};
  },[post]);
  const run=async(action,request,accept)=> {
    const token=generation.current;setBusy(true);setError('');
    try {const result=await post({action:'mysql_instance_restore_'+action,request});if(token===generation.current)accept(result);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native instance restore request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(()=> {
    if(!ACTIVE.has(receipt?.state))return;
    const token=generation.current;let pending=false,live=true;
    const timer=setInterval(async()=> {
      if(pending)return;pending=true;
      try {const result=await post({action:'mysql_instance_restore_status',request:{job_id:receipt.job_id}});if(live && token===generation.current)setReceipt(result);}
      catch(failure) {if(live && token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native restore status unavailable');}
      finally {pending=false;}
    },1500);
    return ()=>{live=false;clearInterval(timer);};
  },[receipt?.job_id,receipt?.state,post]);
  const loadSources=offset=>run('sources',{offset,limit:25},setSources);
  const loadBackups=offset=>run('backups',{source_server_id:source.server_id,offset,limit:25},setBackups);
  const loadJobs=offset=>run('list',{offset,limit:25},setJobs);
  return <Box sx={{p:2}}>
    <Alert severity="warning">Restore a managed full-instance backup onto a separate confirmed MySQL instance during an exclusive maintenance window. Native DDL, data, accounts and GTIDs can change independently; cancellation does not undo earlier effects. Configure trusted local_infile on the target before loading. Closing this view does not cancel a job.</Alert>
    <Alert severity="info">Native utility return, current target observations, recovered data/definitions and production cutover have separate acceptance. Account loading is optional. An uncertain restore is never automatically repeated.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={()=>run('inspect',{},value=>{setTarget(value);setReview(null);})}>Inspect instance restore target</Button>
    {target && <Box component="pre" aria-label="Native instance restore target" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(target,null,2)}</Box>}
    <Button disabled={busy} onClick={()=>loadSources(0)}>Load instance backup sources</Button>
    {sources && <>
      {sources.sources.map(row=><Button disabled={busy} key={row.server_id} onClick={()=>{setSource(row);setBackups(null);setBackup(null);setReview(null);}}>Use backup source {row.name}</Button>)}
      <TablePagination component="div" count={sources.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={sources.offset/25} onPageChange={(_event,next)=>loadSources(next*25)} />
    </>}
    {source && <Box><Box>Backup source: {source.name}</Box><Button disabled={busy} onClick={()=>loadBackups(0)}>Load source instance backups</Button></Box>}
    {backups && <>
      <Table size="small" aria-label="Restore source instance backups"><TableHead><TableRow>{['Backup','State','Use'].map(label=><TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
        {backups.jobs.map(row=><TableRow key={row.job_id}><TableCell>{row.job_id}</TableCell><TableCell>{row.state}</TableCell><TableCell><Button disabled={busy || !['completed','artifact_verified'].includes(row.state) || row.artifact_removed} onClick={()=>{setBackup(row);setReview(null);}}>Use instance backup {row.job_id}</Button></TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={backups.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={backups.offset/25} onPageChange={(_event,next)=>loadBackups(next*25)} />
    </>}
    {backup && <Alert severity="info">Selected instance backup: {backup.job_id}</Alert>}
    <TextField fullWidth label="Confirm native restore target UUID" value={confirmation} disabled={busy} onChange={event=>{setConfirmation(event.target.value);setReview(null);}} />
    <TextField fullWidth multiline minRows={6} label="Native instance restore options" value={options} disabled={busy}
      helperText="Native load options include load_users, include_users/exclude_users, schema/object filters, load_data/load_ddl, drop_existing_objects and update_gtid_set. Input and progress paths are assigned privately."
      onChange={event=>{setOptions(event.target.value);setReview(null);}} />
    <Button disabled={busy || !backup || !target || confirmation!==target.identity.server_uuid} onClick={()=> {
      try {run('review',{source_server_id:source.server_id,backup_job_id:backup.job_id,options:{...JSON.parse(options),target_confirmation:confirmation}},value=>{setReview(value);setReceipt(null);setObservation(null);});}
      catch(failure) {setError(failure.message);}
    }}>Review full-instance restore</Button>
    {review && <Box>
      {review.warnings.map(warning=><Alert severity="warning" key={warning}>{warning}</Alert>)}
      <Box component="pre" aria-label="Instance restore review" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify({target:review.target,source_backup:review.source_backup,options:review.options,execution_host:review.execution_host},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={()=>run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value=>{setReceipt(value);setReview(current=>({...current,state:value.state}));})}>Confirm and start instance restore</Button>
    </Box>}
    <Button disabled={busy} onClick={()=>loadJobs(0)}>Load instance restore jobs</Button>
    {jobs && <>
      <Table size="small" aria-label="Instance restore jobs"><TableHead><TableRow>{['Job','Target','State','Inspect'].map(label=><TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
        {jobs.jobs.map(row=><TableRow key={row.job_id}><TableCell>{row.job_id}</TableCell><TableCell>{row.target.server_uuid}</TableCell><TableCell>{row.state}</TableCell><TableCell><Button disabled={busy} onClick={()=>run('status',{job_id:row.job_id},value=>{setReceipt(value);setObservation(null);})}>Inspect instance restore {row.job_id}</Button></TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={jobs.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={jobs.offset/25} onPageChange={(_event,next)=>loadJobs(next*25)} />
    </>}
    {receipt && <Box>
      <Alert severity={receipt.state==='native_load_returned' ? 'info' : receipt.state==='unknown' ? 'warning' : 'info'}>Instance restore {receipt.job_id}: {receipt.state}. Original native load outcome: {receipt.native_load_outcome}. Review independent acceptance receipts for data and definitions. Production cutover remains unverified.</Alert>
      {receipt.native_error && <Alert severity="error">Native restore error {receipt.native_error.code ?? ''}: {receipt.native_error.message}</Alert>}
      <Button disabled={busy} onClick={()=>run('status',{job_id:receipt.job_id},setReceipt)}>Refresh instance restore receipt</Button>
      {receipt.interrupted_utility_observation && <Alert severity={receipt.native_process_termination_confirmed===true ? 'info' : 'warning'}>Interrupted utility cleanup: {receipt.native_process_termination_confirmed===true ? 'confirmed' : 'unconfirmed'}. The original native outcome is unchanged. Target acknowledgement remains separate.</Alert>}
      <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={()=>run('observe_utilities',{job_id:receipt.job_id},setReceipt)}>Observe original restore utility without SQL connection</Button>
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed' && !(receipt.state==='unknown' && receipt.durable_tool && receipt.native_process_termination_confirmed!==true)} onClick={()=>run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel instance restore</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={()=>run('reconcile',{job_id:receipt.job_id},value=>{setReceipt(value);setObservation(value.observation_digest);})}>Observe instance restore target</Button>
      {receipt.state==='unknown' && observation && <Button disabled={busy || confirmation!==receipt.target.server_uuid} onClick={()=>run('acknowledge',{job_id:receipt.job_id,target_confirmation:confirmation,observation_digest:observation},setReceipt)}>Acknowledge observed target for another recovery</Button>}
      <Box component="details"><summary>Native instance restore observations</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
    <MySQLInstanceAcceptance post={post} sourceServerId={source?.server_id} backupJobId={backup?.job_id} targetUuid={target?.identity?.server_uuid} targetConfirmation={confirmation} />
  </Box>;
}
MySQLInstanceRestores.propTypes={post:PropTypes.func.isRequired};
