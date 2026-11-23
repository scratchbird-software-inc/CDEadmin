import {useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../cdeadmin_ui/primitives/Layout';
import {Button} from '../cdeadmin_ui/primitives/Button';
import {TextField} from '../cdeadmin_ui/primitives/Field';
import {Select} from '../cdeadmin_ui/primitives/Choice';
import {Banner} from '../cdeadmin_ui/feedback/Indicators';
import {Dialog} from '../cdeadmin_ui/overlays/Dialog';

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
  const initial = {text: '', binary: '', boolean: false, date: '2000-01-01', time: '00:00:00', timestamp: '2000-01-01 00:00:00', 'firebird-time-tz': {encoding: 'firebird-time-tz', utc: '00:00:00', time_zone: '+00:00'}, 'firebird-timestamp-tz': {encoding: 'firebird-timestamp-tz', utc: '2000-01-01 00:00:00', time_zone: '+00:00'}}[spec.element_kind] ?? '0';
  return Array.from({length: lengths[depth]}, () => depth === lengths.length - 1 ? initial : newArray(spec, depth + 1));
}

export default function ProviderArrayInput({draft, spec, label, disabled, onChange}) {
  const [expanded, setExpanded] = useState(false);
  const [page, setPage] = useState(0);
  const [error, setError] = useState(null);
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
  const titleText = `${label} [${spec.bounds.map((bound) => bound.join(':')).join(', ')}]`;
  return <Box style={{minWidth: 260}}>
    <Button aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
      {titleText}
    </Button>
    <Dialog
      open={expanded}
      onClose={() => setExpanded(false)}
      size="large"
      title={titleText}
      actions={<Button onClick={() => setExpanded(false)}>{gettext('Close array editor')}</Button>}
    >
      <Stack spacing={1}>
        <div>{gettext('Element type')}: {spec.element_kind}{spec.precision ? `(${spec.precision})` : ''}; {gettext('Scale')}: {spec.scale}</div>
        {spec.length && <div>{gettext('Declared length')}: {spec.length} {spec.element_kind === 'binary' ? gettext('bytes') : gettext('characters')}; {gettext('Character set')}: {spec.charset}</div>}
        {spec.element_kind?.startsWith('firebird-') && <div>{gettext('Each element is a JSON object with encoding, utc and time_zone fields. UTC preserves distinct DST instants.')}</div>}
        {spec.element_kind === 'binary' && <div>{gettext('Enter each element as canonical Base64. Fixed-width values are zero-padded by the engine.')}</div>}
        <div>{gettext('Changes remain in the row draft. Save the row, then explicitly commit or roll back the data session.')}</div>
        <Select
          aria-label={`${label} mode`}
          value={draft.isNull ? 'null' : 'value'}
          disabled={disabled}
          options={[
            {value: 'value', label: gettext('Value')},
            {value: 'null', label: 'NULL'},
          ]}
          onChange={(nextValue) => onChange({...draft, isNull: nextValue === 'null'})}
        />
        {!value && <Button disabled={disabled} onClick={initialize}>{gettext('Initialize array')}</Button>}
        {error && <Banner tone="error">{error}</Banner>}
        {value && <>
          {Array.from({length: Math.min(25, count - currentPage * 25)}, (_, offset) => {
            const index = currentPage * 25 + offset;
            const coordinates = arrayCoordinates(index, spec);
            const element = coordinates.reduce((items, coordinate, dimension) =>
              items[coordinate - spec.bounds[dimension][0]], value);
            const name = `${label} [${coordinates.join(', ')}]`;
            const displayValue = spec.element_kind?.startsWith('firebird-') && typeof element === 'object' ?
              JSON.stringify(element) :
              spec.element_kind === 'binary' && element?.encoding === 'base64' ?
                element.data :
                String(element);
            if (spec.element_kind === 'boolean') {
              return (
                <Select
                  key={index}
                  aria-label={name}
                  helperText={name}
                  value={displayValue}
                  disabled={disabled || draft.isNull}
                  options={[
                    {value: 'true', label: gettext('True')},
                    {value: 'false', label: gettext('False')},
                  ]}
                  onChange={(nextValue) => change(index, nextValue === 'true')}
                />
              );
            }
            return (
              <TextField
                key={index}
                helperText={name}
                multiline={spec.element_kind === 'text' || spec.element_kind?.startsWith('firebird-')}
                value={displayValue}
                disabled={disabled || draft.isNull}
                inputProps={{'aria-label': name}}
                onChange={(event) => change(index, event.target.value)}
              />
            );
          })}
          <Box style={{display: 'flex', alignItems: 'center', gap: 8}}>
            <Button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>{gettext('Previous elements')}</Button>
            <span>{currentPage + 1} / {lastPage + 1}</span>
            <Button disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>{gettext('Next elements')}</Button>
          </Box>
        </>}
      </Stack>
    </Dialog>
  </Box>;
}

ProviderArrayInput.propTypes = {
  draft: PropTypes.shape({text: PropTypes.string, isNull: PropTypes.bool}).isRequired,
  spec: PropTypes.shape({bounds: PropTypes.array.isRequired, element_kind: PropTypes.string.isRequired, scale: PropTypes.number, precision: PropTypes.number, length: PropTypes.number, charset: PropTypes.string}).isRequired,
  label: PropTypes.string.isRequired, disabled: PropTypes.bool, onChange: PropTypes.func.isRequired,
};
