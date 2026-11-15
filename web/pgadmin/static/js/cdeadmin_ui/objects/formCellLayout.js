/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Datatype-driven cell grid layout for descriptor forms.
 *
 * Each visible field has an intrinsic natural width determined by the datatype
 * it holds (plus a comfortable buffer). For a group of fields:
 *   1. The mean natural width of the fields defines one "cell" unit.
 *   2. Available container width determines how many cells fit per row.
 *   3. Each field spans ceil(fieldWidth / cellWidth) cells (clamped to row width)
 *      and expands to fill those cells.
 *   4. Fields are placed left-to-right in declaration order; if the next field
 *      needs more cells than remain on the current row, trailing cells on that
 *      row stay empty and the field begins on the next row.
 */

const CHAR_PX = 7.4;
const BUFFER_PX = 36;
const MIN_CELL_PX = 150;
const MAX_CELL_PX = 340;
const MAX_CHECKBOX_INLINE = 12;

const PATH_LIKE_ID = /(path|file|dir|directory|root|url|uri|dsn|conn_str|expected_database|cert|ca|crl|key_file|plugin_list)/i;
const NAME_LIKE_ID = /(^name$|_name$|display_name|profile_name|alias|title|summary)/i;
const SHORT_CODE_ID = /(charset|encoding|dialect|colour|color|locale|port|code)/i;

function clamp(val, min, max) {
  return Math.max(min, Math.min(max, val));
}

export function isProseCodeField(field) {
  if (!field || field.control !== 'code') return false;
  if (field.language === 'text' || field.language === 'plain' || field.language === 'markdown') {
    return true;
  }
  return !field.language && /^(comment|comments|description|notes)$/i.test(String(field.field_id || ''));
}

export function isFullRowField(field) {
  if (!field) return false;
  const control = field.control;
  if (control === 'grid' || control === 'privileges' || control === 'keyvalue') {
    return true;
  }
  if (control === 'code' && !isProseCodeField(field)) {
    return true;
  }
  if (
    control === 'multiselect' &&
    Array.isArray(field.options) &&
    field.options.length > 0 &&
    field.options.length <= MAX_CHECKBOX_INLINE
  ) {
    return true;
  }
  return false;
}

export function estimateFieldNaturalWidth(field, options = []) {
  if (!field) return 220;
  if (typeof field.width_px === 'number' && Number.isFinite(field.width_px) && field.width_px > 0) {
    return field.width_px;
  }
  const optionList = Array.isArray(options) ? options : [];
  const control = field.control;
  const id = String(field.field_id || '');
  const labelLen = String(field.label || '').length + (field.required ? 2 : 0);
  const labelWidth = labelLen * CHAR_PX + 24;

  if (control === 'boolean') {
    return Math.round(clamp(labelLen * CHAR_PX + 54, 140, 260));
  }

  if (control === 'number') {
    const maxDigits =
      typeof field.max === 'number' && Number.isFinite(field.max)
        ? Math.max(3, String(Math.abs(Math.trunc(field.max))).length)
        : 8;
    const dataWidth = maxDigits * 9 + 54 + BUFFER_PX / 2;
    return Math.round(clamp(Math.max(dataWidth, Math.min(labelWidth, 165)), 120, 180));
  }

  if (control === 'select' || control === 'radio') {
    const maxOptChars = optionList.reduce((acc, opt) => {
      const text = String(opt?.label ?? opt?.value ?? '');
      return Math.max(acc, text.length);
    }, 10);
    const optWidth = Math.min(maxOptChars, 34) * CHAR_PX + 34 + BUFFER_PX;
    return Math.round(clamp(Math.max(optWidth, Math.min(labelWidth, 215)), 150, 310));
  }

  if (control === 'password' || control === 'secret-reference') {
    return Math.round(clamp(Math.max(195 + BUFFER_PX / 2, Math.min(labelWidth, 230)), 195, 250));
  }

  if (control === 'multiline' || control === 'json' || isProseCodeField(field)) {
    return 420;
  }

  if (control === 'file' || PATH_LIKE_ID.test(id)) {
    return 360;
  }

  if (typeof field.max_length === 'number' && field.max_length > 0 && field.max_length <= 20) {
    const charW = field.max_length * 8.5 + BUFFER_PX;
    return Math.round(clamp(Math.max(charW, Math.min(labelWidth, 180)), 135, 200));
  }

  if (SHORT_CODE_ID.test(id)) {
    return Math.round(clamp(Math.max(150 + BUFFER_PX / 2, Math.min(labelWidth, 195)), 155, 210));
  }

  if (NAME_LIKE_ID.test(id)) {
    return Math.round(clamp(Math.max(255 + BUFFER_PX / 2, Math.min(labelWidth, 260)), 255, 310));
  }

  if (optionList.length > 0) {
    const sampleChars = optionList.slice(0, 40).reduce((acc, opt) => {
      const text = String(opt?.label ?? opt?.value ?? '');
      return Math.max(acc, Math.min(text.length, 28));
    }, 14);
    const comboWidth = sampleChars * CHAR_PX + 34 + BUFFER_PX;
    return Math.round(clamp(Math.max(comboWidth, Math.min(labelWidth, 225)), 190, 290));
  }

  return Math.round(clamp(Math.max(190 + BUFFER_PX, Math.min(labelWidth, 235)), 185, 265));
}

export function computeCellGridLayout(
  fields,
  availableWidth,
  optionsByField = {},
  {colGap = 16, explicitWidths = null} = {}
) {
  if (!Array.isArray(fields) || fields.length === 0) {
    return {numCols: 1, cellWidth: 220, placements: []};
  }

  const widthMap = new Map();
  const scalarWidths = [];
  for (const field of fields) {
    if (isFullRowField(field)) continue;
    const w =
      explicitWidths && typeof explicitWidths[field.field_id] === 'number'
        ? explicitWidths[field.field_id]
        : estimateFieldNaturalWidth(field, optionsByField[field.field_id] || field.options || []);
    widthMap.set(field.field_id, w);
    scalarWidths.push(w);
  }

  const rawMean =
    scalarWidths.length > 0
      ? scalarWidths.reduce((sum, w) => sum + w, 0) / scalarWidths.length
      : 240;
  const cellWidth = clamp(rawMean, MIN_CELL_PX, MAX_CELL_PX);
  const safeAvailable = Math.max(180, Number(availableWidth) || 760);
  const numCols = Math.max(1, Math.floor((safeAvailable + colGap) / (cellWidth + colGap)));

  const placements = [];
  let colCursor = 1;
  let rowIndex = 1;

  for (const field of fields) {
    if (isFullRowField(field)) {
      if (colCursor > 1) {
        rowIndex += 1;
        colCursor = 1;
      }
      placements.push({
        fieldId: field.field_id,
        row: rowIndex,
        colStart: 1,
        span: numCols,
        gridColumn: `1 / span ${numCols}`,
        ratio: numCols,
        naturalWidth: safeAvailable,
        fullRow: true,
      });
      rowIndex += 1;
      colCursor = 1;
      continue;
    }

    const nw = widthMap.get(field.field_id) ?? cellWidth;
    const ratio = nw / cellWidth;
    const span = Math.min(numCols, Math.max(1, Math.ceil(ratio - 1e-6)));
    const remaining = numCols - colCursor + 1;

    if (span > remaining) {
      rowIndex += 1;
      colCursor = 1;
    }

    const colStart = colCursor;
    placements.push({
      fieldId: field.field_id,
      row: rowIndex,
      colStart,
      span,
      gridColumn: `${colStart} / span ${span}`,
      ratio,
      naturalWidth: nw,
      fullRow: false,
    });

    colCursor += span;
    if (colCursor > numCols) {
      rowIndex += 1;
      colCursor = 1;
    }
  }

  return {
    numCols,
    cellWidth: Math.round(cellWidth * 10) / 10,
    placements,
  };
}
