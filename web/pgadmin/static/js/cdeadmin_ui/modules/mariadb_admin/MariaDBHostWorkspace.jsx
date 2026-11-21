/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Grid, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {NumberField, TextArea, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import {
  MariaDBJobsTable,
  MariaDBReviewCard,
  MariaDBSectionCard,
  useMariaDBServerApi,
} from './mariadbAdminHelpers';

const HOST_OPERATIONS = [
  {value: 'deploy_config', label: 'Validate & Deploy Option File (.cnf)'},
  {value: 'initialize_data', label: 'Initialize MariaDB Data Directory (mariadb-install-db)'},
  {value: 'service_start', label: 'Start MariaDB Daemon / Service'},
  {value: 'service_stop', label: 'Stop MariaDB Daemon / Service'},
  {value: 'service_restart', label: 'Restart MariaDB Daemon / Service'},
  {value: 'service_boot_policy', label: 'Configure Service Boot Policy (enable / disable)'},
];

/**
 * MDB-UI-03 (SR-F-030342): MariaDB Host Configuration, Datadir Initialization
 * & Daemon Service Lifecycle Workspace (`tab="mariadb-host"`).
 */
export default function MariaDBHostWorkspace({endpointUrl, api = null}) {
  const {callServer} = useMariaDBServerApi(endpointUrl, api);

  const [serviceStatus, setServiceStatus] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [configInspection, setConfigInspection] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [review, setReview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // Shared host settings
  const [operation, setOperation] = useState('deploy_config');
  const [serviceMode, setServiceMode] = useState('managed_daemon');
  const [systemdUnit, setSystemdUnit] = useState('mariadb.service');
  const [mariadbdBinary, setMariadbdBinary] = useState('mariadbd');
  const [installDbBinary, setInstallDbBinary] = useState('mariadb-install-db');
  const [configFile, setConfigFile] = useState('/etc/mysql/mariadb.conf.d/50-server.cnf');
  const [replacementText, setReplacementText] = useState('[mariadbd]\n');
  const [datadir, setDatadir] = useState('/var/lib/mysql');
  const [port, setPort] = useState(3306);
  const [bindAddress, setBindAddress] = useState('127.0.0.1');
  const [bootEnabled, setBootEnabled] = useState(true);

  const loadStatusAndJobs = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [svc, jobRes] = await Promise.all([
        callServer({
          action: 'mariadb_host_service_status',
          request: {service_mode: serviceMode, systemd_unit: systemdUnit},
        }).catch(() => null),
        callServer({action: 'mariadb_host_list', request: {offset: 0, limit: 25}}).catch(() => ({jobs: []})),
      ]);
      if (svc) setServiceStatus(svc);
      setJobs(jobRes?.jobs || []);
    } catch (err) {
      setError(err.message || gettext('Failed to load MariaDB host service state.'));
    } finally {
      setBusy(false);
    }
  }, [callServer, serviceMode, systemdUnit]);

  useEffect(() => {
    loadStatusAndJobs();
  }, [loadStatusAndJobs]);

  const handleInspectConfig = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_host_inspect_config',
        request: {configuration_file: configFile.trim()},
      });
      setConfigInspection(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleValidateConfig = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_host_validate_config',
        request: {
          configuration_file: configFile.trim(),
          mariadbd_binary: mariadbdBinary.trim() || 'mariadbd',
        },
      });
      setConfigInspection(res);
      setNotice(gettext('Option file validated natively against mariadbd.'));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleVerifyReadiness = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_host_verify_readiness',
        request: {port: Number(port) || 3306},
      });
      setReadiness(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleReviewOperation = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const options = {
        operation,
        mariadbd_binary: mariadbdBinary.trim() || 'mariadbd',
      };
      if (operation === 'deploy_config') {
        options.configuration_file = configFile.trim();
        options.replacement_text = replacementText;
      } else if (operation === 'initialize_data') {
        options.datadir = datadir.trim();
        options.install_db_binary = installDbBinary.trim() || 'mariadb-install-db';
      } else {
        options.service_mode = serviceMode;
        options.systemd_unit = systemdUnit.trim() || 'mariadb.service';
        options.datadir = datadir.trim();
        options.configuration_file = configFile.trim();
        options.port = Number(port) || 3306;
        options.bind_address = bindAddress.trim() || '127.0.0.1';
        if (operation === 'service_boot_policy') {
          options.enabled = Boolean(bootEnabled);
        }
      }
      const res = await callServer({
        action: 'mariadb_host_review',
        request: {options},
      });
      setReview(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleStartOperation = async (reviewed) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_host_start',
        request: {
          job_id: reviewed.job_id,
          review_digest: reviewed.review_digest,
          confirmed: true,
        },
      });
      setReview(null);
      setSelectedJob(res);
      setNotice(gettext('Executed MariaDB host operation ') + res.job_id);
      await loadStatusAndJobs();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRollbackConfig = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_host_rollback_config',
        request: {job_id: jobId, confirmed: true},
      });
      setSelectedJob(res);
      setNotice(gettext('Rolled back deployed MariaDB option file for job ') + jobId);
      await loadStatusAndJobs();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box style={{padding: '12px', overflow: 'auto'}} data-testid="mariadb-host-workspace">
      <Stack direction="column" gap={3}>
        <Stack direction="row" style={{flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between'}}>
          <Stack direction="row" gap={1} style={{alignItems: 'center'}}>
            <strong>{gettext('MariaDB Host Configuration & Daemon Service')}</strong>
            <FormReference formKey="mariadb-host-workspace" />
          </Stack>
          <Stack direction="row" gap={1}>
            <Button size="sm" intent="neutral" disabled={busy} onClick={handleVerifyReadiness}>
              {gettext('Verify SQL Readiness')}
            </Button>
            <Button size="sm" intent="neutral" disabled={busy} onClick={loadStatusAndJobs}>
              {gettext('Refresh Service Status')}
            </Button>
          </Stack>
        </Stack>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}
        {notice && <Banner status="success">{notice}</Banner>}

        {(serviceStatus || readiness) && (
          <MariaDBSectionCard title={gettext('Daemon Process & SQL Wire Readiness')}>
            <Stack direction="row" gap={2} style={{flexWrap: 'wrap', alignItems: 'center'}}>
              {serviceStatus && (
                <>
                  <Badge status={serviceStatus.running ? 'success' : 'neutral'} label={serviceStatus.running ? gettext('Daemon Running') : gettext('Daemon Stopped')} />
                  <span>
                    <strong>{gettext('Mode:')}</strong> <code>{serviceStatus.service_mode || serviceMode}</code>
                  </span>
                </>
              )}
              {readiness && (
                <Badge status={readiness.ready ? 'success' : 'warning'} label={readiness.ready ? gettext('SQL Wire Ready') : gettext('SQL Wire Unreachable')} />
              )}
            </Stack>
          </MariaDBSectionCard>
        )}

        <MariaDBSectionCard title={gettext('Inspect & Natively Validate Option File Graph')}>
          <Stack direction="column" gap={2}>
            <Grid columns={2} gap={2}>
              <TextField
                label={gettext('Option File Path (.cnf)')}
                value={configFile}
                onChange={(e) => setConfigFile(e.target.value)}
              />
              <TextField
                label={gettext('mariadbd Binary')}
                value={mariadbdBinary}
                onChange={(e) => setMariadbdBinary(e.target.value)}
              />
            </Grid>
            <Stack direction="row" gap={1}>
              <Button intent="neutral" disabled={busy || !configFile.trim()} onClick={handleInspectConfig}>
                {gettext('Inspect Include Graph')}
              </Button>
              <Button intent="neutral" disabled={busy || !configFile.trim()} onClick={handleValidateConfig}>
                {gettext('Validate Natively')}
              </Button>
            </Stack>
            {configInspection && (
              <Box
                style={{
                  maxHeight: 180,
                  overflow: 'auto',
                  padding: '8px',
                  border: '1px solid var(--cde-border-subtle, #d0d7de)',
                  fontFamily: 'monospace',
                  fontSize: '0.78rem',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {JSON.stringify(configInspection, null, 2)}
              </Box>
            )}
          </Stack>
        </MariaDBSectionCard>

        <MariaDBSectionCard title={gettext('Plan Host Configuration, Initialization or Service Action')}>
          <Stack direction="column" gap={2}>
            <Grid columns={3} gap={2}>
              <Select
                label={gettext('Host Operation')}
                value={operation}
                options={HOST_OPERATIONS}
                onChange={(val) => setOperation(val)}
              />
              <Select
                label={gettext('Service Supervisor Mode')}
                value={serviceMode}
                options={[
                  {value: 'managed_daemon', label: 'Managed mariadbd Daemon'},
                  {value: 'systemd', label: 'systemd Unit'},
                ]}
                onChange={(val) => setServiceMode(val)}
              />
              <TextField
                label={gettext('systemd Unit Name')}
                value={systemdUnit}
                onChange={(e) => setSystemdUnit(e.target.value)}
              />
              <TextField
                label={gettext('Data Directory')}
                value={datadir}
                onChange={(e) => setDatadir(e.target.value)}
              />
              <NumberField
                label={gettext('TCP Port')}
                value={port}
                min={1}
                max={65535}
                onChange={(e) => setPort(Number(e.target.value))}
              />
              <TextField
                label={gettext('Bind Address')}
                value={bindAddress}
                onChange={(e) => setBindAddress(e.target.value)}
              />
            </Grid>

            {operation === 'initialize_data' && (
              <TextField
                label={gettext('mariadb-install-db Binary')}
                value={installDbBinary}
                onChange={(e) => setInstallDbBinary(e.target.value)}
              />
            )}

            {operation === 'deploy_config' && (
              <TextArea
                label={gettext('Replacement Option File Content')}
                rows={6}
                value={replacementText}
                onChange={(e) => setReplacementText(e.target.value)}
              />
            )}

            {operation === 'service_boot_policy' && (
              <Checkbox
                label={gettext('Enable MariaDB service at host boot')}
                checked={bootEnabled}
                onChange={(checked) => setBootEnabled(Boolean(checked))}
              />
            )}

            <Stack direction="row" gap={1}>
              <Button intent="primary" disabled={busy} onClick={handleReviewOperation}>
                {gettext('Review Host Operation')}
              </Button>
            </Stack>
          </Stack>
        </MariaDBSectionCard>

        <MariaDBReviewCard
          title={gettext('MariaDB Host Operation Review')}
          review={review}
          busy={busy}
          onConfirm={handleStartOperation}
          onClear={() => setReview(null)}
        />

        <MariaDBJobsTable
          title={gettext('MariaDB Host & Service Jobs')}
          jobs={jobs}
          kindKey="host_operation"
          busy={busy}
          selectedJob={selectedJob}
          onSelect={setSelectedJob}
          onRefreshJob={async (jid) => {
            const st = await callServer({action: 'mariadb_host_status', request: {job_id: jid}});
            setSelectedJob(st);
            await loadStatusAndJobs();
          }}
          extraActions={(job) =>
            job.host_operation === 'deploy_config' && job.state === 'completed' ? (
              <Button
                size="sm"
                intent="destructive"
                disabled={busy}
                onClick={() => handleRollbackConfig(job.job_id)}
              >
                {gettext('Rollback Option File')}
              </Button>
            ) : null
          }
        />
      </Stack>
    </Box>
  );
}

MariaDBHostWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
