import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TablePagination,TextField} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
export default function MySQLHost({post}) {
  const [host,setHost]=useState(''),[port,setPort]=useState(22),[user,setUser]=useState('');
  const [hostKey,setHostKey]=useState(''),[authentication,setAuthentication]=useState('password'),[platform,setPlatform]=useState('posix'),[python,setPython]=useState('python3');
  const [password,setPassword]=useState(''),[key,setKey]=useState(''),[phrase,setPhrase]=useState('');
  const [executable,setExecutable]=useState('mysqld'),[configuration,setConfiguration]=useState(''),[workspace,setWorkspace]=useState('/tmp/scratchrobin-native-host'),[timeout,setTimeoutValue]=useState(60);
  const [catalog,setCatalog]=useState(null),[peer,setPeer]=useState(null),[review,setReview]=useState(null),[confirmed,setConfirmed]=useState(false),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const generation=useRef(0);
  useEffect(() => {generation.current++;setCatalog(null);setPeer(null);setReview(null);setReceipt(null);setJobs(null);setConfirmed(false);setError('');setBusy(false);setPassword('');setKey('');setPhrase('');return () => {generation.current++;};},[post]);
  const change=setter => event => {setter(event.target.value);setReview(null);setConfirmed(false);};
  const credentials=() => authentication==='password' ? {password} : {private_key:key,private_key_password:phrase};
  const selected=() => ({connection:{host,port,username:user,host_key:hostKey,authentication,platform,python},executable,configuration_file:configuration || null,workspace,timeout_seconds:timeout});
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
    setReceipt(value);setReview(null);setConfirmed(false);setPassword('');setKey('');setPhrase('');
    const connection=value.options.connection;
    setHost(connection.host);setPort(connection.port);setUser(connection.username);setHostKey(connection.host_key);
    setAuthentication(connection.authentication);setPlatform(connection.platform);setPython(connection.python);
  };
  const observed=receipt?.reconciliation?.remote_receipt || receipt?.remote_receipt;
  const configurationAfter=observed?.configuration_after_process;
  const decode=value => {try{return new TextDecoder().decode(Uint8Array.from(atob(value || ''),char => char.charCodeAt(0)));}catch{return 'Inspect the original encoded native output in the receipt.';}};
  return <Box sx={{p:1,overflow:'auto',flex:1}}>
    <Alert severity="info">Run native MySQL configuration diagnostics on the database server through an explicitly selected SSH host. The native UUID, hostname and data directory must match; an SSH bastion is not assumed to be the database host. Python 3.9 or later is required on that host. This action checks configuration and does not start, stop or upgrade the server.</Alert>
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
      <TextField select size="small" label="Native SSH platform" value={platform} onChange={event => {const value=event.target.value;setPlatform(value);setPython(value==='windows' ? 'python.exe' : 'python3');setWorkspace(value==='windows' ? 'C:\\ScratchRobin\\mysql-host' : '/tmp/scratchrobin-native-host');setReview(null);setConfirmed(false);}}>
        <MenuItem value="posix">POSIX</MenuItem><MenuItem value="windows">Native Windows PowerShell</MenuItem>
      </TextField>
      <TextField size="small" label="Python on database SSH host" value={python} onChange={change(setPython)} />
      <TextField size="small" label="Native mysqld executable" value={executable} onChange={change(setExecutable)} />
      <TextField size="small" label="Native configuration file (blank: no defaults)" value={configuration} onChange={change(setConfiguration)} />
      <TextField size="small" label="Private workspace on SSH host" value={workspace} onChange={change(setWorkspace)} />
      <TextField size="small" type="number" label="Native diagnostic timeout seconds" value={timeout} onChange={event => {setTimeoutValue(Number(event.target.value));setReview(null);setConfirmed(false);}} />
      <Button disabled={busy} onClick={() => run('review',{options:selected(),credentials:credentials()},value => {setReview(value);setConfirmed(false);})}>Review native host configuration check</Button>
    </Box>
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Native host diagnostic review" sx={{whiteSpace:'pre-wrap',maxHeight:260,overflow:'auto'}}>{JSON.stringify({source:review.source,execution_host:review.execution_host,observation:review.remote_observation},null,2)}</Box>
      <FormControlLabel label="Authorize the reviewed native mysqld configuration check on this database SSH host" control={<Checkbox disabled={busy || review.state!=='reviewed'} checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || !confirmed || review.state!=='reviewed'} onClick={() => run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true,credentials:credentials()},value => {setReceipt(value);setReview(current => ({...current,state:value.state}));setConfirmed(false);})}>Confirm native host configuration check</Button>
    </Box>}
    {jobs && <><Table size="small" aria-label="Native host diagnostic receipts"><TableHead><TableRow>{['Job','Host','State','Receipt'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
      {jobs.jobs.map(job => <TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{job.execution_host.hostname}</TableCell><TableCell>{job.state}</TableCell><TableCell><Button disabled={busy} aria-label={'Inspect native host job '+job.job_id} onClick={() => run('status',{job_id:job.job_id},inspect)}>Inspect</Button></TableCell></TableRow>)}
    </TableBody></Table><TablePagination component="div" count={jobs.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={jobs.offset/25} onPageChange={(_event,next) => load(next*25)} /></>}
    {receipt && <Box>
      <Alert severity={receipt.state==='native_process_returned' && observed?.result?.return_code===0 ? 'success' : 'warning'}>Native host job {receipt.job_id}: {receipt.state}. {receipt.state==='unknown' && 'The original SSH reply is unconfirmed. Reconciliation never repeats the native command.'}</Alert>
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
