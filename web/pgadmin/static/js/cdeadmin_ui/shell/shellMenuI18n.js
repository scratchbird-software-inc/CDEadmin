/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import gettext from 'sources/gettext';
import rawUiCatalogs from 'sources/cdeadmin_ui/i18n/ui_catalogs';

const uiCatalogs = (rawUiCatalogs && rawUiCatalogs.default) || rawUiCatalogs || {};

/**
 * Internationalization (i18n) catalog and translation helpers for the
 * ScratchRobin Main Navigation Menu and Shell controls across all 15
 * supported UI languages.
 */

const SHELL_STRINGS = Object.fromEntries(
  Object.entries(uiCatalogs?.shell || {}).map(([locale, table]) => [locale, {...table}])
);

const MENU_NAME_TO_I18N_KEY = Object.freeze({
  applications: 'menu.applications.title',
  window: 'menu.window.title',
  help: 'menu.help.title',
  object: 'menu.object.title',
  query: 'menu.query.title',
  model: 'menu.model.title',
  cube: 'menu.cube.title',
  bi: 'menu.bi.title',
  screen_mesh: 'menu.screen_mesh.title',
  project: 'menu.project.title',
  design: 'menu.design.title',
  compare: 'menu.compare.title',
});

function interpolate(template, args) {
  if (!args || args.length === 0) return template;
  let idx = 0;
  return String(template).replace(/%s/g, () =>
    idx < args.length ? String(args[idx++]) : '%s'
  );
}

export function normalizeShellLocale(locale) {
  const raw = String(locale || 'en').trim();
  if (!raw) return 'en';
  if (SHELL_STRINGS[raw]) return raw;
  const hyphenToUnderscore = raw.replace(/-/g, '_');
  if (SHELL_STRINGS[hyphenToUnderscore]) return hyphenToUnderscore;
  const lower = hyphenToUnderscore.toLowerCase();
  if (lower.startsWith('zh_hans') || lower === 'zh_cn' || lower === 'zh') {
    return 'zh_Hans_CN';
  }
  if (lower.startsWith('zh_hant') || lower === 'zh_tw' || lower === 'zh_hk') {
    return 'zh_Hant_TW';
  }
  if (lower.startsWith('pt')) {
    return 'pt_BR';
  }
  const base = hyphenToUnderscore.split('_')[0].toLowerCase();
  if (SHELL_STRINGS[base]) return base;
  return hyphenToUnderscore;
}

/**
 * Register or extend shell menu translations for a locale at runtime.
 */
export function registerShellLocaleStrings(locale, entries) {
  const norm = String(locale || '').trim();
  if (!norm || !entries || typeof entries !== 'object') return;
  SHELL_STRINGS[norm] = {
    ...(SHELL_STRINGS[norm] || {}),
    ...entries,
  };
}

/**
 * Translate a structured shell i18n key for `locale`, falling back to
 * `sources/gettext(defaultText)` and English defaults.
 */
export function translateShell(locale, key, defaultText = '', ...args) {
  const norm = normalizeShellLocale(locale);
  const base = norm.split('_')[0].toLowerCase();
  const enTable = SHELL_STRINGS.en || {};
  const targetTable = SHELL_STRINGS[norm] || SHELL_STRINGS[base];

  const fallback = defaultText || enTable[key] || key;

  if (norm !== 'en' && targetTable && targetTable[key]) {
    return interpolate(targetTable[key], args);
  }

  // Allow server-injected Flask-Babel catalog to translate when present
  if (typeof gettext === 'function' && fallback) {
    const serverTranslated = gettext(fallback, ...args);
    if (serverTranslated && serverTranslated !== fallback) {
      return serverTranslated;
    }
  }

  const chosen = (targetTable && targetTable[key]) || enTable[key] || fallback;
  return interpolate(chosen, args);
}

/**
 * Resolve a top-level menu trigger label through the i18n catalog.
 */
export function translateMenuTriggerLabel(locale, menu) {
  if (!menu) return '';
  if (menu.i18nKey) {
    return translateShell(locale, menu.i18nKey, menu.label || menu.name);
  }
  const mappedKey = MENU_NAME_TO_I18N_KEY[menu.name];
  if (mappedKey) {
    return translateShell(locale, mappedKey, menu.label || menu.name);
  }
  if (typeof gettext === 'function' && menu.label) {
    return gettext(menu.label);
  }
  return menu.label || menu.name;
}

const ITEM_ID_TO_I18N_PREFIX = Object.freeze({
  'shell.datasources.open': 'menu.applications.data_sources',
  'applications.data_sources': 'menu.applications.data_sources',
  'shell.preferences.open': 'menu.applications.preferences',
  'applications.preferences': 'menu.applications.preferences',
  'shell.command_palette': 'menu.applications.command_palette',
  'applications.command_palette': 'menu.applications.command_palette',
  'window.toolbar.notebookbar': 'menu.window.tabbed_icon_bar',
  'window.toggle.tabbed_icon_bar': 'menu.window.tabbed_icon_bar',
  'shell.window.toggle_icon_bar': 'menu.window.tabbed_icon_bar',
  'window.toolbar.status_bar': 'menu.window.status_bar',
  'window.toggle.status_bar': 'menu.window.status_bar',
  'shell.window.toggle_status_bar': 'menu.window.status_bar',
  'shell.left_drawer.toggle': 'menu.window.left_drawer',
  'window.toggle.left_drawer': 'menu.window.left_drawer',
  'shell.window.toggle_left_drawer': 'menu.window.left_drawer',
  'window.toolbar.right_drawer': 'menu.window.right_drawer',
  'shell.right_drawer.toggle': 'menu.window.right_drawer',
  'window.toggle.right_drawer': 'menu.window.right_drawer',
  'shell.window.toggle_right_drawer': 'menu.window.right_drawer',
  'shell.window.detach_active': 'menu.window.detach_active',
  'window.detach_active': 'menu.window.detach_active',
  'shell.window.dashboard': 'menu.window.user_dashboard',
  'window.user_dashboard': 'menu.window.user_dashboard',
  'shell.window.close': 'menu.window.close',
  'window.close_active': 'menu.window.close',
  'shell.help.sql_reference': 'menu.help.sql_reference',
  'help.sql_reference': 'menu.help.sql_reference',
  'help.reference.sql': 'menu.help.sql_reference',
  'shell.help.engine_reference': 'menu.help.engine_reference',
  'help.engine_reference': 'menu.help.engine_reference',
  'help.reference.engines': 'menu.help.engine_reference',
  'shell.help.glossary': 'menu.help.glossary',
  'help.glossary': 'menu.help.glossary',
  'help.reference.glossary': 'menu.help.glossary',
  'shell.help.docs': 'menu.help.docs',
  'help.documentation': 'menu.help.docs',
  'shell.help.about': 'menu.help.about',
  'help.about': 'menu.help.about',
});

const CANONICAL_APP_IDS = Object.freeze([
  'data-navigator',
  'sql-editor',
  'erd-designer',
  'cube-designer',
  'bi-designer',
  'screen-mesh-designer',
  'schema-compare',
  'project-explorer',
  'command-line',
  'ml-vector',
  'ai-assistant',
  'ai-interface',
  'discovery',
]);

/**
 * Resolve a menu item's display label through i18n keys, `t_actions`, and `gettext`.
 */
export function translateMenuItemLabel(locale, item, resolvedAction = null) {
  if (!item) return '';
  const args = Array.isArray(item.i18nArgs) ? item.i18nArgs : [];
  if (item.i18nKey) {
    return translateShell(
      locale,
      item.i18nKey,
      resolvedAction?.text || item.label || item.id,
      ...args
    );
  }
  const id = item.actionId || item.id || '';
  if (id.startsWith('shell.app.open.')) {
    const appId = id.slice('shell.app.open.'.length);
    return translateShell(
      locale,
      `app.${appId}.label`,
      resolvedAction?.text || item.label || appId
    );
  }
  const mappedPrefix = ITEM_ID_TO_I18N_PREFIX[id] || ITEM_ID_TO_I18N_PREFIX[item.id];
  if (mappedPrefix) {
    return translateShell(
      locale,
      `${mappedPrefix}.text`,
      resolvedAction?.text || item.label || id,
      ...args
    );
  }
  if (resolvedAction?.text) {
    return typeof gettext?.retranslate === 'function'
      ? gettext.retranslate(resolvedAction.text)
      : resolvedAction.text;
  }
  if (typeof gettext === 'function' && item.label) {
    return gettext(item.label);
  }
  return item.label || item.id || '';
}

/**
 * Resolve a menu item's subtitle / description hint through i18n keys and `t_actions`.
 */
export function translateMenuItemHint(locale, item, resolvedAction = null) {
  if (!item) return '';
  const args = Array.isArray(item.i18nArgs) ? item.i18nArgs : [];
  if (item.hintKey) {
    return translateShell(
      locale,
      item.hintKey,
      item.hint || resolvedAction?.hint || '',
      ...args
    );
  }
  const id = item.actionId || item.id || '';
  if (id.startsWith('shell.app.open.')) {
    const appId = id.slice('shell.app.open.'.length);
    return translateShell(
      locale,
      `app.${appId}.hint`,
      resolvedAction?.hint || ''
    );
  }
  const mappedPrefix = ITEM_ID_TO_I18N_PREFIX[id] || ITEM_ID_TO_I18N_PREFIX[item.id];
  if (mappedPrefix) {
    return translateShell(
      locale,
      `${mappedPrefix}.hint`,
      item.hint || resolvedAction?.hint || '',
      ...args
    );
  }
  if (item.hint) {
    return typeof gettext === 'function' ? gettext(item.hint) : item.hint;
  }
  return resolvedAction?.hint || '';
}

/**
 * Sync built-in shell action translations into a `TActionsRegistry` instance.
 */
export function syncShellActionStrings(actionsRegistry) {
  if (!actionsRegistry || typeof actionsRegistry.registerStrings !== 'function') {
    return;
  }

  Object.keys(SHELL_STRINGS).forEach((locale) => {
    const table = SHELL_STRINGS[locale];
    const bundle = {};
    if (table['shell.system.label']) {
      bundle['shell.system.session.text'] = table['shell.system.label'];
    }
    if (table['shell.system.hint']) {
      bundle['shell.system.session.hint'] = table['shell.system.hint'];
    }
    Object.entries(ITEM_ID_TO_I18N_PREFIX).forEach(([actionId, prefix]) => {
      if (table[`${prefix}.text`]) {
        bundle[`${actionId}.text`] = table[`${prefix}.text`];
      }
      if (table[`${prefix}.hint`]) {
        bundle[`${actionId}.hint`] = table[`${prefix}.hint`];
      }
    });
    CANONICAL_APP_IDS.forEach((appId) => {
      if (table[`app.${appId}.label`]) {
        bundle[`shell.app.open.${appId}.text`] = table[`app.${appId}.label`];
      }
      if (table[`app.${appId}.hint`]) {
        bundle[`shell.app.open.${appId}.hint`] = table[`app.${appId}.hint`];
      }
    });
    actionsRegistry.registerStrings(locale, bundle);
  });
}

export function getSupportedShellLocales() {
  return Object.keys(SHELL_STRINGS);
}
