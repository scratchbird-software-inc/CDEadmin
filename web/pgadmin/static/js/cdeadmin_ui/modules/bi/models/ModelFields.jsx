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
import {Box, Stack} from '../../../primitives/Layout';
import {EmptyState} from '../../../feedback/EmptyState';
import AdaptiveFieldPlacementGrid from '../../../objects/AdaptiveFieldPlacementGrid';
import FieldControl from '../../../objects/FieldControl';
import {activeFields} from '../../../objects/descriptors';

function groups(fields) {
  const found = [];
  const index = {};
  for(const field of fields) {
    const name = field.group || '';
    if(!(name in index)) {
      index[name] = found.length;
      found.push({name, fields: []});
    }
    found[index[name]].fields.push(field);
  }
  return found;
}

/**
 * The typed controls of one form tab (descriptor shape, see modelForm.js).
 * Every field is a FieldControl; grids are RecordGrids, so the model JSON is
 * never edited as text here.
 */
export default function ModelFields({tab, draft, onChange, context, disabled = false, errors = {}, children}) {
  const fields = activeFields(tab.fields, {mode: 'alter', draft});
  if(!fields.length) return <EmptyState message={gettext('Nothing to set on %s.', tab.title)} />;
  return <Stack gap="comfortable" data-cdeadmin-qa-key={`bi.models.tab.${tab.tab}`}>
    {groups(fields).map((group) => <Box key={group.name || '_'} component="section" aria-label={group.name || tab.title}>
      {group.name && <Box component="h4" sx={{m: 0, mb: 1, fontSize: '0.75rem', fontWeight: 600,
        textTransform: 'uppercase', color: 'text.secondary'}}>{group.name}</Box>}
      <AdaptiveFieldPlacementGrid
        fields={group.fields}
        draft={draft}
        context={context}
        qaKey={`bi.models.grid.${tab.tab}.${group.name || 'default'}`}
        renderField={(field) => (
          <FieldControl
            field={field}
            value={draft[field.field_id]}
            draft={draft}
            context={context}
            error={errors[field.field_id]}
            disabled={disabled}
            onChange={(value) => onChange(field.field_id, value)}
          />
        )}
      />
    </Box>)}
    {children}
  </Stack>;
}

ModelFields.propTypes = {
  tab: PropTypes.object.isRequired,
  draft: PropTypes.object.isRequired,
  onChange: PropTypes.func.isRequired,
  context: PropTypes.object,
  disabled: PropTypes.bool,
  errors: PropTypes.object,
  children: PropTypes.node,
};
