/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import getApiInstance from 'sources/api_instance';
import {Box, Grid, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {DuckdbSectionCard, createDuckdbWorkspaceCaller} from './duckdbAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

const EDITOR_OP_CHOICES = [
  {value: 'editor_attachment_inventory', label: 'editor_attachment_inventory (Attached catalogs)'},
  {value: 'editor_extension_inventory', label: 'editor_extension_inventory (Extension capabilities)'},
  {value: 'editor_copy_inventory', label: 'editor_copy_inventory (Database copy catalogs)'},
  {value: 'editor_secret_inventory', label: 'editor_secret_inventory (Session secret identities)'},
  {value: 'editor_secret_receipts', label: 'editor_secret_receipts (Session secret receipts)'},
  {value: 'editor_receipt_list', label: 'editor_receipt_list (Archived operation receipts)'},
];

/**
 * DU-AUD-03 / DU-AUD-05 / DU-AUD-06 / DU-AUD-07 (SR-F-030587):
 * DuckDB Session & Global Runtime Settings, Rich COPY Planner, Foreign Attachment Discovery & Editor Tasks.
 */
export default function DuckdbRuntimeSettingsWorkspace({
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

  // 1. Runtime Settings (DU-AUD-03)
  const [settingsFilter, setSettingsFilter] = useState('');
  const [settingsInventory, setSettingsInventory] = useState(null);
  const [settingName, setSettingName] = useState('threads');
  const [settingScope, setSettingScope] = useState('SESSION');
  const [settingValue, setSettingValue] = useState('2');
  const [settingReview, setSettingReview] = useState(null);
  const [confirmSetting, setConfirmSetting] = useState(false);
  const [confirmDangerous, setConfirmDangerous] = useState(false);

  // 2. Rich COPY & Reader Planner (DU-AUD-05)
  const [copyDirection, setCopyDirection] = useState('to');
  const [copyFormat, setCopyFormat] = useState('JSON');
  const [copySchema, setCopySchema] = useState('main');
  const [copyTable, setCopyTable] = useState('events');
  const [copyResourceId, setCopyResourceId] = useState('table:main.events');
  const [copyPath, setCopyPath] = useState('/tmp/events.ndjson');
  const [copyPartitionCols, setCopyPartitionCols] = useState('');
  const [copyCompression, setCopyCompression] = useState('');
  const [copyPartitionedSource, setCopyPartitionedSource] = useState(false);
  const [copyPlanResult, setCopyPlanResult] = useState(null);

  // 3. Foreign Source Adapters & Discovery (DU-AUD-06 / DU-AUD-07)
  const [foreignAdapters, setForeignAdapters] = useState(null);

  // 4. Original-Session Editor Descriptor Task Runner
  const [editorOpId, setEditorOpId] = useState('editor_attachment_inventory');
  const [editorDraftJson, setEditorDraftJson] = useState('{}');
  const [editorResult, setEditorResult] = useState(null);

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

  const handleLoadSettings = async () => {
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const inv = await callDuckdb({
        action: 'duckdb_runtime_settings',
        sessionId: sid,
        request: {operation: 'inventory', filter: settingsFilter},
      });
      setSettingsInventory(inv);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewSetting = async (isReset = false) => {
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const rev = await callDuckdb({
        action: 'duckdb_runtime_settings',
        sessionId: sid,
        request: isReset
          ? {operation: 'review_reset', name: settingName, scope: settingScope}
          : {operation: 'review', name: settingName, scope: settingScope, value: settingValue},
      });
      setSettingReview(rev);
      setConfirmSetting(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplySetting = async () => {
    if (!settingReview?.review_id || !confirmSetting) return;
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const applied = await callDuckdb({
        action: 'duckdb_runtime_settings',
        sessionId: sid,
        request: {
          operation: 'apply',
          review_id: settingReview.review_id,
          review_digest: settingReview.review_digest,
          confirmed: true,
          security_sensitive_acknowledged: Boolean(confirmDangerous),
        },
      });
      setSettingReview(applied);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handlePlanCopy = async () => {
    setBusy(true);
    setError('');
    try {
      const partitionBy = copyPartitionCols
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const options = {
        ...(copyDirection === 'to' && partitionBy.length ? {partition_by: partitionBy} : {}),
        ...(copyCompression ? {compression: copyCompression} : {}),
      };
      const res = await callDuckdb({
        action: 'duckdb_copy_plan',
        request: {
          direction: copyDirection,
          format: copyFormat,
          path: copyPath,
          ...(copyDirection === 'reader_ctas'
            ? {target_schema: copySchema, target_table: copyTable}
            : {resource_id: copyResourceId || `table:${copySchema}.${copyTable}`}),
          ...(copyDirection !== 'to' && copyPartitionedSource ? {partitioned_source: true} : {}),
          ...(Object.keys(options).length ? {options} : {}),
        },
      });
      setCopyPlanResult(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleLoadForeignAdapters = async () => {
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const res = await callDuckdb({
        action: 'duckdb_attachments',
        sessionId: sid,
        request: {operation: 'inventory'},
      });
      setForeignAdapters(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRunEditorTask = async () => {
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const parsedDraft = JSON.parse(editorDraftJson || '{}');
      const res = await callDuckdb({
        action: 'duckdb_editor_operation',
        sessionId: sid,
        request: {operation_id: editorOpId, draft: parsedDraft},
      });
      setEditorResult(res);
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
            <strong>{gettext('DuckDB Runtime Settings, Rich COPY, Foreign Attachments & Session Tasks')}</strong>
            {activeSessionId && <Badge status="success" label={`Session ${activeSessionId.slice(0, 8)}`} />}
          </Stack>
          <FormReference reference="SR-F-030587" />
        </Stack>

        <Banner status="info">
          {gettext(
            'Inspects duckdb_settings() with SESSION/GLOBAL/RESET semantics and security guardrails, plans CSV/PARQUET/JSON and reader_ctas/reader_insert/Hive-partitioned COPY statements, probes foreign attachment adapters (sqlite, postgres, mysql, httpfs), and runs retained editor_* descriptor tasks.'
          )}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <DuckdbSectionCard
          title={gettext('1. Session & Global Runtime Settings (duckdb_settings)')}
          actions={
            <Button variant="secondary" disabled={busy} onClick={handleLoadSettings}>
              {gettext('Inspect Runtime Settings')}
            </Button>
          }
        >
          <Grid columns={4} gap="sm">
            <TextField
              label={gettext('Filter Settings')}
              value={settingsFilter}
              onChange={(e) => setSettingsFilter(textVal(e))}
            />
            <TextField
              label={gettext('Setting Name')}
              value={settingName}
              onChange={(e) => setSettingName(textVal(e))}
            />
            <Select
              label={gettext('Scope')}
              value={settingScope}
              options={[
                {value: 'SESSION', label: 'SESSION'},
                {value: 'GLOBAL', label: 'GLOBAL'},
              ]}
              onChange={setSettingScope}
            />
            <TextField
              label={gettext('Target Value')}
              value={settingValue}
              onChange={(e) => setSettingValue(textVal(e))}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button disabled={busy} onClick={() => handleReviewSetting(false)}>
              {gettext('Review SET')}
            </Button>
            <Button disabled={busy} onClick={() => handleReviewSetting(true)}>
              {gettext('Review RESET')}
            </Button>
            <Checkbox
              label={gettext('Confirm reviewed setting change')}
              checked={confirmSetting}
              onChange={setConfirmSetting}
            />
            <Checkbox
              label={gettext('Acknowledge security-sensitive setting')}
              checked={confirmDangerous}
              onChange={setConfirmDangerous}
            />
            <Button
              variant="primary"
              disabled={busy || !settingReview?.review_id || !confirmSetting}
              onClick={handleApplySetting}
            >
              {gettext('Apply Setting')}
            </Button>
          </Stack>
          {settingsInventory && (
            <div>
              <Badge status="info" label={`Settings observed: ${settingsInventory.settings?.length ?? 0}`} />
            </div>
          )}
          {settingReview && (
            <pre style={{margin: 0, maxHeight: 160, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {JSON.stringify(settingReview, null, 2)}
            </pre>
          )}
        </DuckdbSectionCard>

        <DuckdbSectionCard
          title={gettext('2. Rich Native COPY & Direct File Reader Planner (CSV / PARQUET / JSON)')}
          actions={
            <Button variant="primary" disabled={busy} onClick={handlePlanCopy}>
              {gettext('Plan Native COPY / Reader SQL')}
            </Button>
          }
        >
          <Grid columns={3} gap="sm">
            <Select
              label={gettext('Direction / Mode')}
              value={copyDirection}
              options={[
                {value: 'to', label: 'COPY ... TO (Export)'},
                {value: 'from', label: 'COPY ... FROM (Import)'},
                {value: 'reader_ctas', label: 'CREATE TABLE AS read_* (Direct Reader CTAS)'},
                {value: 'reader_insert', label: 'INSERT INTO ... SELECT * FROM read_*'},
              ]}
              onChange={setCopyDirection}
            />
            <Select
              label={gettext('Format')}
              value={copyFormat}
              options={[
                {value: 'CSV', label: 'CSV'},
                {value: 'PARQUET', label: 'PARQUET'},
                {value: 'JSON', label: 'JSON / NDJSON'},
              ]}
              onChange={setCopyFormat}
            />
            <TextField
              label={gettext('Absolute Contained File Path')}
              value={copyPath}
              onChange={(e) => setCopyPath(textVal(e))}
            />
            {copyDirection === 'reader_ctas' ? (
              <>
                <TextField
                  label={gettext('Target Schema Name')}
                  value={copySchema}
                  onChange={(e) => setCopySchema(textVal(e))}
                />
                <TextField
                  label={gettext('New Target Table Name')}
                  value={copyTable}
                  onChange={(e) => setCopyTable(textVal(e))}
                />
              </>
            ) : (
              <TextField
                label={gettext('Native Table Resource ID')}
                value={copyResourceId}
                onChange={(e) => setCopyResourceId(textVal(e))}
              />
            )}
            <TextField
              label={gettext('Hive Partition Columns (comma-separated, export)')}
              value={copyPartitionCols}
              onChange={(e) => setCopyPartitionCols(textVal(e))}
            />
            <TextField
              label={gettext('Compression (optional, e.g. GZIP / ZSTD / SNAPPY)')}
              value={copyCompression}
              onChange={(e) => setCopyCompression(textVal(e))}
            />
          </Grid>
          {copyDirection !== 'to' && (
            <Checkbox
              label={gettext('Partitioned source directory')}
              checked={copyPartitionedSource}
              onChange={setCopyPartitionedSource}
            />
          )}
          {(copyPlanResult?.source || copyPlanResult?.sql) && (
            <CodeEditor
              value={copyPlanResult.source || copyPlanResult.sql}
              language="sql"
              readOnly
              minHeight={90}
            />
          )}
        </DuckdbSectionCard>

        <DuckdbSectionCard
          title={gettext('3. Foreign Attachment Adapters & Retained Descriptor Task Runner')}
          actions={
            <Button variant="secondary" disabled={busy} onClick={handleLoadForeignAdapters}>
              {gettext('Probe Foreign Attachment Adapters')}
            </Button>
          }
        >
          {foreignAdapters && (
            <pre style={{margin: 0, maxHeight: 140, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {JSON.stringify(foreignAdapters, null, 2)}
            </pre>
          )}
          <Grid columns={2} gap="sm">
            <Select
              label={gettext('Descriptor Operation (duckdb_editor_operation)')}
              value={editorOpId}
              options={EDITOR_OP_CHOICES}
              onChange={setEditorOpId}
            />
            <TextField
              label={gettext('Operation Draft JSON')}
              value={editorDraftJson}
              onChange={(e) => setEditorDraftJson(textVal(e))}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy} onClick={handleRunEditorTask}>
              {gettext('Execute Original-Session Descriptor Task')}
            </Button>
          </Stack>
          {editorResult && (
            <pre style={{margin: 0, maxHeight: 160, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {JSON.stringify(editorResult, null, 2)}
            </pre>
          )}
        </DuckdbSectionCard>
      </Stack>
    </Box>
  );
}

DuckdbRuntimeSettingsWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  sessionId: PropTypes.string,
  api: PropTypes.object,
};
