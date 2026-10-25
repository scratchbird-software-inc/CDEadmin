import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';

export default function MySQLRecoveryCutover({run, deployment, credentials, busy}) {
  const [selection, setSelection] = useState({target_server_id: '', acceptance_job_id: '', source_fence_job_id: '', target_confirmation: '', event_scheduler: 'OFF', acceptance_scope_acknowledged: false});
  const [review, setReview] = useState(null), [receipt, setReceipt] = useState(null), [page, setPage] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const runRef = useRef(run); runRef.current = run;
  useEffect(() => {
    if(!['dispatching', 'active', 'cancel_requested'].includes(receipt?.state)) return undefined;
    let live = true, pending = false;
    const timer = setInterval(async () => {
      if(pending) return;
      pending = true;
      try {await runRef.current('cutover_status', {job_id: receipt.job_id}, value => {if(live) setReceipt(value);});}
      finally {pending = false;}
    }, 1500);
    return () => {live = false; clearInterval(timer);};
  }, [receipt?.job_id, receipt?.state]);
  const change = (key, value) => {setSelection(current => ({...current, [key]: value})); setReview(null); setConfirmed(false);};
  return <Box component="section" aria-label="Recovered service activation">
    <Alert severity="warning">Register the permanent listener as a normal MySQL target and run independent dump acceptance there. Stop and disable the original source through reviewed host controls. Activation repeats the selected data and definition checks under native locks, persists writable startup, and changes the live read-only flags. Application routing and boot enablement remain explicit host/application choices.</Alert>
    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', my: 1}}>
      {['target_server_id', 'acceptance_job_id', 'source_fence_job_id', 'target_confirmation'].map(key => <TextField key={key} size="small" disabled={busy}
        label={{target_server_id: 'Registered recovered target ID', acceptance_job_id: 'Matched target acceptance job', source_fence_job_id: 'Original source disable job', target_confirmation: 'Confirm recovered UUID'}[key]}
        type={key === 'target_server_id' ? 'number' : 'text'} value={selection[key]} onChange={event => change(key, key === 'target_server_id' ? Number(event.target.value) : event.target.value)} />)}
      <TextField select size="small" label="Activated event scheduler" value={selection.event_scheduler} disabled={busy} onChange={event => change('event_scheduler', event.target.value)}>
        <MenuItem value="OFF">Keep events off</MenuItem><MenuItem value="ON">Enable native events</MenuItem>
      </TextField>
    </Box>
    <FormControlLabel label="I acknowledge the selected expected-dump scope and its exclusions" control={<Checkbox disabled={busy} checked={selection.acceptance_scope_acknowledged} onChange={event => change('acceptance_scope_acknowledged', event.target.checked)} />} />
    <Button disabled={busy || !selection.acceptance_scope_acknowledged} onClick={() => run('cutover_review', {...selection, deployment_job_id: deployment.job_id, credentials}, value => {setReview(value); setReceipt(value); setConfirmed(false);})}>Review recovered service activation</Button>
    <Button disabled={busy} onClick={() => run('cutover_list', {offset: 0, limit: 25}, setPage)}>Load activation receipts</Button>
    {page?.jobs.map(value => <Button disabled={busy} key={value.job_id} onClick={() => {setReceipt(value); setReview(null); setConfirmed(false);}}>Inspect activation {value.job_id}: {value.state}</Button>)}
    {review && <>
      <Box component="pre" aria-label="Recovered activation review" sx={{whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto'}}>{JSON.stringify(review, null, 2)}</Box>
      <FormControlLabel label="Confirm this exact recovered activation review" control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || !confirmed || review.state !== 'reviewed'} onClick={() => run('cutover_start', {job_id: review.job_id, review_digest: review.review_digest, confirmed: true, credentials}, value => {setReceipt(value); setReview(current => ({...current, state: value.state})); setConfirmed(false);})}>Confirm and activate recovered service</Button>
    </>}
    {receipt && <>
      <Box component="pre" aria-label="Recovered activation receipt" sx={{whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto'}}>{JSON.stringify(receipt, null, 2)}</Box>
      <Button disabled={busy} onClick={() => run('cutover_reconcile', {job_id: receipt.job_id, credentials}, setReceipt)}>Observe activation without replay</Button>
      <Button disabled={busy || !['reviewed', 'dispatching', 'active', 'cancel_requested'].includes(receipt.state) || receipt.activation_may_have_dispatched === true} onClick={() => run('cutover_cancel', {job_id: receipt.job_id}, setReceipt)}>Cancel before startup policy claim</Button>
      <Button disabled={busy} onClick={() => run('cutover_observe_utilities', {job_id: receipt.job_id, credentials}, setReceipt)}>Inspect original activation utility</Button>
    </>}
  </Box>;
}
MySQLRecoveryCutover.propTypes = {run: PropTypes.func.isRequired, deployment: PropTypes.object.isRequired, credentials: PropTypes.object.isRequired, busy: PropTypes.bool.isRequired};
