import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import FirebirdHistoryView from './FirebirdHistoryView';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import getApiInstance from '../api_instance';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {bindPublication} from '../cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
import {loadDDNLibraries} from '../cdeadmin_ui/integrations/ddn/library';
import {mysqlDashboardFiles, mysqlFleetFiles, mysqlFleetPublication} from '../cdeadmin_ui/integrations/ddn/mysqlDashboard';
import {duckdbDashboardFiles, duckdbFleetFiles, duckdbFleetPublication} from '../cdeadmin_ui/integrations/ddn/duckdbDashboard';
import {sqliteDashboardFiles, sqliteFleetFiles, sqliteFleetPublication} from '../cdeadmin_ui/integrations/ddn/sqliteDashboard';
import MySQLTrendView from './MySQLTrendView';
import DuckDBTrendView from './DuckDBTrendView';
import SQLiteTrendView from './SQLiteTrendView';
export {mysqlDashboardFiles} from '../cdeadmin_ui/integrations/ddn/mysqlDashboard';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

const defaults = {interval_seconds: 5, retain_samples: 120, lease_seconds: 3600,
  metadata_interval_seconds: 60, heartbeat_enabled: false, heartbeat_timeout_seconds: null};

export default function MySQLMonitoring({serverId, targetId, policyMode=false, engineMode=false, onNavigate, engine='mysql'}) {
  const embedded = ['duckdb', 'sqlite'].includes(engine);
  const embeddedDashboard = engine === 'sqlite' ? sqliteDashboardFiles : duckdbDashboardFiles;
  const embeddedFleetFiles = engine === 'sqlite' ? sqliteFleetFiles : duckdbFleetFiles;
  const embeddedFleetPublication = engine === 'sqlite' ? sqliteFleetPublication : duckdbFleetPublication;
  const scope = engineMode ? 'engine' : targetId ? 'database' : 'server', showPolicy = policyMode && !engineMode;
  const endpoint = `/cdeadmin/api/monitoring/${engine}${engineMode ? '' : '/' + serverId}${targetId ? '?target_id=' + encodeURIComponent(targetId) : ''}`;
  const definitionEndpoint = `/cdeadmin/api/monitoring/${engine}/definition?published=1${engineMode ? '' : '&sid=' + serverId}${targetId ? '&target_id=' + encodeURIComponent(targetId) : ''}`;
  const [snapshot, setSnapshot] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [publishedView, setPublishedView] = useState(null), [display, setDisplay] = useState('dashboard');
  const [page, setPage] = useState('dashboard');
  const [actionError, setActionError] = useState('');
  const [policy, setPolicy] = useState({...defaults, interval_seconds: targetId ? 5 : 15});
  const [mode, setMode] = useState('current'), [showPassword, setShowPassword] = useState(false);
  const [credentials, setCredentials] = useState({username: '', password: '', role: ''});
  const serial = useRef(0), changing = useRef(false);
  useEffect(() => {
    let active = true, pending = false;
    changing.current = false;
    setSnapshot(null); setPublishedView(null); setBusy(false); setError(''); setActionError('');
    setDisplay('dashboard'); setPage('dashboard');
    setCredentials({username: '', password: '', role: ''}); setShowPassword(false); setMode('current');
    setPolicy({...defaults, interval_seconds: targetId ? 5 : 15});
    const read = async () => {
      if(changing.current || pending) return;
      pending = true;
      const token = ++serial.current;
      try {
        const response = await getApiInstance().get(endpoint);
        let publication = null;
        if(!showPolicy) {
          const definition = (await getApiInstance().get(definitionEndpoint)).data.data;
          if(definition?.state === 'published') {
            const {viewer} = await loadDDNLibraries();
            const live = engineMode ? embedded ? embeddedFleetFiles(response.data.data) : mysqlFleetFiles(response.data.data, engine) :
              embedded ? embeddedDashboard(response.data.data, scope) : mysqlDashboardFiles(response.data.data, scope, engine);
            publication = bindPublication(viewer, definition.snapshot, scope, live, engine);
          }
        }
        if(active && token === serial.current) {setSnapshot(response.data.data); setPublishedView(publication); setError('');}
      } catch(failure) {if(active && token === serial.current) {setSnapshot(null); setPublishedView(null); setError(failure.response?.data?.errormsg || 'Monitoring observation unavailable');}}
      finally {pending = false;}
    };
    read(); const timer = setInterval(read, 5000);
    return () => {active = false; serial.current++; clearInterval(timer);};
  }, [endpoint, targetId, definitionEndpoint, showPolicy, scope, engineMode, engine]);
  useEffect(() => {
    if(!showPolicy || !snapshot?.policy || snapshot.state === 'disabled') return;
    setPolicy(value => ({...value, ...Object.fromEntries([...Object.keys(defaults), ...(['mysql', 'mariadb', 'duckdb', 'sqlite'].includes(engine) ? ['history_enabled'] : [])]
      .filter(key => Object.hasOwn(snapshot.policy, key)).map(key => [key, snapshot.policy[key]]))}));
    if(snapshot.authentication) {
      setMode(snapshot.authentication.mode === 'dedicated' ? 'dedicated' : 'current');
      setCredentials({username: snapshot.authentication.username || '', role: snapshot.authentication.role || '', password: ''});
    }
  }, [showPolicy, snapshot]);
  const change = async stop => {
    const token = ++serial.current;
    changing.current = true; setBusy(true); setActionError('');
    try {
      const response = stop ? await getApiInstance().delete(endpoint) : await getApiInstance().post(endpoint,
        {...policy, ...(['mysql', 'mariadb', 'duckdb', 'sqlite'].includes(engine) ? {history_enabled: Boolean(policy.history_enabled)} : {}),
          ...(!embedded && mode === 'dedicated' ? {credentials} : {})});
      if(token === serial.current) setSnapshot(response.data.data);
    } catch(failure) {if(token === serial.current) setActionError(failure.response?.data?.errormsg || 'Monitoring policy change failed');}
    finally {if(token === serial.current) {changing.current = false; setBusy(false); setCredentials(value => ({...value, password: ''}));}}
  };
  const {files, pages} = useMemo(() => engineMode ?
    embedded ? embeddedFleetPublication(snapshot) : mysqlFleetPublication(snapshot, 128, engine) :
    {files: embedded ? embeddedDashboard(snapshot, scope) : mysqlDashboardFiles(snapshot, scope, engine),
      pages: ['dashboard']}, [snapshot, scope, engineMode, engine, embedded]);
  const active = Boolean(snapshot && snapshot.state !== 'disabled');
  const valid = Number.isInteger(policy.interval_seconds) && policy.interval_seconds >= (targetId ? 5 : 15) && policy.interval_seconds <= 300 &&
    Number.isInteger(policy.retain_samples) && policy.retain_samples >= 1 && policy.retain_samples <= 720 &&
    Number.isInteger(policy.lease_seconds) && policy.lease_seconds >= 5 && policy.lease_seconds <= 86400 &&
    Number.isInteger(policy.metadata_interval_seconds) && policy.metadata_interval_seconds >= 60 && policy.metadata_interval_seconds <= 3600 &&
    (policy.heartbeat_timeout_seconds === null || (Number.isInteger(policy.heartbeat_timeout_seconds) &&
      policy.heartbeat_timeout_seconds >= policy.interval_seconds + 5 && policy.heartbeat_timeout_seconds <= 3600));
  return <Box sx={{...compactFormSx, p: 1, height: '100%', overflow: 'auto'}}>
    <FormReference formKey={showPolicy ? `${engine}-monitoring-policy` : `${engine}-dashboard`} />
    {error && <Alert severity="error">{error}</Alert>}
    {actionError && <Alert severity="error">{actionError}</Alert>}
    {showPolicy ? <>
      <Alert severity="info">{embedded ? `Collection owns a separate connection to the registered ${engine === 'sqlite' ? 'SQLite' : 'DuckDB'} file and continues without an open dashboard. Stop collection before changing policy. Samples last for this process and lease.` :
        'Collection owns a separate connection and continues without an open dashboard. Stop collection before changing policy or credentials. Samples and sealed credentials last for this process and lease.'}</Alert>
      {snapshot?.collection_available === false && <Alert severity="warning">{embedded ?
        'Monitoring requires single-process admission and a process lock.' :
        'Monitoring requires worker keys, single-process admission and a process lock.'}</Alert>}
      {!embedded && snapshot?.authentication && <Alert severity="info">Monitoring account: {snapshot.authentication.username} {snapshot.authentication.role}</Alert>}
      {snapshot && <Alert severity={snapshot.samples?.at(-1)?.status === 'unavailable' ? 'warning' : 'info'}>
        Collector: {snapshot.state}. Heartbeat: {snapshot.heartbeat?.status || 'Disabled'}.
        Latest probe: {snapshot.samples?.at(-1)?.status || 'Not observed'}
        {snapshot.samples?.at(-1)?.error_code ? ` (native error ${snapshot.samples.at(-1).error_code})` : ''}.
      </Alert>}
      <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center'}}>
        {!embedded && <TextField select size="small" label="Monitoring credentials" value={mode} disabled={busy || active}
          onChange={event => {setMode(event.target.value); setCredentials(value => ({...value, password: ''}));}}>
          <MenuItem value="current">Current connection credentials</MenuItem><MenuItem value="dedicated">Dedicated monitoring account</MenuItem>
        </TextField>}
        {!embedded && mode === 'dedicated' && ['username', 'password', 'role'].map(key => <TextField key={key} size="small"
          label={`Monitoring ${key}${key === 'role' ? (engine === 'mariadb' ? ' (optional)' : ' (optional; default role host %)') : ''}`} value={credentials[key]}
          type={key === 'password' && !showPassword ? 'password' : 'text'} autoComplete={key === 'password' ? 'new-password' : 'off'}
          disabled={busy || active} onChange={event => setCredentials({...credentials, [key]: event.target.value})} />)}
        {!embedded && mode === 'dedicated' && <FormControlLabel label="Show password" control={<Checkbox checked={showPassword} onChange={event => setShowPassword(event.target.checked)} />} />}
        {Object.entries({interval_seconds: 'Sample interval (seconds)', retain_samples: 'Retained samples',
          lease_seconds: 'Collection lease (seconds)', metadata_interval_seconds: 'Metadata interval (seconds)'}).map(([key, label]) =>
          <TextField key={key} size="small" type="number" label={label} value={policy[key]} disabled={busy || active}
            onChange={event => setPolicy({...policy, [key]: Number(event.target.value)})} />)}
        <FormControlLabel label="Use completed refreshes as availability heartbeats" control={<Checkbox checked={policy.heartbeat_enabled}
          disabled={busy || active} onChange={event => setPolicy({...policy, heartbeat_enabled: event.target.checked})} />} />
        {['mysql', 'mariadb', 'duckdb', 'sqlite'].includes(engine) && <FormControlLabel label="Persist observations in ScratchBird" control={<Checkbox
          checked={Boolean(policy.history_enabled)} disabled={busy || active || snapshot?.history_available === false}
          onChange={event => setPolicy({...policy, history_enabled: event.target.checked})} />} />}
        {['mysql', 'mariadb', 'duckdb', 'sqlite'].includes(engine) && snapshot?.history_storage && <Alert severity={snapshot.history_storage.status === 'unconfirmed' ? 'warning' : 'info'}>
          History: {snapshot.history_storage.status}. Unconfirmed writes: {snapshot.history_storage.failures || 0}.
        </Alert>}
        <TextField size="small" type="number" label="Heartbeat timeout (seconds; blank uses policy default)"
          value={policy.heartbeat_timeout_seconds ?? ''} disabled={busy || active || !policy.heartbeat_enabled}
          onChange={event => setPolicy({...policy, heartbeat_timeout_seconds: event.target.value === '' ? null : Number(event.target.value)})} />
        <Button size="small" disabled={busy || active || !snapshot || snapshot.collection_available === false || !valid ||
          (!embedded && mode === 'dedicated' && (!credentials.username || !credentials.password))} onClick={() => change(false)}>Start collection</Button>
        <Button size="small" disabled={busy || !active} onClick={() => change(true)}>Stop collection</Button>
      </Box>
    </> : <>
      {!engineMode && <TextField select size="small" label="Display" value={display} onChange={event => setDisplay(event.target.value)}>
        <MenuItem value="dashboard">Dashboard</MenuItem><MenuItem value="trends">Retained observations</MenuItem>
        {['mysql', 'mariadb', 'duckdb', 'sqlite'].includes(engine) && <MenuItem value="history">Persistent history</MenuItem>}
      </TextField>}
      {engineMode && pages.length > 1 && !publishedView && <TextField select size="small" label="Dashboard page" value={pages.includes(page) ? page : 'dashboard'} onChange={event => setPage(event.target.value)}>
        {pages.map((item, index) => <MenuItem key={item} value={item}>Page {index + 1}</MenuItem>)}
      </TextField>}
      {engineMode && onNavigate && <TextField select size="small" label="Open registered scope" value="" onChange={event => {
        const [sid, target, name] = JSON.parse(event.target.value); onNavigate(sid, target, name);
      }}>
        <MenuItem value="">Select dashboard</MenuItem>
        {(snapshot?.servers || []).flatMap(server => [
          <MenuItem key={server.server_id} value={JSON.stringify([server.server_id, null, server.name])}>{server.name} / server</MenuItem>,
          ...(server.databases || []).map(database => <MenuItem key={`${server.server_id}/${database.target_id}`} value={JSON.stringify([server.server_id, database.target_id, database.name])}>{server.name} / {database.name}</MenuItem>),
        ])}
      </TextField>}
      {display === 'history' && !engineMode && ['mysql', 'mariadb', 'duckdb', 'sqlite'].includes(engine) ?
        <FirebirdHistoryView key={`${serverId}:${targetId || ''}`} serverId={serverId} targetId={targetId} engine={engine} /> :
        display === 'trends' && !engineMode ? engine === 'sqlite' ? <SQLiteTrendView snapshot={snapshot} /> : embedded ? <DuckDBTrendView snapshot={snapshot} /> :
          <MySQLTrendView snapshot={snapshot} scope={scope} engine={engine} /> :
          <Box sx={{height: 'calc(100% - 76px)', minHeight: 300}}><DDNViewerSurface presentation snapshot={publishedView || {
            format: 'ddn-workspace@1', entry: 'dashboard.ddn', view: pages.includes(page) ? page : 'dashboard', files}} /></Box>}
    </>}
  </Box>;
}
MySQLMonitoring.propTypes = {serverId: PropTypes.number, targetId: PropTypes.string, policyMode: PropTypes.bool,
  engineMode: PropTypes.bool, onNavigate: PropTypes.func, engine: PropTypes.oneOf(['mysql', 'mariadb', 'duckdb', 'sqlite'])};
