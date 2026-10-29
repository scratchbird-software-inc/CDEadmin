import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import getApiInstance from '../api_instance';
import url_for from 'sources/url_for';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {bindPublication} from '../cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
import {loadDDNLibraries} from '../cdeadmin_ui/integrations/ddn/library';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {postgresqlDashboardFiles, postgresqlFleetFiles} from '../cdeadmin_ui/integrations/ddn/postgresqlDashboard';
import {currentPostgresqlNativeMetrics,postgresqlNativeMetricFiles} from '../cdeadmin_ui/integrations/ddn/postgresqlNativeMetrics';
import PostgresqlTrendView from './PostgresqlTrendView';
import FirebirdHistoryView from './FirebirdHistoryView';

export default function PostgresqlMonitoring({serverId, targetId, policyMode=false, engineMode=false, onNavigate}) {
  const [snapshot, setSnapshot] = useState(null);
  const [publishedView, setPublishedView] = useState(null);
  const [page, setPage] = useState('');
  const [display, setDisplay] = useState('dashboard');
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const [busy, setBusy] = useState(false);
  const [nativeSources,setNativeSources]=useState(null);
  const [nativeFamily,setNativeFamily]=useState(''),[nativePage,setNativePage]=useState(0);
  const [mode, setMode] = useState('current');
  const [credentials, setCredentials] = useState({username: '', password: '', role: ''});
  const [policy, setPolicy] = useState({interval_seconds: targetId ? 5 : 15,
    retain_samples: 120, lease_seconds: 3600, metadata_interval_seconds: 60,
    native_metric_sources: [],
    heartbeat_enabled: false, heartbeat_timeout_seconds: null, history_enabled: false});
  const endpoint = useMemo(() => engineMode ? url_for('cdeadmin_postgresql_monitoring.fleet') : url_for('cdeadmin_postgresql_monitoring.monitoring', {sid: serverId}) +
    (targetId ? `?target_id=${encodeURIComponent(targetId)}` : ''), [serverId, targetId, engineMode]);
  const definitionEndpoint = useMemo(() => {
    const params = new URLSearchParams({published: '1'});
    if(!engineMode) params.set('sid', serverId);
    if(targetId) params.set('target_id', targetId);
    return url_for('cdeadmin_postgresql_monitoring.definition') + `?${params}`;
  }, [engineMode, serverId, targetId]);
  useEffect(() => {
    if(!policyMode || engineMode)return;
    let live=true;
    getApiInstance().get(url_for('cdeadmin_postgresql_monitoring.sources')).then(response => {
      if(live)setNativeSources(response.data.data);
    }).catch(() => {if(live)setNativeSources({state:'unavailable',sources:[]});});
    return () => {live=false;};
  },[policyMode,engineMode,serverId,targetId]);
  useEffect(() => {
    let active = true, pending = false;
    const read = async () => {
      if(pending) return;
      pending = true;
      try {
        const response = await getApiInstance().get(endpoint);
        let published = null;
        if(!policyMode || engineMode) {
          const publication = (await getApiInstance().get(definitionEndpoint)).data.data;
          if(publication.state === 'published') {
            const libraries = await loadDDNLibraries();
            const scope = engineMode ? 'engine' : targetId ? 'database' : 'server';
            const live = engineMode ? postgresqlFleetFiles(response.data.data) : postgresqlDashboardFiles(response.data.data, 'PostgreSQL dashboard', scope);
            published = await bindPublication(libraries, publication.snapshot, scope, live, 'postgresql');
          }
        }
        if(active) { setSnapshot(response.data.data); setPublishedView(published); setPollError(''); }
      } catch(err) {
        if(active) { setSnapshot(null); setPublishedView(null); setPollError(err.response?.data?.errormsg || 'Monitoring unavailable'); }
      } finally { pending = false; }
    };
    read();
    const timer = setInterval(read, 5000);
    return () => { active = false; clearInterval(timer); };
  }, [endpoint, definitionEndpoint, policyMode, engineMode, targetId]);
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
  const files = useMemo(() => engineMode ? postgresqlFleetFiles(snapshot) : postgresqlDashboardFiles(snapshot,
    targetId ? 'PostgreSQL database dashboard' : 'PostgreSQL server dashboard',
    targetId ? 'database' : 'server'), [snapshot, targetId, engineMode]);
  const pages = useMemo(() => Array.from(((publishedView?.files || files)[publishedView?.entry || 'dashboard.ddn'] || '').matchAll(/view (dashboard(?:_page_\d+)?) /g), (match) => match[1]), [files, publishedView]);
  const selectedPage = pages.includes(page) ? page : publishedView?.view || 'dashboard';
  const displaySnapshot = useMemo(() => publishedView ? {...publishedView, view: selectedPage,
    layoutState: selectedPage === publishedView.view ? publishedView.layoutState : undefined} : undefined, [publishedView, selectedPage]);
  const active = snapshot && snapshot.state !== 'disabled';
  const valid = [['interval_seconds', targetId ? 5 : 15, 300], ['retain_samples', 1, 720],
    ['lease_seconds', 5, 86400], ['metadata_interval_seconds', 60, 3600]].every(([key, min, max]) =>
    Number.isInteger(policy[key]) && policy[key] >= min && policy[key] <= max) &&
    (!policy.heartbeat_enabled || policy.heartbeat_timeout_seconds === null ||
      (Number.isInteger(policy.heartbeat_timeout_seconds) && policy.heartbeat_timeout_seconds >= policy.interval_seconds + 5 &&
       policy.heartbeat_timeout_seconds <= 3600));
  const nativeFrames=currentPostgresqlNativeMetrics(snapshot,targetId ? 'database' : 'server')?.sources || {};
  const nativeNames=Object.keys(nativeFrames),selectedNative=nativeNames.includes(nativeFamily) ? nativeFamily : nativeNames[0] || '';
  const nativePages=Math.max(1,Math.ceil((nativeFrames[selectedNative]?.rows?.length || 0)/10));
  const selectedNativePage=nativePage<nativePages ? nativePage : 0;
  const nativeFiles=useMemo(() => postgresqlNativeMetricFiles(snapshot,targetId ? 'database' : 'server',selectedNative,selectedNativePage),
    [snapshot,targetId,selectedNative,selectedNativePage]);
  return <Box sx={{height: '100%', p: 1, overflow: 'auto'}}>
    <FormReference formKey={policyMode && !engineMode ? 'postgresql-monitoring-policy' : 'postgresql-dashboard'} />
    {(error || pollError) && <Alert severity="error">{error || pollError}</Alert>}
    {engineMode && onNavigate && snapshot && <TextField select size="small" label="Open dashboard" value=""
      sx={{width: '24rem', maxWidth: '100%', my: 1}} onChange={(event) => {
        const [sid, target, name] = JSON.parse(event.target.value);
        onNavigate(sid, target || undefined, name);
      }}>
      {(snapshot.servers || []).flatMap((server) => [
        <MenuItem key={`server:${server.server_id}`} value={JSON.stringify([server.server_id, null, server.name])}>{server.name}</MenuItem>,
        ...(server.databases || []).map((database) => <MenuItem key={`${server.server_id}:${database.target_id}`}
          value={JSON.stringify([server.server_id, database.target_id, database.name])}>{server.name} / {database.name}</MenuItem>),
      ])}
    </TextField>}
    {policyMode && !engineMode ? <Box sx={{display: 'grid', gap: 1, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 20rem))'}}>
      {nativeSources?.state==='available' && <TextField select size="small" label="Additional native statistics families"
        disabled={busy || active} value={active ? snapshot?.policy?.native_metric_sources || [] : policy.native_metric_sources}
        slotProps={{select:{multiple:true}}} onChange={event => setPolicy({...policy,native_metric_sources:event.target.value})}
        helperText="Selected native views retain their scopes and redaction. Each sample has explicit row and byte limits.">
        {nativeSources.sources.map(source => <MenuItem key={source.source_id} value={source.source_id}>{source.source_id} · {source.scope}</MenuItem>)}
      </TextField>}
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
      <FormControlLabel label="Persist observations in ScratchBird" control={<Checkbox
        checked={Boolean(policy.history_enabled)} disabled={busy || active || snapshot?.history_available === false}
        onChange={event => setPolicy({...policy, history_enabled: event.target.checked})} />} />
      {snapshot?.history_storage && <Alert severity={snapshot.history_storage.status === 'unconfirmed' ? 'warning' : 'info'}>
        History: {snapshot.history_storage.status}. Unconfirmed writes: {snapshot.history_storage.failures || 0}.
      </Alert>}
      {policy.heartbeat_enabled && <TextField size="small" type="number" label="Heartbeat overdue after (seconds)"
        value={policy.heartbeat_timeout_seconds ?? ''} disabled={busy || active}
        helperText={`Blank uses ${Math.max(15, policy.interval_seconds * 3)} seconds`}
        onChange={(event) => setPolicy({...policy, heartbeat_timeout_seconds: event.target.value === '' ? null : Number(event.target.value)})} />}
      <Box sx={{gridColumn: '1 / -1', display: 'flex', gap: 1}}>
        <Button size="small" onClick={() => change()} disabled={busy || !snapshot || active || !valid ||
          snapshot.collection_available === false || (mode === 'dedicated' && (!credentials.username || !credentials.password))}>Start collection</Button>
        <Button size="small" onClick={() => change(true)} disabled={busy || snapshot?.state === 'disabled'}>Stop collection</Button>
      </Box>
    </Box> : !error && <>
      {!engineMode && <TextField select size="small" label="Display" value={display} sx={{minWidth: 200, my: 1}}
        onChange={event => setDisplay(event.target.value)}>
        <MenuItem value="dashboard">Current dashboard</MenuItem>
        <MenuItem value="trends">Retained observations</MenuItem>
        <MenuItem value="history">Persistent history</MenuItem>
        <MenuItem value="native">Additional native statistics</MenuItem>
      </TextField>}
      {(engineMode || display === 'dashboard') && pages.length > 1 && <TextField select size="small" label="Dashboard page" value={selectedPage}
        sx={{minWidth: 160, my: 1}} onChange={(event) => setPage(event.target.value)}>
        {publishedView && !pages.includes(publishedView.view) && <MenuItem value={publishedView.view}>Published view</MenuItem>}
        {pages.map((id, index) => <MenuItem key={id} value={id}>Page {index + 1} of {pages.length}</MenuItem>)}
      </TextField>}
      {!engineMode && display==='native' ? <>
        <TextField select size="small" label="Native statistics family" value={selectedNative} sx={{minWidth:240,my:1}}
          onChange={event => {setNativeFamily(event.target.value);setNativePage(0);}}>
          {!nativeNames.length && <MenuItem value="">No current collected sources</MenuItem>}
          {nativeNames.map(name => <MenuItem key={name} value={name}>{name}</MenuItem>)}
        </TextField>
        {nativePages>1 && <TextField select size="small" label="Native statistics page" value={selectedNativePage} sx={{minWidth:160,my:1}}
          onChange={event => setNativePage(Number(event.target.value))}>
          {Array.from({length:nativePages},(_unused,index) => <MenuItem key={index} value={index}>Page {index+1} of {nativePages}</MenuItem>)}
        </TextField>}
        <DDNViewerSurface files={nativeFiles} entry="dashboard.ddn" view="dashboard" presentation />
      </> : !engineMode && display === 'history' ? <FirebirdHistoryView key={endpoint} serverId={serverId} targetId={targetId} engine="postgresql" /> :
        !engineMode && display === 'trends' ? <PostgresqlTrendView key={endpoint} snapshot={snapshot} scope={targetId ? 'database' : 'server'} /> :
          <DDNViewerSurface files={files} snapshot={displaySnapshot} entry="dashboard.ddn" view={selectedPage} presentation />}
    </>}
  </Box>;
}
PostgresqlMonitoring.propTypes = {serverId: PropTypes.number, targetId: PropTypes.string, policyMode: PropTypes.bool,
  engineMode: PropTypes.bool, onNavigate: PropTypes.func};
