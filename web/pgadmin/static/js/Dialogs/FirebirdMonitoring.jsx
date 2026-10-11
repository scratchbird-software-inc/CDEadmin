import FirebirdActivityView from './FirebirdActivityView';
import FirebirdMonitoringDetails from './FirebirdMonitoringDetails';
import FirebirdDatabaseRanking from './FirebirdDatabaseRanking';
import FirebirdEngineTrends from './FirebirdEngineTrends';
import FirebirdTrendView from './FirebirdTrendView';
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
import {firebirdDashboardFiles, firebirdFleetFiles, firebirdServerDatabaseFiles} from '../cdeadmin_ui/integrations/ddn/firebirdDashboard';

export default function FirebirdMonitoring({serverId, targetId, policyMode=false, engineMode=false, onNavigate}) {
  const [snapshot, setSnapshot] = useState(null);
  const [showTrends, setShowTrends] = useState(false);
  const [showActivity, setShowActivity] = useState(false);
  const [publishedView, setPublishedView] = useState(null);
  const [publishedVersion, setPublishedVersion] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [credentialMode, setCredentialMode] = useState('registration');
  const [credentials, setCredentials] = useState({username: '', password: '', role: ''});
  const [policy, setPolicy] = useState({interval_seconds: targetId ? 5 : 15,
    retain_samples: 120, lease_seconds: 3600, heartbeat_enabled: false, metadata_interval_seconds: 60,
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
            rendered = bindPublication(libraries.viewer, publication.snapshot, scope, live);
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
  const databaseFiles = useMemo(() => firebirdServerDatabaseFiles(snapshot), [snapshot]);
  const changePolicy = async (remove=false) => {
    setBusy(true); setError('');
    try {
      const response = remove ? await getApiInstance().delete(endpoint) :
        await getApiInstance().post(endpoint, {...policy,
          ...(credentialMode === 'dedicated' ? {credentials} : {})});
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
    {!showPolicy && snapshot && onNavigate && <Box aria-label="Dashboard navigation">
      {engineMode ? (snapshot.servers || []).map((server) => <Box key={server.server_id}>
        <Button onClick={() => onNavigate(server.server_id, undefined, server.name)}>{server.name}</Button>
        {server.databases.map((database) => <Button key={database.target_id}
          onClick={() => onNavigate(server.server_id, database.target_id, database.name)}>{database.name}</Button>)}
      </Box>) : <>
        {targetId && <Button onClick={() => onNavigate(serverId, undefined, snapshot.navigation?.name)}>Server dashboard</Button>}
        {!targetId && (snapshot.navigation?.databases || []).map((database) => <Button key={database.target_id}
          onClick={() => onNavigate(serverId, database.target_id, database.name)}>{database.name}</Button>)}
      </>}
    </Box>}
    {!showPolicy && !engineMode && snapshot?.samples?.length > 0 && <Button
      onClick={() => setShowTrends(!showTrends)}>{showTrends ? 'Hide recent observations' : 'View recent observations'}</Button>}
    {!showPolicy && !engineMode && snapshot && showTrends && <FirebirdTrendView
      key={`${serverId}:${targetId || ''}`} snapshot={snapshot} scope={targetId ? 'database' : 'server'} />}
    {!showPolicy && !engineMode && targetId && snapshot && <>
      <Button onClick={() => setShowActivity(!showActivity)}>{showActivity ? 'Hide activity details' : 'View activity details'}</Button>
      {showActivity && <FirebirdActivityView snapshot={snapshot} serverId={serverId} targetId={targetId} />}
    </>}
    {!showPolicy && !engineMode && !targetId && snapshot && <DDNViewerSurface
      files={databaseFiles} entry="dashboard.ddn" view="dashboard" presentation />}
    {!showPolicy && !targetId && snapshot && <FirebirdDatabaseRanking snapshot={snapshot} engineMode={engineMode} />}
    {!showPolicy && engineMode && snapshot && <FirebirdEngineTrends fleet={snapshot} />}
    {!showPolicy && !engineMode && snapshot && <FirebirdMonitoringDetails
      key={`details:${serverId}:${targetId || ''}`} serverId={serverId} targetId={targetId}
      sample={snapshot.samples?.at(-1)} />}
    {showPolicy ? <>
      <Alert severity="info">{gettext('Collection uses a dedicated connection and continues without an open dashboard. This policy and its samples last only for this application process. Stop the current policy before changing it.')}</Alert>
      {snapshot?.authentication && <Alert severity="info">
        {gettext('Active monitoring account')}: {snapshot.authentication.username || gettext('Registration authentication')}
        {snapshot.authentication.role ? ` (${snapshot.authentication.role})` : ''}
      </Alert>}
      <RadioGroup aria-label={gettext('Monitoring authentication')} value={credentialMode}
        onChange={(event) => { setCredentialMode(event.target.value); setCredentials((value) => ({...value, password: ''})); }}>
        <FormControlLabel value="registration" control={<Radio />} label={gettext('Use registration credentials')} />
        <FormControlLabel value="dedicated" control={<Radio />} label={gettext('Use dedicated monitoring account')} />
      </RadioGroup>
      {credentialMode === 'dedicated' && <>
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
        <Button disabled={busy || Boolean(snapshot?.authentication) || snapshot?.collection_available === false ||
          (credentialMode === 'dedicated' && (!credentials.username || !credentials.password))} onClick={() => changePolicy()}>{gettext('Start collection')}</Button>
        <Button disabled={busy} onClick={() => changePolicy(true)}>{gettext('Stop collection')}</Button>
      </Box>
    </> : snapshot && <DDNViewerSurface files={files} snapshot={publishedView || undefined} entry="dashboard.ddn"
      view="dashboard" presentation />}
  </Box>;
}
FirebirdMonitoring.propTypes = {serverId: PropTypes.number,
  targetId: PropTypes.string, policyMode: PropTypes.bool, engineMode: PropTypes.bool, onNavigate: PropTypes.func};
