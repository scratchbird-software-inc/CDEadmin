/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Pure conversion from a rendered result page (the tabular view model of the
 * result service) to the data the existing chart wrapper (BaseChart, Chart.js)
 * draws. The chart type names are the semantic chart set the backend admits as
 * visualization.type; settings are {x: columnKey, y: [columnKey, ...]}.
 */

import gettext from 'sources/gettext';

// Hues only, no neutrals; mid-tone so they read on light and dark themes.
export const SERIES_COLORS = Object.freeze([
  '#2f7fc1', '#e0793a', '#3f9c6b', '#a15fc4', '#d4a72c', '#c8506b', '#2aa0a4', '#7a8a2e',
]);

export function chartTypeLabel(type) {
  switch(type) {
  case 'table': return gettext('Table');
  case 'bar': return gettext('Bar');
  case 'line': return gettext('Line');
  case 'area': return gettext('Area');
  case 'scatter': return gettext('Scatter');
  case 'pie': return gettext('Pie');
  case 'metric': return gettext('Metric');
  default: return type;
  }
}

/** Normalize a tabular view model into {columns: [{key, name, type}], rows: [object]}. */
export function resultTable(viewModel) {
  const rawRows = viewModel?.rows || [];
  let columns = (viewModel?.columns || []).map((column, index) => {
    const key = String(column.key ?? column.name ?? `column_${index + 1}`);
    return {key, name: String(column.label ?? column.name ?? key),
      type: String(column.engine_type ?? column.type ?? '')};
  });
  if(!columns.length && rawRows.length && !Array.isArray(rawRows[0])) {
    columns = Object.keys(rawRows[0]).map((key) => ({key, name: key, type: ''}));
  }
  const rows = rawRows.map((row) => Array.isArray(row) ?
    Object.fromEntries(row.map((value, index) => [columns[index]?.key ?? String(index), value])) : row);
  return {columns, rows};
}

const isNumeric = (value) => value !== null && value !== '' && typeof value !== 'boolean' &&
  value !== undefined && Number.isFinite(Number(value));

/** Columns whose every non-empty value is a number. */
export function numericColumns(table) {
  return table.columns.filter((column) => {
    const values = table.rows.map((row) => row[column.key]).filter((value) => value !== null && value !== undefined);
    return values.length > 0 && values.every(isNumeric);
  });
}

/** Sensible x / y for a result when the question has none saved. */
export function defaultSettings(table) {
  const numeric = numericColumns(table);
  const numericKeys = new Set(numeric.map((column) => column.key));
  const x = table.columns.find((column) => !numericKeys.has(column.key)) || table.columns[0];
  const y = numeric.filter((column) => column.key !== x?.key);
  return {x: x?.key || '', y: y.length ? [y[0].key] : numeric.slice(0, 1).map((column) => column.key)};
}

/** Settings with unknown columns dropped and gaps filled from the result. */
export function effectiveSettings(settings, table) {
  const keys = new Set(table.columns.map((column) => column.key));
  const defaults = defaultSettings(table);
  const x = keys.has(settings?.x) ? settings.x : defaults.x;
  const wanted = (Array.isArray(settings?.y) ? settings.y : settings?.y ? [settings.y] : [])
    .filter((key) => keys.has(key));
  return {x, y: wanted.length ? wanted : defaults.y};
}

const color = (index) => SERIES_COLORS[index % SERIES_COLORS.length];

function withAlpha(hex, alpha) {
  const value = hex.replace('#', '');
  const channel = (start) => parseInt(value.slice(start, start + 2), 16);
  return `rgba(${channel(0)},${channel(2)},${channel(4)},${alpha})`;
}

/**
 * What to draw: {kind: 'table'} | {kind: 'metric', label, value} |
 * {kind: 'empty', reason} | {kind: 'chart', type, data, options}. `type` is a
 * Chart.js type for the BaseChart wrapper.
 */
export function buildChart(type, table, settings) {
  if(type === 'table') return {kind: 'table'};
  if(!table.rows.length) return {kind: 'empty', reason: gettext('The query returned no rows.')};
  const {x, y} = effectiveSettings(settings, table);
  const name = (key) => table.columns.find((column) => column.key === key)?.name || key;
  if(!y.length) {
    return {kind: 'empty', reason: gettext('This chart needs a numeric column. Choose one under Chart settings.')};
  }
  if(type === 'metric') {
    return {kind: 'metric', label: name(y[0]), value: table.rows[0][y[0]]};
  }
  const series = y.slice(0, type === 'pie' ? 1 : y.length);
  if(type === 'scatter') {
    if(!table.rows.every((row) => isNumeric(row[x]))) {
      return {kind: 'empty', reason: gettext('A scatter chart needs a numeric X column.')};
    }
    return {kind: 'chart', type: 'scatter', data: {datasets: series.map((key, index) => ({
      label: name(key), backgroundColor: color(index), borderColor: color(index),
      data: table.rows.map((row) => ({x: Number(row[x]), y: Number(row[key])})),
    }))}, options: baseOptions(true, x ? name(x) : '')};
  }
  const labels = table.rows.map((row) => String(row[x] ?? ''));
  if(type === 'pie') {
    return {kind: 'chart', type: 'pie', data: {labels, datasets: [{
      label: name(series[0]), data: table.rows.map((row) => Number(row[series[0]])),
      backgroundColor: labels.map((_label, index) => color(index)),
    }]}, options: {responsive: true, maintainAspectRatio: false, plugins: {legend: {display: true}}}};
  }
  const area = type === 'area';
  return {kind: 'chart', type: type === 'bar' ? 'bar' : 'line', data: {labels,
    datasets: series.map((key, index) => ({
      label: name(key), data: table.rows.map((row) => Number(row[key])),
      backgroundColor: area ? withAlpha(color(index), 0.3) : color(index),
      borderColor: color(index), fill: area,
    }))}, options: baseOptions(true, x ? name(x) : '')};
}

function baseOptions(scales, xTitle) {
  return {
    responsive: true, maintainAspectRatio: false, parsing: true,
    plugins: {legend: {display: true}},
    ...(scales ? {scales: {
      x: {display: true, title: {display: Boolean(xTitle), text: xTitle}},
      y: {display: true},
    }} : {}),
  };
}
