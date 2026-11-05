/////////////////////////////////////////////////////////////
//
// Scratch notebook bar
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// Every string the bar and its customizer show. A host passes `messages`
// with translations; anything missing falls back to English.

export const DEFAULT_MESSAGES = Object.freeze({
  more: 'More',
  moreCommands: 'More commands',
  quickAccess: 'Quick access',
  options: '{label} options',
  moreItems: 'More {label}',
  customizer: 'Customize the command bar',
  tabs: 'Tabs',
  groups: 'Groups in {tab}',
  commands: 'Commands',
  quickAccessList: 'Quick access commands',
  show: 'Show',
  moveUp: 'Move up',
  moveDown: 'Move down',
  rename: 'Name',
  addTab: 'Add tab',
  removeTab: 'Remove tab',
  addGroup: 'Add group',
  removeGroup: 'Remove group',
  addToGroup: 'Add to group',
  addToQuickAccess: 'Add to quick access',
  remove: 'Remove',
  search: 'Find a command',
  reset: 'Restore the default bar',
  newTab: 'New tab',
  newGroup: 'New group',
  noCustomGroup: 'Choose one of your own groups to add commands to it.',
  emptyGroup: 'No commands yet.',
});

export function message(messages, key, values={}) {
  const template = messages?.[key] ?? DEFAULT_MESSAGES[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    values[name] === undefined ? match : String(values[name]));
}
