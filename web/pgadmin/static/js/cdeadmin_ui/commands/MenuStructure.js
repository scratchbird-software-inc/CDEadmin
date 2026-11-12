/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

const MENU_NAME = /^[a-z][a-z0-9_-]*$/;
const ICON_KEY = /^[a-z0-9][a-z0-9._-]*$/;
const HEX_COLOR = /^#[0-9a-f]{6}$/i;
const FONT_FAMILY = /^[a-zA-Z0-9 ,.'"_-]{1,160}$/;

export const MENU_CUSTOMIZATION_SCHEMA = 'cdeadmin.menu-customization.v1';

export const CDEADMIN_MENU_STRUCTURE = Object.freeze([
  Object.freeze({label: 'File', name: 'file', id: 'mnu_file', index: 0,
    addSeprator: true, hasDynamicMenuItems: false}),
  Object.freeze({label: 'Edit', name: 'edit', id: 'mnu_edit',
    index: 1, addSeprator: true, hasDynamicMenuItems: false}),
  Object.freeze({label: 'View', name: 'view', id: 'mnu_view', index: 2,
    addSeprator: true, hasDynamicMenuItems: false}),
  Object.freeze({label: 'Navigate', name: 'navigate', id: 'mnu_navigate',
    index: 3, addSeprator: true, hasDynamicMenuItems: false}),
  Object.freeze({label: 'Run', name: 'run', id: 'mnu_run', index: 4,
    addSeprator: true, hasDynamicMenuItems: false}),
  Object.freeze({label: 'Data', name: 'data', id: 'mnu_data', index: 5,
    addSeprator: true, hasDynamicMenuItems: false}),
  Object.freeze({label: 'Project', name: 'project', id: 'mnu_project', index: 6,
    addSeprator: true, hasDynamicMenuItems: false}),
  Object.freeze({label: 'Tools', name: 'tools', id: 'mnu_tools', index: 7,
    addSeprator: true, hasDynamicMenuItems: false}),
  Object.freeze({label: 'Window', name: 'window', id: 'mnu_window', index: 8,
    addSeprator: true, hasDynamicMenuItems: false}),
  Object.freeze({label: 'Help', name: 'help', id: 'mnu_help', index: 9,
    addSeprator: false, hasDynamicMenuItems: false}),
]);

// Compatibility alias retained until all callers use the final CDEadmin name.
export const PROVISIONAL_MENU_STRUCTURE = CDEADMIN_MENU_STRUCTURE;

function normalizeMenu(input, index) {
  const name = String(input?.name ?? '').trim();
  if(!MENU_NAME.test(name)) throw new TypeError(`Invalid menu name: ${name}`);
  return Object.freeze({
    label: String(input.label ?? name),
    name,
    id: String(input.id ?? `mnu_${name}`),
    index: Number.isFinite(input.index) ? input.index : index,
    addSeprator: Boolean(input.addSeprator),
    hasDynamicMenuItems: Boolean(input.hasDynamicMenuItems),
    iconKey: ICON_KEY.test(String(input.iconKey ?? '')) ?
      String(input.iconKey) : '',
    presentation: Object.freeze({...input.presentation}),
  });
}

function bounded(value, minimum, maximum, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ?
    Math.max(minimum, Math.min(maximum, number)) : fallback;
}

export function normalizeMenuPresentation(input={}) {
  const fontFamily = String(input.fontFamily ?? '').trim();
  const color = String(input.color ?? '').trim().toUpperCase();
  const backgroundColor = String(input.backgroundColor ?? '').trim().toUpperCase();
  const result = {};
  if(FONT_FAMILY.test(fontFamily)) result.fontFamily = fontFamily;
  if(Number.isFinite(Number(input.fontSize)) && Number(input.fontSize) !== -1) {
    result.fontSize = bounded(input.fontSize, 8, 32, 14);
  }
  if(Number.isFinite(Number(input.fontWeight)) &&
      Number(input.fontWeight) !== -1) {
    result.fontWeight = bounded(input.fontWeight, 300, 900, 400);
  }
  if(HEX_COLOR.test(color)) result.color = color;
  if(HEX_COLOR.test(backgroundColor)) {
    result.backgroundColor = backgroundColor;
  }
  if(['after', 'hidden'].includes(input.iconPosition)) {
    result.iconPosition = input.iconPosition;
  }
  return Object.freeze(result);
}

export function normalizeMenuCustomizations(input={}) {
  let candidate = input;
  if(typeof candidate === 'string') {
    try {
      candidate = JSON.parse(candidate || '{}');
    } catch {
      return Object.freeze({});
    }
  }
  if(candidate?.schema === MENU_CUSTOMIZATION_SCHEMA) candidate = candidate.menus;
  if(!candidate || Array.isArray(candidate) || typeof candidate !== 'object') {
    return Object.freeze({});
  }
  const result = {};
  Object.entries(candidate).forEach(([key, value]) => {
    const name = String(key).trim().toLowerCase();
    if(!MENU_NAME.test(name) || !value || Array.isArray(value) ||
        typeof value !== 'object') return;
    const label = String(value.label ?? name).trim().slice(0, 80) || name;
    const iconKey = String(value.iconKey ?? '').trim().toLowerCase();
    result[name] = Object.freeze({
      name,
      label,
      visible: value.visible !== false,
      index: bounded(value.index, 0, 1000, 100),
      iconKey: ICON_KEY.test(iconKey) ? iconKey : '',
      presentation: normalizeMenuPresentation(value.presentation),
    });
  });
  return Object.freeze(result);
}

export function createMenuCustomizationDocument(menus={}) {
  return Object.freeze({
    schema: MENU_CUSTOMIZATION_SCHEMA,
    menus: normalizeMenuCustomizations(menus),
  });
}

export class MenuStructureRegistry {
  constructor(structure=CDEADMIN_MENU_STRUCTURE) {
    this.replace(structure);
  }

  replace(structure) {
    if(!Array.isArray(structure) || structure.length === 0) {
      throw new TypeError('Menu structure must contain at least one menu.');
    }
    const names = new Set();
    this.structure = Object.freeze(structure.map((menu, index)=>{
      const normalized = normalizeMenu(menu, index);
      if(names.has(normalized.name)) {
        throw new Error(`Duplicate menu name: ${normalized.name}`);
      }
      names.add(normalized.name);
      return normalized;
    }));
    return this.structure;
  }

  get() {
    return this.structure;
  }

  resolve(customizations={}) {
    const overrides = normalizeMenuCustomizations(customizations);
    const defaults = new Map(this.structure.map((item)=>[item.name, item]));
    const result = this.structure.map((item) => {
      const override = overrides[item.name];
      return override ? normalizeMenu({
        ...item,
        label: override.label,
        index: override.index,
        iconKey: override.iconKey,
        presentation: override.presentation,
      }, item.index) : item;
    }).filter((item)=>overrides[item.name]?.visible !== false);
    Object.values(overrides).forEach((override) => {
      if(defaults.has(override.name) || !override.visible) return;
      result.push(normalizeMenu({
        ...override,
        id: `mnu_${override.name}`,
        addSeprator: true,
        hasDynamicMenuItems: false,
      }, result.length));
    });
    return Object.freeze(result.sort((left, right) =>
      left.index - right.index || left.label.localeCompare(right.label)
    ));
  }

  surfaces() {
    // Legacy contribution names remain accepted while their presentation is
    // mapped into the normative CDEadmin menu taxonomy.
    return new Set([
      'context', 'connectors', 'management', 'object',
      ...this.structure.map((menu)=>menu.name),
    ]);
  }
}

export class MenuBindingRegistry {
  constructor() {
    this.bindings = new Map();
  }

  register(input) {
    const surface = String(input?.surface ?? '').trim();
    const commandId = String(input?.commandId ?? '').trim();
    const name = String(input?.name ?? commandId).trim();
    if(!surface || !commandId || !name) {
      throw new TypeError('Menu bindings require surface, commandId, and name.');
    }
    const key = `${surface}:${name}:${String(input.node ?? '')}`;
    const binding = Object.freeze({
      key, surface, commandId, name,
      category: String(input.category ?? 'common'),
      node: input.node ?? null,
      priority: Number.isFinite(input.priority) ? input.priority : 10,
      commandArguments: input.commandArguments ?? {},
    });
    this.bindings.set(key, binding);
    return binding;
  }

  list(surface=null) {
    return [...this.bindings.values()].filter(
      (binding)=>surface === null || binding.surface === surface
    );
  }
}

export const menuStructureRegistry = new MenuStructureRegistry();
export const menuBindingRegistry = new MenuBindingRegistry();

export const PROJECT_TOP_MENU_INDICES = Object.freeze({
  SYSTEM: 0,
  APPLICATIONS: 60,
  WINDOW: 70,
  HELP: 80,
});

export const PROJECT_MINIMAL_MENUS = Object.freeze([
  Object.freeze({
    name: 'system',
    id: 'mnu_system',
    label: 'ScratchRobin',
    index: PROJECT_TOP_MENU_INDICES.SYSTEM,
    iconKey: 'tool.scratchrobin',
    isSystemIcon: true,
    items: Object.freeze([]),
  }),
  Object.freeze({
    name: 'applications',
    id: 'mnu_applications',
    label: 'Applications',
    index: PROJECT_TOP_MENU_INDICES.APPLICATIONS,
    items: Object.freeze([]),
  }),
  Object.freeze({
    name: 'window',
    id: 'mnu_window',
    label: 'Window',
    index: PROJECT_TOP_MENU_INDICES.WINDOW,
    items: Object.freeze([]),
  }),
  Object.freeze({
    name: 'help',
    id: 'mnu_help',
    label: 'Help',
    index: PROJECT_TOP_MENU_INDICES.HELP,
    items: Object.freeze([]),
  }),
]);

export function assertUnsignedMenuIndex(value, fallback = 0) {
  if (value === undefined || value === null) return fallback;
  if (!Number.isInteger(value) || value < 0) {
    throw new RangeError(
      `Menu positional index must be an unsigned integer (>= 0), got: ${value}`
    );
  }
  return value;
}

function normalizeProjectMenuItem(raw, fallbackIndex = 0, owner = 'shell') {
  const index = assertUnsignedMenuIndex(raw?.index, fallbackIndex);
  if (raw?.type === 'separator') {
    return Object.freeze({
      id: String(raw.id || `sep_${owner}_${index}`),
      type: 'separator',
      index,
      owner,
    });
  }
  const id = String(raw?.id || raw?.actionId || raw?.commandId || raw?.name || `item_${index}`).trim();
  const children = Array.isArray(raw?.items || raw?.children)
    ? sortProjectMenuItems(
      (raw.items || raw.children).map((child, i) =>
        normalizeProjectMenuItem(child, (i + 1) * 10, owner)
      )
    )
    : null;
  return Object.freeze({
    id,
    name: String(raw?.name || id),
    label: String(raw?.label ?? id),
    index,
    owner,
    type: raw?.type || (children ? 'submenu' : 'item'),
    actionId: raw?.actionId ? String(raw.actionId) : '',
    commandId: raw?.commandId ? String(raw.commandId) : (raw?.actionId ? String(raw.actionId) : ''),
    iconKey: raw?.iconKey ? String(raw.iconKey) : '',
    shortcut: raw?.shortcut ? String(raw.shortcut) : '',
    i18nKey: raw?.i18nKey ? String(raw.i18nKey) : '',
    hintKey: raw?.hintKey ? String(raw.hintKey) : '',
    hint: raw?.hint ? String(raw.hint) : '',
    i18nArgs: Array.isArray(raw?.i18nArgs) ? Object.freeze([...raw.i18nArgs]) : null,
    checked: typeof raw?.checked === 'boolean' ? raw.checked : undefined,
    isDisabled: Boolean(raw?.isDisabled || raw?.disabled),
    callback: typeof raw?.callback === 'function' ? raw.callback : null,
    presentation: normalizeMenuPresentation(raw?.presentation),
    items: children,
  });
}

export function sortProjectMenuItems(items = []) {
  return Object.freeze(
    [...items].sort((left, right) => {
      if (left.index !== right.index) return left.index - right.index;
      if (left.owner !== right.owner) {
        if (left.owner === 'shell') return -1;
        if (right.owner === 'shell') return 1;
      }
      return String(left.id || '').localeCompare(String(right.id || ''));
    })
  );
}

function mergeMenuItemLists(baseItems = [], incomingItems = []) {
  const merged = [...baseItems];
  for (const incoming of incomingItems) {
    if (incoming.type === 'submenu' && incoming.items) {
      const matchIdx = merged.findIndex(
        (existing) =>
          existing.type === 'submenu' &&
          (existing.index === incoming.index || existing.name === incoming.name)
      );
      if (matchIdx >= 0) {
        const existing = merged[matchIdx];
        merged[matchIdx] = Object.freeze({
          ...existing,
          items: mergeMenuItemLists(existing.items || [], incoming.items),
        });
        continue;
      }
    }
    merged.push(incoming);
  }
  return sortProjectMenuItems(merged);
}

function normalizeProjectTopMenu(raw, fallbackIndex = 0, owner = 'shell') {
  const name = String(raw?.name ?? '').trim().toLowerCase();
  if (!MENU_NAME.test(name)) {
    throw new TypeError(`Invalid top-level menu name: "${raw?.name}"`);
  }
  const index = assertUnsignedMenuIndex(raw?.index, fallbackIndex);
  const items = sortProjectMenuItems(
    (raw?.items || []).map((item, idx) =>
      normalizeProjectMenuItem(item, (idx + 1) * 10, owner)
    )
  );
  return Object.freeze({
    name,
    id: String(raw?.id || `mnu_${name}`),
    label: String(raw?.label ?? name),
    i18nKey: raw?.i18nKey ? String(raw.i18nKey) : '',
    index,
    owner,
    isSystemIcon: Boolean(raw?.isSystemIcon || index === PROJECT_TOP_MENU_INDICES.SYSTEM),
    iconKey: ICON_KEY.test(String(raw?.iconKey ?? '')) ? String(raw.iconKey) : '',
    presentation: normalizeMenuPresentation(raw?.presentation),
    items,
  });
}

/**
 * Recursive unsigned-integer positional Top Menu registry for Area 1.
 * Unoccupied indices collapse with zero visual gap; focused application menus
 * either insert at unoccupied indices (1..59, 61..69, 71..79, 81+) or merge
 * their child items by child `index` into an existing menu (e.g. 60, 70, 80),
 * and cleanly unmerge on teardown.
 */
export class ProjectTopMenuRegistry {
  constructor(baseline = PROJECT_MINIMAL_MENUS) {
    this._listeners = new Set();
    this._focusedOwner = null;
    this._focusedMenus = [];
    this.setBaselineMenus(baseline);
  }

  subscribe(listener) {
    if (typeof listener !== 'function') {
      throw new TypeError('ProjectTopMenuRegistry listener must be a function.');
    }
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  _notify() {
    this._listeners.forEach((listener) => {
      try {
        listener();
      } catch {
        // Keep other listeners healthy.
      }
    });
  }

  setBaselineMenus(menus = PROJECT_MINIMAL_MENUS) {
    this._baselineMenus = Object.freeze(
      (menus || []).map((menu, idx) => normalizeProjectTopMenu(menu, idx * 10, 'shell'))
    );
    this._notify();
    return this.resolve();
  }

  setFocusedApplicationMenus(ownerId, menus = []) {
    const owner = String(ownerId || 'focused-app').trim() || 'focused-app';
    this._focusedOwner = owner;
    this._focusedMenus = Object.freeze(
      (menus || []).map((menu, idx) => normalizeProjectTopMenu(menu, idx + 1, owner))
    );
    this._notify();
    return this.resolve();
  }

  clearFocusedApplicationMenus() {
    const hadMenus = this._focusedMenus.length > 0 || this._focusedOwner !== null;
    this._focusedOwner = null;
    this._focusedMenus = Object.freeze([]);
    if (hadMenus) this._notify();
    return this.resolve();
  }

  getFocusedOwner() {
    return this._focusedOwner;
  }

  resolve() {
    const byIndex = new Map();
    for (const baseMenu of this._baselineMenus) {
      byIndex.set(baseMenu.index, baseMenu);
    }
    for (const appMenu of this._focusedMenus) {
      const existingByIndex = byIndex.get(appMenu.index);
      const existingByName = !existingByIndex
        ? [...byIndex.values()].find((m) => m.name === appMenu.name)
        : null;
      const target = existingByIndex || existingByName;
      if (target) {
        byIndex.set(
          target.index,
          Object.freeze({
            ...target,
            items: mergeMenuItemLists(target.items, appMenu.items),
          })
        );
      } else {
        byIndex.set(appMenu.index, appMenu);
      }
    }
    return Object.freeze(
      [...byIndex.values()].sort(
        (left, right) => left.index - right.index || left.name.localeCompare(right.name)
      )
    );
  }
}

export const projectTopMenuRegistry = new ProjectTopMenuRegistry();
