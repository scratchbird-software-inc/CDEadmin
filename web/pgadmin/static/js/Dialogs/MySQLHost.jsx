import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TablePagination,TextField} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
export default function MySQLHost({post}) {
  const [host,setHost]=useState(''),[port,setPort]=useState(22),[user,setUser]=useState('');
  const [hostKey,setHostKey]=useState(''),[authentication,setAuthentication]=useState('password'),[platform,setPlatform]=useState('posix'),[python,setPython]=useState('python3');
  const [password,setPassword]=useState(''),[key,setKey]=useState(''),[phrase,setPhrase]=useState('');
  const [executable,setExecutable]=useState('mysqld'),[configuration,setConfiguration]=useState(''),[workspace,setWorkspace]=useState('/tmp/scratchrobin-native-host'),[timeout,setTimeoutValue]=useState(60);
  const [operation,setOperation]=useState('validate_config'),[serviceName,setServiceName]=useState('mysql.service'),[bindingJob,setBindingJob]=useState(''),[disconnect,setDisconnect]=useState(false);
  const [catalog,setCatalog]=useState(null),[peer,setPeer]=useState(null),[review,setReview]=useState(null),[confirmed,setConfirmed]=useState(false),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null);
  const [initialDirectory,setInitialDirectory]=useState('/var/lib/mysql-new'),[initialUser,setInitialUser]=useState('mysql'),[secureInitialization,setSecureInitialization]=useState(true);
  const [replacement,setReplacement]=useState(null),[proposedText,setProposedText]=useState(''),[replacementName,setReplacementName]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const generation=useRef(0);
  useEffect(() => {generation.current++;setCatalog(null);setPeer(null);setReview(null);setReceipt(null);setJobs(null);setConfirmed(false);setError('');setBusy(false);setPassword('');setKey('');setPhrase('');setReplacement(null);setProposedText('');setReplacementName('');return () => {generation.current++;};},[post]);
  const change=setter => event => {setter(event.target.value);setReview(null);setConfirmed(false);};
  const credentials=() => authentication==='password' ? {password} : {private_key:key,private_key_password:phrase};
  const selected=() => ({connection:{host,port,username:user,host_key:hostKey,authentication,platform,python},executable,configuration_file:configuration || null,workspace,timeout_seconds:timeout,
    ...(operation==='validate_config' ? {} : operation==='deploy_config' ? {operation,configuration_replacement:replacement} : operation==='initialize_data' ? {operation,initialization:{datadir:initialDirectory,user:initialUser,secure:secureInitialization}} : {operation,service:{manager:'systemd',name:serviceName},binding_job_id:bindingJob || null,disconnect_all_clients:disconnect,...(operation==='install_service' ? {service_installation:{user:initialUser}} : {})})});
  const propose=bytes=>{let binary='';for(let index=0;index<bytes.length;index+=16384)binary+=String.fromCharCode(...bytes.subarray(index,index+16384));setReplacement({base64:btoa(binary)});setReview(null);setConfirmed(false);};
  const upload=async file=>{if(!file)return;const token=generation.current;try{const bytes=new Uint8Array(await file.arrayBuffer());if(token!==generation.current)return;propose(bytes);setReplacementName(file.name);try{setProposedText(new TextDecoder('utf-8',{fatal:true}).decode(bytes));}catch{setProposedText('');}}catch(failure){if(token===generation.current)setError(failure.message);}};
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:'mysql_host_'+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native database-host request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(() => {
    if(!ACTIVE.has(receipt?.state))return;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const value=await post({action:'mysql_host_status',request:{job_id:receipt.job_id}});if(live)setReceipt(value);}
      catch(failure) {if(live)setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending=false;}
    },500);
    return () => {live=false;clearInterval(timer);};
  },[post,receipt?.job_id,receipt?.state]);
  const load=offset => run('list',{offset,limit:25},setJobs);
  const inspect=value => {
    setReceipt(value);setReview(null);setConfirmed(false);setReplacement(null);setProposedText('');setReplacementName('');setPassword('');setKey('');setPhrase('');
    const connection=value.options.connection;
    setHost(connection.host);setPort(connection.port);setUser(connection.username);setHostKey(connection.host_key);
    setAuthentication(connection.authentication);setPlatform(connection.platform);setPython(connection.python);
    setExecutable(value.options.executable || 'mysqld');setConfiguration(value.options.configuration_file || '');
    setWorkspace(value.options.workspace || '');setTimeoutValue(value.options.timeout_seconds || 60);
    setOperation(value.options.operation || 'validate_config');setServiceName(value.options.service?.name || 'mysql.service');
    setBindingJob(value.options.service || value.options.operation==='initialize_data' ? value.job_id : '');setDisconnect(false);
    if(value.options.service_installation)setInitialUser(value.options.service_installation.user);
    if(value.options.initialization){setInitialDirectory(value.options.initialization.datadir);setInitialUser(value.options.initialization.user);setSecureInitialization(value.options.initialization.secure);}
  };
  const observed=receipt?.reconciliation?.remote_receipt || receipt?.remote_receipt;
  const configurationAfter=observed?.configuration_after_process;
  const decode=value => {try{return new TextDecoder().decode(Uint8Array.from(atob(value || ''),char => char.charCodeAt(0)));}catch{return 'Inspect the original encoded native output in the receipt.';}};
  return <Box sx={{p:1,overflow:'auto',flex:1}}>
    <Alert severity="info">Manage native MySQL configuration, initialize a new Linux data directory, or control a Linux systemd service on the selected SSH host. Initialization uses SSH host authority before a SQL endpoint exists; existing-instance operations also bind the native UUID, hostname and data directory. Python 3.9 or later is required on that host. Native host receipts do not establish SQL readiness or upgrade acceptance.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <Button disabled={busy} onClick={() => run('catalog',{},setCatalog)}>Inspect native database-host binding</Button>
      <Button disabled={busy} onClick={() => load(0)}>Load native host receipts</Button>
      <TextField size="small" label="Database SSH host" value={host} onChange={event => {setHost(event.target.value);setPeer(null);setReview(null);setConfirmed(false);}} />
      <TextField size="small" type="number" label="SSH port" value={port} onChange={event => {setPort(Number(event.target.value));setPeer(null);setReview(null);setConfirmed(false);}} />
      <TextField size="small" label="SSH username" value={user} onChange={change(setUser)} />
      <Button disabled={busy} onClick={() => run('peer',{host,port},setPeer)}>Inspect SSH public key</Button>
    </Box>
    {catalog && <Box component="details"><summary>Observed native database host</summary><Box component="pre" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(catalog,null,2)}</Box></Box>}
    {peer && <Box><Alert severity="warning">Unauthenticated SSH peer key: {peer.fingerprint}. Confirm it against the expected host identity before pinning it. No credential or remote command was sent.</Alert>
      <Button disabled={busy || peer.host!==host || peer.port!==port} onClick={() => {setHostKey(peer.openssh_key);setReview(null);setConfirmed(false);}}>Use inspected SSH public key as expected key</Button></Box>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <TextField size="small" label="Expected OpenSSH public host key" value={hostKey} sx={{minWidth:360}} onChange={change(setHostKey)} />
      <TextField select size="small" label="SSH authentication" value={authentication} onChange={event => {setAuthentication(event.target.value);setPassword('');setKey('');setPhrase('');setReview(null);setConfirmed(false);}}>
        <MenuItem value="password">Password</MenuItem><MenuItem value="private_key">Private key</MenuItem>
      </TextField>
      {authentication==='password' ? <TextField size="small" type="password" label="SSH password" value={password} onChange={event => setPassword(event.target.value)} /> : <>
        <TextField size="small" multiline minRows={2} maxRows={4} label="SSH private key" value={key} onChange={event => setKey(event.target.value)} />
        <Button component="label">Load SSH private key<input hidden type="file" onChange={event => {const file=event.target.files?.[0];if(file)file.text().then(setKey).catch(failure => setError(failure.message));}} /></Button>
        <TextField size="small" type="password" label="SSH private-key password" value={phrase} onChange={event => setPhrase(event.target.value)} />
      </>}
      <TextField select size="small" label="Native SSH platform" value={platform} onChange={event => {const value=event.target.value;setPlatform(value);setPython(value==='windows' ? 'python.exe' : 'python3');setWorkspace(value==='windows' ? 'C:\\ScratchRobin\\mysql-host' : '/tmp/scratchrobin-native-host');setOperation('validate_config');setReview(null);setConfirmed(false);}}>
        <MenuItem value="posix">POSIX</MenuItem><MenuItem value="windows">Native Windows PowerShell</MenuItem>
      </TextField>
      <TextField size="small" label="Python on database SSH host" value={python} onChange={change(setPython)} />
      <TextField size="small" label="Native mysqld executable" value={executable} onChange={change(setExecutable)} />
      <TextField size="small" label="Native configuration file (blank: no defaults)" value={configuration} onChange={change(setConfiguration)} />
      <TextField size="small" label="Private workspace on SSH host" value={workspace} onChange={change(setWorkspace)} />
      <TextField size="small" type="number" label="Native diagnostic timeout seconds" value={timeout} onChange={event => {setTimeoutValue(Number(event.target.value));setReview(null);setConfirmed(false);}} />
      <TextField select size="small" label="Native host operation" value={operation} onChange={change(setOperation)}>
        <MenuItem value="validate_config">Check configuration</MenuItem>
        {platform==='posix' && <MenuItem value="deploy_config">Install option file (Linux)</MenuItem>}
        {platform==='posix' && <MenuItem value="initialize_data">Initialize MySQL data directory (Linux)</MenuItem>}
        {platform==='posix' && <MenuItem value="install_service">Install new MySQL service (Linux systemd)</MenuItem>}
        {platform==='posix' && ['start','stop','restart','enable','disable'].map(action => <MenuItem key={action} value={'service_'+action}>{action} MySQL service (Linux systemd)</MenuItem>)}
      </TextField>
      {(operation.startsWith('service_') || operation==='install_service') && <>
        <TextField size="small" label="Exact systemd MySQL unit" value={serviceName} onChange={change(setServiceName)} />
        <TextField size="small" label="Prior verified service job (for offline SQL)" helperText="For installation, select a completed initialization receipt. Service controls use a verified service receipt." value={bindingJob} onChange={change(setBindingJob)} />
        {operation==='install_service' && <><TextField size="small" label="Native service user option" value={initialUser} onChange={change(setInitialUser)} /><Alert severity="info">Create a new native unit after MySQL and systemd validation. Existing unit files are preserved. Installation rereads systemd definitions without starting or enabling MySQL. Select a completed initialization receipt for a new instance before SQL is available.</Alert></>}
        {['service_stop','service_restart'].includes(operation) && <FormControlLabel label="Disconnect all native service clients" control={<Checkbox checked={disconnect} onChange={event => {setDisconnect(event.target.checked);setReview(null);setConfirmed(false);}} />} />}
      </>}
      {operation==='initialize_data' && <Box sx={{width:'100%'}}>
        <Alert severity="warning">Initialize a new or native-empty MySQL data directory on this SSH host. A current SQL connection is not required. Native secure initialization produces an expired temporary root password in the private native output. Failure or cancellation can leave partial files. No SQL readiness or service installation is implied.</Alert>
        <TextField label="Native initialization data directory" value={initialDirectory} onChange={change(setInitialDirectory)} />
        <TextField label="Native initialization user option" value={initialUser} onChange={change(setInitialUser)} />
        <FormControlLabel label="Secure native initialization with temporary root password" control={<Checkbox checked={secureInitialization} onChange={event=>{setSecureInitialization(event.target.checked);setReview(null);setConfirmed(false);}} />} />
      </Box>}
      {operation==='deploy_config' && <Box sx={{width:'100%'}}>
        <Alert severity="info">Install reviewed option-file bytes after native validation. This preserves the existing file ownership and permissions and does not restart MySQL. The SSH account needs authority to replace the file and create the private Linux validation view.</Alert>
        <Button component="label" disabled={busy}>Load replacement native option file<input hidden type="file" aria-label="Replacement native option file" onChange={event=>upload(event.target.files?.[0])} /></Button>
        {replacementName && <Box>Selected file: {replacementName}. Uploaded bytes are retained until you edit the text.</Box>}
        <TextField multiline minRows={6} fullWidth label="Proposed native option-file text (UTF-8)" value={proposedText} disabled={busy} onChange={event=>{const value=event.target.value;setProposedText(value);setReplacementName('');propose(new TextEncoder().encode(value));}} />
      </Box>}
      <Button disabled={busy} onClick={() => run('review',{options:selected(),credentials:credentials()},value => {setReview(value);setConfirmed(false);})}>{operation==='validate_config' ? 'Review native host configuration check' : operation==='deploy_config' ? 'Review native option-file installation' : operation==='initialize_data' ? 'Review native data-directory initialization' : 'Review native host service action'}</Button>
    </Box>
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Native host diagnostic review" sx={{whiteSpace:'pre-wrap',maxHeight:260,overflow:'auto'}}>{JSON.stringify({source:review.source,source_identity_scope:review.source_identity_scope,execution_host:review.execution_host,observation:review.remote_observation},null,2)}</Box>
      <FormControlLabel label={operation==='validate_config' ? 'Authorize the reviewed native mysqld configuration check on this database SSH host' : operation==='deploy_config' ? 'Authorize the reviewed option-file installation on this database SSH host' : operation==='initialize_data' ? 'Authorize the reviewed native data-directory initialization on this SSH host' : 'Authorize the reviewed native MySQL service action on this database SSH host'} control={<Checkbox disabled={busy || review.state!=='reviewed'} checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || !confirmed || review.state!=='reviewed'} onClick={() => run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true,credentials:credentials()},value => {setReceipt(value);setReview(current => ({...current,state:value.state}));setConfirmed(false);})}>{operation==='validate_config' ? 'Confirm native host configuration check' : operation==='deploy_config' ? 'Confirm native option-file installation' : operation==='initialize_data' ? 'Confirm native data-directory initialization' : 'Confirm native host service action'}</Button>
    </Box>}
    {jobs && <><Table size="small" aria-label="Native host diagnostic receipts"><TableHead><TableRow>{['Job','Host','State','Receipt'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
      {jobs.jobs.map(job => <TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{job.execution_host.hostname}</TableCell><TableCell>{job.state}</TableCell><TableCell><Button disabled={busy} aria-label={'Inspect native host job '+job.job_id} onClick={() => run('status',{job_id:job.job_id},inspect)}>Inspect</Button></TableCell></TableRow>)}
    </TableBody></Table><TablePagination component="div" count={jobs.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={jobs.offset/25} onPageChange={(_event,next) => load(next*25)} /></>}
    {receipt && <Box>
      <Alert severity={receipt.state==='native_process_returned' && observed?.result?.return_code===0 ? 'success' : 'warning'}>Native host job {receipt.job_id}: {receipt.state}. {receipt.state==='unknown' && 'The original SSH reply is unconfirmed. Reconciliation never repeats the native command.'}</Alert>
      {receipt.options?.operation==='initialize_data' && <Box>
        <Alert severity="info">Native initialization result: {observed?.initialization_result?.native_initialization_returned===true ? 'returned successfully' : 'unconfirmed or unsuccessful'}. Native process termination: {(observed?.initialization_reconciliation?.process_termination_confirmed ?? observed?.initialization_result?.process_termination_confirmed)===true ? 'confirmed' : 'unconfirmed'}. Original SSH acknowledgement and later observations remain separate.</Alert>
        <Button disabled={busy} onClick={()=>run('cancel_initialization',{job_id:receipt.job_id,credentials:credentials()},setReceipt)}>Cancel original native initializer</Button>
        <Button disabled={busy || observed?.initialization_reconciliation?.process_termination_confirmed!==true} onClick={()=>run('acknowledge_initialization',{job_id:receipt.job_id,credentials:credentials()},setReceipt)}>Acknowledge ended initialization and release its directory claim</Button>
      </Box>}
      {observed?.service_request && <Alert severity="info">Service-manager completion applies to the selected unit. SQL readiness is unconfirmed; reconnect and verify the MySQL endpoint when the service is available. Do not repeat an uncertain request.</Alert>}
      {observed?.service_installation_result && <Alert severity={observed.service_installation_result.installed ? 'info' : 'warning'}>Native service unit installation: {observed.service_installation_result.installed ? 'file installed' : 'not installed'}. Installation does not start or enable MySQL. Inspect the native validation and manager results separately; use this receipt as the prior service association for reviewed startup.</Alert>}
      {observed?.service_after_process?.observed===false && <Alert severity="warning">The service-manager result is retained. The later native unit/process observation is unavailable.</Alert>}
      {configurationAfter && (configurationAfter.observed!==true || configurationAfter.matches_review!==true) &&
        <Alert severity="warning">{configurationAfter.observed===true ?
          'Configuration files changed after review. The native process result is retained; review the current configuration before relying on that result.' :
          'Configuration files could not be observed after execution. The native process result is retained; the current configuration is unconfirmed.'}</Alert>}
      <Button disabled={busy} onClick={() => run('status',{job_id:receipt.job_id},setReceipt)}>Refresh native host receipt</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state) || receipt.state==='reviewed'} onClick={() => run('reconcile',{job_id:receipt.job_id,credentials:credentials()},setReceipt)}>Reconcile native host receipt</Button>
      <Button disabled={busy || receipt.state!=='reviewed'} onClick={() => run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel unstarted native host check</Button>
      {observed?.result && <Box component="details"><summary>Native diagnostic output: exit {observed.result.return_code}</summary>{['stdout','stderr'].map(name => <Box component="pre" key={name} sx={{whiteSpace:'pre-wrap',maxHeight:240,overflow:'auto'}}>{name}: {decode(observed.result.outputs?.[name]?.base64)}</Box>)}</Box>}
      <Box component="details"><summary>Native host observations and reconciliation</summary><Box component="pre" aria-label="Native host diagnostic receipt" sx={{whiteSpace:'pre-wrap',maxHeight:360,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
MySQLHost.propTypes={post:PropTypes.func.isRequired};
