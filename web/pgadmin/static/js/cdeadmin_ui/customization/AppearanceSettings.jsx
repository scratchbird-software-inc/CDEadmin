/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// View > Appearance and accessibility: fonts, colours, area sizes and named
// presets. Changes preview live and are saved with Apply; the presentation
// authority bounds and repairs every value, and safe mode (Ctrl+Shift+0)
// still overrides whatever is shown or saved here.

import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import usePreferences from '../../../../preferences/static/js/store';
import {Button} from '../primitives/Button';
import {Select} from '../primitives/Choice';
import {NumberField, TextField} from '../primitives/Field';
import {ListRow} from '../navigation/AdvancedNavigation';
import {ValidationMessage} from '../feedback/Indicators';
import {
  ColorPicker,
  DestructiveConfirmationDialog,
  PreferencesSurface,
  SimpleInputDialog,
} from '../overlays/StandardSurfaces';
import {
  PRESENTATION_COLOR_PREFERENCES,
  PRESENTATION_OVERRIDE_RANGES,
  previewAppearance,
  resolvePresentation,
} from '../foundations/presentation';
import {
  APPEARANCE_KEYS,
  APPEARANCE_PRESET_PREFERENCE,
  APPEARANCE_SECTIONS,
  MAX_PRESET_NAME_LENGTH,
  PERCENT_FIELDS,
  PRESENTATION_FIELD,
  importPresets,
  parsePresets,
  presetValues,
  readAppearance,
  removePreset,
  serializePresets,
  storePreset,
} from './appearance';

const GRID = {display: 'grid', gap: 'var(--cde-panel-gap, 8px) 16px',
  gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
  alignItems: 'start'};
const ROW = {display: 'flex', flexWrap: 'wrap', alignItems: 'center',
  gap: 'var(--cde-target-spacing, 8px)'};

function preferenceRecord(store, name, value) {
  const preference = store.getPreferences('misc', name);
  if(!preference) {
    throw new Error(gettext('The appearance setting %s is unavailable.', name));
  }
  return {category_id: preference.cid, id: preference.id, mid: preference.mid,
    name: preference.name, value};
}

// Enough of a theme for resolvePresentation to pick light or dark colours.
function themeHint(theme) {
  const dark = theme === 'dark' || (theme === 'system' &&
    window.matchMedia?.('(prefers-color-scheme: dark)').matches);
  return {name: dark ? 'dark' : 'light', palette: {mode: dark ? 'dark' : 'light'}};
}

function effectiveText(name, presentation) {
  const value = presentation[PRESENTATION_FIELD[name]];
  if(value === null || value === undefined) {
    return gettext('the interface text size');
  }
  return String(PERCENT_FIELDS.has(name) ? Math.round(value * 100) :
    Math.round(value * 100) / 100);
}

function NumberSetting({field, value, presentation, onChange}) {
  const [minimum, maximum] = PRESENTATION_OVERRIDE_RANGES[field.name];
  const inherited = value === -1;
  const step = Number.isInteger(minimum) && Number.isInteger(maximum) ? 1 : 0.01;
  return <NumberField label={field.label} value={inherited ? '' : value}
    placeholder={inherited ? effectiveText(field.name, presentation) : ''}
    inputProps={{min: minimum, max: maximum, step,
      'data-cdeadmin-qa-key': `appearance.${field.name}`}}
    helperText={inherited ?
      gettext('Profile value %s. Range %s to %s.',
        effectiveText(field.name, presentation), minimum, maximum) :
      gettext('Range %s to %s. Clear to use the profile value.',
        minimum, maximum)}
    onChange={(event) => {
      const raw = event.target.value;
      onChange(raw === '' ? -1 : Number(raw));
    }} />;
}

NumberSetting.propTypes = {
  field: PropTypes.object.isRequired, value: PropTypes.number,
  presentation: PropTypes.object.isRequired, onChange: PropTypes.func.isRequired,
};

function ColorSetting({field, value, presentation, onChoose, onChange}) {
  const shown = value ||
    presentation.colors?.[PRESENTATION_COLOR_PREFERENCES[field.name]] || '';
  return <div style={{...ROW, flexWrap: 'nowrap'}}>
    <span aria-hidden="true" style={{flex: '0 0 auto', width: 24, height: 24,
      background: shown || 'transparent',
      border: '1px solid var(--cde-color-border, currentColor)'}} />
    <TextField label={field.label} value={value} placeholder={shown || '#RRGGBB'}
      helperText={value ? gettext('Clear to use the profile colour.') :
        gettext('Profile colour %s.', shown || gettext('from the theme'))}
      onChange={(event) => onChange(event.target.value.trim())} />
    <Button onClick={() => onChoose(field, shown)}
      aria-label={gettext('Choose %s colour', field.label)}>
      {gettext('Choose…')}
    </Button>
  </div>;
}

ColorSetting.propTypes = {
  field: PropTypes.object.isRequired, value: PropTypes.string,
  presentation: PropTypes.object.isRequired, onChoose: PropTypes.func.isRequired,
  onChange: PropTypes.func.isRequired,
};

function FontSetting({field, value, onChange}) {
  return <div style={{display: 'grid', gap: 4}}>
    <TextField label={field.label} value={value}
      placeholder={field.monospace ? 'ui-monospace, monospace' :
        '"Atkinson Hyperlegible", sans-serif'}
      helperText={gettext('Comma-separated font names; blank uses the profile font.')}
      onChange={(event) => onChange(event.target.value)} />
    <div aria-label={gettext('%s preview', field.label)}
      style={{fontFamily: value || (field.monospace ? 'var(--cde-font-mono, monospace)' :
        'inherit'), padding: 4, border: '1px solid var(--cde-color-border, currentColor)'}}>
      {field.monospace ? 'SELECT id, name FROM table_1; -- 0O 1lI' :
        gettext('The quick brown fox jumps over the lazy dog. 0123456789')}
    </div>
  </div>;
}

FontSetting.propTypes = {
  field: PropTypes.object.isRequired, value: PropTypes.string,
  onChange: PropTypes.func.isRequired,
};

function PresetsPanel({presets, values, update, onSaveAs, onReplace, onDelete,
  onExport, onImport, busy}) {
  const [selected, setSelected] = useState('');
  const current = presets.presets.find((item) => item.name === selected);
  useEffect(() => {
    if(selected && !current) setSelected('');
  }, [selected, current]);
  return <section aria-labelledby="appearance-presets-heading"
    style={{display: 'grid', gap: 12}}>
    <h3 id="appearance-presets-heading" style={{margin: 0}}>
      {gettext('Your presets')}
    </h3>
    <p style={{margin: 0}}>{gettext(
      'Saving a preset stores every setting in this dialog under a name. Using a preset changes only the settings it holds and shows the result here; Apply makes it your appearance.'
    )}</p>
    <div role="listbox" aria-label={gettext('Saved presets')}
      style={{border: '1px solid var(--cde-color-border, currentColor)',
        maxHeight: 220, overflow: 'auto'}}>
      {presets.presets.length === 0 && <div style={{padding: 8}}>
        {gettext('No presets saved yet.')}</div>}
      {presets.presets.map((preset) => <ListRow key={preset.name}
        label={preset.name} selected={preset.name === selected}
        onSelect={() => setSelected(preset.name)}
        onOpen={() => update(presetValues(preset.values))} />)}
    </div>
    <div style={ROW}>
      <Button intent="primary" disabled={!current}
        onClick={() => update(presetValues(current.values))}>
        {gettext('Use preset')}
      </Button>
      <Button disabled={busy} onClick={() => onSaveAs(values)}>
        {gettext('Save current settings as…')}
      </Button>
      <Button disabled={!current || busy} onClick={() => onReplace(current.name, values)}>
        {gettext('Replace with current settings')}
      </Button>
      <Button intent="destructive" disabled={!current || busy}
        onClick={() => onDelete(current.name)}>
        {gettext('Delete…')}
      </Button>
    </div>
    <div style={ROW}>
      <Button disabled={presets.presets.length === 0} onClick={onExport}>
        {gettext('Export presets…')}
      </Button>
      <Button component="label" disabled={busy}>
        {gettext('Import presets…')}
        <input type="file" hidden accept="application/json,.json"
          data-cdeadmin-qa-key="appearance.import" onChange={onImport} />
      </Button>
    </div>
  </section>;
}

PresetsPanel.propTypes = {
  presets: PropTypes.object.isRequired, values: PropTypes.object.isRequired,
  update: PropTypes.func.isRequired, onSaveAs: PropTypes.func.isRequired,
  onReplace: PropTypes.func.isRequired, onDelete: PropTypes.func.isRequired,
  onExport: PropTypes.func.isRequired, onImport: PropTypes.func.isRequired,
  busy: PropTypes.bool,
};

export default function AppearanceSettings({onClose}) {
  const store = usePreferences();
  const version = store.version;
  const saved = useMemo(() => readAppearance(
    usePreferences.getState().getPreferencesForModule('misc')), [version]);
  const themeOptions = useMemo(() => (usePreferences.getState()
    .getPreferences('misc', 'theme')?.options ?? []).map((option) => ({
    value: option.value, label: option.label})), [version]);
  const [presets, presetsError] = useMemo(() => {
    try {
      return [parsePresets(usePreferences.getState()
        .getPreferencesForModule('misc')[APPEARANCE_PRESET_PREFERENCE]), ''];
    } catch(error) {
      return [parsePresets(''), error.message];
    }
  }, [version]);
  const [message, setMessage] = useState({status: 'info', text: ''});
  const [busy, setBusy] = useState(false);
  const [naming, setNaming] = useState(null);
  const [deleting, setDeleting] = useState('');
  const [picking, setPicking] = useState(null);
  const updateRef = useRef(null);

  useEffect(() => () => previewAppearance(null), []);
  useEffect(() => {
    if(presetsError) setMessage({status: 'error', text: presetsError});
  }, [presetsError]);

  const persist = async (records, success) => {
    setBusy(true);
    try {
      await usePreferences.getState().setPreferences(records);
      setMessage({status: 'success', text: success});
      return true;
    } catch(error) {
      setMessage({status: 'error', text: error?.response?.data?.errormsg ||
        error.message});
      return false;
    } finally {
      setBusy(false);
    }
  };
  const persistPresets = (document, success) => {
    try {
      return persist([preferenceRecord(usePreferences.getState(),
        APPEARANCE_PRESET_PREFERENCE, serializePresets(document))], success);
    } catch(error) {
      setMessage({status: 'error', text: error.message});
      return Promise.resolve(false);
    }
  };
  const apply = async (draft) => {
    const changed = APPEARANCE_KEYS.filter((name) => draft[name] !== saved[name]);
    if(changed.length === 0) return;
    try {
      const records = changed.map((name) => preferenceRecord(
        usePreferences.getState(), name, draft[name]));
      if(await persist(records, gettext('Appearance saved.'))) {
        previewAppearance(null);
      }
    } catch(error) {
      setMessage({status: 'error', text: error.message});
    }
  };
  const savePreset = async (name, values) => {
    try {
      await persistPresets(storePreset(presets, name, values),
        gettext('Preset “%s” saved.', name.trim()));
    } catch(error) {
      setMessage({status: 'error', text: error.message});
    }
  };
  const exportPresets = () => {
    const data = JSON.stringify({schema: presets.schema, presets: presets.presets},
      null, 2);
    const url = URL.createObjectURL(new Blob([data], {type: 'application/json'}));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'cdeadmin-appearance-presets.json';
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const importFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if(!file) return;
    try {
      const merged = importPresets(presets, await file.text(),
        file.name.replace(/\.json$/i, '').slice(0, MAX_PRESET_NAME_LENGTH));
      await persistPresets(merged, gettext('Presets imported from %s.', file.name));
    } catch(error) {
      setMessage({status: 'error', text: error.message});
    }
  };

  const sections = APPEARANCE_SECTIONS.map((section) => ({
    ...section,
    render: ({values, update}) => {
      updateRef.current = update;
      const presentation = resolvePresentation(values, themeHint(values.theme));
      const set = (name) => (value) => update({[name]: value});
      return <section aria-labelledby={`appearance-${section.id}-heading`}
        style={{display: 'grid', gap: 16}}>
        <h2 id={`appearance-${section.id}-heading`} style={{margin: 0}}>
          {section.label}
        </h2>
        <div style={GRID}>
          {section.fields.map((field) => {
            if(field.kind === 'number') {
              return <NumberSetting key={field.name} field={field}
                value={values[field.name]} presentation={presentation}
                onChange={set(field.name)} />;
            }
            if(field.kind === 'color') {
              return <ColorSetting key={field.name} field={field}
                value={values[field.name]} presentation={presentation}
                onChange={set(field.name)}
                onChoose={(chosen, shown) => setPicking({field: chosen, shown,
                  background: presentation.colors?.canvas})} />;
            }
            if(field.kind === 'font') {
              return <FontSetting key={field.name} field={field}
                value={values[field.name]} onChange={set(field.name)} />;
            }
            return <Select key={field.name} label={field.label}
              value={values[field.name]}
              options={field.kind === 'theme' ? themeOptions : field.options}
              onChange={set(field.name)} />;
          })}
        </div>
        {section.id === 'presets' && <PresetsPanel presets={presets}
          values={values} update={update} busy={busy}
          onSaveAs={(current) => setNaming({values: current})}
          onReplace={(name, current) => savePreset(name, current)}
          onDelete={setDeleting} onExport={exportPresets} onImport={importFile} />}
      </section>;
    },
  }));

  return <div data-cdeadmin-qa-key="appearance-settings.dialog"
    style={{height: '100%', minHeight: 0, display: 'grid',
      gridTemplateRows: 'auto minmax(0, 1fr)'}}>
    <div style={{...ROW, padding: '4px 8px', minHeight: 28}}>
      <div style={{flex: 1}}>
        {message.text && <ValidationMessage status={message.status}>
          {message.text}</ValidationMessage>}
      </div>
      {onClose && <Button onClick={onClose}>{gettext('Close')}</Button>}
    </div>
    <PreferencesSurface sections={sections} values={saved}
      onPreview={(next) => previewAppearance(next)}
      onApply={apply}
      onReset={() => { previewAppearance(null); setMessage({status: 'info', text: ''}); }} />
    <SimpleInputDialog open={Boolean(naming)} title={gettext('Save preset')}
      label={gettext('Preset name')} value=""
      validation={(name) => !name.trim() ? gettext('Enter a name.') :
        name.trim().length > MAX_PRESET_NAME_LENGTH ?
          gettext('Use at most %s characters.', MAX_PRESET_NAME_LENGTH) : ''}
      busy={busy}
      onCancel={() => setNaming(null)}
      onApply={async (name) => {
        await savePreset(name, naming.values);
        setNaming(null);
      }} />
    <DestructiveConfirmationDialog open={Boolean(deleting)} verb={gettext('Delete')}
      targetIdentity={deleting || ' '}
      consequence={gettext('The preset is removed from your account. Your current appearance does not change.')}
      reversibility={gettext('Export your presets first if you may want it back.')}
      busy={busy} onCancel={() => setDeleting('')}
      onConfirm={async () => {
        const name = deleting;
        await persistPresets(removePreset(presets, name),
          gettext('Preset “%s” deleted.', name));
        setDeleting('');
      }} />
    <ColorPicker open={Boolean(picking)} value={picking?.shown || '#000000'}
      background={picking?.background || '#FFFFFF'}
      minimumContrast={picking?.field.minimumContrast ?? 0}
      onClose={() => setPicking(null)}
      onConfirm={(value) => {
        updateRef.current?.({[picking.field.name]: value});
        setPicking(null);
      }} />
  </div>;
}

AppearanceSettings.propTypes = {onClose: PropTypes.func};
