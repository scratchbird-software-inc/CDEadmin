import {useId, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, TextField, Typography} from '@mui/material';
import gettext from 'sources/gettext';

export function arrayShape(spec) {
  if (!spec?.bounds?.length || spec.bounds.length > 16) throw new Error(gettext('Array bounds unavailable.'));
  const lengths = spec.bounds.map(([lower, upper]) => {
    if (!Number.isInteger(lower) || !Number.isInteger(upper) || upper < lower) throw new Error(gettext('Invalid array bounds.'));
    return upper - lower + 1;
  });
  return lengths;
}

export function arrayCoordinates(index, spec) {
  const lengths = arrayShape(spec);
  return lengths.map((_, dimension) => {
    const stride = lengths.slice(dimension + 1).reduce((a, b) => a * b, 1);
    return Math.floor(index / stride) % lengths[dimension] + spec.bounds[dimension][0];
  });
}

export function newArray(spec, depth = 0) {
  const lengths = arrayShape(spec);
  // Explicit UI allocation guard, not a native engine limit.
  if (lengths.reduce((a, b) => a * b, 1) > 100000) throw new Error(gettext('Initializing more than 100,000 array elements is not available in this editor.'));
  return Array.from({length: lengths[depth]}, () => depth === lengths.length - 1 ?
    (spec.element_kind === 'boolean' ? false : '0') : newArray(spec, depth + 1));
}

export default function ProviderArrayInput({draft, spec, label, disabled, onChange}) {
  const [expanded, setExpanded] = useState(false);
  const [page, setPage] = useState(0);
  const [error, setError] = useState(null);
  const titleId = useId();
  let value;
  try { value = draft.text ? JSON.parse(draft.text) : null; } catch { value = null; }
  const lengths = arrayShape(spec);
  const count = lengths.reduce((a, b) => a * b, 1);
  const lastPage = Math.max(0, Math.ceil(count / 25) - 1);
  const currentPage = Math.min(page, lastPage);
  const change = (index, text) => {
    const copy = JSON.parse(draft.text);
    const coordinates = arrayCoordinates(index, spec);
    let parent = copy;
    coordinates.forEach((coordinate, dimension) => {
      const offset = coordinate - spec.bounds[dimension][0];
      if (dimension === coordinates.length - 1) parent[offset] = text;
      else parent = parent[offset];
    });
    onChange({...draft, text: JSON.stringify(copy)});
  };
  const initialize = () => {
    try {
      onChange({text: JSON.stringify(newArray(spec)), isNull: false});
      setError(null);
    } catch (failure) { setError(failure.message); }
  };
  return <Box sx={{minWidth: 260}}>
    <Button aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
      {label} [{spec.bounds.map((bound) => bound.join(':')).join(', ')}]
    </Button>
    <Dialog open={expanded} onClose={() => setExpanded(false)} fullWidth maxWidth="md" aria-labelledby={titleId}>
      <DialogTitle id={titleId}>{label} [{spec.bounds.map((bound) => bound.join(':')).join(', ')}]</DialogTitle>
      <DialogContent>
        <Typography>{gettext('Element type')}: {spec.element_kind}{spec.precision ? `(${spec.precision})` : ''}; {gettext('Scale')}: {spec.scale}</Typography>
        <Typography>{gettext('Changes remain in the row draft. Save the row, then explicitly commit or roll back the data session.')}</Typography>
        <TextField select size="small" value={draft.isNull ? 'null' : 'value'} disabled={disabled}
          SelectProps={{inputProps: {'aria-label': `${label} mode`}}}
          onChange={(event) => onChange({...draft, isNull: event.target.value === 'null'})}>
          <MenuItem value="value">{gettext('Value')}</MenuItem><MenuItem value="null">NULL</MenuItem>
        </TextField>
        {!value && <Button disabled={disabled} onClick={initialize}>{gettext('Initialize array')}</Button>}
        {error && <Alert severity="error">{error}</Alert>}
        {value && <>
          {Array.from({length: Math.min(25, count - currentPage * 25)}, (_, offset) => {
            const index = currentPage * 25 + offset;
            const coordinates = arrayCoordinates(index, spec);
            const element = coordinates.reduce((items, coordinate, dimension) =>
              items[coordinate - spec.bounds[dimension][0]], value);
            const name = `${label} [${coordinates.join(', ')}]`;
            return <TextField key={index} size="small" fullWidth helperText={name}
              select={spec.element_kind === 'boolean'} value={String(element)}
              disabled={disabled || draft.isNull}
              inputProps={{'aria-label': name}}
              SelectProps={{inputProps: {'aria-label': name}}}
              onChange={(event) => change(index, spec.element_kind === 'boolean' ?
                event.target.value === 'true' : event.target.value)}>
              {spec.element_kind === 'boolean' && [
                <MenuItem key="true" value="true">{gettext('True')}</MenuItem>,
                <MenuItem key="false" value="false">{gettext('False')}</MenuItem>,
              ]}
            </TextField>;
          })}
          <Button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>{gettext('Previous elements')}</Button>
          <Typography component="span">{currentPage + 1} / {lastPage + 1}</Typography>
          <Button disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>{gettext('Next elements')}</Button>
        </>}
      </DialogContent>
      <DialogActions><Button onClick={() => setExpanded(false)}>{gettext('Close array editor')}</Button></DialogActions>
    </Dialog>
  </Box>;
}

ProviderArrayInput.propTypes = {
  draft: PropTypes.shape({text: PropTypes.string, isNull: PropTypes.bool}).isRequired,
  spec: PropTypes.shape({bounds: PropTypes.array.isRequired, element_kind: PropTypes.string.isRequired, scale: PropTypes.number, precision: PropTypes.number}).isRequired,
  label: PropTypes.string.isRequired, disabled: PropTypes.bool, onChange: PropTypes.func.isRequired,
};
