/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Thin wrapper over the endpoint's workspace action route for the bi_*
 * actions (docs/en_US/bi_saved_questions.rst). `post` is the function
 * makePost() builds: it posts {action, request} and returns the unwrapped
 * data or throws the provider's message. Every request and response shape
 * the UI relies on is visible in this file and nowhere else.
 */

import {createDashboardClient} from './dashboardClient';

const RESOURCE_PAGE_LIMIT = 20;

export function createBIClient(post) {
  const call = (action, request = {}) => post({action, request});
  return {
    ...createDashboardClient(call),

    // collections
    listCollections: async () => (await call('bi_collection_list')).items || [],
    createCollection: (collection) => call('bi_collection_create', {collection}),
    updateCollection: (collectionId, collection) => call('bi_collection_update',
      {collection_id: collectionId, collection}),
    deleteCollection: (collectionId) => call('bi_collection_delete', {collection_id: collectionId}),

    // questions
    listQuestions: async () => (await call('bi_question_list')).items || [],
    getQuestion: (questionId) => call('bi_question_get', {question_id: questionId}),
    createQuestion: (question) => call('bi_question_create', {question}),
    updateQuestion: (questionId, expectedRevision, question) => call('bi_question_update',
      {question_id: questionId, expected_revision: expectedRevision, question}),
    setQuestionStatus: (questionId, expectedRevision, status) => call('bi_question_status',
      {question_id: questionId, expected_revision: expectedRevision, status}),
    moveQuestion: (questionId, expectedRevision, collectionId) => call('bi_question_move',
      {question_id: questionId, expected_revision: expectedRevision, collection_id: collectionId}),
    cloneQuestion: (questionId, name) => call('bi_question_clone', {question_id: questionId, name}),
    deleteQuestion: (questionId, expectedRevision) => call('bi_question_delete',
      {question_id: questionId, expected_revision: expectedRevision}),
    history: async (questionId) => (await call('bi_question_history', {question_id: questionId})).items || [],
    revision: (questionId, revision) => call('bi_question_revision', {question_id: questionId, revision}),

    // compile, run, page
    compile: (question, parameters) => call('bi_question_compile',
      {question, ...(parameters && Object.keys(parameters).length ? {parameters} : {})}),
    compileRevision: (questionId, revision) => call('bi_question_compile',
      {question_id: questionId, revision}),
    execute: (question, {parameters, pageSize, bypassCache = false} = {}) => call('bi_question_execute', {
      question,
      ...(parameters && Object.keys(parameters).length ? {parameters} : {}),
      ...(pageSize ? {page_size: pageSize} : {}),
      ...(bypassCache ? {bypass_cache: true} : {}),
    }),
    page: (resultId, cursor, pageSize) => call('bi_question_page',
      {result_id: resultId, cursor, ...(pageSize ? {page_size: pageSize} : {})}),
    convertSql: (sql, {name, parameterTypes, collectionId} = {}) => call('bi_sql_to_question', {
      sql, ...(name ? {name} : {}),
      ...(parameterTypes && Object.keys(parameterTypes).length ? {parameter_types: parameterTypes} : {}),
      ...(collectionId ? {collection_id: collectionId} : {}),
    }),

    // sources: the endpoint's catalog and semantic models (existing actions)
    listResources: async () => {
      let page = await call('resource_page');
      let items = [...(page?.items || [])];
      for(let count = 1; page?.next_cursor && count < RESOURCE_PAGE_LIMIT; count += 1) {
        page = await call('resource_page', {continuation: page.next_cursor, generation: page.generation});
        items = items.concat(page?.items || []);
      }
      return items;
    },
    inspectResource: (resourceId) => call('resource_inspect', {resource_id: resourceId}),
    listModels: async () => (await call('semantic_model_list')).items || [],
    getModel: (modelId) => call('semantic_model_get', {model_id: modelId}),
  };
}
