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
import {NumberField, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {PostgresqlSectionCard, createPostgresqlServerCaller} from './postgresqlAdminHelpers';

/**
 * PG-UI-05 (SR-F-030454): Exported Snapshot Consumers, Output-Plugin Discovery,
 * Runtime Capabilities & Coordinated Destination Load/Cutover Workspace.
 */
export default function PostgresqlSnapshotCopyWorkspace({
  endpointUrl,
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callServer = useMemo(
    () => createPostgresqlServerCaller(api, endpointUrl),
    [api, endpointUrl]
  );

  const [runtimeCaps, setRuntimeCaps] = useState(null);
  const [outputPlugins, setOutputPlugins] = useState(null);
  const [snapshotName, setSnapshotName] = useState('');
  const [exporterPid, setExporterPid] = useState(0);
  const [databaseName, setDatabaseName] = useState('postgres');
  const [reviewedConsumer, setReviewedConsumer] = useState(null);
  const [openConsumer, setOpenConsumer] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const [sourceSchema, setSourceSchema] = useState('public');
  const [sourceTable, setSourceTable] = useState('');
  const [cutoverMode, setCutoverMode] = useState('atomic_swap');
  const [lastPayload, setLastPayload] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadDiscovery = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [caps, plugins] = await Promise.all([
        callServer({action: 'postgresql_runtime_capabilities', request: {}}),
        callServer({action: 'postgresql_snapshot_output_plugins', request: {}}),
      ]);
      setRuntimeCaps(caps);
      setOutputPlugins(plugins);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [callServer]);

  useEffect(() => {
    loadDiscovery();
  }, [loadDiscovery]);

  const handleReviewConsumer = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_snapshot_consumer_review',
        request: {
          snapshot_name: snapshotName.trim(),
          exporter_backend_pid: Number(exporterPid),
          database: databaseName.trim() || 'postgres',
          max_lifetime_seconds: 120,
        },
      });
      setReviewedConsumer(res);
      setConfirmOpen(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartConsumer = async () => {
    if (!reviewedConsumer || !confirmOpen) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_snapshot_consumer_start',
        request: {
          consumer_id: reviewedConsumer.consumer_id,
          review_digest: reviewedConsumer.review_digest,
          confirmed: true,
        },
      });
      setOpenConsumer(res);
      setReviewedConsumer(null);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleCoordinatedLoad = async () => {
    if (!openConsumer || !sourceTable.trim()) return;
    setBusy(true);
    setError('');
    try {
      const rev = await callServer({
        action: 'postgresql_snapshot_load_review',
        request: {
          consumer_id: openConsumer.consumer_id,
          source_schema: sourceSchema.trim() || 'public',
          source_table: sourceTable.trim(),
          destination_database: databaseName.trim() || 'postgres',
          destination_schema: sourceSchema.trim() || 'public',
          destination_table: sourceTable.trim(),
          cutover_mode: cutoverMode,
        },
      });
      const done = await callServer({
        action: 'postgresql_snapshot_load_start',
        request: {
          load_id: rev.load_id,
          review_digest: rev.review_digest,
          confirmed: true,
        },
      });
      setLastPayload(done);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack gap="md">
      <PostgresqlSectionCard
        title={gettext('Runtime Capabilities, Output Plugins & Snapshot Consumers')}
        actions={<FormReference reference="SR-F-030454" />}
      >
        <Stack gap="sm">
          <Banner status="info">
            {gettext(
              'Discovers installed extensions, encodings and logical decoding output plugins, and opens ordinary-SQL or cross-registration REPEATABLE READ snapshot consumers.'
            )}
          </Banner>
          {error && <ValidationMessage status="error">{error}</ValidationMessage>}
          {runtimeCaps && (
            <Box>
              <Badge status="success" label={runtimeCaps.encoding?.server_encoding} />{' '}
              <span>
                {gettext('Version:')} {runtimeCaps.version_capabilities?.public_version} | {gettext('Installed Extensions:')} {(runtimeCaps.installed_extensions || []).length} | {gettext('Output Plugins:')} {(outputPlugins?.plugins || []).filter((p) => p.installed).map((p) => p.plugin).join(', ')}
              </span>
            </Box>
          )}
          <Grid columns={3} gap="sm">
            <TextField
              label={gettext('Exported Snapshot Name')}
              value={snapshotName}
              onChange={(e) => setSnapshotName(e?.target ? e.target.value : e)}
            />
            <NumberField
              label={gettext('Exporter Backend PID')}
              value={exporterPid}
              min={1}
              onChange={(v) => setExporterPid(Number(v) || 0)}
            />
            <TextField
              label={gettext('Database')}
              value={databaseName}
              onChange={(e) => setDatabaseName(e?.target ? e.target.value : e)}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy || !snapshotName.trim()} onClick={handleReviewConsumer}>
              {gettext('Review SQL Snapshot Consumer')}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={loadDiscovery}>
              {gettext('Refresh Capabilities & Plugins')}
            </Button>
          </Stack>
        </Stack>
      </PostgresqlSectionCard>

      {reviewedConsumer && (
        <PostgresqlSectionCard title={gettext('Reviewed Snapshot Consumer')}>
          <Stack gap="sm">
            <Checkbox
              label={gettext('Confirm independent REPEATABLE READ READ ONLY snapshot import')}
              checked={confirmOpen}
              onChange={setConfirmOpen}
            />
            <Button variant="primary" disabled={busy || !confirmOpen} onClick={handleStartConsumer}>
              {gettext('Open Snapshot Consumer')}
            </Button>
          </Stack>
        </PostgresqlSectionCard>
      )}

      {openConsumer && (
        <PostgresqlSectionCard title={gettext('Coordinated Destination Table Load & Atomic Cutover')}>
          <Stack gap="sm">
            <Grid columns={3} gap="sm">
              <TextField
                label={gettext('Source Schema')}
                value={sourceSchema}
                onChange={(e) => setSourceSchema(e?.target ? e.target.value : e)}
              />
              <TextField
                label={gettext('Source Table')}
                value={sourceTable}
                onChange={(e) => setSourceTable(e?.target ? e.target.value : e)}
              />
              <Select
                label={gettext('Cutover Mode')}
                value={cutoverMode}
                options={[
                  {value: 'atomic_swap', label: 'Atomic table swap under ACCESS EXCLUSIVE lock'},
                  {value: 'stage_only', label: 'Load staging table only'},
                ]}
                onChange={setCutoverMode}
              />
            </Grid>
            <Button variant="primary" disabled={busy || !sourceTable.trim()} onClick={handleCoordinatedLoad}>
              {gettext('Run Coordinated Snapshot Load')}
            </Button>
          </Stack>
        </PostgresqlSectionCard>
      )}

      {(lastPayload || runtimeCaps) && (
        <PostgresqlSectionCard title={gettext('Capability & Snapshot Execution Details')}>
          <CodeEditor
            value={JSON.stringify(lastPayload || {runtime_capabilities: runtimeCaps, output_plugins: outputPlugins}, null, 2)}
            language="json"
            readOnly
            height="200px"
          />
        </PostgresqlSectionCard>
      )}
    </Stack>
  );
}

PostgresqlSnapshotCopyWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
