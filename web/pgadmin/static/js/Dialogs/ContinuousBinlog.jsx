import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TablePagination,TextField} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);

export default function ContinuousBinlog({post,engine,onInspectArchive}) {
  const prefix=engine+'_binlog_capture_';
  const [catalog,setCatalog]=useState(null),[startFile,setStartFile]=useState(''),[serverId,setServerId]=useState(''),[timeout,setTimeoutValue]=useState(null);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[page,setPage]=useState(0);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0);
  useEffect(() => {
    generation.current++;setCatalog(null);setStartFile('');setServerId('');setTimeoutValue(null);setReview(null);setReceipt(null);setJobs(null);setPage(0);setBusy(false);setError('');
    return () => {generation.current++;};
  },[post,engine]);
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
      <TextField disabled={busy} size="small" type="number" label="Receiver runtime seconds (blank: no deadline)" value={timeout ?? ''} onChange={event => {setTimeoutValue(event.target.value==='' ? null : Number(event.target.value));setReview(null);}} />
      <Button disabled={busy} onClick={() => run('review',{options:{start_file:startFile,receiver_server_id:Number(serverId),timeout_seconds:timeout}},setReview)}>Review continuous receiver</Button>
    </Box>
    {catalog && <Box component="details"><summary>Native receiver source: {catalog.status}</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:240,overflow:'auto'}}>{JSON.stringify(catalog,null,2)}</Box></Box>}
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Native continuous receiver review" sx={{whiteSpace:'pre-wrap',maxHeight:280,overflow:'auto'}}>{JSON.stringify({source:review.source,options:review.options,program:review.program,execution_host:review.execution_host},null,2)}</Box>
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
      {snapshots.map(id => <Button key={id} disabled={busy} onClick={() => onInspectArchive(id)}>Inspect produced archive {id}</Button>)}
      <Box component="details"><summary>Native continuous receiver observations</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
ContinuousBinlog.propTypes={post:PropTypes.func.isRequired,engine:PropTypes.oneOf(['mysql','mariadb']).isRequired,onInspectArchive:PropTypes.func.isRequired};
