/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Column type categories for the BI query builder. Native type names differ
 * per engine; the builder only needs four categories to decide which filter
 * operators, summaries and value controls apply. The classification reads the
 * leading word of the declared type (VARCHAR(20), NUMERIC(10,2), TIMESTAMP
 * WITH TIME ZONE, INT UNSIGNED ...) and never the engine identity.
 */

import gettext from 'sources/gettext';

export const CATEGORIES = Object.freeze({
  NUMBER: 'number', TEXT: 'text', DATE: 'date', BOOLEAN: 'boolean',
});

const NUMBER_WORDS = new Set([
  'int', 'integer', 'tinyint', 'smallint', 'mediumint', 'bigint', 'hugeint',
  'int1', 'int2', 'int4', 'int8', 'int16', 'int32', 'int64', 'int128',
  'uint', 'utinyint', 'usmallint', 'ubigint', 'uhugeint',
  'serial', 'smallserial', 'bigserial', 'numeric', 'decimal', 'dec', 'number',
  'float', 'float4', 'float8', 'double', 'real', 'money', 'smallmoney',
  'decfloat', 'fixed',
]);
const DATE_WORDS = new Set([
  'date', 'time', 'timetz', 'timestamp', 'timestamptz', 'datetime',
  'datetime2', 'smalldatetime', 'year',
]);
const BOOLEAN_WORDS = new Set(['bool', 'boolean']);

/** Map a native type name to number / text / date / boolean. */
export function typeCategory(typeName) {
  const word = String(typeName ?? '').trim().toLowerCase().split(/[^a-z0-9_]+/)[0];
  if(BOOLEAN_WORDS.has(word)) return CATEGORIES.BOOLEAN;
  if(NUMBER_WORDS.has(word)) return CATEGORIES.NUMBER;
  if(DATE_WORDS.has(word)) return CATEGORIES.DATE;
  return CATEGORIES.TEXT;
}

const UNARY = new Set(['is_null', 'is_not_null']);
const LISTS = new Set(['in', 'not_in']);

export const isUnaryOperator = (operator) => UNARY.has(operator);
export const isListOperator = (operator) => LISTS.has(operator);
export const isRangeOperator = (operator) => operator === 'between';

const OPERATORS = Object.freeze({
  number: ['eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'between', 'in', 'not_in',
    'is_null', 'is_not_null'],
  date: ['eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'between', 'is_null',
    'is_not_null'],
  text: ['eq', 'ne', 'in', 'not_in', 'is_null', 'is_not_null'],
  boolean: ['eq', 'ne', 'is_null', 'is_not_null'],
});

/** Filter operators the builder offers for a column category. */
export function operatorsFor(category) {
  return OPERATORS[category] || OPERATORS.text;
}

export function operatorLabel(operator) {
  switch(operator) {
  case 'eq': return gettext('is');
  case 'ne': return gettext('is not');
  case 'lt': return gettext('is less than');
  case 'lte': return gettext('is at most');
  case 'gt': return gettext('is greater than');
  case 'gte': return gettext('is at least');
  case 'between': return gettext('is between');
  case 'in': return gettext('is one of');
  case 'not_in': return gettext('is none of');
  case 'is_null': return gettext('is empty');
  case 'is_not_null': return gettext('is not empty');
  default: return operator;
  }
}

const AGGREGATIONS = Object.freeze({
  number: ['count', 'count_distinct', 'sum', 'avg', 'min', 'max'],
  date: ['count', 'count_distinct', 'min', 'max'],
  text: ['count', 'count_distinct', 'min', 'max'],
  boolean: ['count', 'count_distinct'],
});

/** Summaries the builder offers for a column category (count needs no column). */
export function aggregationsFor(category) {
  return AGGREGATIONS[category] || AGGREGATIONS.text;
}

export const ALL_AGGREGATIONS = Object.freeze(
  ['count', 'count_distinct', 'sum', 'avg', 'min', 'max']);

export function aggregationLabel(name) {
  switch(name) {
  case 'count': return gettext('Count of rows');
  case 'count_distinct': return gettext('Distinct values of');
  case 'sum': return gettext('Sum of');
  case 'avg': return gettext('Average of');
  case 'min': return gettext('Minimum of');
  case 'max': return gettext('Maximum of');
  default: return name;
  }
}

/** Parse one typed value from user text; returns {value} or {error}. */
export function parseValue(category, text) {
  const raw = String(text ?? '').trim();
  if(category === CATEGORIES.NUMBER) {
    const number = Number(raw);
    if(raw === '' || !Number.isFinite(number)) return {error: gettext('Enter a number.')};
    return {value: number};
  }
  if(category === CATEGORIES.BOOLEAN) {
    if(raw === 'true') return {value: true};
    if(raw === 'false') return {value: false};
    return {error: gettext('Choose true or false.')};
  }
  if(raw === '') return {error: gettext('Enter a value.')};
  return {value: raw};
}

/** Parse a comma separated list into typed values. */
export function parseList(category, text) {
  const parts = String(text ?? '').split(',').map((part) => part.trim()).filter(Boolean);
  if(!parts.length) return {error: gettext('Enter at least one value.')};
  const values = [];
  for(const part of parts) {
    const parsed = parseValue(category, part);
    if(parsed.error) return parsed;
    values.push(parsed.value);
  }
  return {value: values};
}

/** Show a stored filter value as editable text. */
export function valueText(value) {
  if(Array.isArray(value)) return value.map(String).join(', ');
  if(value === undefined || value === null) return '';
  return String(value);
}
