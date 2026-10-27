import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';

const active=state => ['dispatching','active','cancel_requested'].includes(state);
const polling=receipt => active(receipt?.state) || receipt?.logical_stream_artifact?.state==='sealing';
const defaults=() => ({slot:'',start_lsn:'0/0',end_lsn:'',plugin_options:[],status_interval_seconds:10,fsync_interval_seconds:1,timeout_seconds:null});
export default function PostgresqlLogicalStream({post,databaseTargetId,endpointUrl}) {
  const [target,setTarget]=useState(databaseTargetId || ''),[targets,setTargets]=useState([]),[options,setOptions]=useState(defaults);
  const [receipt,setReceipt]=useState(null),[catalog,setCatalog]=useState(null),[offset,setOffset]=useState(0),[preview,setPreview]=useState(null),[offsets,setOffsets]=useState(['0']);
  const [confirmed,setConfirmed]=useState(false),[stop,setStop]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [replicationOnly,setReplicationOnly]=useState(false),[password,setPassword]=useState('');
  const [transport,setTransport]=useState(null),[hostKey,setHostKey]=useState(''),[sshSecret,setSSHSecret]=useState('');
  const serial=useRef(0),downloads=useRef([]);
  useEffect(() => {
    serial.current++;setTarget(databaseTargetId || '');setTargets([]);setOptions(defaults());setReceipt(null);setCatalog(null);setOffset(0);setPreview(null);setOffsets(['0']);setConfirmed(false);setStop(false);setBusy(false);setError('');
    setReplicationOnly(false);setPassword('');setTransport(null);setHostKey('');setSSHSecret('');
    return () => {serial.current++;downloads.current.splice(0).forEach(close => close());};
  },[post,databaseTargetId]);
  const call=(action,request) => post({action:'postgresql_continuity_'+action,request});
  const perform=async (action,request,accept) => {
    const token=serial.current;setBusy(true);setError('');
    const replication=action==='review' && replicationOnly || action==='start' && receipt?.source?.admission_interface==='logical-replication';
    const access={...(password ? {password} : {}),...(transport?.ssh ? {ssh_host_key:hostKey,
      ...(sshSecret ? {[transport.ssh.authentication==='private_key' ? 'ssh_private_key_password' : 'ssh_password']:sshSecret} : {})} : {})};
    if(replication && action==='start'){setPassword('');setSSHSecret('');}
    try {const result=await call(action,replication ? {...request,replication_access:access} : request);if(token===serial.current)accept(result);}
    catch(failure) {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===serial.current)setBusy(false);}
  };
  useEffect(() => {
    if(!receipt?.job_id || !polling(receipt))return undefined;
    let alive=true,timer;
    const poll=async () => {
      try {const result=await call('status',{job_id:receipt.job_id});if(!alive)return;setReceipt(result);if(polling(result))timer=setTimeout(poll,700);}
      catch(failure) {if(alive)setError(failure.response?.data?.errormsg || failure.message);}
    };
    timer=setTimeout(poll,400);return () => {alive=false;clearTimeout(timer);};
  },[post,receipt?.job_id,receipt?.state,receipt?.logical_stream_artifact?.state]);
  useEffect(() => {setPreview(null);setOffsets(['0']);setConfirmed(false);setStop(false);},[receipt?.job_id,receipt?.state]);
  const edit=(name,value) => {setOptions(current => ({...current,[name]:value}));setReceipt(current => current?.state==='reviewed' ? null : current);setConfirmed(false);};
  const load=value => perform('list',{offset:value,limit:25},result => {setCatalog(result);setOffset(value);});
  const page=(value,stack) => perform('logical_stream_preview',{job_id:receipt.job_id,offset:value,limit:4096},result => {setPreview(result);setOffsets(stack);});
  const download=() => {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{job_id:receipt.job_id},{action:'postgresql_continuity_logical_stream_download',prefix:'postgresql-stream',title:'Native PostgreSQL logical stream output'}));}
    catch(failure) {setError(failure.message);}
  };
  return <Box component="details" sx={{my:1}}><summary>PostgreSQL logical replication streams</summary>
    <Alert severity="info">Runs an independent native receiver for an existing permanent logical slot. Native feedback consumes the slot. Closing this viewer does not stop it. Automatic reconnect and replay are disabled. Captured files use native payload newline delimiters; they do not prove complete transactions or applied replication.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <FormControlLabel label="Use registered logical replication database without SQL admission" control={<Checkbox
      checked={replicationOnly} disabled={busy || Boolean(databaseTargetId) || active(receipt?.state)} onChange={event => {
        serial.current++;setReplicationOnly(event.target.checked);setReceipt(null);setPreview(null);setConfirmed(false);setPassword('');setTransport(null);setHostKey('');setSSHSecret('');
      }} />} />
    {replicationOnly && <Box sx={{my:1}}>
      <Alert severity="info">Uses the saved registration database and native principal through logical replication. The SQL slot catalog is unobserved. Review the exact slot name; native admission may refuse it. Passwords are private, used again before start and omitted from receipts.</Alert>
      <TextField disabled={busy || active(receipt?.state)} size="small" type="password" autoComplete="off" label="Logical replication principal password" value={password} onChange={event => setPassword(event.target.value)} />
      <Button disabled={busy || active(receipt?.state)} onClick={() => {
        setTransport(null);setHostKey('');setSSHSecret('');setReceipt(current => current?.state==='reviewed' ? null : current);
        perform('transport',{probe_ssh:true},value => {setTransport(value);setHostKey(value.ssh_peer?.openssh_key || '');});
      }}>Inspect logical replication SSH transport</Button>
      {transport?.ssh===null && <Alert severity="info">This registration uses a direct database transport.</Alert>}
      {transport?.ssh && <Box>
        <Alert severity="info">SSH peer: {transport.ssh.username}@{transport.ssh.host}:{transport.ssh.port}. Observed host key: {transport.ssh_peer?.fingerprint}. Each connection requires the expected public host key.</Alert>
        <TextField disabled={busy || active(receipt?.state)} fullWidth size="small" label="Logical replication expected SSH public host key" value={hostKey} onChange={event => {setHostKey(event.target.value);setReceipt(current => current?.state==='reviewed' ? null : current);}} />
        <TextField disabled={busy || active(receipt?.state)} size="small" type="password" autoComplete="off" label={transport.ssh.authentication==='private_key' ? 'Logical replication SSH private-key passphrase' : 'Logical replication SSH password'} value={sshSecret} onChange={event => setSSHSecret(event.target.value)} />
      </Box>}
    </Box>}
    <Button disabled={busy || replicationOnly} onClick={() => perform('slot_databases',{},result => setTargets(result.databases || result.targets || []))}>Load logical stream databases</Button>
    <TextField select size="small" label="Logical stream database" value={target} disabled={busy || replicationOnly || Boolean(databaseTargetId) || active(receipt?.state)} onChange={event => {serial.current++;setTarget(event.target.value);setReceipt(null);setPreview(null);setConfirmed(false);setStop(false);}}>
      {target && !targets.some(item => item.target_id===target) && <MenuItem value={target}>{target}</MenuItem>}
      {targets.map(item => <MenuItem key={item.target_id} value={item.target_id}>{item.display_name || item.name || item.target_id}</MenuItem>)}
    </TextField>
    {['slot','start_lsn','end_lsn'].map(name => <TextField key={name} size="small" label={'Logical receiver '+name.replaceAll('_',' ')} value={options[name]} disabled={busy || active(receipt?.state)} onChange={event => edit(name,event.target.value)} />)}
    {['status_interval_seconds','fsync_interval_seconds','timeout_seconds'].map(name => <TextField key={name} type="number" size="small" label={'Logical receiver '+name.replaceAll('_',' ')} value={options[name] ?? ''} disabled={busy || active(receipt?.state)} onChange={event => edit(name,event.target.value==='' ? null : Number(event.target.value))} />)}
    {options.plugin_options.map((pair,index) => <Box key={index} sx={{display:'flex',gap:1,my:1}}>
      {['name','value'].map(name => <TextField key={name} multiline size="small" label={'Logical receiver option '+(index+1)+' '+name} value={pair[name]} disabled={busy || active(receipt?.state)} onChange={event => edit('plugin_options',options.plugin_options.map((entry,position) => position===index ? {...entry,[name]:event.target.value} : entry))} />)}
      <Button disabled={busy || active(receipt?.state)} onClick={() => edit('plugin_options',options.plugin_options.filter((_entry,position) => position!==index))}>Remove logical receiver option {index+1}</Button>
    </Box>)}
    <Button disabled={busy || active(receipt?.state) || options.plugin_options.length>=128} onClick={() => edit('plugin_options',[...options.plugin_options,{name:'',value:''}])}>Add ordered logical receiver option</Button>
    <Button disabled={busy || active(receipt?.state) || !replicationOnly && !target || !options.slot} onClick={() => perform('review',{operation:'logical_stream_capture',database_target_id:replicationOnly ? 'registered-replication-database' : target,options},setReceipt)}>Review logical replication stream</Button>
    <Button disabled={busy} onClick={() => load(0)}>Load logical stream receipts</Button>
    {catalog && <Box>
      {catalog.jobs.filter(item => item.operation==='logical_stream_capture').map(item => <Button key={item.job_id} disabled={busy} onClick={() => perform('status',{job_id:item.job_id},setReceipt)}>Inspect logical stream {item.job_id}</Button>)}
      <Button disabled={busy || !offset} onClick={() => load(Math.max(0,offset-25))}>Previous logical stream receipt page</Button>
      <Button disabled={busy || !catalog.more} onClick={() => load(offset+25)}>Next logical stream receipt page</Button>
    </Box>}
    {receipt && <Box>
      <Alert severity="info">Native logical stream {receipt.job_id}: {receipt.state}. Native utility returned: {String(Boolean(receipt.native_receiver_returned))}. Remote finality is not inferred.</Alert>
      {receipt.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
      {receipt.error_reason && <Alert severity="warning">{receipt.error_reason}</Alert>}
      {receipt.state==='reviewed' && <>
        <FormControlLabel label="Confirm native logical stream consumption" control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={busy || !confirmed} onClick={() => perform('start',{job_id:receipt.job_id,review_digest:receipt.review_digest,confirmed:true},setReceipt)}>Start reviewed logical stream</Button>
      </>}
      {active(receipt.state) && <>
        <FormControlLabel label="Stop this native logical receiver" control={<Checkbox checked={stop} disabled={busy} onChange={event => setStop(event.target.checked)} />} />
        <Button disabled={busy || !stop} onClick={() => perform('cancel',{job_id:receipt.job_id},setReceipt)}>Stop logical replication stream</Button>
      </>}
      {!active(receipt.state) && receipt.state!=='reviewed' && <Button disabled={busy} onClick={() => perform('logical_stream_reconcile',{job_id:receipt.job_id},setReceipt)}>Seal retained logical stream bytes</Button>}
      {receipt.logical_stream_artifact?.state==='sealed' && <>
        <Alert severity="info">Sealed native output: {receipt.logical_stream_artifact.bytes} bytes. Transaction completeness is not inferred.</Alert>
        <Button disabled={busy || !endpointUrl} onClick={download}>Download native logical stream</Button>
        <Button disabled={busy} onClick={() => page('0',['0'])}>Preview native logical bytes</Button>
      </>}
      {preview && <Box><Box component="pre" aria-label="Native logical byte preview" sx={{whiteSpace:'pre-wrap',overflow:'auto',maxHeight:250}}>{JSON.stringify(preview,null,2)}</Box>
        <Button disabled={busy || offsets.length<2} onClick={() => {const previous=offsets.slice(0,-1);page(previous[previous.length-1],previous);}}>Previous native logical bytes</Button>
        <Button disabled={busy || !preview.next_offset} onClick={() => page(preview.next_offset,[...offsets,preview.next_offset])}>Next native logical bytes</Button>
      </Box>}
      <Box component="details"><summary>Native logical stream receipt</summary><Box component="pre" aria-label="Native logical stream receipt" sx={{whiteSpace:'pre-wrap',overflow:'auto',maxHeight:300}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
PostgresqlLogicalStream.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string,endpointUrl:PropTypes.string};
