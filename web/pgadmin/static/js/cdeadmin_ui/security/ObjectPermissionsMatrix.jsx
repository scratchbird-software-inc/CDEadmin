/////////////////////////////////////////////////////////////
//
// ScratchRobin — Enterprise Per-Object Permissions & Grants Matrix
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
import {Checkbox, Select} from '../primitives/Choice';
import {TextField} from '../primitives/Field';
import {Banner, Badge} from '../feedback/Indicators';
import FormReference from '../navigation/FormReference';

const DEFAULT_PRIVILEGES_BY_KIND = Object.freeze({
  table: ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'REFERENCES'],
  view: ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'REFERENCES'],
  'materialized-view': ['SELECT'],
  procedure: ['EXECUTE'],
  function: ['EXECUTE'],
  routine: ['EXECUTE'],
  package: ['EXECUTE'],
  sequence: ['USAGE', 'SELECT', 'UPDATE'],
  type: ['USAGE'],
  domain: ['USAGE'],
  exception: ['USAGE'],
  schema: ['USAGE', 'CREATE'],
  database: ['CONNECT', 'CREATE', 'TEMPORARY'],
});

const FIREBIRD_PRIV_CODE_MAP = Object.freeze({
  S: 'SELECT',
  I: 'INSERT',
  U: 'UPDATE',
  D: 'DELETE',
  R: 'REFERENCES',
  X: 'EXECUTE',
  G: 'USAGE',
  M: 'MEMBERSHIP',
});

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

function normalizeObjectIdentity(boundNodeData, resource) {
  if (resource && typeof resource === 'object') {
    const rawPath = Array.isArray(resource.display_path) ? resource.display_path : [];
    const kind = String(resource.resource_kind || boundNodeData?.cde_resource_kind || boundNodeData?._type || 'table')
      .replace(/^coll-/, '')
      .toLowerCase();
    const name = String(resource.display_name || boundNodeData?._label || boundNodeData?.label || '');
    const schema =
      resource.native?.schema ||
      resource.native?.schema_name ||
      (rawPath.length >= 2 ? rawPath[rawPath.length - 2] : '');
    return {
      sid:
        boundNodeData?.cde_server_id ||
        boundNodeData?.cde_endpoint_id ||
        boundNodeData?.server_id ||
        boundNodeData?._pid ||
        boundNodeData?.sid ||
        '',
      databaseTargetId:
        boundNodeData?.cde_database_target_id ||
        (boundNodeData?._type === 'cde_database_target' ? boundNodeData?._id : '') ||
        '',
      kind,
      schema: schema && schema !== name ? String(schema) : '',
      name,
      resourceId: String(resource.resource_id || boundNodeData?.cde_resource_id || ''),
      engine: String(
        boundNodeData?.cde_engine_id ||
        resource.engine ||
        ''
      ).toLowerCase(),
    };
  }
  const rawType = String(boundNodeData?.cde_resource_kind || boundNodeData?._type || 'table')
    .replace(/^cde_/, '')
    .replace(/^coll-/, '')
    .toLowerCase();
  const kind = rawType === 'database_target' ? 'database' : rawType;
  const label = String(boundNodeData?._label || boundNodeData?.label || '').trim();
  return {
    sid:
      boundNodeData?.cde_server_id ||
      boundNodeData?.cde_endpoint_id ||
      boundNodeData?.server_id ||
      boundNodeData?._pid ||
      boundNodeData?.sid ||
      '',
    databaseTargetId:
      boundNodeData?.cde_database_target_id ||
      (boundNodeData?._type === 'cde_database_target' ? boundNodeData?._id : '') ||
      '',
    kind,
    schema: String(boundNodeData?.schema || boundNodeData?.nspname || ''),
    name: label,
    resourceId: String(boundNodeData?.cde_resource_id || ''),
    engine: String(boundNodeData?.cde_engine_id || '').toLowerCase(),
  };
}

export function normalizeFallbackNativePrivileges(rawPrivileges, objectKind = 'table') {
  if (!Array.isArray(rawPrivileges) || rawPrivileges.length === 0) {
    return [];
  }
  const byKey = new Map();
  rawPrivileges.forEach((row) => {
    if (!row || typeof row !== 'object') return;
    const grantee = String(
      row.grantee ?? row.user ?? row.principal ?? row.role ?? row.rdb$user ?? ''
    ).trim();
    if (!grantee) return;
    const host = row.host || row.grantee_host || null;
    const granteeKind = String(
      row.grantee_kind ||
      (grantee.toUpperCase() === 'PUBLIC'
        ? 'special'
        : row.user_type === 13
          ? 'role'
          : 'user')
    ).toLowerCase();
    const grantor = String(row.grantor ?? row.rdb$grantor ?? '').trim();
    const rawPriv = String(
      row.privilege ?? row.privilege_type ?? row.type ?? ''
    ).trim().toUpperCase();
    const privName = FIREBIRD_PRIV_CODE_MAP[rawPriv] || rawPriv;
    if (!privName) return;
    const grantOpt = Boolean(
      row.grant_option ||
      row.is_grantable === 'YES' ||
      row.is_grantable === true ||
      Number(row.grant_option) > 0
    );
    const colName = row.field_name || row.column_name || null;
    const mapKey = `${granteeKind}:${grantee}:${host || ''}`;
    if (!byKey.has(mapKey)) {
      byKey.set(mapKey, {
        grantee,
        grantee_kind: granteeKind,
        grantee_host: host,
        grantor,
        privileges: {},
      });
    }
    const entry = byKey.get(mapKey);
    const prev = entry.privileges[privName] || {granted: false, grant_option: false, columns: []};
    const nextCols = colName && !prev.columns.includes(colName) ? [...prev.columns, colName] : prev.columns;
    entry.privileges[privName] = {
      granted: true,
      grant_option: prev.grant_option || grantOpt,
      columns: nextCols,
    };
  });
  const supported = DEFAULT_PRIVILEGES_BY_KIND[objectKind] || ['SELECT'];
  return [...byKey.values()].map((item) => {
    supported.forEach((p) => {
      if (!item.privileges[p]) {
        item.privileges[p] = {granted: false, grant_option: false, columns: []};
      }
    });
    return item;
  });
}

function granteeKey(row) {
  return `${row.grantee_kind || 'user'}::${row.grantee}::${row.grantee_host || ''}`;
}

function buildClientPreviewSql({engine, objectKind, schema, objectName, changes}) {
  if (!Array.isArray(changes) || changes.length === 0) return '';
  const q = engine === 'mysql' || engine === 'mariadb' ? '`' : '"';
  const quoteIdent = (v) => `${q}${String(v || '').replaceAll(q, q + q)}${q}`;
  const qualified =
    schema && engine !== 'firebird'
      ? `${quoteIdent(schema)}.${quoteIdent(objectName)}`
      : quoteIdent(objectName);
  const kindKeyword =
    objectKind === 'procedure'
      ? 'PROCEDURE '
      : objectKind === 'function'
        ? 'FUNCTION '
        : objectKind === 'sequence'
          ? 'SEQUENCE '
          : objectKind === 'schema'
            ? 'SCHEMA '
            : objectKind === 'database'
              ? 'DATABASE '
              : '';
  return changes
    .map((chg) => {
      const privList = (chg.privileges || []).join(', ');
      const targetPrincipal =
        chg.grantee?.toUpperCase() === 'PUBLIC'
          ? 'PUBLIC'
          : (engine === 'mysql' || engine === 'mariadb') && chg.grantee_host
            ? `${quoteIdent(chg.grantee)}@${quoteIdent(chg.grantee_host)}`
            : quoteIdent(chg.grantee);
      if (chg.action === 'revoke') {
        return `REVOKE ${privList} ON ${kindKeyword}${qualified} FROM ${targetPrincipal};`;
      }
      const grantOpt = chg.grant_option ? ' WITH GRANT OPTION' : '';
      return `GRANT ${privList} ON ${kindKeyword}${qualified} TO ${targetPrincipal}${grantOpt};`;
    })
    .join('\n');
}

export function computeGrantChanges(baselineRows, draftRows, supportedPrivileges) {
  const baseByKey = new Map((baselineRows || []).map((r) => [granteeKey(r), r]));
  const changes = [];

  (draftRows || []).forEach((row) => {
    const key = granteeKey(row);
    const base = baseByKey.get(key);
    const toGrant = [];
    const toGrantWithOption = [];
    const toRevoke = [];

    (supportedPrivileges || []).forEach((priv) => {
      const cur = row.privileges?.[priv] || {granted: false, grant_option: false};
      const prev = base?.privileges?.[priv] || {granted: false, grant_option: false};
      if (cur.granted && !prev.granted) {
        if (cur.grant_option) toGrantWithOption.push(priv);
        else toGrant.push(priv);
      } else if (!cur.granted && prev.granted) {
        toRevoke.push(priv);
      } else if (cur.granted && prev.granted && cur.grant_option !== prev.grant_option) {
        if (cur.grant_option) {
          toGrantWithOption.push(priv);
        } else {
          toRevoke.push(priv);
          toGrant.push(priv);
        }
      }
    });

    if (toRevoke.length > 0) {
      changes.push({
        action: 'revoke',
        grantee: row.grantee,
        grantee_kind: row.grantee_kind || 'user',
        grantee_host: row.grantee_host || null,
        privileges: toRevoke,
        columns: [],
        grant_option: false,
      });
    }
    if (toGrant.length > 0) {
      changes.push({
        action: 'grant',
        grantee: row.grantee,
        grantee_kind: row.grantee_kind || 'user',
        grantee_host: row.grantee_host || null,
        privileges: toGrant,
        columns: [],
        grant_option: false,
      });
    }
    if (toGrantWithOption.length > 0) {
      changes.push({
        action: 'grant',
        grantee: row.grantee,
        grantee_kind: row.grantee_kind || 'user',
        grantee_host: row.grantee_host || null,
        privileges: toGrantWithOption,
        columns: [],
        grant_option: true,
      });
    }
  });

  // Rows completely removed from draftRows
  (baselineRows || []).forEach((base) => {
    const key = granteeKey(base);
    if (!(draftRows || []).some((r) => granteeKey(r) === key)) {
      const grantedPrivs = (supportedPrivileges || []).filter(
        (p) => base.privileges?.[p]?.granted
      );
      if (grantedPrivs.length > 0) {
        changes.push({
          action: 'revoke',
          grantee: base.grantee,
          grantee_kind: base.grantee_kind || 'user',
          grantee_host: base.grantee_host || null,
          privileges: grantedPrivs,
          columns: [],
          grant_option: false,
        });
      }
    }
  });

  return changes;
}

export default function ObjectPermissionsMatrix({
  boundNodeData = null,
  resource = null,
  sid: sidProp = null,
  databaseTargetId: dbTargetProp = null,
  engine: engineProp = null,
  objectKind: objectKindProp = null,
  schema: schemaProp = null,
  objectName: objectNameProp = null,
  initialPrivileges = null,
  fetchImpl = null,
  compact = false,
  onApplied = null,
}) {
  const runFetch = useMemo(() => {
    if (fetchImpl) return fetchImpl;
    if (typeof window !== 'undefined' && typeof window.fetch === 'function') {
      return window.fetch.bind(window);
    }
    return typeof fetch === 'function' ? fetch : null;
  }, [fetchImpl]);

  const resolvedIdentity = useMemo(() => {
    const base = normalizeObjectIdentity(boundNodeData, resource);
    return {
      sid: sidProp ?? base.sid,
      databaseTargetId: dbTargetProp ?? base.databaseTargetId,
      engine: (engineProp || base.engine || '').toLowerCase(),
      kind: (objectKindProp || base.kind || 'table').toLowerCase(),
      schema: schemaProp ?? base.schema,
      name: objectNameProp || base.name,
      resourceId: base.resourceId,
    };
  }, [
    boundNodeData,
    dbTargetProp,
    engineProp,
    objectKindProp,
    objectNameProp,
    resource,
    schemaProp,
    sidProp,
  ]);

  const fallbackPrivs = useMemo(() => {
    const raw =
      initialPrivileges ??
      resource?.native?.privileges ??
      resource?.native?.grants ??
      resource?.native?.acls ??
      [];
    return normalizeFallbackNativePrivileges(raw, resolvedIdentity.kind);
  }, [initialPrivileges, resolvedIdentity.kind, resource]);

  const defaultSupportedPrivs = useMemo(
    () =>
      DEFAULT_PRIVILEGES_BY_KIND[resolvedIdentity.kind] || [
        'SELECT',
        'INSERT',
        'UPDATE',
        'DELETE',
      ],
    [resolvedIdentity.kind]
  );

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [supported, setSupported] = useState(
    !['sqlite', 'duckdb'].includes(resolvedIdentity.engine)
  );
  const [capabilities, setCapabilities] = useState({
    can_edit: true,
    reason: '',
    supported_privileges: defaultSupportedPrivs,
    supports_grant_option: true,
  });
  const [availablePrincipals, setAvailablePrincipals] = useState([
    {name: 'PUBLIC', kind: 'special'},
  ]);
  const [baselineRows, setBaselineRows] = useState(fallbackPrivs);
  const [draftRows, setDraftRows] = useState(fallbackPrivs);
  const [filterText, setFilterText] = useState('');
  const [newGranteeSelect, setNewGranteeSelect] = useState('');
  const [customGranteeName, setCustomGranteeName] = useState('');
  const [customGranteeKind, setCustomGranteeKind] = useState('user');
  const [customGranteeHost, setCustomGranteeHost] = useState('%');
  const [previewSql, setPreviewSql] = useState('');
  const [showPreview, setShowPreview] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const loadGrants = useCallback(async () => {
    if (['sqlite', 'duckdb'].includes(resolvedIdentity.engine)) {
      setSupported(false);
      return;
    }
    if (!runFetch || (!resolvedIdentity.sid && !resolvedIdentity.resourceId && !resolvedIdentity.name)) {
      setBaselineRows(fallbackPrivs);
      setDraftRows(fallbackPrivs);
      return;
    }
    setLoading(true);
    setErrorMessage(null);
    try {
      const qs = new URLSearchParams();
      if (resolvedIdentity.sid) qs.set('sid', String(resolvedIdentity.sid));
      if (resolvedIdentity.databaseTargetId) {
        qs.set('database_target_id', String(resolvedIdentity.databaseTargetId));
      }
      if (resolvedIdentity.kind) qs.set('object_kind', resolvedIdentity.kind);
      if (resolvedIdentity.schema) qs.set('schema', resolvedIdentity.schema);
      if (resolvedIdentity.name) qs.set('object_name', resolvedIdentity.name);
      if (resolvedIdentity.resourceId) qs.set('resource_id', resolvedIdentity.resourceId);

      const resp = await runFetch(`/cdeadmin/api/security/object_grants?${qs.toString()}`, {
        credentials: 'same-origin',
      });
      if (resp?.ok) {
        const data = await resp.json();
        if (data.supported === false) {
          setSupported(false);
          return;
        }
        setSupported(true);
        const supPrivs =
          Array.isArray(data.capabilities?.supported_privileges) &&
          data.capabilities.supported_privileges.length > 0
            ? data.capabilities.supported_privileges
            : defaultSupportedPrivs;
        setCapabilities({
          can_edit: data.capabilities?.can_edit !== false,
          reason: data.capabilities?.reason || '',
          supported_privileges: supPrivs,
          supports_grant_option: data.capabilities?.supports_grant_option !== false,
        });
        if (Array.isArray(data.principals) && data.principals.length > 0) {
          setAvailablePrincipals(data.principals);
        }
        const rows = Array.isArray(data.grants) ? data.grants : fallbackPrivs;
        setBaselineRows(rows);
        setDraftRows(JSON.parse(JSON.stringify(rows)));
      } else {
        setBaselineRows(fallbackPrivs);
        setDraftRows(JSON.parse(JSON.stringify(fallbackPrivs)));
      }
    } catch {
      setBaselineRows(fallbackPrivs);
      setDraftRows(JSON.parse(JSON.stringify(fallbackPrivs)));
    } finally {
      setLoading(false);
    }
  }, [defaultSupportedPrivs, fallbackPrivs, resolvedIdentity, runFetch]);

  useEffect(() => {
    void loadGrants();
  }, [loadGrants]);

  const supportedPrivs = capabilities.supported_privileges || defaultSupportedPrivs;
  const canEdit = capabilities.can_edit !== false;
  const isMysqlFamily =
    resolvedIdentity.engine === 'mysql' ||
    resolvedIdentity.engine === 'mariadb' ||
    resolvedIdentity.engine === 'tidb' ||
    resolvedIdentity.engine === 'dolt';

  const pendingChanges = useMemo(
    () => computeGrantChanges(baselineRows, draftRows, supportedPrivs),
    [baselineRows, draftRows, supportedPrivs]
  );

  useEffect(() => {
    if (pendingChanges.length === 0) {
      setPreviewSql('');
      return;
    }
    setPreviewSql(
      buildClientPreviewSql({
        engine: resolvedIdentity.engine,
        objectKind: resolvedIdentity.kind,
        schema: resolvedIdentity.schema,
        objectName: resolvedIdentity.name,
        changes: pendingChanges,
      })
    );
  }, [pendingChanges, resolvedIdentity]);

  const handleTogglePrivilege = (rowKey, priv) => {
    if (!canEdit) return;
    setDraftRows((prev) =>
      prev.map((row) => {
        if (granteeKey(row) !== rowKey) return row;
        const cur = row.privileges?.[priv] || {granted: false, grant_option: false, columns: []};
        return {
          ...row,
          privileges: {
            ...row.privileges,
            [priv]: {
              ...cur,
              granted: !cur.granted,
              grant_option: !cur.granted ? cur.grant_option : false,
            },
          },
        };
      })
    );
  };

  const handleToggleGrantOption = (rowKey) => {
    if (!canEdit) return;
    setDraftRows((prev) =>
      prev.map((row) => {
        if (granteeKey(row) !== rowKey) return row;
        const anyGranted = supportedPrivs.some((p) => row.privileges?.[p]?.granted);
        if (!anyGranted) return row;
        const allWithOption = supportedPrivs
          .filter((p) => row.privileges?.[p]?.granted)
          .every((p) => row.privileges?.[p]?.grant_option);
        const nextPrivs = {...row.privileges};
        supportedPrivs.forEach((p) => {
          if (nextPrivs[p]?.granted) {
            nextPrivs[p] = {...nextPrivs[p], grant_option: !allWithOption};
          }
        });
        return {...row, privileges: nextPrivs};
      })
    );
  };

  const handleGrantAllRow = (rowKey, grantValue) => {
    if (!canEdit) return;
    setDraftRows((prev) =>
      prev.map((row) => {
        if (granteeKey(row) !== rowKey) return row;
        const nextPrivs = {...row.privileges};
        supportedPrivs.forEach((p) => {
          nextPrivs[p] = {
            ...(nextPrivs[p] || {columns: []}),
            granted: grantValue,
            grant_option: grantValue ? Boolean(nextPrivs[p]?.grant_option) : false,
          };
        });
        return {...row, privileges: nextPrivs};
      })
    );
  };

  const handleAddGrantee = () => {
    if (!canEdit) return;
    let name = '';
    let kind = customGranteeKind || 'user';
    let host = isMysqlFamily ? customGranteeHost || '%' : null;

    if (newGranteeSelect && newGranteeSelect !== '__custom__') {
      const found = availablePrincipals.find(
        (p) => `${p.kind}:${p.name}:${p.host || ''}` === newGranteeSelect
      );
      if (found) {
        name = found.name;
        kind = found.kind || 'user';
        host = found.host || (isMysqlFamily && kind !== 'special' ? '%' : null);
      }
    } else {
      name = customGranteeName.trim();
    }
    if (!name) return;

    const newRow = {
      grantee: name,
      grantee_kind: name.toUpperCase() === 'PUBLIC' ? 'special' : kind,
      grantee_host: name.toUpperCase() === 'PUBLIC' ? null : host,
      grantor: '',
      privileges: Object.fromEntries(
        supportedPrivs.map((p, idx) => [
          p,
          {granted: idx === 0, grant_option: false, columns: []},
        ])
      ),
    };
    const key = granteeKey(newRow);
    setDraftRows((prev) => {
      if (prev.some((r) => granteeKey(r) === key)) return prev;
      return [...prev, newRow];
    });
    setCustomGranteeName('');
    setNewGranteeSelect('');
  };

  const handlePreviewServerPlan = async () => {
    setShowPreview(true);
    if (!runFetch || pendingChanges.length === 0 || !resolvedIdentity.sid) return;
    try {
      const resp = await runFetch('/cdeadmin/api/security/object_grants/plan', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', ...resolveCsrfHeaders()},
        body: JSON.stringify({
          sid: resolvedIdentity.sid,
          database_target_id: resolvedIdentity.databaseTargetId || undefined,
          object_kind: resolvedIdentity.kind,
          schema: resolvedIdentity.schema || undefined,
          object_name: resolvedIdentity.name,
          changes: pendingChanges,
        }),
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
  };

  const handleApply = async () => {
    if (!canEdit || pendingChanges.length === 0) return;
    setSaving(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      if (runFetch && resolvedIdentity.sid) {
        const resp = await runFetch('/cdeadmin/api/security/object_grants/apply', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', ...resolveCsrfHeaders()},
          body: JSON.stringify({
            sid: resolvedIdentity.sid,
            database_target_id: resolvedIdentity.databaseTargetId || undefined,
            object_kind: resolvedIdentity.kind,
            schema: resolvedIdentity.schema || undefined,
            object_name: resolvedIdentity.name,
            changes: pendingChanges,
          }),
        });
        const data = await resp?.json?.().catch(() => ({}));
        if (!resp?.ok || data?.error || data?.errormsg) {
          throw new Error(data?.error || data?.errormsg || gettext('Failed to apply object permissions.'));
        }
        setStatusMessage(
          gettext('Permissions updated (%s statement(s) executed).', data?.statement_count || pendingChanges.length)
        );
        await loadGrants();
      } else {
        setBaselineRows(JSON.parse(JSON.stringify(draftRows)));
        setStatusMessage(gettext('Permissions staged (%s change(s)).', pendingChanges.length));
      }
      onApplied?.({changes: pendingChanges, sql: previewSql});
    } catch (err) {
      setErrorMessage(err?.message || String(err));
    } finally {
      setSaving(false);
    }
  };

  if (!supported) {
    return (
      <div
        data-cdeadmin-qa-key="object-permissions-unsupported"
        style={{
          border: '1px solid var(--sr-border-default)',
          borderRadius: 10,
          padding: '14px 16px',
          background: 'var(--sr-surface-default, var(--sr-island-bg))',
          fontSize: '0.82rem',
          color: 'var(--sr-text-secondary)',
        }}
      >
        {gettext(
          'This database engine uses embedded file-level access controls and does not define SQL GRANT / REVOKE object permissions.'
        )}
      </div>
    );
  }

  const visibleRows = draftRows.filter((row) => {
    const q = filterText.trim().toLowerCase();
    if (!q) return true;
    return `${row.grantee} ${row.grantee_kind || ''} ${row.grantee_host || ''} ${row.grantor || ''}`
      .toLowerCase()
      .includes(q);
  });

  const principalOptions = [
    {value: '', label: gettext('Select user / role / PUBLIC…')},
    ...availablePrincipals.map((p) => ({
      value: `${p.kind || 'user'}:${p.name}:${p.host || ''}`,
      label: p.host ? `${p.name}@${p.host} (${p.kind || 'user'})` : `${p.name} (${p.kind || 'user'})`,
    })),
    {value: '__custom__', label: gettext('Custom principal name…')},
  ];

  return (
    <Box
      data-cdeadmin-qa-key="object-permissions-matrix"
      sx={{
        border: compact ? 'none' : '1px solid var(--sr-border-default)',
        borderRadius: compact ? 0 : '10px',
        p: compact ? 1 : 2,
        background: 'var(--sr-surface-default, var(--sr-island-bg))',
        display: 'flex',
        flexDirection: 'column',
        gap: 1.5,
        minWidth: 0,
      }}
    >
      {/* Header & Object Badge */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 10,
          flexWrap: 'wrap',
        }}
      >
        <div style={{display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap'}}>
          <span style={{fontWeight: 700, fontSize: '0.88rem', color: 'var(--sr-text-primary)'}}>
            {gettext('Object Permissions & Grants')}
          </span>
          {resolvedIdentity.name && (
            <Badge
              tone="accent"
              label={
                resolvedIdentity.schema
                  ? `${resolvedIdentity.kind.toUpperCase()} · ${resolvedIdentity.schema}.${resolvedIdentity.name}`
                  : `${resolvedIdentity.kind.toUpperCase()} · ${resolvedIdentity.name}`
              }
            />
          )}
          <Badge
            tone={canEdit ? 'success' : 'neutral'}
            label={canEdit ? gettext('Authorized to Grant / Revoke') : gettext('Read-Only Access')}
          />
          <FormReference formKey="object-permissions-matrix" />
        </div>

        <div style={{display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap'}}>
          <Button
            size="small"
            intent="neutral"
            disabled={loading || saving}
            onClick={() => void loadGrants()}
          >
            {loading ? gettext('Loading…') : gettext('Refresh')}
          </Button>
          {pendingChanges.length > 0 && (
            <>
              <Button
                size="small"
                intent="neutral"
                disabled={saving}
                onClick={() => {
                  setDraftRows(JSON.parse(JSON.stringify(baselineRows)));
                  setStatusMessage(null);
                  setErrorMessage(null);
                }}
              >
                {gettext('Revert (%s)', pendingChanges.length)}
              </Button>
              <Button
                size="small"
                intent="neutral"
                disabled={saving}
                onClick={() => void handlePreviewServerPlan()}
              >
                {showPreview ? gettext('Refresh SQL Preview') : gettext('Preview SQL')}
              </Button>
              <Button
                size="small"
                intent="primary"
                data-cdeadmin-qa-key="object-permissions-apply"
                disabled={saving}
                onClick={() => void handleApply()}
              >
                {saving ? gettext('Applying…') : gettext('Apply Permissions')}
              </Button>
            </>
          )}
        </div>
      </div>

      {!canEdit && (
        <Banner status="info">
          {capabilities.reason ||
            gettext(
              'Current connection does not hold GRANT OPTION or ownership on this object. Existing grants are shown read-only.'
            )}
        </Banner>
      )}

      {errorMessage && <Banner status="error">{errorMessage}</Banner>}
      {statusMessage && <Banner status="success">{statusMessage}</Banner>}

      {/* Filter + Add Principal Grant Row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: 10,
          flexWrap: 'wrap',
          padding: '8px 10px',
          borderRadius: 8,
          background: 'var(--sr-surface-subtle)',
          border: '1px solid var(--sr-border-default)',
        }}
      >
        <div style={{minWidth: 200, flex: '1 1 200px', maxWidth: 300}}>
          <TextField
            label={gettext('Filter Principals')}
            placeholder={gettext('Search user, role, or grantor…')}
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
          />
        </div>

        {canEdit && (
          <div style={{display: 'flex', alignItems: 'flex-end', gap: 8, flexWrap: 'wrap'}}>
            <div style={{minWidth: 210}}>
              <Select
                label={gettext('Grant Access To')}
                value={newGranteeSelect}
                options={principalOptions}
                onChange={(val) => setNewGranteeSelect(val)}
              />
            </div>
            {(newGranteeSelect === '__custom__' || availablePrincipals.length <= 1) && (
              <>
                <div style={{width: 150}}>
                  <TextField
                    label={gettext('Principal Name')}
                    placeholder={gettext('e.g. app_reader')}
                    value={customGranteeName}
                    onChange={(e) => setCustomGranteeName(e.target.value)}
                  />
                </div>
                <div style={{width: 120}}>
                  <Select
                    label={gettext('Kind')}
                    value={customGranteeKind}
                    options={[
                      {value: 'user', label: gettext('User')},
                      {value: 'role', label: gettext('Role / Group')},
                      {value: 'special', label: gettext('PUBLIC')},
                    ]}
                    onChange={(val) => setCustomGranteeKind(val)}
                  />
                </div>
                {isMysqlFamily && customGranteeKind !== 'special' && (
                  <div style={{width: 96}}>
                    <TextField
                      label={gettext('Host')}
                      value={customGranteeHost}
                      onChange={(e) => setCustomGranteeHost(e.target.value)}
                    />
                  </div>
                )}
              </>
            )}
            <Button
              size="small"
              intent="secondary"
              data-cdeadmin-qa-key="object-permissions-add-grantee"
              disabled={
                (!newGranteeSelect || newGranteeSelect === '__custom__') &&
                !customGranteeName.trim()
              }
              onClick={handleAddGrantee}
            >
              {gettext('+ Add Grantee')}
            </Button>
          </div>
        )}
      </div>

      {/* Principal x Privilege Matrix */}
      <div
        style={{
          overflowX: 'auto',
          border: '1px solid var(--sr-border-default)',
          borderRadius: 8,
        }}
      >
        <table
          data-cdeadmin-qa-key="object-permissions-table"
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '0.8rem',
          }}
        >
          <thead>
            <tr
              style={{
                background: 'var(--sr-surface-subtle)',
                borderBottom: '1px solid var(--sr-border-default)',
                textAlign: 'left',
              }}
            >
              <th style={{padding: '8px 10px', fontWeight: 600}}>{gettext('Principal')}</th>
              <th style={{padding: '8px 8px', fontWeight: 600}}>{gettext('Type')}</th>
              <th style={{padding: '8px 8px', fontWeight: 600}}>{gettext('Grantor')}</th>
              {supportedPrivs.map((priv) => (
                <th key={priv} style={{padding: '8px 8px', textAlign: 'center', fontWeight: 600}}>
                  {priv}
                </th>
              ))}
              {capabilities.supports_grant_option !== false && (
                <th style={{padding: '8px 8px', textAlign: 'center', fontWeight: 600}}>
                  {gettext('Grant Option')}
                </th>
              )}
              {canEdit && (
                <th style={{padding: '8px 10px', textAlign: 'right', fontWeight: 600}}>
                  {gettext('Quick Actions')}
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {visibleRows.length === 0 ? (
              <tr>
                <td
                  colSpan={supportedPrivs.length + (canEdit ? 5 : 4)}
                  style={{
                    padding: '18px 12px',
                    textAlign: 'center',
                    color: 'var(--sr-text-secondary)',
                  }}
                >
                  {loading
                    ? gettext('Inspecting object grants…')
                    : gettext('No explicit grants found on this object.')}
                </td>
              </tr>
            ) : (
              visibleRows.map((row) => {
                const rKey = granteeKey(row);
                const grantedList = supportedPrivs.filter((p) => row.privileges?.[p]?.granted);
                const allWithOpt =
                  grantedList.length > 0 &&
                  grantedList.every((p) => row.privileges?.[p]?.grant_option);
                return (
                  <tr
                    key={rKey}
                    style={{
                      borderBottom: '1px solid var(--sr-border-subtle, var(--sr-border-default))',
                    }}
                  >
                    <td style={{padding: '7px 10px', fontWeight: 600, fontFamily: 'var(--sr-font-mono, monospace)'}}>
                      {row.grantee_host ? `${row.grantee}@${row.grantee_host}` : row.grantee}
                    </td>
                    <td style={{padding: '7px 8px'}}>
                      <Badge tone="neutral" label={row.grantee_kind || 'user'} />
                    </td>
                    <td style={{padding: '7px 8px', color: 'var(--sr-text-secondary)'}}>
                      {row.grantor || '—'}
                    </td>
                    {supportedPrivs.map((priv) => {
                      const cell = row.privileges?.[priv] || {granted: false, columns: []};
                      return (
                        <td key={priv} style={{padding: '7px 8px', textAlign: 'center'}}>
                          <div style={{display: 'inline-flex', flexDirection: 'column', alignItems: 'center'}}>
                            <Checkbox
                              aria-label={`${row.grantee} ${priv}`}
                              checked={Boolean(cell.granted)}
                              disabled={!canEdit}
                              onChange={() => handleTogglePrivilege(rKey, priv)}
                            />
                            {Array.isArray(cell.columns) && cell.columns.length > 0 && (
                              <span
                                style={{
                                  fontSize: '0.66rem',
                                  color: 'var(--sr-text-secondary)',
                                }}
                                title={cell.columns.join(', ')}
                              >
                                ({cell.columns.length} col)
                              </span>
                            )}
                          </div>
                        </td>
                      );
                    })}
                    {capabilities.supports_grant_option !== false && (
                      <td style={{padding: '7px 8px', textAlign: 'center'}}>
                        <Checkbox
                          aria-label={`${row.grantee} WITH GRANT OPTION`}
                          checked={allWithOpt}
                          disabled={!canEdit || grantedList.length === 0}
                          onChange={() => handleToggleGrantOption(rKey)}
                        />
                      </td>
                    )}
                    {canEdit && (
                      <td style={{padding: '7px 10px', textAlign: 'right', whiteSpace: 'nowrap'}}>
                        <div style={{display: 'inline-flex', gap: 4}}>
                          <Button
                            size="small"
                            intent="neutral"
                            onClick={() => handleGrantAllRow(rKey, true)}
                          >
                            {gettext('All')}
                          </Button>
                          <Button
                            size="small"
                            intent="danger"
                            onClick={() => handleGrantAllRow(rKey, false)}
                          >
                            {gettext('Revoke All')}
                          </Button>
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Live DCL SQL Preview */}
      {(showPreview || pendingChanges.length > 0) && previewSql && (
        <div
          data-cdeadmin-qa-key="object-permissions-sql-preview"
          style={{
            border: '1px solid var(--sr-border-default)',
            borderRadius: 8,
            padding: '10px 12px',
            background: 'var(--sr-surface-subtle)',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
          }}
        >
          <div style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--sr-text-secondary)'}}>
            {gettext('Staged Native DCL Statements (%s)', pendingChanges.length)}
          </div>
          <pre
            style={{
              margin: 0,
              fontFamily: 'var(--sr-font-mono, monospace)',
              fontSize: '0.78rem',
              whiteSpace: 'pre-wrap',
              overflowX: 'auto',
            }}
          >
            {previewSql}
          </pre>
        </div>
      )}
    </Box>
  );
}

ObjectPermissionsMatrix.propTypes = {
  boundNodeData: PropTypes.object,
  resource: PropTypes.object,
  sid: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  databaseTargetId: PropTypes.string,
  engine: PropTypes.string,
  objectKind: PropTypes.string,
  schema: PropTypes.string,
  objectName: PropTypes.string,
  initialPrivileges: PropTypes.array,
  fetchImpl: PropTypes.func,
  compact: PropTypes.bool,
  onApplied: PropTypes.func,
};
