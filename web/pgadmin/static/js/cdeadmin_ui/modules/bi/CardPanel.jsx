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
import {NumberField, TextArea, TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {ComboBox, MultiSelect} from '../../primitives/AdvancedControls';
import {Badge} from '../../feedback/Indicators';
import {CHART_TYPES} from './queryState';
import {chartTypeLabel} from './chartData';
import {GRID_COLUMNS, MAX_H} from './dashboardLayout';
import {MAX_TEXT} from './dashboardState';
import {infoKey} from './dashboardMapping';
import MarkdownView from './MarkdownView';

const INHERIT = '__question__';

function Placement({card, dispatch}) {
  const {x, y, w, h} = card.layout;
  const place = (patch) => dispatch({type: 'placeCard', id: card.id, layout: {...card.layout, ...patch}});
  const field = (label, value, min, max, key, offset = 0) => <NumberField size="small" label={label} value={value + offset}
    slotProps={{htmlInput: {min: min + offset, max: max + offset}}} sx={{width: 110}}
    onChange={(event) => {
      const next = Number(event.target.value);
      if(Number.isFinite(next)) place({[key]: next - offset});
    }} />;
  return <Stack direction="row" gap="compact" role="group" aria-label={gettext('Placement on the grid')}
    sx={{flexWrap: 'wrap'}}>
    {field(gettext('Column'), x, 0, GRID_COLUMNS - 1, 'x', 1)}
    {field(gettext('Row'), y, 0, 10000, 'y', 1)}
    {field(gettext('Width'), w, 1, GRID_COLUMNS, 'w')}
    {field(gettext('Height'), h, 1, MAX_H, 'h')}
  </Stack>;
}

Placement.propTypes = {card: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired};

function QuestionSettings({card, info, question, client, dispatch}) {
  const [history, setHistory] = useState(null);
  const pinned = card.question.revision;
  const latest = question?.revision;
  useEffect(() => {
    let cancelled = false;
    client.history(card.question.question_id).then(
      (items) => { if(!cancelled) setHistory(items); },
      () => { if(!cancelled) setHistory([]); });
    return () => { cancelled = true; };
  }, [client, card.question.question_id]);
  const options = (history || []).map((item) => item.revision);
  if(!options.includes(pinned)) options.push(pinned);
  const override = card.visualization;
  const outputs = info?.outputs || [];
  const charted = override && override.type !== 'table' && override.type !== 'metric';
  const set = (visualization) => dispatch({type: 'setCardVisualization', id: card.id, visualization});
  return <Box sx={{display: 'grid', gap: 1}}>
    <Box sx={{fontSize: '0.8125rem'}}>
      {gettext('Question: %s', question?.name || info?.name || card.question.question_id)}
    </Box>
    <Stack direction="row" gap="compact" sx={{alignItems: 'flex-start', flexWrap: 'wrap'}}>
      <Select size="small" label={gettext('Pinned revision')} value={String(pinned)}
        options={options.sort((a, b) => b - a).map((revision) => ({
          value: String(revision),
          label: revision === latest ? gettext('Revision %s (latest)', revision) : gettext('Revision %s', revision)}))}
        onChange={(revision) => dispatch({type: 'repinCard', id: card.id, revision: Number(revision)})} />
      {latest !== undefined && latest > pinned && <>
        <Badge status="warning" label={gettext('Newer revision %s exists', latest)} />
        <Button size="small" onClick={() => dispatch({type: 'repinCard', id: card.id, revision: latest})}>
          {gettext('Re-pin to latest')}</Button>
      </>}
    </Stack>
    <Select size="small" label={gettext('Show this card as')} value={override?.type || INHERIT}
      options={[{value: INHERIT, label: gettext('As the question saves it (%s)',
        chartTypeLabel(info?.visualization?.type || 'table'))},
      ...CHART_TYPES.map((type) => ({value: type, label: chartTypeLabel(type)}))]}
      onChange={(type) => set(type === INHERIT ? null : {type, settings: override?.settings || {}})} />
    {charted && <>
      <ComboBox freeEntry size="small" label={gettext('X axis column')} options={outputs}
        value={override.settings?.x || ''} disableClearable
        onChange={(x) => set({type: override.type, settings: {...override.settings, x: x || undefined}})} />
      <MultiSelect freeSolo label={gettext('Y axis columns')} options={outputs}
        value={override.settings?.y || []}
        onChange={(y) => set({type: override.type, settings: {...override.settings, y}})} />
    </>}
  </Box>;
}

QuestionSettings.propTypes = {
  card: PropTypes.object.isRequired, info: PropTypes.object, question: PropTypes.object,
  client: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired,
};

/** Settings of the selected card: title, placement, the question pin and visualization, or the text. */
export default function CardPanel({state, card, infos, questions, client, dispatch}) {
  if(!card) {
    return <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
      {gettext('Select a card to edit its title, placement and content.')}</Box>;
  }
  const info = card.question ? infos[infoKey(card.question)] : undefined;
  const question = card.question ? questions.find((item) => item.question_id === card.question.question_id) : undefined;
  return <Box data-cdeadmin-qa-key="bi.dashboard.card" role="group"
    aria-label={gettext('Card %s', card.title || card.id)} sx={{display: 'grid', gap: 1.5, minWidth: 0}}>
    <TextField size="small" label={gettext('Card title')} value={card.title}
      onChange={(event) => dispatch({type: 'setCardTitle', id: card.id, title: event.target.value})} />
    {state.tabs.length > 1 && <Select size="small" label={gettext('Tab')} value={card.tab_id}
      options={state.tabs.map((tab) => ({value: tab.id, label: tab.name}))}
      onChange={(tabId) => dispatch({type: 'moveCardToTab', id: card.id, tabId})} />}
    <Placement card={card} dispatch={dispatch} />
    {card.type === 'question' && <QuestionSettings card={card} info={info} question={question}
      client={client} dispatch={dispatch} />}
    {card.type === 'text' && <Box sx={{display: 'grid', gap: 1}}>
      <TextArea size="small" rows={6} label={gettext('Text (Markdown)')} value={card.text.markdown}
        helperText={gettext('%s of %s characters. HTML is shown as text.', card.text.markdown.length, MAX_TEXT)}
        onChange={(event) => dispatch({type: 'setCardText', id: card.id, markdown: event.target.value})} />
      <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>{gettext('Preview')}</Box>
      <Box sx={{p: 1, border: '1px solid', borderColor: 'divider'}}><MarkdownView markdown={card.text.markdown} /></Box>
    </Box>}
    {card.type === 'metric_panel' && <Box sx={{fontSize: '0.8125rem'}}>
      {gettext('Monitoring panel %s with %s rows. Its values come from the collector channel, not from a question.',
        card.metric_panel.panel_id, card.metric_panel.rows.length)}
    </Box>}
    <Stack direction="row"><Button intent="destructive" aria-label={gettext('Remove card %s', card.title || card.id)}
      onClick={() => dispatch({type: 'removeCard', id: card.id})}>{gettext('Remove card')}</Button></Stack>
  </Box>;
}

CardPanel.propTypes = {
  state: PropTypes.object.isRequired, card: PropTypes.object, infos: PropTypes.object.isRequired,
  questions: PropTypes.array.isRequired, client: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired,
};
