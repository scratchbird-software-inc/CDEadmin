/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Grid, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {NumberField, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import {
  MariaDBJobsTable,
  MariaDBReviewCard,
  MariaDBSectionCard,
  useMariaDBServerApi,
} from './mariadbAdminHelpers';

const GALERA_OPERATIONS = [
  {value: 'bootstrap_cluster', label: 'Bootstrap Galera Primary Cluster (grastate.dat verified)'},
  {value: 'join_node', label: 'Join Member Node to Primary Galera Cluster'},
  {value: 'rejoin_node', label: 'Rejoin Existing Member & Wait for IST/SST Sync'},
  {value: 'set_desync', label: 'Toggle wsrep_desync Maintenance Mode'},
  {value: 'recover_quorum', label: 'Promote Non-Primary Quorum (pc.bootstrap=YES)'},
  {value: 'stop_node', label: 'Cleanly Stop Galera Member'},
];

/**
 * MDB-UI-05 (SR-F-030344): MariaDB Native wsrep / Galera Cluster Membership,
 * grastate.dat Bootstrap, IST/SST Join & Quorum Recovery Workspace (`tab="mariadb-galera"`).
 */
export default function MariaDBGaleraWorkspace({endpointUrl, api = null}) {
  const {callServer} = useMariaDBServerApi(endpointUrl, api);

  const [nodeObservation, setNodeObservation] = useState(null);
  const [grastateInfo, setGrastateInfo] = useState(null);
  const [clusterObservation, setClusterObservation] = useState(null);
  const [review, setReview] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // Inspection & operation options
  const [datadir, setDatadir] = useState('/var/lib/mysql');
  const [providerPath, setProviderPath] = useState('');
  const [peerServerIdsCsv, setPeerServerIdsCsv] = useState('');
  const [operation, setOperation] = useState('bootstrap_cluster');
  const [bootstrapMode, setBootstrapMode] = useState('grastate_and_verify');
  const [peerDatadirsCsv, setPeerDatadirsCsv] = useState('');
  const [forceSafeToBootstrap, setForceSafeToBootstrap] = useState(false);
  const [seedServerId, setSeedServerId] = useState('');
  const [expectedClusterSize, setExpectedClusterSize] = useState(2);
  const [startManagedDaemon, setStartManagedDaemon] = useState(false);
  const [mariadbdBinary, setMariadbdBinary] = useState('mariadbd');
  const [desyncEnabled, setDesyncEnabled] = useState(true);
  const [timeoutSeconds, setTimeoutSeconds] = useState(90);

  const loadNodeAndJobs = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [obs, jobRes] = await Promise.all([
        callServer({action: 'mariadb_galera_inspect', request: {}}).catch(() => null),
        callServer({action: 'mariadb_galera_list', request: {offset: 0, limit: 25}}).catch(() => ({jobs: []})),
      ]);
      if (obs) setNodeObservation(obs);
      setJobs(jobRes?.jobs || []);
    } catch (err) {
      setError(err.message || gettext('Failed to inspect MariaDB Galera wsrep status.'));
    } finally {
      setBusy(false);
    }
  }, [callServer]);

  useEffect(() => {
    loadNodeAndJobs();
  }, [loadNodeAndJobs]);

  const parsePeerIds = () =>
    peerServerIdsCsv
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => (Number.isFinite(Number(s)) ? Number(s) : s));

  const handleInspectGrastate = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_galera_inspect_grastate',
        request: {datadir: datadir.trim()},
      });
      setGrastateInfo(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleInspectCluster = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_galera_inspect_cluster',
        request: {peer_server_ids: parsePeerIds()},
      });
      setClusterObservation(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleReview = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const options = {
        operation,
        timeout_seconds: Number(timeoutSeconds) || 90,
      };
      if (datadir.trim()) options.datadir = datadir.trim();
      if (operation === 'bootstrap_cluster') {
        options.bootstrap_mode = bootstrapMode;
        options.force_safe_to_bootstrap = Boolean(forceSafeToBootstrap);
        if (providerPath.trim()) options.host_provider_path = providerPath.trim();
        const pdirs = peerDatadirsCsv
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        if (pdirs.length > 0) options.peer_datadirs = pdirs;
        const pids = parsePeerIds();
        if (pids.length > 0) options.peer_server_ids = pids;
        if (bootstrapMode === 'managed_daemon') {
          options.mariadbd_binary = mariadbdBinary.trim() || 'mariadbd';
        }
      } else if (operation === 'join_node' || operation === 'rejoin_node') {
        if (seedServerId.trim()) {
          options.seed_server_id = Number.isFinite(Number(seedServerId))
            ? Number(seedServerId)
            : seedServerId.trim();
        }
        options.expected_cluster_size = Number(expectedClusterSize) || 2;
        options.start_managed_daemon = Boolean(startManagedDaemon);
        if (startManagedDaemon) {
          options.mariadbd_binary = mariadbdBinary.trim() || 'mariadbd';
        }
      } else if (operation === 'set_desync') {
        options.enabled = Boolean(desyncEnabled);
      } else if (operation === 'recover_quorum') {
        options.peer_server_ids = parsePeerIds();
      }

      const res = await callServer({
        action: 'mariadb_galera_review',
        request: {options},
      });
      setReview(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleStart = async (reviewed) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_galera_start',
        request: {
          job_id: reviewed.job_id,
          review_digest: reviewed.review_digest,
          confirmed: true,
        },
      });
      setReview(null);
      setSelectedJob(res);
      setNotice(gettext('Executed MariaDB Galera operation ') + res.job_id);
      await loadNodeAndJobs();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box style={{padding: '12px', overflow: 'auto'}} data-testid="mariadb-galera-workspace">
      <Stack direction="column" gap={3}>
        <Stack direction="row" style={{flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between'}}>
          <Stack direction="row" gap={1} style={{alignItems: 'center'}}>
            <strong>{gettext('MariaDB Galera (wsrep) Cluster Administration')}</strong>
            <FormReference formKey="mariadb-galera-workspace" />
          </Stack>
          <Button size="sm" intent="neutral" disabled={busy} onClick={loadNodeAndJobs}>
            {gettext('Refresh Node wsrep Status')}
          </Button>
        </Stack>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}
        {notice && <Banner status="success">{notice}</Banner>}

        {nodeObservation && (
          <MariaDBSectionCard title={gettext('Live wsrep Node Observation')}>
            <Stack direction="row" gap={2} style={{flexWrap: 'wrap', alignItems: 'center'}}>
              <Badge status={nodeObservation.galera_available ? 'success' : 'warning'} label={nodeObservation.galera_available
                  ? gettext('wsrep Provider Loaded')
                  : nodeObservation.availability_reason || gettext('wsrep Inactive')} />
              {nodeObservation.cluster?.wsrep_cluster_status && (
                <Badge status="info" label={nodeObservation.cluster.wsrep_cluster_status} />
              )}
              {nodeObservation.cluster?.wsrep_cluster_size !== undefined && (
                <span>
                  <strong>{gettext('Cluster Size:')}</strong>{' '}
                  <code>{nodeObservation.cluster.wsrep_cluster_size}</code>
                </span>
              )}
              {nodeObservation.local_member?.wsrep_local_state_comment && (
                <span>
                  <strong>{gettext('Member State:')}</strong>{' '}
                  <code>{nodeObservation.local_member.wsrep_local_state_comment}</code>
                </span>
              )}
              {nodeObservation.local_member?.wsrep_last_committed !== undefined && (
                <span>
                  <strong>{gettext('Last Committed Seqno:')}</strong>{' '}
                  <code>{nodeObservation.local_member.wsrep_last_committed}</code>
                </span>
              )}
            </Stack>
          </MariaDBSectionCard>
        )}

        <MariaDBSectionCard title={gettext('Inspect grastate.dat & Multi-Node Quorum')}>
          <Stack direction="column" gap={2}>
            <Grid columns={3} gap={2}>
              <TextField
                label={gettext('Host Datadir (for grastate.dat)')}
                value={datadir}
                onChange={(e) => setDatadir(e.target.value)}
              />
              <TextField
                label={gettext('Galera Provider Library Path (optional)')}
                value={providerPath}
                onChange={(e) => setProviderPath(e.target.value)}
              />
              <TextField
                label={gettext('Registered Peer Server IDs (comma-separated)')}
                value={peerServerIdsCsv}
                onChange={(e) => setPeerServerIdsCsv(e.target.value)}
              />
            </Grid>
            <Stack direction="row" gap={1}>
              <Button intent="neutral" disabled={busy || !datadir.trim()} onClick={handleInspectGrastate}>
                {gettext('Inspect grastate.dat')}
              </Button>
              <Button intent="neutral" disabled={busy} onClick={handleInspectCluster}>
                {gettext('Inspect Cluster Membership & UUIDs')}
              </Button>
            </Stack>
            {(grastateInfo || clusterObservation) && (
              <Box
                style={{
                  maxHeight: 180,
                  overflow: 'auto',
                  padding: '8px',
                  border: '1px solid var(--cde-border-subtle, #d0d7de)',
                  fontFamily: 'monospace',
                  fontSize: '0.78rem',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {JSON.stringify({grastate: grastateInfo, cluster: clusterObservation}, null, 2)}
              </Box>
            )}
          </Stack>
        </MariaDBSectionCard>

        <MariaDBSectionCard title={gettext('Plan Supervised Galera Cluster Operation')}>
          <Stack direction="column" gap={2}>
            <Grid columns={3} gap={2}>
              <Select
                label={gettext('Galera Operation')}
                value={operation}
                options={GALERA_OPERATIONS}
                onChange={(val) => setOperation(val)}
              />
              <NumberField
                label={gettext('Sync Wait Timeout (seconds)')}
                value={timeoutSeconds}
                min={5}
                max={3600}
                onChange={(e) => setTimeoutSeconds(Number(e.target.value))}
              />
              {operation === 'bootstrap_cluster' && (
                <Select
                  label={gettext('Bootstrap Mode')}
                  value={bootstrapMode}
                  options={[
                    {value: 'grastate_and_verify', label: 'Validate grastate.dat & Verify Synced'},
                    {value: 'managed_daemon', label: 'Start Managed mariadbd --wsrep-new-cluster'},
                    {value: 'promote_live_quorum', label: 'Promote Live Quorum (pc.bootstrap=YES)'},
                  ]}
                  onChange={(val) => setBootstrapMode(val)}
                />
              )}
            </Grid>

            {operation === 'bootstrap_cluster' && (
              <Stack direction="column" gap={2}>
                <Grid columns={2} gap={2}>
                  <TextField
                    label={gettext('Peer Datadirs for Highest-Seqno Check (optional CSV)')}
                    value={peerDatadirsCsv}
                    onChange={(e) => setPeerDatadirsCsv(e.target.value)}
                  />
                  {bootstrapMode === 'managed_daemon' && (
                    <TextField
                      label={gettext('mariadbd Binary')}
                      value={mariadbdBinary}
                      onChange={(e) => setMariadbdBinary(e.target.value)}
                    />
                  )}
                </Grid>
                <Checkbox
                  label={gettext('Force safe_to_bootstrap=1 override when grastate.dat reports 0 (requires verified highest seqno)')}
                  checked={forceSafeToBootstrap}
                  onChange={(checked) => setForceSafeToBootstrap(Boolean(checked))}
                />
              </Stack>
            )}

            {(operation === 'join_node' || operation === 'rejoin_node') && (
              <Stack direction="column" gap={2}>
                <Grid columns={3} gap={2}>
                  <TextField
                    label={gettext('Primary Seed Server ID')}
                    value={seedServerId}
                    onChange={(e) => setSeedServerId(e.target.value)}
                  />
                  <NumberField
                    label={gettext('Expected Minimum Cluster Size')}
                    value={expectedClusterSize}
                    min={2}
                    max={64}
                    onChange={(e) => setExpectedClusterSize(Number(e.target.value))}
                  />
                  <TextField
                    label={gettext('mariadbd Binary (if starting daemon)')}
                    value={mariadbdBinary}
                    onChange={(e) => setMariadbdBinary(e.target.value)}
                  />
                </Grid>
                <Checkbox
                  label={gettext('Start managed joiner mariadbd daemon before waiting for Synced')}
                  checked={startManagedDaemon}
                  onChange={(checked) => setStartManagedDaemon(Boolean(checked))}
                />
              </Stack>
            )}

            {operation === 'set_desync' && (
              <Checkbox
                label={gettext('Enable wsrep_desync=ON on this member')}
                checked={desyncEnabled}
                onChange={(checked) => setDesyncEnabled(Boolean(checked))}
              />
            )}

            <Stack direction="row" gap={1}>
              <Button intent="primary" disabled={busy} onClick={handleReview}>
                {gettext('Review Galera Operation')}
              </Button>
            </Stack>
          </Stack>
        </MariaDBSectionCard>

        <MariaDBReviewCard
          title={gettext('MariaDB Galera Operation Review')}
          review={review}
          busy={busy}
          confirmLabel={gettext('Confirm & Execute Galera Operation')}
          onConfirm={handleStart}
          onClear={() => setReview(null)}
        />

        <MariaDBJobsTable
          title={gettext('MariaDB Galera Cluster Jobs')}
          jobs={jobs}
          kindKey="galera_operation"
          busy={busy}
          selectedJob={selectedJob}
          onSelect={setSelectedJob}
          onRefreshJob={async (jid) => {
            const st = await callServer({action: 'mariadb_galera_status', request: {job_id: jid}});
            setSelectedJob(st);
            await loadNodeAndJobs();
          }}
        />
      </Stack>
    </Box>
  );
}

MariaDBGaleraWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
