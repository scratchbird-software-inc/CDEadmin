import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TablePagination,TextField} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
export default function MySQLSourceLogs({post}) {
  const [catalog,setCatalog]=useState(null),[mode,setMode]=useState('TO'),[file,setFile]=useState(''),[date,setDate]=useState('');
  const [timeout,setTimeoutValue]=useState(60),[review,setReview]=useState(null),[confirmed,setConfirmed]=useState(false);
  const [receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[page,setPage]=useState(0);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0);
  useEffect(() => {
    generation.current++;setCatalog(null);setReview(null);setReceipt(null);setJobs(null);setPage(0);setConfirmed(false);setError('');setBusy(false);
    return () => {generation.current++;};
  },[post]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:'mysql_binlog_source_purge_'+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native source log request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(() => {
    if(!ACTIVE.has(receipt?.state))return;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const value=await post({action:'mysql_binlog_source_purge_status',request:{job_id:receipt.job_id}});if(live)setReceipt(value);}
      catch(failure) {if(live)setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending=false;}
    },500);
    return () => {live=false;clearInterval(timer);};
  },[post,receipt?.job_id,receipt?.state]);
  const change=setter => event => {setter(event.target.value);setReview(null);setConfirmed(false);};
  const load=next => run('list',{offset:next*25,limit:25},value => {setJobs(value);setPage(next);});
  return <Box sx={{my:1}}>
    <Alert severity="warning">Native server log administration permanently removes binary logs on the selected database server. Check required backups and replicas first. Application archive files have separate retention controls.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <Button disabled={busy} onClick={() => run('catalog',{},setCatalog)}>Inspect source log purge catalog</Button>
      <Button disabled={busy} onClick={() => load(page)}>Load source log purge receipts</Button>
      <TextField select size="small" label="Native purge condition" value={mode} onChange={change(setMode)}>
        <MenuItem value="TO">Before native filename (keep boundary)</MenuItem><MenuItem value="BEFORE">Before UTC time</MenuItem>
      </TextField>
      {mode==='TO' ? <TextField select size="small" label="Native log to keep as boundary" value={file} sx={{minWidth:250}} onChange={change(setFile)}>
        {(catalog?.logs || []).map(row => <MenuItem value={row.Log_name} key={row.Log_name}>{row.Log_name}</MenuItem>)}
      </TextField> : <TextField size="small" label="Native purge UTC cutoff" value={date} onChange={change(setDate)} helperText="YYYY-MM-DD HH:MM:SS; native server evaluates file timestamps" />}
      <TextField size="small" type="number" label="Purge client read timeout (blank: none)" value={timeout ?? ''} onChange={event => {
        setTimeoutValue(event.target.value==='' ? null : Number(event.target.value));setReview(null);setConfirmed(false);
      }} />
      <Button disabled={busy} onClick={() => run('review',{options:{mode,...(mode==='TO' ? {to_file:file} : {before_utc:date}),timeout_seconds:timeout}},value => {setReview(value);setConfirmed(false);})}>Review native server log purge</Button>
    </Box>
    {catalog && <Box component="details"><summary>Source log administration catalog: {catalog.status}</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:220,overflow:'auto'}}>{JSON.stringify(catalog,null,2)}</Box></Box>}
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Native source log purge review" sx={{whiteSpace:'pre-wrap',maxHeight:260,overflow:'auto'}}>{JSON.stringify({source:review.source,options:review.options,purge_selection:review.purge_selection,execution_host:review.execution_host},null,2)}</Box>
      <FormControlLabel label="I checked required backups and replicas and authorize permanent server log removal" control={<Checkbox disabled={busy || review.state!=='reviewed'} checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || !confirmed || review.state!=='reviewed'} onClick={() => run('start',{
        job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value => {setReceipt(value);setReview(current => ({...current,state:value.state}));setConfirmed(false);})}>Confirm native server log purge</Button>
    </Box>}
    {jobs && <>
      <Table size="small" aria-label="Native source log purge receipts"><TableHead><TableRow>{['Job','Condition','State','Receipt'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
        {jobs.jobs.map(job => <TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{job.options.mode}: {job.options.to_file || job.options.before_utc}</TableCell><TableCell>{job.state}</TableCell>
          <TableCell><Button disabled={busy} aria-label={'Inspect source log purge '+job.job_id} onClick={() => run('status',{job_id:job.job_id},setReceipt)}>Inspect</Button></TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={jobs.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={page} onPageChange={(_event,next) => load(next)} />
    </>}
    {receipt && <Box>
      <Alert severity={receipt.state==='native_acknowledged' ? 'success' : ['unknown','native_failed','not_dispatched'].includes(receipt.state) ? 'warning' : 'info'}>
        Source log purge {receipt.job_id}: {receipt.state}.
        {receipt.state==='native_acknowledged' && ' Native SQL returned successfully. Inspect warnings and independently observed files for the resulting scope.'}
        {receipt.state==='unknown' && ' The original SQL reply is unconfirmed. Reconciliation records current facts and never replays the purge.'}
      </Alert>
      <Button disabled={busy} onClick={() => run('status',{job_id:receipt.job_id},setReceipt)}>Refresh source log purge receipt</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state) || receipt.state==='reviewed'} onClick={() => run('reconcile',{job_id:receipt.job_id},setReceipt)}>Reconcile source log purge</Button>
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed'} onClick={() => run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel source log purge</Button>
      <Box component="details"><summary>Native source log purge observations</summary><Box component="pre" aria-label="Native source log purge receipt" sx={{whiteSpace:'pre-wrap',maxHeight:350,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
MySQLSourceLogs.propTypes={post:PropTypes.func.isRequired};
