/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Badge} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {MoveDialog, NameDialog} from './Dialogs';

/**
 * The dashboards of the collection being browsed (the list follows the same
 * selection, search and "show archived" switch as the questions): open to
 * view, edit, rename, move, archive and duplicate through the bi_dashboard_*
 * actions.
 */
export default function DashboardList({
  client, dashboards, collections, searching, activeDashboardId, dirtyDashboardId,
  onOpen, onChanged, onError,
}) {
  const [dialog, setDialog] = useState(null);
  const pathOf = (id) => collections.find((row) => row.id === id)?.path.join(' / ') || '';
  const attempt = (work, changedId) => async (...args) => {
    await work(...args);
    await onChanged(changedId);
  };
  const direct = (work, changedId) => () => attempt(work, changedId)().catch(
    (error) => onError(error?.message || String(error)));
  const blockedHint = gettext('Save or discard the open changes first.');

  return <Box data-cdeadmin-qa-key="bi.dashboard.list">
    <Box component="ul" aria-label={gettext('Dashboards')} sx={{m: 0, p: 0, listStyle: 'none'}}>
      {dashboards.map((dashboard) => {
        const archived = dashboard.status === 'archived';
        const stop = dashboard.dashboard_id === dirtyDashboardId;
        const active = dashboard.dashboard_id === activeDashboardId;
        return <Box component="li" key={dashboard.dashboard_id} aria-current={active ? 'true' : undefined}
          sx={{borderBottom: '1px solid', borderColor: 'divider', py: 0.5, bgcolor: active ? 'action.selected' : 'transparent'}}>
          <Stack direction="row" gap="compact" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
            <Button size="small" aria-label={gettext('Open dashboard %s', dashboard.name)}
              onClick={() => onOpen(dashboard, 'view')}>{dashboard.name}</Button>
            <Badge status="neutral" label={gettext('Dashboard')} />
            {archived && <Badge status="warning" label={gettext('Archived')} />}
            {searching && dashboard.collection_id && <Box component="span" sx={{fontSize: '0.7rem', color: 'text.secondary'}}>
              {pathOf(dashboard.collection_id)}</Box>}
          </Stack>
          <Stack direction="row" gap="compact" role="group" aria-label={gettext('Actions for dashboard %s', dashboard.name)}
            sx={{flexWrap: 'wrap', mt: 0.5}}>
            <Button size="small" aria-label={gettext('Edit dashboard %s', dashboard.name)}
              onClick={() => onOpen(dashboard, 'edit')}>{gettext('Edit')}</Button>
            <Button size="small" disabled={stop} title={stop ? blockedHint : undefined}
              aria-label={gettext('Rename dashboard %s', dashboard.name)}
              onClick={() => setDialog({kind: 'rename', dashboard})}>{gettext('Rename')}</Button>
            <Button size="small" disabled={stop} title={stop ? blockedHint : undefined}
              aria-label={gettext('Move dashboard %s', dashboard.name)}
              onClick={() => setDialog({kind: 'move', dashboard})}>{gettext('Move')}</Button>
            <Button size="small" disabled={stop} title={stop ? blockedHint : undefined}
              aria-label={archived ? gettext('Restore dashboard %s', dashboard.name) : gettext('Archive dashboard %s', dashboard.name)}
              onClick={direct(() => client.setDashboardStatus(dashboard.dashboard_id, dashboard.revision,
                archived ? 'active' : 'archived'), dashboard.dashboard_id)}>
              {archived ? gettext('Restore') : gettext('Archive')}</Button>
            <Button size="small" aria-label={gettext('Duplicate dashboard %s', dashboard.name)}
              onClick={() => setDialog({kind: 'clone', dashboard})}>{gettext('Duplicate')}</Button>
          </Stack>
        </Box>;
      })}
      {dashboards.length === 0 && <li><EmptyState message={searching ?
        gettext('No dashboard matches the search.') : gettext('No dashboards here yet.')} /></li>}
    </Box>

    {dialog?.kind === 'rename' && <NameDialog open title={gettext('Rename dashboard')}
      label={gettext('Dashboard name')} initial={dialog.dashboard.name} confirmLabel={gettext('Rename')}
      onClose={() => setDialog(null)}
      onConfirm={attempt(async (name) => {
        const record = await client.getDashboard(dialog.dashboard.dashboard_id);
        await client.updateDashboard(record.dashboard_id, record.revision, {...record.definition, name});
      }, dialog.dashboard.dashboard_id)} />}
    {dialog?.kind === 'move' && <MoveDialog open title={gettext('Move dashboard')}
      targets={collections} current={dialog.dashboard.collection_id ?? null} onClose={() => setDialog(null)}
      onConfirm={attempt((collectionId) => client.moveDashboard(
        dialog.dashboard.dashboard_id, dialog.dashboard.revision, collectionId), dialog.dashboard.dashboard_id)} />}
    {dialog?.kind === 'clone' && <NameDialog open title={gettext('Duplicate dashboard')}
      label={gettext('Name of the copy')} initial={gettext('Copy of %s', dialog.dashboard.name)}
      confirmLabel={gettext('Duplicate')} onClose={() => setDialog(null)}
      onConfirm={attempt((name) => client.cloneDashboard(dialog.dashboard.dashboard_id, name))} />}
  </Box>;
}

DashboardList.propTypes = {
  client: PropTypes.object.isRequired,
  dashboards: PropTypes.array.isRequired,
  collections: PropTypes.array.isRequired,
  searching: PropTypes.bool,
  activeDashboardId: PropTypes.string,
  dirtyDashboardId: PropTypes.string,
  onOpen: PropTypes.func.isRequired,
  onChanged: PropTypes.func.isRequired,
  onError: PropTypes.func.isRequired,
};
