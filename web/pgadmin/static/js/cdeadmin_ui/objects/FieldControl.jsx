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

/*
 * A short fixed list of choices is shown as checkboxes instead of behind a
 * picker, so every option is visible (compact_forms.rst: multiple choices use
 * checkboxes or multi-selects). The rule is the same for every engine. Choices
 * drawn from the draft or catalog at runtime, long lists and grid cells keep
 * the picker, so a form's layout never depends on the data it is showing.
 */
export const MAX_CHECKBOX_CHOICES = 12;

export function showsChoicesAsCheckboxes(field, inGrid=false) {
  return !inGrid && field.control === 'multiselect' && Array.isArray(field.options) &&
    field.options.length > 0 && field.options.length <= MAX_CHECKBOX_CHOICES;
}

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
  error, cellErrors, disabled=false, dense=false, inGrid=false, mode='create'}) {
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
  // Provider-native forms declare comments and other free text as multiline, and JSON values as
  // json (text the provider parses). Both were read-only "unsupported" boxes until the browser
  // pass of 2026-11-12, which left every native editor's comment uneditable.
  if(control === 'multiline') {
    return <TextArea {...common} value={value ?? ''} rows={3} placeholder={field.placeholder}
      onChange={(event) => onChange(event.target.value)} />;
  }
  if(control === 'json') {
    return <TextArea {...common} rows={3} placeholder={field.placeholder}
      value={typeof value === 'string' ? value : (value === undefined || value === null ? '' : JSON.stringify(value, null, 1))}
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
  // Help is help: only an error turns a picker red.
  const picker = {label: field.label, required: Boolean(field.required), disabled: isDisabled, fullWidth: true,
    size: dense ? 'small' : 'medium', validationMessage: error || undefined, helperText: help || undefined};
  if(control === 'multiselect' && showsChoicesAsCheckboxes(field, inGrid)) {
    // As with the picker, only offered options are shown and a value outside
    // them is dropped on the next change; the result keeps option order.
    const chosen = new Set(Array.isArray(value) ? value : []);
    const toggle = (optionValue, checked) => {
      const next = new Set(chosen);
      if(checked) next.add(optionValue); else next.delete(optionValue);
      onChange(options.filter((option) => next.has(option.value)).map((option) => option.value));
    };
    return <Box component="fieldset" data-cdeadmin-qa-key={qaKey} disabled={isDisabled}
      aria-describedby={error || help ? helpId : undefined} aria-invalid={error ? 'true' : undefined}
      sx={{m: 0, p: 0, border: 0, minWidth: 0, gridColumn: '1 / -1'}}>
      <Box component="legend" sx={{p: 0, mb: 0.5, fontSize: '0.75rem',
        color: error ? 'error.main' : 'text.secondary'}}>
        {field.label}{field.required ? ' *' : ''}
      </Box>
      <Box sx={{display: 'grid', columnGap: 1,
        gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 14rem), 1fr))'}}>
        {options.map((option) => <Checkbox key={String(option.value)}
          label={option.label ?? String(option.value)} checked={chosen.has(option.value)}
          disabled={isDisabled} size={dense ? 'small' : 'medium'}
          onChange={(checked) => toggle(option.value, checked)} />)}
      </Box>
      <HelpLine id={helpId} error={error} help={help} />
    </Box>;
  }
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
      cellErrors={cellErrors} help={help} mode={mode} />;
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
  // Grid cell errors keyed `field[index].column` (descriptors.validateDraft).
  cellErrors: PropTypes.object,
  disabled: PropTypes.bool,
  dense: PropTypes.bool,
  // Set by RecordGrid: a cell keeps the picker for a multiselect.
  inGrid: PropTypes.bool,
};
