/////////////////////////////////////////////////////////////
//
// ScratchRobin — Comprehensive Preferences, Schemes, Fonts, Menus, Security & Engines
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Dialog} from '../overlays/Dialog';
import {Button} from '../primitives/Button';
import {NumberField, TextField} from '../primitives/Field';
import {Checkbox, Select, Switch} from '../primitives/Choice';
import {SearchField, Slider} from '../primitives/AdvancedControls';
import {Banner} from '../feedback/Indicators';
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
  const isInitialAppMode = mode === 'application' && Boolean(appId) && !initialSection;
  const globalConfig = settings?.global || {};

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState(() => {
    if (initialSection) return initialSection;
    return isInitialAppMode ? `chrome:${appId}` : 'appearance';
  });
  const [expandedIds, setExpandedIds] = useState(() => [
    'appearance',
    'actions',
    'security',
    'engines',
    'chrome',
    'workspace',
  ]);
  const [statusBanner, setStatusBanner] = useState('');

  // Patches accumulated from sub-editors (Schemes, Fonts, Menus/Iconbars, Engines)
  const [pendingGlobalPatch, setPendingGlobalPatch] = useState({});
  const [pendingAppPatches, setPendingAppPatches] = useState({});

  const activeChromeAppId = useMemo(() => {
    if (selectedNodeId.startsWith('chrome:')) {
      return selectedNodeId.slice('chrome:'.length);
    }
    return appId || applications[0]?.id || 'data-navigator';
  }, [selectedNodeId, appId, applications]);

  const activeChromeAppLabel = useMemo(() => {
    const match = applications.find((a) => a.id === activeChromeAppId);
    return match?.label || (activeChromeAppId === appId && appLabel) || activeChromeAppId;
  }, [applications, activeChromeAppId, appId, appLabel]);

  // Domain 1 — Global Appearance & Zoom
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
  const [editedAppScope, setEditedAppScope] = useState(false);
  const [editedGlobalScope, setEditedGlobalScope] = useState(false);

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

  // Native Binary Paths
  const [pgBinPath, setPgBinPath] = useState('');
  const [fbBinPath, setFbBinPath] = useState('');

  useEffect(() => {
    if (!open) return;
    setStatusBanner('');
    setSearchQuery('');
    setEditedAppScope(false);
    setEditedGlobalScope(false);
    setPendingGlobalPatch({});
    setPendingAppPatches({});
    setSelectedNodeId(
      initialSection || (mode === 'application' && appId ? `chrome:${appId}` : 'appearance')
    );
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
  }, [open, mode, appId, initialSection]);

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

  const domainTreeNodes = useMemo(() => {
    const appChildren = (applications.length
      ? applications
      : [{id: activeChromeAppId, label: activeChromeAppLabel}]
    ).map((app) => ({
      id: `chrome:${app.id}`,
      label: app.label || app.id,
      keywords: `${app.label} ${app.id} drawer width zoom ribbon spacing`,
    }));

    const baseNodes = [
      {
        id: 'appearance',
        label: gettext('1. Appearance, Schemes & Fonts'),
        keywords: 'theme colour scheme palette dark light nord solarized fonts typography zoom spacing',
        children: [
          {
            id: 'appearance:schemes',
            label: gettext('Colour Schemes'),
            keywords: 'colour color scheme palette dark light nord solarized high contrast custom',
          },
          {
            id: 'appearance:fonts',
            label: gettext('Fonts & Typography'),
            keywords: 'font family size monospace ligatures line height ui sql diagram',
          },
          {
            id: 'appearance:zoom',
            label: gettext('Island Spacing & Area Zoom'),
            keywords: 'panel gap spacing zoom area scale',
          },
        ],
      },
      {
        id: 'actions',
        label: gettext('2. Actions, Menus & Iconbars'),
        keywords: 'action menu editor toolbar iconbar notebookbar ribbon quick access icons',
        children: [
          {
            id: 'actions:global-menus',
            label: gettext('Global Top Menus (Area 1)'),
            keywords: 'global top menu applications window help custom menu',
          },
          {
            id: 'actions:app-menus',
            label: gettext('Application Menus (Area 1)'),
            keywords: 'application menu object query design cube bi mesh',
          },
          {
            id: 'actions:iconbars',
            label: gettext('Tabbed-Notebook Iconbars (3b)'),
            keywords: 'tabbed notebook iconbar 3b 3b1 quick access ribbon icons',
          },
          {
            id: 'actions:icons',
            label: gettext('Action Icons & Status'),
            keywords: 'semantic icon assignment enabled disabled invisible status',
          },
        ],
      },
      {
        id: 'security',
        label: gettext('3. Security & Access'),
        keywords: 'security configuration users groups roles grant revoke applications permissions',
        children: [
          {
            id: 'security:apps',
            label: gettext('Application Availability'),
            keywords: 'turn on off applications available workspace dock',
          },
          {
            id: 'security:users',
            label: gettext('Users & Grants'),
            keywords: 'users accounts grant revoke roles active locked',
          },
          {
            id: 'security:groups',
            label: gettext('Groups & Permissions'),
            keywords: 'groups roles permissions capabilities grant revoke',
          },
        ],
      },
      {
        id: 'engines',
        label: gettext('4. Database Engines'),
        keywords: 'database engines connectors turn on off postgresql firebird duckdb sqlite mariadb scratchbird',
        children: [
          {
            id: 'engines:connectors',
            label: gettext('Engines On / Off'),
            keywords: 'enable disable database engine connector',
          },
          {
            id: 'shortcuts',
            label: gettext('Binary Paths & Shortcuts'),
            keywords: 'keyboard shortcuts binary path postgresql firebird gbak isql',
          },
        ],
      },
      {
        id: 'chrome',
        label: gettext('5. Application Chrome'),
        keywords: 'application settings left right drawer width ribbon notebookbar override',
        children: appChildren,
      },
      {
        id: 'workspace',
        label: gettext('6. Queries, Tree & DDN'),
        keywords: 'queries max rows step branched tree ddn ai',
        children: [
          {
            id: 'queries',
            label: gettext('Queries & Step Limits'),
            keywords: 'max rows per step fetch pause cancel autocommit csv delimiter',
          },
          {
            id: 'catalog',
            label: gettext('Branched Tree & Safety'),
            keywords: 'branched tree stepx elbow radius sticky ancestors destructive',
          },
          {
            id: 'ddn',
            label: gettext('Designers, DDN & AI'),
            keywords: 'ddn dialect git review gate ai byok drafting',
          },
        ],
      },
    ];

    const q = searchQuery.trim().toLowerCase();
    if (!q) return baseNodes;
    return baseNodes.filter((node) => {
      const selfMatch = `${node.label} ${node.keywords || ''}`.toLowerCase().includes(q);
      const childMatch = (node.children || []).some((c) =>
        `${c.label} ${c.keywords || ''}`.toLowerCase().includes(q)
      );
      return selfMatch || childMatch;
    });
  }, [applications, activeChromeAppId, activeChromeAppLabel, searchQuery]);

  const activeDomainKey = useMemo(() => {
    if (selectedNodeId === 'chrome' || selectedNodeId.startsWith('chrome:')) {
      return 'chrome';
    }
    if (selectedNodeId === 'appearance' || selectedNodeId === 'appearance:zoom') {
      return 'appearance:zoom';
    }
    if (selectedNodeId === 'actions') return 'actions:global-menus';
    if (selectedNodeId === 'security') return 'security:apps';
    if (selectedNodeId === 'engines') return 'engines:connectors';
    if (selectedNodeId === 'workspace') return 'queries';
    return selectedNodeId;
  }, [selectedNodeId]);

  const handleTreePrefChange = (patch) => {
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

  const handleSave = async () => {
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

    if (activeDomainKey === 'chrome' || (isInitialAppMode && !editedGlobalScope)) {
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

    onClose?.();
  };

  return (
    <Dialog
      open={Boolean(open)}
      onClose={onClose}
      size="xlarge"
      title={
        activeDomainKey === 'chrome'
          ? gettext('Preferences & Application Settings — %s', activeChromeAppLabel)
          : gettext('ScratchRobin Preferences & Workspace Settings')
      }
      actions={
        <div style={{display: 'flex', gap: 8, justifyContent: 'space-between', width: '100%', alignItems: 'center'}}>
          <div>
            {activeDomainKey === 'chrome' && (
              <Button
                intent="neutral"
                data-cdeadmin-qa-key="settings-reset-drawers"
                onClick={handleResetDrawers}
              >
                {gettext('Reset Drawer Sizes to Default')}
              </Button>
            )}
          </div>
          <div style={{display: 'flex', gap: 8}}>
            <Button intent="neutral" onClick={onClose}>
              {gettext('Cancel')}
            </Button>
            <Button
              intent="primary"
              data-cdeadmin-qa-key="settings-save"
              onClick={handleSave}
            >
              {gettext('Save Settings')}
            </Button>
          </div>
        </div>
      }
    >
      <div
        data-cdeadmin-qa-key="scratch-preferences-dialog"
        style={{display: 'flex', flexDirection: 'column', gap: 10, minHeight: 460}}
      >
        <SearchField
          label={gettext('Search preferences')}
          placeholder={gettext('Filter settings across schemes, fonts, menus, security, engines & queries…')}
          value={searchQuery}
          onChange={setSearchQuery}
        />

        {statusBanner && <Banner status="info">{statusBanner}</Banner>}

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '265px minmax(0, 1fr)',
            gap: 14,
            flex: 1,
            minHeight: 400,
          }}
        >
          {/* Left Multi-Domain Branched Menu Navigator */}
          <div
            style={{
              border: '1px solid var(--sr-border-default)',
              borderRadius: 'var(--sr-island-radius, 12px)',
              background: 'var(--sr-surface-subtle)',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <ScratchBranchedTree
              ariaLabel={gettext('Preference Domains')}
              nodes={domainTreeNodes}
              selectedId={selectedNodeId}
              expandedIds={expandedIds}
              onExpandedChange={setExpandedIds}
              onSelect={(id) => {
                if (id === 'chrome') {
                  setSelectedNodeId(`chrome:${activeChromeAppId}`);
                } else {
                  setSelectedNodeId(id);
                }
              }}
              showStickyAncestors={false}
              style={{height: 410}}
            />
          </div>

          {/* Right Domain Surface */}
          <ScratchScrollArea
            style={{
              border: '1px solid var(--sr-border-default)',
              borderRadius: 'var(--sr-island-radius, 12px)',
              background: 'var(--sr-surface-card)',
              maxHeight: 430,
            }}
          >
            <div style={{padding: 14, display: 'flex', flexDirection: 'column', gap: 14}}>
              {activeDomainKey === 'appearance:zoom' && (
                <>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap'}}>
                    <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
                      {gettext('1. Appearance, Island Spacing & Global Area Zoom')}
                    </div>
                    <div style={{display: 'flex', gap: 6}}>
                      <Button
                        intent="neutral"
                        data-cdeadmin-qa-key="jump-to-schemes"
                        onClick={() => setSelectedNodeId('appearance:schemes')}
                      >
                        {gettext('Colour Schemes…')}
                      </Button>
                      <Button
                        intent="neutral"
                        data-cdeadmin-qa-key="jump-to-fonts"
                        onClick={() => setSelectedNodeId('appearance:fonts')}
                      >
                        {gettext('Fonts & Typography…')}
                      </Button>
                    </div>
                  </div>
                  <Checkbox
                    label={gettext('Enable internal Tabbed-Icon-Bar by default across applications')}
                    checked={globalDefaultRibbon}
                    onChange={(checked) => {
                      setEditedGlobalScope(true);
                      setGlobalDefaultRibbon(Boolean(checked));
                    }}
                  />
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12}}>
                    <NumberField
                      label={gettext('Panel Spacing Between Areas (px, 0–24)')}
                      value={globalPanelGap}
                      inputProps={{'data-cdeadmin-qa-key': 'settings-global-panel-gap'}}
                      onChange={(e) => {
                        setEditedGlobalScope(true);
                        setGlobalPanelGap(Number(e.target.value));
                      }}
                    />
                    <NumberField
                      label={gettext('Idle Lock Screen Timeout (minutes, 0 = manual only)')}
                      value={lockTimeout}
                      onChange={(e) => {
                        setEditedGlobalScope(true);
                        setLockTimeout(Number(e.target.value) || 0);
                      }}
                    />
                  </div>
                  <div>
                    <div style={{fontWeight: 600, fontSize: '0.8rem', marginBottom: 8}}>
                      {gettext('Per-Area Icon & Font Zoom (%)')}
                    </div>
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
                  </div>
                </>
              )}

              {activeDomainKey === 'appearance:schemes' && (
                <ColorSchemesAndFontsEditor
                  subView="schemes"
                  globalSettings={{...globalConfig, ...pendingGlobalPatch}}
                  onChangeGlobal={handleGlobalSubPatch}
                />
              )}

              {activeDomainKey === 'appearance:fonts' && (
                <ColorSchemesAndFontsEditor
                  subView="fonts"
                  globalSettings={{...globalConfig, ...pendingGlobalPatch}}
                  onChangeGlobal={handleGlobalSubPatch}
                />
              )}

              {activeDomainKey.startsWith('actions:') && (
                <ActionMenuToolbarEditor
                  subView={activeDomainKey.slice('actions:'.length)}
                  globalSettings={{...globalConfig, ...pendingGlobalPatch}}
                  applicationSettings={settings?.applications || {}}
                  applications={applications}
                  actionsRegistry={actionsRegistry}
                  onChangeGlobal={handleGlobalSubPatch}
                  onChangeApp={handleAppSubPatch}
                />
              )}

              {activeDomainKey.startsWith('security:') && (
                <SecurityAccessEditor
                  subView={activeDomainKey.slice('security:'.length)}
                  applications={applications}
                  fetchImpl={fetchImpl}
                  onPermittedAppsChange={(nextAllowed) => {
                    setEditedGlobalScope(true);
                    setPermittedApps(nextAllowed);
                  }}
                  onRefreshAuthorization={onRefreshAuthorization}
                />
              )}

              {activeDomainKey === 'engines:connectors' && (
                <DatabaseEnginesEditor
                  globalSettings={{...globalConfig, ...pendingGlobalPatch}}
                  fetchImpl={fetchImpl}
                  onChangeGlobal={handleGlobalSubPatch}
                />
              )}

              {activeDomainKey === 'chrome' && (
                <>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap'}}>
                    <div style={{fontWeight: 700, fontSize: '0.9rem'}}>
                      {gettext('Application Chrome Defaults — %s', activeChromeAppLabel)}
                    </div>
                    <Button
                      intent="neutral"
                      onClick={() => setSelectedNodeId('actions:iconbars')}
                    >
                      {gettext('Customize Iconbar & Menus…')}
                    </Button>
                  </div>
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
                  <div>
                    <div style={{fontWeight: 600, fontSize: '0.8rem', marginBottom: 8}}>
                      {gettext('Application Layout Spacing & Area Zoom Overrides (blank = Global)')}
                    </div>
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
                  </div>
                  <TextField
                    label={gettext('Default SQL Reference Script')}
                    value={sqlScript}
                    placeholder="-- Common diagnostic or reference SQL script"
                    onChange={(e) => {
                      setEditedAppScope(true);
                      setSqlScript(e.target.value);
                    }}
                  />
                </>
              )}

              {activeDomainKey === 'catalog' && (
                <>
                  <div style={{fontWeight: 700, fontSize: '0.9rem'}}>
                    {gettext('Branched Menu Tree Geometry & Metadata Safety')}
                  </div>
                  <div
                    style={{
                      padding: 12,
                      borderRadius: 8,
                      border: '1px solid var(--sr-border-subtle)',
                      background: 'var(--sr-surface-subtle)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 10,
                    }}
                  >
                    <div style={{fontWeight: 600, fontSize: '0.8rem'}}>
                      {gettext('Branched Menu Tree Live Tuning')}
                    </div>
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
                  </div>

                  <Switch
                    label={gettext('Confirm Destructive Metadata Operations (DROP / TRUNCATE)')}
                    checked={confirmDestructive}
                    onChange={setConfirmDestructive}
                  />
                </>
              )}

              {activeDomainKey === 'queries' && (
                <>
                  <div style={{fontWeight: 700, fontSize: '0.9rem'}}>
                    {gettext('Queries, Fetch Step Limits & Execution')}
                  </div>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12}}>
                    <NumberField
                      label={gettext('Default Max Rows (0 = Unlimited)')}
                      min={0}
                      step={100}
                      value={queryLimits.maxRows}
                      onChange={(e) =>
                        setQueryLimits((prev) => ({
                          ...prev,
                          maxRows: Math.max(0, Number(e.target.value) || 0),
                        }))
                      }
                    />
                    <NumberField
                      label={gettext('Default Rows per Step')}
                      min={10}
                      step={50}
                      value={queryLimits.rowsPerStep}
                      onChange={(e) =>
                        setQueryLimits((prev) => ({
                          ...prev,
                          rowsPerStep: Math.max(10, Number(e.target.value) || 250),
                        }))
                      }
                    />
                  </div>
                  <Switch
                    label={gettext('Auto-Commit Statements by Default')}
                    checked={autoCommit}
                    onChange={setAutoCommit}
                  />
                  <Select
                    label={gettext('CSV / Result Copy Delimiter')}
                    value={csvDelimiter}
                    onChange={setCsvDelimiter}
                    options={[
                      {value: ',', label: gettext('Comma (,)')},
                      {value: ';', label: gettext('Semicolon (;)')},
                      {value: '\t', label: gettext('Tab (\\t)')},
                      {value: '|', label: gettext('Pipe (|)')},
                    ]}
                  />
                </>
              )}

              {activeDomainKey === 'ddn' && (
                <>
                  <div style={{fontWeight: 700, fontSize: '0.9rem'}}>
                    {gettext('Designers, DDN & Optional BYOK AI')}
                  </div>
                  <Select
                    label={gettext('Canonical DDN Dialect Profile')}
                    value={ddnDialect}
                    onChange={setDdnDialect}
                    options={[
                      {value: 'ddn-next-1', label: 'ddn-next-1 (Standalone Open DDN 1.0)'},
                    ]}
                  />
                  <Switch
                    label={gettext('Require Git Review Gate When Accepting Design Versions')}
                    checked={gitReviewGate}
                    onChange={setGitReviewGate}
                  />
                  <Switch
                    label={gettext('Enable Bring-Your-Own-Key AI Drafting (Drafts Only — Never Accepts)')}
                    checked={aiDraftingEnabled}
                    onChange={setAiDraftingEnabled}
                  />
                  {aiDraftingEnabled && (
                    <TextField
                      label={gettext('AI Provider Model / Endpoint Reference')}
                      value={aiModelEndpoint}
                      placeholder="https://api.example.org/v1/models"
                      onChange={(e) => setAiModelEndpoint(e.target.value)}
                    />
                  )}
                </>
              )}

              {activeDomainKey === 'shortcuts' && (
                <>
                  <div style={{fontWeight: 700, fontSize: '0.9rem'}}>
                    {gettext('Keyboard Shortcuts & Engine Binary Paths')}
                  </div>
                  <ScratchFilterTable
                    title={gettext('Keyboard Shortcuts')}
                    columns={[
                      {key: 'action', label: gettext('Action')},
                      {key: 'scope', label: gettext('Scope'), chip: true},
                      {key: 'shortcut', label: gettext('Shortcut'), mono: true},
                    ]}
                    rows={SHORTCUT_REFERENCE_ROWS}
                    maxHeight={200}
                  />
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12}}>
                    <TextField
                      label={gettext('PostgreSQL Binary Path')}
                      value={pgBinPath}
                      placeholder="/usr/bin"
                      onChange={(e) => setPgBinPath(e.target.value)}
                    />
                    <TextField
                      label={gettext('Firebird Binary Path (isql / gbak)')}
                      value={fbBinPath}
                      placeholder="/opt/firebird/bin"
                      onChange={(e) => setFbBinPath(e.target.value)}
                    />
                  </div>
                </>
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
