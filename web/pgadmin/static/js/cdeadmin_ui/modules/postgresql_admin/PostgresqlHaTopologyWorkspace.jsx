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
import UnifiedDataGrid from '../../data/UnifiedDataGrid';
import {PostgresqlSectionCard, createPostgresqlServerCaller} from './postgresqlAdminHelpers';

/**
 * PG-UI-03 (SR-F-030452): PostgreSQL High Availability, Standby Bootstrap,
 * Switchover, Production PITR Destination Restore, Cutover & Archive Retention Workspace.
 */
export default function PostgresqlHaTopologyWorkspace({
  endpointUrl,
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callServer = useMemo(
    () => createPostgresqlServerCaller(api, endpointUrl),
    [api, endpointUrl]
  );

  // HA Topology & Operations
  const [topology, setTopology] = useState(null);
  const [haJobs, setHaJobs] = useState([]);
  const [haOp, setHaOp] = useState('standby_bootstrap');
  const [datadir, setDatadir] = useState('');
  const [standbyDsn, setStandbyDsn] = useState('');
  const [slotName, setSlotName] = useState('sr_standby_slot');
  const [standbyPort, setStandbyPort] = useState(5433);
  const [ctlAction, setCtlAction] = useState('status');
  const [reviewedHa, setReviewedHa] = useState(null);
  const [haConfirmed, setHaConfirmed] = useState(false);

  // Production PITR Destination Restore & Coordinated Cutover
  const [baseJobId, setBaseJobId] = useState('');
  const [destDatadir, setDestDatadir] = useState('');
  const [listenPort, setListenPort] = useState(5434);
  const [verifyRw, setVerifyRw] = useState(true);
  const [reviewedRestore, setReviewedRestore] = useState(null);
  const [restoreConfirmed, setRestoreConfirmed] = useState(false);
  const [activeRestoreId, setActiveRestoreId] = useState('');
  const [terminateWriters, setTerminateWriters] = useState(false);
  const [reviewedCutover, setReviewedCutover] = useState(null);
  const [cutoverConfirmed, setCutoverConfirmed] = useState(false);
  const [lastCutoverId, setLastCutoverId] = useState('');

  // WAL Archives, Holds, Retention Prune & Stream Restart Review
  const [archives, setArchives] = useState([]);
  const [archiveName, setArchiveName] = useState('');
  const [holds, setHolds] = useState([]);
  const [holdId, setHoldId] = useState('');
  const [holdSegment, setHoldSegment] = useState('');
  const [holdReason, setHoldReason] = useState('');
  const [retentionEval, setRetentionEval] = useState(null);
  const [reviewedRetention, setReviewedRetention] = useState(null);
  const [retentionConfirmed, setRetentionConfirmed] = useState(false);
  const [priorStreamJobId, setPriorStreamJobId] = useState('');

  const [lastReceipt, setLastReceipt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refreshTopology = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [topo, jobsRes, archRes] = await Promise.all([
        callServer({action: 'postgresql_ha_topology', request: {}}),
        callServer({action: 'postgresql_ha_list', request: {}}).catch(() => ({jobs: []})),
        callServer({action: 'postgresql_continuity_archives', request: {}}).catch(() => ({archives: []})),
      ]);
      setTopology(topo);
      setHaJobs(jobsRes?.jobs || []);
      const archList = archRes?.archives || [];
      setArchives(archList);
      if (!archiveName && archList[0]?.archive) {
        setArchiveName(archList[0].archive);
      }
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [archiveName, callServer]);

  useEffect(() => {
    refreshTopology();
  }, [refreshTopology]);

  const handleReviewHa = async () => {
    setBusy(true);
    setError('');
    try {
      const options =
        haOp === 'standby_bootstrap'
          ? {
            standby_datadir: datadir.trim(),
            slot_name: slotName.trim(),
            create_slot: true,
            standby_port: Number(standbyPort) || 5433,
            start_standby: true,
          }
          : haOp === 'switchover'
            ? {standby_dsn: standbyDsn.trim(), wait_seconds: 30}
            : haOp === 'promote'
              ? {wait_seconds: 30, ...(standbyDsn.trim() ? {target_dsn: standbyDsn.trim()} : {})}
              : {datadir: datadir.trim(), ctl_action: ctlAction, stop_mode: 'fast'};
      const res = await callServer({
        action: 'postgresql_ha_review',
        request: {operation: haOp, options},
      });
      setReviewedHa(res);
      setHaConfirmed(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartHa = async () => {
    if (!reviewedHa || !haConfirmed) return;
    setBusy(true);
    setError('');
    try {
      const done = await callServer({
        action: 'postgresql_ha_start',
        request: {
          job_id: reviewedHa.job_id,
          review_digest: reviewedHa.review_digest,
          confirmed: true,
        },
      });
      setLastReceipt(done);
      setReviewedHa(null);
      await refreshTopology();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleInspectHaJob = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_ha_status',
        request: {job_id: jobId},
      });
      setLastReceipt(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  // Production PITR Destination Restore & Cutover handlers
  const handleReviewRestore = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_continuity_restore_review',
        request: {
          base_job_id: baseJobId.trim(),
          destination_mode: 'local',
          destination_datadir: destDatadir.trim(),
          start_service: true,
          listen_port: Number(listenPort) || 5434,
          verify_read_write: Boolean(verifyRw),
          database: 'postgres',
        },
      });
      setReviewedRestore(res);
      setRestoreConfirmed(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartRestore = async () => {
    if (!reviewedRestore || !restoreConfirmed) return;
    setBusy(true);
    setError('');
    try {
      const done = await callServer({
        action: 'postgresql_continuity_restore_start',
        request: {
          restore_id: reviewedRestore.restore_id,
          review_digest: reviewedRestore.review_digest,
          confirmed: true,
        },
      });
      setActiveRestoreId(done.restore_id || reviewedRestore.restore_id);
      setReviewedRestore(null);
      setLastReceipt(done);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewCutover = async () => {
    if (!activeRestoreId.trim()) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_continuity_cutover_review',
        request: {
          restore_id: activeRestoreId.trim(),
          terminate_source_writers: Boolean(terminateWriters),
        },
      });
      setReviewedCutover(res);
      setCutoverConfirmed(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartCutover = async () => {
    if (!reviewedCutover || !cutoverConfirmed) return;
    setBusy(true);
    setError('');
    try {
      const done = await callServer({
        action: 'postgresql_continuity_cutover_start',
        request: {
          cutover_id: reviewedCutover.cutover_id,
          review_digest: reviewedCutover.review_digest,
          confirmed: true,
        },
      });
      setLastCutoverId(done.cutover_id || reviewedCutover.cutover_id);
      setReviewedCutover(null);
      setLastReceipt(done);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRollbackCutover = async () => {
    if (!lastCutoverId.trim()) return;
    setBusy(true);
    setError('');
    try {
      const done = await callServer({
        action: 'postgresql_continuity_cutover_rollback',
        request: {
          cutover_id: lastCutoverId.trim(),
          confirmed: true,
        },
      });
      setLastReceipt(done);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleCheckOrchestrationStatus = async () => {
    const req = lastCutoverId.trim()
      ? {cutover_id: lastCutoverId.trim()}
      : activeRestoreId.trim()
        ? {restore_id: activeRestoreId.trim()}
        : null;
    if (!req) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_continuity_orchestration_status',
        request: req,
      });
      setLastReceipt(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  // Archive Hold, Retention Prune & Stream Restart handlers
  const handleEvaluateRetention = async () => {
    if (!archiveName.trim()) return;
    setBusy(true);
    setError('');
    try {
      const [evalRes, holdsRes] = await Promise.all([
        callServer({
          action: 'postgresql_continuity_archive_retention_evaluate',
          request: {archive: archiveName.trim()},
        }),
        callServer({
          action: 'postgresql_continuity_archive_holds',
          request: {archive: archiveName.trim()},
        }).catch(() => ({holds: []})),
      ]);
      setRetentionEval(evalRes);
      setHolds(holdsRes?.holds || []);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRegisterHold = async () => {
    if (!archiveName.trim() || !holdId.trim() || !holdSegment.trim()) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_continuity_archive_hold_register',
        request: {
          archive: archiveName.trim(),
          hold_id: holdId.trim(),
          min_retain_segment: holdSegment.trim(),
          reason: holdReason.trim() || 'Operator hold',
        },
      });
      setLastReceipt(res);
      await handleEvaluateRetention();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReleaseHold = async (targetHoldId) => {
    if (!archiveName.trim() || !targetHoldId) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_continuity_archive_hold_release',
        request: {
          archive: archiveName.trim(),
          hold_id: targetHoldId,
          confirmed: true,
        },
      });
      setLastReceipt(res);
      await handleEvaluateRetention();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewRetentionPrune = async () => {
    if (!archiveName.trim()) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_continuity_archive_retention_review',
        request: {archive: archiveName.trim()},
      });
      setReviewedRetention(res);
      setRetentionConfirmed(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartRetentionPrune = async () => {
    if (!reviewedRetention || !retentionConfirmed) return;
    setBusy(true);
    setError('');
    try {
      const done = await callServer({
        action: 'postgresql_continuity_archive_retention_start',
        request: {
          review_id: reviewedRetention.review_id,
          review_digest: reviewedRetention.review_digest,
          confirmed: true,
        },
      });
      setReviewedRetention(null);
      setLastReceipt(done);
      await handleEvaluateRetention();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewStreamRestart = async () => {
    if (!priorStreamJobId.trim()) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_continuity_stream_restart_review',
        request: {prior_job_id: priorStreamJobId.trim()},
      });
      setLastReceipt(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack gap="md">
      <PostgresqlSectionCard
        title={gettext('Streaming Replication Topology, Failover & Host Control')}
        actions={<FormReference reference="SR-F-030452" />}
      >
        <Stack gap="sm">
          <Banner status="info">
            {gettext(
              'Inspects live primary/standby role, WAL lag and replication slots, and orchestrates standby bootstrap, promotion, fenced switchover, production PITR destination restore/cutover, and WAL archive retention.'
            )}
          </Banner>
          {error && <ValidationMessage status="error">{error}</ValidationMessage>}
          {topology && (
            <Box>
              <Badge status={topology.in_recovery ? 'warning' : 'success'} label={topology.role?.toUpperCase()} />{' '}
              <span>
                {gettext('System ID:')} {topology.system_identifier} | {gettext('Timeline:')} {topology.timeline_id} | {gettext('LSN:')} {topology.wal_lsn} | {gettext('Standbys:')} {(topology.standbys || topology.replicas || []).length}
              </span>
            </Box>
          )}
          <Grid columns={2} gap="sm">
            <Select
              label={gettext('HA / Host Operation')}
              value={haOp}
              options={[
                {value: 'standby_bootstrap', label: 'Bootstrap streaming standby (pg_basebackup -R)'},
                {value: 'promote', label: 'Promote standby to primary (pg_promote)'},
                {value: 'switchover', label: 'Coordinated switchover (fence primary + catchup + promote)'},
                {value: 'host_pg_ctl', label: 'Authorized host pg_ctl lifecycle'},
              ]}
              onChange={setHaOp}
            />
            {(haOp === 'standby_bootstrap' || haOp === 'host_pg_ctl') && (
              <TextField
                label={gettext('Granted Cluster Data Directory')}
                value={datadir}
                onChange={(e) => setDatadir(e?.target ? e.target.value : e)}
              />
            )}
            {haOp === 'standby_bootstrap' && (
              <>
                <TextField
                  label={gettext('Physical Replication Slot')}
                  value={slotName}
                  onChange={(e) => setSlotName(e?.target ? e.target.value : e)}
                />
                <NumberField
                  label={gettext('Standby Port')}
                  value={standbyPort}
                  min={1024}
                  max={65535}
                  onChange={(v) => setStandbyPort(Number(v) || 5433)}
                />
              </>
            )}
            {(haOp === 'switchover' || haOp === 'promote') && (
              <TextField
                label={gettext('Target Standby Connection DSN')}
                value={standbyDsn}
                onChange={(e) => setStandbyDsn(e?.target ? e.target.value : e)}
              />
            )}
            {haOp === 'host_pg_ctl' && (
              <Select
                label={gettext('pg_ctl Action')}
                value={ctlAction}
                options={[
                  {value: 'status', label: 'status'},
                  {value: 'start', label: 'start'},
                  {value: 'stop', label: 'stop (fast)'},
                  {value: 'restart', label: 'restart'},
                  {value: 'reload', label: 'reload'},
                ]}
                onChange={setCtlAction}
              />
            )}
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy} onClick={handleReviewHa}>
              {gettext('Review HA Operation')}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={refreshTopology}>
              {gettext('Refresh Live Topology')}
            </Button>
          </Stack>
          {haJobs.length > 0 && (
            <UnifiedDataGrid
              caption={gettext('Retained HA Operation Jobs')}
              searchable
              exportable
              minHeight={140}
              maxHeight={260}
              rows={haJobs}
              rowKeyGetter={(j) => j.job_id}
              columns={[
                {name: 'job_id', label: gettext('Job ID'), width: 170, mono: true},
                {name: 'operation', label: gettext('Operation'), width: 180},
                {name: 'state', label: gettext('State'), width: 120},
                {
                  name: 'actions',
                  label: gettext('Inspect'),
                  width: 140,
                  render: (_val, j) => (
                    <Button variant="secondary" onClick={() => handleInspectHaJob(j.job_id)}>
                      {gettext('Inspect')}
                    </Button>
                  ),
                },
              ]}
            />
          )}
        </Stack>
      </PostgresqlSectionCard>

      {reviewedHa && (
        <PostgresqlSectionCard title={gettext('Reviewed HA Operation')}>
          <Stack gap="sm">
            <Checkbox
              label={gettext('Confirm HA operation execution (no automatic replay)')}
              checked={haConfirmed}
              onChange={setHaConfirmed}
            />
            <Button variant="primary" disabled={busy || !haConfirmed} onClick={handleStartHa}>
              {gettext('Execute Reviewed HA Operation')}
            </Button>
          </Stack>
        </PostgresqlSectionCard>
      )}

      <PostgresqlSectionCard title={gettext('Production PITR Destination Restore & Coordinated Cutover')}>
        <Stack gap="sm">
          <Grid columns={3} gap="sm">
            <TextField
              label={gettext('Verified Backup Job ID')}
              value={baseJobId}
              onChange={(e) => setBaseJobId(e?.target ? e.target.value : e)}
            />
            <TextField
              label={gettext('Granted Destination Data Directory')}
              value={destDatadir}
              onChange={(e) => setDestDatadir(e?.target ? e.target.value : e)}
            />
            <NumberField
              label={gettext('Restored Listen Port')}
              value={listenPort}
              min={1024}
              max={65535}
              onChange={(v) => setListenPort(Number(v) || 5434)}
            />
          </Grid>
          <Checkbox
            label={gettext('Verify independent read/write SQL acceptance on restored cluster')}
            checked={verifyRw}
            onChange={setVerifyRw}
          />
          <Stack direction="row" gap="sm">
            <Button
              variant="primary"
              disabled={busy || !baseJobId.trim() || !destDatadir.trim()}
              onClick={handleReviewRestore}
            >
              {gettext('Review Destination Restore')}
            </Button>
            {reviewedRestore && (
              <>
                <Checkbox
                  label={gettext('Confirm destination restore')}
                  checked={restoreConfirmed}
                  onChange={setRestoreConfirmed}
                />
                <Button variant="primary" disabled={busy || !restoreConfirmed} onClick={handleStartRestore}>
                  {gettext('Start Destination Restore')}
                </Button>
              </>
            )}
          </Stack>
          <Grid columns={3} gap="sm">
            <TextField
              label={gettext('Completed Restore ID for Cutover')}
              value={activeRestoreId}
              onChange={(e) => setActiveRestoreId(e?.target ? e.target.value : e)}
            />
            <TextField
              label={gettext('Active Cutover ID (Rollback / Status)')}
              value={lastCutoverId}
              onChange={(e) => setLastCutoverId(e?.target ? e.target.value : e)}
            />
            <Checkbox
              label={gettext('Terminate active source writers on fence')}
              checked={terminateWriters}
              onChange={setTerminateWriters}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy || !activeRestoreId.trim()} onClick={handleReviewCutover}>
              {gettext('Review Coordinated Cutover')}
            </Button>
            {reviewedCutover && (
              <>
                <Checkbox
                  label={gettext('Confirm read-only primary fence & cutover')}
                  checked={cutoverConfirmed}
                  onChange={setCutoverConfirmed}
                />
                <Button variant="primary" disabled={busy || !cutoverConfirmed} onClick={handleStartCutover}>
                  {gettext('Execute Coordinated Cutover')}
                </Button>
              </>
            )}
            {lastCutoverId.trim() && (
              <Button variant="secondary" disabled={busy} onClick={handleRollbackCutover}>
                {gettext('Rollback Cutover (Unfence Primary)')}
              </Button>
            )}
            {(activeRestoreId.trim() || lastCutoverId.trim()) && (
              <Button variant="secondary" disabled={busy} onClick={handleCheckOrchestrationStatus}>
                {gettext('Inspect Orchestration Receipt')}
              </Button>
            )}
          </Stack>
        </Stack>
      </PostgresqlSectionCard>

      <PostgresqlSectionCard title={gettext('WAL Archive Holds, Retention Pruning & Stream Restart')}>
        <Stack gap="sm">
          {archives.length > 0 && (
            <Box>
              <span>{gettext('Discovered WAL Archives:')} {archives.map((a) => a.archive || a).join(', ')}</span>
            </Box>
          )}
          <Grid columns={4} gap="sm">
            <TextField
              label={gettext('Owned WAL Archive Name')}
              value={archiveName}
              onChange={(e) => setArchiveName(e?.target ? e.target.value : e)}
            />
            <TextField
              label={gettext('Hold ID')}
              value={holdId}
              onChange={(e) => setHoldId(e?.target ? e.target.value : e)}
            />
            <TextField
              label={gettext('Min Retained WAL Segment')}
              value={holdSegment}
              onChange={(e) => setHoldSegment(e?.target ? e.target.value : e)}
            />
            <TextField
              label={gettext('Hold Reason')}
              value={holdReason}
              onChange={(e) => setHoldReason(e?.target ? e.target.value : e)}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="secondary" disabled={busy || !archiveName.trim()} onClick={handleEvaluateRetention}>
              {gettext('Evaluate Archive Retention Floor')}
            </Button>
            <Button
              variant="secondary"
              disabled={busy || !archiveName.trim() || !holdId.trim() || !holdSegment.trim()}
              onClick={handleRegisterHold}
            >
              {gettext('Register Archive Hold')}
            </Button>
            <Button variant="primary" disabled={busy || !archiveName.trim()} onClick={handleReviewRetentionPrune}>
              {gettext('Review Retention Prune')}
            </Button>
          </Stack>
          {holds.length > 0 && (
            <Stack direction="row" gap="sm">
              {holds.map((h) => (
                <Button key={h.hold_id} variant="secondary" onClick={() => handleReleaseHold(h.hold_id)}>
                  {`${gettext('Release Hold')} ${h.hold_id} (${h.min_retain_segment})`}
                </Button>
              ))}
            </Stack>
          )}
          {reviewedRetention && (
            <Stack direction="row" gap="sm">
              <Checkbox
                label={gettext('Confirm pruning WAL segments older than protected floor')}
                checked={retentionConfirmed}
                onChange={setRetentionConfirmed}
              />
              <Button variant="primary" disabled={busy || !retentionConfirmed} onClick={handleStartRetentionPrune}>
                {gettext('Execute WAL Retention Prune')}
              </Button>
            </Stack>
          )}
          <Grid columns={2} gap="sm">
            <TextField
              label={gettext('Interrupted WAL/Logical Stream Job ID')}
              value={priorStreamJobId}
              onChange={(e) => setPriorStreamJobId(e?.target ? e.target.value : e)}
            />
            <Box>
              <Button
                variant="secondary"
                disabled={busy || !priorStreamJobId.trim()}
                onClick={handleReviewStreamRestart}
              >
                {gettext('Review Safe Stream Restart')}
              </Button>
            </Box>
          </Grid>
          {(retentionEval || lastReceipt) && (
            <CodeEditor
              value={JSON.stringify(lastReceipt || retentionEval, null, 2)}
              language="json"
              readOnly
              height="200px"
            />
          )}
        </Stack>
      </PostgresqlSectionCard>
    </Stack>
  );
}

PostgresqlHaTopologyWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
