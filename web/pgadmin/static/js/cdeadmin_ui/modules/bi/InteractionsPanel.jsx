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
import {NumberField, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {ComboBox} from '../../primitives/AdvancedControls';
import {Banner} from '../../feedback/Indicators';
import {
  cardLabel, drillMappings, makeSource, mappingTargetKey, newCrossFilter, newDrill, questionCards,
  parseFilterValue, sourceKind, withDrillMappings, MAX_LINKS,
} from './dashboardState';
import {infoKey} from './dashboardMapping';

const SOURCE_KINDS = () => [
  {value: 'column', label: gettext('The clicked row\'s column')},
  {value: 'value', label: gettext('A fixed value')},
  {value: 'filter_id', label: gettext('The current value of a filter')},
];

function Section({title, children}) {
  return <Box component="section" aria-label={title} sx={{display: 'grid', gap: 1}}>
    <Box component="h3" sx={{m: 0, fontSize: '0.875rem'}}>{title}</Box>
    {children}
  </Box>;
}

Section.propTypes = {title: PropTypes.string.isRequired, children: PropTypes.node};

function SourceCardSelect({label, state, value, onChange}) {
  return <Select size="small" label={label} value={value}
    options={[{value: '', label: gettext('Choose a card')},
      ...questionCards(state).map((card) => ({value: card.id, label: cardLabel(card)}))]}
    onChange={onChange} />;
}

SourceCardSelect.propTypes = {
  label: PropTypes.string.isRequired, state: PropTypes.object.isRequired,
  value: PropTypes.string, onChange: PropTypes.func.isRequired,
};

function ColumnBox({label, options, value, onChange}) {
  return <ComboBox freeEntry size="small" label={label} options={options} value={value || ''}
    disableClearable onChange={(next) => onChange(next || '')} />;
}

ColumnBox.propTypes = {
  label: PropTypes.string.isRequired, options: PropTypes.array, value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
};

const outputsOf = (state, infos, cardId) => {
  const card = state.cards.find((item) => item.id === cardId);
  return card?.question ? infos[infoKey(card.question)]?.outputs || [] : [];
};

function CrossFilterEditor({state, infos, link, dispatch}) {
  const update = (patch) => dispatch({type: 'updateCrossFilter', id: link.id, patch});
  return <Box role="group" aria-label={gettext('Cross-filter %s', link.id)}
    sx={{display: 'grid', gap: 1, p: 1, border: '1px solid', borderColor: 'divider'}}>
    <SourceCardSelect label={gettext('Clicking a mark or cell in')} state={state}
      value={link.source_card_id} onChange={(id) => update({source_card_id: id, source_column: ''})} />
    <ColumnBox label={gettext('uses the value of column')} options={outputsOf(state, infos, link.source_card_id)}
      value={link.source_column} onChange={(source_column) => update({source_column})} />
    <Select size="small" label={gettext('to set filter')} value={link.filter_id}
      options={state.filters.map((filter) => ({value: filter.id, label: filter.name}))}
      onChange={(filterId) => update({filter_id: filterId})} />
    <Checkbox size="small" label={gettext('Do not filter the clicked card by its own click')}
      checked={link.exclude_source} onChange={(exclude) => update({exclude_source: exclude})} />
    <Stack direction="row"><Button size="small" intent="destructive"
      aria-label={gettext('Remove cross-filter %s', link.id)}
      onClick={() => dispatch({type: 'removeCrossFilter', id: link.id})}>{gettext('Remove')}</Button></Stack>
  </Box>;
}

CrossFilterEditor.propTypes = {
  state: PropTypes.object.isRequired, infos: PropTypes.object.isRequired,
  link: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired,
};

/** Filters of another dashboard, for the mappings of a dashboard drill-through. */
function useTargetFilters(client, dashboardId) {
  const [loaded, setLoaded] = useState({id: '', filters: null});
  useEffect(() => {
    if(!dashboardId) return undefined;
    let cancelled = false;
    client.getDashboard(dashboardId).then(
      (record) => { if(!cancelled) setLoaded({id: dashboardId, filters: record.definition?.filters || []}); },
      () => { if(!cancelled) setLoaded({id: dashboardId, filters: null}); });
    return () => { cancelled = true; };
  }, [client, dashboardId]);
  return loaded.id === dashboardId ? loaded.filters : null;
}

function LiteralValue({label, type, value, onChange}) {
  const [draft, setDraft] = useState(value === undefined || value === null ? '' : String(value));
  const parsed = parseFilterValue(type, draft);
  return <TextField size="small" label={label} value={draft}
    validationMessage={draft.trim() !== '' && parsed === undefined ? gettext('Not a valid %s value.', type) : undefined}
    onChange={(event) => {
      setDraft(event.target.value);
      const next = parseFilterValue(type, event.target.value);
      if(next !== undefined) onChange(next);
    }} />;
}

LiteralValue.propTypes = {
  label: PropTypes.string.isRequired, type: PropTypes.string.isRequired, value: PropTypes.any,
  onChange: PropTypes.func.isRequired,
};

function MappingRow({state, infos, drill, mapping, index, targetInfo, targetFilters, onChange, onRemove}) {
  const target = drill.target;
  const key = mappingTargetKey(target);
  const from = mapping.from;
  const kind = sourceKind(from);
  const label = gettext('Mapping %s of %s', index + 1, drill.id);
  const targetOptions = target.kind === 'dashboard' ?
    (targetFilters || []).map((filter) => ({value: filter.id, label: filter.name})) :
    (targetInfo?.parameters || []).map((parameter) => ({value: parameter.id, label: `${parameter.id} (${parameter.type})`}));
  const knownType = target.kind === 'dashboard' ?
    (targetFilters || []).find((filter) => filter.id === mapping[key])?.type :
    targetInfo?.parameters.find((parameter) => parameter.id === mapping[key])?.type;
  return <Box role="group" aria-label={label}
    sx={{display: 'grid', gap: 0.5, gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', alignItems: 'start'}}>
    {targetOptions.length ?
      <Select size="small" label={target.kind === 'dashboard' ? gettext('Filter to set') : gettext('Parameter to fill')}
        value={mapping[key]} options={[{value: '', label: gettext('Choose')}, ...targetOptions]}
        onChange={(value) => onChange({...mapping, [key]: value})} /> :
      <TextField size="small" label={target.kind === 'dashboard' ? gettext('Filter to set') : gettext('Parameter to fill')}
        value={mapping[key]} onChange={(event) => onChange({...mapping, [key]: event.target.value})} />}
    <Select size="small" label={gettext('takes its value from')} value={kind} options={SOURCE_KINDS()}
      onChange={(next) => onChange({...mapping, from: makeSource(next, '')})} />
    {kind === 'column' && <ColumnBox label={gettext('Column')} options={outputsOf(state, infos, drill.source_card_id)}
      value={from.column} onChange={(column) => onChange({...mapping, from: {column}})} />}
    {kind === 'filter_id' && <Select size="small" label={gettext('Filter')} value={from.filter_id}
      options={[{value: '', label: gettext('Choose')}, ...state.filters.map((filter) => ({value: filter.id, label: filter.name}))]}
      onChange={(filterId) => onChange({...mapping, from: {filter_id: filterId}})} />}
    {kind === 'value' && <LiteralValue key={String(knownType)} label={gettext('Value')} type={knownType || 'string'}
      value={from.value} onChange={(value) => onChange({...mapping, from: {value}})} />}
    <Button size="small" aria-label={gettext('Remove %s', label)} onClick={onRemove}>{gettext('Remove')}</Button>
  </Box>;
}

MappingRow.propTypes = {
  state: PropTypes.object.isRequired, infos: PropTypes.object.isRequired, drill: PropTypes.object.isRequired,
  mapping: PropTypes.object.isRequired, index: PropTypes.number.isRequired, targetInfo: PropTypes.object,
  targetFilters: PropTypes.array, onChange: PropTypes.func.isRequired, onRemove: PropTypes.func.isRequired,
};

function DrillEditor({client, state, infos, questions, dashboards, drill, dispatch}) {
  const update = (patch) => dispatch({type: 'updateDrill', id: drill.id, patch});
  const target = drill.target;
  const targetFilters = useTargetFilters(client, target.kind === 'dashboard' ? target.dashboard_id : '');
  const targetInfo = target.kind === 'question' ? infos[infoKey(target)] : undefined;
  const mappings = drillMappings(target);
  const setMappings = (list) => update({target: withDrillMappings(target, list)});
  const triggerKind = 'column' in drill.trigger ? 'column' : 'row';
  const sourceOutputs = outputsOf(state, infos, drill.source_card_id);
  return <Box role="group" aria-label={gettext('Drill-through %s', drill.label || drill.id)}
    sx={{display: 'grid', gap: 1, p: 1, border: '1px solid', borderColor: 'divider'}}>
    <SourceCardSelect label={gettext('Clicking in')} state={state} value={drill.source_card_id}
      onChange={(id) => update({source_card_id: id})} />
    <TextField size="small" label={gettext('Label')} value={drill.label}
      onChange={(event) => update({label: event.target.value})} />
    <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap'}}>
      <Select size="small" label={gettext('Triggers on')} value={triggerKind}
        options={[{value: 'row', label: gettext('Any part of the row')}, {value: 'column', label: gettext('One column')}]}
        onChange={(kind) => update({trigger: kind === 'row' ? {row: true} : {column: sourceOutputs[0] || ''}})} />
      {triggerKind === 'column' && <ColumnBox label={gettext('Trigger column')} options={sourceOutputs}
        value={drill.trigger.column} onChange={(column) => update({trigger: {column}})} />}
    </Stack>
    <Select size="small" label={gettext('Opens')} value={target.kind}
      options={[{value: 'question', label: gettext('A saved question')}, {value: 'dashboard', label: gettext('Another dashboard')}]}
      onChange={(kind) => update({target: newDrill({id: drill.id, sourceCardId: drill.source_card_id, kind}).target})} />
    {target.kind === 'question' && <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap', alignItems: 'flex-start'}}>
      <Select size="small" label={gettext('Question')} value={target.question_id}
        options={[{value: '', label: gettext('Choose a question')},
          ...questions.filter((question) => question.status !== 'archived' || question.question_id === target.question_id)
            .map((question) => ({value: question.question_id, label: question.name}))]}
        onChange={(id) => update({target: {...target, question_id: id,
          revision: questions.find((question) => question.question_id === id)?.revision || 1,
          parameter_mappings: []}})} />
      <NumberField size="small" label={gettext('Pinned revision')} value={target.revision}
        slotProps={{htmlInput: {min: 1}}}
        onChange={(event) => update({target: {...target, revision: Math.max(1, Number(event.target.value) || 1)}})} />
    </Stack>}
    {target.kind === 'dashboard' && <Select size="small" label={gettext('Dashboard')} value={target.dashboard_id}
      options={[{value: '', label: gettext('Choose a dashboard')},
        ...dashboards.map((dashboard) => ({value: dashboard.dashboard_id, label: dashboard.name}))]}
      onChange={(id) => update({target: {...target, dashboard_id: id, filter_mappings: []}})} />}
    {mappings.map((mapping, index) => <MappingRow key={index} state={state} infos={infos} drill={drill}
      mapping={mapping} index={index} targetInfo={targetInfo} targetFilters={targetFilters}
      onChange={(next) => setMappings(mappings.map((item, position) => position === index ? next : item))}
      onRemove={() => setMappings(mappings.filter((_item, position) => position !== index))} />)}
    <Stack direction="row" gap="compact">
      <Button size="small" onClick={() => setMappings([...mappings,
        {[mappingTargetKey(target)]: '', from: {column: ''}}])}>{gettext('Add value mapping')}</Button>
      <Button size="small" intent="destructive" aria-label={gettext('Remove drill-through %s', drill.label || drill.id)}
        onClick={() => dispatch({type: 'removeDrill', id: drill.id})}>{gettext('Remove')}</Button>
    </Stack>
  </Box>;
}

DrillEditor.propTypes = {
  client: PropTypes.object.isRequired, state: PropTypes.object.isRequired, infos: PropTypes.object.isRequired,
  questions: PropTypes.array.isRequired, dashboards: PropTypes.array.isRequired,
  drill: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired,
};

/**
 * Interactions: cross-filters (a click sets a dashboard filter) and
 * drill-throughs (a click opens a pinned question or another dashboard with
 * values taken from the clicked row, a fixed value or a current filter). The
 * fields are exactly those of dashboard_models.py.
 */
export default function InteractionsPanel({client, state, infos, questions, dashboards, dispatch}) {
  const cards = questionCards(state);
  const first = cards[0];
  return <Box data-cdeadmin-qa-key="bi.dashboard.interactions" sx={{display: 'grid', gap: 2, minWidth: 0}}>
    <Section title={gettext('Cross-filters')}>
      {state.crossFilters.map((link) => <CrossFilterEditor key={link.id} state={state} infos={infos}
        link={link} dispatch={dispatch} />)}
      {(!cards.length || !state.filters.length) && <Banner status="info">
        {gettext('A cross-filter needs a question card and a filter.')}</Banner>}
      <Stack direction="row"><Button disabled={!first || !state.filters.length || state.crossFilters.length >= MAX_LINKS}
        onClick={() => dispatch({type: 'addCrossFilter', link: newCrossFilter({
          id: '', sourceCardId: first.id, filterId: state.filters[0].id})})}>{gettext('Add cross-filter')}</Button></Stack>
    </Section>
    <Section title={gettext('Drill-throughs')}>
      {state.drillThroughs.map((drill) => <DrillEditor key={drill.id} client={client} state={state} infos={infos}
        questions={questions} dashboards={dashboards} drill={drill} dispatch={dispatch} />)}
      {!cards.length && <Banner status="info">{gettext('A drill-through needs a question card.')}</Banner>}
      <Stack direction="row"><Button disabled={!first || state.drillThroughs.length >= MAX_LINKS}
        onClick={() => dispatch({type: 'addDrill', drill: newDrill({id: '', sourceCardId: first.id})})}>
        {gettext('Add drill-through')}</Button></Stack>
    </Section>
  </Box>;
}

InteractionsPanel.propTypes = {
  client: PropTypes.object.isRequired, state: PropTypes.object.isRequired, infos: PropTypes.object.isRequired,
  questions: PropTypes.array.isRequired, dashboards: PropTypes.array.isRequired, dispatch: PropTypes.func.isRequired,
};
