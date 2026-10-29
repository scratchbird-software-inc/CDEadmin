/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {resultTable} from './chartData';

/**
 * Read a bi_question_execute response (docs/en_US/bi_saved_questions.rst,
 * "Execution"): the first rendered page (`page.view_model`, `page.page`) of
 * the admitted result, the result id for further pages, the cache report and
 * the columns the question's result policy redacts.
 */
export function executionFrom(response) {
  const rendered = response.page || {};
  const table = resultTable(rendered.view_model);
  return {
    resultId: response.result?.result_id || '',
    table,
    total: rendered.page?.source_count ?? table.rows.length,
    cursor: rendered.page?.next_cursor || '',
    cache: response.cache || null,
    redacted: response.redacted_columns || [],
    sql: response.sql || '',
  };
}

/** Append the rows of a bi_question_page response; the cursor moves on. */
export function appendPage(execution, response) {
  const next = resultTable(response.view_model);
  const known = new Set(execution.table.columns.map((column) => column.key));
  const rows = next.rows.map((row) => Object.fromEntries(
    Object.entries(row).filter(([key]) => known.has(key))));
  return {
    ...execution,
    table: {columns: execution.table.columns, rows: [...execution.table.rows, ...rows]},
    cursor: response.page?.next_cursor || '',
    total: response.page?.source_count ?? execution.total,
  };
}
