/////////////////////////////////////////////////////////////
//
// ScratchRobin — Enterprise Principal, Role, Group & Authorization Manager
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {Checkbox, Select, Switch} from '../primitives/Choice';
import {TextField} from '../primitives/Field';
import {Banner, Badge} from '../feedback/Indicators';
import FormReference from '../navigation/FormReference';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {useProjectShell} from '../shell/ProjectShell';
import {T_ACTION_STATUS, T_ACTION_TARGET_KIND} from '../actions/t_actions';
import ObjectPermissionsMatrix from './ObjectPermissionsMatrix';

function resolveCsrfHeaders() {
  if (typeof window === 'undefined') return {};
  const headerName =
    window.pgAdmin?.csrf_token_header ||
    document?.querySelector?.('meta[name="csrf-header"]')?.getAttribute('content') ||
    'X-pgA-CSRFToken';
  const token =
    window.pgAdmin?.csrf_token ||
    document?.querySelector?.('meta[name="csrf-token"]')?.getAttribute('content') ||
    '';
  return token ? {[headerName]: token} : {};
}

const DEFAULT_SYSTEM_PRIVS_BY_ENGINE = Object.freeze({
  postgresql: [
    'SUPERUSER',
    'CREATEDB',
    'CREATEROLE',
    'INHERIT',
    'LOGIN',
    'REPLICATION',
    'BYPASSRLS',
  ],
  cockroachdb: ['ADMIN', 'CREATEDB', 'CREATEROLE', 'CONTROLJOB', 'VIEWACTIVITY'],
  yugabytedb: ['SUPERUSER', 'CREATEDB', 'CREATEROLE', 'INHERIT', 'LOGIN', 'REPLICATION', 'BYPASSRLS'],
  mysql: [
    'SELECT',
    'INSERT',
    'UPDATE',
    'DELETE',
    'CREATE',
    'DROP',
    'RELOAD',
    'PROCESS',
    'REFERENCES',
    'INDEX',
    'ALTER',
    'SHOW DATABASES',
    'CREATE USER',
    'EVENT',
    'TRIGGER',
    'EXECUTE',
    'REPLICATION SLAVE',
    'REPLICATION CLIENT',
    'SYSTEM_USER',
  ],
  mariadb: [
    'SELECT',
    'INSERT',
    'UPDATE',
    'DELETE',
    'CREATE',
    'DROP',
    'RELOAD',
    'PROCESS',
    'REFERENCES',
    'INDEX',
    'ALTER',
    'SHOW DATABASES',
    'CREATE USER',
    'EVENT',
    'TRIGGER',
    'EXECUTE',
    'BINLOG MONITOR',
    'REPLICA MONITOR',
  ],
});

function createBlankDraft(kind = 'user', engine = 'postgresql') {
  const isMysql = ['mysql', 'mariadb', 'tidb', 'dolt'].includes(engine);
  return {
    name: '',
    host: isMysql && kind === 'user' ? '%' : '',
    password: '',
    confirmPassword: '',
    plugin: '',
    active: true,
    locked: false,
    can_login: kind === 'user',
    is_admin: false,
    first_name: '',
    middle_name: '',
    last_name: '',
    valid_until: '',
    connection_limit: -1,
    comment: '',
    tags: [],
    member_of: [],
    members: [],
    system_privileges: kind === 'user' && engine === 'postgresql' ? ['LOGIN', 'INHERIT'] : [],
  };
}

function draftFromPrincipal(item, kind = 'user') {
  if (!item) return createBlankDraft(kind);
  return {
    name: item.name || '',
    host: item.host || '',
    password: '',
    confirmPassword: '',
    plugin: item.plugin || '',
    active: item.active !== false,
    locked: Boolean(item.locked),
    can_login: item.can_login !== undefined ? Boolean(item.can_login) : kind === 'user',
    is_admin: Boolean(item.is_admin),
    first_name: item.first_name || '',
    middle_name: item.middle_name || '',
    last_name: item.last_name || '',
    valid_until: item.valid_until || '',
    connection_limit: item.connection_limit ?? -1,
    comment: item.comment || '',
    tags: Array.isArray(item.tags) ? item.tags.map((t) => ({...t})) : [],
    member_of: Array.isArray(item.member_of) ? item.member_of.map((m) => ({...m})) : [],
    members: Array.isArray(item.members) ? item.members.map((m) => ({...m})) : [],
    system_privileges: Array.isArray(item.system_privileges) ? [...item.system_privileges] : [],
  };
}

function buildFallbackPreviewSql({engine, kind, mode, baseline, draft}) {
  const q = engine === 'mysql' || engine === 'mariadb' ? '`' : '"';
  const qi = (v) => `${q}${String(v || '').replaceAll(q, q + q)}${q}`;
  const isMysql = ['mysql', 'mariadb', 'tidb', 'dolt'].includes(engine);
  const name = draft.name || 'new_principal';
  const ident =
    isMysql && kind === 'user'
      ? `${qi(name)}@${qi(draft.host || '%')}`
      : qi(name);

  const stmts = [];
  if (mode === 'create') {
    if (engine === 'postgresql' || engine === 'cockroachdb' || engine === 'yugabytedb') {
      const opts = [...new Set(draft.system_privileges || [])];
      if (draft.can_login && !opts.includes('LOGIN')) opts.push('LOGIN');
      if (!draft.can_login) opts.push('NOLOGIN');
      if (draft.password) opts.push('PASSWORD \'<redacted>\'');
      if (Number(draft.connection_limit) >= 0) opts.push(`CONNECTION LIMIT ${Number(draft.connection_limit)}`);
      if (draft.valid_until) opts.push(`VALID UNTIL '${draft.valid_until}'`);
      stmts.push(`CREATE ROLE ${ident}${opts.length ? ' WITH ' + opts.join(' ') : ''};`);
    } else if (isMysql) {
      if (kind === 'role') {
        stmts.push(`CREATE ROLE ${qi(name)};`);
      } else {
        const parts = [`CREATE USER ${ident}`];
        if (draft.password) parts.push('IDENTIFIED BY \'<redacted>\'');
        parts.push(draft.locked ? 'ACCOUNT LOCK' : 'ACCOUNT UNLOCK');
        stmts.push(`${parts.join(' ')};`);
      }
    }
  } else {
    if (draft.password) {
      if (isMysql) {
        stmts.push(`ALTER USER ${ident} IDENTIFIED BY '<redacted>';`);
      } else {
        stmts.push(`ALTER ROLE ${ident} WITH PASSWORD '<redacted>';`);
      }
    }
    if (baseline && draft.locked !== baseline.locked && isMysql && kind === 'user') {
      stmts.push(`ALTER USER ${ident} ${draft.locked ? 'ACCOUNT LOCK' : 'ACCOUNT UNLOCK'};`);
    }
  }

  // Role membership diffs
  const prevRoles = new Map(((baseline && baseline.member_of) || []).map((m) => [m.role, m]));
  const nextRoles = new Map((draft.member_of || []).map((m) => [m.role, m]));
  nextRoles.forEach((m, roleName) => {
    if (!prevRoles.has(roleName)) {
      const adminClause = m.admin_option ? ' WITH ADMIN OPTION' : '';
      stmts.push(`GRANT ${qi(roleName)} TO ${ident}${adminClause};`);
    }
  });
  prevRoles.forEach((_m, roleName) => {
    if (!nextRoles.has(roleName)) {
      stmts.push(`REVOKE ${qi(roleName)} FROM ${ident};`);
    }
  });

  return stmts.join('\n');
}

export default function PrincipalSecurityManager({
  instanceId = null,
  sid = null,
  databaseTargetId = null,
  engine: engineProp = 'postgresql',
  scope: scopeProp = 'server',
  initialKind = 'user',
  initialPrincipalId = '',
  endpointLabel = '',
  fetchImpl = null,
}) {
  const shell = useProjectShell();
  const runFetch = useMemo(() => {
    if (fetchImpl) return fetchImpl;
    if (typeof window !== 'undefined' && typeof window.fetch === 'function') {
      return window.fetch.bind(window);
    }
    return typeof fetch === 'function' ? fetch : null;
  }, [fetchImpl]);

  const [engine, setEngine] = useState(String(engineProp || 'postgresql').toLowerCase());
  const scope = scopeProp || 'server';
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [capabilities, setCapabilities] = useState({
    effective_user: '',
    can_manage_users: true,
    can_manage_roles: true,
    can_grant: true,
    users_at_server_scope: true,
    roles_at_server_scope: true,
    visibility_state: 'full',
    visibility_message: '',
  });
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [availableSysPrivs, setAvailableSysPrivs] = useState(
    DEFAULT_SYSTEM_PRIVS_BY_ENGINE[engine] || DEFAULT_SYSTEM_PRIVS_BY_ENGINE.postgresql
  );

  const defaultKind = useMemo(() => {
    if (engine === 'postgresql' || engine === 'cockroachdb' || engine === 'yugabytedb') {
      return 'role';
    }
    return initialKind || 'user';
  }, [engine, initialKind]);

  const [activeKind, setActiveKind] = useState(defaultKind);
  const [selectedId, setSelectedId] = useState(initialPrincipalId || null);
  const [mode, setMode] = useState(initialPrincipalId ? 'alter' : 'create'); // 'create' | 'alter'
  const [activeTab, setActiveTab] = useState('general');
  const [filterText, setFilterText] = useState('');
  const [baseline, setBaseline] = useState(null);
  const [draft, setDraft] = useState(() => createBlankDraft(defaultKind, engine));
  const [previewSql, setPreviewSql] = useState('');
  const [statusMessage, setStatusMessage] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [newMemberInput, setNewMemberInput] = useState('');
  const [inspectObjectKind, setInspectObjectKind] = useState('table');
  const [inspectObjectSchema, setInspectObjectSchema] = useState('');
  const [inspectObjectName, setInspectObjectName] = useState('');

  const tryVerifyServerSession = useCallback(async () => {
    if (typeof window === 'undefined') return false;
    const browser = window.pgAdmin?.Browser;
    const serverNode = browser?.Nodes?.server;
    const tree = browser?.tree;
    if (!tree || typeof serverNode?.callbacks?.verify_cde_endpoint !== 'function') {
      return false;
    }
    let serverItem = null;
    let current = tree.selected?.();
    while (current) {
      const d = tree.itemData?.(current);
      if (d?._type === 'server' && Number(d?._id) === Number(sid)) {
        serverItem = current;
        break;
      }
      current = tree.hasParent?.(current) ? tree.parent(current) : null;
    }
    if (!serverItem) return false;
    return new Promise((resolve) => {
      serverNode.callbacks.verify_cde_endpoint.call(serverNode, {
        item: serverItem,
        databaseTargetId: databaseTargetId || '__retry__',
        onSuccess: () => resolve(true),
      });
    });
  }, [databaseTargetId, sid]);

  const loadPrincipals = useCallback(async (allowAuthRetry = true) => {
    if (!runFetch || !sid) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      const qs = new URLSearchParams({sid: String(sid), scope: String(scope)});
      if (databaseTargetId) qs.set('database_target_id', String(databaseTargetId));
      const resp = await runFetch(`/cdeadmin/api/security/principals?${qs.toString()}`, {
        credentials: 'same-origin',
      });
      if (!resp?.ok) {
        const errJson = await resp?.json?.().catch(() => ({}));
        if (
          allowAuthRetry &&
          (resp?.status === 401 || errJson?.code === 'CREDENTIAL_REQUIRED')
        ) {
          const verified = await tryVerifyServerSession();
          if (verified) {
            return loadPrincipals(false);
          }
        }
        throw new Error(errJson?.error || errJson?.errormsg || gettext('Unable to load security principals.'));
      }
      const data = await resp.json();
      if (data.engine) setEngine(String(data.engine).toLowerCase());
      if (data.capabilities) setCapabilities((prev) => ({...prev, ...data.capabilities}));
      if (Array.isArray(data.available_system_privileges) && data.available_system_privileges.length > 0) {
        setAvailableSysPrivs(data.available_system_privileges);
      } else if (data.engine && DEFAULT_SYSTEM_PRIVS_BY_ENGINE[data.engine]) {
        setAvailableSysPrivs(DEFAULT_SYSTEM_PRIVS_BY_ENGINE[data.engine]);
      }
      const nextUsers = Array.isArray(data.users) ? data.users : [];
      const nextRoles = Array.isArray(data.roles) ? data.roles : [];
      setUsers(nextUsers);
      setRoles(nextRoles);

      const listForKind = activeKind === 'role' ? nextRoles : nextUsers;
      if (listForKind.length > 0) {
        const keep = listForKind.find((item) => item.id === selectedId) || listForKind[0];
        setSelectedId(keep.id);
        setMode('alter');
        const hydrated = draftFromPrincipal(keep, activeKind);
        setBaseline(hydrated);
        setDraft(JSON.parse(JSON.stringify(hydrated)));
      } else if (activeKind === 'user' && nextRoles.length > 0 && nextUsers.length === 0) {
        setActiveKind('role');
        setSelectedId(nextRoles[0].id);
        setMode('alter');
        const hydrated = draftFromPrincipal(nextRoles[0], 'role');
        setBaseline(hydrated);
        setDraft(JSON.parse(JSON.stringify(hydrated)));
      } else {
        setSelectedId(null);
        setMode('create');
        const blank = createBlankDraft(activeKind, data.engine || engine);
        setBaseline(null);
        setDraft(blank);
      }
    } catch (err) {
      setErrorMessage(err?.message || String(err));
      if (!selectedId) {
        setMode('create');
      }
    } finally {
      setLoading(false);
    }
  }, [activeKind, databaseTargetId, engine, runFetch, scope, selectedId, sid, tryVerifyServerSession]);

  useEffect(() => {
    void loadPrincipals();
  }, [sid, databaseTargetId, scope]);

  const canEditCurrentKind =
    activeKind === 'role' ? capabilities.can_manage_roles !== false : capabilities.can_manage_users !== false;

  const startCreate = useCallback(
    (kind) => {
      setActiveKind(kind);
      setSelectedId(null);
      setMode('create');
      const blank = createBlankDraft(kind, engine);
      setBaseline(null);
      setDraft(blank);
      setActiveTab('general');
      setStatusMessage(null);
      setErrorMessage(null);
    },
    [engine]
  );

  const selectPrincipal = useCallback((item, kind) => {
    setActiveKind(kind);
    setSelectedId(item.id);
    setMode('alter');
    const hydrated = draftFromPrincipal(item, kind);
    setBaseline(hydrated);
    setDraft(JSON.parse(JSON.stringify(hydrated)));
    setStatusMessage(null);
    setErrorMessage(null);
  }, []);

  useEffect(() => {
    setPreviewSql(
      buildFallbackPreviewSql({
        engine,
        kind: activeKind,
        mode,
        baseline,
        draft,
      })
    );
  }, [activeKind, baseline, draft, engine, mode]);

  const buildRequestPayload = useCallback(
    (op = mode) => {
      const prevRoles = new Set(((baseline && baseline.member_of) || []).map((m) => m.role));
      const currRoles = new Set((draft.member_of || []).map((m) => m.role));
      const grantRoles = (draft.member_of || []).filter((m) => !prevRoles.has(m.role));
      const revokeRoles = [...prevRoles].filter((r) => !currRoles.has(r));

      const prevMembers = new Set(((baseline && baseline.members) || []).map((m) => m.principal));
      const currMembers = new Set((draft.members || []).map((m) => m.principal));
      const grantMembers = (draft.members || []).filter((m) => !prevMembers.has(m.principal));
      const revokeMembers = [...prevMembers].filter((p) => !currMembers.has(p));

      return {
        sid,
        database_target_id: databaseTargetId || undefined,
        scope,
        principal_kind: activeKind,
        operation: op,
        target:
          op === 'create'
            ? null
            : {
              name: baseline?.name || draft.name,
              host: baseline?.host || draft.host || null,
              plugin: baseline?.plugin || draft.plugin || null,
            },
        draft: {
          ...draft,
          password: draft.password || undefined,
          grant_roles: grantRoles,
          revoke_roles: revokeRoles,
          grant_members: grantMembers,
          revoke_members: revokeMembers,
        },
      };
    },
    [activeKind, baseline, databaseTargetId, draft, mode, scope, sid]
  );

  const handleFetchPlan = useCallback(async () => {
    setActiveTab('sql');
    if (!runFetch || !sid) return;
    try {
      const resp = await runFetch('/cdeadmin/api/security/principal/plan', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', ...resolveCsrfHeaders()},
        body: JSON.stringify(buildRequestPayload(mode)),
      });
      if (resp?.ok) {
        const data = await resp.json();
        if (data?.preview_sql) {
          setPreviewSql(data.preview_sql);
        } else if (Array.isArray(data?.statements) && data.statements.length > 0) {
          setPreviewSql(data.statements.join('\n'));
        }
      }
    } catch {
      // Keep client-side SQL preview fallback
    }
  }, [buildRequestPayload, mode, runFetch, sid]);

  const handleApply = useCallback(async () => {
    if (!canEditCurrentKind) return;
    if (!draft.name.trim()) {
      setErrorMessage(gettext('Principal name is required.'));
      return;
    }
    if (draft.password && draft.confirmPassword && draft.password !== draft.confirmPassword) {
      setErrorMessage(gettext('Password and confirmation do not match.'));
      return;
    }
    setSaving(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      if (runFetch && sid) {
        const resp = await runFetch('/cdeadmin/api/security/principal/apply', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', ...resolveCsrfHeaders()},
          body: JSON.stringify(buildRequestPayload(mode)),
        });
        const data = await resp?.json?.().catch(() => ({}));
        if (!resp?.ok || data?.error || data?.errormsg) {
          throw new Error(data?.error || data?.errormsg || gettext('Failed to apply security changes.'));
        }
        setStatusMessage(
          mode === 'create'
            ? gettext('Created %s "%s".', activeKind, draft.name)
            : gettext('Updated %s "%s".', activeKind, draft.name)
        );
        await loadPrincipals();
      } else {
        setStatusMessage(gettext('Security changes staged.'));
      }
    } catch (err) {
      setErrorMessage(err?.message || String(err));
    } finally {
      setSaving(false);
    }
  }, [activeKind, buildRequestPayload, canEditCurrentKind, draft, engine, loadPrincipals, mode, runFetch, sid]);

  const handleDropPrincipal = useCallback(async () => {
    if (!canEditCurrentKind || mode !== 'alter' || !baseline?.name) return;
    setSaving(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      if (runFetch && sid) {
        const resp = await runFetch('/cdeadmin/api/security/principal/apply', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', ...resolveCsrfHeaders()},
          body: JSON.stringify(buildRequestPayload('drop')),
        });
        const data = await resp?.json?.().catch(() => ({}));
        if (!resp?.ok || data?.error || data?.errormsg) {
          throw new Error(data?.error || data?.errormsg || gettext('Failed to drop principal.'));
        }
        setStatusMessage(gettext('Dropped %s "%s".', activeKind, baseline.name));
        setSelectedId(null);
        await loadPrincipals();
      }
    } catch (err) {
      setErrorMessage(err?.message || String(err));
    } finally {
      setSaving(false);
    }
  }, [activeKind, baseline, buildRequestPayload, canEditCurrentKind, loadPrincipals, mode, runFetch, sid]);

  // Wire unified TiB sections & Security menu into ProjectShell when hosted as a workspace tab
  useEffect(() => {
    if (!shell?.updateInstance || !instanceId) return undefined;
    const safeId = String(instanceId).replace(/[^a-zA-Z0-9_-]/g, '_');
    const mkId = (slug) => `secmgr.${safeId}.${slug}`;
    const actions = [
      {
        id: mkId('new_user'),
        icon: 'tib.security_users',
        application: 'data-navigator',
        defaultText: gettext('New User'),
        defaultHint: gettext('Create a new database user account'),
        status: capabilities.can_manage_users !== false ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => startCreate('user')},
      },
      {
        id: mkId('new_role'),
        icon: 'tib.security_roles',
        application: 'data-navigator',
        defaultText: gettext('New Role'),
        defaultHint: gettext('Create a new SQL role or group'),
        status: capabilities.can_manage_roles !== false ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => startCreate('role')},
      },
      {
        id: mkId('refresh'),
        icon: 'tib.refresh',
        application: 'data-navigator',
        defaultText: gettext('Refresh'),
        defaultHint: gettext('Reload users, roles, memberships, and grants from the engine'),
        status: T_ACTION_STATUS.ENABLED,
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => void loadPrincipals()},
      },
      {
        id: mkId('preview_sql'),
        icon: 'tib.staged_sql',
        application: 'data-navigator',
        defaultText: gettext('Preview SQL'),
        defaultHint: gettext('Inspect generated native DCL statements'),
        status: T_ACTION_STATUS.ENABLED,
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => void handleFetchPlan()},
      },
      {
        id: mkId('apply'),
        icon: 'tib.commit',
        application: 'data-navigator',
        defaultText: gettext('Apply Changes'),
        defaultHint: gettext('Execute pending user, role, and membership changes'),
        status: canEditCurrentKind ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => void handleApply()},
      },
      {
        id: mkId('drop'),
        icon: 'tib.record_delete',
        application: 'data-navigator',
        defaultText: gettext('Drop Principal'),
        defaultHint: gettext('Drop the selected user or role'),
        status: canEditCurrentKind && mode === 'alter' ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
        focusScoped: true,
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => void handleDropPrincipal()},
      },
    ];
    shell.updateInstance(instanceId, {
      actions,
      ribbonGroups: [
        {
          id: 'security-principal-actions',
          label: gettext('Security & Principals'),
          headerIcon: 'tib.section_security',
          controls: actions.map((a) => a.id),
        },
      ],
    });
    return undefined;
  }, [
    canEditCurrentKind,
    capabilities.can_manage_roles,
    capabilities.can_manage_users,
    handleApply,
    handleDropPrincipal,
    handleFetchPlan,
    instanceId,
    loadPrincipals,
    mode,
    shell,
    startCreate,
  ]);

  const isUnifiedRoleEngine = ['postgresql', 'cockroachdb', 'yugabytedb'].includes(engine);
  const isMysqlFamily = ['mysql', 'mariadb', 'tidb', 'dolt'].includes(engine);
  const showUsersTab = !isUnifiedRoleEngine;
  const showRolesTab = true;

  const rosterItems = activeKind === 'role' || isUnifiedRoleEngine ? roles : users;
  const filteredRoster = rosterItems.filter((item) => {
    const q = filterText.trim().toLowerCase();
    if (!q) return true;
    return `${item.name} ${item.host || ''} ${item.plugin || ''}`.toLowerCase().includes(q);
  });

  const allRoleNames = useMemo(
    () => [...new Set(roles.map((r) => r.name).filter(Boolean))],
    [roles]
  );

  const toggleMemberOf = (roleName) => {
    if (!canEditCurrentKind) return;
    setDraft((prev) => {
      const exists = (prev.member_of || []).some((m) => m.role === roleName);
      if (exists) {
        return {...prev, member_of: prev.member_of.filter((m) => m.role !== roleName)};
      }
      return {
        ...prev,
        member_of: [
          ...(prev.member_of || []),
          {role: roleName, admin_option: false, default_role: true, inherit_option: true, set_option: true},
        ],
      };
    });
  };

  const toggleMemberOfOption = (roleName, field) => {
    if (!canEditCurrentKind) return;
    setDraft((prev) => ({
      ...prev,
      member_of: (prev.member_of || []).map((m) =>
        m.role === roleName ? {...m, [field]: !m[field]} : m
      ),
    }));
  };

  const toggleSysPriv = (priv) => {
    if (!canEditCurrentKind) return;
    setDraft((prev) => {
      const has = (prev.system_privileges || []).includes(priv);
      return {
        ...prev,
        system_privileges: has
          ? prev.system_privileges.filter((p) => p !== priv)
          : [...(prev.system_privileges || []), priv],
      };
    });
  };

  return (
    <Box
      data-cdeadmin-qa-key="principal-security-manager"
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--sr-surface-canvas, var(--sr-surface-subtle))',
      }}
    >
      {/* Top Context Banner */}
      <div
        style={{
          padding: '10px 16px',
          borderBottom: '1px solid var(--sr-border-default)',
          background: 'var(--sr-surface-default, var(--sr-island-bg))',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div style={{display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}}>
          <span style={{fontWeight: 700, fontSize: '0.94rem'}}>
            {scope === 'server'
              ? gettext('Server Security & User Management')
              : gettext('Database Roles & Authorization')}
          </span>
          {endpointLabel && <Badge tone="accent" label={endpointLabel} />}
          <Badge tone="neutral" label={engine.toUpperCase()} />
          {capabilities.effective_user && (
            <Badge
              tone={canEditCurrentKind ? 'success' : 'neutral'}
              label={gettext('Session: %s', capabilities.effective_user)}
            />
          )}
          <FormReference formKey="security-principal-manager" />
        </div>

        <div style={{display: 'flex', gap: 6, flexWrap: 'wrap'}}>
          {showUsersTab && capabilities.can_manage_users !== false && (
            <Button
              size="small"
              intent="secondary"
              data-cdeadmin-qa-key="secmgr-new-user"
              onClick={() => startCreate('user')}
            >
              {gettext('+ New User')}
            </Button>
          )}
          {showRolesTab && capabilities.can_manage_roles !== false && (
            <Button
              size="small"
              intent="secondary"
              data-cdeadmin-qa-key="secmgr-new-role"
              onClick={() => startCreate('role')}
            >
              {isUnifiedRoleEngine ? gettext('+ New Login / Group Role') : gettext('+ New Role')}
            </Button>
          )}
          <Button
            size="small"
            intent="neutral"
            disabled={loading || saving}
            onClick={() => void loadPrincipals()}
          >
            {loading ? gettext('Refreshing…') : gettext('Refresh')}
          </Button>
        </div>
      </div>

      {capabilities.visibility_state && capabilities.visibility_state !== 'full' && (
        <div style={{padding: '8px 16px 0'}}>
          <Banner status="warning">
            {capabilities.visibility_message ||
              gettext(
                'Connected account has limited security catalog privileges. Only accounts and grants visible to the current session are displayed.'
              )}
          </Banner>
        </div>
      )}
      {errorMessage && (
        <div style={{padding: '8px 16px 0'}}>
          <Banner status="error">{errorMessage}</Banner>
        </div>
      )}
      {statusMessage && (
        <div style={{padding: '8px 16px 0'}}>
          <Banner status="success">{statusMessage}</Banner>
        </div>
      )}

      {/* Master-Detail Split */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: 'grid',
          gridTemplateColumns: 'minmax(240px, 300px) minmax(0, 1fr)',
          gap: 12,
          padding: 12,
        }}
      >
        {/* Left Roster */}
        <div
          style={{
            border: '1px solid var(--sr-border-default)',
            borderRadius: 10,
            background: 'var(--sr-surface-default, var(--sr-island-bg))',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            overflow: 'hidden',
          }}
        >
          {showUsersTab && showRolesTab && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                borderBottom: '1px solid var(--sr-border-default)',
              }}
            >
              <button
                type="button"
                onClick={() => {
                  setActiveKind('user');
                  if (users[0]) selectPrincipal(users[0], 'user');
                }}
                style={{
                  padding: '8px 10px',
                  border: 'none',
                  borderBottom:
                    activeKind === 'user'
                      ? '2px solid var(--sr-accent, #2563eb)'
                      : '2px solid transparent',
                  background: 'transparent',
                  fontWeight: activeKind === 'user' ? 700 : 500,
                  cursor: 'pointer',
                  color: 'var(--sr-text-primary)',
                }}
              >
                {gettext('Users (%s)', users.length)}
              </button>
              <button
                type="button"
                onClick={() => {
                  setActiveKind('role');
                  if (roles[0]) selectPrincipal(roles[0], 'role');
                }}
                style={{
                  padding: '8px 10px',
                  border: 'none',
                  borderBottom:
                    activeKind === 'role'
                      ? '2px solid var(--sr-accent, #2563eb)'
                      : '2px solid transparent',
                  background: 'transparent',
                  fontWeight: activeKind === 'role' ? 700 : 500,
                  cursor: 'pointer',
                  color: 'var(--sr-text-primary)',
                }}
              >
                {gettext('Roles (%s)', roles.length)}
              </button>
            </div>
          )}

          <div style={{padding: 8, borderBottom: '1px solid var(--sr-border-default)'}}>
            <TextField
              placeholder={gettext('Search principals…')}
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
            />
          </div>

          <ScratchScrollArea orientation="vertical" style={{flex: 1, minHeight: 0}}>
            <div style={{display: 'flex', flexDirection: 'column'}}>
              {filteredRoster.length === 0 ? (
                <div style={{padding: 16, fontSize: '0.8rem', color: 'var(--sr-text-secondary)'}}>
                  {loading ? gettext('Loading principals…') : gettext('No principals found.')}
                </div>
              ) : (
                filteredRoster.map((item) => {
                  const isSel = mode === 'alter' && selectedId === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => selectPrincipal(item, isUnifiedRoleEngine ? 'role' : activeKind)}
                      style={{
                        textAlign: 'left',
                        padding: '9px 12px',
                        border: 'none',
                        borderBottom: '1px solid var(--sr-border-subtle, var(--sr-border-default))',
                        background: isSel
                          ? 'color-mix(in srgb, var(--sr-accent, #2563eb) 14%, transparent)'
                          : 'transparent',
                        cursor: 'pointer',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: 8,
                        color: 'var(--sr-text-primary)',
                      }}
                    >
                      <div style={{minWidth: 0}}>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: '0.82rem',
                            fontFamily: 'var(--sr-font-mono, monospace)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {item.host ? `${item.name}@${item.host}` : item.name}
                        </div>
                        <div style={{fontSize: '0.72rem', color: 'var(--sr-text-secondary)'}}>
                          {item.plugin || (item.can_login ? gettext('Login') : gettext('Role / Group'))}
                        </div>
                      </div>
                      <div style={{display: 'flex', gap: 4}}>
                        {item.is_admin && <Badge tone="accent" label={gettext('Admin')} />}
                        {item.locked && <Badge tone="danger" label={gettext('Locked')} />}
                        {item.active === false && <Badge tone="neutral" label={gettext('Inactive')} />}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </ScratchScrollArea>
        </div>

        {/* Right 5-Tab Detail Editor */}
        <div
          style={{
            border: '1px solid var(--sr-border-default)',
            borderRadius: 10,
            background: 'var(--sr-surface-default, var(--sr-island-bg))',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            overflow: 'hidden',
          }}
        >
          {/* Editor Header & Tabs */}
          <div
            style={{
              padding: '10px 16px 0',
              borderBottom: '1px solid var(--sr-border-default)',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8}}>
              <div style={{fontWeight: 700, fontSize: '0.9rem'}}>
                {mode === 'create'
                  ? gettext('Create New %s', activeKind === 'role' ? gettext('Role') : gettext('User'))
                  : gettext('Inspect & Edit: %s', draft.host ? `${draft.name}@${draft.host}` : draft.name)}
              </div>
              <div style={{display: 'flex', gap: 6}}>
                {mode === 'alter' && canEditCurrentKind && (
                  <Button
                    size="small"
                    intent="danger"
                    disabled={saving}
                    onClick={() => void handleDropPrincipal()}
                  >
                    {gettext('Drop %s', activeKind === 'role' ? gettext('Role') : gettext('User'))}
                  </Button>
                )}
                <Button size="small" intent="neutral" onClick={() => void handleFetchPlan()}>
                  {gettext('Preview SQL')}
                </Button>
                {canEditCurrentKind && (
                  <Button
                    size="small"
                    intent="primary"
                    data-cdeadmin-qa-key="secmgr-apply"
                    disabled={saving}
                    onClick={() => void handleApply()}
                  >
                    {saving
                      ? gettext('Applying…')
                      : mode === 'create'
                        ? gettext('Create %s', activeKind === 'role' ? gettext('Role') : gettext('User'))
                        : gettext('Apply Changes')}
                  </Button>
                )}
              </div>
            </div>

            <div role="tablist" style={{display: 'flex', gap: 14, flexWrap: 'wrap'}}>
              {[
                {id: 'general', label: gettext('General & Authentication')},
                {id: 'membership', label: gettext('Role / Group Membership')},
                {id: 'system_privs', label: gettext('System & Special Permissions')},
                {id: 'object_grants', label: gettext('Object Grants')},
                {id: 'sql', label: gettext('SQL Preview')},
              ].map((tab) => (
                <button
                  key={tab.id}
                  role="tab"
                  type="button"
                  aria-selected={activeTab === tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    padding: '6px 4px 8px',
                    border: 'none',
                    borderBottom:
                      activeTab === tab.id
                        ? '2px solid var(--sr-accent, #2563eb)'
                        : '2px solid transparent',
                    background: 'transparent',
                    fontWeight: activeTab === tab.id ? 700 : 500,
                    fontSize: '0.81rem',
                    cursor: 'pointer',
                    color: 'var(--sr-text-primary)',
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Tab Body */}
          <ScratchScrollArea orientation="vertical" style={{flex: 1, minHeight: 0}}>
            <div style={{padding: 16, display: 'flex', flexDirection: 'column', gap: 14}}>
              {activeTab === 'general' && (
                <>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                      gap: 12,
                    }}
                  >
                    <TextField
                      label={gettext('Principal Name')}
                      value={draft.name}
                      disabled={mode === 'alter' || !canEditCurrentKind}
                      onChange={(e) => setDraft((p) => ({...p, name: e.target.value}))}
                    />
                    {isMysqlFamily && activeKind === 'user' && (
                      <TextField
                        label={gettext('Host Pattern')}
                        value={draft.host}
                        disabled={mode === 'alter' || !canEditCurrentKind}
                        onChange={(e) => setDraft((p) => ({...p, host: e.target.value}))}
                      />
                    )}
                    {(activeKind === 'user' || isUnifiedRoleEngine) && (
                      <>
                        <TextField
                          label={
                            mode === 'create'
                              ? gettext('Password')
                              : gettext('New Password (leave blank to keep current)')
                          }
                          type="password"
                          value={draft.password}
                          disabled={!canEditCurrentKind}
                          onChange={(e) => setDraft((p) => ({...p, password: e.target.value}))}
                        />
                        <TextField
                          label={gettext('Confirm Password')}
                          type="password"
                          value={draft.confirmPassword}
                          disabled={!canEditCurrentKind}
                          onChange={(e) => setDraft((p) => ({...p, confirmPassword: e.target.value}))}
                        />
                      </>
                    )}
                    {isMysqlFamily && activeKind === 'user' && (
                      <TextField
                        label={gettext('Authentication Plugin')}
                        value={draft.plugin}
                        placeholder="caching_sha2_password"
                        disabled={!canEditCurrentKind}
                        onChange={(e) => setDraft((p) => ({...p, plugin: e.target.value}))}
                      />
                    )}
                    {isUnifiedRoleEngine && (
                      <>
                        <TextField
                          label={gettext('Connection Limit (-1 = unlimited)')}
                          type="number"
                          value={String(draft.connection_limit ?? -1)}
                          disabled={!canEditCurrentKind}
                          onChange={(e) =>
                            setDraft((p) => ({...p, connection_limit: Number(e.target.value)}))
                          }
                        />
                        <TextField
                          label={gettext('Account Valid Until (ISO Timestamp)')}
                          placeholder="2027-12-31T23:59:59Z"
                          value={draft.valid_until}
                          disabled={!canEditCurrentKind}
                          onChange={(e) => setDraft((p) => ({...p, valid_until: e.target.value}))}
                        />
                      </>
                    )}
                  </div>


                  <div style={{display: 'flex', gap: 20, flexWrap: 'wrap'}}>
                    {isUnifiedRoleEngine && (
                      <Switch
                        label={gettext('Can Login (LOGIN)')}
                        checked={Boolean(draft.can_login)}
                        disabled={!canEditCurrentKind}
                        onChange={(val) => setDraft((p) => ({...p, can_login: Boolean(val)}))}
                      />
                    )}
                    {isMysqlFamily && activeKind === 'user' && (
                      <Switch
                        label={gettext('Account Locked')}
                        checked={Boolean(draft.locked)}
                        disabled={!canEditCurrentKind}
                        onChange={(val) => setDraft((p) => ({...p, locked: Boolean(val)}))}
                      />
                    )}
                  </div>

                  <TextField
                    label={gettext('Comment / Description')}
                    value={draft.comment}
                    disabled={!canEditCurrentKind}
                    onChange={(e) => setDraft((p) => ({...p, comment: e.target.value}))}
                  />

                </>
              )}

              {activeTab === 'membership' && (
                <div style={{display: 'flex', flexDirection: 'column', gap: 14}}>
                  <div style={{fontSize: '0.82rem', color: 'var(--sr-text-secondary)'}}>
                    {gettext(
                      'View and modify role/group memberships assigned to this principal, including ADMIN, INHERIT, and DEFAULT ROLE options.'
                    )}
                  </div>

                  {/* Member Of Table */}
                  <div
                    style={{
                      border: '1px solid var(--sr-border-default)',
                      borderRadius: 8,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        padding: '8px 12px',
                        background: 'var(--sr-surface-subtle)',
                        fontWeight: 600,
                        fontSize: '0.82rem',
                        borderBottom: '1px solid var(--sr-border-default)',
                      }}
                    >
                      {gettext('Member Of (Assigned Roles / Groups)')}
                    </div>
                    <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem'}}>
                      <thead>
                        <tr style={{borderBottom: '1px solid var(--sr-border-default)', textAlign: 'left'}}>
                          <th style={{padding: '7px 10px'}}>{gettext('Granted')}</th>
                          <th style={{padding: '7px 10px'}}>{gettext('Role / Group')}</th>
                          <th style={{padding: '7px 10px', textAlign: 'center'}}>{gettext('Admin Option')}</th>
                          {isUnifiedRoleEngine && (
                            <>
                              <th style={{padding: '7px 10px', textAlign: 'center'}}>{gettext('Inherit')}</th>
                              <th style={{padding: '7px 10px', textAlign: 'center'}}>{gettext('Set')}</th>
                            </>
                          )}
                          {isMysqlFamily && (
                            <th style={{padding: '7px 10px', textAlign: 'center'}}>{gettext('Default Role')}</th>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {allRoleNames.filter((rn) => rn !== draft.name).length === 0 ? (
                          <tr>
                            <td colSpan={6} style={{padding: 14, color: 'var(--sr-text-secondary)'}}>
                              {gettext('No roles discovered in this scope yet.')}
                            </td>
                          </tr>
                        ) : (
                          allRoleNames
                            .filter((rn) => rn !== draft.name)
                            .map((roleName) => {
                              const entry = (draft.member_of || []).find((m) => m.role === roleName);
                              const granted = Boolean(entry);
                              return (
                                <tr
                                  key={roleName}
                                  style={{
                                    borderBottom:
                                      '1px solid var(--sr-border-subtle, var(--sr-border-default))',
                                  }}
                                >
                                  <td style={{padding: '7px 10px'}}>
                                    <Checkbox
                                      checked={granted}
                                      disabled={!canEditCurrentKind}
                                      onChange={() => toggleMemberOf(roleName)}
                                    />
                                  </td>
                                  <td
                                    style={{
                                      padding: '7px 10px',
                                      fontWeight: 600,
                                      fontFamily: 'var(--sr-font-mono, monospace)',
                                    }}
                                  >
                                    {roleName}
                                  </td>
                                  <td style={{padding: '7px 10px', textAlign: 'center'}}>
                                    <Checkbox
                                      checked={Boolean(entry?.admin_option)}
                                      disabled={!canEditCurrentKind || !granted}
                                      onChange={() => toggleMemberOfOption(roleName, 'admin_option')}
                                    />
                                  </td>
                                  {isUnifiedRoleEngine && (
                                    <>
                                      <td style={{padding: '7px 10px', textAlign: 'center'}}>
                                        <Checkbox
                                          checked={entry?.inherit_option !== false && granted}
                                          disabled={!canEditCurrentKind || !granted}
                                          onChange={() => toggleMemberOfOption(roleName, 'inherit_option')}
                                        />
                                      </td>
                                      <td style={{padding: '7px 10px', textAlign: 'center'}}>
                                        <Checkbox
                                          checked={entry?.set_option !== false && granted}
                                          disabled={!canEditCurrentKind || !granted}
                                          onChange={() => toggleMemberOfOption(roleName, 'set_option')}
                                        />
                                      </td>
                                    </>
                                  )}
                                  {isMysqlFamily && (
                                    <td style={{padding: '7px 10px', textAlign: 'center'}}>
                                      <Checkbox
                                        checked={Boolean(entry?.default_role)}
                                        disabled={!canEditCurrentKind || !granted}
                                        onChange={() => toggleMemberOfOption(roleName, 'default_role')}
                                      />
                                    </td>
                                  )}
                                </tr>
                              );
                            })
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* Direct Members (when inspecting/editing a Role/Group) */}
                  {(activeKind === 'role' || isUnifiedRoleEngine) && (
                    <div
                      style={{
                        border: '1px solid var(--sr-border-default)',
                        borderRadius: 8,
                        padding: 12,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 8,
                      }}
                    >
                      <div style={{fontWeight: 600, fontSize: '0.82rem'}}>
                        {gettext('Principals Granted This Role (%s)', (draft.members || []).length)}
                      </div>
                      <div style={{display: 'flex', gap: 6, flexWrap: 'wrap'}}>
                        {(draft.members || []).length === 0 ? (
                          <span style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
                            {gettext('No members currently assigned to this role.')}
                          </span>
                        ) : (
                          (draft.members || []).map((m) => (
                            <div
                              key={m.principal}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 6,
                                padding: '4px 8px',
                                borderRadius: 6,
                                border: '1px solid var(--sr-border-default)',
                                background: 'var(--sr-surface-subtle)',
                                fontSize: '0.78rem',
                              }}
                            >
                              <span style={{fontFamily: 'var(--sr-font-mono, monospace)', fontWeight: 600}}>
                                {m.principal}
                              </span>
                              {canEditCurrentKind && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    setDraft((p) => ({
                                      ...p,
                                      members: (p.members || []).filter((x) => x.principal !== m.principal),
                                    }))
                                  }
                                  style={{
                                    border: 'none',
                                    background: 'transparent',
                                    cursor: 'pointer',
                                    color: 'var(--sr-text-secondary)',
                                  }}
                                  aria-label={gettext('Revoke %s', m.principal)}
                                >
                                  ×
                                </button>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                      {canEditCurrentKind && (
                        <div style={{display: 'flex', gap: 8, alignItems: 'flex-end'}}>
                          <TextField
                            label={gettext('Add Member Principal')}
                            placeholder={gettext('User or role name…')}
                            value={newMemberInput}
                            onChange={(e) => setNewMemberInput(e.target.value)}
                          />
                          <Button
                            size="small"
                            intent="secondary"
                            disabled={!newMemberInput.trim()}
                            onClick={() => {
                              const name = newMemberInput.trim();
                              setDraft((p) => ({
                                ...p,
                                members: [...(p.members || []), {principal: name, admin_option: false}],
                              }));
                              setNewMemberInput('');
                            }}
                          >
                            {gettext('+ Grant Role To Member')}
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'system_privs' && (
                <div style={{display: 'flex', flexDirection: 'column', gap: 10}}>
                  <div style={{fontSize: '0.82rem', color: 'var(--sr-text-secondary)'}}>
                    {gettext(
                      'Engine-native cluster, server, DDL, and special administrative privileges held by this principal.'
                    )}
                  </div>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                      gap: 8,
                    }}
                  >
                    {availableSysPrivs.map((priv) => {
                      const checked = (draft.system_privileges || []).includes(priv);
                      return (
                        <div
                          key={priv}
                          style={{
                            padding: '8px 10px',
                            borderRadius: 8,
                            border: '1px solid var(--sr-border-default)',
                            background: checked
                              ? 'color-mix(in srgb, var(--sr-accent, #2563eb) 10%, var(--sr-surface-subtle))'
                              : 'var(--sr-surface-subtle)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                          }}
                        >
                          <Checkbox
                            label={priv}
                            checked={checked}
                            disabled={!canEditCurrentKind}
                            onChange={() => toggleSysPriv(priv)}
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {activeTab === 'object_grants' && (
                <div style={{display: 'flex', flexDirection: 'column', gap: 12}}>
                  <div
                    style={{
                      display: 'flex',
                      gap: 8,
                      alignItems: 'flex-end',
                      flexWrap: 'wrap',
                      padding: 10,
                      borderRadius: 8,
                      background: 'var(--sr-surface-subtle)',
                      border: '1px solid var(--sr-border-default)',
                    }}
                  >
                    <div style={{width: 140}}>
                      <Select
                        label={gettext('Object Type')}
                        value={inspectObjectKind}
                        options={[
                          {value: 'table', label: gettext('Table')},
                          {value: 'view', label: gettext('View')},
                          {value: 'procedure', label: gettext('Procedure')},
                          {value: 'function', label: gettext('Function')},
                          {value: 'sequence', label: gettext('Sequence')},
                          {value: 'schema', label: gettext('Schema')},
                          {value: 'database', label: gettext('Database')},
                        ]}
                        onChange={(v) => setInspectObjectKind(v)}
                      />
                    </div>
                    <div style={{width: 150}}>
                      <TextField
                        label={gettext('Schema (optional)')}
                        placeholder="public"
                        value={inspectObjectSchema}
                        onChange={(e) => setInspectObjectSchema(e.target.value)}
                      />
                    </div>
                    <div style={{flex: '1 1 180px'}}>
                      <TextField
                        label={gettext('Object Name')}
                        placeholder={gettext('Enter table, view, or routine name to inspect/grant…')}
                        value={inspectObjectName}
                        onChange={(e) => setInspectObjectName(e.target.value)}
                      />
                    </div>
                  </div>
                  {inspectObjectName.trim() ? (
                    <ObjectPermissionsMatrix
                      sid={sid}
                      databaseTargetId={databaseTargetId}
                      engine={engine}
                      objectKind={inspectObjectKind}
                      schema={inspectObjectSchema.trim()}
                      objectName={inspectObjectName.trim()}
                      fetchImpl={runFetch}
                      compact
                    />
                  ) : (
                    <div style={{fontSize: '0.8rem', color: 'var(--sr-text-secondary)', padding: 8}}>
                      {gettext(
                        'Enter an object name above (or select any Table, View, Procedure, Function, or Sequence in the Data Navigator and click the Permissions button in the Tabbed-Icon-Bar) to inspect and edit its Principal × Privilege matrix.'
                      )}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'sql' && (
                <div style={{display: 'flex', flexDirection: 'column', gap: 8}}>
                  <div style={{fontSize: '0.8rem', color: 'var(--sr-text-secondary)'}}>
                    {gettext('Native SQL statements generated for the current changes (passwords redacted in preview):')}
                  </div>
                  <pre
                    data-cdeadmin-qa-key="secmgr-sql-preview"
                    style={{
                      margin: 0,
                      padding: 12,
                      borderRadius: 8,
                      border: '1px solid var(--sr-border-default)',
                      background: 'var(--sr-surface-subtle)',
                      fontFamily: 'var(--sr-font-mono, monospace)',
                      fontSize: '0.8rem',
                      whiteSpace: 'pre-wrap',
                      minHeight: 100,
                    }}
                  >
                    {previewSql || gettext('-- No pending changes --')}
                  </pre>
                </div>
              )}
            </div>
          </ScratchScrollArea>
        </div>
      </div>
    </Box>
  );
}

PrincipalSecurityManager.propTypes = {
  instanceId: PropTypes.string,
  sid: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  databaseTargetId: PropTypes.string,
  engine: PropTypes.string,
  scope: PropTypes.string,
  initialKind: PropTypes.string,
  initialPrincipalId: PropTypes.string,
  endpointLabel: PropTypes.string,
  fetchImpl: PropTypes.func,
};
