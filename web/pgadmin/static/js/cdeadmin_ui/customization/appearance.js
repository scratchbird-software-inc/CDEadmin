/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// Appearance settings and named presets for View > Appearance and
// accessibility. Values are the misc preferences the presentation authority
// reads; the server validates every value and every preset again.

import gettext from 'sources/gettext';
import {
  PRESENTATION_COLOR_PREFERENCES,
  PRESENTATION_OVERRIDE_RANGES,
} from '../foundations/presentation';
import {normalizeAppearanceCustomizations} from './profile';

export const APPEARANCE_PRESETS_SCHEMA = 'cdeadmin.appearance-presets.v1';
export const APPEARANCE_PRESET_PREFERENCE = 'appearance_presets';
export const MAX_APPEARANCE_PRESETS = 40;
export const MAX_PRESET_NAME_LENGTH = 60;
const LEGACY_PROFILE_SCHEMA = 'cdeadmin.interface-profile.v1';

export const APPEARANCE_CHOICE_KEYS = Object.freeze([
  'accessibility_profile', 'accessibility_density', 'accessibility_motion',
  'theme',
]);
export const APPEARANCE_FONT_KEYS = Object.freeze([
  'accessibility_ui_font_family', 'accessibility_monospace_font_family',
]);
export const APPEARANCE_NUMERIC_KEYS = Object.freeze(
  Object.keys(PRESENTATION_OVERRIDE_RANGES));
export const APPEARANCE_COLOR_KEYS = Object.freeze(
  Object.keys(PRESENTATION_COLOR_PREFERENCES));
export const APPEARANCE_KEYS = Object.freeze([
  ...APPEARANCE_CHOICE_KEYS, ...APPEARANCE_FONT_KEYS,
  ...APPEARANCE_NUMERIC_KEYS, ...APPEARANCE_COLOR_KEYS,
]);

const CHOICE_DEFAULTS = Object.freeze({
  accessibility_profile: 'cdeadmin_standard',
  accessibility_density: 'profile',
  accessibility_motion: 'profile',
  theme: 'system',
});

// Where each numeric setting appears in the resolved presentation, so the
// dialog can show the value a blank field inherits.
export const PRESENTATION_FIELD = Object.freeze({
  accessibility_ui_scale: 'scale',
  accessibility_icon_scale: 'iconScale',
  accessibility_line_height: 'lineHeight',
  accessibility_letter_spacing: 'letterSpacing',
  accessibility_control_height: 'controlHeight',
  accessibility_target_size: 'targetSize',
  accessibility_target_spacing: 'targetSpacing',
  accessibility_scrollbar_size: 'scrollbarSize',
  accessibility_resize_handle_size: 'resizeHandleSize',
  accessibility_panel_gap: 'panelGap',
  accessibility_tree_row_height: 'treeRowHeight',
  accessibility_tree_indent: 'treeIndent',
  accessibility_tree_expander_size: 'treeExpanderSize',
  accessibility_tree_guide_width: 'treeGuideWidth',
  accessibility_grid_row_height: 'gridRowHeight',
  accessibility_grid_header_height: 'gridHeaderHeight',
  accessibility_grid_cell_padding: 'gridCellPadding',
  accessibility_tab_height: 'tabHeight',
  accessibility_toolbar_height: 'toolbarHeight',
  accessibility_menu_row_height: 'menuRowHeight',
  accessibility_menu_font_size: 'menuFontSize',
  accessibility_activity_bar_width: 'activityBarWidth',
  accessibility_activity_icon_size: 'activityIconSize',
  accessibility_status_height: 'statusHeight',
  accessibility_corner_radius: 'cornerRadius',
  accessibility_active_tab_scale: 'activeTabScale',
  accessibility_inactive_brightness: 'inactiveBrightness',
  accessibility_focus_width: 'focusWidth',
  accessibility_focus_offset: 'focusOffset',
});
// Presentation stores these as fractions; the settings are percentages.
export const PERCENT_FIELDS = Object.freeze(new Set([
  'accessibility_active_tab_scale', 'accessibility_inactive_brightness',
]));

export const PROFILE_OPTIONS = Object.freeze([
  ['cdeadmin_standard', gettext('CDEadmin standard')],
  ['classic', gettext('Classic compatibility')],
  ['comfortable', gettext('Comfortable')],
  ['system_adaptive', gettext('System adaptive')],
  ['high_contrast_light', gettext('High contrast light')],
  ['high_contrast_dark', gettext('High contrast dark')],
  ['low_vision', gettext('Low vision')],
  ['motor_assistance', gettext('Motor assistance')],
  ['reduced_motion', gettext('Reduced motion')],
  ['compact_expert', gettext('Compact expert')],
].map(([value, label])=>({value, label})));
export const DENSITY_OPTIONS = Object.freeze([
  ['profile', gettext('Use profile')], ['compact', gettext('Compact')],
  ['standard', gettext('Standard')], ['comfortable', gettext('Comfortable')],
  ['touch', gettext('Touch')],
].map(([value, label])=>({value, label})));
export const MOTION_OPTIONS = Object.freeze([
  ['profile', gettext('Use profile')], ['system', gettext('Follow system')],
  ['reduce', gettext('Reduce motion')], ['full', gettext('Full motion')],
].map(([value, label])=>({value, label})));

const number = (name, label) => ({name, label, kind: 'number'});
const color = (name, label, minimumContrast=0) =>
  ({name, label, kind: 'color', minimumContrast});

// Sections of the dialog. Each setting appears in exactly one section.
export const APPEARANCE_SECTIONS = Object.freeze([
  {id: 'presets', label: gettext('Profile and presets'),
    keywords: gettext('profile preset save load export import accessibility'),
    fields: [{name: 'accessibility_profile', label: gettext('Starting profile'),
      kind: 'select', options: PROFILE_OPTIONS}]},
  {id: 'text', label: gettext('Text and fonts'),
    keywords: gettext('font family size scale line height letter spacing'),
    fields: [
      {name: 'accessibility_ui_font_family', label: gettext('Interface font'),
        kind: 'font'},
      {name: 'accessibility_monospace_font_family',
        label: gettext('Editor and data font'), kind: 'font', monospace: true},
      number('accessibility_ui_scale', gettext('Interface scale (%)')),
      number('accessibility_line_height', gettext('Line height')),
      number('accessibility_letter_spacing', gettext('Letter spacing (em)')),
    ]},
  {id: 'colors', label: gettext('Colours'),
    keywords: gettext('colour color theme dark light contrast'),
    fields: [
      {name: 'theme', label: gettext('Theme'), kind: 'theme'},
      color('accessibility_color_canvas', gettext('Canvas')),
      color('accessibility_color_panel', gettext('Panels')),
      color('accessibility_color_text', gettext('Primary text'), 4.5),
      color('accessibility_color_muted_text', gettext('Secondary text'), 4.5),
      color('accessibility_color_primary', gettext('Primary action')),
      color('accessibility_color_focus', gettext('Keyboard focus'), 3),
      color('accessibility_color_border', gettext('Borders'), 3),
      color('accessibility_color_selection', gettext('Selection')),
      color('accessibility_color_success', gettext('Success')),
      color('accessibility_color_warning', gettext('Warning')),
      color('accessibility_color_error', gettext('Error')),
    ]},
  {id: 'menus', label: gettext('Menu and activity bar'),
    keywords: gettext('menu bar activity icon bar rail width size'),
    fields: [
      number('accessibility_menu_font_size', gettext('Menu text size (pixels)')),
      number('accessibility_menu_row_height', gettext('Menu height (pixels)')),
      number('accessibility_activity_bar_width',
        gettext('Activity bar width (pixels)')),
      number('accessibility_activity_icon_size',
        gettext('Activity bar icon size (pixels)')),
      number('accessibility_active_tab_scale',
        gettext('Selected activity scale (%)')),
      number('accessibility_inactive_brightness',
        gettext('Inactive activity brightness (%)')),
      number('accessibility_icon_scale', gettext('Other icons scale (%)')),
    ]},
  {id: 'areas', label: gettext('Areas and controls'),
    keywords: gettext('toolbar tab status control target spacing panel scrollbar radius'),
    fields: [
      number('accessibility_toolbar_height', gettext('Toolbar height (pixels)')),
      number('accessibility_tab_height', gettext('Workspace tab height (pixels)')),
      number('accessibility_status_height', gettext('Status bar height (pixels)')),
      number('accessibility_control_height', gettext('Control height (pixels)')),
      number('accessibility_target_size', gettext('Click target size (pixels)')),
      number('accessibility_target_spacing', gettext('Target spacing (pixels)')),
      number('accessibility_panel_gap', gettext('Panel spacing (pixels)')),
      number('accessibility_scrollbar_size', gettext('Scrollbar size (pixels)')),
      number('accessibility_resize_handle_size',
        gettext('Resize handle size (pixels)')),
      number('accessibility_corner_radius', gettext('Corner radius (pixels)')),
    ]},
  {id: 'explorer', label: gettext('Explorer and grids'),
    keywords: gettext('tree row indent expander grid header cell padding'),
    fields: [
      number('accessibility_tree_row_height', gettext('Tree row height (pixels)')),
      number('accessibility_tree_indent', gettext('Tree indent (pixels)')),
      number('accessibility_tree_expander_size',
        gettext('Tree expander size (pixels)')),
      number('accessibility_tree_guide_width', gettext('Tree line width (pixels)')),
      number('accessibility_grid_row_height', gettext('Grid row height (pixels)')),
      number('accessibility_grid_header_height',
        gettext('Grid header height (pixels)')),
      number('accessibility_grid_cell_padding',
        gettext('Grid cell padding (pixels)')),
    ]},
  {id: 'motion', label: gettext('Density and motion'),
    keywords: gettext('density motion animation focus indicator'),
    fields: [
      {name: 'accessibility_density', label: gettext('Density'), kind: 'select',
        options: DENSITY_OPTIONS},
      {name: 'accessibility_motion', label: gettext('Motion'), kind: 'select',
        options: MOTION_OPTIONS},
      number('accessibility_focus_width', gettext('Focus indicator width (pixels)')),
      number('accessibility_focus_offset', gettext('Focus indicator offset (pixels)')),
    ]},
]);

/** The appearance values in the misc preferences, with defaults filled in. */
export function readAppearance(miscPreferences={}) {
  return Object.fromEntries(APPEARANCE_KEYS.map((name) => {
    const value = miscPreferences[name];
    if(APPEARANCE_NUMERIC_KEYS.includes(name)) {
      const parsed = Number(value);
      return [name, value === '' || value === null || value === undefined ||
        !Number.isFinite(parsed) ? -1 : parsed];
    }
    if(APPEARANCE_CHOICE_KEYS.includes(name)) {
      return [name, value || CHOICE_DEFAULTS[name]];
    }
    return [name, value ?? ''];
  }));
}

/**
 * The appearance settings a preset holds. A preset sets only the settings it
 * contains (one saved from the dialog contains all of them); using it leaves
 * any other setting as it is.
 */
export function presetValues(values={}) {
  return Object.fromEntries(Object.entries(values)
    .filter(([name]) => APPEARANCE_KEYS.includes(name)));
}

export function emptyPresets() {
  return {schema: APPEARANCE_PRESETS_SCHEMA, presets: []};
}

/** Parse the stored presets document; blank means no presets. */
export function parsePresets(text) {
  if(text === undefined || text === null || String(text).trim() === '') {
    return emptyPresets();
  }
  const document = typeof text === 'string' ? JSON.parse(text) : text;
  if(document?.schema !== APPEARANCE_PRESETS_SCHEMA ||
      !Array.isArray(document.presets)) {
    throw new Error(gettext('Appearance presets have an unknown format.'));
  }
  return {schema: APPEARANCE_PRESETS_SCHEMA, presets: document.presets.map(
    (preset) => {
      if(typeof preset?.name !== 'string' || !preset.name.trim() ||
          typeof preset.values !== 'object' || preset.values === null) {
        throw new Error(gettext('An appearance preset is malformed.'));
      }
      return {name: preset.name.trim(), values: {...preset.values}};
    })};
}

export function serializePresets(document) {
  return JSON.stringify({schema: APPEARANCE_PRESETS_SCHEMA,
    presets: document.presets});
}

const sameName = (left, right) =>
  left.trim().toLocaleLowerCase() === right.trim().toLocaleLowerCase();

/** Add a preset, or replace the one with the same name. */
export function storePreset(document, name, values) {
  const trimmed = String(name ?? '').trim();
  if(!trimmed || trimmed.length > MAX_PRESET_NAME_LENGTH) {
    throw new Error(gettext('A preset name must be 1 to %s characters.',
      MAX_PRESET_NAME_LENGTH));
  }
  const preset = {name: trimmed, values: presetValues(values)};
  const index = document.presets.findIndex((item) => sameName(item.name, trimmed));
  const presets = [...document.presets];
  if(index >= 0) presets[index] = preset;
  else presets.push(preset);
  if(presets.length > MAX_APPEARANCE_PRESETS) {
    throw new Error(gettext('Keep at most %s appearance presets.',
      MAX_APPEARANCE_PRESETS));
  }
  return {...document, presets};
}

export function removePreset(document, name) {
  return {...document, presets: document.presets.filter(
    (item) => !sameName(item.name, name))};
}

/**
 * Merge an imported file into the presets. Accepts a presets document, or an
 * interface profile exported by the former Interface Designer
 * (cdeadmin.interface-profile.v1), whose appearance becomes one preset.
 */
export function importPresets(document, text, fallbackName) {
  let imported;
  try {
    imported = JSON.parse(text);
  } catch {
    throw new Error(gettext('The file is not valid JSON.'));
  }
  let incoming;
  if(imported?.schema === LEGACY_PROFILE_SCHEMA) {
    if(typeof imported.presentation !== 'object' || imported.presentation === null) {
      throw new Error(gettext('The interface profile has no appearance values.'));
    }
    incoming = [{name: fallbackName || gettext('Imported profile'),
      values: normalizeAppearanceCustomizations(imported.presentation)}];
  } else {
    incoming = parsePresets(imported).presets;
  }
  return incoming.reduce((result, preset) =>
    storePreset(result, preset.name, preset.values), document);
}
