import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,TextField} from '@mui/material';
import MySQLInstanceAcceptance from './MySQLInstanceAcceptance';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';
import GridNavigation from '../cdeadmin_ui/data/GridNavigation';
import {Checkbox as SrCheckbox, NumberField, Select as SrSelect, Stack} from '../cdeadmin_ui';
import StructuredPayloadCard from '../cdeadmin_ui/modules/StructuredPayloadCard';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
const DEFAULT_OPTIONS=JSON.stringify({load_users:false,checksum:true,threads:4,update_gtid_set:'off',timeout_seconds:3600},null,2);
const GTID_SET_OPTIONS=[
  {value:'off',label:'Off (preserve target GTIDs)'},
  {value:'append',label:'Append backup GTIDs'},
  {value:'replace',label:'Replace target GTID set'},
];
function parseJsonObject(text) {
  try {
    const parsed=JSON.parse(text);
    return parsed && typeof parsed==='object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}
function splitCsvList(text) {
  return String(text || '').split(',').map(s=>s.trim()).filter(Boolean);
}
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
  const parsedOptions=parseJsonObject(options);
  const updateOptionField=(patch)=> {
    const base=parsedOptions ? {...parsedOptions} : {};
    Object.entries(patch).forEach(([k,v])=> {
      if(v===undefined)delete base[k];
      else base[k]=v;
    });
    setOptions(JSON.stringify(base,null,2));
    setReview(null);
  };
  return <Box sx={{p:2}}>
    <FormReference formKey="mysql-instance-restores" />
    <Alert severity="warning">Restore a managed full-instance backup onto a separate confirmed MySQL instance during an exclusive maintenance window. Native DDL, data, accounts and GTIDs can change independently; cancellation does not undo earlier effects. Configure trusted local_infile on the target before loading. Closing this view does not cancel a job.</Alert>
    <Alert severity="info">Native utility return, current target observations, recovered data/definitions and production cutover have separate acceptance. Account loading is optional. An uncertain restore is never automatically repeated.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={()=>run('inspect',{},value=>{setTarget(value);setReview(null);})}>Inspect instance restore target</Button>
    {target && <Box sx={{my:1}}><StructuredPayloadCard title="Inspected restore target" value={target} rawAriaLabel="Native instance restore target" /></Box>}
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
    <Box sx={{my:1.5,p:1.5,border:'1px solid var(--sr-border, rgba(128,128,128,0.22))',borderRadius:1.5}}>
      <Stack gap={1.5}>
        <Stack direction="row" gap={2} style={{flexWrap:'wrap'}}>
          <SrCheckbox label="Load accounts and grants (load_users)" disabled={busy || !parsedOptions} checked={Boolean(parsedOptions?.load_users)} onChange={checked=>updateOptionField({load_users:checked})} />
          <SrCheckbox label="Verify checksums" disabled={busy || !parsedOptions} checked={Boolean(parsedOptions?.checksum)} onChange={checked=>updateOptionField({checksum:checked})} />
          <SrCheckbox label="Load DDL" disabled={busy || !parsedOptions} checked={parsedOptions?.load_ddl !== false} onChange={checked=>updateOptionField({load_ddl:checked})} />
          <SrCheckbox label="Load data" disabled={busy || !parsedOptions} checked={parsedOptions?.load_data !== false} onChange={checked=>updateOptionField({load_data:checked})} />
          <SrCheckbox label="Drop existing objects" disabled={busy || !parsedOptions} checked={Boolean(parsedOptions?.drop_existing_objects)} onChange={checked=>updateOptionField({drop_existing_objects:checked || undefined})} />
        </Stack>
        <Stack direction="row" gap={1.5} style={{flexWrap:'wrap'}}>
          <NumberField label="Worker threads" disabled={busy || !parsedOptions} value={parsedOptions?.threads ?? 4} onChange={e=>updateOptionField({threads:Math.max(1,Number(e.target.value)||1)})} style={{maxWidth:160}} />
          <SrSelect label="GTID set mode" disabled={busy || !parsedOptions} options={GTID_SET_OPTIONS} value={parsedOptions?.update_gtid_set || 'off'} onChange={val=>updateOptionField({update_gtid_set:val})} style={{minWidth:210}} />
          <NumberField label="Timeout (seconds)" disabled={busy || !parsedOptions} value={parsedOptions?.timeout_seconds ?? 3600} onChange={e=>updateOptionField({timeout_seconds:Math.max(1,Number(e.target.value)||3600)})} style={{maxWidth:180}} />
        </Stack>
        <Stack direction="row" gap={1.5} style={{flexWrap:'wrap'}}>
          <TextField size="small" label="Include schemas (comma-separated)" disabled={busy || !parsedOptions} value={Array.isArray(parsedOptions?.include_schemas) ? parsedOptions.include_schemas.join(', ') : ''} onChange={e=>{const list=splitCsvList(e.target.value);updateOptionField({include_schemas:list.length ? list : undefined});}} sx={{minWidth:220,flex:1}} />
          <TextField size="small" label="Exclude tables (comma-separated)" disabled={busy || !parsedOptions} value={Array.isArray(parsedOptions?.exclude_tables) ? parsedOptions.exclude_tables.join(', ') : ''} onChange={e=>{const list=splitCsvList(e.target.value);updateOptionField({exclude_tables:list.length ? list : undefined});}} sx={{minWidth:220,flex:1}} />
        </Stack>
        <Box component="details">
          <summary style={{cursor:'pointer',fontSize:12,opacity:0.8}}>Advanced JSON overrides</summary>
          <Box sx={{mt:1}}>
            <TextField fullWidth multiline minRows={5} label="Native instance restore options" value={options} disabled={busy}
              helperText="Native load options include load_users, include_users/exclude_users, schema/object filters, load_data/load_ddl, drop_existing_objects and update_gtid_set. Input and progress paths are assigned privately."
              onChange={event=>{setOptions(event.target.value);setReview(null);}} />
          </Box>
        </Box>
      </Stack>
    </Box>
    <Button disabled={busy || !backup || !target || confirmation!==target.identity.server_uuid} onClick={()=> {
      try {run('review',{source_server_id:source.server_id,backup_job_id:backup.job_id,options:{...JSON.parse(options),target_confirmation:confirmation}},value=>{setReview(value);setReceipt(null);setObservation(null);});}
      catch(failure) {setError(failure.message);}
    }}>Review full-instance restore</Button>
    {review && <Box sx={{my:1}}>
      {review.warnings.map(warning=><Alert severity="warning" key={warning}>{warning}</Alert>)}
      <StructuredPayloadCard
        title="Reviewed instance restore plan"
        value={{target:review.target,source_backup:review.source_backup,options:review.options,execution_host:review.execution_host}}
        rawAriaLabel="Instance restore review"
      />
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
      <StructuredPayloadCard
        title="Instance restore receipt summary"
        value={{
          job_id:receipt.job_id,
          state:receipt.state,
          native_load_outcome:receipt.native_load_outcome,
          target:receipt.target,
          execution_host:receipt.execution_host,
        }}
        rawText={JSON.stringify(receipt,null,2)}
        rawDisclosureLabel="Native instance restore observations"
      />
    </Box>}
    <MySQLInstanceAcceptance post={post} sourceServerId={source?.server_id} backupJobId={backup?.job_id} targetUuid={target?.identity?.server_uuid} targetConfirmation={confirmation} />
  </Box>;
}
MySQLInstanceRestores.propTypes={post:PropTypes.func.isRequired};
