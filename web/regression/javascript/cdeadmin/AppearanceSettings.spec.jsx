/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// Preferences > Appearance and accessibility (2026-11-05; first a dialog,
// then part of Preferences the same day): fonts, colours, area sizes and named
// presets, previewed live across sections and saved as misc preferences.

import {useState} from 'react';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import usePreferences from '../../../pgadmin/preferences/static/js/store';
import {AppearanceSectionEditor} from
  'sources/cdeadmin_ui/customization/AppearancePreferences';
import {InterfacePreferencesProvider} from
  'sources/cdeadmin_ui/customization/interfaceDrafts';
import {
  APPEARANCE_KEYS,
  APPEARANCE_PRESETS_SCHEMA,
  APPEARANCE_SECTIONS,
  importPresets,
  parsePresets,
  readAppearance,
  removePreset,
  storePreset,
} from 'sources/cdeadmin_ui/customization/appearance';
import {APPEARANCE_PREVIEW_EVENT} from
  'sources/cdeadmin_ui/foundations/presentation';

function preferenceData(presets='') {
  const values = {...readAppearance({}), theme: 'light',
    appearance_presets: presets};
  return Object.entries(values).map(([name, value], index) => ({
    id: index + 1, cid: 1, mid: 1, module: 'misc', name, value,
    ...(name === 'theme' ? {options: [{label: 'Light', value: 'light'},
      {label: 'Dark', value: 'dark'}, {label: 'System', value: 'system'}]} : {}),
  }));
}

function setStore(presets) {
  usePreferences.setState({data: preferenceData(presets), version: 1,
    isLoading: false, failed: false, setPreferences: jest.fn(async () => ({}))});
}

function previews() {
  const seen = [];
  const listener = (event) => seen.push(event.detail.values);
  window.addEventListener(APPEARANCE_PREVIEW_EVENT, listener);
  return {seen, stop: () => window.removeEventListener(
    APPEARANCE_PREVIEW_EVENT, listener)};
}

const written = () => usePreferences.getState().setPreferences.mock.calls
  .flatMap(([records]) => records);

describe('appearance settings helpers', () => {
  it('places every appearance setting in exactly one section', () => {
    const placed = APPEARANCE_SECTIONS.flatMap((section) =>
      section.fields.map((field) => field.name));
    expect([...placed].sort()).toEqual([...APPEARANCE_KEYS].sort());
    expect(new Set(placed).size).toBe(placed.length);
  });

  it('fills unset settings with inherit and profile defaults', () => {
    const values = readAppearance({accessibility_ui_scale: '150'});
    expect(values.accessibility_ui_scale).toBe(150);
    expect(values.accessibility_menu_font_size).toBe(-1);
    expect(values.accessibility_profile).toBe('cdeadmin_standard');
    expect(values.theme).toBe('system');
    expect(values.accessibility_color_text).toBe('');
  });

  it('adds, replaces by name and removes presets', () => {
    let document = parsePresets('');
    document = storePreset(document, ' Large text ', {accessibility_ui_scale: 175,
      not_appearance: 1});
    document = storePreset(document, 'LARGE TEXT', {accessibility_ui_scale: 200});
    expect(document.presets).toHaveLength(1);
    expect(document.presets[0].name).toBe('LARGE TEXT');
    expect(document.presets[0].values.accessibility_ui_scale).toBe(200);
    expect(document.presets[0].values).not.toHaveProperty('not_appearance');
    // A preset holds only what it was given; using it leaves the rest alone.
    expect(Object.keys(document.presets[0].values)).toEqual(['accessibility_ui_scale']);
    expect(removePreset(document, 'large text').presets).toEqual([]);
    expect(() => storePreset(document, ' ', {})).toThrow('preset name');
    let full = parsePresets('');
    for (let index = 0; index < 40; index++) {
      full = storePreset(full, `P${index}`, {});
    }
    expect(() => storePreset(full, 'One more', {})).toThrow('at most 40');
  });

  it('imports presets files and former Interface Designer profiles', () => {
    const presets = JSON.stringify({schema: APPEARANCE_PRESETS_SCHEMA,
      presets: [{name: 'Night', values: {theme: 'dark'}}]});
    expect(importPresets(parsePresets(''), presets).presets[0].name).toBe('Night');

    const legacy = JSON.stringify({schema: 'cdeadmin.interface-profile.v1',
      presentation: {accessibility_ui_scale: 160, accessibility_color_text: 'red',
        accessibility_profile: 'low_vision'}});
    const [preset] = importPresets(parsePresets(''), legacy, 'team').presets;
    expect(preset.name).toBe('team');
    expect(preset.values.accessibility_ui_scale).toBe(160);
    expect(preset.values.accessibility_profile).toBe('low_vision');
    // The invalid colour is dropped, so using the preset leaves it unchanged.
    expect(preset.values).not.toHaveProperty('accessibility_color_text');
    expect(() => importPresets(parsePresets(''), '{')).toThrow('not valid JSON');
    expect(() => importPresets(parsePresets(''), '{"schema":"x"}'))
      .toThrow('unknown format');
  });
});

// Preferences shows one section at a time inside one drafts provider.
function Sections({initial='presets'}) {
  const [section, setSection] = useState(initial);
  return <InterfacePreferencesProvider>
    <button type="button" onClick={() => setSection('text')}>Show text</button>
    <button type="button" onClick={() => setSection('menus')}>Show menus</button>
    <AppearanceSectionEditor sectionId={section} />
  </InterfacePreferencesProvider>;
}

function renderSections(initial) {
  const Component = withTheme(Sections);
  return render(<Component initial={initial} />);
}

describe('Preferences > Appearance and accessibility', () => {
  beforeEach(() => setStore(''));

  it('previews a change and saves only the changed setting', async () => {
    const watch = previews();
    renderSections('text');
    fireEvent.change(screen.getByLabelText('Interface scale (%)'),
      {target: {value: '150'}});
    expect(watch.seen.at(-1).accessibility_ui_scale).toBe(150);

    fireEvent.click(screen.getByRole('button', {name: 'Apply'}));
    await waitFor(() => expect(screen.getByRole('status'))
      .toHaveTextContent('Appearance saved.'));
    expect(written()).toEqual([expect.objectContaining({
      name: 'accessibility_ui_scale', value: 150})]);
    expect(watch.seen.at(-1)).toBeNull();
    watch.stop();
  });

  it('keeps unsaved changes while moving between sections', async () => {
    renderSections('text');
    fireEvent.change(screen.getByLabelText('Interface scale (%)'),
      {target: {value: '160'}});
    fireEvent.click(screen.getByRole('button', {name: 'Show menus'}));
    fireEvent.change(screen.getByLabelText('Menu text size (pixels)'),
      {target: {value: '18'}});
    fireEvent.click(screen.getByRole('button', {name: 'Show text'}));
    expect(screen.getByLabelText('Interface scale (%)')).toHaveValue(160);
    fireEvent.click(screen.getByRole('button', {name: 'Apply'}));
    await waitFor(() => expect(written()).toHaveLength(2));
    expect(written()).toEqual(expect.arrayContaining([
      expect.objectContaining({name: 'accessibility_ui_scale', value: 160}),
      expect.objectContaining({name: 'accessibility_menu_font_size', value: 18}),
    ]));
  });

  it('sizes the menu and activity bar from its own section', () => {
    renderSections('menus');
    expect(screen.getByLabelText('Menu text size (pixels)')).toBeInTheDocument();
    expect(screen.getByLabelText('Activity bar width (pixels)')).toBeInTheDocument();
    expect(screen.getByLabelText('Activity bar icon size (pixels)'))
      .toBeInTheDocument();
  });

  it('saves the current settings as a named preset', async () => {
    renderSections('presets');
    fireEvent.click(screen.getByRole('button', {name: 'Save current settings as…'}));
    fireEvent.change(screen.getByLabelText('Preset name'), {target: {value: 'Mine'}});
    fireEvent.click(screen.getAllByRole('button', {name: 'Apply'}).at(-1));
    await waitFor(() => expect(written()).toHaveLength(1));
    const [record] = written();
    expect(record.name).toBe('appearance_presets');
    const stored = JSON.parse(record.value);
    expect(stored.schema).toBe(APPEARANCE_PRESETS_SCHEMA);
    expect(stored.presets[0].name).toBe('Mine');
    expect(Object.keys(stored.presets[0].values).sort())
      .toEqual([...APPEARANCE_KEYS].sort());
  });

  it('uses a saved preset as the unsaved draft', async () => {
    setStore(JSON.stringify({schema: APPEARANCE_PRESETS_SCHEMA, presets: [
      {name: 'Large', values: {accessibility_ui_scale: 175}}]}));
    const watch = previews();
    renderSections('presets');
    fireEvent.click(screen.getByText('Large'));
    fireEvent.click(screen.getByRole('button', {name: 'Use preset'}));
    expect(watch.seen.at(-1).accessibility_ui_scale).toBe(175);
    expect(usePreferences.getState().setPreferences).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Apply'}));
    await waitFor(() => expect(written()).toEqual([expect.objectContaining({
      name: 'accessibility_ui_scale', value: 175})]));
    watch.stop();
  });

  it('ends the preview when Preferences closes', () => {
    const watch = previews();
    const {unmount} = renderSections('text');
    fireEvent.change(screen.getByLabelText('Interface scale (%)'),
      {target: {value: '150'}});
    unmount();
    expect(watch.seen.at(-1)).toBeNull();
    watch.stop();
  });
});
