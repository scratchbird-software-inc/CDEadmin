import FirebirdActivityView from './FirebirdActivityView';
import FirebirdMonitoringDetails from './FirebirdMonitoringDetails';
import FirebirdDatabaseRanking from './FirebirdDatabaseRanking';
import FirebirdEngineTrends from './FirebirdEngineTrends';
import FirebirdTrendView from './FirebirdTrendView';
import FirebirdHistoryView from './FirebirdHistoryView';
import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Radio, RadioGroup, TextField} from '@mui/material';
import getApiInstance from '../api_instance';
import url_for from 'sources/url_for';
import gettext from 'sources/gettext';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {loadDDNLibraries} from '../cdeadmin_ui/integrations/ddn/library';
import {bindPublication} from '../cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
import {firebirdDashboardFiles, firebirdFleetFiles} from '../cdeadmin_ui/integrations/ddn/firebirdDashboard';

export default function FirebirdMonitoring({serverId, targetId, policyMode=false, engineMode=false, onNavigate}) {
  const [snapshot, setSnapshot] = useState(null);
  const [showTrends, setShowTrends] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showActivity, setShowActivity] = useState(false);
  const [publishedView, setPublishedView] = useState(null);
  const [publishedVersion, setPublishedVersion] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [credentialMode, setCredentialMode] = useState('registration');
  const [credentials, setCredentials] = useState({username: '', password: '', role: ''});
  const [policy, setPolicy] = useState({interval_seconds: targetId ? 5 : 15,
    retain_samples: 120, lease_seconds: 3600, history_enabled: false, heartbeat_enabled: false, heartbeat_timeout_seconds: null, metadata_interval_seconds: 60,
    max_transaction_age_seconds: 0, max_backup_state_seconds: 0,
    require_wire_encryption: false, expected_encryption_state: null});
  const endpoint = useMemo(() => engineMode ? url_for('cdeadmin_monitoring.fleet') : url_for('cdeadmin_monitoring.monitoring', {sid: serverId}) +
    (targetId ? `?target_id=${encodeURIComponent(targetId)}` : ''), [serverId, targetId, engineMode]);
  const definitionEndpoint = useMemo(() => {
    const params = new URLSearchParams({published: '1'});
    if(!engineMode) params.set('sid', serverId);
    if(targetId) params.set('target_id', targetId);
    return url_for('cdeadmin_monitoring.definition') + `?${params}`;
  }, [engineMode, serverId, targetId]);
  useEffect(() => {
    let active = true, pending = false;
    const read = async () => {
      if(pending) return;
      pending = true;
      try {
        const response = await getApiInstance().get(endpoint);
        let rendered = null, version = 0;
        if(!policyMode || engineMode) {
          const publication = (await getApiInstance().get(definitionEndpoint)).data.data;
          if(publication.state === 'published') {
            const libraries = await loadDDNLibraries();
            const scope = engineMode ? 'engine' : targetId ? 'database' : 'server';
            const live = engineMode ? firebirdFleetFiles(response.data.data) :
              firebirdDashboardFiles(response.data.data, 'Firebird dashboard', scope);
            rendered = await bindPublication(libraries, publication.snapshot, scope, live);
            version = publication.version;
          }
        }
        if(active) { setSnapshot(response.data.data); setPublishedView(rendered); setPublishedVersion(version); setError(''); }
      } catch(err) {
        if(active) {
          // Do not continue displaying previously authorized observations.
          setSnapshot(null); setPublishedView(null);
          setError(err.response?.data?.errormsg || gettext('Monitoring is unavailable.'));
        }
      } finally { pending = false; }
    };
    read();
    const timer = setInterval(read, 5000);
    return () => { active = false; clearInterval(timer); };
  }, [endpoint, definitionEndpoint, policyMode, engineMode, targetId]);
  const files = useMemo(() => engineMode ? firebirdFleetFiles(snapshot) : firebirdDashboardFiles(snapshot,
    targetId ? 'Firebird database dashboard' : 'Firebird server dashboard',
    targetId ? 'database' : 'server'), [snapshot, targetId, engineMode]);
  const heartbeatValid = !policy.heartbeat_enabled || policy.heartbeat_timeout_seconds === null ||
    (Number.isInteger(policy.heartbeat_timeout_seconds) &&
      policy.heartbeat_timeout_seconds >= policy.interval_seconds + 5 && policy.heartbeat_timeout_seconds <= 3600);
  const changePolicy = async (remove=false) => {
    setBusy(true); setError('');
    try {
      const response = remove ? await getApiInstance().delete(endpoint) :
        await getApiInstance().post(endpoint, {...policy,
          heartbeat_timeout_seconds: policy.heartbeat_enabled ? policy.heartbeat_timeout_seconds : null,
          ...(snapshot?.attachment_mode !== 'embedded' && credentialMode === 'dedicated' ? {credentials} : {})});
      setSnapshot(response.data.data);
    } catch(err) {
      setError(err.response?.data?.errormsg || gettext('Monitoring policy change failed.'));
    } finally { setBusy(false); setCredentials((value) => ({...value, password: ''})); }
  };
  const showPolicy = policyMode && !engineMode;
  return <Box sx={{height: '100%', display: 'flex', flexDirection: 'column', gap: 1, p: 1, overflow: 'auto'}}>
    <FormReference formKey={showPolicy ? 'firebird-monitoring-policy' : 'firebird-dashboard'} />
    {!showPolicy && publishedVersion > 0 && <Box>Published layout revision {publishedVersion}</Box>}
    {error && <Alert severity="error">{error}</Alert>}
    {snapshot?.scope_note && <Alert severity="info">{snapshot.scope_note}</Alert>}
    {!showPolicy && snapshot && onNavigate && <Box aria-label="Dashboard navigation">
      <TextField select size="small" label={gettext('Open dashboard')} value=""
        sx={{width: '24rem', maxWidth: '100%'}} onChange={(event) => {
          const destination = JSON.parse(event.target.value);
          onNavigate(destination[0], destination[1] ?? undefined, destination[2]);
        }}>
        {engineMode ? (snapshot.servers || []).flatMap((server) => [
          <MenuItem key={`server:${server.server_id}`} value={JSON.stringify([server.server_id, null, server.name])}>{server.name}</MenuItem>,
          ...server.databases.map((database) => <MenuItem key={`${server.server_id}:${database.target_id}`}
            value={JSON.stringify([server.server_id, database.target_id, database.name])}>{server.name} / {database.name}</MenuItem>),
        ]) : [
          ...(targetId ? [<MenuItem key="server" value={JSON.stringify([serverId, null, snapshot.navigation?.name])}>{snapshot.attachment_mode === 'embedded' ? gettext('Registered files dashboard') : gettext('Server dashboard')}</MenuItem>] : []),
          ...(!targetId ? (snapshot.navigation?.databases || []).map((database) => <MenuItem key={database.target_id}
            value={JSON.stringify([serverId, database.target_id, database.name])}>{database.name}</MenuItem>) : []),
        ]}
      </TextField>
    </Box>}
    {!showPolicy && !engineMode && <FormControlLabel label={gettext('Persistent history')}
      control={<Checkbox checked={showHistory} onChange={(event) => setShowHistory(event.target.checked)} />} />}
    {!showPolicy && !engineMode && showHistory && <FirebirdHistoryView key={`${serverId}:${targetId || ''}`}
      serverId={serverId} targetId={targetId} />}
    {!showPolicy && !engineMode && snapshot?.samples?.length > 0 && <FormControlLabel label={gettext('Recent observations')}
      control={<Checkbox checked={showTrends} onChange={(event) => setShowTrends(event.target.checked)} />} />}
    {!showPolicy && !engineMode && snapshot && showTrends && <FirebirdTrendView
      key={`${serverId}:${targetId || ''}`} snapshot={snapshot} scope={targetId ? 'database' : 'server'} />}
    {!showPolicy && !engineMode && targetId && snapshot && <>
      <FormControlLabel label={gettext('Activity details')} control={<Checkbox checked={showActivity} onChange={(event) => setShowActivity(event.target.checked)} />} />
      {showActivity && <FirebirdActivityView snapshot={snapshot} serverId={serverId} targetId={targetId} />}
    </>}
    {!showPolicy && !targetId && snapshot && <FirebirdDatabaseRanking snapshot={snapshot} engineMode={engineMode} />}
    {!showPolicy && engineMode && snapshot && <FirebirdEngineTrends fleet={snapshot} />}
    {!showPolicy && !engineMode && snapshot && <FirebirdMonitoringDetails
      key={`details:${serverId}:${targetId || ''}`} serverId={serverId} targetId={targetId}
      sample={snapshot.samples?.at(-1)} />}
    {showPolicy ? <Box sx={{display: 'grid', gap: 1, gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 24rem))', '& > .MuiAlert-root, & > .MuiFormGroup-root': {gridColumn: '1 / -1'}}}>
      <Alert severity="info">{gettext('Collection uses a dedicated connection and continues without an open dashboard. This policy and its samples last only for this application process. Stop the current policy before changing it.')}</Alert>
      {snapshot?.authentication && <Alert severity="info">
        {gettext('Active monitoring account')}: {snapshot.authentication.username || gettext('Registration authentication')}
        {snapshot.authentication.role ? ` (${snapshot.authentication.role})` : ''}
      </Alert>}
      {snapshot?.attachment_mode === 'embedded' && <Alert severity="info">{gettext('Embedded collection uses authorized local file access. Passwords and network service authentication do not apply.')}</Alert>}
      {snapshot?.attachment_mode !== 'embedded' && <RadioGroup row aria-label={gettext('Monitoring authentication')} value={credentialMode}
        onChange={(event) => { setCredentialMode(event.target.value); setCredentials((value) => ({...value, password: ''})); }}>
        <FormControlLabel value="registration" control={<Radio />} label={gettext('Use current connection credentials')} />
        <FormControlLabel value="dedicated" control={<Radio />} label={gettext('Use dedicated monitoring account')} />
      </RadioGroup>}
      {snapshot?.attachment_mode !== 'embedded' && credentialMode === 'dedicated' && <>
        <TextField size="small" label={gettext('Monitoring username')} value={credentials.username}
          autoComplete="off" onChange={(event) => setCredentials({...credentials, username: event.target.value})} />
        <TextField size="small" label={gettext('Monitoring password')} type="password" value={credentials.password}
          autoComplete="new-password" onChange={(event) => setCredentials({...credentials, password: event.target.value})} />
        <TextField size="small" label={gettext('Monitoring role (optional)')} value={credentials.role}
          onChange={(event) => setCredentials({...credentials, role: event.target.value})} />
        <Alert severity="info">{gettext('Credentials are retained only for this process and collection lease. Stop collection before changing the account. Enter the password again after restart or a failed submission.')}</Alert>
      </>}
      {snapshot?.collection_available === false && <Alert severity="warning">{gettext('The host needs monitoring worker keys, single-process admission and a lock path before collection can start.')}</Alert>}
      {['interval_seconds', 'retain_samples', 'lease_seconds', 'metadata_interval_seconds'].map((key, index) =>
        <TextField key={key} size="small" type="number"
          label={[gettext('Sampling interval (seconds)'), gettext('Retained samples'), gettext('Collection lease (seconds)'), gettext('Metadata sampling interval (seconds)')][index]}
          value={policy[key]} onChange={(event) => setPolicy({...policy, [key]: Number(event.target.value)})} />)}
      <FormControlLabel label={gettext('Use completed refreshes as availability heartbeats')}
        control={<Checkbox checked={policy.heartbeat_enabled} onChange={(event) => setPolicy({...policy, heartbeat_enabled: event.target.checked})} />} />
      <FormControlLabel label={gettext('Archive observations in configured ScratchBird history')}
        control={<Checkbox checked={policy.history_enabled} onChange={(event) => setPolicy({...policy, history_enabled: event.target.checked})} />} />
      {snapshot?.history_storage && <Alert severity="info">History write: {snapshot.history_storage.status}.
        Unconfirmed writes: {snapshot.history_storage.failures}.</Alert>}
      {policy.heartbeat_enabled && <TextField size="small" type="number"
        label={gettext('Heartbeat overdue after (seconds)')}
        value={policy.heartbeat_timeout_seconds ?? ''} error={!heartbeatValid}
        inputProps={{min: policy.interval_seconds + 5, max: 3600}}
        helperText={gettext('Blank uses %s seconds; an explicit value must be between %s and 3600.',
          Math.max(15, policy.interval_seconds * 3), policy.interval_seconds + 5)}
        onChange={(event) => setPolicy({...policy, heartbeat_timeout_seconds:
          event.target.value === '' ? null : Number(event.target.value)})} />}
      {targetId && <>
        {['max_transaction_age_seconds', 'max_backup_state_seconds'].map((key, index) =>
          <TextField key={key} size="small" type="number" value={policy[key]}
            label={index ? 'Backup state observation threshold (seconds; 0 disables)' : 'Old transaction threshold (seconds; 0 disables)'}
            onChange={(event) => setPolicy({...policy, [key]: Number(event.target.value)})} />)}
        <FormControlLabel label="Require encrypted user wire attachments"
          control={<Checkbox checked={policy.require_wire_encryption}
            onChange={(event) => setPolicy({...policy, require_wire_encryption: event.target.checked})} />} />
        <TextField select size="small" label="Expected native database encryption state"
          value={policy.expected_encryption_state ?? ''}
          onChange={(event) => setPolicy({...policy, expected_encryption_state:
            event.target.value === '' ? null : Number(event.target.value)})}>
          <MenuItem value="">No expected state</MenuItem>
          {[0, 1, 2, 3].map((value) => <MenuItem key={value} value={value}>Native state {value}</MenuItem>)}
        </TextField>
      </>}
      <Box>
        <Button disabled={busy || !heartbeatValid || Boolean(snapshot?.authentication) || snapshot?.collection_available === false ||
          (snapshot?.attachment_mode !== 'embedded' && credentialMode === 'dedicated' && (!credentials.username || !credentials.password))} onClick={() => changePolicy()}>{gettext('Start collection')}</Button>
        <Button disabled={busy} onClick={() => changePolicy(true)}>{gettext('Stop collection')}</Button>
      </Box>
    </Box> : snapshot && <DDNViewerSurface files={files} snapshot={publishedView || undefined} entry="dashboard.ddn"
      view="dashboard" presentation viewSelection />}
  </Box>;
}
FirebirdMonitoring.propTypes = {serverId: PropTypes.number,
  targetId: PropTypes.string, policyMode: PropTypes.bool, engineMode: PropTypes.bool, onNavigate: PropTypes.func};
