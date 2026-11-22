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
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import {SqliteSectionCard, createSqliteWorkspaceCaller} from './sqliteAdminHelpers';

const textVal = (e) => (e?.target ? e.target.value : String(e ?? ''));

/**
 * SQ-AUD-11 (SR-F-030562): Native SQLite Incremental Integrity Check (`ext/intck`).
 */
export default function SqliteIntckWorkspace({
  endpointUrl,
  databaseTargetId = '',
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callSqlite = useMemo(
    () => createSqliteWorkspaceCaller(api, endpointUrl, databaseTargetId),
    [api, endpointUrl, databaseTargetId]
  );

  const [status, setStatus] = useState(null);
  const [schemaName, setSchemaName] = useState('main');
  const [maxSteps, setMaxSteps] = useState('200');
  const [unlockInterval, setUnlockInterval] = useState('16');
  const [activeJob, setActiveJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadStatus = useCallback(async () => {
    try {
      const s = await callSqlite({action: 'sqlite_ops_intck_status'});
      setStatus(s);
      if (s?.jobs?.length && !activeJob) {
        setActiveJob(s.jobs[0]);
      }
    } catch (err) {
      setError(err?.message || String(err));
    }
  }, [callSqlite, activeJob]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleOpen = async () => {
    setBusy(true);
    setError('');
    try {
      const job = await callSqlite({
        action: 'sqlite_ops_intck_open',
        request: {
          schema_name: schemaName.trim() || 'main',
          unlock_interval: Number(unlockInterval) || 16,
        },
      });
      setActiveJob(job);
      await loadStatus();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleAction = async (actionName) => {
    if (!activeJob?.job_id) return;
    setBusy(true);
    setError('');
    try {
      const req = {job_id: activeJob.job_id};
      if (actionName === 'sqlite_ops_intck_step' || actionName === 'sqlite_ops_intck_resume') {
        req.max_steps = Number(maxSteps) || 200;
      }
      const updated = await callSqlite({action: actionName, request: req});
      setActiveJob(updated);
      await loadStatus();
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
            <strong>{gettext('SQLite Incremental Integrity Check')}</strong>
            <Badge
              status={status?.runtime?.available ? 'success' : 'warning'}
              label={status?.runtime?.available ? gettext('Intck Helper Ready') : gettext('Helper Unavailable')}
            />
          </Stack>
          <FormReference reference="SR-F-030562" />
        </Stack>

        <Banner status="info">
          {status?.disclaimer || gettext('Incremental integrity check splits B-tree/index verification across unlocked read intervals and does not repair or recover damaged pages.')}
        </Banner>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}

        <SqliteSectionCard title={gettext('Configure Incremental Check Session')}>
          <Grid columns={3} gap="sm">
            <TextField
              label={gettext('Schema Namespace')}
              value={schemaName}
              onChange={(e) => setSchemaName(textVal(e))}
            />
            <TextField
              label={gettext('Steps per Batch')}
              value={maxSteps}
              onChange={(e) => setMaxSteps(textVal(e))}
            />
            <TextField
              label={gettext('Unlock Read-Lock Interval')}
              value={unlockInterval}
              onChange={(e) => setUnlockInterval(textVal(e))}
            />
          </Grid>
          <Stack direction="row" gap="sm">
            <Button variant="primary" disabled={busy} onClick={handleOpen}>
              {gettext('Open Incremental Check')}
            </Button>
          </Stack>
        </SqliteSectionCard>

        {activeJob && (
          <SqliteSectionCard
            title={`${gettext('Check Session')}: ${activeJob.job_id}`}
            actions={
              <Badge
                status={activeJob.corrupt_detected ? 'error' : 'success'}
                label={`${activeJob.state}${activeJob.corrupt_detected ? ` (${gettext('Corrupt')})` : ''}`}
              />
            }
          >
            <Grid columns={3} gap="sm">
              <div>{gettext('Completed Steps')}: <strong>{activeJob.completed_steps ?? 0}</strong></div>
              <div>{gettext('Read-Lock Unlocks')}: <strong>{activeJob.unlock_count ?? 0}</strong></div>
              <div>{gettext('Concurrent Drift')}: <strong>{String(Boolean(activeJob.concurrent_drift_detected))}</strong></div>
            </Grid>
            {(activeJob.corruption_messages || []).length > 0 && (
              <pre style={{margin: 0, whiteSpace: 'pre-wrap'}}>
                {activeJob.corruption_messages.join('\n')}
              </pre>
            )}
            <Stack direction="row" gap="sm">
              <Button
                variant="primary"
                disabled={busy || activeJob.state === 'completed' || activeJob.state === 'closed' || activeJob.state === 'paused'}
                onClick={() => handleAction('sqlite_ops_intck_step')}
              >
                {gettext('Step Batch')}
              </Button>
              <Button
                disabled={busy || (activeJob.state !== 'open' && activeJob.state !== 'active')}
                onClick={() => handleAction('sqlite_ops_intck_pause')}
              >
                {gettext('Pause')}
              </Button>
              <Button
                disabled={busy || activeJob.state !== 'paused'}
                onClick={() => handleAction('sqlite_ops_intck_resume')}
              >
                {gettext('Resume')}
              </Button>
              <Button
                disabled={busy || activeJob.state === 'closed' || activeJob.state === 'completed'}
                onClick={() => handleAction('sqlite_ops_intck_close')}
              >
                {gettext('Close Handle')}
              </Button>
            </Stack>
          </SqliteSectionCard>
        )}
      </Stack>
    </Box>
  );
}

SqliteIntckWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  api: PropTypes.object,
};
