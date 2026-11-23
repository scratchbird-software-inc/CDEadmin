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
import {Checkbox} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {DuckdbSectionCard, createDuckdbWorkspaceCaller} from './duckdbAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

/**
 * DU-AUD-19 (SR-F-030590): DuckDB Single-Stream Logical SQL Dump & Atomic Reload.
 */
export default function DuckdbSqlDumpWorkspace({
  endpointUrl,
  databaseTargetId = '',
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callDuckdb = useMemo(
    () => createDuckdbWorkspaceCaller(api, endpointUrl, databaseTargetId),
    [api, endpointUrl, databaseTargetId]
  );

  const [dumpPath, setDumpPath] = useState('dumps/logical_dump.sql');
  const [includeData, setIncludeData] = useState(true);
  const [exportReceipt, setExportReceipt] = useState(null);
  const [dumpList, setDumpList] = useState([]);
  const [dumpPreview, setDumpPreview] = useState('');
  const [reloadTargetPath, setReloadTargetPath] = useState('restores/reloaded.duckdb');
  const [reloadReview, setReloadReview] = useState(null);
  const [confirmReload, setConfirmReload] = useState(false);
  const [reloadOutcome, setReloadOutcome] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refreshDumps = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({action: 'duckdb_ops_dump_list'});
      setDumpList(res?.dumps || res?.items || []);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [callDuckdb]);

  useEffect(() => {
    refreshDumps();
  }, [refreshDumps]);

  const handleExport = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_dump_export',
        request: {
          output_path: dumpPath,
          include_data: Boolean(includeData),
        },
      });
      setExportReceipt(res);
      await refreshDumps();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReadDump = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_dump_read',
        request: {dump_path: dumpPath},
      });
      setDumpPreview(res?.content || res?.preview || '');
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewReload = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_dump_reload_review',
        request: {
          dump_path: dumpPath,
          target_path: reloadTargetPath,
        },
      });
      setReloadReview(res);
      setConfirmReload(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyReload = async () => {
    if (!reloadReview?.review_id || !confirmReload) return;
    setBusy(true);
    setError('');
    try {
      const res = await callDuckdb({
        action: 'duckdb_ops_dump_reload_apply',
        request: {
          review_id: reloadReview.review_id,
          review_digest: reloadReview.review_digest,
          confirmed: true,
        },
      });
      setReloadOutcome(res);
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
            <strong>{gettext('DuckDB Single-Stream Logical SQL Dump & Transactional Reload')}</strong>
            <Badge status="info" label={`Saved dumps: ${dumpList.length}`} />
          </Stack>
          <FormReference reference="SR-F-030590" />
        </Stack>

        <Banner status="info">
          {gettext(
            'Exports schemas, sequences, ENUM/alias types, FK-ordered tables, lossless Arrow-encoded literals (BLOB hex, HUGEINT, DECIMAL, UNION/STRUCT/LIST/MAP, CR/LF/NUL), views, full-signature macros with defaults, indexes and comments into one self-contained .sql file, and reloads atomically inside one transaction while blocking external/secret statements.'
          )}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <DuckdbSectionCard
          title={gettext('1. Export & Inspect Single-Stream Logical SQL Dump')}
          actions={
            <Stack direction="row" gap="sm">
              <Button variant="primary" disabled={busy} onClick={handleExport}>
                {gettext('Export SQL Dump')}
              </Button>
              <Button variant="secondary" disabled={busy} onClick={handleReadDump}>
                {gettext('Preview Dump File')}
              </Button>
            </Stack>
          }
        >
          <Grid columns={2} gap="sm">
            <TextField
              label={gettext('Dump File Path (below registered root)')}
              value={dumpPath}
              onChange={(e) => setDumpPath(textVal(e))}
            />
            <Box style={{display: 'flex', alignItems: 'flex-end'}}>
              <Checkbox
                label={gettext('Include table row data (FK & hierarchical self-FK ordered)')}
                checked={includeData}
                onChange={setIncludeData}
              />
            </Box>
          </Grid>
          {exportReceipt && (
            <Badge status="success" label={`SHA-256: ${exportReceipt.sha256 || ''}`} />
          )}
          {dumpPreview && (
            <CodeEditor value={dumpPreview} language="sql" readOnly minHeight={160} />
          )}
        </DuckdbSectionCard>

        <DuckdbSectionCard
          title={gettext('2. Reviewed Atomic Single-Transaction Reload')}
          actions={
            <Button variant="secondary" disabled={busy} onClick={handleReviewReload}>
              {gettext('Review Reload Plan')}
            </Button>
          }
        >
          <TextField
            label={gettext('Destination Database File Path')}
            value={reloadTargetPath}
            onChange={(e) => setReloadTargetPath(textVal(e))}
          />
          {reloadReview && (
            <Stack gap="sm">
              <Badge status="info" label={`Statements verified: ${reloadReview.statement_count ?? 0}`} />
              <Checkbox
                label={gettext('Confirm atomic single-transaction SQL reload')}
                checked={confirmReload}
                onChange={setConfirmReload}
              />
              <Button
                variant="primary"
                disabled={busy || !confirmReload}
                onClick={handleApplyReload}
              >
                {gettext('Apply Atomic Reload')}
              </Button>
            </Stack>
          )}
          {reloadOutcome && (
            <pre style={{margin: 0, maxHeight: 140, overflow: 'auto', whiteSpace: 'pre-wrap'}}>
              {JSON.stringify(reloadOutcome, null, 2)}
            </pre>
          )}
        </DuckdbSectionCard>
      </Stack>
    </Box>
  );
}

DuckdbSqlDumpWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  api: PropTypes.object,
};
