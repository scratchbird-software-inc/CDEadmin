/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  collectionPath, flattenCollections, matchingCollectionIds, moveTargets, questionCounts,
  subtreeIds, visibleQuestions,
} from 'sources/cdeadmin_ui/modules/bi/collectionTree';
import {createBIClient} from 'sources/cdeadmin_ui/modules/bi/biClient';
import {appendPage, executionFrom} from 'sources/cdeadmin_ui/modules/bi/executionModel';
import {
  buildChart, defaultSettings, effectiveSettings, numericColumns, resultTable,
} from 'sources/cdeadmin_ui/modules/bi/chartData';
import {questions} from './biFixtures';

const tree = [
  {collection_id: 'a', parent_id: null, name: 'Sales', children: [
    {collection_id: 'b', parent_id: 'a', name: 'Regional', children: [
      {collection_id: 'c', parent_id: 'b', name: 'West', children: []}]}]},
  {collection_id: 'd', parent_id: null, name: 'Ops', children: []},
];
const list = [
  {question_id: '1', name: 'Revenue by region', collection_id: 'b', status: 'active'},
  {question_id: '2', name: 'Old revenue', collection_id: null, status: 'archived'},
  {question_id: '3', name: 'Tickets', collection_id: 'd', status: 'active'},
];

describe('collection tree', () => {
  it('flattens depth first with paths', () => {
    expect(flattenCollections(tree).map((row) => [row.id, row.depth, row.path.join('/')])).toEqual([
      ['a', 0, 'Sales'], ['b', 1, 'Sales/Regional'], ['c', 2, 'Sales/Regional/West'], ['d', 0, 'Ops']]);
    expect(collectionPath(tree, 'c')).toEqual(['Sales', 'Regional', 'West']);
    expect(collectionPath(tree, null)).toEqual([]);
  });
  it('never offers a collection or its descendants as a move target', () => {
    expect(subtreeIds(tree, 'a')).toEqual(['a', 'b', 'c']);
    expect(moveTargets(tree, 'a').map((row) => row.id)).toEqual(['d']);
    expect(moveTargets(tree, 'c').map((row) => row.id)).toEqual(['a', 'b', 'd']);
  });
  it('counts questions and keeps the root under null', () => {
    const counts = questionCounts(list);
    expect(counts.get('b')).toBe(1);
    expect(counts.get(null)).toBe(1);
  });
  it('searches question names case-insensitively and hides archived ones', () => {
    expect(visibleQuestions(list, {text: 'REVENUE'}).map((q) => q.question_id)).toEqual(['1']);
    expect(visibleQuestions(list, {text: 'revenue', includeArchived: true})).toHaveLength(2);
    expect(visibleQuestions(list, {collectionId: null, includeArchived: true}).map((q) => q.question_id)).toEqual(['2']);
    expect(visibleQuestions(list, {collectionId: 'd'})).toHaveLength(1);
  });
  it('keeps the ancestors of a matching collection', () => {
    expect([...matchingCollectionIds(tree, 'west')]).toEqual(['a', 'b', 'c']);
    expect(matchingCollectionIds(tree, ' ')).toBeNull();
  });
});

describe('BI client payloads', () => {
  const make = () => {
    const post = jest.fn(async () => ({}));
    return {post, client: createBIClient(post)};
  };

  it('sends the saved-question actions with optimistic revisions', async () => {
    const {post, client} = make();
    await client.updateQuestion('q', 4, {name: 'n'});
    await client.setQuestionStatus('q', 4, 'archived');
    await client.moveQuestion('q', 4, null);
    await client.createCollection({name: 'x', parent_id: null});
    await client.revision('q', 2);
    expect(post.mock.calls.map(([payload]) => payload)).toEqual([
      {action: 'bi_question_update', request: {question_id: 'q', expected_revision: 4, question: {name: 'n'}}},
      {action: 'bi_question_status', request: {question_id: 'q', expected_revision: 4, status: 'archived'}},
      {action: 'bi_question_move', request: {question_id: 'q', expected_revision: 4, collection_id: null}},
      {action: 'bi_collection_create', request: {collection: {name: 'x', parent_id: null}}},
      {action: 'bi_question_revision', request: {question_id: 'q', revision: 2}},
    ]);
  });

  it('compiles and executes the question document as built', async () => {
    const {post, client} = make();
    await client.compile(questions.detail);
    await client.execute(questions.detail, {parameters: {floor: 1}, pageSize: 50, bypassCache: true});
    await client.execute(questions.detail, {parameters: {}});
    await client.page('r1', 'cur');
    const sent = post.mock.calls.map(([payload]) => payload);
    expect(sent[0]).toEqual({action: 'bi_question_compile', request: {question: questions.detail}});
    expect(sent[1].request).toEqual({question: questions.detail, parameters: {floor: 1}, page_size: 50, bypass_cache: true});
    expect(sent[2].request).toEqual({question: questions.detail});
    expect(sent[3]).toEqual({action: 'bi_question_page', request: {result_id: 'r1', cursor: 'cur'}});
  });

  it('unwraps list responses and follows resource pages', async () => {
    const pages = [{items: [1], next_cursor: 'n', generation: 'g'}, {items: [2]}];
    const post = jest.fn(async ({action}) => action === 'resource_page' ? pages.shift() : {items: ['x']});
    const client = createBIClient(post);
    expect(await client.listResources()).toEqual([1, 2]);
    expect(post.mock.calls[1][0].request).toEqual({continuation: 'n', generation: 'g'});
    expect(await client.listCollections()).toEqual(['x']);
    await client.convertSql('SELECT 1', {parameterTypes: {a: 'integer'}, collectionId: 'c'});
    expect(post.mock.calls.at(-1)[0].request).toEqual({
      sql: 'SELECT 1', parameter_types: {a: 'integer'}, collection_id: 'c'});
  });
});

describe('execution model and charts', () => {
  const response = {
    result: {result_id: 'r1'},
    page: {view_model: {columns: [{key: 'region'}, {key: 'total', engine_type: 'numeric'}],
      rows: [['east', 5], ['west', 7]]}, page: {source_count: 3, next_cursor: 'c2'}},
    redacted_columns: ['ssn'], cache: {hit: false}, sql: 'SELECT 1',
  };

  it('reads the first page and appends later ones', () => {
    const run = executionFrom(response);
    expect(run).toMatchObject({resultId: 'r1', total: 3, cursor: 'c2', redacted: ['ssn']});
    expect(run.table.rows[1]).toEqual({region: 'west', total: 7});
    const more = appendPage(run, {view_model: {columns: [{key: 'region'}, {key: 'total'}],
      rows: [['north', 1]]}, page: {next_cursor: ''}});
    expect(more.table.rows).toHaveLength(3);
    expect(more.cursor).toBe('');
  });

  it('chooses default axes and drops unknown settings', () => {
    const table = resultTable(response.page.view_model);
    expect(numericColumns(table).map((column) => column.key)).toEqual(['total']);
    expect(defaultSettings(table)).toEqual({x: 'region', y: ['total']});
    expect(effectiveSettings({x: 'ghost', y: ['ghost']}, table)).toEqual({x: 'region', y: ['total']});
  });

  it('builds each chart kind, and explains when it cannot', () => {
    const table = resultTable(response.page.view_model);
    expect(buildChart('table', table)).toEqual({kind: 'table'});
    expect(buildChart('metric', table, {})).toMatchObject({kind: 'metric', label: 'total', value: 5});
    expect(buildChart('bar', table, {})).toMatchObject({kind: 'chart', type: 'bar'});
    expect(buildChart('area', table, {}).data.datasets[0].fill).toBe(true);
    expect(buildChart('pie', table, {})).toMatchObject({kind: 'chart', type: 'pie'});
    expect(buildChart('scatter', table, {}).kind).toBe('empty');
    expect(buildChart('bar', {columns: table.columns, rows: []}, {}).kind).toBe('empty');
    expect(buildChart('line', {columns: [{key: 'a', name: 'a'}], rows: [{a: 'x'}]}, {}).kind).toBe('empty');
  });
});
