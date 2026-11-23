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
 * SR-F-030592: DuckDB SQL Editor Session Settings, Catalog Attachments,
 * Retained TEMP/Attached Metadata, Statement Grammar & Non-Executing PREPARE Diagnostics.
 */
export function SqlDuckdbSessionDialog({
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
  const [prepareResult, setPrepareResult] = useState(null);
  const [sessionCatalog, setSessionCatalog] = useState(null);

  const [attachPath, setAttachPath] = useState(':memory:');
  const [attachAlias, setAttachAlias] = useState('aux_catalog');
  const [attachReadOnly, setAttachReadOnly] = useState(false);

  const [settingFilter, setSettingFilter] = useState('threads');
  const [settingsResult, setSettingsResult] = useState(null);
  const [subsystemAction, setSubsystemAction] = useState('duckdb_attachments');
  const [subsystemResult, setSubsystemResult] = useState(null);

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
    throw new Error(gettext('Open a DuckDB query session first.'));
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

  const handleDescribeStatement = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callHost('describe_statement', {
        source: String(editorSource || 'SELECT 1'),
      });
      setPrepareResult(res);
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

  const handleInspectSettings = async () => {
    if (!post) return;
    setBusy(true);
    setError('');
    try {
      const sid = await resolveActiveSession();
      const res = await post({
        action: 'duckdb_runtime_settings',
        session_id: sid,
        language_profile: 'duckdb-sql',
        database_target_id: databaseTargetId,
        request: {operation: 'inventory', filter: settingFilter},
      });
      setSettingsResult(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleInspectSubsystem = async () => {
    if (!post) return;
    setBusy(true);
    setError('');
    try {
      const sid = await resolveActiveSession();
      const res = await post({
        action: subsystemAction,
        session_id: sid,
        language_profile: 'duckdb-sql',
        database_target_id: databaseTargetId,
        request: {operation: 'inventory'},
      });
      setSubsystemResult(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const quotedAlias = `"${String(attachAlias || 'aux_catalog').replace(/"/g, '""')}"`;
  const escapedPath = `'${String(attachPath || ':memory:').replace(/'/g, '\'\'')}'`;
  const attachSql = `ATTACH ${escapedPath} AS ${quotedAlias}${attachReadOnly ? ' (READ_ONLY)' : ''};`;
  const detachSql = `DETACH ${quotedAlias};`;

  return (
    <Dialog
      open={open}
      title={gettext('DuckDB Session Settings, Catalog Attachments, PREPARE & Grammar')}
      onClose={onClose}
      size="lg"
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <FormReference reference="SR-F-030592" />
          <Badge status="info" label={String(txLabel)} />
          {sessionId && <Badge status="success" label={`Session ${sessionId.slice(0, 8)}`} />}
        </Stack>
        <Banner status="info">
          {gettext(
            'Inspects original-session DuckDB runtime settings, attached catalogs, extensions, database-copy eligibility, non-executing extract_statements grammar checks, and PREPARE parameter/result metadata.'
          )}
        </Banner>
        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <Panel style={{padding: 12}}>
          <strong>{gettext('Non-Executing DuckDB Grammar, PREPARE Metadata & Retained Session Catalog')}</strong>
          <Stack gap="sm">
            <Stack direction="row" gap="sm" style={{alignItems: 'center'}}>
              <Button variant="primary" disabled={busy} onClick={handleValidateSyntax}>
                {gettext('Validate DuckDB Syntax')}
              </Button>
              <Button variant="secondary" disabled={busy} onClick={handleDescribeStatement}>
                {gettext('PREPARE & Inspect Types')}
              </Button>
              <Checkbox
                label={gettext('Include system catalogs')}
                checked={includeSystem}
                onChange={setIncludeSystem}
              />
              <Button variant="secondary" disabled={busy} onClick={handleRefreshCatalog}>
                {gettext('Capture Retained Session Metadata')}
              </Button>
            </Stack>
            {(syntaxResult || prepareResult || sessionCatalog) && (
              <pre style={{margin: 0, maxHeight: 140, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
                {JSON.stringify(prepareResult || syntaxResult || sessionCatalog, null, 2)}
              </pre>
            )}
          </Stack>
        </Panel>

        <Panel style={{padding: 12}}>
          <strong>{gettext('ATTACH / DETACH Catalog Statement Helper')}</strong>
          <Grid columns={3} gap="sm">
            <TextField
              label={gettext('Database Path or :memory:')}
              value={attachPath}
              onChange={(e) => setAttachPath(textVal(e))}
            />
            <TextField
              label={gettext('Catalog Alias')}
              value={attachAlias}
              onChange={(e) => setAttachAlias(textVal(e))}
            />
            <Box style={{display: 'flex', alignItems: 'flex-end'}}>
              <Checkbox
                label={gettext('READ_ONLY')}
                checked={attachReadOnly}
                onChange={setAttachReadOnly}
              />
            </Box>
          </Grid>
          <Stack direction="row" gap="sm">
            {onInsertSql && (
              <>
                <Button variant="secondary" onClick={() => onInsertSql(attachSql)}>
                  {gettext('Insert ATTACH')}
                </Button>
                <Button variant="secondary" onClick={() => onInsertSql(detachSql)}>
                  {gettext('Insert DETACH')}
                </Button>
              </>
            )}
            <Badge status="info" label={attachSql} />
          </Stack>
        </Panel>

        {post && (
          <Panel style={{padding: 12}}>
            <strong>{gettext('Original-Session Runtime Settings & Subsystem Inventories')}</strong>
            <Stack gap="sm">
              <Grid columns={2} gap="sm">
                <TextField
                  label={gettext('Runtime Setting Filter')}
                  value={settingFilter}
                  onChange={(e) => setSettingFilter(textVal(e))}
                />
                <Box style={{display: 'flex', alignItems: 'flex-end'}}>
                  <Button disabled={busy} onClick={handleInspectSettings}>
                    {gettext('Inspect Session Settings')}
                  </Button>
                </Box>
              </Grid>
              {settingsResult && (
                <Badge status="info" label={`Matched settings: ${settingsResult.settings?.length ?? 0}`} />
              )}
              <Grid columns={2} gap="sm">
                <Select
                  label={gettext('Original-Session Subsystem')}
                  value={subsystemAction}
                  options={[
                    {value: 'duckdb_attachments', label: 'Attached Catalogs (duckdb_attachments)'},
                    {value: 'duckdb_extensions', label: 'Extension Capabilities (duckdb_extensions)'},
                    {value: 'duckdb_database_copy', label: 'Database Copy Catalogs (duckdb_database_copy)'},
                  ]}
                  onChange={setSubsystemAction}
                />
                <Box style={{display: 'flex', alignItems: 'flex-end'}}>
                  <Button disabled={busy} onClick={handleInspectSubsystem}>
                    {gettext('Inspect Session Subsystem')}
                  </Button>
                </Box>
              </Grid>
              {subsystemResult && (
                <pre style={{margin: 0, maxHeight: 120, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
                  {JSON.stringify(subsystemResult, null, 2)}
                </pre>
              )}
            </Stack>
          </Panel>
        )}
      </Stack>
    </Dialog>
  );
}

SqlDuckdbSessionDialog.propTypes = {
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
 * SR-F-030593: DuckDB EXPLAIN & EXPLAIN ANALYZE Inspector.
 */
export function SqlDuckdbExplainDialog({
  open,
  editorSource = '',
  onClose,
  onRunExplain,
}) {
  const [explainMode, setExplainMode] = useState('logical_physical');
  const [explainFormat, setExplainFormat] = useState('TEXT');
  const [confirmAnalyze, setConfirmAnalyze] = useState(false);

  if (!open) return null;

  const trimmed = String(editorSource || 'SELECT 1').trim().replace(/;+\s*$/, '');
  const isAnalyze = explainMode === 'analyze';
  const formatClause = explainFormat !== 'TEXT' ? ` (FORMAT ${explainFormat})` : '';
  const previewSql = isAnalyze
    ? `EXPLAIN ANALYZE${formatClause} ${trimmed};`
    : `EXPLAIN${formatClause} ${trimmed};`;

  return (
    <Dialog
      open={open}
      title={gettext('DuckDB EXPLAIN & EXPLAIN ANALYZE Plan Inspector')}
      onClose={onClose}
      size="md"
    >
      <Stack gap="md">
        <FormReference reference="SR-F-030593" />
        <Banner status={isAnalyze ? 'warning' : 'info'}>
          {isAnalyze
            ? gettext('EXPLAIN ANALYZE executes the statement on DuckDB to collect operator cardinality and timing profiles.')
            : gettext('EXPLAIN compiles logical and physical plans without executing statement side effects.')}
        </Banner>
        <Grid columns={2} gap="sm">
          <Select
            label={gettext('Explain Mode')}
            value={explainMode}
            options={[
              {value: 'logical_physical', label: 'EXPLAIN (Logical & Physical Plan)'},
              {value: 'analyze', label: 'EXPLAIN ANALYZE (Executes Statement)'},
            ]}
            onChange={(val) => {
              setExplainMode(val);
              setConfirmAnalyze(false);
            }}
          />
          <Select
            label={gettext('Output Format')}
            value={explainFormat}
            options={[
              {value: 'TEXT', label: 'TEXT (ASCII Tree)'},
              {value: 'JSON', label: 'JSON (Operator Graph)'},
              {value: 'HTML', label: 'HTML'},
              {value: 'GRAPHVIZ', label: 'GRAPHVIZ (DOT)'},
            ]}
            onChange={setExplainFormat}
          />
        </Grid>
        {isAnalyze && (
          <Checkbox
            label={gettext('I understand EXPLAIN ANALYZE executes the statement')}
            checked={confirmAnalyze}
            onChange={setConfirmAnalyze}
          />
        )}
        <CodeEditor value={previewSql} language="sql" readOnly minHeight={100} />
        <Stack direction="row" gap="sm">
          <Button
            variant="primary"
            disabled={isAnalyze && !confirmAnalyze}
            onClick={() => onRunExplain(previewSql, explainMode)}
          >
            {gettext('Execute DuckDB Explain')}
          </Button>
          <Button variant="secondary" onClick={onClose}>
            {gettext('Cancel')}
          </Button>
        </Stack>
      </Stack>
    </Dialog>
  );
}

SqlDuckdbExplainDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  editorSource: PropTypes.string,
  onClose: PropTypes.func.isRequired,
  onRunExplain: PropTypes.func.isRequired,
};
