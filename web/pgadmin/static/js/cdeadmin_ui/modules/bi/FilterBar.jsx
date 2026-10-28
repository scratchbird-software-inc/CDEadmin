/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {NumberField, TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {DateField, MultiSelect} from '../../primitives/AdvancedControls';
import {Banner} from '../../feedback/Indicators';
import {
  draftsFromValues, initialValues, valuesFromDrafts,
} from './dashboardViewer';

const ANY = '';

function Widget({filter, draft, error, onChange, onSubmit}) {
  const label = filter.required ? gettext('%s (required)', filter.name) : filter.name;
  const submit = (event) => { if(event.key === 'Enter') { event.preventDefault(); onSubmit(); } };
  const option = (value) => ({value: String(value), label: String(value)});
  switch(filter.widget) {
  case 'select':
    return filter.allowed_values.length ?
      <Select size="small" label={label} value={draft} validationMessage={error}
        options={[{value: ANY, label: gettext('Any')}, ...filter.allowed_values.map(option)]} onChange={onChange} /> :
      <TextField size="small" label={label} value={draft} validationMessage={error}
        onChange={(event) => onChange(event.target.value)} onKeyDown={submit} />;
  case 'multi_select':
    return <MultiSelect label={label} options={filter.allowed_values.map(option)}
      value={draft.map(option)} validationMessage={error}
      isOptionEqualToValue={(left, right) => left.value === right.value}
      onChange={(next) => onChange(next.map((item) => item.value))} />;
  case 'toggle':
    return <Select size="small" label={label} value={draft} validationMessage={error}
      options={[{value: 'any', label: gettext('Any')}, {value: 'true', label: gettext('Yes')},
        {value: 'false', label: gettext('No')}]} onChange={onChange} />;
  case 'date_range':
    return <Box role="group" aria-label={label} sx={{display: 'flex', gap: 0.5}}>
      <DateField size="small" label={gettext('%s from', filter.name)} value={draft[0]} validationMessage={error}
        onChange={(value) => onChange([value, draft[1]])} />
      <DateField size="small" label={gettext('%s to', filter.name)} value={draft[1]}
        onChange={(value) => onChange([draft[0], value])} />
    </Box>;
  case 'date':
    return <DateField size="small" label={label} value={draft} validationMessage={error} onChange={onChange} />;
  case 'number':
    return <NumberField size="small" label={label} value={draft} validationMessage={error}
      onChange={(event) => onChange(event.target.value)} onKeyDown={submit} />;
  default:
    return <TextField size="small" label={label} value={draft} validationMessage={error}
      onChange={(event) => onChange(event.target.value)} onKeyDown={submit} />;
  }
}

Widget.propTypes = {
  filter: PropTypes.object.isRequired, draft: PropTypes.any, error: PropTypes.string,
  onChange: PropTypes.func.isRequired, onSubmit: PropTypes.func.isRequired,
};

/**
 * The viewer's filter bar. Edits are drafts; Apply commits them all at once,
 * so a half-typed value never runs the cards. A value set by a cross-filter
 * click replaces the draft.
 */
export default function FilterBar({dashboard, values, missing, onApply}) {
  const valuesKey = JSON.stringify(values);
  const [drafts, setDrafts] = useState(() => draftsFromValues(dashboard, values));
  useEffect(() => { setDrafts(draftsFromValues(dashboard, values)); }, [dashboard, valuesKey]);
  const result = useMemo(() => valuesFromDrafts(dashboard, drafts), [dashboard, drafts]);
  const failed = Object.keys(result.errors).length > 0;
  const changed = JSON.stringify(result.values) !== JSON.stringify(Object.fromEntries(
    Object.entries(values).filter(([id]) => dashboard.filters.some((filter) => filter.id === id))));
  if(!dashboard.filters.length) return null;
  const apply = () => { if(!failed) onApply(result.values); };
  return <Box component="form" data-cdeadmin-qa-key="bi.dashboard.filterbar" role="search"
    aria-label={gettext('Dashboard filters')} noValidate
    onSubmit={(event) => { event.preventDefault(); apply(); }}
    sx={{display: 'grid', gap: 1, p: 1, border: '1px solid', borderColor: 'divider'}}>
    {missing.length > 0 && <Banner status="warning">
      {gettext('Choose a value for %s to show the cards.', missing.map((filter) => filter.name).join(', '))}
    </Banner>}
    <Stack direction="row" gap="comfortable" sx={{flexWrap: 'wrap', alignItems: 'flex-start'}}>
      {dashboard.filters.map((filter) => <Widget key={filter.id} filter={filter} draft={drafts[filter.id]}
        error={result.errors[filter.id]} onSubmit={apply}
        onChange={(draft) => setDrafts((current) => ({...current, [filter.id]: draft}))} />)}
      <Button intent="primary" type="submit" disabled={failed || !changed}>{gettext('Apply filters')}</Button>
      <Button onClick={() => onApply(initialValues(dashboard))}>{gettext('Reset filters')}</Button>
    </Stack>
  </Box>;
}

FilterBar.propTypes = {
  dashboard: PropTypes.object.isRequired, values: PropTypes.object.isRequired,
  missing: PropTypes.array.isRequired, onApply: PropTypes.func.isRequired,
};
