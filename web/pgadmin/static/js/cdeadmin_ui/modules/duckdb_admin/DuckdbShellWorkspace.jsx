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
import {DuckdbSectionCard, createDuckdbWorkspaceCaller} from './duckdbAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

/**
 * DU-AUD-18 (SR-F-030589): DuckDB Supervised Directive & SQL Batch Runner + CLI Provenance.
 */
export default function DuckdbShellWorkspace({
  endpointUrl,
  databaseTargetId = '',
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callDuckdb = useMemo(
    () => createDuckdbWorkspaceCaller(api, endpointUrl, databaseTargetId),
    [api, endpointUrl, databaseTargetId]
  );

  const [provenance, setProvenance] = useState(null);
  const [mode, setMode] = useState('box');
  const [readOnly, setReadOnly] = useState(true);
  const [bailOnError, setBailOnError] = useState(true);
  const [timeoutSec, setTimeoutSec] = useState('15');
  const initialScript = '.mode box\n.tables\nSELECT version() AS duckdb_version;';
  const scriptRef = useRef(initialScript);
  const [batchResult, setBatchResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadProvenance = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const prov = await callDuckdb({action: 'duckdb_ops_shell_provenance'});
      setProvenance(prov);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [callDuckdb]);

  useEffect(() => {
    loadProvenance();
  }, [loadProvenance]);

  const handleExecuteBatch = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_shell_execute',
        request: {
          script: scriptRef.current,
          mode,
          read_only: Boolean(readOnly),
          bail_on_error: Boolean(bailOnError),
          timeout_seconds: Number(timeoutSec) || 15,
        },
      });
      setBatchResult(res);
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
            <strong>{gettext('DuckDB Directive & SQL Batch Runner')}</strong>
            {provenance && (
              <Badge
                status="success"
                label={`Runtime ${provenance.python_package?.version || '1.5.2'} (${provenance.python_package?.source_id || ''})`}
              />
            )}
          </Stack>
          <FormReference reference="SR-F-030589" />
        </Stack>

        <Banner status="info">
          {gettext(
            'Runs supervised DuckDB dot-directives (.mode, .headers, .separator, .nullvalue, .bail, .echo, .timer, .tables, .schema, .indexes, .databases, .show, .read, .output/.once) and multi-statement SQL in an isolated connection while refusing host escape commands (.shell, .cd, .open).'
          )}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        {provenance && (
          <DuckdbSectionCard title={gettext('DuckDB Engine & Optional CLI Binary Provenance')}>
            <div>{gettext('Python DuckDB Version')}: <code>{provenance.python_package?.version}</code></div>
            <div>{gettext('Source ID')}: <code>{provenance.python_package?.source_id}</code></div>
            <div>{gettext('CLI Binary Status')}: <code>{provenance.cli_binary?.status || 'not_configured'}</code></div>
          </DuckdbSectionCard>
        )}

        <DuckdbSectionCard
          title={gettext('Supervised Directive & SQL Batch Execution')}
          actions={
            <Button variant="primary" disabled={busy} onClick={handleExecuteBatch}>
              {gettext('Execute Batch Script')}
            </Button>
          }
        >
          <Grid columns={4} gap="sm">
            <Select
              label={gettext('Initial Output Mode')}
              value={mode}
              options={[
                {value: 'box', label: 'box'},
                {value: 'markdown', label: 'markdown'},
                {value: 'csv', label: 'csv'},
                {value: 'tsv', label: 'tsv'},
                {value: 'json', label: 'json'},
                {value: 'line', label: 'line'},
                {value: 'list', label: 'list'},
              ]}
              onChange={setMode}
            />
            <TextField
              label={gettext('Timeout (seconds)')}
              value={timeoutSec}
              onChange={(e) => setTimeoutSec(textVal(e))}
            />
            <Box style={{display: 'flex', alignItems: 'flex-end'}}>
              <Checkbox
                label={gettext('Open isolated connection READ_ONLY')}
                checked={readOnly}
                onChange={setReadOnly}
              />
            </Box>
            <Box style={{display: 'flex', alignItems: 'flex-end'}}>
              <Checkbox
                label={gettext('Bail on first error (.bail on)')}
                checked={bailOnError}
                onChange={setBailOnError}
              />
            </Box>
          </Grid>
          <CodeEditor
            value={initialScript}
            language="sql"
            onChange={(val) => {
              scriptRef.current = val;
            }}
            minHeight={150}
          />
          {batchResult && (
            <pre style={{margin: 0, maxHeight: 280, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {batchResult.output || JSON.stringify(batchResult, null, 2)}
            </pre>
          )}
        </DuckdbSectionCard>
      </Stack>
    </Box>
  );
}

DuckdbShellWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  api: PropTypes.object,
};
