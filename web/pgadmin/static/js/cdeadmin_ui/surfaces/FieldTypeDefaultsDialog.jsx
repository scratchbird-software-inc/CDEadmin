import {useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Button} from '../primitives/Button';
import {Dialog} from '../overlays/Dialog';

export default function FieldTypeDefaultsDialog({types, defaults, onClose, onSave, fieldName}) {
  const [type, setType] = useState(types[0]);
  const [draft, setDraft] = useState(defaults);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const update = (property, value) => {
    setDraft((current) => ({...current, [type]: {...current[type], [property]: value}}));
  };
  const save = async () => {
    setSaving(true);
    try {
      await onSave(draft);
      onClose();
    } catch (failure) {
      setError(failure?.message || String(failure));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Dialog open title={fieldName ? gettext('Format Field: %s', fieldName) : gettext('Field Type Defaults')} onClose={onClose} size="small"
      actions={<>
        <Button onClick={onClose}>{gettext('Cancel')}</Button>
        <Button intent="primary" disabled={saving} onClick={save}>{gettext('Save')}</Button>
      </>}>
      <div style={{display: 'grid', gap: 10}}>
        {!fieldName && <label>{gettext('Field type')}{' '}
          <select className="sr-input" value={type} onChange={(event) => setType(event.target.value)}>
            {types.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>}
        <label>{gettext('Font')}{' '}
          <select className="sr-input" value={draft[type]?.font || ''} onChange={(event) => update('font', event.target.value)}>
            <option value="">{gettext(fieldName ? 'Field type default' : 'Application default')}</option>
            <option value="mono">{gettext('Monospace')}</option>
            <option value="sans">{gettext('Sans serif')}</option>
            <option value="serif">{gettext('Serif')}</option>
          </select>
        </label>
        <label>{gettext('Alignment')}{' '}
          <select className="sr-input" value={draft[type]?.hAlign || ''} onChange={(event) => update('hAlign', event.target.value)}>
            <option value="">{gettext(fieldName ? 'Field type default' : 'Application default')}</option>
            <option value="left">{gettext('Left')}</option>
            <option value="center">{gettext('Center')}</option>
            <option value="right">{gettext('Right')}</option>
          </select>
        </label>
        {error && <p role="alert">{error}</p>}
      </div>
    </Dialog>
  );
}

FieldTypeDefaultsDialog.propTypes = {
  types: PropTypes.arrayOf(PropTypes.string).isRequired,
  defaults: PropTypes.object.isRequired,
  fieldName: PropTypes.string,
  onClose: PropTypes.func.isRequired,
  onSave: PropTypes.func.isRequired,
};
