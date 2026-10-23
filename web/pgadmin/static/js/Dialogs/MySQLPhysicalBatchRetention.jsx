import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, TextField} from '@mui/material';

export default function MySQLPhysicalBatchRetention({post, credentials, scopeJobId, busy, onBusy, onChanged}) {
  const [policy, setPolicy] = useState({retention_days: 30, keep_latest: 2});
  const [batch, setBatch] = useState(null), [listing, setListing] = useState(null);
  const [confirmed, setConfirmed] = useState(false), [identity, setIdentity] = useState('');
  const [error, setError] = useState(''), [running, setRunning] = useState(false);
  const [needsInspection, setNeedsInspection] = useState(false);
  const live = useRef(true), stop = useRef(true);
  useEffect(() => {live.current = true; return () => {live.current = false; stop.current = true;};}, []);
  const reset = value => {setBatch(value); setConfirmed(false); setIdentity(''); setNeedsInspection(!!value?.needs_observation || value?.state === 'running');};
  useEffect(() => {reset(null); stop.current = true;}, [scopeJobId]);
  const request = (action, body) => post({action: 'mysql_physical_retention_batch_' + action, request: body});
  const run = async work => {
    onBusy(true); setError('');
    try {await work();}
    catch(failure) {
      stop.current = true;
      if(live.current) {setError(failure.response?.data?.errormsg || failure.message || 'Inspect the original batch before continuing.'); setConfirmed(false); setIdentity(''); setNeedsInspection(true);}
    } finally {if(live.current) {setRunning(false); onBusy(false);}}
  };
  const observe = (action, body) => run(async () => {
    const value = await request(action, body);
    if(live.current) {reset(value); await onChanged();}
  });
  const approval = () => ({job_id: batch.job_id, review_digest: batch.review_digest, confirmed: true, batch_confirmation: identity, credentials});
  const advance = resume => run(async () => {
    stop.current = false; setRunning(true);
    let value = batch, operation = resume ? 'resume' : 'advance';
    do {
      value = await request(operation, approval());
      if(!live.current) return;
      setBatch(value);
      operation = 'advance';
    } while(!stop.current && value.state === 'paused');
    if(live.current) {reset(value); await onChanged();}
  });
  const approved = confirmed && identity === batch?.job_id;
  const terminal = ['completed', 'cancelled', 'nothing_eligible'].includes(batch?.state);
  return <Box component="section" aria-label="Physical retention policy" sx={{my: 2}}>
    <Alert severity="info">Review an age policy for this exact native source, SSH host and workspace. Keep the newest verified full-backup chains and all inputs of protected jobs. Each batch contains at most 100 fixed jobs. Pausing or closing stops future steps; an admitted host removal can continue. No automatic schedule or retry is enabled.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <TextField size="small" type="number" label="Physical retention days" value={policy.retention_days} disabled={busy} onChange={event => {setPolicy({...policy, retention_days: Number(event.target.value)}); reset(null);}} />
    <TextField size="small" type="number" label="Minimum full-backup chains" value={policy.keep_latest} disabled={busy} onChange={event => {setPolicy({...policy, keep_latest: Number(event.target.value)}); reset(null);}} />
    <Button disabled={busy || !scopeJobId} onClick={() => observe('review', {scope_job_id: scopeJobId, policy, credentials})}>Review physical retention policy</Button>
    <Button disabled={busy} onClick={() => run(async () => {const value = await request('list', {offset: 0, limit: 25}); if(live.current) setListing(value);})}>Load physical retention batches</Button>
    {listing && <Box aria-label="Physical retention batches">
      {listing.jobs.map(job => <Button key={job.job_id} disabled={busy} aria-label={'Inspect physical retention batch ' + job.job_id} onClick={() => observe('status', {job_id: job.job_id})}>{job.job_id}: {job.state}</Button>)}
      {listing.more && <Button disabled={busy} onClick={() => run(async () => {
        const value = await request('list', {offset: listing.offset + listing.limit, limit: listing.limit});
        if(live.current) setListing(current => ({...value, jobs: [...current.jobs, ...value.jobs]}));
      })}>More physical retention batches</Button>}
    </Box>}
    {batch && <>
      <Box component="pre" aria-label="Physical retention batch receipt" sx={{whiteSpace: 'pre-wrap', maxHeight: 360, overflow: 'auto'}}>{JSON.stringify(batch, null, 2)}</Box>
      {batch.job_id && <>
        <TextField size="small" label="Exact physical retention batch UUID" value={identity} disabled={busy} onChange={event => setIdentity(event.target.value)} />
        <FormControlLabel label="I confirm this exact physical retention batch." control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={busy || needsInspection || !approved || batch.cancellation_requested || !['reviewed', 'paused'].includes(batch.state)} onClick={() => advance(false)}>Run reviewed physical retention batch</Button>
        <Button disabled={!running} onClick={() => {stop.current = true;}}>Pause after current physical removal</Button>
        <Button disabled={busy || terminal} onClick={() => observe('reconcile', {job_id: batch.job_id, credentials})}>Inspect current physical batch step</Button>
        <Button disabled={busy || needsInspection || !approved || batch.state !== 'interrupted'} onClick={() => advance(true)}>Resume original physical batch step</Button>
        <Button disabled={busy || !approved || terminal} onClick={() => observe('cancel', approval())}>Invalidate unused physical batch reviews</Button>
      </>}
    </>}
  </Box>;
}
MySQLPhysicalBatchRetention.propTypes = {post: PropTypes.func.isRequired, credentials: PropTypes.object.isRequired,
  scopeJobId: PropTypes.string, busy: PropTypes.bool.isRequired, onBusy: PropTypes.func.isRequired, onChanged: PropTypes.func.isRequired};
