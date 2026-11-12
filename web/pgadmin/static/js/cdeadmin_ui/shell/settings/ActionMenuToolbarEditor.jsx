/////////////////////////////////////////////////////////////
//
// ScratchRobin — Action, Menu & Tabbed-Notebook-Iconbar Placement Editor
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Button} from '../../primitives/Button';
import {NumberField, TextField} from '../../primitives/Field';
import {Select, Switch} from '../../primitives/Choice';
import {SearchField} from '../../primitives/AdvancedControls';
import {Icon, listIconDefinitions} from '../../icons';
import {
  CANONICAL_ACTION_CATALOG,
  CANONICAL_APPLICATION_SURFACES,
  FALLBACK_QUICK_ACCESS_IDS,
  readLocalPlacements,
  writeLocalPlacements,
} from '../actionPlacementEngine';

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
      label: g.label,
      hidden: Boolean(g.hidden),
      actions: [...(g.actions || g.controls || [])].map((a) =>
        typeof a === 'string' ? a : a?.actionId || a?.command || ''
      ).filter(Boolean),
    })),
  }));
}

export function ActionMenuToolbarEditor({
  subView = 'global-menus',
  globalSettings = {},
  applicationSettings = {},
  applications = [],
  actionsRegistry = null,
  onChangeGlobal,
  onChangeApp,
}) {
  const localInitial = useMemo(() => readLocalPlacements(), []);

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
  const [iconAssignments, setIconAssignments] = useState(
    () => globalSettings.icon_assignments || localInitial.icon_assignments || {}
  );
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
  const [selectedActionToAdd, setSelectedActionToAdd] = useState(
    CANONICAL_ACTION_CATALOG[0]?.id || 'shell.quick.new'
  );
  const [selectedQuickActionToAdd, setSelectedQuickActionToAdd] = useState('sql.execute');
  const [selectedTabIdx, setSelectedTabIdx] = useState(0);
  const [selectedGroupIdx, setSelectedGroupIdx] = useState(0);
  const [newTabLabel, setNewTabLabel] = useState('');
  const [newGroupLabel, setNewGroupLabel] = useState('');
  const [actionFilter, setActionFilter] = useState('');

  // Merge canonical catalog + any dynamic actions registered in `actionsRegistry`
  const allActions = useMemo(() => {
    const byId = new Map();
    CANONICAL_ACTION_CATALOG.forEach((item) => {
      byId.set(item.id, {...item});
    });
    if (typeof actionsRegistry?.list === 'function') {
      actionsRegistry.list().forEach((act) => {
        if (!act?.id || byId.has(act.id)) return;
        // Skip instance-suffixed duplicates (`foo.bar.sql-editor-1`) in catalog picker
        if (/\.[a-z0-9-]+-\d+$/i.test(act.id)) return;
        byId.set(act.id, {
          id: act.id,
          label: act.text || act.defaultText || act.id,
          icon: act.icon || 'command.default',
          scope: act.application || 'global',
        });
      });
    }
    return [...byId.values()];
  }, [actionsRegistry]);

  const iconOptions = useMemo(() => {
    const defs = listIconDefinitions() || [];
    return defs.map((d) => ({
      value: d.key,
      label: `${d.label || d.key} (${d.key})`,
    }));
  }, []);

  const actionOptions = useMemo(
    () =>
      allActions.map((a) => ({
        value: a.id,
        label: `${a.label} [${a.scope}]`,
      })),
    [allActions]
  );

  const resolveActionMeta = (actionId) => {
    const found = allActions.find((a) => a.id === actionId);
    const assignedIcon = iconAssignments[actionId];
    return {
      id: actionId,
      label: found?.label || actionId,
      icon: assignedIcon || found?.icon || 'command.default',
      scope: found?.scope || 'global',
    };
  };

  const commitGlobalPlacements = (nextPatch = {}) => {
    const nextMenus = nextPatch.menuPlacements ?? menuPlacements;
    const nextQuick = nextPatch.quickAccess ?? quickAccess;
    const nextIcons = nextPatch.iconAssignments ?? iconAssignments;

    setMenuPlacements(nextMenus);
    setQuickAccess(nextQuick);
    setIconAssignments(nextIcons);

    writeLocalPlacements({
      menu_placements: nextMenus,
      quick_access: nextQuick,
      icon_assignments: nextIcons,
    });
    onChangeGlobal?.({
      menu_placements: nextMenus,
      quick_access: nextQuick,
      icon_assignments: nextIcons,
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

  // -------------------------------------------------------------------------
  // Sub-view 1: Global Top Menu Bar (`Area 1`)
  // -------------------------------------------------------------------------
  if (subView === 'global-menus') {
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
  if (subView === 'app-menus') {
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
          options={(applications.length ? applications : [{id: 'data-navigator', label: 'Data Navigator'}]).map(
            (a) => ({value: a.id, label: a.label || a.id})
          )}
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
  // Sub-view 3: Tabbed-Notebook Iconbars (`Area 3b` & `3b1` Quick Strip)
  // -------------------------------------------------------------------------
  if (subView === 'iconbars') {
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

    return (
      <div
        data-cdeadmin-qa-key="settings-iconbars-editor"
        style={{display: 'flex', flexDirection: 'column', gap: 14}}
      >
        <div>
          <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
            {gettext('Tabbed-Notebook Iconbars Editor (Area 3b & 3b1 Quick Strip)')}
          </div>
          <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
            {gettext(
              'Place, reorder, or remove compact action icons on the 3b1 Quick-Access strip and every application’s 3b Tabbed-Notebook-Iconbar.'
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
              options={(applications.length ? applications : [{id: 'data-navigator', label: 'Data Navigator'}]).map(
                (a) => ({value: a.id, label: a.label || a.id})
              )}
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

          {/* Tabs strip */}
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8, alignItems: 'end'}}>
            <Select
              label={gettext('Notebook Tab (3b2 / 3b3)')}
              value={String(safeTabIdx)}
              options={tabs.map((t, idx) => ({value: String(idx), label: t.label}))}
              onChange={(val) => {
                setSelectedTabIdx(Number(val) || 0);
                setSelectedGroupIdx(0);
              }}
            />
            <TextField
              label={gettext('New Tab Title')}
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
              label={gettext('Icon Group inside "%s"', currentTab.label)}
              value={String(safeGroupIdx)}
              options={(currentTab.groups || []).map((g, idx) => ({
                value: String(idx),
                label: g.label,
              }))}
              onChange={(val) => setSelectedGroupIdx(Number(val) || 0)}
            />
            <TextField
              label={gettext('New Group Label')}
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
  // Sub-view 4: Action Semantic Icons & Tri-State Status
  // -------------------------------------------------------------------------
  const filteredActions = allActions.filter((a) => {
    const q = actionFilter.trim().toLowerCase();
    if (!q) return true;
    return `${a.id} ${a.label} ${a.scope}`.toLowerCase().includes(q);
  });

  return (
    <div
      data-cdeadmin-qa-key="settings-action-icons-editor"
      style={{display: 'flex', flexDirection: 'column', gap: 12}}
    >
      <div>
        <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
          {gettext('Action Semantic Icons & Tri-State Visibility')}
        </div>
        <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
          {gettext(
            'Reassign semantic icons or override Enabled / Disabled / Invisible status for any t_action across menus and iconbars.'
          )}
        </div>
      </div>

      <SearchField
        label={gettext('Filter actions')}
        placeholder={gettext('Search by action ID, label, or application…')}
        value={actionFilter}
        onChange={setActionFilter}
      />

      <div style={{display: 'flex', flexDirection: 'column', gap: 6}}>
        {filteredActions.slice(0, 30).map((act) => {
          const currentIcon = iconAssignments[act.id] || act.icon || 'command.default';
          const liveStatus = actionsRegistry?.has?.(act.id)
            ? actionsRegistry.resolve(act.id)?.status || 'enabled'
            : 'enabled';

          return (
            <div
              key={act.id}
              data-cdeadmin-qa-key={`action-icon-row-${act.id}`}
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(160px, 1.3fr) minmax(170px, 1.2fr) 130px',
                gap: 8,
                alignItems: 'center',
                padding: '6px 10px',
                borderRadius: 8,
                border: '1px solid var(--sr-border-subtle)',
                background: 'var(--sr-surface-card)',
              }}
            >
              <div style={{display: 'flex', alignItems: 'center', gap: 8, minWidth: 0}}>
                <Icon iconKey={currentIcon} decorative size="17px" />
                <div style={{minWidth: 0}}>
                  <div style={{fontWeight: 600, fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>
                    {act.label}
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
                  commitGlobalPlacements({
                    iconAssignments: {...iconAssignments, [act.id]: val},
                  });
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
                  if (!val || !actionsRegistry?.setStatus) return;
                  actionsRegistry.setStatus(act.id, val);
                }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

ActionMenuToolbarEditor.propTypes = {
  subView: PropTypes.oneOf(['global-menus', 'app-menus', 'iconbars', 'icons']),
  globalSettings: PropTypes.object,
  applicationSettings: PropTypes.object,
  applications: PropTypes.array,
  actionsRegistry: PropTypes.object,
  onChangeGlobal: PropTypes.func,
  onChangeApp: PropTypes.func,
};
