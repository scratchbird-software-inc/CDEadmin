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

import {useCallback, useEffect, useMemo, useState} from 'react';
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

const PAGE_LIMIT = 200;

/**
 * Every resource the endpoint lists. Unlike the editors' catalog loader this
 * does not hide a failure: an account that cannot list principals must see
 * that, not an empty list that reads as "there are none".
 */
async function listResources(post) {
  const items = [];
  let request = {};
  for(let page = 0; page < PAGE_LIMIT; page++) {
    const result = await post({action: 'resource_page', request});
    items.push(...(result?.items || []));
    if(!result?.next_cursor) break;
    request = {continuation: result.next_cursor, generation: result.generation};
  }
  return items;
}

/** The name a roster row shows: the descriptor's identity fields, joined. */
export function principalLabel(principal, resource) {
  const native = resourceNative(resource);
  const parts = (principal.identity || [])
    .map((field) => native[field] ?? resource?.[field])
    .filter((part) => part !== undefined && part !== null && part !== '');
  if(parts.length > 1) return parts.join('@');
  return resource?.display_name || parts[0] || '';
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
  return <Box component="section" aria-label={gettext('Memberships')} sx={{p: 1}}>
    <Box component="table" sx={{borderCollapse: 'collapse', fontSize: '0.8125rem', width: '100%'}}>
      <thead><tr>{listing.columns.map((column) =>
        <Box component="th" key={column.field} sx={{textAlign: 'left', pr: 2}}>{gettext(column.label)}</Box>)}</tr></thead>
      <tbody>{rows.map((row, index) =>
        <tr key={`${row[listing.columns[0].field]}:${index}`}>{listing.columns.map((column) =>
          <Box component="td" key={column.field} sx={{pr: 2}}>{cell(column, row)}</Box>)}</tr>)}</tbody>
    </Box>
  </Box>;
}

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
    () => (security?.principals || []).filter((principal) => principal.scope === scope),
    [security, scope]);
  const principal = principals.find((item) => item.kind === activeKind) || principals[0];
  const kind = principal?.kind;

  const roster = useMemo(() => {
    if(!principal) return [];
    const needle = filter.trim().toLowerCase();
    return state.resources
      .filter((resource) => resource.resource_kind === principal.kind)
      .map((resource) => ({resource, label: principalLabel(principal, resource)}))
      .filter(({label}) => !needle || label.toLowerCase().includes(needle))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [state.resources, principal, filter]);

  const selected = selection?.mode === 'alter'
    ? state.resources.find((resource) => resource.resource_id === selection.id
      || (resource.resource_kind === kind && resource.display_name === selection.id))
    : null;

  const membershipOperations = useMemo(() => {
    const membership = security?.membership;
    if(!membership || membership.kind !== kind) return [];
    return (state.bundle?.kinds?.[membership.kind]?.operations || [])
      .filter((op) => op.menu?.category === 'security' && op.available !== false)
      .sort((a, b) => (a.menu?.order ?? 0) - (b.menu?.order ?? 0));
  }, [security, kind, state.bundle]);

  const applied = useCallback(() => {
    setDialog(null);
    setRefresh((count) => count + 1);
  }, []);

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

  const create = () => setSelection({mode: 'create'});
  return <Box component="section" aria-label={gettext('Security Manager')}
    sx={{display: 'flex', height: '100%', minHeight: 0}}>
    <Box component="nav" aria-label={gettext('Principals')}
      sx={{width: 300, flex: 'none', display: 'flex', flexDirection: 'column', gap: 1, p: 1, overflow: 'auto'}}>
      {endpointLabel && <Box sx={{fontWeight: 600}}>{endpointLabel}</Box>}
      {principals.length > 1 && <Box role="group" aria-label={gettext('Principal kind')} sx={{display: 'flex', gap: 1}}>
        {principals.map((item) => <Button key={item.kind} intent={item.kind === kind ? 'primary' : 'neutral'}
          aria-pressed={item.kind === kind}
          onClick={() => { setActiveKind(item.kind); setSelection(null); setFilter(''); }}>
          {gettext(item.plural_label)}
        </Button>)}
      </Box>}
      <Button intent="primary" onClick={create}>{gettext('New %s', gettext(principal.label).toLowerCase())}</Button>
      <TextField label={gettext('Filter')} size="small" value={filter}
        onChange={(event) => setFilter(event.target.value)} />
      {roster.length === 0
        ? <Box sx={{fontSize: '0.8125rem'}}>{gettext('No %s found.', gettext(principal.plural_label).toLowerCase())}</Box>
        : <Box component="ul" aria-label={gettext(principal.plural_label)} sx={{listStyle: 'none', m: 0, p: 0}}>
          {roster.map(({resource, label}) => <li key={resource.resource_id}>
            <Button intent={selected?.resource_id === resource.resource_id ? 'primary' : 'neutral'}
              aria-current={selected?.resource_id === resource.resource_id ? 'true' : undefined}
              onClick={() => setSelection({mode: 'alter', id: resource.resource_id})}>{label}</Button>
          </li>)}
        </Box>}
    </Box>
    <Box sx={{flex: 1, minWidth: 0, overflow: 'auto'}}>
      {!selection && <EmptyState message={gettext('Select a %s or create one.', gettext(principal.label).toLowerCase())} />}
      {selection?.mode === 'create' && <ProviderObjectEditorHost key={`create:${kind}`}
        api={api} endpointUrl={endpointUrl} engine={engine} version={version} resourceKind={kind}
        databaseTargetId={databaseTargetId || undefined} mode="create"
        initialRecord={principal.variant ? {[principal.variant.field_id]: principal.variant.value} : {}}
        onAuthRequired={onAuthRequired} onClose={() => setSelection(null)} onApplied={() => { setSelection(null); applied(); }} />}
      {selected && <Box>
        <Box sx={{display: 'flex', gap: 1, p: 1, flexWrap: 'wrap'}}>
          {membershipOperations.map((operation) => <Button key={operation.operation_id} intent="neutral"
            onClick={() => setDialog({operation, target: selected, calls: visualAdminCalls(post, {
              resourceKind: selected.resource_kind, operationId: operation.operation_id, target: selected})})}>{gettext(operation.title)}</Button>)}
        </Box>
        {security.membership?.listing && <Memberships listing={security.membership.listing} resource={selected} />}
        <ProviderObjectEditorHost key={`alter:${selected.resource_id}`}
          api={api} endpointUrl={endpointUrl} engine={engine} version={version}
          resourceId={selected.resource_id} resourceKind={kind} displayName={selected.display_name}
          databaseTargetId={databaseTargetId || undefined} mode="alter" onAuthRequired={onAuthRequired}
          onClose={() => setSelection(null)} onApplied={applied} />
      </Box>}
    </Box>
    {dialog && <OperationDialog open operation={dialog.operation} targetName={dialog.target.display_name}
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
