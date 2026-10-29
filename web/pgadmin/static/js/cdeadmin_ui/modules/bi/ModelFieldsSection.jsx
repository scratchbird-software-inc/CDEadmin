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
import {Checkbox} from '../../primitives/Choice';
import {EmptyState} from '../../feedback/EmptyState';
import Section from './Section';

function Group({title, items, chosen, onToggle}) {
  return <Box role="group" aria-label={title}
    sx={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', maxHeight: 180, overflow: 'auto'}}>
    {items.map((item) => <Checkbox key={item.id} size="small" label={item.name}
      checked={chosen.includes(item.id)} onChange={(checked) => onToggle(item.id, checked)} />)}
  </Box>;
}

Group.propTypes = {
  title: PropTypes.string.isRequired, items: PropTypes.array.isRequired,
  chosen: PropTypes.array.isRequired, onToggle: PropTypes.func.isRequired,
};

/** Dimensions to group by and measures to compute, from a semantic model. */
export default function ModelFieldsSection({model, dimensions, measures, loading, error, onToggleDimension, onToggleMeasure}) {
  return <Section title={gettext('Model fields')} error={error} qaKey="bi.builder.model-fields">
    {loading && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Loading model...')}</Box>}
    {!loading && !model && <EmptyState message={gettext('Choose a semantic model to list its fields.')} />}
    {model && <Box sx={{display: 'grid', gap: 1}}>
      <Box component="h4" sx={{m: 0, fontSize: '0.75rem', color: 'text.secondary'}}>{gettext('Group by')}</Box>
      <Group title={gettext('Dimensions')} items={model.dimensions} chosen={dimensions} onToggle={onToggleDimension} />
      <Box component="h4" sx={{m: 0, fontSize: '0.75rem', color: 'text.secondary'}}>{gettext('Measures')}</Box>
      <Group title={gettext('Measures')} items={model.measures} chosen={measures} onToggle={onToggleMeasure} />
    </Box>}
  </Section>;
}

ModelFieldsSection.propTypes = {
  model: PropTypes.shape({dimensions: PropTypes.array.isRequired, measures: PropTypes.array.isRequired}),
  dimensions: PropTypes.array.isRequired,
  measures: PropTypes.array.isRequired,
  loading: PropTypes.bool,
  error: PropTypes.string,
  onToggleDimension: PropTypes.func.isRequired,
  onToggleMeasure: PropTypes.func.isRequired,
};
