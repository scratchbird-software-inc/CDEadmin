/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from 'react';
import PropTypes from 'prop-types';
import {Box} from '@mui/material';
import {Icon} from '../icons';
import {IconButton} from '../primitives/Button';
import {Drawer, Splitter, StatusBar, Toolbar} from '../layout/WorkbenchChrome';

export const WORKBENCH_LAYOUT_SCHEMA = 'cdeadmin.workbench-layout.v1';
export const WORKBENCH_INSPECT_EVENT = 'cdeadmin:workbench-inspect';
export const ACTIVITY_RAIL_HEIGHT = 48;
export const ACTIVITY_RAIL_WIDTH = ACTIVITY_RAIL_HEIGHT;
export const DEFAULT_WORKBENCH_LAYOUT = Object.freeze({
  schema: WORKBENCH_LAYOUT_SCHEMA,
  navigationWidth: 288,
  inspectorWidth: 340,
  inspectorHeight: 280,
  drawerHeight: 240,
  navigationVisible: false,
  inspectorVisible: false,
  drawerVisible: false,
  activeActivity: '',
});

const WorkbenchActivityContext = createContext(Object.freeze({
  activities: Object.freeze([]), activate: () => false,
}));

export function useWorkbenchActivities() {
  return useContext(WorkbenchActivityContext);
}

export function requestWorkbenchInspection(visible=true, target=window) {
  target.dispatchEvent(new target.CustomEvent(WORKBENCH_INSPECT_EVENT, {
    detail: {visible: Boolean(visible)},
  }));
}

function bounded(value, minimum, maximum, fallback) {
  return Number.isFinite(value) ? Math.max(minimum, Math.min(maximum, value)) : fallback;
}

export function normalizeWorkbenchLayout(value={}) {
  return Object.freeze({
    ...DEFAULT_WORKBENCH_LAYOUT,
    navigationWidth: bounded(value.navigationWidth, 220, 520, 288),
    inspectorWidth: bounded(value.inspectorWidth, 280, 520, 340),
    inspectorHeight: bounded(value.inspectorHeight, 120, 720, 280),
    drawerHeight: bounded(value.drawerHeight, 120, 720, 240),
    navigationVisible: value.navigationVisible === true,
    inspectorVisible: value.inspectorVisible === true,
    drawerVisible: value.drawerVisible === true,
    activeActivity: typeof value.activeActivity === 'string' ?
      value.activeActivity : '',
  });
}

export class WorkbenchLayoutStore {
  constructor(storage=typeof window === 'undefined' ? null : window.localStorage,
    key='cdeadmin.workbench-layout.v1') {
    this.storage = storage;
    this.key = key;
  }

  load(fallback=DEFAULT_WORKBENCH_LAYOUT) {
    try {
      const value = JSON.parse(this.storage?.getItem(this.key) || '{}');
      return value.schema && value.schema !== WORKBENCH_LAYOUT_SCHEMA ?
        normalizeWorkbenchLayout(fallback) :
        normalizeWorkbenchLayout(value.schema ? value : fallback);
    } catch {
      return normalizeWorkbenchLayout(fallback);
    }
  }

  save(value) {
    const normalized = normalizeWorkbenchLayout(value);
    this.storage?.setItem(this.key, JSON.stringify(normalized));
    return normalized;
  }

  reset() {
    this.storage?.removeItem(this.key);
    return DEFAULT_WORKBENCH_LAYOUT;
  }
}

function ActivityRail({activities, active, navigationVisible, onChange}) {
  return <Box component="nav" aria-label="Application activities"
    sx={{height: ACTIVITY_RAIL_HEIGHT, flex: `0 0 ${ACTIVITY_RAIL_HEIGHT}px`,
      display: 'flex', alignItems: 'center', px: 0.5, borderBottom: '1px solid',
      borderColor: 'divider', bgcolor: 'background.navigation',
      overflowX: 'auto', overflowY: 'hidden'}}>
    {activities.map((activity) => {
      const ownsNavigation = activity.navigationVisible !== false;
      const selected = activity.id === active &&
        (navigationVisible || !ownsNavigation);
      return <IconButton key={activity.id}
        data-cdeadmin-qa-key={`activity-${activity.id}`}
        data-selected={selected ? 'true' : 'false'}
        data-visual-emphasis={selected ? 'active' : 'inactive'}
        label={activity.label} aria-current={selected ? 'page' : undefined}
        disabled={activity.disabled === true}
        onClick={() => {
          if(activity.disabled) return;
          onChange(activity.id);
        }}
        sx={{width: 40, height: 40, mx: '2px', flex: '0 0 auto',
          filter: selected ? 'brightness(1)' :
            'brightness(var(--cde-inactive-brightness, 0.85))',
          borderBottom: selected ? '3px solid' : '3px solid transparent',
          borderColor: selected ? 'primary.main' : 'transparent',
          borderRadius: 0}}>
        <Icon iconKey={activity.iconKey || 'command.default'} decorative size="20px" />
      </IconButton>;
    })}
  </Box>;
}

ActivityRail.propTypes = {
  activities: PropTypes.array.isRequired,
  active: PropTypes.string.isRequired,
  navigationVisible: PropTypes.bool.isRequired,
  onChange: PropTypes.func.isRequired,
};

export function WorkbenchShell({activities, navigationViews, children,
  inspector, drawer, status, store: suppliedStore, initialLayout,
  onLayoutChange, navigationTitle, activeActivityOverride,
  startCollapsed=false,
  inspectorTitle='Inspector',
  drawerTitle='Problems, Output, Tasks and Logs'}) {
  const store = useMemo(
    () => suppliedStore ?? new WorkbenchLayoutStore(), [suppliedStore]
  );
  const [layout, setLayout] = useState(() => {
    const restored = store.load(initialLayout);
    return startCollapsed ? normalizeWorkbenchLayout({...restored,
      activeActivity: '', navigationVisible: false, inspectorVisible: false,
    }) : restored;
  });
  const update = useCallback((changes) => setLayout((current) =>
    store.save({...current, ...changes})
  ), [store]);
  useEffect(() => onLayoutChange?.(layout), [layout, onLayoutChange]);
  const knownActivities = activities.length ? activities : [{
    id: 'activity.data', label: 'Data Explorer', iconKey: 'object.database',
  }];
  const requestedActive = activeActivityOverride || layout.activeActivity;
  const active = knownActivities.some((item) => item.id === requestedActive) ?
    requestedActive : '';
  const activity = knownActivities.find((item) => item.id === active);
  const navigation = active ?
    navigationViews[active] ?? activity?.render?.() ?? null : null;
  const activateActivity = useCallback((activityId, {toggle=false,
    navigationVisible}={}) => {
    const requested = knownActivities.find((item) => item.id === activityId);
    if(!requested || requested.disabled) return false;
    const accepted = requested.onSelect?.();
    if(accepted === false) return false;
    const ownsNavigation = requested.navigationVisible !== false;
    const selected = requested.id === active && layout.navigationVisible &&
      ownsNavigation;
    update({activeActivity: requested.id,
      navigationVisible: navigationVisible === undefined ?
        ownsNavigation && !(toggle && selected) :
        ownsNavigation && navigationVisible});
    return true;
  }, [knownActivities, active, layout.navigationVisible, update]);
  useEffect(() => {
    const showActivity = (event) => {
      const detail = typeof event.detail === 'string' ?
        {activityId: event.detail} : event.detail ?? {};
      activateActivity(detail.activityId, {
        navigationVisible: detail.navigationVisible,
      });
    };
    const inspect = (event) => {
      const visible = event.detail?.visible !== false;
      if(visible && !active) return;
      update({inspectorVisible: visible});
    };
    window.addEventListener('cdeadmin:show-activity', showActivity);
    window.addEventListener(WORKBENCH_INSPECT_EVENT, inspect);
    return () => {
      window.removeEventListener('cdeadmin:show-activity', showActivity);
      window.removeEventListener(WORKBENCH_INSPECT_EVENT, inspect);
    };
  }, [activateActivity, update]);
  const activityContext = useMemo(() => Object.freeze({
    activities: Object.freeze([...knownActivities]),
    activate: (activityId) => activateActivity(activityId),
  }), [knownActivities, activateActivity]);
  const sidebarOpen = layout.navigationVisible || layout.inspectorVisible;
  const sidebarWidth = layout.inspectorVisible ?
    bounded(layout.navigationWidth, 280, 520, layout.inspectorWidth) :
    layout.navigationWidth;
  const stacked = layout.navigationVisible && layout.inspectorVisible;
  const resizeSidebar = (width) => update({
    navigationWidth: width, inspectorWidth: width,
  });

  return <WorkbenchActivityContext.Provider value={activityContext}>
    <Box data-cdeadmin-shell="zero-grey" sx={{height: '100%', minHeight: 0,
      display: 'flex', flexDirection: 'column', bgcolor: 'background.default',
      color: 'text.primary'}}>
      <ActivityRail activities={knownActivities} active={active}
        navigationVisible={layout.navigationVisible}
        onChange={(activityId) => activateActivity(activityId, {toggle: true})} />
      <Box sx={{flex: 1, minHeight: 0, display: 'flex', position: 'relative'}}>
        <Box sx={{width: sidebarOpen ? sidebarWidth : 0,
          flex: sidebarOpen ? `0 0 ${sidebarWidth}px` : '0 0 0px',
          minWidth: 0, minHeight: 0, overflow: 'hidden', display: 'flex',
          flexDirection: 'column', bgcolor: 'background.navigation'}}>
          <Box component="aside" aria-label={activity?.label || 'Explorer workspace'}
            aria-hidden={!layout.navigationVisible}
            data-cdeadmin-explorer-workspace="true"
            data-cdeadmin-qa-key="explorer-workspace"
            sx={{flex: layout.navigationVisible ? 1 : '0 0 0px',
              minHeight: layout.navigationVisible ? 120 : 0, minWidth: 0,
              overflow: 'hidden', display: 'flex', flexDirection: 'column',
              visibility: layout.navigationVisible ? 'visible' : 'hidden',
              pointerEvents: layout.navigationVisible ? 'auto' : 'none'}}>
            <Toolbar label="Navigation controls" trailing={<IconButton
              label="Hide navigation" onClick={() => update({navigationVisible: false})}>×</IconButton>}>
              <Box component="strong">{navigationTitle || activity?.label}</Box>
            </Toolbar>
            <Box sx={{flex: 1, minHeight: 0}}>{navigation}</Box>
          </Box>
          {stacked && <Splitter orientation="horizontal" invert
            value={layout.inspectorHeight} min={120} max={720}
            onChange={(inspectorHeight) => update({inspectorHeight})}
            label="Resize explorer and Inspector" />}
          {layout.inspectorVisible && <Box component="aside" aria-label="Inspector"
            sx={{flex: stacked ? `0 0 ${layout.inspectorHeight}px` : 1,
              height: stacked ? layout.inspectorHeight : undefined,
              minHeight: stacked ? 120 : 0, minWidth: 0, overflow: 'hidden',
              display: 'flex', flexDirection: 'column',
              bgcolor: 'background.elevated'}}>
            <Toolbar label="Inspector controls" trailing={<IconButton
              label="Hide Inspector" onClick={() => update({inspectorVisible: false})}>×</IconButton>}>
              <Box component="strong">{inspectorTitle}</Box>
            </Toolbar>
            <Box sx={{flex: 1, minHeight: 0, overflow: 'auto'}}>{inspector}</Box>
          </Box>}
        </Box>
        {sidebarOpen && <Splitter value={sidebarWidth}
          min={layout.inspectorVisible ? 280 : 220}
          max={layout.inspectorVisible ? 520 : 480}
          onChange={resizeSidebar}
          label={layout.inspectorVisible ? 'Resize Inspector' : 'Resize navigation'} />}
        <Box component="main" aria-label="Main workbench"
          sx={{flex: 1, minWidth: 0, minHeight: 0, display: 'flex',
            flexDirection: 'column', bgcolor: 'background.workspace'}}>
          <Box sx={{flex: 1, minHeight: 0, position: 'relative'}}>{children}</Box>
          <Drawer open={layout.drawerVisible} label={drawerTitle}
            height={layout.drawerHeight}
            onHeightChange={(drawerHeight) => update({drawerHeight})}>
            {drawer}
          </Drawer>
          <StatusBar>{status}</StatusBar>
        </Box>
        <IconButton label={layout.drawerVisible ? 'Hide bottom drawer' : 'Show bottom drawer'}
          onClick={() => update({drawerVisible: !layout.drawerVisible})}
          sx={{position: 'absolute', right: 8, bottom: 'var(--cde-status-height)',
            zIndex: 'popover'}}>▤</IconButton>
      </Box>
    </Box>
  </WorkbenchActivityContext.Provider>;
}

WorkbenchShell.propTypes = {
  activities: PropTypes.array,
  navigationViews: PropTypes.object,
  children: PropTypes.node,
  inspector: PropTypes.node,
  drawer: PropTypes.node,
  status: PropTypes.node,
  store: PropTypes.object,
  initialLayout: PropTypes.object,
  onLayoutChange: PropTypes.func,
  activeActivityOverride: PropTypes.string,
  startCollapsed: PropTypes.bool,
  navigationTitle: PropTypes.node,
  inspectorTitle: PropTypes.node,
  drawerTitle: PropTypes.string,
};

WorkbenchShell.defaultProps = {
  activities: [], navigationViews: {},
};
