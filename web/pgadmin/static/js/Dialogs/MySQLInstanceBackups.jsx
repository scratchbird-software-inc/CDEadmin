import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';
import GridNavigation from '../cdeadmin_ui/data/GridNavigation';
import {Checkbox as SrCheckbox, NumberField, Select as SrSelect, Stack} from '../cdeadmin_ui';
import StructuredPayloadCard from '../cdeadmin_ui/modules/StructuredPayloadCard';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
const DEFAULT_OPTIONS=JSON.stringify({users:true,consistent:true,checksum:true,threads:4,compression:'zstd;level=1',timeout_seconds:3600},null,2);
const COMPRESSION_OPTIONS=[
  {value:'zstd;level=1',label:'zstd (level 1)'},
  {value:'zstd',label:'zstd (default)'},
  {value:'gzip',label:'gzip'},
  {value:'none',label:'Uncompressed (none)'},
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
export default function MySQLInstanceBackups({post,endpointUrl}) {
  const [options,setOptions]=useState(DEFAULT_OPTIONS);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[page,setPage]=useState(null),[files,setFiles]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[confirmation,setConfirmation]=useState('');
  const generation=useRef(0),downloads=useRef([]);
  useEffect(()=> {
    generation.current++;setOptions(DEFAULT_OPTIONS);setReview(null);setReceipt(null);setPage(null);setFiles(null);setError('');setConfirmation('');setBusy(false);
    return ()=>{generation.current++;downloads.current.splice(0).forEach(close=>close());};
  },[post,endpointUrl]);
  const run=async (action,request,accept)=> {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:'mysql_instance_backup_'+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native instance backup request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(()=> {
    if(!ACTIVE.has(receipt?.state))return;
    const token=generation.current;let pending=false,live=true;
    const timer=setInterval(async()=> {
      if(pending)return;pending=true;
      try {const value=await post({action:'mysql_instance_backup_status',request:{job_id:receipt.job_id}});if(live && token===generation.current)setReceipt(value);}
      catch(failure) {if(live && token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native backup status is unavailable');}
      finally {pending=false;}
    },1500);
    return ()=>{live=false;clearInterval(timer);};
  },[receipt?.job_id,receipt?.state,post]);
  const load=offset=>run('list',{offset,limit:25},setPage);
  const inspect=job=>run('status',{job_id:job.job_id},value=>{setReceipt(value);setFiles(null);setConfirmation('');});
  const download=row=> {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{job_id:receipt.job_id,path:row.path},
      {action:'mysql_instance_backup_download',prefix:'mysql-instance-backup',title:'Native instance backup file'}));}
    catch(failure) {setError(failure.message || 'Backup file download failed');}
  };
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
    <FormReference formKey="mysql-instance-backups" />
    <Alert severity="info">Create a native MySQL Shell instance dump containing its selected schemas, objects, data and optional accounts/roles/grants. System schemas excluded by MySQL Shell remain excluded. The utility can briefly pause writes to establish consistency. Output stays in a private directory on the application execution host. Account definitions can contain authentication material.</Alert>
    <Alert severity="info">Backup completion and file verification are separate from restored-data/definition verification, physical recovery and production cutover. Managed backup holds protect source archives until separately retired. Closing this view does not cancel a running job.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{my:1.5,p:1.5,border:'1px solid var(--sr-border, rgba(128,128,128,0.22))',borderRadius:1.5}}>
      <Stack gap={1.5}>
        <Stack direction="row" gap={2} style={{flexWrap:'wrap'}}>
          <SrCheckbox label="Include accounts, roles, and grants (users)" disabled={busy || !parsedOptions} checked={Boolean(parsedOptions?.users)} onChange={checked=>updateOptionField({users:checked})} />
          <SrCheckbox label="Consistent snapshot" disabled={busy || !parsedOptions} checked={Boolean(parsedOptions?.consistent)} onChange={checked=>updateOptionField({consistent:checked})} />
          <SrCheckbox label="Compute table checksums" disabled={busy || !parsedOptions} checked={Boolean(parsedOptions?.checksum)} onChange={checked=>updateOptionField({checksum:checked})} />
          <SrCheckbox label="Dry run only" disabled={busy || !parsedOptions} checked={Boolean(parsedOptions?.dryRun)} onChange={checked=>updateOptionField({dryRun:checked || undefined})} />
        </Stack>
        <Stack direction="row" gap={1.5} style={{flexWrap:'wrap'}}>
          <NumberField label="Worker threads" disabled={busy || !parsedOptions} value={parsedOptions?.threads ?? 4} onChange={e=>updateOptionField({threads:Math.max(1,Number(e.target.value)||1)})} style={{maxWidth:160}} />
          <SrSelect label="Compression" disabled={busy || !parsedOptions} options={COMPRESSION_OPTIONS} value={parsedOptions?.compression || 'zstd;level=1'} onChange={val=>updateOptionField({compression:val})} style={{minWidth:200}} />
          <NumberField label="Timeout (seconds)" disabled={busy || !parsedOptions} value={parsedOptions?.timeout_seconds ?? 3600} onChange={e=>updateOptionField({timeout_seconds:Math.max(1,Number(e.target.value)||3600)})} style={{maxWidth:180}} />
        </Stack>
        <Stack direction="row" gap={1.5} style={{flexWrap:'wrap'}}>
          <TextField size="small" label="Include schemas (comma-separated)" disabled={busy || !parsedOptions} value={Array.isArray(parsedOptions?.include_schemas) ? parsedOptions.include_schemas.join(', ') : ''} onChange={e=>{const list=splitCsvList(e.target.value);updateOptionField({include_schemas:list.length ? list : undefined});}} sx={{minWidth:240,flex:1}} />
          <TextField size="small" label="Exclude schemas (comma-separated)" disabled={busy || !parsedOptions} value={Array.isArray(parsedOptions?.exclude_schemas) ? parsedOptions.exclude_schemas.join(', ') : ''} onChange={e=>{const list=splitCsvList(e.target.value);updateOptionField({exclude_schemas:list.length ? list : undefined});}} sx={{minWidth:240,flex:1}} />
        </Stack>
        <Box component="details">
          <summary style={{cursor:'pointer',fontSize:12,opacity:0.8}}>Advanced JSON overrides</summary>
          <Box sx={{mt:1}}>
            <TextField multiline minRows={5} fullWidth label="Native instance backup options" value={options} disabled={busy}
              helperText="Instance options include users, include_schemas, exclude_schemas, include_users and exclude_users, together with native schema-dump options. Optional system_state_tables select native system-table checkpoints; system_state_write_pause_confirmed:true acknowledges a server-wide read lock throughout the dump. The application assigns the private output path."
              onChange={event=>{setOptions(event.target.value);setReview(null);}} />
          </Box>
        </Box>
      </Stack>
    </Box>
    <Button disabled={busy} onClick={()=>{try {const selected=JSON.parse(options);run('review',{options:selected},value=>{setReview(value);setReceipt(null);setFiles(null);});} catch(failure) {setError(failure.message);}}}>Review full-instance backup</Button>
    <Button disabled={busy} onClick={()=>load(0)}>Load instance backup jobs</Button>
    {review && <Box sx={{my:1}}>
      {review.warnings.map(warning=><Alert severity="warning" key={warning}>{warning}</Alert>)}
      <StructuredPayloadCard
        title="Reviewed instance backup plan"
        value={{source:review.source,options:review.options,execution_host:review.execution_host}}
        rawAriaLabel="Instance backup review"
      />
      <Button disabled={busy || review.state!=='reviewed'} onClick={()=>run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value=>{setReceipt(value);setReview(current=>({...current,state:value.state}));})}>Confirm and start instance backup</Button>
    </Box>}
    {page && <>
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Instance backup jobs"
        rows={(page.jobs || []).map(job => ({
          id: job.job_id,
          job_id: job.job_id,
          server_uuid: job.source.server_uuid,
          state: job.state,
          _raw: job,
        }))}
        columns={[
          {key: 'job_id', name: 'Job'},
          {key: 'server_uuid', name: 'Source'},
          {key: 'state', name: 'State'},
          {
            key: '_inspect',
            name: 'Inspect',
            render: (_val, r) => <Button disabled={busy} onClick={()=>inspect(r._raw)}>Inspect instance backup {r._raw.job_id}</Button>,
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
      {page.unavailable_job_ids?.length>0 && <Alert severity="warning">Some backup receipts are unavailable: {page.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={['completed','artifact_verified'].includes(receipt.state) ? 'success' : ['failed','unknown','native_returned_unverified'].includes(receipt.state) ? 'warning' : 'info'}>
        Instance backup {receipt.job_id}: {receipt.state}. Native dump reply acknowledged: {receipt.native_dump_acknowledged ? 'yes' : 'no'}.
        {receipt.state==='artifact_verified' && ' File acceptance does not change the original native reply.'}
        {receipt.artifact_removed && ' Backup files were removed; its receipt remains.'}
      </Alert>
      {receipt.native_error && <Alert severity="error">Native backup error {receipt.native_error.code ?? ''}: {receipt.native_error.message}</Alert>}
      {(receipt.result?.private_script_cleanup || receipt.private_script_cleanup)?.complete===false && <Alert severity="warning">Private execution-script cleanup is incomplete. <Button disabled={busy} onClick={()=>run('cleanup_script',{job_id:receipt.job_id},setReceipt)}>Retry private-script cleanup</Button></Alert>}
      <Button disabled={busy} onClick={()=>inspect(receipt)}>Refresh instance backup receipt</Button>
      {receipt.server_lock_owner && <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={()=>run('observe_source_locks',{job_id:receipt.job_id},setReceipt)}>Observe original source lock cleanup</Button>}
      {receipt.source_lock_cleanup_observation && <Alert severity={receipt.source_lock_cleanup_observation.released===true ? 'info' : 'warning'}>Original source lock cleanup: {receipt.source_lock_cleanup_observation.released===true ? 'confirmed' : 'unconfirmed'}. The original dump reply and file acceptance are unchanged.</Alert>}
      {receipt.utility_observation_unavailable && receipt.native_process_termination_confirmed!==true && <Alert severity="warning">The original utility reference is unavailable. This receipt cannot confirm cleanup or cancel that client. The original outcome is unchanged.</Alert>}
      {receipt.interrupted_utility_observation && <Alert severity={receipt.native_process_termination_confirmed===true ? 'info' : 'warning'}>Interrupted utility cleanup: {receipt.native_process_termination_confirmed===true ? 'confirmed' : 'unconfirmed'}. Original native acknowledgement is unchanged. Backup files still require independent verification.</Alert>}
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed' && !(receipt.state==='unknown' && receipt.durable_tool && receipt.native_process_termination_confirmed!==true)} onClick={()=>run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel instance backup</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state) || receipt.artifact_removed} onClick={()=>run('reconcile',{job_id:receipt.job_id},setReceipt)}>Verify instance backup files</Button>
      <Button disabled={busy || !receipt.result?.artifact || receipt.artifact_removed} onClick={()=>run('files',{job_id:receipt.job_id,offset:0,limit:100},setFiles)}>Load instance backup files</Button>
      <Button disabled={busy || !receipt.result?.artifact || receipt.artifact_removed} onClick={()=>run('pin',{job_id:receipt.job_id,pinned:!receipt.retention_pinned},setReceipt)}>{receipt.retention_pinned ? 'Unprotect instance backup from removal' : 'Protect instance backup from removal'}</Button>
      {files && <>
        <UnifiedDataGrid
          gridRole="table"
          ariaLabel="Verified instance backup files"
          rows={(files.files || []).map(row => ({
            id: row.path,
            path: row.path,
            size: row.size,
            sha256: row.sha256,
            _raw: row,
          }))}
          columns={[
            {key: 'path', name: 'File'},
            {key: 'size', name: 'Bytes'},
            {key: 'sha256', name: 'SHA256'},
            {
              key: '_download',
              name: 'Download',
              render: (_val, r) => <Button onClick={()=>download(r._raw)}>Download {r._raw.path}</Button>,
            },
          ]}
          compact
          searchable={false}
          exportable={false}
        />
        <GridNavigation
          busy={busy}
          page={Math.floor((files.offset || 0) / 100)}
          pages={Math.max(1, Math.ceil((files.total || 0) / 100))}
          endKnown
          canNext={(files.offset || 0) + 100 < (files.total || 0)}
          onFirst={() => run('files',{job_id:receipt.job_id,offset:0,limit:100},setFiles)}
          onPrevious={() => run('files',{job_id:receipt.job_id,offset:Math.max(0,(files.offset||0)-100),limit:100},setFiles)}
          onNext={() => run('files',{job_id:receipt.job_id,offset:(files.offset||0)+100,limit:100},setFiles)}
          onLast={() => run('files',{job_id:receipt.job_id,offset:Math.max(0,(Math.ceil((files.total||0)/100)-1)*100),limit:100},setFiles)}
        />
      </>}
      {!receipt.artifact_removed && !ACTIVE.has(receipt.state) && <Box sx={{my:1,display:'flex',gap:1}}>
        <TextField size="small" label="Confirm instance backup job identity for removal" value={confirmation} onChange={event=>setConfirmation(event.target.value)} />
        <Button disabled={busy || confirmation!==receipt.job_id || receipt.retention_pinned} onClick={()=>run(receipt.artifact_removal ? 'removal_reconcile' : 'remove_artifact',{job_id:receipt.job_id,confirmation},value=>{setReceipt(value);setFiles(null);})}>{receipt.artifact_removal ? 'Reconcile instance backup removal' : 'Remove instance backup files'}</Button>
      </Box>}
      <StructuredPayloadCard
        title="Instance backup receipt summary"
        value={{
          job_id:receipt.job_id,
          state:receipt.state,
          native_dump_acknowledged:Boolean(receipt.native_dump_acknowledged),
          retention_pinned:Boolean(receipt.retention_pinned),
          artifact_removed:Boolean(receipt.artifact_removed),
          source:receipt.source,
          execution_host:receipt.execution_host,
        }}
        rawText={JSON.stringify(receipt,null,2)}
        rawDisclosureLabel="Native instance backup observations"
      />
    </Box>}
  </Box>;
}
MySQLInstanceBackups.propTypes={post:PropTypes.func.isRequired,endpointUrl:PropTypes.string.isRequired};
