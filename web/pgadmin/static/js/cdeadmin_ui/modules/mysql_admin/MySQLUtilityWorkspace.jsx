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
import {Box, Grid, Panel, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {NumberField, PasswordField, TextArea, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';

function stripQueryParams(url) {
  return String(url || '').split('?')[0];
}

/**
 * MYSQL-UI-01 (SR-F-030200): Supervised MySQL 9.7.0 Offline Storage & Benchmark
 * Host Utilities Workspace (`myisamchk`, `myisampack`, `innochecksum`, `ibd2sdi`, `mysqlslap`).
 * Uses 100% cdeadmin_ui primitives.
 */
export default function MySQLUtilityWorkspace({
  endpointUrl,
  databaseTargetId = null,
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const serverEndpointUrl = useMemo(() => stripQueryParams(endpointUrl), [endpointUrl]);

  const callServer = useCallback(
    async (payload) => {
      const response = await api.post(serverEndpointUrl, payload);
      const env = response?.data;
      if (env && env.success === 0) {
        throw new Error(env.errormsg || gettext('MySQL utility request failed.'));
      }
      return env?.data ?? env;
    },
    [api, serverEndpointUrl]
  );

  const [catalog, setCatalog] = useState([]);
  const [serverResource, setServerResource] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const [operationId, setOperationId] = useState('run_myisamchk');
  const [hostKind, setHostKind] = useState('local');
  const [workspacePath, setWorkspacePath] = useState('/tmp/scratchrobin-mysql-util');
  const [datadir, setDatadir] = useState('/var/lib/mysql');
  const [executablePath, setExecutablePath] = useState('');
  const [timeoutSeconds, setTimeoutSeconds] = useState(120);
  const [containerName, setContainerName] = useState('');
  const [dockerContext, setDockerContext] = useState('');
  const [sshHost, setSshHost] = useState('');
  const [sshPort, setSshPort] = useState(22);
  const [sshUsername, setSshUsername] = useState('');
  const [sshHostKey, setSshHostKey] = useState('');
  const [sshAuthMode, setSshAuthMode] = useState('password');
  const [sshPassword, setSshPassword] = useState('');
  const [sshPrivateKey, setSshPrivateKey] = useState('');

  // Utility-specific fields
  const [databaseName, setDatabaseName] = useState(databaseTargetId || '');
  const [tableName, setTableName] = useState('');
  const [myisamMode, setMyisamMode] = useState('check');
  const [includeInformation, setIncludeInformation] = useState(false);
  const [quick, setQuick] = useState(false);
  const [backup, setBackup] = useState(true);
  const [dryRunTest, setDryRunTest] = useState(true);
  const [forcePack, setForcePack] = useState(false);
  const [rebuildIndexes, setRebuildIndexes] = useState(true);
  const [tablespaceScope, setTablespaceScope] = useState('datadir_table');
  const [tablespaceRelpath, setTablespaceRelpath] = useState('');
  const [countOnly, setCountOnly] = useState(false);
  const [strictCheck, setStrictCheck] = useState('crc32');
  const [writeAlgorithm, setWriteAlgorithm] = useState('');
  const [pageTypeSummary, setPageTypeSummary] = useState(true);
  const [skipData, setSkipData] = useState(false);
  const [sdiId, setSdiId] = useState('');

  // mysqlslap fields
  const [benchmarkSchema, setBenchmarkSchema] = useState('cdeadmin_slap_scratch');
  const [concurrency, setConcurrency] = useState('4');
  const [iterations, setIterations] = useState(2);
  const [workloadMode, setWorkloadMode] = useState('auto_generate');
  const [autoLoadType, setAutoLoadType] = useState('mixed');
  const [createSql, setCreateSql] = useState('CREATE TABLE t1 (id INT PRIMARY KEY, v VARCHAR(64));');
  const [querySql, setQuerySql] = useState('SELECT COUNT(*) FROM t1;');
  const [isolatedScratchConfirmed, setIsolatedScratchConfirmed] = useState(false);

  const [destructiveConfirmed, setDestructiveConfirmed] = useState(false);
  const [serverConfirmation, setServerConfirmation] = useState('');
  const [asyncExecution, setAsyncExecution] = useState(false);
  const [reviewedJob, setReviewedJob] = useState(null);
  const [activeJob, setActiveJob] = useState(null);
  const [startConfirmed, setStartConfirmed] = useState(false);

  const loadWorkspace = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [catRes, pageRes, listRes] = await Promise.all([
        callServer({action: 'mysql_utility_catalog', request: {}}),
        callServer({action: 'resource_page', request: {}}).catch(() => null),
        callServer({action: 'mysql_utility_list', request: {offset: 0, limit: 25}}).catch(() => ({jobs: []})),
      ]);
      setCatalog(catRes?.utilities || []);
      const srv = (pageRes?.items || []).find((r) => r.resource_kind === 'server') || null;
      setServerResource(srv);
      setJobs(listRes?.jobs || []);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [callServer]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  const buildDraft = () => {
    const base = {
      execution_host_kind: hostKind,
      workspace: workspacePath.trim(),
      timeout_seconds: Number(timeoutSeconds) || 120,
      confirmation: serverConfirmation.trim(),
      ...(operationId !== 'run_mysqlslap' ? {datadir: datadir.trim()} : {}),
      ...(executablePath.trim() ? {executable_path: executablePath.trim()} : {}),
      ...(hostKind === 'container'
        ? {
          container_name: containerName.trim(),
          ...(dockerContext.trim() ? {docker_context: dockerContext.trim()} : {}),
        }
        : {}),
      ...(hostKind === 'ssh'
        ? {
          ssh_host: sshHost.trim(),
          ssh_port: Number(sshPort) || 22,
          ssh_username: sshUsername.trim(),
          ssh_host_key: sshHostKey.trim(),
          ssh_auth_mode: sshAuthMode,
          ...(sshAuthMode === 'password'
            ? {ssh_password: sshPassword}
            : {ssh_private_key: sshPrivateKey}),
        }
        : {}),
    };

    if (operationId === 'run_myisamchk') {
      return {
        ...base,
        database_name: databaseName.trim(),
        table_name: tableName.trim(),
        mode: myisamMode,
        include_information: includeInformation,
        quick,
        backup,
        destructive_confirmed: destructiveConfirmed,
      };
    }
    if (operationId === 'run_myisampack') {
      return {
        ...base,
        database_name: databaseName.trim(),
        table_name: tableName.trim(),
        dry_run_test: dryRunTest,
        backup,
        force: forcePack,
        rebuild_indexes: rebuildIndexes,
        destructive_confirmed: destructiveConfirmed,
      };
    }
    if (operationId === 'run_innochecksum') {
      return {
        ...base,
        tablespace_scope: tablespaceScope,
        ...(tablespaceScope === 'datadir_table'
          ? {database_name: databaseName.trim(), table_name: tableName.trim()}
          : {tablespace_relpath: tablespaceRelpath.trim()}),
        count_only: countOnly,
        strict_check: strictCheck,
        ...(writeAlgorithm ? {write_algorithm: writeAlgorithm} : {}),
        page_type_summary: pageTypeSummary,
        destructive_confirmed: destructiveConfirmed,
      };
    }
    if (operationId === 'run_ibd2sdi') {
      return {
        ...base,
        tablespace_scope: tablespaceScope,
        ...(tablespaceScope === 'datadir_table'
          ? {database_name: databaseName.trim(), table_name: tableName.trim()}
          : {tablespace_relpath: tablespaceRelpath.trim()}),
        skip_data: skipData,
        strict_check: strictCheck,
        ...(sdiId.trim() ? {sdi_id: sdiId.trim()} : {}),
      };
    }
    return {
      ...base,
      benchmark_schema: benchmarkSchema.trim(),
      concurrency: concurrency.trim(),
      iterations: Number(iterations) || 2,
      workload_mode: workloadMode,
      ...(workloadMode === 'auto_generate'
        ? {auto_load_type: autoLoadType}
        : {create_sql: createSql, query_sql: querySql}),
      isolated_scratch_confirmed: isolatedScratchConfirmed,
    };
  };

  const handleReview = async () => {
    setBusy(true);
    setError('');
    setReviewedJob(null);
    setStartConfirmed(false);
    try {
      const target = serverResource || {
        resource_kind: 'server',
        resource_id: 'server:mysql',
        display_name: serverConfirmation.trim(),
        native: {},
      };
      const res = await callServer({
        action: 'mysql_utility_review',
        request: {
          operation_id: operationId,
          target_resource: target,
          draft: buildDraft(),
        },
      });
      setReviewedJob(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStart = async () => {
    if (!reviewedJob || !startConfirmed) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mysql_utility_start',
        request: {
          job_id: reviewedJob.job_id,
          review_digest: reviewedJob.review_digest,
          confirmed: true,
          async_execution: asyncExecution,
        },
      });
      setActiveJob(res);
      setReviewedJob(null);
      const listRes = await callServer({action: 'mysql_utility_list', request: {offset: 0, limit: 25}}).catch(() => null);
      if (listRes?.jobs) setJobs(listRes.jobs);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handlePollJob = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({action: 'mysql_utility_status', request: {job_id: jobId}});
      setActiveJob(res);
      const listRes = await callServer({action: 'mysql_utility_list', request: {offset: 0, limit: 25}}).catch(() => null);
      if (listRes?.jobs) setJobs(listRes.jobs);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleCancelJob = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({action: 'mysql_utility_cancel', request: {job_id: jobId}});
      setActiveJob(res);
      const listRes = await callServer({action: 'mysql_utility_list', request: {offset: 0, limit: 25}}).catch(() => null);
      if (listRes?.jobs) setJobs(listRes.jobs);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const serverDisplayName = serverResource?.display_name || '';

  return (
    <Box sx={{p: 2, overflow: 'auto', height: '100%'}} data-cdeadmin-qa-key="mysql-admin.utilities">
      <Stack gap="comfortable">
        <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
          <Stack direction="row" gap="standard" style={{alignItems: 'center'}}>
            <h2 style={{margin: 0, fontSize: '1rem'}}>{gettext('MySQL 9.7.0 Supervised Host Storage & Benchmark Utilities')}</h2>
            <FormReference formKey="mysql-utility-workspace" />
          </Stack>
          <Button size="small" intent="neutral" disabled={busy} onClick={loadWorkspace}>
            {gettext('Refresh Catalog & Jobs')}
          </Button>
        </Stack>

        <Banner status="info">
          {gettext(
            'Supervised execution for offline storage utilities (myisamchk, myisampack, innochecksum, ibd2sdi) and isolated scratch concurrency benchmarking (mysqlslap) across local, Docker container, or SSH hosts.'
          )}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <Panel variant="outlined" style={{padding: 12}}>
          <Stack gap="standard">
            <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
              <Select
                label={gettext('Native MySQL utility')}
                size="small"
                options={
                  catalog.length
                    ? catalog.map((u) => ({value: u.operation_id, label: `${u.native_utility} — ${u.title}`}))
                    : [
                      {value: 'run_myisamchk', label: 'myisamchk — Check or repair offline MyISAM table files'},
                      {value: 'run_myisampack', label: 'myisampack — Compress offline MyISAM table files'},
                      {value: 'run_innochecksum', label: 'innochecksum — Inspect or rewrite offline InnoDB page checksums'},
                      {value: 'run_ibd2sdi', label: 'ibd2sdi — Extract offline InnoDB tablespace SDI metadata'},
                      {value: 'run_mysqlslap', label: 'mysqlslap — Run concurrency load benchmark'},
                    ]
                }
                value={operationId}
                onChange={(v) => {
                  setOperationId(v);
                  setReviewedJob(null);
                }}
              />
              <Select
                label={gettext('Execution host')}
                size="small"
                options={[
                  {value: 'local', label: gettext('Local ScratchRobin host')},
                  {value: 'container', label: gettext('Docker / OCI container')},
                  {value: 'ssh', label: gettext('Remote SSH host')},
                ]}
                value={hostKind}
                onChange={setHostKind}
              />
              <TextField
                label={gettext('Private workspace path')}
                size="small"
                value={workspacePath}
                onChange={(e) => setWorkspacePath(e.target.value)}
              />
              {operationId !== 'run_mysqlslap' && (
                <TextField
                  label={gettext('Offline MySQL datadir path')}
                  size="small"
                  value={datadir}
                  onChange={(e) => setDatadir(e.target.value)}
                />
              )}
              <TextField
                label={gettext('Executable override (optional)')}
                size="small"
                value={executablePath}
                onChange={(e) => setExecutablePath(e.target.value)}
              />
              <NumberField
                label={gettext('Timeout (seconds)')}
                size="small"
                min={1}
                max={3600}
                value={timeoutSeconds}
                onChange={(v) => setTimeoutSeconds(v ?? 120)}
              />
            </Grid>

            {hostKind === 'container' && (
              <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                <TextField
                  label={gettext('Container name')}
                  size="small"
                  value={containerName}
                  onChange={(e) => setContainerName(e.target.value)}
                />
                <TextField
                  label={gettext('Docker context (optional)')}
                  size="small"
                  value={dockerContext}
                  onChange={(e) => setDockerContext(e.target.value)}
                />
              </Grid>
            )}

            {hostKind === 'ssh' && (
              <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                <TextField label={gettext('SSH host')} size="small" value={sshHost} onChange={(e) => setSshHost(e.target.value)} />
                <NumberField label={gettext('SSH port')} size="small" min={1} max={65535} value={sshPort} onChange={(v) => setSshPort(v ?? 22)} />
                <TextField label={gettext('SSH username')} size="small" value={sshUsername} onChange={(e) => setSshUsername(e.target.value)} />
                <TextField label={gettext('SSH known host key')} size="small" value={sshHostKey} onChange={(e) => setSshHostKey(e.target.value)} />
                <Select
                  label={gettext('SSH auth mode')}
                  size="small"
                  options={[
                    {value: 'password', label: gettext('Password')},
                    {value: 'private_key', label: gettext('Private key')},
                  ]}
                  value={sshAuthMode}
                  onChange={setSshAuthMode}
                />
                {sshAuthMode === 'password' ? (
                  <PasswordField label={gettext('SSH password')} size="small" value={sshPassword} onChange={(e) => setSshPassword(e.target.value)} />
                ) : (
                  <TextArea label={gettext('SSH private key')} rows={3} value={sshPrivateKey} onChange={(e) => setSshPrivateKey(e.target.value)} />
                )}
              </Grid>
            )}

            {/* Utility-specific parameters */}
            {(operationId === 'run_myisamchk' || operationId === 'run_myisampack') && (
              <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                <TextField label={gettext('Database name')} size="small" value={databaseName} onChange={(e) => setDatabaseName(e.target.value)} />
                <TextField label={gettext('MyISAM table name')} size="small" value={tableName} onChange={(e) => setTableName(e.target.value)} />
                {operationId === 'run_myisamchk' ? (
                  <Select
                    label={gettext('myisamchk mode')}
                    size="small"
                    options={[
                      {value: 'check', label: '--check'},
                      {value: 'medium_check', label: '--medium-check'},
                      {value: 'extend_check', label: '--extend-check'},
                      {value: 'information', label: '--check --information'},
                      {value: 'recover', label: '--recover (mutating)'},
                      {value: 'safe_recover', label: '--safe-recover (mutating)'},
                      {value: 'sort_index', label: '--sort-index (mutating)'},
                      {value: 'analyze', label: '--analyze (mutating)'},
                    ]}
                    value={myisamMode}
                    onChange={setMyisamMode}
                  />
                ) : (
                  <Checkbox label={gettext('Dry-run test only (--test)')} checked={dryRunTest} onChange={setDryRunTest} />
                )}
                <Checkbox label={gettext('Create .BAK table backup (--backup)')} checked={backup} onChange={setBackup} />
                {operationId === 'run_myisamchk' && (
                  <>
                    <Checkbox label={gettext('Include statistics (--information)')} checked={includeInformation} onChange={setIncludeInformation} />
                    <Checkbox label={gettext('Quick index-only check/repair (--quick)')} checked={quick} onChange={setQuick} />
                  </>
                )}
                {operationId === 'run_myisampack' && (
                  <>
                    <Checkbox label={gettext('Force pack (--force)')} checked={forcePack} onChange={setForcePack} />
                    <Checkbox label={gettext('Rebuild MyISAM indexes after pack')} checked={rebuildIndexes} onChange={setRebuildIndexes} />
                  </>
                )}
                <Checkbox
                  label={gettext('Confirm offline mutating file modification')}
                  checked={destructiveConfirmed}
                  onChange={setDestructiveConfirmed}
                />
              </Grid>
            )}

            {(operationId === 'run_innochecksum' || operationId === 'run_ibd2sdi') && (
              <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                <Select
                  label={gettext('Tablespace file scope')}
                  size="small"
                  options={[
                    {value: 'datadir_table', label: gettext('Table .ibd in datadir (<db>/<table>.ibd)')},
                    {value: 'workspace_staged', label: gettext('Staged .ibd relative to workspace')},
                  ]}
                  value={tablespaceScope}
                  onChange={setTablespaceScope}
                />
                {tablespaceScope === 'datadir_table' ? (
                  <>
                    <TextField label={gettext('Database name')} size="small" value={databaseName} onChange={(e) => setDatabaseName(e.target.value)} />
                    <TextField label={gettext('InnoDB table name')} size="small" value={tableName} onChange={(e) => setTableName(e.target.value)} />
                  </>
                ) : (
                  <TextField label={gettext('Relative .ibd path in workspace')} size="small" value={tablespaceRelpath} onChange={(e) => setTablespaceRelpath(e.target.value)} />
                )}
                <Select
                  label={gettext('Checksum verification (--strict-check)')}
                  size="small"
                  options={[
                    {value: 'crc32', label: 'crc32'},
                    {value: 'innodb', label: 'innodb'},
                    {value: 'none', label: 'none'},
                  ]}
                  value={strictCheck}
                  onChange={setStrictCheck}
                />
                {operationId === 'run_innochecksum' ? (
                  <>
                    <Select
                      label={gettext('Rewrite checksums (--write)')}
                      size="small"
                      options={[
                        {value: '', label: gettext('Read-only inspection (no --write)')},
                        {value: 'crc32', label: '--write=crc32 (mutating)'},
                        {value: 'innodb', label: '--write=innodb (mutating)'},
                        {value: 'none', label: '--write=none (mutating)'},
                      ]}
                      value={writeAlgorithm}
                      onChange={setWriteAlgorithm}
                    />
                    <Checkbox label={gettext('Page count only (--count)')} checked={countOnly} onChange={setCountOnly} />
                    <Checkbox label={gettext('Page type summary (--page-type-summary)')} checked={pageTypeSummary} onChange={setPageTypeSummary} />
                    {writeAlgorithm && (
                      <Checkbox
                        label={gettext('Confirm offline InnoDB checksum rewrite')}
                        checked={destructiveConfirmed}
                        onChange={setDestructiveConfirmed}
                      />
                    )}
                  </>
                ) : (
                  <>
                    <TextField label={gettext('Filter SDI object ID (optional)')} size="small" value={sdiId} onChange={(e) => setSdiId(e.target.value)} />
                    <Checkbox label={gettext('Skip SDI data payload (--skip-data)')} checked={skipData} onChange={setSkipData} />
                  </>
                )}
              </Grid>
            )}

            {operationId === 'run_mysqlslap' && (
              <Stack gap="standard">
                <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
                  <TextField
                    label={gettext('Isolated scratch benchmark schema')}
                    size="small"
                    value={benchmarkSchema}
                    onChange={(e) => setBenchmarkSchema(e.target.value)}
                    helperText={gettext('Must start with cdeadmin_slap_ or mysqlslap.')}
                  />
                  <TextField
                    label={gettext('Concurrency levels (e.g. 4 or 1,4,8)')}
                    size="small"
                    value={concurrency}
                    onChange={(e) => setConcurrency(e.target.value)}
                  />
                  <NumberField
                    label={gettext('Iterations')}
                    size="small"
                    min={1}
                    max={1000}
                    value={iterations}
                    onChange={(v) => setIterations(v ?? 2)}
                  />
                  <Select
                    label={gettext('Workload mode')}
                    size="small"
                    options={[
                      {value: 'auto_generate', label: gettext('Auto-generated SQL workload')},
                      {value: 'explicit_sql', label: gettext('Explicit bounded create & query SQL')},
                    ]}
                    value={workloadMode}
                    onChange={setWorkloadMode}
                  />
                  {workloadMode === 'auto_generate' && (
                    <Select
                      label={gettext('Auto-generated load profile')}
                      size="small"
                      options={[
                        {value: 'mixed', label: 'mixed'},
                        {value: 'read', label: 'read'},
                        {value: 'write', label: 'write'},
                        {value: 'key', label: 'key'},
                        {value: 'update', label: 'update'},
                      ]}
                      value={autoLoadType}
                      onChange={setAutoLoadType}
                    />
                  )}
                </Grid>
                {workloadMode === 'explicit_sql' && (
                  <Grid columns="repeat(auto-fit, minmax(300px, 1fr))">
                    <TextArea label={gettext('Create schema objects SQL')} rows={3} value={createSql} onChange={(e) => setCreateSql(e.target.value)} />
                    <TextArea label={gettext('Benchmark query SQL')} rows={3} value={querySql} onChange={(e) => setQuerySql(e.target.value)} />
                  </Grid>
                )}
                <Checkbox
                  label={gettext('I confirm mysqlslap uses an isolated scratch schema and never targets production tables')}
                  checked={isolatedScratchConfirmed}
                  onChange={setIsolatedScratchConfirmed}
                />
              </Stack>
            )}

            <Grid columns="repeat(auto-fit, minmax(260px, 1fr))">
              <TextField
                label={
                  serverDisplayName
                    ? gettext('Type server name (%s) to confirm review', serverDisplayName)
                    : gettext('Type exact MySQL server display name to confirm review')
                }
                size="small"
                value={serverConfirmation}
                onChange={(e) => setServerConfirmation(e.target.value)}
              />
              <Checkbox
                label={gettext('Run asynchronously in supervised background job')}
                checked={asyncExecution}
                onChange={setAsyncExecution}
              />
            </Grid>

            <Stack direction="row" gap="standard">
              <Button intent="primary" disabled={busy || !serverConfirmation.trim()} onClick={handleReview}>
                {gettext('Review Utility Job')}
              </Button>
            </Stack>
          </Stack>
        </Panel>

        {reviewedJob && (
          <Panel variant="outlined" style={{padding: 12}}>
            <Stack gap="standard">
              <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between'}}>
                <strong>{gettext('Reviewed Utility Job')}: {reviewedJob.job_id}</strong>
                <Badge label={reviewedJob.state} status="info" />
              </Stack>
              {(reviewedJob.warnings || []).map((w, idx) => (
                <Banner key={idx} status="warning">{w}</Banner>
              ))}
              <CodeEditor
                label={gettext('Planned command preview')}
                readonly
                language="json"
                value={JSON.stringify(reviewedJob.command_preview, null, 2)}
              />
              <Checkbox
                label={gettext('I reviewed the command preview, host paths, and warnings and authorize execution')}
                checked={startConfirmed}
                onChange={setStartConfirmed}
              />
              <Stack direction="row" gap="standard">
                <Button intent="primary" disabled={busy || !startConfirmed} onClick={handleStart}>
                  {gettext('Start Utility Job')}
                </Button>
              </Stack>
            </Stack>
          </Panel>
        )}

        {activeJob && (
          <Panel variant="outlined" style={{padding: 12}}>
            <Stack gap="standard">
              <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
                <strong>{gettext('Selected Job Receipt')}: {activeJob.job_id}</strong>
                <Stack direction="row" gap="standard" style={{alignItems: 'center'}}>
                  <Badge
                    label={activeJob.state}
                    status={activeJob.state === 'completed' ? 'success' : activeJob.state === 'failed' ? 'error' : 'info'}
                  />
                  <Button size="small" intent="neutral" disabled={busy} onClick={() => handlePollJob(activeJob.job_id)}>
                    {gettext('Poll Status')}
                  </Button>
                  {activeJob.state === 'active' && (
                    <Button size="small" intent="destructive" disabled={busy} onClick={() => handleCancelJob(activeJob.job_id)}>
                      {gettext('Cancel Job')}
                    </Button>
                  )}
                </Stack>
              </Stack>
              <CodeEditor
                label={gettext('Utility execution result / output')}
                readonly
                language="json"
                value={JSON.stringify(activeJob.result || activeJob.error || activeJob, null, 2)}
              />
            </Stack>
          </Panel>
        )}

        <Panel variant="outlined" style={{padding: 12}}>
          <Stack gap="standard">
            <strong>{gettext('Retained Utility Jobs (%s)', jobs.length)}</strong>
            {jobs.length === 0 ? (
              <Box sx={{fontSize: '0.8125rem'}}>{gettext('No MySQL utility jobs recorded for this server yet.')}</Box>
            ) : (
              <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem'}} aria-label={gettext('MySQL utility job history')}>
                <thead>
                  <tr style={{textAlign: 'left', borderBottom: '1px solid var(--sr-border-default)'}}>
                    <th style={{padding: 6}}>{gettext('Job ID')}</th>
                    <th style={{padding: 6}}>{gettext('Utility')}</th>
                    <th style={{padding: 6}}>{gettext('State')}</th>
                    <th style={{padding: 6}}>{gettext('Actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.job_id} style={{borderBottom: '1px solid var(--sr-border-subtle)'}}>
                      <td style={{padding: 6}}><code>{job.job_id}</code></td>
                      <td style={{padding: 6}}>{job.utility || job.operation_id}</td>
                      <td style={{padding: 6}}>{job.state}</td>
                      <td style={{padding: 6}}>
                        <Button size="small" intent="neutral" disabled={busy} onClick={() => handlePollJob(job.job_id)}>
                          {gettext('Inspect')}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Stack>
        </Panel>
      </Stack>
    </Box>
  );
}

MySQLUtilityWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  api: PropTypes.object,
};
