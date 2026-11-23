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
import {NumberField, SecretField, TextArea, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import {
  MariaDBJobsTable,
  MariaDBReviewCard,
  MariaDBSectionCard,
  useMariaDBServerApi,
} from './mariadbAdminHelpers';

const UTILITY_OPTIONS = [
  {value: 'run_aria_chk', label: 'aria_chk — Check, Analyze, Recover or Zerofill Offline Aria Table'},
  {value: 'run_aria_pack', label: 'aria_pack — Compress Offline Aria Table (.MAI/.MAD)'},
  {value: 'run_myisamchk', label: 'myisamchk — Check, Analyze or Recover Offline MyISAM Table'},
  {value: 'run_myisampack', label: 'myisampack — Compress Offline MyISAM Table (.MYI/.MYD)'},
  {value: 'run_innochecksum', label: 'innochecksum — Verify or Rewrite Offline InnoDB Checksums (.ibd)'},
  {value: 'run_mariadb_slap', label: 'mariadb-slap — Isolated Scratch-Schema Load Benchmark'},
];

/**
 * MDB-UI-06 (SR-F-030345): Supervised MariaDB 12.2.2 Offline Aria/MyISAM/InnoDB
 * & Benchmark Host Utilities Workspace (`tab="mariadb-utilities"`).
 */
export default function MariaDBUtilityWorkspace({
  endpointUrl,
  databaseTargetId = null,
  api = null,
}) {
  const {callServer} = useMariaDBServerApi(endpointUrl, api);

  const [catalog, setCatalog] = useState([]);
  const [serverResource, setServerResource] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [review, setReview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // Common host execution parameters
  const [operationId, setOperationId] = useState('run_aria_chk');
  const [hostKind, setHostKind] = useState('local');
  const [workspacePath, setWorkspacePath] = useState('/tmp/scratchrobin-mariadb-util');
  const [datadir, setDatadir] = useState('/var/lib/mysql');
  const [executablePath, setExecutablePath] = useState('');
  const [timeoutSeconds, setTimeoutSeconds] = useState(120);
  const [confirmation, setConfirmation] = useState('');

  // Container / SSH parameters
  const [containerName, setContainerName] = useState('');
  const [dockerContext, setDockerContext] = useState('');
  const [sshHost, setSshHost] = useState('');
  const [sshPort, setSshPort] = useState(22);
  const [sshUsername, setSshUsername] = useState('');
  const [sshHostKey, setSshHostKey] = useState('');
  const [sshAuthMode, setSshAuthMode] = useState('password');
  const [sshPassword, setSshPassword] = useState('');
  const [sshPrivateKey, setSshPrivateKey] = useState('');

  // Aria / MyISAM / InnoDB parameters
  const [databaseName, setDatabaseName] = useState(databaseTargetId || '');
  const [tableName, setTableName] = useState('');
  const [checkMode, setCheckMode] = useState('check');
  const [includeInformation, setIncludeInformation] = useState(false);
  const [quick, setQuick] = useState(false);
  const [backup, setBackup] = useState(true);
  const [dryRunTest, setDryRunTest] = useState(true);
  const [forcePack, setForcePack] = useState(false);
  const [rebuildIndexes, setRebuildIndexes] = useState(true);
  const [destructiveConfirmed, setDestructiveConfirmed] = useState(false);

  // innochecksum parameters
  const [tablespaceScope, setTablespaceScope] = useState('datadir_table');
  const [tablespaceRelpath, setTablespaceRelpath] = useState('');
  const [countOnly, setCountOnly] = useState(false);
  const [rewriteChecksum, setRewriteChecksum] = useState(false);
  const [noCheck, setNoCheck] = useState(false);
  const [pageTypeSummary, setPageTypeSummary] = useState(true);
  const [perPageDetails, setPerPageDetails] = useState(false);
  const [skipFreedPages, setSkipFreedPages] = useState(false);
  const [startPage, setStartPage] = useState('');
  const [endPage, setEndPage] = useState('');

  // mariadb-slap parameters
  const [benchmarkSchema, setBenchmarkSchema] = useState('cdeadmin_slap_scratch');
  const [concurrency, setConcurrency] = useState('4');
  const [iterations, setIterations] = useState(2);
  const [workloadMode, setWorkloadMode] = useState('auto_generate');
  const [autoLoadType, setAutoLoadType] = useState('mixed');
  const [numberIntCols, setNumberIntCols] = useState(2);
  const [numberCharCols, setNumberCharCols] = useState(2);
  const [numberOfQueries, setNumberOfQueries] = useState(100);
  const [createSql, setCreateSql] = useState('');
  const [querySql, setQuerySql] = useState('SELECT 1;');
  const [keepBenchmarkSchema, setKeepBenchmarkSchema] = useState(false);
  const [isolatedScratchConfirmed, setIsolatedScratchConfirmed] = useState(true);

  const loadCatalogAndJobs = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [catRes, pageRes, jobRes] = await Promise.all([
        callServer({action: 'mariadb_utility_catalog', request: {}}).catch(() => null),
        callServer({action: 'resource_page', request: {limit: 50}}).catch(() => ({items: []})),
        callServer({action: 'mariadb_utility_list', request: {offset: 0, limit: 25}}).catch(() => ({jobs: []})),
      ]);
      if (catRes) {
        setCatalog(catRes.utilities || catRes.operations || []);
      }
      const srv =
        (pageRes?.items || []).find((it) => it.resource_kind === 'server') ||
        catRes?.server ||
        catRes?.target_resource ||
        null;
      setServerResource(srv);
      if (srv?.display_name) {
        setConfirmation((prev) => prev || srv.display_name);
      }
      setJobs(jobRes?.jobs || []);
    } catch (err) {
      setError(err.message || gettext('Failed to load MariaDB 12.2.2 host utilities catalog.'));
    } finally {
      setBusy(false);
    }
  }, [callServer]);

  useEffect(() => {
    loadCatalogAndJobs();
  }, [loadCatalogAndJobs]);

  const buildDraft = () => {
    const draft = {
      execution_host_kind: hostKind,
      workspace: workspacePath.trim(),
      timeout_seconds: Number(timeoutSeconds) || 120,
      confirmation: confirmation.trim(),
    };
    if (operationId !== 'run_mariadb_slap') {
      draft.datadir = datadir.trim();
    }
    if (executablePath.trim()) {
      draft.executable_path = executablePath.trim();
    }
    if (hostKind === 'container') {
      draft.container_name = containerName.trim();
      if (dockerContext.trim()) draft.docker_context = dockerContext.trim();
    } else if (hostKind === 'ssh') {
      draft.ssh_host = sshHost.trim();
      draft.ssh_port = Number(sshPort) || 22;
      draft.ssh_username = sshUsername.trim();
      draft.ssh_host_key = sshHostKey.trim();
      draft.ssh_auth_mode = sshAuthMode;
      if (sshAuthMode === 'password') {
        draft.ssh_password = sshPassword;
      } else {
        draft.ssh_private_key = sshPrivateKey;
      }
    }

    if (operationId === 'run_aria_chk' || operationId === 'run_myisamchk') {
      draft.database_name = databaseName.trim();
      draft.table_name = tableName.trim();
      draft.mode = checkMode;
      draft.include_information = Boolean(includeInformation);
      draft.quick = Boolean(quick);
      draft.backup = Boolean(backup);
      draft.destructive_confirmed = Boolean(destructiveConfirmed);
    } else if (operationId === 'run_aria_pack' || operationId === 'run_myisampack') {
      draft.database_name = databaseName.trim();
      draft.table_name = tableName.trim();
      draft.dry_run_test = Boolean(dryRunTest);
      draft.backup = Boolean(backup);
      draft.force = Boolean(forcePack);
      draft.rebuild_indexes = Boolean(rebuildIndexes);
      draft.destructive_confirmed = Boolean(destructiveConfirmed);
    } else if (operationId === 'run_innochecksum') {
      draft.tablespace_scope = tablespaceScope;
      if (tablespaceScope === 'datadir_table') {
        draft.database_name = databaseName.trim();
        draft.table_name = tableName.trim();
      } else {
        draft.tablespace_relpath = tablespaceRelpath.trim();
      }
      draft.count_only = Boolean(countOnly);
      draft.rewrite_checksum = Boolean(rewriteChecksum);
      draft.no_check = Boolean(noCheck);
      draft.page_type_summary = Boolean(pageTypeSummary);
      draft.per_page_details = Boolean(perPageDetails);
      draft.skip_freed_pages = Boolean(skipFreedPages);
      if (startPage !== '') draft.start_page = Number(startPage);
      if (endPage !== '') draft.end_page = Number(endPage);
      draft.destructive_confirmed = Boolean(destructiveConfirmed);
    } else if (operationId === 'run_mariadb_slap') {
      draft.benchmark_schema = benchmarkSchema.trim();
      draft.concurrency = concurrency.trim() || '4';
      draft.iterations = Number(iterations) || 2;
      draft.workload_mode = workloadMode;
      draft.keep_benchmark_schema = Boolean(keepBenchmarkSchema);
      draft.isolated_scratch_confirmed = Boolean(isolatedScratchConfirmed);
      if (workloadMode === 'auto_generate') {
        draft.auto_load_type = autoLoadType;
        draft.number_int_cols = Number(numberIntCols) || 2;
        draft.number_char_cols = Number(numberCharCols) || 2;
        if (numberOfQueries) draft.number_of_queries = Number(numberOfQueries);
      } else {
        if (createSql.trim()) draft.create_sql = createSql.trim();
        draft.query_sql = querySql.trim();
      }
    }
    return draft;
  };

  const handleReview = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await callServer({
        action: 'mariadb_utility_review',
        request: {
          operation_id: operationId,
          target_resource: serverResource || {
            resource_kind: 'server',
            resource_id: `server:${confirmation.trim()}`,
            display_name: confirmation.trim(),
            display_path: [confirmation.trim()],
          },
          draft: buildDraft(),
        },
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
        action: 'mariadb_utility_start',
        request: {
          job_id: reviewed.job_id,
          review_digest: reviewed.review_digest,
          confirmed: true,
        },
      });
      setReview(null);
      setSelectedJob(res);
      setNotice(gettext('Started MariaDB 12.2.2 host utility job ') + res.job_id);
      await loadCatalogAndJobs();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box style={{padding: '12px', overflow: 'auto'}} data-testid="mariadb-utilities-workspace">
      <Stack direction="column" gap={3}>
        <Stack direction="row" style={{flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between'}}>
          <Stack direction="row" gap={1} style={{alignItems: 'center'}}>
            <strong>{gettext('MariaDB 12.2.2 Supervised Host Utilities')}</strong>
            <FormReference formKey="mariadb-utilities-workspace" />
          </Stack>
          <Button size="sm" intent="neutral" disabled={busy} onClick={loadCatalogAndJobs}>
            {gettext('Refresh Jobs')}
          </Button>
        </Stack>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}
        {notice && <Banner status="success">{notice}</Banner>}

        {serverResource && (
          <Stack direction="row" gap={2} style={{flexWrap: 'wrap', alignItems: 'center'}}>
            <Badge status="info" label={serverResource.display_name} />
            <span style={{fontSize: '0.82rem'}}>
              {gettext('Admitted utilities:')} <code>aria_chk</code>, <code>aria_pack</code>,{' '}
              <code>myisamchk</code>, <code>myisampack</code>, <code>innochecksum</code>,{' '}
              <code>mariadb-slap</code> ({catalog.length || 6})
            </span>
          </Stack>
        )}

        <MariaDBSectionCard title={gettext('Configure MariaDB 12.2.2 Utility & Execution Host')}>
          <Stack direction="column" gap={2}>
            <Grid columns={3} gap={2}>
              <Select
                label={gettext('Native MariaDB Utility')}
                value={operationId}
                options={UTILITY_OPTIONS}
                onChange={(val) => {
                  setOperationId(val);
                  setCheckMode('check');
                }}
              />
              <Select
                label={gettext('Execution Host Kind')}
                value={hostKind}
                options={[
                  {value: 'local', label: 'Local Authorized Host'},
                  {value: 'container', label: 'Docker / Container Host'},
                  {value: 'ssh', label: 'SSH Execution Host (Pinned Host Key)'},
                ]}
                onChange={(val) => setHostKind(val)}
              />
              <TextField
                label={gettext('Confirm MariaDB Server Name')}
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
              />
              <TextField
                label={gettext('Private Execution Workspace')}
                value={workspacePath}
                onChange={(e) => setWorkspacePath(e.target.value)}
              />
              {operationId !== 'run_mariadb_slap' && (
                <TextField
                  label={gettext('Offline MariaDB Datadir')}
                  value={datadir}
                  onChange={(e) => setDatadir(e.target.value)}
                />
              )}
              <TextField
                label={gettext('Executable Path Override (optional)')}
                value={executablePath}
                onChange={(e) => setExecutablePath(e.target.value)}
              />
              <NumberField
                label={gettext('Timeout (seconds)')}
                value={timeoutSeconds}
                min={1}
                max={3600}
                onChange={(e) => setTimeoutSeconds(Number(e.target.value))}
              />
            </Grid>

            {hostKind === 'container' && (
              <Grid columns={2} gap={2}>
                <TextField
                  label={gettext('Container Name')}
                  value={containerName}
                  onChange={(e) => setContainerName(e.target.value)}
                />
                <TextField
                  label={gettext('Docker Context (optional)')}
                  value={dockerContext}
                  onChange={(e) => setDockerContext(e.target.value)}
                />
              </Grid>
            )}

            {hostKind === 'ssh' && (
              <Grid columns={3} gap={2}>
                <TextField
                  label={gettext('SSH Host')}
                  value={sshHost}
                  onChange={(e) => setSshHost(e.target.value)}
                />
                <NumberField
                  label={gettext('SSH Port')}
                  value={sshPort}
                  min={1}
                  max={65535}
                  onChange={(e) => setSshPort(Number(e.target.value))}
                />
                <TextField
                  label={gettext('SSH Username')}
                  value={sshUsername}
                  onChange={(e) => setSshUsername(e.target.value)}
                />
                <TextField
                  label={gettext('Pinned SSH Host Key')}
                  value={sshHostKey}
                  onChange={(e) => setSshHostKey(e.target.value)}
                />
                <Select
                  label={gettext('SSH Auth Mode')}
                  value={sshAuthMode}
                  options={[
                    {value: 'password', label: 'Password'},
                    {value: 'private_key', label: 'PEM Private Key'},
                  ]}
                  onChange={(val) => setSshAuthMode(val)}
                />
                {sshAuthMode === 'password' ? (
                  <SecretField
                    label={gettext('SSH Password')}
                    value={sshPassword}
                    onChange={(e) => setSshPassword(e.target.value)}
                  />
                ) : (
                  <TextArea
                    label={gettext('SSH Private Key')}
                    rows={3}
                    value={sshPrivateKey}
                    onChange={(e) => setSshPrivateKey(e.target.value)}
                  />
                )}
              </Grid>
            )}

            {(operationId === 'run_aria_chk' || operationId === 'run_myisamchk') && (
              <Stack direction="column" gap={2}>
                <Grid columns={3} gap={2}>
                  <TextField
                    label={gettext('Database Name')}
                    value={databaseName}
                    onChange={(e) => setDatabaseName(e.target.value)}
                  />
                  <TextField
                    label={gettext('Table Name')}
                    value={tableName}
                    onChange={(e) => setTableName(e.target.value)}
                  />
                  <Select
                    label={gettext('Check / Repair Mode')}
                    value={checkMode}
                    options={
                      operationId === 'run_aria_chk'
                        ? [
                          {value: 'check', label: '--check'},
                          {value: 'extend_check', label: '--extend-check'},
                          {value: 'describe', label: '--description'},
                          {value: 'analyze', label: '--analyze (mutating)'},
                          {value: 'recover', label: '--recover (mutating)'},
                          {value: 'safe_recover', label: '--safe-recover (mutating)'},
                          {value: 'zerofill', label: '--zerofill (mutating)'},
                        ]
                        : [
                          {value: 'check', label: '--check'},
                          {value: 'medium_check', label: '--medium-check'},
                          {value: 'extend_check', label: '--extend-check'},
                          {value: 'information', label: '--check --information'},
                          {value: 'describe', label: '--description'},
                          {value: 'analyze', label: '--analyze (mutating)'},
                          {value: 'recover', label: '--recover (mutating)'},
                          {value: 'safe_recover', label: '--safe-recover (mutating)'},
                          {value: 'sort_index', label: '--sort-index (mutating)'},
                        ]
                    }
                    onChange={(val) => setCheckMode(val)}
                  />
                </Grid>
                <Stack direction="row" gap={2} style={{flexWrap: 'wrap'}}>
                  <Checkbox
                    label={gettext('Include --information')}
                    checked={includeInformation}
                    onChange={(checked) => setIncludeInformation(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Quick (--quick)')}
                    checked={quick}
                    onChange={(checked) => setQuick(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Backup data file (--backup) on repair')}
                    checked={backup}
                    onChange={(checked) => setBackup(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Confirm offline mutating repair / analyze / zerofill')}
                    checked={destructiveConfirmed}
                    onChange={(checked) => setDestructiveConfirmed(Boolean(checked))}
                  />
                </Stack>
              </Stack>
            )}

            {(operationId === 'run_aria_pack' || operationId === 'run_myisampack') && (
              <Stack direction="column" gap={2}>
                <Grid columns={2} gap={2}>
                  <TextField
                    label={gettext('Database Name')}
                    value={databaseName}
                    onChange={(e) => setDatabaseName(e.target.value)}
                  />
                  <TextField
                    label={gettext('Table Name')}
                    value={tableName}
                    onChange={(e) => setTableName(e.target.value)}
                  />
                </Grid>
                <Stack direction="row" gap={2} style={{flexWrap: 'wrap'}}>
                  <Checkbox
                    label={gettext('Dry-run test only (--test)')}
                    checked={dryRunTest}
                    onChange={(checked) => setDryRunTest(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Backup before pack (--backup)')}
                    checked={backup}
                    onChange={(checked) => setBackup(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Force pack (--force)')}
                    checked={forcePack}
                    onChange={(checked) => setForcePack(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Rebuild indexes after pack')}
                    checked={rebuildIndexes}
                    onChange={(checked) => setRebuildIndexes(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Confirm offline table compression')}
                    checked={destructiveConfirmed}
                    onChange={(checked) => setDestructiveConfirmed(Boolean(checked))}
                  />
                </Stack>
              </Stack>
            )}

            {operationId === 'run_innochecksum' && (
              <Stack direction="column" gap={2}>
                <Grid columns={3} gap={2}>
                  <Select
                    label={gettext('Tablespace Scope')}
                    value={tablespaceScope}
                    options={[
                      {value: 'datadir_table', label: 'Datadir Table (<db>/<table>.ibd)'},
                      {value: 'workspace_staged', label: 'Staged .ibd File in Workspace'},
                    ]}
                    onChange={(val) => setTablespaceScope(val)}
                  />
                  {tablespaceScope === 'datadir_table' ? (
                    <>
                      <TextField
                        label={gettext('Database Name')}
                        value={databaseName}
                        onChange={(e) => setDatabaseName(e.target.value)}
                      />
                      <TextField
                        label={gettext('Table Name')}
                        value={tableName}
                        onChange={(e) => setTableName(e.target.value)}
                      />
                    </>
                  ) : (
                    <TextField
                      label={gettext('Relative .ibd Path in Workspace')}
                      value={tablespaceRelpath}
                      onChange={(e) => setTablespaceRelpath(e.target.value)}
                    />
                  )}
                  <TextField
                    label={gettext('Start Page (optional)')}
                    value={startPage}
                    onChange={(e) => setStartPage(e.target.value)}
                  />
                  <TextField
                    label={gettext('End Page (optional)')}
                    value={endPage}
                    onChange={(e) => setEndPage(e.target.value)}
                  />
                </Grid>
                <Stack direction="row" gap={2} style={{flexWrap: 'wrap'}}>
                  <Checkbox
                    label={gettext('Page count only (--count)')}
                    checked={countOnly}
                    onChange={(checked) => setCountOnly(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Page type summary (--page-type-summary)')}
                    checked={pageTypeSummary}
                    onChange={(checked) => setPageTypeSummary(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Per-page details (--per-page-details)')}
                    checked={perPageDetails}
                    onChange={(checked) => setPerPageDetails(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Skip freed pages (--skip-freed-pages)')}
                    checked={skipFreedPages}
                    onChange={(checked) => setSkipFreedPages(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Rewrite checksums (--write)')}
                    checked={rewriteChecksum}
                    onChange={(checked) => setRewriteChecksum(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Ignore bad checksums during rewrite (--no-check)')}
                    checked={noCheck}
                    onChange={(checked) => setNoCheck(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Confirm offline checksum rewrite')}
                    checked={destructiveConfirmed}
                    onChange={(checked) => setDestructiveConfirmed(Boolean(checked))}
                  />
                </Stack>
              </Stack>
            )}

            {operationId === 'run_mariadb_slap' && (
              <Stack direction="column" gap={2}>
                <Grid columns={4} gap={2}>
                  <TextField
                    label={gettext('Isolated Scratch Schema (cdeadmin_slap_*)')}
                    value={benchmarkSchema}
                    onChange={(e) => setBenchmarkSchema(e.target.value)}
                  />
                  <TextField
                    label={gettext('Concurrency Levels (e.g. 4 or 1,4,8)')}
                    value={concurrency}
                    onChange={(e) => setConcurrency(e.target.value)}
                  />
                  <NumberField
                    label={gettext('Iterations')}
                    value={iterations}
                    min={1}
                    max={1000}
                    onChange={(e) => setIterations(Number(e.target.value))}
                  />
                  <Select
                    label={gettext('Workload Mode')}
                    value={workloadMode}
                    options={[
                      {value: 'auto_generate', label: 'Auto-Generate SQL (--auto-generate-sql)'},
                      {value: 'explicit_sql', label: 'Explicit Scratch-Schema SQL'},
                    ]}
                    onChange={(val) => setWorkloadMode(val)}
                  />
                </Grid>

                {workloadMode === 'auto_generate' ? (
                  <Grid columns={4} gap={2}>
                    <Select
                      label={gettext('Load Type')}
                      value={autoLoadType}
                      options={[
                        {value: 'mixed', label: 'Mixed'},
                        {value: 'read', label: 'Read'},
                        {value: 'write', label: 'Write'},
                        {value: 'key', label: 'Key'},
                        {value: 'update', label: 'Update'},
                      ]}
                      onChange={(val) => setAutoLoadType(val)}
                    />
                    <NumberField
                      label={gettext('INT Columns')}
                      value={numberIntCols}
                      min={1}
                      max={64}
                      onChange={(e) => setNumberIntCols(Number(e.target.value))}
                    />
                    <NumberField
                      label={gettext('VARCHAR Columns')}
                      value={numberCharCols}
                      min={1}
                      max={64}
                      onChange={(e) => setNumberCharCols(Number(e.target.value))}
                    />
                    <NumberField
                      label={gettext('Total Queries')}
                      value={numberOfQueries}
                      min={1}
                      max={1000000}
                      onChange={(e) => setNumberOfQueries(Number(e.target.value))}
                    />
                  </Grid>
                ) : (
                  <Grid columns={2} gap={2}>
                    <TextArea
                      label={gettext('Create SQL (optional, scratch schema only)')}
                      rows={3}
                      value={createSql}
                      onChange={(e) => setCreateSql(e.target.value)}
                    />
                    <TextArea
                      label={gettext('Benchmark Query SQL')}
                      rows={3}
                      value={querySql}
                      onChange={(e) => setQuerySql(e.target.value)}
                    />
                  </Grid>
                )}

                <Stack direction="row" gap={2} style={{flexWrap: 'wrap'}}>
                  <Checkbox
                    label={gettext('Keep scratch benchmark schema after run')}
                    checked={keepBenchmarkSchema}
                    onChange={(checked) => setKeepBenchmarkSchema(Boolean(checked))}
                  />
                  <Checkbox
                    label={gettext('Confirm isolated scratch benchmark schema execution')}
                    checked={isolatedScratchConfirmed}
                    onChange={(checked) => setIsolatedScratchConfirmed(Boolean(checked))}
                  />
                </Stack>
              </Stack>
            )}

            <Stack direction="row" gap={1}>
              <Button intent="primary" disabled={busy || !confirmation.trim()} onClick={handleReview}>
                {gettext('Review MariaDB Utility Run')}
              </Button>
            </Stack>
          </Stack>
        </MariaDBSectionCard>

        <MariaDBReviewCard
          title={gettext('MariaDB 12.2.2 Utility Review')}
          review={review}
          busy={busy}
          confirmLabel={gettext('Confirm & Start Utility Job')}
          onConfirm={handleStart}
          onClear={() => setReview(null)}
        />

        <MariaDBJobsTable
          title={gettext('Supervised MariaDB Utility Jobs')}
          jobs={jobs}
          busy={busy}
          selectedJob={selectedJob}
          onSelect={setSelectedJob}
          onRefreshJob={async (jid) => {
            const st = await callServer({action: 'mariadb_utility_status', request: {job_id: jid}});
            setSelectedJob(st);
            await loadCatalogAndJobs();
          }}
          onCancelJob={async (jid) => {
            const st = await callServer({action: 'mariadb_utility_cancel', request: {job_id: jid}});
            setSelectedJob(st);
            await loadCatalogAndJobs();
          }}
        />
      </Stack>
    </Box>
  );
}

MariaDBUtilityWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  api: PropTypes.object,
};
