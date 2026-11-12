/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react';
import PropTypes from 'prop-types';
import usePreferences from '../../../../preferences/static/js/store';
import {Icon} from '../icons';
import {useTActions} from '../actions/t_actions';
import {translateShell} from './shellMenuI18n';
import {useProjectVerticalDockStyles} from './ProjectVerticalDockStyles';

export const DEFAULT_DOCK_BASE_SIZE = 36;
export const DEFAULT_DOCK_MAGNIFIED_SIZE = 58;
export const DEFAULT_DOCK_DISTANCE = 135;
export const DEFAULT_DOCK_RIGHT_LIFT = 7;

/**
 * Pure cosine-bell proximity curve (`0..1`) for vertical dock magnification.
 * Returns `1` when `pointerY === centerY`, smoothly decaying to `0` at `distance`.
 */
export function computeDockProximity(pointerY, centerY, distance = DEFAULT_DOCK_DISTANCE) {
  if (!Number.isFinite(pointerY) || !Number.isFinite(centerY) || distance <= 0) {
    return 0;
  }
  const delta = Math.abs(pointerY - centerY);
  if (delta >= distance) return 0;
  return 0.5 * (1 + Math.cos((Math.PI * delta) / distance));
}

function resolveDockTone(storeTheme) {
  if (typeof document !== 'undefined') {
    const attr = document.documentElement?.getAttribute('data-cde-theme');
    if (attr === 'dark' || attr === 'light') return attr;
  }
  const candidate =
    storeTheme || (typeof window !== 'undefined' ? window.theme : 'light');
  if (candidate === 'system' && typeof window !== 'undefined') {
    return window.matchMedia?.('(prefers-color-scheme: dark)')?.matches
      ? 'dark'
      : 'light';
  }
  return candidate === 'dark' ? 'dark' : 'light';
}

/**
 * Compositor-driven proximity coordinator for all items in the vertical dock.
 * Snapshots resting Y centers on pointer entry so vertical breathing never
 * creates cursor-feedback oscillation, and updates target geometry directly on
 * DOM refs while CSS spring transitions (`cubic-bezier(0.22, 1.2, 0.36, 1)`)
 * interpolate smoothly on the GPU compositor thread (immune to Wayland/background
 * rAF throttling).
 */
function createVerticalDockController({
  baseSize = DEFAULT_DOCK_BASE_SIZE,
  magnifiedSize = DEFAULT_DOCK_MAGNIFIED_SIZE,
  distance = DEFAULT_DOCK_DISTANCE,
  rightLift = DEFAULT_DOCK_RIGHT_LIFT,
  zoomScale = 1,
} = {}) {
  const entries = new Map();
  let pointerY = null;
  let centersCaptured = false;
  let suppressedId = null;

  const applyVisualState = (entry, progress) => {
    const clamped = Math.max(0, Math.min(1, progress));
    const size = baseSize + (magnifiedSize - baseSize) * clamped;
    const iconPx = (19 + 11 * clamped) * zoomScale;
    const liftPx = rightLift * clamped;
    // Middle items gently part neighbors vertically; top/bottom stay edge-pinned
    const slotHeight =
      entry.anchor === 'middle'
        ? baseSize + (magnifiedSize - baseSize) * 0.42 * clamped
        : Math.max(baseSize, size * 0.9);

    if (entry.slotEl) {
      entry.slotEl.style.height = `${slotHeight.toFixed(2)}px`;
    }
    if (entry.btnEl) {
      entry.btnEl.style.width = `${size.toFixed(2)}px`;
      entry.btnEl.style.height = `${size.toFixed(2)}px`;
      entry.btnEl.style.transform = `translate3d(${liftPx.toFixed(2)}px, 0, 0)`;
    }
    if (entry.iconWrapEl) {
      entry.iconWrapEl.style.width = `${iconPx.toFixed(2)}px`;
      entry.iconWrapEl.style.height = `${iconPx.toFixed(2)}px`;
      entry.iconWrapEl.style.fontSize = `${iconPx.toFixed(2)}px`;
    }
    if (entry.tooltipEl) {
      const tooltipLeft = 8 + size + liftPx + 10;
      entry.tooltipEl.style.left = `${tooltipLeft.toFixed(1)}px`;
    }
  };

  const captureRestingCenters = () => {
    let index = 0;
    entries.forEach((entry) => {
      if (entry.slotEl) {
        const rect = entry.slotEl.getBoundingClientRect();
        if (rect && rect.height > 0) {
          entry.centerY = rect.top + rect.height / 2;
        } else {
          const attrY = Number(entry.slotEl.getAttribute('data-dock-center-y'));
          entry.centerY = Number.isFinite(attrY) && attrY > 0
            ? attrY
            : 26 + index * (baseSize + 6);
        }
      }
      index += 1;
    });
    centersCaptured = true;
  };

  const computeTargetProgress = (entry) => {
    const hoverP =
      pointerY === null
        ? 0
        : computeDockProximity(pointerY, entry.centerY, distance);
    const focusP = entry.focused ? 1 : 0;
    return Math.max(hoverP, focusP);
  };

  const syncTargets = () => {
    entries.forEach((entry) => {
      const target = computeTargetProgress(entry);
      entry.target = target;
      const targetSize = Math.round(
        baseSize + (magnifiedSize - baseSize) * target
      );
      if (entry.btnEl) {
        entry.btnEl.setAttribute('data-magnified', target > 0.08 ? 'true' : 'false');
        entry.btnEl.setAttribute('data-target-size', String(targetSize));
      }
      applyVisualState(entry, target);
    });
  };

  return {
    baseSize,
    magnifiedSize,
    register(id, entryData) {
      const entry = {
        ...entryData,
        centerY: 0,
        target: 0,
        focused: false,
      };
      entries.set(id, entry);
      centersCaptured = false;
      applyVisualState(entry, 0);
      if (entry.btnEl) {
        entry.btnEl.setAttribute('data-magnified', 'false');
        entry.btnEl.setAttribute('data-target-size', String(baseSize));
      }
      return () => {
        entries.delete(id);
        centersCaptured = false;
      };
    },
    invalidateCenters() {
      centersCaptured = false;
    },
    setPointerY(nextY) {
      if (nextY === null) {
        pointerY = null;
        suppressedId = null;
        centersCaptured = false;
        syncTargets();
        return;
      }
      if (!centersCaptured) {
        captureRestingCenters();
      }
      if (suppressedId) {
        const suppressedEntry = entries.get(suppressedId);
        if (
          suppressedEntry &&
          Math.abs(nextY - suppressedEntry.centerY) <= baseSize * 0.6
        ) {
          return;
        }
        suppressedId = null;
      }
      pointerY = nextY;
      syncTargets();
    },
    setItemFocused(id, isFocused) {
      const entry = entries.get(id);
      if (!entry) return;
      if (isFocused && !centersCaptured) {
        captureRestingCenters();
      }
      entry.focused = isFocused;
      syncTargets();
    },
    resetAll(activatedId = null) {
      pointerY = null;
      suppressedId = activatedId;
      centersCaptured = false;
      entries.forEach((entry) => {
        entry.focused = false;
      });
      syncTargets();
    },
    dispose() {
      entries.clear();
    },
  };
}

const VerticalDockContext = createContext(null);

function VerticalDockItem({
  id,
  iconKey,
  label,
  tooltipText,
  anchor = 'middle',
  disabled = false,
  active = false,
  hideTooltip = false,
  onClick,
  buttonProps = {},
  children = null,
}) {
  const controller = useContext(VerticalDockContext);
  const tooltipId = useId();
  const slotRef = useRef(null);
  const btnRef = useRef(null);
  const iconWrapRef = useRef(null);
  const tooltipRef = useRef(null);
  const pointerPressedRef = useRef(false);
  const justActivatedRef = useRef(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!controller) return undefined;
    return controller.register(id, {
      anchor,
      slotEl: slotRef.current,
      btnEl: btnRef.current,
      iconWrapEl: iconWrapRef.current,
      tooltipEl: tooltipRef.current,
    });
  }, [anchor, controller, id]);

  const showTooltip = !hideTooltip && (hovered || focused);

  return (
    <div
      ref={slotRef}
      className="sr-vdock-slot"
      data-anchor={anchor}
      data-dock-item-slot={id}
      onMouseEnter={() => {
        justActivatedRef.current = false;
        setHovered(true);
      }}
      onMouseMove={() => {
        if (!hovered && !justActivatedRef.current) setHovered(true);
      }}
      onMouseLeave={() => {
        justActivatedRef.current = false;
        setHovered(false);
      }}
      onPointerEnter={() => {
        justActivatedRef.current = false;
        setHovered(true);
      }}
      onPointerMove={() => {
        if (!hovered && !justActivatedRef.current) setHovered(true);
      }}
      onPointerLeave={() => {
        justActivatedRef.current = false;
        setHovered(false);
      }}
    >
      <button
        ref={btnRef}
        type="button"
        className="sr-vdock-btn"
        aria-label={label}
        aria-describedby={showTooltip ? tooltipId : undefined}
        disabled={disabled}
        data-disabled={disabled ? 'true' : undefined}
        data-active={active ? 'true' : undefined}
        onMouseDown={() => {
          pointerPressedRef.current = true;
        }}
        onPointerDown={() => {
          pointerPressedRef.current = true;
        }}
        onFocus={() => {
          if (pointerPressedRef.current) {
            return;
          }
          setFocused(true);
          controller?.setItemFocused(id, true);
        }}
        onBlur={() => {
          pointerPressedRef.current = false;
          setFocused(false);
          controller?.setItemFocused(id, false);
        }}
        onClick={(e) => {
          pointerPressedRef.current = false;
          justActivatedRef.current = true;
          setHovered(false);
          setFocused(false);
          controller?.resetAll(id);
          e.currentTarget?.blur?.();
          if (disabled) return;
          onClick?.(e);
        }}
        {...buttonProps}
      >
        <span ref={iconWrapRef} className="sr-vdock-icon-wrap" aria-hidden="true">
          <Icon iconKey={iconKey} decorative size="100%" />
        </span>
      </button>

      <div
        ref={tooltipRef}
        id={tooltipId}
        role="tooltip"
        className="sr-vdock-tooltip"
        data-visible={showTooltip ? 'true' : 'false'}
        aria-hidden={!showTooltip}
      >
        {tooltipText || label}
      </div>

      {children}
    </div>
  );
}

VerticalDockItem.propTypes = {
  id: PropTypes.string.isRequired,
  iconKey: PropTypes.string.isRequired,
  label: PropTypes.string.isRequired,
  tooltipText: PropTypes.string,
  anchor: PropTypes.oneOf(['top', 'middle', 'bottom']),
  disabled: PropTypes.bool,
  active: PropTypes.bool,
  hideTooltip: PropTypes.bool,
  onClick: PropTypes.func,
  buttonProps: PropTypes.object,
  children: PropTypes.node,
};

/**
 * Area 2 — Clean-room Vertical Rightward-Expanding Dock (`ProjectVerticalDock`):
 *   1. Top item (isolated): Left Side Drawer Toggle — expands rightward on hover
 *   2. Middle toolbar: `data-navigator` first + authorized user applications —
 *      proximity wave swells hovered icon & neighbors rightward
 *   3. Bottom-aligned item (isolated): Settings Gear — bottom-aligned, expands
 *      rightward & upward on hover, opens Application/Global Settings popup
 */
export function ProjectVerticalDock({
  shell,
  baseItemSize = DEFAULT_DOCK_BASE_SIZE,
  magnification = DEFAULT_DOCK_MAGNIFIED_SIZE,
  distance = DEFAULT_DOCK_DISTANCE,
}) {
  useProjectVerticalDockStyles();
  const railRef = useRef(null);
  const gearWrapRef = useRef(null);
  const [gearPopupOpen, setGearPopupOpen] = useState(false);

  const prefStore = usePreferences();
  const storeTheme = prefStore?.getPreferencesForModule?.('misc')?.theme;
  const [domTone, setDomTone] = useState(() => resolveDockTone(storeTheme));

  useEffect(() => {
    setDomTone(resolveDockTone(storeTheme));
  }, [storeTheme, prefStore?.version]);

  useEffect(() => {
    if (typeof MutationObserver === 'undefined' || typeof document === 'undefined') {
      return undefined;
    }
    const obs = new MutationObserver(() => {
      setDomTone(resolveDockTone(storeTheme));
    });
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-cde-theme'],
    });
    return () => obs.disconnect();
  }, [storeTheme]);

  useTActions(shell?.actionsRegistry);

  const zoomScale =
    typeof shell?.resolveAreaZoom === 'function' ? shell.resolveAreaZoom('area_2') : 1;
  const effectiveBaseSize = Math.round(baseItemSize * zoomScale);
  const effectiveMagnification = Math.round(magnification * zoomScale);
  const effectiveDistance = Math.round(distance * zoomScale);
  const railWidthPx = Math.round(52 * zoomScale);

  const controller = useMemo(
    () =>
      createVerticalDockController({
        baseSize: effectiveBaseSize,
        magnifiedSize: effectiveMagnification,
        distance: effectiveDistance,
        zoomScale,
      }),
    [effectiveBaseSize, effectiveDistance, effectiveMagnification, zoomScale]
  );

  useEffect(() => () => controller.dispose(), [controller]);

  useEffect(() => {
    const el = railRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const obs = new ResizeObserver(() => controller.invalidateCenters());
    obs.observe(el);
    return () => obs.disconnect();
  }, [controller]);

  useEffect(() => {
    if (!gearPopupOpen) return undefined;
    const closeOnOutside = (e) => {
      if (gearWrapRef.current && !gearWrapRef.current.contains(e.target)) {
        setGearPopupOpen(false);
      }
    };
    const closeOnEsc = (e) => {
      if (e.key === 'Escape') setGearPopupOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutside);
    document.addEventListener('keydown', closeOnEsc);
    return () => {
      document.removeEventListener('mousedown', closeOnOutside);
      document.removeEventListener('keydown', closeOnEsc);
    };
  }, [gearPopupOpen]);

  const handlePointerMove = useCallback(
    (event) => {
      const y = event?.clientY ?? event?.nativeEvent?.clientY;
      if (Number.isFinite(y)) {
        controller.setPointerY(y);
      }
    },
    [controller]
  );

  const handlePointerLeave = useCallback(() => {
    controller.setPointerY(null);
  }, [controller]);

  if (!shell) return null;

  const locale = shell.locale || 'en';
  const leftToggleAction = shell.actionsRegistry.has('shell.left_drawer.toggle')
    ? shell.actionsRegistry.resolve('shell.left_drawer.toggle')
    : {enabled: false, checked: false, hint: ''};

  const appSettingsEnabled = Boolean(shell.activeSettingsAppId);

  const navAria = translateShell(
    locale,
    'shell.side.nav_aria',
    'Side Menu Application Launcher'
  );
  const launchAria = translateShell(
    locale,
    'shell.side.launch_aria',
    'Launch Applications'
  );
  const leftDrawerLabel = translateShell(
    locale,
    'shell.side.left_drawer_toggle',
    'Toggle Left Side Drawer'
  );
  const leftDrawerTooltip = leftToggleAction.enabled
    ? leftDrawerLabel
    : translateShell(
      locale,
      'shell.side.left_drawer_unavailable',
      'Left Side Drawer (Unavailable)'
    );
  const settingsLabel = translateShell(locale, 'shell.side.settings', 'Settings');
  const settingsOptionsLabel = translateShell(
    locale,
    'shell.side.settings_options',
    'Settings Options'
  );
  const appSettingsLabel = translateShell(
    locale,
    'shell.side.app_settings',
    'Application Settings'
  );
  const globalSettingsLabel = translateShell(
    locale,
    'shell.side.global_settings',
    'Global Settings'
  );

  return (
    <VerticalDockContext.Provider value={controller}>
      <nav
        ref={railRef}
        className="sr-vdock-rail"
        style={{
          '--sr-vdock-zoom': String(zoomScale),
          '--sr-vdock-rail-width': `${railWidthPx}px`,
        }}
        aria-label={navAria}
        data-tone={domTone}
        data-locale={locale}
        data-cdeadmin-qa-key="project-side-menu"
        onMouseMove={handlePointerMove}
        onMouseLeave={handlePointerLeave}
        onPointerMove={handlePointerMove}
        onPointerLeave={handlePointerLeave}
      >
        {/* 1. Top Isolated Item: Left Side Drawer Toggle */}
        <div className="sr-vdock-zone sr-vdock-zone--top">
          <VerticalDockItem
            id="left-drawer-toggle"
            anchor="top"
            iconKey="action.menu"
            label={leftDrawerLabel}
            tooltipText={leftDrawerTooltip}
            disabled={!leftToggleAction.enabled}
            onClick={() => shell.toggleLeftDrawer()}
            buttonProps={{
              'aria-pressed': Boolean(
                shell.shellLeftDrawerOpen && leftToggleAction.enabled
              ),
              'data-cdeadmin-qa-key': 'side-menu-left-drawer-toggle',
              'data-drawer-open': shell.shellLeftDrawerOpen ? 'true' : 'false',
            }}
          />
        </div>

        <div className="sr-vdock-divider" role="separator" aria-hidden="true" />

        {/* 2 & 3. Middle Stateless Application Launcher Stack (`data-navigator` first) */}
        <div
          className="sr-vdock-zone sr-vdock-zone--apps"
          role="toolbar"
          aria-orientation="vertical"
          aria-label={launchAria}
        >
          {shell.authorizedApps.map((app) => {
            const localizedAppTitle = translateShell(
              locale,
              `app.${app.id}.label`,
              app.label
            );
            const openLabel = translateShell(
              locale,
              'shell.side.open_app',
              'Open %s',
              localizedAppTitle
            );

            return (
              <VerticalDockItem
                key={app.id}
                id={`app-${app.id}`}
                anchor="middle"
                iconKey={app.iconKey || 'command.default'}
                label={openLabel}
                tooltipText={localizedAppTitle}
                onClick={() => shell.openApplication(app.id)}
                buttonProps={{
                  'data-cdeadmin-qa-key': `side-menu-app-${app.id}`,
                }}
              />
            );
          })}
        </div>

        {/* 4. Bottom-Aligned Isolated Item: Settings Gear */}
        <div ref={gearWrapRef} className="sr-vdock-zone sr-vdock-zone--bottom">
          <div className="sr-vdock-divider" role="separator" aria-hidden="true" />
          <VerticalDockItem
            id="settings-gear"
            anchor="bottom"
            iconKey="action.settings"
            label={settingsLabel}
            tooltipText={settingsLabel}
            active={gearPopupOpen}
            hideTooltip={gearPopupOpen}
            onClick={() => setGearPopupOpen((prev) => !prev)}
            buttonProps={{
              'aria-haspopup': 'menu',
              'aria-expanded': gearPopupOpen,
              'data-cdeadmin-qa-key': 'side-menu-settings-gear',
            }}
          >
            {gearPopupOpen && (
              <div
                role="menu"
                aria-label={settingsOptionsLabel}
                data-cdeadmin-qa-key="side-menu-settings-popup"
                className="sr-vdock-settings-popup"
              >
                <button
                  type="button"
                  role="menuitem"
                  className="sr-vdock-settings-item"
                  disabled={!appSettingsEnabled}
                  data-cdeadmin-qa-key="gear-application-settings"
                  onClick={() => {
                    if (!appSettingsEnabled) return;
                    setGearPopupOpen(false);
                    shell.openSettingsDialog('application', shell.activeSettingsAppId);
                  }}
                >
                  <Icon iconKey="action.settings" decorative size="1.05em" />
                  <span>{appSettingsLabel}</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="sr-vdock-settings-item"
                  data-cdeadmin-qa-key="gear-global-settings"
                  onClick={() => {
                    setGearPopupOpen(false);
                    shell.openSettingsDialog('global', null);
                  }}
                >
                  <Icon iconKey="action.preferences" decorative size="1.05em" />
                  <span>{globalSettingsLabel}</span>
                </button>
              </div>
            )}
          </VerticalDockItem>
        </div>
      </nav>
    </VerticalDockContext.Provider>
  );
}

ProjectVerticalDock.propTypes = {
  shell: PropTypes.object,
  baseItemSize: PropTypes.number,
  magnification: PropTypes.number,
  distance: PropTypes.number,
};
