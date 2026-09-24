// Provider-declared scalar editors. Exact numbers stay text on the JSON wire.
import PropTypes from 'prop-types';
import {Box, MenuItem, TextField} from '@mui/material';
import gettext from 'sources/gettext';
import ProviderArrayInput, {arrayShape} from './ProviderArrayInput';

export function rowInputDraft(value, kind) {
  if (kind === 'array') return {text: value == null ? '' : JSON.stringify(value), isNull: value === null};
  return {text: kind === 'binary' && value?.encoding === 'base64' ? value.data :
    value == null ? '' : String(value), isNull: value === null};
}

export function rowInputValue(draft, kind, spec) {
  if (draft.isNull) return null;
  if (kind === 'array') {
    const lengths = arrayShape(spec);
    const visit = (items, depth) => {
      if (!Array.isArray(items) || items.length !== lengths[depth]) throw new Error(gettext('Array dimensions do not match native bounds.'));
      return items.map((item) => {
        if (depth < lengths.length - 1) return visit(item, depth + 1);
        if (item == null) throw new Error(gettext('Array elements cannot be NULL.'));
        if (typeof item === 'number' && !Number.isSafeInteger(item)) throw new Error(gettext('Exact array numbers must be transmitted as text.'));
        if (spec.element_kind === 'text' && typeof item !== 'string') throw new Error(gettext('Text array elements must be strings.'));
        const result = rowInputValue(rowInputDraft(item, spec.element_kind), spec.element_kind);
        if (spec.length && (spec.element_kind === 'binary' ? result.byte_length > spec.length : spec.element_kind === 'text' && Array.from(result).length > spec.length)) throw new Error(gettext('Array element exceeds the declared length.'));
        return ['float32', 'float64'].includes(spec.element_kind) ? result.data : result;
      });
    };
    return visit(JSON.parse(draft.text), 0);
  }
  if (kind === 'binary') {
    try {
      const decoded = atob(draft.text);
      if (btoa(decoded) !== draft.text) throw new Error('Noncanonical base64');
      return {encoding: 'base64', data: draft.text, byte_length: decoded.length};
    } catch {
      throw new Error(gettext('Enter binary data as canonical Base64.'));
    }
  }
  if (kind === 'boolean') {
    if (!['true', 'false'].includes(draft.text)) {
      throw new Error(gettext('Choose True or False for a Boolean value.'));
    }
    return draft.text === 'true';
  }
  if (['date', 'time', 'timestamp'].includes(kind)) {
    const day = '\\d{4}-\\d{2}-\\d{2}';
    const clock = '\\d{2}:\\d{2}:\\d{2}(?:\\.\\d{1,4})?';
    const expression = kind === 'date' ? day : kind === 'time' ? clock : `${day}[ T]${clock}`;
    if (!new RegExp(`^${expression}$`).test(draft.text)) throw new Error(gettext('Enter an ISO date/time with at most four fractional second digits and no time zone.'));
    return draft.text;
  }
  if (kind === 'integer' && !/^[+-]?\d+$/.test(draft.text)) {
    throw new Error(gettext('Enter an integer without a decimal point.'));
  }
  const decimalSpecial = kind === 'decfloat' && /^[+-]?(?:s?NaN|Infinity)$/i.test(draft.text);
  if (['decimal', 'decfloat', 'float32', 'float64'].includes(kind) && !decimalSpecial && !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(draft.text)) {
    throw new Error(gettext('Enter an exact decimal value.'));
  }
  if (['float32', 'float64'].includes(kind)) return {encoding: kind, data: draft.text};
  return draft.text;
}

export default function ProviderRowInput({kind, draft, label, disabled, onChange, spec}) {
  if (kind === 'array') return <ProviderArrayInput {...{draft, label, disabled, onChange, spec}} />;
  return <Box sx={{display: 'flex', gap: 0.5, minWidth: '18rem'}}>
    <TextField size="small" select value={draft.isNull ? 'null' : 'value'}
      sx={{minWidth: '6rem', flexShrink: 0}}
      disabled={disabled} SelectProps={{inputProps: {'aria-label': `${label} mode`}}}
      onChange={(event) => onChange({...draft, isNull: event.target.value === 'null'})}>
      <MenuItem value="value">{gettext('Value')}</MenuItem>
      <MenuItem value="null">NULL</MenuItem>
    </TextField>
    {kind === 'boolean' ?
      <TextField size="small" select value={draft.text}
        disabled={disabled || draft.isNull}
        SelectProps={{inputProps: {'aria-label': label}}}
        onChange={(event) => onChange({...draft, text: event.target.value})}>
        <MenuItem value="">{gettext('Choose value')}</MenuItem>
        <MenuItem value="true">{gettext('True')}</MenuItem>
        <MenuItem value="false">{gettext('False')}</MenuItem>
      </TextField> :
      <TextField size="small" value={draft.text}
        helperText={kind === 'binary' ? gettext('Base64 binary data') :
          ['float32', 'float64'].includes(kind) ? gettext('Approximate native FLOAT/DOUBLE value') : undefined}
        disabled={disabled || draft.isNull} inputProps={{'aria-label': label}}
        onChange={(event) => onChange({...draft, text: event.target.value})} />}
  </Box>;
}

ProviderRowInput.propTypes = {
  kind: PropTypes.oneOf(['text', 'integer', 'decimal', 'decfloat', 'float32', 'float64', 'boolean', 'binary', 'array']).isRequired,
  spec: PropTypes.object,
  draft: PropTypes.shape({text: PropTypes.string, isNull: PropTypes.bool}).isRequired,
  label: PropTypes.string.isRequired,
  disabled: PropTypes.bool,
  onChange: PropTypes.func.isRequired,
};
