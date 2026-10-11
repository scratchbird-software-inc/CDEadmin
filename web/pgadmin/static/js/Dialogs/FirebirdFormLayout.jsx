// Firebird presentation over the provider's native field contracts.
import {useEffect, useId, useState} from 'react';
import PropTypes from 'prop-types';
import {Box, Checkbox, FormControlLabel, FormHelperText, Radio, RadioGroup, TextField} from '@mui/material';
import gettext from 'sources/gettext';

const GROUPS = [
  ['Files and destination', ['split_backup', 'backup_file', 'backup_volumes',
    'backup_files', 'additional_backup_files', 'restore_database',
    'multiple_database_files', 'primary_file_pages', 'database_file_volumes']],
  ['Options', ['backup_flags', 'restore_flags', 'replace_existing', 'mode',
    'method', 'shutdown_timeout', 'repair_action', 'repair_modifiers',
    'backup_level', 'database_guid', 'direct_io', 'no_linger']],
  ['Database settings', ['page_size', 'page_buffers', 'access_mode', 'replica_mode']],
  ['Selection', ['skip_data', 'include_data', 'include_table', 'exclude_table',
    'include_index', 'exclude_index', 'tables']],
  ['Encryption and authentication', ['key_holder', 'key_name', 'crypt_plugin', 'role']],
  ['Execution and statistics', ['parallel_workers', 'statistics', 'statistics_flags',
    'verbose', 'verbose_interval', 'lock_timeout', 'keep_days', 'keep_rows']],
];

export function firebirdFieldGroups(fields) {
  const remaining = new Map(fields.map((field) => [field.field_id, field]));
  const groups = GROUPS.map(([title, ids]) => ({title,
    fields: ids.filter((id) => remaining.has(id)).map((id) => {
      const field = remaining.get(id);
      remaining.delete(id);
      return field;
    }),
  })).filter((group) => group.fields.length);
  if (remaining.size) groups.push({title: 'Additional native options',
    fields: [...remaining.values()]});
  return groups;
}

function NativeChoices({field, value, disabled, onChange, single=false}) {
  const helpId = useId();
  const options = field.options || [];
  const selected = Array.isArray(value) ? value : (field.default || []);
  const help = field.help || field.help_text;
  const choices = options.map((option) => <FormControlLabel
    key={option.value} disabled={disabled} value={option.value}
    label={option.label} control={single ? <Radio size="small" /> :
      <Checkbox size="small" checked={selected.includes(option.value)}
        onChange={(event) => onChange(event.target.checked ?
          [...selected, option.value] : selected.filter((item) => item !== option.value))} />} />);
  return <Box component="fieldset" disabled={disabled}
    aria-describedby={help ? helpId : undefined}
    sx={{m: 0, p: 1, border: 1, borderColor: 'divider', minWidth: 0}}>
    <Box component="legend">{field.label}</Box>
    {single ? <RadioGroup row value={value ?? field.default ?? ''}
      onChange={(event) => onChange(event.target.value)}>{choices}</RadioGroup> :
      <Box sx={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))'}}>
        {choices}
      </Box>}
    {help && <FormHelperText id={helpId}>{help}</FormHelperText>}
  </Box>;
}

NativeChoices.propTypes = {field: PropTypes.object.isRequired, value: PropTypes.any,
  disabled: PropTypes.bool, onChange: PropTypes.func.isRequired, single: PropTypes.bool};

export default function FirebirdFormLayout({fields, draft, disabled, onChange, renderField, onValidityChange}) {
  const [confirmations, setConfirmations] = useState({});
  const valid = fields.filter((field) => field.control === 'password').every((field) =>
    !draft[field.field_id] || confirmations[field.field_id] === draft[field.field_id]);
  useEffect(() => { onValidityChange?.(valid); }, [valid, onValidityChange]);
  return <Box data-cde-firebird-compact-form sx={{display: 'grid', gap: 1,
    '& .MuiInputBase-input': {py: 1}, '& .MuiFormControlLabel-root': {my: 0},
    '& .MuiFormHelperText-root': {mx: 0}}}>
    {firebirdFieldGroups(fields).map((group) => <Box component="fieldset"
      disabled={disabled} key={group.title} sx={{m: 0, p: 1, minWidth: 0,
        border: 1, borderColor: 'divider'}}>
      <Box component="legend" sx={{px: 0.5, fontWeight: 600}}>{gettext(group.title)}</Box>
      <Box sx={{display: 'grid', gap: 1,
        gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 24rem))'}}>
        {group.fields.map((field) => {
          const single = field.control === 'select' && ['mode', 'method', 'access_mode'].includes(field.field_id);
          const choices = field.control === 'multiselect' || single;
          const wide = choices || field.array_editor || field.object_editor ||
            ['code', 'multiline', 'json'].includes(field.control);
          return <Box key={field.field_id} sx={{minWidth: 0, gridColumn: wide ? '1 / -1' : undefined}}>
            {choices ? <NativeChoices field={field} value={draft[field.field_id]}
              single={single} disabled={disabled} onChange={(value) => onChange(field.field_id, value)} /> : renderField(field)}
            {field.control === 'password' && <TextField fullWidth size="small" sx={{mt: 1}}
              type="password" autoComplete="new-password" disabled={disabled}
              label={gettext('Confirm %s', field.label)} value={confirmations[field.field_id] || ''}
              error={Boolean(confirmations[field.field_id]) && confirmations[field.field_id] !== draft[field.field_id]}
              helperText={draft[field.field_id] && confirmations[field.field_id] !== draft[field.field_id] ?
                gettext('Enter the same password again before previewing.') : ''}
              onChange={(event) => setConfirmations((current) => ({...current,
                [field.field_id]: event.target.value}))} />}
          </Box>;
        })}
      </Box>
    </Box>)}
  </Box>;
}

FirebirdFormLayout.propTypes = {fields: PropTypes.array.isRequired,
  draft: PropTypes.object.isRequired, disabled: PropTypes.bool,
  onChange: PropTypes.func.isRequired, renderField: PropTypes.func.isRequired,
  onValidityChange: PropTypes.func};
