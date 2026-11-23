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
import {Checkbox, Select} from '../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../feedback/Indicators';
import {Dialog} from '../overlays/Dialog';
import FormReference from '../navigation/FormReference';
import CodeEditor from '../editors/CodeEditor';

/**
 * PG-UI-06 (SR-F-030455): PostgreSQL Original-Session Framing, Retained Catalog
 * Refresh & Target-Major Non-Executing Grammar Validation Dialog.
 */
export function SqlPostgresSessionDialog({
  open,
  transaction = null,
  editorSource = '',
  callHost,
  onClose,
}) {
  const [targetMajor, setTargetMajor] = useState('18');
  const [includeSystem, setIncludeSystem] = useState(false);
  const [syntaxResult, setSyntaxResult] = useState(null);
  const [sessionCatalog, setSessionCatalog] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (!open) return null;

  const nativeTx = transaction?.provider_payload || {};

  const handleValidateSyntax = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callHost('validate_source', {
        source: String(editorSource || 'SELECT 1'),
        script: true,
        target_server_version: Number(targetMajor) * 10000,
      });
      setSyntaxResult(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRefreshSessionCatalog = async () => {
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

  return (
    <Dialog
      open={open}
      title={gettext('PostgreSQL Session Framing, Retained Catalog & Grammar')}
      onClose={onClose}
      size="lg"
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <FormReference reference="SR-F-030455" />
          <Badge status="info" label={nativeTx.transaction_status || 'IDLE'} />
        </Stack>
        <Banner status="info">
          {gettext(
            'Checks SQL, SQL-body, and PL/pgSQL syntax against the selected PostgreSQL major without executing statements, and observes retained temporary-schema catalog objects on the original backend.'
          )}
        </Banner>
        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <Panel style={{padding: 12}}><strong>{gettext('Target-Major Non-Executing Grammar Validation')}</strong>
          <Stack gap="sm">
            <Grid columns={2} gap="sm">
              <Select
                label={gettext('Target Major Version')}
                value={targetMajor}
                options={[
                  {value: '18', label: 'PostgreSQL 18 (VIRTUAL generated, WITHOUT OVERLAPS, NOT ENFORCED)'},
                  {value: '17', label: 'PostgreSQL 17 (MERGE RETURNING, JSON_TABLE)'},
                  {value: '16', label: 'PostgreSQL 16 (SQL/JSON constructors, pg_stat_io)'},
                  {value: '15', label: 'PostgreSQL 15 (MERGE, SECURITY INVOKER views)'},
                ]}
                onChange={setTargetMajor}
              />
              <Box>
                <Button variant="primary" disabled={busy} onClick={handleValidateSyntax}>
                  {gettext('Validate Editor SQL Without Execution')}
                </Button>
              </Box>
            </Grid>
            {syntaxResult && (
              <CodeEditor
                value={JSON.stringify(syntaxResult, null, 2)}
                language="json"
                readOnly
                height="160px"
              />
            )}
          </Stack>
        </Panel>

        <Panel style={{padding: 12}}><strong>{gettext('Retained-Session Temporary Schema & Search-Path Catalog')}</strong>
          <Stack gap="sm">
            <Checkbox
              label={gettext('Include pg_catalog system objects in retained snapshot')}
              checked={includeSystem}
              onChange={setIncludeSystem}
            />
            <Button variant="secondary" disabled={busy} onClick={handleRefreshSessionCatalog}>
              {gettext('Capture Original-Session Metadata')}
            </Button>
            {sessionCatalog && (
              <CodeEditor
                value={JSON.stringify(sessionCatalog, null, 2)}
                language="json"
                readOnly
                height="160px"
              />
            )}
          </Stack>
        </Panel>
      </Stack>
    </Dialog>
  );
}

SqlPostgresSessionDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  transaction: PropTypes.object,
  editorSource: PropTypes.string,
  callHost: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};

/**
 * PG-UI-07 (SR-F-030456): PostgreSQL EXPLAIN ANALYZE Execution-Consent Dialog.
 */
export function SqlPostgresAnalyzeConsentDialog({
  open,
  onClose,
  onConfirmAnalyze,
}) {
  const [buffers, setBuffers] = useState(true);
  const [wal, setWal] = useState(true);
  const [settingsOpt, setSettingsOpt] = useState(true);
  const [genericPlan, setGenericPlan] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);

  if (!open) return null;

  return (
    <Dialog
      open={open}
      title={gettext('Confirm Live EXPLAIN ANALYZE Execution')}
      onClose={onClose}
      size="md"
    >
      <Stack gap="md">
        <FormReference reference="SR-F-030456" />
        <Banner status="warning">
          {gettext(
            'PostgreSQL EXPLAIN ANALYZE executes the target statement (including INSERT, UPDATE, DELETE, and volatile functions) to measure actual runtime, buffers, and WAL generation.'
          )}
        </Banner>
        <Grid columns={2} gap="sm">
          <Checkbox label="BUFFERS" checked={buffers} onChange={setBuffers} />
          <Checkbox label="WAL" checked={wal} onChange={setWal} />
          <Checkbox label="SETTINGS" checked={settingsOpt} onChange={setSettingsOpt} />
          <Checkbox
            label={gettext('GENERIC_PLAN (non-executing parameter plan)')}
            checked={genericPlan}
            onChange={(v) => {
              setGenericPlan(v);
              if (v) setWal(false);
            }}
          />
        </Grid>
        <Checkbox
          label={gettext('I understand EXPLAIN ANALYZE executes the statement on the connected PostgreSQL session')}
          checked={consentChecked || genericPlan}
          onChange={setConsentChecked}
        />
        <Stack direction="row" gap="sm">
          <Button
            variant="primary"
            disabled={!consentChecked && !genericPlan}
            onClick={() =>
              onConfirmAnalyze({
                analyze: !genericPlan,
                buffers,
                wal: !genericPlan && wal,
                settings: settingsOpt,
                generic_plan: genericPlan,
              })
            }
          >
            {genericPlan ? gettext('Run EXPLAIN (GENERIC_PLAN)') : gettext('Execute EXPLAIN ANALYZE')}
          </Button>
          <Button variant="secondary" onClick={onClose}>
            {gettext('Cancel')}
          </Button>
        </Stack>
      </Stack>
    </Dialog>
  );
}

SqlPostgresAnalyzeConsentDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  onConfirmAnalyze: PropTypes.func.isRequired,
};
