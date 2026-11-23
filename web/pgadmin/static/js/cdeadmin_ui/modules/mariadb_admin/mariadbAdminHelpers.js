/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useMemo} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import getApiInstance from 'sources/api_instance';
import {Box, Panel, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Badge, Banner} from '../../feedback/Indicators';

export function stripQueryParams(url) {
  return String(url || '').split('?')[0];
}

export function formatEpoch(ts) {
  if (!ts) return '—';
  const n = Number(ts);
  if (!Number.isFinite(n)) return String(ts);
  return new Date(n * 1000).toISOString().replace('T', ' ').slice(0, 19) + 'Z';
}

export function useMariaDBServerApi(endpointUrl, injectedApi = null) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const serverEndpointUrl = useMemo(() => stripQueryParams(endpointUrl), [endpointUrl]);

  const callServer = useCallback(
    async (payload) => {
      const response = await api.post(serverEndpointUrl, payload);
      const env = response?.data;
      if (env && env.success === 0) {
        throw new Error(env.errormsg || gettext('MariaDB administration request failed.'));
      }
      return env?.data ?? env;
    },
    [api, serverEndpointUrl]
  );

  return {callServer, serverEndpointUrl};
}

export function MariaDBSectionCard({title, children}) {
  return (
    <Panel style={{padding: 12}}>
      <Stack direction="column" gap={2}>
        {title && <strong style={{fontSize: '0.88rem'}}>{title}</strong>}
        {children}
      </Stack>
    </Panel>
  );
}

MariaDBSectionCard.propTypes = {
  title: PropTypes.node,
  children: PropTypes.node,
};

export function MariaDBReviewCard({
  title,
  review,
  idKey = 'job_id',
  busy = false,
  confirmLabel,
  onConfirm,
  onClear,
}) {
  if (!review) return null;
  const recordId = review[idKey] || review.job_id || review.review_id || review.cutover_id || '';
  const warnings = Array.isArray(review.warnings) ? review.warnings : [];

  return (
    <MariaDBSectionCard title={title || gettext('Reviewed MariaDB Operation')}>
      <Stack direction="column" gap={2}>
        <Stack direction="row" gap={1} style={{alignItems: 'center', flexWrap: 'wrap'}}>
          {recordId && <Badge label={String(recordId)} status="info" />}
          {review.state && <Badge label={String(review.state)} status="info" />}
          {review.review_digest && (
            <span style={{fontSize: '0.78rem', fontFamily: 'monospace'}}>
              {gettext('Digest:')} {String(review.review_digest).slice(0, 20)}…
            </span>
          )}
        </Stack>
        {warnings.map((w, idx) => (
          <Banner key={idx} status="warning">
            {w}
          </Banner>
        ))}
        <Box
          style={{
            maxHeight: 220,
            overflow: 'auto',
            padding: '8px',
            borderRadius: 4,
            border: '1px solid var(--cde-border-subtle, #d0d7de)',
            fontFamily: 'monospace',
            fontSize: '0.78rem',
            whiteSpace: 'pre-wrap',
          }}
        >
          {JSON.stringify(
            review.preflight || review.plan || review.preview || review.options || review,
            null,
            2
          )}
        </Box>
        <Stack direction="row" gap={1}>
          <Button intent="primary" disabled={busy} onClick={() => onConfirm(review)}>
            {confirmLabel || gettext('Confirm & Execute')}
          </Button>
          {onClear && (
            <Button intent="neutral" disabled={busy} onClick={onClear}>
              {gettext('Discard Review')}
            </Button>
          )}
        </Stack>
      </Stack>
    </MariaDBSectionCard>
  );
}

MariaDBReviewCard.propTypes = {
  title: PropTypes.string,
  review: PropTypes.object,
  idKey: PropTypes.string,
  busy: PropTypes.bool,
  confirmLabel: PropTypes.string,
  onConfirm: PropTypes.func.isRequired,
  onClear: PropTypes.func,
};

export function MariaDBJobsTable({
  title,
  jobs = [],
  idKey = 'job_id',
  kindKey = 'operation',
  busy = false,
  selectedJob = null,
  onSelect,
  onRefreshJob,
  onCancelJob,
  onReconcileJob,
  extraActions = null,
}) {
  return (
    <MariaDBSectionCard title={title || gettext('Supervised Job Receipts')}>
      <Stack direction="column" gap={2}>
        {jobs.length === 0 ? (
          <Banner status="info">{gettext('No MariaDB supervised jobs recorded yet.')}</Banner>
        ) : (
          <Box style={{overflowX: 'auto'}}>
            <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem'}}>
              <thead>
                <tr style={{textAlign: 'left', borderBottom: '1px solid var(--cde-border-subtle, #d0d7de)'}}>
                  <th style={{padding: '6px'}}>{gettext('ID')}</th>
                  <th style={{padding: '6px'}}>{gettext('Operation / Phase')}</th>
                  <th style={{padding: '6px'}}>{gettext('State')}</th>
                  <th style={{padding: '6px'}}>{gettext('Created')}</th>
                  <th style={{padding: '6px'}}>{gettext('Actions')}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const jid = job[idKey] || job.job_id;
                  const opLabel =
                    job[kindKey] ||
                    job.phase ||
                    job.host_operation ||
                    job.galera_operation ||
                    job.operation ||
                    '—';
                  const badgeStatus =
                    job.state === 'completed' || job.state === 'succeeded'
                      ? 'success'
                      : job.state === 'failed'
                        ? 'error'
                        : 'info';
                  return (
                    <tr
                      key={jid}
                      style={{borderBottom: '1px solid var(--cde-border-subtle, #eaeef2)'}}
                    >
                      <td style={{padding: '6px', fontFamily: 'monospace'}}>{jid}</td>
                      <td style={{padding: '6px'}}>{String(opLabel)}</td>
                      <td style={{padding: '6px'}}>
                        <Badge label={String(job.state || 'unknown')} status={badgeStatus} />
                      </td>
                      <td style={{padding: '6px'}}>{formatEpoch(job.created_at)}</td>
                      <td style={{padding: '6px'}}>
                        <Stack direction="row" gap={1} style={{flexWrap: 'wrap'}}>
                          {onSelect && (
                            <Button intent="neutral" disabled={busy} onClick={() => onSelect(job)}>
                              {gettext('Inspect')}
                            </Button>
                          )}
                          {onRefreshJob && (
                            <Button intent="neutral" disabled={busy} onClick={() => onRefreshJob(jid)}>
                              {gettext('Status')}
                            </Button>
                          )}
                          {onCancelJob && (job.state === 'running' || job.state === 'dispatching') && (
                            <Button intent="destructive" disabled={busy} onClick={() => onCancelJob(jid)}>
                              {gettext('Cancel')}
                            </Button>
                          )}
                          {onReconcileJob && (
                            <Button intent="neutral" disabled={busy} onClick={() => onReconcileJob(jid)}>
                              {gettext('Reconcile')}
                            </Button>
                          )}
                          {extraActions ? extraActions(job) : null}
                        </Stack>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Box>
        )}
        {selectedJob && (
          <Box
            style={{
              maxHeight: 240,
              overflow: 'auto',
              padding: '8px',
              borderRadius: 4,
              border: '1px solid var(--cde-border-subtle, #d0d7de)',
              fontFamily: 'monospace',
              fontSize: '0.78rem',
              whiteSpace: 'pre-wrap',
            }}
          >
            {JSON.stringify(selectedJob, null, 2)}
          </Box>
        )}
      </Stack>
    </MariaDBSectionCard>
  );
}

MariaDBJobsTable.propTypes = {
  title: PropTypes.string,
  jobs: PropTypes.array,
  idKey: PropTypes.string,
  kindKey: PropTypes.string,
  busy: PropTypes.bool,
  selectedJob: PropTypes.object,
  onSelect: PropTypes.func,
  onRefreshJob: PropTypes.func,
  onCancelJob: PropTypes.func,
  onReconcileJob: PropTypes.func,
  extraActions: PropTypes.func,
};
