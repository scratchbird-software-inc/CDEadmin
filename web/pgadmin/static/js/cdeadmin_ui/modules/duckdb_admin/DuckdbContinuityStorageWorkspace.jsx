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
import {TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import {DuckdbSectionCard, createDuckdbWorkspaceCaller} from './duckdbAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

/**
 * DU-AUD-20 & DU-AUD-21 (SR-F-030591):
 * DuckDB Physical Continuity (.duckdb + .wal Snapshots, WAL Crash Drill, Restore, Cutover)
 * & Storage Lifecycle (Binary MainHeader/DatabaseHeader Inspection, Reopen Probe, Storage Migration).
 */
export default function DuckdbContinuityStorageWorkspace({
  endpointUrl,
  databaseTargetId = '',
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callDuckdb = useMemo(
    () => createDuckdbWorkspaceCaller(api, endpointUrl, databaseTargetId),
    [api, endpointUrl, databaseTargetId]
  );

  // Physical continuity (DU-AUD-20)
  const [continuityState, setContinuityState] = useState(null);
  const [snapshotPath, setSnapshotPath] = useState('snapshots/quiesced_backup.duckdb');
  const [forceCheckpoint, setForceCheckpoint] = useState(true);
  const [snapshotReceipt, setSnapshotReceipt] = useState(null);
  const [walDrillReceipt, setWalDrillReceipt] = useState(null);
  const [restoreDestPath, setRestoreDestPath] = useState('restores/recovered_copy.duckdb');
  const [cutoverBackupPath, setCutoverBackupPath] = useState('snapshots/pre_cutover_rollback.duckdb');
  const [cutoverReview, setCutoverReview] = useState(null);
  const [confirmCutover, setConfirmCutover] = useState(false);

  // Storage lifecycle (DU-AUD-21)
  const [storageHeader, setStorageHeader] = useState(null);
  const [reopenProbe, setReopenProbe] = useState(null);
  const [targetStorageVersion, setTargetStorageVersion] = useState('v1.5.2');
  const [migratedDestPath, setMigratedDestPath] = useState('migrations/migrated_v1_5_2.duckdb');
  const [migrationReview, setMigrationReview] = useState(null);
  const [confirmMigration, setConfirmMigration] = useState(false);
  const [migrationOutcome, setMigrationOutcome] = useState(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const inspectBoth = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [cont, stor] = await Promise.all([
        callDuckdb({action: 'duckdb_ops_continuity_inspect'}),
        callDuckdb({action: 'duckdb_ops_storage_inspect'}),
      ]);
      setContinuityState(cont);
      setStorageHeader(stor);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [callDuckdb]);

  useEffect(() => {
    inspectBoth();
  }, [inspectBoth]);

  const handleCreateSnapshot = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_continuity_snapshot',
        request: {
          snapshot_path: snapshotPath,
          force_checkpoint: Boolean(forceCheckpoint),
        },
      });
      setSnapshotReceipt(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRunWalDrill = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_continuity_wal_drill',
        request: {},
      });
      setWalDrillReceipt(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRestoreNew = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_continuity_restore_new',
        request: {
          snapshot_path: snapshotPath,
          destination_path: restoreDestPath,
        },
      });
      setSnapshotReceipt(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewCutover = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_continuity_cutover_review',
        request: {
          snapshot_path: snapshotPath,
          rollback_backup_path: cutoverBackupPath,
        },
      });
      setCutoverReview(res);
      setConfirmCutover(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyCutover = async () => {
    if (!cutoverReview?.review_id || !confirmCutover) return;
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_continuity_cutover_apply',
        request: {
          review_id: cutoverReview.review_id,
          review_digest: cutoverReview.review_digest,
          confirmed: true,
        },
      });
      setCutoverReview(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReopenProbe = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_storage_reopen_probe',
        request: {},
      });
      setReopenProbe(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewMigration = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_storage_migrate_review',
        request: {
          destination_path: migratedDestPath,
          target_storage_version: targetStorageVersion,
        },
      });
      setMigrationReview(res);
      setConfirmMigration(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyMigration = async () => {
    if (!migrationReview?.review_id || !confirmMigration) return;
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_storage_migrate_apply',
        request: {
          review_id: migrationReview.review_id,
          review_digest: migrationReview.review_digest,
          confirmed: true,
        },
      });
      setMigrationOutcome(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box style={{padding: 16}}>
      <Stack gap="md">
        <Stack direction="row" gap="sm" style={{justifyContent: 'space-between', alignItems: 'center'}}>
          <Stack direction="row" gap="sm" style={{alignItems: 'center'}}>
            <strong>{gettext('DuckDB Physical Continuity, WAL Recovery & Storage Lifecycle')}</strong>
            {storageHeader?.main_header && (
              <Badge
                status="info"
                label={`Storage v${storageHeader.main_header.version_number} (${storageHeader.storage_version_band || ''})`}
              />
            )}
          </Stack>
          <FormReference reference="SR-F-030591" />
        </Stack>

        <Banner status="info">
          {gettext(
            'Inspects .duckdb + .wal continuity state and binary MainHeader/DatabaseHeader blocks, creates quiesced CHECKPOINT snapshots, runs isolated WAL replay drills, executes inode-bound cutovers with rollback retention, and migrates storage versions via ATTACH (STORAGE_VERSION ...) + COPY FROM DATABASE.'
          )}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <DuckdbSectionCard
          title={gettext('1. Physical Continuity (.duckdb + .wal), Snapshots, WAL Drill & Cutover')}
          actions={
            <Stack direction="row" gap="sm">
              <Button variant="secondary" disabled={busy} onClick={inspectBoth}>
                {gettext('Refresh Inspection')}
              </Button>
              <Button variant="secondary" disabled={busy} onClick={handleRunWalDrill}>
                {gettext('Run Isolated WAL Recovery Drill')}
              </Button>
            </Stack>
          }
        >
          {continuityState && (
            <Stack direction="row" gap="sm">
              <Badge status="info" label={`DB bytes: ${continuityState.database_file?.size_bytes ?? 0}`} />
              <Badge
                status={continuityState.wal_file?.exists ? 'warning' : 'success'}
                label={
                  continuityState.wal_file?.exists
                    ? `WAL present (${continuityState.wal_file.size_bytes} B)`
                    : gettext('No pending .wal')
                }
              />
            </Stack>
          )}
          <Grid columns={3} gap="sm">
            <TextField
              label={gettext('Snapshot Path')}
              value={snapshotPath}
              onChange={(e) => setSnapshotPath(textVal(e))}
            />
            <TextField
              label={gettext('Restore-to-New Path')}
              value={restoreDestPath}
              onChange={(e) => setRestoreDestPath(textVal(e))}
            />
            <TextField
              label={gettext('Cutover Rollback Backup Path')}
              value={cutoverBackupPath}
              onChange={(e) => setCutoverBackupPath(textVal(e))}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Checkbox
              label={gettext('Quiesce with FORCE CHECKPOINT')}
              checked={forceCheckpoint}
              onChange={setForceCheckpoint}
            />
            <Button variant="primary" disabled={busy} onClick={handleCreateSnapshot}>
              {gettext('Create Quiesced Snapshot')}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={handleRestoreNew}>
              {gettext('Restore Snapshot to New File')}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={handleReviewCutover}>
              {gettext('Review Inode-Bound Cutover')}
            </Button>
          </Stack>
          {cutoverReview?.review_id && (
            <Stack direction="row" gap="sm" style={{alignItems: 'center'}}>
              <Checkbox
                label={gettext('Confirm replacing live file while retaining rollback backup')}
                checked={confirmCutover}
                onChange={setConfirmCutover}
              />
              <Button variant="primary" disabled={busy || !confirmCutover} onClick={handleApplyCutover}>
                {gettext('Apply Cutover')}
              </Button>
            </Stack>
          )}
          {(snapshotReceipt || walDrillReceipt) && (
            <pre style={{margin: 0, maxHeight: 140, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {JSON.stringify(walDrillReceipt || snapshotReceipt, null, 2)}
            </pre>
          )}
        </DuckdbSectionCard>

        <DuckdbSectionCard
          title={gettext('2. Storage Header Inspection, Reopen Compatibility Probe & Storage Migration')}
          actions={
            <Button variant="secondary" disabled={busy} onClick={handleReopenProbe}>
              {gettext('Run Non-Rewriting Reopen Probe')}
            </Button>
          }
        >
          {storageHeader && (
            <Stack direction="row" gap="sm">
              <Badge status="info" label={`Magic: ${storageHeader.main_header?.magic || 'DUCK'}`} />
              <Badge status="info" label={`Library: ${storageHeader.main_header?.library_git_desc || ''}`} />
              <Badge
                status={storageHeader.main_header?.encrypted ? 'warning' : 'success'}
                label={
                  storageHeader.main_header?.encrypted
                    ? `Encrypted (${storageHeader.main_header.encryption_cipher})`
                    : gettext('Unencrypted')
                }
              />
            </Stack>
          )}
          {reopenProbe && (
            <Badge
              status={reopenProbe.header_unchanged_after_open ? 'success' : 'warning'}
              label={`Header unchanged on open: ${String(reopenProbe.header_unchanged_after_open)}`}
            />
          )}
          <Grid columns={2} gap="sm">
            <Select
              label={gettext('Target Storage Compatibility Version')}
              value={targetStorageVersion}
              options={[
                {value: 'v1.0.0', label: 'v1.0.0 (version_number 64)'},
                {value: 'v1.2.0', label: 'v1.2.0 (version_number 65)'},
                {value: 'v1.3.0', label: 'v1.3.0 (version_number 66)'},
                {value: 'v1.4.0', label: 'v1.4.0 (version_number 67)'},
                {value: 'v1.5.0', label: 'v1.5.0 (version_number 68)'},
                {value: 'v1.5.2', label: 'v1.5.2 (version_number 68)'},
                {value: 'latest', label: 'latest'},
              ]}
              onChange={setTargetStorageVersion}
            />
            <TextField
              label={gettext('Migrated Destination File Path')}
              value={migratedDestPath}
              onChange={(e) => setMigratedDestPath(textVal(e))}
            />
          </Grid>
          <Stack direction="row" gap="sm" style={{alignItems: 'center'}}>
            <Button variant="secondary" disabled={busy} onClick={handleReviewMigration}>
              {gettext('Review Storage Migration')}
            </Button>
            {migrationReview?.review_id && (
              <>
                <Checkbox
                  label={gettext('Confirm writing migrated DuckDB file')}
                  checked={confirmMigration}
                  onChange={setConfirmMigration}
                />
                <Button
                  variant="primary"
                  disabled={busy || !confirmMigration}
                  onClick={handleApplyMigration}
                >
                  {gettext('Apply Storage Migration')}
                </Button>
              </>
            )}
          </Stack>
          {(migrationOutcome || migrationReview) && (
            <pre style={{margin: 0, maxHeight: 140, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {JSON.stringify(migrationOutcome || migrationReview, null, 2)}
            </pre>
          )}
        </DuckdbSectionCard>
      </Stack>
    </Box>
  );
}

DuckdbContinuityStorageWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  api: PropTypes.object,
};
