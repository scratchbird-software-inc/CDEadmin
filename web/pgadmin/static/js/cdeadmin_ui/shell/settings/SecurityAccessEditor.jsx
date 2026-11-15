/////////////////////////////////////////////////////////////
//
// ScratchRobin — Security Configuration Area (Application Availability, Users & Groups)
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Checkbox, Select, Switch} from '../../primitives/Choice';
import {Banner} from '../../feedback/Indicators';
import {Icon} from '../../icons';
import {ScratchBranchedTree} from '../../navigation/ScratchBranchedTree';

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

const DEFAULT_PERMISSION_CATALOG = Object.freeze([
  {id: 'object_register_server', category: 'Catalog & Servers', label: 'Register & Manage Servers'},
  {id: 'tools_query_tool', category: 'Query & Execution', label: 'Execute SQL Queries'},
  {id: 'tools_psql_tool', category: 'Query & Execution', label: 'Open Native Command Line'},
  {id: 'tools_schema_diff', category: 'Schema & Migration', label: 'Run Schema Comparison'},
  {id: 'schema_compare.apply', category: 'Schema & Migration', label: 'Approve & Apply Migration Plans'},
  {id: 'project.asset.edit', category: 'Designers & DDN', label: 'Edit Project & DDN Designs'},
  {id: 'design.version.accept', category: 'Designers & DDN', label: 'Accept DDN Design Versions (Gate)'},
  {id: 'bi.outward.publish', category: 'BI & Dashboards', label: 'Enable BI Alerts, Embeds & Remote Server'},
  {id: 'ai.propose', category: 'AI Assistant', label: 'Draft Queries & BI Questions with AI'},
]);

function buildFallbackSecurityState(applications = []) {
  const allAppIds = (applications.length
    ? applications
    : [
      {id: 'data-navigator', label: 'Data Navigator', iconKey: 'tool.data-explorer', authorized: true},
      {id: 'sql-editor', label: 'SQL Editor', iconKey: 'tool.query', authorized: true},
      {id: 'erd-designer', label: 'ERD & Data Modelling', iconKey: 'tool.erd', authorized: true},
      {id: 'cube-designer', label: 'Cube Designer', iconKey: 'object.cube', authorized: true},
      {id: 'bi-designer', label: 'BI Dashboards & Questions', iconKey: 'tool.dashboard', authorized: true},
      {id: 'screen-mesh-designer', label: 'Screen Mesh Designer', iconKey: 'action.customize', authorized: true},
      {id: 'schema-compare', label: 'Schema Comparison', iconKey: 'tool.schema-diff', authorized: true},
      {id: 'project-explorer', label: 'Project Explorer', iconKey: 'object.folder', authorized: true},
    ]
  ).map((a) => ({
    id: a.id,
    label: a.label || a.id,
    icon: a.iconKey || a.icon || 'command.default',
    system_enabled: a.authorized !== false || a.id === 'data-navigator',
    core: a.id === 'data-navigator',
  }));

  return {
    system_disabled_applications: allAppIds
      .filter((a) => !a.system_enabled && !a.core)
      .map((a) => a.id),
    applications: allAppIds,
    groups: [
      {
        id: 'administrators',
        name: 'Administrators',
        description: 'Full access to all applications, servers, and security settings.',
        builtin: true,
        enabled_applications: allAppIds.map((a) => a.id),
        disabled_applications: [],
        permissions: DEFAULT_PERMISSION_CATALOG.map((p) => p.id),
      },
      {
        id: 'analysts',
        name: 'Data Analysts',
        description: 'Query, BI, Cube, and read-only catalog exploration.',
        builtin: false,
        enabled_applications: ['data-navigator', 'sql-editor', 'cube-designer', 'bi-designer'],
        disabled_applications: ['schema-compare'],
        permissions: ['tools_query_tool', 'project.asset.edit', 'ai.propose'],
      },
    ],
    users: [
      {
        id: 'desktop',
        username: 'desktop',
        email: 'desktop@localhost',
        active: true,
        locked: false,
        auth_source: 'internal',
        groups: ['administrators'],
        enabled_applications: [],
        disabled_applications: [],
      },
    ],
    permission_catalog: [...DEFAULT_PERMISSION_CATALOG],
  };
}

export function SecurityAccessEditor({
  subView = 'apps',
  hideTabs = false,
  applications = [],
  fetchImpl = null,
  onPermittedAppsChange,
  onRefreshAuthorization,
  onNavigateSubView,
}) {
  const runFetch = fetchImpl || (typeof fetch === 'function' ? fetch : null);
  const [activeSubView, setActiveSubView] = useState(subView);
  const [secState, setSecState] = useState(() => buildFallbackSecurityState(applications));
  const [feedback, setFeedback] = useState('');

  useEffect(() => {
    setActiveSubView(subView);
  }, [subView]);

  const switchSubView = useCallback(
    (nextView) => {
      setActiveSubView(nextView);
      onNavigateSubView?.(nextView);
    },
    [onNavigateSubView]
  );

  // Group editor state
  const [selectedGroupId, setSelectedGroupId] = useState('administrators');
  const [newGroupName, setNewGroupName] = useState('');
  const [permTreeExpanded, setPermTreeExpanded] = useState([
    'cat:Catalog & Servers',
    'cat:Query & Execution',
    'cat:Schema & Migration',
    'cat:Designers & DDN',
    'cat:BI & Dashboards',
    'cat:AI Assistant',
  ]);

  // User editor state
  const [selectedUsername, setSelectedUsername] = useState('desktop');
  const [draftUser, setDraftUser] = useState({
    username: 'desktop',
    email: 'desktop@localhost',
    password: '',
    active: true,
    locked: false,
    groups: ['administrators'],
    enabled_applications: [],
    disabled_applications: [],
  });

  const permissionTreeNodes = useMemo(() => {
    const byCat = new Map();
    (secState.permission_catalog || DEFAULT_PERMISSION_CATALOG).forEach((p) => {
      if (!byCat.has(p.category)) byCat.set(p.category, []);
      byCat.get(p.category).push({id: p.id, label: p.label});
    });
    return [...byCat.entries()].map(([cat, children]) => ({
      id: `cat:${cat}`,
      label: cat,
      children,
    }));
  }, [secState.permission_catalog]);

  useEffect(() => {
    if (!runFetch) return undefined;
    let active = true;
    Promise.resolve(runFetch('/cdeadmin/api/shell/security', {credentials: 'same-origin'}))
      .then((res) => (res?.ok ? res.json() : null))
      .then((data) => {
        if (!active || !data?.applications) return;
        setSecState(data);
        if (data.users?.length) {
          const first = data.users[0];
          setSelectedUsername(first.username);
          setDraftUser({
            username: first.username,
            email: first.email || '',
            password: '',
            active: first.active !== false,
            locked: Boolean(first.locked),
            groups: first.groups || ['administrators'],
            enabled_applications: first.enabled_applications || [],
            disabled_applications: first.disabled_applications || [],
          });
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [runFetch]);

  const handleToggleSystemApp = useCallback(
    async (appId, enabled) => {
      if (appId === 'data-navigator') return;
      const disabledSet = new Set(secState.system_disabled_applications || []);
      if (enabled) {
        disabledSet.delete(appId);
      } else {
        disabledSet.add(appId);
      }
      const nextDisabled = [...disabledSet];
      const nextApps = secState.applications.map((a) => ({
        ...a,
        system_enabled: a.core || !disabledSet.has(a.id),
      }));

      setSecState((prev) => ({
        ...prev,
        system_disabled_applications: nextDisabled,
        applications: nextApps,
      }));

      const enabledAppIds = nextApps.filter((a) => a.system_enabled).map((a) => a.id);
      onPermittedAppsChange?.(enabledAppIds);

      if (runFetch) {
        try {
          const res = await runFetch('/cdeadmin/api/shell/security', {
            method: 'PUT',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', ...resolveCsrfHeaders()},
            body: JSON.stringify({system_disabled_applications: nextDisabled}),
          });
          if (res?.ok) {
            const updated = await res.json();
            if (updated?.applications) setSecState(updated);
          }
          await onRefreshAuthorization?.();
        } catch {
          // Offline / test harness safe.
        }
      }
    },
    [onPermittedAppsChange, onRefreshAuthorization, runFetch, secState]
  );

  const subViewTabsBar = hideTabs ? null : (
    <div
      role="tablist"
      aria-label={gettext('Security Configuration Sections')}
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 6,
        paddingBottom: 8,
        borderBottom: '1px solid var(--sr-border-subtle)',
      }}
    >
      {[
        ['apps', gettext('Application Availability')],
        ['users', gettext('Users & Grants')],
        ['groups', gettext('Groups & Permissions')],
      ].map(([key, label]) => {
        const selected = activeSubView === key;
        return (
          <Button
            key={key}
            role="tab"
            aria-selected={selected}
            intent={selected ? 'primary' : 'neutral'}
            data-cdeadmin-qa-key={`security-tab-${key}`}
            onClick={() => switchSubView(key)}
          >
            {label}
          </Button>
        );
      })}
    </div>
  );

  // -------------------------------------------------------------------------
  // Sub-view 1: Application Availability Switchboard
  // -------------------------------------------------------------------------
  if (activeSubView === 'apps') {
    return (
      <div
        data-cdeadmin-qa-key="settings-security-apps-editor"
        style={{display: 'flex', flexDirection: 'column', gap: 12}}
      >
        {subViewTabsBar}
        <div>
          <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
            {gettext('Workspace Application Availability')}
          </div>
          <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
            {gettext(
              'Turn ScratchRobin applications ON or OFF across the installation. Disabled applications are hidden from the Side Dock (Area 2) and Applications Menu (Area 1).'
            )}
          </div>
        </div>

        <div className="sr-bui-table-card" style={{padding: 8, display: 'flex', flexDirection: 'column', gap: 6}}>
          {secState.applications.map((app) => {
            const isEnabled = app.system_enabled !== false || app.core;
            return (
              <div
                key={app.id}
                data-cdeadmin-qa-key={`security-app-row-${app.id}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 10px',
                  borderRadius: 8,
                  background: 'var(--sr-surface-card)',
                  border: '1px solid var(--sr-border-subtle)',
                }}
              >
                <span style={{display: 'inline-flex', alignItems: 'center', gap: 10}}>
                  <Icon iconKey={app.icon || 'command.default'} decorative size="18px" />
                  <span>
                    <div style={{fontWeight: 600, fontSize: '0.82rem'}}>{app.label}</div>
                    <code style={{fontSize: '0.7rem', color: 'var(--sr-text-secondary)'}}>
                      {app.id}
                      {app.core ? ' (Core Standard Application)' : ''}
                    </code>
                  </span>
                </span>
                <Switch
                  label={isEnabled ? gettext('Available') : gettext('Disabled')}
                  checked={isEnabled}
                  disabled={Boolean(app.core)}
                  data-cdeadmin-qa-key={`security-app-switch-${app.id}`}
                  onChange={(checked) => {
                    void handleToggleSystemApp(app.id, checked);
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Sub-view 2: Users & Access Overrides
  // -------------------------------------------------------------------------
  if (activeSubView === 'users') {
    const selectUser = (user) => {
      setSelectedUsername(user.username);
      setDraftUser({
        username: user.username,
        email: user.email || '',
        password: '',
        active: user.active !== false,
        locked: Boolean(user.locked),
        groups: user.groups || ['administrators'],
        enabled_applications: user.enabled_applications || [],
        disabled_applications: user.disabled_applications || [],
      });
    };

    const handleSaveUser = async () => {
      if (!draftUser.username.trim()) return;
      const cleanRecord = {
        ...draftUser,
        username: draftUser.username.trim(),
        email: draftUser.email.trim() || `${draftUser.username.trim()}@localhost`,
      };

      setSecState((prev) => {
        const exists = prev.users.some(
          (u) => u.username.toLowerCase() === cleanRecord.username.toLowerCase()
        );
        const nextUsers = exists
          ? prev.users.map((u) =>
            u.username.toLowerCase() === cleanRecord.username.toLowerCase()
              ? {...u, ...cleanRecord}
              : u
          )
          : [...prev.users, {id: cleanRecord.username, ...cleanRecord}];
        return {...prev, users: nextUsers};
      });
      setSelectedUsername(cleanRecord.username);
      setDraftUser((p) => ({...p, password: ''}));
      setFeedback(gettext('Saved user "%s" access policy.', cleanRecord.username));

      if (runFetch) {
        try {
          const res = await runFetch('/cdeadmin/api/shell/security/users', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', ...resolveCsrfHeaders()},
            body: JSON.stringify(cleanRecord),
          });
          if (res?.ok) {
            const updated = await res.json();
            if (updated?.users) setSecState(updated);
          }
          await onRefreshAuthorization?.();
        } catch {
          // Offline fallback.
        }
      }
    };

    const handleDeleteUser = async (uname) => {
      if (uname === 'desktop' || uname === 'administrator') return;
      setSecState((prev) => ({
        ...prev,
        users: prev.users.filter((u) => u.username !== uname),
      }));
      if (runFetch) {
        try {
          const res = await runFetch(
            `/cdeadmin/api/shell/security/users/${encodeURIComponent(uname)}`,
            {
              method: 'DELETE',
              credentials: 'same-origin',
              headers: resolveCsrfHeaders(),
            }
          );
          if (res?.ok) {
            const updated = await res.json();
            if (updated?.users) setSecState(updated);
          }
          await onRefreshAuthorization?.();
        } catch {
          // Offline fallback.
        }
      }
    };

    return (
      <div
        data-cdeadmin-qa-key="settings-security-users-editor"
        style={{display: 'flex', flexDirection: 'column', gap: 12}}
      >
        {subViewTabsBar}
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
          <div>
            <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
              {gettext('Users, Group Assignments & Application Overrides')}
            </div>
            <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
              {gettext(
                'Manage user accounts, assign security groups, and grant or revoke individual applications.'
              )}
            </div>
          </div>
          <Button
            intent="neutral"
            data-cdeadmin-qa-key="security-user-new"
            onClick={() => {
              setSelectedUsername('__new__');
              setDraftUser({
                username: '',
                email: '',
                password: '',
                active: true,
                locked: false,
                groups: ['analysts'],
                enabled_applications: [],
                disabled_applications: [],
              });
            }}
          >
            {gettext('+ New User')}
          </Button>
        </div>

        {feedback && <Banner status="info">{feedback}</Banner>}

        {/* Users list */}
        <div className="sr-bui-table-card" style={{padding: 6, display: 'flex', flexDirection: 'column', gap: 4}}>
          {secState.users.map((u) => {
            const isSelected = u.username === selectedUsername;
            return (
              <div
                key={u.username}
                data-cdeadmin-qa-key={`security-user-row-${u.username}`}
                onClick={() => selectUser(u)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '6px 10px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  background: isSelected ? 'var(--sr-selection-bg, var(--sr-accent-subtle))' : 'var(--sr-surface-card)',
                  border: isSelected ? '1px solid var(--sr-accent)' : '1px solid var(--sr-border-subtle)',
                }}
              >
                <div>
                  <strong style={{fontSize: '0.82rem'}}>{u.username}</strong>{' '}
                  <span style={{fontSize: '0.74rem', color: 'var(--sr-text-secondary)'}}>
                    ({u.email || 'local'}) · {(u.groups || []).join(', ')}
                  </span>
                </div>
                <div style={{display: 'flex', alignItems: 'center', gap: 6}}>
                  <span style={{fontSize: '0.7rem', fontWeight: 600}}>
                    {u.active === false ? gettext('Inactive') : gettext('Active')}
                  </span>
                  {u.username !== 'desktop' && u.username !== 'administrator' && (
                    <Button
                      intent="danger"
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDeleteUser(u.username);
                      }}
                    >
                      {gettext('Delete')}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* User Editor Card */}
        <div
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10}}>
            <TextField
              label={gettext('Username')}
              value={draftUser.username}
              inputProps={{'data-cdeadmin-qa-key': 'security-user-username'}}
              onChange={(e) => setDraftUser((p) => ({...p, username: e.target.value}))}
            />
            <TextField
              label={gettext('Email')}
              value={draftUser.email}
              inputProps={{'data-cdeadmin-qa-key': 'security-user-email'}}
              onChange={(e) => setDraftUser((p) => ({...p, email: e.target.value}))}
            />
            <TextField
              label={gettext('Password (optional / local)')}
              type="password"
              value={draftUser.password || ''}
              placeholder={gettext('Leave blank to keep unchanged')}
              inputProps={{'data-cdeadmin-qa-key': 'security-user-password'}}
              onChange={(e) => setDraftUser((p) => ({...p, password: e.target.value}))}
            />
          </div>

          <div style={{display: 'flex', gap: 18}}>
            <Switch
              label={gettext('Account Active')}
              checked={Boolean(draftUser.active)}
              onChange={(checked) => setDraftUser((p) => ({...p, active: Boolean(checked)}))}
            />
            <Switch
              label={gettext('Account Locked')}
              checked={Boolean(draftUser.locked)}
              onChange={(checked) => setDraftUser((p) => ({...p, locked: Boolean(checked)}))}
            />
          </div>

          <div>
            <div style={{fontWeight: 600, fontSize: '0.78rem', marginBottom: 6}}>
              {gettext('Member of Groups / Roles')}
            </div>
            <div style={{display: 'flex', flexWrap: 'wrap', gap: 10}}>
              {secState.groups.map((grp) => (
                <Checkbox
                  key={grp.id}
                  label={grp.name}
                  checked={(draftUser.groups || []).includes(grp.id)}
                  onChange={(checked) =>
                    setDraftUser((p) => ({
                      ...p,
                      groups: checked
                        ? [...new Set([...(p.groups || []), grp.id])]
                        : (p.groups || []).filter((id) => id !== grp.id),
                    }))
                  }
                />
              ))}
            </div>
          </div>

          <div>
            <div style={{fontWeight: 600, fontSize: '0.78rem', marginBottom: 6}}>
              {gettext('Per-User Application Grant / Revoke Overrides')}
            </div>
            <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6}}>
              {secState.applications
                .filter((a) => !a.core)
                .map((app) => {
                  const stateVal = (draftUser.enabled_applications || []).includes(app.id)
                    ? 'grant'
                    : (draftUser.disabled_applications || []).includes(app.id)
                      ? 'revoke'
                      : 'inherit';
                  return (
                    <Select
                      key={app.id}
                      label={app.label}
                      value={stateVal}
                      options={[
                        {value: 'inherit', label: gettext('Inherit from Group')},
                        {value: 'grant', label: gettext('Explicit Grant')},
                        {value: 'revoke', label: gettext('Explicit Revoke')},
                      ]}
                      onChange={(val) => {
                        setDraftUser((p) => {
                          const en = (p.enabled_applications || []).filter((id) => id !== app.id);
                          const dis = (p.disabled_applications || []).filter((id) => id !== app.id);
                          if (val === 'grant') en.push(app.id);
                          if (val === 'revoke') dis.push(app.id);
                          return {...p, enabled_applications: en, disabled_applications: dis};
                        });
                      }}
                    />
                  );
                })}
            </div>
          </div>

          <div style={{display: 'flex', justifyContent: 'flex-end'}}>
            <Button
              intent="primary"
              data-cdeadmin-qa-key="security-user-save"
              onClick={() => void handleSaveUser()}
            >
              {gettext('Save User & Grants')}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Sub-view 3: Security Groups & Fine-Grained Permission Grants
  // -------------------------------------------------------------------------
  const activeGroup =
    secState.groups.find((g) => g.id === selectedGroupId) || secState.groups[0];

  const updateActiveGroupLocal = (patch) => {
    if (!activeGroup) return;
    setSecState((prev) => ({
      ...prev,
      groups: prev.groups.map((g) => (g.id === activeGroup.id ? {...g, ...patch} : g)),
    }));
  };

  const handleSaveGroup = async (groupToSave = activeGroup) => {
    if (!groupToSave) return;
    setFeedback(gettext('Saved group "%s" permissions and application grants.', groupToSave.name));
    if (runFetch) {
      try {
        const res = await runFetch('/cdeadmin/api/shell/security/groups', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', ...resolveCsrfHeaders()},
          body: JSON.stringify(groupToSave),
        });
        if (res?.ok) {
          const updated = await res.json();
          if (updated?.groups) setSecState(updated);
        }
        await onRefreshAuthorization?.();
      } catch {
        // Offline fallback.
      }
    }
  };

  const handleCreateGroup = async () => {
    const name = newGroupName.trim();
    if (!name) return;
    const id = name.toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
    const created = {
      id,
      name,
      description: '',
      builtin: false,
      enabled_applications: ['data-navigator'],
      disabled_applications: secState.applications
        .filter((a) => !a.core)
        .map((a) => a.id),
      permissions: [],
    };
    setNewGroupName('');
    setSecState((prev) => ({...prev, groups: [...prev.groups, created]}));
    setSelectedGroupId(id);
    await handleSaveGroup(created);
  };

  return (
    <div
      data-cdeadmin-qa-key="settings-security-groups-editor"
      style={{display: 'flex', flexDirection: 'column', gap: 12}}
    >
      {subViewTabsBar}
      <div>
        <div style={{fontWeight: 700, fontSize: '0.92rem'}}>
          {gettext('Security Groups, Application Access & Permission Grants')}
        </div>
        <div style={{fontSize: '0.78rem', color: 'var(--sr-text-secondary)'}}>
          {gettext(
            'Define reusable security groups to grant or revoke ScratchRobin applications and capability permissions.'
          )}
        </div>
      </div>

      {feedback && <Banner status="info">{feedback}</Banner>}

      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8, alignItems: 'end'}}>
        <Select
          label={gettext('Select Group / Role')}
          value={activeGroup?.id || ''}
          options={secState.groups.map((g) => ({value: g.id, label: g.name}))}
          onChange={(val) => val && setSelectedGroupId(val)}
        />
        <TextField
          label={gettext('Create New Group')}
          placeholder="e.g. Junior Developers"
          value={newGroupName}
          inputProps={{'data-cdeadmin-qa-key': 'security-group-new-name'}}
          onChange={(e) => setNewGroupName(e.target.value)}
        />
        <Button
          intent="neutral"
          data-cdeadmin-qa-key="security-group-create"
          onClick={() => void handleCreateGroup()}
        >
          {gettext('+ Create Group')}
        </Button>
      </div>

      {activeGroup && (
        <div
          style={{
            padding: 12,
            borderRadius: 10,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <TextField
            label={gettext('Group Description')}
            value={activeGroup.description || ''}
            onChange={(e) => updateActiveGroupLocal({description: e.target.value})}
          />

          <div>
            <div style={{fontWeight: 600, fontSize: '0.78rem', marginBottom: 6}}>
              {gettext('Group Application Grants')}
            </div>
            <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6}}>
              {secState.applications.map((app) => {
                const granted =
                  app.core || (activeGroup.enabled_applications || []).includes(app.id);
                return (
                  <Switch
                    key={app.id}
                    label={app.label}
                    checked={granted}
                    disabled={Boolean(app.core)}
                    data-cdeadmin-qa-key={`security-group-app-${app.id}`}
                    onChange={(checked) => {
                      const en = new Set(activeGroup.enabled_applications || []);
                      const dis = new Set(activeGroup.disabled_applications || []);
                      if (checked) {
                        en.add(app.id);
                        dis.delete(app.id);
                      } else {
                        en.delete(app.id);
                        dis.add(app.id);
                      }
                      en.add('data-navigator');
                      updateActiveGroupLocal({
                        enabled_applications: [...en],
                        disabled_applications: [...dis],
                      });
                    }}
                  />
                );
              })}
            </div>
          </div>

          <div>
            <div style={{fontWeight: 600, fontSize: '0.78rem', marginBottom: 6}}>
              {gettext('Capability Permission Grants')}
            </div>
            <div
              style={{
                border: '1px solid var(--sr-border-default)',
                borderRadius: 8,
                background: 'var(--sr-surface-card)',
                overflow: 'hidden',
              }}
            >
              <ScratchBranchedTree
                label={gettext('Group Capability Permissions')}
                items={permissionTreeNodes}
                checkable
                checkedIds={activeGroup.permissions || []}
                onCheckedChange={(nextChecked) =>
                  updateActiveGroupLocal({
                    permissions: nextChecked.filter((id) => !id.startsWith('cat:')),
                  })
                }
                expandedIds={permTreeExpanded}
                onExpandedChange={setPermTreeExpanded}
                stickyAncestors={false}
                style={{height: 190}}
              />
            </div>
          </div>

          <div style={{display: 'flex', justifyContent: 'space-between', gap: 8}}>
            <div>
              {!activeGroup.builtin && (
                <Button
                  intent="danger"
                  onClick={async () => {
                    const gid = activeGroup.id;
                    setSecState((prev) => ({
                      ...prev,
                      groups: prev.groups.filter((g) => g.id !== gid),
                    }));
                    setSelectedGroupId('administrators');
                    if (runFetch) {
                      await runFetch(
                        `/cdeadmin/api/shell/security/groups/${encodeURIComponent(gid)}`,
                        {
                          method: 'DELETE',
                          credentials: 'same-origin',
                          headers: resolveCsrfHeaders(),
                        }
                      ).catch(() => {});
                      await onRefreshAuthorization?.();
                    }
                  }}
                >
                  {gettext('Delete Group')}
                </Button>
              )}
            </div>
            <Button
              intent="primary"
              data-cdeadmin-qa-key="security-group-save"
              onClick={() => void handleSaveGroup(activeGroup)}
            >
              {gettext('Save Group Grants')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

SecurityAccessEditor.propTypes = {
  subView: PropTypes.oneOf(['apps', 'users', 'groups']),
  hideTabs: PropTypes.bool,
  applications: PropTypes.array,
  fetchImpl: PropTypes.func,
  onPermittedAppsChange: PropTypes.func,
  onRefreshAuthorization: PropTypes.func,
  onNavigateSubView: PropTypes.func,
};
