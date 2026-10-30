/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * One typed control per descriptor field. This is the only place a
 * descriptor `control` value is turned into a widget; the object editor,
 * grids and operation dialogs all go through it. It composes cdeadmin_ui
 * primitives only (design principle 9).
 */

import {useId} from 'react';
import PropTypes from 'prop-types';
import {NumberField, SecretField, TextArea, TextField} from '../primitives/Field';
import {Checkbox, Select} from '../primitives/Choice';
import {ComboBox, MultiSelect, Radio} from '../primitives/AdvancedControls';
import {Box} from '../primitives/Layout';
import {ValidationMessage} from '../feedback/Indicators';
import CodeEditor from '../editors/CodeEditor';
import {fieldOptions} from './descriptors';
import RecordGrid from './RecordGrid';
import KeyValueEditor from './KeyValueEditor';

const SIMPLE_TEXT = new Set(['text', 'file']);

function HelpLine({id, error, help}) {
  if(error) return <ValidationMessage id={id} status="error">{error}</ValidationMessage>;
  if(help) return <Box id={id} component="p" sx={{m: 0, mt: 0.5, fontSize: '0.75rem', color: 'text.secondary'}}>{help}</Box>;
  return null;
}

HelpLine.propTypes = {id: PropTypes.string, error: PropTypes.string, help: PropTypes.string};

export function fieldHelpText(field) {
  if(field.available === false) return field.unavailable_reason || 'Not available on this version';
  return [field.help, field.native_keyword ? `Native: ${field.native_keyword}` : null].filter(Boolean).join(' ');
}

export default function FieldControl({field, value, onChange, draft={}, context={}, resourceKind,
  error, disabled=false, dense=false, mode='create'}) {
  const helpId = useId();
  const unavailable = field.available === false;
  const isDisabled = disabled || unavailable || Boolean(field.readonly);
  const help = fieldHelpText(field);
  const qaKey = `object-editor.field.${field.field_id}`;
  const common = {
    label: field.label, required: field.required, disabled: isDisabled, fullWidth: true,
    size: dense ? 'small' : 'medium', validationMessage: error,
    helperText: error || help || undefined,
    inputProps: {'aria-describedby': help ? helpId : undefined, 'data-cdeadmin-qa-key': qaKey},
  };
  const options = fieldOptions(field, {context, draft, resourceKind});
  const control = field.control;

  if(SIMPLE_TEXT.has(control)) {
    return <TextField {...common} value={value ?? ''} placeholder={field.placeholder}
      onChange={(event) => onChange(event.target.value)} />;
  }
  if(control === 'number') {
    return <NumberField {...common} value={value ?? ''}
      inputProps={{...common.inputProps, min: field.min, max: field.max}}
      onChange={(event) => onChange(event.target.value === '' ? '' : Number(event.target.value))} />;
  }
  if(control === 'boolean') {
    return <Box data-cdeadmin-qa-key={qaKey}>
      <Checkbox label={field.label} checked={Boolean(value)} disabled={isDisabled}
        inputProps={{'aria-describedby': help ? helpId : undefined}}
        onChange={(checked) => onChange(checked)} />
      <HelpLine id={helpId} error={error} help={help} />
    </Box>;
  }
  if(control === 'select') {
    const current = options.some((option) => option.value === value) ? value : '';
    return <Select {...common} options={options} value={current} onChange={(next) => onChange(next)} />;
  }
  if(control === 'radio') {
    return <Box data-cdeadmin-qa-key={qaKey}>
      <Radio label={field.label} value={value ?? ''} options={options} disabled={isDisabled}
        onChange={(next) => onChange(next)} />
      <HelpLine id={helpId} error={error} help={help} />
    </Box>;
  }
  // Autocomplete-based primitives take a narrower prop set than TextField.
  const picker = {label: field.label, disabled: isDisabled, fullWidth: true, size: dense ? 'small' : 'medium',
    validationMessage: error || help || undefined};
  if(control === 'multiselect') {
    const selected = options.filter((option) => (Array.isArray(value) ? value : []).includes(option.value));
    return <Box data-cdeadmin-qa-key={qaKey}>
      <MultiSelect {...picker} options={options} value={selected}
        onChange={(next) => onChange(next.map((option) => option.value))} />
    </Box>;
  }
  if(control === 'reference') {
    const selected = options.find((option) => option.value === value) ||
      (value ? {value, label: String(value)} : null);
    return <Box data-cdeadmin-qa-key={qaKey}>
      <ComboBox {...picker} options={options} value={selected} freeEntry={!options.length}
        onChange={(next) => onChange(typeof next === 'object' && next !== null ? next.value : next)} />
    </Box>;
  }
  if(control === 'password' || control === 'secret-reference') {
    return <SecretField {...common} value={value ?? ''} allowReveal={control === 'password'}
      autoComplete="new-password" onChange={(event) => onChange(event.target.value)} />;
  }
  if(control === 'code') {
    return <Box data-cdeadmin-qa-key={qaKey}>
      <Box component="label" sx={{display: 'block', fontSize: '0.75rem', mb: 0.5,
        color: error ? 'error.main' : 'text.secondary'}}>
        {field.label}{field.required ? ' *' : ''}
      </Box>
      <CodeEditor label={field.label} value={value ?? ''} language={field.language || 'sql'}
        readonly={isDisabled} onChange={(next) => onChange(next)} />
      <HelpLine id={helpId} error={error} help={help} />
    </Box>;
  }
  if(control === 'grid' || control === 'privileges') {
    return <RecordGrid field={field} rows={Array.isArray(value) ? value : []} onChange={onChange}
      draft={draft} context={context} resourceKind={resourceKind} disabled={isDisabled} error={error}
      help={help} mode={mode} />;
  }
  if(control === 'keyvalue') {
    return <KeyValueEditor field={field} value={value} onChange={onChange} disabled={isDisabled}
      error={error} help={help} />;
  }
  // Unknown control: show it read-only rather than inventing a widget (principle 5).
  return <TextArea {...common} value={typeof value === 'string' ? value : JSON.stringify(value ?? '', null, 1)}
    disabled helperText={`Unsupported control ${control}; the descriptor needs a typed control.`} rows={2} />;
}

FieldControl.propTypes = {
  field: PropTypes.object.isRequired,
  value: PropTypes.any,
  onChange: PropTypes.func.isRequired,
  draft: PropTypes.object,
  context: PropTypes.object,
  mode: PropTypes.string,
  resourceKind: PropTypes.string,
  error: PropTypes.string,
  disabled: PropTypes.bool,
  dense: PropTypes.bool,
};
