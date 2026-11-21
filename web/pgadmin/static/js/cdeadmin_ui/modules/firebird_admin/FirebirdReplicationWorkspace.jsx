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
import {Box, Grid, Panel, ScrollArea, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {NumberField, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {
  DatabaseTargetPickerBar,
  extractApiError,
  ReceiptHistoryPanel,
  ReviewConfirmationCard,
  useFirebirdTargetScope,
} from './firebirdAdminHelpers';

export default function FirebirdReplicationWorkspace({
  endpointUrl,
  databaseTargetId = null,
  customPost = null,
}) {
  const {
    targets,
    selectedTargetId,
    setSelectedTargetId,
    targetsError,
    reloadTargets,
    post,
  } = useFirebirdTargetScope(endpointUrl, databaseTargetId, false, customPost);

  const [descriptor, setDescriptor] = useState(null);
  const [stateObs, setStateObs] = useState(null);
  const [operation, setOperation] = useState('configure_primary');

  // configure_primary / seed_replica / distribute_segments / promote_replica fields
  const [primaryDbPath, setPrimaryDbPath] = useState('');
  const [replicaDbPath, setReplicaDbPath] = useState('');
  const [replicaRuntimeRoot, setReplicaRuntimeRoot] = useState('');
  const [journalDir, setJournalDir] = useState('');
  const [journalArchiveDir, setJournalArchiveDir] = useState('');
  const [journalSourceDir, setJournalSourceDir] = useState('');
  const [archiveTimeout, setArchiveTimeout] = useState(5);
  const [includeAllTables, setIncludeAllTables] = useState(true);
  const [enablePublication, setEnablePublication] = useState(true);
  const [replicaMode, setReplicaMode] = useState('READ_ONLY');
  const [promotionConfirmed, setPromotionConfirmed] = useState(false);
  const [discardUnappliedConfirmed, setDiscardUnappliedConfirmed] = useState(false);
  const [confirmationName, setConfirmationName] = useState('');

  const [pendingReview, setPendingReview] = useState(null);
  const [lastOutcome, setLastOutcome] = useState(null);
  const [receipts, setReceipts] = useState([]);
  const [selectedReceipt, setSelectedReceipt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const callReplication = useCallback(
    (action, extra = {}) =>
      post({
        action: 'firebird_replication',
        request: {action, ...extra},
      }),
    [post]
  );

  const loadWorkspace = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [desc, listResp, obsResp] = await Promise.all([
        callReplication('describe'),
        callReplication('list').catch(() => ({items: []})),
        callReplication('inspect').catch((err) => ({_inspectError: extractApiError(err)})),
      ]);
      setDescriptor(desc);
      setReceipts(Array.isArray(listResp?.items) ? listResp.items : []);
      if (obsResp?._inspectError) {
        setStateObs(null);
        setError(obsResp._inspectError);
      } else {
        setStateObs(obsResp);
      }
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  }, [callReplication]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  const handleReview = async () => {
    setBusy(true);
    setError('');
    setLastOutcome(null);
    try {
      let payload = {operation};
      if (operation === 'configure_primary') {
        payload = {
          operation,
          ...(primaryDbPath.trim() ? {primary_database_path: primaryDbPath.trim()} : {}),
          journal_directory: journalDir.trim(),
          journal_archive_directory: journalArchiveDir.trim(),
          journal_archive_timeout: Number(archiveTimeout) || 5,
          include_all_tables: Boolean(includeAllTables),
          enable_publication: Boolean(enablePublication),
        };
      } else if (operation === 'seed_replica') {
        payload = {
          operation,
          ...(primaryDbPath.trim() ? {primary_database_path: primaryDbPath.trim()} : {}),
          replica_database_path: replicaDbPath.trim(),
          ...(replicaRuntimeRoot.trim() ? {replica_runtime_root: replicaRuntimeRoot.trim()} : {}),
          journal_source_directory: journalSourceDir.trim(),
          replica_mode: replicaMode,
          confirmation: confirmationName.trim(),
        };
      } else if (operation === 'distribute_segments') {
        payload = {
          operation,
          source_archive_directory: journalArchiveDir.trim(),
          target_source_directory: journalSourceDir.trim(),
        };
      } else if (operation === 'promote_replica') {
        payload = {
          operation,
          ...(replicaDbPath.trim() ? {replica_database_path: replicaDbPath.trim()} : {}),
          ...(journalSourceDir.trim() ? {journal_source_directory: journalSourceDir.trim()} : {}),
          promotion_confirmed: Boolean(promotionConfirmed),
          discard_unapplied_segments_confirmed: Boolean(discardUnappliedConfirmed),
          confirmation: confirmationName.trim(),
        };
      }
      const review = await callReplication('review', payload);
      setPendingReview(review);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApply = async (confirmPayload) => {
    setBusy(true);
    setError('');
    try {
      const applied = await callReplication('apply', confirmPayload);
      setPendingReview(null);
      setLastOutcome(applied);
      await loadWorkspace();
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const inspectReceipt = async (reviewId) => {
    try {
      setSelectedReceipt(await callReplication('get', {review_id: reviewId}));
    } catch (err) {
      setError(extractApiError(err));
    }
  };

  return (
    <ScrollArea orientation="both" style={{height: '100%'}}>
      <Box sx={{p: 2}} data-cdeadmin-qa-key="firebird-replication-workspace">
        <Stack gap="comfortable">
          <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
            <Box>
              <Box component="h2" sx={{m: 0, fontSize: '1.1rem', fontWeight: 600}}>
                {gettext('Firebird Journal Replication Workflow')}
              </Box>
              <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
                {descriptor?.lag_authority || gettext('Inspect MON$REPLICA_MODE, publications, journal archive/source segments, and execute reviewed primary, replica-seed, segment-distribution, and promotion workflows.')}
              </Box>
            </Box>
            <FormReference formKey="firebird-replication" />
          </Stack>

          <DatabaseTargetPickerBar
            targets={targets}
            selectedTargetId={selectedTargetId}
            onSelectTarget={setSelectedTargetId}
            allowServerScope
            disabled={busy}
            onRefresh={() => {
              reloadTargets();
              loadWorkspace();
            }}
          />

          {(error || targetsError) && (
            <ValidationMessage status="error">{error || targetsError}</ValidationMessage>
          )}

          <Banner status="info">
            {gettext('Firebird 5.0.4 uses journal-segment replication without automatic consensus failover. Replica promotion is always an explicit operator-confirmed cutover.')}
          </Banner>

          {stateObs && (
            <Panel variant="outlined" style={{padding: 12}}>
              <Stack gap="standard">
                <Stack direction="row" gap="standard" style={{alignItems: 'center', flexWrap: 'wrap'}}>
                  <strong>{gettext('Observed Replication State')}:</strong>
                  {stateObs.database?.replica_mode && (
                    <Badge label={`Replica Mode: ${stateObs.database.replica_mode}`} status="info" />
                  )}
                  {stateObs.database?.database_guid && (
                    <span>GUID: <code>{stateObs.database.database_guid}</code></span>
                  )}
                </Stack>
                <CodeEditor
                  label={gettext('Live database publications, journal segment directories & replication.log tail')}
                  readonly
                  language="json"
                  value={JSON.stringify(stateObs, null, 2)}
                />
              </Stack>
            </Panel>
          )}

          <Panel variant="outlined" style={{padding: 12}}>
            <Stack gap="comfortable">
              <Box component="h4" sx={{m: 0, fontSize: '0.875rem', fontWeight: 600}}>
                {gettext('Stage & Review Journal Replication Operation')}
              </Box>
              <Select
                label={gettext('Replication operation')}
                size="small"
                options={[
                  {value: 'configure_primary', label: gettext('Configure primary journal & publication')},
                  {value: 'seed_replica', label: gettext('Seed physical replica (nbackup GUID-preserving)')},
                  {value: 'distribute_segments', label: gettext('Distribute contiguous archived journal segments')},
                  {value: 'promote_replica', label: gettext('Promote replica to standalone read/write')},
                ]}
                value={operation}
                disabled={busy}
                onChange={(val) => setOperation(val)}
              />

              {operation === 'configure_primary' && (
                <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                  <TextField label={gettext('Primary database path (optional if target selected)')} size="small" value={primaryDbPath} disabled={busy} onChange={(e) => setPrimaryDbPath(e.target.value)} />
                  <TextField label={gettext('Active journal directory')} size="small" value={journalDir} disabled={busy} onChange={(e) => setJournalDir(e.target.value)} />
                  <TextField label={gettext('Journal archive directory')} size="small" value={journalArchiveDir} disabled={busy} onChange={(e) => setJournalArchiveDir(e.target.value)} />
                  <NumberField
                    label={gettext('Archive timeout (seconds)')}
                    size="small"
                    value={archiveTimeout}
                    disabled={busy}
                    onChange={(e) => setArchiveTimeout(Number(e?.target !== undefined ? e.target.value : e) || 5)}
                  />
                  <Checkbox label={gettext('Include all tables in RDB$DEFAULT publication')} checked={includeAllTables} disabled={busy} onChange={(v) => setIncludeAllTables(Boolean(v))} />
                  <Checkbox label={gettext('Enable publication immediately')} checked={enablePublication} disabled={busy} onChange={(v) => setEnablePublication(Boolean(v))} />
                </Grid>
              )}

              {operation === 'seed_replica' && (
                <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                  <TextField label={gettext('Primary database path (optional if target selected)')} size="small" value={primaryDbPath} disabled={busy} onChange={(e) => setPrimaryDbPath(e.target.value)} />
                  <TextField label={gettext('New replica database path (must not exist)')} size="small" value={replicaDbPath} disabled={busy} onChange={(e) => setReplicaDbPath(e.target.value)} />
                  <TextField label={gettext('Replicajournal_source_directory')} size="small" value={journalSourceDir} disabled={busy} onChange={(e) => setJournalSourceDir(e.target.value)} />
                  <TextField label={gettext('Replica runtime root (optional)')} size="small" value={replicaRuntimeRoot} disabled={busy} onChange={(e) => setReplicaRuntimeRoot(e.target.value)} />
                  <Select
                    label={gettext('Replica mode')}
                    size="small"
                    options={[
                      {value: 'READ_ONLY', label: gettext('READ_ONLY replica')},
                      {value: 'READ_WRITE', label: gettext('READ_WRITE replica')},
                    ]}
                    value={replicaMode}
                    disabled={busy}
                    onChange={(val) => setReplicaMode(val)}
                  />
                  <TextField label={gettext('Type exact replica filename to confirm')} size="small" value={confirmationName} disabled={busy} onChange={(e) => setConfirmationName(e.target.value)} />
                </Grid>
              )}

              {operation === 'distribute_segments' && (
                <Grid columns="repeat(auto-fit, minmax(240px, 1fr))">
                  <TextField label={gettext('Source journal archive directory')} size="small" value={journalArchiveDir} disabled={busy} onChange={(e) => setJournalArchiveDir(e.target.value)} />
                  <TextField label={gettext('Target replica journal source directory')} size="small" value={journalSourceDir} disabled={busy} onChange={(e) => setJournalSourceDir(e.target.value)} />
                </Grid>
              )}

              {operation === 'promote_replica' && (
                <Grid columns="repeat(auto-fit, minmax(240px, 1fr))">
                  <TextField label={gettext('Replica database path (optional if target selected)')} size="small" value={replicaDbPath} disabled={busy} onChange={(e) => setReplicaDbPath(e.target.value)} />
                  <TextField label={gettext('Replica journal source directory (optional lag check)')} size="small" value={journalSourceDir} disabled={busy} onChange={(e) => setJournalSourceDir(e.target.value)} />
                  <TextField label={gettext('Type exact replica filename to confirm promotion')} size="small" value={confirmationName} disabled={busy} onChange={(e) => setConfirmationName(e.target.value)} />
                  <Checkbox label={gettext('Confirm manual replica promotion to standalone primary')} checked={promotionConfirmed} disabled={busy} onChange={(v) => setPromotionConfirmed(Boolean(v))} />
                  <Checkbox label={gettext('Discard remaining unapplied journal segments if present')} checked={discardUnappliedConfirmed} disabled={busy} onChange={(v) => setDiscardUnappliedConfirmed(Boolean(v))} />
                </Grid>
              )}

              <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
                <Button
                  intent={operation === 'promote_replica' ? 'destructive' : 'primary'}
                  disabled={busy}
                  loading={busy}
                  onClick={handleReview}
                >
                  {gettext('Review Replication Operation')}
                </Button>
              </Stack>
            </Stack>
          </Panel>

          {pendingReview && (
            <ReviewConfirmationCard
              review={pendingReview}
              title={gettext('Reviewed Replication Operation: %s', pendingReview.operation)}
              previewLabel={gettext('Generated replication configuration / segment plan')}
              previewText={
                pendingReview.payload?.replication_conf_text ||
                pendingReview.payload?.replica_replication_conf_text ||
                JSON.stringify(pendingReview.payload, null, 2)
              }
              busy={busy}
              onApply={handleApply}
              onDiscard={() => setPendingReview(null)}
            />
          )}

          {lastOutcome && (
            <CodeEditor
              label={gettext('Replication operation receipt')}
              readonly
              language="json"
              value={JSON.stringify(lastOutcome, null, 2)}
            />
          )}

          <ReceiptHistoryPanel
            items={receipts}
            onInspectReceipt={inspectReceipt}
            selectedReceipt={selectedReceipt}
          />
        </Stack>
      </Box>
    </ScrollArea>
  );
}

FirebirdReplicationWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  customPost: PropTypes.func,
};
