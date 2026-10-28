/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {
  CATEGORIES, isListOperator, isRangeOperator, isUnaryOperator, operatorLabel, operatorsFor,
} from './columnTypes';
import {errorAt} from './validateState';
import Section from './Section';

const ROW_SX = {display: 'grid', gridTemplateColumns: 'minmax(90px, 0.7fr) minmax(150px, 1fr) minmax(170px, 1.6fr) auto',
  gap: 1, alignItems: 'start', mb: 1};

function matches(field, filter) {
  if(field.column !== undefined) return filter.column === field.column;
  return Boolean(filter.field) && filter.field.source_id === field.field?.source_id &&
    filter.field.field === field.field?.field;
}

// A stored operator stays selectable until the column's type is known.
function operatorChoices(category, current) {
  const operators = operatorsFor(category);
  return operators.includes(current) ? operators : [...operators, current];
}

function valueHelp(operator) {
  if(isListOperator(operator)) return gettext('Separate values with commas.');
  if(isRangeOperator(operator)) return gettext('From and to, separated by a comma.');
  return undefined;
}

function ValueControl({filter, label, category, error, dispatch}) {
  const patch = (text) => dispatch({type: 'updateFilter', key: filter.key, patch: {text}});
  if(category === CATEGORIES.BOOLEAN && !isListOperator(filter.operator)) {
    return <Select size="small" label={gettext('Value for %s', label)} value={filter.text}
      validationMessage={error}
      options={[{value: '', label: gettext('Choose true or false')},
        {value: 'true', label: gettext('true')}, {value: 'false', label: gettext('false')}]}
      onChange={patch} />;
  }
  return <TextField size="small" label={gettext('Value for %s', label)} value={filter.text}
    validationMessage={error} helperText={valueHelp(filter.operator)}
    placeholder={category === CATEGORIES.DATE ? gettext('YYYY-MM-DD') : undefined}
    onChange={(event) => patch(event.target.value)} />;
}

ValueControl.propTypes = {
  filter: PropTypes.object.isRequired, label: PropTypes.string.isRequired,
  category: PropTypes.string.isRequired, error: PropTypes.string, dispatch: PropTypes.func.isRequired,
};

/** Typed filters: the operators and value control follow the column's type. */
export default function FiltersSection({filters, fields, parameters, errors, dispatch}) {
  const add = (id) => {
    const field = fields.find((candidate) => candidate.id === id);
    if(!field) return;
    dispatch({type: 'addFilter', valueType: field.category,
      operator: operatorsFor(field.category)[0],
      ...(field.column !== undefined ? {column: field.column} : {field: field.field})});
  };
  return <Section title={gettext('Filters')} qaKey="bi.builder.filters">
    {filters.map((filter) => {
      const field = fields.find((candidate) => matches(candidate, filter));
      const label = field?.label || filter.column || filter.field?.field || '';
      const category = filter.type;
      const error = errorAt(errors, `filters.${filter.key}`);
      const bound = Boolean(filter.parameterId);
      return <Box key={filter.key} role="group" aria-label={gettext('Filter on %s', label)} sx={ROW_SX}>
        <Box sx={{fontSize: '0.8125rem', alignSelf: 'center', overflowWrap: 'anywhere'}}>{label}</Box>
        <Select size="small" label={gettext('Operator for %s', label)} value={filter.operator}
          options={operatorChoices(category, filter.operator).map(
            (operator) => ({value: operator, label: operatorLabel(operator)}))}
          onChange={(operator) => dispatch({type: 'updateFilter', key: filter.key, patch: {operator}})} />
        <Box sx={{display: 'grid', gap: 1}}>
          {!isUnaryOperator(filter.operator) && !bound &&
            <ValueControl filter={filter} label={label} category={category} error={error} dispatch={dispatch} />}
          {!isUnaryOperator(filter.operator) && parameters.length > 0 &&
            <Select size="small" label={gettext('Compare %s to', label)} value={filter.parameterId}
              options={[{value: '', label: gettext('A typed value')},
                ...parameters.map((parameter) => ({value: parameter.id, label: gettext('Parameter %s', parameter.name)}))]}
              onChange={(parameterId) => dispatch({type: 'updateFilter', key: filter.key, patch: {parameterId}})} />}
        </Box>
        <Button size="small" aria-label={gettext('Remove filter on %s', label)}
          onClick={() => dispatch({type: 'removeFilter', key: filter.key})}>{gettext('Remove')}</Button>
      </Box>;
    })}
    <Select size="small" label={gettext('Add a filter on')} value="" disabled={fields.length === 0}
      options={[{value: '', label: gettext('Choose a column')},
        ...fields.map((field) => ({value: field.id, label: field.label}))]}
      onChange={add} />
  </Section>;
}

FiltersSection.propTypes = {
  filters: PropTypes.array.isRequired,
  fields: PropTypes.arrayOf(PropTypes.shape({
    id: PropTypes.string.isRequired, label: PropTypes.string.isRequired, category: PropTypes.string.isRequired,
    column: PropTypes.string, field: PropTypes.object,
  })).isRequired,
  parameters: PropTypes.array.isRequired,
  errors: PropTypes.array.isRequired,
  dispatch: PropTypes.func.isRequired,
};
