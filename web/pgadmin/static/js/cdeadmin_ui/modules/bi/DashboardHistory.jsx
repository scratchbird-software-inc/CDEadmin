/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Badge, Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {Dialog} from '../../overlays/Dialog';

function when(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

/** One line describing what a revision's document holds. */
export function revisionSummary(definition) {
  return gettext('%s tabs, %s cards, %s filters, %s cross-filters, %s drill-throughs',
    definition.tabs?.length ?? 0, definition.cards?.length ?? 0, definition.filters?.length ?? 0,
    definition.cross_filters?.length ?? 0, definition.drill_throughs?.length ?? 0);
}

/**
 * Immutable revisions of a stored dashboard (bi_dashboard_history,
 * bi_dashboard_revision). Restoring loads a revision into the editor as an
 * unsaved draft; the next save appends a new revision and nothing is lost.
 */
export default function DashboardHistory({client, dashboardId, currentRevision, onRestore, onClose, canRestore = true}) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  const [summaries, setSummaries] = useState({});
  const [busy, setBusy] = useState('');

  useEffect(() => {
    let cancelled = false;
    client.dashboardHistory(dashboardId).then(
      (history) => { if(!cancelled) setItems(history); },
      (caught) => { if(!cancelled) setError(caught?.message || String(caught)); });
    return () => { cancelled = true; };
  }, [client, dashboardId]);

  const attempt = async (key, work) => {
    setBusy(key);
    setError('');
    try { await work(); } catch(caught) { setError(caught?.message || String(caught)); } finally { setBusy(''); }
  };
  const summarize = (revision) => attempt(`summary-${revision}`, async () => {
    const record = await client.dashboardRevision(dashboardId, revision);
    setSummaries((current) => ({...current, [revision]: revisionSummary(record.definition)}));
  });
  const restore = (revision) => attempt(`restore-${revision}`, async () => {
    const record = await client.dashboardRevision(dashboardId, revision);
    onRestore(record.definition, revision);
    onClose();
  });

  return <Dialog open title={gettext('Dashboard revision history')} size="large" onClose={onClose}
    actions={<Button onClick={onClose}>{gettext('Close')}</Button>}>
    <Stack>
      {error && <Banner status="error">{error}</Banner>}
      {!items && !error && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Loading revisions...')}</Box>}
      {items && items.length === 0 && <EmptyState message={gettext('This dashboard has no revisions.')} />}
      {items && items.length > 0 && <Box component="ul" aria-label={gettext('Revisions')} sx={{m: 0, p: 0, listStyle: 'none'}}>
        {items.map((item) => <Box component="li" key={item.revision}
          sx={{display: 'flex', alignItems: 'center', gap: 1, py: 0.5, borderBottom: '1px solid', borderColor: 'divider', flexWrap: 'wrap'}}>
          <Box sx={{flex: 1, minWidth: 160}}>
            <strong>{gettext('Revision %s', item.revision)}</strong>{' '}
            <Box component="span" sx={{fontSize: '0.75rem', color: 'text.secondary'}}>{when(item.created_at)}</Box>
            {item.actor_user_id != null && <Box component="span" sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
              {' '}{item.actor ? gettext('saved by %s', item.actor) : gettext('saved by another user')}</Box>}
            {summaries[item.revision] && <Box sx={{fontSize: '0.75rem'}}>{summaries[item.revision]}</Box>}
          </Box>
          {item.revision === currentRevision && <Badge status="success" label={gettext('Current')} />}
          {item.status === 'archived' && <Badge status="warning" label={gettext('Archived')} />}
          <Button size="small" loading={busy === `summary-${item.revision}`}
            aria-label={gettext('Summarize revision %s', item.revision)}
            onClick={() => summarize(item.revision)}>{gettext('Summary')}</Button>
          {canRestore && <Button size="small" loading={busy === `restore-${item.revision}`}
            aria-label={gettext('Restore revision %s', item.revision)}
            onClick={() => restore(item.revision)}>{gettext('Restore as draft')}</Button>}
        </Box>)}
      </Box>}
    </Stack>
  </Dialog>;
}

DashboardHistory.propTypes = {
  client: PropTypes.shape({dashboardHistory: PropTypes.func.isRequired, dashboardRevision: PropTypes.func.isRequired}).isRequired,
  dashboardId: PropTypes.string.isRequired,
  currentRevision: PropTypes.number,
  onRestore: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
  canRestore: PropTypes.bool,
};
