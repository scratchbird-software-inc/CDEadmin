import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,Table,TableBody,TableCell,TableHead,TablePagination,TableRow,TextField} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
function example(operation,member) {
  return JSON.stringify(operation.arguments.map(value=> {
    const kind=value.replace(/\?$/,'');
    if(kind==='options')return {};
    if(kind==='instance')return member ? {server_id:member.server_id} : null;
    if(kind==='value')return null;
    if(kind==='option')return 'tag:label';
    return value.endsWith('?') ? null : 'name';
  }),null,2);
}

export default function MySQLTopologies({post}) {
  const [catalog,setCatalog]=useState(null),[operationId,setOperationId]=useState('instance.check_configuration');
  const [argumentsText,setArgumentsText]=useState('[{}]'),[contextName,setContextName]=useState(''),[contextOptions,setContextOptions]=useState('{}');
  const [advertised,setAdvertised]=useState(false),[timeout,setTimeout]=useState('3600');
  const [seed,setSeed]=useState(null),[confirmation,setConfirmation]=useState(''),[members,setMembers]=useState(null),[member,setMember]=useState(null);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[observation,setObservation]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const generation=useRef(0);
  const operation=catalog?.operations.find(value=>value.id===operationId);
  useEffect(()=> {
    generation.current++;setCatalog(null);setSeed(null);setMembers(null);setMember(null);setReview(null);setReceipt(null);setJobs(null);setObservation(null);setBusy(false);setError('');
    setOperationId('instance.check_configuration');setArgumentsText('[{}]');setContextName('');setContextOptions('{}');setAdvertised(false);setTimeout('3600');setConfirmation('');
    return ()=>{generation.current++;};
  },[post]);
  const run=async(action,request,accept)=> {
    const token=generation.current;setBusy(true);setError('');
    try {const result=await post({action:'mysql_topology_'+action,request});if(token===generation.current)accept(result);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native topology request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(()=> {
    if(!ACTIVE.has(receipt?.state))return;
    const token=generation.current;let pending=false,live=true;
    const timer=setInterval(async()=> {
      if(pending)return;pending=true;
      try {const result=await post({action:'mysql_topology_status',request:{job_id:receipt.job_id}});if(live && token===generation.current)setReceipt(result);}
      catch(failure) {if(live && token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native topology status unavailable');}
      finally {pending=false;}
    },1500);
    return ()=>{live=false;clearInterval(timer);};
  },[receipt?.job_id,receipt?.state,post]);
  const selected=()=>({operation:operationId,arguments_json:argumentsText,context_name:contextName,
    context_options_json:contextOptions,use_advertised_endpoint:advertised,
    timeout_seconds:timeout.trim()==='null' ? null : Number(timeout),
    target_confirmation:operation?.read_only ? seed?.identity.server_uuid : confirmation});
  const loadJobs=offset=>run('list',{offset,limit:25},setJobs);
  const loadMembers=offset=>run('members',{offset,limit:25},setMembers);
  const invalidate=()=>setReview(null);
  return <Box sx={{p:2}}>
    <Alert severity="info">Manage native MySQL instance configuration, InnoDB Cluster, ReplicaSet and ClusterSet operations. Native utility replies and current topology observations are separate from workload readiness. Closing this view does not cancel a job.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={()=>run('catalog',{},setCatalog)}>Load native topology methods</Button>
    <Button disabled={busy} onClick={()=>run('inspect',{},value=>{setSeed(value);setReview(null);})}>Inspect topology seed</Button>
    {seed && <Box component="pre" aria-label="Native topology seed" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify(seed,null,2)}</Box>}
    {catalog && <TextField select fullWidth label="Native topology method" value={operationId} disabled={busy} onChange={event=> {
      const value=catalog.operations.find(item=>item.id===event.target.value);setOperationId(value.id);setArgumentsText(example(value,member));setContextOptions('{}');setReview(null);
    }}>{catalog.operations.map(value=><MenuItem key={value.id} value={value.id}>{value.context}.{value.method}</MenuItem>)}</TextField>}
    {operation && <Alert severity="info">Native arguments: {operation.arguments.join(', ') || 'none'}. Instance arguments use registered references such as {'{"server_id":4}'}. Optional arguments have a ? suffix.</Alert>}
    <Button disabled={busy} onClick={()=>loadMembers(0)}>Load registered topology instances</Button>
    {members && <>
      <Table size="small" aria-label="Registered topology instances"><TableHead><TableRow><TableCell>ID</TableCell><TableCell>Instance</TableCell><TableCell>Use</TableCell></TableRow></TableHead><TableBody>
        {members.instances.map(row=><TableRow key={row.server_id}><TableCell>{row.server_id}</TableCell><TableCell>{row.name}</TableCell><TableCell><Button disabled={busy} onClick={()=>{setMember(row);setReview(null);}}>Select topology instance {row.name}</Button></TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={members.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={members.offset/25} onPageChange={(_event,next)=>loadMembers(next*25)} />
    </>}
    {member && <Button disabled={busy || !operation} onClick={()=>{setArgumentsText(example(operation,member));setReview(null);}}>Reset arguments for {member.name}</Button>}
    <TextField fullWidth multiline minRows={5} label="Native topology arguments (JSON array)" value={argumentsText} disabled={busy}
      helperText="Argument text is sent intact; integer digits are preserved. Configure account credentials and host option files through their dedicated workflows."
      onChange={event=>{setArgumentsText(event.target.value);invalidate();}} />
    <TextField fullWidth label="Native cluster context name (optional)" value={contextName} disabled={busy} onChange={event=>{setContextName(event.target.value);invalidate();}} />
    <TextField fullWidth label="Native Cluster context options (JSON object)" value={contextOptions} disabled={busy || operation?.context!=='cluster'} onChange={event=>{setContextOptions(event.target.value);invalidate();}} />
    <FormControlLabel control={<Checkbox checked={advertised} disabled={busy} onChange={event=>{setAdvertised(event.target.checked);invalidate();}} />} label="Use server-advertised addresses for native utilities" />
    <TextField fullWidth label="Native topology runtime seconds or null" value={timeout} disabled={busy} onChange={event=>{setTimeout(event.target.value);invalidate();}} />
    {operation?.read_only ? <Button disabled={busy || !seed} onClick={()=>run('inspect_native',{options:selected()},value=>{setReceipt(value);setReview(null);setObservation(null);})}>Run native topology inspection</Button> : <>
      <TextField fullWidth label="Confirm topology seed UUID" value={confirmation} disabled={busy} onChange={event=>{setConfirmation(event.target.value);invalidate();}} />
      <Button disabled={busy || !seed || confirmation!==seed.identity.server_uuid || !operation} onClick={()=>run('review',{options:selected()},value=>{setReview(value);setReceipt(null);setObservation(null);})}>Review native topology change</Button>
    </>}
    {review && <Box>
      {review.warnings.map(warning=><Alert severity="warning" key={warning}>{warning}</Alert>)}
      <Box component="pre" aria-label="Native topology review" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify({target:review.target,selected_instances:review.selected_instances,options:review.options,execution_host:review.execution_host},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={()=>run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value=>{setReceipt(value);setReview(current=>({...current,state:value.state}));})}>Confirm and start native topology change</Button>
    </Box>}
    <Button disabled={busy} onClick={()=>loadJobs(0)}>Load native topology jobs</Button>
    {jobs && <>
      <Table size="small" aria-label="Native topology jobs"><TableHead><TableRow>{['Job','Method','State','Inspect'].map(value=><TableCell key={value}>{value}</TableCell>)}</TableRow></TableHead><TableBody>
        {jobs.jobs.map(row=><TableRow key={row.job_id}><TableCell>{row.job_id}</TableCell><TableCell>{row.options.operation}</TableCell><TableCell>{row.state}</TableCell><TableCell><Button disabled={busy} onClick={()=>run('status',{job_id:row.job_id},value=>{setReceipt(value);setObservation(null);})}>Inspect topology job {row.job_id}</Button></TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={jobs.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={jobs.offset/25} onPageChange={(_event,next)=>loadJobs(next*25)} />
    </>}
    {receipt && <Box>
      <Alert severity={receipt.native_operation_outcome==='unknown' ? 'warning' : 'info'}>Native topology job {receipt.job_id}: {receipt.state}. Original operation outcome: {receipt.native_operation_outcome}. Workload readiness is unverified.</Alert>
      {receipt.native_error && <Alert severity="error">Native topology error {receipt.native_error.code ?? ''}: {receipt.native_error.message}</Alert>}
      {receipt.result?.control?.result_json && <Box component="pre" aria-label="Native topology result JSON" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{receipt.result.control.result_json}</Box>}
      {receipt.result?.native_json_observation?.native_shell_json_signed_limit && <Alert severity="warning">Stored tags contain unsigned64 integers. MySQL Shell 9.7 options decoding can clamp these to its signed integer limit. The separate SQL tag observation preserves the stored values; the original Shell reply above is unchanged.</Alert>}
      {receipt.result?.native_json_observation && <Box component="pre" aria-label="Native topology stored tag JSON" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify(receipt.result.native_json_observation.tags,null,2)}</Box>}
      {receipt.result?.control?.observation_error && <Alert severity="warning">The native operation returned, but its later result observation failed: {receipt.result.control.observation_error.message}</Alert>}
      {receipt.result?.output_text && <Box component="details"><summary>Native utility messages</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{receipt.result.output_text}</Box></Box>}
      <Button disabled={busy} onClick={()=>run('status',{job_id:receipt.job_id},setReceipt)}>Refresh topology receipt</Button>
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed' && !(receipt.state==='unknown' && receipt.durable_tool && receipt.native_process_termination_confirmed!==true)} onClick={()=>run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel native topology operation</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={()=>run('reconcile',{job_id:receipt.job_id},value=>{setReceipt(value);setObservation(value.observation_digest);})}>Observe current topology target</Button>
      {receipt.state==='unknown' && receipt.remote_database_mutation && observation && <>
        <TextField fullWidth label="Confirm uncertain topology target UUID" value={confirmation} onChange={event=>setConfirmation(event.target.value)} />
        <Button disabled={busy || confirmation!==receipt.target.server_uuid} onClick={()=>run('acknowledge',{job_id:receipt.job_id,target_confirmation:confirmation,observation_digest:observation},setReceipt)}>Acknowledge observed topology target</Button>
      </>}
      <Box component="details"><summary>Native topology observations</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
MySQLTopologies.propTypes={post:PropTypes.func.isRequired};
