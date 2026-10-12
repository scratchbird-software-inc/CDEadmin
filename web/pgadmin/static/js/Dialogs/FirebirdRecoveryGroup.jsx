// ScratchRobin: explicitly reviewed, independently authorized Firebird recovery.
import {useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import gettext from 'sources/gettext';
import FirebirdLimboObservation from './FirebirdLimboObservation';

const emptyParticipant = () => ({server_id: '', database_target_id: '', transaction_id: ''});

export default function FirebirdRecoveryGroup({post}) {
  const [endpoints, setEndpoints] = useState([]);
  const [participants, setParticipants] = useState([emptyParticipant()]);
  const [decision, setDecision] = useState('rollback');
  const [group, setGroup] = useState(null);
  const [lookup, setLookup] = useState('');
  const [confirmations, setConfirmations] = useState([]);
  const [reviewed, setReviewed] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const invoke = async (action, request, accept) => {
    setBusy(true); setError('');
    try { accept(await post({action, request})); }
    catch (e) { setError(e.message || gettext('Recovery request failed. Inspect the retained group before any further decision.')); }
    finally { setBusy(false); }
  };
  const acceptReview = (value) => {
    setGroup(value); setLookup(value.group_id); setReviewed(false);
    setAttempted(value.state !== 'reviewed');
    setConfirmations(value.participants.map(() => ({database: '', transaction_id: ''})));
  };
  const change = (index, key, value) => setParticipants((items) => items.map((item, i) =>
    i === index ? {...item, [key]: value, ...(key === 'server_id' ? {database_target_id: ''} : {})} : item));
  const confirm = (index, key, value) => setConfirmations((items) => items.map((item, i) =>
    i === index ? {...item, [key]: value} : item));
  const ready = group?.state === 'reviewed' && reviewed && !attempted &&
    group.participants.every((item, i) => confirmations[i]?.database === item.database &&
      confirmations[i]?.transaction_id === item.transaction_id);
  return <Box component="section" aria-label={gettext('Coordinated Firebird recovery')}
    sx={{p: 2, overflow: 'auto', minWidth: 0}}>
    <Box component="h3">{gettext('Coordinated Firebird recovery')}</Box>
    <Alert severity="warning">{gettext('Select each participant independently. Stored transaction paths do not authorize access. Decisions run separately; a partial or lost response does not establish a global outcome.')}</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display: 'flex', gap: 1, my: 2}}>
      <TextField label={gettext('Recorded recovery group ID')} value={lookup}
        onChange={(e) => setLookup(e.target.value)} disabled={busy} />
      <Button disabled={busy || !lookup} onClick={() => invoke('firebird_recovery_status',
        {group_id: lookup}, acceptReview)}>{gettext('Read recorded status')}</Button>
    </Box>
    {!group && <>
      <Button disabled={busy} onClick={() => invoke('firebird_recovery_targets', {},
        (value) => setEndpoints(value.endpoints))}>{gettext('Load owned Firebird endpoints')}</Button>
      <TextField select label={gettext('Recovery decision')} value={decision} disabled={busy}
        onChange={(e) => setDecision(e.target.value)}>
        <MenuItem value="rollback">{gettext('Rollback')}</MenuItem>
        <MenuItem value="commit">{gettext('Commit')}</MenuItem>
      </TextField>
      {participants.map((item, i) => <Box key={i} sx={{display: 'flex', gap: 1, my: 2, flexWrap: 'wrap'}}>
        <TextField select label={gettext('Participant %s endpoint', i + 1)}
          value={item.server_id} disabled={busy}
          onChange={(e) => change(i, 'server_id', Number(e.target.value))}>
          {endpoints.map((ep) => <MenuItem key={ep.server_id} value={ep.server_id}>{ep.name}</MenuItem>)}
        </TextField>
        <TextField select label={gettext('Participant %s database', i + 1)}
          value={item.database_target_id} disabled={busy}
          onChange={(e) => change(i, 'database_target_id', e.target.value)}>
          {(endpoints.find((ep) => ep.server_id === item.server_id)?.targets || []).map((target) =>
            <MenuItem key={target.target_id} value={target.target_id}>{target.display_name} — {target.database}</MenuItem>)}
        </TextField>
        <TextField label={gettext('Participant %s transaction ID', i + 1)}
          value={item.transaction_id} disabled={busy}
          onChange={(e) => change(i, 'transaction_id', e.target.value)} />
        <Button disabled={busy || participants.length === 1}
          onClick={() => setParticipants((items) => items.filter((_, index) => index !== i))}>
          {gettext('Remove participant %s', i + 1)}</Button>
      </Box>)}
      <Button disabled={busy || participants.length >= 64}
        onClick={() => setParticipants((items) => [...items, emptyParticipant()])}>{gettext('Add participant')}</Button>
      <Button disabled={busy || participants.some((p) => !p.server_id || !p.database_target_id || !p.transaction_id)}
        onClick={() => invoke('firebird_recovery_preview', {decision, participants}, acceptReview)}>
        {gettext('Inspect and review participants')}</Button>
    </>}
    {group && <>
      <Box component="p" role="status">{gettext('Recorded workflow state: %s', group.state)}</Box>
      <Box component="p">{gettext('Requested decision: %s', group.decision)}</Box>
      {group.dispatch_may_be_interrupted && <Alert severity="warning">{gettext('Dispatch may still be running or may have been interrupted. Reading this record does not retry a decision.')}</Alert>}
      {group.participants.map((item, i) => <Box key={i} sx={{my: 2}}>
        <Box component="h4">{item.server_name}: {item.database} — {item.transaction_id}</Box>
        <Box component="p">{gettext('Participant state: %s', item.state)}</Box>
        {Number.isFinite(item.observed_at) && <Box component="p">
          {gettext('Inspected at: %s', new Date(item.observed_at * 1000).toISOString())}</Box>}
        {item.state === 'unknown_outcome' && <Alert severity="warning">{gettext('This participant has an uncertain outcome. The inspection below may predate dispatch. Do not infer the outcome or replay the decision from this record.')}</Alert>}
        <FirebirdLimboObservation observation={item.receipt || {
          operation_id: 'inspect_limbo', database: item.database,
          transactions: [item.observation], inventory_complete: true, attachment_released: true,
        }} />
        {group.state === 'reviewed' && <Box sx={{display: 'flex', gap: 1}}>
          <TextField label={gettext('Confirm participant %s database', i + 1)} disabled={busy || attempted}
            value={confirmations[i]?.database || ''} onChange={(e) => confirm(i, 'database', e.target.value)} />
          <TextField label={gettext('Confirm participant %s transaction ID', i + 1)} disabled={busy || attempted}
            value={confirmations[i]?.transaction_id || ''} onChange={(e) => confirm(i, 'transaction_id', e.target.value)} />
        </Box>}
      </Box>)}
      {group.state === 'reviewed' && <>
        <FormControlLabel control={<Checkbox checked={reviewed} disabled={busy || attempted}
          onChange={(e) => setReviewed(e.target.checked)} />} label={gettext('Coordinator decision and every participant reviewed')} />
        <Button disabled={busy || !ready} onClick={() => {
          setAttempted(true);
          invoke('firebird_recovery_apply', {group_id: group.group_id,
            review_digest: group.review_digest, decision: group.decision,
            coordinator_reviewed: reviewed, confirmations}, setGroup);
        }}>{gettext('Apply reviewed recovery decision')}</Button>
      </>}
      <Button disabled={busy} onClick={() => {setGroup(null); setAttempted(false);}}>
        {gettext('Start a separate review')}</Button>
    </>}
  </Box>;
}
FirebirdRecoveryGroup.propTypes = {post: PropTypes.func.isRequired};
