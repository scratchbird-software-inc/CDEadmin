import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import getApiInstance from '../api_instance';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {dashboardPanelFiles} from '../cdeadmin_ui/integrations/ddn/dashboardPanels';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

const defaults = {interval_seconds: 5, retain_samples: 120, lease_seconds: 3600,
  metadata_interval_seconds: 60, heartbeat_enabled: false, heartbeat_timeout_seconds: null};

export function mysqlDashboardFiles(snapshot, scope) {
  const last = snapshot?.samples?.at(-1);
  const fresh = snapshot?.state === 'collecting' && Number.isFinite(snapshot?.sample_age_seconds) &&
    snapshot.sample_age_seconds >= 0 && snapshot.sample_age_seconds <= snapshot.stale_after_seconds;
  const sample = fresh && ['available', 'partial'].includes(last?.status) &&
    last.transaction_completed === true && last.scope === scope ? last : null;
  const panels = [{id: 'availability', title: 'MySQL observation and availability', rows: [
    ['Collector', snapshot?.state], ['Probe', last?.status], ['Freshness', sample ? 'Current' : 'No current observation'],
    ['Heartbeat', snapshot?.heartbeat?.status || 'Disabled'], ['Sample age', snapshot?.sample_age_seconds, 'seconds'],
    ['Observed at', last?.ended_at], ['History', 'Volatile process window'],
    ['Native server UUID', sample?.identity?.server_uuid], ['Database', sample?.identity?.database_name],
  ]}];
  for(const name of ['status', 'settings', 'storage', 'activity', 'replication']) {
    const group = sample?.groups?.[name];
    const values = group?.status === 'available' ? group.rows || [] : [];
    panels.push({id: `native_${name}`, title: `MySQL ${name}`, rows: [
      ['Source', group?.status || 'Unavailable', group?.scope || scope],
      ['Visibility', group?.visibility], ['Truncated', group?.truncated],
      ...values.flatMap((row, index) => Object.entries(row).map(([key, value]) =>
        [`${index + 1}: ${key}`, typeof value === 'object' && value !== null ? JSON.stringify(value) : value,
          name === 'storage' ? 'Native estimate; not filesystem usage' : group.scope])),
    ]});
  }
  return dashboardPanelFiles(panels, `MySQL ${scope} dashboard`, 'scratchrobin.mysql.monitoring');
}

export default function MySQLMonitoring({serverId, targetId, policyMode=false}) {
  const endpoint = `/cdeadmin/api/monitoring/mysql/${serverId}${targetId ? '?target_id=' + encodeURIComponent(targetId) : ''}`;
  const [snapshot, setSnapshot] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [policy, setPolicy] = useState({...defaults, interval_seconds: targetId ? 5 : 15});
  const [mode, setMode] = useState('current'), [showPassword, setShowPassword] = useState(false);
  const [credentials, setCredentials] = useState({username: '', password: '', role: ''});
  const serial = useRef(0), changing = useRef(false);
  useEffect(() => {
    let active = true;
    changing.current = false;
    setSnapshot(null); setBusy(false); setError(''); setActionError('');
    setCredentials({username: '', password: '', role: ''}); setShowPassword(false); setMode('current');
    setPolicy({...defaults, interval_seconds: targetId ? 5 : 15});
    const read = async () => {
      if(changing.current) return;
      const token = ++serial.current;
      try {
        const response = await getApiInstance().get(endpoint);
        if(active && token === serial.current) {setSnapshot(response.data.data); setError('');}
      } catch(failure) {if(active && token === serial.current) setError(failure.response?.data?.errormsg || 'Monitoring observation unavailable');}
    };
    read(); const timer = setInterval(read, 5000);
    return () => {active = false; serial.current++; clearInterval(timer);};
  }, [endpoint, targetId]);
  const change = async stop => {
    const token = ++serial.current;
    changing.current = true; setBusy(true); setActionError('');
    try {
      const response = stop ? await getApiInstance().delete(endpoint) : await getApiInstance().post(endpoint,
        {...policy, ...(mode === 'dedicated' ? {credentials} : {})});
      if(token === serial.current) setSnapshot(response.data.data);
    } catch(failure) {if(token === serial.current) setActionError(failure.response?.data?.errormsg || 'Monitoring policy change failed');}
    finally {if(token === serial.current) {changing.current = false; setBusy(false); setCredentials(value => ({...value, password: ''}));}}
  };
  const files = useMemo(() => mysqlDashboardFiles(snapshot, targetId ? 'database' : 'server'), [snapshot, targetId]);
  const active = Boolean(snapshot && snapshot.state !== 'disabled');
  const valid = Number.isInteger(policy.interval_seconds) && policy.interval_seconds >= (targetId ? 5 : 15) && policy.interval_seconds <= 300 &&
    Number.isInteger(policy.retain_samples) && policy.retain_samples >= 1 && policy.retain_samples <= 720 &&
    Number.isInteger(policy.lease_seconds) && policy.lease_seconds >= 5 && policy.lease_seconds <= 86400 &&
    Number.isInteger(policy.metadata_interval_seconds) && policy.metadata_interval_seconds >= 60 && policy.metadata_interval_seconds <= 3600 &&
    (policy.heartbeat_timeout_seconds === null || (Number.isInteger(policy.heartbeat_timeout_seconds) &&
      policy.heartbeat_timeout_seconds >= policy.interval_seconds + 5 && policy.heartbeat_timeout_seconds <= 3600));
  return <Box sx={{...compactFormSx, p: 1, height: '100%', overflow: 'auto'}}>
    <FormReference formKey={policyMode ? 'mysql-monitoring-policy' : 'mysql-dashboard'} />
    {error && <Alert severity="error">{error}</Alert>}
    {actionError && <Alert severity="error">{actionError}</Alert>}
    {policyMode ? <>
      <Alert severity="info">Collection owns a separate connection and continues without an open dashboard. Stop collection before changing policy or credentials. Samples and sealed credentials last for this process and lease.</Alert>
      {snapshot?.collection_available === false && <Alert severity="warning">Monitoring requires worker keys, single-process admission and a process lock.</Alert>}
      {snapshot?.authentication && <Alert severity="info">Monitoring account: {snapshot.authentication.username} {snapshot.authentication.role}</Alert>}
      <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center'}}>
        <TextField select size="small" label="Monitoring credentials" value={mode} disabled={busy || active}
          onChange={event => {setMode(event.target.value); setCredentials(value => ({...value, password: ''}));}}>
          <MenuItem value="current">Current connection credentials</MenuItem><MenuItem value="dedicated">Dedicated monitoring account</MenuItem>
        </TextField>
        {mode === 'dedicated' && ['username', 'password', 'role'].map(key => <TextField key={key} size="small"
          label={`Monitoring ${key}${key === 'role' ? ' (optional; default role host %)' : ''}`} value={credentials[key]}
          type={key === 'password' && !showPassword ? 'password' : 'text'} autoComplete={key === 'password' ? 'new-password' : 'off'}
          disabled={busy || active} onChange={event => setCredentials({...credentials, [key]: event.target.value})} />)}
        {mode === 'dedicated' && <FormControlLabel label="Show password" control={<Checkbox checked={showPassword} onChange={event => setShowPassword(event.target.checked)} />} />}
        {Object.entries({interval_seconds: 'Sample interval (seconds)', retain_samples: 'Retained samples',
          lease_seconds: 'Collection lease (seconds)', metadata_interval_seconds: 'Metadata interval (seconds)'}).map(([key, label]) =>
          <TextField key={key} size="small" type="number" label={label} value={policy[key]} disabled={busy || active}
            onChange={event => setPolicy({...policy, [key]: Number(event.target.value)})} />)}
        <FormControlLabel label="Use completed refreshes as availability heartbeats" control={<Checkbox checked={policy.heartbeat_enabled}
          disabled={busy || active} onChange={event => setPolicy({...policy, heartbeat_enabled: event.target.checked})} />} />
        <TextField size="small" type="number" label="Heartbeat timeout (seconds; blank uses policy default)"
          value={policy.heartbeat_timeout_seconds ?? ''} disabled={busy || active || !policy.heartbeat_enabled}
          onChange={event => setPolicy({...policy, heartbeat_timeout_seconds: event.target.value === '' ? null : Number(event.target.value)})} />
        <Button size="small" disabled={busy || active || !snapshot || snapshot.collection_available === false || !valid ||
          (mode === 'dedicated' && (!credentials.username || !credentials.password))} onClick={() => change(false)}>Start collection</Button>
        <Button size="small" disabled={busy || !active} onClick={() => change(true)}>Stop collection</Button>
      </Box>
    </> : <Box sx={{height: 'calc(100% - 32px)', minHeight: 300}}><DDNViewerSurface presentation snapshot={{
      format: 'ddn-workspace@1', entry: 'dashboard.ddn', view: 'dashboard', files}} /></Box>}
  </Box>;
}
MySQLMonitoring.propTypes = {serverId: PropTypes.number.isRequired, targetId: PropTypes.string, policyMode: PropTypes.bool};
