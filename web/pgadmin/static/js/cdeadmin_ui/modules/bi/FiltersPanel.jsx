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
import {TextArea, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {DateField, MultiSelect} from '../../primitives/AdvancedControls';
import {Badge} from '../../feedback/Indicators';
import {
  FILTER_TYPES, MAX_FILTERS, MULTIPLE_OPERATORS, SINGLE_OPERATORS, WIDGETS_BY_TYPE,
  formatFilterValue, parseFilterValue,
} from './dashboardState';
import MappingGrid from './MappingGrid';

const NO_DEFAULT = '__none__';

export const typeLabel = (type) => ({
  string: gettext('Text'), integer: gettext('Whole number'), number: gettext('Number'),
  boolean: gettext('Yes or no'), date: gettext('Date'), datetime: gettext('Date and time'),
}[type] || type);

export const widgetLabel = (widget) => ({
  text: gettext('Text box'), select: gettext('Drop-down list'), multi_select: gettext('Multi-select list'),
  number: gettext('Number box'), date: gettext('Date picker'), date_range: gettext('Date range'),
  toggle: gettext('Switch'),
}[widget] || widget);

export const operatorLabel = (operator) => ({
  eq: gettext('equals'), ne: gettext('does not equal'), lt: gettext('is less than'),
  lte: gettext('is at most'), gt: gettext('is greater than'), gte: gettext('is at least'),
  in: gettext('is one of'), not_in: gettext('is none of'), between: gettext('is between'),
}[operator] || operator);

/** A text box whose draft may be invalid; only a parsed value is committed. */
function TypedValueField({label, type, value, onCommit, inputType}) {
  const [draft, setDraft] = useState(formatFilterValue(value));
  const parsed = parseFilterValue(type, draft);
  const invalid = draft.trim() !== '' && parsed === undefined;
  return <TextField size="small" label={label} value={draft} type={inputType}
    validationMessage={invalid ? gettext('Not a valid %s.', typeLabel(type).toLowerCase()) : undefined}
    onChange={(event) => {
      setDraft(event.target.value);
      const next = parseFilterValue(type, event.target.value);
      if(next !== undefined) onCommit(next);
      else if(event.target.value.trim() === '') onCommit(undefined);
    }} />;
}

TypedValueField.propTypes = {
  label: PropTypes.string.isRequired, type: PropTypes.string.isRequired, value: PropTypes.any,
  onCommit: PropTypes.func.isRequired, inputType: PropTypes.string,
};

function AllowedValues({filter, onChange}) {
  const [text, setText] = useState(filter.allowed_values.map(formatFilterValue).join('\n'));
  const lines = text.split('\n').map((line) => line.trim()).filter(Boolean);
  const bad = lines.filter((line) => parseFilterValue(filter.type, line) === undefined);
  return <TextArea size="small" rows={3} label={gettext('Allowed values, one per line')} value={text}
    validationMessage={bad.length ? gettext('Not a valid %s: %s', typeLabel(filter.type).toLowerCase(), bad[0]) : undefined}
    onChange={(event) => {
      setText(event.target.value);
      const next = event.target.value.split('\n').map((line) => line.trim()).filter(Boolean)
        .map((line) => parseFilterValue(filter.type, line));
      if(next.every((value) => value !== undefined)) onChange(next);
    }} />;
}

AllowedValues.propTypes = {filter: PropTypes.object.isRequired, onChange: PropTypes.func.isRequired};

/** The default value control for the filter's widget. */
function DefaultValue({filter, onChange}) {
  const has = 'default' in filter;
  const choices = filter.allowed_values;
  const option = (value) => ({value: String(value), label: String(value)});
  switch(filter.widget) {
  case 'date_range': {
    const [from = '', to = ''] = has ? filter.default : [];
    const set = (nextFrom, nextTo) => onChange(nextFrom && nextTo ? [nextFrom, nextTo] : undefined);
    return <Stack direction="row" gap="compact">
      <DateField size="small" label={gettext('Default from')} value={from} onChange={(value) => set(value, to)} />
      <DateField size="small" label={gettext('Default to')} value={to} onChange={(value) => set(from, value)} />
    </Stack>;
  }
  case 'date':
    return <DateField size="small" label={gettext('Default value')} value={has ? String(filter.default) : ''}
      onChange={(value) => onChange(value || undefined)} />;
  case 'select':
    return <Select size="small" label={gettext('Default value')} value={has ? String(filter.default) : NO_DEFAULT}
      options={[{value: NO_DEFAULT, label: gettext('No default')}, ...choices.map(option)]}
      onChange={(value) => onChange(value === NO_DEFAULT ? undefined :
        choices.find((item) => String(item) === value))} />;
  case 'multi_select':
    return <MultiSelect label={gettext('Default values')} options={choices.map(option)}
      value={has ? filter.default.map(option) : []}
      isOptionEqualToValue={(left, right) => left.value === right.value}
      onChange={(next) => onChange(next.length ? next.map((item) =>
        choices.find((value) => String(value) === item.value)) : undefined)} />;
  case 'toggle':
    return <Select size="small" label={gettext('Default value')}
      value={has ? String(filter.default) : NO_DEFAULT}
      options={[{value: NO_DEFAULT, label: gettext('No default')}, {value: 'true', label: gettext('On')},
        {value: 'false', label: gettext('Off')}]}
      onChange={(value) => onChange(value === NO_DEFAULT ? undefined : value === 'true')} />;
  default:
    return <TypedValueField key={filter.id + filter.type} label={gettext('Default value')} type={filter.type}
      value={has ? filter.default : undefined} onCommit={onChange}
      inputType={filter.widget === 'number' ? 'number' : undefined} />;
  }
}

DefaultValue.propTypes = {filter: PropTypes.object.isRequired, onChange: PropTypes.func.isRequired};

function FilterForm({filter, dispatch}) {
  const update = (patch) => dispatch({type: 'updateFilter', id: filter.id, patch});
  const widgets = WIDGETS_BY_TYPE[filter.type] || [filter.widget];
  const operators = filter.widget === 'date_range' ? ['between'] :
    filter.widget === 'multi_select' ? MULTIPLE_OPERATORS : SINGLE_OPERATORS;
  const chooses = filter.widget === 'select' || filter.widget === 'multi_select';
  return <Box role="group" aria-label={gettext('Filter %s', filter.name)} sx={{display: 'grid', gap: 1}}>
    <TextField size="small" label={gettext('Filter name')} value={filter.name}
      onChange={(event) => update({name: event.target.value})} />
    <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap'}}>
      <Select size="small" label={gettext('Value type')} value={filter.type}
        options={FILTER_TYPES.map((type) => ({value: type, label: typeLabel(type)}))}
        onChange={(type) => update({type})} />
      <Select size="small" label={gettext('Widget')} value={filter.widget}
        options={[...new Set([...widgets, filter.widget])].map((widget) => ({value: widget, label: widgetLabel(widget)}))}
        onChange={(widget) => update({widget})} />
      <Select size="small" label={gettext('Matches when the column')} value={filter.operator}
        disabled={operators.length === 1}
        options={operators.map((operator) => ({value: operator, label: operatorLabel(operator)}))}
        onChange={(operator) => update({operator})} />
    </Stack>
    {chooses && <AllowedValues key={filter.id + filter.type} filter={filter} onChange={(allowed) => update({allowed_values: allowed})} />}
    <DefaultValue filter={filter} onChange={(value) => update({default: value})} />
    <Checkbox size="small" label={gettext('Required: a value must be chosen before cards run')}
      checked={filter.required} onChange={(required) => update({required})} />
  </Box>;
}

FilterForm.propTypes = {filter: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired};

/**
 * Dashboard filters: the widgets the viewer shows, their defaults and
 * required flag, and (per filter) the mapping onto each question card.
 */
export default function FiltersPanel({state, infos, dispatch}) {
  const [selectedId, setSelectedId] = useState('');
  const [name, setName] = useState('');
  const [type, setType] = useState('string');
  const selected = state.filters.find((filter) => filter.id === selectedId) || state.filters[0];

  const add = () => {
    if(!name.trim()) return;
    dispatch({type: 'addFilter', filter: {name, type}});
    setName('');
  };
  return <Box data-cdeadmin-qa-key="bi.dashboard.filters" sx={{display: 'grid', gap: 1.5, minWidth: 0}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'flex-start', flexWrap: 'wrap'}}>
      <TextField size="small" label={gettext('New filter name')} value={name}
        onChange={(event) => setName(event.target.value)}
        onKeyDown={(event) => { if(event.key === 'Enter') { event.preventDefault(); add(); } }} />
      <Select size="small" label={gettext('New filter type')} value={type}
        options={FILTER_TYPES.map((item) => ({value: item, label: typeLabel(item)}))} onChange={setType} />
      <Button disabled={!name.trim() || state.filters.length >= MAX_FILTERS} onClick={add}>{gettext('Add filter')}</Button>
    </Stack>
    {state.filters.length === 0 && <Box sx={{fontSize: '0.8125rem', color: 'text.secondary'}}>
      {gettext('No filters yet. A filter adds a widget to the dashboard that narrows the cards it is mapped to.')}
    </Box>}
    {state.filters.length > 0 && <Box component="ul" aria-label={gettext('Dashboard filters')} sx={{m: 0, p: 0, listStyle: 'none'}}>
      {state.filters.map((filter) => <Box component="li" key={filter.id}
        sx={{display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', py: 0.25,
          bgcolor: filter.id === selected?.id ? 'action.selected' : 'transparent'}}>
        <Button size="small" aria-pressed={filter.id === selected?.id}
          aria-label={gettext('Edit filter %s', filter.name)} onClick={() => setSelectedId(filter.id)}>
          {filter.name}</Button>
        <Badge status="neutral" label={widgetLabel(filter.widget)} />
        {filter.required && <Badge status="warning" label={gettext('Required')} />}
        {filter.targets.length === 0 && <Badge status="warning" label={gettext('Not mapped')} />}
        <Button size="small" intent="destructive" aria-label={gettext('Remove filter %s', filter.name)}
          onClick={() => dispatch({type: 'removeFilter', id: filter.id})}>{gettext('Remove')}</Button>
      </Box>)}
    </Box>}
    {selected && <>
      <FilterForm key={selected.id} filter={selected} dispatch={dispatch} />
      <MappingGrid state={state} filter={selected} infos={infos} dispatch={dispatch} />
    </>}
  </Box>;
}

FiltersPanel.propTypes = {
  state: PropTypes.object.isRequired, infos: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired,
};
