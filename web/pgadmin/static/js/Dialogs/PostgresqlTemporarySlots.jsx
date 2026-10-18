import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';

const running=state => ['dispatching','active','cancel_requested'].includes(state);
const pending=state => ['queued_review','reviewing','queued_catalog','querying','queued_execute','active'].includes(state);
const changes=operation => ['peek_text','get_text','peek_binary','get_binary'].includes(operation);
const defaults={slot:'',source_slot:'',plugin:'pgoutput',reserve_wal:true,two_phase:false,upto_lsn:'',upto_nchanges:100,plugin_options:[],timeout_seconds:30};

export default function PostgresqlTemporarySlots({post,databaseTargetId,endpointUrl}) {
  const [target,setTarget]=useState(databaseTargetId || ''),[targets,setTargets]=useState([]),[lifetime,setLifetime]=useState(3600);
  const [resource,setResource]=useState(null),[resources,setResources]=useState(null),[resourceOffset,setResourceOffset]=useState(0);
  const [operation,setOperation]=useState('physical_create'),[options,setOptions]=useState(defaults),[command,setCommand]=useState(null);
  const [commands,setCommands]=useState(null),[commandOffset,setCommandOffset]=useState(0),[inventory,setInventory]=useState(null),[inventoryOffset,setInventoryOffset]=useState(0);
  const [preview,setPreview]=useState(null),[previewOffsets,setPreviewOffsets]=useState(['0']),[remove,setRemove]=useState(false);
  const [confirmed,setConfirmed]=useState(false),[release,setRelease]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const serial=useRef(0),downloads=useRef([]);
  const call=(action,fields={}) => post({action:'postgresql_temporary_slots_'+action,request:{...(action==='databases' ? {} : {database_target_id:target}),...fields}});
  useEffect(() => {
    serial.current++;setTarget(databaseTargetId || '');setTargets([]);setResource(null);setResources(null);setCommand(null);setCommands(null);setInventory(null);setConfirmed(false);setRelease(false);setBusy(false);setError('');setResourceOffset(0);setCommandOffset(0);setInventoryOffset(0);
    return () => {serial.current++;downloads.current.splice(0).forEach(close => close());};
  },[post,databaseTargetId]);
  const changeTarget=value => {serial.current++;setTarget(value);setResource(null);setResources(null);setCommand(null);setCommands(null);setInventory(null);setConfirmed(false);setRelease(false);setBusy(false);setError('');setResourceOffset(0);setCommandOffset(0);setInventoryOffset(0);};
  const perform=async (action,fields={}) => {
    const token=serial.current;setBusy(true);setError('');
    try {
      const value=await call(action,fields);if(token!==serial.current)return;
      if(action==='databases')setTargets(value.databases || value.targets || []);
      else if(action==='list')setResources(value);
      else if(action==='command_list')setCommands(value);
      else if(action==='change_preview')setPreview(value);
      else if(['command_review','command_start','command_status','command_cancel','inventory','change_reconcile','change_remove'].includes(action)){setCommand(value);setConfirmed(false);setRemove(false);setPreview(null);setPreviewOffsets(['0']);}
      else {
        if(value.job_id!==resource?.job_id){setCommand(null);setCommands(null);setInventory(null);setCommandOffset(0);setInventoryOffset(0);}
        setResource(value);setConfirmed(false);setRelease(false);
      }
    } catch(failure) {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===serial.current)setBusy(false);}
  };
  useEffect(() => {
    if(!resource?.job_id || !running(resource.state))return undefined;
    let alive=true,timer;
    const poll=async () => {
      try {const value=await call('status',{job_id:resource.job_id});if(!alive)return;setResource(value);if(running(value.state))timer=setTimeout(poll,700);}
      catch(failure) {if(alive)setError(failure.response?.data?.errormsg || failure.message);}
    };
    timer=setTimeout(poll,400);return () => {alive=false;clearTimeout(timer);};
  },[post,target,resource?.job_id,resource?.state]);
  useEffect(() => {
    if(!command?.job_id || !resource?.job_id || !pending(command.state))return undefined;
    let alive=true,timer;
    const poll=async () => {
      try {
        const value=await call('command_status',{resource_id:resource.job_id,job_id:command.job_id});
        const parent=await call('status',{job_id:resource.job_id});if(!alive)return;
        if(value.catalog_returned)setInventory(value.result);
        setCommand(value);setResource(parent);if(pending(value.state))timer=setTimeout(poll,400);
      } catch(failure) {if(alive)setError(failure.response?.data?.errormsg || failure.message);}
    };
    timer=setTimeout(poll,300);return () => {alive=false;clearTimeout(timer);};
  },[post,target,resource?.job_id,command?.job_id,pending(command?.state)]);
  const open=resource?.state==='active' && resource.ready && !resource.pending_command;
  const blocked=busy || pending(command?.state);
  const edit=(name,value) => {setOptions(current => ({...current,[name]:value}));setCommand(current => current?.state==='reviewed' ? null : current);setConfirmed(false);};
  useEffect(() => {setPreview(null);setPreviewOffsets(['0']);setRemove(false);},[target,resource?.job_id,command?.job_id]);
  const download=() => {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{database_target_id:target,resource_id:resource.job_id,job_id:command.job_id},
      {action:'postgresql_temporary_slots_change_download',prefix:'postgresql-temp-changes',title:'PostgreSQL retained logical output download'}));}
    catch(failure) {setError(failure.message);}
  };
  const reviewCommand=() => {
    const fields=['slot','timeout_seconds'];
    if(operation==='physical_create')fields.push('reserve_wal');
    if(operation==='logical_create')fields.push('plugin','two_phase');
    if(operation.endsWith('_copy'))fields.push('source_slot');
    if(operation==='logical_copy')fields.push('plugin');
    if(operation==='advance')fields.push('upto_lsn');
    if(changes(operation))fields.push('upto_lsn','upto_nchanges','plugin_options');
    perform('command_review',{resource_id:resource.job_id,operation,options:Object.fromEntries(fields.map(name => [name,options[name]]))});
  };
  return <Box component="details" sx={{my:1}}><summary>PostgreSQL temporary replication slots</summary>
    <Alert severity="info">Temporary slots stay on an independently owned backend until native removal, resource release or a native SQL error. Closing this viewer or changing the database selection does not release the resource. Native errors can remove every temporary slot owned by that backend. WAL retention can consume server storage.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={() => perform('databases')}>Load temporary slot databases</Button>
    <TextField select size="small" label="Temporary slot database" value={target} disabled={busy || Boolean(databaseTargetId)} onChange={event => changeTarget(event.target.value)}>
      {target && !targets.some(item => item.target_id===target) && <MenuItem value={target}>{target}</MenuItem>}
      {targets.map(item => <MenuItem key={item.target_id} value={item.target_id}>{item.display_name || item.name || item.target_id}</MenuItem>)}
    </TextField>
    <TextField type="number" size="small" label="Temporary resource maximum seconds" value={lifetime ?? ''} disabled={busy} onChange={event => {setLifetime(event.target.value==='' ? null : Number(event.target.value));setResource(current => current?.state==='reviewed' ? null : current);setConfirmed(false);}} />
    <Button disabled={busy || !target || running(resource?.state)} onClick={() => perform('review',{options:{max_lifetime_seconds:lifetime}})}>Review temporary slot resource</Button>
    <Button disabled={busy || !target} onClick={() => perform('list',{offset:resourceOffset,limit:25})}>Load temporary slot resources</Button>
    {resources && <Box>
      <TextField select size="small" label="Retained temporary slot resource" value={resources.jobs.some(item => item.job_id===resource?.job_id) ? resource.job_id : ''} disabled={busy} onChange={event => {setCommand(null);setInventory(null);perform('status',{job_id:event.target.value});}}>{resources.jobs.map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} — {item.state}</MenuItem>)}</TextField>
      <Button disabled={busy || !resourceOffset} onClick={() => {const next=Math.max(0,resourceOffset-25);setResourceOffset(next);perform('list',{offset:next,limit:25});}}>Previous temporary resources</Button>
      <Button disabled={busy || !resources.more} onClick={() => {setResourceOffset(resourceOffset+25);perform('list',{offset:resourceOffset+25,limit:25});}}>Next temporary resources</Button>
    </Box>}
    {resource && <Box>
      <Alert severity="info">Temporary slot resource {resource.job_id}: {resource.state}. Native backend: {resource.backend_pid || 'not yet acknowledged'}.</Alert>
      {resource.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
      {resource.error_message && <Alert severity="warning">{resource.error_message}</Alert>}
      {resource.state==='reviewed' && <><FormControlLabel label="Confirm independent temporary slot resource" control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} /><Button disabled={busy || !confirmed} onClick={() => perform('start',{job_id:resource.job_id,review_digest:resource.review_digest,confirmed:true})}>Open reviewed temporary slot resource</Button></>}
      {open && <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <TextField select size="small" label="Temporary slot operation" value={operation} disabled={blocked} onChange={event => {setOperation(event.target.value);setCommand(current => current?.state==='reviewed' ? null : current);setConfirmed(false);}}>
          {[['physical_create','Create temporary physical slot'],['logical_create','Create temporary logical slot'],['physical_copy','Copy to temporary physical slot'],['logical_copy','Copy to temporary logical slot'],['advance','Advance owned temporary slot'],['drop','Drop owned temporary slot'],['peek_text','Peek temporary logical text'],['get_text','Consume temporary logical text'],['peek_binary','Peek temporary logical binary'],['get_binary','Consume temporary logical binary']].map(([value,label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
        </TextField>
        <TextField size="small" label="Exact temporary slot name" value={options.slot} disabled={blocked} onChange={event => edit('slot',event.target.value)} />
        {operation.endsWith('_copy') && <TextField size="small" label="Native source slot name" value={options.source_slot} disabled={blocked} onChange={event => edit('source_slot',event.target.value)} />}
        {['logical_create','logical_copy'].includes(operation) && <TextField size="small" label="Temporary slot output plugin" value={options.plugin} disabled={blocked} onChange={event => edit('plugin',event.target.value)} />}
        {operation==='advance' && <TextField size="small" label="Temporary slot target LSN" value={options.upto_lsn} disabled={blocked} onChange={event => edit('upto_lsn',event.target.value)} />}
        {changes(operation) && <Box>
          <Alert severity="warning">Native change counts are transaction thresholds and can return more rows. Get consumes native changes; application flush/publication failure cannot undo consumption. Uncertain gets are never replayed.</Alert>
          <TextField size="small" label="Temporary logical output up to LSN" value={options.upto_lsn} disabled={blocked} onChange={event => edit('upto_lsn',event.target.value)} />
          <TextField type="number" size="small" label="Temporary logical native transaction threshold" value={options.upto_nchanges ?? ''} disabled={blocked} onChange={event => edit('upto_nchanges',event.target.value==='' ? null : Number(event.target.value))} />
          {options.plugin_options.map((pair,index) => <Box key={index} sx={{display:'flex',gap:1,my:1}}>
            {['name','value'].map(key => <TextField key={key} multiline size="small" label={'Temporary plugin option '+(index+1)+' '+key} value={pair[key]} disabled={blocked} onChange={event => edit('plugin_options',options.plugin_options.map((value,position) => position===index ? {...value,[key]:event.target.value} : value))} />)}
            <Button disabled={blocked} onClick={() => edit('plugin_options',options.plugin_options.filter((_value,position) => position!==index))}>Remove temporary plugin option {index+1}</Button>
          </Box>)}
          <Button disabled={blocked || options.plugin_options.length>=128} onClick={() => edit('plugin_options',[...options.plugin_options,{name:'',value:''}])}>Add ordered temporary plugin option</Button>
        </Box>}
        {operation==='physical_create' && <FormControlLabel label="Reserve native WAL for temporary slot" control={<Checkbox checked={options.reserve_wal} disabled={blocked} onChange={event => edit('reserve_wal',event.target.checked)} />} />}
        {operation==='logical_create' && <FormControlLabel label="Enable native temporary two-phase decoding" control={<Checkbox checked={options.two_phase} disabled={blocked} onChange={event => edit('two_phase',event.target.checked)} />} />}
        <TextField type="number" size="small" label="Temporary slot command maximum seconds" value={options.timeout_seconds ?? ''} disabled={blocked} onChange={event => edit('timeout_seconds',event.target.value==='' ? null : Number(event.target.value))} />
        <Button disabled={blocked || !options.slot} onClick={reviewCommand}>Review temporary slot command</Button>
      </Box>}
      <Button disabled={blocked || !open} onClick={() => perform('inventory',{resource_id:resource.job_id,offset:inventoryOffset,limit:25})}>Inspect owned temporary slots</Button>
      <Button disabled={busy} onClick={() => perform('command_list',{resource_id:resource.job_id,offset:commandOffset,limit:25})}>Load temporary slot command receipts</Button>
      {inventory && <Box><Box component="pre" aria-label="Owned native temporary slots" sx={{whiteSpace:'pre-wrap',maxHeight:250,overflow:'auto'}}>{JSON.stringify(inventory,null,2)}</Box>
        <Button disabled={blocked || !open || !inventoryOffset} onClick={() => {const next=Math.max(0,inventoryOffset-25);setInventoryOffset(next);perform('inventory',{resource_id:resource.job_id,offset:next,limit:25});}}>Previous owned temporary slots</Button>
        <Button disabled={blocked || !open || !inventory.more} onClick={() => {setInventoryOffset(inventoryOffset+25);perform('inventory',{resource_id:resource.job_id,offset:inventoryOffset+25,limit:25});}}>Next owned temporary slots</Button>
      </Box>}
      {commands && <Box><TextField select size="small" label="Temporary slot command receipt" value={commands.jobs.some(item => item.job_id===command?.job_id) ? command.job_id : ''} disabled={blocked} onChange={event => perform('command_status',{resource_id:resource.job_id,job_id:event.target.value})}>{commands.jobs.map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} — {item.state}</MenuItem>)}</TextField>
        <Button disabled={busy || !commandOffset} onClick={() => {const next=Math.max(0,commandOffset-25);setCommandOffset(next);perform('command_list',{resource_id:resource.job_id,offset:next,limit:25});}}>Previous temporary commands</Button><Button disabled={busy || !commands.more} onClick={() => {setCommandOffset(commandOffset+25);perform('command_list',{resource_id:resource.job_id,offset:commandOffset+25,limit:25});}}>Next temporary commands</Button>
      </Box>}
      {command && <Box><Alert severity="info">Temporary slot command {command.job_id}: {command.state}. Native command acknowledged: {String(Boolean(command.native_command_acknowledged))}. Automatic retry is disabled.</Alert>
        {command.error_message && <Alert severity="warning">{command.error_message}</Alert>}
        {command.native_error_sqlstate && <Alert severity="warning">Native SQLSTATE: {command.native_error_sqlstate}. Inspect current owned slots separately.</Alert>}
        {command.state==='reviewed' && <><FormControlLabel label="Confirm native temporary slot command" control={<Checkbox checked={confirmed} disabled={busy || !open} onChange={event => setConfirmed(event.target.checked)} />} /><Button disabled={busy || !open || !confirmed} onClick={() => perform('command_start',{resource_id:resource.job_id,job_id:command.job_id,review_digest:command.review_digest,confirmed:true})}>Run reviewed temporary slot command</Button></>}
        {pending(command.state) && <Button disabled={busy} onClick={() => perform('command_cancel',{resource_id:resource.job_id,job_id:command.job_id})}>Cancel temporary slot command</Button>}
        {changes(command.options?.operation) && !pending(command.state) && command.state!=='reviewed' && !command.artifact_removed && <Box>
          <Button disabled={busy} onClick={() => perform('change_reconcile',{resource_id:resource.job_id,job_id:command.job_id})}>Verify retained temporary logical bytes</Button>
          {command.change_artifact && <>
            <Alert severity="info">Native logical capture: {command.change_artifact.state}. Native SQL acknowledged: {String(Boolean(command.native_sql_acknowledged))}.</Alert>
            <Button disabled={busy || !endpointUrl} onClick={download}>Download temporary logical capture</Button>
            <Button disabled={busy} onClick={() => {setPreviewOffsets(['0']);perform('change_preview',{resource_id:resource.job_id,job_id:command.job_id,offset:'0',limit:25});}}>Preview temporary logical records</Button>
            <FormControlLabel label="Remove this temporary logical capture; retain receipt" control={<Checkbox checked={remove} disabled={busy} onChange={event => setRemove(event.target.checked)} />} />
            <Button disabled={busy || !remove} onClick={() => perform('change_remove',{resource_id:resource.job_id,job_id:command.job_id,confirmation:command.job_id})}>Remove temporary logical capture</Button>
          </>}
          {preview && <Box><Box component="pre" aria-label="Temporary logical output preview" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify(preview,null,2)}</Box>
            <Button disabled={busy || previewOffsets.length<2} onClick={() => {const next=previewOffsets.slice(0,-1);setPreviewOffsets(next);perform('change_preview',{resource_id:resource.job_id,job_id:command.job_id,offset:next[next.length-1],limit:25});}}>Previous temporary logical records</Button>
            <Button disabled={busy || !preview.next_offset} onClick={() => {setPreviewOffsets([...previewOffsets,preview.next_offset]);perform('change_preview',{resource_id:resource.job_id,job_id:command.job_id,offset:preview.next_offset,limit:25});}}>Next temporary logical records</Button>
          </Box>}
        </Box>}
        <Box component="details"><summary>Native temporary slot command receipt</summary><Box component="pre" aria-label="Native temporary slot command receipt" sx={{whiteSpace:'pre-wrap',maxHeight:250,overflow:'auto'}}>{JSON.stringify(command,null,2)}</Box></Box>
      </Box>}
      {running(resource.state) && <><FormControlLabel label="Release this backend and all its temporary slots" control={<Checkbox checked={release} disabled={busy} onChange={event => setRelease(event.target.checked)} />} /><Button disabled={busy || !release} onClick={() => perform('release',{job_id:resource.job_id,confirmation:resource.job_id})}>Release temporary slot resource</Button></>}
      {resource.worker_io_closed && resource.backend_pid && <Button disabled={busy} onClick={() => perform('reconcile',{job_id:resource.job_id})}>Verify native temporary slot cleanup</Button>}
      {resource.native_owner_connection_close_returned && <Alert severity="info">Local connection close returned. Original backend termination observed: {String(Boolean(resource.backend_cleanup_observation?.original_backend_termination_observed))}. Native temporary-slot cleanup observed: {String(Boolean(resource.backend_cleanup_observation?.temporary_slot_cleanup_observed))}.</Alert>}
      <Box component="details"><summary>Native temporary slot resource receipt</summary><Box component="pre" aria-label="Native temporary slot resource receipt" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify(resource,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
PostgresqlTemporarySlots.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string,endpointUrl:PropTypes.string};
