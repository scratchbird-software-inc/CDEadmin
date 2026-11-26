/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Grants on one object, driven by the engine's security.json (design
 * Decision 21). The rows are the provider's own grant resources for the
 * object, read through the descriptor's `grants.listing` (which native field
 * names what, and what each stored privilege code means). Granting and
 * revoking are the engine's declared operations, opened with the object fixed
 * so they cannot be pointed at another one, and they run through the same
 * reviewed plan and SQL tab as every other change. No engine names appear
 * here; an engine that lacks column grants or a grantor simply has no such
 * field in its operation.
 */

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {Banner} from '../feedback/Indicators';
import {EmptyState} from '../feedback/EmptyState';
import {ProgressOverlay} from '../feedback/ProgressOverlay';
import OperationDialog from '../objects/OperationDialog';
import {makePost, resourceNative} from '../objects/ProviderObjectEditorHost';
import {descriptorClient, visualAdminCalls} from '../objects/DescriptorClient';
import {listResources} from './providerList';

/** Whether the descriptor offers an object-grants view for this kind of object. */
export function objectGrantsOffered(bundle, objectKind) {
  const security = bundle?.security;
  if(security?.grants?.status !== 'complete' || !security.grants.listing) return false;
  const grantable = bundle.options?.dialect?.[security.grants.grantable_kinds];
  return Array.isArray(grantable) && grantable.includes(objectKind);
}

/** 'user'@'host' (the quoting a server prints a grantee with) split into its two parts. */
export function parseAccount(text) {
  const match = /^(?:'((?:[^']|'')*)'|`((?:[^`]|``)*)`|([^@]*))@(?:'((?:[^']|'')*)'|`((?:[^`]|``)*)`|(.*))$/.exec(String(text ?? ''));
  if(!match) return {user: String(text ?? ''), host: ''};
  const unquote = (quoted, ticked, bare, doubled) => (quoted ?? ticked ?? bare ?? '').replaceAll(doubled, doubled[0]);
  return {user: unquote(match[1], match[2], match[3], '\'\'').replaceAll('``', '`'),
    host: unquote(match[4], match[5], match[6], '\'\'').replaceAll('``', '`')};
}

/** Grants carried on the object itself (listing.embedded): its own entry in the listing holds one row per grant,
 *  and its child resources (columns) hold theirs. isDefault says the rows are the family's default ACL. */
export function embeddedGrants(listing, resources, objectId, objectKind, objectName, path) {
  const spec = listing.embedded;
  const object = resources.find((resource) => objectId && resource.resource_id === objectId)
    || resources.find((resource) => resource.resource_kind === objectKind && resource.display_name === objectName
      && (!path || String(resource.display_path || []).endsWith(String(path))));
  if(!object) return {rows: [], isDefault: false};
  const rowOf = (native, column) => ({...toRow(listing, native, (stored) => stored), column: column || ''});
  const own = (resourceNative(object)[spec.native_field] || []).map((native) => rowOf(native));
  const objectPath = object.display_path || [];
  const children = (spec.children || []).flatMap((child) => resources
    .filter((resource) => resource.resource_kind === child.kind
      && (resource.display_path || []).length === objectPath.length + 1
      && objectPath.every((part, index) => resource.display_path[index] === part))
    .flatMap((resource) => (resourceNative(resource)[child.native_field] || [])
      .map((native) => rowOf(native, child.column ? resource.display_name : ''))));
  return {rows: [...own, ...children], isDefault: Boolean(spec.default_flag && resourceNative(object)[spec.default_flag])};
}

/** The grant rows for one object, read through the descriptor's listing.
 *  objectPath is the object's path in the tree (outermost first), whose tail the listing's fields match. */
export function grantRows(grants, resources, objectName, objectPath, objectKind, objectId) {
  const listing = grants.listing;
  if(listing.embedded) {
    return embeddedGrants(listing, resources, objectId, objectKind, objectName, objectPath).rows
      .sort((a, b) => `${a.grantee}:${a.privilege}:${a.column}`.localeCompare(`${b.grantee}:${b.privilege}:${b.column}`));
  }
  const path = objectPath?.length ? objectPath : [objectName];
  const spec = listing.kinds?.[objectKind];
  const objectKey = listing.object_field || listing.object_fields?.at(-1);
  // Without codes the engine stores privilege names directly.
  const codes = listing.privilege_codes;
  const privilegeName = (stored) => (codes ? codes[stored] : stored);
  const onObject = (native) => {
    if(spec) {
      return spec.scopes.includes(native[listing.scope_field])
        && spec.fields.slice(-path.length).every((field, index, fields) => native[field] === path[path.length - fields.length + index])
        && Object.entries(spec.where || {}).every(([field, value]) => native[field] === value);
    }
    return native[objectKey] === objectName;
  };
  return resources
    .filter((resource) => resource.resource_kind === grants.grant_kind)
    .map((resource) => resourceNative(resource))
    .filter((native) => onObject(native) && (!codes || Object.hasOwn(codes, native[listing.privilege_field])))
    .map((native) => toRow(listing, native, privilegeName))
    .sort((a, b) => `${a.grantee}:${a.privilege}:${a.column}`.localeCompare(`${b.grantee}:${b.privilege}:${b.column}`));
}

function toRow(listing, native, privilegeName) {
  const kindCode = listing.grantee_kind_field ? native[listing.grantee_kind_field] : undefined;
  return {
    grantee: native[listing.grantee_field],
    granteeKind: listing.grantee_kinds?.[String(kindCode)] ?? null,
    privilege: privilegeName(native[listing.privilege_field]),
    stored: native[listing.privilege_field],
    scope: listing.scope_field ? native[listing.scope_field] : undefined,
    column: listing.column_field ? native[listing.column_field] || '' : '',
    grantOption: listing.grant_option_field
      ? native[listing.grant_option_field] === listing.grant_option_equals : null,
    grantor: listing.grantor_field ? native[listing.grantor_field] || '' : '',
    native,
  };
}

/** How the selected principal is spelled in a grant row's grantee field. */
export function granteeSpelling(security, principal, resource) {
  const native = resourceNative(resource);
  const template = security.grants?.listing?.grantee_template;
  const first = (principal.identity || ['name'])[0];
  if(!template) return String(native[first] ?? resource?.display_name ?? '');
  return template.replace(/\{(\w+)\}/g, (_, field) => String(native[field] ?? ''));
}

/** The object a grant row is on, named through the descriptor's own fields (empty for a server-wide grant). */
function objectOf(listing, native) {
  if(listing.object_field) return native[listing.object_field] || '';
  const spec = Object.values(listing.kinds || {}).find((kind) => kind.scopes.includes(native[listing.scope_field]));
  const fields = spec ? spec.fields : (listing.object_fields || []);
  return fields.map((field) => native[field]).filter(Boolean).join('.');
}

/** Every grant a principal holds, across all scopes (the only place global grants show).
 *  principalKind separates a user from a role of the same name where the engine stores a grantee type. */
export function heldRows(grants, resources, grantee, principalKind) {
  const listing = grants.listing;
  const codes = listing.privilege_codes;
  const privilegeName = (stored) => (codes ? codes[stored] : stored);
  if(listing.embedded) {
    const spec = listing.embedded;
    return resources.flatMap((resource) => {
      const own = spec.native_field && resource.resource_kind !== grants.grant_kind ? resourceNative(resource)[spec.native_field] : null;
      const child = (spec.children || []).find((item) => item.kind === resource.resource_kind);
      const rows = own || (child ? resourceNative(resource)[child.native_field] : null);
      if(!Array.isArray(rows)) return [];
      return rows.filter((native) => native[listing.grantee_field] === grantee).map((native) => ({
        ...toRow(listing, native, privilegeName), object: (resource.display_path || [resource.display_name]).slice(1).join('.'),
        scope: resource.resource_kind, column: ''}));
    }).filter((row) => !(principalKind && row.granteeKind) || row.granteeKind === principalKind.toUpperCase())
      .sort((a, b) => `${a.object}:${a.privilege}`.localeCompare(`${b.object}:${b.privilege}`));
  }
  return resources
    .filter((resource) => resource.resource_kind === grants.grant_kind)
    .map((resource) => resourceNative(resource))
    .filter((native) => native[listing.grantee_field] === grantee
      && (!codes || Object.hasOwn(codes, native[listing.privilege_field])))
    .map((native) => ({...toRow(listing, native, privilegeName), object: objectOf(listing, native)}))
    .filter((row) => !(principalKind && row.granteeKind) || row.granteeKind === principalKind.toUpperCase())
    .sort((a, b) => `${a.scope}:${a.object}:${a.privilege}:${a.column}`.localeCompare(`${b.scope}:${b.object}:${b.privilege}:${b.column}`));
}

/** What a principal holds inside databases, for an engine whose grants live in each database (listing.held_across).
 *  `load(target)` lists one database's resources and rejects when it cannot (not connected); those databases are
 *  named in `skipped`, never silently left out. Only successful listings are cached. A database's own entry is
 *  not repeated here: the server-scope listing already carries it. */
export async function heldAcrossDatabases(grants, resources, grantee, principalKind, load, cache = new Map(), limit = 25) {
  const spec = grants.listing?.held_across;
  if(!spec) return {rows: [], skipped: [], truncated: 0};
  // The fields are dotted paths into the listed database's native data (PostgreSQL: catalog_metadata.did).
  const read = (resource, path) => String(path).split('.').reduce((value, key) => value?.[key], resourceNative(resource));
  const eligible = resources.filter((resource) => resource.resource_kind === spec.kind
    && !(spec.skip_field && read(resource, spec.skip_field) === spec.skip_equals));
  const rows = [];
  const skipped = [];
  for(const database of eligible.slice(0, limit)) {
    const id = read(database, spec.id_field);
    if(id === undefined || id === null) { skipped.push(database.display_name); continue; }
    const target = `${spec.target_prefix}${id}`;
    let listing = cache.get(target);
    if(listing === undefined) {
      try { listing = await load(target); cache.set(target, listing); } catch(error) { listing = null; }
    }
    if(listing === null) { skipped.push(database.display_name); continue; }
    rows.push(...heldRows(grants, listing, grantee, principalKind)
      .filter((row) => row.scope !== spec.kind)
      .map((row) => ({...row, database: database.display_name})));
  }
  return {rows, skipped, truncated: Math.max(0, eligible.length - limit)};
}

/** The dialog values a grants view fixes for one object (and one listed row), as the descriptor's dialog maps them. */
export function dialogValues(grants, operation, objectKind, objectName, objectPath, row, objectNative) {
  const dialog = grants.dialog || {};
  const fixed = {...(dialog.fixed || {})};
  const objectType = dialog.object_type_by_kind?.[objectKind] ?? objectTypeValue(operation, objectKind);
  if(dialog.object_type && objectType) fixed[dialog.object_type] = objectType;
  const path = objectPath?.length ? objectPath : [objectName];
  fixed[dialog.object_by_kind?.[objectKind] || dialog.object] = objectName;
  const qualifiers = dialog.qualifiers_by_kind?.[objectKind] ?? dialog.qualifiers ?? [];
  qualifiers.forEach((field, index) => {
    const offset = path.length - 1 - (qualifiers.length - index);
    if(offset >= 0 && !dialog.object_by_kind?.[objectKind]) fixed[field] = path[offset];
  });
  const named = dialog.object_arguments;
  if(named && objectNative?.[named.native_field] != null) fixed[named.field] = String(objectNative[named.native_field]);
  const target = dialog.row;
  if(row && target) {
    if(target.grantee_kind_field && row.granteeKind) fixed[target.grantee_kind_field] = row.granteeKind;
    if(target.grantee_field && row.granteeKind) fixed[target.grantee_field] = row.grantee;
    if(target.grantee_grid) {
      const grid = target.grantee_grid;
      // With a host column the grantee is an account string to split; otherwise it is the name itself.
      fixed[grid.field] = [grid.host
        ? {[grid.user]: parseAccount(row.grantee).user, [grid.host]: parseAccount(row.grantee).host}
        : {[grid.user]: row.grantee}];
    }
    if(target.privileges_field) {
      const item = target.privilege_key
        ? {[target.privilege_key]: row.privilege, ...(row.column && target.columns_key ? {[target.columns_key]: [row.column]} : {})}
        : row.privilege;
      fixed[target.privileges_field] = [item];
    }
  }
  return fixed;
}

/** The operation with its privilege choices limited to what the engine grants on this kind of object
 *  (the dialect's per-kind list the descriptor names as grants.object_privileges); ALL stays as it is. */
export function narrowedOperation(bundle, operation, objectKind) {
  const grants = bundle?.security?.grants;
  const row = grants?.dialog?.row;
  const byKind = grants?.object_privileges ? bundle.options?.dialect?.[grants.object_privileges] : null;
  const allowed = byKind && !Array.isArray(byKind) ? byKind[objectKind] : null;
  if(!operation || !Array.isArray(allowed) || !row?.privileges_field || !row.privilege_key) return operation;
  // A column list is offered only where the engine grants on columns of this kind of object.
  const columnsAllowed = !grants.column_privileges || Object.hasOwn(grants.column_privileges, objectKind);
  const keep = (option) => {
    const value = String(typeof option === 'object' ? option.value : option);
    return value.toUpperCase().startsWith('ALL') || allowed.includes(value);
  };
  return {...operation, fields: (operation.fields || []).map((field) => (field.field_id === row.privileges_field
    ? {...field, columns: (field.columns || [])
      .filter((column) => columnsAllowed || column.field_id !== row.columns_key)
      .map((column) => (column.field_id === row.privilege_key && Array.isArray(column.options)
        ? {...column, options: column.options.filter(keep)} : column))}
    : field))};
}

/** Whether one listed grant can be revoked in a click: the dialog needs to know who and (for a column grant) which columns. */
export function canRevoke(grants, row) {
  const target = grants.dialog?.row;
  if(!target) return false;
  const named = target.grantee_grid || (target.grantee_kind_field && row.granteeKind);
  return Boolean(named) && (!row.column || Boolean(target.columns_key));
}

/** The operation's own spelling of an object kind (its object_type option matching the resource kind). */
export function objectTypeValue(operation, objectKind) {
  const field = (operation?.fields || []).find((item) => item.field_id === 'object_type');
  const wanted = String(objectKind).replace(/-/g, ' ').toLowerCase();
  const match = (field?.options || []).map((option) => (typeof option === 'object' ? option.value : option))
    .find((value) => String(value).toLowerCase() === wanted);
  return match ?? null;
}

export default function DescriptorObjectGrants({
  api, endpointUrl, engine, version, databaseTargetId = '', objectKind, objectName, objectPath, objectId, onApplied, onAuthRequired,
}) {
  const client = useMemo(() => descriptorClient(api), [api]);
  const post = useMemo(() => makePost(api, endpointUrl, databaseTargetId || undefined, {onAuthRequired}),
    [api, endpointUrl, databaseTargetId, onAuthRequired]);
  const [state, setState] = useState({status: 'loading', bundle: null, resources: [], error: null});
  const [refresh, setRefresh] = useState(0);
  const [dialog, setDialog] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const bundle = await client.bundle(engine, {version});
        const resources = objectGrantsOffered(bundle, objectKind) ? await listResources(post) : [];
        if(!cancelled) setState({status: 'ready', bundle, resources, error: null});
      } catch(error) {
        if(!cancelled) setState({status: 'error', bundle: null, resources: [], error: error?.message || String(error)});
      }
    })();
    return () => { cancelled = true; };
  }, [client, engine, version, post, objectKind, refresh]);

  const grants = state.bundle?.security?.grants;
  // Where the object sits in the tree: given, or read from the object's own entry in the listing
  // (a tree node carries its id but not its path).
  const path = useMemo(() => {
    if(objectPath?.length) return objectPath;
    const found = state.resources.find((resource) => objectId && resource.resource_id === objectId)
      || state.resources.find((resource) => resource.resource_kind === objectKind && resource.display_name === objectName);
    return Array.isArray(found?.display_path) ? found.display_path.map(String) : undefined;
  }, [objectPath, objectId, objectKind, objectName, state.resources]);
  const rows = useMemo(() => (grants && state.status === 'ready' && objectGrantsOffered(state.bundle, objectKind)
    ? grantRows(grants, state.resources, objectName, path, objectKind, objectId) : []), [grants, state, objectKind, objectName, path, objectId]);
  const isDefault = useMemo(() => Boolean(grants?.listing?.embedded && state.status === 'ready'
    && embeddedGrants(grants.listing, state.resources, objectId, objectKind, objectName, path).isDefault),
  [grants, state, objectKind, objectName, path, objectId]);
  const operations = useMemo(() => Object.fromEntries(
    (state.bundle?.kinds?.[grants?.grant_kind]?.operations || []).map((op) => [op.operation_id, op])), [state.bundle, grants]);

  const open = useCallback((operationId, row) => {
    const operation = narrowedOperation(state.bundle, operations[operationId], objectKind);
    const objectNative = resourceNative(state.resources.find((resource) => objectId && resource.resource_id === objectId)
      || state.resources.find((resource) => resource.resource_kind === objectKind && resource.display_name === objectName));
    const fixed = dialogValues(grants, operation, objectKind, objectName, path, row, objectNative);
    setDialog({operation, fixed, calls: visualAdminCalls(post, {
      resourceKind: grants.grant_kind, operationId, target: null})});
  }, [operations, state.bundle, state.resources, objectKind, objectName, objectId, path, post, grants]);

  const applied = useCallback((result) => {
    setDialog(null);
    setRefresh((count) => count + 1);
    onApplied?.(result);
  }, [onApplied]);

  if(state.status === 'loading') return <Box sx={{position: 'relative', minHeight: 120}}><ProgressOverlay message={gettext('Loading grants')} /></Box>;
  if(state.status === 'error') return <Box sx={{p: 2}}><Banner status="error">{state.error}</Banner></Box>;
  if(!objectGrantsOffered(state.bundle, objectKind)) {
    return <EmptyState message={gettext('This engine does not grant on this kind of object.')} />;
  }
  const listing = grants.listing;
  const editable = operations.grant && operations.revoke;
  return <Box component="section" aria-label={gettext('Grants')} sx={{p: 1, display: 'flex', flexDirection: 'column', gap: 1}}>
    {editable && <Box sx={{display: 'flex', gap: 1}}>
      <Button intent="primary" onClick={() => open('grant')}>{gettext('Grant privileges')}</Button>
      <Button intent="neutral" onClick={() => open('revoke')}>{gettext('Revoke privileges')}</Button>
    </Box>}
    {isDefault && <Banner status="info">{gettext('No grants are stored for this object, so these are its default privileges.')}</Banner>}
    {rows.length === 0
      ? <Box sx={{fontSize: '0.8125rem'}}>{gettext('No grants on %s.', objectName)}</Box>
      : <Box component="table" aria-label={gettext('Granted privileges')}
        sx={{borderCollapse: 'collapse', fontSize: '0.8125rem', width: '100%'}}>
        <thead><tr>
          <Box component="th" sx={{textAlign: 'left', pr: 2}}>{gettext('Grantee')}</Box>
          <Box component="th" sx={{textAlign: 'left', pr: 2}}>{gettext('Privilege')}</Box>
          {listing.column_field && <Box component="th" sx={{textAlign: 'left', pr: 2}}>{gettext('Column')}</Box>}
          {listing.grant_option_field && <Box component="th" sx={{textAlign: 'left', pr: 2}}>{gettext('Grant option')}</Box>}
          {listing.grantor_field && <Box component="th" sx={{textAlign: 'left', pr: 2}}>{gettext('Granted by')}</Box>}
          <th />
        </tr></thead>
        <tbody>{rows.map((row) => <tr key={`${row.grantee}:${row.privilege}:${row.column}`}>
          <Box component="td" sx={{pr: 2}}>{row.grantee}</Box>
          <Box component="td" sx={{pr: 2}}>{row.privilege}</Box>
          {listing.column_field && <Box component="td" sx={{pr: 2}}>{row.column}</Box>}
          {listing.grant_option_field && <Box component="td" sx={{pr: 2}}>{row.grantOption ? gettext('Yes') : gettext('No')}</Box>}
          {listing.grantor_field && <Box component="td" sx={{pr: 2}}>{row.grantor}</Box>}
          <td>{editable && canRevoke(grants, row) && <Button intent="neutral"
            aria-label={gettext('Revoke %s from %s', row.privilege, row.grantee)}
            onClick={() => open('revoke', row)}>{gettext('Revoke')}</Button>}</td>
        </tr>)}</tbody>
      </Box>}
    {dialog && <OperationDialog open operation={dialog.operation} targetName={objectName} fixedValues={dialog.fixed}
      plan={dialog.calls.plan} apply={dialog.calls.apply} onClose={() => setDialog(null)} onApplied={applied} />}
  </Box>;
}

DescriptorObjectGrants.propTypes = {
  api: PropTypes.object.isRequired,
  endpointUrl: PropTypes.string.isRequired,
  engine: PropTypes.string.isRequired,
  version: PropTypes.string,
  databaseTargetId: PropTypes.string,
  objectKind: PropTypes.string.isRequired,
  objectName: PropTypes.string.isRequired,
  objectPath: PropTypes.arrayOf(PropTypes.string),
  objectId: PropTypes.string,
  onApplied: PropTypes.func,
  onAuthRequired: PropTypes.func,
};
