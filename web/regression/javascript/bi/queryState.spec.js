/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  emptyState, fromQuestion, hasSelection, parameterValues, reduce, toQuestion,
} from 'sources/cdeadmin_ui/modules/bi/queryState';
import {conversions, questions} from './biFixtures';

// The backend stamps contract_version itself; the UI never sends it.
const wire = ({contract_version: _version, ...rest}) => rest;
const apply = (state, ...actions) => actions.reduce(reduce, state);
const record = (definition, overrides = {}) => ({
  question_id: 'q-1', revision: 3, status: 'active', definition, ...overrides});

describe('question document round trips', () => {
  it.each(Object.keys(questions))('%s question: stored document -> builder state -> request payload', (name) => {
    const state = fromQuestion(record(questions[name]));
    expect(toQuestion(state)).toEqual(wire(questions[name]));
    expect(state.dirty).toBe(false);
    expect(state.questionId).toBe('q-1');
    expect(state.revision).toBe(3);
  });

  it('accepts a bare question document such as the one bi_sql_to_question returns', () => {
    const state = fromQuestion(conversions.exact.question);
    expect(state.questionId).toBeNull();
    expect(toQuestion(state).query).toEqual(conversions.exact.question.query);
    expect(toQuestion(state).parameters).toEqual(conversions.exact.question.parameters);
  });

  it('keeps types of stored filter values (numbers, lists, ranges, parameters)', () => {
    const state = fromQuestion(record(questions.filters));
    expect(state.filters.map((filter) => [filter.operator, filter.type, filter.text, filter.parameterId])).toEqual([
      ['between', 'number', '5, 30', ''],
      ['in', 'text', 'east, west', ''],
      ['gte', 'text', '', 'min_amount'],
      ['is_not_null', 'text', '', ''],
    ]);
  });

  it('gives an unnamed question a placeholder name so it can be previewed', () => {
    expect(toQuestion(emptyState()).name).toBe('Untitled question');
  });
});

describe('building the detail question from actions', () => {
  const built = () => apply(emptyState(),
    {type: 'rename', name: 'Big sales'},
    {type: 'selectTable', relation: ['sales']},
    {type: 'addColumn', column: 'region'},
    {type: 'addColumn', column: 'amount'},
    {type: 'aliasColumn', column: 'amount', alias: 'total'},
    {type: 'addFilter', column: 'amount', valueType: 'number', operator: 'gt'},
    {type: 'updateFilter', key: 'f1', patch: {text: '10'}},
    {type: 'addOrder', target: 'amount', direction: 'desc'},
    {type: 'setLimit', limit: 3});

  it('produces the payload the backend normalizes to the detail fixture', () => {
    const {result_policy: _policy, ...expected} = wire(questions.detail);
    expect(toQuestion(built())).toEqual(expected);
  });

  it('ignores a column added twice and a sort added twice', () => {
    const state = apply(built(), {type: 'addColumn', column: 'region'}, {type: 'addOrder', target: 'amount'});
    expect(state.columns).toHaveLength(2);
    expect(state.orderBy).toHaveLength(1);
  });

  it('flags edits as unsaved but not run-time values or catalog retyping', () => {
    const clean = fromQuestion(record(questions.detail));
    expect(apply(clean, {type: 'rename', name: 'Other'}).dirty).toBe(true);
    expect(apply(clean, {type: 'setValue', id: 'x', text: '1'}).dirty).toBe(false);
    expect(apply(clean, {type: 'retypeFilters', types: {amount: 'number'}})).toBe(
      apply(clean, {type: 'retypeFilters', types: {amount: 'number'}}));
    expect(reduce(clean, {type: 'unknown'})).toBe(clean);
  });
});

describe('summaries', () => {
  const picked = apply(emptyState(),
    {type: 'selectTable', relation: ['sales']},
    {type: 'addColumn', column: 'region'});

  it('turns picked columns into the grouping when the first summary is added', () => {
    const state = apply(picked,
      {type: 'addAggregation', function: 'sum', column: 'amount'},
      {type: 'updateAggregation', index: 0, patch: {alias: 'revenue'}},
      {type: 'addAggregation', function: 'count'},
      {type: 'updateAggregation', index: 1, patch: {alias: 'orders'}},
      {type: 'addOrder', target: 'revenue', direction: 'desc'},
      {type: 'setLimit', limit: 10});
    expect(state.columns).toEqual([]);
    expect(state.groupBy).toEqual([{column: 'region'}]);
    const builder = toQuestion(state).query.builder;
    expect(builder.columns).toEqual([]);
    expect(builder.group_by).toEqual([{column: 'region'}]);
    expect(builder.aggregations).toEqual(wire(questions.summary).query.builder.aggregations);
    expect(builder.order_by).toEqual([{column: 'revenue', direction: 'desc'}]);
  });

  it('gives the grouping back to the columns when the last summary is removed', () => {
    const state = apply(picked,
      {type: 'addAggregation', function: 'count'},
      {type: 'removeAggregation', index: 0});
    expect(state.groupBy).toEqual([]);
    expect(state.columns).toEqual([{column: 'region'}]);
  });

  it('drops a sort that no longer names an output', () => {
    const state = apply(picked,
      {type: 'addAggregation', function: 'sum', column: 'amount'},
      {type: 'addOrder', target: 'sum_amount'},
      {type: 'updateAggregation', index: 0, patch: {alias: 'revenue'}});
    expect(state.orderBy).toEqual([]);
  });

  it('removes an empty alias and column instead of sending empty strings', () => {
    const state = apply(picked,
      {type: 'addAggregation', function: 'sum', column: 'amount'},
      {type: 'updateAggregation', index: 0, patch: {alias: '', column: ''}});
    expect(state.aggregations[0]).toEqual({function: 'sum'});
  });
});

describe('filters and parameters', () => {
  const withFilter = apply(emptyState(),
    {type: 'selectTable', relation: ['sales']}, {type: 'addColumn', column: 'region'},
    {type: 'addParameter', parameter: {id: 'floor', type: 'integer'}},
    {type: 'addFilter', column: 'amount', valueType: 'number', operator: 'gt'},
    {type: 'updateFilter', key: 'f1', patch: {text: '7'}});

  it('sends the typed value, a bound parameter, or nothing for IS NULL', () => {
    const filterOf = (state) => toQuestion(state).query.builder.filters[0];
    expect(filterOf(withFilter)).toEqual({operator: 'gt', column: 'amount', value: 7});
    const bound = apply(withFilter, {type: 'updateFilter', key: 'f1', patch: {parameterId: 'floor'}});
    expect(bound.filters[0].text).toBe('');
    expect(filterOf(bound)).toEqual({operator: 'gt', column: 'amount', parameter_id: 'floor'});
    const typed = apply(bound, {type: 'updateFilter', key: 'f1', patch: {text: '9'}});
    expect(typed.filters[0].parameterId).toBe('');
    const unary = apply(typed, {type: 'updateFilter', key: 'f1', patch: {operator: 'is_null'}});
    expect(filterOf(unary)).toEqual({operator: 'is_null', column: 'amount'});
  });

  it('clears the value when the operator changes shape', () => {
    const range = apply(withFilter, {type: 'updateFilter', key: 'f1', patch: {operator: 'between'}});
    expect(range.filters[0].text).toBe('');
    const same = apply(withFilter, {type: 'updateFilter', key: 'f1', patch: {operator: 'gte'}});
    expect(same.filters[0].text).toBe('7');
  });

  it('detaches filters from a removed parameter', () => {
    const bound = apply(withFilter, {type: 'updateFilter', key: 'f1', patch: {parameterId: 'floor'}});
    const state = apply(bound, {type: 'removeParameter', id: 'floor'});
    expect(state.parameters).toEqual([]);
    expect(state.filters[0].parameterId).toBe('');
  });

  it('types run-time values by the declared parameter type and skips empty ones', () => {
    const state = apply(emptyState(),
      {type: 'addParameter', parameter: {id: 'floor', type: 'integer'}},
      {type: 'addParameter', parameter: {id: 'on', type: 'boolean'}},
      {type: 'addParameter', parameter: {id: 'tags', type: 'array'}},
      {type: 'addParameter', parameter: {id: 'who', type: 'string'}},
      {type: 'setValue', id: 'floor', text: '5'}, {type: 'setValue', id: 'on', text: 'true'},
      {type: 'setValue', id: 'tags', text: 'a, b'}, {type: 'setValue', id: 'who', text: ' '});
    expect(parameterValues(state)).toEqual({floor: 5, on: true, tags: ['a', 'b']});
  });

  it('declares a default only when one was typed', () => {
    const state = apply(emptyState(),
      {type: 'addParameter', parameter: {id: 'floor', type: 'integer'}},
      {type: 'updateParameter', id: 'floor', patch: {defaultText: '3', required: true}});
    expect(toQuestion(state).parameters).toEqual([
      {id: 'floor', name: 'floor', type: 'integer', required: true, allowed_values: [], default: 3}]);
  });
});

describe('semantic model sources', () => {
  it('builds the semantic question the backend expects', () => {
    const state = apply(emptyState({name: 'Cube question'}),
      {type: 'selectModel', id: 'model-1', revision: 1},
      {type: 'addDimension', id: 'region'}, {type: 'addMeasure', id: 'revenue'},
      {type: 'addFilter', field: {source_id: 'sales', field: 'region'}, valueType: 'text', operator: 'eq'},
      {type: 'updateFilter', key: 'f1', patch: {text: 'west'}},
      {type: 'addOrder', target: 'revenue', direction: 'desc'}, {type: 'setLimit', limit: 5});
    const {result_policy: _policy, ...expected} = wire(questions.semantic);
    expect(toQuestion(state)).toEqual(expected);
  });

  it('drops a sort when its measure is removed', () => {
    const state = apply(emptyState(),
      {type: 'selectModel', id: 'm'}, {type: 'addMeasure', id: 'revenue'},
      {type: 'addOrder', target: 'revenue'}, {type: 'removeMeasure', id: 'revenue'});
    expect(state.orderBy).toEqual([]);
  });

  it('changing the source resets what was picked but keeps the name and parameters', () => {
    const state = apply(emptyState({name: 'Keep'}),
      {type: 'addParameter', parameter: {id: 'p', type: 'string'}},
      {type: 'selectTable', relation: ['a']}, {type: 'addColumn', column: 'x'},
      {type: 'selectTable', relation: ['b']});
    expect(state.columns).toEqual([]);
    expect(state.name).toBe('Keep');
    expect(state.parameters).toHaveLength(1);
  });
});

describe('SQL mode, conversion and revisions', () => {
  it('sends the raw statement unchanged', () => {
    const state = apply(emptyState(), {type: 'setMode', mode: 'sql'}, {type: 'setSql', sql: 'SELECT 1'});
    expect(toQuestion(state).query).toEqual({kind: 'sql', sql: 'SELECT 1'});
    expect(toQuestion(state).semantic_model).toBeNull();
    expect(hasSelection(state)).toBe(true);
    expect(hasSelection(emptyState({mode: 'sql'}))).toBe(false);
  });

  it('adopts a converted question and keeps the identity of the edit in progress', () => {
    const stored = fromQuestion(record(questions.raw));
    const state = reduce(stored, {type: 'convert', question: conversions.exact.question});
    expect(state.mode).toBe('builder');
    expect(state.questionId).toBe('q-1');
    expect(state.revision).toBe(3);
    expect(state.name).toBe('Raw floor');
    expect(state.dirty).toBe(true);
    expect(toQuestion(state).query.builder.source).toEqual({relation: ['sales']});
  });

  it('restores an older revision as an unsaved draft of the same question', () => {
    const current = fromQuestion(record(questions.summary, {revision: 5}));
    const state = reduce(current, {type: 'restore', definition: questions.detail});
    expect(state.questionId).toBe('q-1');
    expect(state.revision).toBe(5);
    expect(state.name).toBe('Big sales');
    expect(state.dirty).toBe(true);
  });

  it('marks the state clean again after a save', () => {
    const dirty = apply(fromQuestion(record(questions.detail)), {type: 'rename', name: 'Renamed'});
    const saved = reduce(dirty, {type: 'saved', record: record(
      {...questions.detail, name: 'Renamed'}, {revision: 4})});
    expect(saved.dirty).toBe(false);
    expect(saved.revision).toBe(4);
    expect(saved.name).toBe('Renamed');
  });

  it('starts a new question in a collection', () => {
    const state = reduce(emptyState(), {type: 'new', collectionId: 'c-1'});
    expect(state.collectionId).toBe('c-1');
    expect(state.dirty).toBe(false);
  });
});
