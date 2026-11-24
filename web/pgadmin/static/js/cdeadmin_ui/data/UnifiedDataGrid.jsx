/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Popover as BasePopover} from '@base-ui/react/popover';
import gettext from 'sources/gettext';
import {ensureScratchBaseStyles} from '../base/ScratchBaseStyles';
import {Box, Stack} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {Checkbox, Select} from '../primitives/Choice';
import {SearchField} from '../primitives/AdvancedControls';
import RecordDataView from '../surfaces/RecordDataView';
import {defaultLayoutState, orderedColumns} from '../surfaces/RecordForm';
import ColumnOrderDialog from '../surfaces/RecordColumnOrderDialog';
import ColumnDisplaySettingsDialog from '../surfaces/ColumnDisplaySettingsDialog';
import {
  DISPLAY_MODES,
  buildFormLayoutPlacements,
  resolveRecordPresentation,
} from '../surfaces/dataEditSurfaceHelpers';
import GridNavigation from './GridNavigation';
import {downloadGridExport, serializeGridData} from './gridIO';
import {
  formatScalarForClipboard,
  summarizeGridSelection,
  useGridSelection,
} from './gridSelection';

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200, 500].map((val) => ({
  value: String(val),
  label: String(val),
}));

function normalizeColumnSpec(col, idx) {
  if (typeof col === 'string') {
    return {name: col, label: col, fieldKey: col, editable: true};
  }
  const stringKey = typeof col.key === 'string' && col.key ? col.key : null;
  const name = String(stringKey ?? col.accessorKey ?? col.name ?? col.id ?? `col_${idx + 1}`);
  const label = String(col.label ?? col.header ?? col.title ?? col.name ?? stringKey ?? name);
  const fieldKey = stringKey || col.accessorKey || col.name || name;
  const inferredType =
    col.native_type ||
    col.data_type ||
    col.type ||
    (col.numeric ? 'numeric' : col.mono ? 'varchar' : '');
  return {
    ...col,
    name,
    label,
    fieldKey,
    native_type: inferredType,
    key: Boolean(col.key === true || col.primary_key),
    editable: col.editable !== false,
    insertable: col.insertable !== false,
    comment: col.comment || col.help || '',
  };
}

function extractRawRowValues(row, normalizedCols) {
  if (!row || typeof row !== 'object') {
    const first = normalizedCols[0]?.name || 'value';
    return {[first]: row};
  }
  if (row.values && typeof row.values === 'object' && !Array.isArray(row.values)) {
    return row.values;
  }
  const values = {};
  for (const col of normalizedCols) {
    if (typeof col.accessorFn === 'function') {
      values[col.name] = col.accessorFn(row);
    } else if (col.accessorKey && row[col.accessorKey] !== undefined) {
      values[col.name] = row[col.accessorKey];
    } else if (col.fieldKey && row[col.fieldKey] !== undefined) {
      values[col.name] = row[col.fieldKey];
    } else {
      values[col.name] = row[col.name];
    }
  }
  return values;
}

function compareCellValues(a, b) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), undefined, {numeric: true, sensitivity: 'base'});
}

/**
 * Standardized Application Data Grid (`DN-06` / `DN-08` / `DN-10` / `DN-11`):
 * Wraps `RecordDataView` + `AdaptiveRecordFormCard` + `ColumnOrderDialog` +
 * `GridNavigation` + `gridIO` formula-safe export so read-only and editable
 * tables across surfaces, modules, dialogs, and DDN modals share identical:
 *   - 58px row-number & `!` bookmark gutter + top-left `☰` column chooser
 *   - Switchable Grid / Mini-Form / Hybrid / Full-Form presentations
 *   - 3-way column header sort, resize, and sticky pinning
 *   - 2D keyboard navigation (`Tab`, `Arrows`, `Home`/`End`, `PgUp`/`PgDn`, `Ctrl+B`)
 *   - Search, faceted filter chips, client pagination, and reactive Right-Drawer inspection
 */
export default function UnifiedDataGrid({
  columns = [],
  rows = [],
  rowKeyGetter,
  caption,
  ariaLabel,
  qaKey,
  gridRole = 'grid',
  emptyMessage,
  readOnly = true,
  editable = !readOnly,
  onChangeRows,
  defaultDisplayMode = DISPLAY_MODES.GRID,
  displayMode: controlledDisplayMode,
  onDisplayModeChange,
  allowModeSwitch = true,
  searchable = false,
  searchPlaceholder = gettext('Filter rows…'),
  facets = [],
  pagination = false,
  defaultPageSize = 100,
  exportable = false,
  onInspectRow,
  inspectInShellDrawer = false,
  toolbarLeading = null,
  toolbarTrailing = null,
  minHeight = 200,
  maxHeight,
  style,
}) {
  useEffect(() => {
    ensureScratchBaseStyles();
  }, []);

  const gridViewportRef = useRef(null);
  const containerRef = useRef(null);
  const [viewportWidth, setViewportWidth] = useState(780);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver !== 'function') return undefined;
    const ro = new ResizeObserver((entries) => {
      const w = Math.floor(entries?.[0]?.contentRect?.width || el.clientWidth || 0);
      if (w > 120) setViewportWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const normalizedColumns = useMemo(() => {
    if (columns && columns.length > 0) {
      return columns.map(normalizeColumnSpec);
    }
    const sample = rows[0];
    if (!sample || typeof sample !== 'object') return [];
    const src = sample.values && typeof sample.values === 'object' ? sample.values : sample;
    return Object.keys(src)
      .filter((k) => !k.startsWith('__'))
      .map((k, idx) => normalizeColumnSpec({name: k, label: k}, idx));
  }, [columns, rows]);

  const initialWidthPrefs = useMemo(() => {
    const prefs = {};
    for (const col of normalizedColumns) {
      if (typeof col.width === 'number') {
        prefs[col.name] = {width: col.width};
      }
    }
    return prefs;
  }, [normalizedColumns]);

  const [layout, setLayout] = useState(() => ({
    ...defaultLayoutState(),
    displayMode: controlledDisplayMode || defaultDisplayMode,
    gridColPrefs: initialWidthPrefs,
  }));

  const activeDisplayMode = controlledDisplayMode || layout.displayMode;
  const setDisplayMode = (nextMode) => {
    setLayout((prev) => ({...prev, displayMode: nextMode}));
    onDisplayModeChange?.(nextMode);
  };

  const [searchQuery, setSearchQuery] = useState('');
  const [facetSelections, setFacetSelections] = useState({});
  const [sorts, setSorts] = useState([]); // [{ column, direction: 'asc' | 'desc' }]
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(defaultPageSize);
  const [activeRowIndex, setActiveRowIndex] = useState(0);
  const [activeColName, setActiveColName] = useState(() => normalizedColumns[0]?.name || null);
  const [bookmarkedGlobals, setBookmarkedGlobals] = useState(() => new Set());
  const pendingFocusRef = useRef(null);
  const [, setScrollRowRange] = useState({start: 0, end: 50});
  const [columnPickerOpen, setColumnPickerOpen] = useState(false);
  const [columnPickerScope, setColumnPickerScope] = useState('grid');
  const [formatFieldName, setFormatFieldName] = useState(null);

  // Optional local row editing state when `editable` is true
  const [isEditingRow, setIsEditingRow] = useState(false);
  const [editingRowIndex, setEditingRowIndex] = useState(null);
  const [rowDraft, setRowDraft] = useState(null);

  const normalizedRecords = useMemo(
    () =>
      (rows || []).map((raw, idx) => {
        const vals = extractRawRowValues(raw, normalizedColumns);
        const token =
          typeof rowKeyGetter === 'function'
            ? String(rowKeyGetter(raw, idx))
            : String(raw?.identity_token ?? raw?.id ?? idx);
        return {
          __raw: raw,
          __sourceIndex: idx,
          identity_token: token,
          row_number: raw?.row_number ?? idx + 1,
          stage_state: raw?.stage_state || null,
          values: vals,
        };
      }),
    [rows, normalizedColumns, rowKeyGetter]
  );

  const filteredRecords = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return normalizedRecords.filter((rec) => {
      for (const facet of facets) {
        const facetKey = facet.id || facet.column || facet.label;
        const chosen = facetSelections[facetKey];
        if (Array.isArray(chosen) && chosen.length > 0) {
          const colKey = facet.column || facet.id || facetKey;
          const v = String(rec.values?.[colKey] ?? rec.__raw?.[colKey] ?? '');
          if (!chosen.includes(v)) return false;
        }
      }
      if (!q) return true;
      return normalizedColumns.some((col) =>
        String(rec.values?.[col.name] ?? '').toLowerCase().includes(q)
      );
    });
  }, [normalizedRecords, facets, facetSelections, searchQuery, normalizedColumns]);

  const sortedRecords = useMemo(() => {
    if (!sorts.length) return filteredRecords;
    const primary = sorts[0];
    const copy = [...filteredRecords];
    copy.sort((a, b) => {
      const cmp = compareCellValues(a.values?.[primary.column], b.values?.[primary.column]);
      return primary.direction === 'desc' ? -cmp : cmp;
    });
    return copy.map((rec, idx) => ({...rec, row_number: idx + 1}));
  }, [filteredRecords, sorts]);

  const totalPages = pagination ? Math.max(1, Math.ceil(sortedRecords.length / pageSize)) : 1;
  const safePage = pagination ? Math.min(page, totalPages - 1) : 0;

  const visibleRows = useMemo(() => {
    if (!pagination) return sortedRecords;
    const start = safePage * pageSize;
    return sortedRecords.slice(start, start + pageSize);
  }, [sortedRecords, pagination, safePage, pageSize]);

  const safeActiveRowIndex =
    visibleRows.length > 0 ? Math.min(Math.max(0, activeRowIndex), visibleRows.length - 1) : 0;

  const gridCols = useMemo(
    () => orderedColumns(normalizedColumns, layout.gridColOrder, layout.gridVisibleCols),
    [normalizedColumns, layout.gridColOrder, layout.gridVisibleCols]
  );
  const formCols = useMemo(
    () => orderedColumns(normalizedColumns, layout.formColOrder, layout.formVisibleCols),
    [normalizedColumns, layout.formColOrder, layout.formVisibleCols]
  );

  const sharedFormLayout = useMemo(
    () => buildFormLayoutPlacements(formCols, layout.formFieldPrefs, viewportWidth, null, visibleRows),
    [formCols, layout.formFieldPrefs, viewportWidth, visibleRows]
  );

  const effectiveDisplayMode = resolveRecordPresentation(
    activeDisplayMode,
    isEditingRow,
    layout.hybridEditTarget
  );

  const dispatchDrawerInspect = useCallback(
    (rec, focusCol = null) => {
      if (!rec) return;
      onInspectRow?.(rec.__raw, rec.identity_token, focusCol);
      if (!inspectInShellDrawer || typeof window === 'undefined') return;
      if (!document?.querySelector?.('[data-cdeadmin-qa-key="project-shell-backdrop"]')) return;
      try {
        window.dispatchEvent(
          new CustomEvent('scratchrobin:inspect-right-drawer', {
            detail: {
              open: true,
              node: (
                <Box sx={{p: 1.5}}>
                  <Box component="h4" sx={{m: 0, mb: 1, fontSize: '0.82rem', fontWeight: 700}}>
                    {caption || gettext('Record')} #{rec.row_number}
                  </Box>
                  <Box component="dl" sx={{m: 0, display: 'grid', gap: 0.75}}>
                    {normalizedColumns.map((col) => (
                      <Box key={col.name}>
                        <Box component="dt" sx={{fontSize: '0.7rem', fontWeight: 700, color: 'text.secondary'}}>
                          {col.label}
                        </Box>
                        <Box
                          component="dd"
                          className="sr-bui-mono"
                          sx={{
                            m: 0,
                            fontSize: '0.78rem',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                          }}
                        >
                          {rec.values?.[col.name] == null
                            ? '<null>'
                            : typeof rec.values[col.name] === 'object'
                              ? JSON.stringify(rec.values[col.name], null, 2)
                              : String(rec.values[col.name])}
                        </Box>
                      </Box>
                    ))}
                  </Box>
                </Box>
              ),
            },
          })
        );
      } catch {
        // Non-DOM test environment.
      }
    },
    [onInspectRow, inspectInShellDrawer, caption, normalizedColumns]
  );

  const selectRowAtIndex = useCallback(
    (rIdx, colName) => {
      const clamped = Math.max(0, Math.min(rIdx, Math.max(0, visibleRows.length - 1)));
      setActiveRowIndex(clamped);
      if (colName) setActiveColName(colName);
      if (visibleRows[clamped] && (onInspectRow || inspectInShellDrawer)) {
        dispatchDrawerInspect(visibleRows[clamped], colName || null);
      }
    },
    [visibleRows, onInspectRow, inspectInShellDrawer, dispatchDrawerInspect]
  );

  const handleToggleColumnSort = useCallback((colName) => {
    setSorts((prev) => {
      const cur = prev.find((s) => s.column === colName);
      if (!cur) return [{column: colName, direction: 'asc'}];
      if (cur.direction === 'asc') return [{column: colName, direction: 'desc'}];
      return [];
    });
  }, []);

  const toggleBookmarkAtRow = useCallback(
    (rIdx) => {
      const globalIdx = safePage * pageSize + rIdx;
      setBookmarkedGlobals((prev) => {
        const next = new Set(prev);
        if (next.has(globalIdx)) next.delete(globalIdx);
        else next.add(globalIdx);
        return next;
      });
    },
    [safePage, pageSize]
  );

  const acceptCurrentRow = useCallback(() => {
    if (!editable || !isEditingRow || editingRowIndex == null || !rowDraft) {
      setIsEditingRow(false);
      setEditingRowIndex(null);
      setRowDraft(null);
      return;
    }
    const targetRec = visibleRows[editingRowIndex];
    if (targetRec && onChangeRows) {
      const updatedAll = rows.map((orig, idx) => {
        if (idx !== targetRec.__sourceIndex) return orig;
        if (orig && typeof orig === 'object' && orig.values) {
          return {...orig, values: {...orig.values, ...rowDraft}};
        }
        return {...(orig || {}), ...rowDraft};
      });
      onChangeRows(updatedAll);
    }
    setIsEditingRow(false);
    setEditingRowIndex(null);
    setRowDraft(null);
  }, [editable, isEditingRow, editingRowIndex, rowDraft, visibleRows, onChangeRows, rows]);

  const cancelRowDraft = useCallback(() => {
    setIsEditingRow(false);
    setEditingRowIndex(null);
    setRowDraft(null);
  }, []);

  const beginEditRow = useCallback(
    (rIdx) => {
      if (!editable) return;
      const rec = visibleRows[rIdx];
      if (!rec) return;
      setActiveRowIndex(rIdx);
      setEditingRowIndex(rIdx);
      setIsEditingRow(true);
      setRowDraft({...rec.values});
    },
    [editable, visibleRows]
  );

  const handleKeyboardCellNavigate = useCallback(
    (nextRowIdx, nextColName, pageAction) => {
      if (pageAction === 'first_record') {
        setPage(0);
        setActiveRowIndex(0);
        if (nextColName) setActiveColName(nextColName);
        pendingFocusRef.current = {rowIndex: 0, colName: nextColName || activeColName};
        return;
      }
      if (pageAction === 'last_record') {
        const lastIdx = Math.max(0, visibleRows.length - 1);
        setPage(totalPages - 1);
        setActiveRowIndex(lastIdx);
        if (nextColName) setActiveColName(nextColName);
        pendingFocusRef.current = {rowIndex: lastIdx, colName: nextColName || activeColName};
        return;
      }
      if (pageAction === 'next_page' && safePage < totalPages - 1) {
        setPage(safePage + 1);
        setActiveRowIndex(0);
        pendingFocusRef.current = {rowIndex: 0, colName: nextColName || activeColName};
        return;
      }
      if (pageAction === 'prev_page' && safePage > 0) {
        setPage(safePage - 1);
        setActiveRowIndex(0);
        pendingFocusRef.current = {rowIndex: 0, colName: nextColName || activeColName};
        return;
      }
      const clamped = Math.max(0, Math.min(nextRowIdx, Math.max(0, visibleRows.length - 1)));
      setActiveRowIndex(clamped);
      if (nextColName) setActiveColName(nextColName);
      pendingFocusRef.current = {rowIndex: clamped, colName: nextColName || activeColName};
    },
    [totalPages, visibleRows.length, safePage, activeColName]
  );

  useEffect(() => {
    const req = pendingFocusRef.current;
    if (!req || !containerRef.current) return;
    pendingFocusRef.current = null;
    const escCol = String(req.colName || '').replaceAll('"', '\\"');
    const el = containerRef.current.querySelector(
      `[data-grid-nav-cell="${req.rowIndex}:${escCol}"]`
    );
    if (el && typeof el.focus === 'function') {
      el.focus({preventScroll: false});
    }
  }, [activeRowIndex, activeColName, visibleRows]);

  const setColumnPref = useCallback((colName, patch) => {
    setLayout((prev) => ({
      ...prev,
      gridColPrefs: {
        ...prev.gridColPrefs,
        [colName]: {...(prev.gridColPrefs[colName] || {}), ...patch},
      },
    }));
  }, []);

  const gridSelection = useGridSelection({
    rows: visibleRows,
    gridColumns: gridCols,
    activeRowIndex: safeActiveRowIndex,
    activeColName,
    selectRowAtIndex,
    setActiveColName,
    tableName: caption || 'GRID_RESULT',
  });
  const {selectionSlice} = gridSelection;

  const resolveExportPayload = useCallback(() => {
    if (selectionSlice.hasMultiSelection) {
      const targetCols = selectionSlice.selectedColumns.map((c) => ({
        key: c.name,
        label: c.label || c.name,
      }));
      const sourceRows = selectionSlice.allRowsSelected
        ? sortedRecords
        : selectionSlice.slicedRows;
      const targetRows = sourceRows.map((r) => {
        const obj = {};
        for (const col of selectionSlice.selectedColumns) {
          obj[col.name] = r.values?.[col.name] ?? null;
        }
        return obj;
      });
      return {exportCols: targetCols, exportRows: targetRows};
    }
    if (selectionSlice.explicitSingleCell) {
      const targetCols = selectionSlice.selectedColumns.map((c) => ({
        key: c.name,
        label: c.label || c.name,
      }));
      const targetRows = selectionSlice.slicedRows.map((r) => r.values);
      return {exportCols: targetCols, exportRows: targetRows};
    }
    return {
      exportCols: gridCols.map((c) => ({key: c.name, label: c.label || c.name})),
      exportRows: sortedRecords.map((r) => r.values),
    };
  }, [selectionSlice, sortedRecords, gridCols]);

  const copyExport = useCallback(
    async (fmt = 'auto') => {
      if (fmt === 'auto' && !selectionSlice.hasMultiSelection) {
        const scalar = formatScalarForClipboard(selectionSlice.scalarValue);
        if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(scalar).catch(() => {});
        }
        return scalar;
      }
      const resolvedFmt = fmt === 'auto' ? 'tsv' : fmt;
      const {exportCols, exportRows} = resolveExportPayload();
      const text = serializeGridData(exportCols, exportRows, resolvedFmt, {
        newline: '\n',
      });
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text).catch(() => {});
      }
      return text;
    },
    [selectionSlice, resolveExportPayload]
  );

  const downloadExport = useCallback(
    (fmt = 'csv') => {
      const {exportCols, exportRows} = resolveExportPayload();
      const text = serializeGridData(exportCols, exportRows, fmt);
      const stem = String(caption || 'grid_export')
        .toLowerCase()
        .replace(/[^a-z0-9_.-]+/g, '_')
        .replace(/^_+|_+$/g, '') || 'grid_export';
      downloadGridExport(`${stem}.${fmt}`, text);
      return text;
    },
    [resolveExportPayload, caption]
  );

  const columnLabelsMap = useMemo(
    () => Object.fromEntries(normalizedColumns.map((c) => [c.name, c.label])),
    [normalizedColumns]
  );

  const model = {
    acceptCurrentRow,
    activeColName,
    activeRowIndex: safeActiveRowIndex,
    ariaLabel: ariaLabel || caption || gettext('Data Surface Grid'),
    qaKey,
    gridRole,
    emptyMessage,
    beginEditRow,
    bookmarkedGlobals,
    cancelRowDraft,
    currentRow: visibleRows[safeActiveRowIndex] || null,
    conversions: null,
    editingRowIndex,
    effectiveDisplayMode,
    formColumns: formCols,
    gridColumns: gridCols,
    gridSelection,
    gridViewportRef,
    handleKeyboardCellNavigate,
    handleToggleColumnSort,
    hostData: {
      editable,
      sorts,
      filters: [],
      window_offset: safePage * pageSize,
    },
    isEditingRow,
    layout,
    onCopySelection: (fmt) => copyExport(fmt),
    onOpenColumnDisplaySettings: (colName) => setFormatFieldName(colName),
    onOpenExportSelection: exportable ? () => downloadExport('csv') : null,
    openFormFieldContextMenu: (_ev, col) => setFormatFieldName(col?.name || null),
    openHeaderContextMenu: null,
    openMiniFormContextMenu: () => {},
    openRightDrawerWith: ({rowIndex, column}) => {
      if (visibleRows[rowIndex]) {
        dispatchDrawerInspect(visibleRows[rowIndex], column?.name || null);
      }
    },
    quickFindText: searchQuery,
    rowDraft,
    rows: visibleRows,
    selectRowAtIndex,
    setActiveColName,
    setColumnPickerOpen,
    setColumnPickerScope,
    setColumnPref,
    setRowDraft,
    setScrollRowRange,
    sharedFormLayout,
    tableName: caption || 'GRID_RESULT',
    toggleBookmarkAtRow,
    viewportWidth,
  };

  const showToolbar =
    Boolean(caption) ||
    searchable ||
    facets.length > 0 ||
    allowModeSwitch ||
    exportable ||
    selectionSlice.hasMultiSelection ||
    Boolean(toolbarLeading) ||
    Boolean(toolbarTrailing);

  return (
    <Box
      ref={containerRef}
      className="sr-bui-table-card"
      style={{
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        minHeight,
        ...(maxHeight ? {maxHeight} : {}),
        ...style,
      }}
    >
      {showToolbar && (
        <div
          className="sr-bui-toolbar"
          style={{
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 8,
            justifyContent: 'space-between',
          }}
        >
          <div style={{display: 'inline-flex', alignItems: 'center', flexWrap: 'wrap', gap: 8}}>
            {caption && <span className="sr-bui-toolbar-title">{caption}</span>}
            {toolbarLeading}
            {searchable && (
              <div style={{minWidth: 190, maxWidth: 260}}>
                <SearchField
                  aria-label={searchPlaceholder}
                  label=""
                  placeholder={searchPlaceholder}
                  value={searchQuery}
                  onChange={(val) => {
                    setSearchQuery(val);
                    setPage(0);
                  }}
                />
              </div>
            )}
            {facets.map((facet) => {
              const facetKey = facet.id || facet.column || facet.label;
              const chosen = facetSelections[facetKey] || [];
              const options =
                facet.options ||
                Array.from(
                  new Set(
                    normalizedRecords
                      .map((r) => String(r.values?.[facet.column || facet.id || facetKey] ?? ''))
                      .filter(Boolean)
                  )
                ).map((v) => ({value: v, label: v}));
              return (
                <BasePopover.Root key={facetKey}>
                  <BasePopover.Trigger
                    className="sr-bui-chip"
                    data-active={chosen.length > 0 ? 'true' : undefined}
                  >
                    <span>+ {facet.label}</span>
                    {chosen.length > 0 && (
                      <span className="sr-bui-pill" data-tone="info" style={{padding: '0 6px'}}>
                        {chosen.length}
                      </span>
                    )}
                  </BasePopover.Trigger>
                  <BasePopover.Portal>
                    <BasePopover.Positioner
                      sideOffset={5}
                      align="start"
                      style={{zIndex: 'var(--cde-layer-popover, 2400)'}}
                    >
                      <BasePopover.Popup className="sr-popover-popup" style={{minWidth: 190, padding: 8}}>
                        <div style={{display: 'flex', flexDirection: 'column', gap: 6}}>
                          {options.map((opt) => {
                            const val = String(opt.value);
                            return (
                              <Checkbox
                                key={val}
                                label={opt.label}
                                checked={chosen.includes(val)}
                                onChange={(checked) => {
                                  setFacetSelections((prev) => ({
                                    ...prev,
                                    [facetKey]: checked
                                      ? [...chosen, val]
                                      : chosen.filter((item) => item !== val),
                                  }));
                                  setPage(0);
                                }}
                              />
                            );
                          })}
                        </div>
                      </BasePopover.Popup>
                    </BasePopover.Positioner>
                  </BasePopover.Portal>
                </BasePopover.Root>
              );
            })}
          </div>

          <div style={{display: 'inline-flex', alignItems: 'center', flexWrap: 'wrap', gap: 6}}>
            {selectionSlice.hasMultiSelection && (
              <span
                className="sr-bui-pill"
                data-tone="info"
                data-cdeadmin-qa-key="unified-grid-selection-badge"
                style={{padding: '2px 8px', fontSize: '0.73rem'}}
              >
                {summarizeGridSelection(
                  selectionSlice,
                  safeActiveRowIndex,
                  activeColName,
                  safePage * pageSize
                )}
              </span>
            )}
            {exportable && sortedRecords.length > 0 && (
              <Stack direction="row" gap="compact">
                <Button size="small" intent="neutral" onClick={() => copyExport('csv')}>
                  {gettext('Copy CSV')}
                </Button>
                <Button size="small" intent="neutral" onClick={() => copyExport('tsv')}>
                  {gettext('Copy TSV')}
                </Button>
                <Button size="small" intent="neutral" onClick={() => copyExport('json')}>
                  {gettext('Copy JSON')}
                </Button>
                <Button size="small" intent="neutral" onClick={() => downloadExport('csv')}>
                  {gettext('Export CSV')}
                </Button>
              </Stack>
            )}
            {allowModeSwitch && (
              <div
                role="group"
                aria-label={gettext('Display presentation mode')}
                style={{
                  display: 'inline-flex',
                  border: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.28))',
                  borderRadius: 5,
                  overflow: 'hidden',
                }}
              >
                {[
                  {id: DISPLAY_MODES.GRID, text: gettext('Grid'), aria: gettext('Standard Grid')},
                  {id: DISPLAY_MODES.HYBRID, text: gettext('Hybrid'), aria: gettext('Hybrid Grid')},
                  {id: DISPLAY_MODES.MINI_FORMS, text: gettext('Mini'), aria: gettext('Mini-Forms')},
                  {id: DISPLAY_MODES.SINGLE_FORM, text: gettext('Form'), aria: gettext('Full-Form')},
                ].map((opt) => {
                  const active = activeDisplayMode === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      aria-label={opt.aria}
                      aria-pressed={active}
                      onClick={() => setDisplayMode(opt.id)}
                      style={{
                        border: 'none',
                        padding: '3px 8px',
                        fontSize: '0.72rem',
                        fontWeight: active ? 700 : 500,
                        cursor: 'pointer',
                        background: active ? 'var(--sr-accent, #0284c7)' : 'transparent',
                        color: active ? '#ffffff' : 'var(--sr-text-secondary, inherit)',
                      }}
                    >
                      {opt.text}
                    </button>
                  );
                })}
              </div>
            )}
            {toolbarTrailing}
          </div>
        </div>
      )}

      {activeDisplayMode === DISPLAY_MODES.SINGLE_FORM && visibleRows.length > 1 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 10px',
            borderBottom: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.2))',
            fontSize: '0.75rem',
          }}
        >
          <Button
            size="small"
            intent="neutral"
            aria-label={gettext('First record')}
            disabled={safeActiveRowIndex <= 0}
            onClick={() => selectRowAtIndex(0)}
          >
            |&lt;
          </Button>
          <Button
            size="small"
            intent="neutral"
            aria-label={gettext('Previous record')}
            disabled={safeActiveRowIndex <= 0}
            onClick={() => selectRowAtIndex(safeActiveRowIndex - 1)}
          >
            &lt;
          </Button>
          <span style={{fontWeight: 600}}>
            {gettext('Row %s of %s', safeActiveRowIndex + 1, visibleRows.length)}
          </span>
          <Button
            size="small"
            intent="neutral"
            aria-label={gettext('Next record')}
            disabled={safeActiveRowIndex >= visibleRows.length - 1}
            onClick={() => selectRowAtIndex(safeActiveRowIndex + 1)}
          >
            &gt;
          </Button>
          <Button
            size="small"
            intent="neutral"
            aria-label={gettext('Last record')}
            disabled={safeActiveRowIndex >= visibleRows.length - 1}
            onClick={() => selectRowAtIndex(visibleRows.length - 1)}
          >
            &gt;|
          </Button>
        </div>
      )}

      <div style={{display: 'flex', flexDirection: 'column', flex: 1, minHeight: 140, minWidth: 0}}>
        <RecordDataView model={model} />
      </div>

      {pagination && sortedRecords.length > 0 && (
        <GridNavigation
          page={safePage}
          pages={totalPages}
          endKnown
          canNext={safePage < totalPages - 1}
          onFirst={() => {
            setPage(0);
            setActiveRowIndex(0);
          }}
          onPrevious={() => {
            setPage(safePage - 1);
            setActiveRowIndex(0);
          }}
          onNext={() => {
            setPage(safePage + 1);
            setActiveRowIndex(0);
          }}
          onLast={() => {
            setPage(totalPages - 1);
            setActiveRowIndex(0);
          }}
        >
          <Select
            size="small"
            label={gettext('Rows per page')}
            value={String(pageSize)}
            options={PAGE_SIZE_OPTIONS}
            onChange={(nextVal) => {
              setPageSize(Number(nextVal) || 100);
              setPage(0);
            }}
            style={{minWidth: 110}}
          />
          <span style={{fontSize: '0.76rem', color: 'var(--sr-text-secondary)'}}>
            {gettext('%s rows in this result', sortedRecords.length)}
          </span>
        </GridNavigation>
      )}

      <ColumnOrderDialog
        open={columnPickerOpen}
        scope={columnPickerScope}
        allColumns={normalizedColumns}
        columnLabels={columnLabelsMap}
        visibleNames={
          columnPickerScope === 'form' ? layout.formVisibleCols : layout.gridVisibleCols
        }
        orderNames={columnPickerScope === 'form' ? layout.formColOrder : layout.gridColOrder}
        onClose={() => setColumnPickerOpen(false)}
        onApply={(order, visible) => {
          setLayout((prev) =>
            columnPickerScope === 'form'
              ? {...prev, formColOrder: order, formVisibleCols: visible}
              : {...prev, gridColOrder: order, gridVisibleCols: visible}
          );
          setColumnPickerOpen(false);
        }}
      />
      {formatFieldName && (
        <ColumnDisplaySettingsDialog
          open={Boolean(formatFieldName)}
          columns={normalizedColumns}
          initialColumnName={formatFieldName}
          layout={layout}
          onClose={() => setFormatFieldName(null)}
          onApplyLayout={(nextLayout) => setLayout(nextLayout)}
        />
      )}
    </Box>
  );
}

UnifiedDataGrid.propTypes = {
  columns: PropTypes.array,
  rows: PropTypes.array,
  rowKeyGetter: PropTypes.func,
  caption: PropTypes.string,
  ariaLabel: PropTypes.string,
  qaKey: PropTypes.string,
  gridRole: PropTypes.oneOf(['grid', 'table']),
  emptyMessage: PropTypes.node,
  readOnly: PropTypes.bool,
  editable: PropTypes.bool,
  onChangeRows: PropTypes.func,
  defaultDisplayMode: PropTypes.string,
  displayMode: PropTypes.string,
  onDisplayModeChange: PropTypes.func,
  allowModeSwitch: PropTypes.bool,
  searchable: PropTypes.bool,
  searchPlaceholder: PropTypes.string,
  facets: PropTypes.array,
  pagination: PropTypes.bool,
  defaultPageSize: PropTypes.number,
  exportable: PropTypes.bool,
  onInspectRow: PropTypes.func,
  inspectInShellDrawer: PropTypes.bool,
  toolbarLeading: PropTypes.node,
  toolbarTrailing: PropTypes.node,
  minHeight: PropTypes.number,
  maxHeight: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  style: PropTypes.object,
};
