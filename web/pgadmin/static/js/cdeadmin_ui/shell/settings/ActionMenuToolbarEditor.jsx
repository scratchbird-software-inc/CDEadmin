/////////////////////////////////////////////////////////////
//
// ScratchRobin — Unified Action, Menu, Standard Section & TiB Settings Editor
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Button} from '../../primitives/Button';
import {NumberField, TextField} from '../../primitives/Field';
import {Select, Switch} from '../../primitives/Choice';
import {SearchField} from '../../primitives/AdvancedControls';
import {Icon, listIconDefinitions} from '../../icons';
import {
  EXTENDED_ACTION_CATALOG,
  CANONICAL_APPLICATION_SURFACES,
  FALLBACK_QUICK_ACCESS_IDS,
  readLocalPlacements,
  writeLocalPlacements,
} from '../actionPlacementEngine';
import {
  CALLABLE_CODE_TARGETS,
  DEFAULT_TIB_CONFIG,
  DEFAULT_TIB_PALETTE_LIGHT,
  STANDARD_TIB_SECTIONS,
  normalizeTiBConfig,
} from '../tibStandardConfig';

const BASELINE_GLOBAL_MENUS = Object.freeze([
  {
    name: 'applications',
    label: 'Applications',
    index: 60,
    defaultItems: ['shell.datasources.open', 'shell.preferences.open'],
  },
  {
    name: 'window',
    label: 'Window',
    index: 70,
    defaultItems: ['shell.window.dashboard', 'shell.window.close'],
  },
  {
    name: 'help',
    label: 'Help',
    index: 80,
    defaultItems: [
      'shell.help.sql_reference',
      'shell.help.engine_reference',
      'shell.help.glossary',
      'shell.help.docs',
      'shell.help.about',
    ],
  },
]);

function cloneTabs(tabs = []) {
  return tabs.map((t) => ({
    id: t.id,
    label: t.label,
    hidden: Boolean(t.hidden),
    groups: (t.groups || []).map((g) => ({
      id: g.id,
      sectionId: g.sectionId || '',
      label: g.label,
      hidden: Boolean(g.hidden),
      actions: [...(g.actions || g.controls || [])]
        .map((a) => (typeof a === 'string' ? a : a?.actionId || a?.command || ''))
        .filter(Boolean),
    })),
  }));
}

export function ActionMenuToolbarEditor({
  subView = 'global-menus',
  hideTabs = false,
  globalSettings = {},
  applicationSettings = {},
  applications = [],
  actionsRegistry = null,
  onChangeGlobal,
  onChangeApp,
  onNavigateSubView,
}) {
  const localInitial = useMemo(() => readLocalPlacements(), []);
  const [activeSubView, setActiveSubView] = useState(subView);

  useEffect(() => {
    setActiveSubView(subView);
  }, [subView]);

  const switchSubView = (nextView) => {
    setActiveSubView(nextView);
    onNavigateSubView?.(nextView);
  };

  const [menuPlacements, setMenuPlacements] = useState(
    () => globalSettings.menu_placements || localInitial.menu_placements || {}
  );
  const [quickAccess, setQuickAccess] = useState(() =>
    Array.isArray(globalSettings.quick_access) && globalSettings.quick_access.length > 0
      ? globalSettings.quick_access
      : Array.isArray(localInitial.quick_access) && localInitial.quick_access.length > 0
        ? localInitial.quick_access
        : [...FALLBACK_QUICK_ACCESS_IDS]
  );
  const [iconAssignments, setIconAssignments] = useState(() => ({
    ...(globalSettings.icon_assignments || {}),
    ...(localInitial.icon_assignments || {}),
  }));
  const [tibConfig, setTibConfig] = useState(() =>
    normalizeTiBConfig({
      ...(globalSettings.tib_config || {}),
      ...(localInitial.tib_config || {}),
    })
  );
  const [tibSections, setTibSections] = useState(() => ({
    ...(globalSettings.tib_sections || {}),
    ...(localInitial.tib_sections || {}),
  }));
  const [actionDefinitions, setActionDefinitions] = useState(() => ({
    ...(globalSettings.action_definitions || {}),
    ...(localInitial.action_definitions || {}),
  }));
  const [appConfigs, setAppConfigs] = useState(() => {
    const merged = {...(localInitial.applications || {})};
    Object.entries(applicationSettings || {}).forEach(([id, cfg]) => {
      merged[id] = {...(merged[id] || {}), ...(cfg || {})};
    });
    return merged;
  });

  const [selectedGlobalMenu, setSelectedGlobalMenu] = useState('applications');
  const [newCustomMenuName, setNewCustomMenuName] = useState('');
  const [selectedAppId, setSelectedAppId] = useState(
    () => applications[0]?.id || 'data-navigator'
  );
  const [selectedSectionId, setSelectedSectionId] = useState(
    () => STANDARD_TIB_SECTIONS[0]?.id || 'SEC-WORKSPACE'
  );
  const [selectedActionToAdd, setSelectedActionToAdd] = useState(
    EXTENDED_ACTION_CATALOG[0]?.id || 'shell.quick.new'
  );
  const [selectedQuickActionToAdd, setSelectedQuickActionToAdd] = useState('sql.execute');
  const [selectedTabIdx, setSelectedTabIdx] = useState(0);
  const [selectedGroupIdx, setSelectedGroupIdx] = useState(0);
  const [newTabLabel, setNewTabLabel] = useState('');
  const [newGroupLabel, setNewGroupLabel] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [scopeFilter, setScopeFilter] = useState('all');
  const [expandedActionId, setExpandedActionId] = useState(null);

  // Merge canonical catalog + any dynamic actions registered in `actionsRegistry`
  const allActions = useMemo(() => {
    const byId = new Map();
    EXTENDED_ACTION_CATALOG.forEach((item) => {
      byId.set(item.id, {...item});
    });
    if (typeof actionsRegistry?.list === 'function') {
      actionsRegistry.list().forEach((act) => {
        if (!act?.id) return;
        // Skip instance-suffixed duplicates (`foo.bar.sql-editor-1`, `ds.inst-1.commit`) in catalog picker
        if (/\.[a-z0-9-]+-\d+$/i.test(act.id) || /^(?:ds|sql-surf|designer\.cmd)\./i.test(act.id)) {
          return;
        }
        const existing = byId.get(act.id);
        if (existing) {
          byId.set(act.id, {
            ...existing,
            hint: existing.hint || act.defaultHint || act.hint || existing.label,
            shortcut: existing.shortcut || act.shortcut || '',
          });
          return;
        }
        byId.set(act.id, {
          id: act.id,
          label: act.defaultText || act.text || act.id,
          hint: act.defaultHint || act.hint || '',
          icon: act.icon || 'command.default',
          shortcut: act.shortcut || '',
          scope: act.application || 'global',
        });
      });
    }
    return [...byId.values()];
  }, [actionsRegistry]);

  const allScopes = useMemo(() => {
    const set = new Set();
    allActions.forEach((a) => {
      if (a.scope) set.add(a.scope);
    });
    return [...set].sort();
  }, [allActions]);

  const iconOptions = useMemo(() => {
    const defs = listIconDefinitions() || [];
    return defs.map((d) => ({
      value: d.key,
      label: `${d.label || d.key} (${d.key})`,
    }));
  }, []);

  const callableTargetOptions = useMemo(() => {
    const list =
      typeof actionsRegistry?.listCallableTargets === 'function'
        ? actionsRegistry.listCallableTargets()
        : CALLABLE_CODE_TARGETS;
    return list.map((entry) => ({
      value: entry.id,
      label: `${entry.label || entry.id} (${entry.id})`,
    }));
  }, [actionsRegistry]);

  const actionOptions = useMemo(
    () =>
      allActions.map((a) => ({
        value: a.id,
        label: `${actionDefinitions[a.id]?.text || a.label} [${a.scope}]`,
      })),
    [allActions, actionDefinitions]
  );

  const resolveActionMeta = (actionId) => {
    const found = allActions.find((a) => a.id === actionId);
    const def = actionDefinitions[actionId] || {};
    const assignedIcon = def.icon || iconAssignments[actionId];
    return {
      id: actionId,
      label: def.text || found?.label || actionId,
      hint: def.hint ?? found?.hint ?? found?.label ?? '',
      icon: assignedIcon || found?.icon || 'command.default',
      scope: found?.scope || 'global',
    };
  };

  const commitGlobalPlacements = (nextPatch = {}) => {
    const nextMenus = nextPatch.menuPlacements ?? menuPlacements;
    const nextQuick = nextPatch.quickAccess ?? quickAccess;
    const nextIcons = nextPatch.iconAssignments ?? iconAssignments;
    const nextTibConfig = normalizeTiBConfig(nextPatch.tibConfig ?? tibConfig);
    const nextTibSections = nextPatch.tibSections ?? tibSections;
    const nextActionDefs = nextPatch.actionDefinitions ?? actionDefinitions;

    setMenuPlacements(nextMenus);
    setQuickAccess(nextQuick);
    setIconAssignments(nextIcons);
    setTibConfig(nextTibConfig);
    setTibSections(nextTibSections);
    setActionDefinitions(nextActionDefs);

    actionsRegistry?.setActionDefinitions?.(nextActionDefs);

    const payload = {
      menu_placements: nextMenus,
      quick_access: nextQuick,
      icon_assignments: nextIcons,
      tib_config: nextTibConfig,
      tib_sections: nextTibSections,
      action_definitions: nextActionDefs,
    };
    writeLocalPlacements(payload);
    onChangeGlobal?.(payload);
  };

  const updateSingleActionDefinition = (actionId, fieldPatch) => {
    const prevDef = actionDefinitions[actionId] || {};
    const merged = {...prevDef, ...fieldPatch};
    Object.keys(merged).forEach((k) => {
      if (merged[k] === undefined) delete merged[k];
    });
    const nextDefs = {...actionDefinitions};
    if (Object.keys(merged).length === 0) {
      delete nextDefs[actionId];
    } else {
      nextDefs[actionId] = merged;
    }
    const nextIcons = {...iconAssignments};
    if (fieldPatch.icon !== undefined) {
      if (fieldPatch.icon) nextIcons[actionId] = fieldPatch.icon;
      else delete nextIcons[actionId];
    }
    if (fieldPatch.status && actionsRegistry?.has?.(actionId)) {
      actionsRegistry.setStatus?.(actionId, fieldPatch.status);
    }
    commitGlobalPlacements({
      actionDefinitions: nextDefs,
      iconAssignments: nextIcons,
    });
  };

  const resetSingleActionDefinition = (actionId) => {
    const nextDefs = {...actionDefinitions};
    delete nextDefs[actionId];
    const nextIcons = {...iconAssignments};
    delete nextIcons[actionId];
    if (actionsRegistry?.has?.(actionId)) {
      actionsRegistry.setStatus?.(actionId, 'enabled');
    }
    commitGlobalPlacements({
      actionDefinitions: nextDefs,
      iconAssignments: nextIcons,
    });
  };

  const commitAppPlacement = (targetAppId, patch) => {
    const prevApp = appConfigs[targetAppId] || {};
    const nextApp = {...prevApp, ...patch};
    const nextMap = {...appConfigs, [targetAppId]: nextApp};
    setAppConfigs(nextMap);

    const local = readLocalPlacements();
    writeLocalPlacements({
      applications: {
        ...(local.applications || {}),
        [targetAppId]: nextApp,
      },
    });
    onChangeApp?.(targetAppId, patch);
  };

  const subViewTabsBar = hideTabs ? null : (
    <div
      role="tablist"
      aria-label={gettext('Menus, Toolbars & Action Icons Sections')}
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 6,
        paddingBottom: 8,
        borderBottom: '1px solid var(--sr-border-subtle)',
      }}
    >
      {[
        ['global-menus', gettext('Global Top Menus')],
        ['app-menus', gettext('Application Menus')],
        ['iconbars', gettext('Tabbed-Notebook Iconbars')],
        ['tib-appearance', gettext('TiB Appearance')],
        ['icons', gettext('Actions & Code Targets')],
      ].map(([key, label]) => {
        const selected = activeSubView === key;
        return (
          <Button
            key={key}
            role="tab"
            aria-selected={selected}
            intent={selected ? 'primary' : 'neutral'}
            data-cdeadmin-qa-key={`actions-tab-${key}`}
            onClick={() => switchSubView(key)}
          >
            {label}
          </Button>
        );
      })}
    </div>
  );

  // -------------------------------------------------------------------------
  // Sub-view 1: Global Top Menu Bar (`Area 1`)
  // -------------------------------------------------------------------------
  if (activeSubView === 'global-menus') {
    const customMenus = Array.isArray(menuPlacements.__custom_menus)
      ? menuPlacements.__custom_menus
      : [];
    const allGlobalMenuSpecs = [
      ...BASELINE_GLOBAL_MENUS.map((m) => ({...m, builtin: true})),
      ...customMenus.map((cm) => ({
        name: cm.name,
        label: cm.label || cm.name,
        index: cm.index ?? 65,
        defaultItems: cm.actions || [],
        builtin: false,
      })),
    ];
    const activeSpec =
      allGlobalMenuSpecs.find((m) => m.name === selectedGlobalMenu) || allGlobalMenuSpecs[0];
    const cfg = menuPlacements[activeSpec.name] || {};
    const customEntry = customMenus.find((cm) => cm.name === activeSpec.name);

    const isVisible = activeSpec.builtin
      ? cfg.visible !== false
      : customEntry?.visible !== false;
    const displayLabel = activeSpec.builtin
      ? cfg.label ?? activeSpec.label
      : customEntry?.label ?? activeSpec.label;
    const displayIndex = activeSpec.builtin
      ? cfg.index ?? activeSpec.index
      : customEntry?.index ?? activeSpec.index;

    const placedItems = activeSpec.builtin
      ? [
        ...activeSpec.defaultItems.filter(
          (id) => !(cfg.hidden_items || []).includes(id)
        ),
        ...(cfg.added_actions || []),
      ]
      : [...(customEntry?.actions || [])];

    const orderedItems =
      Array.isArray(cfg.item_order) && cfg.item_order.length > 0 && activeSpec.builtin
        ? [...placedItems].sort((a, b) => {
          const ia = cfg.item_order.indexOf(a);
          const ib = cfg.item_order.indexOf(b);
          return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
        })
        : placedItems;

    const handleAddCustomMenu = () => {
      const label = newCustomMenuName.trim();
      if (!label) return;
      const slug = label.toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
      if (!slug || allGlobalMenuSpecs.some((m) => m.name === slug)) return;
      const nextCustom = [
        ...customMenus,
        {name: slug, label, index: 65, visible: true, actions: []},
      ];
      setNewCustomMenuName('');
      setSelectedGlobalMenu(slug);
      commitGlobalPlacements({
        menuPlacements: {...menuPlacements, __custom_menus: nextCustom},
      });
    };

    const handleAddActionToGlobalMenu = () => {
      if (!selectedActionToAdd) return;
      if (activeSpec.builtin) {
        const added = [...new Set([...(cfg.added_actions || []), selectedActionToAdd])];
        const hidden = (cfg.hidden_items || []).filter((id) => id !== selectedActionToAdd);
        commitGlobalPlacements({
          menuPlacements: {
            ...menuPlacements,
            [activeSpec.name]: {...cfg, added_actions: added, hidden_items: hidden},
          },
        });
      } else {
        const nextCustom = customMenus.map((cm) =>
          cm.name === activeSpec.name
            ? {...cm, actions: [...new Set([...(cm.actions || []), selectedActionToAdd])]}
            : cm
        );
        commitGlobalPlacements({
          menuPlacements: {...menuPlacements, __custom_menus: nextCustom},
        });
      }
    };

    const handleRemoveActionFromGlobalMenu = (actionId) => {
      if (activeSpec.builtin) {
        const isDefault = activeSpec.defaultItems.includes(actionId);
        const hidden = isDefault
          ? [...new Set([...(cfg.hidden_items || []), actionId])]
          : cfg.hidden_items || [];
        const added = (cfg.added_actions || []).filter((id) => id !== actionId);
        commitGlobalPlacements({
          menuPlacements: {
            ...menuPlacements,
            [activeSpec.name]: {...cfg, added_actions: added, hidden_items: hidden},
          },
        });
      } else {
        const nextCustom = customMenus.map((cm) =>
          cm.name === activeSpec.name
            ? {...cm, actions: (cm.actions || []).filter((id) => id !== actionId)}
            : cm
        );
        commitGlobalPlacements({
          menuPlacements: {...menuPlacements, __custom_menus: nextCustom},
        });
      }
    };

    const handleMoveGlobalItem = (idx, dir) => {
      const targetIdx = idx + dir;
      if (targetIdx < 0 || targetIdx >= orderedItems.length) return;
      const nextOrder = [...orderedItems];
      const [moved] = nextOrder.splice(idx, 1);
      nextOrder.splice(targetIdx, 0, moved);
      if (activeSpec.builtin) {
        commitGlobalPlacements({
          menuPlacements: {
            ...menuPlacements,
            [activeSpec.name]: {...cfg, item_order: nextOrder},
          },
        });
      } else {
        const nextCustom = customMenus.map((cm) =>
          cm.name === activeSpec.name ? {...cm, actions: nextOrder} : cm
        );
        commitGlobalPlacements({
          menuPlacements: {...menuPlacements, __custom_menus: nextCustom},
        });
      }
    };

    return (
      <div
        data-cdeadmin-qa-key="settings-global-menus-editor"
        style={{display: 'flex', flexDirection: 'column', gap: 12}}
      >
        {subViewTabsBar}
        <div>
          <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
            {gettext('Global Top Menu Bar Editor (Area 1)')}
          </div>
          <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
            {gettext(
              'Customize top-level menus, create custom global menus, and place actions with icons onto Area 1.'
            )}
          </div>
        </div>

        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8, alignItems: 'end'}}>
          <Select
            label={gettext('Select Top-Level Menu')}
            value={activeSpec.name}
            options={allGlobalMenuSpecs.map((m) => ({
              value: m.name,
              label: `${m.label} (pos ${m.index})`,
            }))}
            onChange={(val) => val && setSelectedGlobalMenu(val)}
          />
          <TextField
            label={gettext('Create Custom Global Menu')}
            placeholder="e.g. Favorites or DBA Tools"
            value={newCustomMenuName}
            inputProps={{'data-cdeadmin-qa-key': 'global-menu-new-name'}}
            onChange={(e) => setNewCustomMenuName(e.target.value)}
          />
          <Button
            intent="neutral"
            data-cdeadmin-qa-key="global-menu-add-custom"
            onClick={handleAddCustomMenu}
          >
            {gettext('+ Add Menu')}
          </Button>
        </div>

        <div
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{display: 'grid', gridTemplateColumns: '1fr 140px auto', gap: 10, alignItems: 'center'}}>
            <TextField
              label={gettext('Menu Label')}
              value={displayLabel}
              onChange={(e) => {
                const val = e.target.value;
                if (activeSpec.builtin) {
                  commitGlobalPlacements({
                    menuPlacements: {
                      ...menuPlacements,
                      [activeSpec.name]: {...cfg, label: val},
                    },
                  });
                } else {
                  commitGlobalPlacements({
                    menuPlacements: {
                      ...menuPlacements,
                      __custom_menus: customMenus.map((cm) =>
                        cm.name === activeSpec.name ? {...cm, label: val} : cm
                      ),
                    },
                  });
                }
              }}
            />
            <NumberField
              label={gettext('Position Index')}
              min={1}
              max={99}
              value={displayIndex}
              onChange={(e) => {
                const idxVal = Math.max(1, Number(e.target.value) || activeSpec.index);
                if (activeSpec.builtin) {
                  commitGlobalPlacements({
                    menuPlacements: {
                      ...menuPlacements,
                      [activeSpec.name]: {...cfg, index: idxVal},
                    },
                  });
                } else {
                  commitGlobalPlacements({
                    menuPlacements: {
                      ...menuPlacements,
                      __custom_menus: customMenus.map((cm) =>
                        cm.name === activeSpec.name ? {...cm, index: idxVal} : cm
                      ),
                    },
                  });
                }
              }}
            />
            <div style={{paddingTop: 18}}>
              <Switch
                label={gettext('Visible')}
                checked={isVisible}
                onChange={(checked) => {
                  if (activeSpec.builtin) {
                    commitGlobalPlacements({
                      menuPlacements: {
                        ...menuPlacements,
                        [activeSpec.name]: {...cfg, visible: Boolean(checked)},
                      },
                    });
                  } else {
                    commitGlobalPlacements({
                      menuPlacements: {
                        ...menuPlacements,
                        __custom_menus: customMenus.map((cm) =>
                          cm.name === activeSpec.name ? {...cm, visible: Boolean(checked)} : cm
                        ),
                      },
                    });
                  }
                }}
              />
            </div>
          </div>

          <div style={{display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'end'}}>
            <Select
              label={gettext('Place Action onto "%s" Menu', displayLabel)}
              value={selectedActionToAdd}
              options={actionOptions}
              onChange={(val) => val && setSelectedActionToAdd(val)}
            />
            <Button
              intent="primary"
              data-cdeadmin-qa-key="global-menu-place-action"
              onClick={handleAddActionToGlobalMenu}
            >
              {gettext('+ Place Action')}
            </Button>
          </div>

          <div className="sr-bui-table-card" style={{padding: 8}}>
            <div style={{fontSize: '0.75rem', fontWeight: 700, marginBottom: 6}}>
              {gettext('Items Currently Placed on "%s"', displayLabel)}
            </div>
            {orderedItems.length === 0 ? (
              <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)', padding: 6}}>
                {gettext('No items placed on this menu yet.')}
              </div>
            ) : (
              <div style={{display: 'flex', flexDirection: 'column', gap: 4}}>
                {orderedItems.map((actionId, idx) => {
                  const meta = resolveActionMeta(actionId);
                  return (
                    <div
                      key={actionId}
                      data-cdeadmin-qa-key={`global-menu-item-${actionId}`}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '5px 8px',
                        borderRadius: 6,
                        background: 'var(--sr-surface-card)',
                        border: '1px solid var(--sr-border-subtle)',
                      }}
                    >
                      <span style={{display: 'inline-flex', alignItems: 'center', gap: 8}}>
                        <Icon iconKey={meta.icon} decorative size="15px" />
                        <span style={{fontWeight: 600, fontSize: '0.8rem'}}>{meta.label}</span>
                        <code style={{fontSize: '0.7rem', color: 'var(--sr-text-secondary)'}}>
                          {meta.id}
                        </code>
                      </span>
                      <span style={{display: 'inline-flex', gap: 4}}>
                        <Button
                          intent="neutral"
                          disabled={idx === 0}
                          onClick={() => handleMoveGlobalItem(idx, -1)}
                        >
                          ↑
                        </Button>
                        <Button
                          intent="neutral"
                          disabled={idx === orderedItems.length - 1}
                          onClick={() => handleMoveGlobalItem(idx, 1)}
                        >
                          ↓
                        </Button>
                        <Button
                          intent="danger"
                          data-cdeadmin-qa-key={`global-menu-remove-${actionId}`}
                          onClick={() => handleRemoveActionFromGlobalMenu(actionId)}
                        >
                          {gettext('Remove')}
                        </Button>
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Sub-view 2: Application Menus (`Area 1` Dynamic Focused Menus)
  // -------------------------------------------------------------------------
  if (activeSubView === 'app-menus') {
    const surface =
      CANONICAL_APPLICATION_SURFACES[selectedAppId] ||
      CANONICAL_APPLICATION_SURFACES['data-navigator'];
    const appCfg = appConfigs[selectedAppId] || {};
    const appMenuPlacements = appCfg.menu_placements || {};
    const menuCfg = appMenuPlacements[surface.menuName] || {};

    const items = [
      ...surface.defaultMenuActions.filter(
        (id) => !(menuCfg.hidden_items || []).includes(id)
      ),
      ...(menuCfg.added_actions || []),
    ];

    const saveAppMenuCfg = (nextMenuCfg) => {
      commitAppPlacement(selectedAppId, {
        menu_placements: {
          ...appMenuPlacements,
          [surface.menuName]: nextMenuCfg,
        },
      });
    };

    return (
      <div
        data-cdeadmin-qa-key="settings-app-menus-editor"
        style={{display: 'flex', flexDirection: 'column', gap: 12}}
      >
        {subViewTabsBar}
        <div>
          <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
            {gettext('Application Top Menus Editor (Area 1 Dynamic Menus)')}
          </div>
          <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
            {gettext(
              'Configure the dynamic top menu contributed when an application is focused.'
            )}
          </div>
        </div>

        <Select
          label={gettext('Application')}
          value={selectedAppId}
          options={(applications.length
            ? applications
            : [{id: 'data-navigator', label: 'Data Navigator'}]
          ).map((a) => ({value: a.id, label: a.label || a.id}))}
          onChange={(val) => val && setSelectedAppId(val)}
        />

        <div
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{display: 'grid', gridTemplateColumns: '1fr 140px', gap: 10}}>
            <TextField
              label={gettext('Dynamic Menu Title')}
              value={menuCfg.label ?? surface.menuLabel}
              onChange={(e) => saveAppMenuCfg({...menuCfg, label: e.target.value})}
            />
            <NumberField
              label={gettext('Menu Bar Position')}
              min={1}
              max={59}
              value={menuCfg.index ?? surface.menuIndex}
              onChange={(e) =>
                saveAppMenuCfg({...menuCfg, index: Number(e.target.value) || surface.menuIndex})
              }
            />
          </div>

          <div style={{display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'end'}}>
            <Select
              label={gettext('Add Action to "%s" Menu', menuCfg.label || surface.menuLabel)}
              value={selectedActionToAdd}
              options={actionOptions}
              onChange={(val) => val && setSelectedActionToAdd(val)}
            />
            <Button
              intent="primary"
              data-cdeadmin-qa-key="app-menu-place-action"
              onClick={() => {
                const added = [...new Set([...(menuCfg.added_actions || []), selectedActionToAdd])];
                const hidden = (menuCfg.hidden_items || []).filter(
                  (id) => id !== selectedActionToAdd
                );
                saveAppMenuCfg({...menuCfg, added_actions: added, hidden_items: hidden});
              }}
            >
              {gettext('+ Place Action')}
            </Button>
          </div>

          <div style={{display: 'flex', flexDirection: 'column', gap: 4}}>
            {items.map((actionId) => {
              const meta = resolveActionMeta(actionId);
              return (
                <div
                  key={actionId}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '5px 8px',
                    borderRadius: 6,
                    background: 'var(--sr-surface-card)',
                    border: '1px solid var(--sr-border-subtle)',
                  }}
                >
                  <span style={{display: 'inline-flex', alignItems: 'center', gap: 8}}>
                    <Icon iconKey={meta.icon} decorative size="15px" />
                    <span style={{fontWeight: 600, fontSize: '0.8rem'}}>{meta.label}</span>
                    <code style={{fontSize: '0.7rem', color: 'var(--sr-text-secondary)'}}>
                      {meta.id}
                    </code>
                  </span>
                  <Button
                    intent="danger"
                    onClick={() => {
                      const isDef = surface.defaultMenuActions.includes(actionId);
                      const hidden = isDef
                        ? [...new Set([...(menuCfg.hidden_items || []), actionId])]
                        : menuCfg.hidden_items || [];
                      const added = (menuCfg.added_actions || []).filter((id) => id !== actionId);
                      saveAppMenuCfg({...menuCfg, added_actions: added, hidden_items: hidden});
                    }}
                  >
                    {gettext('Remove')}
                  </Button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Sub-view 3: Tabbed-Notebook Iconbars (`Area 3b`, `3b1` & 26 Standard Sections)
  // -------------------------------------------------------------------------
  if (activeSubView === 'iconbars') {
    const surface =
      CANONICAL_APPLICATION_SURFACES[selectedAppId] ||
      CANONICAL_APPLICATION_SURFACES['data-navigator'];
    const appCfg = appConfigs[selectedAppId] || {};
    const tabs =
      Array.isArray(appCfg.notebookbar_placements?.tabs) &&
      appCfg.notebookbar_placements.tabs.length > 0
        ? cloneTabs(appCfg.notebookbar_placements.tabs)
        : cloneTabs(surface.defaultTabs);

    const safeTabIdx = Math.min(selectedTabIdx, Math.max(0, tabs.length - 1));
    const currentTab = tabs[safeTabIdx] || {id: 'default', label: 'Commands', groups: []};
    const safeGroupIdx = Math.min(
      selectedGroupIdx,
      Math.max(0, (currentTab.groups || []).length - 1)
    );
    const currentGroup = currentTab.groups?.[safeGroupIdx] || null;

    const saveTabs = (nextTabs) => {
      commitAppPlacement(selectedAppId, {
        notebookbar_placements: {tabs: nextTabs},
      });
    };

    const stdSection =
      STANDARD_TIB_SECTIONS.find((s) => s.id === selectedSectionId) || STANDARD_TIB_SECTIONS[0];
    const secOverride = tibSections[stdSection.id] || {};
    const saveSectionOverride = (patch) => {
      const merged = {...secOverride, ...patch};
      const nextSections = {...tibSections, [stdSection.id]: merged};
      commitGlobalPlacements({tibSections: nextSections});
    };
    const resetSectionOverride = () => {
      const nextSections = {...tibSections};
      delete nextSections[stdSection.id];
      commitGlobalPlacements({tibSections: nextSections});
    };

    return (
      <div
        data-cdeadmin-qa-key="settings-iconbars-editor"
        style={{display: 'flex', flexDirection: 'column', gap: 14}}
      >
        {subViewTabsBar}
        <div>
          <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
            {gettext('Tabbed-Notebook Iconbars & Shared Standard Sections (Area 3b & 3b1)')}
          </div>
          <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
            {gettext(
              'Configure the 3b1 Quick-Access strip, edit any of the 26 shared Standard Sections once for all worksurfaces, or customize per-worksurface sub-tabs.'
            )}
          </div>
        </div>

        {/* 3b1 Quick Access Strip */}
        <div
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}
        >
          <div style={{fontWeight: 700, fontSize: '0.82rem'}}>
            {gettext('Area 3b1 — Global Quick-Access Icon Strip')}
          </div>
          <div style={{display: 'flex', flexWrap: 'wrap', gap: 6}}>
            {quickAccess.map((actionId, idx) => {
              const meta = resolveActionMeta(actionId);
              return (
                <span
                  key={actionId}
                  data-cdeadmin-qa-key={`quick-access-chip-${actionId}`}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '4px 8px',
                    borderRadius: 8,
                    background: 'var(--sr-surface-card)',
                    border: '1px solid var(--sr-border-default)',
                    fontSize: '0.78rem',
                  }}
                >
                  <Icon iconKey={meta.icon} decorative size="15px" />
                  <span>{meta.label}</span>
                  {idx > 0 && (
                    <button
                      type="button"
                      aria-label={`Move ${meta.label} left`}
                      onClick={() => {
                        const next = [...quickAccess];
                        const [m] = next.splice(idx, 1);
                        next.splice(idx - 1, 0, m);
                        commitGlobalPlacements({quickAccess: next});
                      }}
                      style={{border: 'none', background: 'transparent', cursor: 'pointer', color: 'inherit'}}
                    >
                      ←
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label={`Remove ${meta.label} from Quick Access`}
                    onClick={() =>
                      commitGlobalPlacements({
                        quickAccess: quickAccess.filter((id) => id !== actionId),
                      })
                    }
                    style={{border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--sr-danger, #c92a2a)'}}
                  >
                    ×
                  </button>
                </span>
              );
            })}
          </div>
          <div style={{display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'end'}}>
            <Select
              label={gettext('Add Icon to 3b1 Quick-Access Strip')}
              value={selectedQuickActionToAdd}
              options={actionOptions}
              onChange={(val) => val && setSelectedQuickActionToAdd(val)}
            />
            <Button
              intent="neutral"
              data-cdeadmin-qa-key="quick-access-add-icon"
              onClick={() => {
                if (!selectedQuickActionToAdd) return;
                commitGlobalPlacements({
                  quickAccess: [...new Set([...quickAccess, selectedQuickActionToAdd])],
                });
              }}
            >
              {gettext('+ Add to 3b1')}
            </Button>
          </div>
        </div>

        {/* Global Shared Standard TiB Sections (26 Sections — Single Edit Updates All Worksurfaces) */}
        <div
          data-cdeadmin-qa-key="tib-standard-sections-editor"
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8}}>
            <div>
              <div style={{fontWeight: 700, fontSize: '0.84rem'}}>
                {gettext('Global Standard TiB Sections (26 Shared Sections)')}
              </div>
              <div style={{fontSize: '0.75rem', color: 'var(--sr-text-secondary)'}}>
                {gettext(
                  'Modifying a standard section here updates its title, header icon, visibility, and extra buttons on every worksurface that mounts it.'
                )}
              </div>
            </div>
            <Button
              intent="neutral"
              data-cdeadmin-qa-key="tib-section-reset"
              onClick={resetSectionOverride}
            >
              {gettext('Reset Section')}
            </Button>
          </div>

          <Select
            label={gettext('Standard Section')}
            value={stdSection.id}
            options={STANDARD_TIB_SECTIONS.map((s) => ({
              value: s.id,
              label: `${s.id} — ${secOverride?.id === s.id ? secOverride.label || s.title : tibSections[s.id]?.label || s.title} (${s.usedBy})`,
            }))}
            onChange={(val) => val && setSelectedSectionId(val)}
          />

          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 10, alignItems: 'center'}}>
            <TextField
              label={gettext('Section Footer Title')}
              value={secOverride.label ?? stdSection.title}
              inputProps={{'data-cdeadmin-qa-key': 'tib-section-title-input'}}
              onChange={(e) => saveSectionOverride({label: e.target.value})}
            />
            <Select
              label={gettext('Section Header Icon (14×14)')}
              value={secOverride.sectionIcon || stdSection.sectionIcon}
              options={iconOptions}
              onChange={(val) => val && saveSectionOverride({sectionIcon: val})}
            />
            <div style={{paddingTop: 18}}>
              <Switch
                label={gettext('Visible')}
                checked={secOverride.hidden !== true}
                onChange={(checked) => saveSectionOverride({hidden: !checked})}
              />
            </div>
          </div>

          <div style={{display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 8, alignItems: 'end'}}>
            <Select
              label={gettext('Add Extra Action to "%s" Across All Worksurfaces', secOverride.label || stdSection.title)}
              value={selectedActionToAdd}
              options={actionOptions}
              onChange={(val) => val && setSelectedActionToAdd(val)}
            />
            <Button
              intent="neutral"
              data-cdeadmin-qa-key="tib-section-add-hero"
              onClick={() => {
                if (!selectedActionToAdd) return;
                const list = [...new Set([...(secOverride.added_hero_actions || []), selectedActionToAdd])];
                saveSectionOverride({added_hero_actions: list});
              }}
            >
              {gettext('+ Add Hero (42×42)')}
            </Button>
            <Button
              intent="primary"
              data-cdeadmin-qa-key="tib-section-add-grid"
              onClick={() => {
                if (!selectedActionToAdd) return;
                const list = [...new Set([...(secOverride.added_grid_actions || []), selectedActionToAdd])];
                saveSectionOverride({added_grid_actions: list});
              }}
            >
              {gettext('+ Add Grid (20×20)')}
            </Button>
          </div>

          {((secOverride.added_hero_actions || []).length > 0 ||
            (secOverride.added_grid_actions || []).length > 0) && (
            <div style={{display: 'flex', flexWrap: 'wrap', gap: 6}}>
              {(secOverride.added_hero_actions || []).map((aid) => {
                const meta = resolveActionMeta(aid);
                return (
                  <span
                    key={`hero-${aid}`}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '3px 8px',
                      borderRadius: 6,
                      background: 'var(--sr-surface-card)',
                      border: '1px solid var(--sr-border-default)',
                      fontSize: '0.75rem',
                    }}
                  >
                    <Icon iconKey={meta.icon} decorative size="14px" />
                    <span>{meta.label} (Hero)</span>
                    <button
                      type="button"
                      aria-label={`Remove ${meta.label}`}
                      onClick={() =>
                        saveSectionOverride({
                          added_hero_actions: (secOverride.added_hero_actions || []).filter(
                            (x) => x !== aid
                          ),
                        })
                      }
                      style={{border: 'none', background: 'transparent', cursor: 'pointer'}}
                    >
                      ×
                    </button>
                  </span>
                );
              })}
              {(secOverride.added_grid_actions || []).map((aid) => {
                const meta = resolveActionMeta(aid);
                return (
                  <span
                    key={`grid-${aid}`}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '3px 8px',
                      borderRadius: 6,
                      background: 'var(--sr-surface-card)',
                      border: '1px solid var(--sr-border-default)',
                      fontSize: '0.75rem',
                    }}
                  >
                    <Icon iconKey={meta.icon} decorative size="14px" />
                    <span>{meta.label} (Grid)</span>
                    <button
                      type="button"
                      aria-label={`Remove ${meta.label}`}
                      onClick={() =>
                        saveSectionOverride({
                          added_grid_actions: (secOverride.added_grid_actions || []).filter(
                            (x) => x !== aid
                          ),
                        })
                      }
                      style={{border: 'none', background: 'transparent', cursor: 'pointer'}}
                    >
                      ×
                    </button>
                  </span>
                );
              })}
            </div>
          )}
        </div>

        {/* 3b Application Tabbed-Notebook-Iconbar */}
        <div
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: 8}}>
            <Select
              label={gettext('Application Tabbed-Notebook-Iconbar (Area 3b)')}
              value={selectedAppId}
              style={{flex: 1}}
              options={(applications.length
                ? applications
                : [{id: 'data-navigator', label: 'Data Navigator'}]
              ).map((a) => ({value: a.id, label: a.label || a.id}))}
              onChange={(val) => {
                if (!val) return;
                setSelectedAppId(val);
                setSelectedTabIdx(0);
                setSelectedGroupIdx(0);
              }}
            />
            <Button
              intent="neutral"
              data-cdeadmin-qa-key="iconbar-reset-app"
              onClick={() => commitAppPlacement(selectedAppId, {notebookbar_placements: null})}
            >
              {gettext('Reset to Default Bar')}
            </Button>
          </div>

          {/* Sub-Tabs strip */}
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8, alignItems: 'end'}}>
            <Select
              label={gettext('Worksurface Sub-Tab')}
              value={String(safeTabIdx)}
              options={tabs.map((t, idx) => ({value: String(idx), label: t.label}))}
              onChange={(val) => {
                setSelectedTabIdx(Number(val) || 0);
                setSelectedGroupIdx(0);
              }}
            />
            <TextField
              label={gettext('New Sub-Tab Title')}
              placeholder="e.g. Custom Tools"
              value={newTabLabel}
              onChange={(e) => setNewTabLabel(e.target.value)}
            />
            <Button
              intent="neutral"
              data-cdeadmin-qa-key="iconbar-add-tab"
              onClick={() => {
                const label = newTabLabel.trim();
                if (!label) return;
                const nextTabs = [
                  ...tabs,
                  {
                    id: `tab-${Date.now().toString(36)}`,
                    label,
                    groups: [{id: 'main', label: 'Tools', actions: []}],
                  },
                ];
                setNewTabLabel('');
                setSelectedTabIdx(nextTabs.length - 1);
                setSelectedGroupIdx(0);
                saveTabs(nextTabs);
              }}
            >
              {gettext('+ Add Tab')}
            </Button>
          </div>

          {/* Group selector + add group */}
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8, alignItems: 'end'}}>
            <Select
              label={gettext('Section inside "%s"', currentTab.label)}
              value={String(safeGroupIdx)}
              options={(currentTab.groups || []).map((g, idx) => ({
                value: String(idx),
                label: g.label,
              }))}
              onChange={(val) => setSelectedGroupIdx(Number(val) || 0)}
            />
            <TextField
              label={gettext('New Section Label')}
              placeholder="e.g. Export"
              value={newGroupLabel}
              onChange={(e) => setNewGroupLabel(e.target.value)}
            />
            <Button
              intent="neutral"
              onClick={() => {
                const label = newGroupLabel.trim();
                if (!label) return;
                const nextTabs = cloneTabs(tabs);
                nextTabs[safeTabIdx].groups.push({
                  id: `grp-${Date.now().toString(36)}`,
                  label,
                  actions: [],
                });
                setNewGroupLabel('');
                setSelectedGroupIdx(nextTabs[safeTabIdx].groups.length - 1);
                saveTabs(nextTabs);
              }}
            >
              {gettext('+ Add Group')}
            </Button>
          </div>

          {/* Place icon into group */}
          {currentGroup && (
            <>
              <div style={{display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'end'}}>
                <Select
                  label={gettext('Place Icon into "%s › %s"', currentTab.label, currentGroup.label)}
                  value={selectedActionToAdd}
                  options={actionOptions}
                  onChange={(val) => val && setSelectedActionToAdd(val)}
                />
                <Button
                  intent="primary"
                  data-cdeadmin-qa-key="iconbar-place-action"
                  onClick={() => {
                    const nextTabs = cloneTabs(tabs);
                    const grp = nextTabs[safeTabIdx].groups[safeGroupIdx];
                    if (!grp.actions.includes(selectedActionToAdd)) {
                      grp.actions.push(selectedActionToAdd);
                      saveTabs(nextTabs);
                    }
                  }}
                >
                  {gettext('+ Place Icon')}
                </Button>
              </div>

              <div style={{display: 'flex', flexDirection: 'column', gap: 4}}>
                {currentGroup.actions.map((actionId, idx) => {
                  const meta = resolveActionMeta(actionId);
                  return (
                    <div
                      key={actionId}
                      data-cdeadmin-qa-key={`iconbar-item-${actionId}`}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '5px 8px',
                        borderRadius: 6,
                        background: 'var(--sr-surface-card)',
                        border: '1px solid var(--sr-border-subtle)',
                      }}
                    >
                      <span style={{display: 'inline-flex', alignItems: 'center', gap: 8}}>
                        <Icon iconKey={meta.icon} decorative size="16px" />
                        <span style={{fontWeight: 600, fontSize: '0.8rem'}}>{meta.label}</span>
                        <code style={{fontSize: '0.7rem', color: 'var(--sr-text-secondary)'}}>
                          {meta.id}
                        </code>
                      </span>
                      <span style={{display: 'inline-flex', gap: 4}}>
                        <Button
                          intent="neutral"
                          disabled={idx === 0}
                          onClick={() => {
                            const nextTabs = cloneTabs(tabs);
                            const arr = nextTabs[safeTabIdx].groups[safeGroupIdx].actions;
                            const [m] = arr.splice(idx, 1);
                            arr.splice(idx - 1, 0, m);
                            saveTabs(nextTabs);
                          }}
                        >
                          ↑
                        </Button>
                        <Button
                          intent="neutral"
                          disabled={idx === currentGroup.actions.length - 1}
                          onClick={() => {
                            const nextTabs = cloneTabs(tabs);
                            const arr = nextTabs[safeTabIdx].groups[safeGroupIdx].actions;
                            const [m] = arr.splice(idx, 1);
                            arr.splice(idx + 1, 0, m);
                            saveTabs(nextTabs);
                          }}
                        >
                          ↓
                        </Button>
                        <Button
                          intent="danger"
                          onClick={() => {
                            const nextTabs = cloneTabs(tabs);
                            nextTabs[safeTabIdx].groups[safeGroupIdx].actions =
                              currentGroup.actions.filter((id) => id !== actionId);
                            saveTabs(nextTabs);
                          }}
                        >
                          {gettext('Remove')}
                        </Button>
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Sub-view 4: Global TiB Appearance, Visibility & Geometry (`tib-appearance`)
  // -------------------------------------------------------------------------
  if (activeSubView === 'tib-appearance') {
    const updateTibCfg = (patch) => {
      commitGlobalPlacements({tibConfig: {...tibConfig, ...patch}});
    };

    const customPal = tibConfig.custom_palette || DEFAULT_TIB_PALETTE_LIGHT;
    const updateCustomColor = (key, val) => {
      updateTibCfg({
        palette_mode: 'custom',
        custom_palette: {...customPal, [key]: val},
      });
    };

    return (
      <div
        data-cdeadmin-qa-key="settings-tib-appearance-editor"
        style={{display: 'flex', flexDirection: 'column', gap: 14}}
      >
        {subViewTabsBar}
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10}}>
          <div>
            <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
              {gettext('Global Tabbed-Icon-Bar (TiB) Appearance & Geometry')}
            </div>
            <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
              {gettext(
                'Every setting on this page applies immediately to all Tabbed-Icon-Bar instances across all 13 worksurfaces.'
              )}
            </div>
          </div>
          <Button
            intent="neutral"
            data-cdeadmin-qa-key="tib-reset-defaults"
            onClick={() => commitGlobalPlacements({tibConfig: {...DEFAULT_TIB_CONFIG}})}
          >
            {gettext('Reset TiB Defaults')}
          </Button>
        </div>

        {/* Sub-Tab & Element Visibility */}
        <div
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{fontWeight: 700, fontSize: '0.82rem'}}>
            {gettext('Sub-Tab Strip & Structural Elements')}
          </div>
          <Select
            label={gettext('Sub-Tab Bar Visibility')}
            aria-label={gettext('Sub-Tab Bar Visibility')}
            value={tibConfig.subtab_visibility}
            options={[
              {
                value: 'multi_only',
                label: gettext('Hide sub-tab bar when worksurface has only 1 sub-tab (Default)'),
              },
              {
                value: 'always',
                label: gettext('Always show sub-tab bar (even for single sub-tab)'),
              },
              {
                value: 'hidden',
                label: gettext('Always hide sub-tab bar'),
              },
            ]}
            onChange={(val) => val && updateTibCfg({subtab_visibility: val})}
          />

          <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 10}}>
            <Switch
              label={gettext('Show Quick-Access Strip (3b1)')}
              checked={tibConfig.show_quick_access}
              onChange={(checked) => updateTibCfg({show_quick_access: Boolean(checked)})}
            />
            <Switch
              label={gettext('Show Section Footer Headers')}
              checked={tibConfig.show_section_headers}
              onChange={(checked) => updateTibCfg({show_section_headers: Boolean(checked)})}
            />
            <Switch
              label={gettext('Show Section Header Icons (14×14)')}
              checked={tibConfig.show_section_icons}
              onChange={(checked) => updateTibCfg({show_section_icons: Boolean(checked)})}
            />
            <Switch
              label={gettext('Show Cluster Dividers')}
              checked={tibConfig.show_cluster_dividers}
              onChange={(checked) => updateTibCfg({show_cluster_dividers: Boolean(checked)})}
            />
            <Switch
              label={gettext('Show Hover Tooltip Hints')}
              checked={tibConfig.show_hover_hints}
              onChange={(checked) => updateTibCfg({show_hover_hints: Boolean(checked)})}
            />
          </div>
        </div>

        {/* Dimensions & Geometry */}
        <div
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{fontWeight: 700, fontSize: '0.82rem'}}>
            {gettext('Section Card & Button Geometry')}
          </div>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10}}>
            <NumberField
              label={gettext('Section Height (px)')}
              min={56}
              max={124}
              value={tibConfig.section_height_px}
              inputProps={{'data-cdeadmin-qa-key': 'tib-section-height-px'}}
              onChange={(e) => updateTibCfg({section_height_px: Number(e.target.value) || 82})}
            />
            <NumberField
              label={gettext('Hero Button Size (px)')}
              min={28}
              max={64}
              value={tibConfig.hero_button_px}
              inputProps={{'data-cdeadmin-qa-key': 'tib-hero-button-px'}}
              onChange={(e) => updateTibCfg({hero_button_px: Number(e.target.value) || 42})}
            />
            <NumberField
              label={gettext('Hero Icon Size (px)')}
              min={16}
              max={44}
              value={tibConfig.hero_icon_px}
              onChange={(e) => updateTibCfg({hero_icon_px: Number(e.target.value) || 28})}
            />
            <NumberField
              label={gettext('Grid Button Size (px)')}
              min={16}
              max={32}
              value={tibConfig.grid_button_px}
              inputProps={{'data-cdeadmin-qa-key': 'tib-grid-button-px'}}
              onChange={(e) => updateTibCfg({grid_button_px: Number(e.target.value) || 20})}
            />
            <NumberField
              label={gettext('Grid Icon Size (px)')}
              min={12}
              max={24}
              value={tibConfig.grid_icon_px}
              onChange={(e) => updateTibCfg({grid_icon_px: Number(e.target.value) || 16})}
            />
            <NumberField
              label={gettext('Grid Gap (px)')}
              min={1}
              max={8}
              value={tibConfig.grid_gap_px}
              onChange={(e) => updateTibCfg({grid_gap_px: Number(e.target.value) || 2})}
            />
            <NumberField
              label={gettext('Section Gap (px)')}
              min={2}
              max={20}
              value={tibConfig.section_gap_px}
              onChange={(e) => updateTibCfg({section_gap_px: Number(e.target.value) || 8})}
            />
            <NumberField
              label={gettext('Section Radius (px)')}
              min={0}
              max={14}
              step={0.5}
              value={tibConfig.section_radius_px}
              onChange={(e) => updateTibCfg({section_radius_px: Number(e.target.value) || 0})}
            />
            <NumberField
              label={gettext('Button Radius (px)')}
              min={0}
              max={12}
              step={0.5}
              value={tibConfig.button_radius_px}
              onChange={(e) => updateTibCfg({button_radius_px: Number(e.target.value) || 0})}
            />
          </div>
        </div>

        {/* Palette & Three-Tone Icon Colours */}
        <div
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <Select
            label={gettext('TiB Card & Three-Tone Icon Palette')}
            value={tibConfig.palette_mode}
            options={[
              {value: 'theme', label: gettext('Follow Active Workbench Colour Theme (Default)')},
              {value: 'custom', label: gettext('Custom TiB Card & Three-Tone Icon Palette')},
            ]}
            onChange={(val) => val && updateTibCfg({palette_mode: val})}
          />
          {tibConfig.palette_mode === 'custom' && (
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10}}>
              {[
                ['section_bg', gettext('Section Background')],
                ['section_border', gettext('Section Border')],
                ['footer_fg', gettext('Section Header Text')],
                ['button_bg', gettext('Button Fill')],
                ['button_border', gettext('Button Border')],
                ['button_checked_bg', gettext('Active Button Fill')],
                ['icon_primary', gettext('Icon Primary Ink')],
                ['icon_secondary', gettext('Icon Secondary Tone')],
                ['icon_accent', gettext('Icon Semantic Accent')],
              ].map(([key, labelText]) => (
                <TextField
                  key={key}
                  label={labelText}
                  value={customPal[key] || ''}
                  inputProps={{'data-cdeadmin-qa-key': `tib-color-${key}`}}
                  onChange={(e) => updateCustomColor(key, e.target.value)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Sub-view 5: Unified Actions Registry (`icons` — Text, Icon, Hint, Status & Target Code)
  // -------------------------------------------------------------------------
  const filteredActions = allActions.filter((a) => {
    if (scopeFilter !== 'all' && a.scope !== scopeFilter) return false;
    const q = actionFilter.trim().toLowerCase();
    if (!q) return true;
    const def = actionDefinitions[a.id] || {};
    return `${a.id} ${def.text || a.label} ${def.hint || a.hint || ''} ${a.scope} ${a.sectionId || ''}`
      .toLowerCase()
      .includes(q);
  });

  return (
    <div
      data-cdeadmin-qa-key="settings-action-icons-editor"
      style={{display: 'flex', flexDirection: 'column', gap: 12}}
    >
      {subViewTabsBar}
      <div>
        <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
          {gettext('Actions Registry — Text, Icons, Hints, Status & Callable Code Targets')}
        </div>
        <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
          {gettext(
            'Adjust the label text, icon, hover hint, tri-state visibility (Enabled / Disabled / Invisible), and callable client handler or server endpoint for any button action from one place.'
          )}
        </div>
      </div>

      <div style={{display: 'grid', gridTemplateColumns: '1fr 220px', gap: 8, alignItems: 'end'}}>
        <SearchField
          label={gettext('Filter actions (%s shown)', filteredActions.length)}
          placeholder={gettext('Search by action ID, text, hint, section, or worksurface…')}
          value={actionFilter}
          onChange={setActionFilter}
        />
        <Select
          label={gettext('Scope')}
          value={scopeFilter}
          options={[
            {value: 'all', label: gettext('All Worksurfaces & Scopes')},
            ...allScopes.map((sc) => ({value: sc, label: sc})),
          ]}
          onChange={(val) => val && setScopeFilter(val)}
        />
      </div>

      <div style={{display: 'flex', flexDirection: 'column', gap: 6}}>
        {filteredActions.map((act) => {
          const def = actionDefinitions[act.id] || {};
          const regResolved = actionsRegistry?.has?.(act.id)
            ? actionsRegistry.resolve(act.id)
            : null;
          const displayLabel = def.text || regResolved?.text || act.label;
          const displayHint = def.hint ?? regResolved?.hint ?? act.hint ?? act.label;
          const displayShortcut = def.shortcut ?? regResolved?.shortcut ?? act.shortcut ?? '';
          const currentIcon =
            def.icon || iconAssignments[act.id] || regResolved?.icon || act.icon || 'command.default';
          const liveStatus =
            def.status || regResolved?.status || 'enabled';
          const targetSpec = def.target || regResolved?.target || {};
          const targetKind = targetSpec.kind === 'server' ? 'server' : 'client';
          const targetHandlerId = targetSpec.handlerId || act.handlerId || '';
          const targetEventName = targetSpec.eventName || '';
          const targetEndpoint = targetSpec.endpoint || `/cdeadmin/api/shell/actions/${act.id}/invoke`;
          const targetMethod = targetSpec.method || 'POST';
          const isExpanded = expandedActionId === act.id || filteredActions.length <= 5;
          const hasOverride = Boolean(actionDefinitions[act.id] || iconAssignments[act.id]);

          return (
            <div
              key={act.id}
              data-cdeadmin-qa-key={`action-icon-row-${act.id}`}
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
                padding: '8px 10px',
                borderRadius: 8,
                border: hasOverride
                  ? '1px solid var(--sr-accent, #2563eb)'
                  : '1px solid var(--sr-border-subtle)',
                background: 'var(--sr-surface-card)',
              }}
            >
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'minmax(170px, 1.35fr) minmax(170px, 1.15fr) 128px auto',
                  gap: 8,
                  alignItems: 'center',
                }}
              >
                <div style={{display: 'flex', alignItems: 'center', gap: 8, minWidth: 0}}>
                  <Icon iconKey={currentIcon} decorative size="18px" />
                  <div style={{minWidth: 0}}>
                    <div
                      style={{
                        fontWeight: 600,
                        fontSize: '0.8rem',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {displayLabel}
                    </div>
                    <code style={{fontSize: '0.68rem', color: 'var(--sr-text-secondary)'}}>
                      {act.id}
                    </code>
                  </div>
                </div>

                <Select
                  aria-label={`Semantic icon for ${act.label}`}
                  value={currentIcon}
                  options={iconOptions}
                  onChange={(val) => {
                    if (!val) return;
                    updateSingleActionDefinition(act.id, {icon: val});
                  }}
                />

                <Select
                  aria-label={`Status for ${act.label}`}
                  value={liveStatus}
                  options={[
                    {value: 'enabled', label: gettext('Enabled')},
                    {value: 'disabled', label: gettext('Disabled')},
                    {value: 'invisible', label: gettext('Invisible')},
                  ]}
                  onChange={(val) => {
                    if (!val) return;
                    updateSingleActionDefinition(act.id, {status: val});
                  }}
                />

                <Button
                  intent={isExpanded ? 'primary' : 'neutral'}
                  data-cdeadmin-qa-key={`action-configure-${act.id}`}
                  onClick={() =>
                    setExpandedActionId((prev) => (prev === act.id ? null : act.id))
                  }
                >
                  {isExpanded ? gettext('Hide Details') : gettext('Configure…')}
                </Button>
              </div>

              {isExpanded && (
                <div
                  data-cdeadmin-qa-key={`action-details-${act.id}`}
                  style={{
                    paddingTop: 8,
                    borderTop: '1px solid var(--sr-border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                  }}
                >
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1.2fr 140px', gap: 8}}>
                    <TextField
                      label={gettext('Button Text')}
                      value={displayLabel}
                      inputProps={{
                        'aria-label': `Button text for ${act.id}`,
                        'data-cdeadmin-qa-key': `action-text-${act.id}`,
                      }}
                      onChange={(e) =>
                        updateSingleActionDefinition(act.id, {text: e.target.value})
                      }
                    />
                    <TextField
                      label={gettext('Hover Hint / Tooltip')}
                      value={displayHint}
                      inputProps={{
                        'aria-label': `Hint for ${act.id}`,
                        'data-cdeadmin-qa-key': `action-hint-${act.id}`,
                      }}
                      onChange={(e) =>
                        updateSingleActionDefinition(act.id, {hint: e.target.value})
                      }
                    />
                    <TextField
                      label={gettext('Shortcut')}
                      value={displayShortcut}
                      placeholder="e.g. F5"
                      inputProps={{
                        'aria-label': `Shortcut for ${act.id}`,
                        'data-cdeadmin-qa-key': `action-shortcut-${act.id}`,
                      }}
                      onChange={(e) =>
                        updateSingleActionDefinition(act.id, {shortcut: e.target.value})
                      }
                    />
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns:
                        targetKind === 'client'
                          ? '150px 1.2fr 1fr auto'
                          : '150px 1.5fr 110px auto',
                      gap: 8,
                      alignItems: 'end',
                    }}
                  >
                    <Select
                      label={gettext('Code Target Kind')}
                      aria-label={`Target kind for ${act.id}`}
                      value={targetKind}
                      options={[
                        {value: 'client', label: gettext('Client Handler')},
                        {value: 'server', label: gettext('Server Endpoint')},
                      ]}
                      onChange={(val) => {
                        if (!val) return;
                        if (val === 'server') {
                          updateSingleActionDefinition(act.id, {
                            target: {
                              kind: 'server',
                              endpoint: targetEndpoint,
                              method: targetMethod,
                            },
                          });
                        } else {
                          updateSingleActionDefinition(act.id, {
                            target: {
                              kind: 'client',
                              handlerId: targetHandlerId || CALLABLE_CODE_TARGETS[0]?.id || '',
                              eventName: targetEventName,
                            },
                          });
                        }
                      }}
                    />

                    {targetKind === 'client' ? (
                      <>
                        <Select
                          label={gettext('Callable Handler (Code Called)')}
                          aria-label={`Callable handler for ${act.id}`}
                          value={targetHandlerId}
                          options={[
                            ...(targetHandlerId &&
                            !callableTargetOptions.some((o) => o.value === targetHandlerId)
                              ? [{value: targetHandlerId, label: targetHandlerId}]
                              : []),
                            ...callableTargetOptions,
                          ]}
                          onChange={(val) =>
                            val &&
                            updateSingleActionDefinition(act.id, {
                              target: {
                                kind: 'client',
                                handlerId: val,
                                ...(targetEventName ? {eventName: targetEventName} : {}),
                              },
                            })
                          }
                        />
                        <TextField
                          label={gettext('Custom Window Event (Optional)')}
                          placeholder="e.g. scratchrobin:custom-cmd"
                          value={targetEventName}
                          inputProps={{
                            'aria-label': `Window event for ${act.id}`,
                            'data-cdeadmin-qa-key': `action-event-${act.id}`,
                          }}
                          onChange={(e) =>
                            updateSingleActionDefinition(act.id, {
                              target: {
                                kind: 'client',
                                ...(targetHandlerId ? {handlerId: targetHandlerId} : {}),
                                eventName: e.target.value,
                              },
                            })
                          }
                        />
                      </>
                    ) : (
                      <>
                        <TextField
                          label={gettext('Server API Endpoint')}
                          value={targetEndpoint}
                          inputProps={{
                            'aria-label': `Server endpoint for ${act.id}`,
                            'data-cdeadmin-qa-key': `action-endpoint-${act.id}`,
                          }}
                          onChange={(e) =>
                            updateSingleActionDefinition(act.id, {
                              target: {
                                kind: 'server',
                                endpoint: e.target.value,
                                method: targetMethod,
                              },
                            })
                          }
                        />
                        <Select
                          label={gettext('HTTP Method')}
                          aria-label={`HTTP method for ${act.id}`}
                          value={targetMethod}
                          options={[
                            {value: 'POST', label: 'POST'},
                            {value: 'PUT', label: 'PUT'},
                            {value: 'GET', label: 'GET'},
                            {value: 'DELETE', label: 'DELETE'},
                          ]}
                          onChange={(val) =>
                            val &&
                            updateSingleActionDefinition(act.id, {
                              target: {
                                kind: 'server',
                                endpoint: targetEndpoint,
                                method: val,
                              },
                            })
                          }
                        />
                      </>
                    )}

                    <Button
                      intent="neutral"
                      disabled={!hasOverride}
                      data-cdeadmin-qa-key={`action-reset-${act.id}`}
                      onClick={() => resetSingleActionDefinition(act.id)}
                    >
                      {gettext('Reset')}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

ActionMenuToolbarEditor.propTypes = {
  subView: PropTypes.oneOf([
    'global-menus',
    'app-menus',
    'iconbars',
    'tib-appearance',
    'icons',
  ]),
  hideTabs: PropTypes.bool,
  globalSettings: PropTypes.object,
  applicationSettings: PropTypes.object,
  applications: PropTypes.array,
  actionsRegistry: PropTypes.object,
  onChangeGlobal: PropTypes.func,
  onChangeApp: PropTypes.func,
  onNavigateSubView: PropTypes.func,
};
