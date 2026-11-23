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
import {Badge, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {
  DatabaseTargetPickerBar,
  extractApiError,
  ReceiptHistoryPanel,
  ReviewConfirmationCard,
  useFirebirdTargetScope,
} from './firebirdAdminHelpers';

export default function FirebirdLockPrintWorkspace({
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
  } = useFirebirdTargetScope(endpointUrl, databaseTargetId, true, customPost);

  const [descriptor, setDescriptor] = useState(null);
  const [mode, setMode] = useState('snapshot'); // 'snapshot' | 'interactive'
  const [owners, setOwners] = useState(true);
  const [locks, setLocks] = useState(true);
  const [requests, setRequests] = useState(false);
  const [history, setHistory] = useState(false);
  const [waitingOnly, setWaitingOnly] = useState(true);
  const [pendingOnly, setPendingOnly] = useState(false);
  const [consistentMutex, setConsistentMutex] = useState(true);
  const [series, setSeries] = useState('');
  const [interactiveSeconds, setInteractiveSeconds] = useState(3);
  const [interactiveInterval, setInteractiveInterval] = useState(1);
  const [interactiveCounters, setInteractiveCounters] = useState('aotw');
  const [timeoutSeconds, setTimeoutSeconds] = useState(15);
  const [includeRawLockKeys, setIncludeRawLockKeys] = useState(false);
  const [sensitiveConfirmed, setSensitiveConfirmed] = useState(false);
  const [confirmationName, setConfirmationName] = useState('');

  const [pendingReview, setPendingReview] = useState(null);
  const [executionResult, setExecutionResult] = useState(null);
  const [receipts, setReceipts] = useState([]);
  const [selectedReceipt, setSelectedReceipt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const callLockPrint = useCallback(
    (action, extra = {}) =>
      post({
        action: 'firebird_lock_print',
        request: {action, ...extra},
      }),
    [post]
  );

  const loadWorkspace = useCallback(async () => {
    if (!selectedTargetId) return;
    setBusy(true);
    setError('');
    try {
      const [desc, listResp] = await Promise.all([
        callLockPrint('describe'),
        callLockPrint('list').catch(() => ({items: []})),
      ]);
      setDescriptor(desc);
      setReceipts(Array.isArray(listResp?.items) ? listResp.items : []);
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  }, [callLockPrint, selectedTargetId]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  const buildDraftOptions = () => {
    const base = {
      timeout_seconds: Number(timeoutSeconds) || 15,
      include_raw_lock_keys: Boolean(includeRawLockKeys),
      sensitive_lock_data_confirmed: Boolean(sensitiveConfirmed),
      ...(confirmationName.trim() ? {confirmation: confirmationName.trim()} : {}),
    };
    if (mode === 'interactive') {
      return {
        ...base,
        interactive_seconds: Number(interactiveSeconds) || 3,
        interactive_interval: Number(interactiveInterval) || 1,
        interactive_counters: interactiveCounters || 'aotw',
      };
    }
    return {
      ...base,
      owners: Boolean(owners),
      locks: Boolean(locks),
      requests: Boolean(owners && requests),
      history: Boolean(history),
      waiting_only: Boolean(owners && waitingOnly),
      pending_only: Boolean((owners || locks) && pendingOnly),
      consistent_mutex: Boolean(consistentMutex),
      ...(locks && series !== '' ? {series: Number(series)} : {}),
    };
  };

  const handleReview = async () => {
    setBusy(true);
    setError('');
    try {
      const review = await callLockPrint('review', {options: buildDraftOptions()});
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
      const res = await callLockPrint('apply', confirmPayload);
      setPendingReview(null);
      setExecutionResult(res);
      await loadWorkspace();
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const inspectReceipt = async (reviewId) => {
    try {
      const rec = await callLockPrint('get', {review_id: reviewId});
      setSelectedReceipt(rec);
    } catch (err) {
      setError(extractApiError(err));
    }
  };

  const parsed = executionResult?.outcome?.parsed || null;
  const summary = executionResult?.durable_summary || null;

  return (
    <ScrollArea orientation="both" style={{height: '100%'}}>
      <Box sx={{p: 2}} data-cdeadmin-qa-key="firebird-lock-print-workspace">
        <Stack gap="comfortable">
          <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
            <Box>
              <Box component="h2" sx={{m: 0, fontSize: '1.1rem', fontWeight: 600}}>
                {gettext('Firebird Lock Table Diagnostics (fb_lock_print)')}
              </Box>
              <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
                {descriptor?.notes || gettext('Inspect database lock owners, wait chains, lock requests, and interactive lock-table throughput.')}
              </Box>
            </Box>
            <FormReference formKey="firebird-lock-print" />
          </Stack>

          {!databaseTargetId && (
            <DatabaseTargetPickerBar
              targets={targets}
              selectedTargetId={selectedTargetId}
              onSelectTarget={setSelectedTargetId}
              disabled={busy}
              onRefresh={reloadTargets}
            />
          )}

          {(error || targetsError) && (
            <ValidationMessage status="error">{error || targetsError}</ValidationMessage>
          )}

          <Panel variant="outlined" style={{padding: 12}}>
            <Stack gap="comfortable">
              <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                <Select
                  label={gettext('Capture mode')}
                  size="small"
                  options={[
                    {value: 'snapshot', label: gettext('Lock-table snapshot (owners / locks / requests)')},
                    {value: 'interactive', label: gettext('Interactive counter sampling (-i)')},
                  ]}
                  value={mode}
                  disabled={busy}
                  onChange={(val) => setMode(val)}
                />
                <NumberField
                  label={gettext('Process timeout (seconds, 1–60)')}
                  size="small"
                  value={timeoutSeconds}
                  disabled={busy}
                  onChange={(e) => setTimeoutSeconds(Number(e?.target !== undefined ? e.target.value : e) || 15)}
                />
              </Grid>

              {mode === 'snapshot' ? (
                <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                  <Checkbox label={gettext('Include lock owners (-o)')} checked={owners} disabled={busy} onChange={(v) => setOwners(Boolean(v))} />
                  <Checkbox label={gettext('Waiting owners only (-w)')} checked={waitingOnly} disabled={busy || !owners} onChange={(v) => setWaitingOnly(Boolean(v))} />
                  <Checkbox label={gettext('Include owner requests (-r)')} checked={requests} disabled={busy || !owners} onChange={(v) => setRequests(Boolean(v))} />
                  <Checkbox label={gettext('Include locks (-l)')} checked={locks} disabled={busy} onChange={(v) => setLocks(Boolean(v))} />
                  <Checkbox label={gettext('Pending locks/owners only')} checked={pendingOnly} disabled={busy || (!owners && !locks)} onChange={(v) => setPendingOnly(Boolean(v))} />
                  <Checkbox label={gettext('Consistent mutex read (-c)')} checked={consistentMutex} disabled={busy} onChange={(v) => setConsistentMutex(Boolean(v))} />
                  <Checkbox label={gettext('Include recent history (-h)')} checked={history} disabled={busy} onChange={(v) => setHistory(Boolean(v))} />
                  <TextField
                    label={gettext('Lock series filter (optional, 0–32767)')}
                    size="small"
                    value={series}
                    disabled={busy || !locks}
                    onChange={(e) => setSeries(e.target.value)}
                  />
                </Grid>
              ) : (
                <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                  <NumberField
                    label={gettext('Sample duration (seconds, 1–30)')}
                    size="small"
                    value={interactiveSeconds}
                    disabled={busy}
                    onChange={(e) => setInteractiveSeconds(Number(e?.target !== undefined ? e.target.value : e) || 3)}
                  />
                  <NumberField
                    label={gettext('Sample interval (seconds, 1–10)')}
                    size="small"
                    value={interactiveInterval}
                    disabled={busy}
                    onChange={(e) => setInteractiveInterval(Number(e?.target !== undefined ? e.target.value : e) || 1)}
                  />
                  <TextField
                    label={gettext('Counter letters (subset of aotw)')}
                    size="small"
                    value={interactiveCounters}
                    disabled={busy}
                    onChange={(e) => setInteractiveCounters(e.target.value)}
                  />
                </Grid>
              )}

              <Panel variant="outlined" style={{padding: 10}}>
                <Stack gap="tight">
                  <Checkbox
                    label={gettext('Include unredacted raw lock keys & AST pointers (one-shot volatile view only)')}
                    checked={includeRawLockKeys}
                    disabled={busy}
                    onChange={(v) => setIncludeRawLockKeys(Boolean(v))}
                  />
                  {includeRawLockKeys && (
                    <Grid columns="repeat(auto-fit, minmax(240px, 1fr))">
                      <Checkbox
                        label={gettext('I confirm exposure of sensitive lock-key bytes')}
                        checked={sensitiveConfirmed}
                        disabled={busy}
                        onChange={(v) => setSensitiveConfirmed(Boolean(v))}
                      />
                      <TextField
                        label={gettext('Type exact database filename to confirm')}
                        size="small"
                        value={confirmationName}
                        disabled={busy}
                        onChange={(e) => setConfirmationName(e.target.value)}
                      />
                    </Grid>
                  )}
                </Stack>
              </Panel>

              <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
                <Button
                  intent="primary"
                  disabled={busy || !selectedTargetId}
                  loading={busy}
                  onClick={handleReview}
                >
                  {gettext('Review fb_lock_print Command')}
                </Button>
              </Stack>
            </Stack>
          </Panel>

          {pendingReview && (
            <ReviewConfirmationCard
              review={pendingReview}
              title={gettext('Reviewed fb_lock_print Execution')}
              previewLabel={gettext('Resolved CLI arguments')}
              previewText={(pendingReview.payload?.cli_arguments || []).join(' ')}
              busy={busy}
              onApply={handleApply}
              onDiscard={() => setPendingReview(null)}
            />
          )}

          {summary && (
            <Panel variant="outlined" style={{padding: 12}} data-cdeadmin-qa-key="firebird-lock-print.result">
              <Stack gap="comfortable">
                <Stack direction="row" gap="standard" style={{alignItems: 'center', flexWrap: 'wrap'}}>
                  <strong>{gettext('Lock Table Observation')}:</strong>
                  <Badge label={summary.state || 'completed'} status="success" />
                  {summary.lock_table_state && <Badge label={summary.lock_table_state} status="info" />}
                  <span>{gettext('Owners')}: <strong>{summary.owners_observed}</strong></span>
                  <span>{gettext('Waiting')}: <strong>{summary.waiting_owners_observed}</strong></span>
                  <span>{gettext('Locks')}: <strong>{summary.locks_observed}</strong></span>
                </Stack>
                {parsed?.header && (
                  <CodeEditor
                    label={gettext('Parsed lock-table header & owners')}
                    readonly
                    language="json"
                    value={JSON.stringify(
                      {
                        header: parsed.header,
                        owners: parsed.owners,
                        locks: parsed.locks,
                        interactive_samples: parsed.interactive_samples,
                      },
                      null,
                      2
                    )}
                  />
                )}
                {executionResult?.outcome?.stdout && (
                  <CodeEditor
                    label={gettext('fb_lock_print output')}
                    readonly
                    language="text"
                    value={executionResult.outcome.stdout}
                  />
                )}
              </Stack>
            </Panel>
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

FirebirdLockPrintWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  customPost: PropTypes.func,
};
