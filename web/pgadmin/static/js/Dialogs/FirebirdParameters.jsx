import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import ProviderRowInput, {rowInputDraft, rowInputValue} from './ProviderRowInput';

export function parameterKind(parameter) {
  const type = parameter.native_type;
  if (['SHORT', 'LONG', 'INT64', 'INT128'].includes(type)) return parameter.scale ? 'decimal' : 'integer';
  if (['TEXT', 'VARYING'].includes(type)) return parameter.charset === 1 ? 'binary' : 'text';
  if (type === 'BLOB') return parameter.subtype === 1 ? 'text' : 'binary';
  return {BOOLEAN: 'boolean', FLOAT: 'float32', DOUBLE: 'float64', D_FLOAT: 'float64',
    DEC16: 'decfloat', DEC34: 'decfloat', DATE: 'text', TIME: 'text', TIMESTAMP: 'text',
    TIME_TZ: 'firebird-time-tz', TIMESTAMP_TZ: 'firebird-timestamp-tz'}[type] || 'json';
}

function exactJson(text) {
  const result = JSON.parse(text);
  const check = value => {
    if (typeof value === 'number' && !Number.isSafeInteger(value)) throw new Error('Use exact text for fractional or large numeric values.');
    if (value && typeof value === 'object') Object.values(value).forEach(check);
  };
  check(result);
  return result;
}

export default function FirebirdParameters({source, dialect, plan, parameters, onChange, onPrepare, disabled}) {
  const [hash, setHash] = useState(null), [draft, setDraft] = useState(null), [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setHash(null);
    if (window.crypto?.subtle) window.crypto.subtle.digest('SHA-256', new TextEncoder().encode(source))
      .then(value => {if (active) setHash({source, value: Array.from(new Uint8Array(value), byte => byte.toString(16).padStart(2, '0')).join('')});})
      .catch(() => {});
    return () => {active = false;};
  }, [source]);
  const current = Boolean(hash?.source === source && hash?.value === plan?.source_sha256 && plan?.client_sql_dialect === dialect);
  const available = current && plan.parameters_complete === true && Array.isArray(plan.parameters);
  const validDraft = available && draft?.plan === plan && draft?.source === source && draft?.parameters === parameters;
  const initialize = () => {
    setError('');
    try {
      const values = exactJson(parameters || '[]');
      if (!Array.isArray(values)) throw new Error('Bindings must be a positional JSON array.');
      if (values.length && values.length !== plan.parameters.length) throw new Error('Existing bindings have a different count. Edit the JSON array or explicitly clear it before initializing.');
      setDraft({plan, source, parameters, values: plan.parameters.map((parameter, index) => {
        const kind = parameterKind(parameter), value = values.length ? values[index] : null;
        return kind === 'json' ? {text: JSON.stringify(value)} : rowInputDraft(value, kind);
      })});
    } catch (failure) {setError(failure.message);}
  };
  const apply = () => {
    if (!validDraft || disabled) return;
    setError('');
    try {
      const values = draft.values.map((value, index) => {
        const kind = parameterKind(plan.parameters[index]);
        return kind === 'json' ? exactJson(value.text) : rowInputValue(value, kind);
      });
      onChange(JSON.stringify(values));
    } catch (failure) {setError(failure.message);}
  };
  return <Box sx={{my: 1}} aria-label="Firebird prepared parameters">
    <FormReference formKey="firebird-parameters" />
    <Button disabled={disabled || !source.trim()} onClick={onPrepare}>Prepare parameter metadata</Button>
    {!current && <Alert severity="info">Prepare this exact statement and SQL dialect to inspect its positional parameters. Preparation does not execute the statement or end your transaction.</Alert>}
    {current && !available && <Alert severity="warning">Native parameter count: {plan.parameter_count}. The compact editor is limited to 512 parameters; use explicit positional JSON bindings.</Alert>}
    {available && <>
      <Box>{plan.parameter_count} native parameters</Box>
      <Button disabled={disabled} onClick={initialize}>Initialize parameter grid from bindings</Button>
    </>}
    {validDraft && <>
      {plan.parameters.map((parameter, index) => {
        const kind = parameterKind(parameter), label = `Parameter ${index + 1}`;
        const change = value => {setError(''); setDraft({...draft, values: draft.values.map((old, position) => position === index ? value : old)});};
        return <Box key={index} sx={{my: 1}}>
          <Box>{label}: {[parameter.relation, parameter.field].filter(Boolean).join('.')} — {parameter.native_type}; bytes {parameter.length}; scale {parameter.scale}; charset {parameter.charset}; {parameter.nullable ? 'nullable' : 'not nullable'}</Box>
          {kind === 'json' ? <TextField label={`${label} (JSON value)`} value={draft.values[index].text} multiline
            disabled={disabled} onChange={event => change({text: event.target.value})} /> :
            <ProviderRowInput kind={kind} label={label} draft={draft.values[index]} disabled={disabled}
              firebirdBlob={parameter.native_type === 'BLOB'} onChange={change} />}
        </Box>;
      })}
      <Button disabled={disabled} onClick={apply}>Use parameter grid values</Button>
    </>}
    {error && <Alert severity="error">{error}</Alert>}
  </Box>;
}
FirebirdParameters.propTypes = {source: PropTypes.string.isRequired, dialect: PropTypes.number.isRequired,
  plan: PropTypes.object, parameters: PropTypes.string.isRequired, onChange: PropTypes.func.isRequired,
  onPrepare: PropTypes.func.isRequired, disabled: PropTypes.bool};
