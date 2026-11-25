import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,MenuItem,TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';
import GridNavigation from '../cdeadmin_ui/data/GridNavigation';
import {NumberField, Stack} from '../cdeadmin_ui';
import StructuredPayloadCard, {KeyValueJsonEditor} from '../cdeadmin_ui/modules/StructuredPayloadCard';

function parseJsonObject(text) {
  try {
    const parsed=JSON.parse(text);
    return parsed && typeof parsed==='object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

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
  const parsedNativeOpts=parseJsonObject(nativeOptions);
  const updateSandboxOpt=(patch)=> {
    const base=parsedNativeOpts ? {...parsedNativeOpts} : {};
    Object.entries(patch).forEach(([k,v])=> {
      if(v===undefined || v==='')delete base[k];
      else base[k]=v;
    });
    setNativeOptions(JSON.stringify(base,null,2));
    invalidate();
  };
  return <Box sx={{p:2}}>
    <FormReference formKey="mysql-sandboxes" />
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
      {operation==='deploy' && <Box sx={{my:1.5,p:1.5,border:'1px solid var(--sr-border, rgba(128,128,128,0.22))',borderRadius:1.5}}>
        <Stack gap={1.25}>
          <Stack direction="row" gap={1.5} style={{flexWrap:'wrap'}}>
            <NumberField label="X Protocol port (portx)" disabled={busy || !parsedNativeOpts} value={parsedNativeOpts?.portx ?? ''} onChange={e=>updateSandboxOpt({portx:e.target.value ? Number(e.target.value) : undefined})} style={{maxWidth:200}} />
            <TextField size="small" label="Allow root from host pattern" disabled={busy || !parsedNativeOpts} value={parsedNativeOpts?.allowRootFrom ?? ''} onChange={e=>updateSandboxOpt({allowRootFrom:e.target.value || undefined})} sx={{minWidth:220,flex:1}} />
            <TextField size="small" label="mysqldOptions (comma-separated option=value)" disabled={busy || !parsedNativeOpts} value={Array.isArray(parsedNativeOpts?.mysqldOptions) ? parsedNativeOpts.mysqldOptions.join(', ') : ''} onChange={e=>{const list=e.target.value.split(',').map(s=>s.trim()).filter(Boolean);updateSandboxOpt({mysqldOptions:list.length ? list : undefined});}} sx={{minWidth:260,flex:1}} />
          </Stack>
          <KeyValueJsonEditor title="Deployment option parameters" disabled={busy} valueJson={nativeOptions} onChangeJson={nextJson=>{setNativeOptions(nextJson);invalidate();}} />
          <Box component="details">
            <summary style={{cursor:'pointer',fontSize:12,opacity:0.8}}>Advanced JSON overrides</summary>
            <Box sx={{mt:1}}>
              <TextField fullWidth multiline minRows={4} label="Native sandbox deployment options (JSON object)" value={nativeOptions} disabled={busy}
                helperText="Native mysqldOptions retains ordered option=value strings. portx defaults to ten times the classic port. Passwords are supplied separately at dispatch."
                onChange={event=>{setNativeOptions(event.target.value);invalidate();}} />
            </Box>
          </Box>
        </Stack>
      </Box>}
      <TextField fullWidth label="Sandbox native runtime seconds or null" value={timeout} disabled={busy} onChange={event=>{setTimeout(event.target.value);invalidate();}} />
      <Button disabled={busy} onClick={()=>prepare('inspect')}>Inspect local sandbox</Button>
      <Button disabled={busy} onClick={()=>prepare('review')}>Review native sandbox operation</Button>
    </>}
    {observed && !observed.observation_digest && <Box sx={{my:1}}><StructuredPayloadCard title="Local sandbox inspection" value={observed} rawAriaLabel="Local sandbox inspection" /></Box>}
    {review && <Box sx={{my:1}}>
      {review.warnings.map(value=><Alert key={value} severity="warning">{value}</Alert>)}
      <StructuredPayloadCard
        title="Reviewed sandbox operation"
        value={{sandbox:review.sandbox,options:review.options,execution_host:review.execution_host,program:review.program}}
        rawAriaLabel="Native sandbox review"
      />
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
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Native sandbox jobs"
        rows={(jobs.jobs || []).map(row => ({
          id: row.job_id,
          job_id: row.job_id,
          operation: row.options.operation,
          port: row.sandbox.port,
          state: row.state,
          _raw: row,
        }))}
        columns={[
          {key: 'job_id', name: 'Job'},
          {key: 'operation', name: 'Method'},
          {key: 'port', name: 'Port'},
          {key: 'state', name: 'State'},
          {
            key: '_inspect',
            name: 'Inspect',
            render: (_val, r) => <Button disabled={busy} onClick={()=>run('status',{job_id:r._raw.job_id},value=>{setReceipt(value);setObserved(null);})}>Inspect sandbox job {r._raw.job_id}</Button>,
          },
        ]}
        compact
        searchable={false}
        exportable={false}
      />
      <GridNavigation
        busy={busy}
        page={Math.floor((jobs.offset || 0) / 25)}
        pages={Math.max(1, Math.ceil((jobs.total || 0) / 25))}
        endKnown
        canNext={(jobs.offset || 0) + 25 < (jobs.total || 0)}
        onFirst={() => loadJobs(0)}
        onPrevious={() => loadJobs(Math.max(0, (jobs.offset || 0) - 25))}
        onNext={() => loadJobs((jobs.offset || 0) + 25)}
        onLast={() => loadJobs(Math.max(0, (Math.ceil((jobs.total || 0) / 25) - 1) * 25))}
      />
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
      <Box sx={{my:1}}>
        <StructuredPayloadCard
          title="Sandbox job receipt"
          value={{
            job_id:receipt.job_id,
            state:receipt.state,
            native_operation_outcome:receipt.native_operation_outcome,
            sandbox:receipt.sandbox,
            options:receipt.options,
          }}
          rawText={JSON.stringify(receipt,null,2)}
          rawAriaLabel="Native sandbox receipt"
        />
      </Box>
    </Box>}
  </Box>;
}
MySQLSandboxes.propTypes={post:PropTypes.func.isRequired};
