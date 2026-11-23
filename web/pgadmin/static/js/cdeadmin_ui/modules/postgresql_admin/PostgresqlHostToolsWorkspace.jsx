/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import getApiInstance from 'sources/api_instance';
import {Box, Grid, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {NumberField, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {PostgresqlSectionCard, createPostgresqlServerCaller} from './postgresqlAdminHelpers';

const UTILITY_OPTIONS = [
  {value: 'host_pg_controldata', label: 'pg_controldata — Inspect cluster control file'},
  {value: 'host_pg_checksums', label: 'pg_checksums — Verify / enable / disable offline checksums'},
  {value: 'host_pg_walsummary', label: 'pg_walsummary — Inspect WAL summary files'},
  {value: 'host_pg_test_fsync', label: 'pg_test_fsync — Benchmark WAL storage sync methods'},
  {value: 'host_pg_test_timing', label: 'pg_test_timing — Measure host clock monotonicity'},
  {value: 'host_initdb', label: 'initdb — Initialize new cluster data directory'},
  {value: 'host_pg_amcheck', label: 'pg_amcheck — Verify heap and B-tree corruption'},
  {value: 'host_pg_createsubscriber', label: 'pg_createsubscriber — Convert physical standby to logical'},
  {value: 'host_pg_resetwal', label: 'pg_resetwal — Reset offline write-ahead log'},
  {value: 'host_pg_rewind', label: 'pg_rewind — Resynchronize diverged cluster timeline'},
  {value: 'host_pg_archivecleanup', label: 'pg_archivecleanup — Remove older WAL archive files'},
  {value: 'host_pgbench', label: 'pgbench — Run isolated scratch benchmark'},
  {value: 'host_pg_upgrade', label: 'pg_upgrade — Check or upgrade major cluster version'},
];

/**
 * PG-UI-01 (SR-F-030450): Supervised PostgreSQL 18 Host Utilities Workspace.
 * Uses 100% cdeadmin_ui primitives with zero MUI imports.
 */
export default function PostgresqlHostToolsWorkspace({
  endpointUrl,
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callServer = useMemo(
    () => createPostgresqlServerCaller(api, endpointUrl),
    [api, endpointUrl]
  );

  const [catalog, setCatalog] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [operationId, setOperationId] = useState('host_pg_controldata');
  const [clusterId, setClusterId] = useState('');
  const [initRootId, setInitRootId] = useState('');
  const [subdir, setSubdir] = useState('new_cluster');
  const [archiveId, setArchiveId] = useState('');
  const [oldestKeptWal, setOldestKeptWal] = useState('');
  const [upgradePairId, setUpgradePairId] = useState('');
  const [upgradeMode, setUpgradeMode] = useState('check');
  const [databaseName, setDatabaseName] = useState('postgres');
  const [durationSeconds, setDurationSeconds] = useState(3);
  const [dryRun, setDryRun] = useState(true);
  const [destructiveAck, setDestructiveAck] = useState(false);
  const [confirmation, setConfirmation] = useState('');

  const [reviewedJob, setReviewedJob] = useState(null);
  const [activeJob, setActiveJob] = useState(null);
  const [startConfirmed, setStartConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadCatalog = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [cat, list] = await Promise.all([
        callServer({action: 'postgresql_host_tools', request: {stage: 'catalog'}}),
        callServer({action: 'postgresql_host_tools', request: {stage: 'list', offset: 0, limit: 20}}).catch(() => ({jobs: []})),
      ]);
      setCatalog(cat);
      setJobs(list?.jobs || []);
      if (!clusterId && cat?.clusters?.[0]?.id) setClusterId(cat.clusters[0].id);
      if (!initRootId && cat?.init_roots?.[0]?.id) setInitRootId(cat.init_roots[0].id);
      if (!archiveId && cat?.archive_dirs?.[0]?.id) setArchiveId(cat.archive_dirs[0].id);
      if (!upgradePairId && cat?.upgrade_pairs?.[0]?.id) setUpgradePairId(cat.upgrade_pairs[0].id);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [archiveId, callServer, clusterId, initRootId, upgradePairId]);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);

  const buildDraft = () => {
    switch (operationId) {
    case 'host_initdb':
      return {
        init_root_id: initRootId,
        subdir: subdir.trim(),
        auth_host: 'scram-sha-256',
        auth_local: 'peer',
        confirmation: `${initRootId}/${subdir.trim()}`,
      };
    case 'host_pg_amcheck':
      return {
        database: databaseName.trim() || 'postgres',
        heapallindexed: true,
      };
    case 'host_pg_archivecleanup':
      return {
        archive_id: archiveId,
        oldest_kept_wal_file: oldestKeptWal.trim(),
        dry_run: Boolean(dryRun),
        confirmation: confirmation.trim() || archiveId,
      };
    case 'host_pg_upgrade':
      return {
        upgrade_pair_id: upgradePairId,
        mode: upgradeMode,
        confirmation: confirmation.trim() || upgradePairId,
      };
    case 'host_pgbench':
      return {
        database: databaseName.trim() || 'postgres',
        initialize: true,
        scale: 1,
        clients: 2,
        transactions: 10,
        scratch_schema_acknowledged: Boolean(destructiveAck),
        confirmation: confirmation.trim() || databaseName.trim(),
      };
    case 'host_pg_test_timing':
      return {
        duration_seconds: Number(durationSeconds) || 3,
        hostname_confirmation: confirmation.trim() || catalog?.hostname || '',
      };
    case 'host_pg_resetwal':
      return {
        cluster_id: clusterId,
        dry_run: Boolean(dryRun),
        stopped_cluster_acknowledged: true,
        destructive_data_loss_acknowledged: Boolean(destructiveAck),
        confirmation: confirmation.trim() || clusterId,
      };
    default:
      return {
        cluster_id: clusterId,
        ...(confirmation.trim() ? {confirmation: confirmation.trim()} : {}),
      };
    }
  };

  const handleReview = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_host_tools',
        request: {
          stage: 'review',
          operation_id: operationId,
          draft: buildDraft(),
        },
      });
      setReviewedJob(res);
      setStartConfirmed(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStart = async () => {
    if (!reviewedJob || !startConfirmed) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_host_tools',
        request: {
          stage: 'start',
          job_id: reviewedJob.job_id,
          review_digest: reviewedJob.review_digest,
          confirmed: true,
        },
      });
      setActiveJob(res);
      setReviewedJob(null);
      await loadCatalog();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRefreshJob = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_host_tools',
        request: {stage: 'status', job_id: jobId},
      });
      setActiveJob(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack gap="md">
      <PostgresqlSectionCard
        title={gettext('Supervised Application-Host & Cluster Utilities')}
        actions={<FormReference reference="SR-F-030450" />}
      >
        <Stack gap="sm">
          <Banner status="info">
            {gettext(
              'Executes reviewed native cluster and host utilities against operator-granted directories with durable non-replayable job receipts.'
            )}
          </Banner>
          {error && <ValidationMessage status="error">{error}</ValidationMessage>}
          <Grid columns={2} gap="sm">
            <Select
              label={gettext('Host Utility')}
              value={operationId}
              options={UTILITY_OPTIONS}
              onChange={(val) => {
                setOperationId(val);
                setReviewedJob(null);
              }}
            />
            <TextField
              label={gettext('Granted Cluster ID')}
              value={clusterId}
              onChange={(e) => setClusterId(e?.target ? e.target.value : e)}
            />
            {operationId === 'host_initdb' && (
              <>
                <TextField
                  label={gettext('Granted Init Root ID')}
                  value={initRootId}
                  onChange={(e) => setInitRootId(e?.target ? e.target.value : e)}
                />
                <TextField
                  label={gettext('New Cluster Subdirectory')}
                  value={subdir}
                  onChange={(e) => setSubdir(e?.target ? e.target.value : e)}
                />
              </>
            )}
            {(operationId === 'host_pg_amcheck' || operationId === 'host_pgbench') && (
              <TextField
                label={gettext('Target Database')}
                value={databaseName}
                onChange={(e) => setDatabaseName(e?.target ? e.target.value : e)}
              />
            )}
            {operationId === 'host_pg_archivecleanup' && (
              <>
                <TextField
                  label={gettext('Granted Archive Directory ID')}
                  value={archiveId}
                  onChange={(e) => setArchiveId(e?.target ? e.target.value : e)}
                />
                <TextField
                  label={gettext('Oldest Kept WAL File')}
                  value={oldestKeptWal}
                  onChange={(e) => setOldestKeptWal(e?.target ? e.target.value : e)}
                />
              </>
            )}
            {operationId === 'host_pg_upgrade' && (
              <>
                <TextField
                  label={gettext('Granted Upgrade Pair ID')}
                  value={upgradePairId}
                  onChange={(e) => setUpgradePairId(e?.target ? e.target.value : e)}
                />
                <Select
                  label={gettext('Upgrade Mode')}
                  value={upgradeMode}
                  options={[
                    {value: 'check', label: '--check (Non-destructive compatibility check)'},
                    {value: 'copy', label: 'Copy upgrade'},
                    {value: 'clone', label: '--clone upgrade'},
                  ]}
                  onChange={setUpgradeMode}
                />
              </>
            )}
            {operationId === 'host_pg_test_timing' && (
              <NumberField
                label={gettext('Duration (seconds)')}
                value={durationSeconds}
                min={1}
                max={30}
                onChange={(v) => setDurationSeconds(Number(v) || 1)}
              />
            )}
            <TextField
              label={gettext('Typed Target Confirmation')}
              value={confirmation}
              onChange={(e) => setConfirmation(e?.target ? e.target.value : e)}
            />
          </Grid>
          <Stack direction="row" gap="md">
            <Checkbox
              label={gettext('Dry-run / check only where supported')}
              checked={dryRun}
              onChange={setDryRun}
            />
            <Checkbox
              label={gettext('Acknowledge scratch or offline mutation boundary')}
              checked={destructiveAck}
              onChange={setDestructiveAck}
            />
          </Stack>
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy} onClick={handleReview}>
              {gettext('Review Utility Plan')}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={loadCatalog}>
              {gettext('Refresh Grants & Receipts')}
            </Button>
          </Stack>
        </Stack>
      </PostgresqlSectionCard>

      {reviewedJob && (
        <PostgresqlSectionCard title={gettext('Reviewed Utility Execution Receipt')}>
          <Stack gap="sm">
            <Box>
              <Badge status="warning" label={reviewedJob.operation_id} />{' '}
              <span>{gettext('Digest:')} {reviewedJob.review_digest}</span>
            </Box>
            <Checkbox
              label={gettext('Confirm one-time utility dispatch (no automatic replay)')}
              checked={startConfirmed}
              onChange={setStartConfirmed}
            />
            <Button variant="primary" disabled={busy || !startConfirmed} onClick={handleStart}>
              {gettext('Start Supervised Utility')}
            </Button>
          </Stack>
        </PostgresqlSectionCard>
      )}

      {(activeJob || jobs.length > 0) && (
        <PostgresqlSectionCard title={gettext('Utility Output & Job History')}>
          <Stack gap="sm">
            {activeJob && (
              <CodeEditor
                value={JSON.stringify(activeJob, null, 2)}
                language="json"
                readOnly
                height="220px"
              />
            )}
            <Stack direction="row" gap="sm">
              {jobs.slice(0, 6).map((j) => (
                <Button
                  key={j.job_id}
                  variant="secondary"
                  onClick={() => handleRefreshJob(j.job_id)}
                >
                  {`${j.operation_id} (${j.state})`}
                </Button>
              ))}
            </Stack>
          </Stack>
        </PostgresqlSectionCard>
      )}
    </Stack>
  );
}

PostgresqlHostToolsWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
