import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,Table,TableBody,TableCell,TableHead,TableRow,TextField} from '@mui/material';

export default function MySQLRetentionSchedule({post,prefix,sourceArchive,days,keep,onOccurrence}) {
  const [interval,setIntervalMinutes]=useState(60),[lifetime,setLifetime]=useState(30);
  const [review,setReview]=useState(null),[ack,setAck]=useState(false),[receipt,setReceipt]=useState(null),[page,setPage]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0);
  useEffect(() => {
    generation.current++;setReview(null);setReceipt(null);setPage(null);setAck(false);setBusy(false);setError('');
    return () => {generation.current++;};
  },[post,prefix]);
  useEffect(() => {generation.current++;setReview(null);setAck(false);setBusy(false);},[days,keep,interval,lifetime,sourceArchive?.job_id]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const result=await post({action:prefix+'retention_schedule_'+action,request});if(token===generation.current)accept(result);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(() => {
    if(receipt?.state!=='enabled')return;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const value=await post({action:prefix+'retention_schedule_status',request:{job_id:receipt.job_id}});if(live)setReceipt(value);}
      catch(failure) {if(live)setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending=false;}
    },2000);
    return () => {live=false;clearInterval(timer);};
  },[post,prefix,receipt?.job_id,receipt?.state]);
  const retained=sourceArchive?.source?.server_uuid && ['completed','artifact_verified'].includes(sourceArchive.state) && !sourceArchive.artifact_removed && !sourceArchive.artifact_removal;
  const load=offset => run('list',{offset,limit:25},setPage);
  return <Box component="details" sx={{my:1}}><summary>Scheduled archive retention</summary>
    <Alert severity="warning">A confirmed policy authorizes future scans and removal of eligible archives from its exact source, principal and role, including archives created later. Protect all files needed for recovery. Backup dependencies and recoverability are not inferred.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {retained ? <Alert severity="info">Schedule source: {sourceArchive.source.server_uuid} / {sourceArchive.source.authenticated_principal} / {sourceArchive.source.active_role}. Archive kind: {prefix==='mysql_raw_binlog_' ? 'Raw' : 'MySQL Shell'}.</Alert> : <Alert severity="info">Inspect a retained verified archive to select the native source for a new policy.</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <TextField size="small" type="number" label="Retention scan interval in minutes" value={interval} onChange={event => setIntervalMinutes(Number(event.target.value))} />
      <TextField size="small" type="number" label="Retention policy lifetime in days" value={lifetime} onChange={event => setLifetime(Number(event.target.value))} />
      <Button disabled={busy || !retained} onClick={() => run('review',{anchor_job_id:sourceArchive.job_id,
        options:{policy:{retention_days:days,keep_latest:keep},interval_seconds:interval*60,expires_after_days:lifetime}},value => {setReview(value);setAck(false);})}>Review scheduled retention policy</Button>
      <Button disabled={busy} onClick={() => load(0)}>Load scheduled retention policies</Button>
    </Box>
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Scheduled retention review" sx={{whiteSpace:'pre-wrap',maxHeight:240,overflow:'auto'}}>{JSON.stringify(review,null,2)}</Box>
      <FormControlLabel control={<Checkbox checked={ack} disabled={busy || review.state!=='reviewed'} onChange={event => setAck(event.target.checked)} />} label="Authorize future archive removal under this reviewed policy" />
      <Button disabled={busy || !ack || review.state!=='reviewed'} onClick={() => run('enable',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value => {setReceipt(value);setReview(current => ({...current,state:value.state}));})}>Confirm and enable scheduled retention</Button>
    </Box>}
    {page && <Box>
      <Table size="small" aria-label="Scheduled retention policies"><TableHead><TableRow><TableCell>Policy</TableCell><TableCell>State</TableCell><TableCell>Source</TableCell><TableCell>Inspect</TableCell></TableRow></TableHead><TableBody>
        {page.jobs.map(job => <TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{job.state}</TableCell><TableCell>{job.source.server_uuid}</TableCell><TableCell><Button disabled={busy} onClick={() => run('status',{job_id:job.job_id},setReceipt)}>Inspect policy {job.job_id}</Button></TableCell></TableRow>)}
      </TableBody></Table>
      <Button disabled={busy || page.offset===0} onClick={() => load(Math.max(0,page.offset-25))}>Previous retention policies</Button>
      <Button disabled={busy || !page.more} onClick={() => load(page.offset+25)}>Next retention policies</Button>
      {page.unavailable_job_ids?.length>0 && <Alert severity="warning">Some policy receipts could not be read.</Alert>}
    </Box>}
    {receipt && <Box>
      <Alert severity={receipt.state==='enabled' ? 'info' : 'warning'}>Scheduled retention {receipt.job_id}: {receipt.state}. {receipt.error_message || 'Interrupted removals require explicit reconciliation and a new policy review.'}</Alert>
      <Button disabled={busy} onClick={() => run('status',{job_id:receipt.job_id},setReceipt)}>Refresh scheduled retention</Button>
      <Button disabled={busy || receipt.state!=='enabled'} onClick={() => run('scan',{job_id:receipt.job_id,confirmed:true},setReceipt)}>Scan archive policy now</Button>
      <Button disabled={busy || receipt.state==='disabled'} onClick={() => run('disable',{job_id:receipt.job_id,confirmed:true},setReceipt)}>Disable scheduled retention</Button>
      {receipt.last_occurrence && <Button disabled={busy} onClick={() => onOccurrence(receipt.last_occurrence)}>Inspect scheduled retention occurrence</Button>}
      <Box component="pre" aria-label="Scheduled retention receipt" sx={{whiteSpace:'pre-wrap',maxHeight:280,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box>
    </Box>}
  </Box>;
}
MySQLRetentionSchedule.propTypes={post:PropTypes.func.isRequired,prefix:PropTypes.string.isRequired,sourceArchive:PropTypes.object,days:PropTypes.number.isRequired,keep:PropTypes.number.isRequired,onOccurrence:PropTypes.func.isRequired};
