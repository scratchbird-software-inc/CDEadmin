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

/** The object-grant rows for one object, read through the descriptor's listing. */
export function grantRows(grants, resources, objectName) {
  const listing = grants.listing;
  // A grant names its object by one native field, or by a path whose last field is the object's own name.
  const objectKey = listing.object_field || listing.object_fields.at(-1);
  // Without codes the engine stores privilege names directly.
  const codes = listing.privilege_codes;
  const privilegeName = (stored) => (codes ? codes[stored] : stored);
  return resources
    .filter((resource) => resource.resource_kind === grants.grant_kind)
    .map((resource) => resourceNative(resource))
    .filter((native) => native[objectKey] === objectName
      && (!codes || Object.hasOwn(codes, native[listing.privilege_field])))
    .map((native) => {
      const kindCode = listing.grantee_kind_field ? native[listing.grantee_kind_field] : undefined;
      return {
        grantee: native[listing.grantee_field],
        granteeKind: listing.grantee_kinds?.[String(kindCode)] ?? null,
        privilege: privilegeName(native[listing.privilege_field]),
        column: listing.column_field ? native[listing.column_field] || '' : '',
        grantOption: listing.grant_option_field
          ? native[listing.grant_option_field] === listing.grant_option_equals : null,
        grantor: listing.grantor_field ? native[listing.grantor_field] || '' : '',
      };
    })
    .sort((a, b) => `${a.grantee}:${a.privilege}:${a.column}`.localeCompare(`${b.grantee}:${b.privilege}:${b.column}`));
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
  api, endpointUrl, engine, version, databaseTargetId = '', objectKind, objectName, onApplied, onAuthRequired,
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
  const rows = useMemo(() => (grants && state.status === 'ready' && objectGrantsOffered(state.bundle, objectKind)
    ? grantRows(grants, state.resources, objectName) : []), [grants, state, objectKind, objectName]);
  const operations = useMemo(() => Object.fromEntries(
    (state.bundle?.kinds?.[grants?.grant_kind]?.operations || []).map((op) => [op.operation_id, op])), [state.bundle, grants]);

  const open = useCallback((operationId, row) => {
    const operation = operations[operationId];
    const objectType = objectTypeValue(operation, objectKind);
    const fixed = {privilege_scope: 'object', ...(objectType ? {object_type: objectType} : {}), object_name: objectName};
    if(row?.granteeKind) Object.assign(fixed, {principal_kind: row.granteeKind, principal: row.grantee, privileges: [row.privilege]});
    setDialog({operation, fixed, calls: visualAdminCalls(post, {
      resourceKind: grants.grant_kind, operationId, target: null})});
  }, [operations, objectKind, objectName, post, grants]);

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
          <td>{editable && row.granteeKind && !row.column && <Button intent="neutral"
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
  onApplied: PropTypes.func,
  onAuthRequired: PropTypes.func,
};
