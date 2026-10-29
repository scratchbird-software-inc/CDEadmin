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
import {NumberField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {errorAt} from './validateState';
import Section from './Section';

const ROW_SX = {display: 'grid', gridTemplateColumns: 'minmax(150px, 1.4fr) minmax(130px, 1fr) auto',
  gap: 1, alignItems: 'start', mb: 1};

/** Sort order (multiple keys, reorderable) and the row limit. */
export default function OrderSection({orderBy, targets, limit, errors, dispatch}) {
  const labelOf = (id) => targets.find((target) => target.id === id)?.label || id;
  const free = targets.filter((target) => !orderBy.some((entry) => entry.target === target.id));
  return <Section title={gettext('Sort and limit')} qaKey="bi.builder.order">
    {orderBy.map((entry, index) => {
      const label = labelOf(entry.target);
      return <Box key={entry.target} role="group" aria-label={gettext('Sort by %s', label)} sx={ROW_SX}>
        <Select size="small" label={gettext('Sort key %s', index + 1)} value={entry.target}
          validationMessage={errorAt(errors, `order.${index}`)}
          options={[entry.target, ...free.map((target) => target.id)].map((id) => ({value: id, label: labelOf(id)}))}
          onChange={(target) => dispatch({type: 'updateOrder', index, patch: {target}})} />
        <Select size="small" label={gettext('Direction for %s', label)} value={entry.direction}
          options={[{value: 'asc', label: gettext('Ascending')}, {value: 'desc', label: gettext('Descending')}]}
          onChange={(direction) => dispatch({type: 'updateOrder', index, patch: {direction}})} />
        <Box sx={{display: 'flex', gap: 0.5}}>
          <Button size="small" disabled={index === 0} aria-label={gettext('Move %s earlier', label)}
            onClick={() => dispatch({type: 'moveOrder', index, delta: -1})}>{gettext('Up')}</Button>
          <Button size="small" disabled={index === orderBy.length - 1} aria-label={gettext('Move %s later', label)}
            onClick={() => dispatch({type: 'moveOrder', index, delta: 1})}>{gettext('Down')}</Button>
          <Button size="small" aria-label={gettext('Remove sort on %s', label)}
            onClick={() => dispatch({type: 'removeOrder', index})}>{gettext('Remove')}</Button>
        </Box>
      </Box>;
    })}
    <Box sx={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 1}}>
      <Select size="small" label={gettext('Add a sort on')} value="" disabled={free.length === 0}
        options={[{value: '', label: gettext('Choose a column')}, ...free.map((target) => ({value: target.id, label: target.label}))]}
        onChange={(target) => target && dispatch({type: 'addOrder', target})} />
      <NumberField size="small" label={gettext('Row limit')} value={Number.isInteger(limit) ? String(limit) : ''}
        inputProps={{min: 1, max: 10000}} validationMessage={errorAt(errors, 'limit')}
        onChange={(event) => dispatch({type: 'setLimit', limit: event.target.value === '' ? NaN : Number(event.target.value)})} />
    </Box>
  </Section>;
}

OrderSection.propTypes = {
  orderBy: PropTypes.array.isRequired,
  targets: PropTypes.array.isRequired,
  limit: PropTypes.number,
  errors: PropTypes.array.isRequired,
  dispatch: PropTypes.func.isRequired,
};
