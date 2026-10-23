import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, TextField} from '@mui/material';

export default function MySQLPhysicalBatchRetention({post, credentials, scopeJobId, busy, onBusy, onChanged}) {
  const [policy, setPolicy] = useState({retention_days: 30, keep_latest: 2});
  const [batch, setBatch] = useState(null), [listing, setListing] = useState(null);
  const [confirmed, setConfirmed] = useState(false), [identity, setIdentity] = useState('');
  const [error, setError] = useState(''), [running, setRunning] = useState(false);
  const [needsInspection, setNeedsInspection] = useState(false);
  const [scheduleOptions, setScheduleOptions] = useState({interval_seconds: 3600, expires_after_days: 30});
  const [schedule, setSchedule] = useState(null), [schedules, setSchedules] = useState(null);
  const [scheduleIdentity, setScheduleIdentity] = useState(''), [scheduleConfirmed, setScheduleConfirmed] = useState(false), [delegate, setDelegate] = useState(false);
  const live = useRef(true), stop = useRef(true);
  useEffect(() => {live.current = true; return () => {live.current = false; stop.current = true;};}, []);
  const reset = value => {setBatch(value); setConfirmed(false); setIdentity(''); setNeedsInspection(!!value?.needs_observation || value?.state === 'running');};
  const resetSchedule = value => {setSchedule(value); setScheduleIdentity(''); setScheduleConfirmed(false); setDelegate(false);};
  useEffect(() => {reset(null); resetSchedule(null); stop.current = true;}, [scopeJobId]);
  const request = (action, body) => post({action: 'mysql_physical_retention_batch_' + action, request: body});
  const run = async work => {
    onBusy(true); setError('');
    try {await work();}
    catch(failure) {
      stop.current = true;
      if(live.current) {setError(failure.response?.data?.errormsg || failure.message || 'Inspect the original batch before continuing.'); setConfirmed(false); setIdentity(''); setNeedsInspection(true); setScheduleConfirmed(false); setScheduleIdentity(''); setDelegate(false);}
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
  const scheduled = schedule?.state === 'enabled' && batch?.options?.scheduled_policy_id === schedule.job_id;
  const scheduleApproved = scheduleConfirmed && scheduleIdentity === schedule?.job_id;
  const scheduleApproval = () => ({job_id: schedule.job_id, confirmed: true, schedule_confirmation: scheduleIdentity});
  const scheduleRequest = (action, body) => run(async () => {
    const value = await post({action: 'mysql_physical_retention_schedule_' + action, request: body});
    if(live.current) {if(action === 'list') setSchedules(value); else {resetSchedule(value); await onChanged();}}
  });
  return <Box component="section" aria-label="Physical retention policy" sx={{my: 2}}>
    <Alert severity="info">Review an age policy for this exact native source, SSH host and workspace. Keep the newest verified full-backup chains and all inputs of protected jobs. Each batch contains at most 100 fixed jobs. Pausing or closing stops future manual steps; an admitted host removal can continue. Background scans require a separately confirmed schedule.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <TextField size="small" type="number" label="Physical retention days" value={policy.retention_days} disabled={busy} onChange={event => {setPolicy({...policy, retention_days: Number(event.target.value)}); reset(null); resetSchedule(null);}} />
    <TextField size="small" type="number" label="Minimum full-backup chains" value={policy.keep_latest} disabled={busy} onChange={event => {setPolicy({...policy, keep_latest: Number(event.target.value)}); reset(null); resetSchedule(null);}} />
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
        <Button disabled={busy || scheduled || needsInspection || !approved || batch.cancellation_requested || !['reviewed', 'paused'].includes(batch.state)} onClick={() => advance(false)}>Run reviewed physical retention batch</Button>
        <Button disabled={!running} onClick={() => {stop.current = true;}}>Pause after current physical removal</Button>
        <Button disabled={busy || scheduled || terminal} onClick={() => observe('reconcile', {job_id: batch.job_id, credentials})}>Inspect current physical batch step</Button>
        <Button disabled={busy || scheduled || needsInspection || !approved || batch.state !== 'interrupted'} onClick={() => advance(true)}>Resume original physical batch step</Button>
        <Button disabled={busy || scheduled || !approved || terminal} onClick={() => observe('cancel', approval())}>Invalidate unused physical batch reviews</Button>
      </>}
    </>}
    <Box component="section" aria-label="Scheduled physical retention" sx={{my: 2}}>
      <Alert severity="warning">A confirmed schedule includes later jobs in this native scope and continues without an open viewer. SSH access is encrypted with configured worker keys. Disable stops future admissions; admitted removal may continue. Interrupted occurrences require inspection and a new policy review. Existing policies stay enabled until disabled.</Alert>
      <TextField size="small" type="number" label="Physical retention scan seconds" value={scheduleOptions.interval_seconds} disabled={busy} onChange={event => {setScheduleOptions({...scheduleOptions, interval_seconds: Number(event.target.value)}); resetSchedule(null);}} />
      <TextField size="small" type="number" label="Physical retention schedule lifetime days" value={scheduleOptions.expires_after_days} disabled={busy} onChange={event => {setScheduleOptions({...scheduleOptions, expires_after_days: Number(event.target.value)}); resetSchedule(null);}} />
      <Button disabled={busy || !scopeJobId} onClick={() => scheduleRequest('review', {scope_job_id: scopeJobId, options: {policy, ...scheduleOptions}, credentials})}>Review physical retention schedule</Button>
      <Button disabled={busy} onClick={() => scheduleRequest('list', {offset: 0, limit: 100})}>Load physical retention schedules</Button>
      {schedules && <Box>{schedules.jobs.map(job => <Button key={job.job_id} disabled={busy} aria-label={'Inspect physical retention schedule ' + job.job_id} onClick={() => scheduleRequest('status', {job_id: job.job_id})}>{job.job_id}: {job.state}</Button>)}</Box>}
      {schedules?.more && <Button disabled={busy} onClick={() => run(async () => {
        const value = await post({action: 'mysql_physical_retention_schedule_list', request: {offset: schedules.offset + schedules.limit, limit: schedules.limit}});
        if(live.current) setSchedules(current => ({...value, jobs: [...current.jobs, ...value.jobs]}));
      })}>More physical retention schedules</Button>}
      {schedule && <>
        <Box component="pre" aria-label="Physical retention schedule receipt" sx={{whiteSpace: 'pre-wrap', maxHeight: 320, overflow: 'auto'}}>{JSON.stringify(schedule, null, 2)}</Box>
        <TextField size="small" label="Exact physical retention schedule UUID" value={scheduleIdentity} disabled={busy} onChange={event => setScheduleIdentity(event.target.value)} />
        <FormControlLabel label="I confirm this exact physical retention schedule." control={<Checkbox checked={scheduleConfirmed} disabled={busy} onChange={event => setScheduleConfirmed(event.target.checked)} />} />
        <FormControlLabel label="Delegate SSH authentication encrypted for this expiring physical policy." control={<Checkbox checked={delegate} disabled={busy || schedule.state !== 'reviewed'} onChange={event => setDelegate(event.target.checked)} />} />
        <Button disabled={busy || !scheduleApproved || !delegate || schedule.state !== 'reviewed'} onClick={() => scheduleRequest('enable', {...scheduleApproval(), review_digest: schedule.review_digest, delegate_ssh_credentials: true, credentials})}>Enable reviewed physical retention schedule</Button>
        <Button disabled={busy} onClick={() => scheduleRequest('status', {job_id: schedule.job_id})}>Refresh physical retention schedule</Button>
        <Button disabled={busy || !scheduleApproved || ['disabled', 'expired'].includes(schedule.state)} onClick={() => scheduleRequest('disable', scheduleApproval())}>Disable physical retention schedule</Button>
        <Button disabled={busy || !scheduleApproved || schedule.state !== 'enabled'} onClick={() => scheduleRequest('scan', scheduleApproval())}>Request due physical retention scan</Button>
        <Button disabled={busy || !scheduleApproved || !schedule.ssh_delegation_present} onClick={() => scheduleRequest('rotate', scheduleApproval())}>Rotate physical retention SSH envelope</Button>
        <Button disabled={busy || !schedule.last_occurrence_id} onClick={() => observe('status', {job_id: schedule.last_occurrence_id})}>Inspect scheduled physical occurrence</Button>
      </>}
    </Box>
  </Box>;
}
MySQLPhysicalBatchRetention.propTypes = {post: PropTypes.func.isRequired, credentials: PropTypes.object.isRequired,
  scopeJobId: PropTypes.string, busy: PropTypes.bool.isRequired, onBusy: PropTypes.func.isRequired, onChanged: PropTypes.func.isRequired};
