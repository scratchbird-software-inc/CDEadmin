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

const PHASE_OPTIONS = [
  {value: 'backup', label: 'Full Physical Backup (mariadb-backup --backup)'},
  {value: 'incremental', label: 'Incremental Backup (--incremental-basedir / --incremental-lsn)'},
  {value: 'prepare', label: 'Staged Chain Prepare (--prepare / --apply-log-only)'},
  {value: 'copy_back', label: 'Copy-Back to Offline Datadir (--copy-back)'},
  {value: 'move_back', label: 'Move-Back to Offline Datadir (--move-back)'},
  {value: 'recover', label: 'Start Isolated Read-Only Recovery & PITR Catch-Up'},
];

/**
 * MDB-UI-01 (SR-F-030340): MariaDB Physical Backups, Incremental Prepare,
 * Isolated Recovery & One-Use Production Cutover Workspace (`tab="mariadb-physical"`).
 */
export default function MariaDBPhysicalWorkspace({endpointUrl, api = null}) {
  const {callServer} = useMariaDBServerApi(endpointUrl, api);

  const [sourceState, setSourceState] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [cutovers, setCutovers] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [review, setReview] = useState(null);
  const [cutoverReview, setCutoverReview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // Physical operation fields
  const [phase, setPhase] = useState('backup');
  const [backupBinary, setBackupBinary] = useState('mariadb-backup');
  const [versionPrefix, setVersionPrefix] = useState('12.2.2');
  const [sourceDatadir, setSourceDatadir] = useState('');
  const [parallel, setParallel] = useState(2);
  const [timeoutSeconds, setTimeoutSeconds] = useState(3600);
  const [encryptionAcknowledged, setEncryptionAcknowledged] = useState(false);

  // Incremental / Prepare / Copy-Back / Recover phase options
  const [parentJobId, setParentJobId] = useState('');
  const [incrementalMode, setIncrementalMode] = useState('basedir');
  const [baseJobId, setBaseJobId] = useState('');
  const [incrementalJobIdsCsv, setIncrementalJobIdsCsv] = useState('');
  const [memoryMiB, setMemoryMiB] = useState(256);
  const [preparedJobId, setPreparedJobId] = useState('');
  const [targetDatadir, setTargetDatadir] = useState('');
  const [restoreJobId, setRestoreJobId] = useState('');
  const [recoveryPort, setRecoveryPort] = useState(13307);
  const [recoveryServerId, setRecoveryServerId] = useState(99173);
  const [pitrArchiveIdsCsv, setPitrArchiveIdsCsv] = useState('');
  const [pitrStopGtid, setPitrStopGtid] = useState('');

  // Cutover options
  const [cutoverRecoveryJobId, setCutoverRecoveryJobId] = useState('');
  const [targetConfirmation, setTargetConfirmation] = useState('');
  const [fenceOldPrimary, setFenceOldPrimary] = useState(true);
  const [updateTargetRegistration, setUpdateTargetRegistration] = useState(true);
  const [promoteWritable, setPromoteWritable] = useState(true);

  const loadAll = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [inspected, jobRes, cutoverRes] = await Promise.all([
        callServer({action: 'mariadb_physical_inspect', request: {}}).catch(() => null),
        callServer({action: 'mariadb_physical_list', request: {offset: 0, limit: 25}}).catch(() => ({jobs: []})),
        callServer({action: 'mariadb_physical_cutover_list', request: {offset: 0, limit: 25}}).catch(() => ({cutovers: []})),
      ]);
      if (inspected) setSourceState(inspected);
      setJobs(jobRes?.jobs || []);
      setCutovers(cutoverRes?.cutovers || cutoverRes?.items || []);
    } catch (err) {
      setError(err.message || gettext('Failed to inspect MariaDB physical backup state.'));
    } finally {
      setBusy(false);
    }
  }, [callServer]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const buildPhaseOptions = () => {
    const opts = {
      phase,
      backup_binary: backupBinary.trim() || 'mariadb-backup',
      version_prefix: versionPrefix.trim() || '12.2.2',
      parallel: Number(parallel) || 1,
      timeout_seconds: Number(timeoutSeconds) || 3600,
    };
    if (encryptionAcknowledged) {
      opts.encryption_acknowledged = true;
    }
    if (phase === 'backup' || phase === 'incremental') {
      if (sourceDatadir.trim()) opts.source_datadir = sourceDatadir.trim();
      if (phase === 'incremental') {
        opts.parent_job_id = parentJobId.trim();
        opts.incremental_mode = incrementalMode;
      }
    } else if (phase === 'prepare') {
      opts.base_job_id = baseJobId.trim();
      opts.incremental_job_ids = incrementalJobIdsCsv
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      opts.memory_bytes = (Number(memoryMiB) || 256) * 1024 * 1024;
    } else if (phase === 'copy_back' || phase === 'move_back') {
      opts.prepared_job_id = preparedJobId.trim();
      opts.target_datadir = targetDatadir.trim();
    } else if (phase === 'recover') {
      opts.restore_job_id = restoreJobId.trim();
      opts.recovery_port = Number(recoveryPort) || 13307;
      opts.recovery_server_id = Number(recoveryServerId) || 99173;
      const archIds = pitrArchiveIdsCsv
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      if (archIds.length > 0 || pitrStopGtid.trim()) {
        opts.pitr = {
          archive_job_ids: archIds,
          ...(pitrStopGtid.trim() ? {stop_gtid: pitrStopGtid.trim()} : {}),
        };
      }
    }
    return opts;
  };

  const handleReviewPhase = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await callServer({
        action: 'mariadb_physical_review',
        request: {options: buildPhaseOptions()},
      });
      setReview(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleStartPhase = async (reviewed) => {
    setBusy(true);
    setError('');
    try {
      const started = await callServer({
        action: 'mariadb_physical_start',
        request: {
          job_id: reviewed.job_id,
          review_digest: reviewed.review_digest,
          confirmed: true,
        },
      });
      setReview(null);
      setSelectedJob(started);
      setNotice(gettext('Dispatched MariaDB physical job ') + started.job_id);
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRefreshJob = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const st = await callServer({action: 'mariadb_physical_status', request: {job_id: jobId}});
      setSelectedJob(st);
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleCancelJob = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const st = await callServer({action: 'mariadb_physical_cancel', request: {job_id: jobId}});
      setSelectedJob(st);
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleReconcileJob = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const st = await callServer({
        action: 'mariadb_physical_reconcile',
        request: {job_id: jobId, confirmed: true},
      });
      setSelectedJob(st);
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleStopRecovery = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const st = await callServer({
        action: 'mariadb_physical_stop_recovery',
        request: {job_id: jobId, confirmed: true},
      });
      setSelectedJob(st);
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleReviewCutover = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_physical_cutover_review',
        request: {
          recovery_job_id: cutoverRecoveryJobId.trim(),
          target_confirmation: targetConfirmation.trim(),
          fence_old_primary: Boolean(fenceOldPrimary),
          update_target_registration: Boolean(updateTargetRegistration),
          promote_writable: Boolean(promoteWritable),
        },
      });
      setCutoverReview(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleStartCutover = async (reviewed) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_physical_cutover_start',
        request: {
          cutover_id: reviewed.cutover_id,
          review_digest: reviewed.review_digest,
          confirmed: true,
        },
      });
      setCutoverReview(null);
      setSelectedJob(res);
      setNotice(gettext('Completed MariaDB one-use cutover ') + res.cutover_id);
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRollbackCutover = async (cutoverId) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_physical_cutover_rollback',
        request: {cutover_id: cutoverId, confirmed: true},
      });
      setSelectedJob(res);
      setNotice(gettext('Rolled back MariaDB cutover ') + cutoverId);
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box style={{padding: '12px', overflow: 'auto'}} data-testid="mariadb-physical-workspace">
      <Stack direction="column" gap={3}>
        <Stack direction="row" style={{flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between'}}>
          <Stack direction="row" gap={1} style={{alignItems: 'center'}}>
            <strong>{gettext('MariaDB Physical Backups, Recovery & Cutover')}</strong>
            <FormReference formKey="mariadb-physical-workspace" />
          </Stack>
          <Button size="sm" intent="neutral" disabled={busy} onClick={loadAll}>
            {gettext('Refresh Live State')}
          </Button>
        </Stack>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}
        {notice && <Banner status="success">{notice}</Banner>}

        {sourceState && (
          <MariaDBSectionCard title={gettext('Live MariaDB Source Inspection')}>
            <Stack direction="row" gap={2} style={{flexWrap: 'wrap', alignItems: 'center'}}>
              <Badge status="info" label={sourceState.source?.version || 'MariaDB'} />
              <span>
                <strong>{gettext('Server UID:')}</strong>{' '}
                <code>{sourceState.source?.server_uid || '—'}</code>
              </span>
              <span>
                <strong>{gettext('Datadir:')}</strong>{' '}
                <code>{sourceState.state?.datadir || '—'}</code>
              </span>
              <span>
                <strong>{gettext('GTID Binlog Pos:')}</strong>{' '}
                <code>{sourceState.state?.gtid_binlog_pos || '—'}</code>
              </span>
            </Stack>
          </MariaDBSectionCard>
        )}

        <MariaDBSectionCard title={gettext('Plan Physical Backup, Chain Prepare, Restore or Isolated Recovery')}>
          <Stack direction="column" gap={2}>
            <Grid columns={3} gap={2}>
              <Select
                label={gettext('Physical Phase')}
                value={phase}
                options={PHASE_OPTIONS}
                onChange={(val) => setPhase(val)}
              />
              <TextField
                label={gettext('mariadb-backup Binary')}
                value={backupBinary}
                onChange={(e) => setBackupBinary(e.target.value)}
              />
              <TextField
                label={gettext('Required Version Prefix')}
                value={versionPrefix}
                onChange={(e) => setVersionPrefix(e.target.value)}
              />
              <NumberField
                label={gettext('Parallel Threads')}
                value={parallel}
                min={1}
                max={64}
                onChange={(e) => setParallel(Number(e.target.value))}
              />
              <NumberField
                label={gettext('Timeout (seconds)')}
                value={timeoutSeconds}
                min={1}
                max={604800}
                onChange={(e) => setTimeoutSeconds(Number(e.target.value))}
              />
              {(phase === 'backup' || phase === 'incremental') && (
                <TextField
                  label={gettext('Source Datadir Override (optional)')}
                  value={sourceDatadir}
                  onChange={(e) => setSourceDatadir(e.target.value)}
                />
              )}
            </Grid>

            {phase === 'incremental' && (
              <Grid columns={2} gap={2}>
                <TextField
                  label={gettext('Parent Backup Job ID')}
                  value={parentJobId}
                  onChange={(e) => setParentJobId(e.target.value)}
                />
                <Select
                  label={gettext('Incremental Mode')}
                  value={incrementalMode}
                  options={[
                    {value: 'basedir', label: '--incremental-basedir (Verified Job Dir)'},
                    {value: 'lsn', label: '--incremental-lsn (Checkpoint LSN)'},
                  ]}
                  onChange={(val) => setIncrementalMode(val)}
                />
              </Grid>
            )}

            {phase === 'prepare' && (
              <Grid columns={3} gap={2}>
                <TextField
                  label={gettext('Base Full Backup Job ID')}
                  value={baseJobId}
                  onChange={(e) => setBaseJobId(e.target.value)}
                />
                <TextField
                  label={gettext('Ordered Incremental Job IDs (comma-separated)')}
                  value={incrementalJobIdsCsv}
                  onChange={(e) => setIncrementalJobIdsCsv(e.target.value)}
                />
                <NumberField
                  label={gettext('Prepare Memory (MiB)')}
                  value={memoryMiB}
                  min={64}
                  max={16384}
                  onChange={(e) => setMemoryMiB(Number(e.target.value))}
                />
              </Grid>
            )}

            {(phase === 'copy_back' || phase === 'move_back') && (
              <Grid columns={2} gap={2}>
                <TextField
                  label={gettext('Prepared Chain Job ID')}
                  value={preparedJobId}
                  onChange={(e) => setPreparedJobId(e.target.value)}
                />
                <TextField
                  label={gettext('Offline Target Datadir')}
                  value={targetDatadir}
                  onChange={(e) => setTargetDatadir(e.target.value)}
                />
              </Grid>
            )}

            {phase === 'recover' && (
              <Grid columns={4} gap={2}>
                <TextField
                  label={gettext('Copy-Back / Move-Back Restore Job ID')}
                  value={restoreJobId}
                  onChange={(e) => setRestoreJobId(e.target.value)}
                />
                <NumberField
                  label={gettext('Isolated Recovery Port')}
                  value={recoveryPort}
                  min={1024}
                  max={65535}
                  onChange={(e) => setRecoveryPort(Number(e.target.value))}
                />
                <TextField
                  label={gettext('PITR Archive Job IDs (optional CSV)')}
                  value={pitrArchiveIdsCsv}
                  onChange={(e) => setPitrArchiveIdsCsv(e.target.value)}
                />
                <TextField
                  label={gettext('PITR Stop GTID (optional)')}
                  value={pitrStopGtid}
                  onChange={(e) => setPitrStopGtid(e.target.value)}
                />
              </Grid>
            )}

            <Checkbox
              label={gettext('Acknowledge tablespace encryption keyring prerequisites if active')}
              checked={encryptionAcknowledged}
              onChange={(checked) => setEncryptionAcknowledged(Boolean(checked))}
            />

            <Stack direction="row" gap={1}>
              <Button intent="primary" disabled={busy} onClick={handleReviewPhase}>
                {gettext('Review Physical Operation')}
              </Button>
            </Stack>
          </Stack>
        </MariaDBSectionCard>

        <MariaDBReviewCard
          title={gettext('Physical Operation Review')}
          review={review}
          busy={busy}
          confirmLabel={gettext('Confirm & Start Physical Job')}
          onConfirm={handleStartPhase}
          onClear={() => setReview(null)}
        />

        <MariaDBSectionCard title={gettext('One-Use Production Cutover (Fence Old Primary & Promote Verified Recovery)')}>
          <Stack direction="column" gap={2}>
            <Grid columns={3} gap={2}>
              <TextField
                label={gettext('Verified Running Recovery Job ID')}
                value={cutoverRecoveryJobId}
                onChange={(e) => setCutoverRecoveryJobId(e.target.value)}
              />
              <TextField
                label={gettext('Target Confirmation (Recovery Datadir, Port, or Server UID)')}
                value={targetConfirmation}
                onChange={(e) => setTargetConfirmation(e.target.value)}
              />
              <Stack direction="column" gap={1}>
                <Checkbox
                  label={gettext('Fence old primary (read_only=ON)')}
                  checked={fenceOldPrimary}
                  onChange={(checked) => setFenceOldPrimary(Boolean(checked))}
                />
                <Checkbox
                  label={gettext('Update registered endpoint route')}
                  checked={updateTargetRegistration}
                  onChange={(checked) => setUpdateTargetRegistration(Boolean(checked))}
                />
                <Checkbox
                  label={gettext('Promote recovery instance writable')}
                  checked={promoteWritable}
                  onChange={(checked) => setPromoteWritable(Boolean(checked))}
                />
              </Stack>
            </Grid>
            <Stack direction="row" gap={1}>
              <Button
                intent="primary"
                disabled={busy || !cutoverRecoveryJobId.trim() || !targetConfirmation.trim()}
                onClick={handleReviewCutover}
              >
                {gettext('Review One-Use Cutover')}
              </Button>
            </Stack>
          </Stack>
        </MariaDBSectionCard>

        <MariaDBReviewCard
          title={gettext('One-Use Production Cutover Review')}
          review={cutoverReview}
          idKey="cutover_id"
          busy={busy}
          confirmLabel={gettext('Confirm & Execute Cutover')}
          onConfirm={handleStartCutover}
          onClear={() => setCutoverReview(null)}
        />

        <MariaDBJobsTable
          title={gettext('Physical Backup & Recovery Jobs')}
          jobs={jobs}
          kindKey="phase"
          busy={busy}
          selectedJob={selectedJob}
          onSelect={setSelectedJob}
          onRefreshJob={handleRefreshJob}
          onCancelJob={handleCancelJob}
          onReconcileJob={handleReconcileJob}
          extraActions={(job) =>
            job.recovery_running ? (
              <Button
                size="sm"
                intent="destructive"
                disabled={busy}
                onClick={() => handleStopRecovery(job.job_id)}
              >
                {gettext('Stop Recovery Daemon')}
              </Button>
            ) : null
          }
        />

        {cutovers.length > 0 && (
          <MariaDBJobsTable
            title={gettext('Production Cutover Receipts')}
            jobs={cutovers}
            idKey="cutover_id"
            busy={busy}
            selectedJob={selectedJob}
            onSelect={setSelectedJob}
            onRefreshJob={async (cid) => {
              const res = await callServer({
                action: 'mariadb_physical_cutover_status',
                request: {cutover_id: cid},
              });
              setSelectedJob(res);
            }}
            extraActions={(c) =>
              c.state === 'completed' ? (
                <Button
                  size="sm"
                  intent="destructive"
                  disabled={busy}
                  onClick={() => handleRollbackCutover(c.cutover_id)}
                >
                  {gettext('Rollback Cutover')}
                </Button>
              ) : null
            }
          />
        )}
      </Stack>
    </Box>
  );
}

MariaDBPhysicalWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
