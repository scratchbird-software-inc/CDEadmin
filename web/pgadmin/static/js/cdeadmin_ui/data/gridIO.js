/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import Papa from 'papaparse';

const DANGEROUS_SPREADSHEET_PREFIX = /^[\t\r ]*[=+\-@]/;

function exportColumns(columns=[]) {
  return columns.flatMap((column) => Array.isArray(column.children) ?
    exportColumns(column.children) :
    column.exportable === false ? [] : [column]);
}

export function safeSpreadsheetValue(value) {
  if(typeof value === 'string' && DANGEROUS_SPREADSHEET_PREFIX.test(value)) {
    return `'${value}`;
  }
  return value;
}

export function gridExportRecords(columns, rows, options={}) {
  const columnsToExport = exportColumns(columns);
  const neutralizeFormulas = options.neutralizeFormulas !== false;
  return rows.map((row) => columnsToExport.reduce((record, column) => {
    const value = column.exportValue ?
      column.exportValue(row?.[column.key], row) : row?.[column.key];
    record[column.key] = neutralizeFormulas ?
      safeSpreadsheetValue(value) : value;
    return record;
  }, {}));
}

export function serializeGridData(columns, rows, format='csv', options={}) {
  const records = gridExportRecords(columns, rows, options);
  if(format === 'json') {
    return JSON.stringify(records, null, options.pretty === false ? 0 : 2);
  }
  if(format !== 'csv' && format !== 'tsv') {
    throw new Error(`Unsupported grid export format: ${format}`);
  }
  return Papa.unparse(records, {
    delimiter: format === 'tsv' ? '\t' : ',',
    newline: options.newline || '\r\n',
    quotes: options.quotes || false,
    header: options.header !== false,
  });
}

export function parseGridData(text, format='csv', options={}) {
  if(format === 'json') {
    const parsed = JSON.parse(text);
    if(!Array.isArray(parsed) || parsed.some((row) =>
      row === null || typeof row !== 'object' || Array.isArray(row))) {
      throw new Error('Grid JSON import must contain an array of objects.');
    }
    return {rows: parsed, errors: [], fields: Object.keys(parsed[0] || {})};
  }
  if(format !== 'csv' && format !== 'tsv') {
    throw new Error(`Unsupported grid import format: ${format}`);
  }
  const parsed = Papa.parse(text, {
    delimiter: format === 'tsv' ? '\t' : ',',
    header: options.header !== false,
    skipEmptyLines: options.skipEmptyLines ?? 'greedy',
    dynamicTyping: options.dynamicTyping ?? false,
  });
  return {
    rows: parsed.data,
    errors: parsed.errors,
    fields: parsed.meta.fields || [],
  };
}

export function downloadGridExport(
  filename,
  content,
  mimeType = 'text/csv;charset=utf-8'
) {
  if (
    typeof Blob === 'undefined' ||
    typeof URL?.createObjectURL !== 'function' ||
    typeof document === 'undefined'
  ) {
    return;
  }
  const blob = new Blob([String(content ?? '')], {type: mimeType});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename || 'grid_export.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}
