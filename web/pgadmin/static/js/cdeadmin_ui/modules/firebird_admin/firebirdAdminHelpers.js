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
import getApiInstance from '../../../api_instance';
import {Box, Grid, Panel, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Select} from '../../primitives/Choice';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import CodeEditor from '../../editors/CodeEditor';

/**
 * Strip or set `database_target_id` on an endpoint workspace URL so that
 * `servers/__init__.py` (`scoped_target`) always matches `request.database_target_id`.
 */
export function buildScopedEndpointUrl(baseEndpointUrl, targetId) {
  const raw = String(baseEndpointUrl || '');
  if (!raw) return '';
  const qIndex = raw.indexOf('?');
  const pathPart = qIndex >= 0 ? raw.slice(0, qIndex) : raw;
  const params = new URLSearchParams(qIndex >= 0 ? raw.slice(qIndex + 1) : '');
  if (targetId) {
    params.set('database_target_id', targetId);
  } else {
    params.delete('database_target_id');
  }
  const qs = params.toString();
  return qs ? `${pathPart}?${qs}` : pathPart;
}

export function extractApiError(error) {
  return (
    error?.response?.data?.errormsg ||
    error?.response?.data?.info ||
    error?.message ||
    String(error)
  );
}

export function createScopedPoster(baseEndpointUrl, targetId, customApi = null) {
  const api = customApi || getApiInstance();
  const url = buildScopedEndpointUrl(baseEndpointUrl, targetId);
  return async (payload) => {
    try {
      const response = await api.post(url, payload);
      return response?.data?.data !== undefined ? response.data.data : response?.data;
    } catch (error) {
      throw new Error(extractApiError(error));
    }
  };
}

export function formatUnixTimestamp(epochSeconds) {
  if (!epochSeconds || typeof epochSeconds !== 'number') return '—';
  try {
    return new Date(epochSeconds * 1000).toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  } catch {
    return String(epochSeconds);
  }
}

export function useFirebirdTargetScope(endpointUrl, initialTargetId, requireTarget = false, customPost = null) {
  const [targets, setTargets] = useState([]);
  const [selectedTargetId, setSelectedTargetId] = useState(initialTargetId || '');
  const [targetsLoading, setTargetsLoading] = useState(false);
  const [targetsError, setTargetsError] = useState('');

  const rootPost = useMemo(
    () => customPost || createScopedPoster(endpointUrl, null),
    [customPost, endpointUrl]
  );

  useEffect(() => {
    if (initialTargetId) {
      setSelectedTargetId(initialTargetId);
    }
  }, [initialTargetId]);

  const reloadTargets = useCallback(async () => {
    setTargetsLoading(true);
    setTargetsError('');
    try {
      const data = await rootPost({action: 'database_target_list', request: {}});
      const items = Array.isArray(data?.targets) ? data.targets : [];
      setTargets(items);
      if (!selectedTargetId && requireTarget && items.length > 0) {
        const preferred = items.find((t) => t.active) || items[0];
        if (preferred?.target_id) {
          setSelectedTargetId(preferred.target_id);
        }
      }
    } catch (err) {
      setTargetsError(extractApiError(err));
    } finally {
      setTargetsLoading(false);
    }
  }, [requireTarget, rootPost, selectedTargetId]);

  useEffect(() => {
    reloadTargets();
  }, [reloadTargets]);

  const post = useMemo(() => {
    if (customPost) {
      return async (payload) => {
        const req = payload?.request && selectedTargetId
          ? {...payload.request, database_target_id: selectedTargetId}
          : payload?.request;
        return customPost({...payload, ...(req ? {request: req} : {})});
      };
    }
    return createScopedPoster(endpointUrl, selectedTargetId || null);
  }, [customPost, endpointUrl, selectedTargetId]);

  const selectedTarget = useMemo(
    () => targets.find((t) => t.target_id === selectedTargetId) || null,
    [targets, selectedTargetId]
  );

  return {
    targets,
    selectedTargetId,
    setSelectedTargetId,
    selectedTarget,
    targetsLoading,
    targetsError,
    reloadTargets,
    post,
  };
}

export function DatabaseTargetPickerBar({
  targets,
  selectedTargetId,
  onSelectTarget,
  allowServerScope = false,
  disabled = false,
  onRefresh,
}) {
  const options = useMemo(() => {
    const base = allowServerScope
      ? [{value: '', label: gettext('Server scope (no specific database)')}]
      : [];
    return [
      ...base,
      ...targets.map((t) => ({
        value: t.target_id,
        label: `${t.display_name || t.target_id}${t.database_name ? ` (${t.database_name})` : ''}`,
      })),
    ];
  }, [allowServerScope, targets]);

  return (
    <Panel variant="outlined" style={{padding: '10px 12px'}}>
      <Stack direction="row" gap="standard" style={{alignItems: 'flex-end', flexWrap: 'wrap'}}>
        <Box style={{minWidth: 280, flex: 1}}>
          <Select
            label={gettext('Target Firebird database registration')}
            size="small"
            fullWidth
            disabled={disabled || (!allowServerScope && options.length === 0)}
            options={options.length ? options : [{value: '', label: gettext('No registered databases found')}]}
            value={selectedTargetId || ''}
            onChange={(val) => onSelectTarget(val)}
          />
        </Box>
        {onRefresh && (
          <Button intent="neutral" size="small" disabled={disabled} onClick={onRefresh}>
            {gettext('Refresh')}
          </Button>
        )}
      </Stack>
    </Panel>
  );
}

DatabaseTargetPickerBar.propTypes = {
  targets: PropTypes.array.isRequired,
  selectedTargetId: PropTypes.string,
  onSelectTarget: PropTypes.func.isRequired,
  allowServerScope: PropTypes.bool,
  disabled: PropTypes.bool,
  onRefresh: PropTypes.func,
};

export function ReviewConfirmationCard({
  review,
  title,
  previewLabel,
  previewText,
  previewLanguage = 'text',
  busy = false,
  onApply,
  onDiscard,
}) {
  if (!review) return null;
  return (
    <Panel
      variant="outlined"
      data-cdeadmin-qa-key="firebird-admin.review-card"
      style={{padding: 12}}
    >
      <Stack gap="standard">
        <Stack direction="row" gap="standard" style={{alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap'}}>
          <Box component="h4" sx={{m: 0, fontSize: '0.875rem', fontWeight: 600}}>
            {title || gettext('Reviewed One-Use Native Action')}
          </Box>
          <Badge label={review.state || 'reviewed'} status="info" />
        </Stack>
        <Grid columns="repeat(auto-fit, minmax(220px, 1fr))">
          <Box sx={{fontSize: '0.75rem'}}>
            <strong>{gettext('Review ID')}:</strong> {review.review_id}
          </Box>
          <Box sx={{fontSize: '0.75rem'}}>
            <strong>{gettext('Digest')}:</strong>{' '}
            <code>{String(review.review_digest || '').slice(0, 16)}…</code>
          </Box>
          <Box sx={{fontSize: '0.75rem'}}>
            <strong>{gettext('Expires')}:</strong> {formatUnixTimestamp(review.expires_at)}
          </Box>
        </Grid>
        {previewText && (
          <CodeEditor
            label={previewLabel || gettext('Reviewed configuration / command')}
            readonly
            language={previewLanguage}
            value={previewText}
          />
        )}
        <Banner status="warning">
          {gettext('Applying claims this review once. Network or host interruption leaves an explicit non-replayable outcome receipt.')}
        </Banner>
        <Stack direction="row" gap="standard" style={{justifyContent: 'flex-end'}}>
          {onDiscard && (
            <Button intent="neutral" size="small" disabled={busy} onClick={onDiscard}>
              {gettext('Discard Review')}
            </Button>
          )}
          <Button
            intent="primary"
            size="small"
            loading={busy}
            disabled={busy}
            onClick={() =>
              onApply({
                review_id: review.review_id,
                review_digest: review.review_digest,
                confirmed: true,
              })
            }
          >
            {gettext('Confirm & Apply Reviewed Operation')}
          </Button>
        </Stack>
      </Stack>
    </Panel>
  );
}

ReviewConfirmationCard.propTypes = {
  review: PropTypes.object,
  title: PropTypes.string,
  previewLabel: PropTypes.string,
  previewText: PropTypes.string,
  previewLanguage: PropTypes.string,
  busy: PropTypes.bool,
  onApply: PropTypes.func.isRequired,
  onDiscard: PropTypes.func,
};

export function ReceiptHistoryPanel({items = [], onInspectReceipt, selectedReceipt = null, error = ''}) {
  return (
    <Panel variant="outlined" style={{padding: 12}}>
      <Stack gap="standard">
        <Box component="h4" sx={{m: 0, fontSize: '0.875rem', fontWeight: 600}}>
          {gettext('Durable Operation Reviews & Outcome Receipts')} ({items.length})
        </Box>
        {error && <ValidationMessage status="error">{error}</ValidationMessage>}
        {items.length === 0 ? (
          <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
            {gettext('No retained reviews or receipts recorded for this owner and scope.')}
          </Box>
        ) : (
          <Box component="table" sx={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem'}}>
            <thead>
              <tr>
                <th style={{textAlign: 'left', padding: '4px 8px'}}>{gettext('Created')}</th>
                <th style={{textAlign: 'left', padding: '4px 8px'}}>{gettext('Operation')}</th>
                <th style={{textAlign: 'left', padding: '4px 8px'}}>{gettext('State')}</th>
                <th style={{textAlign: 'left', padding: '4px 8px'}}>{gettext('Review ID')}</th>
                <th style={{textAlign: 'right', padding: '4px 8px'}}>{gettext('Inspect')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const rid = item.review_id || item.trace_id;
                const st = item.outcome?.state || item.outcome_summary?.state || item.state || 'unknown';
                return (
                  <tr key={rid} style={{borderTop: '1px solid rgba(128,128,128,0.2)'}}>
                    <td style={{padding: '4px 8px'}}>{formatUnixTimestamp(item.created_at || item.started_at)}</td>
                    <td style={{padding: '4px 8px'}}>{item.operation || item.payload?.options?.mode || 'execute'}</td>
                    <td style={{padding: '4px 8px'}}>
                      <Badge
                        label={st}
                        status={
                          ['completed', 'submitted', 'active', 'stopped'].includes(st)
                            ? 'success'
                            : ['rejected', 'failed', 'expired', 'unknown_outcome'].includes(st)
                              ? 'error'
                              : 'info'
                        }
                      />
                    </td>
                    <td style={{padding: '4px 8px'}}><code>{String(rid).slice(0, 12)}…</code></td>
                    <td style={{padding: '4px 8px', textAlign: 'right'}}>
                      {onInspectReceipt && (
                        <Button intent="neutral" size="small" onClick={() => onInspectReceipt(rid)}>
                          {gettext('Details')}
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Box>
        )}
        {selectedReceipt && (
          <CodeEditor
            label={gettext('Selected durable receipt (credential-free)')}
            readonly
            language="json"
            value={JSON.stringify(selectedReceipt, null, 2)}
          />
        )}
      </Stack>
    </Panel>
  );
}

ReceiptHistoryPanel.propTypes = {
  items: PropTypes.array,
  onInspectReceipt: PropTypes.func,
  selectedReceipt: PropTypes.object,
  error: PropTypes.string,
};
