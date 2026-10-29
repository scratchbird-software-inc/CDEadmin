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
import {Box} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {errorAt} from './validateState';

const TYPES = ['string', 'integer', 'number', 'boolean', 'date', 'datetime', 'array'];
const TOKEN = /\{\{\s*([A-Za-z][A-Za-z0-9_-]*)\s*\}\}/g;

/** Parameter names written as {{name}} in SQL text (a hint; the server parses exactly). */
export function sqlParameterNames(sql) {
  return [...new Set([...String(sql || '').matchAll(TOKEN)].map((match) => match[1]))];
}

const ROW_SX = {display: 'grid', gridTemplateColumns: 'minmax(110px, 0.8fr) minmax(130px, 1fr) minmax(120px, 1fr) minmax(130px, 1fr) minmax(130px, 1fr) auto',
  gap: 1, alignItems: 'start', mb: 1};

/** Declared parameters of the question, and the values to run it with. */
export default function ParametersPanel({parameters, values, sql, errors, dispatch}) {
  const [draft, setDraft] = useState('');
  const declared = new Set(parameters.map((parameter) => parameter.id));
  const suggested = sqlParameterNames(sql).filter((name) => !declared.has(name));
  const declare = (id) => {
    const name = id.trim();
    if(!name) return;
    dispatch({type: 'addParameter', parameter: {id: name, name, type: 'string', required: false}});
    setDraft('');
  };
  return <Box data-cdeadmin-qa-key="bi.parameters" sx={{display: 'grid', gap: 1}}>
    {parameters.length === 0 && <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {gettext('No parameters. Declare one to use it in a filter or, in SQL, as {{name}}.')}
    </Box>}
    {parameters.map((parameter) => <Box key={parameter.id} role="group"
      aria-label={gettext('Parameter %s', parameter.id)} sx={ROW_SX}>
      <Box sx={{alignSelf: 'center', overflowWrap: 'anywhere', fontSize: '0.8125rem'}}>{parameter.id}</Box>
      <Select size="small" label={gettext('Type of %s', parameter.id)} value={parameter.type}
        options={TYPES.map((type) => ({value: type, label: type}))}
        onChange={(type) => dispatch({type: 'updateParameter', id: parameter.id, patch: {type}})} />
      <TextField size="small" label={gettext('Default for %s', parameter.id)} value={parameter.defaultText}
        onChange={(event) => dispatch({type: 'updateParameter', id: parameter.id, patch: {defaultText: event.target.value}})} />
      <TextField size="small" label={gettext('Value to run %s with', parameter.id)} value={values[parameter.id] ?? ''}
        validationMessage={errorAt(errors, `parameters.${parameter.id}`)}
        helperText={parameter.type === 'array' ? gettext('Separate values with commas.') : undefined}
        onChange={(event) => dispatch({type: 'setValue', id: parameter.id, text: event.target.value})} />
      <Checkbox size="small" label={gettext('Required')} checked={parameter.required}
        onChange={(required) => dispatch({type: 'updateParameter', id: parameter.id, patch: {required}})} />
      <Button size="small" aria-label={gettext('Remove parameter %s', parameter.id)}
        onClick={() => dispatch({type: 'removeParameter', id: parameter.id})}>{gettext('Remove')}</Button>
    </Box>)}
    <Box sx={{display: 'flex', gap: 1, alignItems: 'flex-start', flexWrap: 'wrap'}}>
      <TextField size="small" label={gettext('New parameter name')} value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => { if(event.key === 'Enter') { event.preventDefault(); declare(draft); } }} />
      <Button size="small" disabled={!draft.trim()} onClick={() => declare(draft)}>{gettext('Add parameter')}</Button>
      {suggested.map((name) => <Button key={name} size="small" onClick={() => declare(name)}>
        {gettext('Declare %s from SQL', name)}
      </Button>)}
    </Box>
  </Box>;
}

ParametersPanel.propTypes = {
  parameters: PropTypes.array.isRequired,
  values: PropTypes.object.isRequired,
  sql: PropTypes.string,
  errors: PropTypes.array.isRequired,
  dispatch: PropTypes.func.isRequired,
};
