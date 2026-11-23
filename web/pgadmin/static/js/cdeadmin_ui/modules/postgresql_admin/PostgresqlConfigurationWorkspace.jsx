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
import UnifiedDataGrid from '../../data/UnifiedDataGrid';
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
  const [selectedJobDetail, setSelectedJobDetail] = useState(null);
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

  const handleInspectStatus = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const detail = await callServer({
        action: 'postgresql_config_status',
        request: {job_id: jobId},
      });
      setSelectedJobDetail(detail);
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
        request: {job_id: jobId, confirmed: true},
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
        title={gettext('Cluster Configuration, HBA/Ident & TLS Certificate Deployment')}
        actions={<FormReference reference="SR-F-030451" />}
      >
        <Stack gap="sm">
          <Banner status="info">
            {gettext(
              'Deploys validated configuration and 0600 TLS files to operator-granted cluster roots with automatic backup restoration if pg_file_settings or pg_hba_file_rules reports syntax errors.'
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
              label={gettext('Configuration / TLS File')}
              value={fileKind}
              options={FILE_KINDS}
              onChange={setFileKind}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="secondary" disabled={busy} onClick={handleInspectFile}>
              {gettext('Inspect Current File')}
            </Button>
            <Checkbox
              label={gettext('Reload PostgreSQL configuration after deployment (pg_reload_conf)')}
              checked={reloadAfter}
              onChange={setReloadAfter}
            />
          </Stack>
          {inspectedFile && (
            <Box>
              <Badge status={inspectedFile.redacted ? 'warning' : 'info'} label={inspectedFile.file_kind} />{' '}
              <span>SHA-256: {inspectedFile.sha256 || 'absent'}</span>
            </Box>
          )}
          <TextArea
            label={gettext('Replacement File Content')}
            rows={8}
            value={replacementText}
            onChange={(e) => setReplacementText(e?.target ? e.target.value : e)}
          />
          <Button variant="primary" disabled={busy || !replacementText.trim()} onClick={handleReviewDeploy}>
            {gettext('Review Configuration Deployment')}
          </Button>
        </Stack>
      </PostgresqlSectionCard>

      {reviewedDeploy && (
        <PostgresqlSectionCard title={gettext('Reviewed Configuration Deployment')}>
          <Stack gap="sm">
            <Box>
              <span>{gettext('Review Digest:')} {reviewedDeploy.review_digest}</span>
            </Box>
            <Checkbox
              label={gettext('Confirm atomic file replacement & live validation')}
              checked={deployConfirmed}
              onChange={setDeployConfirmed}
            />
            <Button variant="primary" disabled={busy || !deployConfirmed} onClick={handleStartDeploy}>
              {gettext('Deploy & Validate Now')}
            </Button>
          </Stack>
        </PostgresqlSectionCard>
      )}

      {deployments.length > 0 && (
        <PostgresqlSectionCard title={gettext('Deployment History, Status & Rollback')}>
          <Stack gap="sm">
            <UnifiedDataGrid
              caption={gettext('Configuration Deployment Jobs')}
              searchable
              exportable
              minHeight={140}
              maxHeight={280}
              rows={deployments}
              rowKeyGetter={(job) => job.job_id}
              columns={[
                {name: 'job_id', label: gettext('Job ID'), width: 170, mono: true},
                {
                  name: 'file_kind',
                  label: gettext('File'),
                  width: 150,
                  render: (_val, job) => <Badge status="info" label={job.file_kind} />,
                },
                {name: 'state', label: gettext('State'), width: 120},
                {
                  name: 'actions',
                  label: gettext('Actions'),
                  width: 280,
                  render: (_val, job) => (
                    <Stack direction="row" gap="sm">
                      <Button variant="secondary" disabled={busy} onClick={() => handleInspectStatus(job.job_id)}>
                        {gettext('Inspect Status')}
                      </Button>
                      {job.state === 'completed' && (
                        <Button variant="secondary" disabled={busy} onClick={() => handleRollback(job.job_id)}>
                          {gettext('Rollback Prior File')}
                        </Button>
                      )}
                    </Stack>
                  ),
                },
              ]}
            />
            {selectedJobDetail && (
              <CodeEditor
                value={JSON.stringify(selectedJobDetail, null, 2)}
                language="json"
                readOnly
                height="180px"
              />
            )}
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
