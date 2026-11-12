/////////////////////////////////////////////////////////////
//
// ScratchRobin — Action, Menu & Tabbed-Notebook-Iconbar Placement Engine
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

export const FALLBACK_QUICK_ACCESS_IDS = Object.freeze([
  'shell.quick.new',
  'shell.quick.save',
  'shell.quick.undo',
  'shell.quick.redo',
]);

export const ACTION_PLACEMENTS_CHANGED_EVENT = 'scratchrobin:action-placements-changed';
export const LOCAL_PLACEMENTS_STORAGE_KEY = 'scratchrobin.shell.action_placements.v1';

/**
 * Built-in baseline catalog of actions per application so the Action/Menu/Iconbar
 * editor can inspect and customize every application even before an instance of
 * that application has been opened in the current session.
 */
export const CANONICAL_APPLICATION_SURFACES = Object.freeze({
  'data-navigator': {
    menuName: 'object',
    menuLabel: 'Object',
    menuIndex: 20,
    defaultMenuActions: ['data-navigator.refresh'],
    defaultTabs: [
      {
        id: 'navigator-catalog',
        label: 'Catalog',
        groups: [{id: 'catalog', label: 'Catalog', actions: ['data-navigator.refresh']}],
      },
    ],
  },
  'sql-editor': {
    menuName: 'query',
    menuLabel: 'Query',
    menuIndex: 25,
    defaultMenuActions: ['sql.execute', 'sql.pause', 'sql.cancel', 'sql.limits'],
    defaultTabs: [
      {
        id: 'sql-execution',
        label: 'Execution',
        groups: [
          {
            id: 'run',
            label: 'Execution & Step Fetch',
            actions: ['sql.execute', 'sql.pause', 'sql.cancel', 'sql.limits'],
          },
        ],
      },
    ],
  },
  'erd-designer': {
    menuName: 'design',
    menuLabel: 'Design',
    menuIndex: 30,
    defaultMenuActions: [
      'erd.palette.entities',
      'erd.palette.udt',
      'erd.save_checkpoint',
      'erd.history',
      'erd.where_used',
    ],
    defaultTabs: [
      {
        id: 'erd-modelling',
        label: 'Modelling',
        groups: [
          {
            id: 'tools',
            label: 'Tools & Palettes',
            actions: [
              'erd.palette.entities',
              'erd.palette.udt',
              'erd.save_checkpoint',
              'erd.history',
              'erd.where_used',
            ],
          },
        ],
      },
    ],
  },
  'cube-designer': {
    menuName: 'design',
    menuLabel: 'Cube',
    menuIndex: 30,
    defaultMenuActions: [
      'cube.palette.elements',
      'cube.palette.udt',
      'cube.save_checkpoint',
      'cube.history',
    ],
    defaultTabs: [
      {
        id: 'cube-modelling',
        label: 'Dimensional',
        groups: [
          {
            id: 'tools',
            label: 'Cube Tools',
            actions: [
              'cube.palette.elements',
              'cube.palette.udt',
              'cube.save_checkpoint',
              'cube.history',
            ],
          },
        ],
      },
    ],
  },
  'bi-designer': {
    menuName: 'design',
    menuLabel: 'Analytics',
    menuIndex: 30,
    defaultMenuActions: ['bi.palette.cards', 'bi.save_checkpoint', 'bi.history', 'bi.where_used'],
    defaultTabs: [
      {
        id: 'bi-authoring',
        label: 'BI & Charts',
        groups: [
          {
            id: 'tools',
            label: 'BI Tools',
            actions: ['bi.palette.cards', 'bi.save_checkpoint', 'bi.history', 'bi.where_used'],
          },
        ],
      },
    ],
  },
  'screen-mesh-designer': {
    menuName: 'design',
    menuLabel: 'Wireframe',
    menuIndex: 30,
    defaultMenuActions: ['mesh.palette.controls', 'mesh.save_checkpoint', 'mesh.history'],
    defaultTabs: [
      {
        id: 'mesh-wireframe',
        label: 'Wireframe',
        groups: [
          {
            id: 'tools',
            label: 'Wireframe Stencil',
            actions: ['mesh.palette.controls', 'mesh.save_checkpoint', 'mesh.history'],
          },
        ],
      },
    ],
  },
  'schema-compare': {
    menuName: 'compare',
    menuLabel: 'Compare',
    menuIndex: 35,
    defaultMenuActions: [
      'schema-compare.pick_source',
      'schema-compare.pick_target',
      'schema-compare.run',
      'schema-compare.review_plan',
    ],
    defaultTabs: [
      {
        id: 'schema-compare-main',
        label: 'Schema Comparison',
        groups: [
          {
            id: 'endpoints',
            label: 'Comparison Workflow',
            actions: [
              'schema-compare.pick_source',
              'schema-compare.pick_target',
              'schema-compare.run',
              'schema-compare.review_plan',
            ],
          },
        ],
      },
    ],
  },
  'project-explorer': {
    menuName: 'project',
    menuLabel: 'Project',
    menuIndex: 28,
    defaultMenuActions: ['project.new_asset', 'project.import_ddn', 'project.export_ddn'],
    defaultTabs: [
      {
        id: 'project-assets',
        label: 'Assets',
        groups: [
          {
            id: 'assets',
            label: 'Project Assets',
            actions: ['project.new_asset', 'project.import_ddn', 'project.export_ddn'],
          },
        ],
      },
    ],
  },
});

export const CANONICAL_ACTION_CATALOG = Object.freeze([
  {id: 'shell.quick.new', label: 'New Item / Tab', icon: 'action.add', scope: 'Quick Access (3b1)'},
  {id: 'shell.quick.save', label: 'Save Active Work', icon: 'action.save', scope: 'Quick Access (3b1)'},
  {id: 'shell.quick.undo', label: 'Undo', icon: 'action.undo', scope: 'Quick Access (3b1)'},
  {id: 'shell.quick.redo', label: 'Redo', icon: 'action.redo', scope: 'Quick Access (3b1)'},
  {id: 'shell.window.toggle_left_drawer', label: 'Toggle Left Side Drawer (3a)', icon: 'navigation.sidebar', scope: 'Global Window'},
  {id: 'shell.window.toggle_right_drawer', label: 'Toggle Right Properties Drawer (3c)', icon: 'action.inspector_drawer', scope: 'Global Window'},
  {id: 'shell.window.toggle_icon_bar', label: 'Toggle Tabbed-Notebook-Bar (3b)', icon: 'view.toolbar', scope: 'Global Window'},
  {id: 'shell.window.toggle_status_bar', label: 'Toggle Status Bar (3d)', icon: 'view.status', scope: 'Global Window'},
  {id: 'shell.window.detach_active', label: 'Float Active Application Window', icon: 'action.external', scope: 'Global Window'},
  {id: 'project.settings.global', label: 'Open Preferences & Settings', icon: 'action.settings', scope: 'Global System'},
  {id: 'project.session.lock', label: 'Lock Session Screen', icon: 'security.lock', scope: 'Global System'},
  {id: 'help.reference.sql', label: 'Multi-Engine SQL Reference', icon: 'help.docs', scope: 'Global Help'},
  {id: 'help.reference.engines', label: 'Database Engine Reference', icon: 'tool.data-explorer', scope: 'Global Help'},
  {id: 'help.reference.glossary', label: 'ScratchRobin Glossary', icon: 'help.info', scope: 'Global Help'},
  {id: 'data-navigator.refresh', label: 'Refresh Catalog Branch', icon: 'action.refresh', scope: 'Data Navigator'},
  {id: 'sql.execute', label: 'Execute SQL Statement', icon: 'action.play', scope: 'SQL Editor'},
  {id: 'sql.pause', label: 'Pause Step Cursor Fetch', icon: 'action.pause', scope: 'SQL Editor'},
  {id: 'sql.cancel', label: 'Cancel Running Statement', icon: 'action.stop', scope: 'SQL Editor'},
  {id: 'sql.limits', label: 'Configure Max Rows & Rows per Step', icon: 'action.tune', scope: 'SQL Editor'},
  {id: 'erd.palette.entities', label: 'Popup Diagram Entity Stencil', icon: 'tool.erd', scope: 'ERD & Data Modelling'},
  {id: 'erd.palette.udt', label: 'Popup User-Defined Data Types & Domains', icon: 'object.domain', scope: 'ERD & Data Modelling'},
  {id: 'erd.save_checkpoint', label: 'Save Design Checkpoint', icon: 'action.save', scope: 'ERD & Data Modelling'},
  {id: 'erd.history', label: 'Checkpoint Version History', icon: 'action.history', scope: 'ERD & Data Modelling'},
  {id: 'erd.where_used', label: 'Inspect Where-Used Bindings', icon: 'action.search', scope: 'ERD & Data Modelling'},
  {id: 'cube.palette.elements', label: 'Popup Cube Measure/Dimension Stencil', icon: 'tool.cube', scope: 'Cube Designer'},
  {id: 'cube.palette.udt', label: 'Popup Dimensional Data Types', icon: 'object.domain', scope: 'Cube Designer'},
  {id: 'cube.save_checkpoint', label: 'Save Cube Checkpoint', icon: 'action.save', scope: 'Cube Designer'},
  {id: 'cube.history', label: 'Cube Version History', icon: 'action.history', scope: 'Cube Designer'},
  {id: 'bi.palette.cards', label: 'Popup BI Chart & Filter Stencil', icon: 'tool.bi', scope: 'BI Questions & Dashboards'},
  {id: 'bi.save_checkpoint', label: 'Save BI Checkpoint', icon: 'action.save', scope: 'BI Questions & Dashboards'},
  {id: 'bi.history', label: 'BI Version History', icon: 'action.history', scope: 'BI Questions & Dashboards'},
  {id: 'bi.where_used', label: 'Inspect BI Data Lineage', icon: 'action.search', scope: 'BI Questions & Dashboards'},
  {id: 'mesh.palette.controls', label: 'Popup Wireframe Control & Region Stencil', icon: 'tool.screen-mesh', scope: 'Screen Mesh Designer'},
  {id: 'mesh.save_checkpoint', label: 'Save Screen Mesh Checkpoint', icon: 'action.save', scope: 'Screen Mesh Designer'},
  {id: 'mesh.history', label: 'Screen Mesh History', icon: 'action.history', scope: 'Screen Mesh Designer'},
  {id: 'schema-compare.pick_source', label: 'Choose Source Endpoint / Design', icon: 'action.source_endpoint', scope: 'Schema Comparison'},
  {id: 'schema-compare.pick_target', label: 'Choose Target Endpoint / Design', icon: 'action.target_endpoint', scope: 'Schema Comparison'},
  {id: 'schema-compare.run', label: 'Run Schema Comparison', icon: 'action.compare_run', scope: 'Schema Comparison'},
  {id: 'schema-compare.review_plan', label: 'Send Plan to Native Operation Review', icon: 'action.send_review', scope: 'Schema Comparison'},
  {id: 'project.new_asset', label: 'New Project Design / Notebook', icon: 'action.add', scope: 'Project Explorer'},
  {id: 'project.import_ddn', label: 'Import DDN File', icon: 'action.import', scope: 'Project Explorer'},
  {id: 'project.export_ddn', label: 'Export DDN Snapshot', icon: 'action.export', scope: 'Project Explorer'},
]);

export function readLocalPlacements() {
  if (typeof window === 'undefined') return {};
  try {
    return JSON.parse(window.localStorage?.getItem(LOCAL_PLACEMENTS_STORAGE_KEY) || '{}') || {};
  } catch {
    return {};
  }
}

export function writeLocalPlacements(patch = {}) {
  if (typeof window === 'undefined') return patch;
  const merged = {...readLocalPlacements(), ...patch};
  try {
    window.localStorage?.setItem(LOCAL_PLACEMENTS_STORAGE_KEY, JSON.stringify(merged));
  } catch {
    // Ignore quota errors.
  }
  window.dispatchEvent(new CustomEvent(ACTION_PLACEMENTS_CHANGED_EVENT, {detail: merged}));
  return merged;
}

/**
 * Resolves live global Area 1 menus by applying `global.menu_placements`
 * (visibility, index ordering, custom labels, custom icons, and extra placed action items).
 */
export function applyGlobalMenuPlacements(
  menus = [],
  globalSettings = {},
  actionsRegistry = null,
  focusedAppSettings = null
) {
  const local = readLocalPlacements();
  const globalPlacements = globalSettings?.menu_placements || local.menu_placements || {};
  const appPlacements = focusedAppSettings?.menu_placements || {};
  const placements = {...globalPlacements, ...appPlacements};
  const iconAssignments = globalSettings?.icon_assignments || local.icon_assignments || {};
  if (!placements || typeof placements !== 'object') return menus;

  const result = [];
  for (const menu of menus) {
    if (menu.isSystemIcon) {
      result.push(menu);
      continue;
    }
    const cfg = placements[menu.name];
    if (cfg && cfg.visible === false) {
      continue;
    }
    const extraActions = Array.isArray(cfg?.added_actions) ? cfg.added_actions : [];
    const hiddenItems = new Set(Array.isArray(cfg?.hidden_items) ? cfg.hidden_items : []);
    const itemOrder = Array.isArray(cfg?.item_order) ? cfg.item_order : null;

    let items = (menu.items || [])
      .filter((it) => !hiddenItems.has(it.actionId || it.id))
      .map((it) => {
        const aid = it.actionId || it.id;
        const assignedIcon = iconAssignments[aid] || iconAssignments[it.iconKey];
        return assignedIcon ? {...it, iconKey: assignedIcon} : it;
      });

    for (const actionId of extraActions) {
      if (items.some((it) => (it.actionId || it.id) === actionId)) continue;
      const catEntry = CANONICAL_ACTION_CATALOG.find((c) => c.id === actionId);
      const regAction = actionsRegistry?.has?.(actionId) ? actionsRegistry.resolve(actionId) : null;
      items.push({
        id: `placed_${actionId}`,
        owner: 'user_placement',
        actionId,
        label: regAction?.text || catEntry?.label || actionId,
        iconKey: iconAssignments[actionId] || regAction?.icon || catEntry?.icon || 'command.default',
        index: 900 + items.length,
      });
    }

    if (itemOrder && itemOrder.length > 0) {
      const rank = new Map(itemOrder.map((id, idx) => [id, idx]));
      items = [...items].sort((a, b) => {
        const ra = rank.has(a.actionId || a.id) ? rank.get(a.actionId || a.id) : 999;
        const rb = rank.has(b.actionId || b.id) ? rank.get(b.actionId || b.id) : 999;
        return ra - rb;
      });
    }

    result.push({
      ...menu,
      label: cfg?.label?.trim() || menu.label,
      index: Number.isFinite(Number(cfg?.index)) ? Number(cfg.index) : menu.index,
      iconKey: cfg?.iconKey !== undefined && cfg.iconKey !== '' ? cfg.iconKey : menu.iconKey,
      items,
    });
  }

  // Append any custom top-level menus defined in `placements.__custom_menus`
  const customMenus = Array.isArray(placements.__custom_menus) ? placements.__custom_menus : [];
  for (const cm of customMenus) {
    if (!cm?.name || cm.visible === false) continue;
    if (result.some((m) => m.name === cm.name)) continue;
    const items = (cm.actions || []).map((actionId, idx) => {
      const catEntry = CANONICAL_ACTION_CATALOG.find((c) => c.id === actionId);
      const regAction = actionsRegistry?.has?.(actionId) ? actionsRegistry.resolve(actionId) : null;
      return {
        id: `custom_${cm.name}_${actionId}`,
        owner: cm.name,
        actionId,
        label: regAction?.text || catEntry?.label || actionId,
        iconKey: iconAssignments[actionId] || regAction?.icon || catEntry?.icon || 'command.default',
        index: (idx + 1) * 10,
      };
    });
    result.push({
      name: cm.name,
      label: cm.label || cm.name,
      index: Number.isFinite(Number(cm.index)) ? Number(cm.index) : 65,
      iconKey: cm.iconKey || '',
      items,
    });
  }

  return result.sort((a, b) => (a.index ?? 50) - (b.index ?? 50));
}

/**
 * Resolves live `3b1` Quick-Access action IDs and `3b` `ribbonTabs` for the focused
 * application instance, merging instance defaults with persisted user placements.
 */
export function resolveInstanceNotebookBarSpec(instance, settings = {}) {
  if (!instance) {
    return {ribbonTabs: [], quickAccess: [...FALLBACK_QUICK_ACCESS_IDS], iconAssignments: {}};
  }
  const local = readLocalPlacements();
  const globalCfg = settings?.global || {};
  const appCfg = settings?.applications?.[instance.appId] || local.applications?.[instance.appId] || {};
  const iconAssignments = globalCfg.icon_assignments || local.icon_assignments || {};

  const quickAccess =
    Array.isArray(appCfg.quick_access) && appCfg.quick_access.length > 0
      ? appCfg.quick_access
      : Array.isArray(globalCfg.quick_access) && globalCfg.quick_access.length > 0
        ? globalCfg.quick_access
        : Array.isArray(local.quick_access) && local.quick_access.length > 0
          ? local.quick_access
          : instance.quickAccess || FALLBACK_QUICK_ACCESS_IDS;

  const baseTabs = Array.isArray(instance.ribbonTabs) ? instance.ribbonTabs : [];
  const nbPlacements = appCfg.notebookbar_placements;
  if (!nbPlacements || !Array.isArray(nbPlacements.tabs) || nbPlacements.tabs.length === 0) {
    return {ribbonTabs: baseTabs, quickAccess, iconAssignments};
  }

  // Map canonical base action IDs to instance-scoped dynamic action IDs when applicable
  // (e.g. `data-navigator.refresh` -> `data-navigator.refresh.<instanceId>`)
  const instanceActionIds = [];
  baseTabs.forEach((t) =>
    (t.groups || []).forEach((g) =>
      (g.actions || g.controls || []).forEach((a) => {
        const id = typeof a === 'string' ? a : a?.actionId || a?.command;
        if (id) instanceActionIds.push(id);
      })
    )
  );

  const mapToLiveActionId = (canonicalOrRawId) => {
    if (instanceActionIds.includes(canonicalOrRawId)) return canonicalOrRawId;
    const prefixed = instanceActionIds.find((liveId) => liveId.startsWith(`${canonicalOrRawId}.`));
    return prefixed || canonicalOrRawId;
  };

  const mergedTabs = nbPlacements.tabs
    .filter((t) => t && t.hidden !== true)
    .map((tab) => ({
      id: tab.id || 'custom-tab',
      label: tab.label || 'Commands',
      groups: (tab.groups || [])
        .filter((g) => g && g.hidden !== true)
        .map((grp) => ({
          id: grp.id || 'group',
          label: grp.label || 'Actions',
          actions: (grp.actions || []).map(mapToLiveActionId),
        })),
    }));

  return {
    ribbonTabs: mergedTabs.length > 0 ? mergedTabs : baseTabs,
    quickAccess: quickAccess.map(mapToLiveActionId),
    iconAssignments,
  };
}
