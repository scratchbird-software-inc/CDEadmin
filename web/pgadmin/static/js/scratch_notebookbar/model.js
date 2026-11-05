/////////////////////////////////////////////////////////////
//
// Scratch notebook bar
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The notebook bar's data model: validation, visibility, extension
// contributions and user customization. Pure functions; see README.md.

export const CONTROL_TYPES = Object.freeze([
  'button', 'toggle', 'menu', 'split', 'select', 'color', 'gallery', 'stack',
  'separator',
]);
export const CUSTOMIZATION_SCHEMA = 'scratch.notebookbar-customization.v1';

const ID = /^[A-Za-z0-9][\w.:-]{0,127}$/;

function fail(message) {
  throw new TypeError(`Notebook bar model: ${message}`);
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function contexts(value) {
  if(value === undefined || value === null || value === '') return [];
  return (Array.isArray(value) ? value : [value]).map(String);
}

function checkControl(control, seen, path) {
  if(!control || typeof control !== 'object') fail(`${path} is not a control`);
  const type = control.type ?? 'button';
  if(!CONTROL_TYPES.includes(type)) fail(`${path} has unknown type ${type}`);
  if(type === 'separator') return {...control, type};
  if(!ID.test(String(control.id ?? ''))) fail(`${path} needs an id`);
  if(seen.has(control.id)) fail(`control id ${control.id} is used twice`);
  seen.add(control.id);
  if(type === 'stack') {
    return {...control, type,
      controls: list(control.controls).map((child, index) =>
        checkControl(child, seen, `${path}.controls[${index}]`))};
  }
  if(typeof control.label !== 'string' || !control.label.trim()) {
    fail(`${control.id} needs a label`);
  }
  if(typeof control.command !== 'string' || !control.command) {
    fail(`${control.id} needs a command`);
  }
  if(['menu', 'split', 'gallery'].includes(type) &&
      list(control.items).length === 0) {
    fail(`${control.id} needs items`);
  }
  if(type === 'select' && list(control.options).length === 0) {
    fail(`${control.id} needs options`);
  }
  return {...control, type, size: control.size === 'large' ? 'large' : 'small'};
}

/** Validate a model and fill defaults; throws TypeError on a bad model. */
export function normalizeModel(model) {
  if(!model || typeof model !== 'object') fail('the model is not an object');
  const seen = new Set();
  const tabIds = new Set();
  const tabs = list(model.tabs).map((tab, tabIndex) => {
    if(!ID.test(String(tab?.id ?? ''))) fail(`tabs[${tabIndex}] needs an id`);
    if(tabIds.has(tab.id)) fail(`tab id ${tab.id} is used twice`);
    tabIds.add(tab.id);
    if(typeof tab.label !== 'string' || !tab.label.trim()) {
      fail(`tab ${tab.id} needs a label`);
    }
    const groupIds = new Set();
    return {...tab, context: contexts(tab.context),
      groups: list(tab.groups).map((group, index) => {
        if(!ID.test(String(group?.id ?? ''))) {
          fail(`tab ${tab.id} groups[${index}] needs an id`);
        }
        if(groupIds.has(group.id)) fail(`group ${tab.id}/${group.id} is used twice`);
        groupIds.add(group.id);
        return {...group, priority: Number.isFinite(group.priority) ?
          group.priority : 0,
        controls: list(group.controls).map((control, controlIndex) =>
          checkControl(control, seen,
            `${tab.id}/${group.id}.controls[${controlIndex}]`))};
      })};
  });
  const quickAccess = list(model.quickAccess).map((control, index) =>
    checkControl(control, seen, `quickAccess[${index}]`));
  const defaultTab = tabIds.has(model.defaultTab) ? model.defaultTab :
    tabs.find((tab) => tab.context.length === 0)?.id ?? tabs[0]?.id ?? null;
  return {tabs, quickAccess, defaultTab};
}

/** Tabs shown in the given context (a string, list or nothing). */
export function visibleTabs(model, context) {
  const active = new Set(contexts(context));
  return model.tabs.filter((tab) => !tab.hidden &&
    (tab.context.length === 0 || tab.context.some((item) => active.has(item))));
}

export function commandState(state, control) {
  return state?.[control?.command] ?? {};
}

export function isControlVisible(control, state) {
  if(control.type === 'separator') return true;
  if(control.type === 'stack') {
    return control.controls.some((child) => isControlVisible(child, state));
  }
  return commandState(state, control).hidden !== true && control.hidden !== true;
}

export function isControlEnabled(control, state) {
  return commandState(state, control).enabled !== false &&
    control.disabled !== true;
}

/** A group is hidden when every non-separator control in it is hidden. */
export function isGroupVisible(group, state) {
  return !group.hidden && group.controls.some((control) =>
    control.type !== 'separator' && isControlVisible(control, state));
}

/** Every control in the model, stacks flattened, in display order. */
export function flattenControls(controls) {
  return controls.flatMap((control) => control.type === 'stack' ?
    flattenControls(control.controls) : [control]);
}

function insertAt(items, item, {insertBefore, insertAfter}) {
  const anchor = insertBefore ?? insertAfter;
  const index = anchor ? items.findIndex((entry) => entry.id === anchor) : -1;
  if(index < 0) return [...items, item];
  const at = insertBefore ? index : index + 1;
  return [...items.slice(0, at), item, ...items.slice(at)];
}

/**
 * Add extension contributions: new tabs, and groups on existing tabs, each
 * placed by insertBefore/insertAfter (an id) or at the end. Contributions may
 * not replace an existing tab or group; the result is normalized again.
 */
export function mergeContributions(model, contributions=[]) {
  let tabs = [...model.tabs];
  for(const contribution of contributions) {
    if(contribution.tab && !contribution.groupsFor) {
      if(tabs.some((tab) => tab.id === contribution.tab.id)) {
        fail(`contributed tab ${contribution.tab.id} already exists`);
      }
      tabs = insertAt(tabs, contribution.tab, contribution);
    } else if(contribution.groupsFor) {
      const index = tabs.findIndex((tab) => tab.id === contribution.groupsFor);
      if(index < 0) continue;
      let groups = [...tabs[index].groups];
      for(const group of contribution.groups ?? []) {
        if(groups.some((existing) => existing.id === group.id)) {
          fail(`contributed group ${group.id} already exists`);
        }
        groups = insertAt(groups, group, contribution);
      }
      tabs = tabs.map((tab, at) => at === index ? {...tab, groups} : tab);
    }
  }
  return normalizeModel({...model, tabs});
}

// Items the customization orders come first, by that order; the rest follow
// in their original order.
function orderBy(items, order) {
  const ordered = items.filter((item) => Number.isFinite(order(item)))
    .map((item, index) => ({item, index}))
    .sort((left, right) => order(left.item) - order(right.item) ||
      left.index - right.index)
    .map(({item}) => item);
  return [...ordered, ...items.filter((item) => !Number.isFinite(order(item)))];
}

/**
 * The model a user sees after their customization. `catalog` maps command
 * ids to controls the host allows a user to place; references to anything
 * else are dropped, so a customization can never surface a command the host
 * does not offer.
 */
export function applyCustomization(model, customization, catalog={}) {
  if(!customization) return model;
  if(customization.schema !== CUSTOMIZATION_SCHEMA) {
    fail('the customization has an unknown schema');
  }
  const placed = new Set();
  const fromCatalog = (commandId, prefix) => {
    const control = catalog[commandId];
    if(!control) return null;
    const base = `${prefix}:${commandId}`;
    let id = base;
    for(let copy = 2; placed.has(id); copy++) id = `${base}-${copy}`;
    placed.add(id);
    return {...control, id, command: control.command ?? commandId};
  };
  const tabSettings = customization.tabs ?? {};
  let tabs = model.tabs.map((tab) => {
    const settings = tabSettings[tab.id] ?? {};
    const groupSettings = settings.groups ?? {};
    return {...tab, hidden: settings.hidden === true || tab.hidden === true,
      label: typeof settings.label === 'string' && settings.label.trim() ?
        settings.label.trim() : tab.label,
      order: settings.order,
      groups: orderBy(tab.groups.map((group) => ({...group,
        hidden: groupSettings[group.id]?.hidden === true || group.hidden === true,
        label: typeof groupSettings[group.id]?.label === 'string' ?
          groupSettings[group.id].label : group.label,
        order: groupSettings[group.id]?.order,
      })), (group) => group.order)};
  });
  for(const added of list(customization.added)) {
    if(!ID.test(String(added?.tab ?? '')) ||
        tabs.some((tab) => tab.id === added.tab)) continue;
    tabs.push({id: added.tab, label: String(added.label || added.tab),
      order: added.order, context: [], custom: true,
      groups: list(added.groups).filter((group) => ID.test(String(group?.id ?? '')))
        .map((group) => ({id: group.id, label: String(group.label ?? ''),
          priority: 0, custom: true,
          controls: list(group.controls).map((commandId) =>
            fromCatalog(commandId, `${added.tab}.${group.id}`)).filter(Boolean)}))});
  }
  tabs = orderBy(tabs, (tab) => tab.order);
  const quickAccess = Array.isArray(customization.quickAccess) ?
    customization.quickAccess.map((commandId) => fromCatalog(commandId, 'quick'))
      .filter(Boolean) : model.quickAccess;
  return normalizeModel({...model, tabs, quickAccess});
}

export function emptyCustomization() {
  return {schema: CUSTOMIZATION_SCHEMA, tabs: {}, added: []};
}
