import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TablePagination,TextField} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
const initial={connection:{host:'',port:22,username:'',host_key:'',authentication:'password',platform:'posix',python:'python3'},
  executable:'/usr/bin/mysqlrouter',directory:'/opt/mysql-router',user:'mysqlrouter',base_port:6446,bind_address:'127.0.0.1',
  seed:{host:'',port:3306,user:'',ssl_mode:'REQUIRED',ssl_ca:null,ssl_cert:null,ssl_key:null},
  extra_arguments:[],workspace:'/tmp/scratchrobin-router',timeout_seconds:120};

export default function MySQLRouters({post}) {
  const [options,setOptions]=useState(initial),[operation,setOperation]=useState('bootstrap'),[binding,setBinding]=useState(''),[unit,setUnit]=useState('mysqlrouter.service'),[disconnect,setDisconnect]=useState(false);
  const [argumentsText,setArgumentsText]=useState('');
  const [password,setPassword]=useState(''),[key,setKey]=useState(''),[phrase,setPhrase]=useState(''),[separate,setSeparate]=useState(false),[bootstrapPassword,setBootstrapPassword]=useState('');
  const [peer,setPeer]=useState(null),[review,setReview]=useState(null),[confirmed,setConfirmed]=useState(false),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0);
  const clearSecrets=()=>{setPassword('');setKey('');setPhrase('');setBootstrapPassword('');};
  useEffect(()=>{generation.current++;setReview(null);setReceipt(null);setPeer(null);setJobs(null);setConfirmed(false);setBusy(false);setError('');clearSecrets();return()=>{generation.current++;};},[post]);
  const reset=()=>{setReview(null);setConfirmed(false);};
  const change=(name,value)=>{setOptions(current=>({...current,[name]:value}));reset();};
  const connection=(name,value)=>{setOptions(current=>({...current,connection:{...current.connection,[name]:value}}));setPeer(null);reset();};
  const seed=(name,value)=>{setOptions(current=>({...current,seed:{...current.seed,[name]:value}}));reset();};
  const credentials=()=>options.connection.authentication==='password' ? {password} : {private_key:key,private_key_password:phrase};
  const secret=()=>operation==='bootstrap' && separate ? {bootstrap_secret:{password:bootstrapPassword}} : {};
  const selected=()=>operation==='bootstrap' ? {...options,extra_arguments:argumentsText.split('\n').filter(Boolean)} : {...options,operation,binding_job_id:binding,service:{manager:'systemd',name:unit},disconnect_all_clients:disconnect};
  const run=async(action,request,accept)=>{
    const token=generation.current;setBusy(true);setError('');
    try {const result=await post({action:'mysql_router_'+action,request});if(token===generation.current)accept(result);}
    catch(failure){if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native Router request failed');}
    finally{if(token===generation.current)setBusy(false);}
  };
  useEffect(()=>{
    if(!ACTIVE.has(receipt?.state))return;
    let live=true,pending=false;
    const timer=setInterval(async()=>{if(pending)return;pending=true;try{const value=await post({action:'mysql_router_status',request:{job_id:receipt.job_id}});if(live)setReceipt(value);}catch(failure){if(live)setError(failure.response?.data?.errormsg || failure.message);}finally{pending=false;}},500);
    return()=>{live=false;clearInterval(timer);};
  },[post,receipt?.job_id,receipt?.state]);
  const load=offset=>run('list',{offset,limit:25},setJobs);
  const inspect=value=>{
    const {operation:_operation,binding_job_id:_binding,service,disconnect_all_clients:_disconnect,...original}=value.options;
    setOptions(original);setArgumentsText(original.extra_arguments.join('\n'));setBinding(value.job_id);setUnit(service?.name || 'mysqlrouter.service');setOperation('install_service');setDisconnect(false);
    setReceipt(value);reset();clearSecrets();
  };
  const original=receipt?.remote_receipt,observed=receipt?.reconciliation?.remote_receipt || original;
  const isBootstrap=receipt?.options?.operation===undefined || receipt?.options?.operation==='bootstrap';
  const decode=value=>{try{return new TextDecoder().decode(Uint8Array.from(atob(value || ''),character=>character.charCodeAt(0)));}catch{return 'Inspect the original encoded native output.';}};
  return <Box sx={{p:1,overflow:'auto',flex:1}}>
    <Alert severity="info">Bootstrap native MySQL Router on a separate Linux SSH host, then install and control its systemd service. Bootstrap requires a live Cluster, ClusterSet or ReplicaSet metadata seed. Original deployment and service receipts remain accessible when SQL is offline. Router startup and routed SQL readiness are separate observations.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',alignItems:'flex-start',my:1}}>
      <Button disabled={busy} onClick={()=>load(0)}>Load Router receipts</Button>
      <TextField select label="Native Router operation" value={operation} onChange={event=>{setOperation(event.target.value);setDisconnect(false);reset();}}>
        <MenuItem value="bootstrap">Bootstrap new Router deployment</MenuItem><MenuItem value="install_service">Install new Router service</MenuItem>
        {['start','stop','restart','enable','disable'].map(action=><MenuItem key={action} value={'service_'+action}>{action} Router service</MenuItem>)}
      </TextField>
      <TextField label="Router SSH host" value={options.connection.host} onChange={event=>connection('host',event.target.value)} />
      <TextField type="number" label="Router SSH port" value={options.connection.port} onChange={event=>connection('port',Number(event.target.value))} />
      <TextField label="Router SSH username" value={options.connection.username} onChange={event=>connection('username',event.target.value)} />
      <Button disabled={busy} onClick={()=>run('peer',{host:options.connection.host,port:options.connection.port},setPeer)}>Inspect Router SSH public key</Button>
      {peer && <Box><Alert severity="warning">Unauthenticated SSH peer key: {peer.fingerprint}. Confirm the expected host identity before pinning this key.</Alert><Button onClick={()=>connection('host_key',peer.openssh_key)}>Use inspected Router host key</Button></Box>}
      <TextField label="Expected Router OpenSSH host key" value={options.connection.host_key} onChange={event=>connection('host_key',event.target.value)} />
      <TextField select label="Router SSH authentication" value={options.connection.authentication} onChange={event=>{connection('authentication',event.target.value);clearSecrets();}}>
        <MenuItem value="password">Password</MenuItem><MenuItem value="private_key">Private key</MenuItem>
      </TextField>
      {options.connection.authentication==='password' ? <TextField type="password" label="Router SSH password" value={password} onChange={event=>setPassword(event.target.value)} /> : <>
        <TextField multiline minRows={2} maxRows={4} label="Router SSH private key" value={key} onChange={event=>setKey(event.target.value)} />
        <TextField type="password" label="Router SSH private-key password" value={phrase} onChange={event=>setPhrase(event.target.value)} />
      </>}
      <TextField label="Python on Router SSH host" value={options.connection.python} onChange={event=>connection('python',event.target.value)} />
      {['executable','directory','user','workspace'].map(name=><TextField key={name} label={{executable:'Native mysqlrouter executable',directory:'Native Router deployment directory',user:'Native Router operating-system user',workspace:'Private Router receipt workspace'}[name]} value={options[name]} onChange={event=>change(name,event.target.value)} />)}
      <TextField type="number" label="Router command timeout seconds" value={options.timeout_seconds} onChange={event=>change('timeout_seconds',Number(event.target.value))} />
      {operation==='bootstrap' ? <>
        <Button disabled={busy} onClick={()=>run('catalog',{},value=>{change('seed',value.suggested_seed);})}>Use registered metadata seed</Button>
        <TextField label="Router metadata seed host" value={options.seed.host} onChange={event=>seed('host',event.target.value)} />
        <TextField type="number" label="Router metadata seed port" value={options.seed.port} onChange={event=>seed('port',Number(event.target.value))} />
        <TextField label="Router bootstrap database account" value={options.seed.user} onChange={event=>seed('user',event.target.value)} />
        <TextField select label="Router metadata TLS mode" value={options.seed.ssl_mode} onChange={event=>seed('ssl_mode',event.target.value)}>{['DISABLED','PREFERRED','REQUIRED','VERIFY_CA','VERIFY_IDENTITY'].map(mode=><MenuItem key={mode} value={mode}>{mode}</MenuItem>)}</TextField>
        {['ssl_ca','ssl_cert','ssl_key'].map(name=><TextField key={name} label={{ssl_ca:'Metadata CA file on Router host',ssl_cert:'Metadata client certificate on Router host',ssl_key:'Metadata private-key file on Router host'}[name]} value={options.seed[name] || ''} onChange={event=>seed(name,event.target.value || null)} />)}
        <FormControlLabel label="Use separate bootstrap account password" control={<Checkbox checked={separate} onChange={event=>{setSeparate(event.target.checked);setBootstrapPassword('');reset();}} />} />
        {separate && <TextField type="password" label="Private bootstrap database password" value={bootstrapPassword} onChange={event=>setBootstrapPassword(event.target.value)} />}
        <TextField type="number" label="Router base port" value={options.base_port} onChange={event=>change('base_port',Number(event.target.value))} />
        <TextField label="Router bind address" value={options.bind_address} onChange={event=>change('bind_address',event.target.value)} />
        <TextField multiline minRows={2} maxRows={6} label="Additional native bootstrap arguments (one per line)" value={argumentsText} onChange={event=>{setArgumentsText(event.target.value);reset();}} />
      </> : <>
        <TextField label="Original Router deployment or service job" value={binding} onChange={event=>{setBinding(event.target.value);reset();}} />
        <TextField label="Exact Router systemd unit" value={unit} onChange={event=>{setUnit(event.target.value);reset();}} />
        {['service_stop','service_restart'].includes(operation) && <FormControlLabel label="Disconnect all routed clients" control={<Checkbox checked={disconnect} onChange={event=>{setDisconnect(event.target.checked);reset();}} />} />}
      </>}
      <Button disabled={busy} onClick={()=>run('review',{options:selected(),credentials:credentials(),...secret()},value=>{setReview(value);setConfirmed(false);})}>Review native Router request</Button>
    </Box>
    {review && <Box>
      <ul>{review.warnings.map(warning=><li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Native Router review" sx={{whiteSpace:'pre-wrap',maxHeight:280,overflow:'auto'}}>{JSON.stringify({source:review.source,source_identity_scope:review.source_identity_scope,host:review.execution_host,observation:review.remote_observation},null,2)}</Box>
      <FormControlLabel label="Authorize the exact reviewed native Router request" control={<Checkbox checked={confirmed} disabled={busy || review.state!=='reviewed'} onChange={event=>setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || !confirmed || review.state!=='reviewed'} onClick={()=>run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true,credentials:credentials(),...secret()},value=>{setReceipt(value);setReview(null);setConfirmed(false);clearSecrets();})}>Confirm native Router request</Button>
    </Box>}
    {jobs && <Box><Table size="small" aria-label="Native Router receipts"><TableHead><TableRow><TableCell>Job</TableCell><TableCell>Operation</TableCell><TableCell>State</TableCell><TableCell>Inspect</TableCell></TableRow></TableHead><TableBody>{jobs.jobs.map(job=><TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{job.options.operation || 'bootstrap'}</TableCell><TableCell>{job.state}</TableCell><TableCell><Button aria-label={'Inspect Router job '+job.job_id} onClick={()=>run('status',{job_id:job.job_id},inspect)}>Inspect</Button></TableCell></TableRow>)}</TableBody></Table><TablePagination component="div" count={jobs.total} page={Math.floor(jobs.offset/25)} rowsPerPage={25} rowsPerPageOptions={[25]} onPageChange={(_event,page)=>load(page*25)} /></Box>}
    {receipt && <Box>
      <Alert severity={receipt.state==='unknown' ? 'warning' : 'info'}>Native Router job {receipt.job_id}: {receipt.state}. Original SSH acknowledgement: {receipt.ssh_reply_observed ? 'observed' : 'unconfirmed'}. Routed SQL readiness is unconfirmed by this receipt.</Alert>
      <Button disabled={busy} onClick={()=>run('reconcile',{job_id:receipt.job_id,credentials:credentials()},setReceipt)}>Inspect original Router invocation</Button>
      {isBootstrap && <><Button disabled={busy} onClick={()=>run('cancel_original',{job_id:receipt.job_id,credentials:credentials()},setReceipt)}>Cancel original Router bootstrap</Button><Button disabled={busy || observed?.utility_observation?.cleanup_confirmed!==true} onClick={()=>run('acknowledge',{job_id:receipt.job_id,credentials:credentials()},setReceipt)}>Acknowledge ended Router bootstrap</Button></>}
      {ACTIVE.has(receipt.state) && <Button disabled={busy} onClick={()=>run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel unstarted Router request</Button>}
      {original?.result && <Box component="details"><summary>Original native Router output: exit {original.result.return_code}</summary>{['stdout','stderr'].map(name=><Box component="pre" key={name} sx={{whiteSpace:'pre-wrap'}}>{name}: {decode(original.outputs?.[name] || original.result.outputs?.[name]?.base64)}</Box>)}</Box>}
      <Box component="details"><summary>Native Router receipt and later observations</summary><Box component="pre" aria-label="Native Router receipt" sx={{whiteSpace:'pre-wrap',maxHeight:360,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
MySQLRouters.propTypes={post:PropTypes.func.isRequired};
