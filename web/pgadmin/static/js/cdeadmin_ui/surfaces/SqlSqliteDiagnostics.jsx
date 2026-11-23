/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Grid, Panel, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextField} from '../primitives/Field';
import {Checkbox, Select} from '../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../feedback/Indicators';
import {Dialog} from '../overlays/Dialog';
import FormReference from '../navigation/FormReference';
import CodeEditor from '../editors/CodeEditor';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

/**
 * SR-F-030567: SQLite Original-Session Framing, ATTACH/DETACH Namespace Helper,
 * Live Connection Limits/PRAGMAs/db_config, Extensions/Captures & Grammar Check.
 */
export function SqlSqliteSessionDialog({
  open,
  transaction = null,
  editorSource = '',
  sessionId = null,
  databaseTargetId = '',
  ensureSession,
  callHost,
  post,
  onInsertSql = null,
  onClose,
}) {
  const [includeSystem, setIncludeSystem] = useState(false);
  const [syntaxResult, setSyntaxResult] = useState(null);
  const [sessionCatalog, setSessionCatalog] = useState(null);

  const [attachPath, setAttachPath] = useState(':memory:');
  const [attachAlias, setAttachAlias] = useState('aux_db');

  const [pragmaName, setPragmaName] = useState('foreign_keys');
  const [pragmaEnabled, setPragmaEnabled] = useState(true);
  const [pragmaState, setPragmaState] = useState(null);
  const [confirmPragma, setConfirmPragma] = useState(false);

  const [limitName, setLimitName] = useState('sql_length');
  const [limitVal, setLimitVal] = useState('1000000');
  const [limitState, setLimitState] = useState(null);
  const [confirmLimit, setConfirmLimit] = useState(false);

  const [sessionToolAction, setSessionToolAction] = useState('sqlite_extensions');
  const [sessionToolSummary, setSessionToolSummary] = useState(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (!open) return null;

  const txLabel = transaction?.state || transaction?.provider_payload?.transaction_state || 'AUTOCOMMIT';

  const resolveActiveSession = async () => {
    if (sessionId) return sessionId;
    if (ensureSession) {
      const sid = await ensureSession();
      if (sid) return sid;
    }
    throw new Error(gettext('Open a SQLite query session first.'));
  };

  const handleValidateSyntax = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callHost('validate_source', {
        source: String(editorSource || 'SELECT 1'),
        script: true,
      });
      setSyntaxResult(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRefreshCatalog = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callHost('refresh_session_metadata', {
        include_system: Boolean(includeSystem),
      });
      setSessionCatalog(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleInspectPragma = async () => {
    if (!post) return;
    setBusy(true);
    setError('');
    try {
      const sid = await resolveActiveSession();
      const res = await post({
        action: 'sqlite_connection_pragmas',
        session_id: sid,
        database_target_id: databaseTargetId,
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
    if (!post || !pragmaState || !confirmPragma) return;
    setBusy(true);
    setError('');
    try {
      const sid = await resolveActiveSession();
      const res = await post({
        action: 'sqlite_connection_pragmas',
        session_id: sid,
        database_target_id: databaseTargetId,
        request: {
          operation: 'set_connection_pragma',
          pragma: pragmaName,
          value: Boolean(pragmaEnabled),
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

  const handleInspectLimit = async () => {
    if (!post) return;
    setBusy(true);
    setError('');
    try {
      const sid = await resolveActiveSession();
      const res = await post({
        action: 'sqlite_connection_limits',
        session_id: sid,
        database_target_id: databaseTargetId,
        request: {operation: 'inspect', limit: limitName},
      });
      setLimitState(res);
      if (typeof res?.effective_value === 'number') {
        setLimitVal(String(res.effective_value));
      }
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyLimit = async () => {
    if (!post || !limitState || !confirmLimit) return;
    setBusy(true);
    setError('');
    try {
      const sid = await resolveActiveSession();
      const res = await post({
        action: 'sqlite_connection_limits',
        session_id: sid,
        database_target_id: databaseTargetId,
        request: {
          operation: 'set_connection_limit',
          limit: limitName,
          value: Number(limitVal),
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

  const handleInspectSessionSubsystem = async () => {
    if (!post) return;
    setBusy(true);
    setError('');
    try {
      const sid = await resolveActiveSession();
      const res = await post({
        action: sessionToolAction,
        session_id: sid,
        database_target_id: databaseTargetId,
        request: {operation: 'inventory'},
      });
      setSessionToolSummary(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const quotedAlias = `"${String(attachAlias || 'aux_db').replace(/"/g, '""')}"`;
  const escapedPath = `'${String(attachPath || ':memory:').replace(/'/g, '\'\'')}'`;
  const attachSql = `ATTACH DATABASE ${escapedPath} AS ${quotedAlias};`;
  const detachSql = `DETACH DATABASE ${quotedAlias};`;

  return (
    <Dialog
      open={open}
      title={gettext('SQLite Session Tuning, ATTACH Namespaces, Captures & Grammar')}
      onClose={onClose}
      size="lg"
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <FormReference reference="SR-F-030567" />
          <Badge status="info" label={String(txLabel)} />
          {sessionId && <Badge status="success" label={`Session ${sessionId.slice(0, 8)}…`} />}
        </Stack>
        <Banner status="info">
          {gettext(
            'Manages original-handle SQLite PRAGMAs, sqlite3_limit bounds, ATTACH/DETACH namespace statements, retained TEMP/attached metadata discovery, non-executing grammar validation, and live extension/preupdate/session-capture inventories.'
          )}
        </Banner>
        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <Panel style={{padding: 12}}>
          <strong>{gettext('Non-Executing SQLite Grammar Validation & Retained TEMP/Attached Catalog')}</strong>
          <Stack gap="sm">
            <Stack direction="row" gap="sm" style={{alignItems: 'center'}}>
              <Button variant="primary" disabled={busy} onClick={handleValidateSyntax}>
                {gettext('Validate SQLite Syntax Without Execution')}
              </Button>
              <Checkbox
                label={gettext('Include sqlite_schema system objects')}
                checked={includeSystem}
                onChange={setIncludeSystem}
              />
              <Button variant="secondary" disabled={busy} onClick={handleRefreshCatalog}>
                {gettext('Capture Retained Session Metadata')}
              </Button>
            </Stack>
            {syntaxResult && (
              <pre style={{margin: 0, maxHeight: 120, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
                {JSON.stringify(syntaxResult, null, 2)}
              </pre>
            )}
            {sessionCatalog && (
              <pre style={{margin: 0, maxHeight: 120, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
                {JSON.stringify(sessionCatalog, null, 2)}
              </pre>
            )}
          </Stack>
        </Panel>

        <Panel style={{padding: 12}}>
          <strong>{gettext('Session ATTACH / DETACH Namespace Builder')}</strong>
          <Grid columns={2} gap="sm">
            <TextField
              label={gettext('Database File URI / :memory:')}
              value={attachPath}
              onChange={(e) => setAttachPath(textVal(e))}
            />
            <TextField
              label={gettext('Schema Alias')}
              value={attachAlias}
              onChange={(e) => setAttachAlias(textVal(e))}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            {onInsertSql && (
              <>
                <Button variant="secondary" onClick={() => onInsertSql(attachSql)}>
                  {gettext('Insert ATTACH Statement')}
                </Button>
                <Button variant="secondary" onClick={() => onInsertSql(detachSql)}>
                  {gettext('Insert DETACH Statement')}
                </Button>
              </>
            )}
            <Badge status="info" label={attachSql} />
          </Stack>
        </Panel>

        {post && (
          <Panel style={{padding: 12}}>
            <strong>{gettext('Original-Session PRAGMAs, sqlite3_limit & Helper Subsystems')}</strong>
            <Stack gap="sm">
              <Grid columns={3} gap="sm">
                <Select
                  label={gettext('Boolean PRAGMA')}
                  value={pragmaName}
                  options={[
                    {value: 'foreign_keys', label: 'foreign_keys'},
                    {value: 'recursive_triggers', label: 'recursive_triggers'},
                    {value: 'query_only', label: 'query_only'},
                    {value: 'defer_foreign_keys', label: 'defer_foreign_keys'},
                    {value: 'trusted_schema', label: 'trusted_schema'},
                    {value: 'cell_size_check', label: 'cell_size_check'},
                  ]}
                  onChange={setPragmaName}
                />
                <Box style={{display: 'flex', alignItems: 'flex-end'}}>
                  <Checkbox
                    label={gettext('Enable PRAGMA')}
                    checked={pragmaEnabled}
                    onChange={setPragmaEnabled}
                  />
                </Box>
                <Stack direction="row" gap="sm" style={{alignItems: 'flex-end'}}>
                  <Button disabled={busy} onClick={handleInspectPragma}>
                    {gettext('Inspect PRAGMA')}
                  </Button>
                  <Button variant="primary" disabled={busy || !pragmaState || !confirmPragma} onClick={handleApplyPragma}>
                    {gettext('Set PRAGMA')}
                  </Button>
                </Stack>
              </Grid>
              {pragmaState && (
                <Stack direction="row" gap="sm" style={{alignItems: 'center'}}>
                  <Badge status="info" label={`${pragmaName}: ${String(pragmaState.effective_value)}`} />
                  <Checkbox
                    label={gettext('Confirm session PRAGMA update')}
                    checked={confirmPragma}
                    onChange={setConfirmPragma}
                  />
                </Stack>
              )}

              <Grid columns={3} gap="sm">
                <Select
                  label={gettext('sqlite3_limit Category')}
                  value={limitName}
                  options={[
                    {value: 'sql_length', label: 'SQLITE_LIMIT_SQL_LENGTH'},
                    {value: 'vdbe_op', label: 'SQLITE_LIMIT_VDBE_OP'},
                    {value: 'worker_threads', label: 'SQLITE_LIMIT_WORKER_THREADS'},
                    {value: 'attached', label: 'SQLITE_LIMIT_ATTACHED'},
                    {value: 'variable_number', label: 'SQLITE_LIMIT_VARIABLE_NUMBER'},
                  ]}
                  onChange={setLimitName}
                />
                <TextField
                  label={gettext('Limit Value')}
                  value={limitVal}
                  onChange={(e) => setLimitVal(textVal(e))}
                />
                <Stack direction="row" gap="sm" style={{alignItems: 'flex-end'}}>
                  <Button disabled={busy} onClick={handleInspectLimit}>
                    {gettext('Inspect Limit')}
                  </Button>
                  <Button variant="primary" disabled={busy || !limitState || !confirmLimit} onClick={handleApplyLimit}>
                    {gettext('Set Limit')}
                  </Button>
                </Stack>
              </Grid>
              {limitState && (
                <Stack direction="row" gap="sm" style={{alignItems: 'center'}}>
                  <Badge status="info" label={`${limitName}: ${limitState.effective_value}`} />
                  <Checkbox
                    label={gettext('Confirm session limit update')}
                    checked={confirmLimit}
                    onChange={setConfirmLimit}
                  />
                </Stack>
              )}

              <Grid columns={2} gap="sm">
                <Select
                  label={gettext('Original-Session Helper Inventory')}
                  value={sessionToolAction}
                  options={[
                    {value: 'sqlite_extensions', label: 'Approved Loadable Extensions'},
                    {value: 'sqlite_native_sessions', label: 'Native Changeset / Patchset Captures (3.53+)'},
                    {value: 'sqlite_native_arrays', label: 'Native Typed CARRAY Bindings (3.53+)'},
                    {value: 'sqlite_native_preupdate', label: 'Native Preupdate Hook Capture (3.45.1+)'},
                  ]}
                  onChange={setSessionToolAction}
                />
                <Box style={{display: 'flex', alignItems: 'flex-end'}}>
                  <Button disabled={busy} onClick={handleInspectSessionSubsystem}>
                    {gettext('Inspect Session Subsystem')}
                  </Button>
                </Box>
              </Grid>
              {sessionToolSummary && (
                <pre style={{margin: 0, maxHeight: 120, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
                  {JSON.stringify(sessionToolSummary, null, 2)}
                </pre>
              )}
            </Stack>
          </Panel>
        )}
      </Stack>
    </Dialog>
  );
}

SqlSqliteSessionDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  transaction: PropTypes.object,
  editorSource: PropTypes.string,
  sessionId: PropTypes.string,
  databaseTargetId: PropTypes.string,
  ensureSession: PropTypes.func,
  callHost: PropTypes.func.isRequired,
  post: PropTypes.func,
  onInsertSql: PropTypes.func,
  onClose: PropTypes.func.isRequired,
};

/**
 * SR-F-030568: SQLite EXPLAIN QUERY PLAN & VDBE Bytecode (`EXPLAIN`) Inspector.
 */
export function SqlSqliteExplainDialog({
  open,
  editorSource = '',
  onClose,
  onRunExplain,
}) {
  const [explainMode, setExplainMode] = useState('query_plan');

  if (!open) return null;

  const trimmed = String(editorSource || 'SELECT 1').trim().replace(/;+\s*$/, '');
  const previewSql =
    explainMode === 'vdbe'
      ? `EXPLAIN ${trimmed};`
      : `EXPLAIN QUERY PLAN ${trimmed};`;

  return (
    <Dialog
      open={open}
      title={gettext('SQLite EXPLAIN QUERY PLAN & VDBE Bytecode')}
      onClose={onClose}
      size="md"
    >
      <Stack gap="md">
        <FormReference reference="SR-F-030568" />
        <Banner status="info">
          {gettext(
            'Prepares SQLite EXPLAIN QUERY PLAN (index/scan hierarchy) or EXPLAIN (VDBE virtual machine opcodes) without mutating database rows.'
          )}
        </Banner>
        <Select
          label={gettext('SQLite Explain Mode')}
          value={explainMode}
          options={[
            {value: 'query_plan', label: 'EXPLAIN QUERY PLAN (Scan, Search & Temp B-Tree Tree)'},
            {value: 'vdbe', label: 'EXPLAIN (VDBE Virtual Machine Bytecode Program)'},
          ]}
          onChange={setExplainMode}
        />
        <CodeEditor value={previewSql} language="sql" readOnly minHeight={100} />
        <Stack direction="row" gap="sm">
          <Button
            variant="primary"
            onClick={() => {
              onRunExplain(previewSql, explainMode);
            }}
          >
            {gettext('Execute SQLite Explain')}
          </Button>
          <Button variant="secondary" onClick={onClose}>
            {gettext('Cancel')}
          </Button>
        </Stack>
      </Stack>
    </Dialog>
  );
}

SqlSqliteExplainDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  editorSource: PropTypes.string,
  onClose: PropTypes.func.isRequired,
  onRunExplain: PropTypes.func.isRequired,
};
