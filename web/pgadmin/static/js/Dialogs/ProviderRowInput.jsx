// Provider-declared scalar editors. Exact numbers stay text on the JSON wire.
import PropTypes from 'prop-types';
import {Box, MenuItem, TextField} from '@mui/material';
import gettext from 'sources/gettext';

export function rowInputDraft(value, kind) {
  return {text: kind === 'binary' && value?.encoding === 'base64' ? value.data :
    value == null ? '' : String(value), isNull: value === null};
}

export function rowInputValue(draft, kind) {
  if (draft.isNull) return null;
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

export default function ProviderRowInput({kind, draft, label, disabled, onChange}) {
  return <Box sx={{display: 'flex', gap: 0.5, minWidth: 220}}>
    <TextField size="small" select value={draft.isNull ? 'null' : 'value'}
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
  kind: PropTypes.oneOf(['text', 'integer', 'decimal', 'decfloat', 'float32', 'float64', 'boolean', 'binary']).isRequired,
  draft: PropTypes.shape({text: PropTypes.string, isNull: PropTypes.bool}).isRequired,
  label: PropTypes.string.isRequired,
  disabled: PropTypes.bool,
  onChange: PropTypes.func.isRequired,
};
