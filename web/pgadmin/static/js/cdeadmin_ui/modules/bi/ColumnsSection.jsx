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

/**
 * Pick the columns to show, or (once summaries exist) the columns to group
 * by. The same list serves both, so the heading says which one it is.
 */
export default function ColumnsSection({columns, selected, summarized, loading, onToggle, error}) {
  const title = summarized ? gettext('Group by') : gettext('Columns');
  const chosen = new Set(selected.map((entry) => entry.column));
  return <Section title={title} error={error} qaKey="bi.builder.columns">
    {loading && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Loading columns...')}</Box>}
    {!loading && columns.length === 0 && <EmptyState message={gettext('Choose a table to list its columns.')} />}
    <Box role="group" aria-label={title}
      sx={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', maxHeight: 200, overflow: 'auto'}}>
      {columns.map((column) => <Checkbox key={column.name} size="small"
        label={<span>{column.name}{column.type &&
          <Box component="span" sx={{color: 'text.secondary', ml: 0.5, fontSize: '0.7rem'}}>{column.type}</Box>}</span>}
        checked={chosen.has(column.name)} onChange={(checked) => onToggle(column.name, checked)} />)}
    </Box>
  </Section>;
}

ColumnsSection.propTypes = {
  columns: PropTypes.arrayOf(PropTypes.shape({name: PropTypes.string.isRequired, type: PropTypes.string})).isRequired,
  selected: PropTypes.arrayOf(PropTypes.shape({column: PropTypes.string.isRequired})).isRequired,
  summarized: PropTypes.bool,
  loading: PropTypes.bool,
  onToggle: PropTypes.func.isRequired,
  error: PropTypes.string,
};
