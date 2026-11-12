/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useId, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {NavigationMenu} from '@base-ui/react/navigation-menu';
import usePreferences from '../../../../preferences/static/js/store';
import {Icon, inferActionIconKey} from '../icons';
import {useTActions} from '../actions/t_actions';
import {PROJECT_TOP_MENU_INDICES} from '../commands/MenuStructure';
import {
  translateMenuItemHint,
  translateMenuItemLabel,
  translateMenuTriggerLabel,
  translateShell,
} from './shellMenuI18n';
import {useProjectNavigationMenuStyles} from './ProjectNavigationMenuStyles';
import {
  COLOR_SCHEME_CHANGED_EVENT,
  applySchemeAndTypographyToDOM,
  listToggleableColorSchemes,
  readStoredSchemeAndFontState,
  resolveColorSchemeById,
} from './colorSchemesAndFonts';
import {
  ACTION_PLACEMENTS_CHANGED_EVENT,
  applyGlobalMenuPlacements,
} from './actionPlacementEngine';

function resolveThemeTone(selected) {
  if (selected === 'system' && typeof window !== 'undefined') {
    return window.matchMedia?.('(prefers-color-scheme: dark)')?.matches
      ? 'dark'
      : 'light';
  }
  return selected === 'dark' ? 'dark' : 'light';
}

/**
 * Base UI 10x10 chevron icon that rotates 180deg when `[data-popup-open]` is active.
 */
function ChevronDownSvg(props) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true" {...props}>
      <path
        d="M1.5 3.5L5 7L8.5 3.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Base UI NavigationMenu popup arrow (`https://base-ui.com/react/components/navigation-menu`).
 */
function ArrowSvg(props) {
  return (
    <svg width="20" height="10" viewBox="0 0 20 10" fill="none" aria-hidden="true" {...props}>
      <path
        d="M9.66437 2.60207L4.80758 6.97318C4.07308 7.63423 3.11989 8 2.13172 8H0V10H20V8H18.5349C17.5468 8 16.5936 7.63423 15.8591 6.97318L11.0023 2.60207C10.622 2.2598 10.0447 2.25979 9.66437 2.60207Z"
        className="sr-nav-arrow-fill"
      />
      <path
        d="M8.99542 1.85876C9.75604 1.17425 10.9106 1.17422 11.6713 1.85878L16.5281 6.22989C17.0789 6.72568 17.7938 7.00001 18.5349 7.00001L15.89 7L11.0023 2.60207C10.622 2.2598 10.0447 2.2598 9.66436 2.60207L4.77734 7L2.13171 7.00001C2.87284 7.00001 3.58774 6.72568 4.13861 6.22989L8.99542 1.85876Z"
        className="sr-nav-arrow-stroke"
      />
    </svg>
  );
}

function GlobeSvg() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6.25" stroke="currentColor" strokeWidth="1.3" />
      <ellipse cx="8" cy="8" rx="2.75" ry="6.25" stroke="currentColor" strokeWidth="1.2" />
      <path d="M2 8H14" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function ToneIconSvg({isDark}) {
  if (isDark) {
    return (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d="M13.2 9.8A5.5 5.5 0 0 1 6.2 2.8a5.5 5.5 0 1 0 7 7Z"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="3.1" stroke="currentColor" strokeWidth="1.4" />
      <path
        d="M8 1.5V3M8 13V14.5M1.5 8H3M13 8H14.5M3.4 3.4L4.5 4.5M11.5 11.5L12.6 12.6M12.6 3.4L11.5 4.5M4.5 11.5L3.4 12.6"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

ToneIconSvg.propTypes = {
  isDark: PropTypes.bool.isRequired,
};

function NavigationMenuCardItem({item, locale, actionsRegistry, compact = false}) {
  const uid = useId();
  const [subExpanded, setSubExpanded] = useState(false);

  const resolvedAction =
    item.actionId && actionsRegistry?.has(item.actionId)
      ? actionsRegistry.resolve(item.actionId)
      : null;
  if (resolvedAction && !resolvedAction.visible) return null;

  const disabled = Boolean(
    item.isDisabled || (resolvedAction && !resolvedAction.enabled)
  );
  const label = translateMenuItemLabel(locale, item, resolvedAction);
  const hint = translateMenuItemHint(locale, item, resolvedAction);
  const iconKey =
    resolvedAction?.icon ||
    item.iconKey ||
    inferActionIconKey({name: item.id, label}) ||
    'command.default';
  const checked =
    typeof item.checked === 'boolean' ? item.checked : resolvedAction?.checked;
  const hasCheck = typeof checked === 'boolean';
  const hasSub = Array.isArray(item.items) && item.items.length > 0;
  const descId = hint ? `${uid}-desc` : undefined;
  const role = hasCheck ? 'menuitemcheckbox' : 'menuitem';

  return (
    <li className="sr-nav-list-entry">
      <NavigationMenu.Link
        closeOnClick={!disabled && !hasSub}
        active={Boolean(checked)}
        className={`sr-nav-card-link${compact && !hint ? ' sr-nav-card-link--compact' : ''}`}
        data-checked={checked ? 'true' : undefined}
        data-menu-item-index={item.index}
        data-command-id={item.actionId || item.commandId || item.id}
        render={
          <button
            type="button"
            role={role}
            aria-label={label}
            aria-describedby={descId}
            aria-checked={hasCheck ? checked : undefined}
            aria-haspopup={hasSub ? 'menu' : undefined}
            aria-expanded={hasSub ? subExpanded : undefined}
            disabled={disabled}
          />
        }
        onClick={(event) => {
          if (disabled) {
            event.preventDefault();
            return;
          }
          if (hasSub) {
            event.preventDefault();
            setSubExpanded((prev) => !prev);
            return;
          }
          if (item.callback) {
            item.callback();
          } else if (item.actionId && actionsRegistry?.has(item.actionId)) {
            void actionsRegistry.execute(item.actionId);
          }
        }}
      >
        <span className="sr-nav-card-icon" aria-hidden="true">
          <Icon iconKey={iconKey} decorative size="1.05em" />
        </span>
        <span className="sr-nav-card-body">
          <span className="sr-nav-card-title-row">
            <span className="sr-nav-card-title">{label}</span>
          </span>
          {hint && (
            <span id={descId} className="sr-nav-card-desc">
              {hint}
            </span>
          )}
        </span>
        {(hasCheck || item.shortcut || hasSub) && (
          <span className="sr-nav-card-meta" aria-hidden="true">
            {hasCheck && (
              <span className="sr-nav-check-badge">{checked ? '✓' : ''}</span>
            )}
            {item.shortcut && <kbd className="sr-nav-shortcut">{item.shortcut}</kbd>}
            {hasSub && <span>{subExpanded ? '▾' : '▸'}</span>}
          </span>
        )}
      </NavigationMenu.Link>

      {hasSub && subExpanded && (
        <ul className="sr-nav-section-list sr-nav-submenu-children" role="menu">
          {item.items.map((subItem) =>
            subItem.type === 'separator' ? (
              <li key={subItem.id} role="separator" className="sr-nav-separator" />
            ) : (
              <NavigationMenuCardItem
                key={`${subItem.owner}_${subItem.id}_${subItem.index}`}
                item={subItem}
                locale={locale}
                actionsRegistry={actionsRegistry}
                compact
              />
            )
          )}
        </ul>
      )}
    </li>
  );
}

NavigationMenuCardItem.propTypes = {
  item: PropTypes.object.isRequired,
  locale: PropTypes.string.isRequired,
  actionsRegistry: PropTypes.object,
  compact: PropTypes.bool,
};

function NavigationMenuPanelContent({menu, locale, actionsRegistry}) {
  const executableCount = useMemo(
    () => (menu.items || []).filter((it) => it.type !== 'separator').length,
    [menu.items]
  );
  const useTwoColumnGrid = menu.name === 'applications' && executableCount >= 5;
  const listClassName = useTwoColumnGrid ? 'sr-nav-section-grid' : 'sr-nav-section-list';

  return (
    <ul className={listClassName} role="menu" aria-label={translateMenuTriggerLabel(locale, menu)}>
      {(menu.items || []).map((item) => {
        if (item.type === 'separator') {
          return <li key={item.id} role="separator" className="sr-nav-separator" />;
        }
        return (
          <NavigationMenuCardItem
            key={`${item.owner}_${item.id}_${item.index}`}
            item={item}
            locale={locale}
            actionsRegistry={actionsRegistry}
          />
        );
      })}
    </ul>
  );
}

NavigationMenuPanelContent.propTypes = {
  menu: PropTypes.object.isRequired,
  locale: PropTypes.string.isRequired,
  actionsRegistry: PropTypes.object,
};

/**
 * Area 1 — ScratchRobin Main Navigation Menu built on Base UI `NavigationMenu`
 * (`https://base-ui.com/react/components/navigation-menu`) with full i18n
 * support and unsigned-integer positional ordering:
 *   0  = System Icon (Session / Lock Screen / Logout)
 *   1..59, 61..69, 71..79, 81+ = Dynamic focused-application menus
 *   60 = Applications
 *   70 = Window
 *   80 = Help
 *   Right-aligned = Language NavigationMenu + Light/Dark Theme Switcher
 */
export function ProjectNavigationMenuBar({shell}) {
  useProjectNavigationMenuStyles();
  const barRef = useRef(null);
  const [activeMenu, setActiveMenu] = useState(null);
  const [langMenu, setLangMenu] = useState(null);
  const [, bumpMenu] = useState(0);

  const prefStore = usePreferences();
  const storeTheme = prefStore?.getPreferencesForModule?.('misc')?.theme;
  const [schemeState, setSchemeState] = useState(() => readStoredSchemeAndFontState());
  const [fallbackTone, setFallbackTone] = useState(() =>
    resolveThemeTone(typeof window !== 'undefined' ? window.theme : 'light')
  );
  const [optimisticTone, setOptimisticTone] = useState(null);

  useEffect(() => {
    setOptimisticTone(null);
  }, [storeTheme, prefStore?.version]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onSchemeChanged = (event) => {
      const nextState = event?.detail?.state || readStoredSchemeAndFontState();
      setSchemeState(nextState);
      if (event?.detail?.scheme?.baseTone) {
        setOptimisticTone(event.detail.scheme.baseTone);
        setFallbackTone(event.detail.scheme.baseTone);
      }
    };
    const onPlacementsChanged = () => bumpMenu((n) => n + 1);
    window.addEventListener(COLOR_SCHEME_CHANGED_EVENT, onSchemeChanged);
    window.addEventListener(ACTION_PLACEMENTS_CHANGED_EVENT, onPlacementsChanged);
    return () => {
      window.removeEventListener(COLOR_SCHEME_CHANGED_EVENT, onSchemeChanged);
      window.removeEventListener(ACTION_PLACEMENTS_CHANGED_EVENT, onPlacementsChanged);
    };
  }, []);

  // Hydrate colour scheme & typography when shell server settings load
  useEffect(() => {
    const g = shell?.settings?.global;
    if (!g) return;
    if (g.active_color_scheme || g.custom_color_schemes?.length || g.typography?.ui_font_family) {
      const {state: appliedState} = applySchemeAndTypographyToDOM(
        {
          activeSchemeId: g.active_color_scheme || undefined,
          customSchemes: Array.isArray(g.custom_color_schemes) ? g.custom_color_schemes : undefined,
          enabledSchemeIds: Array.isArray(g.enabled_scheme_ids) ? g.enabled_scheme_ids : undefined,
          typography: g.typography || undefined,
        },
        {persistLocal: true, syncPreferences: false}
      );
      setSchemeState(appliedState);
    }
  }, [
    shell?.settings?.global?.active_color_scheme,
    shell?.settings?.global?.custom_color_schemes,
    shell?.settings?.global?.enabled_scheme_ids,
    shell?.settings?.global?.typography,
  ]);

  const activeScheme = useMemo(
    () => resolveColorSchemeById(schemeState.activeSchemeId, schemeState.customSchemes),
    [schemeState.activeSchemeId, schemeState.customSchemes]
  );
  const toggleableSchemes = useMemo(
    () => listToggleableColorSchemes(schemeState),
    [schemeState]
  );

  const tone = useMemo(
    () =>
      optimisticTone ||
      (schemeState.activeSchemeId && schemeState.activeSchemeId !== 'light'
        ? activeScheme.baseTone
        : storeTheme
          ? resolveThemeTone(storeTheme)
          : fallbackTone),
    [optimisticTone, schemeState.activeSchemeId, activeScheme.baseTone, storeTheme, prefStore?.version, fallbackTone]
  );
  const isDark = tone === 'dark';

  useTActions(shell?.actionsRegistry);

  useEffect(() => {
    if (!shell?.menuRegistry) return undefined;
    return shell.menuRegistry.subscribe(() => bumpMenu((n) => n + 1));
  }, [shell?.menuRegistry]);

  useEffect(() => {
    const el = barRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const update = () =>
      document.documentElement.style.setProperty(
        '--cde-actual-menu-height',
        `${el.getBoundingClientRect().height}px`
      );
    update();
    const obs = new ResizeObserver(update);
    obs.observe(el);
    return () => {
      obs.disconnect();
      document.documentElement.style.removeProperty('--cde-actual-menu-height');
    };
  }, []);

  const handleSelectScheme = useCallback(
    async (schemeId) => {
      const {scheme} = applySchemeAndTypographyToDOM(
        {activeSchemeId: schemeId},
        {persistLocal: true, syncPreferences: true}
      );
      setOptimisticTone(scheme.baseTone);
      setFallbackTone(scheme.baseTone);
      if (typeof shell?.saveSettings === 'function') {
        try {
          await shell.saveSettings({global: {active_color_scheme: scheme.id}});
        } catch {
          // Offline / test harness safe.
        }
      }
    },
    [shell]
  );

  const handleToggleTone = useCallback(async () => {
    const nextSchemeId =
      activeScheme.id === 'light' || activeScheme.id === 'dark'
        ? isDark
          ? 'light'
          : 'dark'
        : (() => {
            const idx = toggleableSchemes.findIndex((s) => s.id === activeScheme.id);
            const next = toggleableSchemes[(idx + 1) % toggleableSchemes.length];
            return next?.id || (isDark ? 'light' : 'dark');
          })();
    await handleSelectScheme(nextSchemeId);
  }, [activeScheme.id, isDark, toggleableSchemes, handleSelectScheme]);

  if (!shell) return null;

  const locale = shell.locale || 'en';
  const area1Zoom =
    typeof shell.resolveAreaZoom === 'function' ? shell.resolveAreaZoom('area_1') : 1;
  const menus = applyGlobalMenuPlacements(
    shell.menuRegistry.resolve(),
    shell.settings?.global,
    shell.actionsRegistry,
    shell.focusedInstance ? shell.settings?.applications?.[shell.focusedInstance.appId] : null
  );
  const systemLabel = translateShell(locale, 'shell.system.label', 'System Session Menu');
  const systemHint = translateShell(
    locale,
    'shell.system.hint',
    'ScratchRobin Session (Lock Screen / Logout)'
  );
  const mainNavAria = translateShell(locale, 'shell.nav.aria', 'Main Menu');
  const utilitiesAria = translateShell(
    locale,
    'shell.nav.utilities_aria',
    'Language and Appearance'
  );
  const langAria = translateShell(
    locale,
    'shell.language.aria',
    'Language (%s)',
    locale.toUpperCase()
  );
  const langHint = translateShell(
    locale,
    'shell.language.hint',
    'Switch interface language'
  );
  const langHeading = translateShell(
    locale,
    'shell.language.heading',
    'Interface Language'
  );
  const toneLabel =
    activeScheme.id === 'light'
      ? translateShell(locale, 'shell.tone.light', 'Light')
      : activeScheme.id === 'dark'
        ? translateShell(locale, 'shell.tone.dark', 'Dark')
        : activeScheme.label;
  const toneSwitchHint = isDark
    ? translateShell(locale, 'shell.tone.switch_to_light', 'Switch to light theme')
    : translateShell(locale, 'shell.tone.switch_to_dark', 'Switch to dark theme');

  return (
    <header
      ref={barRef}
      className="sr-nav-bar"
      style={{'--sr-area1-zoom': String(area1Zoom)}}
      data-tone={tone}
      data-locale={locale}
      data-test="app-menu-bar"
      data-cdeadmin-qa-key="project-top-menu"
    >
      <NavigationMenu.Root
        className="sr-nav-root sr-nav-root--main"
        aria-label={mainNavAria}
        value={activeMenu}
        delay={80}
        closeDelay={100}
        onValueChange={(nextVal) => {
          setActiveMenu(nextVal);
          if (nextVal != null) setLangMenu(null);
        }}
      >
        <NavigationMenu.List className="sr-nav-list" role="menubar" aria-label={mainNavAria}>
          {menus.map((menu) => {
            if (menu.isSystemIcon || menu.index === PROJECT_TOP_MENU_INDICES.SYSTEM) {
              return (
                <NavigationMenu.Item key={menu.name} value={menu.name} className="sr-nav-item">
                  <button
                    type="button"
                    role="menuitem"
                    className="sr-nav-system-btn"
                    aria-label={systemLabel}
                    title={systemHint}
                    data-menu-index={menu.index}
                    data-menu-name={menu.name}
                    data-cdeadmin-qa-key="top-menu-system-icon"
                    onClick={() => {
                      setActiveMenu(null);
                      setLangMenu(null);
                      shell.openSessionDialog();
                    }}
                  >
                    <Icon iconKey={menu.iconKey || 'tool.scratchrobin'} decorative size="1.25em" />
                  </button>
                </NavigationMenu.Item>
              );
            }

            const triggerLabel = translateMenuTriggerLabel(locale, menu);
            return (
              <NavigationMenu.Item key={menu.name} value={menu.name} className="sr-nav-item">
                <NavigationMenu.Trigger
                  className="sr-nav-trigger"
                  role="menuitem"
                  aria-label={triggerLabel}
                  data-menu-index={menu.index}
                  data-menu-name={menu.name}
                  data-label={triggerLabel}
                >
                  {menu.iconKey && <Icon iconKey={menu.iconKey} decorative size="1em" />}
                  <span>{triggerLabel}</span>
                  <NavigationMenu.Icon className="sr-nav-chevron">
                    <ChevronDownSvg />
                  </NavigationMenu.Icon>
                </NavigationMenu.Trigger>

                <NavigationMenu.Content className="sr-nav-content">
                  <NavigationMenuPanelContent
                    menu={menu}
                    locale={locale}
                    actionsRegistry={shell.actionsRegistry}
                  />
                </NavigationMenu.Content>
              </NavigationMenu.Item>
            );
          })}
        </NavigationMenu.List>

        <NavigationMenu.Portal>
          <NavigationMenu.Positioner
            className="sr-nav-positioner"
            data-tone={tone}
            sideOffset={8}
            collisionPadding={{top: 6, bottom: 6, left: 12, right: 12}}
          >
            <NavigationMenu.Popup
              className="sr-nav-popup"
              aria-hidden={activeMenu == null ? 'true' : undefined}
            >
              <NavigationMenu.Arrow className="sr-nav-arrow">
                <ArrowSvg />
              </NavigationMenu.Arrow>
              <NavigationMenu.Viewport className="sr-nav-viewport" />
            </NavigationMenu.Popup>
          </NavigationMenu.Positioner>
        </NavigationMenu.Portal>
      </NavigationMenu.Root>

      {/* Right-aligned controls: Base UI Language NavigationMenu + Theme Switcher */}
      <div
        className="sr-nav-utilities"
        data-cdeadmin-qa-key="top-menu-right-controls"
      >
        <NavigationMenu.Root
          className="sr-nav-root"
          aria-label={utilitiesAria}
          value={langMenu}
          delay={80}
          closeDelay={100}
          onValueChange={(nextVal) => {
            setLangMenu(nextVal);
            if (nextVal != null) setActiveMenu(null);
          }}
        >
          <NavigationMenu.List className="sr-nav-list">
            <NavigationMenu.Item value="language" className="sr-nav-item">
              <NavigationMenu.Trigger
                className="sr-nav-trigger sr-nav-trigger--utility"
                aria-label={langAria}
                title={langHint}
                data-cdeadmin-qa-key="top-menu-language"
              >
                <GlobeSvg />
                <span>{locale.toUpperCase()}</span>
                <NavigationMenu.Icon className="sr-nav-chevron">
                  <ChevronDownSvg />
                </NavigationMenu.Icon>
              </NavigationMenu.Trigger>

              <NavigationMenu.Content className="sr-nav-content sr-nav-content--compact">
                <div className="sr-nav-heading">{langHeading}</div>
                <ul className="sr-nav-section-list" role="menu" aria-label={langHeading}>
                  {shell.languages.map((lang) => {
                    const selected = lang.code === locale;
                    return (
                      <li key={lang.code} className="sr-nav-list-entry">
                        <NavigationMenu.Link
                          closeOnClick
                          active={selected}
                          className="sr-nav-card-link sr-nav-card-link--compact"
                          data-checked={selected ? 'true' : undefined}
                          data-language-code={lang.code}
                          render={
                            <button
                              type="button"
                              role="menuitemradio"
                              aria-label={lang.label}
                              aria-checked={selected}
                            />
                          }
                          onClick={() => {
                            void shell.changeLanguage(lang.code);
                          }}
                        >
                          <span className="sr-nav-card-body">
                            <span className="sr-nav-card-title">{lang.label}</span>
                          </span>
                          <span className="sr-nav-card-meta" aria-hidden="true">
                            <span className="sr-nav-shortcut">{lang.code.toUpperCase()}</span>
                            <span className="sr-nav-check-badge">{selected ? '✓' : ''}</span>
                          </span>
                        </NavigationMenu.Link>
                      </li>
                    );
                  })}
                </ul>
              </NavigationMenu.Content>
            </NavigationMenu.Item>

            <NavigationMenu.Item value="scheme" className="sr-nav-item">
              <NavigationMenu.Trigger
                className="sr-nav-trigger sr-nav-trigger--utility"
                aria-label="Select colour scheme"
                title="Choose colour scheme or manage custom palettes"
                data-cdeadmin-qa-key="top-menu-scheme-menu"
              >
                <span
                  aria-hidden="true"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '2px',
                  }}
                >
                  <span
                    style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '999px',
                      background: activeScheme?.colors?.backdropA || '#28749e',
                      border: '1px solid rgba(128,128,128,0.45)',
                    }}
                  />
                  <span
                    style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '999px',
                      background: activeScheme?.colors?.accent || '#0d6ca8',
                      border: '1px solid rgba(128,128,128,0.45)',
                    }}
                  />
                </span>
                <NavigationMenu.Icon className="sr-nav-chevron">
                  <ChevronDownSvg />
                </NavigationMenu.Icon>
              </NavigationMenu.Trigger>

              <NavigationMenu.Content className="sr-nav-content sr-nav-content--compact">
                <div className="sr-nav-heading">Colour Schemes</div>
                <ul className="sr-nav-section-list" role="menu" aria-label="Colour Schemes">
                  {toggleableSchemes.map((scheme) => {
                    const selected = scheme.id === activeScheme.id;
                    return (
                      <li key={scheme.id} className="sr-nav-list-entry">
                        <NavigationMenu.Link
                          closeOnClick
                          active={selected}
                          className="sr-nav-card-link sr-nav-card-link--compact"
                          data-checked={selected ? 'true' : undefined}
                          data-scheme-id={scheme.id}
                          data-cdeadmin-qa-key={`top-menu-scheme-option-${scheme.id}`}
                          render={
                            <button
                              type="button"
                              role="menuitemradio"
                              aria-label={scheme.label}
                              aria-checked={selected}
                            />
                          }
                          onClick={() => {
                            void handleSelectScheme(scheme.id);
                          }}
                        >
                          <span
                            aria-hidden="true"
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '3px',
                              flexShrink: 0,
                            }}
                          >
                            <span
                              style={{
                                width: '10px',
                                height: '10px',
                                borderRadius: '3px',
                                background: scheme.colors?.backdropA,
                                border: '1px solid rgba(128,128,128,0.4)',
                              }}
                            />
                            <span
                              style={{
                                width: '10px',
                                height: '10px',
                                borderRadius: '3px',
                                background: scheme.colors?.islandBg,
                                border: '1px solid rgba(128,128,128,0.4)',
                              }}
                            />
                            <span
                              style={{
                                width: '10px',
                                height: '10px',
                                borderRadius: '3px',
                                background: scheme.colors?.accent,
                                border: '1px solid rgba(128,128,128,0.4)',
                              }}
                            />
                          </span>
                          <span className="sr-nav-card-body">
                            <span className="sr-nav-card-title">{scheme.label}</span>
                          </span>
                          <span className="sr-nav-card-meta" aria-hidden="true">
                            <span className="sr-nav-shortcut">
                              {scheme.baseTone === 'dark' ? 'DARK' : 'LIGHT'}
                            </span>
                            <span className="sr-nav-check-badge">{selected ? '✓' : ''}</span>
                          </span>
                        </NavigationMenu.Link>
                      </li>
                    );
                  })}
                  <li className="sr-nav-list-entry" style={{borderTop: '1px solid var(--sr-nav-border)', marginTop: '4px', paddingTop: '4px'}}>
                    <NavigationMenu.Link
                      closeOnClick
                      className="sr-nav-card-link sr-nav-card-link--compact"
                      data-cdeadmin-qa-key="top-menu-manage-schemes"
                      render={
                        <button
                          type="button"
                          role="menuitem"
                          aria-label="Customize Colour Schemes & Fonts"
                        />
                      }
                      onClick={() => {
                        if (typeof shell?.openSettingsDialog === 'function') {
                          shell.openSettingsDialog('global', null, 'appearance:schemes');
                        } else if (typeof window !== 'undefined') {
                          window.dispatchEvent(
                            new CustomEvent('scratchrobin:open-preferences', {
                              detail: {mode: 'global', sectionId: 'appearance:schemes'},
                            })
                          );
                        }
                      }}
                    >
                      <span className="sr-nav-card-body">
                        <span className="sr-nav-card-title">Customize Schemes &amp; Fonts…</span>
                      </span>
                    </NavigationMenu.Link>
                  </li>
                </ul>
              </NavigationMenu.Content>
            </NavigationMenu.Item>
          </NavigationMenu.List>

          <NavigationMenu.Portal>
            <NavigationMenu.Positioner
              className="sr-nav-positioner"
              data-tone={tone}
              align="end"
              sideOffset={8}
              collisionPadding={{top: 6, bottom: 6, left: 12, right: 12}}
            >
              <NavigationMenu.Popup
                className="sr-nav-popup"
                aria-hidden={langMenu == null ? 'true' : undefined}
              >
                <NavigationMenu.Arrow className="sr-nav-arrow">
                  <ArrowSvg />
                </NavigationMenu.Arrow>
                <NavigationMenu.Viewport className="sr-nav-viewport" />
              </NavigationMenu.Popup>
            </NavigationMenu.Positioner>
          </NavigationMenu.Portal>
        </NavigationMenu.Root>

        <button
          type="button"
          className="sr-nav-tone-btn"
          aria-label={toneSwitchHint}
          aria-pressed={isDark}
          title={toneSwitchHint}
          data-cdeadmin-qa-key="top-menu-tone"
          onClick={() => {
            void handleToggleTone();
          }}
        >
          <ToneIconSvg isDark={isDark} />
          <span>{toneLabel}</span>
        </button>
      </div>
    </header>
  );
}

ProjectNavigationMenuBar.propTypes = {
  shell: PropTypes.object,
};
