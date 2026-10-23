import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';

export default function MySQLPhysicalBackupSchedule({post, physical, credentials, busy, onBusy}) {
  const [timing, setTiming] = useState({interval_seconds: 86400, expires_after_days: 30});
  const [drill, setDrill] = useState(false), [drillOptions, setDrillOptions] = useState({mysqld: '/usr/sbin/mysqld', gtid_mode: 'ON', timeout_seconds: 300});
  const [policy, setPolicy] = useState(null), [policies, setPolicies] = useState(null), [occurrences, setOccurrences] = useState(null), [occurrence, setOccurrence] = useState(null);
  const [identity, setIdentity] = useState(''), [confirmed, setConfirmed] = useState(false), [delegate, setDelegate] = useState(false), [error, setError] = useState('');
  const live = useRef(true);
  useEffect(() => {live.current = true; return () => {live.current = false;};}, []);
  const reset = value => {if(value?.job_id !== policy?.job_id) {setOccurrences(null); setOccurrence(null);} setPolicy(value); setIdentity(''); setConfirmed(false); setDelegate(false);};
  useEffect(() => {reset(null);}, [physical]);
  const run = async (action, request, accept = reset) => {
    onBusy(true); setError('');
    try {const value = await post({action: 'mysql_physical_backup_schedule_' + action, request}); if(live.current) accept(value);}
    catch(failure) {if(live.current) {setError(failure.response?.data?.errormsg || failure.message || 'Inspect the original scheduled work.'); setIdentity(''); setConfirmed(false); setDelegate(false);}}
    finally {if(live.current) onBusy(false);}
  };
  const approval = () => ({job_id: policy.job_id, schedule_confirmation: identity, confirmed: true});
  const approved = identity === policy?.job_id && confirmed;
  const change = value => {setTiming({...timing, ...value}); reset(null);};
  return <Box component="section" aria-label="Recurring physical backups" sx={{my: 2}}>
    <Alert severity="warning">Schedule full native backups independently of this viewer. This delegates SSH and the registered SQL password encrypted until expiry or revocation, and authorizes native backup/read locks and archive protection. An optional startup drill uses separate prepared and copied files, a read-only MySQL and a private Unix socket, then stops it. SQL startup does not establish full data/definition recovery acceptance.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <TextField size="small" type="number" label="Full backup interval seconds" value={timing.interval_seconds} disabled={busy} onChange={event => change({interval_seconds: Number(event.target.value)})} />
    <TextField size="small" type="number" label="Full backup policy lifetime days" value={timing.expires_after_days} disabled={busy} onChange={event => change({expires_after_days: Number(event.target.value)})} />
    <FormControlLabel label="Run an isolated native startup drill after each backup" control={<Checkbox checked={drill} disabled={busy} onChange={event => {setDrill(event.target.checked); reset(null);}} />} />
    {drill && <>
      <TextField size="small" label="Startup drill mysqld" value={drillOptions.mysqld} disabled={busy} onChange={event => {setDrillOptions({...drillOptions, mysqld: event.target.value}); reset(null);}} />
      <TextField size="small" type="number" label="Startup drill lifetime seconds" value={drillOptions.timeout_seconds} disabled={busy} onChange={event => {setDrillOptions({...drillOptions, timeout_seconds: Number(event.target.value)}); reset(null);}} />
      <TextField select size="small" label="Startup drill GTID mode" value={drillOptions.gtid_mode} disabled={busy} onChange={event => {setDrillOptions({...drillOptions, gtid_mode: event.target.value}); reset(null);}}>
        {['OFF', 'OFF_PERMISSIVE', 'ON_PERMISSIVE', 'ON'].map(value => <MenuItem value={value} key={value}>{value}</MenuItem>)}
      </TextField>
    </>}
    <Button disabled={busy || physical.phase !== 'backup' || !physical.accept_release_candidate} onClick={() => run('review', {options: {physical, drill: drill ? drillOptions : null, ...timing}, credentials})}>Review recurring physical backup policy</Button>
    <Button disabled={busy} onClick={() => run('list', {offset: 0, limit: 25}, setPolicies)}>Load recurring physical backup policies</Button>
    {policies && <Box>{policies.jobs.map(value => <Button key={value.job_id} disabled={busy} aria-label={'Inspect recurring backup policy ' + value.job_id} onClick={() => {setOccurrences(null); setOccurrence(null); run('status', {job_id: value.job_id});}}>{value.job_id}: {value.state}</Button>)}</Box>}
    {policies?.more && <Button disabled={busy} onClick={() => run('list', {offset: policies.offset + policies.limit, limit: policies.limit}, value => setPolicies(current => ({...value, jobs: [...current.jobs, ...value.jobs]})))}>More recurring backup policies</Button>}
    {policy && <>
      <Box component="pre" aria-label="Recurring physical backup policy receipt" sx={{whiteSpace: 'pre-wrap', maxHeight: 320, overflow: 'auto'}}>{JSON.stringify(policy, null, 2)}</Box>
      <TextField size="small" label="Exact recurring backup policy UUID" value={identity} disabled={busy} onChange={event => setIdentity(event.target.value)} />
      <FormControlLabel label="I confirm this exact recurring native backup policy." control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} />
      <FormControlLabel label="Delegate SSH and the registered SQL password encrypted for this expiring backup policy." control={<Checkbox checked={delegate} disabled={busy || policy.state !== 'reviewed'} onChange={event => setDelegate(event.target.checked)} />} />
      <Button disabled={busy || !approved || !delegate || policy.state !== 'reviewed'} onClick={() => run('enable', {...approval(), review_digest: policy.review_digest, delegate_ssh_credentials: true, delegate_database_credentials: true, credentials})}>Enable reviewed recurring backup policy</Button>
      <Button disabled={busy} onClick={() => run('status', {job_id: policy.job_id})}>Refresh recurring backup policy</Button>
      <Button disabled={busy || !approved || ['disabled', 'expired'].includes(policy.state)} onClick={() => run('disable', approval())}>Disable recurring backup policy</Button>
      <Button disabled={busy || !approved || policy.state !== 'enabled'} onClick={() => run('scan', approval())}>Request due recurring backup</Button>
      <Button disabled={busy || !approved || !policy.ssh_delegation_present} onClick={() => run('rotate', approval())}>Rotate recurring backup credential envelope</Button>
      <Button disabled={busy} onClick={() => run('occurrences', {job_id: policy.job_id, offset: 0, limit: 25}, setOccurrences)}>Load native backup occurrences</Button>
      {occurrences && <Box>{occurrences.jobs.map(value => <Button key={value.job_id} disabled={busy} aria-label={'Inspect native backup occurrence ' + value.job_id} onClick={() => run('occurrence', {job_id: policy.job_id, occurrence_id: value.job_id}, setOccurrence)}>{value.job_id}: {value.state}</Button>)}</Box>}
      {occurrences?.more && <Button disabled={busy} onClick={() => run('occurrences', {job_id: policy.job_id, offset: occurrences.offset + occurrences.limit, limit: occurrences.limit}, value => setOccurrences(current => ({...value, jobs: [...current.jobs, ...value.jobs]})))}>More native backup occurrences</Button>}
      {occurrence && <>
        <Box component="pre" aria-label="Native backup occurrence receipt" sx={{whiteSpace: 'pre-wrap', maxHeight: 360, overflow: 'auto'}}>{JSON.stringify(occurrence, null, 2)}</Box>
        <Button disabled={busy} onClick={() => run('occurrence', {job_id: policy.job_id, occurrence_id: occurrence.job_id}, setOccurrence)}>Refresh native backup occurrence</Button>
        <Button disabled={busy || !approved || policy.state === 'enabled' || occurrence.protection_released} onClick={() => run('release', {...approval(), occurrence_id: occurrence.job_id, credentials}, setOccurrence)}>Reconcile native ends and release workflow protection</Button>
        <Alert severity="info">Original native jobs remain available under Load physical jobs. Disable the policy before manual cancellation or reconciliation. Unknown outcomes retain workflow protection until every original process and credential cleanup is independently confirmed. Archive protection and data-file retention remain separate.</Alert>
      </>}
    </>}
  </Box>;
}
MySQLPhysicalBackupSchedule.propTypes = {post: PropTypes.func.isRequired, physical: PropTypes.object.isRequired, credentials: PropTypes.object.isRequired,
  busy: PropTypes.bool.isRequired, onBusy: PropTypes.func.isRequired};
