/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useMemo, useState} from 'react';
import gettext from 'sources/gettext';
import {safeSpreadsheetValue} from './gridIO';
import {formatRowsForExport} from '../surfaces/dataEditSurfaceHelpers';

/**
 * Canonical 2D grid selection state shared across RecordDataView,
 * DataEditSurface, SqlEditorSurface, and UnifiedDataGrid.
 *
 * Supports:
 *  - Single cell (`cells: ['r:col']`)
 *  - Group of cells (`Shift+Click` / drag / `Shift+Arrow` rectangular block,
 *    or `Ctrl/Cmd+Click` non-contiguous cells)
 *  - Full row (`rows: [r]`) & Group of rows (`Shift+Click`, `Ctrl/Cmd+Click`, drag)
 *  - Full column (`cols: ['col']`) & Group of columns (`Shift+Click`, `Ctrl/Cmd+Click`, drag)
 *  - Combined rows AND columns (`rows: [...], cols: [...]` -> 2D sub-matrix slice)
 *  - Entire result set (`all: true` via corner button or `Ctrl/Cmd+A`)
 */
export const EMPTY_GRID_SELECTION = Object.freeze({
  all: false,
  rows: [],
  cols: [],
  cells: [],
  cellAnchor: null,
  rowAnchor: null,
  colAnchor: null,
});

export function makeCellKey(rowIndex, colName) {
  return `${rowIndex}:${colName}`;
}

export function parseCellKey(cellKey) {
  const str = String(cellKey || '');
  const sep = str.indexOf(':');
  if (sep < 0) return null;
  const rowIndex = Number.parseInt(str.slice(0, sep), 10);
  const colName = str.slice(sep + 1);
  if (!Number.isFinite(rowIndex) || rowIndex < 0 || !colName) return null;
  return {rowIndex, colName};
}

function uniqueSortedNumbers(nums, maxExclusive = Infinity) {
  return Array.from(
    new Set(
      (nums || []).filter(
        (n) => Number.isInteger(n) && n >= 0 && n < maxExclusive
      )
    )
  ).sort((a, b) => a - b);
}

function orderedColumnSubset(colNames, gridColumns) {
  const chosen = new Set(colNames || []);
  const ordered = [];
  for (const col of gridColumns || []) {
    const name = typeof col === 'string' ? col : col?.name;
    if (name && chosen.has(name)) ordered.push(name);
  }
  return ordered;
}

function buildRectangularCellKeys(r1, c1Name, r2, c2Name, gridColumns) {
  const colNames = (gridColumns || []).map((c) =>
    typeof c === 'string' ? c : c.name
  );
  const idx1 = colNames.indexOf(c1Name);
  const idx2 = colNames.indexOf(c2Name);
  const safeC1 = idx1 >= 0 ? idx1 : Math.max(0, idx2);
  const safeC2 = idx2 >= 0 ? idx2 : Math.max(0, idx1);
  if (!colNames.length) return [];

  const minR = Math.max(0, Math.min(r1, r2));
  const maxR = Math.max(0, Math.max(r1, r2));
  const minC = Math.max(0, Math.min(safeC1, safeC2));
  const maxC = Math.min(colNames.length - 1, Math.max(safeC1, safeC2));

  const keys = [];
  for (let r = minR; r <= maxR; r += 1) {
    for (let c = minC; c <= maxC; c += 1) {
      keys.push(makeCellKey(r, colNames[c]));
    }
  }
  return keys;
}

function materializeSelectionToCellSet(selection, rowCount, gridColumns) {
  const set = new Set();
  if (!selection) return set;
  const colNames = (gridColumns || []).map((c) =>
    typeof c === 'string' ? c : c.name
  );
  if (selection.all) {
    for (let r = 0; r < rowCount; r += 1) {
      for (const cName of colNames) {
        set.add(makeCellKey(r, cName));
      }
    }
    return set;
  }
  const hasRows = selection.rows?.length > 0;
  const hasCols = selection.cols?.length > 0;
  if (hasRows && hasCols) {
    const colSet = new Set(selection.cols);
    for (const r of selection.rows) {
      if (r < 0 || r >= rowCount) continue;
      for (const cName of colNames) {
        if (colSet.has(cName)) set.add(makeCellKey(r, cName));
      }
    }
  } else if (hasRows) {
    for (const r of selection.rows) {
      if (r < 0 || r >= rowCount) continue;
      for (const cName of colNames) {
        set.add(makeCellKey(r, cName));
      }
    }
  } else if (hasCols) {
    const colSet = new Set(selection.cols);
    for (let r = 0; r < rowCount; r += 1) {
      for (const cName of colNames) {
        if (colSet.has(cName)) set.add(makeCellKey(r, cName));
      }
    }
  }
  for (const k of selection.cells || []) {
    const parsed = parseCellKey(k);
    if (parsed && parsed.rowIndex < rowCount && colNames.includes(parsed.colName)) {
      set.add(k);
    }
  }
  return set;
}

export function selectSingleCellState(_prev, rowIndex, colName) {
  const safeRow = Math.max(0, Number(rowIndex) || 0);
  const safeCol = String(colName || '');
  return {
    all: false,
    rows: [],
    cols: [],
    cells: safeCol ? [makeCellKey(safeRow, safeCol)] : [],
    cellAnchor: safeCol ? {rowIndex: safeRow, colName: safeCol} : null,
    rowAnchor: safeRow,
    colAnchor: safeCol || null,
  };
}

export function extendCellRangeState(
  prev,
  rowIndex,
  colName,
  gridColumns,
  rowCount = Infinity,
  additive = false
) {
  const safeRow = Math.max(0, Number(rowIndex) || 0);
  const safeCol = String(colName || (gridColumns?.[0]?.name ?? ''));
  const anchor = prev?.cellAnchor || {rowIndex: safeRow, colName: safeCol};
  const rectKeys = buildRectangularCellKeys(
    anchor.rowIndex,
    anchor.colName,
    safeRow,
    safeCol,
    gridColumns
  );
  let nextCells = rectKeys;
  if (additive && Number.isFinite(rowCount)) {
    const base = materializeSelectionToCellSet(prev, rowCount, gridColumns);
    for (const k of rectKeys) base.add(k);
    nextCells = Array.from(base);
  } else if (additive && prev?.cells?.length) {
    nextCells = Array.from(new Set([...prev.cells, ...rectKeys]));
  }
  return {
    all: false,
    rows: [],
    cols: [],
    cells: nextCells,
    cellAnchor: anchor,
    rowAnchor: anchor.rowIndex,
    colAnchor: anchor.colName,
  };
}

export function selectDragCellRangeState(
  prev,
  startRow,
  startCol,
  endRow,
  endCol,
  gridColumns,
  baseCells = null
) {
  const rectKeys = buildRectangularCellKeys(
    startRow,
    startCol,
    endRow,
    endCol,
    gridColumns
  );
  const nextCells =
    Array.isArray(baseCells) && baseCells.length > 0
      ? Array.from(new Set([...baseCells, ...rectKeys]))
      : rectKeys;
  return {
    all: false,
    rows: [],
    cols: [],
    cells: nextCells,
    cellAnchor: {rowIndex: startRow, colName: startCol},
    rowAnchor: startRow,
    colAnchor: startCol,
  };
}

export function toggleCellInSelectionState(
  prev,
  rowIndex,
  colName,
  rowCount,
  gridColumns
) {
  const safeRow = Math.max(0, Number(rowIndex) || 0);
  const safeCol = String(colName || '');
  if (!safeCol) return prev || EMPTY_GRID_SELECTION;

  const set = materializeSelectionToCellSet(prev, rowCount, gridColumns);
  const key = makeCellKey(safeRow, safeCol);
  if (set.has(key)) {
    set.delete(key);
  } else {
    set.add(key);
  }
  return {
    all: false,
    rows: [],
    cols: [],
    cells: Array.from(set),
    cellAnchor: {rowIndex: safeRow, colName: safeCol},
    rowAnchor: safeRow,
    colAnchor: safeCol,
  };
}

export function selectRowState(
  prev,
  rowIndex,
  {shiftKey = false, ctrlKey = false, metaKey = false} = {},
  rowCount = Infinity
) {
  const isToggle = Boolean(ctrlKey || metaKey);
  const clamped = Math.max(
    0,
    Math.min(Number(rowIndex) || 0, Math.max(0, rowCount - 1))
  );

  if (shiftKey) {
    const anchor = prev?.rowAnchor ?? clamped;
    const minR = Math.max(0, Math.min(anchor, clamped));
    const maxR = Math.min(Math.max(0, rowCount - 1), Math.max(anchor, clamped));
    const range = [];
    for (let r = minR; r <= maxR; r += 1) range.push(r);
    const mergedRows = isToggle
      ? uniqueSortedNumbers([...(prev?.rows || []), ...range], rowCount)
      : range;
    const keepCols =
      isToggle || (prev?.cols?.length > 0 && prev?.rows?.length > 0)
        ? prev.cols
        : [];
    return {
      all: false,
      rows: mergedRows,
      cols: keepCols,
      cells: [],
      cellAnchor: {rowIndex: anchor, colName: prev?.colAnchor || ''},
      rowAnchor: anchor,
      colAnchor: prev?.colAnchor || null,
    };
  }

  if (isToggle) {
    let baseRows = prev?.rows || [];
    if (prev?.all && Number.isFinite(rowCount)) {
      baseRows = Array.from({length: rowCount}, (_, idx) => idx);
    }
    const rowSet = new Set(baseRows);
    if (rowSet.has(clamped)) rowSet.delete(clamped);
    else rowSet.add(clamped);
    return {
      all: false,
      rows: uniqueSortedNumbers(Array.from(rowSet), rowCount),
      cols: prev?.all ? [] : prev?.cols || [],
      cells: [],
      cellAnchor: {rowIndex: clamped, colName: prev?.colAnchor || ''},
      rowAnchor: clamped,
      colAnchor: prev?.colAnchor || null,
    };
  }

  return {
    all: false,
    rows: [clamped],
    cols: [],
    cells: [],
    cellAnchor: {rowIndex: clamped, colName: prev?.colAnchor || ''},
    rowAnchor: clamped,
    colAnchor: prev?.colAnchor || null,
  };
}

export function selectDragRowRangeState(
  prev,
  startRow,
  endRow,
  rowCount = Infinity,
  baseRows = null,
  preservedCols = null
) {
  const minR = Math.max(0, Math.min(startRow, endRow));
  const maxR = Math.min(Math.max(0, rowCount - 1), Math.max(startRow, endRow));
  const range = [];
  for (let r = minR; r <= maxR; r += 1) range.push(r);
  const rows =
    Array.isArray(baseRows) && baseRows.length > 0
      ? uniqueSortedNumbers([...baseRows, ...range], rowCount)
      : range;
  return {
    all: false,
    rows,
    cols: Array.isArray(preservedCols) ? preservedCols : [],
    cells: [],
    cellAnchor: {rowIndex: startRow, colName: prev?.colAnchor || ''},
    rowAnchor: startRow,
    colAnchor: prev?.colAnchor || null,
  };
}

export function selectColumnState(
  prev,
  colName,
  {shiftKey = false, ctrlKey = false, metaKey = false} = {},
  gridColumns = []
) {
  const colNames = (gridColumns || []).map((c) =>
    typeof c === 'string' ? c : c.name
  );
  if (!colName || !colNames.includes(colName)) {
    return prev || EMPTY_GRID_SELECTION;
  }
  const isToggle = Boolean(ctrlKey || metaKey);

  if (shiftKey) {
    const anchorCol =
      prev?.colAnchor && colNames.includes(prev.colAnchor)
        ? prev.colAnchor
        : colName;
    const i1 = colNames.indexOf(anchorCol);
    const i2 = colNames.indexOf(colName);
    const rangeCols = colNames.slice(Math.min(i1, i2), Math.max(i1, i2) + 1);
    const mergedCols = isToggle
      ? orderedColumnSubset([...(prev?.cols || []), ...rangeCols], gridColumns)
      : rangeCols;
    const keepRows =
      isToggle || (prev?.rows?.length > 0 && prev?.cols?.length > 0)
        ? prev.rows
        : [];
    return {
      all: false,
      rows: keepRows,
      cols: mergedCols,
      cells: [],
      cellAnchor: {rowIndex: prev?.rowAnchor ?? 0, colName: anchorCol},
      rowAnchor: prev?.rowAnchor ?? 0,
      colAnchor: anchorCol,
    };
  }

  if (isToggle) {
    let baseCols = prev?.cols || [];
    if (prev?.all) {
      baseCols = [...colNames];
    }
    const colSet = new Set(baseCols);
    if (colSet.has(colName)) colSet.delete(colName);
    else colSet.add(colName);
    return {
      all: false,
      rows: prev?.all ? [] : prev?.rows || [],
      cols: orderedColumnSubset(Array.from(colSet), gridColumns),
      cells: [],
      cellAnchor: {rowIndex: prev?.rowAnchor ?? 0, colName},
      rowAnchor: prev?.rowAnchor ?? 0,
      colAnchor: colName,
    };
  }

  return {
    all: false,
    rows: [],
    cols: [colName],
    cells: [],
    cellAnchor: {rowIndex: prev?.rowAnchor ?? 0, colName},
    rowAnchor: prev?.rowAnchor ?? 0,
    colAnchor: colName,
  };
}

export function selectDragColumnRangeState(
  prev,
  startCol,
  endCol,
  gridColumns = [],
  baseCols = null,
  preservedRows = null
) {
  const colNames = (gridColumns || []).map((c) =>
    typeof c === 'string' ? c : c.name
  );
  const i1 = colNames.indexOf(startCol);
  const i2 = colNames.indexOf(endCol);
  if (i1 < 0 || i2 < 0) return prev || EMPTY_GRID_SELECTION;
  const rangeCols = colNames.slice(Math.min(i1, i2), Math.max(i1, i2) + 1);
  const cols =
    Array.isArray(baseCols) && baseCols.length > 0
      ? orderedColumnSubset([...baseCols, ...rangeCols], gridColumns)
      : rangeCols;
  return {
    all: false,
    rows: Array.isArray(preservedRows) ? preservedRows : [],
    cols,
    cells: [],
    cellAnchor: {rowIndex: prev?.rowAnchor ?? 0, colName: startCol},
    rowAnchor: prev?.rowAnchor ?? 0,
    colAnchor: startCol,
  };
}

export function selectAllState(gridColumns = []) {
  const firstCol =
    typeof gridColumns?.[0] === 'string'
      ? gridColumns[0]
      : gridColumns?.[0]?.name || '';
  return {
    all: true,
    rows: [],
    cols: [],
    cells: [],
    cellAnchor: {rowIndex: 0, colName: firstCol},
    rowAnchor: 0,
    colAnchor: firstCol || null,
  };
}

export function isGridRowSelected(selection, rowIndex) {
  if (!selection) return false;
  if (selection.all) return true;
  return Boolean(selection.rows?.includes(rowIndex));
}

export function isGridColumnSelected(selection, colName) {
  if (!selection) return false;
  if (selection.all) return true;
  return Boolean(selection.cols?.includes(colName));
}

export function isGridCellSelected(selection, rowIndex, colName) {
  if (!selection) return false;
  if (selection.all) return true;
  const hasRows = selection.rows?.length > 0;
  const hasCols = selection.cols?.length > 0;
  if (hasRows && hasCols) {
    if (selection.rows.includes(rowIndex) && selection.cols.includes(colName)) {
      return true;
    }
  } else if (hasRows) {
    if (selection.rows.includes(rowIndex)) return true;
  } else if (hasCols) {
    if (selection.cols.includes(colName)) return true;
  }
  if (selection.cells?.length) {
    return selection.cells.includes(makeCellKey(rowIndex, colName));
  }
  return false;
}

/**
 * Extract the ordered 2D sub-matrix (`slicedRows` x `selectedColumns`)
 * represented by the current selection so Copy and Export act on the exact
 * cell, cell block, row(s), column(s), row-x-column intersection, or full
 * result set chosen by the user.
 */
export function extractSelectionSlice(
  rows = [],
  gridColumns = [],
  selection = EMPTY_GRID_SELECTION,
  activeRowIndex = 0,
  activeColName = ''
) {
  const rowCount = rows.length;
  const colMap = new Map(gridColumns.map((c) => [c.name, c]));
  const allColNames = gridColumns.map((c) => c.name);

  if (rowCount === 0 || gridColumns.length === 0) {
    return {
      kind: 'empty',
      hasMultiSelection: false,
      allRowsSelected: false,
      rowIndices: [],
      selectedColumns: [],
      slicedRows: [],
      cellCount: 0,
      scalarValue: null,
    };
  }

  // 1. Entire result set
  if (selection?.all) {
    const rowIndices = Array.from({length: rowCount}, (_, i) => i);
    return {
      kind: 'all',
      hasMultiSelection: true,
      allRowsSelected: true,
      rowIndices,
      selectedColumns: gridColumns,
      slicedRows: rows,
      cellCount: rowCount * gridColumns.length,
      scalarValue: null,
    };
  }

  const validRows = uniqueSortedNumbers(selection?.rows || [], rowCount);
  const validColNames = orderedColumnSubset(selection?.cols || [], gridColumns);
  const validParsedCells = (selection?.cells || [])
    .map(parseCellKey)
    .filter(
      (c) => c && c.rowIndex < rowCount && colMap.has(c.colName)
    );

  // 2. Both rows AND columns selected -> 2D intersection sub-matrix
  if (validRows.length > 0 && validColNames.length > 0) {
    const selectedColumns = validColNames.map((n) => colMap.get(n)).filter(Boolean);
    const slicedRows = validRows.map((rIdx) => {
      const src = rows[rIdx];
      const vals = {};
      for (const col of selectedColumns) {
        vals[col.name] = src?.values?.[col.name] ?? null;
      }
      return {...src, values: vals};
    });
    return {
      kind: 'rows_and_cols',
      hasMultiSelection: true,
      allRowsSelected: false,
      rowIndices: validRows,
      selectedColumns,
      slicedRows,
      cellCount: validRows.length * selectedColumns.length,
      scalarValue:
        validRows.length === 1 && selectedColumns.length === 1
          ? slicedRows[0]?.values?.[selectedColumns[0].name]
          : null,
    };
  }

  // 3. Full row or group of rows
  if (validRows.length > 0) {
    const slicedRows = validRows.map((rIdx) => rows[rIdx]);
    return {
      kind: validRows.length === 1 ? 'row' : 'rows',
      hasMultiSelection: true,
      allRowsSelected: false,
      rowIndices: validRows,
      selectedColumns: gridColumns,
      slicedRows,
      cellCount: validRows.length * gridColumns.length,
      scalarValue: null,
    };
  }

  // 4. Full column or group of columns
  if (validColNames.length > 0) {
    const selectedColumns = validColNames.map((n) => colMap.get(n)).filter(Boolean);
    const rowIndices = Array.from({length: rowCount}, (_, i) => i);
    const slicedRows = rows.map((src) => {
      const vals = {};
      for (const col of selectedColumns) {
        vals[col.name] = src?.values?.[col.name] ?? null;
      }
      return {...src, values: vals};
    });
    return {
      kind: selectedColumns.length === 1 ? 'column' : 'columns',
      hasMultiSelection: true,
      allRowsSelected: true,
      rowIndices,
      selectedColumns,
      slicedRows,
      cellCount: rowCount * selectedColumns.length,
      scalarValue: null,
    };
  }

  // 5. Group of cells (> 1 cell)
  if (validParsedCells.length > 1) {
    const cellKeySet = new Set(
      validParsedCells.map((c) => makeCellKey(c.rowIndex, c.colName))
    );
    const rowIndices = uniqueSortedNumbers(
      validParsedCells.map((c) => c.rowIndex),
      rowCount
    );
    const colNamesInCells = orderedColumnSubset(
      validParsedCells.map((c) => c.colName),
      gridColumns
    );
    const selectedColumns = colNamesInCells
      .map((n) => colMap.get(n))
      .filter(Boolean);
    const slicedRows = rowIndices.map((rIdx) => {
      const src = rows[rIdx];
      const vals = {};
      for (const col of selectedColumns) {
        vals[col.name] = cellKeySet.has(makeCellKey(rIdx, col.name))
          ? (src?.values?.[col.name] ?? null)
          : null;
      }
      return {...src, values: vals};
    });
    return {
      kind: 'cells',
      hasMultiSelection: true,
      allRowsSelected: false,
      rowIndices,
      selectedColumns,
      slicedRows,
      cellCount: cellKeySet.size,
      scalarValue: null,
    };
  }

  // 6. Single cell (explicitly clicked 1 cell or active cursor cell)
  const fallbackRow = Math.max(0, Math.min(activeRowIndex || 0, rowCount - 1));
  const fallbackCol =
    activeColName && colMap.has(activeColName)
      ? activeColName
      : allColNames[0] || '';
  const single =
    validParsedCells.length === 1
      ? validParsedCells[0]
      : {rowIndex: fallbackRow, colName: fallbackCol};
  const colObj = colMap.get(single.colName) || gridColumns[0];
  const scalarValue = rows[single.rowIndex]?.values?.[colObj.name];

  return {
    kind: 'cell',
    hasMultiSelection: false,
    allRowsSelected: false,
    explicitSingleCell: validParsedCells.length === 1,
    rowIndices: [single.rowIndex],
    selectedColumns: [colObj],
    slicedRows: [
      {
        ...rows[single.rowIndex],
        values: {[colObj.name]: scalarValue},
      },
    ],
    cellCount: 1,
    scalarValue,
  };
}

export function formatScalarForClipboard(val) {
  if (val === null || val === undefined) return '';
  if (typeof val === 'object') return JSON.stringify(val);
  return String(safeSpreadsheetValue(val));
}

export function formatSelectionForClipboard(
  slice,
  format = 'auto',
  tableName = 'RESULT_SET',
  {includeHeader = true} = {}
) {
  if (!slice || slice.kind === 'empty') return '';
  if (format === 'auto') {
    if (!slice.hasMultiSelection) {
      return formatScalarForClipboard(slice.scalarValue);
    }
    const fullTsv = formatRowsForExport(
      slice.slicedRows,
      slice.selectedColumns,
      'tsv',
      tableName
    );
    if (!includeHeader) {
      const nl = fullTsv.indexOf('\n');
      return nl >= 0 ? fullTsv.slice(nl + 1) : '';
    }
    return fullTsv;
  }

  const formatted = formatRowsForExport(
    slice.slicedRows,
    slice.selectedColumns,
    format,
    tableName
  );
  if (!includeHeader && (format === 'tsv' || format === 'csv')) {
    const nl = formatted.indexOf('\n');
    return nl >= 0 ? formatted.slice(nl + 1) : '';
  }
  return formatted;
}

export function summarizeGridSelection(
  slice,
  activeRowIndex = 0,
  activeColName = '',
  windowOffset = 0
) {
  const globalRowNum = windowOffset + (activeRowIndex || 0) + 1;
  if (!slice || slice.kind === 'empty' || !slice.hasMultiSelection) {
    return activeColName
      ? `${gettext('Row')} ${globalRowNum} · ${activeColName}`
      : `${gettext('Row')} ${globalRowNum}`;
  }

  // Compute numeric sum across selected cells
  let sum = 0;
  let numCnt = 0;
  for (const r of slice.slicedRows) {
    for (const c of slice.selectedColumns) {
      const v = r?.values?.[c.name];
      if (
        v !== null &&
        v !== undefined &&
        v !== '' &&
        typeof v !== 'boolean' &&
        Number.isFinite(Number(v))
      ) {
        sum += Number(v);
        numCnt += 1;
      }
    }
  }
  const sumSuffix =
    numCnt > 0 ? ` · ${gettext('Sum')}: ${sum.toLocaleString()}` : '';

  if (slice.kind === 'all') {
    return `${gettext('All')} (${slice.rowIndices.length} × ${slice.selectedColumns.length})${sumSuffix}`;
  }
  if (slice.kind === 'row') {
    return `${gettext('Row')} ${windowOffset + slice.rowIndices[0] + 1} (${slice.selectedColumns.length} ${gettext('cols')})${sumSuffix}`;
  }
  if (slice.kind === 'rows') {
    return `${slice.rowIndices.length} ${gettext('rows selected')} (${slice.cellCount} ${gettext('cells')})${sumSuffix}`;
  }
  if (slice.kind === 'column') {
    return `${gettext('Column')} ${slice.selectedColumns[0]?.name} (${slice.rowIndices.length} ${gettext('rows')})${sumSuffix}`;
  }
  if (slice.kind === 'columns') {
    return `${slice.selectedColumns.length} ${gettext('columns selected')} (${slice.cellCount} ${gettext('cells')})${sumSuffix}`;
  }
  if (slice.kind === 'rows_and_cols') {
    return `${slice.rowIndices.length} ${gettext('rows')} × ${slice.selectedColumns.length} ${gettext('cols')} (${slice.cellCount} ${gettext('cells')})${sumSuffix}`;
  }
  return `${slice.cellCount} ${gettext('cells selected')}${sumSuffix}`;
}

/**
 * Shared React hook managing 2D spreadsheet-style selection, keyboard range
 * extension, drag selection, and clipboard copy across all ScratchRobin grids.
 */
export function useGridSelection({
  rows = [],
  gridColumns = [],
  activeRowIndex = 0,
  activeColName = '',
  selectRowAtIndex,
  setActiveColName,
  tableName = 'RESULT_SET',
}) {
  const [selection, setSelection] = useState(EMPTY_GRID_SELECTION);

  const selectionSlice = useMemo(
    () =>
      extractSelectionSlice(
        rows,
        gridColumns,
        selection,
        activeRowIndex,
        activeColName
      ),
    [rows, gridColumns, selection, activeRowIndex, activeColName]
  );

  const selectSingleCell = useCallback((rowIndex, colName) => {
    setSelection((prev) => selectSingleCellState(prev, rowIndex, colName));
  }, []);

  const handleCellClick = useCallback(
    (rowIndex, colName, ev) => {
      const shiftKey = Boolean(ev?.shiftKey);
      const ctrlKey = Boolean(ev?.ctrlKey || ev?.metaKey);
      if (shiftKey) {
        setSelection((prev) =>
          extendCellRangeState(
            prev.cellAnchor
              ? prev
              : {
                ...prev,
                cellAnchor: {
                  rowIndex: activeRowIndex || 0,
                  colName: activeColName || colName,
                },
              },
            rowIndex,
            colName,
            gridColumns,
            rows.length,
            ctrlKey
          )
        );
        selectRowAtIndex?.(rowIndex, colName, {preserveSelection: true});
      } else if (ctrlKey) {
        setSelection((prev) => {
          // Ensure the previously active single cell stays in the set when Ctrl-adding a second cell
          const seeded =
            !prev.all &&
            prev.rows.length === 0 &&
            prev.cols.length === 0 &&
            prev.cells.length === 0 &&
            activeColName
              ? {
                ...prev,
                cells: [makeCellKey(activeRowIndex || 0, activeColName)],
              }
              : prev;
          return toggleCellInSelectionState(
            seeded,
            rowIndex,
            colName,
            rows.length,
            gridColumns
          );
        });
        selectRowAtIndex?.(rowIndex, colName, {preserveSelection: true});
      } else {
        setSelection((prev) => selectSingleCellState(prev, rowIndex, colName));
        selectRowAtIndex?.(rowIndex, colName, {preserveSelection: true});
      }
    },
    [activeColName, activeRowIndex, gridColumns, rows.length, selectRowAtIndex]
  );

  const handleRowHeaderClick = useCallback(
    (rowIndex, ev) => {
      setSelection((prev) =>
        selectRowState(
          prev,
          rowIndex,
          {
            shiftKey: Boolean(ev?.shiftKey),
            ctrlKey: Boolean(ev?.ctrlKey),
            metaKey: Boolean(ev?.metaKey),
          },
          rows.length
        )
      );
      selectRowAtIndex?.(rowIndex, undefined, {preserveSelection: true});
    },
    [rows.length, selectRowAtIndex]
  );

  const handleColumnSelectClick = useCallback(
    (colName, ev) => {
      setSelection((prev) => {
        const seeded =
          ev?.shiftKey && !prev.colAnchor && activeColName
            ? {...prev, colAnchor: activeColName}
            : prev;
        return selectColumnState(
          seeded,
          colName,
          {
            shiftKey: Boolean(ev?.shiftKey),
            ctrlKey: Boolean(ev?.ctrlKey),
            metaKey: Boolean(ev?.metaKey),
          },
          gridColumns
        );
      });
      setActiveColName?.(colName);
    },
    [activeColName, gridColumns, setActiveColName]
  );

  const selectAll = useCallback(() => {
    if (!rows.length || !gridColumns.length) return;
    setSelection(selectAllState(gridColumns));
  }, [rows.length, gridColumns]);

  const clearSelection = useCallback(() => {
    setSelection((prev) =>
      selectSingleCellState(
        prev,
        activeRowIndex || 0,
        activeColName || gridColumns[0]?.name || ''
      )
    );
  }, [activeRowIndex, activeColName, gridColumns]);

  const toggleSelectAll = useCallback(() => {
    if (!rows.length || !gridColumns.length) return;
    setSelection((prev) =>
      prev.all
        ? selectSingleCellState(
          prev,
          activeRowIndex || 0,
          activeColName || gridColumns[0]?.name || ''
        )
        : selectAllState(gridColumns)
    );
  }, [rows.length, gridColumns, activeRowIndex, activeColName]);

  const extendCellSelectionTo = useCallback(
    (targetRowIndex, targetColName) => {
      const clampedRow = Math.max(
        0,
        Math.min(targetRowIndex, Math.max(0, rows.length - 1))
      );
      const safeCol =
        targetColName || activeColName || gridColumns[0]?.name || '';
      setSelection((prev) => {
        // If user was extending full-row selection (e.g. after Shift+Space)
        if (prev.rows.length > 0 && prev.cols.length === 0 && targetColName === activeColName) {
          return selectRowState(prev, clampedRow, {shiftKey: true}, rows.length);
        }
        // If user was extending full-column selection (e.g. after Ctrl+Space)
        if (prev.cols.length > 0 && prev.rows.length === 0 && clampedRow === activeRowIndex) {
          return selectColumnState(prev, safeCol, {shiftKey: true}, gridColumns);
        }
        const seeded = prev.cellAnchor
          ? prev
          : {
            ...prev,
            cellAnchor: {
              rowIndex: activeRowIndex || 0,
              colName: activeColName || safeCol,
            },
          };
        return extendCellRangeState(
          seeded,
          clampedRow,
          safeCol,
          gridColumns,
          rows.length,
          false
        );
      });
      selectRowAtIndex?.(clampedRow, safeCol, {preserveSelection: true});
    },
    [activeColName, activeRowIndex, gridColumns, rows.length, selectRowAtIndex]
  );

  const copySelectionToClipboard = useCallback(
    (format = 'auto', options = {}) => {
      const text = formatSelectionForClipboard(
        selectionSlice,
        format,
        tableName,
        options
      );
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(text).catch(() => {});
      }
      return text;
    },
    [selectionSlice, tableName]
  );

  return {
    selection,
    setSelection,
    selectionSlice,
    selectSingleCell,
    handleCellClick,
    handleRowHeaderClick,
    handleColumnSelectClick,
    selectAll,
    clearSelection,
    toggleSelectAll,
    extendCellSelectionTo,
    copySelectionToClipboard,
  };
}
