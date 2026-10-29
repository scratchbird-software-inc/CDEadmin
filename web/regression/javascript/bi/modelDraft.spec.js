/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  addDiscoveredSource, canonical, embeddedContent, emptyModel, fromDraft, parseTyped, portableId, sameDefinition,
  toDraft, uniqueId, validateDraft,
} from 'sources/cdeadmin_ui/modules/bi/models/modelDraft';
import {definitionOf, fillIds, initialSession, reduce} from 'sources/cdeadmin_ui/modules/bi/models/modelSession';
import {emptyQuery, parseDetailFields, queryErrors, toQuery} from 'sources/cdeadmin_ui/modules/bi/models/queryDraft';
import {modelForm, modelOptionContext, queryForm} from 'sources/cdeadmin_ui/modules/bi/models/modelForm';
import {modelFixtures as fixtures} from './modelFixtures';

const stored = () => JSON.parse(JSON.stringify(fixtures.draft.definition));
const profile = fixtures.catalog.capabilities.analytical_profile;

describe('model draft round trip', () => {
  it('rebuilds exactly the document the backend validator produced', () => {
    for(const record of [fixtures.draft, fixtures.published, fixtures.lossy]) {
      const {definition, problems} = fromDraft(toDraft(record.definition));
      expect(problems).toEqual([]);
      expect(canonical(definition)).toEqual(canonical(record.definition));
    }
  });

  it('keeps embedded charts, dashboards, reports and schedules byte for byte', () => {
    const original = stored();
    const {definition} = fromDraft(toDraft(original));
    for(const key of ['visualizations', 'dashboards', 'reports', 'schedules']) {
      expect(definition[key]).toEqual(original[key]);
      expect(definition[key].length).toBeGreaterThan(0);
    }
    expect(Object.keys(embeddedContent(original)).sort()).toEqual(
      ['dashboards', 'reports', 'schedules', 'visualizations']);
  });

  it('keeps keys the typed controls do not show', () => {
    const original = stored();
    original.annotations = {owner: 'finance'};
    original.sources[0].provider_config = {hint: 'x'};
    original.measures[0].extra_flag = true;
    original.security.future_key = {a: 1};
    const {definition} = fromDraft(toDraft(original));
    expect(definition.annotations).toEqual({owner: 'finance'});
    expect(definition.sources[0].provider_config).toEqual({hint: 'x'});
    expect(definition.measures[0].extra_flag).toBe(true);
    expect(definition.security.future_key).toEqual({a: 1});
  });

  it('turns a typed edit into the stored shape', () => {
    const draft = toDraft(stored());
    draft.measures = [...draft.measures, {id: 'avg_rev', name: 'Average', measure_kind: 'calculated',
      aggregation: 'none', calc_left: 'revenue', calc_operator: 'divide', calc_right: 'orders', _keep: {}}];
    draft.parameters = draft.parameters.map((row) => ({...row, default_text: '5'}));
    const {definition, problems} = fromDraft(draft);
    expect(problems).toEqual([]);
    expect(definition.measures.at(-1)).toMatchObject({id: 'avg_rev', aggregation: 'none', field: null,
      expression: {operator: 'divide', left: {measure: 'revenue'}, right: {measure: 'orders'}}});
    expect(definition.parameters[0].default).toBe(5);
  });

  it('reports a parameter value that does not match its type without losing the document', () => {
    const draft = toDraft(stored());
    draft.parameters = draft.parameters.map((row) => ({...row, default_text: 'many'}));
    const {definition, problems} = fromDraft(draft);
    expect(problems).toHaveLength(1);
    expect(problems[0]).toMatch(/Parameter floor/);
    expect(definition.sources).toHaveLength(1);
  });

  it('compares definitions by content, not key order', () => {
    const original = stored();
    const reordered = Object.fromEntries(Object.entries(original).reverse());
    expect(Object.keys(reordered)).not.toEqual(Object.keys(original));
    expect(sameDefinition(original, reordered)).toBe(true);
    expect(sameDefinition(original, {...original, name: 'Other'})).toBe(false);
  });
});

describe('typed values and identifiers', () => {
  it('makes portable, unique identifiers', () => {
    expect(portableId('Sales table!')).toBe('Sales_table_');
    expect(portableId('1st')).toBe('item_1st');
    expect(uniqueId('source', ['source', 'source_2'])).not.toBe('source');
    expect(uniqueId('source', [])).toBe('source');
  });

  it('parses text against a parameter type', () => {
    expect(parseTyped('3', 'integer', 'x')).toBe(3);
    expect(parseTyped('[1, 2]', 'array', 'x')).toEqual([1, 2]);
    expect(() => parseTyped('2.5', 'integer', 'x')).toThrow(/integer/);
    expect(() => parseTyped('maybe', 'boolean', 'x')).toThrow(/boolean/);
  });
});

describe('new models', () => {
  const resources = [
    {resource_id: 'column:1', resource_kind: 'column', display_name: 'amount', display_path: ['s', 'amount']},
    {resource_id: 'table:sales', resource_kind: 'table', display_name: 'sales', display_path: ['analytics', 'sales']},
  ];

  it('starts from the first discovered table of a kind the provider supports', () => {
    const model = emptyModel(resources, profile);
    expect(model.sources).toHaveLength(1);
    expect(model.sources[0]).toMatchObject({resource_id: 'table:sales', relation: ['analytics', 'sales'],
      source_kind: 'table', classification: 'fact'});
    expect(model.semantic_family).toBe('relational');
  });

  it('is a complete document with every section the contract has', () => {
    const model = emptyModel([], profile);
    expect(Object.keys(model).sort()).toEqual(Object.keys(stored()).sort());
  });

  it('adds a discovered source under an unused identifier', () => {
    const draft = addDiscoveredSource(toDraft(emptyModel(resources, profile)), resources[1], profile);
    expect(draft.sources.map((row) => row.id)).toEqual(['sales', 'sales_2']);
  });
});

describe('draft checks', () => {
  it('flags duplicate and non-portable identifiers, a missing name and no source', () => {
    const draft = toDraft(stored());
    draft.measures = [...draft.measures, {...draft.measures[0]}];
    draft.dimensions = [{...draft.dimensions[0], id: '9bad'}];
    draft.name = ' ';
    draft.sources = [];
    const errors = validateDraft(draft);
    expect(errors.measures).toMatch(/unique/);
    expect(errors.dimensions).toMatch(/identifiers/);
    expect(errors.name).toBeTruthy();
    expect(errors.sources).toBeTruthy();
  });

  it('accepts the stored model', () => {
    expect(validateDraft(toDraft(stored()))).toEqual({});
  });

  it('asks a tenant filter for its source and field', () => {
    const draft = {...toDraft(stored()), tenant_enabled: true};
    expect(validateDraft(draft).tenant_field).toBeTruthy();
  });
});

describe('model session reducer', () => {
  const loaded = () => reduce(initialSession(), {type: 'load', record: fixtures.draft});

  it('loads a record clean, with its identity and a draft', () => {
    const state = loaded();
    expect(state.record).toEqual({model_id: fixtures.draft.model_id, name: fixtures.draft.name,
      status: 'draft', revision: fixtures.draft.revision, updated_at: fixtures.draft.updated_at});
    expect(state.dirty).toBe(false);
    expect(state.draft.name).toBe('Sales cube');
  });

  it('becomes dirty on an edit and clean again when the edit is undone', () => {
    const state = loaded();
    const edited = reduce(state, {type: 'edit', field: 'name', value: 'Renamed'});
    expect(edited.dirty).toBe(true);
    expect(reduce(edited, {type: 'edit', field: 'name', value: 'Sales cube'}).dirty).toBe(false);
  });

  it('clears the validation result when the draft changes', () => {
    const validated = reduce(loaded(), {type: 'validated', result: fixtures.validOutcome});
    expect(validated.validation.valid).toBe(true);
    expect(validated.lineage).toEqual(fixtures.validOutcome.lineage);
    expect(reduce(validated, {type: 'edit', field: 'description', value: 'x'}).validation).toBeNull();
  });

  it('keeps the last lineage when validation fails', () => {
    const state = reduce(reduce(loaded(), {type: 'lineage', lineage: fixtures.lineage}),
      {type: 'validated', result: fixtures.invalidOutcome});
    expect(state.validation.valid).toBe(false);
    expect(state.lineage).toEqual(fixtures.lineage);
  });

  it('takes a status change without touching the draft or the dirty flag', () => {
    const edited = reduce(loaded(), {type: 'edit', field: 'name', value: 'Renamed'});
    const state = reduce(edited, {type: 'status', record: fixtures.published});
    expect(state.record).toMatchObject({status: 'published', revision: fixtures.published.revision});
    expect(state.draft.name).toBe('Renamed');
    expect(state.dirty).toBe(true);
  });

  it('starts a new model unsaved and clean', () => {
    const state = reduce(loaded(), {type: 'new', definition: emptyModel([], profile)});
    expect(state.record).toBeNull();
    expect(state.dirty).toBe(false);
  });

  it('replaces the whole draft from the advanced JSON tab', () => {
    const next = {...stored(), name: 'From JSON'};
    const state = reduce(loaded(), {type: 'definition', definition: next});
    expect(state.draft.name).toBe('From JSON');
    expect(state.dirty).toBe(true);
    expect(definitionOf(state).definition.name).toBe('From JSON');
  });

  it('adds a discovered source', () => {
    const state = reduce(loaded(), {type: 'addSource', profile, resource: {
      resource_id: 'table:extra', resource_kind: 'table', display_name: 'extra', display_path: ['extra']}});
    expect(state.draft.sources.map((row) => row.resource_id)).toEqual(['table:sales', 'table:extra']);
    expect(state.dirty).toBe(true);
  });

  it('gives new grid rows the next free identifier', () => {
    const draft = toDraft(stored());
    const filled = fillIds({...draft, measures: [...draft.measures, {name: 'New'}],
      dimensions: [...draft.dimensions, {name: 'D', hierarchies: [{name: 'H', levels: [{name: 'L'}]}]}]});
    const ids = filled.measures.map((row) => row.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.at(-1)).toMatch(/^measure/);
    const added = filled.dimensions.at(-1);
    expect(added.id).toMatch(/^dimension/);
    expect(added.hierarchies[0].id).toMatch(/^hierarchy/);
    expect(added.hierarchies[0].levels[0].id).toMatch(/^level/);
  });

  it('leaves an identifier the user cleared alone', () => {
    const draft = toDraft(stored());
    expect(fillIds({...draft, measures: [{...draft.measures[0], id: ''}]}).measures[0].id).toBe('');
  });

  it('builds no definition before a model is open', () => {
    expect(definitionOf(initialSession())).toEqual({definition: null, problems: []});
  });
});

describe('model forms', () => {
  it('has the editor tabs, one per concern', () => {
    expect(modelForm(profile).tabs.map((tab) => tab.tab)).toEqual(
      ['model', 'dimensions', 'measures', 'parameters', 'security', 'materializations']);
  });

  it('takes source and classification vocabulary from the provider profile', () => {
    const graph = {source_kinds: ['node'], source_classifications: ['node-set'], measure_kinds: ['score']};
    const sources = modelForm(graph).tabs[0].fields.find((field) => field.field_id === 'sources');
    const kinds = sources.columns.find((column) => column.field_id === 'source_kind');
    expect(kinds.options.map((option) => option.value)).toEqual(['node']);
  });

  it('offers time intelligence and window fields only when the provider supports them', () => {
    const fieldIds = (capabilities) => queryForm(capabilities).tabs[0].fields.map((field) => field.field_id);
    expect(fieldIds({})).not.toContain('time_operation');
    expect(fieldIds({})).not.toContain('windows');
    const capabilities = fixtures.catalog.capabilities;
    expect(fieldIds(capabilities)).toEqual(expect.arrayContaining(['time_operation', 'windows']));
  });

  it('derives the reference lists from the draft, with an explicit none', () => {
    const draft = toDraft(stored());
    const {model} = modelOptionContext(draft, null);
    expect(model.sources.map((item) => item.value)).toEqual(['sales']);
    expect(model.measures.map((item) => item.value)).toEqual(['revenue', 'orders']);
    expect(model.levels.map((item) => item.value)).toEqual(['region', 'region_level']);
    expect(model.levels_or_none[0]).toEqual({value: '', label: 'None'});
    expect(model.parameters_or_none.map((item) => item.value)).toEqual(['', 'floor']);
  });
});

describe('cube query draft', () => {
  it('builds the query document the backend compiles', () => {
    const query = {...emptyQuery(), rows: ['region_level'], measures: ['revenue'],
      filters: [{source_id: 'sales', field: 'amount', operator: 'gte', value_text: '10', parameter_id: ''}],
      parameters: [{parameter_id: 'floor', value_text: '3'}]};
    const {query: document, problems} = toQuery(query, stored().parameters);
    expect(problems).toEqual([]);
    expect(document).toMatchObject({
      axes: {rows: ['region_level'], columns: [], pages: []}, measures: ['revenue'],
      filters: [{field: {source_id: 'sales', field: 'amount'}, operator: 'gte', value: 10}],
      parameters: {floor: 3}, totals: false, limit: 500,
      drill: {mode: 'summary', target_level: null, detail_fields: []}, time_intelligence: {}, windows: [],
    });
  });

  it('binds a filter to a parameter instead of a value', () => {
    const query = {...emptyQuery(), measures: ['revenue'], filters: [
      {source_id: 'sales', field: 'amount', operator: 'gte', value_text: '10', parameter_id: 'floor'}]};
    const {query: document} = toQuery(query, stored().parameters);
    expect(document.filters[0]).toEqual({field: {source_id: 'sales', field: 'amount'}, operator: 'gte',
      parameter_id: 'floor'});
  });

  it('adds time intelligence and windows only when chosen', () => {
    const query = {...emptyQuery(), measures: ['revenue'], time_operation: 'period_comparison',
      time_dimension: 'order_date', time_period: 'month', time_anchor: '2026-03-01',
      windows: [{id: 'Run Total', measure_id: 'revenue', operation: 'running_sum', partition_by: [],
        order_level: 'region_level', direction: 'asc', frame_size: 1}]};
    const {query: document} = toQuery(query, []);
    expect(document.time_intelligence).toEqual({operation: 'period_comparison', dimension_id: 'order_date',
      period: 'month', anchor: '2026-03-01'});
    expect(document.windows[0]).toMatchObject({id: 'Run_Total', order_by: {level_id: 'region_level', direction: 'asc'}});
  });

  it('reports a parameter value of the wrong type', () => {
    const query = {...emptyQuery(), measures: ['revenue'], parameters: [{parameter_id: 'floor', value_text: 'lots'}]};
    expect(toQuery(query, stored().parameters).problems).toHaveLength(1);
  });

  it('parses drill-through fields and asks for a measure and a drill target', () => {
    expect(parseDetailFields('sales.region, sales.customer.name, bad')).toEqual([
      {source_id: 'sales', field: 'region'}, {source_id: 'sales', field: 'customer.name'}]);
    expect(queryErrors(emptyQuery()).measures).toBeTruthy();
    expect(queryErrors({...emptyQuery(), measures: ['m'], drill_mode: 'down'}).drill_target).toBeTruthy();
    expect(queryErrors({...emptyQuery(), measures: ['m']})).toEqual({});
  });
});
