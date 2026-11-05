/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The tabbed command bar's model, built from the same main menus the menu
// bar shows: one tab per top-level menu, one group per run of items between
// separators, a menu button per submenu and a toggle per checkbox item.
// Commands run through the menu items' own callbacks, so permissions,
// enablement and customization are exactly the menu bar's. Layout is
// generic: small labelled buttons stacked three high, unless a command
// declares `toolbarSize: 'large'`.

export const COMMAND_BAR_STACK = 3;
// A long run of items is split into groups of this many, so a narrow window
// folds them into More one group at a time rather than all at once.
export const COMMAND_BAR_GROUP = 12;

const ID = /^[A-Za-z0-9][\w.:-]{0,127}$/;

function controlId(item, fallback) {
  const candidate = String(item.commandId || item.name || '');
  return ID.test(candidate) ? candidate : fallback;
}

function stack(controls, prefix) {
  const result = [];
  let run = [];
  const flush = () => {
    if(run.length === 1) result.push(run[0]);
    else if(run.length) result.push({type: 'stack', id: `${prefix}.s${result.length}`,
      controls: run});
    run = [];
  };
  for(const control of controls) {
    if(control.size === 'large') {
      flush();
      result.push(control);
    } else {
      run.push(control);
      if(run.length === COMMAND_BAR_STACK) flush();
    }
  }
  flush();
  return result;
}

/**
 * Build {model, state, catalog, run} from menus shaped like
 * pgAdmin.Browser.MainMenus (name, label, getMenuItems(); items with label,
 * callback, isDisabled, checked, shortcut, commandId, iconKey, type,
 * getMenuItems()). `icon(item)` returns the icon node for an item.
 */
export function buildCommandBarModel(menus=[], icon=() => null) {
  const items = new Map();
  const state = {};
  const catalog = {};
  const used = new Set();
  const unique = (id) => {
    let value = id;
    for(let copy = 2; used.has(value); copy++) value = `${id}-${copy}`;
    used.add(value);
    return value;
  };
  const leaf = (item, fallback, detail) => {
    const id = unique(controlId(item, fallback));
    items.set(id, item);
    state[id] = {enabled: !item.isDisabled,
      ...(typeof item.checked === 'boolean' ? {checked: item.checked} : {})};
    const control = {id, command: id, label: String(item.label ?? id),
      type: typeof item.checked === 'boolean' ? 'toggle' : 'button',
      icon: (size) => icon(item, size),
      size: item.toolbarSize === 'large' ? 'large' : 'small',
      ...(typeof item.shortcut === 'string' ? {shortcut: item.shortcut} : {})};
    catalog[id] = {label: control.label, icon: control.icon, type: control.type,
      detail, ...(control.shortcut ? {shortcut: control.shortcut} : {})};
    return control;
  };
  const submenu = (item, fallback, detail) => {
    const id = unique(controlId(item, fallback));
    const children = (item.getMenuItems?.() ?? []).flatMap((child, index) => {
      if(child.type === 'separator') return [{type: 'separator'}];
      if(child.getMenuItems?.()?.length) {
        // A deeper submenu becomes its items, one level down.
        return child.getMenuItems().filter((grand) => grand.type !== 'separator')
          .map((grand, at) => leaf(grand, `${id}.${index}.${at}`,
            `${detail} › ${item.label} › ${child.label}`));
      }
      return [leaf(child, `${id}.${index}`, `${detail} › ${item.label}`)];
    });
    const menuItems = children.map((child) => child.type === 'separator' ? child :
      {id: child.id, label: child.label, command: child.command,
        checked: state[child.id].checked, disabled: !state[child.id].enabled});
    state[id] = {enabled: menuItems.some((child) => child.type !== 'separator' &&
      !child.disabled)};
    return {id, command: id, type: 'menu', label: String(item.label ?? id),
      icon: (size) => icon(item, size), items: menuItems, size: 'small'};
  };

  const tabs = menus.filter((menu) => menu?.name && menu.visible !== false)
    .map((menu) => {
      const groups = [];
      let current = [];
      const close = () => {
        for(let start = 0; start < current.length; start += COMMAND_BAR_GROUP) {
          const run = current.slice(start, start + COMMAND_BAR_GROUP);
          const groupId = `${menu.name}.g${groups.length}`;
          // No caption under the group; the customizer names it by its first
          // commands.
          const title = run.slice(0, 2).map((control) => control.label)
            .join(', ') + (run.length > 2 ? ', …' : '');
          groups.push({id: groupId, label: '', title,
            priority: -groups.length, controls: stack(run, groupId)});
        }
        current = [];
      };
      (menu.getMenuItems?.() ?? []).forEach((item, index) => {
        if(item.type === 'separator') {
          close();
        } else if(item.getMenuItems?.()?.length) {
          current.push(submenu(item, `${menu.name}.${index}`, menu.label));
        } else {
          current.push(leaf(item, `${menu.name}.${index}`, menu.label));
        }
      });
      close();
      return {id: menu.name, label: String(menu.label ?? menu.name), groups};
    }).filter((tab) => tab.groups.length);

  const run = (command, detail={}) => {
    const target = items.get(detail.item ?? command);
    if(!target || target.isDisabled) return false;
    target.callback?.(target);
    return true;
  };
  return {model: {tabs, quickAccess: []}, state, catalog, run};
}
