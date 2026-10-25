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
import {formForKind, editorAvailable} from './descriptors';

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

export default function ProviderObjectEditorHost({api, endpointUrl, engine, version, resourceId, resourceKind,
  databaseTargetId, mode='alter', displayName, context={}, onClose, onApplied, descriptorClient}) {
  const client = useMemo(() => descriptorClient || new DescriptorClient(api), [api, descriptorClient]);
  const post = useMemo(() => makePost(api, endpointUrl, databaseTargetId), [api, endpointUrl, databaseTargetId]);
  const [state, setState] = useState({status: 'loading', bundle: null, resource: null, error: null});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const bundle = await client.bundle(engine, {version});
        const resource = mode === 'alter' && resourceId ?
          await post({action: 'resource_inspect', request: {resource_id: resourceId}}) : null;
        if(!cancelled) setState({status: 'ready', bundle, resource, error: null});
      } catch(error) {
        if(!cancelled) setState({status: 'error', bundle: null, resource: null, error: error?.message || String(error)});
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
  const {bundle, resource} = state;
  if(!editorAvailable(bundle, resourceKind)) {
    return <EmptyState message={`No ${resourceKind} editor is declared for ${engine} yet.`}
      actionLabel="Close" onAction={onClose} />;
  }
  const form = formForKind(bundle, resourceKind);
  const calls = visualAdminCalls(post, {resourceKind, operationId: mode === 'create' ? 'create' : 'alter',
    target: resource});
  return <ObjectEditor form={form} mode={mode} resourceKind={resourceKind}
    record={recordFromResource(resource)} context={{...context, bundle}}
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
  descriptorClient: PropTypes.object,
};
