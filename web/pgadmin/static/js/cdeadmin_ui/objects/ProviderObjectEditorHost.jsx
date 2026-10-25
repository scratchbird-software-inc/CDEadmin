/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Hosts the family ObjectEditor for one provider resource: loads the
 * engine's descriptor bundle, inspects the resource for its current values,
 * and wires plan/apply to the workspace's visual-administration actions.
 * Transport details stop here; ObjectEditor sees only a form, a record and
 * two callbacks.
 */

import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Box} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {EmptyState} from '../feedback/EmptyState';
import {ValidationMessage} from '../feedback/Indicators';
import {ProgressOverlay} from '../feedback/ProgressOverlay';
import ObjectEditor from './ObjectEditor';
import {DescriptorClient, visualAdminCalls} from './DescriptorClient';
import {buildOptionContext, formForKind, editorAvailable} from './descriptors';
import {Stack} from '../primitives/Layout';

const DATABASE_SCOPED = new Set(['resource_inspect', 'resource_page', 'visual_admin_validate',
  'visual_admin_plan', 'visual_admin_apply']);

/** First provider-native block of a resource, as the workspace reads it. */
export function resourceNative(resource) {
  const extensions = resource?.extensions || {};
  for(const [key, value] of Object.entries(extensions)) {
    if(key !== 'cdeadmin' && value && typeof value === 'object' && value.native) return value.native;
  }
  return {};
}

/** Flatten a resource into the record the editor pre-fills from. */
export function recordFromResource(resource) {
  if(!resource) return {};
  const native = resourceNative(resource);
  return {
    ...native,
    name: native.name ?? resource.display_name,
    display_name: resource.display_name,
    resource_id: resource.resource_id,
    resource_kind: resource.resource_kind,
    parent: native.parent ?? ((resource.display_path || []).slice(0, -1).join('.') || undefined),
  };
}

export function makePost(api, endpointUrl, databaseTargetId) {
  return async (payload) => {
    const request = {...(payload.request || {})};
    if(databaseTargetId && DATABASE_SCOPED.has(payload.action) && request.database_target_id === undefined) {
      request.database_target_id = databaseTargetId;
    }
    const response = await api.post(endpointUrl, {...payload, request});
    const envelope = response?.data;
    if(envelope && envelope.success === 0) throw new Error(envelope.errormsg || 'Provider request failed');
    return envelope?.data ?? envelope;
  };
}

const HIDDEN_NATIVE_KEYS = new Set(['columns', 'constraints', 'indexes', 'triggers', 'dependencies', 'dependents',
  'navigator_parent_resource_id', 'system_object']);

function formatValue(value) {
  if(value === null || value === undefined) return '—';
  if(typeof value === 'boolean') return value ? 'Yes' : 'No';
  if(typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/** Read-only property groups from the provider's native block (Statistics tab). */
export function NativeProperties({resource}) {
  const native = resourceNative(resource);
  const rows = Object.entries(native).filter(([key, value]) =>
    !HIDDEN_NATIVE_KEYS.has(key) && (typeof value !== 'object' || value === null || Array.isArray(value) && value.every((item) => typeof item !== 'object')));
  if(!rows.length) return <EmptyState message="The provider reported no statistics for this object." />;
  return <Box component="dl" sx={{display: 'grid', gridTemplateColumns: 'max-content 1fr', columnGap: 2, rowGap: 0.5, m: 0,
    fontSize: '0.8125rem'}} data-cdeadmin-qa-key="object-editor.statistics">
    {rows.map(([key, value]) => <Box key={key} sx={{display: 'contents'}}>
      <Box component="dt" sx={{color: 'text.secondary'}}>{key.replace(/_/g, ' ')}</Box>
      <Box component="dd" sx={{m: 0, fontFamily: 'monospace', wordBreak: 'break-all'}}>{formatValue(value)}</Box>
    </Box>)}
  </Box>;
}
NativeProperties.propTypes = {resource: PropTypes.object};

function NativeDependencies({resource}) {
  const native = resourceNative(resource);
  const dependsOn = native.dependencies || native.depends_on || [];
  const dependents = native.dependents || [];
  if(!dependsOn.length && !dependents.length) {
    return <EmptyState message="The provider reported no dependency information for this object." />;
  }
  const list = (title, items) => <Box>
    <Box component="h4" sx={{m: 0, mb: 0.5, fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary'}}>{title}</Box>
    <Box component="ul" sx={{m: 0, pl: 2, fontSize: '0.8125rem'}}>
      {items.map((item, index) => <li key={index}>{typeof item === 'object' ? `${item.kind || item.resource_kind || ''} ${item.name || item.display_name || ''}`.trim() : String(item)}</li>)}
    </Box>
  </Box>;
  return <Stack gap="comfortable">{list('Depends on', dependsOn)}{list('Dependents', dependents)}</Stack>;
}
NativeDependencies.propTypes = {resource: PropTypes.object};

function NativeChildList({resource, resources, kind}) {
  const children = (resources || []).filter((row) => row.resource_kind === kind &&
    (row.parent_resource_id === resource?.resource_id ||
      (row.display_path || []).slice(0, -1).join('.') === (resource?.display_path || []).join('.')));
  if(!children.length) return <EmptyState message={`No ${kind}s on this object.`} />;
  return <Box component="ul" sx={{m: 0, pl: 2, fontSize: '0.8125rem'}} data-cdeadmin-qa-key={`object-editor.children.${kind}`}>
    {children.map((row) => <li key={row.resource_id}>{row.display_name}</li>)}
  </Box>;
}
NativeChildList.propTypes = {resource: PropTypes.object, resources: PropTypes.array, kind: PropTypes.string};

export default function ProviderObjectEditorHost({api, endpointUrl, engine, version, resourceId, resourceKind,
  databaseTargetId, mode='alter', displayName, context={}, tabRenderers: tabRenderersProp={}, onClose, onApplied,
  descriptorClient}) {
  const client = useMemo(() => descriptorClient || new DescriptorClient(api), [api, descriptorClient]);
  const post = useMemo(() => makePost(api, endpointUrl, databaseTargetId), [api, endpointUrl, databaseTargetId]);
  const [state, setState] = useState({status: 'loading', bundle: null, resource: null, resources: [], error: null});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const bundle = await client.bundle(engine, {version});
        const [resource, page] = await Promise.all([
          mode === 'alter' && resourceId ? post({action: 'resource_inspect', request: {resource_id: resourceId}}) : null,
          // One page of the endpoint's resources feeds catalog lists and reference pickers.
          post({action: 'resource_page', request: {}}).catch(() => null),
        ]);
        if(!cancelled) setState({status: 'ready', bundle, resource, resources: page?.items || [], error: null});
      } catch(error) {
        if(!cancelled) setState({status: 'error', bundle: null, resource: null, resources: [], error: error?.message || String(error)});
      }
    })();
    return () => { cancelled = true; };
  }, [client, engine, version, resourceId, mode, post]);

  if(state.status === 'loading') {
    return <Box sx={{position: 'relative', minHeight: 160}}>
      <ProgressOverlay message="Loading object editor" />
    </Box>;
  }
  if(state.status === 'error') {
    return <Box sx={{p: 2}}>
      <ValidationMessage status="error">{state.error}</ValidationMessage>
      <Box sx={{mt: 1}}><Button intent="neutral" onClick={onClose}>Close</Button></Box>
    </Box>;
  }
  const {bundle, resource, resources} = state;
  if(!editorAvailable(bundle, resourceKind)) {
    return <EmptyState message={`No ${resourceKind} editor is declared for ${engine} yet.`}
      actionLabel="Close" onAction={onClose} />;
  }
  const form = formForKind(bundle, resourceKind);
  const calls = visualAdminCalls(post, {resourceKind, operationId: mode === 'create' ? 'create' : 'alter',
    target: resource});
  const optionContext = buildOptionContext(bundle, resources);
  const target = resource ? {columns: (resourceNative(resource).columns || []).map((column) => column?.name ?? column)} : {};
  const tabRenderers = {
    Statistics: () => <NativeProperties resource={resource} />,
    Dependencies: () => <NativeDependencies resource={resource} />,
    Data: () => <EmptyState message="Row data opens in the data grid from the object's menu." />,
    Indexes: () => <NativeChildList resource={resource} resources={resources} kind="index" />,
    Triggers: () => <NativeChildList resource={resource} resources={resources} kind="trigger" />,
    ...tabRenderersProp,
  };
  return <ObjectEditor form={form} mode={mode} resourceKind={resourceKind}
    record={recordFromResource(resource)} context={{...context, ...optionContext, target}}
    tabRenderers={tabRenderers}
    title={displayName ? `${mode === 'create' ? 'Create' : 'Edit'} ${form.family_title.toLowerCase()} — ${displayName}` : undefined}
    plan={({draft}) => calls.plan({draft})}
    apply={({plan}) => calls.apply({plan})}
    onClose={onClose} onApplied={onApplied} />;
}

ProviderObjectEditorHost.propTypes = {
  api: PropTypes.object.isRequired,
  endpointUrl: PropTypes.string.isRequired,
  engine: PropTypes.string.isRequired,
  version: PropTypes.string,
  resourceId: PropTypes.string,
  resourceKind: PropTypes.string.isRequired,
  databaseTargetId: PropTypes.string,
  mode: PropTypes.oneOf(['create', 'alter']),
  displayName: PropTypes.string,
  context: PropTypes.object,
  onClose: PropTypes.func,
  onApplied: PropTypes.func,
  tabRenderers: PropTypes.object,
  descriptorClient: PropTypes.object,
};
