/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {createModelsClient} from 'sources/cdeadmin_ui/modules/bi/models/modelsClient';
import {modelFixtures as fixtures} from './modelFixtures';

const MODEL = fixtures.ids.model;

function client(answers = {}) {
  const post = jest.fn(async (payload) => {
    const key = payload.action;
    if(!(key in answers)) throw new Error(`unexpected action ${key}`);
    return typeof answers[key] === 'function' ? answers[key](payload) : answers[key];
  });
  return {post, api: createModelsClient(post)};
}

describe('Models client requests', () => {
  it('reads the catalog and unwraps the model list', async () => {
    const {post, api} = client({semantic_model_capabilities: fixtures.catalog,
      semantic_model_list: {items: fixtures.list}});
    expect(await api.catalog()).toEqual(fixtures.catalog);
    expect(await api.list()).toEqual(fixtures.list);
    expect(post).toHaveBeenCalledWith({action: 'semantic_model_capabilities', request: {}});
  });

  it('sends lifecycle calls with the revision the edit is based on', async () => {
    const {post, api} = client({semantic_model_update: fixtures.updated, semantic_model_status: fixtures.published,
      semantic_model_clone: fixtures.draft, semantic_model_delete: {}, semantic_model_create: fixtures.draft});
    const definition = fixtures.draft.definition;
    await api.create(definition);
    await api.update(MODEL, 1, definition);
    await api.setStatus(MODEL, 2, 'published');
    await api.clone(MODEL, 'Copy');
    await api.remove(MODEL, 3);
    expect(post.mock.calls.map(([payload]) => payload)).toEqual([
      {action: 'semantic_model_create', request: {definition}},
      {action: 'semantic_model_update', request: {model_id: MODEL, expected_revision: 1, definition}},
      {action: 'semantic_model_status', request: {model_id: MODEL, expected_revision: 2, status: 'published'}},
      {action: 'semantic_model_clone', request: {model_id: MODEL, name: 'Copy'}},
      {action: 'semantic_model_delete', request: {model_id: MODEL, expected_revision: 3}},
    ]);
  });

  it('asks for history and a comparison of two revisions', async () => {
    const {post, api} = client({semantic_model_history: fixtures.history,
      semantic_model_compare: fixtures.compare});
    expect(await api.history(MODEL)).toEqual(fixtures.history.items);
    expect(await api.compare(MODEL, 1, 2)).toEqual(fixtures.compare);
    expect(post).toHaveBeenLastCalledWith({action: 'semantic_model_compare',
      request: {model_id: MODEL, left_revision: 1, right_revision: 2}});
  });

  it('queries a stored model by id or an unsaved draft by definition, reusing a session', async () => {
    const {post, api} = client({semantic_query_compile: {sql: 'x'}, semantic_query_diagnostics: {},
      semantic_query_execute: {occurrence: {occurrence_id: 'o1'}},
      poll: {rendered_result: {}}, close_session: {}});
    const query = {measures: ['revenue']};
    await api.compile({model_id: MODEL}, query);
    await api.diagnostics({definition: {name: 'x'}}, query);
    await api.execute({model_id: MODEL}, query, 's1');
    await api.execute({model_id: MODEL}, query, '');
    await api.poll('o1');
    await api.closeSession('s1');
    expect(post.mock.calls.map(([payload]) => payload)).toEqual([
      {action: 'semantic_query_compile', request: {model_id: MODEL, query}},
      {action: 'semantic_query_diagnostics', request: {definition: {name: 'x'}, query}},
      {action: 'semantic_query_execute', request: {model_id: MODEL, query, session_id: 's1'}},
      {action: 'semantic_query_execute', request: {model_id: MODEL, query}},
      {action: 'poll', occurrence_id: 'o1'},
      {action: 'close_session', session_id: 's1'},
    ]);
  });

  it('confirms a materialization plan by id and digest only', async () => {
    const {post, api} = client({semantic_materialization_plan: {plan_id: 'p', plan_digest: 'd', state: 'ready'},
      visual_admin_apply: {}});
    const plan = await api.materializationPlan(MODEL, 'rollup');
    await api.applyPlan({...plan, sql: 'ignored'});
    expect(post).toHaveBeenCalledWith({action: 'semantic_materialization_plan',
      request: {model_id: MODEL, materialization_id: 'rollup'}});
    expect(post).toHaveBeenLastCalledWith({action: 'visual_admin_apply',
      request: {plan_id: 'p', plan_digest: 'd', confirmed: true}});
  });

  it('migrates as a dry run unless told otherwise', async () => {
    const {post, api} = client({semantic_model_migrate: fixtures.migration.dry});
    await api.migrate(MODEL);
    await api.migrate(MODEL, {dryRun: false, acceptLoss: true, collectionId: 'c1'});
    expect(post.mock.calls.map(([payload]) => payload.request)).toEqual([
      {model_id: MODEL, dry_run: true, accept_loss: false},
      {model_id: MODEL, dry_run: false, accept_loss: true, collection_id: 'c1'},
    ]);
  });

  it('keeps reports running through the report scheduler actions', async () => {
    const {post, api} = client({report_scheduler_list: {items: [{report_id: 'morning'}]},
      report_scheduler_occurrences: {items: []}, report_scheduler_authorize: {}, report_scheduler_revoke: {},
      report_scheduler_cancel: {}});
    expect(await api.grants()).toEqual([{report_id: 'morning'}]);
    expect(await api.occurrences('morning')).toEqual([]);
    await api.authorize(MODEL, 'morning');
    await api.revoke('morning');
    await api.cancel('o-1');
    expect(post.mock.calls.slice(2).map(([payload]) => payload)).toEqual([
      {action: 'report_scheduler_authorize', request: {model_id: MODEL, report_id: 'morning', expires_in_days: 30}},
      {action: 'report_scheduler_revoke', request: {report_id: 'morning'}},
      {action: 'report_scheduler_cancel', request: {occurrence_id: 'o-1'}},
    ]);
  });

  it('lets a provider failure through to the caller', async () => {
    const {api} = client({semantic_model_get: () => { throw new Error('model is unavailable'); }});
    await expect(api.get(MODEL)).rejects.toThrow('model is unavailable');
  });
});
