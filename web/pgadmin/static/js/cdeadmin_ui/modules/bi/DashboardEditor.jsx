/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextArea} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {Badge, Banner} from '../../feedback/Indicators';
import {Dialog} from '../../overlays/Dialog';
import {NameDialog, collectionOptions} from './Dialogs';
import {chartTypeLabel} from './chartData';
import {
  AUTO_REFRESH_CHOICES, MAX_CARDS, MAX_TABS, cardLabel, questionCards,
} from './dashboardState';
import {dashboardIssues} from './dashboardMapping';
import {refreshLabel} from './dashboardViewer';
import useQuestionInfos from './useQuestionInfos';
import LayoutGrid from './LayoutGrid';
import PanelTabs from './PanelTabs';
import CardPicker from './CardPicker';
import CardPanel from './CardPanel';
import FiltersPanel from './FiltersPanel';
import InteractionsPanel from './InteractionsPanel';
import MarkdownView from './MarkdownView';

const SIDE_TABS = ['card', 'filters', 'interactions', 'settings'];
const sideLabel = (id) => ({
  card: gettext('Card'), filters: gettext('Filters'),
  interactions: gettext('Cross-filters and drill-through'), settings: gettext('Settings'),
}[id]);

function CardSummary({card, info, question}) {
  if(card.type === 'text') return <Box sx={{maxHeight: '100%', overflow: 'hidden'}}><MarkdownView markdown={card.text.markdown} /></Box>;
  if(card.type === 'metric_panel') {
    return <Box>{gettext('Monitoring panel %s, %s rows', card.metric_panel.panel_id, card.metric_panel.rows.length)}</Box>;
  }
  const latest = question?.revision;
  return <Box sx={{display: 'grid', gap: 0.25}}>
    <span>{question?.name || info?.name || card.question.question_id}</span>
    <Box component="span" sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {gettext('Revision %s', card.question.revision)}
      {latest !== undefined && latest > card.question.revision ? gettext(' (newer: %s)', latest) : ''}
      {card.visualization ? gettext(', shown as %s', chartTypeLabel(card.visualization.type)) : ''}
    </Box>
  </Box>;
}

CardSummary.propTypes = {card: PropTypes.object.isRequired, info: PropTypes.object, question: PropTypes.object};

function SettingsPanel({state, collections, dispatch}) {
  const seconds = state.settings.auto_refresh_seconds || 0;
  const choices = [...new Set([...AUTO_REFRESH_CHOICES, seconds])].sort((a, b) => a - b);
  return <Box sx={{display: 'grid', gap: 1.5}}>
    <TextArea size="small" rows={3} label={gettext('Description')} value={state.description}
      onChange={(event) => dispatch({type: 'describe', description: event.target.value})} />
    <Select size="small" label={gettext('Collection')} value={state.collectionId ?? '__root__'}
      options={collectionOptions(collections)}
      onChange={(value) => dispatch({type: 'setCollection', collectionId: value === '__root__' ? null : value})} />
    <Select size="small" label={gettext('Refresh the viewer automatically')} value={seconds}
      options={choices.map((value) => ({value, label: refreshLabel(value)}))}
      onChange={(value) => dispatch({type: 'setAutoRefresh', seconds: value})} />
    {state.settings.monitoring && <Box sx={{fontSize: '0.8125rem'}}>
      {gettext('Monitoring dashboard bound to channel %s. Its panels show collector values.', state.settings.monitoring.channel)}
    </Box>}
  </Box>;
}

SettingsPanel.propTypes = {
  state: PropTypes.object.isRequired, collections: PropTypes.array.isRequired, dispatch: PropTypes.func.isRequired,
};

function Issues({issues}) {
  if(!issues.length) return null;
  const errors = issues.filter((issue) => issue.level === 'error');
  return <Banner status={errors.length ? 'error' : 'warning'}>
    <Box component="ul" aria-label={gettext('Dashboard checks')} sx={{m: 0, pl: 2}}>
      {issues.slice(0, 8).map((issue, index) => <li key={index}>{issue.message}</li>)}
      {issues.length > 8 && <li>{gettext('and %s more', issues.length - 8)}</li>}
    </Box>
  </Banner>;
}

Issues.propTypes = {issues: PropTypes.array.isRequired};

/**
 * The dashboard editor: a grid of cards per tab, and a side panel for the
 * selected card, the dashboard filters (with their mapping onto the cards),
 * cross-filters and drill-throughs, and settings. It edits the reducer state
 * it is given; saving belongs to the workspace.
 */
export default function DashboardEditor({client, catalog, state, dispatch, questions, dashboards, collections}) {
  const [tabId, setTabId] = useState(state.tabs[0].id);
  const [side, setSide] = useState('card');
  const [selectedId, setSelectedId] = useState('');
  const [dialog, setDialog] = useState(null);
  const activeTab = state.tabs.some((tab) => tab.id === tabId) ? tabId : state.tabs[0].id;
  const selected = state.cards.find((card) => card.id === selectedId);

  const pins = useMemo(() => [
    ...questionCards(state).map((card) => card.question),
    ...state.drillThroughs.filter((drill) => drill.target.kind === 'question' && drill.target.question_id)
      .map((drill) => ({question_id: drill.target.question_id, revision: drill.target.revision})),
  ], [state]);
  const {infos} = useQuestionInfos(client, pins, catalog);
  const issues = useMemo(() => dashboardIssues(state, infos), [state, infos]);

  // A card that was just added is selected and its tab shown.
  const count = useRef(state.cards.length);
  useEffect(() => {
    if(state.cards.length > count.current) {
      const added = state.cards[state.cards.length - 1];
      setSelectedId(added.id);
      setTabId(added.tab_id);
      setSide('card');
    }
    count.current = state.cards.length;
  }, [state.cards]);

  const select = useCallback((card) => { setSelectedId(card.id); setSide('card'); }, []);
  const place = useCallback((id, layout) => dispatch({type: 'placeCard', id, layout}), [dispatch]);
  const nudge = useCallback((id, dx, dy) => dispatch({type: 'nudgeCard', id, dx, dy}), [dispatch]);
  const resize = useCallback((id, dw, dh) => dispatch({type: 'resizeCardBy', id, dw, dh}), [dispatch]);
  const tab = state.tabs.find((item) => item.id === activeTab);
  const tabCards = state.cards.filter((card) => card.tab_id === activeTab);
  const full = state.cards.length >= MAX_CARDS;

  const removeTab = () => {
    if(tabCards.length) setDialog({kind: 'removeTab'});
    else dispatch({type: 'removeTab', id: activeTab});
  };

  return <Box data-cdeadmin-qa-key="bi.dashboard.editor" sx={{display: 'grid', gap: 1.5, alignItems: 'start', minWidth: 0,
    gridTemplateColumns: {xs: 'minmax(0, 1fr)', lg: 'minmax(0, 1fr) minmax(320px, 400px)'}}}>
    <Box sx={{display: 'grid', gap: 1, minWidth: 0}}>
      <Issues issues={issues} />
      <PanelTabs label={gettext('Dashboard tabs')} ids={state.tabs.map((item) => item.id)}
        labelOf={(id) => state.tabs.find((item) => item.id === id)?.name || id}
        active={activeTab} onChange={setTabId}
        extra={<Stack direction="row" gap="compact" sx={{ml: 1}}>
          <Button size="small" disabled={state.tabs.length >= MAX_TABS} onClick={() => setDialog({kind: 'addTab'})}>
            {gettext('Add tab')}</Button>
          <Button size="small" onClick={() => setDialog({kind: 'renameTab'})}>{gettext('Rename tab')}</Button>
          <Button size="small" intent="destructive" disabled={state.tabs.length <= 1} onClick={removeTab}>
            {gettext('Remove tab')}</Button>
        </Stack>} />
      <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap'}}>
        <Button intent="primary" disabled={full} onClick={() => setDialog({kind: 'pick'})}>{gettext('Add question card')}</Button>
        <Button disabled={full} onClick={() => dispatch({type: 'addTextCard', tabId: activeTab,
          markdown: gettext('Write **Markdown** here.')})}>{gettext('Add text card')}</Button>
        <Button disabled={!tabCards.length} onClick={() => dispatch({type: 'compactTab', tabId: activeTab})}>
          {gettext('Tidy layout')}</Button>
      </Stack>
      <Box role="tabpanel" aria-label={tab.name}>
        {tabCards.length === 0 && <Box sx={{p: 2, fontSize: '0.8125rem', color: 'text.secondary'}}>
          {gettext('This tab has no cards. Add a question card or a text card.')}</Box>}
        <LayoutGrid editable cards={state.cards} tabId={activeTab} label={gettext('Cards of %s', tab.name)}
          onPlace={place} onNudge={nudge} onResizeBy={resize}
          renderCard={(card, {handles}) => {
            const label = cardLabel(card);
            const isSelected = card.id === selectedId;
            return <Box role="group" aria-label={gettext('Card %s', label)} data-selected={isSelected || undefined}
              sx={{height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', bgcolor: 'background.paper',
                border: '1px solid', borderColor: isSelected ? 'primary.main' : 'divider',
                outline: isSelected ? '1px solid' : 'none', outlineColor: 'primary.main'}}>
              <Stack direction="row" gap="compact" sx={{alignItems: 'center', p: 0.5, flexWrap: 'wrap'}}>
                {handles}
                <Box component="span" sx={{flex: 1, minWidth: 60, fontWeight: 600, fontSize: '0.8125rem',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{label}</Box>
                <Badge status="neutral" label={card.type === 'question' ? gettext('Question') :
                  card.type === 'text' ? gettext('Text') : gettext('Monitoring')} />
                <Button size="small" aria-label={gettext('Edit card %s', label)} aria-pressed={isSelected}
                  onClick={() => select(card)}>{gettext('Edit')}</Button>
              </Stack>
              <Box sx={{p: 1, fontSize: '0.8125rem', overflow: 'hidden', flex: 1, minHeight: 0}}>
                <CardSummary card={card} info={card.question ? infos[`${card.question.question_id}@${card.question.revision}`] : undefined}
                  question={card.question ? questions.find((item) => item.question_id === card.question.question_id) : undefined} />
              </Box>
            </Box>;
          }} />
      </Box>
    </Box>
    <Box sx={{display: 'grid', gap: 1, minWidth: 0}}>
      <PanelTabs label={gettext('Editor panels')} ids={SIDE_TABS} labelOf={sideLabel} active={side} onChange={setSide} />
      <Box role="tabpanel" aria-label={sideLabel(side)} sx={{minWidth: 0}}>
        {side === 'card' && <CardPanel state={state} card={selected} infos={infos} questions={questions}
          client={client} dispatch={dispatch} />}
        {side === 'filters' && <FiltersPanel state={state} infos={infos} dispatch={dispatch} />}
        {side === 'interactions' && <InteractionsPanel client={client} state={state} infos={infos}
          questions={questions} dashboards={dashboards} dispatch={dispatch} />}
        {side === 'settings' && <SettingsPanel state={state} collections={collections} dispatch={dispatch} />}
      </Box>
    </Box>

    {dialog?.kind === 'pick' && <CardPicker client={client} questions={questions}
      collections={collections}
      onClose={() => setDialog(null)}
      onPick={(question) => {
        dispatch({type: 'addQuestionCard', tabId: activeTab,
          question: {question_id: question.question_id, revision: question.revision}, title: question.name});
        setDialog(null);
      }} />}
    {dialog?.kind === 'addTab' && <NameDialog open title={gettext('Add a tab')} label={gettext('Tab name')}
      confirmLabel={gettext('Add tab')} onClose={() => setDialog(null)}
      onConfirm={(name) => { dispatch({type: 'addTab', name}); }} />}
    {dialog?.kind === 'renameTab' && <NameDialog open title={gettext('Rename tab')} label={gettext('Tab name')}
      initial={tab.name} confirmLabel={gettext('Rename')} onClose={() => setDialog(null)}
      onConfirm={(name) => { dispatch({type: 'renameTab', id: activeTab, name}); }} />}
    {dialog?.kind === 'removeTab' && <Dialog open title={gettext('Remove this tab?')} onClose={() => setDialog(null)}
      actions={<Stack direction="row" gap="compact">
        <Button onClick={() => setDialog(null)}>{gettext('Keep the tab')}</Button>
        <Button intent="destructive" onClick={() => { dispatch({type: 'removeTab', id: activeTab}); setDialog(null); }}>
          {gettext('Remove tab and cards')}</Button>
      </Stack>}>
      {gettext('The %s cards on this tab are removed with it, together with the filter mappings, cross-filters and drill-throughs that use them.', tabCards.length)}
    </Dialog>}
  </Box>;
}

DashboardEditor.propTypes = {
  client: PropTypes.object.isRequired,
  catalog: PropTypes.object,
  state: PropTypes.object.isRequired,
  dispatch: PropTypes.func.isRequired,
  questions: PropTypes.array.isRequired,
  dashboards: PropTypes.array.isRequired,
  collections: PropTypes.array.isRequired,
};
