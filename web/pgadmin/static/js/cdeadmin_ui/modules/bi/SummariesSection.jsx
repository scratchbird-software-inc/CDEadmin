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
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {aggregationLabel, aggregationsFor, ALL_AGGREGATIONS} from './columnTypes';
import {defaultAggregationName} from './outputs';
import {errorAt} from './validateState';
import Section from './Section';

const ROW_SX = {display: 'grid', gridTemplateColumns: 'minmax(150px, 1fr) minmax(150px, 1.2fr) minmax(120px, 1fr) auto',
  gap: 1, alignItems: 'start', mb: 1};

/** Summaries (count, sum, average, minimum, maximum, distinct count). */
export default function SummariesSection({aggregations, columns, errors, dispatch}) {
  const category = (name) => columns.find((column) => column.name === name)?.category;
  const columnOptions = (fn) => columns
    .filter((column) => aggregationsFor(column.category).includes(fn))
    .map((column) => ({value: column.name, label: column.name}));
  return <Section title={gettext('Summaries')} qaKey="bi.builder.summaries"
    actions={<Button size="small" onClick={() => dispatch({type: 'addAggregation', function: 'count'})}>
      {gettext('Add summary')}
    </Button>}>
    {aggregations.length === 0 && <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {gettext('No summaries. Add one to count, total or average rows; the columns you picked become the grouping.')}
    </Box>}
    {aggregations.map((aggregation, index) => {
      const label = (text) => gettext('%s (summary %s)', text, index + 1);
      const needsColumn = aggregation.function !== 'count';
      const known = category(aggregation.column);
      return <Box key={index} role="group" aria-label={gettext('Summary %s', index + 1)} sx={ROW_SX}>
        <Select size="small" label={label(gettext('Summary'))} value={aggregation.function}
          options={ALL_AGGREGATIONS.map((fn) => ({value: fn, label: aggregationLabel(fn)}))}
          onChange={(fn) => dispatch({type: 'updateAggregation', index, patch: {
            function: fn,
            // A column that does not fit the new summary is dropped rather than kept invalid.
            ...(aggregation.column && known && !aggregationsFor(known).includes(fn) ? {column: ''} : {}),
          }})} />
        <Select size="small" label={label(gettext('Column'))} value={aggregation.column || ''}
          validationMessage={errorAt(errors, `aggregations.${index}`)}
          options={[{value: '', label: needsColumn ? gettext('Choose a column') : gettext('(all rows)')},
            ...columnOptions(aggregation.function),
            // A stored column stays selectable while the column list loads.
            ...(aggregation.column && !columnOptions(aggregation.function).some((option) => option.value === aggregation.column) ?
              [{value: aggregation.column, label: aggregation.column}] : [])]}
          onChange={(column) => dispatch({type: 'updateAggregation', index, patch: {column}})} />
        <TextField size="small" label={label(gettext('Name'))} value={aggregation.alias || ''}
          placeholder={defaultAggregationName(aggregation)}
          onChange={(event) => dispatch({type: 'updateAggregation', index, patch: {alias: event.target.value.trim()}})} />
        <Stack direction="row">
          <Button size="small" intent="neutral" aria-label={gettext('Remove summary %s', index + 1)}
            onClick={() => dispatch({type: 'removeAggregation', index})}>{gettext('Remove')}</Button>
        </Stack>
      </Box>;
    })}
  </Section>;
}

SummariesSection.propTypes = {
  aggregations: PropTypes.array.isRequired,
  columns: PropTypes.array.isRequired,
  errors: PropTypes.array.isRequired,
  dispatch: PropTypes.func.isRequired,
};
