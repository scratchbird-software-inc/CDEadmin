/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Server family editor host (design 6.x, tier 3): registers or edits a provider
 * endpoint through the descriptor `server` form instead of the legacy SchemaView
 * dialog. The form's backend_field_id values are the servers-API keys, so the
 * payload is toBackendDraft plus the three registration envelope keys. There is
 * no DDL plan: ObjectEditor runs in directApply mode.
 */
import {useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Box} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {Banner, ValidationMessage} from '../feedback/Indicators';
import {ProgressOverlay} from '../feedback/ProgressOverlay';
import {EmptyState} from '../feedback/EmptyState';
import ObjectEditor from './ObjectEditor';
import {DescriptorClient} from './DescriptorClient';
import {formForKind, editorAvailable, recordFromBackend, versionSupportNotice} from './descriptors';

/** Envelope keys the servers API reads besides the form's own fields. */
export function registrationPayload(form, draft, {profileId, intent='endpoint', verifyNow=true}={}) {
  const data = {...draft};
  // A multi-profile form (Firebird native/embedded) carries its profile as a select.
  const profile = data.profile ?? profileId;
  delete data.profile;
  return {...data, cde_profile_id: profile ?? profileId, cde_registration_intent: intent, cde_verify_now: verifyNow};
}

/*
 * An endpoint whose registration changes pass the provider's lifecycle admission (MySQL, owner work
 * 2026-10-23: retained SQL sessions block route changes) is edited through its workspace action
 * endpoint_profile_update, never the generic servers update, which refuses it. That action takes
 * the provider edit form's complete values, so the request is the current record merged with the
 * changes, limited to the fields that form owns. A change to a field it does not own is refused
 * here rather than silently dropped; an unchanged secret is left out so the stored one stays.
 */
export function lifecycleProfileRequest(ownedFields, record, changes) {
  const owned = new Set(ownedFields);
  const refused = Object.keys(changes).filter((key) => !owned.has(key));
  if(refused.length) {
    throw new Error(`This endpoint's registration changes go through its provider, which does not edit: ${refused.join(', ')}`);
  }
  const merged = {...record, ...changes};
  const request = {};
  for(const field of ownedFields) {
    if(/password/i.test(field) && !(field in changes && changes[field])) continue;
    if(field in merged && merged[field] !== undefined) request[field] = merged[field];
  }
  return request;
}

/*
 * The servers API answers a refused registration with an HTTP error whose body says why (a
 * password is required to verify, a field is missing). Show that sentence, not the transport's
 * "Request failed with status code 401" (browser pass 2026-11-12).
 */
async function send(api, request) {
  let response;
  try {
    response = await api(request);
  } catch(error) {
    const body = error?.response?.data;
    throw new Error(body?.errormsg || body?.info || error?.message || String(error));
  }
  if(response?.data?.success === 0) throw new Error(response.data.errormsg || response.data.info || 'Request refused');
  return response;
}

export default function ServerRegistrationHost({api, engine, version, versionSupport, mode='create', urlFor, initialData={}, profileId,
  intent='endpoint', verifyNow=true, displayName, onClose, onSaved, descriptorClient, lifecycleUrl}) {
  const client = useMemo(() => descriptorClient || new DescriptorClient(api), [api, descriptorClient]);
  const [state, setState] = useState({status: 'loading', bundle: null, record: {}, error: null});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const bundle = await client.bundle(engine, {version});
        let data = initialData;
        if(mode === 'alter') {
          const response = await api.get(urlFor(false));
          data = response.data;
        }
        if(!cancelled) setState({status: 'ready', bundle, record: data, error: null});
      } catch(error) {
        if(!cancelled) setState({status: 'error', bundle: null, record: {}, error: error?.message || String(error)});
      }
    })();
    return () => { cancelled = true; };
  }, [client, engine, version, mode]);

  if(state.status === 'loading') {
    return <Box sx={{position: 'relative', minHeight: 160}}><ProgressOverlay message="Loading server editor" /></Box>;
  }
  if(state.status === 'error') {
    return <Box sx={{p: 2}}>
      <ValidationMessage status="error">{state.error}</ValidationMessage>
      <Box sx={{mt: 1}}><Button intent="neutral" onClick={onClose}>Close</Button></Box>
    </Box>;
  }
  const {bundle, record} = state;
  if(!editorAvailable(bundle, 'server')) {
    return <EmptyState message={`No server editor is declared for ${engine} yet.`} actionLabel="Close" onAction={onClose} />;
  }
  const form = formForKind(bundle, 'server');
  const fromBackend = recordFromBackend(form, record);
  if(form.tabs.some((tab) => tab.fields.some((field) => field.field_id === 'profile'))) {
    fromBackend.profile = record.cde_profile_id || profileId;
  }
  const apply = async ({draft}) => {
    if(mode === 'alter' && lifecycleUrl) {
      const read = await send(api, {url: lifecycleUrl, method: 'POST', data: {action: 'endpoint_profile_read'}});
      const editForm = read?.data?.data?.endpoint_registration?.forms?.forms?.edit;
      if(!editForm) throw new Error(read?.data?.errormsg || 'The provider did not return its edit form');
      // The editor reports changes under the servers API's names (cde_route_compress); the provider
      // edit form and the record use field ids (compress).
      const fieldOf = new Map(form.tabs.flatMap((tab) => tab.fields)
        .filter((field) => field.backend_field_id).map((field) => [field.backend_field_id, field.field_id]));
      const changes = Object.fromEntries(Object.entries(draft).map(([key, value]) => [fieldOf.get(key) || key, value]));
      const request = lifecycleProfileRequest(editForm.fields.map((field) => field.field_id), fromBackend, changes);
      const response = await send(api, {url: lifecycleUrl, method: 'POST', data: {action: 'endpoint_profile_update', request}});
      onSaved?.(response.data);
      return response.data;
    }
    const payload = registrationPayload(form, draft, {profileId: record.cde_profile_id || profileId, intent, verifyNow});
    const response = await send(api, {url: urlFor(mode === 'create'), method: mode === 'create' ? 'POST' : 'PUT', data: payload});
    onSaved?.(response.data);
    return response.data;
  };
  const notice = versionSupportNotice(versionSupport);
  const editor = <ObjectEditor form={form} mode={mode} resourceKind="server" record={fromBackend} context={{}}
    title={displayName} directApply applyLabel={mode === 'create' ? 'Register' : 'Save'}
    apply={apply} onClose={onClose} />;
  return notice ? <Box><Banner status="info">{notice}</Banner>{editor}</Box> : editor;
}

ServerRegistrationHost.propTypes = {
  api: PropTypes.oneOfType([PropTypes.object, PropTypes.func]).isRequired,
  engine: PropTypes.string.isRequired,
  version: PropTypes.string,
  versionSupport: PropTypes.object,
  mode: PropTypes.oneOf(['create', 'alter']),
  urlFor: PropTypes.func.isRequired,
  initialData: PropTypes.object,
  profileId: PropTypes.string,
  intent: PropTypes.string,
  verifyNow: PropTypes.bool,
  displayName: PropTypes.string,
  onClose: PropTypes.func,
  onSaved: PropTypes.func,
  // Workspace URL of an endpoint edited through its provider lifecycle (see lifecycleProfileRequest).
  lifecycleUrl: PropTypes.string,
  descriptorClient: PropTypes.object,
};
