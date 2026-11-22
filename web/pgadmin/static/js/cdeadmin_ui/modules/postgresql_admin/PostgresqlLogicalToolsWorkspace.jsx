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
import {TextArea, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {PostgresqlSectionCard, createPostgresqlServerCaller} from './postgresqlAdminHelpers';

/**
 * PG-UI-12 (SR-F-030542): Native cdeadmin_ui Logical pg_dump / pg_restore,
 * COPY CSV/Text Import-Export, Catalog Object Search & Bulk Grant Wizard Workspace.
 */
export default function PostgresqlLogicalToolsWorkspace({
  endpointUrl,
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callServer = useMemo(
    () => createPostgresqlServerCaller(api, endpointUrl),
    [api, endpointUrl]
  );

  // Logical pg_dump / pg_restore state
  const [backupCatalog, setBackupCatalog] = useState(null);
  const [logicalTask, setLogicalTask] = useState('backup');
  const [archiveFilename, setArchiveFilename] = useState('database_backup.dump');
  const [archiveFormat, setArchiveFormat] = useState('custom');
  const [schemaOnly, setSchemaOnly] = useState(false);
  const [dataOnly, setDataOnly] = useState(false);
  const [cleanDrop, setCleanDrop] = useState(false);
  const [reviewedLogical, setReviewedLogical] = useState(null);
  const [confirmLogical, setConfirmLogical] = useState(false);

  // COPY stream export / import state
  const [copySchema, setCopySchema] = useState('public');
  const [copyTable, setCopyTable] = useState('');
  const [copyData, setCopyData] = useState('');
  const [copyHeader, setCopyHeader] = useState(true);
  const [reviewedCopy, setReviewedCopy] = useState(null);
  const [confirmCopy, setConfirmCopy] = useState(false);

  // Catalog search & Bulk Grant state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [grantMode, setGrantMode] = useState('GRANT');
  const [grantee, setGrantee] = useState('');
  const [grantTargets, setGrantTargets] = useState('');
  const [grantPriv, setGrantPriv] = useState('SELECT');
  const [reviewedGrant, setReviewedGrant] = useState(null);
  const [confirmGrant, setConfirmGrant] = useState(false);

  const [lastOutput, setLastOutput] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadBackupCatalog = useCallback(async () => {
    try {
      const cat = await callServer({action: 'postgresql_ops_logical_backup_catalog', request: {}});
      setBackupCatalog(cat);
    } catch {
      // Host backup directory optional until used
    }
  }, [callServer]);

  useEffect(() => {
    loadBackupCatalog();
  }, [loadBackupCatalog]);

  const handleReviewLogical = async () => {
    setBusy(true);
    setError('');
    try {
      const rev = await callServer({
        action: 'postgresql_ops_logical_backup_review',
        request: {
          task: logicalTask,
          filename: archiveFilename.trim(),
          format: archiveFormat,
          schema_only: schemaOnly,
          data_only: dataOnly,
          clean: cleanDrop,
        },
      });
      setReviewedLogical(rev);
      setConfirmLogical(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartLogical = async () => {
    if (!reviewedLogical || !confirmLogical) return;
    setBusy(true);
    setError('');
    try {
      const done = await callServer({
        action: 'postgresql_ops_logical_backup_start',
        request: {
          job_id: reviewedLogical.job_id,
          review_digest: reviewedLogical.review_digest,
          confirmed: true,
        },
      });
      setLastOutput(done);
      setReviewedLogical(null);
      await loadBackupCatalog();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleCopyExport = async () => {
    if (!copyTable.trim()) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_ops_copy_export',
        request: {schema: copySchema.trim() || 'public', table: copyTable.trim(), format: 'csv', header: copyHeader},
      });
      setCopyData(res.data || '');
      setLastOutput(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewCopyImport = async () => {
    if (!copyTable.trim() || !copyData.trim()) return;
    setBusy(true);
    setError('');
    try {
      const rev = await callServer({
        action: 'postgresql_ops_copy_import_review',
        request: {
          schema: copySchema.trim() || 'public',
          table: copyTable.trim(),
          header: copyHeader,
          data: copyData,
        },
      });
      setReviewedCopy(rev);
      setConfirmCopy(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartCopyImport = async () => {
    if (!reviewedCopy || !confirmCopy) return;
    setBusy(true);
    setError('');
    try {
      const done = await callServer({
        action: 'postgresql_ops_copy_import_start',
        request: {
          job_id: reviewedCopy.job_id,
          review_digest: reviewedCopy.review_digest,
          confirmed: true,
        },
      });
      setReviewedCopy(null);
      setLastOutput(done);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleSearchCatalog = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_ops_catalog_search',
        request: {query: searchQuery.trim()},
      });
      setSearchResults(res?.results || []);
      setLastOutput(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewBulkGrant = async () => {
    const targets = grantTargets.split(',').map((s) => s.trim()).filter(Boolean);
    if (!grantee.trim() || !targets.length) return;
    setBusy(true);
    setError('');
    try {
      const rev = await callServer({
        action: 'postgresql_ops_bulk_grant_review',
        request: {
          mode: grantMode,
          grantee: grantee.trim(),
          object_kind: 'TABLE',
          privileges: [grantPriv],
          targets,
        },
      });
      setReviewedGrant(rev);
      setConfirmGrant(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartBulkGrant = async () => {
    if (!reviewedGrant || !confirmGrant) return;
    setBusy(true);
    setError('');
    try {
      const done = await callServer({
        action: 'postgresql_ops_bulk_grant_start',
        request: {
          job_id: reviewedGrant.job_id,
          review_digest: reviewedGrant.review_digest,
          confirmed: true,
        },
      });
      setReviewedGrant(null);
      setLastOutput(done);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack gap="md">
      <PostgresqlSectionCard
        title={gettext('Supervised Logical Backup (pg_dump) & Restore (pg_restore)')}
        actions={<FormReference reference="SR-F-030542" />}
      >
        <Stack gap="sm">
          <Banner status="info">
            {gettext(
              'Provides native cdeadmin_ui logical pg_dump / pg_restore archives, streaming COPY CSV import/export, fast catalog search, and reviewed bulk privilege grants.'
            )}
          </Banner>
          {error && <ValidationMessage status="error">{error}</ValidationMessage>}
          {backupCatalog && (
            <Box>
              <Badge status="info" label={`${(backupCatalog.archives || []).length} ${gettext('Archives')}`} />{' '}
              <span>{backupCatalog.backup_dir}</span>
            </Box>
          )}
          <Grid columns={3} gap="sm">
            <Select
              label={gettext('Logical Task')}
              value={logicalTask}
              options={[
                {value: 'backup', label: 'Logical Backup (pg_dump)'},
                {value: 'restore', label: 'Logical Restore (pg_restore / psql)'},
                {value: 'toc', label: 'Inspect Archive TOC (pg_restore --list)'},
              ]}
              onChange={setLogicalTask}
            />
            <TextField
              label={gettext('Archive Filename')}
              value={archiveFilename}
              onChange={(e) => setArchiveFilename(e?.target ? e.target.value : e)}
            />
            <Select
              label={gettext('Archive Format')}
              value={archiveFormat}
              options={[
                {value: 'custom', label: 'Custom (-Fc)'},
                {value: 'plain', label: 'Plain SQL (-Fp)'},
                {value: 'tar', label: 'Tar (-Ft)'},
              ]}
              onChange={setArchiveFormat}
            />
          </Grid>
          <Stack direction="row" gap="md">
            <Checkbox label={gettext('Schema only')} checked={schemaOnly} onChange={setSchemaOnly} />
            <Checkbox label={gettext('Data only')} checked={dataOnly} onChange={setDataOnly} />
            <Checkbox label={gettext('Clean (--clean --if-exists)')} checked={cleanDrop} onChange={setCleanDrop} />
          </Stack>
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy || !archiveFilename.trim()} onClick={handleReviewLogical}>
              {gettext('Review Logical Backup / Restore')}
            </Button>
            {reviewedLogical && (
              <>
                <Checkbox
                  label={gettext('Confirm logical archive execution')}
                  checked={confirmLogical}
                  onChange={setConfirmLogical}
                />
                <Button variant="primary" disabled={busy || !confirmLogical} onClick={handleStartLogical}>
                  {gettext('Start Logical Job')}
                </Button>
              </>
            )}
          </Stack>
        </Stack>
      </PostgresqlSectionCard>

      <PostgresqlSectionCard title={gettext('Native Streaming COPY CSV Import / Export')}>
        <Stack gap="sm">
          <Grid columns={3} gap="sm">
            <TextField
              label={gettext('Schema')}
              value={copySchema}
              onChange={(e) => setCopySchema(e?.target ? e.target.value : e)}
            />
            <TextField
              label={gettext('Table')}
              value={copyTable}
              onChange={(e) => setCopyTable(e?.target ? e.target.value : e)}
            />
            <Checkbox label={gettext('CSV Header Row')} checked={copyHeader} onChange={setCopyHeader} />
          </Grid>
          <TextArea
            label={gettext('CSV Payload (Exported or Staged for COPY FROM STDIN)')}
            rows={4}
            value={copyData}
            onChange={(e) => setCopyData(e?.target ? e.target.value : e)}
          />
          <Stack direction="row" gap="sm">
            <Button variant="secondary" disabled={busy || !copyTable.trim()} onClick={handleCopyExport}>
              {gettext('Export Table via COPY TO STDOUT')}
            </Button>
            <Button
              variant="primary"
              disabled={busy || !copyTable.trim() || !copyData.trim()}
              onClick={handleReviewCopyImport}
            >
              {gettext('Review COPY FROM STDIN Import')}
            </Button>
            {reviewedCopy && (
              <>
                <Checkbox label={gettext('Confirm atomic COPY import')} checked={confirmCopy} onChange={setConfirmCopy} />
                <Button variant="primary" disabled={busy || !confirmCopy} onClick={handleStartCopyImport}>
                  {gettext('Execute COPY Import')}
                </Button>
              </>
            )}
          </Stack>
        </Stack>
      </PostgresqlSectionCard>

      <PostgresqlSectionCard title={gettext('Catalog Object Search & Bulk Privilege Wizard')}>
        <Stack gap="sm">
          <Grid columns={2} gap="sm">
            <TextField
              label={gettext('Search Relations, Routines & Comments')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e?.target ? e.target.value : e)}
            />
            <Box>
              <Button variant="secondary" disabled={busy} onClick={handleSearchCatalog}>
                {gettext('Search Catalog Objects')}
              </Button>
            </Box>
          </Grid>
          {searchResults.length > 0 && (
            <Box>
              <Badge status="info" label={`${searchResults.length} ${gettext('Matches')}`} />
            </Box>
          )}
          <Grid columns={4} gap="sm">
            <Select
              label={gettext('Action')}
              value={grantMode}
              options={[
                {value: 'GRANT', label: 'GRANT'},
                {value: 'REVOKE', label: 'REVOKE'},
              ]}
              onChange={setGrantMode}
            />
            <TextField
              label={gettext('Role / Grantee')}
              value={grantee}
              onChange={(e) => setGrantee(e?.target ? e.target.value : e)}
            />
            <Select
              label={gettext('Privilege')}
              value={grantPriv}
              options={[
                {value: 'SELECT', label: 'SELECT'},
                {value: 'INSERT', label: 'INSERT'},
                {value: 'UPDATE', label: 'UPDATE'},
                {value: 'DELETE', label: 'DELETE'},
                {value: 'ALL', label: 'ALL PRIVILEGES'},
              ]}
              onChange={setGrantPriv}
            />
            <TextField
              label={gettext('Target Tables (schema.table, ...)')}
              value={grantTargets}
              onChange={(e) => setGrantTargets(e?.target ? e.target.value : e)}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button
              variant="primary"
              disabled={busy || !grantee.trim() || !grantTargets.trim()}
              onClick={handleReviewBulkGrant}
            >
              {gettext('Review Bulk Privilege SQL')}
            </Button>
            {reviewedGrant && (
              <>
                <Checkbox
                  label={gettext('Confirm atomic privilege batch')}
                  checked={confirmGrant}
                  onChange={setConfirmGrant}
                />
                <Button variant="primary" disabled={busy || !confirmGrant} onClick={handleStartBulkGrant}>
                  {gettext('Apply Bulk Privileges')}
                </Button>
              </>
            )}
          </Stack>
          {lastOutput && (
            <CodeEditor
              value={JSON.stringify(lastOutput, null, 2)}
              language="json"
              readOnly
              height="180px"
            />
          )}
        </Stack>
      </PostgresqlSectionCard>
    </Stack>
  );
}

PostgresqlLogicalToolsWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
