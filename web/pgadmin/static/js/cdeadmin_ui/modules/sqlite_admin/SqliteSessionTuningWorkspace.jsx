/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
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
import {SqliteSectionCard, createSqliteWorkspaceCaller} from './sqliteAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

const LIMIT_OPTIONS = [
  {value: 'sql_length', label: 'SQLITE_LIMIT_SQL_LENGTH'},
  {value: 'length', label: 'SQLITE_LIMIT_LENGTH'},
  {value: 'column', label: 'SQLITE_LIMIT_COLUMN'},
  {value: 'expr_depth', label: 'SQLITE_LIMIT_EXPR_DEPTH'},
  {value: 'compound_select', label: 'SQLITE_LIMIT_COMPOUND_SELECT'},
  {value: 'vdbe_op', label: 'SQLITE_LIMIT_VDBE_OP'},
  {value: 'function_arg', label: 'SQLITE_LIMIT_FUNCTION_ARG'},
  {value: 'attached', label: 'SQLITE_LIMIT_ATTACHED'},
  {value: 'like_pattern_length', label: 'SQLITE_LIMIT_LIKE_PATTERN_LENGTH'},
  {value: 'variable_number', label: 'SQLITE_LIMIT_VARIABLE_NUMBER'},
  {value: 'trigger_depth', label: 'SQLITE_LIMIT_TRIGGER_DEPTH'},
  {value: 'worker_threads', label: 'SQLITE_LIMIT_WORKER_THREADS'},
];

const PRAGMA_OPTIONS = [
  {value: 'foreign_keys', label: 'foreign_keys (boolean)'},
  {value: 'busy_timeout', label: 'busy_timeout (ms)'},
  {value: 'wal_autocheckpoint', label: 'wal_autocheckpoint (pages)'},
  {value: 'analysis_limit', label: 'analysis_limit (rows)'},
  {value: 'recursive_triggers', label: 'recursive_triggers (boolean)'},
  {value: 'query_only', label: 'query_only (boolean)'},
  {value: 'read_uncommitted', label: 'read_uncommitted (boolean)'},
  {value: 'defer_foreign_keys', label: 'defer_foreign_keys (boolean)'},
  {value: 'ignore_check_constraints', label: 'ignore_check_constraints (boolean)'},
  {value: 'trusted_schema', label: 'trusted_schema (boolean)'},
  {value: 'legacy_alter_table', label: 'legacy_alter_table (boolean)'},
  {value: 'cell_size_check', label: 'cell_size_check (boolean)'},
  {value: 'automatic_index', label: 'automatic_index (boolean)'},
  {value: 'reverse_unordered_selects', label: 'reverse_unordered_selects (boolean)'},
  {value: 'case_sensitive_like', label: 'case_sensitive_like (boolean)'},
  {value: 'cache_size', label: 'cache_size (pages / KiB)'},
  {value: 'temp_store', label: 'temp_store (DEFAULT/FILE/MEMORY)'},
  {value: 'soft_heap_limit64', label: 'soft_heap_limit64 (bytes)'},
];

const NUMERIC_PRAGMAS = new Set(['busy_timeout', 'wal_autocheckpoint', 'analysis_limit', 'cache_size', 'soft_heap_limit64']);

const DBCONFIG_OPTIONS = [
  {value: 'defensive', label: 'SQLITE_DBCONFIG_DEFENSIVE'},
  {value: 'enable_fkey', label: 'SQLITE_DBCONFIG_ENABLE_FKEY'},
  {value: 'enable_trigger', label: 'SQLITE_DBCONFIG_ENABLE_TRIGGER'},
  {value: 'enable_view', label: 'SQLITE_DBCONFIG_ENABLE_VIEW'},
  {value: 'dqs_dml', label: 'SQLITE_DBCONFIG_DQS_DML'},
  {value: 'dqs_ddl', label: 'SQLITE_DBCONFIG_DQS_DDL'},
  {value: 'trusted_schema', label: 'SQLITE_DBCONFIG_TRUSTED_SCHEMA'},
  {value: 'legacy_alter_table', label: 'SQLITE_DBCONFIG_LEGACY_ALTER_TABLE'},
  {value: 'legacy_file_format', label: 'SQLITE_DBCONFIG_LEGACY_FILE_FORMAT'},
  {value: 'no_ckpt_on_close', label: 'SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE'},
  {value: 'enable_qpsg', label: 'SQLITE_DBCONFIG_ENABLE_QPSG'},
  {value: 'trigger_eqp', label: 'SQLITE_DBCONFIG_TRIGGER_EQP'},
  {value: 'enable_fts3_tokenizer', label: 'SQLITE_DBCONFIG_ENABLE_FTS3_TOKENIZER'},
  {value: 'enable_load_extension', label: 'SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION (dangerous)'},
  {value: 'writable_schema', label: 'SQLITE_DBCONFIG_WRITABLE_SCHEMA (dangerous)'},
  {value: 'reset_database', label: 'SQLITE_DBCONFIG_RESET_DATABASE (dangerous)'},
];

const DANGEROUS_DBCONFIGS = new Set(['reset_database', 'writable_schema', 'enable_load_extension']);

/**
 * SR-F-030566: SQLite Original-Session Connection Tuning, Limits, PRAGMAs,
 * `sqlite3_db_config`, Retained Maintenance & Descriptor Task Workspace.
 */
export default function SqliteSessionTuningWorkspace({
  endpointUrl,
  databaseTargetId = '',
  sessionId: externalSessionId = '',
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callSqlite = useMemo(
    () => createSqliteWorkspaceCaller(api, endpointUrl, databaseTargetId),
    [api, endpointUrl, databaseTargetId]
  );

  const [ownedSessionId, setOwnedSessionId] = useState('');
  const activeSessionId = externalSessionId || ownedSessionId;

  // 1. PRAGMA synchronous (sqlite_connection_settings)
  const [syncState, setSyncState] = useState(null);
  const [syncTarget, setSyncTarget] = useState('FULL');
  const [confirmSync, setConfirmSync] = useState(false);

  // 2. sqlite3_limit (sqlite_connection_limits)
  const [limitName, setLimitName] = useState('sql_length');
  const [limitValue, setLimitValue] = useState('1000000');
  const [limitState, setLimitState] = useState(null);
  const [confirmLimit, setConfirmLimit] = useState(false);

  // 3. Session PRAGMAs (sqlite_connection_pragmas)
  const [pragmaName, setPragmaName] = useState('foreign_keys');
  const [pragmaBoolVal, setPragmaBoolVal] = useState(true);
  const [pragmaNumVal, setPragmaNumVal] = useState('5000');
  const [pragmaState, setPragmaState] = useState(null);
  const [confirmPragma, setConfirmPragma] = useState(false);

  // 4. sqlite3_db_config (sqlite_connection_config)
  const [configName, setConfigName] = useState('defensive');
  const [configBoolVal, setConfigBoolVal] = useState(true);
  const [configState, setConfigState] = useState(null);
  const [confirmConfig, setConfirmConfig] = useState(false);
  const [confirmDangerousConfig, setConfirmDangerousConfig] = useState(false);

  // 5. Retained Maintenance (sqlite_connection_maintenance)
  const [maintKind, setMaintKind] = useState('shrink_memory');
  const [maintOutcome, setMaintOutcome] = useState(null);

  // 6. Original-Session Descriptor Task Runner (sqlite_editor_operation)
  const [editorContract, setEditorContract] = useState(null);
  const [editorOpId, setEditorOpId] = useState('editor_extension_inventory');
  const [editorDraftJson, setEditorDraftJson] = useState('{}');
  const editorDraftRef = useRef('{}');
  const [editorResult, setEditorResult] = useState(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const ensureSession = useCallback(async () => {
    if (activeSessionId) return activeSessionId;
    const res = await api.post(endpointUrl, {
      action: 'open_session',
      language_profile: 'sqlite-sql',
      ...(databaseTargetId ? {database_target_id: databaseTargetId} : {}),
    });
    const data = res?.data?.data ?? res?.data;
    const sid = data?.session_id || '';
    if (!sid) {
      throw new Error(gettext('Unable to open SQLite session handle.'));
    }
    setOwnedSessionId(sid);
    return sid;
  }, [activeSessionId, api, databaseTargetId, endpointUrl]);

  const loadEditorContract = useCallback(async () => {
    if (!databaseTargetId) return;
    try {
      const c = await callSqlite({
        action: 'sqlite_editor_operation',
        request: {operation_id: 'describe'},
      });
      setEditorContract(c);
    } catch {
      // Optional initial load
    }
  }, [callSqlite, databaseTargetId]);

  useEffect(() => {
    loadEditorContract();
  }, [loadEditorContract]);

  const handleInspectSync = async () => {
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const res = await callSqlite({
        action: 'sqlite_connection_settings',
        sessionId: sid,
        request: {operation: 'inspect'},
      });
      setSyncState(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplySync = async () => {
    if (!syncState || !confirmSync) return;
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const res = await callSqlite({
        action: 'sqlite_connection_settings',
        sessionId: sid,
        request: {
          operation: 'set_connection_synchronous',
          value: syncTarget,
          expected_code: syncState.effective_code,
          confirmed: true,
        },
      });
      setSyncState(res);
      setConfirmSync(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleInspectLimit = async () => {
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const res = await callSqlite({
        action: 'sqlite_connection_limits',
        sessionId: sid,
        request: {operation: 'inspect', limit: limitName},
      });
      setLimitState(res);
      if (typeof res?.effective_value === 'number') {
        setLimitValue(String(res.effective_value));
      }
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyLimit = async () => {
    if (!limitState || !confirmLimit) return;
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const res = await callSqlite({
        action: 'sqlite_connection_limits',
        sessionId: sid,
        request: {
          operation: 'set_connection_limit',
          limit: limitName,
          value: Number(limitValue),
          expected_value: limitState.effective_value ?? limitState.before_value,
          confirmed: true,
        },
      });
      setLimitState(res);
      setConfirmLimit(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleInspectPragma = async () => {
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const res = await callSqlite({
        action: 'sqlite_connection_pragmas',
        sessionId: sid,
        request: {operation: 'inspect', pragma: pragmaName},
      });
      setPragmaState(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyPragma = async () => {
    if (!pragmaState || !confirmPragma) return;
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const isNum = NUMERIC_PRAGMAS.has(pragmaName);
      const nextVal = isNum ? Number(pragmaNumVal) : Boolean(pragmaBoolVal);
      const res = await callSqlite({
        action: 'sqlite_connection_pragmas',
        sessionId: sid,
        request: {
          operation: 'set_connection_pragma',
          pragma: pragmaName,
          value: nextVal,
          expected_value: pragmaState.effective_value ?? pragmaState.before_value,
          confirmed: true,
        },
      });
      setPragmaState(res);
      setConfirmPragma(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleInspectConfig = async () => {
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const res = await callSqlite({
        action: 'sqlite_connection_config',
        sessionId: sid,
        request: {operation: 'inspect', config: configName},
      });
      setConfigState(res);
      if (typeof res?.effective_value === 'boolean') {
        setConfigBoolVal(res.effective_value);
      }
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyConfig = async () => {
    if (!configState || !confirmConfig) return;
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const req = {
        operation: 'set_connection_config',
        config: configName,
        value: Boolean(configBoolVal),
        expected_value: configState.effective_value ?? configState.before_value,
        confirmed: true,
        ...(DANGEROUS_DBCONFIGS.has(configName) && configBoolVal
          ? {dangerous_change_confirmed: Boolean(confirmDangerousConfig)}
          : {}),
      };
      const res = await callSqlite({
        action: 'sqlite_connection_config',
        sessionId: sid,
        request: req,
      });
      setConfigState(res);
      setConfirmConfig(false);
      setConfirmDangerousConfig(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handlePrepareMaintenance = async () => {
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const res = await callSqlite({
        action: 'sqlite_connection_maintenance',
        sessionId: sid,
        request: {maintenance: maintKind},
      });
      setMaintOutcome(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRunEditorOperation = async () => {
    setBusy(true);
    setError('');
    try {
      const sid = await ensureSession();
      const draft = JSON.parse(editorDraftJson || '{}');
      const res = await callSqlite({
        action: 'sqlite_editor_operation',
        sessionId: sid,
        request: {operation_id: editorOpId, draft},
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
            <strong>{gettext('SQLite Connection Tuning, Limits, PRAGMAs & db_config')}</strong>
            <Badge
              status={activeSessionId ? 'success' : 'info'}
              label={activeSessionId ? `${gettext('Session')}: ${activeSessionId.slice(0, 8)}…` : gettext('On-Demand Handle')}
            />
          </Stack>
          <FormReference reference="SR-F-030566" />
        </Stack>

        <Banner status="info">
          {gettext('Applies compare-and-set original-connection synchronous durability, sqlite3_limit caps, session PRAGMAs, sqlite3_db_config flags, retained connection maintenance, and typed original-session descriptor tasks without claiming file-wide persistence for connection-local settings.')}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <SqliteSectionCard title={gettext('Original-Connection PRAGMA synchronous (Compare-and-Set)')}>
          <Grid columns={3} gap="sm">
            <Select
              label={gettext('Target Synchronous Mode')}
              value={syncTarget}
              options={[
                {value: 'OFF', label: 'OFF (0)'},
                {value: 'NORMAL', label: 'NORMAL (1)'},
                {value: 'FULL', label: 'FULL (2)'},
                {value: 'EXTRA', label: 'EXTRA (3)'},
              ]}
              onChange={setSyncTarget}
            />
            <div style={{display: 'flex', alignItems: 'flex-end'}}>
              <Button disabled={busy} onClick={handleInspectSync}>
                {gettext('Inspect Synchronous')}
              </Button>
            </div>
            <div style={{display: 'flex', alignItems: 'flex-end'}}>
              <Button variant="primary" disabled={busy || !syncState || !confirmSync} onClick={handleApplySync}>
                {gettext('Apply Synchronous')}
              </Button>
            </div>
          </Grid>
          {syncState && (
            <Stack direction="row" gap="sm" style={{alignItems: 'center'}}>
              <Badge status="info" label={`Effective code: ${syncState.effective_code}`} />
              <Checkbox
                label={gettext('Confirm connection-local synchronous change')}
                checked={confirmSync}
                onChange={setConfirmSync}
              />
            </Stack>
          )}
        </SqliteSectionCard>

        <SqliteSectionCard title={gettext('Native sqlite3_limit Controls (12 Categories)')}>
          <Grid columns={3} gap="sm">
            <Select
              label={gettext('Limit Category')}
              value={limitName}
              options={LIMIT_OPTIONS}
              onChange={setLimitName}
            />
            <TextField
              label={gettext('Limit Value (0..2147483647)')}
              value={limitValue}
              onChange={(e) => setLimitValue(textVal(e))}
            />
            <Stack direction="row" gap="sm" style={{alignItems: 'flex-end'}}>
              <Button disabled={busy} onClick={handleInspectLimit}>
                {gettext('Inspect Limit')}
              </Button>
              <Button variant="primary" disabled={busy || !limitState || !confirmLimit} onClick={handleApplyLimit}>
                {gettext('Apply Limit')}
              </Button>
            </Stack>
          </Grid>
          {limitState && (
            <Stack direction="row" gap="sm" style={{alignItems: 'center'}}>
              <Badge status="info" label={`${limitName}: ${limitState.effective_value}`} />
              <Checkbox
                label={gettext('Confirm original-handle sqlite3_limit update')}
                checked={confirmLimit}
                onChange={setConfirmLimit}
              />
            </Stack>
          )}
        </SqliteSectionCard>

        <SqliteSectionCard title={gettext('Original-Session PRAGMA Controls')}>
          <Grid columns={3} gap="sm">
            <Select
              label={gettext('Session PRAGMA')}
              value={pragmaName}
              options={PRAGMA_OPTIONS}
              onChange={setPragmaName}
            />
            {NUMERIC_PRAGMAS.has(pragmaName) ? (
              <TextField
                label={gettext('Numeric Value')}
                value={pragmaNumVal}
                onChange={(e) => setPragmaNumVal(textVal(e))}
              />
            ) : (
              <div style={{display: 'flex', alignItems: 'flex-end'}}>
                <Checkbox
                  label={gettext('Enable PRAGMA flag')}
                  checked={pragmaBoolVal}
                  onChange={setPragmaBoolVal}
                />
              </div>
            )}
            <Stack direction="row" gap="sm" style={{alignItems: 'flex-end'}}>
              <Button disabled={busy} onClick={handleInspectPragma}>
                {gettext('Inspect PRAGMA')}
              </Button>
              <Button variant="primary" disabled={busy || !pragmaState || !confirmPragma} onClick={handleApplyPragma}>
                {gettext('Apply PRAGMA')}
              </Button>
            </Stack>
          </Grid>
          {pragmaState && (
            <Stack direction="row" gap="sm" style={{alignItems: 'center'}}>
              <Badge status="info" label={`${pragmaName}: ${String(pragmaState.effective_value)}`} />
              <Checkbox
                label={gettext('Confirm original-session PRAGMA update')}
                checked={confirmPragma}
                onChange={setConfirmPragma}
              />
            </Stack>
          )}
        </SqliteSectionCard>

        <SqliteSectionCard title={gettext('Native sqlite3_db_config Policies')}>
          <Grid columns={3} gap="sm">
            <Select
              label={gettext('db_config Flag')}
              value={configName}
              options={DBCONFIG_OPTIONS}
              onChange={setConfigName}
            />
            <div style={{display: 'flex', alignItems: 'flex-end'}}>
              <Checkbox
                label={gettext('Target boolean state (ON)')}
                checked={configBoolVal}
                onChange={setConfigBoolVal}
              />
            </div>
            <Stack direction="row" gap="sm" style={{alignItems: 'flex-end'}}>
              <Button disabled={busy} onClick={handleInspectConfig}>
                {gettext('Inspect db_config')}
              </Button>
              <Button variant="primary" disabled={busy || !configState || !confirmConfig} onClick={handleApplyConfig}>
                {gettext('Apply db_config')}
              </Button>
            </Stack>
          </Grid>
          {configState && (
            <Stack gap="sm">
              <Badge status="info" label={`${configState.native_constant || configName}: ${String(configState.effective_value)}`} />
              <Checkbox
                label={gettext('Confirm sqlite3_db_config update')}
                checked={confirmConfig}
                onChange={setConfirmConfig}
              />
              {DANGEROUS_DBCONFIGS.has(configName) && configBoolVal && (
                <Checkbox
                  label={gettext('Acknowledge destructive reset / writable_schema / extension-loader risk')}
                  checked={confirmDangerousConfig}
                  onChange={setConfirmDangerousConfig}
                />
              )}
            </Stack>
          )}
        </SqliteSectionCard>

        <SqliteSectionCard title={gettext('Retained-Connection Maintenance & Descriptor Task Adapter')}>
          <Grid columns={2} gap="sm">
            <Select
              label={gettext('Retained Maintenance Recipe')}
              value={maintKind}
              options={[
                {value: 'shrink_memory', label: 'PRAGMA shrink_memory'},
                {value: 'analyze', label: 'ANALYZE (retained session)'},
                {value: 'reindex', label: 'REINDEX (retained session)'},
              ]}
              onChange={setMaintKind}
            />
            <div style={{display: 'flex', alignItems: 'flex-end'}}>
              <Button disabled={busy} onClick={handlePrepareMaintenance}>
                {gettext('Prepare Retained Maintenance')}
              </Button>
            </div>
          </Grid>
          {maintOutcome && (
            <Badge status="success" label={`${gettext('Prepared plan')}: ${maintOutcome.plan_id || maintOutcome.state || 'ready'}`} />
          )}

          <Grid columns={2} gap="sm">
            <TextField
              label={gettext('Original-Session Descriptor Task ID')}
              value={editorOpId}
              onChange={(e) => setEditorOpId(textVal(e))}
            />
            <div style={{display: 'flex', alignItems: 'flex-end'}}>
              <Button disabled={busy || !databaseTargetId} onClick={handleRunEditorOperation}>
                {gettext('Execute Session Descriptor Task')}
              </Button>
            </div>
          </Grid>
          <CodeEditor
            language="json"
            value={editorDraftJson}
            onChange={(val) => {
              if (val !== editorDraftRef.current) {
                editorDraftRef.current = val;
                setEditorDraftJson(val);
              }
            }}
            minHeight={90}
          />
          {editorContract?.operations && (
            <div>
              {gettext('Registered Original-Session Descriptor Tasks')}: <strong>{editorContract.operations.length}</strong>
            </div>
          )}
          {editorResult && (
            <pre style={{margin: 0, maxHeight: 160, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {JSON.stringify(editorResult, null, 2)}
            </pre>
          )}
        </SqliteSectionCard>
      </Stack>
    </Box>
  );
}

SqliteSessionTuningWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  sessionId: PropTypes.string,
  api: PropTypes.object,
};
