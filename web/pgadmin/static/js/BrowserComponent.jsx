/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AppMenuBar from './AppMenuBar';
import AppNotebookBar from './AppNotebookBar';
import {commandBarMode} from './cdeadmin_ui/shell/commandBarSettings';
import SQLNotebook from './cdeadmin_ui/projects/SQLNotebook';
import {NOTEBOOK_TYPE} from './cdeadmin_ui/projects/SQLNotebookModel';
import {createCloseGuardRegistry, ModalCloseGuardContext} from './helpers/ModalCloseGuard';
import ObjectBreadcrumbs from './components/ObjectBreadcrumbs';
import {
  getDefaultGroup,
  WORKSPACE_EVENTS as LAYOUT_EVENTS,
  Workspace as Layout,
  WorkspaceController as LayoutDocker,
} from 'sources/cdeadmin_ui/workspace/Workspace';
import gettext from 'sources/gettext';
import ObjectExplorer from './tree/ObjectExplorer';
import Properties from '../../misc/properties/Properties';
import SQL from '../../misc/sql/static/js/SQL';
import Statistics from '../../misc/statistics/static/js/Statistics';
import {
  BROWSER_PANELS, WORKSPACES,
} from '../../browser/static/js/constants';
import Dependencies from '../../misc/dependencies/static/js/Dependencies';
import Dependents from '../../misc/dependents/static/js/Dependents';
import ModalProvider from './helpers/ModalProvider';
import { NotifierProvider } from './helpers/Notifier';
import ObjectExplorerToolbar from './tree/ObjectExplorer/ObjectExplorerToolbar';
import MainMoreToolbar from './helpers/MainMoreToolbar';
import Dashboard from '../../dashboard/static/js/Dashboard';
import usePreferences from '../../preferences/static/js/store';
import { getBrowser } from './utils';
import PropTypes from 'prop-types';
import Processes from '../../misc/bgprocess/static/js/Processes';
import currentUser from 'pgadmin.user_management.current_user';
import { useBeforeUnload } from './custom_hooks';
import pgWindow from 'sources/window';
import { useWorkspace, WorkspaceProvider } from '../../misc/workspaces/static/js/WorkspaceProvider';
import { PgAdminProvider, usePgAdmin } from './PgAdminProvider';
import PreferencesComponent from '../../preferences/static/js/components/PreferencesComponent';
import { ApplicationStateProvider } from '../../settings/static/ApplicationStateProvider';
import { appAutoUpdateNotifier } from './helpers/appAutoUpdateNotifier';
import {
  Box,
  Button,
  Dialog,
  EmptyState,
  Icon,
  ScratchPopoverPalette,
  ScratchScrollArea,
  Tab,
  initializeCDEadminPlatform,
  ProjectExplorer,
  SurfaceHost,
  InspectorHost,
  requestPreferencesSection,
  APPEARANCE_PREFERENCES_ID,
  DESIGNER_PREFERENCES_ID,
  requestWorkbenchInspection,
  workbenchContextService,
  ProjectShellProvider,
  ProjectWorkbenchFrame,
  useProjectShell,
  T_ACTION_STATUS,
  T_ACTION_TARGET_KIND,
} from 'sources/cdeadmin_ui';
import {providerContextMenuItems} from '../../browser/static/js/ProviderContextMenu';
import {openFamilyCreate} from '../../browser/static/js/ProviderObjectEditor';
import {SchemaCompareWorkspace} from './cdeadmin_ui/modules/schema_compare/SchemaCompareWorkspace';
import {
  DesignStoreClient,
  ERDDesignerSurface,
  ERDModelsNavigator,
  ERD_MODEL_OPEN_EVENT,
  requestERDModelCreate,
  CubeDesignerSurface,
  CubesNavigator,
  CUBE_OPEN_EVENT,
  requestCubeCreate,
  BIDesignerSurface,
  BIDesignsNavigator,
  BI_DESIGN_OPEN_EVENT,
  requestBIDesignCreate,
  ScreenMeshDesignerSurface,
  ScreenMeshesNavigator,
  SCREEN_MESH_OPEN_EVENT,
  requestScreenMeshCreate,
} from 'sources/cdeadmin_ui/integrations/ddn';

export const processesPanelData = {
  id: BROWSER_PANELS.PROCESSES, title: gettext('Processes'), content: <Processes />, closable: true, group: 'playground'
};

export const preferencesPanelData = {
  id: BROWSER_PANELS.PREFERENCES, title: gettext('Preferences'), content: <PreferencesComponent panelId={BROWSER_PANELS.PREFERENCES} />, closable: true, manualClose: true, group: 'playground'
};

// Startup shows ONLY the User Dashboard placeholder (no preloaded SQL tab).
export const defaultTabsData = [
  {
    id: BROWSER_PANELS.DASHBOARD, title: gettext('ScratchRobin'),
    tooltip: gettext('ScratchRobin Dashboard'), iconKey: 'tool.scratchrobin',
    content: <Dashboard />, closable: false, group: 'playground'
  },
];

function buildNavigatorSelectionConfig(pgAdmin, instanceId, selectedItem = null, selectedData = null) {
  const addAction = `data-navigator.add_child.${instanceId}`;
  const propertiesAction = `data-navigator.properties.${instanceId}`;
  const removeAction = `data-navigator.remove.${instanceId}`;
  const refreshAction = `data-navigator.refresh.${instanceId}`;
  const enginesAction = `data-navigator.engines.${instanceId}`;

  const nodeType = selectedData?._type || null;
  const providerMenus = selectedData ? providerContextMenuItems(selectedData, selectedItem) || [] : [];
  const findProviderSuffix = (suffix) =>
    providerMenus.find((m) => String(m.commandId).split('.').at(-1) === suffix);
  const runProviderMenu = (menu) =>
    menu?.commandHandler?.(
      menu.commandArguments({itemData: selectedData, item: selectedItem}),
      {itemData: selectedData, item: selectedItem}
    );

  const selectPropertiesTab = () => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:navigator-select-tab', {
          detail: {tab: 'properties', focusEditor: true},
        })
      );
    }
  };

  let addSpec = {
    enabled: false,
    text: gettext('Add Child Object…'),
    hint: gettext('Select an engine to add a server, or a server to add a database'),
    icon: 'action.new',
    invoke: () => {},
  };
  let propSpec = {
    enabled: false,
    text: gettext('Properties…'),
    hint: gettext('Select a server, database, or catalog object to view or edit its properties'),
    icon: 'action.properties',
    invoke: () => {},
  };
  let removeSpec = {
    enabled: false,
    text: gettext('Remove…'),
    hint: gettext('Select a server, database, or catalog object to remove it'),
    icon: 'action.delete',
    invoke: () => {},
  };

  if (nodeType === 'engine_type') {
    const engineId = selectedData.engine_id || selectedData._id;
    addSpec = {
      enabled: true,
      text: gettext('Register Server…'),
      hint: gettext('Register a server or database file for this engine'),
      icon: 'object.server',
      invoke: () => {
        const serverNode = pgAdmin?.Browser?.Nodes?.server;
        serverNode?.callbacks?.register_engine_server?.call(serverNode, {
          item: selectedItem,
          engineId,
        });
      },
    };
  } else if (nodeType === 'localhost_placeholder') {
    propSpec = {
      enabled: true,
      text: gettext('Properties…'),
      hint: gettext('Configure port, credentials, and settings for this local server'),
      icon: 'action.properties',
      invoke: selectPropertiesTab,
    };
  } else if (nodeType === 'server') {
    const createDb = findProviderSuffix('create_database') || findProviderSuffix('register_database');
    const dbNode = pgAdmin?.Browser?.Nodes?.database;
    const canLegacyCreateDb =
      !selectedData?.cde_endpoint && Boolean(selectedData?.connected);
    const canAddDb = createDb
      ? Boolean(createDb.enable(selectedData, selectedItem))
      : canLegacyCreateDb;
    if (createDb || !selectedData?.cde_endpoint) {
      addSpec = {
        enabled: canAddDb,
        text: gettext('Create Database…'),
        hint: createDb?.disabledReason || gettext('Add or create a database on this server'),
        icon: 'object.database',
        invoke: () => {
          if (createDb) {
            runProviderMenu(createDb);
          } else {
            dbNode?.callbacks?.show_obj_properties?.call(dbNode, {
              action: 'create',
              item: selectedItem,
            });
          }
        },
      };
    }
    propSpec = {
      enabled: true,
      text: gettext('Server Properties…'),
      hint: gettext('Edit connection settings, port, and credentials for this server'),
      icon: 'action.properties',
      invoke: selectPropertiesTab,
    };
    const forgetMenu = findProviderSuffix('forget');
    removeSpec = {
      enabled: true,
      text: gettext('Remove Server…'),
      hint: gettext('Remove this server registration'),
      icon: 'action.delete',
      invoke: () => {
        if (forgetMenu && forgetMenu.enable(selectedData, selectedItem)) {
          runProviderMenu(forgetMenu);
          return;
        }
        const serverNode = pgAdmin?.Browser?.Nodes?.server;
        serverNode?.callbacks?.delete_obj?.call(serverNode, {
          item: selectedItem,
          url: 'drop',
        });
      },
    };
  } else if (nodeType === 'coll-database') {
    const dbNode = pgAdmin?.Browser?.Nodes?.database;
    addSpec = {
      enabled: true,
      text: gettext('Create Database…'),
      hint: gettext('Create a new database on this server'),
      icon: 'object.database',
      invoke: () =>
        dbNode?.callbacks?.show_obj_properties?.call(dbNode, {
          action: 'create',
          item: selectedItem,
        }),
    };
  } else if (nodeType === 'cde_database_target' || nodeType === 'database') {
    propSpec = {
      enabled: true,
      text: gettext('Database Properties…'),
      hint: gettext('View or edit properties for this database'),
      icon: 'action.properties',
      invoke: selectPropertiesTab,
    };
    const removeDb = findProviderSuffix('remove') || findProviderSuffix('drop');
    const dbNode = pgAdmin?.Browser?.Nodes?.database;
    removeSpec = {
      enabled: removeDb ? Boolean(removeDb.enable(selectedData, selectedItem)) : nodeType === 'database',
      text: removeDb && String(removeDb.commandId).endsWith('.remove')
        ? gettext('Remove Database…')
        : gettext('Drop Database…'),
      hint: removeDb?.disabledReason || gettext('Remove or drop this database'),
      icon: 'action.delete',
      invoke: () => {
        if (removeDb) {
          runProviderMenu(removeDb);
        } else {
          dbNode?.callbacks?.delete_obj?.call(dbNode, {
            item: selectedItem,
            url: 'drop',
          });
        }
      },
    };
  } else if (nodeType === 'cde_resource_group') {
    const createMenu = findProviderSuffix('create');
    const kind = selectedData?.cde_resource_kind;
    addSpec = {
      enabled: true,
      text: createMenu?.label || gettext('New %s…', selectedData?.label || kind || 'Object'),
      hint: gettext('Create a new object in this group'),
      icon: 'action.new',
      invoke: () => {
        if (kind && openFamilyCreate(selectedData, selectedItem, kind)) return;
        if (createMenu) runProviderMenu(createMenu);
      },
    };
  } else if (nodeType && nodeType !== 'server_group') {
    propSpec = {
      enabled: true,
      text: gettext('Properties…'),
      hint: gettext('Inspect or edit properties for the selected object'),
      icon: 'action.properties',
      invoke: selectPropertiesTab,
    };
    const dropMenu = findProviderSuffix('drop');
    const modNode = pgAdmin?.Browser?.Nodes?.[nodeType];
    if (dropMenu || modNode?.canDrop) {
      removeSpec = {
        enabled: dropMenu ? Boolean(dropMenu.enable(selectedData, selectedItem)) : true,
        text: gettext('Drop Object…'),
        hint: gettext('Drop the selected object'),
        icon: 'action.delete',
        invoke: () => {
          if (dropMenu) {
            runProviderMenu(dropMenu);
          } else {
            modNode?.callbacks?.delete_obj?.call(modNode, {
              item: selectedItem,
              url: 'drop',
            });
          }
        },
      };
    }
  }

  const actions = [
    {
      id: addAction,
      icon: addSpec.icon,
      application: 'data-navigator',
      defaultText: addSpec.text,
      defaultHint: addSpec.hint,
      status: addSpec.enabled ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
      focusScoped: true,
      target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: addSpec.invoke},
    },
    {
      id: propertiesAction,
      icon: propSpec.icon,
      application: 'data-navigator',
      defaultText: propSpec.text,
      defaultHint: propSpec.hint,
      status: propSpec.enabled ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
      focusScoped: true,
      target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: propSpec.invoke},
    },
    {
      id: removeAction,
      icon: removeSpec.icon,
      application: 'data-navigator',
      defaultText: removeSpec.text,
      defaultHint: removeSpec.hint,
      status: removeSpec.enabled ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
      focusScoped: true,
      target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: removeSpec.invoke},
    },
    {
      id: refreshAction,
      icon: 'action.refresh',
      application: 'data-navigator',
      defaultText: gettext('Refresh Catalog'),
      defaultHint: gettext('Refresh selected database catalog branch'),
      status: T_ACTION_STATUS.ENABLED,
      focusScoped: true,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => pgAdmin?.Browser?.Events?.trigger?.('pgadmin-browser:tree:refresh'),
      },
    },
    {
      id: enginesAction,
      icon: 'object.database',
      application: 'data-navigator',
      defaultText: gettext('Configure Database Engines…'),
      defaultHint: gettext('Enable or disable database engine connectors'),
      status: T_ACTION_STATUS.ENABLED,
      focusScoped: true,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () =>
          window.dispatchEvent(
            new CustomEvent('scratchrobin:open-preferences', {
              detail: {mode: 'global', sectionId: 'engines:connectors'},
            })
          ),
      },
    },
  ];

  const menuItems = [];
  if (addSpec.enabled) {
    menuItems.push({
      id: addAction,
      actionId: addAction,
      label: addSpec.text,
      iconKey: addSpec.icon,
      index: 5,
    });
  }
  if (propSpec.enabled) {
    menuItems.push({
      id: propertiesAction,
      actionId: propertiesAction,
      label: propSpec.text,
      iconKey: propSpec.icon,
      index: 10,
    });
  }
  if (removeSpec.enabled) {
    menuItems.push({
      id: removeAction,
      actionId: removeAction,
      label: removeSpec.text,
      iconKey: removeSpec.icon,
      index: 15,
    });
  }
  if (!nodeType || nodeType === 'server_group') {
    menuItems.push({
      id: enginesAction,
      actionId: enginesAction,
      label: gettext('Configure Database Engines…'),
      iconKey: 'object.database',
      index: 18,
    });
  }
  menuItems.push({
    id: refreshAction,
    actionId: refreshAction,
    label: gettext('Refresh Catalog'),
    i18nKey: 'menu.object.refresh_catalog.text',
    hintKey: 'menu.object.refresh_catalog.hint',
    iconKey: 'action.refresh',
    index: 25,
  });

  return {
    actions,
    menus: [
      {
        name: 'object',
        label: gettext('Object'),
        i18nKey: 'menu.object.title',
        index: 20,
        items: menuItems,
      },
    ],
    ribbonTabs: [
      {
        id: 'navigator-home',
        label: gettext('Navigator'),
        groups: [
          {
            id: 'navigator-object',
            label: gettext('Selected Object'),
            controls: [addAction, propertiesAction, removeAction],
          },
          {
            id: 'navigator-catalog',
            label: gettext('Catalog'),
            controls: [refreshAction],
          },
        ],
      },
    ],
  };
}

export function navigatorTabIdsForNodeType(nodeType, pgAdmin = null) {
  if (!nodeType || nodeType === 'server_group') {
    return ['connectors'];
  }
  if (
    nodeType === 'engine_type' ||
    nodeType === 'localhost_placeholder' ||
    nodeType === 'server' ||
    nodeType === 'cde_database_target'
  ) {
    return ['properties', 'statistics'];
  }
  if (nodeType === 'cde_resource_group' || String(nodeType).startsWith('coll-')) {
    return ['properties', 'statistics'];
  }
  if (nodeType === 'database') {
    return ['properties', 'sql', 'statistics'];
  }
  if (nodeType === 'cde_resource') {
    return ['properties', 'sql', 'statistics', 'dependencies', 'dependents'];
  }
  const nodeDef = pgAdmin?.Browser?.Nodes?.[nodeType];
  if (nodeDef) {
    const ids = ['properties'];
    if (nodeDef.hasSQL !== false) ids.push('sql');
    if (nodeDef.hasStatistics !== false) ids.push('statistics');
    if (nodeDef.hasDependencies) ids.push('dependencies');
    if (nodeDef.hasDependents) ids.push('dependents');
    return ids;
  }
  return ['properties', 'sql', 'statistics', 'dependencies', 'dependents'];
}

function DataNavigatorWorkArea({instanceId}) {
  const shell = useProjectShell();
  const shellRef = useRef(shell);
  shellRef.current = shell;
  const lastSelectionKeyRef = useRef(null);
  const pgAdmin = usePgAdmin();
  const [selectedNodeType, setSelectedNodeType] = useState(() => {
    const item = pgAdmin?.Browser?.tree?.selected?.();
    const data = item ? pgAdmin?.Browser?.tree?.itemData?.(item) : null;
    return data?._type || null;
  });
  const [view, setView] = useState('connectors');
  const [engines, setEngines] = useState([]);
  const [enginesLoading, setEnginesLoading] = useState(true);
  const [, setLocaleRev] = useState(0);

  const loadEnabledEngines = useCallback(() => {
    if (typeof fetch !== 'function') {
      setEnginesLoading(false);
      return;
    }
    fetch('/cdeadmin/api/shell/engines', {credentials: 'same-origin'})
      .then((res) => (res?.ok ? res.json() : null))
      .then((data) => {
        if (Array.isArray(data?.engines)) {
          setEngines(data.engines.filter((eng) => Boolean(eng.enabled)));
        }
      })
      .catch(() => {})
      .finally(() => setEnginesLoading(false));
  }, []);

  useEffect(() => {
    loadEnabledEngines();
    if (typeof window === 'undefined') return undefined;
    const onConnectorsChanged = () => loadEnabledEngines();
    window.addEventListener('scratchrobin:connectors-changed', onConnectorsChanged);
    return () => window.removeEventListener('scratchrobin:connectors-changed', onConnectorsChanged);
  }, [loadEnabledEngines]);

  useEffect(() => {
    const events = pgAdmin?.Browser?.Events;
    const syncSelectionActions = (item, data) => {
      const currentShell = shellRef.current;
      if (!instanceId || !currentShell?.updateInstance) return;
      const selectionKey = data
        ? `${data._type || ''}:${data._id ?? data.id ?? data.engine_id ?? data._label ?? ''}:${Boolean(data.connected)}`
        : 'none';
      if (lastSelectionKeyRef.current === selectionKey) return;
      lastSelectionKeyRef.current = selectionKey;
      const cfg = buildNavigatorSelectionConfig(pgAdmin, instanceId, item, data);
      currentShell.updateInstance(instanceId, {
        actions: cfg.actions,
        menus: cfg.menus,
        ribbonTabs: cfg.ribbonTabs,
      });
    };
    const onTreeSelected = (item, data) => {
      const nextType = data?._type || null;
      setSelectedNodeType(nextType);
      syncSelectionActions(item, data);
      const allowed = navigatorTabIdsForNodeType(nextType, pgAdmin);
      setView((prev) => (allowed.includes(prev) ? prev : allowed[0]));
    };
    const onNodeDeselected = () => {
      setSelectedNodeType(null);
      syncSelectionActions(null, null);
    };
    const onSelectTab = (ev) => {
      const requested = ev?.detail?.tab;
      if (requested) {
        setView(requested);
      }
      if (ev?.detail?.focusEditor && typeof document !== 'undefined') {
        setTimeout(() => {
          const root = document.querySelector('[data-cdeadmin-qa-key="data-navigator-work-area"]');
          const portInput =
            root?.querySelector('input[type="number"]:not([disabled])') ||
            root?.querySelector('[data-cdeadmin-qa-key^="object-editor."] input:not([disabled])');
          portInput?.focus?.();
          portInput?.select?.();
        }, 60);
      }
    };
    events?.on?.('pgadmin-browser:tree:selected', onTreeSelected);
    events?.on?.('pgadmin-browser:node:deselected', onNodeDeselected);
    const onLanguageChanged = (ev) => {
      setLocaleRev((prev) => ev?.detail?.revision ?? prev + 1);
      lastSelectionKeyRef.current = null;
      const curItem = pgAdmin?.Browser?.tree?.selected?.();
      const curData = curItem ? pgAdmin?.Browser?.tree?.itemData?.(curItem) : null;
      syncSelectionActions(curItem, curData);
    };
    if (typeof window !== 'undefined') {
      window.addEventListener('scratchrobin:navigator-select-tab', onSelectTab);
      window.addEventListener('scratchrobin:language-changed', onLanguageChanged);
    }
    const currentItem = pgAdmin?.Browser?.tree?.selected?.();
    const currentData = currentItem ? pgAdmin?.Browser?.tree?.itemData?.(currentItem) : null;
    if (currentData) {
      setSelectedNodeType(currentData._type || null);
      syncSelectionActions(currentItem, currentData);
    }
    return () => {
      events?.off?.('pgadmin-browser:tree:selected', onTreeSelected);
      events?.off?.('pgadmin-browser:node:deselected', onNodeDeselected);
      if (typeof window !== 'undefined') {
        window.removeEventListener('scratchrobin:navigator-select-tab', onSelectTab);
        window.removeEventListener('scratchrobin:language-changed', onLanguageChanged);
      }
    };
  }, [instanceId, pgAdmin]);

  const focusEngineInTree = useCallback(
    async (engineId) => {
      if (shell && !shell.shellLeftDrawerOpen) {
        shell.toggleLeftDrawer?.();
      }
      const tree = pgAdmin?.Browser?.tree;
      if (!tree) return;
      try {
        const rootChildren = tree.children?.() || [];
        const serverGroup = rootChildren[0];
        if (serverGroup) {
          await tree.open?.(serverGroup);
          const connectors = tree.children?.(serverGroup) || [];
          const match = connectors.find(
            (c) =>
              c?._metadata?.data?.engine_id === engineId ||
              c?._metadata?.data?._id === engineId ||
              c?.fileName === `engine_type_${engineId}`
          );
          if (match) {
            await tree.open?.(match);
            await tree.select?.(match, true, 'center');
          }
        }
      } catch {
        // Ignore transient tree focus race while drawer mounts.
      }
    },
    [pgAdmin, shell]
  );

  const renderConnectorsOverview = () => (
    <Box
      data-cdeadmin-qa-key="data-navigator-connectors-overview"
      sx={{p: 2, display: 'flex', flexDirection: 'column', gap: 2}}
    >
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 1.5,
          flexWrap: 'wrap',
        }}
      >
        <Box>
          <Box sx={{fontWeight: 700, fontSize: '0.95rem'}}>
            {gettext('Enabled Database Connectors (%s)', engines.length)}
          </Box>
          <Box sx={{fontSize: '0.8rem', color: 'text.secondary'}}>
            {gettext(
              'Click any enabled engine below or expand Connectors in the Left Side Drawer to inspect local endpoints and register servers.'
            )}
          </Box>
        </Box>
        <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap'}}>
          {shell && !shell.shellLeftDrawerOpen && (
            <Button
              size="small"
              intent="neutral"
              data-cdeadmin-qa-key="navigator-open-left-drawer"
              onClick={() => shell.toggleLeftDrawer?.()}
            >
              {gettext('Open Catalog Tree Drawer')}
            </Button>
          )}
          <Button
            size="small"
            intent="primary"
            data-cdeadmin-qa-key="navigator-configure-engines"
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent('scratchrobin:open-preferences', {
                  detail: {mode: 'global', sectionId: 'engines:connectors'},
                })
              )
            }
          >
            {gettext('Database Engines (On / Off)…')}
          </Button>
        </Box>
      </Box>

      {enginesLoading ? (
        <Box sx={{py: 3, textAlign: 'center', fontSize: '0.82rem', color: 'text.secondary'}}>
          {gettext('Loading enabled database connectors…')}
        </Box>
      ) : engines.length === 0 ? (
        <EmptyState
          message={gettext('No database engines are currently enabled')}
          description={gettext(
            'Enable one or more database engines in Settings › Database Engines to populate the Data Navigator catalog tree.'
          )}
          actionLabel={gettext('Enable Database Engines…')}
          onAction={() =>
            window.dispatchEvent(
              new CustomEvent('scratchrobin:open-preferences', {
                detail: {mode: 'global', sectionId: 'engines:connectors'},
              })
            )
          }
        />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            gap: 10,
          }}
        >
          {engines.map((eng) => {
            const localUp = Boolean(eng.local_available ?? eng.local_detected);
            return (
              <div
                key={eng.id}
                data-cdeadmin-qa-key={`navigator-engine-card-${eng.id}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '10px 12px',
                  borderRadius: 10,
                  border: '1px solid var(--sr-border-default)',
                  background: 'var(--sr-surface-subtle)',
                  color: 'var(--sr-text-primary)',
                }}
              >
                <button
                  type="button"
                  onClick={() => void focusEngineInTree(eng.id)}
                  style={{
                    flex: 1,
                    minWidth: 0,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: 0,
                    border: 'none',
                    background: 'transparent',
                    color: 'inherit',
                    textAlign: 'left',
                    cursor: 'pointer',
                  }}
                >
                  <Icon iconKey={eng.icon || `engine.${eng.id}`} decorative size={20} />
                  <span style={{flex: 1, minWidth: 0}}>
                    <span style={{display: 'block', fontWeight: 600, fontSize: '0.84rem'}}>
                      {eng.label}
                    </span>
                    <span
                      style={{
                        display: 'block',
                        fontSize: '0.72rem',
                        color: localUp ? 'var(--sr-success, #16a34a)' : 'var(--sr-text-secondary)',
                      }}
                    >
                      {localUp ? gettext('Local listener detected') : eng.category || gettext('Enabled')}
                    </span>
                  </span>
                </button>
                <Button
                  size="small"
                  intent="neutral"
                  data-cdeadmin-qa-key={`navigator-register-engine-${eng.id}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    const serverNode = pgAdmin?.Browser?.Nodes?.server;
                    serverNode?.callbacks?.register_engine_server?.call(serverNode, {
                      engineId: eng.id,
                    });
                  }}
                >
                  {gettext('Register…')}
                </Button>
              </div>
            );
          })}
        </div>
      )}
    </Box>
  );

  const allPages = [
    {id: 'connectors', label: gettext('Connectors'), render: renderConnectorsOverview},
    {id: 'properties', label: gettext('Properties'), render: () => <Properties />},
    {id: 'sql', label: gettext('SQL'), render: () => <SQL />},
    {id: 'statistics', label: gettext('Statistics'), render: () => <Statistics />},
    {id: 'dependencies', label: gettext('Dependencies'), render: () => <Dependencies />},
    {id: 'dependents', label: gettext('Dependents'), render: () => <Dependents />},
  ];
  const allowedTabIds = navigatorTabIdsForNodeType(selectedNodeType, pgAdmin);
  const pages = allPages.filter((p) => allowedTabIds.includes(p.id));
  const current = pages.find((p) => p.id === view) || pages[0];
  return (
    <Box
      data-cdeadmin-qa-key="data-navigator-work-area"
      sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}
    >
      <Box
        role="tablist"
        aria-label={gettext('Catalog Object Views')}
        sx={{
          display: 'flex',
          alignItems: 'center',
          px: 2.5,
          borderBottom: '1px solid',
          borderColor: 'divider',
          bgcolor: 'background.paper',
          flexShrink: 0,
        }}
      >
        {pages.map((p) => (
          <Tab
            key={p.id}
            label={p.label}
            active={p.id === current.id}
            onActivate={() => setView(p.id)}
          />
        ))}
      </Box>
      {current.id === 'connectors' ? (
        <ScratchScrollArea orientation="both" style={{flex: 1, minHeight: 0}}>
          {current.render()}
        </ScratchScrollArea>
      ) : (
        <Box sx={{flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden'}}>
          {current.render()}
        </Box>
      )}
    </Box>
  );
}

DataNavigatorWorkArea.propTypes = {
  instanceId: PropTypes.string,
};

const DESIGNER_STENCIL_ITEMS = Object.freeze({
  'erd-designer': [
    {id: 'entity', label: 'Physical / Logical Entity', badge: 'Table', iconKey: 'object.table'},
    {id: 'view', label: 'Derived View', badge: 'View', iconKey: 'object.view'},
    {id: 'rel-1n', label: '1:N Foreign Key Relation', badge: '1:N', iconKey: 'action.compare'},
    {id: 'concept', label: 'Conceptual Whiteboard Box', badge: 'Draft', iconKey: 'tool.erd'},
    {id: 'deploy-node', label: 'Deployment Server / Host', badge: 'Infra', iconKey: 'object.server'},
  ],
  'cube-designer': [
    {id: 'measure-group', label: 'Fact Measure Group', badge: 'Fact', iconKey: 'tool.cube'},
    {id: 'dimension', label: 'Dimension Entity', badge: 'Dim', iconKey: 'object.table'},
    {id: 'role-play', label: 'Role-Playing Dimension Link', badge: 'Role', iconKey: 'action.compare'},
    {id: 'mat-agg', label: 'Materialized Aggregate Plan', badge: 'Agg', iconKey: 'action.execute'},
  ],
  'bi-designer': [
    {id: 'chart-card', label: 'Chart Visualization Card', badge: 'Chart', iconKey: 'tool.bi'},
    {id: 'kpi-tile', label: 'KPI Gauge / Metric Tile', badge: 'KPI', iconKey: 'action.properties'},
    {id: 'filter-widget', label: 'Cross-Filter Control', badge: 'Filter', iconKey: 'action.filter'},
    {id: 'drill-link', label: 'Drill-Through Action', badge: 'Link', iconKey: 'action.compare'},
  ],
  'screen-mesh-designer': [
    {id: 'ui-frame', label: 'Screen Frame (ui.frame)', badge: 'Screen', iconKey: 'tool.screen-mesh'},
    {id: 'ui-grid', label: 'Named Data Grid (ui.grid)', badge: 'Grid', iconKey: 'object.table'},
    {id: 'ui-dropdown', label: 'Dropdown Select (ui.dropdown)', badge: 'Control', iconKey: 'action.filter'},
    {id: 'ui-radio', label: 'Radio Choice (ui.radio)', badge: 'Control', iconKey: 'action.properties'},
    {id: 'ui-tabs', label: 'Tabbed Section (ui.tabs)', badge: 'Layout', iconKey: 'action.layers'},
    {id: 'ui-region', label: 'Image Hotspot Region (ui.region)', badge: 'Region', iconKey: 'action.select_marquee'},
    {id: 'nav-link', label: 'Screen Navigation Relation', badge: 'Flow', iconKey: 'action.compare'},
  ],
});

const SHARED_UDT_PALETTE_ITEMS = Object.freeze([
  {id: 'uuidv7', label: 'UUIDv7 Identity (Time-Ordered)', badge: 'PK'},
  {id: 'money-dec', label: 'Monetary DECIMAL(18, 4)', badge: 'Numeric'},
  {id: 'email-dom', label: 'Verified Email VARCHAR(320)', badge: 'Domain'},
  {id: 'utc-ts', label: 'UTC Timestamp With Time Zone', badge: 'Temporal'},
  {id: 'json-doc', label: 'Structured JSONB Document', badge: 'Document'},
  {id: 'type-map', label: 'Edit Cross-Engine Type Maps…', badge: 'Map'},
]);

function DesignerToolbarPalettes({appId}) {
  const stencils = DESIGNER_STENCIL_ITEMS[appId] || DESIGNER_STENCIL_ITEMS['erd-designer'];
  const dispatchPaletteInsert = (kind, itemId) => {
    window.dispatchEvent(
      new CustomEvent('scratchrobin:designer-palette-select', {
        detail: {appId, kind, itemId},
      })
    );
  };
  return (
    <Box sx={{display: 'inline-flex', alignItems: 'center', gap: 0.5}}>
      <ScratchPopoverPalette
        title={gettext('Insert Diagram Element / Stencil')}
        qaKey={`palette-entities-${appId}`}
        trigger={
          <button
            type="button"
            className="sr-icon-btn"
            aria-label={gettext('Diagram Entity & Stencil Palette')}
            title={gettext('Diagram Entity & Stencil Palette')}
            data-cdeadmin-qa-key={`toolbar-palette-entities-${appId}`}
          >
            <Icon iconKey="action.palette_entities" decorative />
          </button>
        }
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 0.25}}>
          {stencils.map((item) => (
            <button
              key={item.id}
              type="button"
              className="sr-select-item"
              style={{border: 'none', background: 'transparent', width: '100%', textAlign: 'left'}}
              onClick={() => dispatchPaletteInsert('stencil', item.id)}
            >
              <span style={{display: 'inline-flex', alignItems: 'center', gap: 6}}>
                <Icon iconKey={item.iconKey || 'action.palette_entities'} decorative />
                <span>{item.label}</span>
              </span>
              <span className="sr-bui-pill">{item.badge}</span>
            </button>
          ))}
        </Box>
      </ScratchPopoverPalette>

      <ScratchPopoverPalette
        title={gettext('User-Defined Data Types & Domains')}
        qaKey={`palette-udt-${appId}`}
        trigger={
          <button
            type="button"
            className="sr-icon-btn"
            aria-label={gettext('User-Defined Data Types Palette')}
            title={gettext('User-Defined Data Types Palette')}
            data-cdeadmin-qa-key={`toolbar-palette-udt-${appId}`}
          >
            <Icon iconKey="action.palette_udt" decorative />
          </button>
        }
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 0.25}}>
          {SHARED_UDT_PALETTE_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className="sr-select-item"
              style={{border: 'none', background: 'transparent', width: '100%', textAlign: 'left'}}
              onClick={() => dispatchPaletteInsert('udt', item.id)}
            >
              <span>{item.label}</span>
              <span className="sr-bui-pill">{item.badge}</span>
            </button>
          ))}
        </Box>
      </ScratchPopoverPalette>
    </Box>
  );
}

DesignerToolbarPalettes.propTypes = {
  appId: PropTypes.string.isRequired,
};

function DesignerApplicationWorkArea({
  instanceId,
  SurfaceComponent,
  client,
  openEvent,
  onCreate,
  emptyMessage,
  createLabel,
  initialProjectId = null,
  initialDesignId = null,
  initialKind = undefined,
}) {
  const shell = useProjectShell();
  const [selection, setSelection] = useState(() =>
    initialProjectId && initialDesignId
      ? {projectId: initialProjectId, designId: initialDesignId, kind: initialKind}
      : null
  );

  useEffect(() => {
    if (!openEvent || typeof window === 'undefined') return undefined;
    const onOpen = (event) => {
      if (shell && shell.focusedId !== instanceId) return;
      const detail = event?.detail || {};
      if (!detail.projectId || !detail.designId) return;
      event.stopImmediatePropagation?.();
      setSelection({
        projectId: detail.projectId,
        designId: detail.designId,
        kind: detail.kind,
      });
    };
    window.addEventListener(openEvent, onOpen, true);
    return () => window.removeEventListener(openEvent, onOpen, true);
  }, [instanceId, openEvent, shell]);

  if (!selection?.projectId || !selection?.designId) {
    return (
      <Box
        sx={{
          height: '100%',
          minHeight: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          p: 3,
        }}
      >
        <EmptyState
          message={emptyMessage}
          actionLabel={createLabel}
          onAction={() => {
            if (shell && !shell.shellLeftDrawerOpen) {
              shell.toggleLeftDrawer();
            }
            onCreate?.();
          }}
        />
      </Box>
    );
  }

  return (
    <SurfaceComponent
      client={client}
      projectId={selection.projectId}
      designId={selection.designId}
      {...(selection.kind ? {initialKind: selection.kind} : {})}
    />
  );
}

DesignerApplicationWorkArea.propTypes = {
  instanceId: PropTypes.string.isRequired,
  SurfaceComponent: PropTypes.elementType.isRequired,
  client: PropTypes.object.isRequired,
  openEvent: PropTypes.string.isRequired,
  onCreate: PropTypes.func,
  emptyMessage: PropTypes.string.isRequired,
  createLabel: PropTypes.string.isRequired,
  initialProjectId: PropTypes.string,
  initialDesignId: PropTypes.string,
  initialKind: PropTypes.string,
};

export function bindDesignerOpenEvents(
  ensureSurfaceHost, notifyError, targetWindow = window
) {
  const handlers = [
    [
      'cdeadmin:erd-model-open',
      (event) => ensureSurfaceHost().open('diagram.erd.designer', {
        toolInstanceId:
          `diagram.erd.designer:${event.detail.projectId}:${event.detail.designId}`,
        restoreRef: event.detail.designId,
        projectId: event.detail.projectId,
        title: event.detail.title || 'Data Model (ERD) Designer',
      }),
    ],
    [
      'cdeadmin:cube-open',
      (event) => ensureSurfaceHost().open('diagram.cube.designer', {
        toolInstanceId:
          `diagram.cube.designer:${event.detail.projectId}:${event.detail.designId}`,
        restoreRef: event.detail.designId,
        projectId: event.detail.projectId,
        title: event.detail.title || 'Cube Designer',
      }),
    ],
    [
      'cdeadmin:bi-design-open',
      (event) => ensureSurfaceHost().open('diagram.bi.designer', {
        toolInstanceId:
          `diagram.bi.designer:${event.detail.projectId}:${event.detail.designId}`,
        restoreRef: event.detail.designId,
        projectId: event.detail.projectId,
        title: event.detail.title || 'BI Question & Dashboard Designer',
      }, {kind: event.detail.kind || 'question'}),
    ],
    [
      'cdeadmin:screen-mesh-open',
      (event) => ensureSurfaceHost().open('diagram.screen_mesh.designer', {
        toolInstanceId:
          `diagram.screen_mesh.designer:${event.detail.projectId}:${event.detail.designId}`,
        restoreRef: event.detail.designId,
        projectId: event.detail.projectId,
        title: event.detail.title || 'Screen Mesh Designer',
      }, {kind: event.detail.kind || 'screen'}),
    ],
  ];
  const removers = handlers.map(([eventName, invoke]) => {
    const listener = (event) => Promise.resolve(invoke(event)).catch(
      (error) => notifyError?.(error.message)
    );
    targetWindow.addEventListener(eventName, listener);
    return () => targetWindow.removeEventListener(eventName, listener);
  });
  return () => removers.forEach((remove) => remove());
}

const getMorePanelGroup = (tabsData) => {
  return {
    ...getDefaultGroup(),
    panelExtra: () => <MainMoreToolbar tabsData={tabsData}/>
  };
};

let defaultLayout = {
  dockbox: {
    mode: 'horizontal',
    children: [
      {
        size: 100,
        id: BROWSER_PANELS.MAIN,
        group: 'playground',
        tabs: defaultTabsData.map((t)=>LayoutDocker.getPanel(t)),
        panelLock: {panelStyle: 'playground'},
      },
    ]
  },
};

function Layouts({browser, platform, topBarMode = 'menu'}) {
  const pgAdmin = usePgAdmin();
  const surfaceHost = useRef(null);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const designStoreClient = useMemo(() => new DesignStoreClient(), []);
  const {
    config, enabled, currentWorkspace,
    setObjectExplorerVisible, changeWorkspace,
  } = useWorkspace();

  const ensureSurfaceHost = useCallback(() => {
    const docker = pgAdmin.Browser.docker.default_workspace;
    if(!docker) throw new Error('The main workbench is not ready.');
    if(!surfaceHost.current || surfaceHost.current.docker !== docker) {
      surfaceHost.current?.dispose();
      surfaceHost.current = new SurfaceHost(docker, undefined, {
        referencePanelId: BROWSER_PANELS.MAIN,
        context: () => ({
          services: {
            'project.assets': platform.projectAssets,
            'schema_compare.runtime': platform.schemaCompare,
            'lineage.runtime': platform.lineage,
            'quality.runtime': platform.quality,
            'contract.runtime': platform.contract,
            'etl.runtime': platform.etl,
            'cdc.runtime': platform.cdc,
            'replication.runtime': platform.replication,
            'tracing.runtime': platform.tracing,
            'migration.runtime': platform.migration,
            'cdeadmin.api.runtime': platform.apiDesigner,
          },
          commands: platform.modules.commands,
          currentUser,
          onCloseBlocked: (_descriptor, reason) =>
            pgAdmin.Browser.notifier.warning(reason),
        }),
      });
    }
    return surfaceHost.current;
  }, [pgAdmin, platform]);

  useEffect(()=>{
    const docker = pgAdmin.Browser.docker.default_workspace;
    if(!docker) return;

    return docker.eventBus.registerListener(
      LAYOUT_EVENTS.RESET, ()=>setObjectExplorerVisible(true));
  }, [setObjectExplorerVisible]);
  useEffect(() => {
    const showInspector = (_item, data) => requestWorkbenchInspection(
      data?._type !== 'cde_resource_group'
    );
    const hideInspector = () => requestWorkbenchInspection(false);
    pgAdmin.Browser.Events.on(
      'pgadmin-browser:node:selected', showInspector
    );
    pgAdmin.Browser.Events.on(
      'pgadmin-browser:node:deselected', hideInspector
    );
    return () => {
      pgAdmin.Browser.Events.off(
        'pgadmin-browser:node:selected', showInspector
      );
      pgAdmin.Browser.Events.off(
        'pgadmin-browser:node:deselected', hideInspector
      );
    };
  }, [pgAdmin]);

  const openPreferences = useCallback((sectionId) => {
    changeWorkspace(WORKSPACES.DEFAULT);
    if(sectionId) requestPreferencesSection(sectionId);
    if (typeof document !== 'undefined' && document.querySelector('[data-cdeadmin-qa-key="project-shell-backdrop"]')) {
      window.dispatchEvent(new CustomEvent('scratchrobin:open-preferences', {
        detail: {mode: 'global', sectionId: sectionId || null},
      }));
      return true;
    }
    setPreferencesOpen(true);
    return true;
  }, [changeWorkspace]);
  const openInterfaceDesigner = useCallback(
    () => openPreferences(DESIGNER_PREFERENCES_ID), [openPreferences]);
  const openAppearanceSettings = useCallback(
    () => openPreferences(APPEARANCE_PREFERENCES_ID), [openPreferences]);
  const openCommandBarCustomizer = useCallback(
    () => openPreferences(`${DESIGNER_PREFERENCES_ID}-command-bar`), [openPreferences]);
  useEffect(() => {
    const context = () => ({
      showActivity: (activityId) => {
        changeWorkspace(WORKSPACES.DEFAULT);
        window.dispatchEvent(new CustomEvent(
          'cdeadmin:show-activity', {detail: activityId}
        ));
      },
      createProject: () => window.dispatchEvent(new CustomEvent(
        'cdeadmin:project-create'
      )),
      openInterfaceDesigner,
      openAppearanceSettings,
      openCommandBarCustomizer,
      service: platform.schemaCompare,
      schemaCompare: platform.schemaCompare,
      lineage: platform.lineage,
      quality: platform.quality,
      contract: platform.contract,
      etl: platform.etl,
      cdc: platform.cdc,
      replication: platform.replication,
      tracing: platform.tracing,
      migration: platform.migration,
      apiDesigner: platform.apiDesigner,
      currentUser,
      openSurface: (surfaceId, input, restoreContext) => ensureSurfaceHost().open(
        surfaceId, input, restoreContext),
    });
    pgAdmin.Browser.CDEadminCommandContext = context;
    return () => {
      if(pgAdmin.Browser.CDEadminCommandContext === context) {
        delete pgAdmin.Browser.CDEadminCommandContext;
      }
    };
  }, [changeWorkspace, ensureSurfaceHost, openAppearanceSettings,
    openCommandBarCustomizer, openInterfaceDesigner, pgAdmin,
    platform.cdc,
    platform.contract, platform.etl,
    platform.lineage, platform.quality,
    platform.apiDesigner, platform.migration, platform.replication, platform.schemaCompare,
    platform.tracing]);
  useEffect(() => {
    const open = (event) => ensureSurfaceHost().open(
      `schema_compare.${event.detail.surface}`, {
        toolInstanceId: `schema-compare-${event.detail.sessionId}`,
        restoreRef: event.detail.sessionId, title: 'Schema Comparison',
      }
    ).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    window.addEventListener('cdeadmin:schema-compare-open', open);
    return () => window.removeEventListener('cdeadmin:schema-compare-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => {
    const open = (event) => ensureSurfaceHost().open(
      `quality.${event.detail.surface}`, {
        toolInstanceId: `quality-${event.detail.sessionId}`,
        restoreRef: event.detail.sessionId, title: 'Data Quality',
      }
    ).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    window.addEventListener('cdeadmin:quality-open', open);
    return () => window.removeEventListener('cdeadmin:quality-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => {
    const open = (event) => ensureSurfaceHost().open(
      `contract.${event.detail.surface}`, {
        toolInstanceId: `contract-${event.detail.sessionId}`,
        restoreRef: event.detail.sessionId, title: 'Data Contract Manager',
      }
    ).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    window.addEventListener('cdeadmin:contract-open', open);
    return () => window.removeEventListener('cdeadmin:contract-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => {
    const open = (event) => ensureSurfaceHost().open(
      `etl.${event.detail.surface}`, {
        toolInstanceId: `etl-${event.detail.sessionId}`,
        restoreRef: event.detail.sessionId, title: 'ETL Designer',
      }
    ).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    window.addEventListener('cdeadmin:etl-open', open);
    return () => window.removeEventListener('cdeadmin:etl-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => {
    const open = (event) => ensureSurfaceHost().open(
      `cdc.${event.detail.surface}`, {
        toolInstanceId: `cdc-${event.detail.sessionId}`,
        restoreRef: event.detail.sessionId, title: 'CDC Designer',
      }
    ).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    window.addEventListener('cdeadmin:cdc-open', open);
    return () => window.removeEventListener('cdeadmin:cdc-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => {
    const open = (event) => ensureSurfaceHost().open(
      `replication.${event.detail.surface}`, {
        toolInstanceId: `replication-${event.detail.sessionId}`,
        restoreRef: event.detail.sessionId, title: 'Replication Topology',
      }
    ).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    window.addEventListener('cdeadmin:replication-open', open);
    return () => window.removeEventListener('cdeadmin:replication-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => {
    const open = (event) => ensureSurfaceHost().open(
      `tracing.${event.detail.surface}`, {
        toolInstanceId: `tracing-${event.detail.sessionId}`,
        restoreRef: event.detail.sessionId, title: 'Distributed Tracing',
      }
    ).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    window.addEventListener('cdeadmin:tracing-open', open);
    return () => window.removeEventListener('cdeadmin:tracing-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => {
    const open = (event) => ensureSurfaceHost().open(
      `migration.${event.detail.surface}`, {
        toolInstanceId: `migration-${event.detail.sessionId}`,
        restoreRef: event.detail.sessionId, title: 'Migration Planning',
      }
    ).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    window.addEventListener('cdeadmin:migration-open', open);
    return () => window.removeEventListener('cdeadmin:migration-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => {
    const open = (event) => ensureSurfaceHost().open(`api.${event.detail.surface}`, {
      toolInstanceId: `api-${event.detail.sessionId}`, restoreRef: event.detail.sessionId,
      title: 'API Designer',
    }).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    window.addEventListener('cdeadmin:api-open', open);
    return () => window.removeEventListener('cdeadmin:api-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => {
    const open = (event) => ensureSurfaceHost().open(
      `lineage.${event.detail.surface}`, {
        toolInstanceId: `lineage-${event.detail.sessionId}`,
        restoreRef: event.detail.sessionId, title: 'Data Lineage',
      }
    ).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    window.addEventListener('cdeadmin:lineage-open', open);
    return () => window.removeEventListener('cdeadmin:lineage-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => bindDesignerOpenEvents(
    ensureSurfaceHost,
    (message) => pgAdmin.Browser.notifier.error(message),
    window
  ), [ensureSurfaceHost, pgAdmin]);
  const openAsset = async (project, asset) => {
    try {
      if(asset.asset_type === NOTEBOOK_TYPE) {
        const guards = createCloseGuardRegistry();
        const id = `sql-notebook-${project.project_id}-${asset.asset_id}`;
        pgAdmin.Browser.docker.default_workspace.openTab({id, title: asset.name,
          closable: true, floatable: true, beforeClose: guards.beforeClose,
          content: <ModalCloseGuardContext.Provider value={guards.register}>
            <SQLNotebook client={platform.projectAssets} initialProjectId={project.project_id} initialAssetId={asset.asset_id} />
          </ModalCloseGuardContext.Provider>}, BROWSER_PANELS.MAIN, 'middle', true);
        return;
      }
      ensureSurfaceHost();
      const candidates = platform.modules.surfaces.list({
        assetType: asset.asset_type,
      });
      const editable = asset.access !== 'viewer' && asset.editor_capable;
      const surface = candidates.find((item) => editable && item.editable) ??
        candidates.find((item) => item.readOnly);
      if(!surface) {
        throw new Error('No registered surface can open asset type ' +
          asset.asset_type + '.');
      }
      await surfaceHost.current.open(surface.id, {
        toolInstanceId: surface.id + '-' + asset.asset_id,
        restoreRef: asset.asset_id,
        projectId: project.project_id,
        title: asset.name,
      });
    } catch(error) {
      pgAdmin.Browser.notifier.error(error.message);
    }
  };

  // Panels outside the Project Explorer (the Diagrams tool) open assets the
  // same way it does.
  const openAssetRef = useRef(openAsset);
  openAssetRef.current = openAsset;
  useEffect(() => {
    const open = (event) => openAssetRef.current(
      event.detail.project, event.detail.asset);
    window.addEventListener('cdeadmin:open-project-asset', open);
    return () => window.removeEventListener('cdeadmin:open-project-asset', open);
  }, []);

  useEffect(() => () => surfaceHost.current?.dispose(), []);

  const buildShellApplication = useCallback(({appId, appMeta, instanceId, sequence}) => {
    const inspectorRightDrawer = () => (
      <InspectorHost
        corePages={[
          {id: 'properties', label: gettext('Properties'), content: <Properties />},
          {id: 'statistics', label: gettext('Statistics'), content: <Statistics />},
          {id: 'dependencies', label: gettext('Dependencies'), content: <Dependencies />},
          {id: 'dependents', label: gettext('Dependents'), content: <Dependents />},
        ]}
      />
    );

    if (appId === 'data-navigator') {
      const selectedItem = pgAdmin?.Browser?.tree?.selected?.() || null;
      const selectedData = selectedItem
        ? pgAdmin?.Browser?.tree?.itemData?.(selectedItem) || null
        : null;
      const navConfig = buildNavigatorSelectionConfig(
        pgAdmin,
        instanceId,
        selectedItem,
        selectedData
      );
      return {
        title: sequence > 1 ? `${appMeta.label} #${sequence}` : appMeta.label,
        supportsLeftDrawer: true,
        supportsRightDrawer: true,
        supportsTabbedIconBar: true,
        actions: navConfig.actions,
        menus: navConfig.menus,
        ribbonTabs: navConfig.ribbonTabs,
        renderLeftDrawer: () => (
          <div style={{height: '100%', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column'}}>
            <ObjectExplorerToolbar />
            <div style={{flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column'}}>
              <ObjectExplorer />
            </div>
          </div>
        ),
        renderWorkArea: () => <DataNavigatorWorkArea instanceId={instanceId} />,
        renderRightDrawer: inspectorRightDrawer,
      };
    }

    const buildDesignerToolbarConfig = (designerAppId, createFn, createText) => {
      const pfx = `${designerAppId}.${instanceId}`;
      const actCreate = `${pfx}.create`;
      const actCut = `${pfx}.cut`;
      const actCopy = `${pfx}.copy`;
      const actPaste = `${pfx}.paste`;
      const actPointer = `${pfx}.select_pointer`;
      const actMarquee = `${pfx}.select_marquee`;
      const actAlign = `${pfx}.align`;
      const actLayers = `${pfx}.layers`;
      const actCheckpoints = `${pfx}.checkpoints`;
      const emitTool = (tool) =>
        window.dispatchEvent(
          new CustomEvent('scratchrobin:designer-tool-action', {
            detail: {appId: designerAppId, instanceId, tool},
          })
        );
      return {
        supportsLeftDrawer: true,
        supportsRightDrawer: true,
        supportsTabbedIconBar: true,
        actions: [
          {
            id: actCreate,
            icon: 'action.new',
            application: designerAppId,
            defaultText: createText,
            defaultHint: createText,
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => createFn()},
          },
          {
            id: actCut,
            icon: 'action.cut',
            application: designerAppId,
            defaultText: gettext('Cut Selection'),
            defaultHint: gettext('Cut selected diagram elements'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitTool('cut')},
          },
          {
            id: actCopy,
            icon: 'action.copy',
            application: designerAppId,
            defaultText: gettext('Copy Selection'),
            defaultHint: gettext('Copy selected diagram elements'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitTool('copy')},
          },
          {
            id: actPaste,
            icon: 'action.paste',
            application: designerAppId,
            defaultText: gettext('Paste Elements'),
            defaultHint: gettext('Paste copied diagram elements'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitTool('paste')},
          },
          {
            id: actPointer,
            icon: 'action.select_pointer',
            application: designerAppId,
            defaultText: gettext('Pointer Select Tool'),
            defaultHint: gettext('Select and move individual elements'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitTool('pointer')},
          },
          {
            id: actMarquee,
            icon: 'action.select_marquee',
            application: designerAppId,
            defaultText: gettext('Marquee Region Select'),
            defaultHint: gettext('Drag rectangular marquee selection'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitTool('marquee')},
          },
          {
            id: actAlign,
            icon: 'action.align',
            application: designerAppId,
            defaultText: gettext('Align & Distribute'),
            defaultHint: gettext('Align selected nodes to layered grid'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitTool('align')},
          },
          {
            id: actLayers,
            icon: 'action.layers',
            application: designerAppId,
            defaultText: gettext('Modelling Layers & Levels'),
            defaultHint: gettext('Switch Conceptual / Logical / Physical / Deployment layer view'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitTool('layers')},
          },
          {
            id: actCheckpoints,
            icon: 'action.checkpoints',
            application: designerAppId,
            defaultText: gettext('Checkpoints & DDN Diff'),
            defaultHint: gettext('Inspect directed save points and version diffs'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitTool('checkpoints')},
          },
        ],
        ribbonTabs: [
          {
            id: `${designerAppId}-tools`,
            label: gettext('Tools'),
            groups: [
              {
                id: `${designerAppId}-edit`,
                label: gettext('Edit'),
                controls: [actCreate, actCut, actCopy, actPaste],
              },
              {
                id: `${designerAppId}-canvas`,
                label: gettext('Canvas'),
                controls: [actPointer, actMarquee, actAlign, actLayers, actCheckpoints],
              },
            ],
          },
        ],
        renderToolbarExtras: () => <DesignerToolbarPalettes appId={designerAppId} />,
      };
    };

    if (appId === 'sql-editor') {
      const runAction = `sql-editor.execute.${instanceId}`;
      const pauseAction = `sql-editor.pause.${instanceId}`;
      const cancelAction = `sql-editor.cancel.${instanceId}`;
      const limitsAction = `sql-editor.limits.${instanceId}`;
      return {
        title: sequence > 1 ? `${appMeta.label} #${sequence}` : appMeta.label,
        supportsLeftDrawer: true,
        supportsRightDrawer: true,
        supportsTabbedIconBar: true,
        actions: [
          {
            id: runAction,
            icon: 'action.execute',
            application: 'sql-editor',
            defaultText: gettext('Execute SQL'),
            defaultHint: gettext('Run active SQL statement'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => true},
          },
          {
            id: pauseAction,
            icon: 'action.query_pause',
            application: 'sql-editor',
            defaultText: gettext('Pause Step Fetch'),
            defaultHint: gettext('Suspend cursor step fetching after current batch'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => true},
          },
          {
            id: cancelAction,
            icon: 'action.stop',
            application: 'sql-editor',
            defaultText: gettext('Cancel Running Query'),
            defaultHint: gettext('Cancel active engine query execution'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => true},
          },
          {
            id: limitsAction,
            icon: 'action.fetch_limits',
            application: 'sql-editor',
            defaultText: gettext('Max Rows & Step Size'),
            defaultHint: gettext('Configure Max Rows and Rows per Step limits'),
            focusScoped: true,
            target: {
              kind: T_ACTION_TARGET_KIND.CLIENT,
              invoke: () =>
                window.dispatchEvent(
                  new CustomEvent('scratchrobin:open-preferences', {
                    detail: {mode: 'global'},
                  })
                ),
            },
          },
        ],
        menus: [
          {
            name: 'query',
            label: gettext('Query'),
            i18nKey: 'menu.query.title',
            index: 25,
            items: [
              {
                id: runAction,
                actionId: runAction,
                label: gettext('Execute SQL'),
                i18nKey: 'menu.query.execute_sql.text',
                hintKey: 'menu.query.execute_sql.hint',
                iconKey: 'action.execute',
                index: 10,
              },
            ],
          },
        ],
        ribbonTabs: [
          {
            id: 'sql-home',
            label: gettext('SQL'),
            groups: [
              {
                id: 'sql-execution',
                label: gettext('Execution'),
                controls: [runAction, pauseAction, cancelAction, limitsAction],
              },
            ],
          },
        ],
        renderLeftDrawer: () => (
          <ProjectExplorer
            client={platform.projectAssets}
            onOpenAsset={openAsset}
          />
        ),
        renderWorkArea: () => <SQLNotebook client={platform.projectAssets} />,
        renderRightDrawer: inspectorRightDrawer,
      };
    }

    if (appId === 'erd-designer') {
      return {
        ...buildDesignerToolbarConfig('erd-designer', requestERDModelCreate, gettext('New Data Model')),
        menus: [
          {
            name: 'model',
            label: gettext('Model'),
            i18nKey: 'menu.model.title',
            index: 30,
            items: [
              {
                id: 'erd.create',
                label: gettext('New Data Model'),
                i18nKey: 'menu.model.new_model.text',
                hintKey: 'menu.model.new_model.hint',
                iconKey: 'tool.erd',
                index: 10,
                callback: () => requestERDModelCreate(),
              },
            ],
          },
        ],
        renderLeftDrawer: () => <ERDModelsNavigator client={designStoreClient} />,
        renderWorkArea: (inst) => (
          <DesignerApplicationWorkArea
            instanceId={inst.instanceId}
            SurfaceComponent={ERDDesignerSurface}
            client={designStoreClient}
            openEvent={ERD_MODEL_OPEN_EVENT}
            onCreate={requestERDModelCreate}
            emptyMessage={gettext(
              'Select an existing data model in the Left Side Drawer or create a new Draft model to begin.'
            )}
            createLabel={gettext('New Data Model')}
            initialProjectId={inst.meta?.projectId || null}
            initialDesignId={inst.meta?.designId || null}
          />
        ),
        renderRightDrawer: inspectorRightDrawer,
      };
    }

    if (appId === 'cube-designer') {
      return {
        ...buildDesignerToolbarConfig('cube-designer', requestCubeCreate, gettext('New Cube')),
        menus: [
          {
            name: 'cube',
            label: gettext('Cube'),
            i18nKey: 'menu.cube.title',
            index: 30,
            items: [
              {
                id: 'cube.create',
                label: gettext('New Cube'),
                i18nKey: 'menu.cube.new_cube.text',
                hintKey: 'menu.cube.new_cube.hint',
                iconKey: 'tool.cube',
                index: 10,
                callback: () => requestCubeCreate(),
              },
            ],
          },
        ],
        renderLeftDrawer: () => <CubesNavigator client={designStoreClient} />,
        renderWorkArea: (inst) => (
          <DesignerApplicationWorkArea
            instanceId={inst.instanceId}
            SurfaceComponent={CubeDesignerSurface}
            client={designStoreClient}
            openEvent={CUBE_OPEN_EVENT}
            onCreate={requestCubeCreate}
            emptyMessage={gettext(
              'Select an existing semantic cube in the Left Side Drawer or create a new Draft cube to begin.'
            )}
            createLabel={gettext('New Cube')}
            initialProjectId={inst.meta?.projectId || null}
            initialDesignId={inst.meta?.designId || null}
          />
        ),
        renderRightDrawer: inspectorRightDrawer,
      };
    }

    if (appId === 'bi-designer') {
      return {
        ...buildDesignerToolbarConfig('bi-designer', requestBIDesignCreate, gettext('New BI Design')),
        menus: [
          {
            name: 'bi',
            label: gettext('BI'),
            i18nKey: 'menu.bi.title',
            index: 30,
            items: [
              {
                id: 'bi.create',
                label: gettext('New BI Design'),
                i18nKey: 'menu.bi.new_design.text',
                hintKey: 'menu.bi.new_design.hint',
                iconKey: 'tool.bi',
                index: 10,
                callback: () => requestBIDesignCreate(),
              },
            ],
          },
        ],
        renderLeftDrawer: () => <BIDesignsNavigator client={designStoreClient} />,
        renderWorkArea: (inst) => (
          <DesignerApplicationWorkArea
            instanceId={inst.instanceId}
            SurfaceComponent={BIDesignerSurface}
            client={designStoreClient}
            openEvent={BI_DESIGN_OPEN_EVENT}
            onCreate={requestBIDesignCreate}
            emptyMessage={gettext(
              'Select an existing BI question or dashboard in the Left Side Drawer or create a new Draft design to begin.'
            )}
            createLabel={gettext('New BI Design')}
            initialProjectId={inst.meta?.projectId || null}
            initialDesignId={inst.meta?.designId || null}
            initialKind={inst.meta?.kind}
          />
        ),
        renderRightDrawer: inspectorRightDrawer,
      };
    }

    if (appId === 'screen-mesh-designer') {
      return {
        ...buildDesignerToolbarConfig('screen-mesh-designer', requestScreenMeshCreate, gettext('New Screen Mesh')),
        menus: [
          {
            name: 'screen_mesh',
            label: gettext('Screen Mesh'),
            i18nKey: 'menu.screen_mesh.title',
            index: 30,
            items: [
              {
                id: 'screen_mesh.create',
                label: gettext('New Screen Mesh'),
                i18nKey: 'menu.screen_mesh.new_mesh.text',
                hintKey: 'menu.screen_mesh.new_mesh.hint',
                iconKey: 'tool.screen-mesh',
                index: 10,
                callback: () => requestScreenMeshCreate(),
              },
            ],
          },
        ],
        renderLeftDrawer: () => <ScreenMeshesNavigator client={designStoreClient} />,
        renderWorkArea: (inst) => (
          <DesignerApplicationWorkArea
            instanceId={inst.instanceId}
            SurfaceComponent={ScreenMeshDesignerSurface}
            client={designStoreClient}
            openEvent={SCREEN_MESH_OPEN_EVENT}
            onCreate={requestScreenMeshCreate}
            emptyMessage={gettext(
              'Select an existing screen mesh or flow in the Left Side Drawer or create a new Draft design to begin.'
            )}
            createLabel={gettext('New Screen Mesh')}
            initialProjectId={inst.meta?.projectId || null}
            initialDesignId={inst.meta?.designId || null}
            initialKind={inst.meta?.kind}
          />
        ),
        renderRightDrawer: inspectorRightDrawer,
      };
    }

    if (appId === 'schema-compare') {
      const scSessionId = `shell-schema-compare-${instanceId}`;
      try {
        platform.schemaCompare.get(scSessionId);
      } catch {
        platform.schemaCompare.create({id: scSessionId});
      }
      const actPickLeft = `schema-compare.pick_left.${instanceId}`;
      const actPickRight = `schema-compare.pick_right.${instanceId}`;
      const actRun = `schema-compare.run.${instanceId}`;
      const actReview = `schema-compare.review.${instanceId}`;
      const scExecuteCommand = (cmdId, args = {}, extra = {}) =>
        platform.modules.commands.execute(
          cmdId,
          {...args, sessionId: scSessionId},
          {
            services: {
              'schema_compare.runtime': platform.schemaCompare,
              'project.assets': platform.projectAssets,
            },
            commands: platform.modules.commands,
            currentUser,
            service: platform.schemaCompare,
            schemaCompare: platform.schemaCompare,
            sessionId: scSessionId,
            ...extra,
          }
        );

      return {
        title: sequence > 1 ? `${appMeta.label} #${sequence}` : appMeta.label,
        supportsLeftDrawer: false,
        supportsRightDrawer: true,
        supportsTabbedIconBar: true,
        actions: [
          {
            id: actPickLeft,
            icon: 'action.endpoint_source',
            application: 'schema-compare',
            defaultText: gettext('Choose Left / Source Endpoint'),
            defaultHint: gettext('Open Source endpoint or DDN asset picker dialog'),
            focusScoped: true,
            target: {
              kind: T_ACTION_TARGET_KIND.CLIENT,
              invoke: () => window.dispatchEvent(new CustomEvent('scratchrobin:schema-compare-pick-left')),
            },
          },
          {
            id: actPickRight,
            icon: 'action.endpoint_target',
            application: 'schema-compare',
            defaultText: gettext('Choose Right / Target Endpoint'),
            defaultHint: gettext('Open Target endpoint or DDN asset picker dialog'),
            focusScoped: true,
            target: {
              kind: T_ACTION_TARGET_KIND.CLIENT,
              invoke: () => window.dispatchEvent(new CustomEvent('scratchrobin:schema-compare-pick-right')),
            },
          },
          {
            id: actRun,
            icon: 'action.compare_run',
            application: 'schema-compare',
            defaultText: gettext('Run Comparison'),
            defaultHint: gettext('Compare selected Source and Target schemas'),
            focusScoped: true,
            target: {
              kind: T_ACTION_TARGET_KIND.CLIENT,
              invoke: () => window.dispatchEvent(new CustomEvent('scratchrobin:schema-compare-run')),
            },
          },
          {
            id: actReview,
            icon: 'action.send_review',
            application: 'schema-compare',
            defaultText: gettext('Send Plan to Review'),
            defaultHint: gettext('Open Change Plan & Native Operation Review'),
            focusScoped: true,
            target: {
              kind: T_ACTION_TARGET_KIND.CLIENT,
              invoke: () => window.dispatchEvent(new CustomEvent('scratchrobin:schema-compare-review')),
            },
          },
        ],
        ribbonTabs: [
          {
            id: 'schema-compare-home',
            label: gettext('Compare'),
            groups: [
              {
                id: 'schema-compare-workflow',
                label: gettext('Workflow'),
                controls: [actPickLeft, actPickRight, actRun, actReview],
              },
            ],
          },
        ],
        renderWorkArea: () => (
          <SchemaCompareWorkspace
            service={platform.schemaCompare}
            sessionId={scSessionId}
            executeCommand={scExecuteCommand}
          />
        ),
        renderRightDrawer: inspectorRightDrawer,
      };
    }

    if (appId === 'project-explorer') {
      return {
        menus: [
          {
            name: 'project',
            label: gettext('Project'),
            i18nKey: 'menu.project.title',
            index: 22,
            items: [
              {
                id: 'project.create',
                label: gettext('New Project'),
                i18nKey: 'menu.project.new_project.text',
                hintKey: 'menu.project.new_project.hint',
                iconKey: 'tool.project-explorer',
                index: 10,
                callback: () =>
                  window.dispatchEvent(new CustomEvent('cdeadmin:project-create')),
              },
            ],
          },
        ],
        renderLeftDrawer: () => (
          <ProjectExplorer
            client={platform.projectAssets}
            onOpenAsset={openAsset}
            onSelectAsset={(project, asset) => {
              workbenchContextService.update({
                surfaceTitle: asset.name,
                projectId: project.project_id,
                assetId: asset.asset_id,
                persistence: 'clean',
                validation:
                  asset.validation_state === 'invalid'
                    ? ['Asset validation failed']
                    : [],
              });
            }}
          />
        ),
        renderWorkArea: () => (
          <ProjectExplorer
            client={platform.projectAssets}
            onOpenAsset={openAsset}
          />
        ),
        renderRightDrawer: inspectorRightDrawer,
      };
    }

    return null;
  }, [designStoreClient, openAsset, pgAdmin, platform.modules.commands, platform.projectAssets, platform.schemaCompare]);

  return (
    <ApplicationStateProvider>
      <ProjectShellProvider
        username={currentUser?.username || currentUser?.email || ''}
        applicationFactory={buildShellApplication}
      >
        {topBarMode === 'notebook' ? <AppNotebookBar /> : <AppMenuBar />}
        <div
          style={{
            height:
              'calc(100% - var(--cde-actual-menu-height, var(--cde-menu-row-height, 32px)))',
          }}
        >
          <ProjectWorkbenchFrame
            fallbackArea3={
              <div style={{height: '100%', width: '100%'}}>
                <Layout
                  getLayoutInstance={(obj) => {
                    pgAdmin.Browser.docker.default_workspace = obj;
                  }}
                  defaultLayout={defaultLayout}
                  layoutId="CDEadmin/Workbench/Main"
                  savedLayout={null}
                  groups={{
                    playground: getMorePanelGroup(defaultTabsData),
                  }}
                  resetToTabPanel={BROWSER_PANELS.MAIN}
                  enableToolEvents
                  isLayoutVisible={!enabled || currentWorkspace == WORKSPACES.DEFAULT}
                />
                {enabled &&
                  config.map((item) => (
                    <Layout
                      key={item.docker}
                      getLayoutInstance={(obj) => {
                        pgAdmin.Browser.docker[item.docker] = obj;
                        obj.eventBus.fireEvent(LAYOUT_EVENTS.INIT);
                      }}
                      defaultLayout={item.layout}
                      layoutId={`Workspace/Layout-${item.workspace}`}
                      savedLayout={pgAdmin.Browser.utils.layout[`Workspace/Layout-${item.workspace}`]}
                      groups={{
                        playground: item?.tabsData
                          ? getMorePanelGroup(item?.tabsData)
                          : {...getDefaultGroup()},
                      }}
                      resetToTabPanel={BROWSER_PANELS.MAIN}
                      isLayoutVisible={currentWorkspace == item.workspace}
                    />
                  ))}
              </div>
            }
          />
        </div>
        <Dialog
          open={preferencesOpen}
          onClose={() => setPreferencesOpen(false)}
          title={gettext('User Preferences')}
          size="large"
          actions={
            <Button onClick={() => setPreferencesOpen(false)}>
              {gettext('Close')}
            </Button>
          }
        >
          <Box sx={{height: '65vh', minHeight: 360}}>
            <PreferencesComponent panelId={BROWSER_PANELS.PREFERENCES} />
          </Box>
        </Dialog>
      </ProjectShellProvider>
    </ApplicationStateProvider>
  );
}

Layouts.propTypes = {
  browser: PropTypes.string,
  platform: PropTypes.object.isRequired,
  topBarMode: PropTypes.string,
};

export default function BrowserComponent({pgAdmin}) {

  const {isLoading, failed, getPreferencesForModule} = usePreferences();
  let { name: browser } = useMemo(()=>getBrowser(), []);
  const [uiReady, setUiReady] = useState(false);
  const [platform, setPlatform] = useState(null);
  const [platformError, setPlatformError] = useState(null);
  const confirmOnClose = getPreferencesForModule('browser').confirm_on_refresh_close;
  useBeforeUnload({
    enabled: confirmOnClose,
    beforeClose: (forceClose)=>{
      window.electronUI?.focus();
      pgAdmin.Browser.notifier.confirm(
        gettext('Quit ScratchRobin'),
        gettext('Are you sure you want to quit the application?'),
        function() { forceClose(); },
        function() { return true; },
        gettext('Yes'),
        gettext('No'),
        'default',
        'id-app-quit'
      );
    },
    isNewTab: true,
  });

  // Called when Install and Restart btn called for auto-update install
  function installUpdate() {
    if (window.electronUI) {
      window.electronUI.sendDataForAppUpdate({
        'install_update_now': true
      });
    }}
  
  // Listen for auto-update events from the Electron main process and display notifications
  // to the user based on the update status (e.g., update available, downloading, downloaded, installed, or error).
  if (window.electronUI && typeof window.electronUI.notifyAppAutoUpdate === 'function') {
    window.electronUI.notifyAppAutoUpdate((data)=>{
      if (data?.check_version_update) {
        pgAdmin.Browser.check_version_update(true);
      } else if (data.update_downloading) {
        appAutoUpdateNotifier('Update downloading.', 'info', null, 10000);
      } else if (data.no_update_available) {
        appAutoUpdateNotifier('No update available.', 'info', null, 10000);
      } else if (data.update_downloaded) {
        const UPDATE_DOWNLOADED_MESSAGE = gettext('An update is ready. Restart the app now to install it, or later to keep using the current version.');
        appAutoUpdateNotifier(UPDATE_DOWNLOADED_MESSAGE, 'warning', installUpdate, null, 'Update downloaded', 'update_downloaded');
      } else if (data.error) {
        appAutoUpdateNotifier(`${data.errMsg}`, 'error');
      } else if (data.update_installed) {
        const UPDATE_INSTALLED_MESSAGE = gettext('Update installed successfully!');
        appAutoUpdateNotifier(UPDATE_INSTALLED_MESSAGE, 'success');
      }
    });
  }

  useEffect(()=>{
    if(uiReady) {
      pgAdmin?.Browser?.uiloaded?.();
    }
  }, [uiReady]);

  useEffect(() => {
    let active = true;
    initializeCDEadminPlatform().then((runtime) => {
      if(active) setPlatform(runtime);
    }).catch((error) => {
      if(active) setPlatformError(error);
    });
    return () => { active = false; };
  }, []);

  if(isLoading) {
    return <></>;
  }
  if(failed) {
    return <>Failed to load preferences</>;
  }
  if(platformError) {
    return <div role="alert">ScratchRobin platform initialization failed: {
      platformError.message}</div>;
  }
  if(!platform) return <></>;

  return (
    <PgAdminProvider value={pgAdmin}>
      <WorkspaceProvider>
        <ModalProvider>
          <NotifierProvider pgAdmin={pgAdmin} pgWindow={pgWindow} onReady={()=>setUiReady(true)}/>
          <Layouts
            browser={browser}
            platform={platform}
            topBarMode={commandBarMode(getPreferencesForModule('misc'))}
          />
        </ModalProvider>
        <ObjectBreadcrumbs pgAdmin={pgAdmin} />
      </WorkspaceProvider>
    </PgAdminProvider>
  );
}

BrowserComponent.propTypes = {
  pgAdmin: PropTypes.object,
};
