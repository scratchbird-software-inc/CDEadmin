import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,TextField} from '@mui/material';
import MySQLInstanceAcceptance from './MySQLInstanceAcceptance';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';
import GridNavigation from '../cdeadmin_ui/data/GridNavigation';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
const DEFAULT_OPTIONS=JSON.stringify({load_users:false,checksum:true,threads:4,update_gtid_set:'off',timeout_seconds:3600},null,2);
export default function MySQLInstanceRestores({post}) {
  const [sources,setSources]=useState(null),[source,setSource]=useState(null),[backups,setBackups]=useState(null),[backup,setBackup]=useState(null);
  const [target,setTarget]=useState(null),[confirmation,setConfirmation]=useState(''),[options,setOptions]=useState(DEFAULT_OPTIONS);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[observation,setObservation]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const generation=useRef(0);
  useEffect(()=> {
    generation.current++;setSources(null);setSource(null);setBackups(null);setBackup(null);setTarget(null);setConfirmation('');setOptions(DEFAULT_OPTIONS);
    setReview(null);setReceipt(null);setJobs(null);setObservation(null);setBusy(false);setError('');
    return ()=>{generation.current++;};
  },[post]);
  const run=async(action,request,accept)=> {
    const token=generation.current;setBusy(true);setError('');
    try {const result=await post({action:'mysql_instance_restore_'+action,request});if(token===generation.current)accept(result);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native instance restore request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(()=> {
    if(!ACTIVE.has(receipt?.state))return;
    const token=generation.current;let pending=false,live=true;
    const timer=setInterval(async()=> {
      if(pending)return;pending=true;
      try {const result=await post({action:'mysql_instance_restore_status',request:{job_id:receipt.job_id}});if(live && token===generation.current)setReceipt(result);}
      catch(failure) {if(live && token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native restore status unavailable');}
      finally {pending=false;}
    },1500);
    return ()=>{live=false;clearInterval(timer);};
  },[receipt?.job_id,receipt?.state,post]);
  const loadSources=offset=>run('sources',{offset,limit:25},setSources);
  const loadBackups=offset=>run('backups',{source_server_id:source.server_id,offset,limit:25},setBackups);
  const loadJobs=offset=>run('list',{offset,limit:25},setJobs);
  return <Box sx={{p:2}}>
    <FormReference formKey="mysql-instance-restores" />
    <Alert severity="warning">Restore a managed full-instance backup onto a separate confirmed MySQL instance during an exclusive maintenance window. Native DDL, data, accounts and GTIDs can change independently; cancellation does not undo earlier effects. Configure trusted local_infile on the target before loading. Closing this view does not cancel a job.</Alert>
    <Alert severity="info">Native utility return, current target observations, recovered data/definitions and production cutover have separate acceptance. Account loading is optional. An uncertain restore is never automatically repeated.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={()=>run('inspect',{},value=>{setTarget(value);setReview(null);})}>Inspect instance restore target</Button>
    {target && <Box component="pre" aria-label="Native instance restore target" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(target,null,2)}</Box>}
    <Button disabled={busy} onClick={()=>loadSources(0)}>Load instance backup sources</Button>
    {sources && <>
      {sources.sources.map(row=><Button disabled={busy} key={row.server_id} onClick={()=>{setSource(row);setBackups(null);setBackup(null);setReview(null);}}>Use backup source {row.name}</Button>)}
      {sources.total > 25 && (
        <GridNavigation
          busy={busy}
          page={Math.floor(sources.offset / 25)}
          pages={Math.max(1, Math.ceil(sources.total / 25))}
          endKnown
          canNext={sources.offset + 25 < sources.total}
          onFirst={()=>loadSources(0)}
          onPrevious={()=>loadSources(Math.max(0,sources.offset-25))}
          onNext={()=>loadSources(sources.offset+25)}
          onLast={()=>loadSources(Math.max(0,(Math.ceil(sources.total/25)-1)*25))}
        />
      )}
    </>}
    {source && <Box><Box>Backup source: {source.name}</Box><Button disabled={busy} onClick={()=>loadBackups(0)}>Load source instance backups</Button></Box>}
    {backups && <>
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Restore source instance backups"
        rows={(backups.jobs || []).map(row => ({
          id: row.job_id,
          job_id: row.job_id,
          state: row.state,
          _raw: row,
        }))}
        columns={[
          {key: 'job_id', name: 'Backup'},
          {key: 'state', name: 'State'},
          {
            key: '_use',
            name: 'Use',
            render: (_val, r) => <Button disabled={busy || !['completed','artifact_verified'].includes(r._raw.state) || r._raw.artifact_removed} onClick={()=>{setBackup(r._raw);setReview(null);}}>Use instance backup {r._raw.job_id}</Button>,
          },
        ]}
        compact
        searchable={false}
        exportable={false}
      />
      <GridNavigation
        busy={busy}
        page={Math.floor((backups.offset || 0) / 25)}
        pages={Math.max(1, Math.ceil((backups.total || 0) / 25))}
        endKnown
        canNext={(backups.offset || 0) + 25 < (backups.total || 0)}
        onFirst={() => loadBackups(0)}
        onPrevious={() => loadBackups(Math.max(0, (backups.offset || 0) - 25))}
        onNext={() => loadBackups((backups.offset || 0) + 25)}
        onLast={() => loadBackups(Math.max(0, (Math.ceil((backups.total || 0) / 25) - 1) * 25))}
      />
    </>}
    {backup && <Alert severity="info">Selected instance backup: {backup.job_id}</Alert>}
    <TextField fullWidth label="Confirm native restore target UUID" value={confirmation} disabled={busy} onChange={event=>{setConfirmation(event.target.value);setReview(null);}} />
    <TextField fullWidth multiline minRows={6} label="Native instance restore options" value={options} disabled={busy}
      helperText="Native load options include load_users, include_users/exclude_users, schema/object filters, load_data/load_ddl, drop_existing_objects and update_gtid_set. Input and progress paths are assigned privately."
      onChange={event=>{setOptions(event.target.value);setReview(null);}} />
    <Button disabled={busy || !backup || !target || confirmation!==target.identity.server_uuid} onClick={()=> {
      try {run('review',{source_server_id:source.server_id,backup_job_id:backup.job_id,options:{...JSON.parse(options),target_confirmation:confirmation}},value=>{setReview(value);setReceipt(null);setObservation(null);});}
      catch(failure) {setError(failure.message);}
    }}>Review full-instance restore</Button>
    {review && <Box>
      {review.warnings.map(warning=><Alert severity="warning" key={warning}>{warning}</Alert>)}
      <Box component="pre" aria-label="Instance restore review" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify({target:review.target,source_backup:review.source_backup,options:review.options,execution_host:review.execution_host},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={()=>run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value=>{setReceipt(value);setReview(current=>({...current,state:value.state}));})}>Confirm and start instance restore</Button>
    </Box>}
    <Button disabled={busy} onClick={()=>loadJobs(0)}>Load instance restore jobs</Button>
    {jobs && <>
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Instance restore jobs"
        rows={(jobs.jobs || []).map(row => ({
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
            render: (_val, r) => <Button disabled={busy} onClick={()=>run('status',{job_id:r._raw.job_id},value=>{setReceipt(value);setObservation(null);})}>Inspect instance restore {r._raw.job_id}</Button>,
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
      <Alert severity={receipt.state==='native_load_returned' ? 'info' : receipt.state==='unknown' ? 'warning' : 'info'}>Instance restore {receipt.job_id}: {receipt.state}. Original native load outcome: {receipt.native_load_outcome}. Review independent acceptance receipts for data and definitions. Production cutover remains unverified.</Alert>
      {receipt.native_error && <Alert severity="error">Native restore error {receipt.native_error.code ?? ''}: {receipt.native_error.message}</Alert>}
      <Button disabled={busy} onClick={()=>run('status',{job_id:receipt.job_id},setReceipt)}>Refresh instance restore receipt</Button>
      {receipt.utility_observation_unavailable && receipt.native_process_termination_confirmed!==true && <Alert severity="warning">The original utility reference is unavailable. This receipt cannot confirm cleanup or cancel that client. The original outcome is unchanged.</Alert>}
      {receipt.interrupted_utility_observation && <Alert severity={receipt.native_process_termination_confirmed===true ? 'info' : 'warning'}>Interrupted utility cleanup: {receipt.native_process_termination_confirmed===true ? 'confirmed' : 'unconfirmed'}. The original native outcome is unchanged. Target acknowledgement remains separate.</Alert>}
      <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={()=>run('observe_utilities',{job_id:receipt.job_id},setReceipt)}>Observe original restore utility without SQL connection</Button>
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed' && !(receipt.state==='unknown' && receipt.durable_tool && receipt.native_process_termination_confirmed!==true)} onClick={()=>run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel instance restore</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={()=>run('reconcile',{job_id:receipt.job_id},value=>{setReceipt(value);setObservation(value.observation_digest);})}>Observe instance restore target</Button>
      {receipt.state==='unknown' && observation && <Button disabled={busy || confirmation!==receipt.target.server_uuid} onClick={()=>run('acknowledge',{job_id:receipt.job_id,target_confirmation:confirmation,observation_digest:observation},setReceipt)}>Acknowledge observed target for another recovery</Button>}
      <Box component="details"><summary>Native instance restore observations</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
    <MySQLInstanceAcceptance post={post} sourceServerId={source?.server_id} backupJobId={backup?.job_id} targetUuid={target?.identity?.server_uuid} targetConfirmation={confirmation} />
  </Box>;
}
MySQLInstanceRestores.propTypes={post:PropTypes.func.isRequired};
