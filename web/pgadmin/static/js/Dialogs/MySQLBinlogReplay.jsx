import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TablePagination,TextField} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
export default function MySQLBinlogReplay({post}) {
  const [target,setTarget]=useState(null),[sources,setSources]=useState(null),[source,setSource]=useState('');
  const [archives,setArchives]=useState(null),[archive,setArchive]=useState('');
  const [mode,setMode]=useState('all'),[gtid,setGtid]=useState(''),[confirmation,setConfirmation]=useState(''),[timeout,setTimeoutValue]=useState(3600);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[facts,setFacts]=useState(null),[ack,setAck]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0);
  useEffect(() => {generation.current++;setTarget(null);setSources(null);setSource('');setArchives(null);setArchive('');setReview(null);setReceipt(null);setJobs(null);setFacts(null);setAck('');setConfirmation('');setBusy(false);setError('');return () => {generation.current++;};},[post]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:'mysql_binlog_replay_'+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native replay request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(() => {
    if(!ACTIVE.has(receipt?.state))return;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const value=await post({action:'mysql_binlog_replay_status',request:{job_id:receipt.job_id}});if(live)setReceipt(value);}
      catch(failure) {if(live)setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending=false;}
    },1000);
    return () => {live=false;clearInterval(timer);};
  },[post,receipt?.job_id,receipt?.state]);
  const change=setter => event => {setter(event.target.value);setReview(null);};
  const loadJobs=offset => run('list',{offset,limit:25},setJobs);
  const inspect=job => run('status',{job_id:job.job_id},value => {setReceipt(value);setFacts(null);setAck('');});
  const save=() => {
    const url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='mysql-replay-'+receipt.job_id+'.json';link.click();
    window.setTimeout(() => URL.revokeObjectURL(url),1000);
  };
  return <Box sx={{p:1,overflow:'auto',flex:1}}>
    <Alert severity="warning">Replay changes from a sealed whole-server archive onto this separate target. Restore and verify a compatible base first. Transactions can commit individually; cancellation does not undo them. Native utility return and GTID coverage do not verify recovered data or production cutover.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <Button disabled={busy} onClick={() => run('inspect',{},value => {setTarget(value);setReview(null);})}>Inspect replay target</Button>
      <Button disabled={busy} onClick={() => run('sources',{offset:0,limit:25},setSources)}>Load archive sources</Button>
      <Button disabled={busy} onClick={() => loadJobs(0)}>Load replay jobs</Button>
    </Box>
    {target && <Box component="details" open><summary>Native replay target: {target.identity.server_uuid}</summary><Box component="pre" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(target,null,2)}</Box></Box>}
    {sources && <>
      <TextField select size="small" label="Owned archive source" value={source} sx={{minWidth:280}} onChange={event => {setSource(event.target.value);setArchives(null);setArchive('');setReview(null);}}>
        {sources.sources.map(item => <MenuItem key={item.server_id} value={item.server_id}>{item.name} ({item.server_id})</MenuItem>)}
      </TextField>
      <TablePagination component="div" count={sources.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={sources.offset/25} onPageChange={(_event,next) => run('sources',{offset:next*25,limit:25},value => {setSources(value);setSource('');setArchives(null);setArchive('');setReview(null);})} />
      <Button disabled={busy || source===''} onClick={() => run('archives',{source_server_id:source,offset:0,limit:25},setArchives)}>Load sealed archives</Button>
    </>}
    {archives && <>
      <TextField select size="small" label="Sealed native archive" value={archive} sx={{minWidth:380}} onChange={change(setArchive)}>
        {archives.jobs.filter(item => ['completed','artifact_verified'].includes(item.state) && !item.artifact_removed && item.native_process_termination_confirmed===true).map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} ({item.result?.artifact?.total_bytes} bytes)</MenuItem>)}
      </TextField>
      <TablePagination component="div" count={archives.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={archives.offset/25} onPageChange={(_event,next) => run('archives',{source_server_id:source,offset:next*25,limit:25},value => {setArchives(value);setArchive('');setReview(null);})} />
      {archives.unavailable_job_ids?.length>0 && <Alert severity="warning">Some archive receipts are unavailable: {archives.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <TextField select size="small" label="Replay boundary" value={mode} onChange={change(setMode)}><MenuItem value="all">All archived transactions</MenuItem><MenuItem value="before">Stop before GTID</MenuItem><MenuItem value="after">Stop after GTID</MenuItem></TextField>
      {mode!=='all' && <TextField size="small" label="Native stop GTID" value={gtid} onChange={change(setGtid)} />}
      <TextField size="small" label="Confirm target server UUID" value={confirmation} onChange={change(setConfirmation)} />
      <TextField size="small" type="number" label="Runtime seconds (blank: no deadline)" value={timeout ?? ''} onChange={event => {setTimeoutValue(event.target.value==='' ? null : Number(event.target.value));setReview(null);}} />
      <Button disabled={busy || !target || source==='' || !archive || confirmation!==target.identity.server_uuid} onClick={() => run('review',{source_server_id:source,archive_job_id:archive,options:{stop_mode:mode,stop_gtid:mode==='all' ? null : gtid,target_confirmation:confirmation,timeout_seconds:timeout}},setReview)}>Review replay</Button>
    </Box>
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Native replay review" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify({target:review.target,source_archive:review.source_archive,options:review.options,execution_host:review.execution_host},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={() => run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value => {setReceipt(value);setFacts(null);setAck('');setReview(current => ({...current,state:value.state}));})}>Confirm and start replay</Button>
    </Box>}
    {jobs && <>
      <Table size="small" aria-label="Native MySQL replay jobs"><TableHead><TableRow>{['Job','State','Native load','Receipt'].map(value => <TableCell key={value}>{value}</TableCell>)}</TableRow></TableHead><TableBody>{jobs.jobs.map(job => <TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{job.state}</TableCell><TableCell>{job.native_load_outcome}</TableCell><TableCell><Button disabled={busy} aria-label={'Inspect replay '+job.job_id} onClick={() => inspect(job)}>Inspect</Button></TableCell></TableRow>)}</TableBody></Table>
      <TablePagination component="div" count={jobs.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={jobs.offset/25} onPageChange={(_event,next) => loadJobs(next*25)} />
      {jobs.unavailable_job_ids?.length>0 && <Alert severity="warning">Some replay receipts are unavailable: {jobs.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={receipt.state==='unknown' ? 'warning' : 'info'}>Replay {receipt.job_id}: {receipt.state}. Native load: {receipt.native_load_outcome}. {receipt.state==='unknown' && ('The outcome is uncertain. '+(receipt.target_state_acknowledged_at ? '' : 'This target is fenced. ')+'This operation will not replay automatically.')} Recovered data has not been independently verified.</Alert>
      <Button disabled={busy} onClick={() => inspect(receipt)}>Refresh replay receipt</Button>
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed'} onClick={() => run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel replay</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={() => run('reconcile',{job_id:receipt.job_id},value => {setReceipt(value);setFacts(value);setAck('');})}>Inspect current target facts</Button>
      <Button onClick={save}>Download replay receipt</Button>
      {facts && <Box component="pre" aria-label="Native replay reconciliation" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(facts.reconciliation,null,2)}</Box>}
      {receipt.state==='unknown' && !receipt.target_state_acknowledged_at && facts && <Box sx={{display:'flex',gap:1,my:1}}>
        <TextField size="small" label="Acknowledge uncertain target UUID" value={ack} onChange={event => setAck(event.target.value)} />
        <Button disabled={busy || receipt.native_process_termination_confirmed!==true || facts.reconciliation?.native_lock_free!==true || ack!==receipt.target.server_uuid} onClick={() => run('acknowledge',{job_id:receipt.job_id,target_confirmation:ack,observation_digest:facts.observation_digest},value => {setReceipt(value);setFacts(null);setAck('');})}>Acknowledge facts and release target fence</Button>
      </Box>}
      {receipt.target_state_acknowledged_at && <Alert severity="info">The observed target state was acknowledged. The original native load outcome remains uncertain. A new operation requires a new review.</Alert>}
      <Box component="details"><summary>Native replay observations</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
MySQLBinlogReplay.propTypes={post:PropTypes.func.isRequired};
