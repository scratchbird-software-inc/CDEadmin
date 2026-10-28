/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Builder state for BI saved questions: one pure reducer plus the two
 * conversions that connect it to the backend contract (docs/en_US/
 * bi_saved_questions.rst): toQuestion(state) produces the question document
 * the bi_* actions accept, fromQuestion(record) loads one. Nothing here
 * touches the DOM, the network or an engine identity.
 *
 * State shape (all UI-only fields are listed here and never leave the module):
 *   questionId, revision, status   identity of the stored question, if any
 *   name, description, collectionId
 *   mode                           'builder' | 'sql'
 *   source                         {kind: 'table', relation: [..]} or
 *                                  {kind: 'model', model: {id, revision}}
 *   columns, groupBy               [{column, alias?}]  (columns is empty
 *                                  while summaries exist; groupBy is empty
 *                                  without summaries)
 *   aggregations                   [{function, column?, alias?}]
 *   dimensions, measures           ids, for model sources
 *   filters                        [{key, type, operator, column | field,
 *                                    text, parameterId}]
 *   orderBy                        [{target, direction}]
 *   limit, sql, parameters, visualization, resultPolicy
 *   values                         run-time parameter values {id: text}
 *   dirty                          unsaved edits
 */

import {
  CATEGORIES, isListOperator, isRangeOperator, isUnaryOperator,
  parseList, parseValue, valueText,
} from './columnTypes';
import {orderTargets} from './outputs';

export const DEFAULT_LIMIT = 500;
export const MAX_LIMIT = 10000;
export const UNTITLED = 'Untitled question';
export const CHART_TYPES = Object.freeze([
  'table', 'bar', 'line', 'area', 'scatter', 'pie', 'metric']);

const isPlain = (value) => value && typeof value === 'object' && !Array.isArray(value);

export function emptyState(overrides = {}) {
  return {
    questionId: null, revision: null, status: 'active',
    name: '', description: '', collectionId: null,
    mode: 'builder',
    source: {kind: 'table', relation: []},
    columns: [], groupBy: [], aggregations: [],
    dimensions: [], measures: [],
    filters: [], orderBy: [],
    limit: DEFAULT_LIMIT, sql: '',
    parameters: [], values: {},
    visualization: {type: 'table', settings: {}},
    resultPolicy: null,
    dirty: false, nextKey: 1,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------

function parseParameterText(type, text) {
  const raw = String(text ?? '').trim();
  switch(type) {
  case 'integer': {
    const number = Number(raw);
    return raw !== '' && Number.isInteger(number) ? {value: number} : {error: true};
  }
  case 'number': {
    const number = Number(raw);
    return raw !== '' && Number.isFinite(number) ? {value: number} : {error: true};
  }
  case 'boolean':
    return raw === 'true' || raw === 'false' ? {value: raw === 'true'} : {error: true};
  case 'array':
    return {value: raw.split(',').map((part) => part.trim()).filter(Boolean)};
  default:
    return {value: raw};
  }
}

/** Typed run-time values for the parameters that have one, keyed by id. */
export function parameterValues(state) {
  const result = {};
  for(const parameter of state.parameters) {
    const text = state.values[parameter.id];
    if(text === undefined || String(text).trim() === '') continue;
    const parsed = parseParameterText(parameter.type, text);
    result[parameter.id] = parsed.error ? text : parsed.value;
  }
  return result;
}

function parameterDocument(parameter) {
  const document = {
    id: parameter.id, name: parameter.name || parameter.id,
    type: parameter.type, required: Boolean(parameter.required),
    allowed_values: parameter.allowed_values || [],
  };
  if(String(parameter.defaultText ?? '').trim() !== '') {
    const parsed = parseParameterText(parameter.type, parameter.defaultText);
    document.default = parsed.error ? parameter.defaultText : parsed.value;
  }
  return document;
}

function parameterState(document) {
  return {
    id: document.id, name: document.name || document.id,
    type: document.type || 'string', required: Boolean(document.required),
    allowed_values: document.allowed_values || [],
    defaultText: 'default' in document ? valueText(document.default) : '',
  };
}

// ---------------------------------------------------------------------------
// state -> question document
// ---------------------------------------------------------------------------

function filterDocument(filter, semantic) {
  const entry = {operator: filter.operator};
  if(semantic) entry.field = {...filter.field};
  else entry.column = filter.column;
  if(isUnaryOperator(filter.operator)) return entry;
  if(filter.parameterId) {
    entry.parameter_id = filter.parameterId;
    return entry;
  }
  const parsed = isListOperator(filter.operator) || isRangeOperator(filter.operator) ?
    parseList(filter.type, filter.text) : parseValue(filter.type, filter.text);
  entry.value = parsed.error ? filter.text : parsed.value;
  return entry;
}

const named = (entry) => ({column: entry.column, ...(entry.alias ? {alias: entry.alias} : {})});

function queryDocument(state) {
  if(state.mode === 'sql') return {kind: 'sql', sql: state.sql};
  const limit = state.limit;
  if(state.source.kind === 'model') {
    return {kind: 'semantic', builder: {
      group_by: [...state.dimensions],
      aggregations: state.measures.map((id) => ({measure_id: id})),
      filters: state.filters.map((filter) => filterDocument(filter, true)),
      order_by: state.orderBy.map((entry) => ({id: entry.target, direction: entry.direction})),
      limit,
    }};
  }
  const summarized = state.aggregations.length > 0;
  return {kind: 'builder', builder: {
    source: {relation: [...state.source.relation]},
    columns: summarized ? [] : state.columns.map(named),
    group_by: summarized ? state.groupBy.map(named) : [],
    aggregations: state.aggregations.map((entry) => ({
      function: entry.function,
      ...(entry.column ? {column: entry.column} : {}),
      ...(entry.alias ? {alias: entry.alias} : {}),
    })),
    filters: state.filters.map((filter) => filterDocument(filter, false)),
    order_by: state.orderBy.map((entry) => ({column: entry.target, direction: entry.direction})),
    limit,
  }};
}

/**
 * The saved-question document for the current state. An unnamed question gets
 * a placeholder name so previews and runs work before the first save; the save
 * dialog asks for a real one.
 */
export function toQuestion(state) {
  const question = {
    name: state.name.trim() || UNTITLED,
    description: state.description,
    collection_id: state.collectionId,
    semantic_model: state.source.kind === 'model' && state.mode === 'builder' ?
      {id: state.source.model.id, revision: state.source.model.revision ?? null} : null,
    query: queryDocument(state),
    visualization: {type: state.visualization.type, settings: {...state.visualization.settings}},
    parameters: state.parameters.map(parameterDocument),
  };
  if(state.resultPolicy) question.result_policy = state.resultPolicy;
  return question;
}

// ---------------------------------------------------------------------------
// question document -> state
// ---------------------------------------------------------------------------

function inferType(value) {
  const sample = Array.isArray(value) ? value[0] : value;
  if(typeof sample === 'number') return CATEGORIES.NUMBER;
  if(typeof sample === 'boolean') return CATEGORIES.BOOLEAN;
  return CATEGORIES.TEXT;
}

function filterState(document, key) {
  const filter = {
    key: `f${key}`, type: inferType(document.value),
    operator: document.operator || 'eq',
    text: valueText(document.value), parameterId: document.parameter_id || '',
  };
  if(document.field) filter.field = {...document.field};
  else filter.column = document.column;
  return filter;
}

function namedState(entry) {
  const item = typeof entry === 'string' ? {column: entry} : entry;
  return {column: item.column, ...(item.alias ? {alias: item.alias} : {})};
}

/**
 * Load a question into builder state. `record` is either a bi_question_get
 * response ({question_id, revision, status, definition}) or a bare question
 * document (for example the result of bi_sql_to_question).
 */
export function fromQuestion(record) {
  const definition = record.definition || record;
  const state = emptyState({
    questionId: record.question_id ?? null, revision: record.revision ?? null,
    status: record.status || 'active',
    name: definition.name || '', description: definition.description || '',
    collectionId: definition.collection_id ?? null,
    parameters: (definition.parameters || []).map(parameterState),
    visualization: {
      type: definition.visualization?.type || 'table',
      settings: {...(definition.visualization?.settings || {})},
    },
    resultPolicy: definition.result_policy || null,
  });
  const query = definition.query;
  if(query.kind === 'sql') {
    return {...state, mode: 'sql', sql: query.sql};
  }
  const builder = query.builder;
  let key = 1;
  const filters = (builder.filters || []).map((filter) => filterState(filter, key++));
  const next = {...state, filters, nextKey: key, limit: builder.limit ?? DEFAULT_LIMIT};
  if(query.kind === 'semantic') {
    return {
      ...next, source: {kind: 'model', model: {
        id: definition.semantic_model.id, revision: definition.semantic_model.revision ?? null}},
      dimensions: [...(builder.group_by || [])],
      measures: (builder.aggregations || []).map((entry) => entry.measure_id),
      orderBy: (builder.order_by || []).map((entry) => ({target: entry.id, direction: entry.direction || 'asc'})),
    };
  }
  const aggregations = (builder.aggregations || []).map((entry) => ({...entry}));
  return {
    ...next, source: {kind: 'table', relation: [...builder.source.relation]},
    columns: aggregations.length ? [] : (builder.columns || []).map(namedState),
    groupBy: aggregations.length ? (builder.group_by || []).map(namedState) : [],
    aggregations,
    orderBy: (builder.order_by || []).map((entry) => ({target: entry.column, direction: entry.direction || 'asc'})),
  };
}

// ---------------------------------------------------------------------------
// reducer
// ---------------------------------------------------------------------------

const without = (list, index) => list.filter((_item, position) => position !== index);
const replaceAt = (list, index, value) => list.map((item, position) => position === index ? value : item);

function pruneOrder(state) {
  const valid = new Set(orderTargets(state, null).map((target) => target.id));
  const orderBy = state.orderBy.filter((entry) => valid.has(entry.target));
  return orderBy.length === state.orderBy.length ? state : {...state, orderBy};
}

function normalizeFilter(filter, patch) {
  const next = {...filter, ...patch};
  if('operator' in patch) {
    if(isUnaryOperator(next.operator)) {
      next.text = '';
      next.parameterId = '';
    } else if(!isListOperator(filter.operator) && isListOperator(next.operator) ||
        !isRangeOperator(filter.operator) && isRangeOperator(next.operator)) {
      next.text = '';
    }
  }
  if('parameterId' in patch && patch.parameterId) next.text = '';
  if('text' in patch && patch.text) next.parameterId = '';
  return next;
}

function resetSource(state, source) {
  return {
    ...state, source,
    columns: [], groupBy: [], aggregations: [], dimensions: [], measures: [],
    filters: [], orderBy: [],
  };
}

function step(state, action) {
  switch(action.type) {
  case 'rename': return {...state, name: action.name};
  case 'describe': return {...state, description: action.description};
  case 'setCollection': return {...state, collectionId: action.collectionId ?? null};
  case 'setMode': return {...state, mode: action.mode};
  case 'setSql': return {...state, sql: action.sql};
  case 'setLimit': return {...state, limit: action.limit};
  case 'selectTable':
    return resetSource(state, {kind: 'table', relation: [...action.relation]});
  case 'selectModel':
    return resetSource(state, {kind: 'model', model: {id: action.id, revision: action.revision ?? null}});

  case 'addColumn':
    if(state.columns.some((entry) => entry.column === action.column)) return state;
    return {...state, columns: [...state.columns, {column: action.column}]};
  case 'removeColumn':
    return pruneOrder({...state, columns: state.columns.filter((entry) => entry.column !== action.column)});
  case 'aliasColumn':
    return {...state, columns: state.columns.map((entry) => entry.column === action.column ?
      named({column: entry.column, alias: action.alias.trim()}) : entry)};

  case 'addGroupBy':
    if(state.groupBy.some((entry) => entry.column === action.column)) return state;
    return {...state, groupBy: [...state.groupBy, {column: action.column}]};
  case 'removeGroupBy':
    return pruneOrder({...state, groupBy: state.groupBy.filter((entry) => entry.column !== action.column)});

  case 'addAggregation': {
    const entry = {function: action.function, ...(action.column ? {column: action.column} : {})};
    if(state.aggregations.length === 0) {
      // Picked columns become the grouping, because a summary groups what is shown.
      return {...state, aggregations: [entry], groupBy: state.columns, columns: []};
    }
    return {...state, aggregations: [...state.aggregations, entry]};
  }
  case 'updateAggregation': {
    const current = state.aggregations[action.index];
    if(!current) return state;
    const merged = {...current, ...action.patch};
    if(!merged.column) delete merged.column;
    if(!merged.alias) delete merged.alias;
    return pruneOrder({...state, aggregations: replaceAt(state.aggregations, action.index, merged)});
  }
  case 'removeAggregation': {
    const aggregations = without(state.aggregations, action.index);
    const base = {...state, aggregations};
    return pruneOrder(aggregations.length ? base :
      {...base, columns: state.groupBy, groupBy: []});
  }

  case 'addDimension':
    return state.dimensions.includes(action.id) ? state :
      {...state, dimensions: [...state.dimensions, action.id]};
  case 'removeDimension':
    return pruneOrder({...state, dimensions: state.dimensions.filter((id) => id !== action.id)});
  case 'addMeasure':
    return state.measures.includes(action.id) ? state :
      {...state, measures: [...state.measures, action.id]};
  case 'removeMeasure':
    return pruneOrder({...state, measures: state.measures.filter((id) => id !== action.id)});

  case 'addFilter': {
    const filter = {
      key: `f${state.nextKey}`, type: action.valueType || CATEGORIES.TEXT,
      operator: action.operator || 'eq', text: '', parameterId: '',
      ...(action.field ? {field: {...action.field}} : {column: action.column}),
    };
    return {...state, filters: [...state.filters, filter], nextKey: state.nextKey + 1};
  }
  case 'updateFilter':
    return {...state, filters: state.filters.map((filter) =>
      filter.key === action.key ? normalizeFilter(filter, action.patch) : filter)};
  case 'removeFilter':
    return {...state, filters: state.filters.filter((filter) => filter.key !== action.key)};
  case 'retypeFilters': {
    // Catalog column types arrive after a stored question loads.
    const filters = state.filters.map((filter) => {
      const type = action.types[filter.column] || action.types[filter.field?.field];
      return type && type !== filter.type ? {...filter, type} : filter;
    });
    return filters.some((filter, index) => filter !== state.filters[index]) ? {...state, filters} : state;
  }

  case 'addOrder':
    if(state.orderBy.some((entry) => entry.target === action.target)) return state;
    return {...state, orderBy: [...state.orderBy, {target: action.target, direction: action.direction || 'asc'}]};
  case 'updateOrder':
    return {...state, orderBy: replaceAt(state.orderBy, action.index,
      {...state.orderBy[action.index], ...action.patch})};
  case 'removeOrder':
    return {...state, orderBy: without(state.orderBy, action.index)};
  case 'moveOrder': {
    const target = action.index + action.delta;
    if(target < 0 || target >= state.orderBy.length) return state;
    const orderBy = state.orderBy.slice();
    [orderBy[action.index], orderBy[target]] = [orderBy[target], orderBy[action.index]];
    return {...state, orderBy};
  }

  case 'addParameter': {
    if(state.parameters.some((parameter) => parameter.id === action.parameter.id)) return state;
    return {...state, parameters: [...state.parameters, parameterState(action.parameter)]};
  }
  case 'updateParameter':
    return {...state, parameters: state.parameters.map((parameter) =>
      parameter.id === action.id ? {...parameter, ...action.patch} : parameter)};
  case 'removeParameter':
    return {
      ...state,
      parameters: state.parameters.filter((parameter) => parameter.id !== action.id),
      filters: state.filters.map((filter) => filter.parameterId === action.id ?
        {...filter, parameterId: ''} : filter),
    };
  case 'setValue':
    return {...state, values: {...state.values, [action.id]: action.text}};

  case 'setVisualization':
    return {...state, visualization: {
      type: action.visualization.type ?? state.visualization.type,
      settings: isPlain(action.visualization.settings) ?
        {...action.visualization.settings} : state.visualization.settings,
    }};

  default:
    return state;
  }
}

const CLEAN_ACTIONS = new Set(['setValue', 'retypeFilters']);

/** The reducer: pure, and flags unsaved edits for every real change. */
export function reduce(state, action) {
  switch(action.type) {
  case 'new':
    return emptyState({collectionId: action.collectionId ?? null, ...(action.overrides || {})});
  case 'load':
    return fromQuestion(action.record);
  case 'convert': {
    // Adopt a converted builder question but keep the identity of the edit in progress.
    const converted = fromQuestion(action.question);
    return {
      ...converted, questionId: state.questionId, revision: state.revision,
      status: state.status, name: state.name || converted.name,
      description: state.description, collectionId: state.collectionId,
      parameters: converted.parameters.length ? converted.parameters : state.parameters,
      visualization: state.visualization, resultPolicy: state.resultPolicy,
      values: state.values, dirty: true,
    };
  }
  case 'restore': {
    // An older revision becomes the draft of the same question; saving appends a revision.
    const restored = fromQuestion(action.definition);
    return {
      ...restored, questionId: state.questionId, revision: state.revision,
      status: state.status, values: state.values, dirty: true,
    };
  }
  case 'saved': {
    const loaded = fromQuestion(action.record);
    return {...loaded, values: state.values, filters: state.filters.length === loaded.filters.length ?
      loaded.filters.map((filter, index) => ({...filter, type: state.filters[index].type})) : loaded.filters,
    dirty: false};
  }
  default: {
    const next = step(state, action);
    if(next === state) return state;
    return CLEAN_ACTIONS.has(action.type) ? next : {...next, dirty: true};
  }
  }
}

// ---------------------------------------------------------------------------
// Read helpers shared by components
// ---------------------------------------------------------------------------

/** True when the state has chosen what to show (used to enable Run). */
export function hasSelection(state) {
  if(state.mode === 'sql') return state.sql.trim() !== '';
  if(state.source.kind === 'model') return state.measures.length > 0;
  return state.source.relation.length > 0 &&
    (state.columns.length > 0 || state.aggregations.length > 0);
}
