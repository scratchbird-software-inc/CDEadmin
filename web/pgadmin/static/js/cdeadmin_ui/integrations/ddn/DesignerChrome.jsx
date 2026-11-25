/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button, IconButton} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {Dialog} from '../../overlays/Dialog';
import {StatusBadge} from '../../status/StatusBadge';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {Tab} from '../../navigation/TabsAndBreadcrumbs';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {Icon, inferActionIconKey} from '../../icons';
import {
  T_ACTION_STATUS,
  T_ACTION_TARGET_KIND,
  t_actions,
} from '../../actions/t_actions';
import RecordGrid from '../../objects/RecordGrid';
import UnifiedDataGrid from '../../data/UnifiedDataGrid';
import {ScratchDiffTable} from '../../data/beautiful';
import {
  useProjectInstanceScope,
  useProjectShell,
} from '../../shell/ProjectShell';

export const DESIGNER_TOOL_ACTION_EVENT = 'scratchrobin:designer-tool-action';
export const DESIGNER_PALETTE_SELECT_EVENT =
  'scratchrobin:designer-palette-select';
export const BI_OPEN_SQL_EVENT = 'scratchrobin:open-sql-from-bi';

const CANONICAL_DESIGNER_RBAC_ACTIONS = Object.freeze([
  {id: 'erd.designer.save', app: 'erd-designer', label: 'Save Checkpoint'},
  {id: 'erd.designer.accept', app: 'erd-designer', label: 'Accept'},
  {id: 'erd.designer.convert', app: 'erd-designer', label: 'Engine Conversion'},
  {
    id: 'erd.designer.alter_plan',
    app: 'erd-designer',
    label: 'Alter Plan & Migration',
  },
  {id: 'cube.designer.save', app: 'cube-designer', label: 'Save Draft'},
  {id: 'cube.designer.accept', app: 'cube-designer', label: 'Accept Cube'},
  {
    id: 'cube.designer.materialization_plan',
    app: 'cube-designer',
    label: 'Materialization DDL Plan',
  },
  {id: 'bi.designer.save', app: 'bi-designer', label: 'Save Draft'},
  {id: 'bi.designer.accept', app: 'bi-designer', label: 'Accept'},
  {
    id: 'bi.designer.sql_bridge',
    app: 'bi-designer',
    label: 'Compile Dialect SQL',
  },
  {
    id: 'bi.designer.outward_review',
    app: 'bi-designer',
    label: 'Subscriptions & Alerts',
  },
  {
    id: 'screen_mesh.designer.save',
    app: 'screen-mesh-designer',
    label: 'Save Draft',
  },
  {
    id: 'screen_mesh.designer.accept',
    app: 'screen-mesh-designer',
    label: 'Accept',
  },
  {
    id: 'screen_mesh.designer.redact',
    app: 'screen-mesh-designer',
    label: 'Redact Sensitive Regions',
  },
]);

export function ensureDesignerRbacActions(registry = t_actions) {
  if (
    !registry ||
    typeof registry.has !== 'function' ||
    typeof registry.register !== 'function'
  ) {
    return;
  }
  CANONICAL_DESIGNER_RBAC_ACTIONS.forEach((spec) => {
    if (!registry.has(spec.id)) {
      try {
        registry.register({
          id: spec.id,
          application: spec.app,
          focusScoped: false,
          defaultText: gettext(spec.label),
          defaultHint: gettext(spec.label),
          icon: inferActionIconKey({name: spec.id, label: spec.label}),
          permission: [spec.id],
          status: T_ACTION_STATUS.ENABLED,
          target: {
            kind: T_ACTION_TARGET_KIND.CLIENT,
            invoke: (args) => args?.invoke?.(),
          },
        });
      } catch {
        // Ignore duplicate or custom-registry registration mismatches.
      }
    }
  });
}

function resolveFromRegistry(actionId, registry) {
  if (!actionId || !registry) return null;
  if (
    typeof registry.has === 'function' &&
    typeof registry.resolve === 'function'
  ) {
    if (registry.has(actionId)) {
      try {
        return registry.resolve(actionId);
      } catch {
        return null;
      }
    }
    const canonical = CANONICAL_DESIGNER_RBAC_ACTIONS.find(
      (spec) => spec.id === actionId
    );
    if (!canonical) return null;
    const currentUser = registry.getCurrentUser?.() || null;
    let enabled = true;
    if (
      currentUser &&
      !currentUser.is_admin &&
      !currentUser.is_superuser
    ) {
      const perms = new Set(currentUser.permissions || []);
      enabled = perms.has(canonical.id);
    }
    return {
      id: canonical.id,
      text: gettext(canonical.label),
      hint: gettext(canonical.label),
      icon: inferActionIconKey({name: canonical.id, label: canonical.label}),
      permission: [canonical.id],
      enabled,
      visible: true,
      status: enabled ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
    };
  }
  if (typeof registry.get === 'function') {
    const cmd = registry.get(actionId);
    if (!cmd) return null;
    const enabled = cmd.enabled !== false && cmd.status !== 'disabled';
    const visible = cmd.visible !== false && cmd.status !== 'invisible';
    return {
      id: actionId,
      text: cmd.title || cmd.label || '',
      hint: cmd.description || cmd.hint || '',
      icon: cmd.icon || '',
      permission: cmd.permission || [],
      enabled,
      visible,
      status: !visible
        ? T_ACTION_STATUS.INVISIBLE
        : enabled
          ? T_ACTION_STATUS.ENABLED
          : T_ACTION_STATUS.DISABLED,
    };
  }
  return null;
}

export function isDesignerCommandEnabled(
  commandId,
  commands = t_actions,
  shellRegistry = null
) {
  const primary = resolveFromRegistry(commandId, commands);
  if (primary && (!primary.visible || !primary.enabled)) {
    return false;
  }
  const secondary =
    shellRegistry && shellRegistry !== commands
      ? resolveFromRegistry(commandId, shellRegistry)
      : null;
  if (secondary && (!secondary.visible || !secondary.enabled)) {
    return false;
  }
  return true;
}

export async function executeDesignerCommand({
  commandId,
  invoke,
  executeCommand = null,
  commands = t_actions,
  shellRegistry = null,
  enabled = true,
}) {
  if (typeof executeCommand === 'function') {
    return await executeCommand(commandId, {enabled, invoke});
  }
  ensureDesignerRbacActions(commands);
  if (shellRegistry && shellRegistry !== commands) {
    ensureDesignerRbacActions(shellRegistry);
  }
  if (
    !enabled ||
    !isDesignerCommandEnabled(commandId, commands, shellRegistry)
  ) {
    const err = new Error(gettext('Action is disabled: %s', commandId));
    err.code = 'action_disabled';
    throw err;
  }
  return await invoke?.();
}

function useRegistryRevision(registry) {
  const revRef = useRef(0);
  const subscribe = useCallback(
    (onStoreChange) => {
      if (!registry || typeof registry.subscribe !== 'function') {
        return () => {};
      }
      return registry.subscribe(() => {
        revRef.current += 1;
        onStoreChange();
      });
    },
    [registry]
  );
  const getSnapshot = useCallback(() => revRef.current, []);
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

function sanitizeActionSegment(raw, fallback = 'item') {
  const cleaned = String(raw || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  if (!cleaned) return fallback;
  return /^[a-z]/.test(cleaned) ? cleaned : `n_${cleaned}`;
}

function createSlotChannel(initialValues = {}) {
  let state = {...initialValues};
  const listeners = new Set();
  return {
    getState: () => state,
    publish(patch) {
      let changed = false;
      const next = {...state};
      Object.entries(patch || {}).forEach(([k, v]) => {
        if (next[k] !== v) {
          next[k] = v;
          changed = true;
        }
      });
      if (changed) {
        state = next;
        listeners.forEach((fn) => fn());
      }
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}

function ShellSlotOutlet({channel, slot}) {
  const snapshot = useSyncExternalStore(
    channel.subscribe,
    channel.getState,
    channel.getState
  );
  return snapshot?.[slot] ?? null;
}

ShellSlotOutlet.propTypes = {
  channel: PropTypes.object.isRequired,
  slot: PropTypes.string.isRequired,
};

function ShellLeftDrawerBridge({channel, getHostRender, instance}) {
  const snapshot = useSyncExternalStore(
    channel.subscribe,
    channel.getState,
    channel.getState
  );
  const [mode, setMode] = useState('elements');
  const hostRender = getHostRender?.();
  const elementNode = snapshot?.left ?? null;

  if (!hostRender) {
    return elementNode;
  }
  if (!elementNode) {
    return hostRender(instance);
  }

  return (
    <Box sx={{display: 'flex', flexDirection: 'column', minHeight: '100%'}}>
      <Box
        role="tablist"
        aria-label={gettext('Left drawer mode')}
        sx={{
          display: 'flex',
          gap: 0.25,
          px: 0.75,
          pt: 0.5,
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Tab
          label={gettext('Elements')}
          active={mode === 'elements'}
          onActivate={() => setMode('elements')}
        />
        <Tab
          label={gettext('Designs')}
          active={mode === 'designs'}
          onActivate={() => setMode('designs')}
        />
      </Box>
      <Box sx={{flex: 1, minHeight: 0}}>
        {mode === 'designs' ? hostRender(instance) : elementNode}
      </Box>
    </Box>
  );
}

ShellLeftDrawerBridge.propTypes = {
  channel: PropTypes.object.isRequired,
  getHostRender: PropTypes.func,
  instance: PropTypes.object,
};

/**
 * Formats canonical design save-point statuses for Area 3d Status Bar.
 */
export function formatSavePointStatusLabel(status) {
  const norm = String(status || 'draft')
    .trim()
    .toLowerCase();
  if (norm === 'accepted') return gettext('Accepted');
  if (norm === 'in_review' || norm === 'in-review') return gettext('In-review');
  if (norm === 'in_progress' || norm === 'in-progress') {
    return gettext('In-progress');
  }
  return gettext('Draft');
}

/**
 * Shared Area 3d Status Bar strip for DDN task designers inside ProjectShell.
 */
export function DesignerShellStatusBar({
  title = '',
  version = 1,
  status = 'draft',
  engine = '',
  suspectCount = 0,
  extra = null,
}) {
  const statusLabel = formatSavePointStatusLabel(status);
  const norm = String(status || 'draft').toLowerCase();
  const statusTone =
    norm === 'accepted'
      ? 'success'
      : norm === 'in_review' || norm === 'in-review'
        ? 'warning'
        : 'info';
  const hasSuspect = Number(suspectCount) > 0;

  return (
    <Box
      data-cdeadmin-qa-key="designer-shell-status"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 1,
        fontSize: '0.75rem',
      }}
    >
      {title && <strong>{title}</strong>}
      <Box component="span">v{version || 1}</Box>
      <StatusBadge status={statusTone} label={statusLabel} />
      {engine && (
        <Box component="span">
          {gettext('Engine')}: {engine}
        </Box>
      )}
      <StatusBadge
        status={hasSuspect ? 'warning' : 'success'}
        label={
          hasSuspect
            ? `${suspectCount} ${gettext('suspect')}`
            : gettext('valid')
        }
      />
      {extra}
    </Box>
  );
}

DesignerShellStatusBar.propTypes = {
  title: PropTypes.string,
  version: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  status: PropTypes.string,
  engine: PropTypes.string,
  suspectCount: PropTypes.number,
  extra: PropTypes.node,
};

/**
 * Shared Area 3a Model / Element Navigator tree for ERD, Cube, BI and Screen Mesh.
 */
export function DesignerElementNavigator({
  title,
  sections = [],
  emptyMessage = '',
  footer = null,
}) {
  return (
    <Box
      role="navigation"
      aria-label={title || gettext('Model Navigator')}
      data-cdeadmin-qa-key="designer-element-navigator"
      sx={{p: 1, display: 'flex', flexDirection: 'column', gap: 1}}
    >
      {title && (
        <Box sx={{fontSize: '0.8125rem', fontWeight: 700}}>{title}</Box>
      )}
      {sections.map((section) => {
        const items = section.items || [];
        return (
          <Box
            key={section.id}
            role="group"
            aria-label={section.label}
            sx={{display: 'flex', flexDirection: 'column', gap: 0.375}}
          >
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.6875rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.03em',
                color: 'text.secondary',
              }}
            >
              <span>{section.label}</span>
              <span>{items.length}</span>
            </Box>
            {items.length === 0 ? (
              <Box sx={{fontSize: '0.75rem', color: 'text.secondary', pl: 0.5}}>
                {section.emptyText ||
                  emptyMessage ||
                  gettext('No elements in this section.')}
              </Box>
            ) : (
              <Stack gap="compact">
                {items.map((item) => (
                  <Button
                    key={item.id}
                    size="small"
                    intent={item.active ? 'primary' : 'neutral'}
                    onClick={() => item.onSelect?.(item)}
                    data-cdeadmin-qa-key={`navigator-item.${item.id}`}
                  >
                    <Box
                      component="span"
                      sx={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        width: '100%',
                        gap: 0.5,
                        textAlign: 'left',
                      }}
                    >
                      <span>{item.label}</span>
                      {item.sublabel ? (
                        <Box
                          component="span"
                          sx={{fontSize: '0.6875rem', opacity: 0.8}}
                        >
                          {item.sublabel}
                        </Box>
                      ) : null}
                    </Box>
                  </Button>
                ))}
              </Stack>
            )}
          </Box>
        );
      })}
      {footer}
    </Box>
  );
}

DesignerElementNavigator.propTypes = {
  title: PropTypes.string,
  sections: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      emptyText: PropTypes.string,
      items: PropTypes.arrayOf(
        PropTypes.shape({
          id: PropTypes.string.isRequired,
          label: PropTypes.string.isRequired,
          sublabel: PropTypes.string,
          active: PropTypes.bool,
          onSelect: PropTypes.func,
        })
      ),
    })
  ),
  emptyMessage: PropTypes.string,
  footer: PropTypes.node,
};

/**
 * Cooperative 6-Region Shell Anatomy bridge (`A2`) for DDN task designers.
 * Publishes Area 3a (Model/Element Navigator), Area 3c (Properties Inspector),
 * Area 3d (Status Bar), and Area 3b1 (`quickActions`) onto the active
 * `ProjectShell` instance without render loops, restoring defaults on unmount.
 */
export function useDesignerShellRegions({
  title = '',
  statusNode = null,
  statusText = '',
  leftDrawerNode = null,
  rightDrawerNode = null,
  rightOpen = true,
  quickActions = null,
} = {}) {
  const shell = useProjectShell();
  const scope = useProjectInstanceScope();
  const instanceId = scope?.instanceId || null;
  const inShell = Boolean(shell && instanceId);
  const updateInstance = shell?.updateInstance || null;

  const channelRef = useRef(null);
  if (!channelRef.current) {
    channelRef.current = createSlotChannel({
      left: leftDrawerNode,
      right: rightDrawerNode,
      status: statusNode,
    });
  }

  const latestRef = useRef({
    quickActions,
    statusText,
    title,
  });
  latestRef.current = {
    quickActions,
    statusText,
    title,
  };

  useEffect(() => {
    channelRef.current.publish({
      left: leftDrawerNode,
      right: rightDrawerNode,
      status: statusNode,
    });
  }, [leftDrawerNode, rightDrawerNode, statusNode]);

  const baselineRef = useRef(null);
  const initialRightOpenRef = useRef(rightOpen);
  initialRightOpenRef.current = rightOpen;

  const buildQuickActionsProxy = useCallback(() => {
    const qa = latestRef.current.quickActions || {};
    return {
      onNew:
        typeof qa.onNew === 'function'
          ? (...args) => latestRef.current.quickActions?.onNew?.(...args)
          : undefined,
      onSave:
        typeof qa.onSave === 'function'
          ? (...args) => latestRef.current.quickActions?.onSave?.(...args)
          : undefined,
      onUndo:
        typeof qa.onUndo === 'function'
          ? (...args) => latestRef.current.quickActions?.onUndo?.(...args)
          : undefined,
      onRedo:
        typeof qa.onRedo === 'function'
          ? (...args) => latestRef.current.quickActions?.onRedo?.(...args)
          : undefined,
    };
  }, []);

  const shellRef = useRef(shell);
  shellRef.current = shell;

  useEffect(() => {
    if (!inShell || !updateInstance || !instanceId) return undefined;
    const channel = channelRef.current;
    baselineRef.current = null;

    updateInstance(instanceId, (prev) => {
      baselineRef.current = {
        supportsLeftDrawer: prev.supportsLeftDrawer,
        leftOpen: prev.leftOpen,
        renderLeftDrawer: prev.renderLeftDrawer,
        supportsRightDrawer: prev.supportsRightDrawer,
        rightOpen: prev.rightOpen,
        rightMode: prev.rightMode,
        rightViews: prev.rightViews,
        renderRightDrawer: prev.renderRightDrawer,
        renderStatus: prev.renderStatus,
        statusText: prev.statusText,
        quickActions: prev.quickActions,
      };
      return {
        supportsLeftDrawer: true,
        renderLeftDrawer: (inst) => (
          <ShellLeftDrawerBridge
            channel={channel}
            getHostRender={() => baselineRef.current?.renderLeftDrawer}
            instance={inst}
          />
        ),
        supportsRightDrawer: true,
        rightOpen: Boolean(initialRightOpenRef.current),
        rightMode: 'properties',
        rightViews: [{id: 'properties', label: gettext('Properties')}],
        renderRightDrawer: () => (
          <ShellSlotOutlet channel={channel} slot="right" />
        ),
        renderStatus: () => <ShellSlotOutlet channel={channel} slot="status" />,
        statusText: latestRef.current.statusText || prev.statusText || '',
        quickActions: buildQuickActionsProxy(),
      };
    });

    if (
      shellRef.current?.focusedId === instanceId &&
      !shellRef.current?.shellLeftDrawerOpen
    ) {
      updateInstance(instanceId, {supportsLeftDrawer: true, leftOpen: false});
      shellRef.current.toggleLeftDrawer?.();
    }

    return () => {
      const saved = baselineRef.current;
      baselineRef.current = null;
      if (saved) {
        updateInstance(instanceId, () => ({...saved}));
      }
    };
  }, [inShell, instanceId, updateInstance, buildQuickActionsProxy]);

  const quickSig = [
    typeof quickActions?.onNew === 'function' ? '1' : '0',
    typeof quickActions?.onSave === 'function' ? '1' : '0',
    typeof quickActions?.onUndo === 'function' ? '1' : '0',
    typeof quickActions?.onRedo === 'function' ? '1' : '0',
  ].join(':');
  const scalarSig = `${title || ''}||${statusText || ''}||${quickSig}`;
  const lastScalarSigRef = useRef('');

  useEffect(() => {
    if (!inShell || !updateInstance || !instanceId) return;
    if (lastScalarSigRef.current === scalarSig) return;
    lastScalarSigRef.current = scalarSig;
    updateInstance(instanceId, (prev) => ({
      ...(title ? {title} : {}),
      statusText: statusText || prev.statusText || '',
      quickActions: buildQuickActionsProxy(),
    }));
  }, [inShell, instanceId, updateInstance, scalarSig, title, statusText, buildQuickActionsProxy]);

  const openPropertiesDrawer = useCallback(() => {
    if (!inShell || !updateInstance || !instanceId) return;
    updateInstance(instanceId, {
      supportsRightDrawer: true,
      rightOpen: true,
      rightMode: 'properties',
    });
  }, [inShell, instanceId, updateInstance]);

  return {
    inShell,
    shell,
    instanceId,
    openPropertiesDrawer,
  };
}

/**
 * Subscribes active designer surface to `scratchrobin:designer-tool-action`
 * and `scratchrobin:designer-palette-select` workbench events.
 */
export function useDesignerWorkbenchEvents({
  appId,
  instanceId = null,
  inShell = false,
  shell = null,
  onToolAction = null,
  onPaletteSelect = null,
}) {
  const latestRef = useRef({
    appId,
    instanceId,
    inShell,
    focusedId: shell?.focusedId || null,
    onToolAction,
    onPaletteSelect,
  });
  latestRef.current = {
    appId,
    instanceId,
    inShell,
    focusedId: shell?.focusedId || null,
    onToolAction,
    onPaletteSelect,
  };

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const matchesActiveInstance = (detail) => {
      const cur = latestRef.current;
      if (detail?.appId && cur.appId && detail.appId !== cur.appId) {
        return false;
      }
      if (cur.inShell && cur.instanceId) {
        if (detail?.instanceId && detail.instanceId !== cur.instanceId) {
          return false;
        }
        if (
          !detail?.instanceId &&
          cur.focusedId &&
          cur.focusedId !== cur.instanceId
        ) {
          return false;
        }
      }
      return true;
    };

    const handleTool = (event) => {
      const detail = event?.detail || {};
      if (!detail.tool || !matchesActiveInstance(detail)) return;
      latestRef.current.onToolAction?.(detail.tool, detail);
    };

    const handlePalette = (event) => {
      const detail = event?.detail || {};
      if (!detail.kind || !detail.itemId || !matchesActiveInstance(detail)) {
        return;
      }
      latestRef.current.onPaletteSelect?.(detail.kind, detail.itemId, detail);
    };

    window.addEventListener(DESIGNER_TOOL_ACTION_EVENT, handleTool);
    window.addEventListener(DESIGNER_PALETTE_SELECT_EVENT, handlePalette);
    return () => {
      window.removeEventListener(DESIGNER_TOOL_ACTION_EVENT, handleTool);
      window.removeEventListener(DESIGNER_PALETTE_SELECT_EVENT, handlePalette);
    };
  }, []);
}

/**
 * Grouped tabbed-menu ribbon for ScratchRobin's four DDN task designers.
 * When mounted inside `ProjectShell` (`inShell === true`), promotes all
 * categories, groups, and button items onto Area `3b` (`shell.actionsRegistry`
 * + `ribbonTabs` + `renderToolbarExtras`) and renders `null` inside Area `3e`.
 * When rendered standalone (`!inShell`), renders the accessible DOM toolbar.
 */
export function DesignerTabbedMenu({
  label = gettext('Designer menu'),
  tabs = [],
  activeTab: controlledTab,
  onTabChange,
  leading = null,
  trailing = null,
  shellTrailing,
  onClose = null,
  commands = t_actions,
}) {
  const shell = useProjectShell();
  const scope = useProjectInstanceScope();
  const instanceId = scope?.instanceId || null;
  const inShell = Boolean(shell && instanceId);
  const updateInstance = shell?.updateInstance || null;
  const shellActions = shell?.actionsRegistry || null;

  useEffect(() => {
    ensureDesignerRbacActions(commands);
    if (shellActions && shellActions !== commands) {
      ensureDesignerRbacActions(shellActions);
    }
  }, [commands, shellActions]);

  const cmdRev = useRegistryRevision(commands);
  const shellRev = useRegistryRevision(shellActions);

  const [internalTab, setInternalTab] = useState(tabs[0]?.id || '');
  const currentId = controlledTab ?? internalTab;
  const active = tabs.find((tab) => tab.id === currentId) || tabs[0] || null;
  const selectTab = useCallback(
    (tabId) => {
      if (controlledTab === undefined) setInternalTab(tabId);
      onTabChange?.(tabId);
    },
    [controlledTab, onTabChange]
  );

  const handlersRef = useRef(new Map());
  const registeredActionIdsRef = useRef(new Set());
  const hostBaselineRef = useRef(null);
  const extrasChannelRef = useRef(null);
  if (!extrasChannelRef.current) {
    extrasChannelRef.current = createSlotChannel({extras: null});
  }

  const effectiveShellTrailing =
    shellTrailing !== undefined ? shellTrailing : trailing;

  const shellPromotion = useMemo(() => {
    if (!inShell || !instanceId) return null;
    const safeInst = sanitizeActionSegment(instanceId, 'inst');
    const nextHandlers = new Map();
    const actions = [];
    const customNodes = [];

    const buildTabGroups = (tab, isActiveTab) => {
      const tabGroups = [];
      const tabSlug = sanitizeActionSegment(tab?.id || 'main', 'tab');
      (tab?.groups || []).forEach((group, gIdx) => {
        const grpControls = [];
        (group.items || []).forEach((item, iIdx) => {
          if (typeof item.render === 'function') {
            if (isActiveTab) {
              customNodes.push({
                key: item.id || `custom_${tabSlug}_${gIdx}_${iIdx}`,
                render: item.render,
              });
            }
            return;
          }
          const rbacId =
            item.actionId ||
            (resolveFromRegistry(item.id, commands) ||
            resolveFromRegistry(item.id, shellActions)
              ? item.id
              : null);
          const resolvedCmd = rbacId
            ? resolveFromRegistry(rbacId, commands)
            : null;
          const resolvedShell =
            rbacId && shellActions && shellActions !== commands
              ? resolveFromRegistry(rbacId, shellActions)
              : null;
          if (
            (resolvedCmd && !resolvedCmd.visible) ||
            (resolvedShell && !resolvedShell.visible)
          ) {
            return;
          }
          const baseLabel = item.label || resolvedCmd?.text || item.id;
          const displayLabel =
            item.badge !== undefined && item.badge !== null && item.badge !== ''
              ? `${baseLabel} (${item.badge})`
              : baseLabel;
          const hint = resolvedCmd?.hint || item.hint || displayLabel;
          const iconKey =
            resolvedCmd?.icon ||
            item.icon ||
            item.iconKey ||
            inferActionIconKey({name: rbacId || item.id, label: baseLabel}) ||
            'command.default';
          const isDisabled =
            Boolean(item.disabled) ||
            (resolvedCmd ? !resolvedCmd.enabled : false) ||
            (resolvedShell ? !resolvedShell.enabled : false);
          const itemActionId = `designer.cmd.${safeInst}.${tabSlug}.${sanitizeActionSegment(
            item.id || item.label,
            `item_${gIdx}_${iIdx}`
          )}`;

          grpControls.push(itemActionId);
          nextHandlers.set(itemActionId, () => {
            if (item.onClick) {
              return item.onClick();
            }
            if (resolvedCmd && typeof commands?.execute === 'function') {
              return commands.execute(resolvedCmd.id);
            }
            return undefined;
          });
          actions.push({
            id: itemActionId,
            focusScoped: true,
            icon: iconKey,
            defaultText: displayLabel,
            defaultHint: hint,
            permission: item.permission || resolvedCmd?.permission || [],
            status: isDisabled
              ? T_ACTION_STATUS.DISABLED
              : T_ACTION_STATUS.ENABLED,
            ...(typeof item.active === 'boolean'
              ? {checked: Boolean(item.active)}
              : {}),
            target: {
              kind: T_ACTION_TARGET_KIND.CLIENT,
              invoke: () => handlersRef.current.get(itemActionId)?.(),
            },
          });
        });

        if (grpControls.length > 0) {
          tabGroups.push({
            id: sanitizeActionSegment(group.id || group.label, `grp_${gIdx}`),
            sectionId: group.sectionId || undefined,
            label: group.label || tab?.label || label,
            actions: grpControls,
            controls: grpControls,
          });
        }
      });
      return tabGroups;
    };

    const promotedTabs = (tabs.length > 0 ? tabs : [{id: 'main', label, groups: []}]).map(
      (tab, tIdx) => {
        const subId = `designer-subtab-${safeInst}-${sanitizeActionSegment(
          tab.id,
          `t${tIdx}`
        )}`;
        const isSelected = tab.id === active?.id;
        return {
          id: subId,
          rawTabId: tab.id,
          label: tab.label || label,
          isUnderTab: tabs.length > 1,
          selected: isSelected,
          onSelect: () => selectTab(tab.id),
          allowEmpty: true,
          groups: buildTabGroups(tab, isSelected),
        };
      }
    );

    const signature = [
      label,
      active?.id || '',
      actions
        .map(
          (a) =>
            `${a.id}:${a.defaultText}:${a.icon}:${a.status}:${
              typeof a.checked === 'boolean' ? a.checked : ''
            }`
        )
        .join('|'),
      promotedTabs
        .map(
          (pt) =>
            `${pt.id}:${pt.selected}:${pt.groups
              .map((g) => `${g.id}:${g.label}:${g.controls.join(',')}`)
              .join(';')}`
        )
        .join('||'),
    ].join('##');

    return {
      actions,
      promotedTabs,
      customNodes,
      nextHandlers,
      signature,
    };
  }, [
    inShell,
    instanceId,
    tabs,
    active,
    label,
    selectTab,
    commands,
    shellActions,
    cmdRev,
    shellRev,
  ]);

  if (shellPromotion) {
    handlersRef.current = shellPromotion.nextHandlers;
  }

  useEffect(() => {
    if (!inShell) return;
    const customNodes = shellPromotion?.customNodes || [];
    const hasExtras =
      customNodes.length > 0 || Boolean(effectiveShellTrailing);
    const extrasNode = hasExtras ? (
      <Box
        data-cdeadmin-qa-key="designer-3b-extras"
        sx={{
          display: 'inline-flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        {customNodes.map((entry) => (
          <Box
            key={entry.key}
            sx={{display: 'inline-flex', alignItems: 'center'}}
          >
            {entry.render()}
          </Box>
        ))}
        {effectiveShellTrailing}
      </Box>
    ) : null;
    extrasChannelRef.current.publish({extras: extrasNode});
  }, [inShell, shellPromotion, effectiveShellTrailing]);

  const latestPromotionRef = useRef(shellPromotion);
  latestPromotionRef.current = shellPromotion;
  const promotionSig = shellPromotion?.signature || '';
  const hasCustomExtras =
    (shellPromotion?.customNodes?.length || 0) > 0 ||
    Boolean(effectiveShellTrailing);

  useEffect(() => {
    if (!inShell || !updateInstance || !instanceId) return undefined;
    const promo = latestPromotionRef.current;
    if (!promo) return undefined;

    const prevRegistered = registeredActionIdsRef.current;
    const nextRegistered = new Set(promo.actions.map((a) => a.id));
    prevRegistered.forEach((oldId) => {
      if (!nextRegistered.has(oldId)) {
        shellActions?.unregister?.(oldId);
      }
    });
    registeredActionIdsRef.current = nextRegistered;

    const extrasChannel = extrasChannelRef.current;
    updateInstance(instanceId, (prev) => {
      if (!hostBaselineRef.current) {
        hostBaselineRef.current = {
          actions: [...(prev.actions || [])],
          ribbonTabs: [...(prev.ribbonTabs || [])],
          ribbonGroups: (prev.ribbonTabs || []).flatMap(
            (rt) => rt.groups || []
          ),
          renderToolbarExtras: prev.renderToolbarExtras || null,
        };
      }
      const hostActions = (hostBaselineRef.current.actions || []).filter(
        (a) => a?.id && !nextRegistered.has(a.id)
      );
      const hostGroups = (hostBaselineRef.current.ribbonGroups || []).filter(
        (g) => g.id !== 'inline-fallback-inspect'
      );
      const hostExtras = hostBaselineRef.current.renderToolbarExtras;
      const selectedSub =
        promo.promotedTabs.find((t) => t.selected) || promo.promotedTabs[0];

      return {
        supportsTabbedIconBar: true,
        useUnderTabs: promo.promotedTabs.length > 1,
        selectedUnderTabId: selectedSub?.id || null,
        actions: [...promo.actions, ...hostActions],
        ribbonTabs: promo.promotedTabs.map((pt) => ({
          ...pt,
          groups: [...pt.groups, ...hostGroups],
        })),
        renderToolbarExtras:
          hasCustomExtras || typeof hostExtras === 'function'
            ? (inst, sh) => {
              const baseNode =
                typeof hostExtras === 'function' ? hostExtras(inst, sh) : null;
              return (
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: 1,
                    width: '100%',
                  }}
                >
                  {baseNode}
                  <ShellSlotOutlet channel={extrasChannel} slot="extras" />
                </Box>
              );
            }
            : null,
      };
    });

    return undefined;
  }, [inShell, instanceId, updateInstance, shellActions, promotionSig, label, hasCustomExtras]);

  useEffect(() => {
    if (!inShell || !updateInstance || !instanceId) return undefined;
    return () => {
      registeredActionIdsRef.current.forEach((id) => {
        shellActions?.unregister?.(id);
      });
      registeredActionIdsRef.current = new Set();
      const saved = hostBaselineRef.current;
      hostBaselineRef.current = null;
      if (saved) {
        updateInstance(instanceId, () => ({
          actions: saved.actions,
          ribbonTabs: saved.ribbonTabs,
          renderToolbarExtras: saved.renderToolbarExtras,
        }));
      }
    };
  }, [inShell, instanceId, updateInstance, shellActions]);

  if (inShell) {
    return null;
  }

  return (
    <Box
      component="nav"
      aria-label={label}
      data-cdeadmin-qa-key="designer-tabbed-menu"
      sx={{
        flexShrink: 0,
        borderBottom: '1px solid',
        borderColor: 'divider',
        bgcolor: 'background.paper',
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 0.75,
          px: 1,
          minHeight: 'var(--cde-tab-height, 32px)',
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        {leading && (
          <Box sx={{display: 'flex', alignItems: 'center', gap: 0.75, mr: 0.5}}>
            {leading}
          </Box>
        )}
        <Box
          role="tablist"
          aria-label={`${label} ${gettext('categories')}`}
          sx={{display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 0.25}}
        >
          {tabs.map((tab) => (
            <Tab
              key={tab.id}
              label={tab.label}
              active={tab.id === active?.id}
              attention={Boolean(tab.attention)}
              dirty={Boolean(tab.dirty)}
              disabled={Boolean(tab.disabled)}
              onActivate={() => selectTab(tab.id)}
            />
          ))}
        </Box>
        {(trailing || onClose) && (
          <Box
            sx={{
              ml: 'auto',
              display: 'flex',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 0.75,
              py: 0.25,
            }}
          >
            {trailing}
            {onClose && (
              <IconButton
                label={gettext('Close %s', label)}
                data-cdeadmin-qa-key="designer-tabbed-menu-close"
                onClick={onClose}
              >
                ×
              </IconButton>
            )}
          </Box>
        )}
      </Box>
      {active && (
        <Box
          role="tabpanel"
          aria-label={`${active.label} ${gettext('commands')}`}
          data-cdeadmin-qa-key={`designer-menu-panel.${active.id}`}
          sx={{
            display: 'flex',
            alignItems: 'stretch',
            flexWrap: 'wrap',
            gap: 1,
            px: 1,
            py: 0.5,
            minHeight: 'calc(var(--cde-toolbar-height, 32px) + 6px)',
            bgcolor: 'background.default',
          }}
        >
          {(active.groups || []).map((group, idx) => (
            <Box
              key={group.id || group.label || idx}
              role="group"
              aria-label={group.label || active.label}
              sx={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                gap: 0.25,
                pr: 1.25,
                borderRight:
                  idx < active.groups.length - 1 ? '1px solid' : 'none',
                borderColor: 'divider',
              }}
            >
              {group.label && (
                <Box
                  component="span"
                  sx={{
                    fontSize: '0.6875rem',
                    fontWeight: 600,
                    letterSpacing: '0.03em',
                    textTransform: 'uppercase',
                    color: 'text.secondary',
                    lineHeight: 1.1,
                  }}
                >
                  {group.label}
                </Box>
              )}
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: 0.5,
                }}
              >
                {(group.items || []).map((item, itemIdx) => {
                  if (item.render) {
                    return (
                      <Box
                        key={item.id || itemIdx}
                        sx={{display: 'inline-flex', alignItems: 'center'}}
                      >
                        {item.render()}
                      </Box>
                    );
                  }
                  const rbacId =
                    item.actionId ||
                    (resolveFromRegistry(item.id, commands) ? item.id : null);
                  const resolvedAction = rbacId
                    ? resolveFromRegistry(rbacId, commands)
                    : null;
                  if (resolvedAction && !resolvedAction.visible) {
                    return null;
                  }
                  const buttonLabel =
                    item.label || resolvedAction?.text || item.id;
                  const buttonHint = resolvedAction?.hint || item.hint || '';
                  const iconKey =
                    resolvedAction?.icon ||
                    item.icon ||
                    item.iconKey ||
                    inferActionIconKey({
                      name: rbacId || item.id,
                      label: buttonLabel,
                    }) ||
                    'command.default';
                  const isDisabled =
                    Boolean(item.disabled) ||
                    (resolvedAction ? !resolvedAction.enabled : false);
                  return (
                    <Button
                      key={item.id || item.label || itemIdx}
                      size="small"
                      intent={
                        item.intent || (item.active ? 'primary' : 'neutral')
                      }
                      title={buttonHint || undefined}
                      disabled={isDisabled}
                      onClick={
                        item.onClick ||
                        (resolvedAction && typeof commands?.execute === 'function'
                          ? () => commands.execute(resolvedAction.id)
                          : undefined)
                      }
                      data-cdeadmin-qa-key={item.qaKey || item.id || undefined}
                    >
                      <Box
                        component="span"
                        sx={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 0.5,
                        }}
                      >
                        <Icon iconKey={iconKey} decorative size="0.95em" />
                        <span>
                          {buttonLabel}
                          {item.badge !== undefined &&
                          item.badge !== null &&
                          item.badge !== ''
                            ? ` (${item.badge})`
                            : ''}
                        </span>
                      </Box>
                    </Button>
                  );
                })}
              </Box>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}

DesignerTabbedMenu.propTypes = {
  label: PropTypes.string,
  tabs: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      icon: PropTypes.string,
      iconKey: PropTypes.string,
      attention: PropTypes.bool,
      dirty: PropTypes.bool,
      disabled: PropTypes.bool,
      groups: PropTypes.arrayOf(
        PropTypes.shape({
          id: PropTypes.string,
          label: PropTypes.string,
          items: PropTypes.array,
        })
      ),
    })
  ),
  activeTab: PropTypes.string,
  onTabChange: PropTypes.func,
  leading: PropTypes.node,
  trailing: PropTypes.node,
  shellTrailing: PropTypes.node,
  onClose: PropTypes.func,
  commands: PropTypes.object,
};

/**
 * Canonical ScratchRobin tabbed form body for designer dialogs
 * (matching ObjectEditor.jsx and docs/en_US/ui_unified_design.rst).
 */
export function DesignerModalTabs({
  tabs = [],
  activeTab: controlledTab,
  onTabChange,
  formKey = '',
  banner = null,
  minHeight = 280,
}) {
  const [internalTab, setInternalTab] = useState(tabs[0]?.id || '');
  const currentId = controlledTab ?? internalTab;
  const active = tabs.find((t) => t.id === currentId) || tabs[0] || null;
  const selectTab = (id) => {
    if (controlledTab === undefined) setInternalTab(id);
    onTabChange?.(id);
  };

  return (
    <Box sx={{display: 'flex', flexDirection: 'column', minHeight}}>
      {formKey && <FormReference formKey={formKey} />}
      {banner}
      {tabs.length > 1 && (
        <Box
          role="tablist"
          aria-label={gettext('Dialog sections')}
          sx={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 0.25,
            borderBottom: '1px solid',
            borderColor: 'divider',
            mb: 1.5,
          }}
        >
          {tabs.map((tab) => (
            <Tab
              key={tab.id}
              label={tab.label}
              active={tab.id === active?.id}
              attention={Boolean(tab.attention)}
              dirty={Boolean(tab.dirty)}
              disabled={Boolean(tab.disabled)}
              onActivate={() => selectTab(tab.id)}
            />
          ))}
        </Box>
      )}
      {active && (
        <Box
          role="tabpanel"
          aria-label={active.label}
          sx={{flex: 1, minHeight: 0, pt: tabs.length > 1 ? 0.5 : 0}}
        >
          {typeof active.render === 'function' ? active.render() : active.content}
        </Box>
      )}
    </Box>
  );
}

DesignerModalTabs.propTypes = {
  tabs: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      attention: PropTypes.bool,
      dirty: PropTypes.bool,
      disabled: PropTypes.bool,
      content: PropTypes.node,
      render: PropTypes.func,
    })
  ),
  activeTab: PropTypes.string,
  onTabChange: PropTypes.func,
  formKey: PropTypes.string,
  banner: PropTypes.node,
  minHeight: PropTypes.number,
};

/**
 * Responsive multi-column field layout obeying compact_forms.rst.
 */
export function FormGrid({columns = 2, children, sx = {}}) {
  const template =
    columns === 1
      ? '1fr'
      : `repeat(auto-fit, minmax(${columns >= 3 ? '180px' : '230px'}, 1fr))`;
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: template,
        gap: 1.5,
        alignItems: 'start',
        ...sx,
      }}
    >
      {children}
    </Box>
  );
}

FormGrid.propTypes = {
  columns: PropTypes.number,
  children: PropTypes.node,
  sx: PropTypes.object,
};

/**
 * Typed tabular record editor replacing raw JSON textareas and CSV strings
 * (ui_unified_design.rst Principle 3: json is not a user-facing control).
 */
export function TypedRowsEditor({
  label,
  columns = [],
  rows = [],
  onChange,
  addLabel = gettext('Add row'),
  emptyText = gettext('No entries configured.'),
  disabled = false,
  reorderable = false,
}) {
  const descriptorField = useMemo(
    () => ({
      field_id: String(label || 'rows')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '') || 'rows',
      label,
      control: 'grid',
      reorderable,
      columns: columns.map((col) => ({
        field_id: col.key,
        label: col.label,
        control: col.type || 'text',
        options: col.options,
        placeholder: col.placeholder,
        minWidth: col.minWidth,
        default:
          col.default !== undefined
            ? col.default
            : col.type === 'boolean'
              ? false
              : col.type === 'number'
                ? 0
                : col.type === 'select'
                  ? (col.options?.[0]?.value ?? '')
                  : '',
      })),
    }),
    [label, columns, reorderable]
  );

  return (
    <RecordGrid
      field={descriptorField}
      rows={rows}
      onChange={(next) => onChange?.(next)}
      disabled={disabled}
      addLabel={`+ ${addLabel}`}
      emptyText={emptyText}
      maxInlineColumns={Math.max(6, columns.length)}
      cellLabelFormat={(colLabel, rowNum) => `${colLabel} row ${rowNum}`}
    />
  );
}

TypedRowsEditor.propTypes = {
  label: PropTypes.string.isRequired,
  columns: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      type: PropTypes.oneOf(['text', 'number', 'select', 'boolean']),
      options: PropTypes.array,
      placeholder: PropTypes.string,
      minWidth: PropTypes.number,
      default: PropTypes.any,
      checkboxLabel: PropTypes.string,
    })
  ),
  rows: PropTypes.array,
  onChange: PropTypes.func,
  addLabel: PropTypes.string,
  emptyText: PropTypes.string,
  disabled: PropTypes.bool,
  reorderable: PropTypes.bool,
};

/**
 * Typed key/value dictionary editor backed by TypedRowsEditor.
 */
export function KeyValuePairsEditor({
  label,
  value = {},
  onChange,
  keyLabel = gettext('Key'),
  valueLabel = gettext('Value'),
  keyPlaceholder = '',
  valuePlaceholder = '',
  disabled = false,
}) {
  const externalRows = useMemo(
    () =>
      Object.entries(value || {}).map(([k, v]) => ({
        key: k,
        value: typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v ?? ''),
      })),
    [value]
  );
  const [draftRows, setDraftRows] = useState(externalRows);
  useEffect(() => {
    setDraftRows((prev) => {
      const pendingBlank = prev.filter((r) => !String(r.key || '').trim());
      return pendingBlank.length ? [...externalRows, ...pendingBlank] : externalRows;
    });
  }, [externalRows]);
  const handleChange = (nextRows) => {
    setDraftRows(nextRows);
    const out = {};
    for (const r of nextRows) {
      const k = String(r.key || '').trim();
      if (!k) continue;
      const raw = String(r.value ?? '');
      if (raw === 'true') out[k] = true;
      else if (raw === 'false') out[k] = false;
      else if (raw !== '' && !Number.isNaN(Number(raw)) && /^-?\d+(\.\d+)?$/.test(raw)) {
        out[k] = Number(raw);
      } else {
        out[k] = raw;
      }
    }
    onChange?.(out);
  };
  return (
    <TypedRowsEditor
      label={label}
      rows={draftRows}
      disabled={disabled}
      addLabel={gettext('Add %s', keyLabel.toLowerCase())}
      columns={[
        {key: 'key', label: keyLabel, placeholder: keyPlaceholder, minWidth: 140},
        {key: 'value', label: valueLabel, placeholder: valuePlaceholder, minWidth: 180},
      ]}
      onChange={handleChange}
    />
  );
}

KeyValuePairsEditor.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.object,
  onChange: PropTypes.func,
  keyLabel: PropTypes.string,
  valueLabel: PropTypes.string,
  keyPlaceholder: PropTypes.string,
  valuePlaceholder: PropTypes.string,
  disabled: PropTypes.bool,
};

/**
 * Shared Checkpoint History, Visual Diff & Restore/Branch Dialog
 * across ERD, Cube, BI and Screen Mesh designers.
 */
export function DesignCheckpointHistoryDrawer({
  open,
  onClose,
  client,
  projectId,
  designId,
  currentVersion,
  activeVersion,
  onOpenVersion,
  onRestored,
}) {
  const [versions, setVersions] = useState([]);
  const [baseVer, setBaseVer] = useState('');
  const [targetVer, setTargetVer] = useState('');
  const [diffResult, setDiffResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('history');

  useEffect(() => {
    if (!open || !client || !projectId || !designId) return;
    let active = true;
    setBusy(true);
    setError('');
    Promise.resolve(client.listVersions?.(projectId, designId))
      .then((list) => {
        if (!active) return;
        const items = Array.isArray(list) ? list : list?.versions || [];
        setVersions(items);
        if (items.length >= 2) {
          setBaseVer(String(items[items.length - 2].version));
          setTargetVer(String(items[items.length - 1].version));
        } else if (items.length === 1) {
          setBaseVer(String(items[0].version));
          setTargetVer(String(items[0].version));
        }
      })
      .catch((err) => active && setError(err?.message || String(err)))
      .finally(() => active && setBusy(false));
    return () => {
      active = false;
    };
  }, [open, client, projectId, designId]);

  const runCompare = async () => {
    if (!baseVer || !targetVer) return;
    setBusy(true);
    setError('');
    try {
      if (typeof client.diffDesignVersions === 'function') {
        const res = await client.diffDesignVersions(projectId, designId, {
          baseVersion: Number(baseVer),
          targetVersion: Number(targetVer),
        });
        setDiffResult(res);
      } else {
        const [a, b] = await Promise.all([
          client.openSession(projectId, designId, {version: Number(baseVer)}),
          client.openSession(projectId, designId, {version: Number(targetVer)}),
        ]);
        const aLines = String(a?.design?.version?.ddn_text || '').split('\n');
        const bLines = String(b?.design?.version?.ddn_text || '').split('\n');
        const unified = [
          `--- v${baseVer}`,
          `+++ v${targetVer}`,
          ...aLines.filter((l) => !bLines.includes(l)).map((l) => `- ${l}`),
          ...bLines.filter((l) => !aLines.includes(l)).map((l) => `+ ${l}`),
        ].join('\n');
        setDiffResult({
          base_version: Number(baseVer),
          target_version: Number(targetVer),
          unified_diff: unified || '-- Identical DDN text.',
          added_elements: [],
          removed_elements: [],
          modified_elements: [],
        });
      }
      setTab('diff');
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const restoreAsDraft = async (ver) => {
    setBusy(true);
    setError('');
    try {
      const snap = await client.openSession(projectId, designId, {
        version: Number(ver),
      });
      const head = versions.reduce(
        (m, item) => Math.max(m, Number(item.version) || 0),
        Number(currentVersion) || 1
      );
      const saved = await client.saveVersion(projectId, designId, {
        expected_head_version: head,
        ddn_text: snap?.design?.version?.ddn_text || '',
        status: 'draft',
        note: `Branched draft from checkpoint v${ver}`,
      });
      const newVer = saved?.design?.version?.version ?? head + 1;
      onRestored?.(newVer);
      onClose?.();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const versionOptions = versions.map((v) => ({
    value: String(v.version),
    label: `v${v.version} (${v.status})${v.note ? ` — ${v.note}` : ''}`,
  }));

  return (
    <Dialog
      open={Boolean(open)}
      onClose={onClose}
      title={gettext('Checkpoints, Directed Save Points & Version Diff')}
      size="large"
      busy={busy}
      actions={<Button onClick={onClose}>{gettext('Close')}</Button>}
    >
      <DesignerModalTabs
        formKey="design-checkpoints-diff"
        activeTab={tab}
        onTabChange={setTab}
        banner={error ? <Banner status="error">{error}</Banner> : null}
        tabs={[
          {
            id: 'history',
            label: `${gettext('Checkpoints')} (${versions.length})`,
            render: () =>
              versions.length === 0 ? (
                <EmptyState message={gettext('No checkpoints recorded yet.')} />
              ) : (
                <UnifiedDataGrid
                  gridRole="table"
                  ariaLabel={gettext('Design checkpoints')}
                  searchable
                  exportable
                  minHeight={180}
                  maxHeight={380}
                  rows={versions.slice().reverse()}
                  rowKeyGetter={(item) => item.version}
                  columns={[
                    {
                      name: 'version',
                      label: gettext('Version'),
                      width: 150,
                      render: (_val, item) => (
                        <span>
                          <strong>v{item.version}</strong>
                          {Number(item.version) === Number(activeVersion)
                            ? ` (${gettext('Active')})`
                            : ''}
                          {Number(item.version) === Number(currentVersion)
                            ? ` · ${gettext('Loaded')}`
                            : ''}
                        </span>
                      ),
                    },
                    {
                      name: 'status',
                      label: gettext('Status'),
                      width: 120,
                      render: (_val, item) => (
                        <StatusBadge
                          status={
                            item.status === 'accepted'
                              ? 'success'
                              : item.status === 'in_review'
                                ? 'warning'
                                : 'info'
                          }
                          label={item.status}
                        />
                      ),
                    },
                    {
                      name: 'parent_version',
                      label: gettext('Parent'),
                      width: 90,
                      accessorFn: (item) =>
                        (item.parent_version ?? item.base_version)
                          ? `v${item.parent_version ?? item.base_version}`
                          : '—',
                    },
                    {
                      name: 'note',
                      label: gettext('Summary / Note'),
                      width: 220,
                      accessorFn: (item) => item.note || '—',
                    },
                    {
                      name: 'created_at',
                      label: gettext('Created'),
                      width: 170,
                      accessorFn: (item) => item.created_at || item.saved_at || '—',
                    },
                    {
                      name: 'actions',
                      label: gettext('Actions'),
                      width: 210,
                      render: (_val, item) => (
                        <Stack direction="row" gap="compact">
                          <Button
                            size="small"
                            onClick={() => {
                              onOpenVersion?.(Number(item.version));
                              onClose?.();
                            }}
                          >
                            {gettext('Inspect')}
                          </Button>
                          <Button
                            size="small"
                            onClick={() => restoreAsDraft(item.version)}
                          >
                            {gettext('Branch Draft')}
                          </Button>
                        </Stack>
                      ),
                    },
                  ]}
                />
              ),
          },
          {
            id: 'diff',
            label: gettext('Compare Checkpoints (DDN Diff)'),
            render: () => (
              <Stack gap="standard">
                <FormGrid columns={3}>
                  <Select
                    label={gettext('Base Checkpoint')}
                    value={baseVer}
                    options={versionOptions}
                    onChange={setBaseVer}
                  />
                  <Select
                    label={gettext('Target Checkpoint')}
                    value={targetVer}
                    options={versionOptions}
                    onChange={setTargetVer}
                  />
                  <Box sx={{pt: 2.25}}>
                    <Button intent="primary" disabled={busy || !baseVer || !targetVer} onClick={runCompare}>
                      {gettext('Compare Versions')}
                    </Button>
                  </Box>
                </FormGrid>
                {diffResult && (
                  <Stack gap="compact">
                    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap'}}>
                      <StatusBadge
                        status="success"
                        label={`+${(diffResult.added_elements || []).length} ${gettext('added')}`}
                      />
                      <StatusBadge
                        status="warning"
                        label={`~${(diffResult.modified_elements || []).length} ${gettext('modified')}`}
                      />
                      <StatusBadge
                        status="error"
                        label={`-${(diffResult.removed_elements || []).length} ${gettext('removed')}`}
                      />
                    </Box>
                    {((diffResult.added_elements || []).length > 0 ||
                      (diffResult.modified_elements || []).length > 0 ||
                      (diffResult.removed_elements || []).length > 0) && (
                      <ScratchDiffTable
                        caption={gettext('Checkpoint element differences')}
                        showIncludeToggle={false}
                        searchable
                        filterable
                        items={[
                          ...(diffResult.added_elements || []).map((el, i) => ({
                            id: `add:${el.id || el.name || i}`,
                            name: el.name || el.id || String(el),
                            kind: el.kind || 'element',
                            delta: 'add',
                            summary: el.summary || '',
                          })),
                          ...(diffResult.modified_elements || []).map((el, i) => ({
                            id: `mod:${el.id || el.name || i}`,
                            name: el.name || el.id || String(el),
                            kind: el.kind || 'element',
                            delta: 'modify',
                            before: el.before,
                            after: el.after,
                            summary: el.summary || '',
                          })),
                          ...(diffResult.removed_elements || []).map((el, i) => ({
                            id: `rem:${el.id || el.name || i}`,
                            name: el.name || el.id || String(el),
                            kind: el.kind || 'element',
                            delta: 'drop',
                            summary: el.summary || '',
                          })),
                        ]}
                        style={{maxHeight: 200}}
                      />
                    )}
                    <Box sx={{minHeight: 220}}>
                      <CodeEditor
                        label={gettext('Checkpoint DDN Diff')}
                        value={diffResult.unified_diff || '-- No DDN differences.'}
                        readonly
                        language="sql"
                      />
                    </Box>
                  </Stack>
                )}
              </Stack>
            ),
          },
        ]}
      />
    </Dialog>
  );
}

DesignCheckpointHistoryDrawer.propTypes = {
  open: PropTypes.bool,
  onClose: PropTypes.func,
  client: PropTypes.object,
  projectId: PropTypes.string,
  designId: PropTypes.string,
  currentVersion: PropTypes.number,
  activeVersion: PropTypes.number,
  onOpenVersion: PropTypes.func,
  onRestored: PropTypes.func,
};

/**
 * Shared "Where Used in Designs / Impact Explorer" dialog across all 4 designers.
 */
export function WhereUsedDialog({
  open,
  onClose,
  client,
  projectId,
  initialTargetRef = '',
  designId = '',
}) {
  const [targetRef, setTargetRef] = useState(initialTargetRef);
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setTargetRef(initialTargetRef || '');
  }, [initialTargetRef]);

  const runSearch = async (queryRef = targetRef) => {
    if (!client || !projectId) return;
    setBusy(true);
    setError('');
    try {
      if (typeof client.queryWhereUsed === 'function') {
        const data = await client.queryWhereUsed(projectId, {
          targetRef: queryRef,
          designId,
          includeSuspect: true,
        });
        setResults(Array.isArray(data) ? data : data?.usages || []);
      } else if (typeof client.queryScreenMeshUsage === 'function') {
        const data = await client.queryScreenMeshUsage(projectId, {
          targetRef: queryRef,
          includeSuspect: true,
        });
        setResults(Array.isArray(data) ? data : data?.usages || []);
      }
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (open && projectId) {
      runSearch(initialTargetRef || '');
    }
  }, [open, projectId, initialTargetRef]);

  return (
    <Dialog
      open={Boolean(open)}
      onClose={onClose}
      title={gettext('Where Used Across Designs (ERD · Cubes · BI · Screen Meshes)')}
      size="large"
      busy={busy}
      actions={<Button onClick={onClose}>{gettext('Close')}</Button>}
    >
      <Stack gap="standard">
        <FormReference formKey="design-where-used" />
        {error && <Banner status="error">{error}</Banner>}
        <FormGrid columns={2}>
          <TextField
            label={gettext('Filter by Catalog Table / Column / Cube / Design Ref')}
            placeholder="e.g. main.work_orders or cube:operations"
            value={targetRef}
            onChange={(e) => setTargetRef(e.target.value)}
          />
          <Box sx={{pt: 2.25}}>
            <Button intent="primary" onClick={() => runSearch(targetRef)}>
              {gettext('Search Cross-Design References')}
            </Button>
          </Box>
        </FormGrid>
        {results.length === 0 ? (
          <EmptyState message={gettext('No cross-design references matched this filter.')} />
        ) : (
          <UnifiedDataGrid
            gridRole="table"
            ariaLabel={gettext('Where used results')}
            searchable
            exportable
            minHeight={160}
            maxHeight={340}
            rows={results}
            rowKeyGetter={(item, idx) => item.binding_id || idx}
            columns={[
              {
                name: 'design_kind',
                label: gettext('Design Kind'),
                width: 130,
                accessorFn: (item) => item.design_kind || item.kind || 'design',
              },
              {
                name: 'design_title',
                label: gettext('Design Title'),
                width: 190,
                accessorFn: (item) => item.design_title || item.title || item.design_id,
              },
              {
                name: 'element',
                label: gettext('Element'),
                width: 170,
                accessorFn: (item) => item.element_label || item.element_id || '—',
              },
              {
                name: 'target_ref',
                label: gettext('Target Reference'),
                width: 220,
                mono: true,
                accessorFn: (item) => item.target_ref || '—',
              },
              {
                name: 'validity',
                label: gettext('Validity'),
                width: 120,
                accessorFn: (item) => item.validity || 'referenced',
                render: (_val, item) => (
                  <StatusBadge
                    status={
                      item.validity === 'suspect'
                        ? 'warning'
                        : item.validity === 'valid'
                          ? 'success'
                          : 'info'
                    }
                    label={item.validity || 'referenced'}
                  />
                ),
              },
            ]}
          />
        )}
      </Stack>
    </Dialog>
  );
}

WhereUsedDialog.propTypes = {
  open: PropTypes.bool,
  onClose: PropTypes.func,
  client: PropTypes.object,
  projectId: PropTypes.string,
  initialTargetRef: PropTypes.string,
  designId: PropTypes.string,
};
