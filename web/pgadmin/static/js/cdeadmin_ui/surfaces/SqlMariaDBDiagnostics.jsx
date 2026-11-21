/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Grid, Panel, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextField} from '../primitives/Field';
import {Checkbox, Select} from '../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../feedback/Indicators';
import {Dialog} from '../overlays/Dialog';

/**
 * MDB-UI-08 (SR-F-030346): MariaDB Original-Session System Variables,
 * Optimizer Flagsets (`optimizer_switch` / `optimizer_trace`) & Editor Context Dialog.
 */
export function SqlMariaDBSessionDialog({
  open,
  transaction = null,
  callHost,
  onClose,
}) {
  const [diagConfirmed, setDiagConfirmed] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // Editor completion context
  const [editorContext, setEditorContext] = useState(null);

  // Session variable state
  const [variableName, setVariableName] = useState('sql_mode');
  const [varValueMode, setVarValueMode] = useState('VALUE');
  const [varValue, setVarValue] = useState('');
  const [varInspect, setVarInspect] = useState(null);
  const [varReview, setVarReview] = useState(null);

  // Flagset state
  const [flagsetName, setFlagsetName] = useState('optimizer_switch');
  const [flagMode, setFlagMode] = useState('VALUE');
  const [flagValue, setFlagValue] = useState('');
  const [flagInspect, setFlagInspect] = useState(null);
  const [flagReview, setFlagReview] = useState(null);

  useEffect(() => {
    if (!open) return;
    setError('');
    setNotice('');
  }, [open]);

  if (!open) return null;

  const nativeTx = transaction?.provider_payload || {};
  const observedBool = (v) =>
    typeof v === 'boolean' ? (v ? gettext('On') : gettext('Off')) : gettext('Not observed');

  const handleRefreshContext = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await callHost('mariadb_editor_context', {
        request: {
          operation: 'refresh_completion',
          diagnostics_change_confirmed: Boolean(diagConfirmed),
        },
      });
      setEditorContext(res);
      setNotice(gettext('Refreshed original-session MariaDB sql_mode, active role, and temporary table context.'));
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleInspectVariable = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await callHost('mariadb_session_variables', {
        request: {
          operation: 'inspect',
          variable: variableName.trim(),
          diagnostics_change_confirmed: Boolean(diagConfirmed),
        },
      });
      setVarInspect(res);
      setVarReview(null);
      if (res?.effective_value !== undefined && res?.effective_value !== null) {
        setVarValue(String(res.effective_value));
      }
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewVariable = async () => {
    setBusy(true);
    setError('');
    try {
      const req = {
        operation: 'review',
        variable: variableName.trim(),
        value_mode: varValueMode,
        diagnostics_change_confirmed: Boolean(diagConfirmed),
      };
      if (varValueMode === 'VALUE') req.value = varValue;
      const res = await callHost('mariadb_session_variables', {request: req});
      setVarReview(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyVariable = async () => {
    if (!varReview) return;
    setBusy(true);
    setError('');
    try {
      const req = {
        operation: 'set_session',
        variable: variableName.trim(),
        value_mode: varValueMode,
        expected_value: varReview.expected_value,
        confirmed: true,
        diagnostics_change_confirmed: Boolean(diagConfirmed),
      };
      if (varValueMode === 'VALUE') req.value = varValue;
      const res = await callHost('mariadb_session_variables', {request: req});
      setVarInspect(res);
      setVarReview(null);
      setNotice(gettext('Updated MariaDB original-session variable %s.', res.variable || variableName));
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleInspectFlagset = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await callHost('mariadb_session_flagsets', {
        request: {
          operation: 'inspect',
          variable: flagsetName,
          diagnostics_change_confirmed: Boolean(diagConfirmed),
        },
      });
      setFlagInspect(res);
      setFlagReview(null);
      if (res?.effective_value) setFlagValue(String(res.effective_value));
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewFlagset = async () => {
    setBusy(true);
    setError('');
    try {
      const req = {
        operation: 'review',
        variable: flagsetName,
        value_mode: flagMode,
        diagnostics_change_confirmed: Boolean(diagConfirmed),
      };
      if (flagMode === 'VALUE') req.value = flagValue;
      const res = await callHost('mariadb_session_flagsets', {request: req});
      setFlagReview(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyFlagset = async () => {
    if (!flagReview) return;
    setBusy(true);
    setError('');
    try {
      const req = {
        operation: 'set_session_flags',
        variable: flagsetName,
        value_mode: flagMode,
        expected_value: flagReview.expected_value,
        confirmed: true,
        diagnostics_change_confirmed: Boolean(diagConfirmed),
      };
      if (flagMode === 'VALUE') req.value = flagValue;
      const res = await callHost('mariadb_session_flagsets', {request: req});
      setFlagInspect(res);
      setFlagReview(null);
      setNotice(gettext('Updated MariaDB session %s flags.', flagsetName));
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      title={gettext('MariaDB Original-Session Variables, Optimizer Flagsets & Context')}
      formReference="SR-F-030346"
      size="large"
      onClose={onClose}
      actions={
        <Button intent="neutral" onClick={onClose}>
          {gettext('Close')}
        </Button>
      }
    >
      <Stack gap="comfortable" data-cdeadmin-qa-key="sql-surface.mariadb-session-diagnostics">
        <Banner status="info">
          {gettext(
            'Executes directly on the retained MariaDB SQL session (never a disposable connection). MariaDB DDL statements can implicitly commit active transactions.'
          )}
        </Banner>

        <Checkbox
          label={gettext('Confirm explicit original-session inspection updates SHOW WARNINGS / session diagnostics')}
          checked={diagConfirmed}
          onChange={(v) => setDiagConfirmed(Boolean(v))}
        />

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}
        {notice && <Banner status="success">{notice}</Banner>}

        <Panel variant="outlined" style={{padding: 12}}>
          <Stack gap="standard">
            <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between'}}>
              <strong>{gettext('Observed Session Transaction & Completion Overlay')}</strong>
              <Button intent="neutral" disabled={busy || !diagConfirmed} onClick={handleRefreshContext}>
                {gettext('Refresh Session Context & Temporary Tables')}
              </Button>
            </Stack>
            <Stack direction="row" gap="standard" style={{flexWrap: 'wrap', fontSize: '0.8rem'}}>
              <span>{gettext('Autocommit:')} <strong>{observedBool(nativeTx.autocommit)}</strong></span>
              <span>{gettext('In transaction:')} <strong>{observedBool(nativeTx.in_transaction)}</strong></span>
              {nativeTx.xa_state && <Badge label={`XA: ${nativeTx.xa_state}`} status="info" />}
              {editorContext?.context?.sql_mode !== undefined && (
                <span><code>sql_mode={editorContext.context.sql_mode || '(empty)'}</code></span>
              )}
              {editorContext?.context?.temporary_table_count !== undefined && (
                <Badge label={`Temp tables: ${editorContext.context.temporary_table_count}`} status="info" />
              )}
            </Stack>
          </Stack>
        </Panel>

        <Panel variant="outlined" style={{padding: 12}}>
          <Stack gap="standard">
            <strong>{gettext('Original-Session System Variable (SET SESSION)')}</strong>
            <Grid columns={3} gap="standard">
              <TextField
                label={gettext('Session Variable Name')}
                value={variableName}
                onChange={(e) => setVariableName(e.target.value)}
              />
              <Select
                label={gettext('Value Mode')}
                options={[
                  {value: 'VALUE', label: gettext('Explicit Value')},
                  {value: 'DEFAULT', label: gettext('Session DEFAULT')},
                ]}
                value={varValueMode}
                onChange={(v) => setVarValueMode(v)}
              />
              {varValueMode === 'VALUE' && (
                <TextField
                  label={gettext('New Session Value')}
                  value={varValue}
                  onChange={(e) => setVarValue(e.target.value)}
                />
              )}
            </Grid>
            <Stack direction="row" gap="standard">
              <Button intent="neutral" disabled={busy || !diagConfirmed || !variableName.trim()} onClick={handleInspectVariable}>
                {gettext('Inspect Variable')}
              </Button>
              <Button intent="neutral" disabled={busy || !diagConfirmed || !variableName.trim()} onClick={handleReviewVariable}>
                {gettext('Review Assignment')}
              </Button>
              {varReview?.ready_to_apply && (
                <Button intent="primary" disabled={busy} onClick={handleApplyVariable}>
                  {gettext('Confirm & Apply SET SESSION')}
                </Button>
              )}
            </Stack>
            {(varReview || varInspect) && (
              <Box style={{fontFamily: 'monospace', fontSize: '0.76rem', whiteSpace: 'pre-wrap'}}>
                {JSON.stringify(varReview || varInspect, null, 2)}
              </Box>
            )}
          </Stack>
        </Panel>

        <Panel variant="outlined" style={{padding: 12}}>
          <Stack gap="standard">
            <strong>{gettext('Optimizer FLAGSET (optimizer_switch / optimizer_trace)')}</strong>
            <Grid columns={3} gap="standard">
              <Select
                label={gettext('FLAGSET Variable')}
                options={[
                  {value: 'optimizer_switch', label: 'optimizer_switch'},
                  {value: 'optimizer_trace', label: 'optimizer_trace'},
                ]}
                value={flagsetName}
                onChange={(v) => setFlagsetName(v)}
              />
              <Select
                label={gettext('Assignment Mode')}
                options={[
                  {value: 'VALUE', label: gettext('Flag Expression (e.g. index_merge=on)')},
                  {value: 'DEFAULT', label: gettext('Reset to DEFAULT')},
                ]}
                value={flagMode}
                onChange={(v) => setFlagMode(v)}
              />
              {flagMode === 'VALUE' && (
                <TextField
                  label={gettext('Flagset Value')}
                  value={flagValue}
                  onChange={(e) => setFlagValue(e.target.value)}
                />
              )}
            </Grid>
            <Stack direction="row" gap="standard">
              <Button intent="neutral" disabled={busy || !diagConfirmed} onClick={handleInspectFlagset}>
                {gettext('Inspect Flagset')}
              </Button>
              <Button intent="neutral" disabled={busy || !diagConfirmed} onClick={handleReviewFlagset}>
                {gettext('Review Flagset')}
              </Button>
              {flagReview?.ready_to_apply && (
                <Button intent="primary" disabled={busy} onClick={handleApplyFlagset}>
                  {gettext('Confirm & Apply Flagset')}
                </Button>
              )}
            </Stack>
            {(flagReview || flagInspect) && (
              <Box style={{fontFamily: 'monospace', fontSize: '0.76rem', whiteSpace: 'pre-wrap', maxHeight: 140, overflow: 'auto'}}>
                {JSON.stringify(flagReview || flagInspect, null, 2)}
              </Box>
            )}
          </Stack>
        </Panel>
      </Stack>
    </Dialog>
  );
}

SqlMariaDBSessionDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  transaction: PropTypes.object,
  callHost: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};

/**
 * MDB-UI-09: Explicit confirmation before running MariaDB ANALYZE FORMAT=JSON
 * (which executes the statement on the live session to collect r_rows / r_total_time_ms).
 */
export function SqlMariaDBAnalyzeConsentDialog({open, busy = false, onConfirm, onClose}) {
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    if (open) setConfirmed(false);
  }, [open]);

  if (!open) return null;

  return (
    <Dialog
      open={open}
      title={gettext('Run MariaDB ANALYZE FORMAT=JSON (Executes Statement)')}
      size="medium"
      onClose={onClose}
      actions={
        <>
          <Button intent="neutral" disabled={busy} onClick={onClose}>
            {gettext('Cancel')}
          </Button>
          <Button intent="primary" disabled={busy || !confirmed} onClick={onConfirm}>
            {gettext('Execute ANALYZE FORMAT=JSON')}
          </Button>
        </>
      }
    >
      <Stack gap="standard">
        <Banner status="warning">
          {gettext(
            'Unlike EXPLAIN FORMAT=JSON, MariaDB ANALYZE FORMAT=JSON executes the statement on the active session to measure actual r_loops, r_rows, and r_total_time_ms.'
          )}
        </Banner>
        <Checkbox
          label={gettext('I understand ANALYZE FORMAT=JSON executes this statement on the active MariaDB session')}
          checked={confirmed}
          onChange={(v) => setConfirmed(Boolean(v))}
        />
      </Stack>
    </Dialog>
  );
}

SqlMariaDBAnalyzeConsentDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  busy: PropTypes.bool,
  onConfirm: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};
