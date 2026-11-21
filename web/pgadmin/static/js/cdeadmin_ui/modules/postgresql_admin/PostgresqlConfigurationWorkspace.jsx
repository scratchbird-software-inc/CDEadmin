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

const FILE_KINDS = [
  {value: 'postgresql.conf', label: 'postgresql.conf — Main server parameters'},
  {value: 'pg_hba.conf', label: 'pg_hba.conf — Host-based authentication rules'},
  {value: 'pg_ident.conf', label: 'pg_ident.conf — User name maps'},
  {value: 'server.crt', label: 'server.crt — Server TLS certificate'},
  {value: 'server.key', label: 'server.key — Server TLS private key (0600, redacted on read)'},
  {value: 'root.crt', label: 'root.crt — Trusted TLS root CA bundle'},
];

/**
 * PG-UI-02 (SR-F-030451): PostgreSQL Configuration, HBA/Ident & TLS Deployment Workspace.
 */
export default function PostgresqlConfigurationWorkspace({
  endpointUrl,
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callServer = useMemo(
    () => createPostgresqlServerCaller(api, endpointUrl),
    [api, endpointUrl]
  );

  const [clusterId, setClusterId] = useState('main18');
  const [fileKind, setFileKind] = useState('postgresql.conf');
  const [inspectedFile, setInspectedFile] = useState(null);
  const [replacementText, setReplacementText] = useState('');
  const [reloadAfter, setReloadAfter] = useState(true);
  const [reviewedDeploy, setReviewedDeploy] = useState(null);
  const [deployConfirmed, setDeployConfirmed] = useState(false);
  const [deployments, setDeployments] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadList = useCallback(async () => {
    try {
      const res = await callServer({action: 'postgresql_config_list', request: {}});
      setDeployments(res?.jobs || []);
    } catch {
      // Non-fatal before cluster selection
    }
  }, [callServer]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const handleInspectFile = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_config_inspect_file',
        request: {cluster_id: clusterId.trim(), file_kind: fileKind},
      });
      setInspectedFile(res);
      setReplacementText(res?.redacted ? '' : String(res?.content || ''));
      setReviewedDeploy(null);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewDeploy = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_config_review_deploy',
        request: {
          cluster_id: clusterId.trim(),
          file_kind: fileKind,
          replacement_text: replacementText,
          reload_after: Boolean(reloadAfter),
        },
      });
      setReviewedDeploy(res);
      setDeployConfirmed(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartDeploy = async () => {
    if (!reviewedDeploy || !deployConfirmed) return;
    setBusy(true);
    setError('');
    try {
      await callServer({
        action: 'postgresql_config_start_deploy',
        request: {
          job_id: reviewedDeploy.job_id,
          review_digest: reviewedDeploy.review_digest,
          confirmed: true,
        },
      });
      setReviewedDeploy(null);
      await handleInspectFile();
      await loadList();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRollback = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      await callServer({
        action: 'postgresql_config_rollback',
        request: {job_id: jobId, confirmed: true, reload_after: true},
      });
      await handleInspectFile();
      await loadList();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack gap="md">
      <PostgresqlSectionCard
        title={gettext('Server Configuration, HBA Rules & TLS Material')}
        actions={<FormReference reference="SR-F-030451" />}
      >
        <Stack gap="sm">
          <Banner status="info">
            {gettext(
              'Validates postgresql.conf via native postgres -C before atomic backup-staged deployment, redacts 0600 private keys on read, and supports one-click rollback.'
            )}
          </Banner>
          {error && <ValidationMessage status="error">{error}</ValidationMessage>}
          <Grid columns={2} gap="sm">
            <TextField
              label={gettext('Granted Cluster ID')}
              value={clusterId}
              onChange={(e) => setClusterId(e?.target ? e.target.value : e)}
            />
            <Select
              label={gettext('Configuration or TLS File')}
              value={fileKind}
              options={FILE_KINDS}
              onChange={setFileKind}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="secondary" disabled={busy} onClick={handleInspectFile}>
              {gettext('Inspect File')}
            </Button>
            <Checkbox
              label={gettext('Reload server configuration after deploy (pg_ctl reload)')}
              checked={reloadAfter}
              onChange={setReloadAfter}
            />
          </Stack>
          {inspectedFile && (
            <Box>
              <Badge status={inspectedFile.redacted ? 'warning' : 'success'} label={inspectedFile.redacted ? gettext('Private Key Redacted') : gettext('SHA-256 Verified')} />{' '}
              <span>{inspectedFile.sha256 || gettext('No existing file')}</span>
            </Box>
          )}
          <TextArea
            label={gettext('Staged Replacement Content')}
            rows={10}
            value={replacementText}
            onChange={(e) => setReplacementText(e?.target ? e.target.value : e)}
          />
          <Button variant="primary" disabled={busy || !replacementText} onClick={handleReviewDeploy}>
            {gettext('Validate & Review Deployment')}
          </Button>
        </Stack>
      </PostgresqlSectionCard>

      {reviewedDeploy && (
        <PostgresqlSectionCard title={gettext('Validated Configuration Deployment Review')}>
          <Stack gap="sm">
            <CodeEditor
              value={JSON.stringify(reviewedDeploy.validation || reviewedDeploy, null, 2)}
              language="json"
              readOnly
              height="140px"
            />
            <Checkbox
              label={gettext('Confirm atomic backup-staged deployment')}
              checked={deployConfirmed}
              onChange={setDeployConfirmed}
            />
            <Button variant="primary" disabled={busy || !deployConfirmed} onClick={handleStartDeploy}>
              {gettext('Deploy Configuration')}
            </Button>
          </Stack>
        </PostgresqlSectionCard>
      )}

      {deployments.length > 0 && (
        <PostgresqlSectionCard title={gettext('Deployment Receipts & Rollback')}>
          <Stack gap="xs">
            {deployments.slice(0, 6).map((d) => (
              <Stack key={d.job_id} direction="row" gap="sm">
                <Badge status="info" label={d.file_kind} />
                <span>{d.state}</span>
                {d.state === 'completed' && (
                  <Button variant="secondary" disabled={busy} onClick={() => handleRollback(d.job_id)}>
                    {gettext('Rollback to Backup')}
                  </Button>
                )}
              </Stack>
            ))}
          </Stack>
        </PostgresqlSectionCard>
      )}
    </Stack>
  );
}

PostgresqlConfigurationWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
