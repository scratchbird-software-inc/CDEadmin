/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Pure conversion between a stored semantic model (the document that
 * semantic_models.validate_model normalises) and the flat draft the Models
 * view edits with typed controls and grids. `fromDraft(toDraft(x))` is the
 * identity on a backend-normalised model; a Jest spec checks that against
 * fixtures generated from the real validator.
 *
 * Nothing the editor does not show is dropped: provider_config, unsupported
 * expression trees, annotations and the embedded visualizations, dashboards,
 * schedules and reports are carried through untouched (grid rows keep them in
 * `_keep`).
 */

import gettext from 'sources/gettext';

export const PORTABLE_ID = /^[A-Za-z][A-Za-z0-9_-]{0,127}$/;

export const FILTER_OPERATORS = Object.freeze(['eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'in', 'not_in', 'between',
  'is_null', 'is_not_null']);
export const AGGREGATIONS = Object.freeze(['sum', 'count', 'count_distinct', 'min', 'max', 'avg', 'none']);
export const CALCULATION_OPERATORS = Object.freeze(['add', 'subtract', 'multiply', 'divide']);
export const JOIN_TYPES = Object.freeze(['inner', 'left', 'right', 'full', 'cross']);
export const CARDINALITIES = Object.freeze(['one-to-one', 'one-to-many', 'many-to-one', 'many-to-many']);
export const TIME_ROLES = Object.freeze(['calendar-time', 'fiscal-time', 'event-time', 'processing-time',
  'valid-time', 'system-time']);
export const TIME_VALUE_TYPES = Object.freeze(['string', 'date', 'datetime']);
export const CERTIFICATION_STATUSES = Object.freeze(['uncertified', 'candidate', 'certified', 'deprecated']);
export const PARAMETER_TYPES = Object.freeze(['string', 'integer', 'number', 'boolean', 'date', 'datetime', 'array']);
export const MODEL_STATUSES = Object.freeze(['draft', 'published', 'archived']);
export const DRILL_MODES = Object.freeze(['summary', 'down', 'through']);
export const WINDOW_DIRECTIONS = Object.freeze(['asc', 'desc']);

const NO_VALUE_OPERATORS = new Set(['is_null', 'is_not_null']);

/** Make an identifier the backend accepts out of free text. */
export function portableId(value, fallback = 'item') {
  const text = String(value || fallback).trim().replace(/[^A-Za-z0-9_-]+/g, '_');
  return (/^[A-Za-z]/.test(text) ? text : `item_${text}`).slice(0, 128);
}

/** The first free identifier of the form `base`, `base_2`, `base_3`... */
export function uniqueId(base, taken) {
  const used = new Set(taken);
  let candidate = portableId(base);
  let suffix = 2;
  while (used.has(candidate)) {
    candidate = `${portableId(base).slice(0, 120)}_${suffix}`;
    suffix += 1;
  }
  return candidate;
}

// ---------------------------------------------------------------------------
// typed text <-> value
// ---------------------------------------------------------------------------
/** Show a stored value as editable text; strings that look like JSON are quoted so they round-trip. */
export function valueToText(value) {
  if(value === undefined || value === null) return '';
  if(typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return typeof parsed === 'string' ? value : JSON.stringify(value);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value);
}

/** Text from a member field: valid JSON is taken as typed JSON, anything else stays text. */
export function textToValue(text) {
  const value = String(text ?? '');
  if(value.trim() === '') return value;
  try { return JSON.parse(value); } catch { return value; }
}

function parameterDefaultToText(value, type) {
  if(value === undefined) return '';
  return ['string', 'date', 'datetime'].includes(type) ? String(value) : JSON.stringify(value);
}

/** Parse a parameter default or allowed value by the declared type; throws a gettext message. */
export function parseTyped(text, type, label) {
  const value = String(text);
  if(['string', 'date', 'datetime'].includes(type)) return value;
  let parsed;
  try { parsed = JSON.parse(value); } catch {
    throw new Error(gettext('%s must be valid JSON for a %s parameter.', label, type));
  }
  const ok = {
    integer: Number.isInteger(parsed), number: typeof parsed === 'number',
    boolean: typeof parsed === 'boolean', array: Array.isArray(parsed),
  }[type];
  if(!ok) throw new Error(gettext('%s does not match type %s.', label, type));
  return parsed;
}

const splitList = (text) => String(text || '').split(',').map((item) => item.trim()).filter(Boolean);

// ---------------------------------------------------------------------------
// filters (default filters, row policies, role filters)
// ---------------------------------------------------------------------------
function filterRow(filter) {
  const {field, operator, value, parameter_id: parameterId, ...rest} = filter;
  return {
    source_id: field?.source_id || '', field: field?.field || '', operator: operator || 'eq',
    parameter_id: parameterId || '', value_text: valueToText(value),
    _keep: rest,
  };
}

function filterFromRow(row) {
  const entry = {...(row._keep || {}), field: {source_id: row.source_id, field: row.field},
    operator: row.operator};
  if(NO_VALUE_OPERATORS.has(row.operator)) return entry;
  if(row.parameter_id) entry.parameter_id = row.parameter_id;
  else entry.value = textToValue(row.value_text);
  return entry;
}

// ---------------------------------------------------------------------------
// sections: stored shape <-> grid rows
// ---------------------------------------------------------------------------
function sourceRow(source) {
  const {id, resource_id: resourceId, relation, alias, source_kind: kind, classification, grain,
    ...rest} = source;
  const foreign = (grain || []).filter((item) => item.source_id !== id);
  return {
    id, resource_id: resourceId, relation: (relation || []).join('.'), alias, source_kind: kind,
    classification, grain: (grain || []).map((item) => item.field).join(', '),
    // a grain field of another source keeps its source
    _keep: {...rest, ...(foreign.length ? {grain_sources: Object.fromEntries(foreign.map(
      (item) => [item.field, item.source_id]))} : {})},
  };
}

function sourceFromRow(row) {
  const {grain_sources: grainSources, ...kept} = row._keep || {};
  return {
    ...kept, id: row.id, resource_id: row.resource_id,
    relation: String(row.relation || '').split('.').map((part) => part.trim()).filter(Boolean),
    alias: row.alias || row.id, source_kind: row.source_kind, classification: row.classification,
    grain: splitList(row.grain).map((field) => ({source_id: grainSources?.[field] || row.id, field})),
  };
}

function joinRow(join) {
  const predicates = join.predicates || [];
  const simple = predicates.length === 1 && (predicates[0].operator || 'eq') === 'eq';
  const first = simple ? predicates[0] : {};
  const {id, left_source: left, right_source: right, join_type: type, cardinality, predicates: _p, ...rest} = join;
  return {
    id, left_source: left, right_source: right, join_type: type || 'inner',
    cardinality: cardinality || 'many-to-one',
    left_field: first.left?.field || '', right_field: first.right?.field || '',
    // predicates the grid cannot show (several, or not equality) are kept as stored
    _keep: simple || !predicates.length ? rest : {...rest, predicates},
  };
}

function joinFromRow(row) {
  const {predicates: kept, ...rest} = row._keep || {};
  const join = {...rest, id: row.id, left_source: row.left_source, right_source: row.right_source,
    join_type: row.join_type, cardinality: row.cardinality};
  if(kept) join.predicates = kept;
  else if(row.join_type === 'cross') join.predicates = [];
  else {
    join.predicates = [{operator: 'eq',
      left: {source_id: row.left_source, field: row.left_field},
      right: {source_id: row.right_source, field: row.right_field}}];
  }
  return join;
}

function relationshipRow(item) {
  const {id, name, from_source: from, to_source: to, relationship_kind: kind, ...rest} = item;
  return {id, name, from_source: from, to_source: to, relationship_kind: kind, _keep: rest};
}

const relationshipFromRow = (row) => ({...(row._keep || {}), id: row.id, name: row.name,
  from_source: row.from_source, to_source: row.to_source, relationship_kind: row.relationship_kind});

function levelRow(level) {
  return {id: level.id, name: level.name, source_id: level.field?.source_id || '', field: level.field?.field || '',
    _keep: Object.fromEntries(Object.entries(level).filter(([key]) => !['id', 'name', 'field'].includes(key)))};
}

const levelFromRow = (row) => ({...(row._keep || {}), id: row.id, name: row.name,
  field: {source_id: row.source_id, field: row.field}});

function dimensionRow(dimension) {
  const {id, name, field, dimension_kind: kind, time_intelligence: time, hierarchies, ...rest} = dimension;
  return {
    id, name, source_id: field?.source_id || '', field: field?.field || '', dimension_kind: kind,
    time_enabled: Boolean(time), time_role: time?.role || 'calendar-time', timezone: time?.timezone || 'UTC',
    time_value_type: time?.value_type || 'string', fiscal_year_start_month: time?.fiscal_year_start_month ?? 1,
    hierarchies: (hierarchies || []).map((hierarchy) => ({
      id: hierarchy.id, name: hierarchy.name, levels: (hierarchy.levels || []).map(levelRow),
      _keep: Object.fromEntries(Object.entries(hierarchy).filter(([key]) => !['id', 'name', 'levels'].includes(key))),
    })),
    _keep: {...rest, ...(time ? {time_extra: Object.fromEntries(Object.entries(time).filter(([key]) =>
      !['role', 'timezone', 'value_type', 'fiscal_year_start_month'].includes(key)))} : {})},
  };
}

function dimensionFromRow(row) {
  const {time_extra: timeExtra, ...rest} = row._keep || {};
  return {
    ...rest, id: row.id, name: row.name, field: {source_id: row.source_id, field: row.field},
    dimension_kind: row.dimension_kind,
    time_intelligence: row.time_enabled ? {
      calendar: 'gregorian', ...(timeExtra || {}), role: row.time_role, timezone: row.timezone,
      value_type: row.time_value_type, fiscal_year_start_month: Number(row.fiscal_year_start_month),
    } : null,
    hierarchies: (row.hierarchies || []).map((hierarchy) => ({
      ...(hierarchy._keep || {}), id: hierarchy.id, name: hierarchy.name,
      levels: (hierarchy.levels || []).map(levelFromRow),
    })),
  };
}

function simpleExpression(expression) {
  return expression && Object.keys(expression).length === 3 && expression.operator &&
    expression.left?.measure !== undefined && Object.keys(expression.left).length === 1 &&
    expression.right?.measure !== undefined && Object.keys(expression.right).length === 1;
}

function measureRow(measure) {
  const {id, name, aggregation, field, format, measure_kind: kind, certification, expression, ...rest} = measure;
  const simple = simpleExpression(expression);
  return {
    id, name, measure_kind: kind, aggregation, source_id: field?.source_id || '', field: field?.field || '',
    format: format || '', certification_status: certification?.status || 'uncertified',
    certification_owner: certification?.owner || '', certification_definition: certification?.definition || '',
    calc_left: simple ? expression.left.measure : '', calc_operator: simple ? expression.operator : 'divide',
    calc_right: simple ? expression.right.measure : '',
    calc_complex: Boolean(expression) && !simple,
    _keep: {...rest, ...(expression && !simple ? {expression} : {}),
      ...(certification ? {certification_extra: Object.fromEntries(Object.entries(certification).filter(
        ([key]) => !['status', 'owner', 'definition'].includes(key)))} : {})},
  };
}

function measureFromRow(row) {
  const {expression: keptExpression, certification_extra: certificationExtra, ...rest} = row._keep || {};
  const measure = {
    ...rest, id: row.id, name: row.name, format: row.format || '', measure_kind: row.measure_kind,
    certification: {...(certificationExtra || {}), status: row.certification_status,
      owner: row.certification_owner || '', definition: row.certification_definition || ''},
  };
  if(row.measure_kind === 'calculated' || keptExpression) {
    measure.aggregation = 'none';
    measure.field = null;
    measure.expression = keptExpression || {operator: row.calc_operator, left: {measure: row.calc_left},
      right: {measure: row.calc_right}};
    return measure;
  }
  measure.aggregation = row.aggregation;
  measure.field = row.aggregation === 'count' && !row.field ? null : {source_id: row.source_id, field: row.field};
  return measure;
}

function parameterRow(parameter) {
  const {id, name, type, required, default: defaultValue, allowed_values: allowed, ...rest} = parameter;
  return {
    id, name, type, required: Boolean(required),
    default_text: parameterDefaultToText(defaultValue, type),
    allowed_text: type === 'array' ? '' : (allowed || []).map((item) => parameterDefaultToText(item, type)).join(', '),
    _keep: {...rest, ...(type === 'array' ? {allowed_values: allowed || []} : {})},
  };
}

function parameterFromRow(row, index, problems) {
  const {allowed_values: keptAllowed, ...rest} = row._keep || {};
  const label = (what) => gettext('Parameter %s: %s', row.id || index + 1, what);
  const parameter = {...rest, id: row.id, name: row.name, type: row.type, required: Boolean(row.required)};
  try {
    parameter.allowed_values = keptAllowed || splitList(row.allowed_text).map((item) =>
      parseTyped(item, row.type, label(gettext('allowed value'))));
    if(row.default_text !== '') {
      parameter.default = parseTyped(row.default_text, row.type, label(gettext('default')));
    }
  } catch(error) {
    problems.push(error.message);
    parameter.allowed_values = keptAllowed || [];
  }
  return parameter;
}

function materializationRow(item) {
  const {id, name, strategy, enabled, ...rest} = item;
  return {id, name, strategy: strategy || 'provider_managed', enabled: Boolean(enabled), _keep: rest};
}

const materializationFromRow = (row) => ({...(row._keep || {}), id: row.id, name: row.name,
  strategy: row.strategy, enabled: Boolean(row.enabled)});

function roleRow(role) {
  const {name, principal_claim: claim, filters, ...rest} = role;
  return {name, principal_claim: claim || 'role', filters: (filters || []).map(filterRow), _keep: rest};
}

const roleFromRow = (row) => ({...(row._keep || {}), name: row.name, principal_claim: row.principal_claim,
  filters: (row.filters || []).map(filterFromRow)});

// ---------------------------------------------------------------------------
// whole model
// ---------------------------------------------------------------------------
const EMBEDDED_KEYS = ['visualizations', 'dashboards', 'schedules', 'reports'];

/** The part of a model the Models view shows but does not edit. */
export function embeddedContent(definition) {
  return Object.fromEntries(EMBEDDED_KEYS.map((key) => [key, definition?.[key] || []]));
}

export function toDraft(definition) {
  const {name, description, semantic_family: family, sources, joins, relationships, dimensions, measures,
    parameters, default_filters: defaultFilters, materializations, security, contract_version: version,
    ...rest} = definition;
  const policy = security || {};
  const tenant = policy.tenant_filter;
  const {row_filters: rowFilters, tenant_filter: _tenant, roles, ...securityRest} = policy;
  return {
    name: name || '', description: description || '', semantic_family: family || 'relational',
    sources: (sources || []).map(sourceRow), joins: (joins || []).map(joinRow),
    relationships: (relationships || []).map(relationshipRow),
    dimensions: (dimensions || []).map(dimensionRow), measures: (measures || []).map(measureRow),
    parameters: (parameters || []).map(parameterRow),
    default_filters: (defaultFilters || []).map(filterRow),
    row_filters: (rowFilters || []).map(filterRow),
    tenant_enabled: Boolean(tenant), tenant_source: tenant?.field?.source_id || '',
    tenant_field: tenant?.field?.field || '', tenant_claim: tenant?.principal_claim || 'tenant_id',
    tenant_required: tenant ? Boolean(tenant.required) : true,
    roles: (roles || []).map(roleRow),
    materializations: (materializations || []).map(materializationRow),
    // carried through unchanged
    _carry: {contract_version: version, security_extra: securityRest,
      tenant_extra: tenant ? Object.fromEntries(Object.entries(tenant).filter(([key]) =>
        !['field', 'principal_claim', 'required'].includes(key))) : {},
      rest},
  };
}

/**
 * Build the stored document from a draft. Returns `{definition, problems}`: problems are values the typed
 * controls could not turn into the stored shape (a parameter default that is not valid JSON, say); the
 * definition is still complete so the backend validator reports everything else.
 */
export function fromDraft(draft) {
  const problems = [];
  const carry = draft._carry || {};
  const security = {...(carry.security_extra || {}), row_filters: (draft.row_filters || []).map(filterFromRow),
    tenant_filter: draft.tenant_enabled ? {...(carry.tenant_extra || {}),
      field: {source_id: draft.tenant_source, field: draft.tenant_field},
      principal_claim: draft.tenant_claim, required: Boolean(draft.tenant_required)} : null,
    roles: (draft.roles || []).map(roleFromRow)};
  const definition = {
    ...(carry.rest || {}),
    ...(carry.contract_version ? {contract_version: carry.contract_version} : {}),
    name: draft.name, description: draft.description, semantic_family: draft.semantic_family,
    sources: (draft.sources || []).map(sourceFromRow), joins: (draft.joins || []).map(joinFromRow),
    relationships: (draft.relationships || []).map(relationshipFromRow),
    dimensions: (draft.dimensions || []).map(dimensionFromRow),
    measures: (draft.measures || []).map(measureFromRow),
    parameters: (draft.parameters || []).map((row, index) => parameterFromRow(row, index, problems)),
    default_filters: (draft.default_filters || []).map(filterFromRow),
    materializations: (draft.materializations || []).map(materializationFromRow),
    security,
  };
  return {definition, problems};
}

/** Order the stored keys the way the backend returns them so equality checks compare content only. */
export function canonical(value) {
  if(Array.isArray(value)) return value.map(canonical);
  if(value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

export const sameDefinition = (left, right) => JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));

// ---------------------------------------------------------------------------
// new model
// ---------------------------------------------------------------------------
export function emptyModel(resources, profile = {}) {
  const kinds = profile.source_kinds || ['table', 'collection', 'index'];
  const resource = (resources || []).find((item) => kinds.includes(item.resource_kind));
  const sources = resource ? [sourceFromResource(resource, profile, [])] : [];
  return {
    contract_version: '1.0.0', name: gettext('New semantic model'),
    semantic_family: profile.semantic_family || 'relational', description: '', sources, joins: [],
    relationships: [], dimensions: [], measures: [], parameters: [], default_filters: [],
    materializations: [], security: {row_filters: [], tenant_filter: null, roles: []},
    visualizations: [], dashboards: [], schedules: [], reports: [], annotations: {},
  };
}

/** A source entry for a discovered resource, with an identifier no other source uses. */
export function sourceFromResource(resource, profile = {}, takenIds = []) {
  const id = uniqueId(resource.display_name || 'source', takenIds);
  return {
    id, resource_id: resource.resource_id, relation: resource.display_path || [resource.display_name],
    alias: id, source_kind: resource.resource_kind,
    classification: profile.source_classifications?.[0] || 'fact', grain: [], provider_config: {},
  };
}

export function addDiscoveredSource(draft, resource, profile) {
  const taken = draft.sources.map((row) => row.id);
  return {...draft, sources: [...draft.sources, sourceRow(sourceFromResource(resource, profile, taken))]};
}

// ---------------------------------------------------------------------------
// light client-side checks (the backend validator is the authority)
// ---------------------------------------------------------------------------
function duplicates(rows, key) {
  const seen = new Set();
  const repeated = new Set();
  for(const row of rows) {
    if(seen.has(row[key])) repeated.add(row[key]);
    seen.add(row[key]);
  }
  return repeated;
}

export function validateDraft(draft) {
  const errors = {};
  const sections = [
    ['sources', gettext('Source'), 'id'], ['joins', gettext('Join'), 'id'],
    ['relationships', gettext('Relationship'), 'id'], ['dimensions', gettext('Dimension'), 'id'],
    ['measures', gettext('Measure'), 'id'], ['parameters', gettext('Parameter'), 'id'],
    ['materializations', gettext('Materialization'), 'id'],
  ];
  for(const [section, label, key] of sections) {
    const rows = draft[section] || [];
    const repeated = duplicates(rows, key);
    const bad = rows.find((row) => !PORTABLE_ID.test(String(row[key] || '')));
    if(bad) errors[section] = gettext('%s identifiers must start with a letter and use letters, digits, - or _.', label);
    else if(repeated.size) errors[section] = gettext('%s identifiers must be unique: %s.', label, [...repeated].join(', '));
  }
  if(!String(draft.name || '').trim()) errors.name = gettext('Model name is required.');
  if(!(draft.sources || []).length) errors.sources = errors.sources || gettext('A model needs at least one data source.');
  const levels = new Map();
  for(const dimension of draft.dimensions || []) {
    for(const hierarchy of dimension.hierarchies || []) {
      for(const level of hierarchy.levels || []) levels.set(level.id, (levels.get(level.id) || 0) + 1);
    }
  }
  const repeatedLevels = [...levels].filter(([, count]) => count > 1).map(([id]) => id);
  if(repeatedLevels.length) {
    errors.dimensions = errors.dimensions ||
      gettext('Level identifiers must be unique across dimensions: %s.', repeatedLevels.join(', '));
  }
  const tenant = draft.tenant_enabled && (!draft.tenant_source || !draft.tenant_field);
  if(tenant) errors.tenant_field = gettext('A tenant filter needs a source and a field.');
  return errors;
}
