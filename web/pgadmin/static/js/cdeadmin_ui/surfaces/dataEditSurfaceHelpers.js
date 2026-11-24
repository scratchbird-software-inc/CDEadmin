/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {computeCellGridLayout} from '../objects/formCellLayout';
import {safeSpreadsheetValue} from '../data/gridIO';

export const SURFACE_VIEWS = Object.freeze({
  DATA: 'data',
  METRICS: 'metrics',
  SQL: 'sql',
  FIELDS: 'fields',
  INFORMATION: 'information',
  METADATA: 'metadata',
  MESSAGES: 'messages',
});

export const DISPLAY_MODES = Object.freeze({
  GRID: 'grid',
  MINI_FORMS: 'mini_forms',
  HYBRID: 'hybrid',
  SINGLE_FORM: 'single_form',
  HYBRID_EDIT: 'hybrid_edit',
});

export function resolveRecordPresentation(mode, isEditing, editTarget) {
  if (mode !== DISPLAY_MODES.HYBRID_EDIT) return mode;
  if (!isEditing) return DISPLAY_MODES.GRID;
  return editTarget === 'single_form' ? DISPLAY_MODES.SINGLE_FORM : DISPLAY_MODES.HYBRID;
}

export const BOOLEAN_FORMATS = Object.freeze({
  TF: 'T/F',
  YN: 'Y/N',
  TRUE_FALSE: 'True/False',
  ONE_ZERO: '1/0',
});

const UUID_CLEAN_RE = /^[0-9a-fA-F]{32}$/;
const UUID_DASHED_RE =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

export function normalizeUuidText(raw) {
  const str = String(raw ?? '').trim();
  if (UUID_DASHED_RE.test(str)) return str.toLowerCase();
  if (UUID_CLEAN_RE.test(str)) {
    const lc = str.toLowerCase();
    return `${lc.slice(0, 8)}-${lc.slice(8, 12)}-${lc.slice(12, 16)}-${lc.slice(
      16,
      20
    )}-${lc.slice(20)}`;
  }
  return str;
}

export const FIELD_FONTS = {
  mono: 'var(--sr-font-mono, monospace)',
  sans: 'sans-serif',
  serif: 'serif',
};

export function inferColumnMeta(col = {}) {
  if (col.client_type) {
    return {
      clientType: col.client_type,
      defaultAlignment: col.default_alignment || 'left',
      isComplex: Boolean(col.is_complex),
    };
  }
  const inputKind = String(col.input_kind || '').toLowerCase();
  const native = String(col.native_type || '').toUpperCase();
  if (inputKind === 'array' || native.includes('ARRAY') || native.endsWith('[]')) {
    return {clientType: 'array', defaultAlignment: 'left', isComplex: true};
  }
  if (native.includes('JSON') || inputKind === 'json') {
    return {clientType: 'json', defaultAlignment: 'left', isComplex: true};
  }
  if (
    native.includes('BLOB') ||
    native.includes('BYTEA') ||
    native.includes('BINARY') ||
    inputKind === 'binary'
  ) {
    return {clientType: 'blob', defaultAlignment: 'left', isComplex: true};
  }
  if (native.includes('BOOL') || inputKind === 'boolean') {
    return {clientType: 'boolean', defaultAlignment: 'center', isComplex: false};
  }
  if (native.includes('UUID') || native.includes('GUID')) {
    return {clientType: 'uuid', defaultAlignment: 'left', isComplex: false};
  }
  if (
    /(INT|NUMERIC|DECIMAL|DECFLOAT|FLOAT|DOUBLE|REAL|NUMBER|SERIAL|MONEY)/.test(
      native
    ) ||
    ['integer', 'decimal', 'decfloat', 'float32', 'float64'].includes(inputKind)
  ) {
    return {clientType: 'number', defaultAlignment: 'right', isComplex: false};
  }
  if (/(TIMESTAMP|DATETIME)/.test(native)) {
    return {clientType: 'timestamp', defaultAlignment: 'left', isComplex: false};
  }
  if (native.includes('DATE')) {
    return {clientType: 'date', defaultAlignment: 'left', isComplex: false};
  }
  if (native.includes('TIME')) {
    return {clientType: 'time', defaultAlignment: 'left', isComplex: false};
  }
  return {clientType: 'text', defaultAlignment: 'left', isComplex: false};
}

export function isComplexOrOversizedCell(value, colMeta, colPrefs = {}) {
  if (value === null || value === undefined) return false;
  if (colPrefs.inlineBox) return false;
  if (colMeta.isComplex) return true;
  if (typeof value === 'object') return true;
  const str = String(value);
  return str.length > 512 || str.includes('\n');
}

export function formatCellValue(value, colMeta, options = {}) {
  if (value === null || value === undefined) {
    return {isNull: true, isComplex: false, text: '<null>'};
  }
  if (isComplexOrOversizedCell(value, colMeta, options.colPrefs)) {
    return {isNull: false, isComplex: true, text: '[...]'};
  }
  const boolStyle = options.booleanFormat || BOOLEAN_FORMATS.TF;
  if (colMeta.clientType === 'boolean' || typeof value === 'boolean') {
    const truthy =
      value === true ||
      value === 1 ||
      String(value).toLowerCase() === 'true' ||
      String(value).toLowerCase() === 't' ||
      String(value).toLowerCase() === 'y';
    if (boolStyle === BOOLEAN_FORMATS.YN) {
      return {isNull: false, isComplex: false, text: truthy ? 'Y' : 'N'};
    }
    if (boolStyle === BOOLEAN_FORMATS.TRUE_FALSE) {
      return {
        isNull: false,
        isComplex: false,
        text: truthy ? 'True' : 'False',
      };
    }
    if (boolStyle === BOOLEAN_FORMATS.ONE_ZERO) {
      return {isNull: false, isComplex: false, text: truthy ? '1' : '0'};
    }
    return {isNull: false, isComplex: false, text: truthy ? 'T' : 'F'};
  }

  if (colMeta.clientType === 'uuid') {
    return {isNull: false, isComplex: false, text: normalizeUuidText(value)};
  }

  if (
    colMeta.clientType === 'timestamp' ||
    colMeta.clientType === 'date' ||
    colMeta.clientType === 'time'
  ) {
    const raw = String(value);
    if (options.localeDateFormat && colMeta.clientType !== 'time') {
      const parsed = new Date(raw);
      if (!Number.isNaN(parsed.getTime())) {
        try {
          const fmtOpts =
            colMeta.clientType === 'date'
              ? {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                ...(options.timeZone ? {timeZone: options.timeZone} : {}),
              }
              : {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                ...(options.timeZone ? {timeZone: options.timeZone} : {}),
              };
          return {
            isNull: false,
            isComplex: false,
            text: new Intl.DateTimeFormat(options.locale || undefined, fmtOpts).format(
              parsed
            ),
          };
        } catch {
          // Fallback to native wire representation
        }
      }
    }
    return {isNull: false, isComplex: false, text: raw};
  }

  if (colMeta.clientType === 'number') {
    if (typeof value === 'number' && Number.isFinite(value)) {
      const decimals = options.colPrefs?.decimals;
      if (typeof decimals === 'number' && decimals >= 0 && decimals <= 12) {
        return {
          isNull: false,
          isComplex: false,
          text: value.toFixed(decimals),
        };
      }
    }
    return {isNull: false, isComplex: false, text: String(value)};
  }

  return {isNull: false, isComplex: false, text: String(value)};
}

export function serializeValueForEdit(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') {
    if (value.encoding === 'base64' && typeof value.data === 'string') {
      return value.data;
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

export function isValidJsonDraft(value, column) {
  if (inferColumnMeta(column).clientType !== 'json' || typeof value !== 'string' || value === '<null>') {
    return true;
  }
  try {
    JSON.parse(value);
    return true;
  } catch {
    return false;
  }
}

export function coerceEditedValue(rawInput, col, colMeta = inferColumnMeta(col)) {
  if (rawInput === undefined) return undefined;
  if (rawInput === null) return null;
  if (typeof rawInput === 'object') return rawInput;
  const str = String(rawInput);
  if (str === '<null>') return null;
  if (colMeta.clientType === 'boolean') {
    const lc = str.trim().toLowerCase();
    if (['t', 'true', 'y', 'yes', '1'].includes(lc)) return true;
    if (['f', 'false', 'n', 'no', '0'].includes(lc)) return false;
  }
  if (colMeta.clientType === 'json' || colMeta.clientType === 'array') {
    try {
      return JSON.parse(str);
    } catch {
      return str;
    }
  }
  if (
    colMeta.clientType === 'number' &&
    !['decfloat', 'decimal', 'integer'].includes(col?.input_kind)
  ) {
    const trimmed = str.trim();
    if (trimmed !== '' && Number.isFinite(Number(trimmed)) && trimmed.length <= 15) {
      return Number(trimmed);
    }
  }
  return str;
}

/**
 * Estimate a tight, content- and datatype-adaptive pixel width for a form field
 * so Mini-Forms, Hybrid, and Single Form pack fields efficiently without wasted width.
 */
export function estimateAdaptiveColumnWidthPx(col, meta, sampleRows = null, explicitWidthPx = null) {
  if (typeof explicitWidthPx === 'number' && Number.isFinite(explicitWidthPx) && explicitWidthPx > 0) {
    return Math.round(explicitWidthPx);
  }
  const colName = String(col?.name || '');
  const native = String(col?.native_type || '').toUpperCase();
  const lenMatch = native.match(/\((\d+)(?:\s*,\s*\d+)?\)/);
  const declaredLen =
    (typeof col?.max_length === 'number' && col.max_length > 0 ? col.max_length : null) ||
    (typeof col?.character_length === 'number' && col.character_length > 0 ? col.character_length : null) ||
    (lenMatch ? parseInt(lenMatch[1], 10) : null);

  let maxObservedChars = 0;
  if (Array.isArray(sampleRows) && sampleRows.length > 0) {
    const limit = Math.min(sampleRows.length, 60);
    for (let i = 0; i < limit; i += 1) {
      const v = sampleRows[i]?.values?.[colName];
      if (v === null || v === undefined || typeof v === 'object') continue;
      const len = String(v).length;
      if (len > maxObservedChars) maxObservedChars = len;
    }
  }

  // Header width needed so `COL_NAME 🔑  TYPE` stays readable without clipping
  const typeTagLen = Math.min(11, native.length);
  const headerNeedPx = Math.round(
    colName.length * 7.1 + (col?.key ? 18 : 0) + typeTagLen * 5.0 + 22
  );

  let dataNeedPx = 148;
  if (meta.clientType === 'boolean') {
    dataNeedPx = 74;
  } else if (meta.clientType === 'number') {
    const digits = Math.max(4, Math.min(18, maxObservedChars || declaredLen || 7));
    dataNeedPx = digits * 8.2 + 28;
  } else if (meta.clientType === 'date') {
    dataNeedPx = 114;
  } else if (meta.clientType === 'time') {
    dataNeedPx = 102;
  } else if (meta.clientType === 'timestamp') {
    dataNeedPx = 176;
  } else if (meta.clientType === 'uuid') {
    dataNeedPx = 266;
  } else if (meta.isComplex) {
    dataNeedPx = 156;
  } else {
    let targetChars;
    if (maxObservedChars > 0) {
      targetChars = Math.min(
        52,
        Math.max(
          maxObservedChars + 2,
          declaredLen && declaredLen <= 8 ? declaredLen : 2
        )
      );
    } else if (declaredLen && declaredLen > 0) {
      targetChars = Math.min(44, declaredLen);
    } else {
      targetChars = 16;
    }
    dataNeedPx = targetChars * 7.5 + 24;
  }

  return Math.round(Math.max(84, Math.min(420, Math.max(headerNeedPx, dataNeedPx))));
}

/**
 * Convert visible form columns into SR-F-020033 (`formCellLayout.js`) descriptors
 * so Mini-Forms (b), Hybrid (c), and Single Form (d) share identical placement logic
 * AND tight content-adaptive field widths (`adaptiveWidths`).
 */
export function buildFormLayoutPlacements(
  columns,
  formFieldPrefs,
  availableWidth,
  prevNumCols = null,
  sampleRows = null
) {
  const adaptiveWidths = {};
  const safeFormPrefs = formFieldPrefs || {};
  const descriptors = (columns || []).map((col) => {
    const meta = inferColumnMeta(col);
    const prefs = safeFormPrefs[col.name] || {};
    let control = 'text';
    if (prefs.inlineBox) {
      control = 'multiline';
    } else if (meta.clientType === 'boolean') {
      control = 'boolean';
    } else if (meta.clientType === 'number') {
      control = 'number';
    } else if (meta.isComplex) {
      control = 'text';
    }
    const adaptiveW = estimateAdaptiveColumnWidthPx(
      col,
      meta,
      sampleRows,
      prefs.widthPx
    );
    adaptiveWidths[col.name] = adaptiveW;
    return {
      field_id: col.name,
      label: col.name,
      control,
      required: col.nullable === false,
      width_px: prefs.inlineBox ? undefined : adaptiveW,
      max_length: meta.clientType === 'uuid' ? 36 : undefined,
    };
  });
  const base = computeCellGridLayout(descriptors, Math.max(240, availableWidth || 720), {}, {
    colGap: 12,
    prevNumCols,
  });
  return {
    ...base,
    adaptiveWidths,
  };
}

function sqlLiteral(val) {
  if (val === null || val === undefined) return 'NULL';
  if (typeof val === 'boolean') return val ? 'TRUE' : 'FALSE';
  if (typeof val === 'number' && Number.isFinite(val)) return String(val);
  if (typeof val === 'object') {
    return `'${JSON.stringify(val).replaceAll('\'', '\'\'')}'`;
  }
  return `'${String(val).replaceAll('\'', '\'\'')}'`;
}

export function formatRowsForExport(rows, columns, format, tableName = 'TARGET_TABLE') {
  const colNames = columns.map((c) => c.name);
  if (format === 'json') {
    const items = rows.map((r) => {
      const obj = {};
      for (const c of colNames) obj[c] = r.values?.[c] ?? null;
      return obj;
    });
    return JSON.stringify(items, null, 2);
  }

  if (format === 'tsv' || format === 'csv') {
    const sep = format === 'tsv' ? '\t' : ',';
    const esc = (v, isHeader = false) => {
      if (v === null || v === undefined) return '';
      const raw = isHeader
        ? String(v)
        : typeof v === 'object'
          ? String(safeSpreadsheetValue(JSON.stringify(v)))
          : String(safeSpreadsheetValue(v));
      if (format === 'csv' && (raw.includes(',') || raw.includes('"') || raw.includes('\n'))) {
        return `"${raw.replaceAll('"', '""')}"`;
      }
      return raw.replaceAll('\t', ' ').replaceAll('\n', ' ');
    };
    const header = colNames.map((c) => esc(c, true)).join(sep);
    const lines = rows.map((r) => colNames.map((c) => esc(r.values?.[c])).join(sep));
    return [header, ...lines].join('\n');
  }

  if (format === 'sql_insert') {
    const quotedTable = `"${String(tableName).replaceAll('"', '""')}"`;
    const quotedCols = colNames.map((c) => `"${c.replaceAll('"', '""')}"`).join(', ');
    return rows
      .map((r) => {
        const vals = colNames.map((c) => sqlLiteral(r.values?.[c])).join(', ');
        return `INSERT INTO ${quotedTable} (${quotedCols}) VALUES (${vals});`;
      })
      .join('\n');
  }

  if (format === 'sql_update') {
    const quotedTable = `"${String(tableName).replaceAll('"', '""')}"`;
    const keyCols = columns.filter((c) => c.key).map((c) => c.name);
    const whereCols = keyCols.length > 0 ? keyCols : colNames.slice(0, 1);
    return rows
      .map((r) => {
        const setCols = colNames.filter((c) => !whereCols.includes(c));
        const effectiveSet = setCols.length > 0 ? setCols : colNames;
        const setClause = effectiveSet
          .map((c) => `"${c.replaceAll('"', '""')}" = ${sqlLiteral(r.values?.[c])}`)
          .join(', ');
        const whereClause = whereCols
          .map((c) => {
            const v = r.values?.[c];
            return v === null || v === undefined
              ? `"${c.replaceAll('"', '""')}" IS NULL`
              : `"${c.replaceAll('"', '""')}" = ${sqlLiteral(v)}`;
          })
          .join(' AND ');
        return `UPDATE ${quotedTable} SET ${setClause} WHERE ${whereClause};`;
      })
      .join('\n');
  }

  return '';
}

export function parseImportedRecords(text, format = 'auto') {
  const trimmed = String(text || '').trim();
  if (!trimmed) return [];
  if (format === 'json' || (format === 'auto' && trimmed.startsWith('['))) {
    const parsed = JSON.parse(trimmed);
    return Array.isArray(parsed) ? parsed : [parsed];
  }
  const lines = trimmed.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 2) return [];
  const sep = lines[0].includes('\t') ? '\t' : ',';
  const splitLine = (line) => {
    const out = [];
    let cur = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      if (ch === '"') {
        if (inQuotes && line[i + 1] === '"') {
          cur += '"';
          i += 1;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (ch === sep && !inQuotes) {
        out.push(cur);
        cur = '';
      } else {
        cur += ch;
      }
    }
    out.push(cur);
    return out;
  };
  const headers = splitLine(lines[0]).map((h) => h.trim());
  return lines.slice(1).map((line) => {
    const vals = splitLine(line);
    const rec = {};
    headers.forEach((h, idx) => {
      if (!h) return;
      const v = vals[idx] ?? '';
      rec[h] = v === '' || v === '<null>' ? null : v;
    });
    return rec;
  });
}

export function formatBytes(bytes) {
  const n = Number(bytes || 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

export const MAX_COLUMN_HINT_CHARS = 128;

/**
 * Format a database column comment as a bounded per-field editing hint.
 * Slices strictly to the first 128 Unicode characters so unlimited text/blob
 * column comments remain concise and safe to render below the focused field.
 */
export function formatColumnCommentHint(comment) {
  if (comment === null || comment === undefined) return '';
  const text = String(comment).trim();
  if (!text) return '';
  const chars = Array.from(text);
  return chars.length > MAX_COLUMN_HINT_CHARS
    ? chars.slice(0, MAX_COLUMN_HINT_CHARS).join('')
    : text;
}
