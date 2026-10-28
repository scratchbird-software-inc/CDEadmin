/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  aggregationsFor, operatorsFor, parseList, parseValue, typeCategory, valueText,
} from 'sources/cdeadmin_ui/modules/bi/columnTypes';
import {emptyState, reduce} from 'sources/cdeadmin_ui/modules/bi/queryState';
import {orderTargets, outputId, tableOutputs} from 'sources/cdeadmin_ui/modules/bi/outputs';
import {errorAt, validateState} from 'sources/cdeadmin_ui/modules/bi/validateState';

const apply = (state, ...actions) => actions.reduce(reduce, state);

describe('typeCategory', () => {
  it.each([
    ['INTEGER', 'number'], ['NUMERIC(10,2)', 'number'], ['bigint unsigned', 'number'],
    ['double precision', 'number'], ['VARCHAR(20)', 'text'], ['text', 'text'], ['', 'text'],
    ['TIMESTAMP WITH TIME ZONE', 'date'], ['date', 'date'], ['boolean', 'boolean'],
    [undefined, 'text'],
  ])('%s is %s', (type, category) => expect(typeCategory(type)).toBe(category));
});

describe('operators and summaries per category', () => {
  it('offers ranges for numbers and dates but not text', () => {
    expect(operatorsFor('number')).toContain('between');
    expect(operatorsFor('date')).toContain('between');
    expect(operatorsFor('text')).not.toContain('between');
    expect(operatorsFor('nope')).toEqual(operatorsFor('text'));
  });
  it('offers sum and avg for numbers only', () => {
    expect(aggregationsFor('number')).toEqual(expect.arrayContaining(['sum', 'avg']));
    expect(aggregationsFor('text')).not.toContain('sum');
    expect(aggregationsFor('boolean')).toEqual(['count', 'count_distinct']);
  });
});

describe('value parsing', () => {
  it('types numbers and booleans and reports bad input', () => {
    expect(parseValue('number', ' 12.5 ')).toEqual({value: 12.5});
    expect(parseValue('number', 'abc').error).toBeTruthy();
    expect(parseValue('number', '').error).toBeTruthy();
    expect(parseValue('boolean', 'true')).toEqual({value: true});
    expect(parseValue('boolean', 'x').error).toBeTruthy();
    expect(parseValue('text', ' a ')).toEqual({value: 'a'});
  });
  it('parses lists and round-trips them to text', () => {
    expect(parseList('number', '1, 2,3')).toEqual({value: [1, 2, 3]});
    expect(parseList('number', '1, x').error).toBeTruthy();
    expect(parseList('text', ' , ').error).toBeTruthy();
    expect(valueText([5, 30])).toBe('5, 30');
    expect(valueText(null)).toBe('');
    expect(valueText(0)).toBe('0');
  });
});

describe('output naming', () => {
  it('mirrors the backend identifier rules', () => {
    expect(outputId('Order Total!')).toBe('Order_Total');
    expect(outputId('9lives')).toBe('c_9lives');
    expect(outputId('###')).toBe('col');
  });

  it('numbers duplicate outputs and offers native names for sorting', () => {
    const state = apply(emptyState(), {type: 'selectTable', relation: ['t']},
      {type: 'addColumn', column: 'a b'}, {type: 'addColumn', column: 'a_b'});
    expect(tableOutputs(state).map((output) => output.id)).toEqual(['a_b', 'a_b_2']);
    expect(orderTargets(state).map((target) => target.id)).toEqual(['a_b', 'a_b_2', 'a b']);
  });

  it('lists dimensions then measures for a semantic source', () => {
    const state = apply(emptyState(), {type: 'selectModel', id: 'm'},
      {type: 'addMeasure', id: 'revenue'}, {type: 'addDimension', id: 'region'});
    const model = {dimensions: [{id: 'region', name: 'Region'}], measures: [{id: 'revenue', name: 'Revenue'}]};
    expect(orderTargets(state, model)).toEqual([
      {id: 'region', kind: 'dimension', label: 'Region'},
      {id: 'revenue', kind: 'measure', label: 'Revenue'}]);
  });
});

describe('validateState', () => {
  const ready = apply(emptyState({name: 'Ok'}), {type: 'selectTable', relation: ['t']},
    {type: 'addColumn', column: 'a'});

  it('accepts a complete question', () => {
    expect(validateState(ready, {forSave: true})).toEqual([]);
  });

  it('asks for a source, a selection and a name', () => {
    expect(errorAt(validateState(emptyState()), 'source')).toMatch(/table/);
    const noColumns = apply(emptyState(), {type: 'selectTable', relation: ['t']});
    expect(errorAt(validateState(noColumns), 'selection')).toMatch(/column or summary/);
    expect(errorAt(validateState(emptyState(), {forSave: true}), 'name')).toMatch(/name/);
  });

  it('requires a column for every summary but count', () => {
    const state = apply(ready, {type: 'addAggregation', function: 'sum'});
    expect(errorAt(validateState(state), 'aggregations.0')).toMatch(/column/);
    expect(validateState(apply(ready, {type: 'addAggregation', function: 'count'}))).toEqual([]);
  });

  it('checks filter values by type and shape', () => {
    const filter = (operator, text) => apply(ready,
      {type: 'addFilter', column: 'a', valueType: 'number', operator},
      {type: 'updateFilter', key: 'f1', patch: {text}});
    expect(errorAt(validateState(filter('gt', 'x')), 'filters.f1')).toMatch(/number/);
    expect(errorAt(validateState(filter('between', '1')), 'filters.f1')).toMatch(/two values/);
    expect(validateState(filter('between', '1, 2'))).toEqual([]);
    expect(validateState(filter('is_null', ''))).toEqual([]);
  });

  it('checks the limit, the sort targets and parameter names', () => {
    expect(errorAt(validateState(apply(ready, {type: 'setLimit', limit: 0})), 'limit')).toMatch(/1 to/);
    const sorted = {...ready, orderBy: [{target: 'ghost', direction: 'asc'}]};
    expect(errorAt(validateState(sorted), 'order.0')).toMatch(/shown/);
    const params = apply(ready, {type: 'addParameter', parameter: {id: '1bad', type: 'string'}});
    expect(errorAt(validateState(params), 'parameters.1bad')).toMatch(/start with a letter/);
  });

  it('needs a statement in SQL mode and a measure for a model', () => {
    expect(errorAt(validateState(emptyState({mode: 'sql'})), 'sql')).toBeTruthy();
    const model = apply(emptyState(), {type: 'selectModel', id: 'm'});
    expect(errorAt(validateState(model), 'selection')).toMatch(/measure/);
  });
});
