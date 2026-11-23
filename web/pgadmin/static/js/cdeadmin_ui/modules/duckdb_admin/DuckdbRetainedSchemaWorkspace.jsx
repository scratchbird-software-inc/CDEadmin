/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import getApiInstance from 'sources/api_instance';
import {Box, Grid, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Checkbox} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {DuckdbSectionCard, createDuckdbWorkspaceCaller} from './duckdbAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

/**
 * DU-AUD-17 (SR-F-030588): DuckDB Original-Session Retained DDN Schema Workflow & Receipts.
 */
export default function DuckdbRetainedSchemaWorkspace({
  endpointUrl,
  databaseTargetId = '',
  sessionId: externalSessionId = '',
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callDuckdb = useMemo(
    () => createDuckdbWorkspaceCaller(api, endpointUrl, databaseTargetId),
    [api, endpointUrl, databaseTargetId]
  );

  const [ownedSessionId, setOwnedSessionId] = useState('');
  const activeSessionId = externalSessionId || ownedSessionId;

  const [observed, setObserved] = useState(null);
  const [desiredSeed, setDesiredSeed] = useState('');
  const desiredJsonRef = useRef('');
  const [editorEpoch, setEditorEpoch] = useState(0);
  const [deletionsText, setDeletionsText] = useState('');
  const [alterationsJson, setAlterationsJson] = useState('');
  const [rebuildResourceId, setRebuildResourceId] = useState('');
  const [rebuildPreserveRows, setRebuildPreserveRows] = useState(true);
  const [rebuildCompleteDef, setRebuildCompleteDef] = useState(true);
  const [rebuildLossAck, setRebuildLossAck] = useState(false);
  const [rebuildDiscardCols, setRebuildDiscardCols] = useState(false);
  const [rebuildConversionsJson, setRebuildConversionsJson] = useState('');
  const [rebuildRenamesJson, setRebuildRenamesJson] = useState('');
  const [previewResult, setPreviewResult] = useState(null);
  const [reviewedPlan, setReviewedPlan] = useState(null);
  const [confirmApply, setConfirmApply] = useState(false);
  const [applyOutcome, setApplyOutcome] = useState(null);
  const [receipts, setReceipts] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const ensureSession = useCallback(async () => {
    if (activeSessionId) return activeSessionId;
    const res = await api.post(endpointUrl, {
      action: 'open_session',
      language_profile: 'duckdb-sql',
      ...(databaseTargetId ? {database_target_id: databaseTargetId} : {}),
    });
    const data = res?.data?.data ?? res?.data;
    const sid = data?.session_id || '';
    if (!sid) {
      throw new Error(gettext('Unable to open DuckDB query session handle.'));
    }
    setOwnedSessionId(sid);
    return sid;
  }, [activeSessionId, api, databaseTargetId, endpointUrl]);

  const observedModel = observed?.model || (observed?.rows ? observed : null);

  const buildRetainedModifiers = () => {
    const deletions = deletionsText.split(',').map((s) => s.trim()).filter(Boolean);
    const alterations = alterationsJson.trim() ? JSON.parse(alterationsJson) : [];
    const rebuilds = [];
    if (rebuildResourceId.trim()) {
      rebuilds.push({
        resource_id: rebuildResourceId.trim(),
        preserve_rows_confirmed: rebuildPreserveRows,
        complete_definition_confirmed: rebuildCompleteDef,
        ...(rebuildLossAck ? {loss_acknowledged: true} : {}),
        ...(rebuildDiscardCols ? {discard_columns_confirmed: true} : {}),
        ...(rebuildConversionsJson.trim() ? {column_conversions: JSON.parse(rebuildConversionsJson)} : {}),
        ...(rebuildRenamesJson.trim() ? {column_renames: JSON.parse(rebuildRenamesJson)} : {}),
      });
    }
    return {
      ...(deletions.length ? {deletions} : {}),
      ...(alterations.length ? {alterations} : {}),
      ...(rebuilds.length ? {rebuilds} : {}),
    };
  };

  const handleObserve = async () => {
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const res = await callDuckdb({
        action: 'duckdb_retained_schema',
        sessionId: sid,
        request: {operation: 'observe'},
      });
      setObserved(res);
      const doc = res?.model || (res?.rows ? res : null);
      if (doc) {
        const formatted = JSON.stringify(doc, null, 2);
        desiredJsonRef.current = formatted;
        setDesiredSeed(formatted);
        setEditorEpoch((n) => n + 1);
      }
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handlePreview = async () => {
    if (!observedModel) return;
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const desired = JSON.parse(desiredJsonRef.current || '{}');
      const modifiers = buildRetainedModifiers();
      const res = await callDuckdb({
        action: 'duckdb_retained_schema',
        sessionId: sid,
        request: {
          operation: 'preview',
          baseline: observedModel,
          desired,
          ...modifiers,
        },
      });
      setPreviewResult(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReview = async () => {
    if (!observedModel) return;
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const desired = JSON.parse(desiredJsonRef.current || '{}');
      const modifiers = buildRetainedModifiers();
      const res = await callDuckdb({
        action: 'duckdb_retained_schema',
        sessionId: sid,
        request: {
          operation: 'review',
          baseline: observedModel,
          desired,
          ...(previewResult?.execution_sha256 ? {execution_sha256: previewResult.execution_sha256} : {}),
          ...modifiers,
        },
      });
      setReviewedPlan(res);
      setConfirmApply(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const reviewedId = reviewedPlan?.review_id || reviewedPlan?.application_id || '';
  const reviewedDigest = reviewedPlan?.review_digest || reviewedPlan?.plan_digest || '';

  const handleApply = async () => {
    if (!reviewedId || !confirmApply) return;
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const res = await callDuckdb({
        action: 'duckdb_retained_schema',
        sessionId: sid,
        request: {
          operation: 'apply',
          review_id: reviewedId,
          review_digest: reviewedDigest,
          confirmed: true,
        },
      });
      setApplyOutcome(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleLoadReceipts = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_retained_schema_receipts',
        request: {operation: 'list'},
      });
      setReceipts(res?.items || res?.receipts || []);
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
            <strong>{gettext('DuckDB Original-Session Retained DDN Schema Workflow')}</strong>
            {activeSessionId && <Badge status="success" label={`Session ${activeSessionId.slice(0, 8)}`} />}
          </Stack>
          <FormReference reference="SR-F-030588" />
        </Stack>

        <Banner status="info">
          {gettext(
            'Observes TEMP, attached and uncommitted objects on the exact retained DuckDB connection, plans/reviews DDN schema diffs, and applies reviewed changes in-session without issuing COMMIT or ROLLBACK.'
          )}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <DuckdbSectionCard
          title={gettext('1. Observe, Edit & Preview Retained-Session DDN Model')}
          actions={
            <Stack direction="row" gap="sm">
              <Button variant="primary" disabled={busy} onClick={handleObserve}>
                {gettext('Observe Retained Session')}
              </Button>
              <Button variant="secondary" disabled={busy || !observed} onClick={handlePreview}>
                {gettext('Preview Diff')}
              </Button>
              <Button variant="secondary" disabled={busy || !observed} onClick={handleReview}>
                {gettext('Seal Review Plan')}
              </Button>
            </Stack>
          }
        >
          {observed && (
            <Badge
              status="info"
              label={`Model contract: ${observed.model?.contract || observed.provenance?.mapping || 'scratchrobin.duckdb.retained-session-ddn@1'}`}
            />
          )}
          <CodeEditor
            key={editorEpoch}
            value={desiredSeed}
            language="json"
            onChange={(val) => {
              desiredJsonRef.current = val;
            }}
            minHeight={180}
          />
          <Grid columns={3} gap="sm">
            <TextField
              label={gettext('Explicit Deletions (comma-separated resource IDs)')}
              value={deletionsText}
              onChange={(e) => setDeletionsText(textVal(e))}
            />
            <TextField
              label={gettext('Explicit Alterations JSON Array')}
              value={alterationsJson}
              onChange={(e) => setAlterationsJson(textVal(e))}
            />
            <TextField
              label={gettext('Retained Rebuild Table Resource ID')}
              value={rebuildResourceId}
              onChange={(e) => setRebuildResourceId(textVal(e))}
            />
            <TextField
              label={gettext('Rebuild Column Conversions JSON')}
              value={rebuildConversionsJson}
              onChange={(e) => setRebuildConversionsJson(textVal(e))}
            />
            <TextField
              label={gettext('Rebuild Column Renames JSON')}
              value={rebuildRenamesJson}
              onChange={(e) => setRebuildRenamesJson(textVal(e))}
            />
          </Grid>
          {rebuildResourceId.trim() && (
            <Stack direction="row" gap="sm" style={{flexWrap: 'wrap'}}>
              <Checkbox
                label={gettext('Confirm preserving retained table rows')}
                checked={rebuildPreserveRows}
                onChange={setRebuildPreserveRows}
              />
              <Checkbox
                label={gettext('Confirm complete retained table definition')}
                checked={rebuildCompleteDef}
                onChange={setRebuildCompleteDef}
              />
              <Checkbox
                label={gettext('Acknowledge retained conversion loss')}
                checked={rebuildLossAck}
                onChange={setRebuildLossAck}
              />
              <Checkbox
                label={gettext('Confirm retained column discard')}
                checked={rebuildDiscardCols}
                onChange={setRebuildDiscardCols}
              />
            </Stack>
          )}
          {previewResult && (
            <pre style={{margin: 0, maxHeight: 140, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {JSON.stringify(previewResult, null, 2)}
            </pre>
          )}
        </DuckdbSectionCard>

        <DuckdbSectionCard
          title={gettext('2. One-Shot Reviewed Apply & Read-Only Receipts')}
          actions={
            <Button variant="secondary" disabled={busy} onClick={handleLoadReceipts}>
              {gettext('Refresh Retained Schema Receipts')}
            </Button>
          }
        >
          {reviewedPlan && (
            <Stack gap="sm">
              <Badge status="info" label={`Application: ${reviewedId}`} />
              <Checkbox
                label={gettext('Confirm applying reviewed DDN changes on the retained session (caller retains COMMIT/ROLLBACK)')}
                checked={confirmApply}
                onChange={setConfirmApply}
              />
              <Button variant="primary" disabled={busy || !confirmApply} onClick={handleApply}>
                {gettext('Apply Reviewed Retained Schema Plan')}
              </Button>
            </Stack>
          )}
          {applyOutcome && (
            <pre style={{margin: 0, maxHeight: 140, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {JSON.stringify(applyOutcome, null, 2)}
            </pre>
          )}
          <div>
            <Badge status="info" label={`Archived retained receipts: ${receipts.length}`} />
          </div>
        </DuckdbSectionCard>
      </Stack>
    </Box>
  );
}

DuckdbRetainedSchemaWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  sessionId: PropTypes.string,
  api: PropTypes.object,
};
