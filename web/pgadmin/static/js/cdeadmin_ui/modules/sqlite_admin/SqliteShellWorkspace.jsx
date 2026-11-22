/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import getApiInstance from 'sources/api_instance';
import {Box, Grid, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import {SqliteSectionCard, createSqliteWorkspaceCaller} from './sqliteAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

/**
 * SQ-AUD-13 (SR-F-030564): Declared External Shell (`sqlite-shell`) & Matching CLI Qualification.
 */
export default function SqliteShellWorkspace({
  endpointUrl,
  databaseTargetId = '',
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callSqlite = useMemo(
    () => createSqliteWorkspaceCaller(api, endpointUrl, databaseTargetId),
    [api, endpointUrl, databaseTargetId]
  );

  const [provenance, setProvenance] = useState(null);
  const [command, setCommand] = useState('dbinfo');
  const [pattern, setPattern] = useState('');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadProvenance = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const prov = await callSqlite({action: 'sqlite_ops_shell_provenance'});
      setProvenance(prov);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [callSqlite]);

  useEffect(() => {
    loadProvenance();
  }, [loadProvenance]);

  const handleRunCommand = async () => {
    setBusy(true);
    setError('');
    try {
      const req = {command};
      if (pattern.trim() && ['schema', 'tables', 'indexes'].includes(command)) {
        req.pattern = pattern.trim();
      }
      const res = await callSqlite({action: 'sqlite_ops_shell_inspect', request: req});
      setResult(res);
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
            <strong>{gettext('SQLite Native Shell Inspection (sqlite-shell)')}</strong>
            <Badge
              status={provenance?.matched ? 'success' : 'warning'}
              label={
                provenance?.matched
                  ? `${gettext('Matched CLI')} ${provenance.cli_runtime?.version}`
                  : gettext('CLI Unverified')
              }
            />
          </Stack>
          <FormReference reference="SR-F-030564" />
        </Stack>

        <Banner status="info">
          {gettext('Verifies exact sqlite_version() and sqlite_source_id() agreement between Python sqlite3 and CDEADMIN_SQLITE_BINARY, then runs allowlisted dot-commands in an isolated -readonly -safe -batch child process.')}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        {provenance && (
          <SqliteSectionCard title={gettext('Verified CLI & Library Build Provenance')}>
            <div>{gettext('Version')}: <code>{provenance.cli_runtime?.version}</code></div>
            <div>{gettext('Source ID')}: <code>{provenance.cli_runtime?.source_id}</code></div>
            <div>{gettext('Binary SHA-256')}: <code>{provenance.binary_sha256}</code></div>
          </SqliteSectionCard>
        )}

        <SqliteSectionCard title={gettext('Read-Only Safe Dot-Command Inspector')}>
          <Grid columns={2} gap="sm">
            <Select
              label={gettext('Allowlisted Dot-Command')}
              value={command}
              onChange={(val) => setCommand(val)}
              options={[
                {value: 'dbinfo', label: '.dbinfo (Database header & page metrics)'},
                {value: 'schema', label: '.schema (Object DDL definitions)'},
                {value: 'fullschema', label: '.fullschema (DDL + sqlite_stat tables)'},
                {value: 'tables', label: '.tables (User relations)'},
                {value: 'indexes', label: '.indexes (Declared indexes)'},
                {value: 'vfsinfo', label: '.vfsinfo (Active VFS stack)'},
              ]}
            />
            <TextField
              label={gettext('Optional Table Pattern (.schema / .tables / .indexes)')}
              value={pattern}
              onChange={(e) => setPattern(textVal(e))}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy} onClick={handleRunCommand}>
              {gettext('Execute Read-Only Dot-Command')}
            </Button>
          </Stack>
          {result && (
            <pre style={{margin: 0, maxHeight: 320, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {result.output}
            </pre>
          )}
        </SqliteSectionCard>
      </Stack>
    </Box>
  );
}

SqliteShellWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  api: PropTypes.object,
};
