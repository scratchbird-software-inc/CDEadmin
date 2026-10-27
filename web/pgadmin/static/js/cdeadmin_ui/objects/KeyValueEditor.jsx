/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Name/value pairs for a descriptor `keyvalue` field (engine attributes,
 * per-database settings, config maps). Value shape is an object; the editor
 * never asks the user to type JSON.
 */

import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import {Box, Stack} from '../primitives/Layout';
import {TextField} from '../primitives/Field';
import {Button, IconButton} from '../primitives/Button';
import {ValidationMessage} from '../feedback/Indicators';

function entries(value) {
  if(value && typeof value === 'object' && !Array.isArray(value)) {
    return Object.entries(value).map(([key, item]) => ({key, value: item}));
  }
  if(Array.isArray(value)) {
    return value.map((item) => typeof item === 'object' && item !== null ?
      {key: item.key ?? item.name ?? '', value: item.value ?? ''} : {key: String(item), value: ''});
  }
  return [];
}

function toObject(rows) {
  const out = {};
  for(const row of rows) {
    if(row.key !== '') out[row.key] = row.value;
  }
  return out;
}

export default function KeyValueEditor({field, value, onChange, disabled=false, error, help}) {
  // Rows live locally so a half-typed name is not dropped by the object view.
  const [rows, setRows] = useState(() => entries(value));
  useEffect(() => {
    const external = toObject(entries(value));
    if(JSON.stringify(external) !== JSON.stringify(toObject(rows))) setRows(entries(value));
  }, [value]);
  const headingId = `keyvalue-${field.field_id}`;
  const commit = (updated) => {
    setRows(updated);
    onChange(toObject(updated));
  };
  const set = (index, part, next) => commit(rows.map((row, position) =>
    position === index ? {...row, [part]: next} : row));
  return <Box role="group" aria-labelledby={headingId} data-cdeadmin-qa-key={`object-editor.keyvalue.${field.field_id}`}
    sx={{border: '1px solid', borderColor: error ? 'error.main' : 'divider', p: 1}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center', mb: 1}}>
      <Box id={headingId} component="span" sx={{fontSize: '0.8125rem', fontWeight: 600, flex: 1}}>
        {field.label}{field.required ? ' *' : ''}
      </Box>
      <Button size="small" intent="neutral" disabled={disabled}
        onClick={() => commit([...rows, {key: '', value: ''}])}>
        Add setting
      </Button>
    </Stack>
    <Stack gap="compact">
      {rows.map((row, index) => <Stack key={index} direction="row" gap="compact">
        <TextField size="small" label={`Name ${index + 1}`} value={row.key} disabled={disabled}
          onChange={(event) => set(index, 'key', event.target.value)} sx={{flex: 1}} />
        <TextField size="small" label={`Value ${index + 1}`} disabled={disabled}
          value={typeof row.value === 'object' ? JSON.stringify(row.value) : String(row.value ?? '')}
          onChange={(event) => set(index, 'value', event.target.value)} sx={{flex: 2}} />
        <IconButton label={`Remove setting ${index + 1}`} disabled={disabled}
          onClick={() => commit(rows.filter((_row, position) => position !== index))}>×</IconButton>
      </Stack>)}
      {rows.length === 0 && <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>No settings.</Box>}
    </Stack>
    {error && <ValidationMessage status="error">{error}</ValidationMessage>}
    {!error && help && <Box sx={{fontSize: '0.75rem', color: 'text.secondary', mt: 0.5}}>{help}</Box>}
  </Box>;
}

KeyValueEditor.propTypes = {
  field: PropTypes.object.isRequired,
  value: PropTypes.any,
  onChange: PropTypes.func.isRequired,
  disabled: PropTypes.bool,
  error: PropTypes.string,
  help: PropTypes.string,
};
