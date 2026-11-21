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
import {TextField} from '../../primitives/Field';
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

export default function FirebirdRuntimeLifecycleWorkspace({
  endpointUrl,
  databaseTargetId = null,
  defaultOperation = 'migrate_database',
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
  const [runtimeInv, setRuntimeInv] = useState(null);
  const [operation, setOperation] = useState(defaultOperation || 'migrate_database');

  // ODS inspection state
  const [odsInspectPath, setOdsInspectPath] = useState('');
  const [odsObservation, setOdsObservation] = useState(null);

  // Operation draft state
  const [disruptionConfirmed, setDisruptionConfirmed] = useState(false);
  const [targetBundleDirName, setTargetBundleDirName] = useState('firebird-5.0.4-staged');
  const [migrationRoute, setMigrationRoute] = useState('gbak_backup_restore');
  const [sourcePath, setSourcePath] = useState('');
  const [targetDbPath, setTargetDbPath] = useState('');
  const [pageSize, setPageSize] = useState('8192');
  const [confirmationName, setConfirmationName] = useState('');

  const [pendingReview, setPendingReview] = useState(null);
  const [lastOutcome, setLastOutcome] = useState(null);
  const [receipts, setReceipts] = useState([]);
  const [selectedReceipt, setSelectedReceipt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const callRuntime = useCallback(
    (action, extra = {}) =>
      post({
        action: 'firebird_runtime_lifecycle',
        request: {action, ...extra},
      }),
    [post]
  );

  const loadWorkspace = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [desc, listResp, invResp] = await Promise.all([
        callRuntime('describe'),
        callRuntime('list').catch(() => ({items: []})),
        callRuntime('inspect').catch((err) => ({_inspectError: extractApiError(err)})),
      ]);
      setDescriptor(desc);
      setReceipts(Array.isArray(listResp?.items) ? listResp.items : []);
      if (invResp?._inspectError) {
        setRuntimeInv(null);
        setError(invResp._inspectError);
      } else {
        setRuntimeInv(invResp);
      }
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  }, [callRuntime]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  const handleInspectOds = async () => {
    if (!odsInspectPath.trim()) return;
    setBusy(true);
    setError('');
    try {
      const obs = await callRuntime('inspect_ods', {database_path: odsInspectPath.trim()});
      setOdsObservation(obs);
      if (obs?.recommended_migration_route) {
        setMigrationRoute(obs.recommended_migration_route);
      }
      if (!sourcePath.trim()) {
        setSourcePath(odsInspectPath.trim());
      }
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReview = async () => {
    setBusy(true);
    setError('');
    setLastOutcome(null);
    try {
      let payload = {operation};
      if (operation === 'daemon_stop' || operation === 'daemon_restart') {
        payload = {operation, disruption_confirmed: Boolean(disruptionConfirmed)};
      } else if (operation === 'stage_runtime_bundle') {
        payload = {operation, target_directory_name: targetBundleDirName.trim()};
      } else if (operation === 'migrate_database') {
        payload = {
          operation,
          migration_route: migrationRoute,
          source_path: sourcePath.trim(),
          target_database_path: targetDbPath.trim(),
          page_size: Number(pageSize) || 8192,
          confirmation: confirmationName.trim(),
        };
      }
      const review = await callRuntime('review', payload);
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
      const applied = await callRuntime('apply', confirmPayload);
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
      setSelectedReceipt(await callRuntime('get', {review_id: reviewId}));
    } catch (err) {
      setError(extractApiError(err));
    }
  };

  return (
    <ScrollArea orientation="both" style={{height: '100%'}}>
      <Box sx={{p: 2}} data-cdeadmin-qa-key="firebird-runtime-lifecycle-workspace">
        <Stack gap="comfortable">
          <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
            <Box>
              <Box component="h2" sx={{m: 0, fontSize: '1.1rem', fontWeight: 600}}>
                {gettext('Firebird Runtime Lifecycle & Cross-ODS Migration')}
              </Box>
              <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
                {gettext('Inspect Firebird 5.0.4 (ODS %s) runtime binaries, probe physical database ODS headers, manage owned daemons, and run non-destructive cross-ODS migrations.', descriptor?.native_ods_version || '13.1')}
              </Box>
            </Box>
            <FormReference formKey="firebird-runtime-lifecycle" />
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

          {runtimeInv && (
            <Panel variant="outlined" style={{padding: 12}}>
              <Stack gap="standard">
                <Stack direction="row" gap="standard" style={{alignItems: 'center', flexWrap: 'wrap'}}>
                  <strong>{gettext('Runtime')}:</strong> <code>{runtimeInv.runtime_root}</code>
                  <Badge label={`Firebird ${runtimeInv.engine_version}`} status="info" />
                  <Badge label={`Native ODS ${runtimeInv.native_ods_version}`} status="success" />
                  {runtimeInv.daemon_status?.state && (
                    <Badge label={`Daemon: ${runtimeInv.daemon_status.state}`} status="neutral" />
                  )}
                </Stack>
                <CodeEditor
                  label={gettext('Runtime binary & library SHA-256 inventory')}
                  readonly
                  language="json"
                  value={JSON.stringify(runtimeInv, null, 2)}
                />
              </Stack>
            </Panel>
          )}

          <Panel variant="outlined" style={{padding: 12}}>
            <Stack gap="standard">
              <Box component="h4" sx={{m: 0, fontSize: '0.875rem', fontWeight: 600}}>
                {gettext('Physical Database Header ODS Probe (gstat -h)')}
              </Box>
              <Grid columns="1fr auto">
                <TextField
                  label={gettext('Canonical database file path on host')}
                  size="small"
                  value={odsInspectPath}
                  disabled={busy}
                  onChange={(e) => setOdsInspectPath(e.target.value)}
                />
                <Button
                  intent="neutral"
                  size="small"
                  disabled={busy || !odsInspectPath.trim()}
                  onClick={handleInspectOds}
                >
                  {gettext('Inspect ODS')}
                </Button>
              </Grid>
              {odsObservation && (
                <Banner status="info">
                  {gettext(
                    'Observed ODS %s (%s). Recommended migration route: %s',
                    odsObservation.ods_text,
                    odsObservation.compatibility,
                    odsObservation.recommended_migration_route || gettext('None required (native 13.1)')
                  )}
                </Banner>
              )}
            </Stack>
          </Panel>

          <Panel variant="outlined" style={{padding: 12}}>
            <Stack gap="comfortable">
              <Box component="h4" sx={{m: 0, fontSize: '0.875rem', fontWeight: 600}}>
                {gettext('Stage & Review Runtime or ODS Migration Operation')}
              </Box>
              <Select
                label={gettext('Lifecycle operation')}
                size="small"
                options={[
                  {value: 'migrate_database', label: gettext('Migrate database to new file (never overwrites source)')},
                  {value: 'stage_runtime_bundle', label: gettext('Stage isolated runtime bundle directory')},
                  {value: 'daemon_start', label: gettext('Start managed Firebird daemon')},
                  {value: 'daemon_restart', label: gettext('Restart managed Firebird daemon')},
                  {value: 'daemon_stop', label: gettext('Stop managed Firebird daemon')},
                ]}
                value={operation}
                disabled={busy}
                onChange={(val) => setOperation(val)}
              />

              {(operation === 'daemon_stop' || operation === 'daemon_restart') && (
                <Checkbox
                  label={gettext('I confirm active attachments will be disrupted when stopping or restarting the Firebird daemon')}
                  checked={disruptionConfirmed}
                  disabled={busy}
                  onChange={(v) => setDisruptionConfirmed(Boolean(v))}
                />
              )}

              {operation === 'stage_runtime_bundle' && (
                <TextField
                  label={gettext('Target runtime directory basename inside staging root')}
                  size="small"
                  value={targetBundleDirName}
                  disabled={busy}
                  onChange={(e) => setTargetBundleDirName(e.target.value)}
                />
              )}

              {operation === 'migrate_database' && (
                <Grid columns="repeat(auto-fit, minmax(240px, 1fr))">
                  <Select
                    label={gettext('Migration route')}
                    size="small"
                    options={[
                      {value: 'gbak_backup_restore', label: gettext('Cross-version gbak backup & restore -> ODS 13.1')},
                      {value: 'ods13_minor_upgrade', label: gettext('ODS 13.0 -> 13.1 minor upgrade copy')},
                    ]}
                    value={migrationRoute}
                    disabled={busy}
                    onChange={(val) => setMigrationRoute(val)}
                  />
                  <Select
                    label={gettext('Target page size')}
                    size="small"
                    options={[
                      {value: '4096', label: '4096'},
                      {value: '8192', label: '8192'},
                      {value: '16384', label: '16384'},
                      {value: '32768', label: '32768'},
                    ]}
                    value={pageSize}
                    disabled={busy}
                    onChange={(val) => setPageSize(val)}
                  />
                  <TextField
                    label={gettext('Source database / backup file path (inside staging root)')}
                    size="small"
                    value={sourcePath}
                    disabled={busy}
                    onChange={(e) => setSourcePath(e.target.value)}
                  />
                  <TextField
                    label={gettext('New target database file path (must not exist)')}
                    size="small"
                    value={targetDbPath}
                    disabled={busy}
                    onChange={(e) => setTargetDbPath(e.target.value)}
                  />
                  <TextField
                    label={gettext('Type exact target database filename to confirm cutover')}
                    size="small"
                    value={confirmationName}
                    disabled={busy}
                    onChange={(e) => setConfirmationName(e.target.value)}
                  />
                </Grid>
              )}

              <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
                <Button
                  intent={operation === 'daemon_stop' ? 'destructive' : 'primary'}
                  disabled={busy}
                  loading={busy}
                  onClick={handleReview}
                >
                  {gettext('Review Lifecycle Operation')}
                </Button>
              </Stack>
            </Stack>
          </Panel>

          {pendingReview && (
            <ReviewConfirmationCard
              review={pendingReview}
              title={gettext('Reviewed Runtime / Migration Operation: %s', pendingReview.operation)}
              previewLabel={gettext('Reviewed migration / daemon execution plan')}
              previewText={JSON.stringify(pendingReview.payload, null, 2)}
              previewLanguage="json"
              busy={busy}
              onApply={handleApply}
              onDiscard={() => setPendingReview(null)}
            />
          )}

          {lastOutcome && (
            <CodeEditor
              label={gettext('Runtime lifecycle / migration receipt')}
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

FirebirdRuntimeLifecycleWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  defaultOperation: PropTypes.string,
  customPost: PropTypes.func,
};
