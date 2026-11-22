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
import {Checkbox} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {SqliteSectionCard, createSqliteWorkspaceCaller} from './sqliteAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

/**
 * SQ-AUD-15 (SR-F-030565): Database-Wide Native SQL Script Exchange (`.dump` & Reviewed Import).
 */
export default function SqliteSqlDumpWorkspace({
  endpointUrl,
  databaseTargetId = '',
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callSqlite = useMemo(
    () => createSqliteWorkspaceCaller(api, endpointUrl, databaseTargetId),
    [api, endpointUrl, databaseTargetId]
  );

  const [dataOnly, setDataOnly] = useState(false);
  const [preserveNewlines, setPreserveNewlines] = useState(true);
  const [excludeSystem, setExcludeSystem] = useState(false);
  const [tablesFilter, setTablesFilter] = useState('');
  const [lastDump, setLastDump] = useState(null);
  const [dumpHistory, setDumpHistory] = useState([]);

  const [importSql, setImportSql] = useState('');
  const [editorRevision, setEditorRevision] = useState(0);
  const importSqlRef = useRef('');
  const [reviewedImport, setReviewedImport] = useState(null);
  const [confirmImport, setConfirmImport] = useState(false);
  const [importOutcome, setImportOutcome] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadHistory = useCallback(async () => {
    try {
      const res = await callSqlite({action: 'sqlite_ops_dump_list'});
      setDumpHistory(res?.dumps || []);
    } catch {
      // Optional initial load
    }
  }, [callSqlite]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleExportDump = async () => {
    setBusy(true);
    setError('');
    try {
      const req = {
        data_only: dataOnly,
        preserve_newlines: preserveNewlines,
        exclude_system: excludeSystem,
      };
      const tbls = tablesFilter.split(',').map((t) => t.trim()).filter(Boolean);
      if (tbls.length) {
        req.tables = tbls;
      }
      const res = await callSqlite({action: 'sqlite_ops_dump_export', request: req});
      const preview = res.script_preview || '';
      importSqlRef.current = preview;
      setLastDump(res);
      setImportSql(preview);
      setEditorRevision((rev) => rev + 1);
      await loadHistory();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewImport = async () => {
    setBusy(true);
    setError('');
    try {
      const rev = await callSqlite({
        action: 'sqlite_ops_dump_import_review',
        request: {sql_text: importSql},
      });
      setReviewedImport(rev);
      setConfirmImport(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyImport = async () => {
    if (!reviewedImport || !confirmImport) return;
    setBusy(true);
    setError('');
    try {
      const out = await callSqlite({
        action: 'sqlite_ops_dump_import_apply',
        request: {
          review_id: reviewedImport.review_id,
          review_digest: reviewedImport.review_digest,
          confirmed: true,
        },
      });
      setImportOutcome(out);
      setReviewedImport(null);
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
          <strong>{gettext('SQLite Database-Wide Native SQL Script Exchange')}</strong>
          <FormReference reference="SR-F-030565" />
        </Stack>

        <Banner status="info">
          {gettext('Exports complete database or table-subset DDL + INSERT scripts via the provenance-matched sqlite3 .dump CLI, and applies reviewed SQL scripts inside an atomic transaction with independent read-back verification.')}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <SqliteSectionCard title={gettext('Native .dump SQL Script Export')}>
          <Grid columns={3} gap="sm">
            <Checkbox
              label={gettext('Data only (--data-only)')}
              checked={dataOnly}
              onChange={setDataOnly}
            />
            <Checkbox
              label={gettext('Preserve literal newlines (--newlines)')}
              checked={preserveNewlines}
              onChange={setPreserveNewlines}
            />
            <Checkbox
              label={gettext('Exclude system tables (--nosys)')}
              checked={excludeSystem}
              onChange={setExcludeSystem}
            />
          </Grid>
          <TextField
            label={gettext('Optional Comma-Separated Table Filter')}
            value={tablesFilter}
            onChange={(e) => setTablesFilter(textVal(e))}
          />
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy} onClick={handleExportDump}>
              {gettext('Generate Native SQL Dump')}
            </Button>
          </Stack>
          {lastDump && (
            <Stack direction="row" gap="sm">
              <Badge status="info" label={`${lastDump.byte_length} bytes`} />
              <Badge status="info" label={`SHA-256: ${String(lastDump.sha256 || '').slice(0, 16)}…`} />
              {lastDump.fidelity?.contains_blob_values && <Badge status="info" label={gettext('Hex BLOBs')} />}
            </Stack>
          )}
          {dumpHistory.length > 0 && (
            <div>{gettext('Saved Private Dump Artifacts')}: <strong>{dumpHistory.length}</strong></div>
          )}
        </SqliteSectionCard>

        <SqliteSectionCard title={gettext('Reviewed Atomic SQL Script Import')}>
          <CodeEditor
            key={`dump-import-editor-${editorRevision}`}
            language="sql"
            value={importSql}
            onChange={(val) => {
              if (val !== importSqlRef.current) {
                importSqlRef.current = val;
                setImportSql(val);
              }
            }}
            minHeight={140}
          />
          <Stack direction="row" gap="sm">
            <Button disabled={busy || !importSql.trim()} onClick={handleReviewImport}>
              {gettext('Review SQL Script Import')}
            </Button>
          </Stack>
          {reviewedImport && (
            <Stack gap="sm">
              <div>
                {gettext('Reviewed Statements')}: <strong>{reviewedImport.payload?.statement_count}</strong>
              </div>
              <Checkbox
                label={gettext('Confirm atomic SQLite script execution')}
                checked={confirmImport}
                onChange={setConfirmImport}
              />
              <Button variant="primary" disabled={busy || !confirmImport} onClick={handleApplyImport}>
                {gettext('Apply Reviewed SQL Script')}
              </Button>
            </Stack>
          )}
          {importOutcome && (
            <Badge
              status="success"
              label={`${gettext('Committed')} (${importOutcome.outcome?.executed_statements} ${gettext('statements verified')})`}
            />
          )}
        </SqliteSectionCard>
      </Stack>
    </Box>
  );
}

SqliteSqlDumpWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  api: PropTypes.object,
};
