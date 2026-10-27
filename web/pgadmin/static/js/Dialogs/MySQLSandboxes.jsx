import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,MenuItem,Table,TableBody,TableCell,TableHead,TablePagination,TableRow,TextField} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
export default function MySQLSandboxes({post}) {
  const [catalog,setCatalog]=useState(null),[operation,setOperation]=useState('deploy'),[directory,setDirectory]=useState('');
  const [port,setPort]=useState('3310'),[nativeOptions,setNativeOptions]=useState('{}'),[timeout,setTimeout]=useState('300');
  const [password,setPassword]=useState(''),[secretReady,setSecretReady]=useState(false),[confirmation,setConfirmation]=useState('');
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[observed,setObserved]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const generation=useRef(0);
  const needsSecret=['deploy','stop'].includes(operation);
  useEffect(()=> {
    generation.current++;setCatalog(null);setDirectory('');setReview(null);setReceipt(null);setJobs(null);setObserved(null);
    setPassword('');setSecretReady(false);setConfirmation('');setBusy(false);setError('');
    return ()=>{generation.current++;};
  },[post]);
  const run=async(action,request,accept)=> {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:'mysql_sandbox_'+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native sandbox request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(()=> {
    if(!ACTIVE.has(receipt?.state))return;
    let live=true,pending=false;const token=generation.current;
    const timer=setInterval(async()=> {
      if(pending)return;pending=true;
      try {const value=await post({action:'mysql_sandbox_status',request:{job_id:receipt.job_id}});if(live && token===generation.current)setReceipt(value);}
      catch(failure) {if(live && token===generation.current)setError(failure.message);}
      finally {pending=false;}
    },1500);
    return ()=>{live=false;clearInterval(timer);};
  },[post,receipt?.job_id,receipt?.state]);
  const invalidate=()=>{setReview(null);setObserved(null);setPassword('');setSecretReady(false);};
  const selected=()=>({operation,port:Number(port),sandbox_directory:directory,native_options:JSON.parse(nativeOptions),
    timeout_seconds:timeout.trim()==='null' ? null : Number(timeout)});
  const prepare=action=> {
    try {run(action,{options:selected()},value=> {
      if(action==='review'){setReview(value);setReceipt(null);}else setObserved(value);
    });}catch(failure){setError(failure.message);}
  };
  const loadJobs=offset=>run('list',{offset,limit:25},setJobs);
  return <Box sx={{p:2}}>
    <Alert severity="info">Native MySQL testing sandboxes run on the ScratchRobin application execution host under its operating-system account. This works without connecting to the selected database registration. Review the host and directory before dispatch. Closing this view does not stop a job or a sandbox.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={()=>run('catalog',{},value=>{setCatalog(value);setDirectory(value.sandbox_directories[0] || '');invalidate();})}>Load native sandbox capabilities</Button>
    {catalog && <>
      <Alert severity="info">Execution scope: {catalog.execution_scope}. MySQL Shell {catalog.version}. Deploy options: {catalog.deploy_options.join(', ')}. The native server installation is configured on this host.</Alert>
      <TextField fullWidth select label="Native sandbox method" value={operation} disabled={busy} onChange={event=>{setOperation(event.target.value);setNativeOptions('{}');invalidate();}}>
        {Object.entries(catalog.methods).map(([key,value])=><MenuItem key={key} value={key}>{value}</MenuItem>)}
      </TextField>
      <TextField fullWidth select label="Execution-host sandbox base directory" value={directory} disabled={busy} onChange={event=>{setDirectory(event.target.value);invalidate();}}>
        {catalog.sandbox_directories.map(value=><MenuItem key={value} value={value}>{value}</MenuItem>)}
      </TextField>
      <TextField fullWidth label="Sandbox classic protocol port" value={port} disabled={busy} onChange={event=>{setPort(event.target.value);invalidate();}} />
      {operation==='deploy' && <TextField fullWidth multiline minRows={4} label="Native sandbox deployment options (JSON object)" value={nativeOptions} disabled={busy}
        helperText="Native mysqldOptions retains ordered option=value strings. portx defaults to ten times the classic port. Passwords are supplied separately at dispatch."
        onChange={event=>{setNativeOptions(event.target.value);invalidate();}} />}
      <TextField fullWidth label="Sandbox native runtime seconds or null" value={timeout} disabled={busy} onChange={event=>{setTimeout(event.target.value);invalidate();}} />
      <Button disabled={busy} onClick={()=>prepare('inspect')}>Inspect local sandbox</Button>
      <Button disabled={busy} onClick={()=>prepare('review')}>Review native sandbox operation</Button>
    </>}
    {observed && !observed.observation_digest && <Box component="pre" aria-label="Local sandbox inspection" sx={{whiteSpace:'pre-wrap',maxHeight:350,overflow:'auto'}}>{JSON.stringify(observed,null,2)}</Box>}
    {review && <Box>
      {review.warnings.map(value=><Alert key={value} severity="warning">{value}</Alert>)}
      <Box component="pre" aria-label="Native sandbox review" sx={{whiteSpace:'pre-wrap',maxHeight:350,overflow:'auto'}}>{JSON.stringify({sandbox:review.sandbox,options:review.options,execution_host:review.execution_host,program:review.program},null,2)}</Box>
      {needsSecret && <TextField fullWidth type="password" autoComplete="new-password" label="Sandbox native root password" value={password} disabled={busy}
        helperText="Excluded from the saved review and cleared after dispatch. Enter an empty value explicitly to use an empty native password."
        onChange={event=>{setPassword(event.target.value);setSecretReady(true);}} />}
      {needsSecret && <Button disabled={busy} onClick={()=>{setPassword('');setSecretReady(true);}}>Use empty native sandbox password</Button>}
      <TextField fullWidth label="Confirm reviewed sandbox port" value={confirmation} disabled={busy} onChange={event=>setConfirmation(event.target.value)} />
      <Button disabled={busy || review.state!=='reviewed' || confirmation!==String(review.sandbox.port) || needsSecret && !secretReady} onClick={()=> {
        const request={job_id:review.job_id,review_digest:review.review_digest,confirmed:true,
          ...(needsSecret ? {sandbox_secret:{password}} : {})};
        setPassword('');setSecretReady(false);
        run('start',request,value=>{setReceipt(value);setReview(current=>({...current,state:value.state}));setObserved(null);});
      }}>Confirm and start native sandbox operation</Button>
    </Box>}
    <Button disabled={busy} onClick={()=>loadJobs(0)}>Load native sandbox jobs</Button>
    {jobs && <>
      <Table size="small" aria-label="Native sandbox jobs"><TableHead><TableRow>{['Job','Method','Port','State','Inspect'].map(value=><TableCell key={value}>{value}</TableCell>)}</TableRow></TableHead><TableBody>
        {jobs.jobs.map(row=><TableRow key={row.job_id}><TableCell>{row.job_id}</TableCell><TableCell>{row.options.operation}</TableCell><TableCell>{row.sandbox.port}</TableCell><TableCell>{row.state}</TableCell><TableCell><Button disabled={busy} onClick={()=>run('status',{job_id:row.job_id},value=>{setReceipt(value);setObserved(null);})}>Inspect sandbox job {row.job_id}</Button></TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={jobs.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={jobs.offset/25} onPageChange={(_event,next)=>loadJobs(next*25)} />
    </>}
    {receipt && <Box>
      <Alert severity={receipt.native_operation_outcome==='unknown' ? 'warning' : 'info'}>Native sandbox job {receipt.job_id}: {receipt.state}. Original native outcome: {receipt.native_operation_outcome}. SQL readiness is unverified.</Alert>
      {receipt.native_error && <Alert severity="error">Native sandbox error {receipt.native_error.code ?? ''}: {receipt.native_error.message}</Alert>}
      {receipt.target_state_acknowledged_at && <Alert severity="info">Observed sandbox state acknowledged. The original uncertain outcome is unchanged.</Alert>}
      <Button disabled={busy} onClick={()=>run('status',{job_id:receipt.job_id},setReceipt)}>Refresh native sandbox receipt</Button>
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed' && !(receipt.state==='unknown' && receipt.durable_tool && receipt.native_process_termination_confirmed!==true)} onClick={()=>run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel native sandbox utility</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={()=>run('reconcile',{job_id:receipt.job_id},value=>{setReceipt(value);setObserved(value);})}>Observe current sandbox state</Button>
      {receipt.state==='unknown' && observed?.observation_digest && <>
        <TextField fullWidth label="Confirm uncertain sandbox port" value={confirmation} onChange={event=>setConfirmation(event.target.value)} />
        <Button disabled={busy || confirmation!==String(receipt.sandbox.port) || receipt.native_process_termination_confirmed!==true || !receipt.reconciliation?.state?.process?.qualified}
          onClick={()=>run('acknowledge',{job_id:receipt.job_id,observation_digest:observed.observation_digest,sandbox_confirmation:confirmation},setReceipt)}>Acknowledge observed sandbox state</Button>
      </>}
      <Box component="pre" aria-label="Native sandbox receipt" sx={{whiteSpace:'pre-wrap',maxHeight:450,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box>
    </Box>}
  </Box>;
}
MySQLSandboxes.propTypes={post:PropTypes.func.isRequired};
