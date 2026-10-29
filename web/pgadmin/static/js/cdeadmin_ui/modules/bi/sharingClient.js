/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * The sharing actions (docs/en_US/bi_permissions.rst, "Actions") as methods
 * biClient.js mixes into the one BI client. `call(action, request)` is the
 * same unwrapping post the other BI methods use. `type` is one of
 * 'collection', 'question' or 'dashboard'.
 */

const target = (type, id) => ({resource_type: type, resource_id: id});

export function createSharingClient(call) {
  return {
    /** Collections (a tree) and items others shared with the caller at this endpoint. */
    sharedWithMe: async () => {
      const shared = await call('bi_shared_with_me');
      return {collections: shared.collections || [], questions: shared.questions || [],
        dashboards: shared.dashboards || []};
    },
    effectiveAccess: (type, id) => call('bi_access_get', target(type, id)),
    listGrants: (type, id) => call('bi_grant_list', target(type, id)),
    addGrant: (type, id, principalType, principalId, level) => call('bi_grant_add', {
      ...target(type, id), principal_type: principalType, principal_id: principalId, level}),
    updateGrant: (type, id, grantId, level) => call('bi_grant_update', {
      ...target(type, id), grant_id: grantId, level}),
    removeGrant: (type, id, grantId) => call('bi_grant_remove', {...target(type, id), grant_id: grantId}),
    setInherit: (type, id, inherit) => call('bi_access_inherit', {...target(type, id), inherit}),
    transferOwner: (type, id, newOwnerId, confirm) => call('bi_transfer_owner', {
      ...target(type, id), new_owner_id: newOwnerId, confirm}),
    searchPrincipals: async (text, {kinds, limit} = {}) => (await call('bi_principal_search', {
      text, ...(kinds ? {kinds} : {}), ...(limit ? {limit} : {})})).items || [],
    auditTrail: async (type, id) => (await call('bi_audit_list', target(type, id))).items || [],
  };
}
