import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Table, TableBody, TableCell, TableHead, TableRow, TablePagination, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

const ACTIVE = new Set(['dispatching', 'active', 'verifying', 'verifying_inputs', 'cancel_requested']);
const defaults = () => ({format:'plain', wal_method:'stream', checkpoint:'fast', manifest_checksums:'SHA256',
  label:'ScratchRobin physical backup', compression:'', max_rate_kib:'', slot:'', create_slot:false, no_slot:false,
  write_recovery_conf:false, verify_page_checksums:true, progress:true, estimate_size:true, sync:true, sync_method:'fsync', timeout_seconds:3600});
const walDefaults = () => ({archive:'',compression:'none',slot:'',synchronous:true,sync:true,status_interval_seconds:10,end_lsn:'',no_loop:false,timeout_seconds:null});

export default function PostgresqlContinuity({post}) {
  const [operation,setOperation]=useState('full_backup'), [options,setOptions]=useState(defaults);
  const [walOptions,setWalOptions]=useState(walDefaults);
  const [copyMode,setCopyMode]=useState('copy'), [inputs,setInputs]=useState([]);
  const [recoveryDatabase,setRecoveryDatabase]=useState('postgres'), [checks,setChecks]=useState([]);
  const [targetKind,setTargetKind]=useState(''), [targetValue,setTargetValue]=useState(''), [targetInclusive,setTargetInclusive]=useState(true), [targetTimeline,setTargetTimeline]=useState('current');
  const [walArchives,setWalArchives]=useState(null), [walArchive,setWalArchive]=useState('');
  const [page,setPage]=useState(0), [catalog,setCatalog]=useState(null), [review,setReview]=useState(null), [receipt,setReceipt]=useState(null);
  const [busy,setBusy]=useState(false), [error,setError]=useState('');
  const [confirmStop,setConfirmStop]=useState(false);
  const generation=useRef(0);
  useEffect(() => {
    generation.current++;setOperation('full_backup');setOptions(defaults());setWalOptions(walDefaults());setCopyMode('copy');setInputs([]);
    setRecoveryDatabase('postgres');setChecks([]);
    setTargetKind('');setTargetValue('');setTargetInclusive(true);setTargetTimeline('current');setWalArchives(null);setWalArchive('');
    setPage(0);setCatalog(null);setReview(null);setReceipt(null);setBusy(false);setError('');setConfirmStop(false);
    return () => {generation.current++;};
  },[post]);
  useEffect(() => {setConfirmStop(false);},[receipt?.job_id,receipt?.state]);
  useEffect(() => {
    if(!receipt || !ACTIVE.has(receipt.state))return;
    let live=true, pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {
        const result=await post({action:'postgresql_continuity_status',request:{job_id:receipt.job_id}});
        if(live)setReceipt(result);
      } catch(failure) {if(live)setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending=false;}
    },2000);
    return () => {live=false;clearInterval(timer);};
  },[post,receipt?.job_id,receipt?.state]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const result=await post({action:'postgresql_continuity_'+action,request});if(token===generation.current)accept(result);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native continuity request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  const load=next => run('list',{offset:next*25,limit:25},result => {setCatalog(result);setPage(next);});
  const edit=(name,value) => {setOptions(current => ({...current,[name]:value}));setReview(null);};
  const editWal=(name,value) => {setWalOptions(current => ({...current,[name]:value}));setReview(null);};
  const select=(name,values) => <TextField key={name} disabled={busy} select size="small" label={name.replaceAll('_',' ')} value={options[name]}
    onChange={event => edit(name,event.target.value)}>{values.map(value => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>;
  const prepare=() => {
    let nativeOptions;
    if(operation==='wal_capture')nativeOptions=walOptions;
    else if(operation==='combine')nativeOptions={format:'plain',copy_mode:copyMode,...Object.fromEntries(['manifest_checksums','sync','sync_method','timeout_seconds'].map(key => [key,options[key]]))};
    else if(operation==='recovery_drill')nativeOptions={database:recoveryDatabase,checks:checks.map(check => ({schema:check.schema,table:check.table,...(check.expected_rows==='' ? {} : {expected_rows:check.expected_rows})})),timeout_seconds:options.timeout_seconds,
      ...(targetKind ? {target:{kind:targetKind,...(targetKind==='immediate' ? {} : {value:targetValue}),inclusive:targetInclusive,timeline:targetTimeline},wal_archive:walArchive} : {})};
    else if(operation==='verify')nativeOptions={timeout_seconds:options.timeout_seconds};
    else nativeOptions={...options,max_rate_kib:options.max_rate_kib==='' ? null : Number(options.max_rate_kib)};
    run('review',{operation,options:nativeOptions,...(operation==='combine' ? {chain:inputs} : ['full_backup','wal_capture'].includes(operation) ? {} : {base_job_id:inputs[0]})},setReview);
  };
  const download=() => {
    const url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='postgresql-continuity-'+receipt.job_id+'.json';link.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  };
  const backup=['full_backup','incremental_backup'].includes(operation);
  return <Box aria-label="PostgreSQL continuity workspace" sx={{p:1,overflow:'auto',flex:1,minHeight:0,minWidth:0,height:'100%',boxSizing:'border-box'}}>
    <FormReference formKey="postgresql-continuity" />
    <Alert severity="info">Physical backups include the whole PostgreSQL cluster. Files and native tools run on the application host. Verification checks the recorded scope; a recovery drill is required to demonstrate recovery.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <TextField disabled={busy} select size="small" label="Continuity operation" value={operation} onChange={event => {setOperation(event.target.value);setInputs([]);setReview(null);}}>
        {[['full_backup','Full physical backup'],['incremental_backup','Incremental physical backup'],['wal_capture','Capture native WAL archive'],['verify','Verify existing backup'],['combine','Reconstruct backup chain'],['recovery_drill','Recover isolated backup copy']].map(([value,label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
      </TextField>
      <Button disabled={busy} onClick={() => load(page)}>Load backup jobs</Button>
    </Box>
    {catalog && <>
      <Table size="small" aria-label="Native physical backup jobs"><TableHead><TableRow>
        {['Operation','Job','State','Input','Receipt'].map(label => <TableCell key={label}>{label}</TableCell>)}
      </TableRow></TableHead><TableBody>{catalog.jobs.map(job => <TableRow key={job.job_id}>
        <TableCell>{job.operation}</TableCell><TableCell>{job.job_id}</TableCell><TableCell>{job.state}</TableCell>
        <TableCell><Button disabled={busy || ['full_backup','wal_capture'].includes(operation) || job.operation==='wal_capture' || (operation!=='verify' && job.state!=='verified') || ACTIVE.has(job.state) || inputs.includes(job.job_id)}
          onClick={() => {setInputs(current => operation==='combine' ? [...current,job.job_id] : [job.job_id]);setReview(null);}}>Select input</Button></TableCell>
        <TableCell><Button disabled={busy} aria-label={'Inspect backup '+job.job_id} onClick={() => run('status',{job_id:job.job_id},setReceipt)}>Inspect</Button></TableCell>
      </TableRow>)}</TableBody></Table>
      <TablePagination component="div" count={catalog.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={page} onPageChange={(_event,next) => load(next)} />
      {catalog.unavailable_job_ids?.length>0 && <Alert severity="warning">Some backup receipts could not be read: {catalog.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {!['full_backup','wal_capture'].includes(operation) && <Box><b>{operation==='combine' ? 'Ordered chain (full backup first)' : 'Selected input'}</b>
      <ol>{inputs.map(id => <li key={id}>{id} <Button disabled={busy} onClick={() => {setInputs(current => current.filter(value => value!==id));setReview(null);}}>Remove input</Button></li>)}</ol>
    </Box>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      {backup && <>{select('format',['plain','tar'])}{select('wal_method',['stream','fetch','none'])}{select('checkpoint',['fast','spread'])}
        {['label','compression','slot','max_rate_kib'].map(name => <TextField key={name} disabled={busy} size="small" label={name.replaceAll('_',' ')} value={options[name]} onChange={event => edit(name,event.target.value)} />)}</>}
      {operation==='combine' && <TextField disabled={busy} select size="small" label="Native copy method" value={copyMode} onChange={event => {setCopyMode(event.target.value);setReview(null);}}>
        {['copy','clone','copy-file-range','link'].map(value => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>}
      {operation==='wal_capture' && <>
        {['archive','compression','slot','end_lsn'].map(name => <TextField key={name} disabled={busy} size="small" label={'WAL '+name.replaceAll('_',' ')} value={walOptions[name]} onChange={event => editWal(name,event.target.value)} />)}
        <TextField disabled={busy} size="small" type="number" label="WAL status interval seconds" value={walOptions.status_interval_seconds} onChange={event => editWal('status_interval_seconds',Number(event.target.value))} />
        {['synchronous','sync','no_loop'].map(name => <FormControlLabel key={name} label={'WAL '+name.replaceAll('_',' ')} control={<Checkbox disabled={busy} checked={walOptions[name]} onChange={event => editWal(name,event.target.checked)} />} />)}
      </>}
      <TextField disabled={busy} size="small" type="number" label="Timeout seconds (blank: no limit)" value={(operation==='wal_capture' ? walOptions.timeout_seconds : options.timeout_seconds) ?? ''} onChange={event => (operation==='wal_capture' ? editWal : edit)('timeout_seconds',event.target.value==='' ? null : Number(event.target.value))} />
      {!['verify','recovery_drill','wal_capture'].includes(operation) && <>{select('manifest_checksums',['NONE','CRC32C','SHA224','SHA256','SHA384','SHA512'])}{select('sync_method',['fsync','syncfs'])}
        {(backup ? ['create_slot','no_slot','write_recovery_conf','verify_page_checksums','progress','estimate_size','sync'] : ['sync']).map(name => <FormControlLabel key={name} label={name.replaceAll('_',' ')}
          control={<Checkbox disabled={busy} checked={options[name]} onChange={event => edit(name,event.target.checked)} />} />)}</>}
    </Box>
    {operation==='recovery_drill' && <Box sx={{my:1}}>
      <TextField disabled={busy} size="small" label="Recovery database" value={recoveryDatabase} onChange={event => {setRecoveryDatabase(event.target.value);setReview(null);}} />
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <TextField disabled={busy} select size="small" label="Recovery target" value={targetKind} onChange={event => {setTargetKind(event.target.value);setReview(null);}}>
          {[['','Backup consistency'],['time','Timestamp'],['xid','Transaction ID'],['lsn','WAL location (LSN)'],['name','Named restore point'],['immediate','Earliest consistent state']].map(([value,label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
        </TextField>
        {targetKind && <>
          {targetKind!=='immediate' && <TextField disabled={busy} size="small" label="Exact native target value" value={targetValue} onChange={event => {setTargetValue(event.target.value);setReview(null);}} />}
          <TextField disabled={busy} size="small" label="Recovery timeline (current, latest or ID)" value={targetTimeline} onChange={event => {setTargetTimeline(event.target.value);setReview(null);}} />
          {['time','xid','lsn'].includes(targetKind) && <FormControlLabel label="Include target" control={<Checkbox disabled={busy} checked={targetInclusive} onChange={event => {setTargetInclusive(event.target.checked);setReview(null);}} />} />}
          <Button disabled={busy} onClick={() => run('archives',{},setWalArchives)}>Load WAL archives</Button>
          <TextField disabled={busy} select size="small" label="Native WAL archive" value={walArchive} onChange={event => {setWalArchive(event.target.value);setReview(null);}}>
            <MenuItem value="">Select archive</MenuItem>{(walArchives?.archives || []).map(name => <MenuItem key={name} value={name}>{name}</MenuItem>)}
          </TextField>
        </>}
      </Box>
      {targetKind && <Alert severity="info">Completed native WAL files are read from the selected owner/endpoint archive on the application host. PostgreSQL must reach the selected target before a successful receipt is produced. The original backup and archive remain unchanged.{walArchives && ` Archive directory: ${walArchives.owner_endpoint_directory}`}</Alert>}
      <Alert severity="info">The private recovery copy runs without a network listener. Optional checks count rows in the selected native heap tables or materialized views. Names are exact; leave the expected count blank to record the observed count.</Alert>
      {checks.map((check,index) => <Box key={index} sx={{display:'flex',gap:1,my:1}}>
        {['schema','table','expected_rows'].map(name => <TextField key={name} disabled={busy} size="small" label={`${name.replaceAll('_',' ')} ${index+1}`} value={check[name]}
          onChange={event => {setChecks(current => current.map((value,position) => position===index ? {...value,[name]:event.target.value} : value));setReview(null);}} />)}
        <Button disabled={busy} onClick={() => {setChecks(current => current.filter((_value,position) => position!==index));setReview(null);}}>Remove check {index+1}</Button>
      </Box>)}
      <Button disabled={busy || checks.length>=64} onClick={() => {setChecks(current => [...current,{schema:'public',table:'',expected_rows:''}]);setReview(null);}}>Add recovery table check</Button>
    </Box>}
    <Button disabled={busy || (operation==='combine' ? inputs.length<2 : !['full_backup','wal_capture'].includes(operation) && !inputs.length)} onClick={prepare}>Review native operation</Button>
    {review && <Box sx={{my:1}}>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" sx={{whiteSpace:'pre-wrap',overflow:'auto',maxHeight:280}} aria-label="Native backup review">{JSON.stringify({operation:review.operation,source:review.source,options:review.options,inputs:review.inputs,tools:review.tool_identities},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={() => run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},result => {setReceipt(result);setReview(current => ({...current,state:result.state}));})}>Confirm and start reviewed operation</Button>
    </Box>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={['verified','recovered','captured'].includes(receipt.state) ? 'success' : ['failed','unknown','not_dispatched'].includes(receipt.state) ? 'warning' : 'info'}>
        Job {receipt.job_id}: {receipt.state}. {receipt.observation_blocker}
        {receipt.state==='verified' && ` Native file verification: ${receipt.verification_scope?.files ? 'yes' : 'no'}; WAL verification: ${receipt.verification_scope?.wal ? 'yes' : 'no'}. Recovery drill: ${receipt.recovery_drill_complete ? 'complete' : 'not completed'}.`}
        {receipt.state==='recovered' && ` Isolated native recovery completed. Selected heap row counts: ${receipt.verification_scope?.selected_heap_counts}. Point-in-time recovery: ${receipt.recovery_observation?.point_in_time_recovery ? 'completed for the reviewed target' : 'not requested'}. Production restore has a separate receipt.`}
        {receipt.operation==='wal_capture' && ` Completed archive files observed: ${receipt.archive_observation?.completed_files ?? 0}. Newly published: ${receipt.archive_observation?.new_files ?? 0}. Native recovery verification has a separate receipt.`}
      </Alert>
      <Button disabled={busy} onClick={() => run('status',{job_id:receipt.job_id},setReceipt)}>Refresh receipt</Button>
      <Button onClick={download}>Download receipt</Button>
      <Button disabled={busy || (!ACTIVE.has(receipt.state) && receipt.state!=='reviewed')} onClick={() => run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel native job</Button>
      {['unknown','failed','cancelled'].includes(receipt.state) && <Box>
        <Alert severity="info">Reconciliation stops reviewed native utilities still using this job&apos;s workspace on the application host. {receipt.operation==='wal_capture' ? 'Then review a new WAL capture with the same archive name to resume.' : 'Then select this job as input to Verify existing backup. A stopped utility does not establish a complete backup.'}</Alert>
        <FormControlLabel label="Confirm stopping this job's remaining native utilities" control={<Checkbox disabled={busy} checked={confirmStop} onChange={event => setConfirmStop(event.target.checked)} />} />
        <Button disabled={busy || !confirmStop} onClick={() => run('reconcile_writer',{job_id:receipt.job_id,confirmed:true},result => {setReceipt(result);setConfirmStop(false);})}>Reconcile native writer</Button>
      </Box>}
      {receipt.writer_reconciliation?.process_scope_stopped && <Alert severity="info">Owned native utilities are stopped. Backup verification and recovery retain separate receipts.</Alert>}
      <Box component="details"><summary>Native observations and artifact location</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',overflow:'auto',maxHeight:400}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
PostgresqlContinuity.propTypes={post:PropTypes.func.isRequired};
