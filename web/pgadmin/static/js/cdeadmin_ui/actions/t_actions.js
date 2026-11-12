/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useReducer} from 'react';
import gettext from 'sources/gettext';
import {commandRegistry} from '../commands/CommandRegistry';
import {inferActionIconKey} from '../icons/registry';

const ACTION_ID_PATTERN = /^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$/;

export const T_ACTION_SCHEMA = 'cdeadmin.t_action.v1';

export const T_ACTION_STATUS = Object.freeze({
  ENABLED: 'enabled',
  DISABLED: 'disabled',
  INVISIBLE: 'invisible',
});

const VALID_STATUSES = new Set(Object.values(T_ACTION_STATUS));

export const T_ACTION_TARGET_KIND = Object.freeze({
  CLIENT: 'client',
  SERVER: 'server',
});

function normalizeActionId(rawId) {
  const id = String(rawId ?? '').trim();
  if (!ACTION_ID_PATTERN.test(id)) {
    throw new TypeError(`Invalid t_actions identifier: "${rawId}"`);
  }
  return id;
}

function normalizeStatus(status, fallback = T_ACTION_STATUS.ENABLED) {
  const candidate = String(status ?? fallback).trim().toLowerCase();
  if (!VALID_STATUSES.has(candidate)) {
    throw new TypeError(
      `Invalid t_actions status "${status}". Expected enabled, disabled, or invisible.`
    );
  }
  return candidate;
}

function normalizeTarget(id, input = {}) {
  const rawTarget = input.target ?? (
    typeof input.execute === 'function'
      ? {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: input.execute}
      : typeof input.handler === 'function'
        ? {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: input.handler}
        : input.endpoint
          ? {
            kind: T_ACTION_TARGET_KIND.SERVER,
            endpoint: input.endpoint,
            method: input.method || 'POST',
          }
          : null
  );

  if (!rawTarget || typeof rawTarget !== 'object') {
    throw new TypeError(`t_action "${id}" requires a client or server code target.`);
  }

  const kind = String(rawTarget.kind || '').trim().toLowerCase();
  if (kind === T_ACTION_TARGET_KIND.CLIENT) {
    const invoke = rawTarget.invoke ?? rawTarget.handler ?? rawTarget.execute;
    if (typeof invoke !== 'function') {
      throw new TypeError(`Client t_action "${id}" requires a callable invoke handler.`);
    }
    return Object.freeze({
      kind: T_ACTION_TARGET_KIND.CLIENT,
      invoke,
    });
  }

  if (kind === T_ACTION_TARGET_KIND.SERVER) {
    const endpoint = String(
      rawTarget.endpoint || `/cdeadmin/api/shell/actions/${id}/invoke`
    ).trim();
    if (!endpoint) {
      throw new TypeError(`Server t_action "${id}" requires an endpoint.`);
    }
    const method = String(rawTarget.method || 'POST').trim().toUpperCase();
    return Object.freeze({
      kind: T_ACTION_TARGET_KIND.SERVER,
      endpoint,
      method,
      buildPayload: typeof rawTarget.buildPayload === 'function'
        ? rawTarget.buildPayload
        : null,
    });
  }

  throw new TypeError(`t_action "${id}" target.kind must be "client" or "server".`);
}

export function createTAction(input = {}) {
  const id = normalizeActionId(input.id);
  const application = String(input.application || 'project').trim().toLowerCase() || 'project';
  const defaultText = String(input.defaultText ?? input.text ?? input.label ?? id);
  const defaultHint = String(input.defaultHint ?? input.hint ?? input.description ?? '');
  const icon = String(
    input.icon ||
    input.iconKey ||
    inferActionIconKey({name: id, label: defaultText}) ||
    'command.default'
  ).trim();
  const baseStatus = normalizeStatus(input.status, T_ACTION_STATUS.ENABLED);
  const target = normalizeTarget(id, input);

  return Object.freeze({
    schema: T_ACTION_SCHEMA,
    id,
    icon,
    application,
    status: baseStatus,
    baseStatus,
    focusScoped: Boolean(input.focusScoped),
    checked: typeof input.checked === 'boolean' ? input.checked : undefined,
    shortcut: input.shortcut ? String(input.shortcut) : '',
    toolbarSize: input.toolbarSize === 'large' ? 'large' : 'small',
    paletteItems: Array.isArray(input.paletteItems) ? Object.freeze([...input.paletteItems]) : undefined,
    defaultText,
    defaultHint,
    target,
  });
}

function csrfHeaders() {
  if (typeof window === 'undefined') return {};
  const pgAdmin = window.pgAdmin;
  const headerName = pgAdmin?.csrf_token_header || 'X-pgA-CSRFToken';
  const token = pgAdmin?.csrf_token ||
    document?.querySelector?.('meta[name="csrf-token"]')?.getAttribute('content') ||
    '';
  return token ? {[headerName]: token} : {};
}

export class TActionsRegistry {
  constructor({
    translate = gettext,
    fetchImpl = (...args) => fetch(...args),
  } = {}) {
    this._translate = translate;
    this._fetch = fetchImpl;
    this._actions = new Map();
    this._runtimeStatuses = new Map();
    this._checkedStates = new Map();
    this._authzOverrides = new Map();
    this._i18nCatalog = new Map();
    this._locale = 'en';
    this._listeners = new Set();
  }

  subscribe(listener) {
    if (typeof listener !== 'function') {
      throw new TypeError('t_actions listener must be a function.');
    }
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  _notify() {
    this._listeners.forEach((listener) => {
      try {
        listener();
      } catch {
        // Keep other subscribers healthy.
      }
    });
  }

  setLocale(locale, strings = null) {
    this._locale = String(locale || 'en').trim() || 'en';
    if (strings && typeof strings === 'object') {
      this.registerStrings(this._locale, strings);
    } else {
      this._notify();
    }
  }

  getLocale() {
    return this._locale;
  }

  registerStrings(locale, dictionary = {}) {
    const loc = String(locale || 'en').trim() || 'en';
    const current = this._i18nCatalog.get(loc) || {};
    this._i18nCatalog.set(loc, {...current, ...dictionary});
    this._notify();
  }

  register(input) {
    const action = createTAction(input);
    if (this._actions.has(action.id)) {
      throw new Error(`t_action already registered: ${action.id}`);
    }
    this._actions.set(action.id, action);
    const initialStatus = action.focusScoped
      ? T_ACTION_STATUS.INVISIBLE
      : action.status;
    this._runtimeStatuses.set(action.id, initialStatus);
    if (typeof action.checked === 'boolean') {
      this._checkedStates.set(action.id, action.checked);
    }
    this._notify();
    return () => this.unregister(action.id);
  }

  upsert(input) {
    const action = createTAction(input);
    const prevStatus = this._runtimeStatuses.get(action.id);
    this._actions.set(action.id, action);
    if (prevStatus === undefined) {
      this._runtimeStatuses.set(
        action.id,
        action.focusScoped ? T_ACTION_STATUS.INVISIBLE : action.status
      );
    } else if (input.status !== undefined) {
      this._runtimeStatuses.set(action.id, action.status);
    }
    if (typeof input.checked === 'boolean') {
      this._checkedStates.set(action.id, input.checked);
    }
    this._notify();
    return this.resolve(action.id);
  }

  unregister(id) {
    const normalized = normalizeActionId(id);
    const existed = this._actions.delete(normalized);
    this._runtimeStatuses.delete(normalized);
    this._checkedStates.delete(normalized);
    if (existed) this._notify();
    return existed;
  }

  has(id) {
    try {
      return this._actions.has(normalizeActionId(id));
    } catch {
      return false;
    }
  }

  _lookupI18n(id, suffix, fallback) {
    const key = `${id}.${suffix}`;
    const localeMap = this._i18nCatalog.get(this._locale);
    if (localeMap && typeof localeMap[key] === 'string') {
      return localeMap[key];
    }
    const baseLocale = String(this._locale || '').split(/[-_]/)[0].toLowerCase();
    if (baseLocale && baseLocale !== this._locale) {
      const baseMap = this._i18nCatalog.get(baseLocale);
      if (baseMap && typeof baseMap[key] === 'string') {
        return baseMap[key];
      }
    }
    if (typeof this._translate === 'function') {
      const translated = this._translate(key);
      if (translated && translated !== key) {
        return translated;
      }
      if (fallback) {
        const direct = this._translate(fallback);
        if (direct) return direct;
      }
    }
    return fallback;
  }

  resolve(id) {
    const normalized = normalizeActionId(id);
    const base = this._actions.get(normalized);
    if (!base) {
      throw new Error(`Unknown t_action: ${normalized}`);
    }
    const runtimeStatus = this._runtimeStatuses.get(normalized) ?? base.status;
    const authzOverride = this._authzOverrides.get(normalized);
    let effectiveStatus = runtimeStatus;
    if (authzOverride === T_ACTION_STATUS.INVISIBLE) {
      effectiveStatus = T_ACTION_STATUS.INVISIBLE;
    } else if (
      authzOverride === T_ACTION_STATUS.DISABLED &&
      effectiveStatus === T_ACTION_STATUS.ENABLED
    ) {
      effectiveStatus = T_ACTION_STATUS.DISABLED;
    }

    const text = this._lookupI18n(normalized, 'text', base.defaultText);
    const hint = this._lookupI18n(normalized, 'hint', base.defaultHint);
    const checked = this._checkedStates.has(normalized)
      ? this._checkedStates.get(normalized)
      : base.checked;

    return Object.freeze({
      ...base,
      status: effectiveStatus,
      enabled: effectiveStatus === T_ACTION_STATUS.ENABLED,
      visible: effectiveStatus !== T_ACTION_STATUS.INVISIBLE,
      checked,
      text,
      hint,
    });
  }

  list({application = null, includeInvisible = true} = {}) {
    const appFilter = application ? String(application).trim().toLowerCase() : null;
    const result = [];
    for (const id of this._actions.keys()) {
      const resolved = this.resolve(id);
      if (appFilter && resolved.application !== appFilter) continue;
      if (!includeInvisible && !resolved.visible) continue;
      result.push(resolved);
    }
    return result;
  }

  setStatus(id, status) {
    const normalized = normalizeActionId(id);
    if (!this._actions.has(normalized)) {
      throw new Error(`Unknown t_action: ${normalized}`);
    }
    const nextStatus = normalizeStatus(status);
    if (this._runtimeStatuses.get(normalized) !== nextStatus) {
      this._runtimeStatuses.set(normalized, nextStatus);
      this._notify();
    }
    return this.resolve(normalized);
  }

  setChecked(id, checked) {
    const normalized = normalizeActionId(id);
    if (!this._actions.has(normalized)) {
      throw new Error(`Unknown t_action: ${normalized}`);
    }
    const next = Boolean(checked);
    if (this._checkedStates.get(normalized) !== next) {
      this._checkedStates.set(normalized, next);
      this._notify();
    }
    return this.resolve(normalized);
  }

  setStatuses(statusMap = {}) {
    let changed = false;
    Object.entries(statusMap || {}).forEach(([id, status]) => {
      const normalized = normalizeActionId(id);
      if (!this._actions.has(normalized)) return;
      const next = normalizeStatus(status);
      if (this._runtimeStatuses.get(normalized) !== next) {
        this._runtimeStatuses.set(normalized, next);
        changed = true;
      }
    });
    if (changed) this._notify();
  }

  setAuthorizationOverrides(overrides = {}) {
    this._authzOverrides.clear();
    Object.entries(overrides || {}).forEach(([id, status]) => {
      if (!ACTION_ID_PATTERN.test(String(id || '').trim())) return;
      const candidate = String(status || '').trim().toLowerCase();
      if (VALID_STATUSES.has(candidate)) {
        this._authzOverrides.set(String(id).trim(), candidate);
      }
    });
    this._notify();
  }

  /**
   * Step 1 of Teardown-Before-Activate: hides all focus-scoped actions
   * owned by the outgoing application (or all non-project applications when null).
   */
  deactivateApplication(application = null) {
    const appFilter = application ? String(application).trim().toLowerCase() : null;
    let changed = false;
    for (const [id, action] of this._actions.entries()) {
      if (!action.focusScoped) continue;
      if (appFilter && action.application !== appFilter) continue;
      if (this._runtimeStatuses.get(id) !== T_ACTION_STATUS.INVISIBLE) {
        this._runtimeStatuses.set(id, T_ACTION_STATUS.INVISIBLE);
        changed = true;
      }
    }
    if (changed) this._notify();
  }

  /**
   * Step 4 of Teardown-Before-Activate: activates focus-scoped actions for
   * the incoming application according to its baseStatus + per-instance overrides.
   */
  activateApplication(application, statusOverrides = {}) {
    const appFilter = String(application || '').trim().toLowerCase();
    if (!appFilter) return;
    let changed = false;
    for (const [id, action] of this._actions.entries()) {
      if (action.application !== appFilter) continue;
      const desired = statusOverrides[id] !== undefined
        ? normalizeStatus(statusOverrides[id])
        : action.baseStatus;
      if (this._runtimeStatuses.get(id) !== desired) {
        this._runtimeStatuses.set(id, desired);
        changed = true;
      }
    }
    if (changed) this._notify();
  }

  async execute(id, args = {}, context = {}) {
    const resolved = this.resolve(id);
    if (resolved.status === T_ACTION_STATUS.INVISIBLE) {
      const err = new Error(`Action is invisible and cannot run: ${resolved.id}`);
      err.code = 'action_invisible';
      throw err;
    }
    if (resolved.status === T_ACTION_STATUS.DISABLED) {
      const err = new Error(`Action is disabled: ${resolved.id}`);
      err.code = 'action_disabled';
      throw err;
    }

    if (resolved.target.kind === T_ACTION_TARGET_KIND.CLIENT) {
      return await resolved.target.invoke(args, context);
    }

    const payload = resolved.target.buildPayload
      ? resolved.target.buildPayload(args, context)
      : args;
    const method = resolved.target.method;
    const response = await this._fetch(resolved.target.endpoint, {
      method,
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        ...csrfHeaders(),
      },
      ...(method === 'GET' ? {} : {body: JSON.stringify(payload ?? {})}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const err = new Error(data?.error || `Server action failed (${response.status})`);
      err.code = data?.code || 'server_action_failed';
      throw err;
    }
    return data;
  }

  /**
   * Build `{model, state, catalog, onCommand}` for `scratch_notebookbar`'s
   * `<NotebookBar />` directly from `t_actions` entries.
   */
  toNotebookBar(tabsSpec = [], renderIcon = () => null, quickAccessSpec = []) {
    const state = {};
    const catalog = {};

    const mapControl = (itemSpec) => {
      if (!itemSpec) return null;
      if (itemSpec.type === 'separator') return {type: 'separator'};
      if (itemSpec.type === 'stack' && Array.isArray(itemSpec.controls)) {
        const children = itemSpec.controls.map(mapControl).filter(Boolean);
        return children.length
          ? {type: 'stack', id: itemSpec.id, controls: children}
          : null;
      }

      const actionId = typeof itemSpec === 'string' ? itemSpec : itemSpec.actionId || itemSpec.id;
      if (!actionId || !this.has(actionId)) return null;
      const action = this.resolve(actionId);
      state[action.id] = {
        enabled: action.status === T_ACTION_STATUS.ENABLED,
        hidden: action.status === T_ACTION_STATUS.INVISIBLE,
        ...(typeof action.checked === 'boolean' ? {checked: action.checked} : {}),
      };
      const rawPaletteItems =
        (typeof itemSpec === 'object' && Array.isArray(itemSpec.items) && itemSpec.items) ||
        action.paletteItems ||
        null;
      const mappedMenuItems = rawPaletteItems
        ? rawPaletteItems.map((entry, idx) => {
          if (entry.type === 'separator') return {type: 'separator'};
          return {
            id: entry.id || `${action.id}.item.${idx}`,
            label: entry.label || entry.id || `${action.id}.${idx}`,
            command: entry.command || action.id,
            checked: entry.checked,
            disabled: Boolean(entry.disabled),
            icon: entry.icon
              ? (size) => renderIcon({icon: entry.icon, text: entry.label}, size)
              : undefined,
          };
        })
        : undefined;

      const controlType = (typeof itemSpec === 'object' && itemSpec.type)
        ? itemSpec.type
        : mappedMenuItems
          ? 'menu'
          : typeof action.checked === 'boolean'
            ? 'toggle'
            : 'button';
      const control = {
        id: (typeof itemSpec === 'object' && itemSpec.controlId) || action.id,
        command: action.id,
        label: action.text,
        tooltip: action.hint || action.text,
        shortcut: action.shortcut || undefined,
        type: controlType,
        size: (typeof itemSpec === 'object' && itemSpec.size) || 'small',
        showLabel: Boolean(typeof itemSpec === 'object' && itemSpec.showLabel),
        ...(mappedMenuItems ? {items: mappedMenuItems} : {}),
        icon: (size) => renderIcon(action, size),
      };
      catalog[action.id] = {
        label: action.text,
        detail: action.application,
        icon: control.icon,
        type: control.type,
      };
      return control;
    };

    const tabs = (tabsSpec || []).map((tab) => ({
      id: tab.id,
      label: tab.label,
      ...(tab.context ? {context: tab.context} : {}),
      ...(tab.selectOnContext ? {selectOnContext: true} : {}),
      groups: (tab.groups || []).map((group, idx) => ({
        id: group.id || `${tab.id}.g${idx}`,
        label: group.label ?? '',
        title: group.title || group.label || group.id || `${tab.id}.g${idx}`,
        priority: Number.isFinite(group.priority) ? group.priority : (100 - idx),
        controls: (group.controls || []).map(mapControl).filter(Boolean),
      })).filter((group) => group.controls.length > 0),
    })).filter((tab) => tab.groups.length > 0);

    const quickAccess = (quickAccessSpec || []).map(mapControl).filter(Boolean);

    return {
      model: {tabs, quickAccess},
      state,
      catalog,
      onCommand: (commandId, detail = {}) => this.execute(commandId, detail),
    };
  }

  syncFromCommandRegistry(sourceRegistry = commandRegistry) {
    if (!sourceRegistry?.list) return;
    for (const cmd of sourceRegistry.list()) {
      if (this.has(cmd.id)) continue;
      const appPrefix = cmd.id.split('.')[0] || 'project';
      this.upsert({
        id: cmd.id,
        icon: cmd.iconKey || 'command.default',
        application: appPrefix,
        defaultText: cmd.label || cmd.id,
        defaultHint: cmd.description || '',
        status: cmd.defaultVisible === false
          ? T_ACTION_STATUS.INVISIBLE
          : cmd.defaultEnabled === false
            ? T_ACTION_STATUS.DISABLED
            : T_ACTION_STATUS.ENABLED,
        target: {
          kind: T_ACTION_TARGET_KIND.CLIENT,
          invoke: (args, ctx) => sourceRegistry.execute(cmd.id, args, ctx),
        },
      });
    }
  }
}

export const t_actions = new TActionsRegistry();

export function useTActions(registry = t_actions, application = null) {
  const [, bump] = useReducer((n) => n + 1, 0);
  useEffect(() => registry.subscribe(bump), [registry]);
  return {
    actions: registry.list({application}),
    resolve: (id) => registry.resolve(id),
    execute: (id, args, ctx) => registry.execute(id, args, ctx),
    setStatus: (id, status) => registry.setStatus(id, status),
  };
}
