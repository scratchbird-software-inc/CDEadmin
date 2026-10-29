/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Client-side checks that mirror the obvious rules of bi/models.py so the
 * builder can disable Run and point at the field before a request is sent.
 * The backend validator stays authoritative and its messages are shown as
 * returned; this list only prevents requests that cannot succeed.
 */

import gettext from 'sources/gettext';
import {
  isListOperator, isRangeOperator, isUnaryOperator, parseList, parseValue,
} from './columnTypes';
import {MAX_LIMIT} from './queryState';
import {orderTargets} from './outputs';

const PARAMETER_ID = /^[A-Za-z][A-Za-z0-9_-]{0,127}$/;

function filterError(filter) {
  if(isUnaryOperator(filter.operator) || filter.parameterId) return null;
  if(isListOperator(filter.operator)) return parseList(filter.type, filter.text).error || null;
  if(isRangeOperator(filter.operator)) {
    const parsed = parseList(filter.type, filter.text);
    if(parsed.error) return parsed.error;
    return parsed.value.length === 2 ? null : gettext('Enter exactly two values separated by a comma.');
  }
  return parseValue(filter.type, filter.text).error || null;
}

/**
 * Validation messages for the state: [{path, message}]. `forSave` adds the
 * requirements that only a stored question has (a name).
 */
export function validateState(state, {forSave = false, model = null} = {}) {
  const errors = [];
  const add = (path, message) => errors.push({path, message});
  if(forSave && !state.name.trim()) add('name', gettext('Enter a name.'));
  if(state.mode === 'sql') {
    if(!state.sql.trim()) add('sql', gettext('Enter a SELECT statement.'));
  } else {
    if(state.source.kind === 'table' && !state.source.relation.length) {
      add('source', gettext('Choose a table to start from.'));
    }
    if(state.source.kind === 'model') {
      if(!state.measures.length) add('selection', gettext('Choose at least one measure.'));
    } else if(state.source.relation.length && !state.columns.length && !state.aggregations.length) {
      add('selection', gettext('Choose at least one column or summary.'));
    }
    state.aggregations.forEach((aggregation, index) => {
      if(aggregation.function !== 'count' && !aggregation.column) {
        add(`aggregations.${index}`, gettext('Choose a column to summarize.'));
      }
    });
    state.filters.forEach((filter) => {
      const message = filterError(filter);
      if(message) add(`filters.${filter.key}`, message);
    });
    const targets = new Set(orderTargets(state, model).map((target) => target.id));
    state.orderBy.forEach((entry, index) => {
      if(!targets.has(entry.target)) add(`order.${index}`, gettext('Sort by a column that is shown.'));
    });
    if(!Number.isInteger(state.limit) || state.limit < 1 || state.limit > MAX_LIMIT) {
      add('limit', gettext('Limit must be a whole number from 1 to %s.', MAX_LIMIT));
    }
  }
  const seen = new Set();
  for(const parameter of state.parameters) {
    if(!PARAMETER_ID.test(parameter.id)) {
      add(`parameters.${parameter.id}`, gettext('Parameter names start with a letter and use letters, digits, - and _.'));
    } else if(seen.has(parameter.id)) {
      add(`parameters.${parameter.id}`, gettext('Parameter names must be unique.'));
    }
    seen.add(parameter.id);
  }
  return errors;
}

export function errorAt(errors, path) {
  return errors.find((error) => error.path === path)?.message || '';
}
