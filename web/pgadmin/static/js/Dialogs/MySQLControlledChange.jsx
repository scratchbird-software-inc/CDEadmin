import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, MenuItem, TextField, Typography} from '@mui/material';

export function MySQLAlterPolicy({value, onChange, disabled, post, databaseTargetId}) {
  const [replicas,setReplicas]=useState([]),[next,setNext]=useState(null),[error,setError]=useState('');
  useEffect(() => {setReplicas([]);setNext(null);setError('');},[databaseTargetId]);
  const selected=value || {method:'native',algorithm:'INPLACE',lock:'NONE',lock_wait_seconds:5,timeout_seconds:3600};
  const change=fields => onChange({...selected,...fields});
  return <Box sx={{display:'flex',flexWrap:'wrap',gap:1,my:1}}>
    <TextField select size="small" label="Table change execution" value={value ? value.method : 'locked'} disabled={disabled}
      onChange={event => onChange(event.target.value==='locked' ? null : event.target.value==='native' ?
        {...selected,method:'native',algorithm:'INPLACE',lock:'NONE',replicas:[]} : {...selected,method:'pt-online-schema-change',algorithm:'COPY',lock:'NONE',replicas:[]})}>
      <MenuItem value="locked">Existing table-lock workflow</MenuItem><MenuItem value="native">Controlled native ALTER</MenuItem>
      <MenuItem value="pt-online-schema-change">Percona online copy</MenuItem>
    </TextField>
    {value && <>
      <TextField select size="small" label="Native ALTER algorithm" value={selected.algorithm} disabled={disabled || selected.method!=='native'}
        onChange={event => change({algorithm:event.target.value,lock:event.target.value==='INSTANT' ? 'DEFAULT' : selected.lock})}>
        {['INSTANT','INPLACE','COPY'].map(option => <MenuItem key={option} value={option}>{option}</MenuItem>)}
      </TextField>
      <TextField select size="small" label="Native ALTER lock" value={selected.lock} disabled={disabled || selected.algorithm==='INSTANT' || selected.method!=='native'}
        onChange={event => change({lock:event.target.value})}>
        {['DEFAULT','NONE','SHARED','EXCLUSIVE'].map(option => <MenuItem key={option} value={option}>{option}</MenuItem>)}
      </TextField>
      <TextField size="small" label="Metadata lock wait seconds" type="number" value={selected.lock_wait_seconds} disabled={disabled}
        onChange={event => change({lock_wait_seconds:Number(event.target.value)})} />
      <TextField size="small" label="Controlled ALTER maximum seconds" type="number" value={selected.timeout_seconds} disabled={disabled}
        onChange={event => change({timeout_seconds:Number(event.target.value)})} />
      {selected.method==='pt-online-schema-change' && <Box sx={{width:'100%'}}>
        <Button disabled={disabled || !post || !databaseTargetId} onClick={async () => {
          try {
            const result=await post({action:'mysql_online_ddl_replicas',request:{database_target_id:databaseTargetId,offset:next || 0}});
            setReplicas(current => [...current,...result.rows.filter(row => !current.some(old => old.endpoint_id===row.endpoint_id))]);setNext(result.next_offset);setError('');
          } catch(failure) {setError(failure.response?.data?.errormsg || failure.message);}
        }}>{next===null ? 'Discover replica registrations' : 'More replica registrations'}</Button>
        {error && <Alert severity="error">{error}</Alert>}
        <TextField select size="small" label="Registered replica channels" value={(selected.replicas || []).map(item => item.endpoint_id)} disabled={disabled}
          SelectProps={{multiple:true}} onChange={event => change({replicas:event.target.value.map(id => (selected.replicas || []).find(item => item.endpoint_id===id) ||
            {endpoint_id:id,channel:'',max_lag_seconds:1})})}>
          {replicas.map(item => <MenuItem key={item.endpoint_id} value={item.endpoint_id}>{item.label}</MenuItem>)}
        </TextField>
        {(selected.replicas || []).map(item => <Box key={item.endpoint_id} sx={{display:'flex',gap:1,my:1}}>
          <TextField size="small" label={`Replica ${item.endpoint_id} channel (blank for default)`} value={item.channel} disabled={disabled}
            onChange={event => change({replicas:selected.replicas.map(row => row===item ? {...item,channel:event.target.value} : row)})} />
          <TextField size="small" type="number" label={`Replica ${item.endpoint_id} maximum lag seconds`} value={item.max_lag_seconds} disabled={disabled}
            onChange={event => change({replicas:selected.replicas.map(row => row===item ? {...item,max_lag_seconds:Number(event.target.value)} : row)})} />
        </Box>)}
      </Box>}
    </>}
  </Box>;
}
MySQLAlterPolicy.propTypes={value:PropTypes.object,onChange:PropTypes.func.isRequired,disabled:PropTypes.bool,post:PropTypes.func,databaseTargetId:PropTypes.string};

export default function MySQLControlledChange({post,databaseTargetId,review,confirmed,onReceipt}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[observation,setObservation]=useState(null);
  const refs=useRef({post,onReceipt});refs.current={post,onReceipt};
  const generation=useRef(0);
  const job=review?.controlled_job;
  const active=Boolean(job && !review.controlled_terminal && ['starting','running'].includes(job.state));
  const api=(action,request={}) => refs.current.post({action:`mysql_online_ddl_${action}`,
    request:{database_target_id:databaseTargetId,review_id:review.review_id,...request}});
  useEffect(() => {generation.current++;setError('');setObservation(null);setBusy(false);return () => {generation.current++;};},[databaseTargetId,review?.review_id]);
  useEffect(() => {
    if(!active)return undefined;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const result=await api('status');if(live)refs.current.onReceipt(result);}
      catch(failure) {if(live)setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending=false;}
    },1000);
    return () => {live=false;clearInterval(timer);};
  },[active,databaseTargetId,review?.review_id]);
  const run=async action => {
    const token=++generation.current;setBusy(true);setError('');
    try {
      const result=await api(action,action==='start' ? {review_digest:review.review_digest,confirmed} : {});
      if(token!==generation.current)return;
      if(action==='observe')setObservation(result);else refs.current.onReceipt(result);
    } catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===generation.current)setBusy(false);}
  };
  if(!review?.plan?.operations?.some(op => op.execution))return null;
  return <Box aria-label="Controlled MySQL DDN change" sx={{my:1}}>
    <Alert severity="warning">Prevent external DDL during this operation. The cooperating application lock does not fence other tools.
      Native ALGORITHM/LOCK governs DML concurrency; brief metadata locks can still block it. There is no fallback to a different algorithm.
      Cancellation or a stopped application does not establish rollback. Closing this workspace leaves the admitted job running.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {review.outcome?.error_code && <Alert severity="warning">Native MySQL error {review.outcome.error_code}; SQLSTATE {review.outcome.sqlstate || 'unavailable'}.
      The original outcome remains {review.state}. Observe current native state before preparing another change.</Alert>}
    {review.plan.operations[0].copy_admission && <Alert severity="warning">
      Online copy uses Percona Toolkit {review.plan.operations[0].copy_admission.tool.version} on the application host.
      It creates a table copy and synchronization triggers, rebuilds referring foreign keys, preserves existing triggers and drops its old table on completion.
      Foreign-key names can change. {review.plan.operations[0].copy_admission.lag_coverage}
      Load thresholds: pause above 25 running threads; abort above 50. Cutover requires the separate action below.
    </Alert>}
    <Button disabled={busy || review.state!=='reviewed' || Boolean(job) || !confirmed} onClick={() => run('start')}>Start controlled ALTER</Button>
    <Button disabled={busy || !active} onClick={() => run('cancel')}>Cancel controlled ALTER</Button>
    <Button disabled={busy || !active || job?.copy_stage!=='cutover-waiting' || job.replica_policy_ready===false} onClick={() => run('cutover')}>Allow reviewed copy cutover</Button>
    <Button disabled={busy} onClick={() => run('status')}>Read controlled ALTER status</Button>
    <Button disabled={busy || active} onClick={() => run('observe')}>Observe current native table</Button>
    {job && <>
      <Typography>Controlled job: {job.state}. Native outcome: {review.state}. {job.cancel_requested ? 'Cancellation requested; native outcome remains separate.' : ''}</Typography>
      <Typography>Execution host: {job.execution_host?.kind} / {job.execution_host?.platform}. Native server owns DDL execution and commits.</Typography>
      {job.replica_observations?.map((item,index) => <Typography key={index}>Replica {item.endpoint_id}, channel {item.channel || '(default)'}:
        {item.within_policy ? ' within reviewed lag policy' : ' paused / unconfirmed'}. Lag seconds: {item.seconds_behind_source ?? 'unknown'}.
        IO: {item.io_running || 'unknown'}; SQL: {item.sql_running || 'unknown'}.</Typography>)}
      <Box sx={{maxHeight:280,overflow:'auto'}}>{job.events?.map((event,index) => <Typography key={index}>{event.stage}: {JSON.stringify(event)}</Typography>)}</Box>
      {job.utility_result && <TextField label="Native online-copy process output" multiline minRows={3} maxRows={12}
        value={`Exit: ${job.utility_result.return_code}\n${job.utility_result.stdout}\n${job.utility_result.stderr}`}
        slotProps={{input:{readOnly:true}}} sx={{width:'100%'}} />}
    </>}
    {observation && <>
      <Alert severity="info">Current native observation; original outcome remains unchanged. Owned thread still present: {String(observation.observed_thread_still_present)}.</Alert>
      <TextField label="Controlled ALTER current native definition" multiline minRows={3} maxRows={12} value={observation.native_definition || ''}
        slotProps={{input:{readOnly:true}}} sx={{width:'100%'}} />
      {observation.artifacts && <TextField label="Native online-copy cleanup observation" multiline minRows={3} maxRows={12}
        value={JSON.stringify({artifacts:observation.artifacts,process:observation.utility_process,
          utility_native_thread_still_present:observation.utility_native_thread_still_present},null,2)}
        slotProps={{input:{readOnly:true}}} sx={{width:'100%'}} />}
    </>}
  </Box>;
}
MySQLControlledChange.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string,review:PropTypes.object,
  confirmed:PropTypes.bool,onReceipt:PropTypes.func.isRequired};
