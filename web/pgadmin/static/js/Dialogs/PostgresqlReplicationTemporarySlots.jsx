import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

const active=state => ['dispatching','active','cancel_requested'].includes(state);
const pending=state => ['queued_review','reviewing','queued_catalog','querying','queued_execute','active'].includes(state);
const credentials={password:'',ssh_host_key:'',ssh_password:'',ssh_private_key_password:''};
const initialOptions={slot:'',plugin:'test_decoding',snapshot:'export',two_phase:false,reserve_wal:false,invalidate_snapshot:false,timeout_seconds:30};
const databaseTarget=name => 'postgresql-replication-database:'+Array.from(new TextEncoder().encode(name),byte => byte.toString(16).padStart(2,'0')).join('');

export default function PostgresqlReplicationTemporarySlots({post}) {
  const [database,setDatabase]=useState(''),[access,setAccess]=useState(credentials),[lifetime,setLifetime]=useState(3600);
  const [resource,setResource]=useState(null),[resources,setResources]=useState(null),[resourceOffset,setResourceOffset]=useState(0);
  const [command,setCommand]=useState(null),[commands,setCommands]=useState(null),[commandOffset,setCommandOffset]=useState(0);
  const [operation,setOperation]=useState('logical_create'),[options,setOptions]=useState(initialOptions);
  const [confirmed,setConfirmed]=useState(false),[release,setRelease]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const serial=useRef(0),target=database ? databaseTarget(database) : '';
  useEffect(() => {
    serial.current++;setDatabase('');setAccess(credentials);setResource(null);setResources(null);setCommand(null);setCommands(null);
    setResourceOffset(0);setCommandOffset(0);setConfirmed(false);setRelease(false);setBusy(false);setError('');
    return () => {serial.current++;};
  },[post]);
  const clear=() => {setResource(null);setResources(null);setCommand(null);setCommands(null);setResourceOffset(0);setCommandOffset(0);setConfirmed(false);setRelease(false);};
  const call=(action,fields={}) => post({action:'postgresql_replication_temporary_'+action,request:{
    ...(action!=='scope' && target ? {database_target_id:target} : {}),
    ...(['scope','review','start'].includes(action) ? {replication_access:Object.fromEntries(Object.entries(access).filter(([_key,value]) => value!==''))} : {}),...fields}});
  const perform=async (action,fields={}) => {
    const token=serial.current;setBusy(true);setError('');
    try {
      const value=await call(action,fields);if(token!==serial.current)return;
      if(action==='scope'){if(value.source.database!==database)clear();setDatabase(value.source.database);}
      else if(action==='list')setResources(value);
      else if(action==='command_list')setCommands(value);
      else if(action.startsWith('command_') || action==='inventory'){setCommand(value);setConfirmed(false);}
      else {
        if(value.source?.database && value.source.database!==database){clear();setDatabase(value.source.database);}
        if(value.job_id!==resource?.job_id){setCommand(null);setCommands(null);setCommandOffset(0);}
        setResource(value);setConfirmed(false);setRelease(false);
        if(action==='start')setAccess(credentials);
      }
    } catch(failure) {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===serial.current)setBusy(false);}
  };
  useEffect(() => {
    if(!resource?.job_id || !active(resource.state))return undefined;
    let live=true,timer;const token=serial.current;
    const poll=async () => {
      try {const value=await call('status',{job_id:resource.job_id});if(!live || token!==serial.current)return;setResource(value);if(active(value.state))timer=setTimeout(poll,700);}
      catch(failure) {if(live && token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    };
    timer=setTimeout(poll,400);return () => {live=false;clearTimeout(timer);};
  },[post,target,resource?.job_id,resource?.state]);
  useEffect(() => {
    if(!resource?.job_id || !command?.job_id || !pending(command.state))return undefined;
    let live=true,timer;const token=serial.current;
    const poll=async () => {
      try {
        const value=await call('command_status',{resource_id:resource.job_id,job_id:command.job_id});
        const parent=await call('status',{job_id:resource.job_id});if(!live || token!==serial.current)return;
        setCommand(value);setResource(parent);if(pending(value.state))timer=setTimeout(poll,400);
      } catch(failure) {if(live && token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    };
    timer=setTimeout(poll,300);return () => {live=false;clearTimeout(timer);};
  },[post,target,resource?.job_id,command?.job_id,pending(command?.state)]);
  const open=resource?.state==='active' && resource.ready && !resource.pending_command;
  const blocked=busy || pending(command?.state);
  const edit=(name,value) => {setOptions(current => ({...current,[name]:value}));setCommand(current => current?.state==='reviewed' ? null : current);setConfirmed(false);};
  const reviewCommand=() => {
    const fields=['slot','timeout_seconds','invalidate_snapshot'];
    if(operation==='physical_create')fields.push('reserve_wal');
    if(operation==='logical_create')fields.push('plugin','snapshot','two_phase');
    perform('command_review',{resource_id:resource.job_id,operation,options:Object.fromEntries(fields.map(key => [key,options[key]]))});
  };
  return <Box component="details" sx={{my:1}}><summary>Temporary replication slots and exported snapshots</summary>
    <FormReference formKey="postgresql-replication-temporary" />
    <Alert severity="info">Uses the saved registration&apos;s database and a retained native replication connection. No SQL bootstrap or catalog connection is required. Status and review preserve the last exported snapshot; another native command or backend termination invalidates it. Closing this viewer does not release the resource.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box component="details"><summary>Registered replication credentials</summary>
      <Alert severity="info">Leave credentials empty to use the saved registration. They are not stored in receipts.</Alert>
      {Object.entries({password:'Temporary replication password',ssh_host_key:'Temporary replication SSH host key',ssh_password:'Temporary replication SSH password',ssh_private_key_password:'Temporary replication SSH private key password'}).map(([key,label]) =>
        <TextField key={key} size="small" label={label} type={key==='ssh_host_key' ? 'text' : 'password'} value={access[key]} disabled={busy} onChange={event => setAccess(current => ({...current,[key]:event.target.value}))} />)}
    </Box>
    <Button disabled={busy} onClick={() => perform('scope')}>Inspect registered replication database</Button>
    <TextField size="small" label="Retained replication database name" value={database} disabled={busy} onChange={event => {serial.current++;clear();setDatabase(event.target.value);setError('');}} />
    <TextField size="small" type="number" label="Replication resource maximum seconds" value={lifetime ?? ''} disabled={busy} onChange={event => {setLifetime(event.target.value==='' ? null : Number(event.target.value));setResource(current => current?.state==='reviewed' ? null : current);setConfirmed(false);}} />
    <Button disabled={busy || active(resource?.state)} onClick={() => perform('review',{options:{max_lifetime_seconds:lifetime}})}>Review temporary replication resource</Button>
    <Button disabled={busy || !target} onClick={() => perform('list',{offset:resourceOffset,limit:25})}>Load retained replication resources</Button>
    {resources && <Box>
      <TextField select size="small" label="Retained replication resource" value={resources.jobs.some(item => item.job_id===resource?.job_id) ? resource.job_id : ''} disabled={busy} onChange={event => perform('status',{job_id:event.target.value})}>
        {resources.jobs.map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} — {item.state}</MenuItem>)}
      </TextField>
      <Button disabled={busy || !resourceOffset} onClick={() => {const next=Math.max(0,resourceOffset-25);setResourceOffset(next);perform('list',{offset:next,limit:25});}}>Previous replication resources</Button>
      <Button disabled={busy || !resources.more} onClick={() => {setResourceOffset(resourceOffset+25);perform('list',{offset:resourceOffset+25,limit:25});}}>Next replication resources</Button>
    </Box>}
    {resource && <Box>
      <Alert severity="info">Replication resource {resource.job_id}: {resource.state}. Original backend: {resource.backend_pid || 'not yet acknowledged'}. Database: {resource.source?.database}. Native slot catalog is unobserved.</Alert>
      {resource.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
      {resource.error_message && <Alert severity="warning">{resource.error_message}</Alert>}
      <Button disabled={busy} onClick={() => perform('status',{job_id:resource.job_id})}>Refresh retained replication resource</Button>
      {resource.state==='reviewed' && <><FormControlLabel label="Confirm original replication resource" control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} /><Button disabled={busy || !confirmed} onClick={() => perform('start',{job_id:resource.job_id,review_digest:resource.review_digest,confirmed:true})}>Open reviewed replication resource</Button></>}
      {open && <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <TextField select size="small" label="Retained replication command" value={operation} disabled={blocked} onChange={event => {setOperation(event.target.value);setCommand(current => current?.state==='reviewed' ? null : current);setConfirmed(false);}}>
          {[['logical_create','Create temporary logical slot'],['physical_create','Create temporary physical slot'],['drop','Drop acknowledged temporary slot']].map(([value,label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
        </TextField>
        <TextField size="small" label="Exact retained replication slot" value={options.slot} disabled={blocked} onChange={event => edit('slot',event.target.value)} />
        {operation==='logical_create' && <>
          <TextField size="small" label="Retained replication output plugin" value={options.plugin} disabled={blocked} onChange={event => edit('plugin',event.target.value)} />
          <TextField select size="small" label="Native replication snapshot" value={options.snapshot} disabled={blocked} onChange={event => edit('snapshot',event.target.value)}><MenuItem value="export">Export snapshot</MenuItem><MenuItem value="nothing">No snapshot export</MenuItem></TextField>
          <FormControlLabel label="Temporary replication two-phase decoding" control={<Checkbox checked={options.two_phase} disabled={blocked} onChange={event => edit('two_phase',event.target.checked)} />} />
        </>}
        {operation==='physical_create' && <FormControlLabel label="Reserve temporary replication WAL" control={<Checkbox checked={options.reserve_wal} disabled={blocked} onChange={event => edit('reserve_wal',event.target.checked)} />} />}
        <FormControlLabel label="Allow invalidation of the current exported snapshot" control={<Checkbox checked={options.invalidate_snapshot} disabled={blocked} onChange={event => edit('invalidate_snapshot',event.target.checked)} />} />
        <TextField size="small" type="number" label="Retained replication command maximum seconds" value={options.timeout_seconds ?? ''} disabled={blocked} onChange={event => edit('timeout_seconds',event.target.value==='' ? null : Number(event.target.value))} />
        <Button disabled={blocked || !options.slot} onClick={reviewCommand}>Review retained replication command</Button>
      </Box>}
      <Button disabled={blocked || !open} onClick={() => perform('inventory',{resource_id:resource.job_id,offset:0,limit:25})}>Read retained replication acknowledgements</Button>
      <Button disabled={busy} onClick={() => perform('command_list',{resource_id:resource.job_id,offset:commandOffset,limit:25})}>Load retained replication command receipts</Button>
      {commands && <Box><TextField select size="small" label="Retained replication command receipt" value={commands.jobs.some(item => item.job_id===command?.job_id) ? command.job_id : ''} disabled={blocked} onChange={event => perform('command_status',{resource_id:resource.job_id,job_id:event.target.value})}>{commands.jobs.map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} — {item.state}</MenuItem>)}</TextField>
        <Button disabled={busy || !commandOffset} onClick={() => {const next=Math.max(0,commandOffset-25);setCommandOffset(next);perform('command_list',{resource_id:resource.job_id,offset:next,limit:25});}}>Previous replication commands</Button><Button disabled={busy || !commands.more} onClick={() => {setCommandOffset(commandOffset+25);perform('command_list',{resource_id:resource.job_id,offset:commandOffset+25,limit:25});}}>Next replication commands</Button>
      </Box>}
      {command && <Box><Alert severity="info">Retained replication command {command.job_id}: {command.state}. Native acknowledgement: {String(Boolean(command.native_command_acknowledged))}. Automatic retry is disabled.</Alert>
        {command.error_message && <Alert severity="warning">{command.error_message}</Alert>}
        {command.native_error_sqlstate && <Alert severity="warning">Native SQLSTATE: {command.native_error_sqlstate}.</Alert>}
        {command.state==='reviewed' && <><FormControlLabel label="Confirm retained replication command" control={<Checkbox checked={confirmed} disabled={busy || !open} onChange={event => setConfirmed(event.target.checked)} />} /><Button disabled={busy || !open || !confirmed} onClick={() => perform('command_start',{resource_id:resource.job_id,job_id:command.job_id,review_digest:command.review_digest,confirmed:true})}>Run reviewed replication command</Button></>}
        {pending(command.state) && <Button disabled={busy} onClick={() => perform('command_cancel',{resource_id:resource.job_id,job_id:command.job_id})}>Cancel retained replication command</Button>}
        <Box component="pre" aria-label="Retained replication command observation" sx={{whiteSpace:'pre-wrap',maxHeight:250,overflow:'auto'}}>{JSON.stringify(command,null,2)}</Box>
      </Box>}
      {resource.latest_native_inventory && <Box component="pre" aria-label="Retained replication snapshot acknowledgement" sx={{whiteSpace:'pre-wrap',maxHeight:250,overflow:'auto'}}>{JSON.stringify(resource.latest_native_inventory,null,2)}</Box>}
      {active(resource.state) && <><FormControlLabel label="Release this replication backend and snapshot" control={<Checkbox checked={release} disabled={busy} onChange={event => setRelease(event.target.checked)} />} /><Button disabled={busy || !release} onClick={() => perform('release',{job_id:resource.job_id,confirmation:resource.job_id})}>Release retained replication resource</Button></>}
      {resource.native_owner_connection_close_returned && <Alert severity="info">Local replication connection close returned. Remote cleanup is not independently observed. An earlier exported snapshot cannot be used after its owner closes.</Alert>}
      <Box component="details"><summary>Retained replication resource receipt</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:250,overflow:'auto'}}>{JSON.stringify(resource,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
PostgresqlReplicationTemporarySlots.propTypes={post:PropTypes.func.isRequired};
