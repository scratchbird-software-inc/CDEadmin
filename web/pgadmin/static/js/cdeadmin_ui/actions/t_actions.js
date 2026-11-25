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
import {
  CALLABLE_CODE_TARGETS,
  STANDARD_TIB_ACTIONS,
} from '../shell/tibStandardConfig';

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
    const handlerId = rawTarget.handlerId ? String(rawTarget.handlerId).trim() : '';
    const eventName = rawTarget.eventName ? String(rawTarget.eventName).trim() : '';
    const actionKey = rawTarget.actionKey ? String(rawTarget.actionKey).trim() : '';
    const invoke =
      rawTarget.invoke ??
      rawTarget.handler ??
      rawTarget.execute ??
      (eventName
        ? (args, context) => {
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent(eventName, {
                detail: {actionId: id, handlerId, actionKey, args, context},
              })
            );
          }
          return {ok: true, eventName, actionId: id};
        }
        : null);
    if (typeof invoke !== 'function') {
      throw new TypeError(`Client t_action "${id}" requires a callable invoke handler.`);
    }
    return Object.freeze({
      kind: T_ACTION_TARGET_KIND.CLIENT,
      invoke,
      ...(handlerId ? {handlerId} : {}),
      ...(eventName ? {eventName} : {}),
      ...(actionKey ? {actionKey} : {}),
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

function stringList(value) {
  if (value === undefined || value === null || value === '') return Object.freeze([]);
  return Object.freeze(
    (Array.isArray(value) ? value : [value])
      .map((item) => String(item).trim())
      .filter(Boolean)
  );
}

export function createTAction(input = {}) {
  const id = normalizeActionId(input.id);
  const canonicalId = input.canonicalId ? String(input.canonicalId).trim() : '';
  const application = String(input.application || 'project').trim().toLowerCase() || 'project';
  const defaultText = String(input.defaultText ?? input.text ?? input.label ?? id);
  const defaultHint = String(input.defaultHint ?? input.hint ?? input.description ?? '');
  const icon = String(
    input.icon ||
    input.iconKey ||
    inferActionIconKey({id, name: id, label: defaultText, description: defaultHint}) ||
    'command.default'
  ).trim();
  const baseStatus = normalizeStatus(input.status, T_ACTION_STATUS.ENABLED);
  const target = normalizeTarget(id, input);
  const requiresConfirmation = Boolean(input.requiresConfirmation);

  return Object.freeze({
    schema: T_ACTION_SCHEMA,
    id,
    ...(canonicalId ? {canonicalId} : {}),
    icon,
    application,
    status: baseStatus,
    baseStatus,
    focusScoped: Boolean(input.focusScoped),
    delegated: Boolean(input.delegated),
    checked: typeof input.checked === 'boolean' ? input.checked : undefined,
    shortcut: input.shortcut ? String(input.shortcut) : '',
    toolbarSize: input.toolbarSize === 'large' ? 'large' : 'small',
    paletteItems: Array.isArray(input.paletteItems) ? Object.freeze([...input.paletteItems]) : undefined,
    permission: stringList(input.permission ?? input.requiredPermission),
    capability: input.capability ? String(input.capability).trim() : '',
    allowedSecurityGroups: stringList(input.allowedSecurityGroups),
    deniedSecurityGroups: stringList(input.deniedSecurityGroups),
    requiresConfirmation,
    confirmationIntent: String(
      input.confirmationIntent ?? (requiresConfirmation ? 'explicit' : 'none')
    ),
    aiExposure: String(input.aiExposure ?? 'hidden'),
    aiRiskClass: input.aiRiskClass == null ? null : String(input.aiRiskClass),
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
    this._actionDefinitions = new Map();
    this._callableTargets = new Map();
    CALLABLE_CODE_TARGETS.forEach((entry) => {
      this._callableTargets.set(entry.id, {
        ...entry,
        invoke: null,
      });
    });
    this._currentUser = null;
    this._activeInstanceId = null;
    this._instanceBindings = new Map();
    this._commandRegistryDetach = null;
    this._i18nCatalog = new Map();
    this._locale = 'en';
    this._listeners = new Set();
  }

  registerCallableTarget(handlerId, invoke, meta = {}) {
    const cleanId = String(handlerId || '').trim();
    if (!cleanId) return () => {};
    const existing = this._callableTargets.get(cleanId) || {};
    this._callableTargets.set(cleanId, {
      ...existing,
      ...meta,
      id: cleanId,
      label: meta.label || existing.label || cleanId,
      category: meta.category || existing.category || 'Custom',
      invoke: typeof invoke === 'function' ? invoke : existing.invoke || null,
    });
    return () => {
      const cur = this._callableTargets.get(cleanId);
      if (cur && cur.invoke === invoke) {
        this._callableTargets.set(cleanId, {...cur, invoke: null});
      }
    };
  }

  listCallableTargets() {
    return [...this._callableTargets.values()];
  }

  setActionDefinitions(definitions = {}) {
    this._actionDefinitions.clear();
    Object.entries(definitions || {}).forEach(([rawId, spec]) => {
      if (!spec || typeof spec !== 'object') return;
      const cleanId = String(rawId || '').trim();
      if (!ACTION_ID_PATTERN.test(cleanId)) return;
      const next = {};
      if (typeof spec.text === 'string' && spec.text.trim()) next.text = spec.text.trim();
      if (typeof spec.hint === 'string') next.hint = spec.hint.trim();
      if (typeof spec.icon === 'string' && spec.icon.trim()) next.icon = spec.icon.trim();
      if (typeof spec.shortcut === 'string') next.shortcut = spec.shortcut.trim();
      if (spec.status && VALID_STATUSES.has(String(spec.status).toLowerCase())) {
        next.status = String(spec.status).toLowerCase();
      }
      if (spec.target && typeof spec.target === 'object') {
        const tKind = String(spec.target.kind || '').trim().toLowerCase();
        if (tKind === T_ACTION_TARGET_KIND.CLIENT || tKind === T_ACTION_TARGET_KIND.SERVER) {
          next.target = {
            kind: tKind,
            ...(spec.target.handlerId ? {handlerId: String(spec.target.handlerId).trim()} : {}),
            ...(spec.target.eventName ? {eventName: String(spec.target.eventName).trim()} : {}),
            ...(spec.target.actionKey ? {actionKey: String(spec.target.actionKey).trim()} : {}),
            ...(spec.target.endpoint ? {endpoint: String(spec.target.endpoint).trim()} : {}),
            ...(spec.target.method ? {method: String(spec.target.method).trim().toUpperCase()} : {}),
          };
        }
      }
      if (Object.keys(next).length > 0) {
        this._actionDefinitions.set(cleanId, Object.freeze(next));
      }
    });
    this._notify();
  }

  getActionDefinitions() {
    return Object.fromEntries(this._actionDefinitions.entries());
  }

  _lookupDefinitionOverride(normalized, base) {
    if (this._actionDefinitions.size === 0) return null;
    if (this._actionDefinitions.has(normalized)) {
      return this._actionDefinitions.get(normalized);
    }
    if (base?.canonicalId && this._actionDefinitions.has(base.canonicalId)) {
      return this._actionDefinitions.get(base.canonicalId);
    }
    const parts = normalized.split('.');
    // Match base prefix for trailing instance-scoped IDs (`sql-editor.execute.sql-editor-1` -> `sql-editor.execute`)
    if (parts.length >= 2) {
      const stem = parts.slice(0, -1).join('.');
      if (this._actionDefinitions.has(stem)) {
        return this._actionDefinitions.get(stem);
      }
    }
    // Match middle-instance surface IDs (`ds.<inst>.commit`, `sql-surf.<inst>.exec_stmt`, `designer.cmd.<inst>.<tab>.<item>`)
    const tail = parts.at(-1);
    if (tail) {
      const surfaceAliases = {
        exec_stmt: 'tib.exec.execute_sql',
        exec_script: 'tib.exec.execute_script',
        autocommit: 'tib.tx.auto_commit_toggle',
        commit: 'tib.tx.commit',
        rollback: 'tib.tx.rollback',
        edit_accept: 'tib.rec.edit_accept_row',
        insert_row: 'tib.rec.insert_row',
        duplicate_row: 'tib.rec.duplicate_row',
        set_null: 'tib.rec.set_null',
      };
      if (parts[0] === 'ds' || parts[0] === 'sql-surf') {
        const directStem = `${parts[0]}.${tail}`;
        if (this._actionDefinitions.has(directStem)) {
          return this._actionDefinitions.get(directStem);
        }
      }
      const canonicalCandidate = surfaceAliases[tail] || `tib.${tail}`;
      if (this._actionDefinitions.has(canonicalCandidate)) {
        return this._actionDefinitions.get(canonicalCandidate);
      }
    }
    return null;
  }

  setCurrentUser(user = null) {
    this._currentUser = user && typeof user === 'object' ? {...user} : null;
    this._notify();
  }

  getCurrentUser() {
    return this._currentUser;
  }

  setActiveInstance(instanceId = null) {
    const next = instanceId ? String(instanceId).trim() : null;
    if (this._activeInstanceId !== next) {
      this._activeInstanceId = next;
      this._notify();
    }
  }

  getActiveInstance() {
    return this._activeInstanceId;
  }

  bindInstanceActions(instanceId, bindings = {}) {
    const inst = String(instanceId || '').trim();
    if (!inst) return () => {};
    const map = new Map();
    Object.entries(bindings || {}).forEach(([rawId, spec]) => {
      if (!spec || !ACTION_ID_PATTERN.test(String(rawId || '').trim())) return;
      const id = String(rawId).trim();
      if (typeof spec === 'function') {
        map.set(id, {invoke: spec, status: T_ACTION_STATUS.ENABLED});
      } else if (typeof spec === 'string') {
        map.set(id, {targetActionId: spec});
      } else if (typeof spec === 'object') {
        map.set(id, {...spec});
      }
    });
    this._instanceBindings.set(inst, map);
    if (this._activeInstanceId === inst) {
      this._notify();
    }
    return () => this.unbindInstanceActions(inst);
  }

  unbindInstanceActions(instanceId) {
    const inst = String(instanceId || '').trim();
    if (!inst) return false;
    const existed = this._instanceBindings.delete(inst);
    if (existed && this._activeInstanceId === inst) {
      this._notify();
    }
    return existed;
  }

  _resolveInstanceDelegation(id) {
    const activeInst = this._activeInstanceId;
    if (!activeInst) return null;
    const explicit = this._instanceBindings.get(activeInst)?.get(id);
    if (explicit) {
      if (explicit.targetActionId && this._actions.has(explicit.targetActionId)) {
        return {type: 'action', actionId: explicit.targetActionId, spec: explicit};
      }
      return {type: 'inline', spec: explicit};
    }
    const suffixedId = `${id}.${activeInst}`;
    if (this._actions.has(suffixedId)) {
      return {type: 'action', actionId: suffixedId, spec: null};
    }
    return null;
  }

  hasPermission(permission) {
    const required = stringList(permission);
    if (required.length === 0) return true;
    if (!this._currentUser) return true;
    if (this._currentUser.is_admin || this._currentUser.is_superuser) return true;
    const perms = new Set(this._currentUser.permissions || []);
    return required.every((p) => perms.has(p));
  }

  _evaluateUserPolicy(base) {
    if (!this._currentUser) return null;
    if (this._currentUser.is_admin || this._currentUser.is_superuser) return null;
    const groups = new Set(this._currentUser.security_groups || []);
    if (base.deniedSecurityGroups?.some((g) => groups.has(g))) {
      return T_ACTION_STATUS.INVISIBLE;
    }
    if (
      base.allowedSecurityGroups?.length > 0 &&
      !base.allowedSecurityGroups.some((g) => groups.has(g))
    ) {
      return T_ACTION_STATUS.INVISIBLE;
    }
    if (base.permission?.length > 0) {
      const perms = new Set(this._currentUser.permissions || []);
      if (!base.permission.every((p) => perms.has(p))) {
        return T_ACTION_STATUS.DISABLED;
      }
    }
    return null;
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
    const normalized = String(id || '').trim();
    if (!normalized) return false;
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

  _translateText(text) {
    if (!text || typeof text !== 'string') return text;
    if (typeof this._translate?.retranslate === 'function') {
      return this._translate.retranslate(text);
    }
    if (typeof this._translate === 'function') {
      return this._translate(text);
    }
    return text;
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
        const direct = this._translateText(fallback);
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
    const delegation = this._resolveInstanceDelegation(normalized);
    let delegatedResolved = null;
    if (delegation?.type === 'action' && delegation.actionId !== normalized) {
      delegatedResolved = this.resolve(delegation.actionId);
    }

    let runtimeStatus = this._runtimeStatuses.get(normalized) ?? base.status;
    if (delegatedResolved) {
      runtimeStatus = delegatedResolved.status;
    } else if (delegation?.type === 'inline') {
      const spec = delegation.spec;
      if (spec.status && VALID_STATUSES.has(String(spec.status).toLowerCase())) {
        runtimeStatus = String(spec.status).toLowerCase();
      } else if (typeof spec.enabled === 'boolean') {
        runtimeStatus = spec.enabled ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED;
      } else {
        runtimeStatus = T_ACTION_STATUS.ENABLED;
      }
    } else if (base.delegated && runtimeStatus === T_ACTION_STATUS.ENABLED) {
      runtimeStatus = T_ACTION_STATUS.DISABLED;
    }

    const defOverride = this._lookupDefinitionOverride(normalized, base);
    const userPolicyStatus = this._evaluateUserPolicy(base);
    const authzOverride = this._authzOverrides.get(normalized);
    let effectiveStatus = runtimeStatus;
    if (defOverride?.status) {
      effectiveStatus = defOverride.status;
    }
    if (
      authzOverride === T_ACTION_STATUS.INVISIBLE ||
      userPolicyStatus === T_ACTION_STATUS.INVISIBLE
    ) {
      effectiveStatus = T_ACTION_STATUS.INVISIBLE;
    } else if (
      (authzOverride === T_ACTION_STATUS.DISABLED ||
        userPolicyStatus === T_ACTION_STATUS.DISABLED) &&
      effectiveStatus === T_ACTION_STATUS.ENABLED
    ) {
      effectiveStatus = T_ACTION_STATUS.DISABLED;
    }

    const text =
      defOverride?.text ||
      this._lookupI18n(normalized, 'text', base.defaultText);
    const hint =
      defOverride?.hint !== undefined
        ? defOverride.hint
        : this._lookupI18n(normalized, 'hint', base.defaultHint);
    const resolvedIcon = defOverride?.icon || base.icon;
    const resolvedShortcut =
      defOverride?.shortcut !== undefined ? defOverride.shortcut : base.shortcut;
    const checked = delegatedResolved && typeof delegatedResolved.checked === 'boolean'
      ? delegatedResolved.checked
      : delegation?.type === 'inline' && typeof delegation.spec.checked === 'boolean'
        ? delegation.spec.checked
        : this._checkedStates.has(normalized)
          ? this._checkedStates.get(normalized)
          : base.checked;
    const paletteItems =
      delegatedResolved?.paletteItems ||
      (Array.isArray(delegation?.spec?.paletteItems) ? delegation.spec.paletteItems : undefined) ||
      base.paletteItems;

    return Object.freeze({
      ...base,
      icon: resolvedIcon,
      shortcut: resolvedShortcut,
      ...(defOverride?.target ? {targetOverride: defOverride.target} : {}),
      ...(paletteItems ? {paletteItems} : {}),
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

    // User-configured target override from Settings -> Actions takes top precedence
    if (resolved.targetOverride) {
      const ov = resolved.targetOverride;
      if (ov.kind === T_ACTION_TARGET_KIND.SERVER) {
        const endpoint = ov.endpoint || `/cdeadmin/api/shell/actions/${resolved.id}/invoke`;
        const method = (ov.method || 'POST').toUpperCase();
        const response = await this._fetch(endpoint, {
          method,
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            ...csrfHeaders(),
          },
          ...(method === 'GET' ? {} : {body: JSON.stringify(args ?? {})}),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          const err = new Error(data?.error || `Server action failed (${response.status})`);
          err.code = data?.code || 'server_action_failed';
          throw err;
        }
        return data;
      }
      if (ov.kind === T_ACTION_TARGET_KIND.CLIENT) {
        if (ov.handlerId && this._callableTargets.has(ov.handlerId)) {
          const entry = this._callableTargets.get(ov.handlerId);
          if (typeof entry.invoke === 'function') {
            return await entry.invoke(args, context);
          }
          if (entry.eventName && typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent(entry.eventName, {
                detail: {
                  actionId: resolved.id,
                  handlerId: entry.id,
                  actionKey: ov.actionKey || entry.actionKey || entry.id,
                  args,
                  context,
                },
              })
            );
            return {ok: true, handlerId: entry.id};
          }
        }
        if (ov.eventName && typeof window !== 'undefined') {
          window.dispatchEvent(
            new CustomEvent(ov.eventName, {
              detail: {
                actionId: resolved.id,
                handlerId: ov.handlerId || '',
                actionKey: ov.actionKey || '',
                args,
                context,
              },
            })
          );
          return {ok: true, eventName: ov.eventName};
        }
      }
    }

    const delegation = this._resolveInstanceDelegation(resolved.id);
    if (delegation?.type === 'action' && delegation.actionId !== resolved.id) {
      return await this.execute(delegation.actionId, args, context);
    }
    if (delegation?.type === 'inline') {
      const fn = delegation.spec?.invoke || delegation.spec?.handler || delegation.spec?.execute;
      if (typeof fn === 'function') {
        return await fn(args, context);
      }
    }

    if (resolved.target.kind === T_ACTION_TARGET_KIND.CLIENT) {
      if (
        resolved.target.handlerId &&
        this._callableTargets.get(resolved.target.handlerId)?.invoke
      ) {
        return await this._callableTargets.get(resolved.target.handlerId).invoke(args, context);
      }
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
  toNotebookBar(tabsSpec = [], renderIcon = () => null, quickAccessSpec = [], options = {}) {
    const state = {};
    const catalog = {};
    const showSectionIcons = options?.showSectionIcons !== false;

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
        ...(typeof itemSpec === 'object' && itemSpec.value !== undefined
          ? {value: itemSpec.value}
          : action.value !== undefined
            ? {value: action.value}
            : {}),
      };
      const rawPaletteItems =
        (typeof itemSpec === 'object' && Array.isArray(itemSpec.items) && itemSpec.items) ||
        action.paletteItems ||
        null;
      const mappedMenuItems = rawPaletteItems
        ? rawPaletteItems.map((entry, idx) => {
          if (entry.type === 'separator') return {type: 'separator'};
          const translatedLabel = this._translateText(
            entry.label || entry.id || `${action.id}.${idx}`
          );
          return {
            id: entry.id || `${action.id}.item.${idx}`,
            label: translatedLabel,
            tooltip: entry.tooltip
              ? this._translateText(entry.tooltip)
              : translatedLabel,
            command: entry.command || action.id,
            checked: entry.checked,
            showLabel: Boolean(entry.showLabel),
            badge: entry.badge,
            disabled: Boolean(entry.disabled),
            icon: entry.icon
              ? (size) => renderIcon({icon: entry.icon, text: translatedLabel}, size)
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
      const rawHint = String(action.hint || '').trim();
      const rawText = String(action.text || '').trim();
      const resolvedTooltip = !rawHint || rawHint === rawText
        ? rawText
        : rawHint.toLowerCase().startsWith(rawText.toLowerCase())
          ? rawHint
          : `${rawText} — ${rawHint}`;
      const control = {
        id: (typeof itemSpec === 'object' && itemSpec.controlId) || action.id,
        command: action.id,
        label: action.text,
        tooltip: resolvedTooltip,
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
      label: this._translateText(tab.label),
      ...(tab.allowEmpty ? {allowEmpty: true} : {}),
      ...(tab.closable !== undefined ? {closable: Boolean(tab.closable)} : {}),
      ...(tab.draggable !== undefined ? {draggable: Boolean(tab.draggable)} : {}),
      ...(tab.renamable !== undefined ? {renamable: Boolean(tab.renamable)} : {}),
      ...(tab.context ? {context: tab.context} : {}),
      ...(tab.selectOnContext ? {selectOnContext: true} : {}),
      groups: (tab.groups || []).map((group, idx) => {
        const groupLabel = this._translateText(group.label ?? '');
        const groupTitle = this._translateText(
          group.title || group.label || group.id || `${tab.id}.g${idx}`
        );
        const rawItems = group.controls || group.actions || [];
        const headerIcon =
          showSectionIcons && group.sectionIcon
            ? renderIcon({id: group.id, icon: group.sectionIcon, text: groupLabel}, 'section')
            : null;
        return {
          id: group.id || `${tab.id}.g${idx}`,
          label: groupLabel,
          title: groupTitle,
          ...(group.sectionId ? {sectionId: group.sectionId} : {}),
          ...(group.sectionIcon ? {sectionIcon: group.sectionIcon} : {}),
          ...(headerIcon ? {headerIcon} : {}),
          priority: Number.isFinite(group.priority) ? group.priority : (100 - idx),
          controls: rawItems.map(mapControl).filter(Boolean),
        };
      }).filter((group) => group.controls.length > 0),
    })).filter((tab) => tab.allowEmpty || tab.groups.length > 0);

    const quickAccess = (quickAccessSpec || []).map(mapControl).filter(Boolean);

    return {
      model: {tabs, quickAccess},
      state,
      catalog,
      onCommand: (commandId, detail = {}) => this.execute(commandId, detail),
    };
  }

  _syncSingleCommand(cmd, sourceRegistry = commandRegistry) {
    if (!cmd || !ACTION_ID_PATTERN.test(String(cmd.id || '').trim())) return;
    if (this.has(cmd.id)) return;
    const appPrefix = cmd.id.split('.')[0] || 'project';
    this.upsert({
      id: cmd.id,
      icon: cmd.iconKey && cmd.iconKey !== 'command.default' ? cmd.iconKey : undefined,
      application: appPrefix,
      defaultText: cmd.label || cmd.id,
      defaultHint: cmd.description || '',
      permission: cmd.permission,
      allowedSecurityGroups: cmd.allowedSecurityGroups,
      deniedSecurityGroups: cmd.deniedSecurityGroups,
      requiresConfirmation: cmd.requiresConfirmation,
      confirmationIntent: cmd.confirmationIntent,
      aiExposure: cmd.aiExposure,
      aiRiskClass: cmd.aiRiskClass,
      status: cmd.defaultVisible === false
        ? T_ACTION_STATUS.INVISIBLE
        : cmd.defaultEnabled === false
          ? T_ACTION_STATUS.DISABLED
          : T_ACTION_STATUS.ENABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: (args, ctx) =>
          sourceRegistry.execute(cmd.id, args, {
            currentUser: this._currentUser || undefined,
            ...ctx,
          }),
      },
    });
  }

  syncFromCommandRegistry(sourceRegistry = commandRegistry) {
    if (!sourceRegistry?.list) return;
    for (const cmd of sourceRegistry.list()) {
      this._syncSingleCommand(cmd, sourceRegistry);
    }
  }

  attachCommandRegistry(sourceRegistry = commandRegistry) {
    if (this._commandRegistryDetach) {
      this._commandRegistryDetach();
      this._commandRegistryDetach = null;
    }
    if (!sourceRegistry) return () => {};
    this.syncFromCommandRegistry(sourceRegistry);
    if (typeof sourceRegistry.onRegister === 'function') {
      this._commandRegistryDetach = sourceRegistry.onRegister((cmd, eventType) => {
        if (eventType === 'register') {
          this._syncSingleCommand(cmd, sourceRegistry);
        }
      });
    }
    return () => {
      if (this._commandRegistryDetach) {
        this._commandRegistryDetach();
        this._commandRegistryDetach = null;
      }
    };
  }
}

/**
 * Seeds all 232 canonical TiB button actions onto a TActionsRegistry so every
 * standard TiB action is inspectable, placeable, and editable (text, icon,
 * hint, status, and code target) from Settings -> Menus & Toolbars -> Actions.
 */
export function seedStandardTiBActions(registry) {
  if (!registry || typeof registry.upsert !== 'function') return;
  for (const act of STANDARD_TIB_ACTIONS) {
    if (registry.has(act.id)) continue;
    registry.upsert({
      id: act.id,
      icon: act.icon,
      application: 'tib',
      defaultText: act.label,
      defaultHint: act.hint,
      toolbarSize: act.slotKind === 'hero' ? 'large' : 'small',
      status: T_ACTION_STATUS.ENABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        handlerId: act.handlerId,
        eventName: 'scratchrobin:tib-command',
        actionKey: act.id,
      },
    });
  }
}

export const t_actions = new TActionsRegistry();
t_actions.attachCommandRegistry(commandRegistry);
seedStandardTiBActions(t_actions);

if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('scratchrobin:language-changed', (ev) => {
    const nextLoc = ev?.detail?.locale || gettext?.getLocale?.() || 'en';
    t_actions.setLocale(nextLoc);
  });
}

export function useLocaleRevision() {
  const [revision, bump] = useReducer((n) => n + 1, 0);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.addEventListener !== 'function') {
      return undefined;
    }
    const handler = () => bump();
    window.addEventListener('scratchrobin:language-changed', handler);
    return () => window.removeEventListener('scratchrobin:language-changed', handler);
  }, []);
  return revision;
}

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
