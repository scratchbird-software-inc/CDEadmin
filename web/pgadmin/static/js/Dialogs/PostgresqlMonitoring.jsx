import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import getApiInstance from '../api_instance';
import url_for from 'sources/url_for';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {postgresqlDashboardFiles} from '../cdeadmin_ui/integrations/ddn/postgresqlDashboard';

export default function PostgresqlMonitoring({serverId, targetId, policyMode=false}) {
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState('current');
  const [credentials, setCredentials] = useState({username: '', password: '', role: ''});
  const [policy, setPolicy] = useState({interval_seconds: targetId ? 5 : 15,
    retain_samples: 120, lease_seconds: 3600, metadata_interval_seconds: 60,
    heartbeat_enabled: false, heartbeat_timeout_seconds: null});
  const endpoint = useMemo(() => url_for('cdeadmin_postgresql_monitoring.monitoring', {sid: serverId}) +
    (targetId ? `?target_id=${encodeURIComponent(targetId)}` : ''), [serverId, targetId]);
  useEffect(() => {
    let active = true, pending = false;
    const read = async () => {
      if(pending) return;
      pending = true;
      try {
        const response = await getApiInstance().get(endpoint);
        if(active) { setSnapshot(response.data.data); setError(''); }
      } catch(err) {
        if(active) { setSnapshot(null); setError(err.response?.data?.errormsg || 'Monitoring unavailable'); }
      } finally { pending = false; }
    };
    read();
    const timer = setInterval(read, 5000);
    return () => { active = false; clearInterval(timer); };
  }, [endpoint]);
  const change = async (stop=false) => {
    setBusy(true); setError('');
    try {
      const response = stop ? await getApiInstance().delete(endpoint) :
        await getApiInstance().post(endpoint, {...policy,
          heartbeat_timeout_seconds: policy.heartbeat_enabled ? policy.heartbeat_timeout_seconds : null,
          ...(mode === 'dedicated' ? {credentials} : {})});
      setSnapshot(response.data.data);
    } catch(err) { setError(err.response?.data?.errormsg || 'Monitoring policy change failed'); }
    finally { setBusy(false); setCredentials((value) => ({...value, password: ''})); }
  };
  const files = useMemo(() => postgresqlDashboardFiles(snapshot,
    targetId ? 'PostgreSQL database dashboard' : 'PostgreSQL server dashboard',
    targetId ? 'database' : 'server'), [snapshot, targetId]);
  const active = snapshot && snapshot.state !== 'disabled';
  const valid = [['interval_seconds', targetId ? 5 : 15, 300], ['retain_samples', 1, 720],
    ['lease_seconds', 5, 86400], ['metadata_interval_seconds', 60, 3600]].every(([key, min, max]) =>
    Number.isInteger(policy[key]) && policy[key] >= min && policy[key] <= max) &&
    (!policy.heartbeat_enabled || policy.heartbeat_timeout_seconds === null ||
      (Number.isInteger(policy.heartbeat_timeout_seconds) && policy.heartbeat_timeout_seconds >= policy.interval_seconds + 5 &&
       policy.heartbeat_timeout_seconds <= 3600));
  return <Box sx={{height: '100%', p: 1, overflow: 'auto'}}>
    <FormReference formKey={policyMode ? 'postgresql-monitoring-policy' : 'postgresql-dashboard'} />
    {error && <Alert severity="error">{error}</Alert>}
    {policyMode ? <Box sx={{display: 'grid', gap: 1, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 20rem))'}}>
      <Alert severity="info" sx={{gridColumn: '1 / -1'}}>Collection uses a separate connection and continues without an open dashboard. Stop collection before changing its policy. Samples and credentials last only for this process and lease.</Alert>
      {snapshot?.collection_available === false && <Alert severity="warning" sx={{gridColumn: '1 / -1'}}>
        Monitoring requires worker keys, single-process admission and a process lock.
      </Alert>}
      {snapshot?.authentication && <Alert severity="info" sx={{gridColumn: '1 / -1'}}>
        Monitoring account: {snapshot.authentication.username} {snapshot.authentication.role}
      </Alert>}
      <TextField select size="small" label="Monitoring credentials" value={mode} disabled={busy || active}
        onChange={(event) => { setMode(event.target.value); setCredentials({...credentials, password: ''}); }}>
        <MenuItem value="current">Current connection credentials</MenuItem>
        <MenuItem value="dedicated">Dedicated monitoring account</MenuItem>
      </TextField>
      {mode === 'dedicated' && ['username', 'password', 'role'].map((key) => <TextField key={key} size="small"
        label={`Monitoring ${key}${key === 'role' ? ' (optional)' : ''}`} value={credentials[key]}
        type={key === 'password' ? 'password' : 'text'} autoComplete={key === 'password' ? 'new-password' : 'off'}
        disabled={busy || active} onChange={(event) => setCredentials({...credentials, [key]: event.target.value})} />)}
      {Object.entries({interval_seconds: 'Sample interval (seconds)', retain_samples: 'Retained samples',
        lease_seconds: 'Collection lease (seconds)', metadata_interval_seconds: 'Metadata interval (seconds)'}).map(([key, label]) =>
        <TextField key={key} size="small" type="number" label={label} value={policy[key]} disabled={busy || active}
          onChange={(event) => setPolicy({...policy, [key]: Number(event.target.value)})} />)}
      <FormControlLabel label="Use completed refreshes as availability heartbeats" control={<Checkbox
        checked={policy.heartbeat_enabled} disabled={busy || active}
        onChange={(event) => setPolicy({...policy, heartbeat_enabled: event.target.checked})} />} />
      {policy.heartbeat_enabled && <TextField size="small" type="number" label="Heartbeat overdue after (seconds)"
        value={policy.heartbeat_timeout_seconds ?? ''} disabled={busy || active}
        helperText={`Blank uses ${Math.max(15, policy.interval_seconds * 3)} seconds`}
        onChange={(event) => setPolicy({...policy, heartbeat_timeout_seconds: event.target.value === '' ? null : Number(event.target.value)})} />}
      <Box sx={{gridColumn: '1 / -1', display: 'flex', gap: 1}}>
        <Button size="small" onClick={() => change()} disabled={busy || !snapshot || active || !valid ||
          snapshot.collection_available === false || (mode === 'dedicated' && (!credentials.username || !credentials.password))}>Start collection</Button>
        <Button size="small" onClick={() => change(true)} disabled={busy || snapshot?.state === 'disabled'}>Stop collection</Button>
      </Box>
    </Box> : <DDNViewerSurface files={files} entry="dashboard.ddn" view="dashboard" presentation />}
  </Box>;
}
PostgresqlMonitoring.propTypes = {serverId: PropTypes.number.isRequired, targetId: PropTypes.string, policyMode: PropTypes.bool};
