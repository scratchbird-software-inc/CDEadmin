/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// CDEadmin's settings for the tabbed command bar: which bar is shown, the
// user's bar customization, the translated strings, and the mapping from
// CDEadmin's appearance variables (--cde-*) to the bar's (--snb-*).

import gettext from 'sources/gettext';
import {CUSTOMIZATION_SCHEMA} from '../../scratch_notebookbar';

export const COMMAND_BAR_MODE_PREFERENCE = 'accessibility_command_bar';
export const COMMAND_BAR_CUSTOMIZATION_PREFERENCE = Object.freeze({
  module: 'browser', name: 'command_bar_customization'});

export function commandBarMode(miscPreferences={}) {
  return miscPreferences[COMMAND_BAR_MODE_PREFERENCE] === 'notebook' ?
    'notebook' : 'menu';
}

/** The stored customization, or null when unset or unreadable. */
export function readCommandBarCustomization(store) {
  const {module, name} = COMMAND_BAR_CUSTOMIZATION_PREFERENCE;
  const text = store.getPreferences(module, name)?.value;
  if(!text) return null;
  try {
    const document = JSON.parse(text);
    return document?.schema === CUSTOMIZATION_SCHEMA ? document : null;
  } catch {
    return null;
  }
}

export async function saveCommandBarCustomization(store, document) {
  const {module, name} = COMMAND_BAR_CUSTOMIZATION_PREFERENCE;
  const preference = store.getPreferences(module, name);
  if(!preference) {
    throw new Error(gettext('The command bar customization setting is unavailable.'));
  }
  await store.setPreferences([{category_id: preference.cid, id: preference.id,
    mid: preference.mid, name: preference.name,
    value: document ? JSON.stringify(document) : ''}]);
}

// Each string listed literally so translation extraction finds it.
export const COMMAND_BAR_MESSAGES = Object.freeze({
  more: gettext('More'),
  moreCommands: gettext('More commands'),
  quickAccess: gettext('Quick access'),
  options: gettext('{label} options'),
  moreItems: gettext('More {label}'),
  customizer: gettext('Customize the command bar'),
  tabs: gettext('Tabs'),
  groups: gettext('Groups in {tab}'),
  commands: gettext('Commands'),
  quickAccessList: gettext('Quick access commands'),
  show: gettext('Show'),
  moveUp: gettext('Move up'),
  moveDown: gettext('Move down'),
  rename: gettext('Name'),
  addTab: gettext('Add tab'),
  removeTab: gettext('Remove tab'),
  addGroup: gettext('Add group'),
  removeGroup: gettext('Remove group'),
  addToGroup: gettext('Add to group'),
  addToQuickAccess: gettext('Add to quick access'),
  remove: gettext('Remove'),
  search: gettext('Find a command'),
  reset: gettext('Restore the default bar'),
  newTab: gettext('New tab'),
  newGroup: gettext('New group'),
  noCustomGroup: gettext('Choose one of your own groups to add commands to it.'),
  emptyGroup: gettext('No commands yet.'),
});

// The bar follows View > Appearance and Accessibility through these.
export const COMMAND_BAR_THEME = Object.freeze({
  '--snb-font-size': 'var(--cde-menu-font-size, 0.875rem)',
  '--snb-small-font-size': 'calc(var(--cde-menu-font-size, 0.875rem) * 0.86)',
  '--snb-tab-height': 'var(--cde-menu-row-height, 30px)',
  '--snb-control-height': 'max(var(--cde-target-size, 28px), 1.9em)',
  // --cde-icon-scale is the icon scale setting as an em length (1em = 100%).
  '--snb-icon-size': 'calc(1.15 * var(--cde-icon-scale, 1em))',
  '--snb-large-icon-size': 'calc(2.2 * var(--cde-icon-scale, 1em))',
  '--snb-gap': 'var(--cde-target-spacing, 4px)',
  '--snb-radius': 'var(--cde-corner-radius, 0px)',
  '--snb-focus-width': 'var(--cde-focus-width, 2px)',
  '--snb-focus-offset': 'var(--cde-focus-offset, 1px)',
  '--snb-color-background': 'var(--cde-color-navigation, Canvas)',
  '--snb-color-panel': 'var(--cde-color-panel, Canvas)',
  '--snb-color-text': 'var(--cde-color-text, CanvasText)',
  '--snb-color-muted': 'var(--cde-color-text-muted, GrayText)',
  '--snb-color-border': 'var(--cde-color-border, GrayText)',
  '--snb-color-hover': 'var(--cde-color-hover, Highlight)',
  '--snb-color-selected': 'var(--cde-color-primary, Highlight)',
  '--snb-color-selected-text': 'var(--cde-color-primary-text, HighlightText)',
  '--snb-color-accent': 'var(--cde-color-primary, Highlight)',
  '--snb-color-focus': 'var(--cde-color-focus, Highlight)',
  '--snb-color-hint': 'var(--cde-color-text, CanvasText)',
  '--snb-color-hint-text': 'var(--cde-color-panel, Canvas)',
  '--snb-motion': 'var(--cde-motion-fast, 150ms)',
});
