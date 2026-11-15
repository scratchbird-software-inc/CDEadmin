/////////////////////////////////////////////////////////////
//
// ScratchRobin — Unified Configuration Dialog (Branch-Menu + Tabbed Forms)
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Dialog} from '../overlays/Dialog';
import {Button} from '../primitives/Button';
import {NumberField, TextField} from '../primitives/Field';
import {Checkbox, Select, Switch} from '../primitives/Choice';
import {SearchField, Slider} from '../primitives/AdvancedControls';
import {Banner} from '../feedback/Indicators';
import {Icon} from '../icons';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {
  ScratchBranchedTree,
  readBranchedTreePreferences,
  writeBranchedTreePreferences,
} from '../navigation/ScratchBranchedTree';
import {ScratchFilterTable} from '../data/beautiful/ScratchFilterTable';
import {
  readDefaultQueryLimits,
  writeDefaultQueryLimits,
} from '../query/QueryExecutionController';
import {ColorSchemesAndFontsEditor} from './settings/ColorSchemesAndFontsEditor';
import {ActionMenuToolbarEditor} from './settings/ActionMenuToolbarEditor';
import {SecurityAccessEditor} from './settings/SecurityAccessEditor';
import {DatabaseEnginesEditor} from './settings/DatabaseEnginesEditor';

const EXTRA_PREFS_STORAGE_KEY = 'scratchrobin.preferences.domains.v1';

const SHORTCUT_REFERENCE_ROWS = Object.freeze([
  {id: 'sc.run', action: 'Execute Query / Statement', scope: 'Query Surfaces', shortcut: 'F5 / Ctrl+Enter'},
  {id: 'sc.pause', action: 'Pause Step Cursor Fetch', scope: 'Query Surfaces', shortcut: 'Ctrl+Shift+P'},
  {id: 'sc.cancel', action: 'Cancel Running Query', scope: 'Query Surfaces', shortcut: 'Alt+Break / Esc'},
  {id: 'sc.left', action: 'Toggle Left Side Drawer (3a)', scope: 'Workbench Shell', shortcut: 'Ctrl+B'},
  {id: 'sc.right', action: 'Toggle Right Object Properties (3c)', scope: 'Workbench Shell', shortcut: 'Ctrl+I'},
  {id: 'sc.palette', action: 'Open Command Palette', scope: 'Workbench Shell', shortcut: 'Ctrl+K'},
]);

const DEFAULT_EXPANDED_BRANCHES = Object.freeze([
  'branch:workbench',
  'branch:databases',
  'branch:security',
  'branch:applications',
]);

function readExtraDomainPrefs() {
  try {
    const raw = window?.localStorage?.getItem(EXTRA_PREFS_STORAGE_KEY);
    if (!raw) return {};
    return JSON.parse(raw) || {};
  } catch {
    return {};
  }
}

function writeExtraDomainPrefs(next) {
  try {
    const merged = {...readExtraDomainPrefs(), ...next};
    window?.localStorage?.setItem(EXTRA_PREFS_STORAGE_KEY, JSON.stringify(merged));
    return merged;
  } catch {
    return next;
  }
}

/**
 * Maps legacy or programmatic `sectionId` strings (e.g. `appearance:schemes`,
 * `actions:iconbars`, `security:users`, `engines:connectors`, `chrome:sql-editor`)
 * onto `{pageId, tabId}` in the unified branch-menu + top-tabs layout.
 */
function resolveSectionTarget(sectionId, mode, appId, fallbackAppId) {
  if (!sectionId) {
    if (mode === 'application' && appId) {
      return {pageId: `chrome:${appId}`, tabId: 'layout'};
    }
    return {pageId: 'appearance', tabId: 'general'};
  }
  if (sectionId === 'chrome') {
    return {pageId: `chrome:${appId || fallbackAppId}`, tabId: 'layout'};
  }
  if (sectionId.startsWith('chrome:')) {
    return {pageId: sectionId, tabId: 'layout'};
  }
  switch (sectionId) {
  case 'appearance':
  case 'appearance:zoom':
    return {pageId: 'appearance', tabId: 'general'};
  case 'catalog':
  case 'appearance:tree':
    return {pageId: 'appearance', tabId: 'tree'};
  case 'themes':
  case 'appearance:schemes':
    return {pageId: 'themes', tabId: 'palettes'};
  case 'fonts':
  case 'appearance:fonts':
    return {pageId: 'fonts', tabId: 'typography'};
  case 'menus':
  case 'actions':
  case 'actions:global-menus':
    return {pageId: 'menus', tabId: 'global-menus'};
  case 'actions:app-menus':
    return {pageId: 'menus', tabId: 'app-menus'};
  case 'actions:iconbars':
    return {pageId: 'menus', tabId: 'iconbars'};
  case 'actions:icons':
    return {pageId: 'menus', tabId: 'icons'};
  case 'shortcuts':
    return {pageId: 'shortcuts', tabId: 'keymap'};
  case 'engines':
  case 'engines:connectors':
    return {pageId: 'engines', tabId: 'connectors'};
  case 'engines:paths':
    return {pageId: 'engines', tabId: 'paths'};
  case 'queries':
  case 'workspace':
    return {pageId: 'queries', tabId: 'execution'};
  case 'queries:export':
    return {pageId: 'queries', tabId: 'export'};
  case 'ddn':
    return {pageId: 'ddn', tabId: 'dialect'};
  case 'ddn:ai':
    return {pageId: 'ddn', tabId: 'ai'};
  case 'security':
  case 'security:apps':
    return {pageId: 'security', tabId: 'apps'};
  case 'security:users':
    return {pageId: 'security', tabId: 'users'};
  case 'security:groups':
    return {pageId: 'security', tabId: 'groups'};
  case 'security:session':
    return {pageId: 'security', tabId: 'session'};
  default:
    return {pageId: 'appearance', tabId: 'general'};
  }
}

function SettingsGroup({title, children}) {
  return (
    <fieldset
      style={{
        margin: 0,
        padding: '10px 14px 14px',
        border: '1px solid var(--sr-border-default)',
        borderRadius: 6,
        background: 'color-mix(in srgb, var(--sr-surface-subtle) 45%, var(--sr-surface-card))',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        minWidth: 0,
      }}
    >
      {title && (
        <div
          style={{
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: 'var(--sr-text-primary)',
            textAlign: 'center',
            paddingBottom: 6,
            borderBottom: '1px solid var(--sr-border-subtle)',
          }}
        >
          {title}
        </div>
      )}
      {children}
    </fieldset>
  );
}

SettingsGroup.propTypes = {
  title: PropTypes.node,
  children: PropTypes.node,
};

const PAGE_HELP_SUMMARY = Object.freeze({
  appearance:
    'Configure default workspace spacing, area zoom percentages, and Branched Tree line geometry.',
  themes:
    'Select a built-in or custom colour palette and choose which schemes appear in the top-bar quick switcher.',
  fonts:
    'Set UI, monospace SQL/code, and DDN diagram font stacks, sizes, line height, and ligatures.',
  menus:
    'Customize top-level menus, application menus, tabbed iconbars, quick-access strips, and semantic icons.',
  shortcuts:
    'Review workbench and query execution keyboard shortcuts.',
  engines:
    'Enable or disable database engine connectors shown in Data Navigator and configure optional local tool paths.',
  queries:
    'Control cursor step-fetch limits, default auto-commit behaviour, result delimiters, and destructive DDL prompts.',
  ddn:
    'Configure DDN exchange profile defaults, Git review gates on version acceptance, and optional BYOK AI drafting.',
  security:
    'Manage enabled workspace applications, user accounts, security groups, permissions, and idle session lock.',
  chrome:
    'Override drawer widths, default drawer visibility, area zoom, and reference SQL for the selected application.',
});

export function ScratchPreferencesDialog({
  open,
  mode = 'global',
  appId = null,
  appLabel = '',
  initialSection = null,
  settings = {},
  applications = [],
  actionsRegistry = null,
  fetchImpl = null,
  onSaveSettings,
  onRefreshAuthorization,
  onResetDrawers,
  onClose,
}) {
  const fallbackAppId = appId || applications[0]?.id || 'data-navigator';
  const isInitialAppMode = mode === 'application' && Boolean(appId) && !initialSection;
  const globalConfig = settings?.global || {};

  const initialTarget = resolveSectionTarget(initialSection, mode, appId, fallbackAppId);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPageId, setSelectedPageId] = useState(initialTarget.pageId);
  const [activeTabByPage, setActiveTabByPage] = useState(() => ({
    [initialTarget.pageId]: initialTarget.tabId,
  }));
  const [expandedIds, setExpandedIds] = useState(() => [...DEFAULT_EXPANDED_BRANCHES]);
  const [statusBanner, setStatusBanner] = useState('');
  const [showHelp, setShowHelp] = useState(false);
  const [localeRev, setLocaleRev] = useState(() => gettext.getRevision?.() || 0);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onLanguageChanged = (ev) => {
      setLocaleRev((prev) => ev?.detail?.revision ?? prev + 1);
    };
    window.addEventListener('scratchrobin:language-changed', onLanguageChanged);
    return () => window.removeEventListener('scratchrobin:language-changed', onLanguageChanged);
  }, []);

  // Patches accumulated from sub-editors (Schemes, Fonts, Menus/Iconbars, Engines)
  const [pendingGlobalPatch, setPendingGlobalPatch] = useState({});
  const [pendingAppPatches, setPendingAppPatches] = useState({});
  const [editedAppScope, setEditedAppScope] = useState(false);
  const [editedGlobalScope, setEditedGlobalScope] = useState(false);
  const [dirtyExtras, setDirtyExtras] = useState(false);

  const activeChromeAppId = useMemo(() => {
    if (selectedPageId.startsWith('chrome:')) {
      return selectedPageId.slice('chrome:'.length);
    }
    return fallbackAppId;
  }, [selectedPageId, fallbackAppId]);

  const activeChromeAppLabel = useMemo(() => {
    const match = applications.find((a) => a.id === activeChromeAppId);
    return match?.label || (activeChromeAppId === appId && appLabel) || activeChromeAppId;
  }, [applications, activeChromeAppId, appId, appLabel]);

  // Global Appearance & Zoom
  const [globalDefaultRibbon, setGlobalDefaultRibbon] = useState(
    globalConfig.default_tabbed_icon_bar !== false
  );
  const [globalPanelGap, setGlobalPanelGap] = useState(
    Number(globalConfig.panel_gap ?? 6)
  );
  const [globalAreaZoom, setGlobalAreaZoom] = useState(() => ({
    area_1: Number(globalConfig.area_zoom?.area_1 ?? 100),
    area_2: Number(globalConfig.area_zoom?.area_2 ?? 100),
    area_3a: Number(globalConfig.area_zoom?.area_3a ?? 100),
    area_3b: Number(globalConfig.area_zoom?.area_3b ?? 100),
    area_3c: Number(globalConfig.area_zoom?.area_3c ?? 100),
    area_3d: Number(globalConfig.area_zoom?.area_3d ?? 100),
    area_3e: Number(globalConfig.area_zoom?.area_3e ?? 100),
  }));

  // Application Chrome Overrides (per selected app)
  const [showRibbon, setShowRibbon] = useState(true);
  const [defaultLeftOpen, setDefaultLeftOpen] = useState(false);
  const [defaultRightOpen, setDefaultRightOpen] = useState(false);
  const [leftWidth, setLeftWidth] = useState(288);
  const [rightWidth, setRightWidth] = useState(320);
  const [sqlScript, setSqlScript] = useState('');
  const [appPanelGap, setAppPanelGap] = useState('');
  const [appAreaZoom, setAppAreaZoom] = useState({
    area_3a: '',
    area_3b: '',
    area_3c: '',
    area_3d: '',
    area_3e: '',
  });

  // Catalog, Branched Tree Geometry & Safety
  const [treePrefs, setTreePrefs] = useState(() => readBranchedTreePreferences());
  const [lockTimeout, setLockTimeout] = useState(
    Number(globalConfig.lock_screen_timeout_minutes ?? 15)
  );
  const [confirmDestructive, setConfirmDestructive] = useState(true);
  const [permittedApps, setPermittedApps] = useState(() =>
    applications.filter((a) => a.authorized !== false).map((a) => a.id)
  );

  // Queries & Step Limits
  const [queryLimits, setQueryLimits] = useState(() => readDefaultQueryLimits());
  const [autoCommit, setAutoCommit] = useState(true);
  const [csvDelimiter, setCsvDelimiter] = useState(',');

  // Designers, DDN & AI
  const [ddnDialect, setDdnDialect] = useState('ddn-next-1');
  const [gitReviewGate, setGitReviewGate] = useState(false);
  const [aiDraftingEnabled, setAiDraftingEnabled] = useState(false);
  const [aiModelEndpoint, setAiModelEndpoint] = useState('');

  // Optional External Tool Paths
  const [pgBinPath, setPgBinPath] = useState('');
  const [fbBinPath, setFbBinPath] = useState('');

  const navigateToSection = useCallback(
    (sectionId) => {
      const next = resolveSectionTarget(sectionId, mode, appId, fallbackAppId);
      setSelectedPageId(next.pageId);
      setActiveTabByPage((prev) => ({...prev, [next.pageId]: next.tabId}));
    },
    [mode, appId, fallbackAppId]
  );

  useEffect(() => {
    if (!open) return;
    setStatusBanner('');
    setShowHelp(false);
    setSearchQuery('');
    setEditedAppScope(false);
    setEditedGlobalScope(false);
    setDirtyExtras(false);
    setPendingGlobalPatch({});
    setPendingAppPatches({});

    const next = resolveSectionTarget(initialSection, mode, appId, fallbackAppId);
    setSelectedPageId(next.pageId);
    setActiveTabByPage((prev) => ({...prev, [next.pageId]: next.tabId}));

    setTreePrefs(readBranchedTreePreferences());
    setQueryLimits(readDefaultQueryLimits());

    const extras = readExtraDomainPrefs();
    setConfirmDestructive(extras.confirmDestructive !== false);
    setAutoCommit(extras.autoCommit !== false);
    setCsvDelimiter(extras.csvDelimiter || ',');
    setDdnDialect(extras.ddnDialect || 'ddn-next-1');
    setGitReviewGate(Boolean(extras.gitReviewGate));
    setAiDraftingEnabled(Boolean(extras.aiDraftingEnabled));
    setAiModelEndpoint(extras.aiModelEndpoint || '');
    setPgBinPath(extras.pgBinPath || '');
    setFbBinPath(extras.fbBinPath || '');
  }, [open, mode, appId, initialSection, fallbackAppId]);

  useEffect(() => {
    if (!open) return;
    const gCfg = settings?.global || {};
    setLockTimeout(Number(gCfg.lock_screen_timeout_minutes ?? 15));
    setGlobalDefaultRibbon(gCfg.default_tabbed_icon_bar !== false);
    setGlobalPanelGap(Number(gCfg.panel_gap ?? 6));
    setGlobalAreaZoom({
      area_1: Number(gCfg.area_zoom?.area_1 ?? 100),
      area_2: Number(gCfg.area_zoom?.area_2 ?? 100),
      area_3a: Number(gCfg.area_zoom?.area_3a ?? 100),
      area_3b: Number(gCfg.area_zoom?.area_3b ?? 100),
      area_3c: Number(gCfg.area_zoom?.area_3c ?? 100),
      area_3d: Number(gCfg.area_zoom?.area_3d ?? 100),
      area_3e: Number(gCfg.area_zoom?.area_3e ?? 100),
    });
    setPermittedApps(
      applications.filter((a) => a.authorized !== false).map((a) => a.id)
    );
  }, [open, settings, applications]);

  useEffect(() => {
    if (!open || !activeChromeAppId) return;
    const cfg = settings?.applications?.[activeChromeAppId] || {};
    setShowRibbon(cfg.show_tabbed_icon_bar !== false);
    setDefaultLeftOpen(Boolean(cfg.default_left_drawer_open));
    setDefaultRightOpen(Boolean(cfg.default_right_drawer_open));
    setLeftWidth(Number(cfg.left_drawer_width || 288));
    setRightWidth(Number(cfg.right_drawer_width || 320));
    setSqlScript(String(cfg.default_sql_reference_script || ''));
    setAppPanelGap(
      cfg.panel_gap === null || cfg.panel_gap === undefined ? '' : String(cfg.panel_gap)
    );
    setAppAreaZoom({
      area_3a: cfg.area_zoom?.area_3a ? String(cfg.area_zoom.area_3a) : '',
      area_3b: cfg.area_zoom?.area_3b ? String(cfg.area_zoom.area_3b) : '',
      area_3c: cfg.area_zoom?.area_3c ? String(cfg.area_zoom.area_3c) : '',
      area_3d: cfg.area_zoom?.area_3d ? String(cfg.area_zoom.area_3d) : '',
      area_3e: cfg.area_zoom?.area_3e ? String(cfg.area_zoom.area_3e) : '',
    });
  }, [open, activeChromeAppId, settings]);

  const branchMenuItems = useMemo(() => {
    const appChildren = (applications.length
      ? applications
      : [{id: activeChromeAppId, label: activeChromeAppLabel}]
    ).map((app) => ({
      id: `chrome:${app.id}`,
      label: app.label || app.id,
      iconKey: app.iconKey || 'command.default',
      keywords: `${app.label} ${app.id} application drawer width zoom ribbon spacing sql`,
    }));

    const branches = [
      {
        id: 'branch:workbench',
        label: gettext('Workbench'),
        iconKey: 'action.preferences',
        defaultPageId: 'appearance',
        keywords: 'workbench interface appearance themes fonts menus toolbars shortcuts',
        children: [
          {
            id: 'appearance',
            label: gettext('Appearance'),
            iconKey: 'action.preferences',
            keywords: 'appearance layout spacing panel gap zoom area branched tree stepx radius',
          },
          {
            id: 'themes',
            label: gettext('Colour Themes'),
            iconKey: 'action.preferences',
            keywords: 'colour color theme scheme palette dark light nord solarized high contrast custom',
          },
          {
            id: 'fonts',
            label: gettext('Fonts & Typography'),
            iconKey: 'object.type',
            keywords: 'fonts typography family size monospace ligatures line height ui sql diagram',
          },
          {
            id: 'menus',
            label: gettext('Menus & Toolbars'),
            iconKey: 'action.customize',
            keywords: 'actions menus toolbars iconbar notebookbar ribbon quick access icons',
          },
          {
            id: 'shortcuts',
            label: gettext('Keyboard Shortcuts'),
            iconKey: 'command.default',
            keywords: 'keyboard shortcuts hotkeys keybindings f5 execute palette',
          },
        ],
      },
      {
        id: 'branch:databases',
        label: gettext('Databases & DDN'),
        iconKey: 'object.database',
        defaultPageId: 'engines',
        keywords: 'databases engines connectors queries ddn designers ai',
        children: [
          {
            id: 'engines',
            label: gettext('Database Engines'),
            iconKey: 'object.database',
            keywords: 'database engines connectors postgresql firebird duckdb sqlite mariadb scratchbird binary path gbak isql',
          },
          {
            id: 'queries',
            label: gettext('Queries & Execution'),
            iconKey: 'tool.psql',
            keywords: 'queries execution max rows step fetch pause cancel autocommit csv delimiter destructive',
          },
          {
            id: 'ddn',
            label: gettext('Designers & DDN'),
            iconKey: 'tool.erd',
            keywords: 'designers ddn dialect git review gate ai byok drafting',
          },
        ],
      },
      {
        id: 'branch:security',
        label: gettext('Security'),
        iconKey: 'object.role',
        defaultPageId: 'security',
        keywords: 'security users groups roles permissions applications session lock timeout',
        children: [
          {
            id: 'security',
            label: gettext('Users, Groups & Access'),
            iconKey: 'object.role',
            keywords: 'security users groups roles grant revoke applications permissions lock screen timeout',
          },
        ],
      },
      {
        id: 'branch:applications',
        label: gettext('Applications'),
        iconKey: 'object.extension',
        defaultPageId: appChildren[0]?.id || `chrome:${activeChromeAppId}`,
        keywords: 'applications chrome drawer width zoom ribbon',
        children: appChildren,
      },
    ];

    const q = searchQuery.trim().toLowerCase();
    if (!q) return branches;

    return branches
      .map((branch) => {
        const selfMatch = `${branch.label} ${branch.keywords || ''}`.toLowerCase().includes(q);
        const matchingChildren = (branch.children || []).filter((child) =>
          `${child.label} ${child.keywords || ''}`.toLowerCase().includes(q)
        );
        if (matchingChildren.length > 0) {
          return {...branch, children: matchingChildren};
        }
        return selfMatch ? branch : null;
      })
      .filter(Boolean);
  }, [applications, activeChromeAppId, activeChromeAppLabel, searchQuery, localeRev]);

  const pageSpec = useMemo(() => {
    if (selectedPageId.startsWith('chrome:')) {
      return {
        title: activeChromeAppLabel,
        helpKey: 'chrome',
        tabs: [
          {id: 'layout', label: gettext('Layout & Drawers'), qaKey: 'app-tab-layout'},
          {id: 'defaults', label: gettext('Defaults'), qaKey: 'app-tab-defaults'},
        ],
      };
    }
    switch (selectedPageId) {
    case 'themes':
      return {
        title: gettext('Colour Themes'),
        helpKey: 'themes',
        tabs: [],
      };
    case 'fonts':
      return {
        title: gettext('Fonts & Typography'),
        helpKey: 'fonts',
        tabs: [],
      };
    case 'menus':
      return {
        title: gettext('Menus & Toolbars'),
        helpKey: 'menus',
        tabs: [
          {id: 'global-menus', label: gettext('Global Menus'), qaKey: 'actions-tab-global-menus'},
          {id: 'app-menus', label: gettext('Application Menus'), qaKey: 'actions-tab-app-menus'},
          {id: 'iconbars', label: gettext('Tabbed Iconbars'), qaKey: 'actions-tab-iconbars'},
          {id: 'icons', label: gettext('Action Icons'), qaKey: 'actions-tab-icons'},
        ],
      };
    case 'shortcuts':
      return {
        title: gettext('Keyboard Shortcuts'),
        helpKey: 'shortcuts',
        tabs: [],
      };
    case 'engines':
      return {
        title: gettext('Database Engines'),
        helpKey: 'engines',
        tabs: [
          {id: 'connectors', label: gettext('Connectors'), qaKey: 'engines-tab-connectors'},
          {id: 'paths', label: gettext('External Tool Paths'), qaKey: 'engines-tab-paths'},
        ],
      };
    case 'queries':
      return {
        title: gettext('Queries & Execution'),
        helpKey: 'queries',
        tabs: [
          {id: 'execution', label: gettext('Execution & Fetch'), qaKey: 'queries-tab-execution'},
          {id: 'export', label: gettext('Export & Safety'), qaKey: 'queries-tab-export'},
        ],
      };
    case 'ddn':
      return {
        title: gettext('Designers & DDN'),
        helpKey: 'ddn',
        tabs: [
          {id: 'dialect', label: gettext('DDN & Version Gates'), qaKey: 'ddn-tab-dialect'},
          {id: 'ai', label: gettext('AI Assistant'), qaKey: 'ddn-tab-ai'},
        ],
      };
    case 'security':
      return {
        title: gettext('Users, Groups & Access'),
        helpKey: 'security',
        tabs: [
          {id: 'apps', label: gettext('Applications'), qaKey: 'security-tab-apps'},
          {id: 'users', label: gettext('Users'), qaKey: 'security-tab-users'},
          {id: 'groups', label: gettext('Groups & Permissions'), qaKey: 'security-tab-groups'},
          {id: 'session', label: gettext('Session'), qaKey: 'security-tab-session'},
        ],
      };
    case 'appearance':
    default:
      return {
        title: gettext('Appearance'),
        helpKey: 'appearance',
        tabs: [
          {id: 'general', label: gettext('General'), qaKey: 'appearance-tab-general'},
          {id: 'tree', label: gettext('Branched Tree'), qaKey: 'appearance-tab-tree'},
        ],
      };
    }
  }, [selectedPageId, activeChromeAppLabel, localeRev]);

  const activeTabId = useMemo(() => {
    const stored = activeTabByPage[selectedPageId];
    if (pageSpec.tabs.length === 0) return 'default';
    if (stored && pageSpec.tabs.some((t) => t.id === stored)) return stored;
    return pageSpec.tabs[0].id;
  }, [activeTabByPage, selectedPageId, pageSpec.tabs]);

  const setActiveTab = (tabId) => {
    setActiveTabByPage((prev) => ({...prev, [selectedPageId]: tabId}));
  };

  const isAppPage = selectedPageId.startsWith('chrome:');
  const isDirty =
    editedGlobalScope ||
    editedAppScope ||
    dirtyExtras ||
    Object.keys(pendingGlobalPatch).length > 0 ||
    Object.keys(pendingAppPatches).length > 0;

  const handleTreePrefChange = (patch) => {
    setDirtyExtras(true);
    const next = writeBranchedTreePreferences(patch);
    setTreePrefs(next);
  };

  const handleResetDrawers = async () => {
    if (!activeChromeAppId) return;
    const reset = await onResetDrawers?.(activeChromeAppId);
    setLeftWidth(Number(reset?.left_drawer_width || 288));
    setRightWidth(Number(reset?.right_drawer_width || 320));
    setStatusBanner(
      gettext('Left and right drawer widths reset to defaults (288px / 320px).')
    );
  };

  const handleGlobalSubPatch = (patch) => {
    setEditedGlobalScope(true);
    setPendingGlobalPatch((prev) => ({...prev, ...patch}));
  };

  const handleAppSubPatch = (targetAppId, patch) => {
    setPendingAppPatches((prev) => ({
      ...prev,
      [targetAppId]: {...(prev[targetAppId] || {}), ...patch},
    }));
  };

  const persistAllSettings = async () => {
    writeBranchedTreePreferences(treePrefs);
    writeDefaultQueryLimits(queryLimits);
    writeExtraDomainPrefs({
      confirmDestructive,
      autoCommit,
      csvDelimiter,
      ddnDialect,
      gitReviewGate,
      aiDraftingEnabled,
      aiModelEndpoint,
      pgBinPath,
      fbBinPath,
    });

    const saveAppValues = async () => {
      const parsedAppZoom = {};
      Object.entries(appAreaZoom).forEach(([key, raw]) => {
        const trimmed = String(raw ?? '').trim();
        if (trimmed !== '' && Number.isFinite(Number(trimmed))) {
          parsedAppZoom[key] = Math.max(70, Math.min(160, Math.round(Number(trimmed))));
        }
      });
      const trimmedGap = String(appPanelGap ?? '').trim();
      const parsedGap =
        trimmedGap === '' || !Number.isFinite(Number(trimmedGap))
          ? null
          : Math.max(0, Math.min(24, Math.round(Number(trimmedGap))));

      const extraForActive = pendingAppPatches[activeChromeAppId] || {};
      await onSaveSettings?.({
        scope: 'application',
        appId: activeChromeAppId,
        values: {
          show_tabbed_icon_bar: showRibbon,
          default_left_drawer_open: defaultLeftOpen,
          default_right_drawer_open: defaultRightOpen,
          left_drawer_width: Number(leftWidth) || 288,
          right_drawer_width: Number(rightWidth) || 320,
          default_sql_reference_script: sqlScript,
          panel_gap: parsedGap,
          area_zoom: parsedAppZoom,
          ...extraForActive,
        },
      });
    };

    const saveExtraPatchedApps = async (skipAppId = null) => {
      for (const [patchedAppId, patchVals] of Object.entries(pendingAppPatches)) {
        if (patchedAppId === skipAppId) continue;
        await onSaveSettings?.({
          scope: 'application',
          appId: patchedAppId,
          values: patchVals,
        });
      }
    };

    const saveGlobalValues = async () => {
      const clampPct = (v) =>
        Math.max(70, Math.min(160, Math.round(Number(v) || 100)));
      const clampedGap = Number.isFinite(Number(globalPanelGap))
        ? Math.max(0, Math.min(24, Math.round(Number(globalPanelGap))))
        : 6;

      await onSaveSettings?.({
        scope: 'global',
        values: {
          lock_screen_timeout_minutes: Number(lockTimeout) || 0,
          default_tabbed_icon_bar: globalDefaultRibbon,
          panel_gap: clampedGap,
          area_zoom: {
            area_1: clampPct(globalAreaZoom.area_1),
            area_2: clampPct(globalAreaZoom.area_2),
            area_3a: clampPct(globalAreaZoom.area_3a),
            area_3b: clampPct(globalAreaZoom.area_3b),
            area_3c: clampPct(globalAreaZoom.area_3c),
            area_3d: clampPct(globalAreaZoom.area_3d),
            area_3e: clampPct(globalAreaZoom.area_3e),
          },
          ...pendingGlobalPatch,
        },
        permittedApps,
      });
    };

    if (isAppPage || (isInitialAppMode && !editedGlobalScope)) {
      await saveAppValues();
      await saveExtraPatchedApps(activeChromeAppId);
      if (editedGlobalScope || Object.keys(pendingGlobalPatch).length > 0) {
        await saveGlobalValues();
      }
    } else {
      await saveGlobalValues();
      if (editedAppScope) {
        await saveAppValues();
        await saveExtraPatchedApps(activeChromeAppId);
      } else {
        await saveExtraPatchedApps(null);
      }
    }
  };

  const handleApply = async () => {
    await persistAllSettings();
    setEditedGlobalScope(false);
    setEditedAppScope(false);
    setDirtyExtras(false);
    setPendingGlobalPatch({});
    setPendingAppPatches({});
    setStatusBanner(gettext('Configuration changes applied.'));
  };

  const handleOk = async () => {
    await persistAllSettings();
    onClose?.();
  };

  return (
    <Dialog
      open={Boolean(open)}
      onClose={onClose}
      size="xlarge"
      title={
        isAppPage
          ? gettext('Configure — %s', activeChromeAppLabel)
          : gettext('Configure — ScratchRobin')
      }
      actions={
        <div style={{display: 'flex', gap: 8, justifyContent: 'space-between', width: '100%', alignItems: 'center'}}>
          <div style={{display: 'flex', gap: 8, alignItems: 'center'}}>
            <Button
              intent="neutral"
              data-cdeadmin-qa-key="settings-help"
              onClick={() => setShowHelp((prev) => !prev)}
            >
              {gettext('Help')}
            </Button>
            {isAppPage && (
              <Button
                intent="neutral"
                data-cdeadmin-qa-key="settings-reset-drawers"
                onClick={handleResetDrawers}
              >
                {gettext('Reset Drawer Sizes')}
              </Button>
            )}
          </div>
          <div style={{display: 'flex', gap: 8, alignItems: 'center'}}>
            <Button
              intent="primary"
              data-cdeadmin-qa-key="settings-save"
              onClick={handleOk}
            >
              {gettext('OK')}
            </Button>
            <Button
              intent="neutral"
              disabled={!isDirty}
              data-cdeadmin-qa-key="settings-apply"
              onClick={handleApply}
            >
              {gettext('Apply')}
            </Button>
            <Button
              intent="neutral"
              data-cdeadmin-qa-key="settings-cancel"
              onClick={onClose}
            >
              {gettext('Cancel')}
            </Button>
          </div>
        </div>
      }
    >
      <div
        data-cdeadmin-qa-key="scratch-preferences-dialog"
        style={{
          margin: -16,
          height: 'min(620px, 74vh)',
          minHeight: 490,
          display: 'grid',
          gridTemplateColumns: '246px minmax(0, 1fr)',
          overflow: 'hidden',
          background: 'var(--sr-surface-card)',
        }}
      >
        {/* Left Pane: Compact Search + Branched-Menu Navigation */}
        <div
          style={{
            borderRight: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-card)',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '8px 10px',
              borderBottom: '1px solid var(--sr-border-subtle)',
              flexShrink: 0,
            }}
          >
            <SearchField
              aria-label={gettext('Search configuration')}
              placeholder={gettext('Search…')}
              value={searchQuery}
              onChange={(val) => {
                setSearchQuery(val);
                if (val && val.trim()) {
                  setExpandedIds([...DEFAULT_EXPANDED_BRANCHES]);
                }
              }}
              inputProps={{'data-cdeadmin-qa-key': 'settings-sidebar-search'}}
            />
          </div>

          <ScratchBranchedTree
            label={gettext('Configuration Categories')}
            items={branchMenuItems}
            selectedId={selectedPageId}
            expandedIds={expandedIds}
            onExpandedChange={setExpandedIds}
            renderIcon={(node) =>
              node?.iconKey ? <Icon iconKey={node.iconKey} decorative size="15px" /> : null
            }
            onSelect={(nodeOrId) => {
              const node = typeof nodeOrId === 'object' ? nodeOrId : null;
              const id = typeof nodeOrId === 'string' ? nodeOrId : node?.id;
              if (!id) return;
              if (id.startsWith('branch:')) {
                setExpandedIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
                const firstChild = node?.children?.[0]?.id || node?.defaultPageId;
                if (firstChild) {
                  setSelectedPageId(firstChild);
                }
                return;
              }
              setSelectedPageId(id);
            }}
            stickyAncestors={false}
            style={{flex: 1, minHeight: 0}}
          />
        </div>

        {/* Right Pane: Page Header + Optional Kate-Style Top Tab Bar + Form Body */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
            minHeight: 0,
            background: 'var(--sr-surface-card)',
          }}
        >
          {/* Page Header */}
          <div
            style={{
              padding: '11px 18px 9px',
              borderBottom:
                pageSpec.tabs.length > 0 ? 'none' : '1px solid var(--sr-border-default)',
              flexShrink: 0,
            }}
          >
            <div
              data-cdeadmin-qa-key="settings-page-title"
              style={{
                fontSize: '1.12rem',
                fontWeight: 600,
                lineHeight: 1.25,
                color: 'var(--sr-text-primary)',
              }}
            >
              {pageSpec.title}
            </div>
          </div>

          {/* Horizontal Top Tab Bar — rendered only when the page has multiple tabs */}
          {pageSpec.tabs.length > 0 && (
            <div
              role="tablist"
              aria-label={gettext('%s Sections', pageSpec.title)}
              style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${pageSpec.tabs.length}, minmax(0, 1fr))`,
                borderTop: '1px solid var(--sr-border-default)',
                borderBottom: '1px solid var(--sr-border-default)',
                background: 'var(--sr-surface-subtle)',
                flexShrink: 0,
              }}
            >
              {pageSpec.tabs.map((tab, idx) => {
                const selected = activeTabId === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    data-cdeadmin-qa-key={tab.qaKey}
                    onClick={() => setActiveTab(tab.id)}
                    style={{
                      appearance: 'none',
                      border: 'none',
                      borderRight:
                        idx < pageSpec.tabs.length - 1
                          ? '1px solid var(--sr-border-subtle)'
                          : 'none',
                      padding: '7px 12px',
                      fontSize: '0.8125rem',
                      fontFamily: 'inherit',
                      fontWeight: selected ? 600 : 500,
                      color: selected ? 'var(--sr-text-primary)' : 'var(--sr-text-secondary)',
                      background: selected
                        ? 'color-mix(in srgb, var(--sr-accent) 14%, var(--sr-surface-card))'
                        : 'transparent',
                      boxShadow: selected ? 'inset 0 -2px 0 var(--sr-accent)' : 'none',
                      cursor: 'pointer',
                      textAlign: 'center',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>
          )}

          {/* Scrollable Form Surface */}
          <ScratchScrollArea fillViewport style={{flex: 1, minHeight: 0}}>
            <div style={{padding: '14px 18px 18px', display: 'flex', flexDirection: 'column', gap: 14}}>
              {showHelp && PAGE_HELP_SUMMARY[pageSpec.helpKey] && (
                <Banner status="info">{PAGE_HELP_SUMMARY[pageSpec.helpKey]}</Banner>
              )}
              {statusBanner && <Banner status="info">{statusBanner}</Banner>}

              {/* Appearance -> General */}
              {selectedPageId === 'appearance' && activeTabId === 'general' && (
                <>
                  <SettingsGroup title={gettext('Workspace Layout')}>
                    <Checkbox
                      label={gettext('Enable internal Tabbed-Icon-Bar by default across applications')}
                      checked={globalDefaultRibbon}
                      onChange={(checked) => {
                        setEditedGlobalScope(true);
                        setGlobalDefaultRibbon(Boolean(checked));
                      }}
                    />
                    <div style={{maxWidth: 320}}>
                      <NumberField
                        label={gettext('Panel Spacing Between Areas (px, 0–24)')}
                        value={globalPanelGap}
                        inputProps={{'data-cdeadmin-qa-key': 'settings-global-panel-gap'}}
                        onChange={(e) => {
                          setEditedGlobalScope(true);
                          setGlobalPanelGap(Number(e.target.value));
                        }}
                      />
                    </div>
                  </SettingsGroup>

                  <SettingsGroup title={gettext('Per-Area Interface & Icon Zoom (%)')}>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10}}>
                      {[
                        ['area_1', gettext('Area 1 — Top Menu (%)')],
                        ['area_2', gettext('Area 2 — Side Menu (%)')],
                        ['area_3b', gettext('Area 3b — Tabbed-Notebook-Bar (%)')],
                        ['area_3e', gettext('Area 3e — Main Work Area (%)')],
                        ['area_3a', gettext('Area 3a — Left Drawer (%)')],
                        ['area_3c', gettext('Area 3c — Right Drawer (%)')],
                        ['area_3d', gettext('Area 3d — Status Bar (%)')],
                      ].map(([areaKey, areaLabel]) => (
                        <NumberField
                          key={areaKey}
                          label={areaLabel}
                          value={globalAreaZoom[areaKey]}
                          inputProps={{'data-cdeadmin-qa-key': `settings-global-zoom-${areaKey}`}}
                          onChange={(e) => {
                            setEditedGlobalScope(true);
                            setGlobalAreaZoom((prev) => ({
                              ...prev,
                              [areaKey]: Number(e.target.value) || 100,
                            }));
                          }}
                        />
                      ))}
                    </div>
                  </SettingsGroup>
                </>
              )}

              {/* Appearance -> Branched Tree */}
              {selectedPageId === 'appearance' && activeTabId === 'tree' && (
                <SettingsGroup title={gettext('Branched Menu Tree Geometry')}>
                  <Slider
                    label={gettext('Depth Indent Step — stepX (%s px)', treePrefs.stepX)}
                    min={12}
                    max={28}
                    step={1}
                    value={treePrefs.stepX}
                    onChange={(val) => handleTreePrefChange({stepX: val})}
                  />
                  <Slider
                    label={gettext('Quadratic Elbow Radius (%s px)', treePrefs.radius)}
                    min={4}
                    max={14}
                    step={1}
                    value={treePrefs.radius}
                    onChange={(val) => handleTreePrefChange({radius: val})}
                  />
                  <Switch
                    label={gettext('Show Sticky Ancestor Breadcrumb Bar on Deep Trees')}
                    checked={treePrefs.stickyAncestors}
                    onChange={(checked) => handleTreePrefChange({stickyAncestors: checked})}
                  />
                </SettingsGroup>
              )}

              {/* Colour Themes (single form, no top tabs needed) */}
              {selectedPageId === 'themes' && (
                <ColorSchemesAndFontsEditor
                  subView="schemes"
                  hideTabs
                  globalSettings={{...globalConfig, ...pendingGlobalPatch}}
                  onChangeGlobal={handleGlobalSubPatch}
                  onNavigateSubView={(sub) => navigateToSection(`appearance:${sub}`)}
                />
              )}

              {/* Fonts & Typography (single form, no top tabs needed) */}
              {selectedPageId === 'fonts' && (
                <ColorSchemesAndFontsEditor
                  subView="fonts"
                  hideTabs
                  globalSettings={{...globalConfig, ...pendingGlobalPatch}}
                  onChangeGlobal={handleGlobalSubPatch}
                  onNavigateSubView={(sub) => navigateToSection(`appearance:${sub}`)}
                />
              )}

              {/* Menus & Toolbars (4 top tabs) */}
              {selectedPageId === 'menus' && (
                <ActionMenuToolbarEditor
                  subView={activeTabId}
                  hideTabs
                  globalSettings={{...globalConfig, ...pendingGlobalPatch}}
                  applicationSettings={settings?.applications || {}}
                  applications={applications}
                  actionsRegistry={actionsRegistry}
                  onChangeGlobal={handleGlobalSubPatch}
                  onChangeApp={handleAppSubPatch}
                  onNavigateSubView={(sub) => setActiveTab(sub)}
                />
              )}

              {/* Keyboard Shortcuts (single form, no top tabs needed) */}
              {selectedPageId === 'shortcuts' && (
                <SettingsGroup title={gettext('Workbench & Query Surface Shortcuts')}>
                  <ScratchFilterTable
                    title={gettext('Keyboard Shortcuts')}
                    columns={[
                      {key: 'action', label: gettext('Action')},
                      {key: 'scope', label: gettext('Scope'), chip: true},
                      {key: 'shortcut', label: gettext('Shortcut'), mono: true},
                    ]}
                    rows={SHORTCUT_REFERENCE_ROWS}
                    maxHeight={320}
                  />
                </SettingsGroup>
              )}

              {/* Database Engines -> Connectors */}
              {selectedPageId === 'engines' && activeTabId === 'connectors' && (
                <DatabaseEnginesEditor
                  globalSettings={{...globalConfig, ...pendingGlobalPatch}}
                  fetchImpl={fetchImpl}
                  onChangeGlobal={handleGlobalSubPatch}
                />
              )}

              {/* Database Engines -> External Tool Paths */}
              {selectedPageId === 'engines' && activeTabId === 'paths' && (
                <SettingsGroup title={gettext('Optional Local Client Utility Paths')}>
                  <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
                    {gettext(
                      'ScratchRobin executes backup, restore, and DDL maintenance natively. Set local utility directories only if you also invoke external vendor CLI tools.'
                    )}
                  </div>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12}}>
                    <TextField
                      label={gettext('PostgreSQL Client Directory')}
                      value={pgBinPath}
                      placeholder="/usr/bin"
                      onChange={(e) => {
                        setDirtyExtras(true);
                        setPgBinPath(e.target.value);
                      }}
                    />
                    <TextField
                      label={gettext('Firebird Client Directory')}
                      value={fbBinPath}
                      placeholder="/opt/firebird/bin"
                      onChange={(e) => {
                        setDirtyExtras(true);
                        setFbBinPath(e.target.value);
                      }}
                    />
                  </div>
                </SettingsGroup>
              )}

              {/* Queries & Execution -> Execution & Fetch */}
              {selectedPageId === 'queries' && activeTabId === 'execution' && (
                <SettingsGroup title={gettext('Cursor Fetch & Transaction Defaults')}>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12}}>
                    <NumberField
                      label={gettext('Default Max Rows (0 = Unlimited)')}
                      min={0}
                      step={100}
                      value={queryLimits.maxRows}
                      onChange={(e) => {
                        setDirtyExtras(true);
                        setQueryLimits((prev) => ({
                          ...prev,
                          maxRows: Math.max(0, Number(e.target.value) || 0),
                        }));
                      }}
                    />
                    <NumberField
                      label={gettext('Default Rows per Step')}
                      min={10}
                      step={50}
                      value={queryLimits.rowsPerStep}
                      onChange={(e) => {
                        setDirtyExtras(true);
                        setQueryLimits((prev) => ({
                          ...prev,
                          rowsPerStep: Math.max(10, Number(e.target.value) || 250),
                        }));
                      }}
                    />
                  </div>
                  <Checkbox
                    label={gettext('Auto-commit statements by default in new SQL Editor tabs')}
                    checked={autoCommit}
                    onChange={(checked) => {
                      setDirtyExtras(true);
                      setAutoCommit(Boolean(checked));
                    }}
                  />
                </SettingsGroup>
              )}

              {/* Queries & Execution -> Export & Safety */}
              {selectedPageId === 'queries' && activeTabId === 'export' && (
                <>
                  <SettingsGroup title={gettext('Result Copy & CSV Formatting')}>
                    <div style={{maxWidth: 320}}>
                      <Select
                        label={gettext('CSV / Result Copy Delimiter')}
                        value={csvDelimiter}
                        onChange={(val) => {
                          setDirtyExtras(true);
                          setCsvDelimiter(val);
                        }}
                        options={[
                          {value: ',', label: gettext('Comma (,)')},
                          {value: ';', label: gettext('Semicolon (;)')},
                          {value: '\t', label: gettext('Tab (\\t)')},
                          {value: '|', label: gettext('Pipe (|)')},
                        ]}
                      />
                    </div>
                  </SettingsGroup>

                  <SettingsGroup title={gettext('Metadata Modification Safety')}>
                    <Checkbox
                      label={gettext('Confirm destructive metadata operations (DROP / TRUNCATE)')}
                      checked={confirmDestructive}
                      onChange={(checked) => {
                        setDirtyExtras(true);
                        setConfirmDestructive(Boolean(checked));
                      }}
                    />
                  </SettingsGroup>
                </>
              )}

              {/* Designers & DDN -> DDN & Version Gates */}
              {selectedPageId === 'ddn' && activeTabId === 'dialect' && (
                <SettingsGroup title={gettext('Diagram-Design-Notation (DDN) & Acceptance Gate')}>
                  <Select
                    label={gettext('Canonical DDN Dialect Profile')}
                    value={ddnDialect}
                    onChange={(val) => {
                      setDirtyExtras(true);
                      setDdnDialect(val);
                    }}
                    options={[
                      {value: 'ddn-next-1', label: 'ddn-next-1 (Standalone Open DDN 1.0)'},
                    ]}
                  />
                  <Checkbox
                    label={gettext('Require Git review gate when accepting design versions')}
                    checked={gitReviewGate}
                    onChange={(checked) => {
                      setDirtyExtras(true);
                      setGitReviewGate(Boolean(checked));
                    }}
                  />
                </SettingsGroup>
              )}

              {/* Designers & DDN -> AI Assistant */}
              {selectedPageId === 'ddn' && activeTabId === 'ai' && (
                <SettingsGroup title={gettext('Bring-Your-Own-Key AI Drafting')}>
                  <Checkbox
                    label={gettext('Enable BYOK AI drafting (draft proposals only — never accepts or publishes)')}
                    checked={aiDraftingEnabled}
                    onChange={(checked) => {
                      setDirtyExtras(true);
                      setAiDraftingEnabled(Boolean(checked));
                    }}
                  />
                  <TextField
                    label={gettext('AI Provider Model / Endpoint Reference')}
                    value={aiModelEndpoint}
                    disabled={!aiDraftingEnabled}
                    placeholder="https://api.example.org/v1/models"
                    onChange={(e) => {
                      setDirtyExtras(true);
                      setAiModelEndpoint(e.target.value);
                    }}
                  />
                </SettingsGroup>
              )}

              {/* Security -> Applications / Users / Groups */}
              {selectedPageId === 'security' && activeTabId !== 'session' && (
                <SecurityAccessEditor
                  subView={activeTabId}
                  hideTabs
                  applications={applications}
                  fetchImpl={fetchImpl}
                  onPermittedAppsChange={(nextAllowed) => {
                    setEditedGlobalScope(true);
                    setPermittedApps(nextAllowed);
                  }}
                  onRefreshAuthorization={onRefreshAuthorization}
                  onNavigateSubView={(sub) => setActiveTab(sub)}
                />
              )}

              {/* Security -> Session */}
              {selectedPageId === 'security' && activeTabId === 'session' && (
                <SettingsGroup title={gettext('Workspace Session & Idle Lock')}>
                  <div style={{maxWidth: 340}}>
                    <NumberField
                      label={gettext('Idle Lock Screen Timeout (minutes, 0 = manual only)')}
                      value={lockTimeout}
                      onChange={(e) => {
                        setEditedGlobalScope(true);
                        setLockTimeout(Number(e.target.value) || 0);
                      }}
                    />
                  </div>
                </SettingsGroup>
              )}

              {/* Applications -> <App> -> Layout & Drawers */}
              {isAppPage && activeTabId === 'layout' && (
                <>
                  <SettingsGroup title={gettext('Toolbars & Side Drawers')}>
                    <Checkbox
                      label={gettext('Show internal Tabbed-Icon-Bar (NotebookBar) when focused')}
                      checked={showRibbon}
                      onChange={(checked) => {
                        setEditedAppScope(true);
                        setShowRibbon(Boolean(checked));
                      }}
                    />
                    <Checkbox
                      label={gettext('Open Left Side Drawer by default for new instances')}
                      checked={defaultLeftOpen}
                      onChange={(checked) => {
                        setEditedAppScope(true);
                        setDefaultLeftOpen(Boolean(checked));
                      }}
                    />
                    <Checkbox
                      label={gettext('Open Right Side Drawer by default for new instances')}
                      checked={defaultRightOpen}
                      onChange={(checked) => {
                        setEditedAppScope(true);
                        setDefaultRightOpen(Boolean(checked));
                      }}
                    />
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12}}>
                      <NumberField
                        label={gettext('Left Drawer Width (px)')}
                        value={leftWidth}
                        onChange={(e) => {
                          setEditedAppScope(true);
                          setLeftWidth(Number(e.target.value) || 288);
                        }}
                      />
                      <NumberField
                        label={gettext('Right Drawer Width (px)')}
                        value={rightWidth}
                        onChange={(e) => {
                          setEditedAppScope(true);
                          setRightWidth(Number(e.target.value) || 320);
                        }}
                      />
                    </div>
                  </SettingsGroup>

                  <SettingsGroup title={gettext('Spacing & Area Zoom Overrides (blank = Global)')}>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10}}>
                      <NumberField
                        label={gettext('Panel Spacing Override (px, 0–24)')}
                        value={appPanelGap}
                        placeholder={String(globalConfig.panel_gap ?? 6)}
                        inputProps={{'data-cdeadmin-qa-key': 'settings-app-panel-gap'}}
                        onChange={(e) => {
                          setEditedAppScope(true);
                          setAppPanelGap(e.target.value);
                        }}
                      />
                      {[
                        ['area_3b', gettext('Area 3b — Tabbed-Notebook-Bar Zoom (%)')],
                        ['area_3a', gettext('Area 3a — Left Drawer Zoom (%)')],
                        ['area_3c', gettext('Area 3c — Right Drawer Zoom (%)')],
                        ['area_3d', gettext('Area 3d — Status Bar Zoom (%)')],
                        ['area_3e', gettext('Area 3e — Main Work Area Zoom (%)')],
                      ].map(([areaKey, areaLabel]) => (
                        <NumberField
                          key={areaKey}
                          label={areaLabel}
                          value={appAreaZoom[areaKey]}
                          placeholder={String(globalConfig.area_zoom?.[areaKey] ?? 100)}
                          inputProps={{'data-cdeadmin-qa-key': `settings-app-zoom-${areaKey}`}}
                          onChange={(e) => {
                            setEditedAppScope(true);
                            setAppAreaZoom((prev) => ({...prev, [areaKey]: e.target.value}));
                          }}
                        />
                      ))}
                    </div>
                  </SettingsGroup>
                </>
              )}

              {/* Applications -> <App> -> Defaults */}
              {isAppPage && activeTabId === 'defaults' && (
                <SettingsGroup title={gettext('Startup & Reference Defaults')}>
                  <TextField
                    label={gettext('Default SQL Reference Script')}
                    value={sqlScript}
                    placeholder="-- Common diagnostic or reference SQL script"
                    onChange={(e) => {
                      setEditedAppScope(true);
                      setSqlScript(e.target.value);
                    }}
                  />
                </SettingsGroup>
              )}
            </div>
          </ScratchScrollArea>
        </div>
      </div>
    </Dialog>
  );
}

ScratchPreferencesDialog.propTypes = {
  open: PropTypes.bool,
  mode: PropTypes.oneOf(['application', 'global']),
  appId: PropTypes.string,
  appLabel: PropTypes.string,
  initialSection: PropTypes.string,
  settings: PropTypes.object,
  applications: PropTypes.array,
  actionsRegistry: PropTypes.object,
  fetchImpl: PropTypes.func,
  onSaveSettings: PropTypes.func,
  onRefreshAuthorization: PropTypes.func,
  onResetDrawers: PropTypes.func,
  onClose: PropTypes.func,
};
