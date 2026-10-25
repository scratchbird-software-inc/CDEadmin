/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Fetches and caches resolved UI descriptor bundles from
 * GET /cdeadmin/api/ui/descriptors/<engine>[?version=], and adapts the
 * provider workspace's visual-administration calls (validate/plan/apply)
 * to the plan/apply functions the ObjectEditor and OperationDialog take.
 */

const DESCRIPTOR_URL = '/cdeadmin/api/ui/descriptors';

export class DescriptorClient {
  constructor(api, {baseUrl=DESCRIPTOR_URL}={}) {
    this.api = api;
    this.baseUrl = baseUrl;
    this.cache = new Map();
  }

  key(engine, version) {
    return `${engine}@${version || ''}`;
  }

  async bundle(engine, {version}={}) {
    const key = this.key(engine, version);
    if(!this.cache.has(key)) {
      const url = version ? `${this.baseUrl}/${engine}?version=${encodeURIComponent(version)}` : `${this.baseUrl}/${engine}`;
      const promise = this.api.get(url).then((response) => {
        const envelope = response?.data;
        if(!envelope || envelope.success !== 1) throw new Error(envelope?.errormsg || 'UI descriptors unavailable');
        return envelope.data;
      }).catch((error) => {
        this.cache.delete(key);
        throw error;
      });
      this.cache.set(key, promise);
    }
    return this.cache.get(key);
  }

  invalidate(engine) {
    for(const key of [...this.cache.keys()]) {
      if(!engine || key.startsWith(`${engine}@`)) this.cache.delete(key);
    }
  }
}

/**
 * Build `plan`/`apply` callbacks for one target over the workspace `post`
 * helper (action + request), so editor components never see the transport.
 *
 * `post` is the function ProviderWorkspaceContent already passes around:
 * post({action, request}) -> response data. `target` is the full resource
 * dict (or null for create); `resourceKind`/`operationId` name the plan.
 */
export function visualAdminCalls(post, {resourceKind, operationId, target=null, sessionId}) {
  const base = () => ({resource_kind: resourceKind, operation_id: operationId, target_resource: target,
    ...(sessionId ? {session_id: sessionId} : {})});
  return {
    async validate({draft}) {
      return post({action: 'visual_admin_validate', request: {...base(), draft}});
    },
    async plan({draft}) {
      const validation = await post({action: 'visual_admin_validate', request: {...base(), draft}});
      if(validation && validation.valid === false) {
        const message = (validation.errors || []).map((row) => row.message || row.code).join(' ') || 'The provider rejected the draft.';
        const error = new Error(message);
        error.validation = validation;
        throw error;
      }
      return post({action: 'visual_admin_plan', request: {...base(), draft}});
    },
    async apply({plan}) {
      return post({action: 'visual_admin_apply', request: {plan_id: plan.plan_id, plan_digest: plan.plan_digest,
        confirmed: true, ...(sessionId ? {session_id: sessionId} : {})}});
    },
  };
}

let shared = null;

/** Process-wide client; `api` is only needed the first time. */
export function descriptorClient(api) {
  if(!shared) {
    if(!api) throw new Error('descriptorClient needs an API instance on first use');
    shared = new DescriptorClient(api);
  }
  return shared;
}

export function resetDescriptorClient() {
  shared = null;
}
