/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * The cube query tester: a flat draft for typed controls and the pure
 * conversion to the query document semantic_models.validate_query admits.
 * The query is never stored by the Models view; saved, repeatable queries
 * are BI questions.
 */

import gettext from 'sources/gettext';
import {parseTyped, portableId, textToValue} from './modelDraft';

export function emptyQuery() {
  return {
    rows: [], columns: [], pages: [], measures: [], filters: [], parameters: [],
    drill_mode: 'summary', drill_target: '', drill_details: '',
    time_operation: '', time_dimension: '', time_start: '', time_end: '', time_period: '', time_anchor: '',
    windows: [], totals: false, limit: 500,
  };
}

const NO_VALUE = new Set(['is_null', 'is_not_null']);

/** `source.field, other.field` -> field references (the first dot splits the source from the field). */
export function parseDetailFields(text) {
  return String(text || '').split(',').map((item) => item.trim()).filter(Boolean).map((item) => {
    const [sourceId, ...rest] = item.split('.');
    return {source_id: sourceId, field: rest.join('.')};
  }).filter((item) => item.source_id && item.field);
}

/**
 * The query document for a draft. `parameters` are the model's parameter definitions, which type the
 * values. Returns `{query, problems}`.
 */
export function toQuery(draft, parameters = []) {
  const problems = [];
  const filters = (draft.filters || []).map((row) => {
    const entry = {field: {source_id: row.source_id, field: row.field}, operator: row.operator};
    if(NO_VALUE.has(row.operator)) return entry;
    if(row.parameter_id) entry.parameter_id = row.parameter_id;
    else entry.value = textToValue(row.value_text);
    return entry;
  });
  const values = {};
  for(const row of draft.parameters || []) {
    const definition = parameters.find((item) => item.id === row.parameter_id);
    if(!definition) continue;
    try {
      values[row.parameter_id] = parseTyped(row.value_text, definition.type, gettext('Parameter %s', row.parameter_id));
    } catch(error) {
      problems.push(error.message);
    }
  }
  const query = {
    axes: {rows: [...draft.rows], columns: [...draft.columns], pages: [...draft.pages]},
    measures: [...draft.measures], filters, cross_filters: [], parameters: values,
    totals: Boolean(draft.totals), limit: Number(draft.limit) || 500,
    drill: {mode: draft.drill_mode, target_level: draft.drill_mode === 'down' ? (draft.drill_target || null) : null,
      detail_fields: draft.drill_mode === 'through' ? parseDetailFields(draft.drill_details) : []},
    time_intelligence: {}, windows: [],
  };
  if(draft.time_operation) {
    const time = {operation: draft.time_operation, dimension_id: draft.time_dimension};
    if(['as_of', 'range'].includes(draft.time_operation)) time.start = draft.time_start;
    if(draft.time_operation === 'range') time.end = draft.time_end;
    if(['period_to_date', 'period_comparison'].includes(draft.time_operation)) {
      time.period = draft.time_period;
      time.anchor = draft.time_anchor;
    }
    query.time_intelligence = time;
  }
  query.windows = (draft.windows || []).map((row) => ({
    id: portableId(row.id), measure_id: row.measure_id, operation: row.operation,
    partition_by: row.partition_by || [],
    order_by: {level_id: row.order_level, direction: row.direction || 'asc'},
    frame_size: Number(row.frame_size) || 1,
  }));
  return {query, problems};
}

/** Light checks before a request; the backend validator is the authority. */
export function queryErrors(draft) {
  const errors = {};
  if(!(draft.measures || []).length) errors.measures = gettext('Choose at least one measure.');
  if(draft.drill_mode === 'down' && !draft.drill_target) errors.drill_target = gettext('Drill-down needs a target level.');
  return errors;
}
