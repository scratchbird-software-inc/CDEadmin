/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Security Manager driven by the engine's security.json (design Decision 21).
 *
 * It carries no fields and no engine branches. It lists the principals the
 * descriptor declares for the scope, opens one in the engine's own role-family
 * editor (ProviderObjectEditorHost) and offers the engine's declared
 * membership operations. Names, scope and what exists at all come from the
 * descriptor; everything that is edited comes from the provider's own forms
 * and operations, through the same reviewed plan and SQL tab as any editor.
 */

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextField} from '../primitives/Field';
import {Banner} from '../feedback/Indicators';
import {EmptyState} from '../feedback/EmptyState';
import {ProgressOverlay} from '../feedback/ProgressOverlay';
import OperationDialog from '../objects/OperationDialog';
import ProviderObjectEditorHost, {makePost, resourceNative} from '../objects/ProviderObjectEditorHost';
import {descriptorClient, visualAdminCalls} from '../objects/DescriptorClient';
import {operationContext} from '../objects/descriptors';
import {listResources, scopedEndpointUrl} from './providerList';
import {granteeSpelling, heldAcrossDatabases, heldRows} from './DescriptorObjectGrants';

/** The name a roster row shows: the descriptor's identity fields, joined. */
export function principalLabel(principal, resource) {
  const native = resourceNative(resource);
  const parts = (principal.identity || [])
    .map((field) => native[field] ?? resource?.[field])
    .filter((part) => part !== undefined && part !== null && part !== '');
  if(parts.length > 1) return parts.join('@');
  return resource?.display_name || parts[0] || '';
}

/** The notices that apply: the descriptor's declared failure patterns found in what the provider reported. */
export function activeAccessNotices(security, resources) {
  return (security?.access_notices || []).filter((notice) => resources
    .filter((resource) => resource.resource_kind === notice.source.kind)
    .some((resource) => {
      const rows = notice.source.native_field.split('.').reduce((node, key) => node?.[key], resourceNative(resource));
      return Array.isArray(rows) && rows.some((row) => Object.entries(notice.match).every(([field, wanted]) =>
        (Array.isArray(wanted) ? wanted : [wanted]).includes(row?.[field])));
    }));
}

function cell(column, row) {
  const value = row?.[column.field];
  if(Object.hasOwn(column, 'equals')) return value === column.equals ? gettext('Yes') : gettext('No');
  if(column.boolean) return value ? gettext('Yes') : gettext('No');
  return value === undefined || value === null ? '' : String(value);
}

function Memberships({listing, resource}) {
  const rows = resourceNative(resource)?.[listing.native_field];
  if(!Array.isArray(rows) || rows.length === 0) return null;
  const title = gettext(listing.title || 'Memberships');
  return <Box component="section" aria-label={title} sx={{p: 1}}>
    {listing.title && <Box sx={{fontWeight: 600, mb: 0.5}}>{title}</Box>}
    <Box component="table" sx={{borderCollapse: 'collapse', fontSize: '0.8125rem', width: '100%'}}>
      <thead><tr>{listing.columns.map((column) =>
        <Box component="th" key={column.field} sx={{textAlign: 'left', pr: 2}}>{gettext(column.label)}</Box>)}</tr></thead>
      <tbody>{rows.map((row, index) =>
        <tr key={`${row[listing.columns[0].field]}:${index}`}>{listing.columns.map((column) =>
          <Box component="td" key={column.field} sx={{pr: 2}}>{cell(column, row)}</Box>)}</tr>)}</tbody>
    </Box>
  </Box>;
}

function Held({grants, resources, grantee, principalKind, across}) {
  const own = heldRows(grants, resources, grantee, principalKind);
  const inDatabases = across?.rows || [];
  const rows = [...own, ...inDatabases];
  const skipped = across?.skipped || [];
  const note = across?.status === 'loading' ? gettext('Reading the connected databases…')
    : skipped.length > 0 ? gettext('Not included, because they could not be read (connect them to include their objects): %s.', skipped.join(', '))
      : null;
  if(rows.length === 0 && !note) return null;
  const listing = grants.listing;
  const withDatabase = Boolean(grants.listing?.held_across);
  return <Box component="section" aria-label={gettext('Privileges held')} sx={{p: 1}}>
    <Box sx={{fontWeight: 600, mb: 0.5}}>{gettext('Privileges held')}</Box>
    {rows.length > 0 && <Box component="table" sx={{borderCollapse: 'collapse', fontSize: '0.8125rem', width: '100%'}}>
      <thead><tr>
        {[...(withDatabase ? ['Database'] : []), 'Scope', 'Object', 'Privilege', ...(listing.column_field ? ['Column'] : []),
          ...(listing.grant_option_field ? ['Grant option'] : [])].map((label) =>
          <Box component="th" key={label} sx={{textAlign: 'left', pr: 2}}>{gettext(label)}</Box>)}
      </tr></thead>
      <tbody>{rows.map((row, index) => <tr key={`${row.database || ''}:${row.scope}:${row.object}:${row.privilege}:${row.column}:${index}`}>
        {withDatabase && <Box component="td" sx={{pr: 2}}>{row.database || ''}</Box>}
        <Box component="td" sx={{pr: 2}}>{row.scope}</Box>
        <Box component="td" sx={{pr: 2}}>{row.object}</Box>
        <Box component="td" sx={{pr: 2}}>{row.privilege}</Box>
        {listing.column_field && <Box component="td" sx={{pr: 2}}>{row.column}</Box>}
        {listing.grant_option_field && <Box component="td" sx={{pr: 2}}>{row.grantOption ? gettext('Yes') : gettext('No')}</Box>}
      </tr>)}</tbody>
    </Box>}
    {note && <Box sx={{fontSize: '0.75rem', mt: 0.5}}>{note}{across?.truncated > 0 ? ' ' + gettext('%s more databases were not read.', across.truncated) : ''}</Box>}
  </Box>;
}

Held.propTypes = {grants: PropTypes.object.isRequired, resources: PropTypes.array.isRequired, grantee: PropTypes.string.isRequired, principalKind: PropTypes.string, across: PropTypes.object};

Memberships.propTypes = {listing: PropTypes.object.isRequired, resource: PropTypes.object};

export default function DescriptorSecurityManager({
  api, endpointUrl, engine, version, scope = 'server', databaseTargetId = '',
  initialKind, initialPrincipalId, endpointLabel, onAuthRequired,
}) {
  const client = useMemo(() => descriptorClient(api), [api]);
  const post = useMemo(() => makePost(api, endpointUrl, databaseTargetId || undefined, {onAuthRequired}),
    [api, endpointUrl, databaseTargetId, onAuthRequired]);
  const [state, setState] = useState({status: 'loading', bundle: null, resources: [], error: null});
  const [refresh, setRefresh] = useState(0);
  const [filter, setFilter] = useState('');
  const [activeKind, setActiveKind] = useState(initialKind || null);
  const [selection, setSelection] = useState(initialPrincipalId
    ? {mode: 'alter', id: initialPrincipalId} : null);
  const [dialog, setDialog] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const bundle = await client.bundle(engine, {version});
        const resources = await listResources(post);
        if(!cancelled) setState({status: 'ready', bundle, resources, error: null});
      } catch(error) {
        if(!cancelled) setState({status: 'error', bundle: null, resources: [], error: error?.message || String(error)});
      }
    })();
    return () => { cancelled = true; };
  }, [client, engine, version, post, refresh]);

  const security = state.bundle?.security;
  const principals = useMemo(
    () => (security?.principals || []).filter((item) => item.scope === scope),
    [security, scope]);
  // A kind merged into another has no roster of its own; it only adds a create action.
  const rostered = useMemo(() => principals.filter((item) => !item.roster?.merged_into), [principals]);
  const principal = rostered.find((item) => item.kind === activeKind) || rostered[0];
  const kind = principal?.kind;
  const creators = useMemo(() => (principal
    ? [principal, ...principals.filter((item) => item.roster?.merged_into === principal.kind)] : []),
  [principal, principals]);

  const notices = useMemo(() => activeAccessNotices(security, state.resources), [security, state.resources]);

  const roster = useMemo(() => {
    if(!principal) return [];
    const needle = filter.trim().toLowerCase();
    return state.resources
      .filter((resource) => resource.resource_kind === principal.kind)
      .map((resource) => ({resource, label: principalLabel(principal, resource),
        marks: (principal.roster?.markers || [])
          .filter((marker) => resourceNative(resource)?.[marker.field] === marker.equals)
          .map((marker) => gettext(marker.label))}))
      .filter(({label}) => !needle || label.toLowerCase().includes(needle))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [state.resources, principal, filter]);

  const selected = selection?.mode === 'alter'
    ? state.resources.find((resource) => resource.resource_id === selection.id
      || (resource.resource_kind === kind && resource.display_name === selection.id))
    : null;

  const membershipOperations = useMemo(() => {
    const membership = security?.membership;
    const reachable = membership && (membership.kind === kind
      || principals.some((item) => item.kind === membership.kind && item.roster?.merged_into === kind));
    if(!reachable) return [];
    return (state.bundle?.kinds?.[membership.kind]?.operations || [])
      .filter((op) => op.menu?.category === 'security' && op.available !== false)
      .sort((a, b) => (a.menu?.order ?? 0) - (b.menu?.order ?? 0));
  }, [security, kind, principals, state.bundle]);

  // Membership operations target the membership kind's own resource; when its roster is merged
  // into the selected kind they are the same account listed under that kind.
  const membershipTarget = selected && security?.membership && security.membership.kind !== kind
    ? state.resources.find((resource) => resource.resource_kind === security.membership.kind
      && resource.display_name === selected.display_name) || null
    : selected;

  const applied = useCallback(() => {
    setDialog(null);
    setRefresh((count) => count + 1);
  }, []);

  // Where an engine keeps grants inside each database, what a principal holds there is read from the
  // connected databases one at a time (a database that cannot be read is named, never dropped silently).
  const acrossCache = useRef(new Map());
  const [across, setAcross] = useState(null);
  useEffect(() => { acrossCache.current = new Map(); }, [refresh, post]);
  const heldGrantee = selected && principal && security?.grants?.listing?.held_across && scope === 'server'
    ? granteeSpelling(security, principal, selected) : null;
  useEffect(() => {
    if(!heldGrantee || state.status !== 'ready') { setAcross(null); return undefined; }
    let cancelled = false;
    setAcross({status: 'loading', rows: [], skipped: [], truncated: 0});
    heldAcrossDatabases(security.grants, state.resources, heldGrantee, principal.kind,
      (target) => listResources(makePost(api, scopedEndpointUrl(endpointUrl, target), target, {onAuthRequired})), acrossCache.current)
      .then((result) => { if(!cancelled) setAcross({status: 'ready', ...result}); })
      .catch(() => { if(!cancelled) setAcross(null); });
    return () => { cancelled = true; };
  }, [heldGrantee, state.status, state.resources, security, principal, api, endpointUrl, onAuthRequired, refresh]);

  if(state.status === 'loading') {
    return <Box sx={{position: 'relative', minHeight: 160}}><ProgressOverlay message={gettext('Loading security')} /></Box>;
  }
  if(state.status === 'error') {
    return <Box sx={{p: 2}}><Banner status="error">{state.error}</Banner></Box>;
  }
  if(!principal) {
    return <EmptyState message={security?.reason
      || gettext('This engine has no %s principals.', scope === 'database' ? gettext('database') : gettext('server'))} />;
  }

  const creating = selection?.mode === 'create'
    ? creators.find((item) => item.kind === selection.kind) || principal : null;
  return <Box component="section" aria-label={gettext('Security Manager')}
    sx={{display: 'flex', height: '100%', minHeight: 0}}>
    <Box component="nav" aria-label={gettext('Principals')}
      sx={{width: 300, flex: 'none', display: 'flex', flexDirection: 'column', gap: 1, p: 1, overflow: 'auto'}}>
      {endpointLabel && <Box sx={{fontWeight: 600}}>{endpointLabel}</Box>}
      {rostered.length > 1 && <Box role="group" aria-label={gettext('Principal kind')} sx={{display: 'flex', gap: 1}}>
        {rostered.map((item) => <Button key={item.kind} intent={item.kind === kind ? 'primary' : 'neutral'}
          aria-pressed={item.kind === kind}
          onClick={() => { setActiveKind(item.kind); setSelection(null); setFilter(''); }}>
          {gettext(item.plural_label)}
        </Button>)}
      </Box>}
      {creators.map((item) => <Button key={item.kind} intent="primary"
        onClick={() => setSelection({mode: 'create', kind: item.kind})}>{gettext('New %s', gettext(item.label).toLowerCase())}</Button>)}
      <TextField label={gettext('Filter')} size="small" value={filter}
        onChange={(event) => setFilter(event.target.value)} />
      {roster.length === 0
        ? <Box sx={{fontSize: '0.8125rem'}}>{gettext('No %s found.', gettext(principal.plural_label).toLowerCase())}</Box>
        : <Box component="ul" aria-label={gettext(principal.plural_label)} sx={{listStyle: 'none', m: 0, p: 0}}>
          {roster.map(({resource, label, marks}) => <li key={resource.resource_id}>
            <Button intent={selected?.resource_id === resource.resource_id ? 'primary' : 'neutral'}
              aria-current={selected?.resource_id === resource.resource_id ? 'true' : undefined}
              onClick={() => setSelection({mode: 'alter', id: resource.resource_id})}>
              {label}{marks.length > 0 && <Box component="span" sx={{ml: 1, fontSize: '0.75rem', opacity: 0.8}}>{marks.join(', ')}</Box>}
            </Button>
          </li>)}
        </Box>}
    </Box>
    <Box sx={{flex: 1, minWidth: 0, overflow: 'auto'}}>
      {notices.map((notice) => <Box key={notice.id} sx={{p: 1}}><Banner status="warning">{gettext(notice.message)}</Banner></Box>)}
      {!selection && <EmptyState message={gettext('Select a %s or create one.', gettext(principal.label).toLowerCase())} />}
      {creating && <ProviderObjectEditorHost key={`create:${creating.kind}`}
        api={api} endpointUrl={endpointUrl} engine={engine} version={version} resourceKind={creating.kind}
        databaseTargetId={databaseTargetId || undefined} mode="create"
        initialRecord={creating.variant ? {[creating.variant.field_id]: creating.variant.value} : {}}
        onAuthRequired={onAuthRequired} onClose={() => setSelection(null)} onApplied={() => { setSelection(null); applied(); }} />}
      {selected && <Box>
        <Box sx={{display: 'flex', gap: 1, p: 1, flexWrap: 'wrap'}}>
          {membershipTarget && membershipOperations.map((operation) => <Button key={operation.operation_id} intent="neutral"
            onClick={() => setDialog({operation, target: membershipTarget, calls: visualAdminCalls(post, {
              resourceKind: membershipTarget.resource_kind, operationId: operation.operation_id, target: membershipTarget})})}>{gettext(operation.title)}</Button>)}
        </Box>
        {security.membership?.listing && membershipTarget && <Memberships listing={security.membership.listing} resource={membershipTarget} />}
        {security.membership?.member_of_listing && <Memberships listing={security.membership.member_of_listing} resource={selected} />}
        {security.grants?.listing?.held && <Held grants={security.grants} resources={state.resources}
          grantee={granteeSpelling(security, principal, selected)} principalKind={principal.kind} across={across} />}
        <ProviderObjectEditorHost key={`alter:${selected.resource_id}`}
          api={api} endpointUrl={endpointUrl} engine={engine} version={version}
          resourceId={selected.resource_id} resourceKind={kind} displayName={selected.display_name}
          databaseTargetId={databaseTargetId || undefined} mode="alter" onAuthRequired={onAuthRequired}
          onClose={() => setSelection(null)} onApplied={applied} />
      </Box>}
    </Box>
    {dialog && <OperationDialog open operation={dialog.operation} targetName={dialog.target.display_name}
      context={operationContext(state.bundle, state.resources, dialog.target)}
      plan={dialog.calls.plan} apply={dialog.calls.apply}
      onClose={() => setDialog(null)} onApplied={applied} />}
  </Box>;
}

DescriptorSecurityManager.propTypes = {
  api: PropTypes.object.isRequired,
  endpointUrl: PropTypes.string.isRequired,
  engine: PropTypes.string.isRequired,
  version: PropTypes.string,
  scope: PropTypes.oneOf(['server', 'database']),
  databaseTargetId: PropTypes.string,
  initialKind: PropTypes.string,
  initialPrincipalId: PropTypes.string,
  endpointLabel: PropTypes.string,
  onAuthRequired: PropTypes.func,
};
