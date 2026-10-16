import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Table, TableBody, TableCell, TableHead, TableRow, TablePagination, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

const ACTIVE = new Set(['dispatching', 'active', 'verifying', 'verifying_inputs', 'cancel_requested']);
const defaults = () => ({format:'plain', wal_method:'stream', checkpoint:'fast', manifest_checksums:'SHA256',
  label:'ScratchRobin physical backup', compression:'', max_rate_kib:'', slot:'', create_slot:false, no_slot:false,
  write_recovery_conf:false, verify_page_checksums:true, progress:true, estimate_size:true, sync:true, sync_method:'fsync', timeout_seconds:3600});

export default function PostgresqlContinuity({post}) {
  const [operation,setOperation]=useState('full_backup'), [options,setOptions]=useState(defaults);
  const [copyMode,setCopyMode]=useState('copy'), [inputs,setInputs]=useState([]);
  const [page,setPage]=useState(0), [catalog,setCatalog]=useState(null), [review,setReview]=useState(null), [receipt,setReceipt]=useState(null);
  const [busy,setBusy]=useState(false), [error,setError]=useState('');
  const generation=useRef(0);
  useEffect(() => {
    generation.current++;setOperation('full_backup');setOptions(defaults());setCopyMode('copy');setInputs([]);
    setPage(0);setCatalog(null);setReview(null);setReceipt(null);setBusy(false);setError('');
    return () => {generation.current++;};
  },[post]);
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
  const select=(name,values) => <TextField key={name} disabled={busy} select size="small" label={name.replaceAll('_',' ')} value={options[name]}
    onChange={event => edit(name,event.target.value)}>{values.map(value => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>;
  const prepare=() => {
    let nativeOptions;
    if(operation==='combine')nativeOptions={format:'plain',copy_mode:copyMode,...Object.fromEntries(['manifest_checksums','sync','sync_method','timeout_seconds'].map(key => [key,options[key]]))};
    else if(operation==='verify')nativeOptions={};
    else nativeOptions={...options,max_rate_kib:options.max_rate_kib==='' ? null : Number(options.max_rate_kib)};
    run('review',{operation,options:nativeOptions,...(operation==='combine' ? {chain:inputs} : operation==='full_backup' ? {} : {base_job_id:inputs[0]})},setReview);
  };
  const download=() => {
    const url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='postgresql-continuity-'+receipt.job_id+'.json';link.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  };
  const backup=['full_backup','incremental_backup'].includes(operation);
  return <Box sx={{p:1,overflow:'auto',flex:1}}>
    <FormReference formKey="postgresql-continuity" />
    <Alert severity="info">Physical backups include the whole PostgreSQL cluster. Files and native tools run on the application host. Verification checks the recorded scope; a recovery drill is required to demonstrate recovery.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <TextField disabled={busy} select size="small" label="Continuity operation" value={operation} onChange={event => {setOperation(event.target.value);setInputs([]);setReview(null);}}>
        {[['full_backup','Full physical backup'],['incremental_backup','Incremental physical backup'],['verify','Verify existing backup'],['combine','Reconstruct backup chain']].map(([value,label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
      </TextField>
      <Button disabled={busy} onClick={() => load(page)}>Load backup jobs</Button>
    </Box>
    {catalog && <>
      <Table size="small" aria-label="Native physical backup jobs"><TableHead><TableRow>
        {['Operation','Job','State','Input','Receipt'].map(label => <TableCell key={label}>{label}</TableCell>)}
      </TableRow></TableHead><TableBody>{catalog.jobs.map(job => <TableRow key={job.job_id}>
        <TableCell>{job.operation}</TableCell><TableCell>{job.job_id}</TableCell><TableCell>{job.state}</TableCell>
        <TableCell><Button disabled={busy || operation==='full_backup' || (operation!=='verify' && job.state!=='verified') || ACTIVE.has(job.state) || inputs.includes(job.job_id)}
          onClick={() => {setInputs(current => operation==='combine' ? [...current,job.job_id] : [job.job_id]);setReview(null);}}>Select input</Button></TableCell>
        <TableCell><Button disabled={busy} aria-label={'Inspect backup '+job.job_id} onClick={() => run('status',{job_id:job.job_id},setReceipt)}>Inspect</Button></TableCell>
      </TableRow>)}</TableBody></Table>
      <TablePagination component="div" count={catalog.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={page} onPageChange={(_event,next) => load(next)} />
      {catalog.unavailable_job_ids?.length>0 && <Alert severity="warning">Some backup receipts could not be read: {catalog.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {operation!=='full_backup' && <Box><b>{operation==='combine' ? 'Ordered chain (full backup first)' : 'Selected input'}</b>
      <ol>{inputs.map(id => <li key={id}>{id} <Button disabled={busy} onClick={() => {setInputs(current => current.filter(value => value!==id));setReview(null);}}>Remove input</Button></li>)}</ol>
    </Box>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      {backup && <>{select('format',['plain','tar'])}{select('wal_method',['stream','fetch','none'])}{select('checkpoint',['fast','spread'])}
        {['label','compression','slot','max_rate_kib'].map(name => <TextField key={name} disabled={busy} size="small" label={name.replaceAll('_',' ')} value={options[name]} onChange={event => edit(name,event.target.value)} />)}</>}
      {operation==='combine' && <TextField disabled={busy} select size="small" label="Native copy method" value={copyMode} onChange={event => {setCopyMode(event.target.value);setReview(null);}}>
        {['copy','clone','copy-file-range','link'].map(value => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>}
      {operation!=='verify' && <>{select('manifest_checksums',['NONE','CRC32C','SHA224','SHA256','SHA384','SHA512'])}{select('sync_method',['fsync','syncfs'])}
        <TextField disabled={busy} size="small" type="number" label="Timeout seconds" value={options.timeout_seconds} onChange={event => edit('timeout_seconds',Number(event.target.value))} />
        {(backup ? ['create_slot','no_slot','write_recovery_conf','verify_page_checksums','progress','estimate_size','sync'] : ['sync']).map(name => <FormControlLabel key={name} label={name.replaceAll('_',' ')}
          control={<Checkbox disabled={busy} checked={options[name]} onChange={event => edit(name,event.target.checked)} />} />)}</>}
    </Box>
    <Button disabled={busy || (operation==='combine' ? inputs.length<2 : operation!=='full_backup' && !inputs.length)} onClick={prepare}>Review native operation</Button>
    {review && <Box sx={{my:1}}>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" sx={{whiteSpace:'pre-wrap',overflow:'auto',maxHeight:280}} aria-label="Native backup review">{JSON.stringify({operation:review.operation,source:review.source,options:review.options,inputs:review.inputs,tools:review.tool_identities},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={() => run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},result => {setReceipt(result);setReview(current => ({...current,state:result.state}));})}>Confirm and start reviewed operation</Button>
    </Box>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={receipt.state==='verified' ? 'success' : ['failed','unknown','not_dispatched'].includes(receipt.state) ? 'warning' : 'info'}>
        Job {receipt.job_id}: {receipt.state}. {receipt.observation_blocker}
        {receipt.state==='verified' && ` Native file verification: ${receipt.verification_scope?.files ? 'yes' : 'no'}; WAL verification: ${receipt.verification_scope?.wal ? 'yes' : 'no'}. Recovery drill: ${receipt.recovery_drill_complete ? 'complete' : 'not completed'}.`}
      </Alert>
      <Button disabled={busy} onClick={() => run('status',{job_id:receipt.job_id},setReceipt)}>Refresh receipt</Button>
      <Button onClick={download}>Download receipt</Button>
      <Button disabled={busy || (!ACTIVE.has(receipt.state) && receipt.state!=='reviewed')} onClick={() => run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel native job</Button>
      <Box component="details"><summary>Native observations and artifact location</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',overflow:'auto',maxHeight:400}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
PostgresqlContinuity.propTypes={post:PropTypes.func.isRequired};
