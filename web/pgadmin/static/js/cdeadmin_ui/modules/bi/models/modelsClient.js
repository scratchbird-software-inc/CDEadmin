/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Every workspace action the Models view uses, with the request and response
 * shapes it relies on (semantic_model_*, semantic_query_*,
 * semantic_materialization_plan, report_scheduler_*). `post` is the function
 * makePost() builds, or the workspace's own post: it takes {action, request}
 * and returns the unwrapped data or throws the provider's message.
 */

import {createBIClient} from '../biClient';

export function createModelsClient(post) {
  const call = (action, request = {}) => post({action, request});
  const resources = createBIClient(post);
  return {
    // workspace catalog: capabilities, delivery profiles, scheduler grants
    catalog: () => call('semantic_model_capabilities'),
    listResources: resources.listResources,

    // lifecycle
    list: async () => (await call('semantic_model_list')).items || [],
    get: (modelId) => call('semantic_model_get', {model_id: modelId}),
    create: (definition) => call('semantic_model_create', {definition}),
    update: (modelId, expectedRevision, definition) => call('semantic_model_update',
      {model_id: modelId, expected_revision: expectedRevision, definition}),
    setStatus: (modelId, expectedRevision, status) => call('semantic_model_status',
      {model_id: modelId, expected_revision: expectedRevision, status}),
    clone: (modelId, name) => call('semantic_model_clone', {model_id: modelId, name}),
    remove: (modelId, expectedRevision) => call('semantic_model_delete',
      {model_id: modelId, expected_revision: expectedRevision}),
    history: async (modelId) => (await call('semantic_model_history', {model_id: modelId})).items || [],
    compare: (modelId, left, right) => call('semantic_model_compare',
      {model_id: modelId, left_revision: left, right_revision: right}),
    validate: (definition) => call('semantic_model_validate', {definition}),
    lineage: (definition) => call('semantic_model_lineage', {definition}),

    // queries: a stored model by id, or an unsaved draft by definition
    compile: (target, query) => call('semantic_query_compile', {...target, query}),
    diagnostics: (target, query) => call('semantic_query_diagnostics', {...target, query}),
    execute: (target, query, sessionId) => call('semantic_query_execute',
      {...target, query, ...(sessionId ? {session_id: sessionId} : {})}),
    poll: (occurrenceId) => post({action: 'poll', occurrence_id: occurrenceId}),
    closeSession: (sessionId) => post({action: 'close_session', session_id: sessionId}),

    // materializations: provider plan, then the confirmed apply
    materializationPlan: (modelId, materializationId) => call('semantic_materialization_plan',
      {model_id: modelId, materialization_id: materializationId}),
    applyPlan: (plan) => post({action: 'visual_admin_apply', request: {
      plan_id: plan.plan_id, plan_digest: plan.plan_digest, confirmed: true}}),

    // migration of embedded visualizations and dashboards into BI objects
    migrate: (modelId, {dryRun = true, acceptLoss = false, collectionId} = {}) => call('semantic_model_migrate', {
      model_id: modelId, dry_run: dryRun, accept_loss: acceptLoss,
      ...(collectionId ? {collection_id: collectionId} : {})}),

    // reports keep running through the report scheduler
    grants: async () => (await call('report_scheduler_list')).items || [],
    occurrences: async (reportId) => (await call('report_scheduler_occurrences', {report_id: reportId})).items || [],
    authorize: (modelId, reportId, days = 30) => call('report_scheduler_authorize',
      {model_id: modelId, report_id: reportId, expires_in_days: days}),
    revoke: (reportId) => call('report_scheduler_revoke', {report_id: reportId}),
    cancel: (occurrenceId) => call('report_scheduler_cancel', {occurrence_id: occurrenceId}),
  };
}
