import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import ReceiverFileCleanup from './ReceiverFileCleanup';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TablePagination,TextField} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);

export default function ContinuousBinlog({post,engine,onInspectArchive}) {
  const prefix=engine+'_binlog_capture_';
  const [catalog,setCatalog]=useState(null),[startFile,setStartFile]=useState(''),[serverId,setServerId]=useState(''),[timeout,setTimeoutValue]=useState(null);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[page,setPage]=useState(0);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const [confirmStop,setConfirmStop]=useState(false);
  const [confirmRecollect,setConfirmRecollect]=useState(false);
  const [checkpoints,setCheckpoints]=useState(null),[checkpointArchive,setCheckpointArchive]=useState(''),[checkpoint,setCheckpoint]=useState(null),[confirmCheckpoint,setConfirmCheckpoint]=useState(false);
  const [tails,setTails]=useState(null),[tailFiles,setTailFiles]=useState([]),[tailReview,setTailReview]=useState(null);
  const generation=useRef(0);
  useEffect(() => {
    generation.current++;setCatalog(null);setStartFile('');setServerId('');setTimeoutValue(null);setReview(null);setReceipt(null);setJobs(null);setPage(0);setBusy(false);setError('');setConfirmStop(false);
    return () => {generation.current++;};
  },[post,engine]);
  useEffect(() => {setConfirmStop(false);setConfirmRecollect(false);},[receipt?.job_id,receipt?.state]);
  useEffect(() => {setTails(null);setTailFiles([]);setTailReview(null);},[post,engine,receipt?.job_id]);
  useEffect(() => {setCheckpoints(null);setCheckpointArchive('');setCheckpoint(null);setConfirmCheckpoint(false);},[post,engine,receipt?.job_id]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:prefix+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native binary-log receiver request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(() => {
    if(!ACTIVE.has(receipt?.state))return;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const value=await post({action:prefix+'status',request:{job_id:receipt.job_id}});if(live)setReceipt(value);}
      catch(failure) {if(live)setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending=false;}
    },1000);
    return () => {live=false;clearInterval(timer);};
  },[post,prefix,receipt?.job_id,receipt?.state]);
  const load=next => run('list',{offset:next*25,limit:25},value => {setJobs(value);setPage(next);});
  const snapshots=receipt?.result?.last_archive_job_ids || receipt?.progress?.last_archive_job_ids || [];
  return <Box component="section" aria-label={'Continuous '+engine+' binary logs'} sx={{my:1}}>
    <Alert severity="info">The native receiver follows active binary logs. Independently verified closed batches become ordinary native archives for download and replay. Private active tails are retained separately. No receiver is automatically restarted.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <Button disabled={busy} onClick={() => run('catalog',{},setCatalog)}>Inspect receiver source</Button>
      <Button disabled={busy} onClick={() => load(page)}>Load binary-log receivers</Button>
      <TextField disabled={busy} size="small" select label="Receiver starting native log" value={startFile} onChange={event => {setStartFile(event.target.value);setReview(null);}}>
        <MenuItem value="">Select native log</MenuItem>{(catalog?.logs || []).map(row => <MenuItem key={row.Log_name} value={row.Log_name}>{row.Log_name}{row.closed ? ' (closed)' : ' (active)'}</MenuItem>)}
      </TextField>
      <TextField disabled={busy} size="small" type="number" label="Unique receiver server ID" value={serverId} onChange={event => {setServerId(event.target.value);setReview(null);}} />
      <TextField disabled={busy} size="small" type="number" label="Receiver runtime seconds (blank: no deadline)" value={timeout ?? ''} onChange={event => {setTimeoutValue(event.target.value==='' ? null : Number(event.target.value));setReview(null);setTailReview(null);}} />
      <Button disabled={busy} onClick={() => run('review',{options:{start_file:startFile,receiver_server_id:Number(serverId),timeout_seconds:timeout}},setReview)}>Review continuous receiver</Button>
    </Box>
    {catalog && <Box component="details"><summary>Native receiver source: {catalog.status}</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:240,overflow:'auto'}}>{JSON.stringify(catalog,null,2)}</Box></Box>}
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Native continuous receiver review" sx={{whiteSpace:'pre-wrap',maxHeight:280,overflow:'auto'}}>{JSON.stringify({source:review.source,options:review.options,program:review.program,execution_host:review.execution_host,continuation:review.continuation},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={() => run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value => {setReceipt(value);setReview(current => ({...current,state:value.state}));})}>Confirm and start continuous receiver</Button>
    </Box>}
    {jobs && <>
      <Table size="small" aria-label="Native binary-log receivers"><TableHead><TableRow>{['Job','Starting log','State','Receipt'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
        {jobs.jobs.map(job => <TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{job.options.start_file}</TableCell><TableCell>{job.state}</TableCell>
          <TableCell><Button disabled={busy} onClick={() => run('status',{job_id:job.job_id},setReceipt)}>Inspect receiver {job.job_id}</Button></TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={jobs.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={page} onPageChange={(_event,next) => load(next)} />
    </>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={['unknown','failed','not_dispatched'].includes(receipt.state) ? 'warning' : 'info'}>Receiver {receipt.job_id}: {receipt.state}. Published archive batches: {receipt.result?.published_batches ?? receipt.progress?.published_batches ?? 0}. Automatic restart: disabled.</Alert>
      <Button disabled={busy} onClick={() => run('status',{job_id:receipt.job_id},setReceipt)}>Refresh continuous receiver</Button>
      <Button disabled={busy || (!ACTIVE.has(receipt.state) && receipt.state!=='reviewed')} onClick={() => run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel continuous receiver</Button>
      {['cancelled','captured'].includes(receipt.state) && receipt.native_process_termination_confirmed && receipt.result?.next_file && <Button disabled={busy}
        onClick={() => run('review',{resume_job_id:receipt.job_id,options:{start_file:receipt.result.next_file,receiver_server_id:Number(serverId),timeout_seconds:timeout}},value => {setStartFile(value.options.start_file);setReview(value);})}>Review restart from stopped receiver</Button>}
      {['unknown','failed','cancelled','captured'].includes(receipt.state) && <Box>
        <FormControlLabel label="Confirm stopping this receiver's remaining native utilities" control={<Checkbox disabled={busy} checked={confirmStop} onChange={event => setConfirmStop(event.target.checked)} />} />
        <Button disabled={busy || !confirmStop} onClick={() => run('reconcile_writer',{job_id:receipt.job_id,confirmed:true},value => {setReceipt(value);setConfirmStop(false);})}>Reconcile receiver writers</Button>
      </Box>}
      {receipt.writer_reconciliation?.process_scope_stopped && <Alert severity="info">Owned receiver and snapshot-parser utilities are stopped. This does not verify private tails or establish database recovery.</Alert>}
      {engine==='mysql' && ['unknown','failed'].includes(receipt.state) && (receipt.writer_reconciliation?.process_scope_stopped || receipt.native_process_termination_confirmed) && <Box>
        <Alert severity="info">A separate full collection can read the original native file again if it is still available. Existing archive batches may be duplicated. The unresolved receiver and cursor stay unchanged; no SQL is replayed.</Alert>
        <FormControlLabel label="Acknowledge full recollection and possible duplicate archives" control={<Checkbox disabled={busy} checked={confirmRecollect} onChange={event => {setConfirmRecollect(event.target.checked);setReview(null);}} />} />
        <Button disabled={busy || !confirmRecollect} onClick={() => run('review',{recollect_job_id:receipt.job_id,acknowledge_recollection:true,
          options:{start_file:receipt.options.start_file,receiver_server_id:Number(serverId),timeout_seconds:timeout}},value => {setStartFile(value.options.start_file);setReview(value);})}>Review full recollection from original log</Button>
      </Box>}
      {engine==='mysql' && ['unknown','failed','cancelled','captured'].includes(receipt.state) && <Box>
        <Button disabled={busy} onClick={() => run('checkpoint_catalog',{job_id:receipt.job_id},value => {setCheckpoints(value);setCheckpointArchive('');setCheckpoint(null);setConfirmCheckpoint(false);})}>Inspect retained checkpoint archives</Button>
        {checkpoints && <>
          <Alert severity="info">Select a verified archive published by this receiver. Its native successor can provide a new collection boundary even if the original starting log was purged. Complete backup/log-chain and database recovery acceptance remain separate.</Alert>
          <TextField disabled={busy} size="small" select label="Retained receiver checkpoint archive" value={checkpointArchive} onChange={event => {setCheckpointArchive(event.target.value);setCheckpoint(null);setConfirmCheckpoint(false);setReview(null);}} sx={{minWidth:320}}>
            <MenuItem value="">Select retained archive</MenuItem>{checkpoints.archives.map(row => <MenuItem key={row.job_id} disabled={!row.available} value={row.job_id}>{row.job_id}{row.available ? ' → '+row.end_at.file+' ('+row.bytes+' bytes)' : ' (unavailable)'}</MenuItem>)}
          </TextField>
          <Button disabled={busy || !checkpoints.more} onClick={() => run('checkpoint_catalog',{job_id:receipt.job_id,after:checkpoints.next_after},value => {setCheckpoints(value);setCheckpointArchive('');setCheckpoint(null);setConfirmCheckpoint(false);})}>Next checkpoint archive page</Button>
          <Button disabled={busy || !checkpointArchive} onClick={() => run('checkpoint_inspect',{job_id:receipt.job_id,archive_job_id:checkpointArchive},value => {setCheckpoint(value);setConfirmCheckpoint(false);setReview(null);})}>Inspect native archive successor</Button>
          {checkpoint && <Box>
            <Alert severity="info">Native successor: {checkpoint.checkpoint.next_file}. Complete archive bytes will be verified in the worker before the native receiver starts. The prior receiver outcome stays unchanged.</Alert>
            <Box component="pre" aria-label="Native receiver archive checkpoint" sx={{whiteSpace:'pre-wrap',maxHeight:220,overflow:'auto'}}>{JSON.stringify(checkpoint,null,2)}</Box>
            <FormControlLabel label="Acknowledge the retained archive checkpoint" control={<Checkbox disabled={busy} checked={confirmCheckpoint} onChange={event => {setConfirmCheckpoint(event.target.checked);setReview(null);}} />} />
            <Button disabled={busy || !confirmCheckpoint} onClick={() => run('review',{recover_job_id:receipt.job_id,archive_job_id:checkpointArchive,acknowledge_archive_checkpoint:true,
              options:{start_file:checkpoint.checkpoint.next_file,receiver_server_id:Number(serverId),timeout_seconds:timeout}},value => {setStartFile(value.options.start_file);setReview(value);})}>Review receiver from retained checkpoint</Button>
          </Box>}
        </>}
      </Box>}
      {['unknown','failed','cancelled','captured'].includes(receipt.state) && <ReceiverFileCleanup post={post} engine={engine} receiverJobId={receipt.job_id} />}
      {['unknown','failed','cancelled','captured'].includes(receipt.state) && <Box>
        <Button disabled={busy} onClick={() => run('tail_catalog',{job_id:receipt.job_id},value => {setTails(value);setTailFiles([]);setTailReview(null);})}>Inspect stopped receiver files</Button>
        {tails && <>
          <Alert severity="info">Only complete native closed files can be adopted. Each adoption creates a separate verified archive; the receiver outcome and active tails remain independent.</Alert>
          <Table size="small" aria-label="Stopped native receiver files"><TableHead><TableRow>{['Select','Native log','Local bytes','Native bytes','Eligibility'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
            {tails.logs.map(row => <TableRow key={row.Log_name}>
              <TableCell><Checkbox inputProps={{'aria-label':'Adopt '+row.Log_name}} disabled={busy || !row.eligible} checked={tailFiles.includes(row.Log_name)} onChange={event => {setTailFiles(current => event.target.checked ? [...current,row.Log_name] : current.filter(name => name!==row.Log_name));setTailReview(null);}} /></TableCell>
              <TableCell>{row.Log_name}</TableCell><TableCell>{row.local_bytes}</TableCell><TableCell>{row.File_size}</TableCell><TableCell>{row.eligible ? 'Complete closed candidate' : row.reason}</TableCell>
            </TableRow>)}
          </TableBody></Table>
          <Button disabled={busy || !tailFiles.length} onClick={() => run('tail_review',{job_id:receipt.job_id,options:{log_names:tails.logs.filter(row => tailFiles.includes(row.Log_name)).map(row => row.Log_name),timeout_seconds:timeout}},setTailReview)}>Review stopped-file adoption</Button>
        </>}
        {tailReview && <Box>
          <Box component="pre" aria-label="Stopped-file archive review" sx={{whiteSpace:'pre-wrap',maxHeight:280,overflow:'auto'}}>{JSON.stringify(tailReview,null,2)}</Box>
          <Button disabled={busy || tailReview.state!=='reviewed'} onClick={() => run('tail_start',{job_id:tailReview.job_id,review_digest:tailReview.review_digest,confirmed:true},value => {setTailReview(current => ({...current,state:value.state}));onInspectArchive(value.job_id);})}>Confirm and adopt stopped logs</Button>
        </Box>}
      </Box>}
      {snapshots.map(id => <Button key={id} disabled={busy} onClick={() => onInspectArchive(id)}>Inspect produced archive {id}</Button>)}
      <Box component="details"><summary>Native continuous receiver observations</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
ContinuousBinlog.propTypes={post:PropTypes.func.isRequired,engine:PropTypes.oneOf(['mysql','mariadb']).isRequired,onInspectArchive:PropTypes.func.isRequired};
