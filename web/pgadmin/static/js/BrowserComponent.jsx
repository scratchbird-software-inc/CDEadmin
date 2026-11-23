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
  WORKSPACE_EVENTS as LAYOUT_EVENTS,
  dockTabIconKey,
} from 'sources/cdeadmin_ui/workspace/Workspace';
import EventBus from './helpers/EventBus';
import SQLConnections, {
  SQLConnectionSelect,
  useSQLConnections,
} from './cdeadmin_ui/editors/SQLConnections';
import FormReference from './cdeadmin_ui/navigation/FormReference';
import FirebirdIsql from './Dialogs/FirebirdIsql';
import getApiInstance from './api_instance';
import {translateShell} from './cdeadmin_ui/shell/shellMenuI18n';
import gettext from 'sources/gettext';
import ObjectExplorer from './tree/ObjectExplorer';
import Properties, {resolveConnectorModeSelection} from '../../misc/properties/Properties';
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
import { ApplicationStateProvider } from '../../settings/static/ApplicationStateProvider';
import { appAutoUpdateNotifier } from './helpers/appAutoUpdateNotifier';
import {
  Box,
  Button,
  EmptyState,
  Icon,
  ScratchPopoverPalette,
  ScratchScrollArea,
  initializeCDEadminPlatform,
  ProjectExplorer,
  SurfaceHost,
  InspectorHost,
  APPEARANCE_PREFERENCES_ID,
  DESIGNER_PREFERENCES_ID,
  requestWorkbenchInspection,
  workbenchContextService,
  TextArea,
  ProjectShellProvider,
  ProjectWorkbenchFrame,
  useProjectShell,
  T_ACTION_STATUS,
  T_ACTION_TARGET_KIND,
  t_actions,
} from 'sources/cdeadmin_ui';
import {
  canLaunchServerMenu,
  providerContextMenuItems,
} from '../../browser/static/js/ProviderContextMenu';
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

// Startup shows ONLY the User Dashboard placeholder (no preloaded SQL tab).
export const defaultTabsData = [
  {
    id: BROWSER_PANELS.DASHBOARD, title: gettext('ScratchRobin'),
    tooltip: gettext('ScratchRobin Dashboard'), iconKey: 'tool.scratchrobin',
    content: <Dashboard />, closable: false, group: 'playground'
  },
];

export function formatCatalogPageTitle(nodeData) {
  if (!nodeData || !nodeData._type || nodeData._type === 'server_group') {
    return gettext('Data Navigator');
  }
  const rawLabel = String(
    nodeData.label || nodeData._label || nodeData.cde_database || nodeData.engine_id || nodeData._id || ''
  ).trim();
  const nodeType = String(nodeData._type);
  if (nodeType === 'cde_database_target' || nodeType === 'database') {
    return gettext('database: %s', rawLabel);
  }
  if (nodeType === 'server' || nodeType === 'localhost_placeholder') {
    return gettext('server: %s', rawLabel);
  }
  if (nodeType === 'engine_type') {
    return gettext('connector: %s', rawLabel);
  }
  if (nodeType === 'cde_resource') {
    const kind = String(nodeData.cde_resource_kind || 'object')
      .replace(/_/g, ' ')
      .toLowerCase();
    return `${gettext(kind)}: ${rawLabel}`;
  }
  if (nodeType === 'cde_resource_group' || nodeType.startsWith('coll-')) {
    const stripped = rawLabel.replace(/\s*\(\d+\)\s*$/, '').trim() || rawLabel;
    return gettext(stripped);
  }
  const cleanType = nodeType.replace(/^coll-/, '').replace(/_/g, ' ').toLowerCase();
  return `${gettext(cleanType)}: ${rawLabel}`;
}

export function catalogNodeIdentityKey(nodeData) {
  if (!nodeData || !nodeData._type || nodeData._type === 'server_group') {
    return null;
  }
  const type = String(nodeData._type);
  const idPart =
    nodeData.cde_database_target_id ??
    nodeData.cde_resource_id ??
    nodeData._id ??
    nodeData.id ??
    nodeData.engine_id ??
    nodeData.cde_database ??
    nodeData.label ??
    nodeData._label ??
    '';
  const parentPart =
    nodeData.cde_endpoint_id ??
    nodeData.server_id ??
    nodeData.cde_profile_id ??
    '';
  return `${type}:${parentPart}:${idPart}`;
}

const VIEW_ACTION_META = Object.freeze({
  properties: {
    icon: 'action.properties',
    label: () => gettext('Properties'),
  },
  statistics: {
    icon: 'action.statistics',
    label: () => gettext('Statistics'),
  },
  sql: {
    icon: 'action.sql_preview',
    label: () => gettext('SQL'),
  },
  dependencies: {
    icon: 'action.dependencies',
    label: () => gettext('Dependencies'),
  },
  dependents: {
    icon: 'action.dependents',
    label: () => gettext('Dependents'),
  },
});

export function buildNavigatorSelectionConfig(
  pgAdmin,
  instanceId,
  selectedItem = null,
  selectedData = null,
  activeView = null,
  options = {}
) {
  const nodeType = selectedData?._type || null;
  const pageTitle = formatCatalogPageTitle(selectedData);
  const allowedViews = navigatorTabIdsForNodeType(nodeType, pgAdmin);
  const resolvedView =
    activeView && allowedViews.includes(activeView) ? activeView : allowedViews[0];

  const providerMenus = selectedData
    ? providerContextMenuItems(selectedData, selectedItem) || []
    : [];
  const findProviderSuffix = (suffix) =>
    providerMenus.find((m) => String(m.commandId).split('.').at(-1) === suffix);
  const runProviderMenu = (menu) =>
    menu?.commandHandler?.(
      menu.commandArguments({itemData: selectedData, item: selectedItem}),
      {itemData: selectedData, item: selectedItem}
    );

  const dispatchViewSelect = (viewId, focusEditor = false) => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:navigator-select-tab', {
          detail: {instanceId, tab: viewId, focusEditor},
        })
      );
    }
  };

  const actions = [];
  const viewControlIds = [];
  const connectorModeControlIds = [];
  const pageControlIds = [];
  const catalogControlIds = [];
  const menuItems = [];
  let menuIndex = 5;

  const safeInstId =
    String(instanceId || 'inst')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '') || 'inst';

  // 1. View Switch Icons (Properties, Statistics, SQL, Dependencies, Dependents) — NO tabs in work area
  const objectViews = allowedViews.filter((v) => v !== 'connectors' && VIEW_ACTION_META[v]);
  objectViews.forEach((viewId) => {
    const meta = VIEW_ACTION_META[viewId];
    const actId = `data-navigator.view_${viewId}.${safeInstId}`;
    const labelText = meta.label();
    actions.push({
      id: actId,
      icon: meta.icon,
      application: 'data-navigator',
      defaultText: labelText,
      defaultHint: labelText,
      checked: resolvedView === viewId,
      status: T_ACTION_STATUS.ENABLED,
      focusScoped: true,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => dispatchViewSelect(viewId, viewId === 'properties'),
      },
    });
    viewControlIds.push(actId);
    menuItems.push({
      id: actId,
      actionId: actId,
      label: labelText,
      iconKey: meta.icon,
      checked: resolvedView === viewId,
      index: menuIndex,
    });
    menuIndex += 5;
  });

  if (viewControlIds.length > 0) {
    menuItems.push({id: `sep_views_${instanceId}`, type: 'separator', index: menuIndex});
    menuIndex += 5;
  }

  const pushPageAction = ({key, icon, text, hint, enabled = true, invoke}) => {
    const actId = `data-navigator.${key}.${safeInstId}`;
    actions.push({
      id: actId,
      icon,
      application: 'data-navigator',
      defaultText: text,
      defaultHint: hint || text,
      status: enabled ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
      focusScoped: true,
      target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke},
    });
    pageControlIds.push(actId);
    menuItems.push({
      id: actId,
      actionId: actId,
      label: text,
      iconKey: icon,
      disabled: !enabled,
      index: menuIndex,
    });
    menuIndex += 5;
  };

  // 2. Active Page Action Icons (specific to the open catalog object page)
  if (nodeType === 'cde_database_target' || nodeType === 'database') {
    const connectMenu = findProviderSuffix('connect');
    const studioMenu = findProviderSuffix('studio');
    const editMenu = findProviderSuffix('edit') || findProviderSuffix('alter');
    const dropMenu = findProviderSuffix('drop');
    const dbNode = pgAdmin?.Browser?.Nodes?.database;

    if (connectMenu || nodeType === 'database') {
      const canConnect = connectMenu
        ? Boolean(connectMenu.enable(selectedData, selectedItem))
        : !selectedData?.connected;
      const connectLabel = gettext('Connect');
      pushPageAction({
        key: 'db_connect',
        icon: 'action.connect',
        text: connectLabel,
        hint: (!canConnect && connectMenu?.disabledReason) || connectLabel,
        enabled: canConnect,
        invoke: () => {
          if (connectMenu) {
            runProviderMenu(connectMenu);
          } else {
            dbNode?.callbacks?.connect_database?.call(dbNode, {item: selectedItem});
          }
        },
      });
    }

    const canSql = studioMenu ? Boolean(studioMenu.enable(selectedData, selectedItem)) : true;
    const sqlLabel = gettext('Open SQL Editor');
    pushPageAction({
      key: 'db_open_sql',
      icon: 'action.script',
      text: sqlLabel,
      hint: (!canSql && studioMenu?.disabledReason) || sqlLabel,
      enabled: canSql,
      invoke: () => {
        if (studioMenu) {
          runProviderMenu(studioMenu);
        } else {
          pgAdmin?.DataGrid?.show_query_tool?.('', selectedItem);
        }
      },
    });

    const canEdit = editMenu
      ? Boolean(editMenu.enable(selectedData, selectedItem))
      : Boolean(dbNode);
    const editLabel = gettext('Edit Connection / Settings');
    pushPageAction({
      key: 'db_edit_settings',
      icon: 'action.settings',
      text: editLabel,
      hint: (!canEdit && editMenu?.disabledReason) || editLabel,
      enabled: canEdit,
      invoke: () => {
        if (editMenu) {
          runProviderMenu(editMenu);
        } else {
          dbNode?.callbacks?.show_obj_properties?.call(dbNode, {
            action: 'edit',
            item: selectedItem,
          });
        }
      },
    });

    const canDrop = dropMenu
      ? Boolean(dropMenu.enable(selectedData, selectedItem))
      : Boolean(dbNode);
    const dropLabel = gettext('Drop Database');
    pushPageAction({
      key: 'db_drop',
      icon: 'action.drop',
      text: dropLabel,
      hint: (!canDrop && dropMenu?.disabledReason) || dropLabel,
      enabled: canDrop,
      invoke: () => {
        if (dropMenu) {
          runProviderMenu(dropMenu);
        } else {
          dbNode?.callbacks?.delete_obj?.call(dbNode, {
            item: selectedItem,
            url: 'drop',
          });
        }
      },
    });
  } else if (nodeType === 'server') {
    const serverNode = pgAdmin?.Browser?.Nodes?.server;
    const dbNode = pgAdmin?.Browser?.Nodes?.database;
    const createDbMenu = findProviderSuffix('create_database');
    const registerDbMenu = findProviderSuffix('register_database');
    const forgetMenu = findProviderSuffix('forget');

    const verifyLabel = gettext('Verify / Connect');
    pushPageAction({
      key: 'srv_connect',
      icon: 'action.connect',
      text: verifyLabel,
      hint: verifyLabel,
      enabled: true,
      invoke: () => serverNode?.callbacks?.connect_server?.call(serverNode, {item: selectedItem}),
    });

    if (createDbMenu || !selectedData?.cde_endpoint) {
      const canCreate = createDbMenu
        ? canLaunchServerMenu(createDbMenu, selectedData, selectedItem)
        : Boolean(selectedData?.connected);
      const createLabel = gettext('Create Database');
      pushPageAction({
        key: 'srv_create_db',
        icon: 'action.create_database',
        text: createLabel,
        hint: (!canCreate && createDbMenu?.disabledReason) || createLabel,
        enabled: canCreate,
        invoke: () => {
          if (createDbMenu) {
            runProviderMenu(createDbMenu);
          } else {
            dbNode?.callbacks?.show_obj_properties?.call(dbNode, {
              action: 'create',
              item: selectedItem,
            });
          }
        },
      });
    }

    if (registerDbMenu) {
      const canRegister = canLaunchServerMenu(registerDbMenu, selectedData, selectedItem);
      const registerLabel = gettext('Register Database');
      pushPageAction({
        key: 'srv_register_db',
        icon: 'action.attach',
        text: registerLabel,
        hint: (!canRegister && registerDbMenu?.disabledReason) || registerLabel,
        enabled: canRegister,
        invoke: () => runProviderMenu(registerDbMenu),
      });
    }

    const removeSrvLabel = gettext('Remove Server');
    pushPageAction({
      key: 'srv_remove',
      icon: 'action.delete',
      text: removeSrvLabel,
      hint: removeSrvLabel,
      enabled: true,
      invoke: () => {
        if (forgetMenu && forgetMenu.enable(selectedData, selectedItem)) {
          runProviderMenu(forgetMenu);
          return;
        }
        serverNode?.callbacks?.delete_obj?.call(serverNode, {
          item: selectedItem,
          url: 'drop',
        });
      },
    });
  } else if (nodeType === 'engine_type') {
    const rawEngineId = selectedData.engine_id || selectedData._id || '';
    const engineId = rawEngineId === 'opensearch_sql_ppl' ? 'opensearch' : rawEngineId;
    const {
      profiles,
      profile,
      activeIntent,
      networkSupportsDatabaseIntent,
      networkSupportsCreateIntent,
    } = resolveConnectorModeSelection(
      engineId,
      options.connectorProfileId ?? null,
      options.connectorIntent ?? 'endpoint'
    );

    const pushConnectorModeToggle = ({key, icon, text, checked, detail}) => {
      const actId = `data-navigator.${key}.${safeInstId}`;
      actions.push({
        id: actId,
        icon,
        application: 'data-navigator',
        defaultText: text,
        defaultHint: text,
        checked: Boolean(checked),
        status: T_ACTION_STATUS.ENABLED,
        focusScoped: true,
        target: {
          kind: T_ACTION_TARGET_KIND.CLIENT,
          invoke: () => {
            if (typeof window !== 'undefined') {
              window.dispatchEvent(
                new CustomEvent('scratchrobin:connector-select-mode', {
                  detail: {instanceId, ...detail},
                })
              );
            }
          },
        },
      });
      connectorModeControlIds.push(actId);
      menuItems.push({
        id: actId,
        actionId: actId,
        label: text,
        iconKey: icon,
        checked: Boolean(checked),
        index: menuIndex,
      });
      menuIndex += 5;
    };

    if (profiles.length > 1 && profile) {
      profiles.forEach((candidate, idx) => {
        const isEmbedded = candidate.route_kind === 'embedded_file';
        const baseLabel = candidate.display_name || candidate.engine_display_name || engineId;
        const label = isEmbedded
          ? gettext('%s (This computer)', baseLabel)
          : gettext('%s (Server)', baseLabel);
        const safeKey =
          String(candidate.profile_id || idx)
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, '') || `p${idx}`;
        pushConnectorModeToggle({
          key: `eng_profile_${safeKey}`,
          icon: isEmbedded ? 'action.embedded_host' : 'action.server_host',
          text: label,
          checked: candidate.profile_id === profile.profile_id,
          detail: {profileId: candidate.profile_id},
        });
      });
    }

    if (profile?.route_kind === 'embedded_file') {
      pushConnectorModeToggle({
        key: 'eng_intent_open_file',
        icon: 'action.attach',
        text: gettext('Open Existing File'),
        checked: activeIntent === 'register_existing',
        detail: {intent: 'register_existing'},
      });
      pushConnectorModeToggle({
        key: 'eng_intent_create_file',
        icon: 'action.create_database',
        text: gettext('Create New File'),
        checked: activeIntent === 'create_database',
        detail: {intent: 'create_database'},
      });
    } else if (networkSupportsDatabaseIntent) {
      pushConnectorModeToggle({
        key: 'eng_intent_register_server',
        icon: 'action.connect',
        text: gettext('Register Server'),
        checked: activeIntent === 'endpoint',
        detail: {intent: 'endpoint'},
      });
      pushConnectorModeToggle({
        key: 'eng_intent_register_existing_db',
        icon: 'action.attach',
        text: gettext('Register Existing Database'),
        checked: activeIntent === 'register_existing',
        detail: {intent: 'register_existing'},
      });
      if (networkSupportsCreateIntent) {
        pushConnectorModeToggle({
          key: 'eng_intent_create_db',
          icon: 'action.create_database',
          text: gettext('Create Database'),
          checked: activeIntent === 'create_database',
          detail: {intent: 'create_database'},
        });
      }
    }
  } else if (nodeType === 'coll-database') {
    const dbNode = pgAdmin?.Browser?.Nodes?.database;
    const createLabel = gettext('Create Database');
    pushPageAction({
      key: 'coll_create_db',
      icon: 'action.create_database',
      text: createLabel,
      hint: createLabel,
      enabled: true,
      invoke: () =>
        dbNode?.callbacks?.show_obj_properties?.call(dbNode, {
          action: 'create',
          item: selectedItem,
        }),
    });
  } else if (nodeType === 'cde_resource_group') {
    const createMenu = findProviderSuffix('create');
    const kind = selectedData?.cde_resource_kind;
    if (createMenu || kind) {
      const newLabel =
        createMenu?.label?.replace(/\.{3}|…$/, '') ||
        gettext('New %s', selectedData?.label || kind || 'Object');
      pushPageAction({
        key: 'grp_create',
        icon: 'action.create',
        text: newLabel,
        hint: newLabel,
        enabled: true,
        invoke: () => {
          if (kind && openFamilyCreate(selectedData, selectedItem, kind)) return;
          if (createMenu) runProviderMenu(createMenu);
        },
      });
    }
  } else if (nodeType && nodeType !== 'server_group' && nodeType !== 'localhost_placeholder') {
    const queryMenu = findProviderSuffix('query') || findProviderSuffix('studio');
    const alterMenu = findProviderSuffix('alter') || findProviderSuffix('edit');
    const dropMenu = findProviderSuffix('drop');
    const modNode = pgAdmin?.Browser?.Nodes?.[nodeType];

    if (queryMenu) {
      const canQuery = Boolean(queryMenu.enable(selectedData, selectedItem));
      const sqlLabel = gettext('Open SQL Editor');
      pushPageAction({
        key: 'obj_open_sql',
        icon: 'action.script',
        text: sqlLabel,
        hint: (!canQuery && queryMenu.disabledReason) || sqlLabel,
        enabled: canQuery,
        invoke: () => runProviderMenu(queryMenu),
      });
    }
    if (alterMenu || modNode) {
      const canAlter = alterMenu ? Boolean(alterMenu.enable(selectedData, selectedItem)) : true;
      const editLabel = gettext('Edit / Alter');
      pushPageAction({
        key: 'obj_edit',
        icon: 'action.edit',
        text: editLabel,
        hint: (!canAlter && alterMenu?.disabledReason) || editLabel,
        enabled: canAlter,
        invoke: () => {
          if (alterMenu) {
            runProviderMenu(alterMenu);
          } else {
            modNode?.callbacks?.show_obj_properties?.call(modNode, {
              action: 'edit',
              item: selectedItem,
            });
          }
        },
      });
    }
    if (dropMenu || modNode?.canDrop) {
      const canDrop = dropMenu ? Boolean(dropMenu.enable(selectedData, selectedItem)) : true;
      const dropLabel = gettext('Drop');
      pushPageAction({
        key: 'obj_drop',
        icon: 'action.drop',
        text: dropLabel,
        hint: (!canDrop && dropMenu?.disabledReason) || dropLabel,
        enabled: canDrop,
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
      });
    }
  }

  // 3. Unbound Connectors page action + Catalog Refresh
  if (!nodeType || nodeType === 'server_group') {
    const enginesAction = `data-navigator.engines.${safeInstId}`;
    const enginesLabel = gettext('Configure Database Engines');
    actions.push({
      id: enginesAction,
      icon: 'action.settings',
      application: 'data-navigator',
      defaultText: enginesLabel,
      defaultHint: enginesLabel,
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
    });
    catalogControlIds.push(enginesAction);
    menuItems.push({
      id: enginesAction,
      actionId: enginesAction,
      label: enginesLabel,
      iconKey: 'action.settings',
      index: menuIndex,
    });
    menuIndex += 5;
  }

  if (selectedData && nodeType && nodeType !== 'server_group') {
    const separateTabAction = `data-navigator.open_separate_tab.${safeInstId}`;
    const separateTabLabel = gettext('Open in Separate Tab…');
    actions.push({
      id: separateTabAction,
      icon: 'action.external_link',
      application: 'data-navigator',
      defaultText: separateTabLabel,
      defaultHint: separateTabLabel,
      status: T_ACTION_STATUS.ENABLED,
      focusScoped: true,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () =>
          window.dispatchEvent(
            new CustomEvent('scratchrobin:open-catalog-tab', {
              detail: {item: selectedItem, data: selectedData, activeView: resolvedView},
            })
          ),
      },
    });
    menuItems.push({
      id: separateTabAction,
      actionId: separateTabAction,
      label: separateTabLabel,
      iconKey: 'action.external_link',
      index: menuIndex + 5,
    });
  }

  const refreshAction = `data-navigator.refresh.${safeInstId}`;
  const refreshLabel = gettext('Refresh');
  actions.push({
    id: refreshAction,
    icon: 'action.refresh',
    application: 'data-navigator',
    defaultText: refreshLabel,
    defaultHint: refreshLabel,
    status: T_ACTION_STATUS.ENABLED,
    focusScoped: true,
    target: {
      kind: T_ACTION_TARGET_KIND.CLIENT,
      invoke: () => {
        if (selectedItem && pgAdmin?.Browser?.tree?.refresh) {
          pgAdmin.Browser.tree.refresh(selectedItem);
        } else {
          pgAdmin?.Browser?.Events?.trigger?.('pgadmin-browser:tree:refresh');
        }
      },
    },
  });
  catalogControlIds.push(refreshAction);
  menuItems.push({
    id: refreshAction,
    actionId: refreshAction,
    label: gettext('Refresh Catalog'),
    i18nKey: 'menu.object.refresh_catalog.text',
    hintKey: 'menu.object.refresh_catalog.hint',
    iconKey: 'action.refresh',
    index: menuIndex + 10,
  });

  const groups = [];
  if (viewControlIds.length > 0) {
    groups.push({
      id: 'page-views',
      label: gettext('Views'),
      controls: viewControlIds,
    });
  }
  if (connectorModeControlIds.length > 0) {
    groups.push({
      id: 'page-connector-modes',
      label: gettext('Registration Mode'),
      controls: connectorModeControlIds,
    });
  }
  if (pageControlIds.length > 0) {
    groups.push({
      id: 'page-actions',
      label: gettext('Actions'),
      controls: pageControlIds,
    });
  }
  if (catalogControlIds.length > 0) {
    groups.push({
      id: 'page-catalog',
      label: gettext('Catalog'),
      controls: catalogControlIds,
    });
  }

  return {
    title: pageTitle,
    activeView: resolvedView,
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
        id: `page-${instanceId}`,
        label: pageTitle,
        allowEmpty: true,
        groups,
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
  if (nodeType === 'cde_resource_group') {
    return ['properties'];
  }
  if (String(nodeType).startsWith('coll-')) {
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

export function CatalogPageCoordinator() {
  const shell = useProjectShell();
  const shellRef = useRef(shell);
  shellRef.current = shell;
  const pgAdmin = usePgAdmin();
  const syncingTreeRef = useRef(false);

  const refreshOpenCatalogInstances = useCallback(() => {
    const currentShell = shellRef.current;
    if (!currentShell?.updateInstance) return;
    (currentShell.instances || []).forEach((inst) => {
      if (inst.appId !== 'data-navigator' || inst.meta?.isCustomInlineTab) return;
      const isUnbound = Boolean(inst.meta?.isUnboundNavigator);
      const item = isUnbound ? null : inst.meta?.boundNodeItem || null;
      const liveData = isUnbound
        ? null
        : (item && pgAdmin?.Browser?.tree?.itemData?.(item)) || inst.meta?.boundNodeData || null;
      const cfg = buildNavigatorSelectionConfig(
        pgAdmin,
        inst.instanceId,
        item,
        liveData,
        inst.meta?.activeView || null,
        {
          connectorProfileId: inst.meta?.connectorProfileId,
          connectorIntent: inst.meta?.connectorIntent,
        }
      );
      let nextTitle = cfg.title;
      if (isUnbound) {
        const suffixMatch = String(inst.title || '').match(/\s+(#\d+)$/);
        const baseTitle = translateShell(
          currentShell.locale,
          'app.data-navigator.label',
          gettext('Data Navigator')
        );
        nextTitle = suffixMatch ? `${baseTitle} ${suffixMatch[1]}` : baseTitle;
      }
      currentShell.updateInstance(inst.instanceId, {
        title: nextTitle,
        statusText: `${nextTitle} — ${gettext('Ready')}`,
        actions: cfg.actions,
        menus: cfg.menus,
        ribbonTabs: cfg.ribbonTabs,
        meta: {
          ...inst.meta,
          boundNodeData: liveData,
          activeView: cfg.activeView,
        },
      });
    });
  }, [pgAdmin]);

  useEffect(() => {
    const events = pgAdmin?.Browser?.Events;
    if (!events?.on) return undefined;

    const onTreeSelected = (rawItem, rawData) => {
      if (syncingTreeRef.current) return;
      const currentShell = shellRef.current;
      if (!currentShell) return;
      const item = rawItem || pgAdmin?.Browser?.tree?.selected?.() || null;
      const data = rawData || (item ? pgAdmin?.Browser?.tree?.itemData?.(item) : null);
      if (!data || !data._type || data._type === 'server_group') {
        return;
      }

      const nodeKey = catalogNodeIdentityKey(data);
      if (!nodeKey) return;

      const focused = currentShell.focusedInstance;
      const shouldFocusBrowse =
        !focused ||
        (focused.appId === 'data-navigator' && !focused.meta?.isCustomInlineTab);

      const existing = (currentShell.instances || []).find(
        (inst) =>
          inst.appId === 'data-navigator' &&
          !inst.meta?.isCustomInlineTab &&
          inst.meta?.catalogNodeKey === nodeKey
      );
      if (existing) {
        const cfg = buildNavigatorSelectionConfig(
          pgAdmin,
          existing.instanceId,
          item,
          data,
          existing.meta?.activeView || null,
          {
            connectorProfileId: existing.meta?.connectorProfileId,
            connectorIntent: existing.meta?.connectorIntent,
          }
        );
        currentShell.updateInstance(existing.instanceId, {
          title: cfg.title,
          statusText: `${cfg.title} — ${gettext('Ready')}`,
          actions: cfg.actions,
          menus: cfg.menus,
          ribbonTabs: cfg.ribbonTabs,
          meta: {
            ...existing.meta,
            isUnboundNavigator: false,
            catalogNodeKey: nodeKey,
            boundNodeItem: item,
            boundNodeData: data,
            activeView: cfg.activeView,
          },
        });
        if (shouldFocusBrowse) {
          currentShell.focusInstance(existing.instanceId);
        }
        return;
      }

      const isReplaceableCandidate = (inst) =>
        inst &&
        inst.appId === 'data-navigator' &&
        !inst.meta?.isCustomInlineTab &&
        !inst.meta?.pinnedCatalogTab;

      const replaceable =
        (isReplaceableCandidate(focused) ? focused : null) ||
        [...(currentShell.instances || [])].reverse().find(isReplaceableCandidate);

      if (replaceable) {
        const allowed = navigatorTabIdsForNodeType(data._type, pgAdmin);
        const sameType = replaceable.meta?.boundNodeData?._type === data._type;
        const preservedView = sameType ? replaceable.meta?.activeView : null;
        const initialView =
          preservedView && allowed.includes(preservedView)
            ? preservedView
            : allowed.includes('properties')
              ? 'properties'
              : allowed[0];
        const cfg = buildNavigatorSelectionConfig(
          pgAdmin,
          replaceable.instanceId,
          item,
          data,
          initialView
        );
        currentShell.updateInstance(replaceable.instanceId, {
          title: cfg.title,
          statusText: `${cfg.title} — ${gettext('Ready')}`,
          actions: cfg.actions,
          menus: cfg.menus,
          ribbonTabs: cfg.ribbonTabs,
          meta: {
            ...replaceable.meta,
            isUnboundNavigator: false,
            isReplaceableBrowse: !replaceable.meta?.pinnedWhenBound,
            pinnedCatalogTab: Boolean(replaceable.meta?.pinnedWhenBound),
            catalogNodeKey: nodeKey,
            boundNodeItem: item,
            boundNodeData: data,
            activeView: cfg.activeView,
            connectorProfileId: null,
            connectorIntent: 'endpoint',
          },
        });
        if (shouldFocusBrowse) {
          currentShell.focusInstance(replaceable.instanceId);
        }
        return;
      }

      const allowed = navigatorTabIdsForNodeType(data._type, pgAdmin);
      const initialView = allowed.includes('properties') ? 'properties' : allowed[0];
      currentShell.openApplication('data-navigator', {
        title: formatCatalogPageTitle(data),
        isUnboundNavigator: false,
        isReplaceableBrowse: true,
        catalogNodeKey: nodeKey,
        boundNodeItem: item,
        boundNodeData: data,
        activeView: initialView,
        connectorProfileId: null,
        connectorIntent: 'endpoint',
        leftOpen:
          currentShell.focusedInstance?.supportsLeftDrawer
            ? Boolean(currentShell.shellLeftDrawerOpen)
            : true,
      });
    };

    const onOpenCatalogTabEvent = (ev) => {
      const currentShell = shellRef.current;
      if (!currentShell) return;
      const item = ev?.detail?.item || pgAdmin?.Browser?.tree?.selected?.() || null;
      const data = ev?.detail?.data || (item ? pgAdmin?.Browser?.tree?.itemData?.(item) : null);
      if (!data || !data._type || data._type === 'server_group') return;
      const nodeKey = catalogNodeIdentityKey(data);
      const allowed = navigatorTabIdsForNodeType(data._type, pgAdmin);
      const requestedView = ev?.detail?.activeView;
      const initialView =
        requestedView && allowed.includes(requestedView)
          ? requestedView
          : allowed.includes('properties')
            ? 'properties'
            : allowed[0];
      currentShell.openApplication('data-navigator', {
        title: formatCatalogPageTitle(data),
        isUnboundNavigator: false,
        pinnedCatalogTab: true,
        isReplaceableBrowse: false,
        catalogNodeKey: nodeKey,
        boundNodeItem: item,
        boundNodeData: data,
        activeView: initialView,
        connectorProfileId: null,
        connectorIntent: 'endpoint',
        leftOpen:
          currentShell.focusedInstance?.supportsLeftDrawer
            ? Boolean(currentShell.shellLeftDrawerOpen)
            : true,
      });
    };

    const onCatalogNodeChanged = () => {
      refreshOpenCatalogInstances();
    };

    const onSelectViewEvent = (ev) => {
      const currentShell = shellRef.current;
      if (!currentShell) return;
      const requestedView = ev?.detail?.tab;
      const targetId = ev?.detail?.instanceId || currentShell.focusedId;
      let target = (currentShell.instances || []).find((i) => i.instanceId === targetId);
      if (!ev?.detail?.instanceId && (!target || target.appId !== 'data-navigator' || target.isInlineTab)) {
        target =
          (currentShell.instances || []).find(
            (i) =>
              i.appId === 'data-navigator' &&
              !i.isInlineTab &&
              i.meta?.isReplaceableBrowse !== false
          ) ||
          (currentShell.instances || []).find(
            (i) => i.appId === 'data-navigator' && !i.isInlineTab
          ) ||
          null;
        if (!target && requestedView) {
          const selItem = pgAdmin?.Browser?.tree?.selected?.() || null;
          const selData = (selItem && pgAdmin?.Browser?.tree?.itemData?.(selItem)) || null;
          target = currentShell.openApplication('data-navigator', {
            isUnboundNavigator: !selData,
            isReplaceableBrowse: true,
            boundNodeItem: selItem,
            boundNodeData: selData,
            activeView: requestedView,
          });
        }
      }
      if (target && target.appId === 'data-navigator' && requestedView) {
        const selItem = pgAdmin?.Browser?.tree?.selected?.() || null;
        const selData = (selItem && pgAdmin?.Browser?.tree?.itemData?.(selItem)) || null;
        const isUnbound = selData ? false : Boolean(target.meta?.isUnboundNavigator);
        const item = selItem || (isUnbound ? null : target.meta?.boundNodeItem || null);
        const data =
          selData ||
          (isUnbound
            ? null
            : (item && pgAdmin?.Browser?.tree?.itemData?.(item)) || target.meta?.boundNodeData || null);
        const cfg = buildNavigatorSelectionConfig(
          pgAdmin,
          target.instanceId,
          item,
          data,
          requestedView,
          {
            connectorProfileId: target.meta?.connectorProfileId,
            connectorIntent: target.meta?.connectorIntent,
          }
        );
        currentShell.updateInstance(target.instanceId, {
          title: isUnbound ? target.title : cfg.title,
          actions: cfg.actions,
          menus: cfg.menus,
          ribbonTabs: cfg.ribbonTabs,
          meta: {
            ...target.meta,
            isUnboundNavigator: isUnbound,
            boundNodeItem: item,
            boundNodeData: data,
            catalogNodeKey: isUnbound ? null : catalogNodeIdentityKey(data),
            activeView: cfg.activeView,
          },
        });
        if (ev?.detail?.focusEditor && currentShell.focusedId !== target.instanceId) {
          currentShell.focusInstance(target.instanceId);
        }
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

    const onConnectorModeEvent = (ev) => {
      const currentShell = shellRef.current;
      if (!currentShell) return;
      const targetId = ev?.detail?.instanceId || currentShell.focusedId;
      const target = (currentShell.instances || []).find((i) => i.instanceId === targetId);
      if (!target || target.appId !== 'data-navigator') return;
      const nextProfileId =
        ev?.detail?.profileId !== undefined
          ? ev.detail.profileId
          : target.meta?.connectorProfileId ?? null;
      const nextIntent =
        ev?.detail?.intent !== undefined
          ? ev.detail.intent
          : target.meta?.connectorIntent || 'endpoint';
      const item = target.meta?.boundNodeItem || null;
      const data =
        (item && pgAdmin?.Browser?.tree?.itemData?.(item)) || target.meta?.boundNodeData || null;
      const cfg = buildNavigatorSelectionConfig(
        pgAdmin,
        target.instanceId,
        item,
        data,
        'properties',
        {
          connectorProfileId: nextProfileId,
          connectorIntent: nextIntent,
        }
      );
      currentShell.updateInstance(target.instanceId, {
        actions: cfg.actions,
        menus: cfg.menus,
        ribbonTabs: cfg.ribbonTabs,
        meta: {
          ...target.meta,
          activeView: cfg.activeView,
          connectorProfileId: nextProfileId,
          connectorIntent: nextIntent,
        },
      });
    };

    events.on('pgadmin-browser:tree:selected', onTreeSelected);
    events.on('pgadmin:browser:node:updated', onCatalogNodeChanged);
    events.on('pgadmin-browser:tree:updated', onCatalogNodeChanged);
    events.on('pgadmin:database:connected', onCatalogNodeChanged);
    events.on('pgadmin:server:connected', onCatalogNodeChanged);
    if (typeof window !== 'undefined') {
      window.addEventListener('scratchrobin:navigator-select-tab', onSelectViewEvent);
      window.addEventListener('scratchrobin:connector-select-mode', onConnectorModeEvent);
      window.addEventListener('scratchrobin:open-catalog-tab', onOpenCatalogTabEvent);
      window.addEventListener('scratchrobin:language-changed', onCatalogNodeChanged);
    }

    return () => {
      events.off?.('pgadmin-browser:tree:selected', onTreeSelected);
      events.off?.('pgadmin:browser:node:updated', onCatalogNodeChanged);
      events.off?.('pgadmin-browser:tree:updated', onCatalogNodeChanged);
      events.off?.('pgadmin:database:connected', onCatalogNodeChanged);
      events.off?.('pgadmin:server:connected', onCatalogNodeChanged);
      if (typeof window !== 'undefined') {
        window.removeEventListener('scratchrobin:navigator-select-tab', onSelectViewEvent);
        window.removeEventListener('scratchrobin:connector-select-mode', onConnectorModeEvent);
        window.removeEventListener('scratchrobin:open-catalog-tab', onOpenCatalogTabEvent);
        window.removeEventListener('scratchrobin:language-changed', onCatalogNodeChanged);
      }
    };
  }, [pgAdmin, refreshOpenCatalogInstances]);

  // Keep the tree highlight synchronized when switching between open catalog page tabs
  useEffect(() => {
    const focused = shell?.focusedInstance;
    if (!focused || focused.appId !== 'data-navigator') return;
    const boundItem = focused.meta?.boundNodeItem;
    const tree = pgAdmin?.Browser?.tree;
    if (!boundItem || !tree?.select) return;
    const currentSelected = tree.selected?.();
    if (currentSelected === boundItem) return;
    syncingTreeRef.current = true;
    Promise.resolve(tree.select(boundItem))
      .catch(() => {})
      .finally(() => {
        syncingTreeRef.current = false;
      });
  }, [pgAdmin, shell?.focusedId, shell?.focusedInstance]);

  return null;
}

export function DataNavigatorWorkArea({instanceId}) {
  const shell = useProjectShell();
  const pgAdmin = usePgAdmin();
  const [engines, setEngines] = useState([]);
  const [enginesLoading, setEnginesLoading] = useState(true);
  const [, setLocaleRev] = useState(0);

  const instance =
    shell?.instances?.find((inst) => inst.instanceId === instanceId) || shell?.focusedInstance || null;
  const isUnboundNavigator = instance?.meta?.isUnboundNavigator !== false;
  const boundNodeItem = isUnboundNavigator ? null : instance?.meta?.boundNodeItem || null;
  const boundNodeData = isUnboundNavigator
    ? null
    : (boundNodeItem && pgAdmin?.Browser?.tree?.itemData?.(boundNodeItem)) ||
      instance?.meta?.boundNodeData ||
      null;
  const selectedNodeType = boundNodeData?._type || null;
  const activeView = instance?.meta?.activeView || (selectedNodeType ? 'properties' : 'connectors');

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
    const onLang = (ev) => setLocaleRev((prev) => ev?.detail?.revision ?? prev + 1);
    window.addEventListener('scratchrobin:connectors-changed', onConnectorsChanged);
    window.addEventListener('scratchrobin:language-changed', onLang);
    return () => {
      window.removeEventListener('scratchrobin:connectors-changed', onConnectorsChanged);
      window.removeEventListener('scratchrobin:language-changed', onLang);
    };
  }, [loadEnabledEngines]);

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
    {id: 'connectors', render: renderConnectorsOverview},
    {
      id: 'properties',
      render: () => (
        <Properties boundNodeItem={boundNodeItem} boundNodeData={boundNodeData} />
      ),
    },
    {
      id: 'sql',
      render: () => <SQL boundNodeItem={boundNodeItem} boundNodeData={boundNodeData} />,
    },
    {
      id: 'statistics',
      render: () => (
        <Statistics boundNodeItem={boundNodeItem} boundNodeData={boundNodeData} />
      ),
    },
    {
      id: 'dependencies',
      render: () => (
        <Dependencies boundNodeItem={boundNodeItem} boundNodeData={boundNodeData} />
      ),
    },
    {
      id: 'dependents',
      render: () => (
        <Dependents boundNodeItem={boundNodeItem} boundNodeData={boundNodeData} />
      ),
    },
  ];
  const allowedTabIds = navigatorTabIdsForNodeType(selectedNodeType, pgAdmin);
  const pages = allPages.filter((p) => allowedTabIds.includes(p.id));
  const current = pages.find((p) => p.id === activeView) || pages[0];
  return (
    <Box
      data-cdeadmin-qa-key="data-navigator-work-area"
      data-active-view={current.id}
      sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}
    >
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

export const PLATFORM_MODULE_DEFINITIONS = Object.freeze([
  {slug: 'schema_compare', moduleId: 'cdeadmin.schema_compare', label: () => gettext('Schema Comparison'), iconKey: 'tool.schema-compare'},
  {slug: 'lineage', moduleId: 'cdeadmin.lineage', label: () => gettext('Data Lineage'), iconKey: 'tool.lineage'},
  {slug: 'quality', moduleId: 'cdeadmin.quality', label: () => gettext('Data Quality'), iconKey: 'tool.quality'},
  {slug: 'data_contract', moduleId: 'cdeadmin.contract', label: () => gettext('Data Contract Manager'), iconKey: 'tool.contract'},
  {slug: 'etl', moduleId: 'cdeadmin.etl', label: () => gettext('ETL Designer'), iconKey: 'tool.etl'},
  {slug: 'cdc', moduleId: 'cdeadmin.cdc', label: () => gettext('CDC Designer'), iconKey: 'tool.cdc'},
  {slug: 'replication', moduleId: 'cdeadmin.replication', label: () => gettext('Replication Topology'), iconKey: 'tool.replication'},
  {slug: 'tracing', moduleId: 'cdeadmin.tracing', label: () => gettext('Distributed Tracing'), iconKey: 'tool.tracing'},
  {slug: 'migration', moduleId: 'cdeadmin.migration', label: () => gettext('Migration Planning'), iconKey: 'tool.migration'},
  {slug: 'api', moduleId: 'cdeadmin.api', label: () => gettext('API Designer'), iconKey: 'tool.api'},
  {slug: 'ml_vector', moduleId: 'cdeadmin.ml_vector', label: () => gettext('ML & Vector'), iconKey: 'tool.ml-vector', requiredPermission: 'ml_vector.view'},
  {slug: 'ai', moduleId: 'cdeadmin.ai_interface', preferredSurfaceId: 'cdeadmin.ai_interface.ai_workbench', label: () => gettext('AI Assistant'), iconKey: 'tool.ai', requiredPermission: 'ai.use', aiGated: true},
  {slug: 'ai_interface', moduleId: 'cdeadmin.ai_interface', preferredSurfaceId: 'cdeadmin.ai_interface.ai_admin', label: () => gettext('AI Interface'), iconKey: 'tool.ai', requiredPermission: 'ai.use', aiGated: true},
  {slug: 'discovery_intelligence', moduleId: 'cdeadmin.discovery_intelligence', label: () => gettext('Discovery Intelligence'), iconKey: 'tool.search', requiredPermission: 'discovery.use'},
]);

function sharedObjectExplorerDrawer() {
  return (
    <div style={{height: '100%', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column'}}>
      <ObjectExplorerToolbar />
      <div style={{flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column'}}>
        <ObjectExplorer />
      </div>
    </div>
  );
}

export function SQLStudioApplicationWorkArea({instanceId, projectAssets, initialMode = 'studio'}) {
  const [mode, setMode] = useState(initialMode);
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onMode = (event) => {
      const targetId = event?.detail?.instanceId;
      if (targetId && targetId !== instanceId) return;
      const nextMode = event?.detail?.mode;
      if (nextMode === 'studio' || nextMode === 'notebook') {
        setMode(nextMode);
      }
    };
    window.addEventListener('scratchrobin:sql-editor-mode', onMode);
    return () => window.removeEventListener('scratchrobin:sql-editor-mode', onMode);
  }, [instanceId]);

  return (
    <Box sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}>
      {mode === 'notebook' ? (
        <SQLNotebook client={projectAssets} />
      ) : (
        <SQLConnections instanceId={instanceId} />
      )}
    </Box>
  );
}

SQLStudioApplicationWorkArea.propTypes = {
  instanceId: PropTypes.string,
  projectAssets: PropTypes.object,
  initialMode: PropTypes.string,
};

export function buildSqlStudioShellConfig({
  instanceId,
  title,
  projectAssets,
  renderLeftDrawer = sharedObjectExplorerDrawer,
  renderRightDrawer,
}) {
  const modeStudioAction = `sql-editor.mode.studio.${instanceId}`;
  const modeNotebookAction = `sql-editor.mode.notebook.${instanceId}`;
  const runAction = `sql-editor.execute.${instanceId}`;
  const explainAction = `sql-editor.explain.${instanceId}`;
  const cancelAction = `sql-editor.cancel.${instanceId}`;
  const commitAction = `sql-editor.commit.${instanceId}`;
  const rollbackAction = `sql-editor.rollback.${instanceId}`;
  const builderAction = `sql-editor.builder.${instanceId}`;
  const saveBiAction = `sql-editor.save_bi.${instanceId}`;
  const limitsAction = `sql-editor.limits.${instanceId}`;
  const emitSqlAction = (action) => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('scratchrobin:sql-editor-mode', {
        detail: {instanceId, mode: 'studio'},
      }));
      window.dispatchEvent(new CustomEvent('scratchrobin:sql-editor-action', {
        detail: {instanceId, action},
      }));
    }
    return true;
  };
  return {
    title,
    leftDrawerSharedKey: 'data-navigator:shared-left-tree',
    supportsLeftDrawer: true,
    supportsRightDrawer: true,
    supportsTabbedIconBar: true,
    actions: [
      {
        id: modeStudioAction,
        icon: 'tool.query',
        application: 'sql-editor',
        defaultText: gettext('SQL Studio'),
        defaultHint: gettext('Switch to interactive SQL Studio query editor'),
        focusScoped: true,
        target: {
          kind: T_ACTION_TARGET_KIND.CLIENT,
          invoke: () => window.dispatchEvent(new CustomEvent('scratchrobin:sql-editor-mode', {
            detail: {instanceId, mode: 'studio'},
          })),
        },
      },
      {
        id: modeNotebookAction,
        icon: 'object.notebook',
        application: 'sql-editor',
        defaultText: gettext('SQL Notebook'),
        defaultHint: gettext('Switch to authored project SQL Notebook cells'),
        focusScoped: true,
        target: {
          kind: T_ACTION_TARGET_KIND.CLIENT,
          invoke: () => window.dispatchEvent(new CustomEvent('scratchrobin:sql-editor-mode', {
            detail: {instanceId, mode: 'notebook'},
          })),
        },
      },
      {
        id: runAction,
        icon: 'action.execute',
        application: 'sql-editor',
        defaultText: gettext('Execute SQL'),
        defaultHint: gettext('Run active SQL statement'),
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitSqlAction('execute')},
      },
      {
        id: explainAction,
        icon: 'action.explain',
        application: 'sql-editor',
        defaultText: gettext('Explain Plan'),
        defaultHint: gettext('Generate query execution plan'),
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitSqlAction('explain')},
      },
      {
        id: cancelAction,
        icon: 'action.stop',
        application: 'sql-editor',
        defaultText: gettext('Cancel Running Query'),
        defaultHint: gettext('Cancel active engine query execution'),
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitSqlAction('cancel')},
      },
      {
        id: commitAction,
        icon: 'action.commit',
        application: 'sql-editor',
        defaultText: gettext('Commit'),
        defaultHint: gettext('Commit active transaction'),
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitSqlAction('commit')},
      },
      {
        id: rollbackAction,
        icon: 'action.rollback',
        application: 'sql-editor',
        defaultText: gettext('Rollback'),
        defaultHint: gettext('Roll back active transaction'),
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitSqlAction('rollback')},
      },
      {
        id: builderAction,
        icon: 'action.sql_preview',
        application: 'sql-editor',
        defaultText: gettext('Visual SQL Builder'),
        defaultHint: gettext('Open structured Visual SQL Builder'),
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitSqlAction('sql_builder')},
      },
      {
        id: saveBiAction,
        icon: 'tool.bi',
        application: 'sql-editor',
        defaultText: gettext('Save as BI Question…'),
        defaultHint: gettext('Create a Draft BI Question from the active SQL query'),
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitSqlAction('save_bi_question')},
      },
      {
        id: limitsAction,
        icon: 'action.fetch_limits',
        application: 'sql-editor',
        defaultText: gettext('Max Rows & Step Size'),
        defaultHint: gettext('Configure personal Max Rows and Rows per Step limits'),
        focusScoped: true,
        target: {
          kind: T_ACTION_TARGET_KIND.CLIENT,
          invoke: () =>
            window.dispatchEvent(
              new CustomEvent('scratchrobin:open-preferences', {
                detail: {mode: 'user', sectionId: 'queries'},
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
            callback: () => emitSqlAction('execute'),
          },
          {
            id: explainAction,
            actionId: explainAction,
            label: gettext('Explain Plan'),
            iconKey: 'action.explain',
            index: 15,
            callback: () => emitSqlAction('explain'),
          },
          {
            id: builderAction,
            actionId: builderAction,
            label: gettext('Visual SQL Builder'),
            iconKey: 'action.sql_preview',
            index: 20,
            callback: () => emitSqlAction('sql_builder'),
          },
          {
            id: modeNotebookAction,
            actionId: modeNotebookAction,
            label: gettext('SQL Notebook'),
            iconKey: 'object.notebook',
            index: 30,
            callback: () => window.dispatchEvent(new CustomEvent('scratchrobin:sql-editor-mode', {
              detail: {instanceId, mode: 'notebook'},
            })),
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
            id: 'sql-view-mode',
            label: gettext('Workspace'),
            controls: [modeStudioAction, modeNotebookAction],
          },
          {
            id: 'sql-execution',
            label: gettext('Execution'),
            controls: [runAction, explainAction, cancelAction, commitAction, rollbackAction],
          },
          {
            id: 'sql-authoring',
            label: gettext('Authoring'),
            controls: [builderAction, saveBiAction, limitsAction],
          },
        ],
      },
    ],
    renderLeftDrawer,
    renderWorkArea: () => (
      <SQLStudioApplicationWorkArea
        instanceId={instanceId}
        projectAssets={projectAssets}
      />
    ),
    renderRightDrawer,
  };
}

export function CommandLineWorkArea({instanceId}) {
  const pgAdmin = usePgAdmin();
  const sqlState = useSQLConnections();
  const selectedEntry = useMemo(
    () => sqlState.entries.find((e) => e.id === sqlState.selected) || sqlState.entries[0] || null,
    [sqlState.entries, sqlState.selected]
  );
  const [surfaceMode, setSurfaceMode] = useState('console');
  const [statement, setStatement] = useState('SELECT 1;');
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState([]);
  const sessionsRef = useRef(new Map());
  const statementRef = useRef(statement);
  statementRef.current = statement;

  const postWorkspaceAction = useCallback(async (payload) => {
    const endpointUrl = selectedEntry?.baseEndpointUrl || selectedEntry?.endpointUrl;
    if (!endpointUrl) {
      throw new Error(gettext('Select a connected database first.'));
    }
    const response = await getApiInstance().post(endpointUrl, payload);
    return response?.data?.data ?? response?.data ?? {};
  }, [selectedEntry]);

  const executeStatement = useCallback(async (rawSql) => {
    const sql = String(rawSql ?? statementRef.current ?? '').trim();
    if (!sql) return;
    const endpointUrl = selectedEntry?.baseEndpointUrl || selectedEntry?.endpointUrl;
    if (!endpointUrl) {
      setTranscript((prev) => [
        ...prev,
        {
          id: `cli-${Date.now()}`,
          sql,
          error: gettext('No active database connection selected. Connect to a database in the Data Navigator tree first.'),
        },
      ]);
      return;
    }
    setBusy(true);
    try {
      const api = getApiInstance();
      let sessionMeta = sessionsRef.current.get(selectedEntry.id);
      if (!sessionMeta?.sessionId) {
        const bootResp = await api.get(endpointUrl);
        const boot = bootResp?.data?.data ?? bootResp?.data ?? {};
        const lang = (boot.languages || [])[0] || {};
        const languageProfile = lang.language_profile || 'sql';
        const parameters = lang.parameter_shape === 'array' ? [] : {};
        const openedResp = await api.post(endpointUrl, {
          action: 'open_session',
          language_profile: languageProfile,
          ...(selectedEntry.databaseTargetId
            ? {database_target_id: selectedEntry.databaseTargetId}
            : {}),
        });
        const opened = openedResp?.data?.data ?? openedResp?.data ?? {};
        sessionMeta = {
          sessionId: opened.session_id,
          languageProfile,
          parameters,
        };
        if (sessionMeta.sessionId) {
          sessionsRef.current.set(selectedEntry.id, sessionMeta);
        }
      }
      const execResp = await api.post(endpointUrl, {
        action: 'execute',
        session_id: sessionMeta.sessionId,
        source: sql,
        parameters: sessionMeta.parameters,
        max_rows: 200,
        ...(selectedEntry.databaseTargetId
          ? {database_target_id: selectedEntry.databaseTargetId}
          : {}),
      });
      const execData = execResp?.data?.data ?? execResp?.data ?? {};
      let result = execData;
      const occurrenceId = execData.occurrence_id;
      if (occurrenceId) {
        let attempts = 0;
        do {
          if (attempts > 0) {
            await new Promise((resolve) => setTimeout(resolve, 60));
          }
          attempts += 1;
          const polled = await api.post(endpointUrl, {
            action: 'poll',
            occurrence_id: occurrenceId,
            buffer_rows: 200,
            ...(selectedEntry.databaseTargetId
              ? {database_target_id: selectedEntry.databaseTargetId}
              : {}),
          });
          result = polled?.data?.data ?? polled?.data ?? {};
        } while (
          result.occurrence &&
          !result.occurrence?.operation?.terminal &&
          attempts < 50
        );
      }
      const vm = result.rendered_result?.view_model || result;
      const rawCols = vm.columns || [];
      const rawRows = vm.rows || vm.records || [];
      const opFailed =
        result.occurrence?.operation?.status === 'failed' ||
        result.state === 'failed';
      setTranscript((prev) => [
        ...prev,
        {
          id: `cli-${Date.now()}-${prev.length}`,
          connectionLabel: selectedEntry.label || selectedEntry.id,
          sql,
          columns: rawCols.map((c) => c?.name || c?.label || String(c)),
          rows: rawRows,
          rowCount: vm.row_count ?? rawRows.length,
          state: result.occurrence?.operation?.status || result.state || 'completed',
          error:
            result.occurrence?.operation?.error?.message ||
            result.error?.message ||
            (opFailed ? gettext('Execution failed.') : ''),
        },
      ]);
    } catch (err) {
      setTranscript((prev) => [
        ...prev,
        {
          id: `cli-${Date.now()}-${prev.length}`,
          connectionLabel: selectedEntry?.label || '',
          sql,
          error: err?.response?.data?.errormsg || err?.message || String(err),
        },
      ]);
    } finally {
      setBusy(false);
    }
  }, [selectedEntry]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onAction = (event) => {
      const targetId = event?.detail?.instanceId;
      if (targetId && targetId !== instanceId) return;
      const action = event?.detail?.action;
      if (action === 'execute') executeStatement();
      else if (action === 'clear') setTranscript([]);
      else if (action === 'mode_console') setSurfaceMode('console');
      else if (action === 'mode_firebird_isql') setSurfaceMode('firebird-isql');
      else if (action === 'open_psql') {
        if (typeof pgAdmin?.Tools?.Psql?.openPsqlTool === 'function') {
          pgAdmin.Tools.Psql.openPsqlTool();
        }
      }
    };
    window.addEventListener('scratchrobin:command-line-action', onAction);
    return () => window.removeEventListener('scratchrobin:command-line-action', onAction);
  }, [executeStatement, instanceId, pgAdmin]);

  return (
    <Box
      data-cdeadmin-qa-key="command-line-workspace"
      sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', p: 1.5, gap: 1.5}}
    >
      <Box sx={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap'}}>
        <Box sx={{fontWeight: 600}}>
          {selectedEntry
            ? `${gettext('Active Target')}: ${selectedEntry.engine ? `${selectedEntry.engine} — ` : ''}${selectedEntry.label}`
            : gettext('Select a connected database in the toolbar or Data Navigator tree.')}
        </Box>
        <FormReference formKey="command-line-workspace" />
      </Box>
      {surfaceMode === 'firebird-isql' ? (
        <Box sx={{flex: 1, minHeight: 0, overflow: 'auto'}}>
          <FirebirdIsql
            post={postWorkspaceAction}
            databaseTargetId={selectedEntry?.databaseTargetId || ''}
          />
        </Box>
      ) : (
        <>
          <Box sx={{display: 'flex', gap: 1, alignItems: 'flex-start'}}>
            <Box sx={{flex: 1}}>
              <TextArea
                label={gettext('CLI Statement')}
                value={statement}
                onChange={(e) => setStatement(e?.target ? e.target.value : String(e ?? ''))}
              />
            </Box>
            <Box sx={{display: 'flex', flexDirection: 'column', gap: 1, pt: 3}}>
              <Button intent="primary" loading={busy} onClick={() => executeStatement()}>
                {gettext('Execute Statement')}
              </Button>
              <Button onClick={() => setTranscript([])}>
                {gettext('Clear Console')}
              </Button>
            </Box>
          </Box>
          <ScratchScrollArea orientation="both" style={{flex: 1, minHeight: 140}}>
            <Box
              role="log"
              aria-label={gettext('CLI Transcript')}
              sx={{fontFamily: 'monospace', fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: 1, p: 1}}
            >
              {transcript.length === 0 && (
                <Box sx={{opacity: 0.75}}>
                  {gettext('Ready. Enter a SQL or provider CLI command above and press Execute Statement.')}
                </Box>
              )}
              {transcript.map((entry) => (
                <Box key={entry.id} sx={{border: '1px solid var(--cde-border-subtle, #ccc)', borderRadius: 1, p: 1}}>
                  <Box sx={{fontWeight: 600}}>
                    {entry.connectionLabel ? `[${entry.connectionLabel}] ` : ''}&gt; {entry.sql}
                  </Box>
                  {entry.error ? (
                    <Box role="alert" sx={{color: 'var(--cde-color-danger, #b91c1c)', mt: 0.5}}>
                      {entry.error}
                    </Box>
                  ) : (
                    <Box sx={{mt: 0.5, whiteSpace: 'pre-wrap'}}>
                      {entry.columns?.length > 0 && (
                        <Box sx={{fontWeight: 600}}>{entry.columns.join(' | ')}</Box>
                      )}
                      {(entry.rows || []).slice(0, 50).map((r, idx) => (
                        <Box key={idx}>{Array.isArray(r) ? r.map((v) => (v === null ? 'NULL' : String(v))).join(' | ') : JSON.stringify(r)}</Box>
                      ))}
                      <Box sx={{opacity: 0.75, mt: 0.25}}>
                        {gettext('Rows')}: {entry.rowCount ?? 0}
                      </Box>
                    </Box>
                  )}
                </Box>
              ))}
            </Box>
          </ScratchScrollArea>
        </>
      )}
    </Box>
  );
}

CommandLineWorkArea.propTypes = {
  instanceId: PropTypes.string,
};

export function ProjectShellDockerBridge({config = [], enabled = false, platform = null}) {
  const shell = useProjectShell();
  const pgAdmin = usePgAdmin();
  const shellRef = useRef(shell);
  shellRef.current = shell;
  if (typeof window !== 'undefined') {
    window.__scratchrobinProjectShellRef = shellRef;
  }
  const panelMetaRef = useRef(new Map());

  const adapter = useMemo(() => {
    const eventBus = new EventBus();
    const metaMap = panelMetaRef.current;

    const find = (panelId) => {
      if (panelId === BROWSER_PANELS.MAIN) {
        return {
          id: BROWSER_PANELS.MAIN,
          internal: {title: gettext('Properties'), closable: false},
        };
      }
      const inst = (shellRef.current?.instances || []).find((i) => i.instanceId === panelId);
      if (!inst) return null;
      const stored = metaMap.get(panelId) || {};
      const tabs = (shellRef.current?.instances || []).map((t) => ({
        id: t.instanceId,
        internal: metaMap.get(t.instanceId) || {
          title: t.title,
          iconKey: t.iconKey,
          closable: t.closable !== false,
        },
      }));
      return {
        id: inst.instanceId,
        beforeClose: inst.onBeforeClose,
        metaData: stored.metaData,
        internal: {
          title: inst.title,
          iconKey: inst.iconKey,
          closable: inst.closable !== false,
          ...stored,
        },
        parent: {
          id: BROWSER_PANELS.MAIN,
          activeId: shellRef.current?.focusedId || null,
          tabs,
        },
      };
    };

    const focus = (panelId) => {
      const currentShell = shellRef.current;
      if (!currentShell) return false;
      if (panelId === BROWSER_PANELS.SQL) {
        const exists = (currentShell.instances || []).some(
          (i) => i.instanceId === BROWSER_PANELS.SQL
        );
        if (!exists) {
          const sqlTitle = gettext('SQL Editor');
          metaMap.set(BROWSER_PANELS.SQL, {
            title: sqlTitle,
            iconKey: 'tool.query',
            closable: true,
          });
          const sqlShellCfg = buildSqlStudioShellConfig({
            instanceId: BROWSER_PANELS.SQL,
            title: sqlTitle,
            projectAssets: platform?.projectAssets || null,
            renderLeftDrawer: platform ? sharedObjectExplorerDrawer : null,
            renderRightDrawer: platform ? () => <InspectorHost /> : null,
          });
          currentShell.openInlineTab({
            instanceId: BROWSER_PANELS.SQL,
            appId: 'sql-editor',
            iconKey: 'tool.query',
            closable: true,
            ...sqlShellCfg,
          });
        } else {
          currentShell.focusInstance(BROWSER_PANELS.SQL);
        }
        eventBus.fireEvent(LAYOUT_EVENTS.ACTIVE, BROWSER_PANELS.SQL);
        return true;
      }
      const ok = currentShell.focusInstance(panelId);
      if (ok) {
        eventBus.fireEvent(LAYOUT_EVENTS.ACTIVE, panelId);
      }
      return ok;
    };

    const openTab = (panelData, _refTabId, _direction = 'middle', forceRerender = false) => {
      const currentShell = shellRef.current;
      if (!currentShell || !panelData?.id) return false;
      const existing = (currentShell.instances || []).find((i) => i.instanceId === panelData.id);
      if (existing && !forceRerender) {
        return focus(panelData.id);
      }
      const resolvedTitle = gettext.retranslate(panelData.title || '');
      const resolvedIconKey = dockTabIconKey({
        id: panelData.id,
        title: resolvedTitle,
        icon: panelData.icon,
        iconKey: panelData.iconKey,
      });
      metaMap.set(panelData.id, {
        title: resolvedTitle,
        tooltip: panelData.tooltip ?? resolvedTitle,
        icon: panelData.icon,
        iconKey: resolvedIconKey,
        closable: panelData.closable !== false,
        manualClose: Boolean(panelData.manualClose),
        floatable: panelData.floatable !== false,
        detachable: Boolean(panelData.detachable),
        metaData: panelData.metaData,
      });
      currentShell.openInlineTab({
        instanceId: panelData.id,
        appId: panelData.appId || 'data-navigator',
        title: resolvedTitle,
        iconKey: resolvedIconKey,
        closable: panelData.closable !== false,
        supportsLeftDrawer: panelData.supportsLeftDrawer !== false,
        supportsRightDrawer: panelData.supportsRightDrawer !== false,
        supportsTabbedIconBar: panelData.supportsTabbedIconBar !== false,
        leftDrawerSharedKey: panelData.leftDrawerSharedKey || undefined,
        actions: panelData.actions || [],
        ribbonTabs: panelData.ribbonTabs || [],
        menus: panelData.menus || [],
        renderLeftDrawer: panelData.renderLeftDrawer || undefined,
        renderRightDrawer: panelData.renderRightDrawer || undefined,
        renderToolbarExtras: panelData.renderToolbarExtras || undefined,
        statusText: panelData.statusText || undefined,
        onBeforeClose: panelData.beforeClose || null,
        renderWorkArea: () => panelData.content,
      });
      eventBus.fireEvent(LAYOUT_EVENTS.ACTIVE, panelData.id);
      return true;
    };

    const openDialog = (panelData) =>
      openTab({...panelData, closable: true}, BROWSER_PANELS.MAIN, 'middle', true);

    const close = (panelId, force = false) => {
      const currentShell = shellRef.current;
      if (!currentShell) return false;
      const inst = (currentShell.instances || []).find((i) => i.instanceId === panelId);
      if (!inst) return false;
      const stored = metaMap.get(panelId);
      if (stored?.manualClose && !force) {
        eventBus.fireEvent(LAYOUT_EVENTS.CLOSING, panelId);
        return true;
      }
      const res = currentShell.closeInstance(panelId, {force: Boolean(force)});
      const finalize = (closed) => {
        if (closed === false) return false;
        metaMap.delete(panelId);
        eventBus.fireEvent(LAYOUT_EVENTS.CLOSING, panelId);
        eventBus.fireEvent(LAYOUT_EVENTS.REMOVE, panelId);
        if (shellRef.current?.focusedId) {
          eventBus.fireEvent(LAYOUT_EVENTS.ACTIVE, shellRef.current.focusedId);
        }
        return true;
      };
      if (res && typeof res.then === 'function') {
        return res.then(finalize);
      }
      return finalize(res);
    };

    const closeAll = (panelId, exceptCurrent = false) => {
      const currentShell = shellRef.current;
      if (!currentShell) return;
      (currentShell.instances || []).forEach((inst) => {
        if (inst.closable === false) return;
        if (exceptCurrent && inst.instanceId === panelId) return;
        close(inst.instanceId);
      });
    };

    const setTitle = (panelId, title, icon, tooltip) => {
      const stored = metaMap.get(panelId) || {};
      const nextTitle = title ? gettext.retranslate(title) : stored.title;
      const nextIconKey = icon
        ? dockTabIconKey({id: panelId, title: nextTitle, icon})
        : stored.iconKey;
      metaMap.set(panelId, {
        ...stored,
        ...(nextTitle ? {title: nextTitle} : {}),
        ...(icon ? {icon, iconKey: nextIconKey} : {}),
        ...(tooltip ? {tooltip} : {}),
      });
      shellRef.current?.updateInstance?.(panelId, {
        ...(nextTitle ? {title: nextTitle, statusText: `${nextTitle} — ${gettext('Ready')}`} : {}),
        ...(nextIconKey ? {iconKey: nextIconKey} : {}),
      });
      eventBus.fireEvent(LAYOUT_EVENTS.REFRESH_TITLE, panelId);
    };

    const setInternalAttrs = (panelId, attrs) => {
      const stored = metaMap.get(panelId) || {};
      metaMap.set(panelId, {...stored, ...attrs});
    };

    const getInternalAttrs = (panelId) => metaMap.get(panelId) || find(panelId)?.internal || {};

    return {
      eventBus,
      find,
      findPanels: () =>
        (shellRef.current?.instances || []).map((i) => find(i.instanceId)).filter(Boolean),
      focus,
      openTab,
      openDialog,
      close,
      closeAll,
      isTabOpen: (panelId) => Boolean(find(panelId)),
      isTabVisible: (panelId) => shellRef.current?.focusedId === panelId,
      setTitle,
      setInternalAttrs,
      getInternalAttrs,
      place: () => false,
      moveAdjacent: () => false,
      navigatePanel: () => {},
      resetLayout: () => eventBus.fireEvent(LAYOUT_EVENTS.RESET),
      saveLayout: () => {},
      loadLayout: () => {},
    };
  }, []);

  if (pgAdmin?.Browser?.docker && pgAdmin.Browser.docker.default_workspace !== adapter) {
    pgAdmin.Browser.docker.default_workspace = adapter;
  }

  useEffect(() => {
    if (!pgAdmin?.Browser?.docker) return undefined;
    pgAdmin.Browser.docker.default_workspace = adapter;
    if (enabled && Array.isArray(config)) {
      config.forEach((item) => {
        if (item?.docker) {
          pgAdmin.Browser.docker[item.docker] = adapter;
          adapter.eventBus.fireEvent(LAYOUT_EVENTS.INIT);
        }
      });
    }
    return undefined;
  }, [adapter, config, enabled, pgAdmin]);

  return null;
}

ProjectShellDockerBridge.propTypes = {
  config: PropTypes.array,
  enabled: PropTypes.bool,
  platform: PropTypes.object,
};

function Layouts({browser: _browser, platform, topBarMode = 'menu'}) {
  const pgAdmin = usePgAdmin();
  const surfaceHost = useRef(null);
  const openAssetRef = useRef(null);
  const designStoreClient = useMemo(() => new DesignStoreClient(), []);
  const {
    config, enabled,
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
            'cdeadmin.ai.runtime': platform.ai,
            'cdeadmin.ml_vector.runtime': platform.mlVector,
            'cdeadmin.ai_interface.runtime': platform.aiInterface,
            'cdeadmin.discovery_intelligence.runtime': platform.discoveryIntelligence,
          },
          commands: platform.modules.commands,
          currentUser,
          openSurface: (target, input = {}) => {
            const nextSurfaceId =
              typeof target === 'string'
                ? target
                : target?.toolKind || target?.surfaceId || '';
            if (!nextSurfaceId) return Promise.resolve(null);
            return surfaceHost.current?.open(nextSurfaceId, {
              toolInstanceId: input.toolInstanceId || `surface-${nextSurfaceId}`,
              ...input,
            });
          },
          onCloseBlocked: (_descriptor, reason) =>
            pgAdmin.Browser.notifier.warning(reason),
        }),
        enrichPanel: (descriptor, surfaceId) => {
          let surfaceDef = null;
          try {
            surfaceDef = platform.modules?.surfaces?.get?.(surfaceId) || null;
          } catch {
            surfaceDef = null;
          }
          const moduleId = surfaceDef?.moduleId || '';
          const siblingSurfaces = (platform.modules?.surfaces?.list?.() || [])
            .filter((item) => moduleId && item.moduleId === moduleId)
            .slice(0, 8);
          const surfaceActions = siblingSurfaces.map((sib) => ({
            id: `surface.switch.${descriptor.toolInstanceId}.${sib.id}`,
            icon: sib.iconKey || descriptor.presentation.iconKey || 'command.default',
            application: 'project-explorer',
            defaultText: sib.title,
            defaultHint: sib.title,
            focusScoped: true,
            target: {
              kind: T_ACTION_TARGET_KIND.CLIENT,
              invoke: () =>
                surfaceHost.current?.open(sib.id, {
                  toolInstanceId: `surface-${sib.id}`,
                  restoreRef: descriptor.restoreRef || undefined,
                  projectId: descriptor.projectId || undefined,
                  title: sib.title,
                }),
            },
          }));
          const explorerActionId = `surface.project_explorer.${descriptor.toolInstanceId}`;
          const allActions = [
            ...surfaceActions,
            {
              id: explorerActionId,
              icon: 'tool.project-explorer',
              application: 'project-explorer',
              defaultText: gettext('Project Explorer'),
              defaultHint: gettext('Open Project Explorer workspace'),
              focusScoped: true,
              target: {
                kind: T_ACTION_TARGET_KIND.CLIENT,
                invoke: () =>
                  window.dispatchEvent(
                    new CustomEvent('scratchrobin:open-app-surface', {
                      detail: {appId: 'project-explorer'},
                    })
                  ),
              },
            },
          ];
          const activityItem = (platform.modules?.activity?.list?.() || []).find(
            (act) => moduleId && act.moduleId === moduleId && typeof act.render === 'function'
          );
          return {
            appId: 'project-explorer',
            supportsLeftDrawer: true,
            supportsRightDrawer: true,
            supportsTabbedIconBar: true,
            actions: allActions,
            ribbonTabs: [
              {
                id: `module-ribbon-${descriptor.toolInstanceId}`,
                label: gettext('Workspace'),
                groups: [
                  ...(surfaceActions.length > 0
                    ? [
                      {
                        id: `module-views-${descriptor.toolInstanceId}`,
                        label: gettext('Views'),
                        controls: surfaceActions.map((a) => a.id),
                      },
                    ]
                    : []),
                  {
                    id: `module-nav-${descriptor.toolInstanceId}`,
                    label: gettext('Project'),
                    controls: [explorerActionId],
                  },
                ],
              },
            ],
            leftDrawerSharedKey: activityItem
              ? undefined
              : 'project-explorer:shared-left-tree',
            renderLeftDrawer: () =>
              activityItem ? (
                activityItem.render()
              ) : (
                <ProjectExplorer
                  variant="tree"
                  client={platform.projectAssets}
                  onOpenAsset={(p, a) => openAssetRef.current?.(p, a)}
                />
              ),
            renderRightDrawer: () => <InspectorHost />,
            statusText: `${descriptor.presentation.title} — ${gettext('Ready')}`,
          };
        },
        onStateUpdated: (toolId, state) => {
          const shellApi =
            typeof window !== 'undefined'
              ? window.__scratchrobinProjectShellRef?.current
              : null;
          if (!shellApi?.updateInstance) return;
          const parts = [];
          if (state?.persistence) parts.push(`${gettext('State')}: ${state.persistence}`);
          if (Array.isArray(state?.problems) && state.problems.length > 0) {
            parts.push(`${gettext('Problems')}: ${state.problems.length}`);
          }
          if (state?.activeTaskId) parts.push(`${gettext('Task')}: ${state.activeTaskId}`);
          if (parts.length > 0) {
            shellApi.updateInstance(toolId, {statusText: parts.join(' · ')});
          }
        },
      });
    }
    return surfaceHost.current;
  }, [pgAdmin, platform]);

  const openPlatformModule = useCallback((slug) => {
    const def = PLATFORM_MODULE_DEFINITIONS.find((m) => m.slug === slug);
    if (!def) return null;
    if (def.slug === 'schema_compare') {
      const shellApi =
        typeof window !== 'undefined'
          ? window.__scratchrobinProjectShellRef?.current
          : null;
      if (shellApi?.openApplication) {
        return shellApi.openApplication('schema-compare');
      }
    }
    const allSurfaces = platform.modules?.surfaces?.list?.() || [];
    const primarySurface =
      (def.preferredSurfaceId && allSurfaces.find((s) => s.id === def.preferredSurfaceId)) ||
      allSurfaces.find((s) => s.moduleId === def.moduleId);
    if (!primarySurface) return null;
    return ensureSurfaceHost()
      .open(primarySurface.id, {
        toolInstanceId: `module-${def.slug}-main`,
        title: def.label(),
        iconKey: def.iconKey,
      })
      .catch((error) => pgAdmin.Browser?.notifier?.error?.(error.message));
  }, [ensureSurfaceHost, pgAdmin, platform]);

  const platformModuleLaunchers = useMemo(() => {
    const aiEnabled =
      typeof window === 'undefined' ||
      window.__scratchrobinShellSettings?.global?.ai_drafting_enabled !== false;
    return PLATFORM_MODULE_DEFINITIONS.filter((def) => {
      if (def.aiGated && !aiEnabled) return false;
      if (def.requiredPermission && !t_actions.hasPermission(def.requiredPermission)) {
        return false;
      }
      return true;
    }).map((def) => ({
      id: `module.open.${def.slug}`,
      label: def.label(),
      iconKey: def.iconKey,
      onOpen: () => openPlatformModule(def.slug),
    }));
  }, [openPlatformModule]);

  useEffect(() => {
    const actionIds = PLATFORM_MODULE_DEFINITIONS.map((def) => {
      const actionId = `module.open.${def.slug}`;
      t_actions.upsert({
        id: actionId,
        icon: def.iconKey,
        application: 'project',
        defaultText: def.label(),
        defaultHint: gettext('Open %s workspace', def.label()),
        permission: def.requiredPermission || '',
        status:
          def.aiGated &&
          typeof window !== 'undefined' &&
          window.__scratchrobinShellSettings?.global?.ai_drafting_enabled === false
            ? T_ACTION_STATUS.INVISIBLE
            : T_ACTION_STATUS.ENABLED,
        target: {
          kind: T_ACTION_TARGET_KIND.CLIENT,
          invoke: () => openPlatformModule(def.slug),
        },
      });
      return actionId;
    });
    return () => actionIds.forEach((id) => t_actions.unregister(id));
  }, [openPlatformModule]);

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
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('scratchrobin:open-preferences', {
        detail: {mode: 'user', sectionId: sectionId || null},
      }));
    }
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
      ai: platform.ai,
      mlVector: platform.mlVector,
      aiInterface: platform.aiInterface,
      discoveryIntelligence: platform.discoveryIntelligence,
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
    platform.ai, platform.aiInterface, platform.cdc,
    platform.contract, platform.discoveryIntelligence, platform.etl,
    platform.lineage, platform.mlVector, platform.quality,
    platform.apiDesigner, platform.migration, platform.replication, platform.schemaCompare,
    platform.tracing]);
  useEffect(() => {
    const open = (event) => ensureSurfaceHost().open(
      `ml-vector.${event.detail?.surface || 'vector_explorer'}`, {
        toolInstanceId: `ml-vector-${event.detail?.sessionId || 'main'}`,
        restoreRef: event.detail?.sessionId,
        title: gettext('ML & Vector'),
      }
    ).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    window.addEventListener('cdeadmin:ml-vector-open', open);
    return () => window.removeEventListener('cdeadmin:ml-vector-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => {
    const open = (event) => {
      const requested = event.detail?.screenId || 'cdeadmin.ai_interface.ai_workbench';
      ensureSurfaceHost().open(requested, {
        toolInstanceId: `ai-${event.detail?.sessionId || 'workbench'}`,
        restoreRef: event.detail?.sessionId,
        title: gettext('AI Assistant'),
      }).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    };
    window.addEventListener('cdeadmin:ai-open', open);
    return () => window.removeEventListener('cdeadmin:ai-open', open);
  }, [ensureSurfaceHost, pgAdmin]);
  useEffect(() => {
    const open = (event) => {
      const fallback = (platform.modules?.surfaces?.list?.() || []).find(
        (s) => s.moduleId === 'cdeadmin.ai_interface'
      )?.id;
      const screenId = event.detail?.screenId || fallback;
      if (!screenId) return;
      ensureSurfaceHost().open(screenId, {
        toolInstanceId: `ai-interface-${screenId}`,
        title: gettext('AI Interface'),
      }).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    };
    window.addEventListener('cdeadmin:ai-interface-open', open);
    return () => window.removeEventListener('cdeadmin:ai-interface-open', open);
  }, [ensureSurfaceHost, pgAdmin, platform]);
  useEffect(() => {
    const open = (event) => {
      const fallback = (platform.modules?.surfaces?.list?.() || []).find(
        (s) => s.moduleId === 'cdeadmin.discovery_intelligence'
      )?.id;
      const screenId = event.detail?.screenId || fallback;
      if (!screenId) return;
      ensureSurfaceHost().open(screenId, {
        toolInstanceId: `discovery-${screenId}`,
        title: gettext('Discovery Intelligence'),
      }).catch((error) => pgAdmin.Browser.notifier.error(error.message));
    };
    window.addEventListener('cdeadmin:discovery-open', open);
    return () => window.removeEventListener('cdeadmin:discovery-open', open);
  }, [ensureSurfaceHost, pgAdmin, platform]);
  useEffect(() => {
    const onOpenSqlFromBi = (event) => {
      const detail = event?.detail || {};
      const shellApi =
        typeof window !== 'undefined'
          ? window.__scratchrobinProjectShellRef?.current
          : null;
      const existingSql = (shellApi?.instances || []).find(
        (inst) => inst.appId === 'sql-editor' || inst.instanceId === BROWSER_PANELS.SQL
      );
      if (existingSql) {
        shellApi?.focusInstance?.(existingSql.instanceId);
      } else if (shellApi?.openApplication) {
        shellApi.openApplication('sql-editor');
      } else {
        pgAdmin.Browser.docker?.default_workspace?.focus?.(BROWSER_PANELS.SQL);
      }
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent('cdeadmin:open-sql-in-editor', {detail}));
      }, 0);
    };
    window.addEventListener('scratchrobin:open-sql-from-bi', onOpenSqlFromBi);
    return () => window.removeEventListener('scratchrobin:open-sql-from-bi', onOpenSqlFromBi);
  }, [pgAdmin]);
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
          appId: 'project-explorer',
          leftDrawerSharedKey: 'project-explorer:shared-left-tree',
          renderLeftDrawer: () => (
            <ProjectExplorer
              variant="tree"
              client={platform.projectAssets}
              onOpenAsset={(p, a) => openAssetRef.current?.(p, a)}
            />
          ),
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
        assetType: asset.asset_type,
        projectId: project.project_id,
        title: asset.name,
      });
    } catch(error) {
      pgAdmin.Browser.notifier.error(error.message);
    }
  };

  // Panels outside the Project Explorer (the Diagrams tool) open assets the
  // same way it does.
  openAssetRef.current = openAsset;
  useEffect(() => {
    const open = (event) => openAssetRef.current(
      event.detail.project, event.detail.asset);
    window.addEventListener('cdeadmin:open-project-asset', open);
    return () => window.removeEventListener('cdeadmin:open-project-asset', open);
  }, []);

  useEffect(() => () => surfaceHost.current?.dispose(), []);

  const buildShellApplication = useCallback(({appId, appMeta, instanceId, sequence, options = {}}) => {
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
      const hasBoundNode = Boolean(options.boundNodeData && options.boundNodeData._type);
      const isUnboundNavigator =
        options.isUnboundNavigator !== undefined
          ? Boolean(options.isUnboundNavigator)
          : !hasBoundNode;
      const boundItem = isUnboundNavigator ? null : options.boundNodeItem || null;
      const boundData = isUnboundNavigator ? null : options.boundNodeData || null;
      const navConfig = buildNavigatorSelectionConfig(
        pgAdmin,
        instanceId,
        boundItem,
        boundData,
        options.activeView || null
      );
      const resolvedTitle = isUnboundNavigator
        ? (sequence > 1 ? `${appMeta.label} #${sequence}` : appMeta.label)
        : options.title || navConfig.title;
      return {
        title: resolvedTitle,
        leftDrawerTitle: appMeta.label,
        leftDrawerSharedKey: 'data-navigator:shared-left-tree',
        supportsLeftDrawer: true,
        supportsRightDrawer: true,
        supportsTabbedIconBar: true,
        actions: navConfig.actions,
        menus: navConfig.menus,
        ribbonTabs: navConfig.ribbonTabs,
        meta: {
          isUnboundNavigator,
          pinnedCatalogTab: Boolean(options.pinnedCatalogTab),
          pinnedWhenBound: Boolean(sequence > 1 && isUnboundNavigator && !options.pinnedCatalogTab),
          isReplaceableBrowse: options.pinnedCatalogTab ? false : options.isReplaceableBrowse !== false,
          catalogNodeKey: isUnboundNavigator
            ? null
            : options.catalogNodeKey || catalogNodeIdentityKey(boundData),
          boundNodeItem: boundItem,
          boundNodeData: boundData,
          activeView: navConfig.activeView,
        },
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
      return buildSqlStudioShellConfig({
        instanceId,
        title: sequence > 1 ? `${appMeta.label} #${sequence}` : appMeta.label,
        projectAssets: platform.projectAssets,
        renderRightDrawer: inspectorRightDrawer,
      });
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
        leftDrawerSharedKey: 'project-explorer:shared-left-tree',
        leftDrawerTitle: gettext('Project Navigator'),
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
            variant="tree"
            client={platform.projectAssets}
            onOpenAsset={openAsset}
            modules={platformModuleLaunchers}
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
            variant="workspace"
            client={platform.projectAssets}
            onOpenAsset={openAsset}
            modules={platformModuleLaunchers}
          />
        ),
        renderRightDrawer: inspectorRightDrawer,
      };
    }

    if (appId === 'command-line') {
      const actExec = `command-line.execute.${instanceId}`;
      const actClear = `command-line.clear.${instanceId}`;
      const actConsole = `command-line.mode_console.${instanceId}`;
      const actIsql = `command-line.mode_firebird_isql.${instanceId}`;
      const actPsql = `command-line.open_psql.${instanceId}`;
      const emitCli = (action) =>
        window.dispatchEvent(
          new CustomEvent('scratchrobin:command-line-action', {
            detail: {instanceId, action},
          })
        );
      return {
        title: sequence > 1 ? `${appMeta.label} #${sequence}` : appMeta.label,
        leftDrawerSharedKey: 'data-navigator:shared-left-tree',
        supportsLeftDrawer: true,
        supportsRightDrawer: true,
        supportsTabbedIconBar: true,
        actions: [
          {
            id: actExec,
            icon: 'action.execute',
            application: 'command-line',
            defaultText: gettext('Execute Statement'),
            defaultHint: gettext('Run CLI statement against active database target'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitCli('execute')},
          },
          {
            id: actClear,
            icon: 'action.delete',
            application: 'command-line',
            defaultText: gettext('Clear Console'),
            defaultHint: gettext('Clear command transcript output'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitCli('clear')},
          },
          {
            id: actConsole,
            icon: 'tool.command-line',
            application: 'command-line',
            defaultText: gettext('Interactive CLI Console'),
            defaultHint: gettext('Switch to interactive provider CLI console'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitCli('mode_console')},
          },
          {
            id: actIsql,
            icon: 'tool.command-line',
            application: 'command-line',
            defaultText: gettext('External Firebird ISQL'),
            defaultHint: gettext('Configure and launch external Firebird ISQL terminal'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitCli('mode_firebird_isql')},
          },
          {
            id: actPsql,
            icon: 'tool.psql',
            application: 'command-line',
            defaultText: gettext('PostgreSQL PSQL Tool'),
            defaultHint: gettext('Open native PostgreSQL PSQL terminal session'),
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => emitCli('open_psql')},
          },
        ],
        menus: [
          {
            name: 'terminal',
            label: gettext('Terminal'),
            index: 26,
            items: [
              {
                id: actExec,
                actionId: actExec,
                label: gettext('Execute Statement'),
                iconKey: 'action.execute',
                index: 10,
                callback: () => emitCli('execute'),
              },
              {
                id: actClear,
                actionId: actClear,
                label: gettext('Clear Console'),
                iconKey: 'action.delete',
                index: 15,
                callback: () => emitCli('clear'),
              },
              {
                id: actIsql,
                actionId: actIsql,
                label: gettext('External Firebird ISQL'),
                iconKey: 'tool.command-line',
                index: 25,
                callback: () => emitCli('mode_firebird_isql'),
              },
              {
                id: actPsql,
                actionId: actPsql,
                label: gettext('PostgreSQL PSQL Tool'),
                iconKey: 'tool.psql',
                index: 30,
                callback: () => emitCli('open_psql'),
              },
            ],
          },
        ],
        ribbonTabs: [
          {
            id: 'cli-home',
            label: gettext('Command Line'),
            groups: [
              {
                id: 'cli-exec',
                label: gettext('Execution'),
                controls: [actExec, actClear],
              },
              {
                id: 'cli-shells',
                label: gettext('Engine Terminals'),
                controls: [actConsole, actIsql, actPsql],
              },
            ],
          },
        ],
        renderToolbarExtras: () => <SQLConnectionSelect />,
        renderLeftDrawer: sharedObjectExplorerDrawer,
        renderWorkArea: () => <CommandLineWorkArea instanceId={instanceId} />,
        renderRightDrawer: inspectorRightDrawer,
      };
    }

    return null;
  }, [designStoreClient, openAsset, pgAdmin, platform.modules.commands, platform.projectAssets, platform.schemaCompare, platformModuleLaunchers]);

  return (
    <ApplicationStateProvider>
      <ProjectShellProvider
        username={currentUser?.username || currentUser?.email || ''}
        applicationFactory={buildShellApplication}
      >
        <ProjectShellDockerBridge config={config} enabled={enabled} platform={platform} />
        <CatalogPageCoordinator />
        {topBarMode === 'notebook' ? <AppNotebookBar /> : <AppMenuBar />}
        <div
          style={{
            height:
              'calc(100% - var(--cde-actual-menu-height, var(--cde-menu-row-height, 32px)))',
          }}
        >
          <ProjectWorkbenchFrame />
        </div>
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
