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
import {Checkbox, Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import UnifiedDataGrid from '../../data/UnifiedDataGrid';
import {PostgresqlSectionCard, createPostgresqlServerCaller} from './postgresqlAdminHelpers';

/**
 * PG-UI-10 (SR-F-030540): Active Backend Sessions, Lock Tree, Fenced Query Cancel /
 * Session Terminate, pg_stat_statements Top-Query Explorer & Shared Statistics Reset.
 */
export default function PostgresqlActivityLocksWorkspace({
  endpointUrl,
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callServer = useMemo(
    () => createPostgresqlServerCaller(api, endpointUrl),
    [api, endpointUrl]
  );

  const [activity, setActivity] = useState(null);
  const [statements, setStatements] = useState(null);
  const [sortBy, setSortBy] = useState('total_exec_time');
  const [signalKind, setSignalKind] = useState('cancel');
  const [reviewedSignal, setReviewedSignal] = useState(null);
  const [confirmSignal, setConfirmSignal] = useState(false);

  const [resetTarget, setResetTarget] = useState('pg_stat_statements');
  const [reviewedReset, setReviewedReset] = useState(null);
  const [confirmReset, setConfirmReset] = useState(false);

  const [lastOutcome, setLastOutcome] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refreshAll = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [act, stmts] = await Promise.all([
        callServer({action: 'postgresql_ops_activity_locks', request: {}}),
        callServer({
          action: 'postgresql_ops_stat_statements',
          request: {sort_by: sortBy, limit: 50},
        }).catch(() => ({installed: false, rows: []})),
      ]);
      setActivity(act);
      setStatements(stmts);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }, [callServer, sortBy]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const handleReviewSignal = async (pid) => {
    setBusy(true);
    setError('');
    try {
      const rev = await callServer({
        action: 'postgresql_ops_session_signal_review',
        request: {pid: Number(pid), signal: signalKind},
      });
      setReviewedSignal(rev);
      setConfirmSignal(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartSignal = async () => {
    if (!reviewedSignal || !confirmSignal) return;
    setBusy(true);
    setError('');
    try {
      const done = await callServer({
        action: 'postgresql_ops_session_signal_start',
        request: {
          job_id: reviewedSignal.job_id,
          review_digest: reviewedSignal.review_digest,
          confirmed: true,
        },
      });
      setLastOutcome(done);
      setReviewedSignal(null);
      await refreshAll();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleReviewReset = async () => {
    setBusy(true);
    setError('');
    try {
      const rev = await callServer({
        action: 'postgresql_ops_stats_reset_review',
        request: {target: resetTarget},
      });
      setReviewedReset(rev);
      setConfirmReset(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartReset = async () => {
    if (!reviewedReset || !confirmReset) return;
    setBusy(true);
    setError('');
    try {
      const done = await callServer({
        action: 'postgresql_ops_stats_reset_start',
        request: {
          job_id: reviewedReset.job_id,
          review_digest: reviewedReset.review_digest,
          confirmed: true,
        },
      });
      setLastOutcome(done);
      setReviewedReset(null);
      await refreshAll();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const sessions = activity?.sessions || [];
  const locks = activity?.locks || [];
  const stmtRows = statements?.rows || [];

  return (
    <Stack gap="md">
      <PostgresqlSectionCard
        title={gettext('Active Backend Sessions, Blocking PIDs & Fenced Signals')}
        actions={<FormReference reference="SR-F-030540" />}
      >
        <Stack gap="sm">
          <Banner status="info">
            {gettext(
              'Observes pg_stat_activity, pg_blocking_pids() and pg_locks, and fences pg_cancel_backend / pg_terminate_backend against exact PID + backend_start UTC timestamps so recycled PIDs are never signalled.'
            )}
          </Banner>
          {error && <ValidationMessage status="error">{error}</ValidationMessage>}
          <Grid columns={2} gap="sm">
            <Select
              label={gettext('Session Signal Mode')}
              value={signalKind}
              options={[
                {value: 'cancel', label: 'Cancel Active Query (pg_cancel_backend)'},
                {value: 'terminate', label: 'Terminate Backend Session (pg_terminate_backend)'},
              ]}
              onChange={setSignalKind}
            />
            <Box>
              <Button variant="secondary" disabled={busy} onClick={refreshAll}>
                {gettext('Refresh Activity, Locks & Statements')}
              </Button>
            </Box>
          </Grid>
          <Box>
            <Badge status="info" label={`${sessions.length} ${gettext('Sessions')}`} />{' '}
            <Badge status={locks.some((l) => !l.granted) ? 'warning' : 'success'} label={`${locks.length} ${gettext('Locks')}`} />
          </Box>
          {sessions.length > 0 && (
            <UnifiedDataGrid
              caption={gettext('Active Backend Sessions')}
              searchable
              exportable
              facets={[{id: 'state', column: 'state', label: gettext('State')}]}
              minHeight={160}
              maxHeight={300}
              rows={sessions}
              rowKeyGetter={(s) => s.pid}
              columns={[
                {
                  name: 'pid',
                  label: gettext('PID'),
                  width: 110,
                  render: (_val, s) => (
                    <Badge status={s.blocking_pids?.length ? 'error' : 'info'} label={`PID ${s.pid}`} />
                  ),
                },
                {name: 'usename', label: gettext('User'), width: 120, accessorFn: (s) => s.usename || 'bg'},
                {name: 'datname', label: gettext('Database'), width: 120, accessorFn: (s) => s.datname || '-'},
                {name: 'state', label: gettext('State'), width: 130, accessorFn: (s) => s.state || s.backend_type || ''},
                {
                  name: 'blocking_pids',
                  label: gettext('Blocked By'),
                  width: 120,
                  accessorFn: (s) => (s.blocking_pids?.length ? s.blocking_pids.join(',') : ''),
                },
                {name: 'query_preview', label: gettext('Query Preview'), width: 260, mono: true},
                {
                  name: 'signal_action',
                  label: gettext('Action'),
                  width: 170,
                  render: (_val, s) =>
                    s.usename ? (
                      <Button variant="secondary" disabled={busy} onClick={() => handleReviewSignal(s.pid)}>
                        {signalKind === 'terminate' ? gettext('Review Terminate') : gettext('Review Cancel')}
                      </Button>
                    ) : null,
                },
              ]}
            />
          )}
          {reviewedSignal && (
            <Stack direction="row" gap="sm">
              <Checkbox
                label={`${gettext('Confirm')} ${reviewedSignal.payload?.signal} PID ${reviewedSignal.payload?.pid}`}
                checked={confirmSignal}
                onChange={setConfirmSignal}
              />
              <Button variant="primary" disabled={busy || !confirmSignal} onClick={handleStartSignal}>
                {gettext('Dispatch Fenced Signal')}
              </Button>
            </Stack>
          )}
        </Stack>
      </PostgresqlSectionCard>

      <PostgresqlSectionCard title={gettext('pg_stat_statements Top Queries & Shared Statistics Reset')}>
        <Stack gap="sm">
          <Grid columns={3} gap="sm">
            <Select
              label={gettext('Sort Top Queries By')}
              value={sortBy}
              options={[
                {value: 'total_exec_time', label: 'Total Execution Time (ms)'},
                {value: 'mean_exec_time', label: 'Mean Execution Time (ms)'},
                {value: 'calls', label: 'Calls'},
                {value: 'rows', label: 'Rows'},
                {value: 'shared_blks_read', label: 'Shared Blocks Read'},
                {value: 'wal_bytes', label: 'WAL Bytes'},
              ]}
              onChange={setSortBy}
            />
            <Select
              label={gettext('Statistics Reset Target')}
              value={resetTarget}
              options={[
                {value: 'pg_stat_statements', label: 'pg_stat_statements_reset()'},
                {value: 'io', label: 'pg_stat_reset_shared(\'io\')'},
                {value: 'wal', label: 'pg_stat_reset_shared(\'wal\')'},
                {value: 'bgwriter', label: 'pg_stat_reset_shared(\'bgwriter\')'},
                {value: 'checkpointer', label: 'pg_stat_reset_shared(\'checkpointer\')'},
                {value: 'archiver', label: 'pg_stat_reset_shared(\'archiver\')'},
              ]}
              onChange={setResetTarget}
            />
            <Box>
              <Button variant="secondary" disabled={busy} onClick={handleReviewReset}>
                {gettext('Review Statistics Reset')}
              </Button>
            </Box>
          </Grid>
          {reviewedReset && (
            <Stack direction="row" gap="sm">
              <Checkbox
                label={`${gettext('Confirm resetting statistics for')} ${reviewedReset.payload?.target}`}
                checked={confirmReset}
                onChange={setConfirmReset}
              />
              <Button variant="primary" disabled={busy || !confirmReset} onClick={handleStartReset}>
                {gettext('Execute Statistics Reset')}
              </Button>
            </Stack>
          )}
          {stmtRows.length > 0 && (
            <UnifiedDataGrid
              caption={gettext('pg_stat_statements Top Queries')}
              searchable
              exportable
              minHeight={160}
              maxHeight={280}
              rows={stmtRows}
              rowKeyGetter={(r, idx) => r.queryid ?? idx}
              columns={[
                {name: 'queryid', label: gettext('Query ID'), width: 130, mono: true},
                {name: 'calls', label: gettext('Calls'), width: 90, numeric: true},
                {name: 'total_exec_time_ms', label: gettext('Total ms'), width: 110, numeric: true},
                {name: 'mean_exec_time_ms', label: gettext('Mean ms'), width: 110, numeric: true},
                {name: 'rows', label: gettext('Rows'), width: 90, numeric: true},
                {name: 'query', label: gettext('Normalized SQL'), width: 320, mono: true},
              ]}
            />
          )}
          {lastOutcome && (
            <CodeEditor
              value={JSON.stringify(lastOutcome, null, 2)}
              language="json"
              readOnly
              height="160px"
            />
          )}
        </Stack>
      </PostgresqlSectionCard>
    </Stack>
  );
}

PostgresqlActivityLocksWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
