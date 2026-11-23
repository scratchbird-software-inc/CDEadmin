import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';
import GridNavigation from '../cdeadmin_ui/data/GridNavigation';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
export default function MySQLInstanceAcceptance({post,sourceServerId,backupJobId,targetUuid,targetConfirmation}) {
  const [options,setOptions]=useState('{"threads":4,"timeout_seconds":3600}'),[pause,setPause]=useState(false);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[page,setPage]=useState(null),[observation,setObservation]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const generation=useRef(0);
  useEffect(()=> {
    generation.current++;setReview(null);setReceipt(null);setPage(null);setObservation(null);setPause(false);setBusy(false);setError('');
    return ()=>{generation.current++;};
  },[post,sourceServerId,backupJobId,targetUuid,targetConfirmation]);
  const run=async(action,request,accept)=> {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:'mysql_instance_acceptance_'+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Independent dump acceptance request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(()=> {
    if(!ACTIVE.has(receipt?.state))return;
    const token=generation.current;let pending=false,live=true;
    const timer=setInterval(async()=> {
      if(pending)return;pending=true;
      try {const value=await post({action:'mysql_instance_acceptance_status',request:{job_id:receipt.job_id}});if(live && token===generation.current)setReceipt(value);}
      catch(failure) {if(live && token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Independent acceptance status unavailable');}
      finally {pending=false;}
    },1500);
    return ()=>{live=false;clearInterval(timer);};
  },[receipt?.job_id,receipt?.state,post]);
  const load=offset=>run('list',{offset,limit:25},setPage);
  return <Box component="details" sx={{my:2}}>
    <FormReference formKey="mysql-instance-acceptance" />
    <summary>Independent dump acceptance</summary>
    <Alert severity="warning">Full row counts, native checksums and native definition re-export run under a server-wide read lock and instance backup lock. Writes can pause for the entire check. Select the source backup and confirm the target UUID above. Closing this view does not cancel a job.</Alert>
    <Alert severity="info">Each exported surface has a separate result. Acceptance reads the target and creates private verification files; it issues no data, DDL, account or GTID restore. Managed physical targets retain their original recovery reference. Select the expected backup checkpoint explicitly; unexported state and production cutover remain separate.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <TextField fullWidth label="Independent dump acceptance options" value={options} disabled={busy} onChange={event=>{setOptions(event.target.value);setReview(null);}} />
    <FormControlLabel control={<Checkbox checked={pause} disabled={busy} onChange={event=>{setPause(event.target.checked);setReview(null);}} />} label="Confirm server-wide write pause for independent acceptance" />
    <Button disabled={busy || !pause || !sourceServerId || !backupJobId || !targetUuid || targetConfirmation!==targetUuid} onClick={()=> {
      try {run('review',{source_server_id:sourceServerId,backup_job_id:backupJobId,
        options:{...JSON.parse(options),target_confirmation:targetConfirmation,server_wide_write_pause_confirmed:true}},value=>{setReview(value);setReceipt(null);setObservation(null);});}
      catch(failure) {setError(failure.message);}
    }}>Review independent dump acceptance</Button>
    {review && <Box>
      {review.warnings.map(warning=><Alert severity="warning" key={warning}>{warning}</Alert>)}
      <Box component="pre" aria-label="Independent dump acceptance review" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify({target:review.target,source_backup:review.source_backup,options:review.options},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={()=>run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value=>{setReceipt(value);setReview(current=>({...current,state:value.state}));})}>Confirm and start independent acceptance</Button>
    </Box>}
    <Button disabled={busy} onClick={()=>load(0)}>Load independent acceptance jobs</Button>
    {page && <>
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Independent acceptance jobs"
        rows={(page.jobs || []).map(row => ({
          id: row.job_id,
          job_id: row.job_id,
          server_uuid: row.target.server_uuid,
          state: row.state,
          _raw: row,
        }))}
        columns={[
          {key: 'job_id', name: 'Job'},
          {key: 'server_uuid', name: 'Target'},
          {key: 'state', name: 'State'},
          {
            key: '_inspect',
            name: 'Inspect',
            render: (_val, r) => <Button disabled={busy} onClick={()=>run('status',{job_id:r._raw.job_id},value=>{setReceipt(value);setObservation(null);})}>Inspect acceptance {r._raw.job_id}</Button>,
          },
        ]}
        compact
        searchable={false}
        exportable={false}
      />
      <GridNavigation
        busy={busy}
        page={Math.floor((page.offset || 0) / 25)}
        pages={Math.max(1, Math.ceil((page.total || 0) / 25))}
        endKnown
        canNext={(page.offset || 0) + 25 < (page.total || 0)}
        onFirst={() => load(0)}
        onPrevious={() => load(Math.max(0, (page.offset || 0) - 25))}
        onNext={() => load((page.offset || 0) + 25)}
        onLast={() => load(Math.max(0, (Math.ceil((page.total || 0) / 25) - 1) * 25))}
      />
    </>}
    {receipt && <Box>
      <Alert severity={receipt.acceptance_outcome==='matched' ? 'success' : ['not_matched','unconfirmed'].includes(receipt.acceptance_outcome) ? 'warning' : 'info'}>Independent acceptance {receipt.job_id}: {receipt.state}. Recorded outcome: {receipt.acceptance_outcome}. No restore was issued.</Alert>
      {receipt.physical_recovery && <Alert severity="info">Managed physical recovery {receipt.physical_recovery.job_id}: comparison against the selected expected dump. This does not authorize production cutover.</Alert>}
      {receipt.native_error_code && <Alert severity="error">Native acceptance failure code: {receipt.native_error_code}</Alert>}
      {receipt.result && <>
        <UnifiedDataGrid
          gridRole="table"
          ariaLabel="Recorded dump acceptance surfaces"
          rows={['data','definitions','accounts','system_state'].map(key => ({
            id: key,
            surface: key,
            result: !receipt.result[key]?.requested ? 'Not exported / not checked' : receipt.result[key]?.matched===true ? 'Matched' : receipt.result[key]?.matched===false ? 'Different' : 'Unconfirmed',
          }))}
          columns={[
            {key: 'surface', name: 'Exported surface'},
            {key: 'result', name: 'Recorded result'},
          ]}
          compact
          searchable={false}
          exportable={false}
        />
        {receipt.result.server_locks_released===false && (receipt.recovery_fence_release_confirmed===true ?
          <Alert severity="info">The original unlock replies were unconfirmed. A later native observation confirmed that the private SQL session and its server locks are gone. Original check results are unchanged.</Alert> :
          <Alert severity="warning">Private server-lock cleanup is unconfirmed. Target protection remains active. Observe the acceptance target to check the original private SQL session.</Alert>)}
      </>}
      <Button disabled={busy} onClick={()=>run('status',{job_id:receipt.job_id},setReceipt)}>Refresh acceptance receipt</Button>
      {receipt.utility_observation_unavailable && receipt.native_process_termination_confirmed!==true && <Alert severity="warning">The original utility reference is unavailable. This receipt cannot confirm cleanup or cancel that client. The original outcome is unchanged.</Alert>}
      {receipt.interrupted_utility_observation && <Alert severity={receipt.native_process_termination_confirmed===true ? 'info' : 'warning'}>Interrupted utility cleanup: {receipt.native_process_termination_confirmed===true ? 'confirmed' : 'unconfirmed'}. Earlier checks are unchanged; private SQL-lock cleanup and target acknowledgement remain separate.</Alert>}
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed' && !(receipt.state==='unknown' && receipt.durable_tool && receipt.native_process_termination_confirmed!==true)} onClick={()=>run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel independent acceptance</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={()=>run('observe_utilities',{job_id:receipt.job_id},setReceipt)}>Observe original acceptance utility without SQL connection</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={()=>run('reconcile',{job_id:receipt.job_id},value=>{setReceipt(value);setObservation(value.observation_digest);})}>Observe acceptance target</Button>
      {receipt.state==='unknown' && observation && <Button disabled={busy || targetConfirmation!==receipt.target.server_uuid} onClick={()=>run('acknowledge',{job_id:receipt.job_id,target_confirmation:targetConfirmation,observation_digest:observation},setReceipt)}>Acknowledge observed acceptance target</Button>}
      <Box component="details"><summary>Independent acceptance observations</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
MySQLInstanceAcceptance.propTypes={post:PropTypes.func.isRequired,sourceServerId:PropTypes.number,backupJobId:PropTypes.string,targetUuid:PropTypes.string,targetConfirmation:PropTypes.string};
