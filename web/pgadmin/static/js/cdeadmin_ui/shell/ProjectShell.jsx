/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  Component,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {createPortal} from 'react-dom';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import usePreferences from '../../../../preferences/static/js/store';
import {NotebookBar} from '../../scratch_notebookbar';
import {COMMAND_BAR_MESSAGES, COMMAND_BAR_THEME} from './commandBarSettings';
import {Box} from '../primitives/Layout';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {Button, IconButton} from '../primitives/Button';
import {StatusBar, Toolbar} from '../layout/WorkbenchChrome';
import {Icon} from '../icons';
import {ProjectNavigationMenuBar} from './ProjectNavigationMenuBar';
import {ProjectVerticalDock} from './ProjectVerticalDock';
import {useProjectShellStyles, DEFAULT_PANEL_GAP_PX} from './ProjectShellStyles';
import {syncShellActionStrings, translateShell} from './shellMenuI18n';
import {
  T_ACTION_STATUS,
  T_ACTION_TARGET_KIND,
  TActionsRegistry,
  t_actions as globalTActions,
  useTActions,
} from '../actions/t_actions';
import {
  PROJECT_TOP_MENU_INDICES,
  ProjectTopMenuRegistry,
} from '../commands/MenuStructure';
import {
  ProjectHelpReferenceDialog,
  ProjectLockScreen,
  ProjectSessionLogoutDialog,
  ProjectSettingsDialog,
} from './ProjectShellDialogs';
import {
  applySchemeAndTypographyToDOM,
  hasStoredSchemeOrTypography,
  readStoredSchemeAndFontState,
} from './colorSchemesAndFonts';
import {
  ACTION_PLACEMENTS_CHANGED_EVENT,
  CANONICAL_ACTION_CATALOG,
  resolveInstanceNotebookBarSpec,
} from './actionPlacementEngine';

export const USER_DASHBOARD_ID = '__user_dashboard__';
const DRAWER_WIDTH_STORAGE_KEY = 'scratchrobin.shell.drawer_widths.v1';
const LAYOUT_PREFS_STORAGE_KEY = 'scratchrobin.shell.layout_prefs.v1';
const INSTANCE_DRAG_MIME = 'application/x-scratchrobin-instance';

export const SHELL_ZOOM_AREA_KEYS = Object.freeze([
  'area_1',
  'area_2',
  'area_3a',
  'area_3b',
  'area_3c',
  'area_3d',
  'area_3e',
]);

export const DEFAULT_AREA_ZOOM_PERCENT = Object.freeze({
  area_1: 100,
  area_2: 100,
  area_3a: 100,
  area_3b: 100,
  area_3c: 100,
  area_3d: 100,
  area_3e: 100,
});

export const DEFAULT_QUICK_ACCESS_IDS = Object.freeze([
  'shell.quick.new',
  'shell.quick.save',
  'shell.quick.undo',
  'shell.quick.redo',
]);

export const DEFAULT_PROJECT_APPLICATIONS = Object.freeze([
  Object.freeze({
    id: 'data-navigator',
    label: 'Data Navigator',
    iconKey: 'tool.data-explorer',
    supportsLeftDrawer: true,
    supportsRightDrawer: true,
    supportsTabbedIconBar: true,
    defaultLeftOpen: true,
  }),
  Object.freeze({
    id: 'sql-editor',
    label: 'SQL Editor',
    iconKey: 'tool.query',
    supportsLeftDrawer: true,
    supportsRightDrawer: true,
    supportsTabbedIconBar: true,
    defaultLeftOpen: false,
  }),
  Object.freeze({
    id: 'erd-designer',
    label: 'ERD & Data Modelling',
    iconKey: 'tool.erd',
    supportsLeftDrawer: true,
    supportsRightDrawer: true,
    supportsTabbedIconBar: true,
    defaultLeftOpen: true,
  }),
  Object.freeze({
    id: 'cube-designer',
    label: 'Cube Designer',
    iconKey: 'tool.cube',
    supportsLeftDrawer: true,
    supportsRightDrawer: true,
    supportsTabbedIconBar: true,
    defaultLeftOpen: true,
  }),
  Object.freeze({
    id: 'bi-designer',
    label: 'BI Questions & Dashboards',
    iconKey: 'tool.bi',
    supportsLeftDrawer: true,
    supportsRightDrawer: true,
    supportsTabbedIconBar: true,
    defaultLeftOpen: true,
  }),
  Object.freeze({
    id: 'screen-mesh-designer',
    label: 'Screen Mesh Designer',
    iconKey: 'tool.screen-mesh',
    supportsLeftDrawer: true,
    supportsRightDrawer: true,
    supportsTabbedIconBar: true,
    defaultLeftOpen: true,
  }),
  Object.freeze({
    id: 'schema-compare',
    label: 'Schema Comparison',
    iconKey: 'tool.schema-compare',
    supportsLeftDrawer: false,
    supportsRightDrawer: true,
    supportsTabbedIconBar: true,
    defaultLeftOpen: false,
  }),
  Object.freeze({
    id: 'project-explorer',
    label: 'Project Explorer',
    iconKey: 'tool.project-explorer',
    supportsLeftDrawer: true,
    supportsRightDrawer: true,
    supportsTabbedIconBar: true,
    defaultLeftOpen: true,
  }),
  Object.freeze({
    id: 'command-line',
    label: 'Command Line',
    iconKey: 'action.terminal',
    supportsLeftDrawer: false,
    supportsRightDrawer: false,
    supportsTabbedIconBar: false,
    defaultLeftOpen: false,
  }),
]);

const DEFAULT_SUPPORTED_LANGUAGES = Object.freeze([
  {code: 'en', label: 'English'},
  {code: 'fr', label: 'Français'},
  {code: 'de', label: 'Deutsch'},
  {code: 'es', label: 'Español'},
  {code: 'ja', label: '日本語'},
]);

function csrfHeaders() {
  if (typeof window === 'undefined') return {};
  const pgAdmin = window.pgAdmin;
  const headerName = pgAdmin?.csrf_token_header || 'X-pgA-CSRFToken';
  const token =
    pgAdmin?.csrf_token ||
    document?.querySelector?.('meta[name="csrf-token"]')?.getAttribute('content') ||
    '';
  return token ? {[headerName]: token} : {};
}

function clampWidth(val, min, max, fallback) {
  const num = Number(val);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(min, Math.min(max, Math.round(num)));
}

export function clampPanelGap(val, fallback = DEFAULT_PANEL_GAP_PX) {
  if (val === null || val === undefined || val === '') return fallback;
  const num = Number(val);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(0, Math.min(24, Math.round(num)));
}

export function clampZoomPercent(val, fallback = 100) {
  if (val === null || val === undefined || val === '') return fallback;
  const num = Number(val);
  if (!Number.isFinite(num) || num <= 0) return fallback;
  return Math.max(70, Math.min(160, Math.round(num)));
}

function loadLocalDrawerWidths() {
  try {
    return JSON.parse(window?.localStorage?.getItem(DRAWER_WIDTH_STORAGE_KEY) || '{}') || {};
  } catch {
    return {};
  }
}

function saveLocalDrawerWidths(map) {
  try {
    window?.localStorage?.setItem(DRAWER_WIDTH_STORAGE_KEY, JSON.stringify(map));
  } catch {
    // Ignore storage quota errors.
  }
}

function loadLocalLayoutPrefs() {
  try {
    return JSON.parse(window?.localStorage?.getItem(LAYOUT_PREFS_STORAGE_KEY) || '{}') || {};
  } catch {
    return {};
  }
}

function saveLocalLayoutPrefs(prefs) {
  try {
    window?.localStorage?.setItem(LAYOUT_PREFS_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Ignore storage quota errors.
  }
}

function resolveCurrentTone(prefStore) {
  if (typeof document !== 'undefined') {
    const attrTone = document.documentElement?.getAttribute('data-cde-theme');
    if (attrTone === 'dark' || attrTone === 'light') return attrTone;
  }
  const rawTheme = String(prefStore?.getPreferences?.('misc', 'theme')?.value || '').toLowerCase();
  if (rawTheme.includes('dark') || rawTheme.includes('contrast')) return 'dark';
  return 'light';
}

/**
 * Single short vertical line resize handle inset just inside the workspace-facing
 * edge of Area 3a (Left Side Drawer, right edge) and Area 3c (Right Side Drawer,
 * left edge), preserving full ARIA separator keyboard and pointer drag semantics.
 */
function DrawerInsetResizeHandle({
  side,
  value,
  min,
  max,
  onChange,
  label,
  invert = false,
}) {
  const startRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const clamp = (next) => Math.max(min, Math.min(max, Math.round(next)));
  const delta = (next) => (invert ? -next : next);

  const handlePointerDown = (event) => {
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    startRef.current = {x: event.clientX, value};
    setDragging(true);
  };

  const handlePointerMove = (event) => {
    if (!startRef.current) return;
    onChange?.(clamp(startRef.current.value + delta(event.clientX - startRef.current.x)));
  };

  const handlePointerUp = (event) => {
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    startRef.current = null;
    setDragging(false);
  };

  return (
    <div
      role="separator"
      tabIndex={0}
      aria-label={label}
      aria-orientation="vertical"
      aria-valuenow={Math.round(value)}
      aria-valuemin={min}
      aria-valuemax={max}
      data-cdeadmin-qa-key={`drawer-resize-${side}`}
      data-dragging={dragging ? 'true' : 'false'}
      className={`sr-drawer-resize-handle sr-drawer-resize-handle--${side}`}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      onKeyDown={(event) => {
        const decrease = event.key === 'ArrowLeft';
        const increase = event.key === 'ArrowRight';
        if (!decrease && !increase) return;
        event.preventDefault();
        const step = event.shiftKey ? 16 : 4;
        onChange?.(clamp(value + delta(increase ? step : -step)));
      }}
    />
  );
}

DrawerInsetResizeHandle.propTypes = {
  side: PropTypes.oneOf(['left', 'right']).isRequired,
  value: PropTypes.number.isRequired,
  min: PropTypes.number.isRequired,
  max: PropTypes.number.isRequired,
  onChange: PropTypes.func,
  label: PropTypes.string.isRequired,
  invert: PropTypes.bool,
};

function copyStylesToPopup(sourceDoc, targetDoc) {
  if (!sourceDoc || !targetDoc || !targetDoc.head) return;
  try {
    targetDoc.documentElement.className = sourceDoc.documentElement.className;
    targetDoc.documentElement.style.cssText = sourceDoc.documentElement.style.cssText;
    targetDoc.body.style.margin = '0';
    targetDoc.body.style.height = '100vh';
    targetDoc.body.style.overflow = 'hidden';
    const nodes = sourceDoc.querySelectorAll('link[rel="stylesheet"], style');
    nodes.forEach((node) => {
      targetDoc.head.appendChild(node.cloneNode(true));
    });
  } catch {
    // Cross-window or JSDOM partial environment.
  }
}

const ProjectShellContext = createContext(null);

export function useProjectShell() {
  return useContext(ProjectShellContext);
}

/**
 * Renders a detached floating application instance into its native pop-out
 * browser window with ONLY its Main Work Area + bottom Status Area (zero
 * repeated Top Menu, Tabbed-Icon-Bar, Side Menu, or Left/Right Drawers).
 */
function FloatingSubFormPortal({
  instance,
  locked,
  showStatusBar,
  onFocusInstance,
  onRedockInstance,
  onBeginDragBack,
}) {
  if (!instance?.detached || !instance?.popupContainer) return null;

  const content = locked ? (
    <Box
      data-cdeadmin-qa-key={`floating-locked-${instance.instanceId}`}
      sx={{
        height: '100vh',
        width: '100vw',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        color: 'text.secondary',
        fontSize: '0.875rem',
      }}
    >
      {gettext('Session locked — unlock on the main ScratchRobin window.')}
    </Box>
  ) : (
    <Box
      data-cdeadmin-qa-key={`floating-subform-${instance.instanceId}`}
      onPointerDown={() => onFocusInstance?.(instance.instanceId)}
      sx={{
        height: '100%',
        width: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        bgcolor: 'background.default',
        color: 'text.primary',
      }}
    >
      <Box
        data-cdeadmin-qa-key={`floating-workarea-${instance.instanceId}`}
        sx={{flex: 1, minHeight: 0, overflow: 'auto', position: 'relative'}}
      >
        {typeof instance.renderWorkArea === 'function'
          ? instance.renderWorkArea(instance)
          : instance.workArea}
      </Box>
      {showStatusBar && (
        <StatusBar label={`${instance.title} status`}>
          <Box sx={{flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis'}}>
            {typeof instance.renderStatus === 'function'
              ? instance.renderStatus(instance)
              : instance.statusText || `${instance.title} (Floating)`}
          </Box>
          <Box
            component="button"
            type="button"
            draggable
            data-cdeadmin-qa-key={`floating-redock-${instance.instanceId}`}
            onDragStart={(e) => {
              e.dataTransfer?.setData(INSTANCE_DRAG_MIME, instance.instanceId);
              onBeginDragBack?.(instance.instanceId);
            }}
            onClick={() => onRedockInstance?.(instance.instanceId)}
            style={{
              cursor: 'grab',
              border: '1px solid currentColor',
              background: 'transparent',
              color: 'inherit',
              fontSize: '0.75rem',
              padding: '1px 6px',
            }}
            title={gettext('Drag onto Area 3 or click to re-dock as a tab')}
          >
            {gettext('Dock to Main Area')}
          </Box>
        </StatusBar>
      )}
    </Box>
  );

  return createPortal(content, instance.popupContainer);
}

FloatingSubFormPortal.propTypes = {
  instance: PropTypes.object,
  locked: PropTypes.bool,
  showStatusBar: PropTypes.bool,
  onFocusInstance: PropTypes.func,
  onRedockInstance: PropTypes.func,
  onBeginDragBack: PropTypes.func,
};

/**
 * Central provider and state machine for the standardized ScratchRobin
 * Project Framework & Application Shell (`docs/en_US/project_shell_behaviour.rst`).
 */
export function ProjectShellProvider({
  children,
  applications: suppliedApplications = DEFAULT_PROJECT_APPLICATIONS,
  applicationFactory,
  userDashboard = null,
  actionsRegistry: suppliedActionsRegistry = null,
  menuRegistry: suppliedMenuRegistry = null,
  fetchImpl = null,
  openPopupWindow = null,
  username = '',
  onOpenDataSources = null,
  onOpenPreferences = null,
  onLogout = null,
  initialLocked = false,
  onTeardownStep = null,
}) {
  const actionsRegistry = useMemo(
    () => suppliedActionsRegistry || globalTActions || new TActionsRegistry(),
    [suppliedActionsRegistry]
  );
  const menuRegistry = useMemo(
    () => suppliedMenuRegistry || new ProjectTopMenuRegistry(),
    [suppliedMenuRegistry]
  );
  const runFetch = useMemo(() => {
    const base =
      fetchImpl || (typeof fetch === 'function' ? (...a) => fetch(...a) : null);
    if (!base) return null;
    return (url, init = {}) =>
      base(url, {
        credentials: 'same-origin',
        ...init,
        headers: {...csrfHeaders(), ...(init.headers || {})},
      });
  }, [fetchImpl]);

  const instanceCounter = useRef(0);
  const draggedFloatingRef = useRef(null);

  const [catalogApps, setCatalogApps] = useState(() => {
    const list = [...suppliedApplications];
    const navIdx = list.findIndex((a) => a.id === 'data-navigator');
    if (navIdx > 0) {
      const [nav] = list.splice(navIdx, 1);
      list.unshift(nav);
    }
    return list.map((a) => ({...a, authorized: a.authorized !== false}));
  });

  const [settings, setSettings] = useState(() => {
    const localWidths = loadLocalDrawerWidths();
    const localLayout = loadLocalLayoutPrefs();
    const appsMap = {};
    suppliedApplications.forEach((app) => {
      const appLayout = localLayout.applications?.[app.id] || {};
      appsMap[app.id] = {
        show_tabbed_icon_bar: app.supportsTabbedIconBar !== false,
        default_left_drawer_open: Boolean(app.defaultLeftOpen),
        default_right_drawer_open: false,
        default_right_drawer_mode: 'properties',
        left_drawer_width: clampWidth(localWidths[app.id]?.left, 180, 640, 288),
        right_drawer_width: clampWidth(localWidths[app.id]?.right, 200, 640, 320),
        default_sql_reference_script: '',
        panel_gap:
          appLayout.panel_gap === null || appLayout.panel_gap === undefined || appLayout.panel_gap === ''
            ? null
            : clampPanelGap(appLayout.panel_gap),
        area_zoom: appLayout.area_zoom && typeof appLayout.area_zoom === 'object'
          ? {...appLayout.area_zoom}
          : {},
      };
    });
    return {
      global: {
        default_tabbed_icon_bar: true,
        lock_screen_timeout_minutes: 15,
        panel_gap: clampPanelGap(localLayout.global?.panel_gap, DEFAULT_PANEL_GAP_PX),
        area_zoom: {
          ...DEFAULT_AREA_ZOOM_PERCENT,
          ...(localLayout.global?.area_zoom || {}),
        },
      },
      applications: appsMap,
    };
  });

  const [languages, setLanguages] = useState(DEFAULT_SUPPORTED_LANGUAGES);
  const [locale, setLocaleState] = useState('en');

  useEffect(() => {
    syncShellActionStrings(actionsRegistry);
    actionsRegistry.setLocale(locale);
  }, [actionsRegistry, locale]);
  const [locked, setLocked] = useState(Boolean(initialLocked));
  const [lockBusy, setLockBusy] = useState(false);
  const [lockError, setLockError] = useState('');
  const [sessionDialogOpen, setSessionDialogOpen] = useState(false);
  const [settingsDialog, setSettingsDialog] = useState({
    open: false,
    mode: 'global',
    appId: null,
    initialSection: null,
  });
  const [helpTopic, setHelpTopic] = useState('');

  useEffect(() => {
    if (!hasStoredSchemeOrTypography()) return;
    const stored = readStoredSchemeAndFontState();
    applySchemeAndTypographyToDOM(stored, {persistLocal: false, syncPreferences: false});
  }, []);

  const [instances, setInstances] = useState([]);
  // Focused target: an instanceId (docked or floating), USER_DASHBOARD_ID, or null.
  const [focusedId, setFocusedId] = useState(null);
  const [dashboardTabbed, setDashboardTabbed] = useState(false);
  const [showStatusBar, setShowStatusBar] = useState(true);
  const [toolbarRibbonOverride, setToolbarRibbonOverride] = useState(null);

  // Explicit observable shell states governed by Teardown-Before-Activate:
  const [shellLeftDrawerOpen, setShellLeftDrawerOpen] = useState(false);
  const [activeSettingsAppId, setActiveSettingsAppId] = useState(null);
  const [teardownHistory, setTeardownHistory] = useState([]);

  const instancesRef = useRef(instances);
  instancesRef.current = instances;
  const focusedIdRef = useRef(focusedId);
  focusedIdRef.current = focusedId;

  const authorizedApps = useMemo(() => {
    const permitted = catalogApps.filter((a) => a.authorized !== false);
    const navIdx = permitted.findIndex((a) => a.id === 'data-navigator');
    if (navIdx > 0) {
      const [nav] = permitted.splice(navIdx, 1);
      permitted.unshift(nav);
    }
    return permitted;
  }, [catalogApps]);

  const focusedInstance = useMemo(
    () => instances.find((item) => item.instanceId === focusedId) || null,
    [instances, focusedId]
  );

  const dockedInstances = useMemo(
    () => instances.filter((item) => !item.detached),
    [instances]
  );

  // User Dashboard Lifecycle rule:
  // If User Dashboard was opened as a tab and all other docked tabs are closed
  // or detached, its tab disappears and it reverts to normal placeholder mode.
  useEffect(() => {
    if (dashboardTabbed && dockedInstances.length === 0) {
      setDashboardTabbed(false);
      if (focusedId === USER_DASHBOARD_ID) {
        setFocusedId(null);
      }
    }
  }, [dashboardTabbed, dockedInstances.length, focusedId]);

  /**
   * Deterministic 4-Step Teardown-Before-Activate Protocol:
   * 1. Remove outgoing menus & set outgoing focus-scoped t_actions to 'invisible'
   * 2. Close Left Side Drawer & disable Area 2 Left Drawer Toggle ('disabled')
   * 3. Clear Application Settings target on Area 2 Gear (null / 'disabled')
   * 4. Activate incoming application instance (if any)
   */
  const executeFocusTransition = useCallback(
    (nextTargetId, nextInstancesList = instancesRef.current) => {
      const prevInstance =
        nextInstancesList.find((i) => i.instanceId === focusedIdRef.current) ||
        instancesRef.current.find((i) => i.instanceId === focusedIdRef.current) ||
        null;

      const recordStep = (step, detail) => {
        onTeardownStep?.(step, detail);
        setTeardownHistory((prev) => [...prev.slice(-24), {step, ...detail}]);
      };

      // Step 1: Unmerge/remove outgoing menus & hide focus-scoped t_actions
      menuRegistry.clearFocusedApplicationMenus();
      actionsRegistry.deactivateApplication(prevInstance?.appId || null);
      recordStep('1.menus_cleared', {outgoingAppId: prevInstance?.appId || null});

      // Step 2: Reset Left Side Drawer to closed & grey out Area 2 toggle
      setShellLeftDrawerOpen(false);
      if (actionsRegistry.has('shell.left_drawer.toggle')) {
        actionsRegistry.setChecked('shell.left_drawer.toggle', false);
        actionsRegistry.setStatus('shell.left_drawer.toggle', T_ACTION_STATUS.DISABLED);
      }
      recordStep('2.left_drawer_reset', {leftDrawerOpen: false, toggleStatus: 'disabled'});

      // Step 3: Clear Application Settings on Area 2 Gear
      setActiveSettingsAppId(null);
      if (actionsRegistry.has('shell.settings.application')) {
        actionsRegistry.setStatus('shell.settings.application', T_ACTION_STATUS.DISABLED);
      }
      recordStep('3.app_settings_cleared', {activeSettingsAppId: null});

      // Step 4: Activate incoming application instance (if focusing an app)
      const incoming =
        nextTargetId && nextTargetId !== USER_DASHBOARD_ID
          ? nextInstancesList.find((i) => i.instanceId === nextTargetId) || null
          : null;

      setFocusedId(incoming ? incoming.instanceId : nextTargetId === USER_DASHBOARD_ID ? USER_DASHBOARD_ID : null);

      if (incoming) {
        if (Array.isArray(incoming.actions)) {
          incoming.actions.forEach((act) => {
            actionsRegistry.upsert({
              ...act,
              application: incoming.appId,
              focusScoped: act.focusScoped !== false,
            });
          });
        }
        actionsRegistry.activateApplication(incoming.appId, incoming.actionStatuses || {});

        const resolvedMenus =
          typeof incoming.buildMenus === 'function'
            ? incoming.buildMenus(incoming)
            : incoming.menus || [];
        if (resolvedMenus.length > 0) {
          menuRegistry.setFocusedApplicationMenus(incoming.instanceId, resolvedMenus);
        }

        const leftSupported = Boolean(incoming.supportsLeftDrawer);
        const restoredLeftOpen = leftSupported && Boolean(incoming.leftOpen);
        setShellLeftDrawerOpen(restoredLeftOpen);
        if (actionsRegistry.has('shell.left_drawer.toggle')) {
          actionsRegistry.setStatus(
            'shell.left_drawer.toggle',
            leftSupported ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED
          );
          actionsRegistry.setChecked('shell.left_drawer.toggle', restoredLeftOpen);
        }

        setActiveSettingsAppId(incoming.appId);
        if (actionsRegistry.has('shell.settings.application')) {
          actionsRegistry.setStatus('shell.settings.application', T_ACTION_STATUS.ENABLED);
        }
        recordStep('4.incoming_activated', {
          instanceId: incoming.instanceId,
          appId: incoming.appId,
          leftDrawerOpen: restoredLeftOpen,
          activeSettingsAppId: incoming.appId,
        });
      }
    },
    [actionsRegistry, menuRegistry, onTeardownStep]
  );

  // Build default instance configuration when launching an application
  const createDefaultInstanceSpec = useCallback(
    (appMeta, instanceId, seq, options = {}) => {
      const appCfg = settings?.applications?.[appMeta.id] || {};
      const defaultLeftOpen =
        options.leftOpen !== undefined
          ? Boolean(options.leftOpen)
          : appCfg.default_left_drawer_open !== undefined
            ? Boolean(appCfg.default_left_drawer_open)
            : Boolean(appMeta.defaultLeftOpen);
      const defaultRightOpen =
        options.rightOpen !== undefined
          ? Boolean(options.rightOpen)
          : Boolean(appCfg.default_right_drawer_open);
      const defaultRightMode =
        options.rightMode || appCfg.default_right_drawer_mode || 'properties';

      const custom =
        typeof applicationFactory === 'function'
          ? applicationFactory({
            appId: appMeta.id,
            appMeta,
            instanceId,
            sequence: seq,
            options,
            settings: appCfg,
          })
          : null;

      const title =
        options.title ||
        custom?.title ||
        (seq > 1 ? `${appMeta.label} #${seq}` : appMeta.label);

      const inspectActionId = `${appMeta.id}.inspect`;
      const rightHistoryActionId = `${appMeta.id}.history`;

      const defaultActions =
        custom?.actions || [
          {
            id: inspectActionId,
            icon: 'action.properties',
            application: appMeta.id,
            defaultText: gettext('Properties'),
            defaultHint: gettext('Toggle Properties in Right Side Drawer'),
            focusScoped: true,
            target: {
              kind: T_ACTION_TARGET_KIND.CLIENT,
              invoke: () => {
                toggleInstanceRightDrawerRef.current?.(instanceId, 'properties');
              },
            },
          },
          {
            id: rightHistoryActionId,
            icon: 'action.history',
            application: appMeta.id,
            defaultText: gettext('History'),
            defaultHint: gettext('Toggle History in Right Side Drawer'),
            focusScoped: true,
            target: {
              kind: T_ACTION_TARGET_KIND.CLIENT,
              invoke: () => {
                toggleInstanceRightDrawerRef.current?.(instanceId, 'history');
              },
            },
          },
        ];

      const defaultRibbonTabs =
        custom?.ribbonTabs ||
        (appMeta.supportsTabbedIconBar !== false
          ? [
            {
              id: `${appMeta.id}-home`,
              label: appMeta.label,
              groups: [
                {
                  id: `${appMeta.id}-inspect-group`,
                  label: gettext('Inspect'),
                  controls: [inspectActionId, rightHistoryActionId],
                },
              ],
            },
          ]
          : []);

      return {
        instanceId,
        appId: appMeta.id,
        title,
        iconKey: custom?.iconKey || appMeta.iconKey || 'command.default',
        detached: false,
        popupWindow: null,
        popupContainer: null,
        supportsLeftDrawer:
          custom?.supportsLeftDrawer !== undefined
            ? Boolean(custom.supportsLeftDrawer)
            : Boolean(appMeta.supportsLeftDrawer),
        supportsRightDrawer:
          custom?.supportsRightDrawer !== undefined
            ? Boolean(custom.supportsRightDrawer)
            : Boolean(appMeta.supportsRightDrawer),
        supportsTabbedIconBar:
          custom?.supportsTabbedIconBar !== undefined
            ? Boolean(custom.supportsTabbedIconBar)
            : appMeta.supportsTabbedIconBar !== false,
        leftOpen: defaultLeftOpen,
        rightOpen: defaultRightOpen,
        rightMode: defaultRightMode,
        rightViews: custom?.rightViews || [
          {id: 'properties', label: gettext('Properties')},
          {id: 'history', label: gettext('History')},
        ],
        actions: defaultActions,
        actionStatuses: custom?.actionStatuses || {},
        menus: custom?.menus || [],
        buildMenus: custom?.buildMenus || null,
        ribbonTabs: defaultRibbonTabs,
        quickAccess: custom?.quickAccess || options.quickAccess || DEFAULT_QUICK_ACCESS_IDS,
        quickActions: custom?.quickActions || options.quickActions || null,
        statusText: custom?.statusText || `${title} — Ready`,
        workArea: custom?.workArea || null,
        renderWorkArea:
          custom?.renderWorkArea ||
          ((inst) =>
            inst.workArea || (
              <Box sx={{p: 2}}>
                <Box sx={{fontWeight: 600, mb: 0.5}}>{inst.title}</Box>
                <Box sx={{fontSize: '0.875rem', color: 'text.secondary'}}>
                  {gettext('Active work surface for %s.', inst.title)}
                </Box>
              </Box>
            )),
        renderLeftDrawer:
          custom?.renderLeftDrawer ||
          ((inst) => (
            <Box sx={{p: 1.5, fontSize: '0.8125rem'}}>
              {gettext('%s Navigation', inst.title)}
            </Box>
          )),
        renderRightDrawer:
          custom?.renderRightDrawer ||
          ((inst) => (
            <Box sx={{p: 1.5, fontSize: '0.8125rem'}}>
              {gettext('%s — %s', inst.title, inst.rightMode)}
            </Box>
          )),
        renderToolbarExtras: custom?.renderToolbarExtras || options?.renderToolbarExtras || null,
        renderStatus: custom?.renderStatus || null,
        onBeforeClose: custom?.onBeforeClose || null,
        meta: {...options, ...(custom?.meta || {})},
      };
    },
    [applicationFactory, settings]
  );

  const toggleInstanceRightDrawerRef = useRef(null);

  const openApplication = useCallback(
    (appId, options = {}) => {
      const appMeta = authorizedApps.find((a) => a.id === appId);
      if (!appMeta) return null;
      instanceCounter.current += 1;
      const sameTypeCount =
        instancesRef.current.filter((i) => i.appId === appId).length + 1;
      const instanceId =
        options.instanceId || `${appId}-${instanceCounter.current}`;
      const newInstance = createDefaultInstanceSpec(
        appMeta,
        instanceId,
        sameTypeCount,
        options
      );
      const nextList = [...instancesRef.current, newInstance];
      instancesRef.current = nextList;
      setInstances(nextList);
      setToolbarRibbonOverride(null);
      executeFocusTransition(instanceId, nextList);
      return newInstance;
    },
    [authorizedApps, createDefaultInstanceSpec, executeFocusTransition]
  );

  const openInlineTab = useCallback(
    (tabSpec = {}) => {
      const targetAppId = tabSpec.appId || 'data-navigator';
      const existing =
        tabSpec.instanceId &&
        instancesRef.current.find((i) => i.instanceId === tabSpec.instanceId);
      if (existing) {
        const updatedList = instancesRef.current.map((item) =>
          item.instanceId === existing.instanceId
            ? {
              ...item,
              ...tabSpec,
              instanceId: existing.instanceId,
              appId: existing.appId,
            }
            : item
        );
        instancesRef.current = updatedList;
        setInstances(updatedList);
        executeFocusTransition(existing.instanceId, updatedList);
        return updatedList.find((i) => i.instanceId === existing.instanceId);
      }

      instanceCounter.current += 1;
      const instanceId =
        tabSpec.instanceId || `inline-${targetAppId}-${instanceCounter.current}`;
      const parentAppInstance = instancesRef.current.find(
        (i) => i.appId === targetAppId && typeof i.renderLeftDrawer === 'function'
      );
      const supportsLeft = Boolean(tabSpec.supportsLeftDrawer);
      const newTab = {
        instanceId,
        appId: targetAppId,
        title: tabSpec.title || gettext('Object Editor'),
        iconKey: tabSpec.iconKey || 'object.table',
        supportsLeftDrawer: supportsLeft,
        supportsRightDrawer: tabSpec.supportsRightDrawer !== false,
        supportsTabbedIconBar: tabSpec.supportsTabbedIconBar !== false,
        leftOpen:
          typeof tabSpec.leftOpen === 'boolean'
            ? tabSpec.leftOpen
            : Boolean(supportsLeft && parentAppInstance?.leftOpen),
        rightOpen: Boolean(tabSpec.rightOpen),
        rightMode: tabSpec.rightMode || 'properties',
        rightViews: tabSpec.rightViews || [{id: 'properties', label: gettext('Properties')}],
        detached: false,
        popupWindow: null,
        popupContainer: null,
        actions: tabSpec.actions || [],
        menus: tabSpec.menus || [],
        ribbonTabs: tabSpec.ribbonTabs || [],
        quickAccess: tabSpec.quickAccess || null,
        quickActions: tabSpec.quickActions || null,
        statusText: tabSpec.statusText || gettext('Inline Editor — Ready'),
        renderWorkArea:
          tabSpec.renderWorkArea ||
          (() => <Box sx={{p: 2}}>{tabSpec.title || gettext('Object Editor')}</Box>),
        renderLeftDrawer:
          tabSpec.renderLeftDrawer ||
          (supportsLeft && parentAppInstance?.renderLeftDrawer) ||
          (() => null),
        renderRightDrawer:
          tabSpec.renderRightDrawer ||
          ((inst) =>
            inst.inspectorNode || (
              <Box sx={{p: 1.5, fontSize: '0.8125rem', color: 'text.secondary'}}>
                {gettext('Select a subnode row or element to inspect extended properties.')}
              </Box>
            )),
        renderToolbarExtras: tabSpec.renderToolbarExtras || null,
        renderStatus: tabSpec.renderStatus || null,
        onBeforeClose: tabSpec.onBeforeClose || null,
        inspectorNode: tabSpec.inspectorNode || null,
        meta: {...(tabSpec.meta || {})},
      };

      const nextList = [...instancesRef.current, newTab];
      instancesRef.current = nextList;
      setInstances(nextList);
      setToolbarRibbonOverride(null);
      executeFocusTransition(instanceId, nextList);
      return newTab;
    },
    [executeFocusTransition]
  );

  const focusInstance = useCallback(
    (targetId) => {
      if (targetId === USER_DASHBOARD_ID) {
        if (focusedIdRef.current !== USER_DASHBOARD_ID) {
          executeFocusTransition(USER_DASHBOARD_ID, instancesRef.current);
        }
        return true;
      }
      const target = instancesRef.current.find((i) => i.instanceId === targetId);
      if (!target) return false;
      if (target.detached && target.popupWindow && !target.popupWindow.closed) {
        try {
          target.popupWindow.focus?.();
        } catch {
          // Ignore focus restrictions.
        }
      }
      if (focusedIdRef.current !== targetId) {
        executeFocusTransition(targetId, instancesRef.current);
      }
      return true;
    },
    [executeFocusTransition]
  );

  const openUserDashboardTab = useCallback(() => {
    const hasDockedApps = instancesRef.current.some((i) => !i.detached);
    if (hasDockedApps) {
      setDashboardTabbed(true);
      executeFocusTransition(USER_DASHBOARD_ID, instancesRef.current);
    } else {
      setDashboardTabbed(false);
      executeFocusTransition(null, instancesRef.current);
    }
  }, [executeFocusTransition]);

  const closeInstance = useCallback(
    (targetId = focusedIdRef.current) => {
      if (!targetId) return false;
      if (targetId === USER_DASHBOARD_ID) {
        if (!dashboardTabbed) return false;
        setDashboardTabbed(false);
        const fallbackDocked = instancesRef.current.filter((i) => !i.detached);
        const nextFocus = fallbackDocked.at(-1)?.instanceId || null;
        executeFocusTransition(nextFocus, instancesRef.current);
        return true;
      }

      const target = instancesRef.current.find((i) => i.instanceId === targetId);
      if (!target) return false;
      if (typeof target.onBeforeClose === 'function') {
        const allowed = target.onBeforeClose(target);
        if (allowed === false) return false;
      }
      if (target.popupWindow && !target.popupWindow.closed) {
        try {
          target.popupWindow.__srClosingProgrammatically = true;
          target.popupWindow.close();
        } catch {
          // Ignore popup close error.
        }
      }

      const nextList = instancesRef.current.filter((i) => i.instanceId !== targetId);
      instancesRef.current = nextList;
      setInstances(nextList);

      const remainingDocked = nextList.filter((i) => !i.detached);
      const willKeepDashboardTab = dashboardTabbed && remainingDocked.length > 0;
      if (!willKeepDashboardTab && dashboardTabbed) {
        setDashboardTabbed(false);
      }

      if (focusedIdRef.current === targetId) {
        const nextFocus =
          remainingDocked.at(-1)?.instanceId ||
          (willKeepDashboardTab ? USER_DASHBOARD_ID : null) ||
          nextList.at(-1)?.instanceId ||
          null;
        executeFocusTransition(nextFocus, nextList);
      }
      return true;
    },
    [dashboardTabbed, executeFocusTransition]
  );

  const toggleLeftDrawer = useCallback(() => {
    const active = instancesRef.current.find((i) => i.instanceId === focusedIdRef.current);
    if (!active || !active.supportsLeftDrawer) return false;
    const nextOpen = !active.leftOpen;
    const nextList = instancesRef.current.map((item) =>
      item.instanceId === active.instanceId ? {...item, leftOpen: nextOpen} : item
    );
    instancesRef.current = nextList;
    setInstances(nextList);
    setShellLeftDrawerOpen(nextOpen);
    if (actionsRegistry.has('shell.left_drawer.toggle')) {
      actionsRegistry.setChecked('shell.left_drawer.toggle', nextOpen);
    }
    return nextOpen;
  }, [actionsRegistry]);

  const toggleInstanceRightDrawer = useCallback(
    (targetInstanceId = focusedIdRef.current, requestedMode = null) => {
      const active = instancesRef.current.find((i) => i.instanceId === targetInstanceId);
      if (!active || !active.supportsRightDrawer) return false;
      const sameMode = !requestedMode || requestedMode === active.rightMode;
      const nextOpen = sameMode ? !active.rightOpen : true;
      const nextMode = requestedMode || active.rightMode || 'properties';
      const nextList = instancesRef.current.map((item) =>
        item.instanceId === active.instanceId
          ? {...item, rightOpen: nextOpen, rightMode: nextMode}
          : item
      );
      instancesRef.current = nextList;
      setInstances(nextList);
      if (actionsRegistry.has('shell.right_drawer.toggle')) {
        actionsRegistry.setChecked('shell.right_drawer.toggle', nextOpen);
      }
      return nextOpen;
    },
    [actionsRegistry]
  );
  toggleInstanceRightDrawerRef.current = toggleInstanceRightDrawer;

  const updateInstance = useCallback((instanceId, patch) => {
    const nextList = instancesRef.current.map((item) => {
      if (item.instanceId !== instanceId) return item;
      const resolvedPatch = typeof patch === 'function' ? patch(item) : patch;
      return {...item, ...resolvedPatch};
    });
    instancesRef.current = nextList;
    setInstances(nextList);
  }, []);

  /**
   * Detach a docked application tab into a native pop-out window.
   * Floating windows contain ONLY the Main Work Area + bottom Status Area,
   * and focusing the floating window drives the Main Form's menus, drawers,
   * settings gear, and Tabbed-Icon-Bar.
   */
  const detachInstance = useCallback(
    (instanceId) => {
      const target = instancesRef.current.find((i) => i.instanceId === instanceId);
      if (!target || target.detached) return false;

      const opener =
        openPopupWindow ||
        ((url, name, features) => window.open(url, name, features));

      const popup = opener(
        '',
        `scratchrobin_${instanceId}`,
        'popup=yes,width=1100,height=760,resizable=yes'
      );
      if (!popup || !popup.document) return false;

      popup.document.title = `${target.title} — ScratchRobin`;
      copyStylesToPopup(document, popup.document);
      let rootEl = popup.document.getElementById('scratchrobin-floating-root');
      if (!rootEl) {
        rootEl = popup.document.createElement('div');
        rootEl.id = 'scratchrobin-floating-root';
        rootEl.style.height = '100%';
        rootEl.style.width = '100%';
        popup.document.body.innerHTML = '';
        popup.document.body.appendChild(rootEl);
      }

      const onPopupFocus = () => {
        focusInstance(instanceId);
      };
      const onPopupUnload = () => {
        if (popup.__srClosingProgrammatically) return;
        closeInstance(instanceId);
      };
      popup.addEventListener?.('focus', onPopupFocus);
      popup.addEventListener?.('beforeunload', onPopupUnload);

      const nextList = instancesRef.current.map((item) =>
        item.instanceId === instanceId
          ? {
            ...item,
            detached: true,
            popupWindow: popup,
            popupContainer: rootEl,
          }
          : item
      );
      instancesRef.current = nextList;
      setInstances(nextList);

      const remainingDocked = nextList.filter((i) => !i.detached);
      if (dashboardTabbed && remainingDocked.length === 0) {
        setDashboardTabbed(false);
      }

      // Keep the newly detached floating window as the focused application
      // so the Main Form's menus/drawers/ribbon remain active for it!
      executeFocusTransition(instanceId, nextList);
      return true;
    },
    [closeInstance, dashboardTabbed, executeFocusTransition, focusInstance, openPopupWindow]
  );

  /**
   * Drop a floating sub-form back onto Area 3 to close the pop-out window
   * and restore it as a docked tab with zero state loss.
   */
  const redockInstance = useCallback(
    (instanceId) => {
      const target = instancesRef.current.find((i) => i.instanceId === instanceId);
      if (!target || !target.detached) return false;

      if (target.popupWindow && !target.popupWindow.closed) {
        try {
          target.popupWindow.__srClosingProgrammatically = true;
          target.popupWindow.close();
        } catch {
          // Ignore close error.
        }
      }
      draggedFloatingRef.current = null;

      const nextList = instancesRef.current.map((item) =>
        item.instanceId === instanceId
          ? {
            ...item,
            detached: false,
            popupWindow: null,
            popupContainer: null,
          }
          : item
      );
      instancesRef.current = nextList;
      setInstances(nextList);
      executeFocusTransition(instanceId, nextList);
      return true;
    },
    [executeFocusTransition]
  );

  // Drawer resizing + persistence + reset
  const setDrawerWidth = useCallback(
    (side, width) => {
      const appId = focusedInstance?.appId;
      if (!appId) return;
      const clamped =
        side === 'left'
          ? clampWidth(width, 180, 640, 288)
          : clampWidth(width, 200, 640, 320);
      const field = side === 'left' ? 'left_drawer_width' : 'right_drawer_width';

      setSettings((prev) => ({
        ...prev,
        applications: {
          ...prev.applications,
          [appId]: {
            ...(prev.applications?.[appId] || {}),
            [field]: clamped,
          },
        },
      }));

      const local = loadLocalDrawerWidths();
      local[appId] = {
        ...(local[appId] || {}),
        [side]: clamped,
      };
      saveLocalDrawerWidths(local);
    },
    [focusedInstance?.appId]
  );

  const resetDrawerWidths = useCallback(
    async (appId) => {
      const targetApp = appId || focusedInstance?.appId;
      if (!targetApp) return null;
      let serverValues = {left_drawer_width: 288, right_drawer_width: 320};
      if (runFetch) {
        try {
          const res = await runFetch(
            `/cdeadmin/api/shell/settings/${encodeURIComponent(targetApp)}/reset-drawers`,
            {
              method: 'POST',
              credentials: 'same-origin',
              headers: {'Content-Type': 'application/json', ...csrfHeaders()},
            }
          );
          if (res?.ok) {
            const data = await res.json();
            if (data?.application_settings || data?.settings) {
              serverValues = data.application_settings || data.settings;
            }
          }
        } catch {
          // Offline / test fallback uses 288 / 320.
        }
      }
      const local = loadLocalDrawerWidths();
      delete local[targetApp];
      saveLocalDrawerWidths(local);

      setSettings((prev) => ({
        ...prev,
        applications: {
          ...prev.applications,
          [targetApp]: {
            ...(prev.applications?.[targetApp] || {}),
            left_drawer_width: serverValues.left_drawer_width || 288,
            right_drawer_width: serverValues.right_drawer_width || 320,
          },
        },
      }));
      return serverValues;
    },
    [focusedInstance?.appId, runFetch]
  );

  const saveShellSettings = useCallback(
    async ({scope, appId, values, permittedApps}) => {
      if (scope === 'application' && appId) {
        setSettings((prev) => ({
          ...prev,
          applications: {
            ...prev.applications,
            [appId]: {
              ...(prev.applications?.[appId] || {}),
              ...values,
            },
          },
        }));
        const local = loadLocalDrawerWidths();
        local[appId] = {
          left: values.left_drawer_width || 288,
          right: values.right_drawer_width || 320,
        };
        saveLocalDrawerWidths(local);

        const localLayout = loadLocalLayoutPrefs();
        localLayout.applications = {
          ...(localLayout.applications || {}),
          [appId]: {
            ...(localLayout.applications?.[appId] || {}),
            panel_gap: values.panel_gap ?? null,
            area_zoom: values.area_zoom || {},
          },
        };
        saveLocalLayoutPrefs(localLayout);

        if (runFetch) {
          await runFetch('/cdeadmin/api/shell/settings', {
            method: 'PUT',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', ...csrfHeaders()},
            body: JSON.stringify({
              application_id: appId,
              ...values,
              applications: {[appId]: values},
            }),
          }).catch(() => {});
        }
      } else if (scope === 'global') {
        setSettings((prev) => ({
          ...prev,
          global: {
            ...(prev.global || {}),
            ...values,
          },
        }));

        const localLayout = loadLocalLayoutPrefs();
        localLayout.global = {
          ...(localLayout.global || {}),
          panel_gap: clampPanelGap(values.panel_gap, DEFAULT_PANEL_GAP_PX),
          area_zoom: {
            ...DEFAULT_AREA_ZOOM_PERCENT,
            ...(localLayout.global?.area_zoom || {}),
            ...(values.area_zoom || {}),
          },
        };
        saveLocalLayoutPrefs(localLayout);

        if (Array.isArray(permittedApps)) {
          const allowedSet = new Set(['data-navigator', ...permittedApps]);
          const disabledList = catalogApps
            .map((a) => a.id)
            .filter((id) => id !== 'data-navigator' && !allowedSet.has(id));
          setCatalogApps((prev) =>
            prev.map((a) => ({...a, authorized: allowedSet.has(a.id)}))
          );
          if (runFetch) {
            await runFetch('/cdeadmin/api/shell/authorization', {
              method: 'PUT',
              credentials: 'same-origin',
              headers: {'Content-Type': 'application/json', ...csrfHeaders()},
              body: JSON.stringify({
                enabled_applications: [...allowedSet],
                disabled_applications: disabledList,
                role_policies: {
                  default: {applications: [...allowedSet], actions: {}},
                },
              }),
            }).catch(() => {});
          }
        }
        if (runFetch) {
          await runFetch('/cdeadmin/api/shell/settings', {
            method: 'PUT',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', ...csrfHeaders()},
            body: JSON.stringify({...values, global: values}),
          }).catch(() => {});
        }
      }
    },
    [catalogApps, runFetch]
  );

  const resolvePanelGap = useCallback(() => {
    const appCfg =
      (focusedInstance && settings?.applications?.[focusedInstance.appId]) || null;
    if (
      appCfg &&
      appCfg.panel_gap !== null &&
      appCfg.panel_gap !== undefined &&
      appCfg.panel_gap !== ''
    ) {
      return clampPanelGap(appCfg.panel_gap, DEFAULT_PANEL_GAP_PX);
    }
    return clampPanelGap(settings?.global?.panel_gap, DEFAULT_PANEL_GAP_PX);
  }, [focusedInstance, settings]);

  const resolveAreaZoom = useCallback(
    (areaKey) => {
      const appCfg =
        (focusedInstance && settings?.applications?.[focusedInstance.appId]) || null;
      const appZoomVal = appCfg?.area_zoom?.[areaKey];
      if (
        appZoomVal !== null &&
        appZoomVal !== undefined &&
        appZoomVal !== '' &&
        Number.isFinite(Number(appZoomVal)) &&
        Number(appZoomVal) > 0
      ) {
        return clampZoomPercent(appZoomVal, 100) / 100;
      }
      const globalZoomVal = settings?.global?.area_zoom?.[areaKey];
      return clampZoomPercent(globalZoomVal, 100) / 100;
    },
    [focusedInstance, settings]
  );

  // Session Lock & Unlock
  const lockSession = useCallback(async () => {
    setLockError('');
    setLocked(true);
    if (typeof window !== 'undefined') {
      window.electronUI?.minimizeMainForLock?.();
    }
    if (runFetch) {
      await runFetch('/cdeadmin/api/shell/session/lock', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', ...csrfHeaders()},
      }).catch(() => {});
    }
  }, [runFetch]);

  const unlockSession = useCallback(
    async (password) => {
      setLockBusy(true);
      setLockError('');
      try {
        if (runFetch) {
          const res = await runFetch('/cdeadmin/api/shell/session/unlock', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', ...csrfHeaders()},
            body: JSON.stringify({password}),
          });
          // If backend endpoint exists (status !== 404), enforce its password check
          if (res && res.status !== 404) {
            const data = await res.json().catch(() => ({}));
            if (!res.ok || data?.locked) {
              setLockError(data?.error || gettext('Invalid password.'));
              return false;
            }
          } else if (!String(password || '').trim()) {
            setLockError(gettext('Password is required to unlock the session.'));
            return false;
          }
        } else if (!String(password || '').trim()) {
          setLockError(gettext('Password is required to unlock the session.'));
          return false;
        }
        setLocked(false);
        setLockError('');
        return true;
      } catch (err) {
        setLockError(err?.message || gettext('Unable to verify unlock credentials.'));
        return false;
      } finally {
        setLockBusy(false);
      }
    },
    [runFetch]
  );

  const changeLanguage = useCallback(
    async (langCode) => {
      const code = String(langCode || 'en').trim();
      setLocaleState(code);
      actionsRegistry.setLocale(code);
      gettext.setCatalog?.(null, code);
      if (runFetch) {
        const res = await runFetch('/cdeadmin/api/shell/language', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', ...csrfHeaders()},
          body: JSON.stringify({language: code}),
        }).catch(() => null);
        if (res && typeof res.json === 'function' && res.ok) {
          const payload = await res.json().catch(() => null);
          if (payload?.catalog && typeof payload.catalog === 'object') {
            gettext.setCatalog?.(payload.catalog, payload.current || code);
          }
        }
      }
    },
    [actionsRegistry, runFetch]
  );

  useEffect(() => {
    if (locale === 'en' && gettext.getLocale?.() && gettext.getLocale() !== 'en') {
      gettext.setCatalog?.(null, 'en');
    }
    if (instancesRef.current.length === 0 || typeof gettext.retranslate !== 'function') {
      return;
    }
    let changed = false;
    const nextList = instancesRef.current.map((inst) => {
      const nextTitle = gettext.retranslate(inst.title);
      if (nextTitle && nextTitle !== inst.title) {
        changed = true;
        return {...inst, title: nextTitle};
      }
      return inst;
    });
    if (changed) {
      instancesRef.current = nextList;
      setInstances(nextList);
    }
  }, [locale]);

  const applyAuthorizationPayload = useCallback(
    (data) => {
      if (!data) return;
      if (Array.isArray(data.applications) && data.applications.length > 0) {
        const byId = new Map(data.applications.map((a) => [a.id, a]));
        setCatalogApps((prev) =>
          prev.map((app) => {
            const serverEntry = byId.get(app.id);
            const isAuth = serverEntry ? serverEntry.authorized !== false : false;
            return {
              ...app,
              authorized: isAuth || app.id === 'data-navigator',
            };
          })
        );
      }
      const overrides = data.action_statuses || data.action_overrides;
      if (overrides) {
        actionsRegistry.setAuthorizationOverrides(overrides);
      }
      if (data.settings || data.global_settings || Array.isArray(data.applications)) {
        const localWidths = loadLocalDrawerWidths();
        const localLayout = loadLocalLayoutPrefs();
        const serverGlobal = {
          ...(data.global_settings || {}),
          ...(data.settings?.global || {}),
        };
        if (
          serverGlobal.active_color_scheme ||
          serverGlobal.custom_color_schemes ||
          serverGlobal.enabled_scheme_ids ||
          serverGlobal.typography
        ) {
          applySchemeAndTypographyToDOM(
            {
              activeSchemeId: serverGlobal.active_color_scheme,
              customSchemes: serverGlobal.custom_color_schemes,
              enabledSchemeIds: serverGlobal.enabled_scheme_ids,
              typography: serverGlobal.typography,
            },
            {persistLocal: true, syncPreferences: false}
          );
        }
        setSettings((prev) => {
          const mergedApps = {...prev.applications};
          const appSettingsMap = {...(data.settings?.applications || {})};
          if (Array.isArray(data.applications)) {
            data.applications.forEach((a) => {
              if (a?.id && a?.settings) {
                appSettingsMap[a.id] = {...(appSettingsMap[a.id] || {}), ...a.settings};
              }
            });
          }
          Object.entries(appSettingsMap).forEach(([id, cfg]) => {
            const localAppLayout = localLayout.applications?.[id] || {};
            mergedApps[id] = {
              ...(mergedApps[id] || {}),
              ...cfg,
              left_drawer_width:
                localWidths[id]?.left ?? cfg.left_drawer_width ?? 288,
              right_drawer_width:
                localWidths[id]?.right ?? cfg.right_drawer_width ?? 320,
              panel_gap:
                localAppLayout.panel_gap ?? cfg.panel_gap ?? mergedApps[id]?.panel_gap ?? null,
              area_zoom: {
                ...(mergedApps[id]?.area_zoom || {}),
                ...(cfg.area_zoom || {}),
                ...(localAppLayout.area_zoom || {}),
              },
            };
          });
          return {
            global: {
              ...prev.global,
              ...serverGlobal,
              panel_gap: clampPanelGap(
                localLayout.global?.panel_gap ?? serverGlobal.panel_gap ?? prev.global?.panel_gap,
                DEFAULT_PANEL_GAP_PX
              ),
              area_zoom: {
                ...DEFAULT_AREA_ZOOM_PERCENT,
                ...(prev.global?.area_zoom || {}),
                ...(serverGlobal.area_zoom || {}),
                ...(localLayout.global?.area_zoom || {}),
              },
            },
            applications: mergedApps,
          };
        });
      }
      if (typeof data.session_locked === 'boolean') {
        setLocked(data.session_locked);
      }
    },
    [actionsRegistry]
  );

  const refreshAuthorization = useCallback(async () => {
    if (!runFetch) return null;
    try {
      const res = await runFetch('/cdeadmin/api/shell/authorization', {
        credentials: 'same-origin',
      });
      if (res?.ok) {
        const data = await res.json();
        applyAuthorizationPayload(data);
        return data;
      }
    } catch {
      // Offline / test fallback.
    }
    return null;
  }, [applyAuthorizationPayload, runFetch]);

  const saveSettings = useCallback(
    async (payload = {}) => {
      if (payload.global && typeof payload.global === 'object') {
        await saveShellSettings({scope: 'global', values: payload.global});
      }
      if (payload.applications && typeof payload.applications === 'object') {
        for (const [appId, appVals] of Object.entries(payload.applications)) {
          if (appVals && typeof appVals === 'object') {
            await saveShellSettings({scope: 'application', appId, values: appVals});
          }
        }
      }
    },
    [saveShellSettings]
  );

  // Hydrate server authorization, settings, languages & lock state on mount
  useEffect(() => {
    if (!runFetch) return undefined;
    let active = true;
    Promise.resolve(
      runFetch('/cdeadmin/api/shell/authorization', {credentials: 'same-origin'})
    )
      .then((res) => (res?.ok ? res.json() : null))
      .then((data) => {
        if (!active || !data) return;
        applyAuthorizationPayload(data);
      })
      .catch(() => {});

    Promise.resolve(
      runFetch('/cdeadmin/api/shell/languages', {credentials: 'same-origin'})
    )
      .then((res) => (res?.ok ? res.json() : null))
      .then((data) => {
        if (!active || !data) return;
        const langList = data.supported || data.languages;
        if (Array.isArray(langList) && langList.length > 0) {
          setLanguages(langList);
        }
        if (data.current) {
          setLocaleState(data.current);
          actionsRegistry.setLocale(data.current);
          if (data.current !== 'en' || (data.catalog && Object.keys(data.catalog).length > 0)) {
            gettext.setCatalog?.(data.catalog || null, data.current);
          }
        }
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, [actionsRegistry, applyAuthorizationPayload, runFetch]);

  // Register core shell actions (including 3b1 New/Save/Undo/Redo) in t_actions
  useEffect(() => {
    actionsRegistry.upsert({
      id: 'shell.quick.new',
      icon: 'action.new',
      application: 'project',
      defaultText: gettext('New'),
      defaultHint: gettext('New item or workspace instance'),
      status: focusedInstance ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => {
          if (typeof focusedInstance?.quickActions?.onNew === 'function') {
            return focusedInstance.quickActions.onNew(focusedInstance);
          }
          if (focusedInstance?.appId) {
            return openApplication(focusedInstance.appId);
          }
          return null;
        },
      },
    });
    actionsRegistry.upsert({
      id: 'shell.quick.save',
      icon: 'action.save',
      application: 'project',
      defaultText: gettext('Save'),
      defaultHint: gettext('Save active changes'),
      status:
        typeof focusedInstance?.quickActions?.onSave === 'function'
          ? T_ACTION_STATUS.ENABLED
          : T_ACTION_STATUS.DISABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => focusedInstance?.quickActions?.onSave?.(focusedInstance),
      },
    });
    actionsRegistry.upsert({
      id: 'shell.quick.undo',
      icon: 'action.undo',
      application: 'project',
      defaultText: gettext('Undo'),
      defaultHint: gettext('Undo last change'),
      status:
        typeof focusedInstance?.quickActions?.onUndo === 'function'
          ? T_ACTION_STATUS.ENABLED
          : T_ACTION_STATUS.DISABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => focusedInstance?.quickActions?.onUndo?.(focusedInstance),
      },
    });
    actionsRegistry.upsert({
      id: 'shell.quick.redo',
      icon: 'action.redo',
      application: 'project',
      defaultText: gettext('Redo'),
      defaultHint: gettext('Redo last undone change'),
      status:
        typeof focusedInstance?.quickActions?.onRedo === 'function'
          ? T_ACTION_STATUS.ENABLED
          : T_ACTION_STATUS.DISABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => focusedInstance?.quickActions?.onRedo?.(focusedInstance),
      },
    });
    actionsRegistry.upsert({
      id: 'shell.system.session',
      icon: 'tool.scratchrobin',
      application: 'project',
      defaultText: gettext('Session'),
      defaultHint: gettext('Lock Screen or Logout'),
      status: T_ACTION_STATUS.ENABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => setSessionDialogOpen(true),
      },
    });
    actionsRegistry.upsert({
      id: 'shell.datasources.open',
      icon: 'object.server',
      application: 'project',
      defaultText: gettext('Data Sources'),
      defaultHint: gettext('Manage server and database connections'),
      status: T_ACTION_STATUS.ENABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => {
          if (onOpenDataSources) return onOpenDataSources();
          return openApplication('data-navigator');
        },
      },
    });
    actionsRegistry.upsert({
      id: 'shell.preferences.open',
      icon: 'action.preferences',
      application: 'project',
      defaultText: gettext('Preferences'),
      defaultHint: gettext('Personal colour palettes, fonts, UI personalization, and user API keys'),
      status: T_ACTION_STATUS.ENABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => {
          if (onOpenPreferences) return onOpenPreferences();
          setSettingsDialog({open: true, mode: 'global', appId: null});
          return true;
        },
      },
    });
    actionsRegistry.upsert({
      id: 'shell.left_drawer.toggle',
      icon: 'tool.data-explorer',
      application: 'project',
      defaultText: gettext('Toggle Left Side Drawer'),
      defaultHint: gettext('Open or close the active application Left Side Drawer'),
      status: focusedInstance?.supportsLeftDrawer
        ? T_ACTION_STATUS.ENABLED
        : T_ACTION_STATUS.DISABLED,
      checked: Boolean(shellLeftDrawerOpen),
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => toggleLeftDrawer(),
      },
    });
    actionsRegistry.upsert({
      id: 'shell.right_drawer.toggle',
      icon: 'action.properties',
      application: 'project',
      defaultText: gettext('Right Side Drawer'),
      defaultHint: gettext('Open or close the active application Right Side Drawer'),
      status: focusedInstance?.supportsRightDrawer
        ? T_ACTION_STATUS.ENABLED
        : T_ACTION_STATUS.DISABLED,
      checked: Boolean(focusedInstance?.rightOpen),
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => toggleInstanceRightDrawer(),
      },
    });
    actionsRegistry.upsert({
      id: 'shell.window.dashboard',
      icon: 'tool.dashboard',
      application: 'project',
      defaultText: gettext('User Dashboard'),
      defaultHint: gettext('Show User Dashboard in the Application Area'),
      status: T_ACTION_STATUS.ENABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => openUserDashboardTab(),
      },
    });
    const canCloseActive =
      Boolean(focusedInstance) || (focusedId === USER_DASHBOARD_ID && dashboardTabbed);
    actionsRegistry.upsert({
      id: 'shell.window.close',
      icon: 'action.close',
      application: 'project',
      defaultText: gettext('Close'),
      defaultHint: gettext('Close the currently active application'),
      status: canCloseActive ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => closeInstance(),
      },
    });
    actionsRegistry.upsert({
      id: 'shell.settings.application',
      icon: 'action.settings',
      application: 'project',
      defaultText: gettext('Application Settings'),
      defaultHint: gettext('Configure settings for the currently active application'),
      status: activeSettingsAppId ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () =>
          activeSettingsAppId &&
          setSettingsDialog({open: true, mode: 'application', appId: activeSettingsAppId}),
      },
    });
    actionsRegistry.upsert({
      id: 'shell.settings.global',
      icon: 'action.settings',
      application: 'project',
      defaultText: gettext('Global Settings'),
      defaultHint: gettext('Configure global ScratchRobin settings and authorization'),
      status: T_ACTION_STATUS.ENABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => setSettingsDialog({open: true, mode: 'global', appId: null}),
      },
    });
    [
      [
        'shell.engines.open',
        'engines:connectors',
        gettext('Database Engines (On / Off)'),
        gettext('Enable or disable database engine connectors'),
        'object.server',
      ],
      [
        'shell.security.open',
        'security:apps',
        gettext('Security, Users & Groups'),
        gettext('Configure application availability, users, groups, and grants'),
        'object.role',
      ],
      [
        'shell.users.open',
        'security:users',
        gettext('Users & Group Grants'),
        gettext('Create and manage users, roles, and group grants'),
        'object.user',
      ],
      [
        'shell.menus.open',
        'actions:global-menus',
        gettext('Menus, Toolbars & Icons'),
        gettext('Place action icons on global menus, application menus, and iconbars'),
        'action.customize',
      ],
      [
        'shell.schemes.open',
        'appearance:schemes',
        gettext('Colour Schemes & Fonts'),
        gettext('Configure colour schemes and UI / SQL / diagram fonts'),
        'action.preferences',
      ],
    ].forEach(([id, initialSection, label, hint, icon]) => {
      actionsRegistry.upsert({
        id,
        icon,
        application: 'project',
        defaultText: label,
        defaultHint: hint,
        status: T_ACTION_STATUS.ENABLED,
        target: {
          kind: T_ACTION_TARGET_KIND.CLIENT,
          invoke: () =>
            setSettingsDialog({open: true, mode: 'global', appId: null, initialSection}),
        },
      });
    });
    [
      ['shell.help.sql_reference', 'sql', gettext('SQL Reference'), 'tool.query'],
      ['shell.help.engine_reference', 'engines', gettext('Database Engine Reference'), 'object.database'],
      ['shell.help.glossary', 'glossary', gettext('Glossary of Terms'), 'action.help'],
      ['shell.help.docs', 'docs', gettext('Help'), 'action.help'],
      ['shell.help.about', 'about', gettext('About'), 'tool.scratchrobin'],
    ].forEach(([id, topic, label, icon]) => {
      actionsRegistry.upsert({
        id,
        icon,
        application: 'project',
        defaultText: label,
        defaultHint: label,
        status: T_ACTION_STATUS.ENABLED,
        target: {
          kind: T_ACTION_TARGET_KIND.CLIENT,
          invoke: () => setHelpTopic(topic),
        },
      });
    });

    authorizedApps.forEach((app) => {
      actionsRegistry.upsert({
        id: `shell.app.open.${app.id}`,
        icon: app.iconKey || 'command.default',
        application: 'project',
        defaultText: app.label,
        defaultHint: gettext('Open a new %s instance', app.label),
        status: T_ACTION_STATUS.ENABLED,
        target: {
          kind: T_ACTION_TARGET_KIND.CLIENT,
          invoke: () => openApplication(app.id),
        },
      });
    });

    // Ensure every canonical action in the placement catalog has a baseline entry
    // in `actionsRegistry` so user-placed actions in global menus or `3b`/`3b1`
    // iconbars resolve labels and semantic icons cleanly even before an instance registers a custom handler.
    CANONICAL_ACTION_CATALOG.forEach((entry) => {
      if (!actionsRegistry.has(entry.id)) {
        actionsRegistry.upsert({
          id: entry.id,
          icon: entry.icon || 'command.default',
          application: entry.scope === 'global' || entry.scope === 'quick' ? 'project' : entry.scope,
          defaultText: entry.label,
          defaultHint: entry.label,
          status: T_ACTION_STATUS.ENABLED,
          target: {
            kind: T_ACTION_TARGET_KIND.CLIENT,
            invoke: () => {
              if (entry.id === 'project.settings.global') {
                setSettingsDialog({open: true, mode: 'global', appId: null, initialSection: null});
              } else if (entry.id === 'project.settings.application' && activeSettingsAppId) {
                setSettingsDialog({
                  open: true,
                  mode: 'application',
                  appId: activeSettingsAppId,
                  initialSection: null,
                });
              } else if (entry.id === 'shell.window.dashboard') {
                openUserDashboardTab();
              } else if (entry.id === 'shell.window.close') {
                closeInstance();
              }
            },
          },
        });
      }
    });
  }, [
    actionsRegistry,
    activeSettingsAppId,
    authorizedApps,
    closeInstance,
    dashboardTabbed,
    focusedId,
    focusedInstance,
    onOpenDataSources,
    onOpenPreferences,
    openApplication,
    openUserDashboardTab,
    shellLeftDrawerOpen,
    toggleInstanceRightDrawer,
    toggleLeftDrawer,
    locale,
  ]);

  const showTabbedIconBar = useMemo(() => {
    // User Dashboard NEVER displays a Tabbed-Icon-Bar.
    if (!focusedInstance || focusedId === USER_DASHBOARD_ID) return false;
    if (!focusedInstance.supportsTabbedIconBar) return false;
    if (toolbarRibbonOverride !== null) return toolbarRibbonOverride;
    const appCfg = settings?.applications?.[focusedInstance.appId];
    if (typeof appCfg?.show_tabbed_icon_bar === 'boolean') {
      return appCfg.show_tabbed_icon_bar;
    }
    return settings?.global?.default_tabbed_icon_bar !== false;
  }, [focusedId, focusedInstance, settings, toolbarRibbonOverride]);

  // Synchronize baseline Top Menus (0 System, 60 Applications, 70 Window, 80 Help)
  useEffect(() => {
    const canCloseActive =
      Boolean(focusedInstance) || (focusedId === USER_DASHBOARD_ID && dashboardTabbed);
    const floatingSuffix = translateShell(
      locale,
      'menu.window.open_app_floating_suffix',
      '(Floating)'
    );

    const appMenuItems = [
      {
        id: 'shell.datasources.open',
        actionId: 'shell.datasources.open',
        label: translateShell(locale, 'menu.applications.data_sources.text', 'Data Sources'),
        i18nKey: 'menu.applications.data_sources.text',
        hintKey: 'menu.applications.data_sources.hint',
        iconKey: 'object.server',
        index: 10,
        callback: () => actionsRegistry.execute('shell.datasources.open'),
      },
      {
        id: 'shell.preferences.open',
        actionId: 'shell.preferences.open',
        label: translateShell(
          locale,
          'menu.applications.preferences.text',
          'Configure ScratchRobin…'
        ),
        i18nKey: 'menu.applications.preferences.text',
        hintKey: 'menu.applications.preferences.hint',
        iconKey: 'action.settings',
        index: 20,
        callback: () => actionsRegistry.execute('shell.preferences.open'),
      },
      {id: 'sep_apps', type: 'separator', index: 30},
      ...authorizedApps.map((app, idx) => {
        const translatedAppLabel = translateShell(
          locale,
          `app.${app.id}.label`,
          app.label
        );
        return {
          id: `shell.app.open.${app.id}`,
          actionId: `shell.app.open.${app.id}`,
          label: translatedAppLabel,
          i18nKey: `app.${app.id}.label`,
          hintKey: `app.${app.id}.hint`,
          hint: translateShell(
            locale,
            'menu.applications.launch_hint',
            'Open a new %s workspace instance.',
            translatedAppLabel
          ),
          iconKey: app.iconKey,
          index: 40 + idx * 5,
          callback: () => openApplication(app.id),
        };
      }),
    ];

    const windowItems = [
      {
        id: 'window.toolbar.notebookbar',
        label: translateShell(locale, 'menu.window.tabbed_icon_bar.text', 'Tabbed-Icon-Bar'),
        i18nKey: 'menu.window.tabbed_icon_bar.text',
        hintKey: 'menu.window.tabbed_icon_bar.hint',
        iconKey: 'action.customize',
        index: 10,
        checked: Boolean(showTabbedIconBar),
        disabled: !focusedInstance || !focusedInstance.supportsTabbedIconBar,
        callback: () => setToolbarRibbonOverride((prev) => !(prev ?? showTabbedIconBar)),
      },
      {
        id: 'window.toolbar.right_drawer',
        label: translateShell(locale, 'menu.window.right_drawer.text', 'Right Side Drawer'),
        i18nKey: 'menu.window.right_drawer.text',
        hintKey: 'menu.window.right_drawer.hint',
        iconKey: 'action.properties',
        index: 15,
        checked: Boolean(focusedInstance?.rightOpen),
        disabled: !focusedInstance || !focusedInstance.supportsRightDrawer,
        callback: () => toggleInstanceRightDrawer(),
      },
      {
        id: 'window.toolbar.status_bar',
        label: translateShell(locale, 'menu.window.status_bar.text', 'Status Bar'),
        i18nKey: 'menu.window.status_bar.text',
        hintKey: 'menu.window.status_bar.hint',
        iconKey: 'action.properties',
        index: 20,
        checked: Boolean(showStatusBar),
        callback: () => setShowStatusBar((prev) => !prev),
      },
      {id: 'sep_window_1', type: 'separator', index: 30},
      {
        id: 'shell.window.dashboard',
        actionId: 'shell.window.dashboard',
        label: translateShell(locale, 'menu.window.user_dashboard.text', 'User Dashboard'),
        i18nKey: 'menu.window.user_dashboard.text',
        hintKey: 'menu.window.user_dashboard.hint',
        iconKey: 'tool.dashboard',
        index: 40,
        checked:
          focusedId === USER_DASHBOARD_ID ||
          (!focusedInstance && dockedInstances.length === 0),
        callback: () => openUserDashboardTab(),
      },
      {
        id: 'shell.window.close',
        actionId: 'shell.window.close',
        label: translateShell(locale, 'menu.window.close.text', 'Close'),
        i18nKey: 'menu.window.close.text',
        hintKey: 'menu.window.close.hint',
        iconKey: 'action.close',
        index: 45,
        disabled: !canCloseActive,
        callback: () => closeInstance(),
      },
      ...(instances.length > 0
        ? [
          {id: 'sep_window_open_apps', type: 'separator', index: 50},
          ...instances.map((inst, idx) => ({
            id: `window.open_instance.${inst.instanceId}`,
            label: inst.detached ? `${inst.title} ${floatingSuffix}` : inst.title,
            hintKey: 'menu.window.focus_instance.hint',
            i18nArgs: [inst.title],
            iconKey: inst.iconKey,
            index: 60 + idx * 5,
            checked: inst.instanceId === focusedId,
            callback: () => focusInstance(inst.instanceId),
          })),
        ]
        : []),
    ];

    const helpItems = [
      {
        id: 'shell.help.sql_reference',
        actionId: 'shell.help.sql_reference',
        label: translateShell(locale, 'menu.help.sql_reference.text', 'SQL Reference'),
        i18nKey: 'menu.help.sql_reference.text',
        hintKey: 'menu.help.sql_reference.hint',
        iconKey: 'tool.query',
        index: 10,
        callback: () => setHelpTopic('sql'),
      },
      {
        id: 'shell.help.engine_reference',
        actionId: 'shell.help.engine_reference',
        label: translateShell(
          locale,
          'menu.help.engine_reference.text',
          'Database Engine Reference'
        ),
        i18nKey: 'menu.help.engine_reference.text',
        hintKey: 'menu.help.engine_reference.hint',
        iconKey: 'object.database',
        index: 20,
        callback: () => setHelpTopic('engines'),
      },
      {
        id: 'shell.help.glossary',
        actionId: 'shell.help.glossary',
        label: translateShell(locale, 'menu.help.glossary.text', 'Glossary of Terms'),
        i18nKey: 'menu.help.glossary.text',
        hintKey: 'menu.help.glossary.hint',
        iconKey: 'action.help',
        index: 30,
        callback: () => setHelpTopic('glossary'),
      },
      {
        id: 'shell.help.docs',
        actionId: 'shell.help.docs',
        label: translateShell(locale, 'menu.help.docs.text', 'Help'),
        i18nKey: 'menu.help.docs.text',
        hintKey: 'menu.help.docs.hint',
        iconKey: 'action.help',
        index: 40,
        callback: () => setHelpTopic('docs'),
      },
      {
        id: 'shell.help.about',
        actionId: 'shell.help.about',
        label: translateShell(locale, 'menu.help.about.text', 'About'),
        i18nKey: 'menu.help.about.text',
        hintKey: 'menu.help.about.hint',
        iconKey: 'tool.scratchrobin',
        index: 50,
        callback: () => setHelpTopic('about'),
      },
    ];

    menuRegistry.setBaselineMenus([
      {
        name: 'system',
        id: 'mnu_system',
        label: 'ScratchRobin',
        index: PROJECT_TOP_MENU_INDICES.SYSTEM,
        iconKey: 'tool.scratchrobin',
        isSystemIcon: true,
        items: [],
      },
      {
        name: 'applications',
        id: 'mnu_applications',
        label: translateShell(locale, 'menu.applications.title', 'Applications'),
        i18nKey: 'menu.applications.title',
        index: PROJECT_TOP_MENU_INDICES.APPLICATIONS,
        items: appMenuItems,
      },
      {
        name: 'window',
        id: 'mnu_window',
        label: translateShell(locale, 'menu.window.title', 'Window'),
        i18nKey: 'menu.window.title',
        index: PROJECT_TOP_MENU_INDICES.WINDOW,
        items: windowItems,
      },
      {
        name: 'help',
        id: 'mnu_help',
        label: translateShell(locale, 'menu.help.title', 'Help'),
        i18nKey: 'menu.help.title',
        index: PROJECT_TOP_MENU_INDICES.HELP,
        items: helpItems,
      },
    ]);
  }, [
    actionsRegistry,
    authorizedApps,
    closeInstance,
    dashboardTabbed,
    dockedInstances.length,
    focusInstance,
    focusedId,
    focusedInstance,
    instances,
    locale,
    menuRegistry,
    openApplication,
    openUserDashboardTab,
    showStatusBar,
    showTabbedIconBar,
    toggleInstanceRightDrawer,
  ]);

  const handleLogout = useCallback(() => {
    if (onLogout) {
      onLogout();
      return;
    }
    if (typeof window !== 'undefined' && window.location) {
      window.location.assign('/logout?next=/browser/');
    }
  }, [onLogout]);

  // Listen for inline docked object editor tabs and 3c inspector updates from any module
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handleOpenInline = (e) => {
      if (e?.detail) openInlineTab(e.detail);
    };
    const handleCloseInline = (e) => {
      if (e?.detail?.instanceId) closeInstance(e.detail.instanceId);
    };
    const handleInspectRight = (e) => {
      const targetId = e?.detail?.instanceId || focusedIdRef.current;
      if (!targetId || targetId === USER_DASHBOARD_ID) return;
      updateInstance(targetId, {
        supportsRightDrawer: true,
        rightOpen: e?.detail?.open !== false,
        inspectorNode: e?.detail?.node ?? null,
        ...(e?.detail?.renderRightDrawer ? {renderRightDrawer: e.detail.renderRightDrawer} : {}),
      });
    };
    const handleOpenPreferences = (e) => {
      const detail = e?.detail || {};
      setSettingsDialog({
        open: true,
        mode: detail.mode || 'global',
        appId: detail.appId || null,
        initialSection: detail.sectionId || detail.initialSection || null,
      });
    };
    window.addEventListener('scratchrobin:open-inline-tab', handleOpenInline);
    window.addEventListener('scratchrobin:close-inline-tab', handleCloseInline);
    window.addEventListener('scratchrobin:inspect-right-drawer', handleInspectRight);
    window.addEventListener('scratchrobin:open-preferences', handleOpenPreferences);
    return () => {
      window.removeEventListener('scratchrobin:open-inline-tab', handleOpenInline);
      window.removeEventListener('scratchrobin:close-inline-tab', handleCloseInline);
      window.removeEventListener('scratchrobin:inspect-right-drawer', handleInspectRight);
      window.removeEventListener('scratchrobin:open-preferences', handleOpenPreferences);
    };
  }, [closeInstance, openInlineTab, updateInstance]);

  const contextValue = useMemo(
    () => ({
      actionsRegistry,
      menuRegistry,
      authorizedApps,
      catalogApps,
      instances,
      dockedInstances,
      focusedId,
      focusedInstance,
      dashboardTabbed,
      userDashboard,
      locked,
      locale,
      languages,
      settings,
      shellLeftDrawerOpen,
      activeSettingsAppId,
      showTabbedIconBar,
      showStatusBar,
      teardownHistory,
      draggedFloatingRef,
      openApplication,
      openInlineTab,
      focusInstance,
      closeInstance,
      detachInstance,
      redockInstance,
      updateInstance,
      openUserDashboardTab,
      toggleLeftDrawer,
      toggleInstanceRightDrawer,
      setDrawerWidth,
      resetDrawerWidths,
      saveShellSettings,
      saveSettings,
      refreshAuthorization,
      resolvePanelGap,
      resolveAreaZoom,
      lockSession,
      unlockSession,
      changeLanguage,
      openSessionDialog: () => setSessionDialogOpen(true),
      openSettingsDialog: (mode, appId = activeSettingsAppId, initialSection = null) =>
        setSettingsDialog({open: true, mode, appId, initialSection}),
    }),
    [
      actionsRegistry,
      activeSettingsAppId,
      authorizedApps,
      catalogApps,
      changeLanguage,
      closeInstance,
      dashboardTabbed,
      detachInstance,
      dockedInstances,
      focusInstance,
      focusedId,
      focusedInstance,
      instances,
      languages,
      locale,
      lockSession,
      locked,
      menuRegistry,
      openApplication,
      openInlineTab,
      openUserDashboardTab,
      redockInstance,
      refreshAuthorization,
      resetDrawerWidths,
      resolveAreaZoom,
      resolvePanelGap,
      saveSettings,
      saveShellSettings,
      setDrawerWidth,
      settings,
      shellLeftDrawerOpen,
      showStatusBar,
      showTabbedIconBar,
      teardownHistory,
      toggleInstanceRightDrawer,
      toggleLeftDrawer,
      unlockSession,
      updateInstance,
      userDashboard,
    ]
  );

  const activeAppLabel =
    catalogApps.find((a) => a.id === settingsDialog.appId)?.label ||
    settingsDialog.appId ||
    '';

  return (
    <ProjectShellContext.Provider value={contextValue}>
      {locked ? (
        <ProjectLockScreen
          username={username}
          busy={lockBusy}
          error={lockError}
          onUnlock={unlockSession}
          onLogout={handleLogout}
        />
      ) : (
        children
      )}
      {instances
        .filter((i) => i.detached)
        .map((inst) => (
          <FloatingSubFormPortal
            key={inst.instanceId}
            instance={inst}
            locked={locked}
            showStatusBar={showStatusBar}
            onFocusInstance={focusInstance}
            onRedockInstance={redockInstance}
            onBeginDragBack={(id) => {
              draggedFloatingRef.current = id;
            }}
          />
        ))}
      {!locked && (
        <>
          <ProjectSessionLogoutDialog
            open={sessionDialogOpen}
            username={username}
            onClose={() => setSessionDialogOpen(false)}
            onLockScreen={lockSession}
            onLogout={handleLogout}
          />
          <ProjectSettingsDialog
            open={settingsDialog.open}
            mode={settingsDialog.mode}
            appId={settingsDialog.appId}
            appLabel={activeAppLabel}
            initialSection={settingsDialog.initialSection}
            settings={settings}
            applications={catalogApps}
            actionsRegistry={actionsRegistry}
            fetchImpl={runFetch}
            onSaveSettings={saveShellSettings}
            onRefreshAuthorization={refreshAuthorization}
            onResetDrawers={resetDrawerWidths}
            onClose={() =>
              setSettingsDialog((prev) => ({...prev, open: false, initialSection: null}))
            }
          />
          <ProjectHelpReferenceDialog
            open={Boolean(helpTopic)}
            topic={helpTopic}
            fetchImpl={runFetch}
            onClose={() => setHelpTopic('')}
          />
        </>
      )}
    </ProjectShellContext.Provider>
  );
}

ProjectShellProvider.propTypes = {
  children: PropTypes.node,
  applications: PropTypes.array,
  applicationFactory: PropTypes.func,
  userDashboard: PropTypes.node,
  actionsRegistry: PropTypes.object,
  menuRegistry: PropTypes.object,
  fetchImpl: PropTypes.func,
  openPopupWindow: PropTypes.func,
  username: PropTypes.string,
  onOpenDataSources: PropTypes.func,
  onOpenPreferences: PropTypes.func,
  onLogout: PropTypes.func,
  initialLocked: PropTypes.bool,
  onTeardownStep: PropTypes.func,
};

/**
 * Area 1 — Top Menu Bar:
 * Uses Base UI's `NavigationMenu` (`@base-ui/react/navigation-menu`) with full
 * internationalization (`shellMenuI18n.js`) while preserving unsigned-integer
 * positional ordering (`0` System Icon, `60` Applications, `70` Window,
 * `80` Help, dynamic focused-application menus, and right-aligned Language +
 * Light/Dark theme controls).
 */
export function ProjectTopMenuBar() {
  const shell = useProjectShell();
  if (!shell) return null;
  return <ProjectNavigationMenuBar shell={shell} />;
}

/**
 * Area 2 — Side Menu (Vertical Rightward-Expanding Dock Island):
 *   1. Top item: Left Side Drawer Toggle (expands rightward on hover)
 *   2. Middle stack: `data-navigator` first + authorized user applications
 *      (stateless launcher; proximity spring wave expands rightward without shifting Area 3)
 *   3. Bottom-aligned item: Settings Gear (expands rightward & upward on hover;
 *      opens Application Settings | Global Settings popup)
 */
export function ProjectSideMenu() {
  const shell = useProjectShell();
  if (!shell) return null;
  return <ProjectVerticalDock shell={shell} />;
}

/**
 * Area 3b — Tabbed-Notebook-Bar (`NotebookBar` Island):
 *   - `3b1`: Quick-access strip (`New`, `Save`, `Undo`, `Redo`) on Background Colour `b`
 *   - `3b2`: Tab strip track on Background Colour `b` (inactive tabs slightly darker than `3b3`)
 *   - `3b3`: Active folder tab merging seamlessly into `3b` icon panel
 *   - `3b4`: Right-aligned `[x]` close button
 *   - `3b` : Active tab's ribbon command icons
 * Mounted on the Main Form across the full width of Area 3 for the focused
 * application (docked or floating), NEVER shown on User Dashboard.
 */
export function ProjectApplicationNotebookBar() {
  const shell = useProjectShell();
  useTActions(shell?.actionsRegistry);
  const [, bumpPlacements] = useState(0);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onPlacementsChanged = () => bumpPlacements((n) => n + 1);
    window.addEventListener(ACTION_PLACEMENTS_CHANGED_EVENT, onPlacementsChanged);
    return () => window.removeEventListener(ACTION_PLACEMENTS_CHANGED_EVENT, onPlacementsChanged);
  }, []);

  if (!shell || !shell.showTabbedIconBar || !shell.focusedInstance) return null;

  const {ribbonTabs, quickAccess, iconAssignments} = resolveInstanceNotebookBarSpec(
    shell.focusedInstance,
    shell.settings
  );

  const bar = shell.actionsRegistry.toNotebookBar(
    ribbonTabs || [],
    (action) => {
      const resolvedIcon =
        iconAssignments?.[action.id] ||
        iconAssignments?.[action.icon] ||
        action.icon ||
        'command.default';
      return <Icon iconKey={resolvedIcon} decorative size="100%" />;
    },
    quickAccess
  );

  // Ensure at least one tab exists so 3b3 + 3b4 ([x] close button) render cleanly.
  const model =
    bar.model.tabs.length > 0
      ? bar.model
      : {
        tabs: [
          {
            id: `${shell.focusedInstance.appId}-default`,
            label: shell.focusedInstance.title,
            groups: [],
          },
        ],
        quickAccess: bar.model.quickAccess || [],
      };

  const zoom3b = shell.resolveAreaZoom?.('area_3b') ?? 1;
  const barStyle = {
    ...COMMAND_BAR_THEME,
    '--sr-zoom-3b': String(zoom3b),
    '--snb-color-background': 'var(--sr-strip-b)',
    '--snb-color-panel': 'var(--sr-island-bg)',
    '--snb-color-text': 'var(--sr-island-fg)',
    '--snb-color-muted': 'var(--sr-island-muted)',
    '--snb-color-border': 'var(--sr-island-border)',
    '--snb-radius': '8px',
    '--snb-font-size': 'calc(0.84375rem * var(--sr-zoom-3b, 1))',
    '--snb-small-font-size': 'calc(0.74rem * var(--sr-zoom-3b, 1))',
    '--snb-tab-height': 'calc(30px * var(--sr-zoom-3b, 1))',
    '--snb-panel-height': 'calc(36px * var(--sr-zoom-3b, 1))',
    '--snb-control-height': 'calc(28px * var(--sr-zoom-3b, 1))',
    '--snb-icon-size': 'calc(17px * var(--sr-zoom-3b, 1))',
    '--snb-large-icon-size': 'calc(20px * var(--sr-zoom-3b, 1))',
  };

  return (
    <div
      className="sr-island sr-island-3b"
      data-area-part="3b"
      data-cdeadmin-qa-key="project-application-notebookbar"
      style={barStyle}
    >
      <NotebookBar
        model={model}
        state={bar.state}
        catalog={bar.catalog}
        accessKeyTrigger={null}
        label={gettext('%s Commands', shell.focusedInstance.title)}
        messages={COMMAND_BAR_MESSAGES}
        onCommand={(commandId, detail) => bar.onCommand(commandId, detail)}
        end={
          <span style={{display: 'inline-flex', alignItems: 'center', gap: 4}}>
            {shell.focusedInstance.supportsRightDrawer && (
              <IconButton
                label={gettext('Toggle Object Properties Drawer')}
                aria-pressed={Boolean(shell.focusedInstance.rightOpen)}
                data-cdeadmin-qa-key="notebookbar-toggle-right-drawer"
                onClick={() => shell.toggleInstanceRightDrawer()}
              >
                <Icon iconKey="action.inspector_drawer" decorative size="15px" />
              </IconButton>
            )}
            <IconButton
              label={gettext('Close Active Application')}
              data-area-part="3b4"
              data-cdeadmin-qa-key="notebookbar-close-active"
              onClick={() => shell.closeInstance(shell.focusedInstance.instanceId)}
            >
              ×
            </IconButton>
          </span>
        }
      />
      {typeof shell.focusedInstance.renderToolbarExtras === 'function' && (
        <div className="sr-3b-extras-bar" data-cdeadmin-qa-key="notebookbar-extras">
          <ShellSurfaceErrorBoundary
            resetKey={`${shell.focusedInstance.instanceId}:extras`}
            surfaceName={gettext('%s Toolbar', shell.focusedInstance.title)}
            compact
          >
            {shell.focusedInstance.renderToolbarExtras(shell.focusedInstance, shell)}
          </ShellSurfaceErrorBoundary>
        </div>
      )}
    </div>
  );
}

class ShellSurfaceErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = {error: null};
  }

  static getDerivedStateFromError(error) {
    return {error};
  }

  componentDidUpdate(prevProps) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({error: null});
    }
  }

  componentDidCatch(error, info) {
    console.error('[ScratchRobin Surface Error]', this.props.surfaceName, error, info);
  }

  render() {
    if (this.state.error) {
      if (this.props.compact) {
        return null;
      }
      return (
        <Box
          role="alert"
          data-cdeadmin-qa-key="shell-surface-error-boundary"
          sx={{p: 2.5, display: 'flex', flexDirection: 'column', gap: 1}}
        >
          <Box sx={{fontWeight: 700, fontSize: '0.9rem'}}>
            {gettext('%s encountered a rendering error', this.props.surfaceName || gettext('Application surface'))}
          </Box>
          <Box sx={{fontSize: '0.8rem', color: 'text.secondary', fontFamily: 'monospace'}}>
            {this.state.error?.message || String(this.state.error)}
          </Box>
          <Box>
            <Button size="small" onClick={() => this.setState({error: null})}>
              {gettext('Retry Surface')}
            </Button>
          </Box>
        </Box>
      );
    }
    return this.props.children;
  }
}

ShellSurfaceErrorBoundary.propTypes = {
  children: PropTypes.node,
  compact: PropTypes.bool,
  resetKey: PropTypes.string,
  surfaceName: PropTypes.string,
};

/**
 * Complete Main Form body below Area 1 Top Menu sitting on Background Colour `a`:
 *   - Area 2 Side Menu rounded island on the far left (full height)
 *   - Area 3b Tabbed-Notebook-Bar rounded island spanning full Area 3 width
 *   - Area 3a Optional Left Drawer rounded island (full remaining height to bottom,
 *     inset short vertical resize handle on right edge)
 *   - Area 3e Main Application Work Area rounded island + Area 3c Optional Right
 *     Drawer rounded island (inset short vertical resize handle on left edge)
 *   - Area 3d Optional Status Bar rounded island spanning underneath 3e + 3c
 */
export function ProjectWorkbenchFrame({fallbackArea3 = null}) {
  useProjectShellStyles();
  const prefStore = usePreferences();
  const shell = useProjectShell();
  const area3Ref = useRef(null);
  const draggedTabOutsideRef = useRef(false);
  const [dropActive, setDropActive] = useState(false);
  const [domTone, setDomTone] = useState(() => resolveCurrentTone(prefStore));

  useEffect(() => {
    setDomTone(resolveCurrentTone(prefStore));
    if (typeof document === 'undefined' || typeof MutationObserver === 'undefined') {
      return undefined;
    }
    const root = document.documentElement;
    if (!root) return undefined;
    const obs = new MutationObserver(() => {
      setDomTone(resolveCurrentTone(prefStore));
    });
    obs.observe(root, {attributes: true, attributeFilter: ['data-cde-theme', 'data-theme']});
    return () => obs.disconnect();
  }, [prefStore]);

  if (!shell) return null;

  const {
    dockedInstances,
    focusedId,
    focusedInstance,
    dashboardTabbed,
    userDashboard,
    settings,
    shellLeftDrawerOpen,
    showStatusBar,
  } = shell;

  const appCfg =
    (focusedInstance && settings?.applications?.[focusedInstance.appId]) || {};
  const leftWidth = clampWidth(appCfg.left_drawer_width, 180, 640, 288);
  const rightWidth = clampWidth(appCfg.right_drawer_width, 200, 640, 320);

  const panelGap = shell.resolvePanelGap?.() ?? DEFAULT_PANEL_GAP_PX;
  const zoom3a = shell.resolveAreaZoom?.('area_3a') ?? 1;
  const zoom3b = shell.resolveAreaZoom?.('area_3b') ?? 1;
  const zoom3c = shell.resolveAreaZoom?.('area_3c') ?? 1;
  const zoom3d = shell.resolveAreaZoom?.('area_3d') ?? 1;
  const zoom3e = shell.resolveAreaZoom?.('area_3e') ?? 1;

  const leftVisible = Boolean(
    focusedInstance && focusedInstance.supportsLeftDrawer && shellLeftDrawerOpen
  );
  const rightVisible = Boolean(
    focusedInstance && focusedInstance.supportsRightDrawer && focusedInstance.rightOpen
  );

  // Build Area 3 docked items list:
  const dashboardItem = {
    instanceId: USER_DASHBOARD_ID,
    title: gettext('User Dashboard'),
    iconKey: 'tool.scratchrobin',
    isDashboard: true,
  };

  const dockedItems =
    dockedInstances.length === 0
      ? []
      : dashboardTabbed
        ? [dashboardItem, ...dockedInstances]
        : dockedInstances;

  const showTabStrip = dockedItems.length >= 2;

  // Determine which docked item displays inside Area 3e right now:
  const activeDockedItem =
    focusedId === USER_DASHBOARD_ID && dashboardTabbed
      ? dashboardItem
      : dockedItems.find((item) => item.instanceId === focusedId) ||
        dockedItems[0] ||
        null;

  const statusVisible = Boolean(
    showStatusBar && activeDockedItem && !activeDockedItem.isDashboard
  );

  const handleArea3DragOver = (e) => {
    const types = Array.from(e.dataTransfer?.types || []);
    if (types.includes(INSTANCE_DRAG_MIME) || shell.draggedFloatingRef.current) {
      e.preventDefault();
      if (!dropActive) setDropActive(true);
    }
  };

  const handleArea3Drop = (e) => {
    setDropActive(false);
    const droppedId =
      e.dataTransfer?.getData(INSTANCE_DRAG_MIME) ||
      shell.draggedFloatingRef.current;
    if (droppedId) {
      e.preventDefault();
      shell.redockInstance(droppedId);
    }
  };

  return (
    <div
      className="sr-shell-backdrop"
      data-tone={domTone}
      data-cdeadmin-shell="zero-grey"
      data-cdeadmin-project-shell="standardized"
      data-cdeadmin-qa-key="project-shell-backdrop"
      style={{
        '--sr-panel-gap': `${panelGap}px`,
        '--sr-zoom-3a': String(zoom3a),
        '--sr-zoom-3b': String(zoom3b),
        '--sr-zoom-3c': String(zoom3c),
        '--sr-zoom-3d': String(zoom3d),
        '--sr-zoom-3e': String(zoom3e),
      }}
    >
      {/* Area 2 — Side Menu Rounded Island (full height) */}
      <ProjectSideMenu />

      {/* Area 3 Outer Column: 3b across full top width, then [3a | [3e + 3c / 3d]] */}
      <div className="sr-area3-outer" data-cdeadmin-qa-key="project-area-3-outer">
        {/* Area 3b — Tabbed-Notebook-Bar Island (3b1, 3b2, 3b3, 3b4, 3b) */}
        <ProjectApplicationNotebookBar />

        <div className="sr-area3-lower-row">
          {/* Area 3a — Optional Left Side Drawer Island (extends to bottom) */}
          {leftVisible ? (
            <aside
              className="sr-island sr-island-3a"
              data-area-part="3a"
              aria-label={gettext('%s Left Drawer', focusedInstance.title)}
              aria-hidden={false}
              data-cdeadmin-explorer-workspace="true"
              data-cdeadmin-qa-key="explorer-workspace"
              style={{
                width: `${leftWidth}px`,
                flex: `0 0 ${leftWidth}px`,
              }}
            >
              <div
                className="sr-zoom-surface"
                data-cdeadmin-qa-key="project-left-drawer"
                style={{'--sr-surface-zoom': String(zoom3a)}}
              >
                <Toolbar
                  label={gettext('Left Side Drawer')}
                  trailing={
                    <IconButton
                      label={gettext('Close Left Side Drawer')}
                      onClick={() => shell.toggleLeftDrawer()}
                    >
                      ×
                    </IconButton>
                  }
                >
                  <Box component="strong" sx={{fontSize: '0.8125rem'}}>
                    {focusedInstance.title}
                  </Box>
                </Toolbar>
                <ScratchScrollArea fillViewport style={{flex: 1, minHeight: 0}}>
                  <ShellSurfaceErrorBoundary
                    resetKey={`${focusedInstance.instanceId}:left`}
                    surfaceName={gettext('%s Left Drawer', focusedInstance.title)}
                  >
                    {focusedInstance.renderLeftDrawer(focusedInstance)}
                  </ShellSurfaceErrorBoundary>
                </ScratchScrollArea>
              </div>
              <DrawerInsetResizeHandle
                side="left"
                value={leftWidth}
                min={180}
                max={640}
                onChange={(w) => shell.setDrawerWidth('left', w)}
                label={gettext('Resize Left Side Drawer')}
              />
            </aside>
          ) : (
            <aside
              aria-label={gettext('Left Side Drawer')}
              aria-hidden="true"
              data-cdeadmin-explorer-workspace="true"
              data-cdeadmin-qa-key="explorer-workspace"
              style={{display: 'none'}}
            />
          )}

          {/* Center + Right Column: [3e + 3c] above 3d Status Bar */}
          <div className="sr-area3-center-right-col">
            <div className="sr-area3-work-and-right-row">
              {/* Area 3e — Main Application Work Area Island */}
              <main
                ref={area3Ref}
                className="sr-island sr-island-3e"
                data-area-part="3e"
                aria-label={gettext('Application Area')}
                data-cdeadmin-qa-key="project-area-3"
                data-drop-active={dropActive ? 'true' : 'false'}
                onDragOver={handleArea3DragOver}
                onDragLeave={() => setDropActive(false)}
                onDrop={handleArea3Drop}
                style={{
                  outline: dropActive ? '2px dashed var(--sr-island-accent)' : 'none',
                  outlineOffset: '-3px',
                }}
              >
                {/* Multi-Application Tab Strip ONLY when >= 2 docked items */}
                {showTabStrip && (
                  <div
                    role="tablist"
                    aria-label={gettext('Open Applications')}
                    data-cdeadmin-qa-key="area-3-tab-strip"
                    className="sr-area3-app-tabs"
                  >
                    {dockedItems.map((item) => {
                      const isActive = item.instanceId === focusedId;
                      return (
                        <div
                          key={item.instanceId}
                          role="tab"
                          aria-selected={isActive}
                          tabIndex={isActive ? 0 : -1}
                          draggable={!item.isDashboard}
                          data-cdeadmin-tab-id={item.instanceId}
                          data-tab-active={isActive ? 'true' : 'false'}
                          className="sr-area3-app-tab"
                          onClick={() => shell.focusInstance(item.instanceId)}
                          onDragStart={(e) => {
                            if (item.isDashboard) return;
                            draggedTabOutsideRef.current = false;
                            e.dataTransfer?.setData('text/plain', item.instanceId);
                          }}
                          onDragLeave={() => {
                            draggedTabOutsideRef.current = true;
                          }}
                          onDragEnd={(e) => {
                            if (item.isDashboard) return;
                            const rect = area3Ref.current?.getBoundingClientRect();
                            const hasCoords =
                              Number.isFinite(e.clientX) && Number.isFinite(e.clientY);
                            const outsideCoords =
                              rect &&
                              hasCoords &&
                              (e.clientX < rect.left ||
                                e.clientX > rect.right ||
                                e.clientY < rect.top ||
                                e.clientY > rect.bottom);
                            if (outsideCoords || (!hasCoords && draggedTabOutsideRef.current)) {
                              shell.detachInstance(item.instanceId);
                            }
                            draggedTabOutsideRef.current = false;
                          }}
                        >
                          {!item.isDashboard && (
                            <Icon
                              iconKey={item.iconKey || 'command.default'}
                              decorative
                              size="1em"
                            />
                          )}
                          <span
                            title={item.title}
                            style={{
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {item.title}
                          </span>
                          {/* Active tab carries a small [x] to close the active application */}
                          {isActive && (
                            <button
                              type="button"
                              aria-label={gettext('Close %s', item.title)}
                              data-cdeadmin-qa-key="active-tab-close"
                              onClick={(e) => {
                                e.stopPropagation();
                                shell.closeInstance(item.instanceId);
                              }}
                              style={{
                                border: 'none',
                                background: 'transparent',
                                color: 'inherit',
                                cursor: 'pointer',
                                padding: '0 3px',
                                fontSize: '0.95rem',
                                lineHeight: 1,
                              }}
                            >
                              ×
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Area 3e Zoomed Surface: User Dashboard OR Active Docked Application */}
                <div
                  className="sr-zoom-surface"
                  style={{'--sr-surface-zoom': String(zoom3e)}}
                >
                  {fallbackArea3 && (
                    <Box
                      data-cdeadmin-qa-key="user-dashboard-surface"
                      data-dashboard-mode={dashboardTabbed ? 'tab' : 'placeholder'}
                      aria-hidden={Boolean(activeDockedItem && !activeDockedItem.isDashboard)}
                      onPointerDown={() => {
                        if (dashboardTabbed) shell.focusInstance(USER_DASHBOARD_ID);
                      }}
                      sx={{
                        flex: !activeDockedItem || activeDockedItem.isDashboard ? 1 : '0 0 0px',
                        display:
                          !activeDockedItem || activeDockedItem.isDashboard ? 'block' : 'none',
                        minHeight: 0,
                        overflow: 'auto',
                        position: 'relative',
                      }}
                    >
                      {fallbackArea3}
                    </Box>
                  )}
                  {!fallbackArea3 && (!activeDockedItem || activeDockedItem.isDashboard) && (
                    <Box
                      data-cdeadmin-qa-key="user-dashboard-surface"
                      data-dashboard-mode={dashboardTabbed ? 'tab' : 'placeholder'}
                      onPointerDown={() => {
                        if (dashboardTabbed) shell.focusInstance(USER_DASHBOARD_ID);
                      }}
                      sx={{flex: 1, minHeight: 0, overflow: 'auto', position: 'relative'}}
                    >
                      {userDashboard || (
                        <Box sx={{p: 3}}>
                          <Box sx={{fontSize: '1.125rem', fontWeight: 700, mb: 0.5}}>
                            {gettext('User Dashboard')}
                          </Box>
                          <Box sx={{fontSize: '0.875rem', color: 'text.secondary'}}>
                            {gettext(
                              'Select an application from the Side Menu or Applications menu to begin working.'
                            )}
                          </Box>
                        </Box>
                      )}
                    </Box>
                  )}
                  {activeDockedItem && !activeDockedItem.isDashboard && (
                    <Box
                      data-cdeadmin-qa-key={`docked-instance-${activeDockedItem.instanceId}`}
                      onPointerDown={() => shell.focusInstance(activeDockedItem.instanceId)}
                      sx={{
                        flex: 1,
                        minHeight: 0,
                        display: 'flex',
                        flexDirection: 'column',
                      }}
                    >
                      <ScratchScrollArea fillViewport style={{flex: 1, minHeight: 0, position: 'relative'}}>
                        <ShellSurfaceErrorBoundary
                          resetKey={`${activeDockedItem.instanceId}:work`}
                          surfaceName={activeDockedItem.title}
                        >
                          {activeDockedItem.renderWorkArea(activeDockedItem)}
                        </ShellSurfaceErrorBoundary>
                      </ScratchScrollArea>
                    </Box>
                  )}
                </div>
              </main>

              {/* Area 3c — Optional Right Side Drawer Island */}
              {rightVisible && (
                <aside
                  className="sr-island sr-island-3c"
                  data-area-part="3c"
                  aria-label={gettext('%s Right Drawer', focusedInstance.title)}
                  data-cdeadmin-qa-key="project-right-drawer"
                  style={{
                    width: `${rightWidth}px`,
                    flex: `0 0 ${rightWidth}px`,
                  }}
                >
                  <DrawerInsetResizeHandle
                    side="right"
                    invert
                    value={rightWidth}
                    min={200}
                    max={640}
                    onChange={(w) => shell.setDrawerWidth('right', w)}
                    label={gettext('Resize Right Side Drawer')}
                  />
                  <div
                    className="sr-zoom-surface"
                    style={{'--sr-surface-zoom': String(zoom3c)}}
                  >
                    <Toolbar
                      label={gettext('Right Side Drawer')}
                      trailing={
                        <IconButton
                          label={gettext('Close Right Side Drawer')}
                          onClick={() => shell.toggleInstanceRightDrawer()}
                        >
                          ×
                        </IconButton>
                      }
                    >
                      <Box sx={{display: 'flex', alignItems: 'center', gap: 0.5}}>
                        {(focusedInstance.rightViews || []).map((v) => (
                          <Button
                            key={v.id}
                            size="small"
                            intent={focusedInstance.rightMode === v.id ? 'primary' : 'neutral'}
                            onClick={() =>
                              shell.toggleInstanceRightDrawer(focusedInstance.instanceId, v.id)
                            }
                          >
                            {v.label}
                          </Button>
                        ))}
                      </Box>
                    </Toolbar>
                    <ScratchScrollArea fillViewport style={{flex: 1, minHeight: 0}}>
                      <ShellSurfaceErrorBoundary
                        resetKey={`${focusedInstance.instanceId}:right:${focusedInstance.rightMode || ''}`}
                        surfaceName={gettext('%s Right Drawer', focusedInstance.title)}
                      >
                        {focusedInstance.renderRightDrawer(focusedInstance)}
                      </ShellSurfaceErrorBoundary>
                    </ScratchScrollArea>
                  </div>
                </aside>
              )}
            </div>

            {/* Area 3d — Optional Status Bar Island (spans underneath 3e + 3c) */}
            {statusVisible && (
              <div
                className="sr-island sr-island-3d"
                data-area-part="3d"
                data-cdeadmin-qa-key="project-status-bar"
              >
                <StatusBar label={`${activeDockedItem.title} status`}>
                  {typeof activeDockedItem.renderStatus === 'function'
                    ? activeDockedItem.renderStatus(activeDockedItem)
                    : activeDockedItem.statusText}
                </StatusBar>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

ProjectWorkbenchFrame.propTypes = {
  fallbackArea3: PropTypes.node,
};
