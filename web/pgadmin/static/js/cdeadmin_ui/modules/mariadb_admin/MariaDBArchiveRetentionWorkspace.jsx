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
import {Checkbox} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import {
  MariaDBJobsTable,
  MariaDBReviewCard,
  MariaDBSectionCard,
  useMariaDBServerApi,
} from './mariadbAdminHelpers';

/**
 * MDB-UI-02 (SR-F-030341): MariaDB Dependency-Aware Binary-Log Retention,
 * Protection Holds & PITR Recovery Chains Workspace (`tab="mariadb-archive-retention"`).
 */
export default function MariaDBArchiveRetentionWorkspace({endpointUrl, api = null}) {
  const {callServer} = useMariaDBServerApi(endpointUrl, api);

  const [holds, setHolds] = useState([]);
  const [chains, setChains] = useState([]);
  const [retentionJobs, setRetentionJobs] = useState([]);
  const [evaluation, setEvaluation] = useState(null);
  const [activeReview, setActiveReview] = useState(null);
  const [reviewKind, setReviewKind] = useState('');
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // Retention Policy
  const [keepCount, setKeepCount] = useState(5);
  const [maxAgeDays, setMaxAgeDays] = useState(14);

  // Uncertain hold recording
  const [originOperation, setOriginOperation] = useState('mariadb_physical_backup');
  const [originJobId, setOriginJobId] = useState('');
  const [sourceUid, setSourceUid] = useState('');
  const [uncertaintyReason, setUncertaintyReason] = useState('');
  const [reconciliationAck, setReconciliationAck] = useState(true);

  // Recovery Chain authoring
  const [chainBackupJobId, setChainBackupJobId] = useState('');
  const [chainArchiveIdsCsv, setChainArchiveIdsCsv] = useState('');
  const [chainStopGtid, setChainStopGtid] = useState('');

  const loadAll = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [holdRes, chainRes, retRes] = await Promise.all([
        callServer({action: 'mariadb_binlog_hold_list', request: {offset: 0, limit: 50}}).catch(() => ({holds: []})),
        callServer({action: 'mariadb_binlog_recovery_chain_list', request: {offset: 0, limit: 50}}).catch(() => ({chains: []})),
        callServer({action: 'mariadb_binlog_retention_list', request: {offset: 0, limit: 25}}).catch(() => ({jobs: []})),
      ]);
      setHolds(holdRes?.holds || holdRes?.items || []);
      setChains(chainRes?.chains || chainRes?.items || []);
      setRetentionJobs(retRes?.jobs || retRes?.items || []);
    } catch (err) {
      setError(err.message || gettext('Failed to load MariaDB retention holds and chains.'));
    } finally {
      setBusy(false);
    }
  }, [callServer]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const buildPolicy = () => ({
    keep_latest: Number(keepCount) || 5,
    max_age_seconds: (Number(maxAgeDays) || 14) * 86400,
  });

  const handleEvaluateRetention = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_binlog_retention_evaluate',
        request: {policy: buildPolicy()},
      });
      setEvaluation(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleReviewRetention = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_binlog_retention_review',
        request: {policy: buildPolicy()},
      });
      setReviewKind('retention_start');
      setActiveReview(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRecordUncertainHold = async () => {
    setBusy(true);
    setError('');
    try {
      await callServer({
        action: 'mariadb_binlog_hold_record_uncertain',
        request: {
          origin_operation: originOperation.trim(),
          origin_job_id: originJobId.trim(),
          source_uid: sourceUid.trim(),
          uncertainty_reason: uncertaintyReason.trim(),
        },
      });
      setNotice(gettext('Recorded MariaDB uncertain-outcome hold protecting dependent binlog archives.'));
      setOriginJobId('');
      setUncertaintyReason('');
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleReviewRetireHold = async (holdId) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_binlog_hold_review_retire',
        request: {hold_id: holdId},
      });
      setReviewKind('hold_retire');
      setActiveReview(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleReviewRecoveryChain = async () => {
    setBusy(true);
    setError('');
    try {
      const archiveIds = chainArchiveIdsCsv
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await callServer({
        action: 'mariadb_binlog_recovery_chain_review',
        request: {
          backup_job_id: chainBackupJobId.trim(),
          archive_job_ids: archiveIds,
          ...(chainStopGtid.trim() ? {stop_gtid: chainStopGtid.trim()} : {}),
        },
      });
      setReviewKind('chain_activate');
      setActiveReview(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleReviewRetireChain = async (chainId) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'mariadb_binlog_recovery_chain_review_retire',
        request: {chain_id: chainId},
      });
      setReviewKind('chain_retire');
      setActiveReview(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmReview = async (rev) => {
    setBusy(true);
    setError('');
    try {
      if (reviewKind === 'retention_start') {
        await callServer({
          action: 'mariadb_binlog_retention_start',
          request: {
            job_id: rev.job_id || rev.review_id,
            review_digest: rev.review_digest,
            confirmed: true,
          },
        });
        setNotice(gettext('Started MariaDB dependency-aware archive retention job.'));
      } else if (reviewKind === 'hold_retire') {
        await callServer({
          action: 'mariadb_binlog_hold_retire',
          request: {
            review_id: rev.review_id,
            review_digest: rev.review_digest,
            confirmed: true,
            ...(reconciliationAck ? {reconciliation_acknowledged: true} : {}),
          },
        });
        setNotice(gettext('Retired MariaDB archive protection hold.'));
      } else if (reviewKind === 'chain_activate') {
        await callServer({
          action: 'mariadb_binlog_recovery_chain_activate',
          request: {
            review_id: rev.review_id,
            review_digest: rev.review_digest,
            confirmed: true,
          },
        });
        setNotice(gettext('Activated MariaDB PITR recovery chain protection.'));
      } else if (reviewKind === 'chain_retire') {
        await callServer({
          action: 'mariadb_binlog_recovery_chain_retire',
          request: {
            review_id: rev.review_id,
            review_digest: rev.review_digest,
            confirmed: true,
          },
        });
        setNotice(gettext('Retired MariaDB PITR recovery chain.'));
      }
      setActiveReview(null);
      setReviewKind('');
      await loadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box style={{padding: '12px', overflow: 'auto'}} data-testid="mariadb-archive-retention-workspace">
      <Stack direction="column" gap={3}>
        <Stack direction="row" style={{flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between'}}>
          <Stack direction="row" gap={1} style={{alignItems: 'center'}}>
            <strong>{gettext('MariaDB Binary-Log Archive Retention, Holds & Recovery Chains')}</strong>
            <FormReference formKey="mariadb-archive-retention-workspace" />
          </Stack>
          <Button size="sm" intent="neutral" disabled={busy} onClick={loadAll}>
            {gettext('Refresh Holds & Chains')}
          </Button>
        </Stack>

        {error && <ValidationMessage status="error">{error}</ValidationMessage>}
        {notice && <Banner status="success">{notice}</Banner>}

        <MariaDBSectionCard title={gettext('Dependency-Aware Archive Retention Policy')}>
          <Stack direction="column" gap={2}>
            <Grid columns={2} gap={2}>
              <NumberField
                label={gettext('Keep Latest Verified Archives')}
                value={keepCount}
                min={1}
                max={500}
                onChange={(e) => setKeepCount(Number(e.target.value))}
              />
              <NumberField
                label={gettext('Maximum Archive Age (days)')}
                value={maxAgeDays}
                min={1}
                max={3650}
                onChange={(e) => setMaxAgeDays(Number(e.target.value))}
              />
            </Grid>
            <Stack direction="row" gap={1}>
              <Button intent="neutral" disabled={busy} onClick={handleEvaluateRetention}>
                {gettext('Evaluate Protected vs Eligible Archives')}
              </Button>
              <Button intent="primary" disabled={busy} onClick={handleReviewRetention}>
                {gettext('Review Retention Purge')}
              </Button>
            </Stack>
            {evaluation && (
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
                {JSON.stringify(evaluation, null, 2)}
              </Box>
            )}
          </Stack>
        </MariaDBSectionCard>

        <MariaDBSectionCard title={gettext('Protection Holds & Uncertain-Outcome Hold Registration')}>
          <Stack direction="column" gap={2}>
            <Grid columns={4} gap={2}>
              <TextField
                label={gettext('Origin Operation')}
                value={originOperation}
                onChange={(e) => setOriginOperation(e.target.value)}
              />
              <TextField
                label={gettext('Origin Job ID')}
                value={originJobId}
                onChange={(e) => setOriginJobId(e.target.value)}
              />
              <TextField
                label={gettext('MariaDB Server UID')}
                value={sourceUid}
                onChange={(e) => setSourceUid(e.target.value)}
              />
              <TextField
                label={gettext('Uncertainty / Hold Reason')}
                value={uncertaintyReason}
                onChange={(e) => setUncertaintyReason(e.target.value)}
              />
            </Grid>
            <Stack direction="row" gap={2} style={{alignItems: 'center'}}>
              <Button
                intent="neutral"
                disabled={busy || !originJobId.trim() || !sourceUid.trim() || !uncertaintyReason.trim()}
                onClick={handleRecordUncertainHold}
              >
                {gettext('Record Uncertain Hold')}
              </Button>
              <Checkbox
                label={gettext('Acknowledge manual outcome reconciliation when retiring uncertain holds')}
                checked={reconciliationAck}
                onChange={(checked) => setReconciliationAck(Boolean(checked))}
              />
            </Stack>

            {holds.length === 0 ? (
              <Banner status="info">{gettext('No active MariaDB backup or uncertain holds.')}</Banner>
            ) : (
              <Stack direction="column" gap={1}>
                {holds.map((h) => (
                  <Stack
                    key={h.hold_id}
                    direction="row"
                    style={{alignItems: 'center', justifyContent: 'space-between', padding: '6px 8px', border: '1px solid var(--cde-border-subtle, #eaeef2)'}}
                  >
                    <Stack direction="row" gap={1} style={{flexWrap: 'wrap', alignItems: 'center'}}>
                      <Badge status="info" label={h.hold_kind || 'hold'} />
                      <code>{h.hold_id}</code>
                      <Badge status={h.state === 'retired' ? 'neutral' : 'info'} label={h.state} />
                      {h.gtid_pos && <code>{h.gtid_pos}</code>}
                    </Stack>
                    {h.state !== 'retired' && (
                      <Button
                        size="sm"
                        intent="neutral"
                        disabled={busy}
                        onClick={() => handleReviewRetireHold(h.hold_id)}
                      >
                        {gettext('Review Retire')}
                      </Button>
                    )}
                  </Stack>
                ))}
              </Stack>
            )}
          </Stack>
        </MariaDBSectionCard>

        <MariaDBSectionCard title={gettext('Verified PITR Recovery Chains')}>
          <Stack direction="column" gap={2}>
            <Grid columns={3} gap={2}>
              <TextField
                label={gettext('Active Physical Backup Hold Job ID')}
                value={chainBackupJobId}
                onChange={(e) => setChainBackupJobId(e.target.value)}
              />
              <TextField
                label={gettext('Ordered Archive Job IDs (comma-separated)')}
                value={chainArchiveIdsCsv}
                onChange={(e) => setChainArchiveIdsCsv(e.target.value)}
              />
              <TextField
                label={gettext('Canonical Stop GTID (optional)')}
                value={chainStopGtid}
                onChange={(e) => setChainStopGtid(e.target.value)}
              />
            </Grid>
            <Stack direction="row" gap={1}>
              <Button
                intent="primary"
                disabled={busy || !chainBackupJobId.trim() || !chainArchiveIdsCsv.trim()}
                onClick={handleReviewRecoveryChain}
              >
                {gettext('Review Recovery Chain')}
              </Button>
            </Stack>
            {chains.map((ch) => (
              <Stack
                key={ch.chain_id}
                direction="row"
                style={{alignItems: 'center', justifyContent: 'space-between', padding: '6px 8px', border: '1px solid var(--cde-border-subtle, #eaeef2)'}}
              >
                <Stack direction="row" gap={1} style={{alignItems: 'center'}}>
                  <code>{ch.chain_id}</code>
                  <Badge status={ch.state === 'active' ? 'success' : 'neutral'} label={ch.state} />
                </Stack>
                {ch.state !== 'retired' && (
                  <Button
                    size="sm"
                    intent="neutral"
                    disabled={busy}
                    onClick={() => handleReviewRetireChain(ch.chain_id)}
                  >
                    {gettext('Review Retire Chain')}
                  </Button>
                )}
              </Stack>
            ))}
          </Stack>
        </MariaDBSectionCard>

        <MariaDBReviewCard
          title={gettext('Retention / Hold / Chain Review')}
          review={activeReview}
          idKey="review_id"
          busy={busy}
          onConfirm={handleConfirmReview}
          onClear={() => setActiveReview(null)}
        />

        <MariaDBJobsTable
          title={gettext('Retention Purge Jobs')}
          jobs={retentionJobs}
          busy={busy}
          selectedJob={selectedRecord}
          onSelect={setSelectedRecord}
          onRefreshJob={async (jid) => {
            const st = await callServer({action: 'mariadb_binlog_retention_status', request: {job_id: jid}});
            setSelectedRecord(st);
            await loadAll();
          }}
          onCancelJob={async (jid) => {
            await callServer({action: 'mariadb_binlog_retention_cancel', request: {job_id: jid}});
            await loadAll();
          }}
          onReconcileJob={async (jid) => {
            await callServer({action: 'mariadb_binlog_retention_reconcile', request: {job_id: jid}});
            await loadAll();
          }}
        />
      </Stack>
    </Box>
  );
}

MariaDBArchiveRetentionWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
