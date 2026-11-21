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
import {NumberField, TextField} from '../../primitives/Field';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import {
  MariaDBJobsTable,
  MariaDBReviewCard,
  MariaDBSectionCard,
  useMariaDBServerApi,
} from './mariadbAdminHelpers';

/**
 * MDB-UI-04 (SR-F-030343): MariaDB Server Upgrade Preflight, Clean Shutdown,
 * Binary Switchover, System-Table Upgrade & Rollback Workspace (`tab="mariadb-upgrade"`).
 */
export default function MariaDBUpgradeWorkspace({endpointUrl, api = null}) {
  const {callServer} = useMariaDBServerApi(endpointUrl, api);

  const [sourceInfo, setSourceInfo] = useState(null);
  const [preflightResult, setPreflightResult] = useState(null);
  const [review, setReview] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // Upgrade options
  const [datadir, setDatadir] = useState('/var/lib/mysql');
  const [targetMariadbdBinary, setTargetMariadbdBinary] = useState('mariadbd');
  const [targetUpgradeBinary, setTargetUpgradeBinary] = useState('mariadb-upgrade');
  const [targetVersionPrefix, setTargetVersionPrefix] = useState('12.2.2');
  const [targetPort, setTargetPort] = useState(3306);
  const [configFile, setConfigFile] = useState('');
  const [backupJobId, setBackupJobId] = useState('');
  const [verifiedBackupDir, setVerifiedBackupDir] = useState('');
  const [verifiedLogicalDumpPath, setVerifiedLogicalDumpPath] = useState('');

  const loadAll = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [src, jobRes] = await Promise.all([
        callServer({action: 'mariadb_upgrade_inspect_source', request: {}}).catch(() => null),
        callServer({action: 'mariadb_upgrade_list', request: {offset: 0, limit: 25}}).catch(() => ({jobs: []})),
      ]);
      if (src) {
        setSourceInfo(src);
        if (src.datadir) setDatadir(src.datadir);
      }
      setJobs(jobRes?.jobs || []);
    } catch (err) {
      setError(err.message || gettext('Failed to inspect MariaDB upgrade source.'));
    } finally {
      setBusy(false);
    }
  }, [callServer]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const buildOptions = () => {
    const opts = {
      datadir: datadir.trim(),
      target_mariadbd_binary: targetMariadbdBinary.trim() || 'mariadbd',
      target_upgrade_binary: targetUpgradeBinary.trim() || 'mariadb-upgrade',
      target_version_prefix: targetVersionPrefix.trim() || '12.2.2',
      target_port: Number(targetPort) || 3306,
    };
    if (configFile.trim()) opts.configuration_file = configFile.trim();
    if (backupJobId.trim()) opts.backup_job_id = backupJobId.trim();
    if (verifiedBackupDir.trim()) opts.verified_backup_dir = verifiedBackupDir.trim();
    if (verifiedLogicalDumpPath.trim()) opts.verified_logical_dump_path = verifiedLogicalDumpPath.trim();
    return opts;
  };

  const handlePreflight = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_upgrade_preflight',
        request: buildOptions(),
      });
      setPreflightResult(res);
      setNotice(gettext('MariaDB upgrade compatibility & backup prerequisite preflight passed.'));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleReview = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_upgrade_review',
        request: {options: buildOptions()},
      });
      setReview(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleStart = async (reviewed) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_upgrade_start',
        request: {
          job_id: reviewed.job_id,
          review_digest: reviewed.review_digest,
          confirmed: true,
        },
      });
      setReview(null);
      setSelectedJob(res);
      setNotice(gettext('Completed MariaDB server upgrade ') + res.job_id);
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleJobAction = async (actionName, jobId, successMsg) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: actionName,
        request: {job_id: jobId, confirmed: true},
      });
      setSelectedJob(res);
      setNotice(successMsg);
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box style={{padding: '12px', overflow: 'auto'}} data-testid="mariadb-upgrade-workspace">
      <Stack direction="column" gap={3}>
        <Stack direction="row" style={{flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between'}}>
          <Stack direction="row" gap={1} style={{alignItems: 'center'}}>
            <strong>{gettext('MariaDB Server Upgrade & Rollback')}</strong>
            <FormReference formKey="mariadb-upgrade-workspace" />
          </Stack>
          <Button size="sm" intent="neutral" disabled={busy} onClick={loadAll}>
            {gettext('Inspect Source Server')}
          </Button>
        </Stack>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}
        {notice && <Banner status="success">{notice}</Banner>}

        {sourceInfo && (
          <MariaDBSectionCard title={gettext('Live Source MariaDB Instance')}>
            <Stack direction="row" gap={2} style={{flexWrap: 'wrap', alignItems: 'center'}}>
              <Badge status="info" label={sourceInfo.version || 'MariaDB'} />
              {sourceInfo.server_uid && (
                <span>
                  <strong>{gettext('Server UID:')}</strong> <code>{sourceInfo.server_uid}</code>
                </span>
              )}
              {sourceInfo.datadir && (
                <span>
                  <strong>{gettext('Datadir:')}</strong> <code>{sourceInfo.datadir}</code>
                </span>
              )}
            </Stack>
          </MariaDBSectionCard>
        )}

        <MariaDBSectionCard title={gettext('Pre-Upgrade Compatibility & Backup Prerequisite Check')}>
          <Stack direction="column" gap={2}>
            <Banner status="info">
              {gettext(
                'Requires an admitted verified physical backup job, verified backup directory, or verified logical dump before stopping the source daemon cleanly (innodb_fast_shutdown=0) and running mariadb-upgrade.'
              )}
            </Banner>
            <Grid columns={3} gap={2}>
              <TextField
                label={gettext('Data Directory')}
                value={datadir}
                onChange={(e) => setDatadir(e.target.value)}
              />
              <TextField
                label={gettext('Target mariadbd Binary')}
                value={targetMariadbdBinary}
                onChange={(e) => setTargetMariadbdBinary(e.target.value)}
              />
              <TextField
                label={gettext('Target mariadb-upgrade Binary')}
                value={targetUpgradeBinary}
                onChange={(e) => setTargetUpgradeBinary(e.target.value)}
              />
              <TextField
                label={gettext('Target Version Prefix')}
                value={targetVersionPrefix}
                onChange={(e) => setTargetVersionPrefix(e.target.value)}
              />
              <NumberField
                label={gettext('Target TCP Port')}
                value={targetPort}
                min={1024}
                max={65535}
                onChange={(e) => setTargetPort(Number(e.target.value))}
              />
              <TextField
                label={gettext('Configuration File (.cnf, optional)')}
                value={configFile}
                onChange={(e) => setConfigFile(e.target.value)}
              />
              <TextField
                label={gettext('Verified Physical Backup Job ID (optional)')}
                value={backupJobId}
                onChange={(e) => setBackupJobId(e.target.value)}
              />
              <TextField
                label={gettext('Verified Backup Directory (optional)')}
                value={verifiedBackupDir}
                onChange={(e) => setVerifiedBackupDir(e.target.value)}
              />
              <TextField
                label={gettext('Verified Logical Dump Path (optional)')}
                value={verifiedLogicalDumpPath}
                onChange={(e) => setVerifiedLogicalDumpPath(e.target.value)}
              />
            </Grid>
            <Stack direction="row" gap={1}>
              <Button intent="neutral" disabled={busy || !datadir.trim()} onClick={handlePreflight}>
                {gettext('Run Preflight Check')}
              </Button>
              <Button intent="primary" disabled={busy || !datadir.trim()} onClick={handleReview}>
                {gettext('Review Server Upgrade')}
              </Button>
            </Stack>
            {preflightResult && (
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
                {JSON.stringify(preflightResult, null, 2)}
              </Box>
            )}
          </Stack>
        </MariaDBSectionCard>

        <MariaDBReviewCard
          title={gettext('MariaDB Server Upgrade Review')}
          review={review}
          busy={busy}
          confirmLabel={gettext('Confirm & Execute Upgrade')}
          onConfirm={handleStart}
          onClear={() => setReview(null)}
        />

        <MariaDBJobsTable
          title={gettext('MariaDB Upgrade Jobs')}
          jobs={jobs}
          busy={busy}
          selectedJob={selectedJob}
          onSelect={setSelectedJob}
          onRefreshJob={async (jid) => {
            const st = await callServer({action: 'mariadb_upgrade_status', request: {job_id: jid}});
            setSelectedJob(st);
            await loadAll();
          }}
          onReconcileJob={(jid) =>
            handleJobAction('mariadb_upgrade_reconcile', jid, gettext('Reconciled MariaDB upgrade job.'))
          }
          extraActions={(job) => (
            <>
              <Button
                size="sm"
                intent="neutral"
                disabled={busy}
                onClick={() =>
                  handleJobAction('mariadb_upgrade_stop_target', job.job_id, gettext('Stopped upgraded target daemon.'))
                }
              >
                {gettext('Stop Target')}
              </Button>
              {job.state !== 'rolled_back' && (
                <Button
                  size="sm"
                  intent="destructive"
                  disabled={busy}
                  onClick={() =>
                    handleJobAction('mariadb_upgrade_rollback', job.job_id, gettext('Rolled back MariaDB upgrade datadir snapshot.'))
                  }
                >
                  {gettext('Rollback')}
                </Button>
              )}
            </>
          )}
        />
      </Stack>
    </Box>
  );
}

MariaDBUpgradeWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
