/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Select} from '../../primitives/Choice';
import {Badge, Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {Dialog} from '../../overlays/Dialog';
import {AUTO_REFRESH_CHOICES} from './dashboardState';
import {refreshLabel} from './dashboardViewer';
import {infoKey} from './dashboardMapping';
import useDashboardViewer from './useDashboardViewer';
import LayoutGrid from './LayoutGrid';
import PanelTabs from './PanelTabs';
import FilterBar from './FilterBar';
import ViewerCard from './ViewerCard';

const message = (error) => error?.message || String(error);

function Fullscreen({title, onClose, children}) {
  const ref = useRef(null);
  // Focus moves into the overlay and returns to the control that opened it.
  useEffect(() => {
    const opener = document.activeElement;
    ref.current?.focus();
    return () => { if(opener && opener.isConnected) opener.focus?.(); };
  }, []);
  return <Box role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}
    onKeyDown={(event) => { if(event.key === 'Escape') { event.stopPropagation(); onClose(); } }}
    sx={{position: 'fixed', inset: 0, zIndex: 1300, bgcolor: 'background.default', p: 2, overflow: 'auto'}}>
    <Box sx={{height: '100%', minHeight: 240}}>{children}</Box>
  </Box>;
}

Fullscreen.propTypes = {title: PropTypes.string.isRequired, onClose: PropTypes.func.isRequired, children: PropTypes.node};

/** The board of one loaded dashboard. */
function Board({client, record, initial, onDrill}) {
  const dashboard = record.definition;
  const dashboardId = record.dashboard_id;
  const viewer = useDashboardViewer({client, dashboardId, dashboard, initial, onDrill});
  const {state, infos} = viewer;
  const links = (card) => dashboard.cross_filters.some((link) => link.source_card_id === card.id) ||
    dashboard.drill_throughs.some((drill) => drill.source_card_id === card.id);
  const renderCard = (card, fullscreen = false) => <ViewerCard card={card} run={state.cards[card.id]}
    info={card.question ? infos[infoKey(card.question)] : undefined}
    interactive={card.type === 'question' && links(card)} fullscreen={fullscreen}
    onRefresh={viewer.refreshCard} onFullscreen={viewer.setFullscreen} onActivate={viewer.activate} />;
  const full = state.fullscreen ? dashboard.cards.find((card) => card.id === state.fullscreen) : null;
  const refreshChoices = [...new Set([...AUTO_REFRESH_CHOICES, viewer.refreshSeconds])].sort((a, b) => a - b);
  const tab = dashboard.tabs.find((item) => item.id === state.tabId) || dashboard.tabs[0];
  return <Box data-cdeadmin-qa-key="bi.dashboard.view" sx={{display: 'grid', gap: 1, minWidth: 0}}>
    <Stack direction="row" gap="comfortable" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
      <Box component="h2" sx={{m: 0, fontSize: '1.125rem', flex: 1, minWidth: 160}}>{dashboard.name}</Box>
      <Badge status="neutral" label={gettext('Revision %s', record.revision)} />
      <Select size="small" label={gettext('Auto-refresh')} value={viewer.refreshSeconds}
        options={refreshChoices.map((seconds) => ({value: seconds, label: refreshLabel(seconds)}))}
        onChange={(seconds) => viewer.setRefreshSeconds(Number(seconds))} />
      <Button onClick={viewer.refreshAll}>{gettext('Refresh all cards')}</Button>
    </Stack>
    {dashboard.description && <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>{dashboard.description}</Box>}
    {viewer.notice && <Banner status="error" onClose={() => viewer.setNotice('')}>{viewer.notice}</Banner>}
    <FilterBar dashboard={dashboard} values={state.values} missing={viewer.missing} onApply={viewer.setValues} />
    {dashboard.tabs.length > 1 && <PanelTabs label={gettext('Dashboard tabs')} ids={dashboard.tabs.map((item) => item.id)}
      labelOf={(id) => dashboard.tabs.find((item) => item.id === id)?.name || id}
      active={tab.id} onChange={viewer.selectTab} />}
    <Box role="tabpanel" aria-label={tab.name}>
      {dashboard.cards.every((card) => card.tab_id !== tab.id) ?
        <EmptyState message={gettext('This tab has no cards.')} /> :
        <LayoutGrid cards={dashboard.cards} tabId={tab.id} label={gettext('Cards of %s', tab.name)}
          renderCard={(card) => renderCard(card)} />}
    </Box>
    {full && <Fullscreen title={gettext('%s in full screen', full.title || full.id)}
      onClose={() => viewer.setFullscreen(null)}>{renderCard(full, true)}</Fullscreen>}
    {viewer.choices && <Dialog open title={gettext('What should this click do?')} onClose={() => viewer.setChoices(null)}
      actions={<Button onClick={() => viewer.setChoices(null)}>{gettext('Cancel')}</Button>}>
      <Stack>
        {viewer.choices.items.map((item) => <Button key={`${item.kind}-${item.id}`}
          onClick={() => viewer.perform(item, viewer.choices.row)}>{item.label}</Button>)}
      </Stack>
    </Dialog>}
  </Box>;
}

Board.propTypes = {
  client: PropTypes.object.isRequired, record: PropTypes.object.isRequired,
  initial: PropTypes.object, onDrill: PropTypes.func,
};

/**
 * Loads a stored dashboard (its latest saved revision) and shows it. The
 * board is display and interaction only: layout and mapping are edited in the
 * editor, never here.
 */
export default function DashboardView({client, dashboardId, initial, onDrill, onLoaded}) {
  const [loaded, setLoaded] = useState({status: 'loading', record: null, error: ''});
  useEffect(() => {
    let cancelled = false;
    setLoaded({status: 'loading', record: null, error: ''});
    client.getDashboard(dashboardId).then(
      (record) => {
        if(cancelled) return;
        setLoaded({status: 'ready', record, error: ''});
        onLoaded?.(record);
      },
      (error) => { if(!cancelled) setLoaded({status: 'error', record: null, error: message(error)}); });
    return () => { cancelled = true; };
    // onLoaded only names the breadcrumb; changing it must not reload the dashboard.
  }, [client, dashboardId]);
  if(loaded.status === 'error') return <Banner status="error">{loaded.error}</Banner>;
  if(loaded.status === 'loading') return <Box role="status" sx={{fontSize: '0.8125rem', p: 1}}>
    {gettext('Loading dashboard...')}</Box>;
  return <Board client={client} record={loaded.record} initial={initial} onDrill={onDrill} />;
}

DashboardView.propTypes = {
  client: PropTypes.object.isRequired,
  dashboardId: PropTypes.string.isRequired,
  initial: PropTypes.object,
  onDrill: PropTypes.func,
  onLoaded: PropTypes.func,
};
