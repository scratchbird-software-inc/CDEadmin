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
import {Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import RecordGrid from '../../objects/RecordGrid';
import UnifiedDataGrid from '../../data/UnifiedDataGrid';
import {SqliteSectionCard, createSqliteWorkspaceCaller} from './sqliteAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

/**
 * SQ-AUD-09 (SR-F-030560): Native SQLite Resumable Bulk Update & Resumable Vacuum (RBU).
 */
export default function SqliteRbuWorkspace({
  endpointUrl,
  databaseTargetId = '',
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callSqlite = useMemo(
    () => createSqliteWorkspaceCaller(api, endpointUrl, databaseTargetId),
    [api, endpointUrl, databaseTargetId]
  );

  const [catalog, setCatalog] = useState(null);
  const [mode, setMode] = useState('update');
  const [targetTable, setTargetTable] = useState('');
  const [opRows, setOpRows] = useState([
    {op: 'insert', values_json: '{"id":1}', where_json: ''},
  ]);
  const [stepBudget, setStepBudget] = useState('250');
  const [activeJob, setActiveJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadCatalog = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const data = await callSqlite({action: 'sqlite_ops_rbu_catalog'});
      setCatalog(data);
      if (data?.jobs?.length && !activeJob) {
        setActiveJob(data.jobs[0]);
      }
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [callSqlite, activeJob]);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);

  const handleOpenJob = async () => {
    setBusy(true);
    setError('');
    try {
      let job;
      if (mode === 'vacuum') {
        job = await callSqlite({action: 'sqlite_ops_rbu_open_vacuum', request: {}});
      } else {
        const parsedOps = opRows.map((row) => {
          const entry = {op: row.op || 'insert'};
          if (String(row.values_json || '').trim()) {
            entry.values = JSON.parse(row.values_json);
          }
          if (String(row.where_json || '').trim()) {
            entry.where = JSON.parse(row.where_json);
          }
          return entry;
        });
        job = await callSqlite({
          action: 'sqlite_ops_rbu_open_update',
          request: {
            tables: [{table: targetTable.trim(), operations: parsedOps}],
          },
        });
      }
      setActiveJob(job);
      await loadCatalog();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleJobAction = async (actionName) => {
    if (!activeJob?.job_id) return;
    setBusy(true);
    setError('');
    try {
      const req = {job_id: activeJob.job_id};
      if (actionName === 'sqlite_ops_rbu_step' || actionName === 'sqlite_ops_rbu_resume') {
        req.step_budget = Number(stepBudget) || 250;
      }
      const updated = await callSqlite({action: actionName, request: req});
      setActiveJob(updated);
      await loadCatalog();
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
            <strong>{gettext('SQLite Resumable Bulk Update & Vacuum (RBU)')}</strong>
            <Badge
              status={catalog?.runtime?.available ? 'success' : 'warning'}
              label={catalog?.runtime?.available ? gettext('RBU Helper Ready') : gettext('Helper Unavailable')}
            />
          </Stack>
          <FormReference reference="SR-F-030560" />
        </Stack>

        <Banner status="info">
          {gettext('RBU accumulates Stage 1 updates in an *-oal file invisible to concurrent readers before incremental *-wal checkpointing. Triggers, CHECK constraints, and foreign keys are not evaluated during RBU apply.')}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <SqliteSectionCard
          title={gettext('Open Resumable RBU Session')}
          actions={
            <Button onClick={loadCatalog} disabled={busy}>
              {gettext('Refresh')}
            </Button>
          }
        >
          <Grid columns={2} gap="sm">
            <Select
              label={gettext('RBU Operation Mode')}
              value={mode}
              onChange={(val) => setMode(val)}
              options={[
                {value: 'update', label: gettext('Resumable Bulk Update (sqlite3rbu_open)')},
                {value: 'vacuum', label: gettext('Resumable Vacuum (sqlite3rbu_vacuum)')},
              ]}
            />
            <TextField
              label={gettext('Step Budget per Batch')}
              value={stepBudget}
              onChange={(e) => setStepBudget(textVal(e))}
            />
          </Grid>
          {mode === 'update' && (
            <Stack gap="sm">
              <TextField
                label={gettext('Target Ordinary Table Name')}
                value={targetTable}
                onChange={(e) => setTargetTable(textVal(e))}
              />
              <RecordGrid
                field={{
                  field_id: 'rbu_operations',
                  label: gettext('Typed Row Operations (insert / update / delete)'),
                  control: 'grid',
                  columns: [
                    {
                      field_id: 'op',
                      label: gettext('Operation'),
                      control: 'select',
                      default: 'insert',
                      options: [
                        {value: 'insert', label: 'INSERT'},
                        {value: 'update', label: 'UPDATE'},
                        {value: 'delete', label: 'DELETE'},
                      ],
                    },
                    {
                      field_id: 'values_json',
                      label: gettext('Column Values (JSON object)'),
                      control: 'text',
                      default: '{"id":1}',
                    },
                    {
                      field_id: 'where_json',
                      label: gettext('Key Match (JSON object)'),
                      control: 'text',
                    },
                  ],
                }}
                rows={opRows}
                onChange={setOpRows}
                disabled={busy}
              />
            </Stack>
          )}
          <Stack direction="row" gap="sm">
            <Button
              variant="primary"
              disabled={busy || (mode === 'update' && !targetTable.trim())}
              onClick={handleOpenJob}
            >
              {mode === 'vacuum' ? gettext('Open RBU Vacuum') : gettext('Build Package & Open RBU Update')}
            </Button>
          </Stack>
        </SqliteSectionCard>

        {activeJob && (
          <SqliteSectionCard
            title={`${gettext('Active RBU Job')}: ${activeJob.job_id}`}
            actions={<Badge status="info" label={`${activeJob.state} / ${activeJob.rbu_state}`} />}
          >
            <Grid columns={3} gap="sm">
              <div>{gettext('Total Steps')}: <strong>{activeJob.total_steps ?? 0}</strong></div>
              <div>{gettext('Stage 1 Progress (bp)')}: <strong>{activeJob.stage1_permyriad ?? 0} / 10000</strong></div>
              <div>{gettext('Stage 2 Checkpoint (bp)')}: <strong>{activeJob.stage2_permyriad ?? 0} / 10000</strong></div>
            </Grid>
            <Stack direction="row" gap="sm">
              <Button
                variant="primary"
                disabled={busy || activeJob.state === 'completed' || activeJob.state === 'paused' || activeJob.state === 'aborted'}
                onClick={() => handleJobAction('sqlite_ops_rbu_step')}
              >
                {gettext('Step Batch')}
              </Button>
              <Button
                disabled={busy || (activeJob.state !== 'open' && activeJob.state !== 'active')}
                onClick={() => handleJobAction('sqlite_ops_rbu_pause')}
              >
                {gettext('Pause & Savestate')}
              </Button>
              <Button
                disabled={busy || activeJob.state !== 'paused'}
                onClick={() => handleJobAction('sqlite_ops_rbu_resume')}
              >
                {gettext('Verify State & Resume')}
              </Button>
              <Button
                disabled={busy || activeJob.state === 'completed' || activeJob.state === 'aborted'}
                onClick={() => handleJobAction('sqlite_ops_rbu_abort')}
              >
                {gettext('Abort & Clean Sidecars')}
              </Button>
            </Stack>
          </SqliteSectionCard>
        )}

        {(catalog?.jobs || []).length > 0 && (
          <SqliteSectionCard title={gettext('Retained RBU Sessions')}>
            <UnifiedDataGrid
              caption={gettext('RBU Sessions')}
              searchable
              exportable
              minHeight={140}
              maxHeight={260}
              rows={catalog.jobs}
              rowKeyGetter={(j) => j.job_id}
              columns={[
                {name: 'job_id', label: gettext('Job ID'), width: 170, mono: true},
                {name: 'state', label: gettext('State'), width: 110},
                {name: 'rbu_state', label: gettext('RBU Stage'), width: 110},
                {name: 'total_steps', label: gettext('Steps'), width: 90, numeric: true},
                {
                  name: 'select',
                  label: gettext('Select'),
                  width: 120,
                  render: (_val, j) => (
                    <Button variant="secondary" disabled={busy} onClick={() => setActiveJob(j)}>
                      {gettext('Select')}
                    </Button>
                  ),
                },
              ]}
            />
          </SqliteSectionCard>
        )}
      </Stack>
    </Box>
  );
}

SqliteRbuWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  api: PropTypes.object,
};
