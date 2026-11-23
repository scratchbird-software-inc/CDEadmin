/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {EmptyState} from '../feedback/EmptyState';
import {
  isGridCellSelected,
  isGridColumnSelected,
  isGridRowSelected,
  makeCellKey,
  selectDragCellRangeState,
  selectDragColumnRangeState,
  selectDragRowRangeState,
  useGridSelection,
} from '../data/gridSelection';
import {AdaptiveRecordFormCard} from './RecordForm';
import {
  FIELD_FONTS,
  DISPLAY_MODES,
  formatCellValue,
  inferColumnMeta,
  isComplexOrOversizedCell,
  serializeValueForEdit,
} from './dataEditSurfaceHelpers';

const DEFAULT_COL_WIDTH = 156;
const GUTTER_WIDTH = 62;

/** Shared record viewport. Controllers own sessions, drafts, authorization and
 * provider effects; this component owns the existing Data Viewer presentation
 * and unified 2D spreadsheet-grade cell / row / column / all selection. */
export default function RecordDataView({model}) {
  const {
    acceptCurrentRow,
    activeColName,
    activeRowIndex,
    beginEditRow,
    bookmarkedGlobals,
    cancelRowDraft,
    currentRow,
    conversions,
    editingRowIndex,
    effectiveDisplayMode,
    formColumns,
    gridColumns,
    gridViewportRef,
    handleKeyboardCellNavigate,
    handleToggleColumnSort,
    hostData,
    isEditingRow,
    layout,
    openFormFieldContextMenu,
    openHeaderContextMenu,
    openMiniFormContextMenu,
    openRightDrawerWith,
    quickFindText,
    rowDraft,
    rows,
    selectRowAtIndex,
    setActiveColName,
    setColumnPickerOpen,
    setColumnPickerScope,
    setColumnPref,
    setRowDraft,
    setScrollRowRange,
    sharedFormLayout,
    toggleBookmarkAtRow,
    viewportWidth,
  } = model;

  const fallbackGridSelection = useGridSelection({
    rows,
    gridColumns,
    activeRowIndex,
    activeColName,
    selectRowAtIndex,
    setActiveColName,
    tableName: model.tableName || 'RESULT_SET',
  });
  const activeGridSelection = model.gridSelection || fallbackGridSelection;
  const {selection, selectionSlice} = activeGridSelection;

  const gridRootRef = useRef(null);
  const dragStateRef = useRef(null);
  const suppressNextClickRef = useRef(false);
  const [gridMenu, setGridMenu] = useState(null); // {x, y, rowIndex, colName}

  useEffect(() => {
    const handleGlobalMouseUp = () => {
      if (dragStateRef.current) {
        const hadMove = dragStateRef.current.moved;
        dragStateRef.current = null;
        if (hadMove) {
          setTimeout(() => {
            suppressNextClickRef.current = false;
          }, 0);
        }
      }
    };
    const handleGlobalClick = () => {
      setGridMenu(null);
    };
    window.addEventListener('mouseup', handleGlobalMouseUp);
    window.addEventListener('click', handleGlobalClick);
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp);
      window.removeEventListener('click', handleGlobalClick);
    };
  }, []);

  const focusGridCellDom = (rIdx, cName) => {
    const root = gridRootRef.current;
    if (!root || !cName) return;
    const escCol = String(cName).replaceAll('"', '\\"');
    const el = root.querySelector(`[data-grid-nav-cell="${rIdx}:${escCol}"]`);
    if (el && typeof el.focus === 'function') {
      el.focus({preventScroll: true});
    }
  };

  const invokeCopy = (fmt = 'auto', options = {}) => {
    if (typeof model.onCopySelection === 'function') {
      return model.onCopySelection(fmt, options);
    }
    return activeGridSelection.copySelectionToClipboard(fmt, options);
  };

  const renderStandardGridRow = (row, rIdx) => {
    const isCurrent = rIdx === activeRowIndex;
    const isRowSelected = isGridRowSelected(selection, rIdx);
    const isRowEdit =
      isEditingRow && (editingRowIndex ?? activeRowIndex) === rIdx;
    const stageMarker =
      row.stage_state === 'inserted'
        ? '+'
        : row.stage_state === 'updated'
          ? '✎'
          : row.stage_state === 'deleted'
            ? '−'
            : '';

    let pinnedLeftAcc = GUTTER_WIDTH;

    return (
      <div
        key={row.identity_token || `r-${rIdx}`}
        role="row"
        data-surface-row-idx={rIdx}
        aria-selected={isRowSelected || isCurrent}
        onClick={() => selectRowAtIndex(rIdx)}
        style={{
          display: 'flex',
          alignItems: 'stretch',
          minWidth: 'max-content',
          borderBottom:
            '1px solid var(--sr-border-subtle, rgba(128,128,128,0.18))',
          background:
            row.stage_state === 'deleted'
              ? 'rgba(220, 38, 38, 0.08)'
              : isRowSelected
                ? 'var(--sr-grid-row-selected, rgba(2,132,199,0.16))'
                : isCurrent
                  ? 'var(--sr-surface-selected, rgba(2,132,199,0.09))'
                  : 'transparent',
          textDecoration:
            row.stage_state === 'deleted' ? 'line-through' : 'none',
        }}
      >
        {/* Left Row Number Gutter — click/Shift+click/Ctrl+click/drag selects full row(s); double-click toggles bookmark */}
        <div
          role="rowheader"
          data-grid-row-select={rIdx}
          data-row-selected={isRowSelected ? 'true' : undefined}
          aria-selected={isRowSelected || undefined}
          onMouseDown={(ev) => {
            if (ev.button !== 0) return;
            dragStateRef.current = {
              kind: 'row',
              startRow: rIdx,
              baseRows:
                ev.ctrlKey || ev.metaKey ? [...(selection.rows || [])] : null,
              preservedCols:
                ev.ctrlKey || ev.metaKey ? [...(selection.cols || [])] : [],
              moved: false,
            };
          }}
          onMouseEnter={() => {
            const drag = dragStateRef.current;
            if (!drag || drag.kind !== 'row') return;
            if (drag.startRow === rIdx && !drag.moved) return;
            drag.moved = true;
            suppressNextClickRef.current = true;
            activeGridSelection.setSelection((prev) =>
              selectDragRowRangeState(
                prev,
                drag.startRow,
                rIdx,
                rows.length,
                drag.baseRows,
                drag.preservedCols
              )
            );
            selectRowAtIndex(rIdx, undefined, {preserveSelection: true});
          }}
          onClick={(ev) => {
            ev.stopPropagation();
            if (suppressNextClickRef.current) {
              suppressNextClickRef.current = false;
              return;
            }
            activeGridSelection.handleRowHeaderClick(rIdx, ev);
            focusGridCellDom(rIdx, activeColName || gridColumns[0]?.name);
          }}
          onDoubleClick={(ev) => {
            ev.stopPropagation();
            toggleBookmarkAtRow(rIdx);
          }}
          onContextMenu={(ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            if (!isRowSelected) {
              activeGridSelection.handleRowHeaderClick(rIdx, {});
            }
            setGridMenu({
              x: ev.clientX,
              y: ev.clientY,
              rowIndex: rIdx,
              colName: activeColName || gridColumns[0]?.name || '',
            });
          }}
          title={gettext(
            'Click to select row · Shift/Ctrl+Click for multiple rows · Double-click to toggle bookmark'
          )}
          style={{
            position: 'sticky',
            left: 0,
            zIndex: 3,
            width: GUTTER_WIDTH,
            flex: `0 0 ${GUTTER_WIDTH}px`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 6px',
            fontSize: '0.74rem',
            fontWeight: isRowSelected || isCurrent ? 700 : 500,
            color: isRowSelected
              ? '#ffffff'
              : 'var(--sr-text-muted, #64748b)',
            background: isRowSelected
              ? 'var(--sr-accent, #0284c7)'
              : 'var(--sr-surface-subtle, #f1f5f9)',
            borderRight:
              '1px solid var(--sr-border-default, rgba(128,128,128,0.28))',
            cursor: 'pointer',
            userSelect: 'none',
          }}
        >
          <span>
            {isCurrent ? '▶' : stageMarker}
            {bookmarkedGlobals.has((hostData?.window_offset || 0) + rIdx) && (
              <span
                data-cdeadmin-qa-key={`grid-bookmark-badge-${rIdx}`}
                style={{
                  marginLeft: 2,
                  padding: '0 4px',
                  borderRadius: 999,
                  background: '#f59e0b',
                  color: '#ffffff',
                  fontWeight: 800,
                  fontSize: '0.66rem',
                }}
              >
                !
              </span>
            )}
          </span>
          <span>{row.row_number}</span>
        </div>

        {gridColumns.map((col) => {
          const nativeMeta = inferColumnMeta(col);
          const cPrefs = {
            ...hostData?.field_type_defaults?.[nativeMeta.clientType],
            ...layout.gridColPrefs[col.name],
            font:
              layout.gridColPrefs[col.name]?.font ||
              hostData?.field_type_defaults?.[nativeMeta.clientType]?.font,
            hAlign:
              layout.gridColPrefs[col.name]?.hAlign ||
              hostData?.field_type_defaults?.[nativeMeta.clientType]?.hAlign,
          };
          const w = cPrefs.width || DEFAULT_COL_WIDTH;
          const hAlign = cPrefs.hAlign || nativeMeta.defaultAlignment || 'left';
          const vAlign = cPrefs.vAlign || 'middle';
          const wrapMode = cPrefs.wrapMode || 'none';
          const isPinned = Boolean(cPrefs.pinned);
          const stickyLeft = isPinned ? pinnedLeftAcc : undefined;
          if (isPinned) pinnedLeftAcc += w;

          const isActiveCell = isCurrent && activeColName === col.name;
          const isSelectedCell = isGridCellSelected(selection, rIdx, col.name);
          const showSelectionFill =
            isSelectedCell &&
            (selectionSlice.hasMultiSelection ||
              Boolean(selectionSlice.explicitSingleCell));

          const nativeValue =
            isRowEdit &&
            rowDraft &&
            Object.prototype.hasOwnProperty.call(rowDraft, col.name)
              ? rowDraft[col.name]
              : row.values?.[col.name];
          const rawVal =
            conversions?.displayValue(col.name, nativeValue) ?? nativeValue;
          const colMeta =
            conversions?.pairFor(col.name) &&
            (typeof rawVal === 'string' || rawVal == null)
              ? {...nativeMeta, clientType: 'text', isComplex: false}
              : nativeMeta;
          const formatted = formatCellValue(rawVal, colMeta, {
            booleanFormat: layout.booleanFormat,
            localeDateFormat: layout.localeDateFormat,
            colPrefs: cPrefs,
          });
          const canEditCell =
            isRowEdit &&
            effectiveDisplayMode === DISPLAY_MODES.GRID &&
            (row.stage_state === 'inserted'
              ? col.insertable !== false
              : col.editable !== false) &&
            !isComplexOrOversizedCell(rawVal, colMeta, cPrefs);

          const quickMatch =
            quickFindText &&
            formatted.text
              .toLowerCase()
              .includes(quickFindText.trim().toLowerCase());

          let cellBg;
          if (quickMatch) {
            cellBg = 'rgba(250, 204, 21, 0.24)';
          } else if (showSelectionFill && isPinned) {
            cellBg =
              'linear-gradient(rgba(2, 132, 199, 0.20), rgba(2, 132, 199, 0.20)), var(--sr-surface-card, #ffffff)';
          } else if (showSelectionFill) {
            cellBg = 'var(--sr-grid-cell-selected, rgba(2, 132, 199, 0.18))';
          } else if (isPinned) {
            cellBg = 'var(--sr-surface-card)';
          }

          return (
            <div
              key={col.name}
              role={model.gridRole === 'table' ? 'cell' : 'gridcell'}
              data-grid-nav-cell={`${rIdx}:${col.name}`}
              data-cell-selected={isSelectedCell ? 'true' : undefined}
              aria-selected={isSelectedCell || isActiveCell || undefined}
              tabIndex={isActiveCell ? 0 : -1}
              onMouseDown={(ev) => {
                if (ev.button !== 0 || canEditCell) return;
                const tgt = ev.target;
                if (
                  tgt instanceof HTMLInputElement ||
                  tgt instanceof HTMLTextAreaElement ||
                  tgt instanceof HTMLButtonElement
                ) {
                  return;
                }
                const additive = Boolean(ev.ctrlKey || ev.metaKey);
                let baseCells = null;
                if (additive) {
                  const curCells = [...(selection.cells || [])];
                  if (
                    !curCells.length &&
                    !selection.all &&
                    !selection.rows.length &&
                    !selection.cols.length &&
                    activeColName
                  ) {
                    curCells.push(makeCellKey(activeRowIndex || 0, activeColName));
                  }
                  baseCells = curCells;
                }
                dragStateRef.current = {
                  kind: 'cell',
                  startRow: rIdx,
                  startCol: col.name,
                  baseCells,
                  moved: false,
                };
              }}
              onMouseEnter={() => {
                const drag = dragStateRef.current;
                if (!drag || drag.kind !== 'cell') return;
                if (
                  drag.startRow === rIdx &&
                  drag.startCol === col.name &&
                  !drag.moved
                ) {
                  return;
                }
                drag.moved = true;
                suppressNextClickRef.current = true;
                activeGridSelection.setSelection((prev) =>
                  selectDragCellRangeState(
                    prev,
                    drag.startRow,
                    drag.startCol,
                    rIdx,
                    col.name,
                    gridColumns,
                    drag.baseCells
                  )
                );
                selectRowAtIndex(rIdx, col.name, {preserveSelection: true});
              }}
              onClick={(ev) => {
                ev.stopPropagation();
                if (suppressNextClickRef.current) {
                  suppressNextClickRef.current = false;
                  return;
                }
                activeGridSelection.handleCellClick(rIdx, col.name, ev);
                if (!canEditCell && typeof ev.currentTarget.focus === 'function') {
                  ev.currentTarget.focus({preventScroll: true});
                }
              }}
              onContextMenu={(ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                if (!isSelectedCell) {
                  activeGridSelection.handleCellClick(rIdx, col.name, {});
                }
                setGridMenu({
                  x: ev.clientX,
                  y: ev.clientY,
                  rowIndex: rIdx,
                  colName: col.name,
                });
              }}
              onDoubleClick={(ev) => {
                ev.stopPropagation();
                if (formatted.isComplex) {
                  openRightDrawerWith({
                    mode: 'complex_value',
                    rowIndex: rIdx,
                    column: col,
                  });
                } else if (hostData?.editable) {
                  beginEditRow(rIdx);
                  setActiveColName(col.name);
                }
              }}
              onKeyDown={(ev) => {
                const colIdx = gridColumns.findIndex(
                  (c) => c.name === col.name
                );
                const lastColIdx = gridColumns.length - 1;
                const isTextInput =
                  ev.target instanceof HTMLInputElement ||
                  ev.target instanceof HTMLTextAreaElement ||
                  Boolean(ev.target?.isContentEditable);

                if (
                  ev.key === 'Tab' &&
                  !ev.altKey &&
                  !ev.ctrlKey &&
                  !ev.metaKey
                ) {
                  ev.preventDefault();
                  if (!ev.shiftKey) {
                    if (colIdx < lastColIdx) {
                      const nextC = gridColumns[colIdx + 1].name;
                      activeGridSelection.selectSingleCell(rIdx, nextC);
                      handleKeyboardCellNavigate(rIdx, nextC, null, 'grid');
                    } else {
                      const nextC = gridColumns[0]?.name || col.name;
                      activeGridSelection.selectSingleCell(rIdx + 1, nextC);
                      handleKeyboardCellNavigate(rIdx + 1, nextC, null, 'grid');
                    }
                  } else if (colIdx > 0) {
                    const nextC = gridColumns[colIdx - 1].name;
                    activeGridSelection.selectSingleCell(rIdx, nextC);
                    handleKeyboardCellNavigate(rIdx, nextC, null, 'grid');
                  } else {
                    const nextC = gridColumns[lastColIdx]?.name || col.name;
                    activeGridSelection.selectSingleCell(
                      Math.max(0, rIdx - 1),
                      nextC
                    );
                    handleKeyboardCellNavigate(rIdx - 1, nextC, null, 'grid');
                  }
                  return;
                }

                if (canEditCell || isTextInput) {
                  if (ev.key === 'Escape') {
                    ev.preventDefault();
                    cancelRowDraft();
                  } else if (ev.key === 'Enter') {
                    ev.preventDefault();
                    acceptCurrentRow();
                  } else if (ev.key === 'ArrowDown') {
                    ev.preventDefault();
                    handleKeyboardCellNavigate(rIdx + 1, col.name, null, 'grid');
                  } else if (ev.key === 'ArrowUp') {
                    ev.preventDefault();
                    handleKeyboardCellNavigate(rIdx - 1, col.name, null, 'grid');
                  }
                  return;
                }

                // Grid-level Selection & Copy Shortcuts
                if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'a') {
                  ev.preventDefault();
                  activeGridSelection.selectAll();
                  return;
                }
                if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'c') {
                  ev.preventDefault();
                  invokeCopy(ev.shiftKey ? 'csv' : 'auto');
                  return;
                }
                if (
                  ev.key === ' ' &&
                  ev.shiftKey &&
                  !ev.ctrlKey &&
                  !ev.metaKey
                ) {
                  ev.preventDefault();
                  activeGridSelection.handleRowHeaderClick(rIdx, {});
                  return;
                }
                if (ev.key === ' ' && (ev.ctrlKey || ev.metaKey)) {
                  ev.preventDefault();
                  if (ev.shiftKey) {
                    activeGridSelection.selectAll();
                  } else {
                    activeGridSelection.handleColumnSelectClick(col.name, {});
                  }
                  return;
                }
                if (ev.key === 'Escape' && selectionSlice.hasMultiSelection) {
                  ev.preventDefault();
                  activeGridSelection.clearSelection();
                  return;
                }

                // Shift+Arrow / Shift+Home / Shift+End extends range selection
                if (ev.shiftKey && !ev.ctrlKey && !ev.metaKey) {
                  if (ev.key === 'ArrowDown') {
                    ev.preventDefault();
                    const nextR = Math.min(rows.length - 1, rIdx + 1);
                    activeGridSelection.extendCellSelectionTo(nextR, col.name);
                    handleKeyboardCellNavigate(nextR, col.name, null, 'grid', {
                      preserveSelection: true,
                    });
                    focusGridCellDom(nextR, col.name);
                    return;
                  }
                  if (ev.key === 'ArrowUp') {
                    ev.preventDefault();
                    const nextR = Math.max(0, rIdx - 1);
                    activeGridSelection.extendCellSelectionTo(nextR, col.name);
                    handleKeyboardCellNavigate(nextR, col.name, null, 'grid', {
                      preserveSelection: true,
                    });
                    focusGridCellDom(nextR, col.name);
                    return;
                  }
                  if (ev.key === 'ArrowRight') {
                    ev.preventDefault();
                    const nextC =
                      colIdx < lastColIdx
                        ? gridColumns[colIdx + 1].name
                        : col.name;
                    activeGridSelection.extendCellSelectionTo(rIdx, nextC);
                    handleKeyboardCellNavigate(rIdx, nextC, null, 'grid', {
                      preserveSelection: true,
                    });
                    focusGridCellDom(rIdx, nextC);
                    return;
                  }
                  if (ev.key === 'ArrowLeft') {
                    ev.preventDefault();
                    const nextC =
                      colIdx > 0 ? gridColumns[colIdx - 1].name : col.name;
                    activeGridSelection.extendCellSelectionTo(rIdx, nextC);
                    handleKeyboardCellNavigate(rIdx, nextC, null, 'grid', {
                      preserveSelection: true,
                    });
                    focusGridCellDom(rIdx, nextC);
                    return;
                  }
                  if (ev.key === 'Home') {
                    ev.preventDefault();
                    const firstC = gridColumns[0]?.name || col.name;
                    activeGridSelection.extendCellSelectionTo(rIdx, firstC);
                    handleKeyboardCellNavigate(rIdx, firstC, null, 'grid', {
                      preserveSelection: true,
                    });
                    focusGridCellDom(rIdx, firstC);
                    return;
                  }
                  if (ev.key === 'End') {
                    ev.preventDefault();
                    const endC = gridColumns[lastColIdx]?.name || col.name;
                    activeGridSelection.extendCellSelectionTo(rIdx, endC);
                    handleKeyboardCellNavigate(rIdx, endC, null, 'grid', {
                      preserveSelection: true,
                    });
                    focusGridCellDom(rIdx, endC);
                    return;
                  }
                }

                if (ev.key === 'ArrowDown') {
                  ev.preventDefault();
                  activeGridSelection.selectSingleCell(
                    Math.min(rows.length - 1, rIdx + 1),
                    col.name
                  );
                  handleKeyboardCellNavigate(rIdx + 1, col.name, null, 'grid');
                } else if (ev.key === 'ArrowUp') {
                  ev.preventDefault();
                  activeGridSelection.selectSingleCell(
                    Math.max(0, rIdx - 1),
                    col.name
                  );
                  handleKeyboardCellNavigate(rIdx - 1, col.name, null, 'grid');
                } else if (ev.key === 'ArrowRight') {
                  ev.preventDefault();
                  if (colIdx < lastColIdx) {
                    const nextC = gridColumns[colIdx + 1].name;
                    activeGridSelection.selectSingleCell(rIdx, nextC);
                    handleKeyboardCellNavigate(rIdx, nextC, null, 'grid');
                  } else {
                    const nextC = gridColumns[0]?.name || col.name;
                    activeGridSelection.selectSingleCell(
                      Math.min(rows.length - 1, rIdx + 1),
                      nextC
                    );
                    handleKeyboardCellNavigate(rIdx + 1, nextC, null, 'grid');
                  }
                } else if (ev.key === 'ArrowLeft') {
                  ev.preventDefault();
                  if (colIdx > 0) {
                    const nextC = gridColumns[colIdx - 1].name;
                    activeGridSelection.selectSingleCell(rIdx, nextC);
                    handleKeyboardCellNavigate(rIdx, nextC, null, 'grid');
                  } else {
                    const nextC = gridColumns[lastColIdx]?.name || col.name;
                    activeGridSelection.selectSingleCell(
                      Math.max(0, rIdx - 1),
                      nextC
                    );
                    handleKeyboardCellNavigate(rIdx - 1, nextC, null, 'grid');
                  }
                } else if (ev.key === 'PageDown') {
                  ev.preventDefault();
                  handleKeyboardCellNavigate(
                    rIdx,
                    col.name,
                    'next_page',
                    'grid'
                  );
                } else if (ev.key === 'PageUp') {
                  ev.preventDefault();
                  handleKeyboardCellNavigate(
                    rIdx,
                    col.name,
                    'prev_page',
                    'grid'
                  );
                } else if (ev.key === 'Home') {
                  ev.preventDefault();
                  const firstC = gridColumns[0]?.name || col.name;
                  if (ev.ctrlKey || ev.metaKey) {
                    activeGridSelection.selectSingleCell(0, firstC);
                    handleKeyboardCellNavigate(
                      0,
                      firstC,
                      'first_record',
                      'grid'
                    );
                  } else {
                    activeGridSelection.selectSingleCell(rIdx, firstC);
                    handleKeyboardCellNavigate(rIdx, firstC, null, 'grid');
                  }
                } else if (ev.key === 'End') {
                  ev.preventDefault();
                  const endC = gridColumns[lastColIdx]?.name || col.name;
                  if (ev.ctrlKey || ev.metaKey) {
                    activeGridSelection.selectSingleCell(
                      Math.max(0, rows.length - 1),
                      endC
                    );
                    handleKeyboardCellNavigate(
                      rows.length - 1,
                      endC,
                      'last_record',
                      'grid'
                    );
                  } else {
                    activeGridSelection.selectSingleCell(rIdx, endC);
                    handleKeyboardCellNavigate(rIdx, endC, null, 'grid');
                  }
                } else if (
                  (ev.ctrlKey || ev.metaKey) &&
                  ev.key.toLowerCase() === 'b'
                ) {
                  ev.preventDefault();
                  toggleBookmarkAtRow(rIdx);
                } else if (ev.key === 'Enter' || ev.key === 'F2') {
                  ev.preventDefault();
                  beginEditRow(rIdx);
                }
              }}
              style={{
                width: w,
                flex: `0 0 ${w}px`,
                minHeight: 28,
                padding: canEditCell ? '1px 2px' : '4px 8px',
                display: 'flex',
                alignItems:
                  vAlign === 'top'
                    ? 'flex-start'
                    : vAlign === 'bottom'
                      ? 'flex-end'
                      : 'center',
                justifyContent:
                  hAlign === 'right'
                    ? 'flex-end'
                    : hAlign === 'center'
                      ? 'center'
                      : 'flex-start',
                textAlign: hAlign,
                fontFamily: FIELD_FONTS[cPrefs.font],
                borderRight:
                  '1px solid var(--sr-border-subtle, rgba(128,128,128,0.16))',
                outline: isActiveCell
                  ? '2px solid var(--sr-accent, #0284c7)'
                  : 'none',
                outlineOffset: -2,
                position: isPinned ? 'sticky' : 'relative',
                left: stickyLeft,
                zIndex: isPinned ? 2 : 1,
                background: cellBg,
                userSelect: canEditCell ? 'text' : 'none',
                overflow: 'hidden',
              }}
            >
              {typeof col.render === 'function' ? (
                <div
                  onClick={(ev) => ev.stopPropagation()}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: 4,
                    fontSize: '0.8125rem',
                  }}
                >
                  {col.render(rawVal, row.__raw || row, rIdx)}
                </div>
              ) : formatted.isComplex ? (
                <button
                  type="button"
                  className="sr-btn"
                  aria-label={`${col.name} [...]`}
                  style={{minHeight: 20, padding: '0 7px', fontSize: '0.73rem'}}
                  onClick={(ev) => {
                    ev.stopPropagation();
                    selectRowAtIndex(rIdx, col.name);
                    openRightDrawerWith({
                      mode: 'complex_value',
                      rowIndex: rIdx,
                      column: col,
                    });
                  }}
                >
                  [...]
                </button>
              ) : canEditCell ? (
                <input
                  type="text"
                  autoFocus={isActiveCell}
                  aria-label={`${col.name} cell editor`}
                  value={
                    rawVal === null || rawVal === undefined
                      ? ''
                      : serializeValueForEdit(rawVal)
                  }
                  placeholder={rawVal === null ? '<null>' : ''}
                  onChange={(ev) =>
                    setRowDraft((prev) => ({
                      ...(prev || {}),
                      [col.name]: ev.target.value,
                    }))
                  }
                  style={{
                    width: '100%',
                    height: 24,
                    padding: '0 5px',
                    border: 'none',
                    outline: 'none',
                    background: 'var(--sr-surface-card)',
                    color: 'inherit',
                    textAlign: hAlign,
                    fontSize: '0.8125rem',
                  }}
                />
              ) : (
                <span
                  style={{
                    width: '100%',
                    fontSize: '0.8125rem',
                    color: formatted.isNull
                      ? 'var(--sr-text-muted, #64748b)'
                      : 'inherit',
                    fontStyle: formatted.isNull ? 'italic' : 'normal',
                    whiteSpace: wrapMode === 'none' ? 'nowrap' : 'normal',
                    overflow: 'hidden',
                    textOverflow: wrapMode === 'none' ? 'ellipsis' : 'clip',
                    display: wrapMode === 'clamp' ? '-webkit-box' : 'block',
                    WebkitLineClamp: wrapMode === 'clamp' ? 3 : undefined,
                    WebkitBoxOrient:
                      wrapMode === 'clamp' ? 'vertical' : undefined,
                    wordBreak: wrapMode !== 'none' ? 'break-word' : undefined,
                  }}
                >
                  {formatted.text}
                </span>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  const renderDataView = () => {
    if (effectiveDisplayMode === DISPLAY_MODES.SINGLE_FORM) {
      if (!currentRow) {
        return <EmptyState message={gettext('No rows returned.')} />;
      }
      const isRowEdit =
        isEditingRow && (editingRowIndex ?? activeRowIndex) === activeRowIndex;
      return (
        <AdaptiveRecordFormCard
          row={currentRow}
          rowIndex={activeRowIndex}
          isCurrent
          isEditing={isRowEdit}
          isBookmarked={bookmarkedGlobals.has(
            (hostData?.window_offset || 0) + activeRowIndex
          )}
          draftValues={isRowEdit ? rowDraft : null}
          columns={formColumns}
          formLayout={sharedFormLayout}
          formFieldPrefs={layout.formFieldPrefs}
          fieldTypeDefaults={hostData?.field_type_defaults}
          conversions={conversions}
          booleanFormat={layout.booleanFormat}
          localeDateFormat={layout.localeDateFormat}
          fullArea
          totalRowsInPage={rows.length}
          onSelectRow={selectRowAtIndex}
          onFocusField={setActiveColName}
          onNavigateFormField={(nextRowIdx, nextCol, action) =>
            handleKeyboardCellNavigate(nextRowIdx, nextCol, action, 'form')
          }
          onToggleBookmark={toggleBookmarkAtRow}
          onFieldChange={(cName, val) =>
            setRowDraft((prev) => ({...(prev || {}), [cName]: val}))
          }
          onOpenComplexInDrawer={(rIdx, col) =>
            openRightDrawerWith({
              mode: 'complex_value',
              rowIndex: rIdx,
              column: col,
            })
          }
          onFormContextMenu={openMiniFormContextMenu}
          onFieldContextMenu={openFormFieldContextMenu}
        />
      );
    }

    if (effectiveDisplayMode === DISPLAY_MODES.MINI_FORMS) {
      if (!rows.length) {
        return <EmptyState message={gettext('No rows returned.')} />;
      }
      return (
        <ScratchScrollArea
          orientation="vertical"
          fillViewport
          style={{flex: 1, minHeight: 0}}
        >
          <div data-cdeadmin-qa-key="data-surface-mini-forms-list">
            {rows.map((row, rIdx) => {
              const isRowEdit =
                isEditingRow && (editingRowIndex ?? activeRowIndex) === rIdx;
              return (
                <div
                  key={row.identity_token || `mf-${rIdx}`}
                  data-surface-row-idx={rIdx}
                >
                  <AdaptiveRecordFormCard
                    row={row}
                    rowIndex={rIdx}
                    isCurrent={rIdx === activeRowIndex}
                    isEditing={isRowEdit}
                    isBookmarked={bookmarkedGlobals.has(
                      (hostData?.window_offset || 0) + rIdx
                    )}
                    draftValues={isRowEdit ? rowDraft : null}
                    columns={formColumns}
                    formLayout={sharedFormLayout}
                    formFieldPrefs={layout.formFieldPrefs}
                    fieldTypeDefaults={hostData?.field_type_defaults}
                    conversions={conversions}
                    booleanFormat={layout.booleanFormat}
                    localeDateFormat={layout.localeDateFormat}
                    totalRowsInPage={rows.length}
                    onSelectRow={selectRowAtIndex}
                    onFocusField={setActiveColName}
                    onNavigateFormField={(nextRowIdx, nextCol, action) =>
                      handleKeyboardCellNavigate(
                        nextRowIdx,
                        nextCol,
                        action,
                        'form'
                      )
                    }
                    onToggleBookmark={toggleBookmarkAtRow}
                    onFieldChange={(cName, val) =>
                      setRowDraft((prev) => ({...(prev || {}), [cName]: val}))
                    }
                    onOpenComplexInDrawer={(idx, col) =>
                      openRightDrawerWith({
                        mode: 'complex_value',
                        rowIndex: idx,
                        column: col,
                      })
                    }
                    onFormContextMenu={openMiniFormContextMenu}
                    onFieldContextMenu={openFormFieldContextMenu}
                  />
                </div>
              );
            })}
          </div>
        </ScratchScrollArea>
      );
    }

    // Standard Grid `(a)` & Hybrid `(c)`
    let headerPinnedAcc = GUTTER_WIDTH;
    return (
      <ScratchScrollArea
        orientation="both"
        fillViewport
        viewportRef={gridViewportRef}
        style={{flex: 1, minHeight: 0, position: 'relative'}}
        onScroll={(ev) => {
          const vp = ev.currentTarget;
          if (!vp) return;
          const start = Math.floor((vp.scrollTop || 0) / 28);
          const visibleCount = Math.ceil((vp.clientHeight || 600) / 28);
          setScrollRowRange({start, end: start + visibleCount});
        }}
      >
        <div
          ref={gridRootRef}
          role={model.gridRole || 'grid'}
          aria-multiselectable="true"
          aria-label={model.ariaLabel || gettext('Data Surface Grid')}
          data-cdeadmin-qa-key={model.qaKey || 'data-surface-standard-grid'}
          style={{minWidth: 'max-content', width: '100%'}}
        >
          {/* Sticky Column Header Bar with Top-Left Select-All (▣) + Column Picker (☰) */}
          <div
            role="row"
            style={{
              position: 'sticky',
              top: 0,
              zIndex: 6,
              display: 'flex',
              alignItems: 'stretch',
              minHeight: 34,
              background: 'var(--sr-surface-subtle, #f1f5f9)',
              borderBottom:
                '1px solid var(--sr-border-default, rgba(128,128,128,0.32))',
            }}
          >
            {/* Top-left Select-All + Visible Columns above Row Number Gutter */}
            <div
              role="columnheader"
              style={{
                position: 'sticky',
                left: 0,
                zIndex: 7,
                width: GUTTER_WIDTH,
                flex: `0 0 ${GUTTER_WIDTH}px`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0 4px',
                background: selection.all
                  ? 'rgba(2, 132, 199, 0.16)'
                  : 'var(--sr-surface-subtle, #f1f5f9)',
                borderRight:
                  '1px solid var(--sr-border-default, rgba(128,128,128,0.28))',
              }}
            >
              <button
                type="button"
                aria-label={gettext('Select entire result set')}
                aria-pressed={Boolean(selection.all)}
                title={gettext('Select entire result set (Ctrl+A)')}
                data-cdeadmin-qa-key="data-surface-select-all"
                onClick={() => {
                  activeGridSelection.toggleSelectAll();
                  focusGridCellDom(
                    activeRowIndex || 0,
                    activeColName || gridColumns[0]?.name
                  );
                }}
                style={{
                  border: 'none',
                  background: selection.all
                    ? 'var(--sr-accent, #0284c7)'
                    : 'transparent',
                  color: selection.all
                    ? '#ffffff'
                    : 'var(--sr-text-secondary, inherit)',
                  cursor: 'pointer',
                  fontSize: '0.82rem',
                  lineHeight: 1,
                  padding: '3px 5px',
                  borderRadius: 4,
                  fontWeight: 700,
                }}
              >
                {selection.all ? '▣' : '☐'}
              </button>
              <button
                type="button"
                aria-label={gettext('Select and reorder visible columns')}
                title={gettext('Select and reorder visible columns')}
                data-cdeadmin-qa-key="data-surface-hamburger-columns"
                onClick={() => {
                  setColumnPickerScope('grid');
                  setColumnPickerOpen(true);
                }}
                style={{
                  border: 'none',
                  background: 'transparent',
                  color: 'inherit',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  lineHeight: 1,
                  padding: '3px 5px',
                  borderRadius: 4,
                }}
              >
                ☰
              </button>
            </div>

            {gridColumns.map((col) => {
              const cPrefs = layout.gridColPrefs[col.name] || {};
              const w = cPrefs.width || DEFAULT_COL_WIDTH;
              const isPinned = Boolean(cPrefs.pinned);
              const stickyLeft = isPinned ? headerPinnedAcc : undefined;
              if (isPinned) headerPinnedAcc += w;

              const isColSelected = isGridColumnSelected(selection, col.name);
              const sortEntry = (hostData?.sorts || []).find(
                (s) => s.column === col.name
              );
              const hasFilter = (hostData?.filters || []).some(
                (f) => f.column === col.name
              );
              const sortGlyph = !sortEntry
                ? '⇅'
                : sortEntry.direction === 'desc'
                  ? '↓'
                  : '↑';

              return (
                <div
                  key={col.name}
                  role="columnheader"
                  data-grid-col-header={col.name}
                  data-col-selected={isColSelected ? 'true' : undefined}
                  aria-selected={isColSelected || undefined}
                  aria-sort={
                    !sortEntry
                      ? 'none'
                      : sortEntry.direction === 'desc'
                        ? 'descending'
                        : 'ascending'
                  }
                  onContextMenu={(ev) => {
                    if (typeof openHeaderContextMenu === 'function') {
                      openHeaderContextMenu(ev, col);
                    } else {
                      ev.preventDefault();
                      ev.stopPropagation();
                      setGridMenu({
                        x: ev.clientX,
                        y: ev.clientY,
                        rowIndex: activeRowIndex || 0,
                        colName: col.name,
                      });
                    }
                  }}
                  style={{
                    width: w,
                    flex: `0 0 ${w}px`,
                    position: isPinned ? 'sticky' : 'relative',
                    left: stickyLeft,
                    zIndex: isPinned ? 7 : 5,
                    background: isColSelected
                      ? 'rgba(2, 132, 199, 0.16)'
                      : 'var(--sr-surface-subtle, #f1f5f9)',
                    borderRight:
                      '1px solid var(--sr-border-default, rgba(128,128,128,0.24))',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'stretch',
                  }}
                >
                  {/* Top Column-Selector Strip: plain click selects column; Shift+Click range; Ctrl+Click toggle; drag selects multiple columns */}
                  <div
                    data-grid-col-select={col.name}
                    title={gettext(
                      'Click to select column · Shift+Click range · Ctrl+Click toggle · Drag across columns'
                    )}
                    onMouseDown={(ev) => {
                      if (ev.button !== 0) return;
                      ev.stopPropagation();
                      dragStateRef.current = {
                        kind: 'col',
                        startCol: col.name,
                        baseCols:
                          ev.ctrlKey || ev.metaKey
                            ? [...(selection.cols || [])]
                            : null,
                        preservedRows:
                          ev.ctrlKey || ev.metaKey
                            ? [...(selection.rows || [])]
                            : [],
                        moved: false,
                      };
                    }}
                    onMouseEnter={() => {
                      const drag = dragStateRef.current;
                      if (!drag || drag.kind !== 'col') return;
                      if (drag.startCol === col.name && !drag.moved) return;
                      drag.moved = true;
                      suppressNextClickRef.current = true;
                      activeGridSelection.setSelection((prev) =>
                        selectDragColumnRangeState(
                          prev,
                          drag.startCol,
                          col.name,
                          gridColumns,
                          drag.baseCols,
                          drag.preservedRows
                        )
                      );
                      setActiveColName(col.name);
                    }}
                    onClick={(ev) => {
                      ev.stopPropagation();
                      if (suppressNextClickRef.current) {
                        suppressNextClickRef.current = false;
                        return;
                      }
                      activeGridSelection.handleColumnSelectClick(col.name, ev);
                      focusGridCellDom(activeRowIndex || 0, col.name);
                    }}
                    style={{
                      height: 6,
                      width: '100%',
                      cursor: 'pointer',
                      background: isColSelected
                        ? 'var(--sr-accent, #0284c7)'
                        : 'rgba(128, 128, 128, 0.20)',
                      borderBottom:
                        '1px solid rgba(128, 128, 128, 0.16)',
                      flexShrink: 0,
                    }}
                  />

                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      flex: 1,
                      minHeight: 26,
                    }}
                  >
                    <button
                      type="button"
                      title={gettext(
                        'Click to sort · Shift+Click or Ctrl+Click to select column(s)'
                      )}
                      onClick={(ev) => {
                        if (ev.shiftKey || ev.ctrlKey || ev.metaKey) {
                          ev.preventDefault();
                          ev.stopPropagation();
                          activeGridSelection.handleColumnSelectClick(
                            col.name,
                            ev
                          );
                          focusGridCellDom(activeRowIndex || 0, col.name);
                          return;
                        }
                        setActiveColName(col.name);
                        handleToggleColumnSort(col.name);
                      }}
                      style={{
                        flex: 1,
                        minWidth: 0,
                        height: '100%',
                        padding: '0 8px',
                        border: 'none',
                        background:
                          isColSelected || activeColName === col.name
                            ? 'var(--sr-surface-selected, rgba(2,132,199,0.1))'
                            : 'transparent',
                        color: isColSelected
                          ? 'var(--sr-accent, #0284c7)'
                          : 'inherit',
                        fontWeight: isColSelected ? 700 : 600,
                        fontSize: '0.76rem',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 4,
                        cursor: 'pointer',
                      }}
                    >
                      <span
                        style={{
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {isPinned ? '📌 ' : ''}
                        {col.label || col.name}
                        {col.key ? ' 🔑' : ''}
                        {hasFilter ? ' •' : ''}
                      </span>
                      <span
                        aria-hidden="true"
                        style={{
                          opacity: sortEntry ? 1 : 0.42,
                          color: sortEntry ? 'var(--sr-accent)' : 'inherit',
                          fontSize: '0.74rem',
                        }}
                      >
                        {sortGlyph}
                      </span>
                    </button>

                    {/* Drag-resize column border */}
                    <div
                      role="separator"
                      aria-orientation="vertical"
                      onMouseDown={(ev) => {
                        ev.preventDefault();
                        ev.stopPropagation();
                        const startX = ev.clientX;
                        const startW = w;
                        const onMove = (me) => {
                          const nextW = Math.max(
                            64,
                            Math.min(680, startW + (me.clientX - startX))
                          );
                          setColumnPref(col.name, {width: nextW});
                        };
                        const onUp = () => {
                          window.removeEventListener('mousemove', onMove);
                          window.removeEventListener('mouseup', onUp);
                        };
                        window.addEventListener('mousemove', onMove);
                        window.addEventListener('mouseup', onUp);
                      }}
                      style={{
                        width: 5,
                        alignSelf: 'stretch',
                        cursor: 'col-resize',
                        flexShrink: 0,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {!rows.length ? (
            <EmptyState
              message={model.emptyMessage || gettext('No matching rows.')}
            />
          ) : (
            rows.map((row, rIdx) => {
              if (
                effectiveDisplayMode === DISPLAY_MODES.HYBRID &&
                rIdx === activeRowIndex
              ) {
                const isRowEdit =
                  isEditingRow && (editingRowIndex ?? activeRowIndex) === rIdx;
                return (
                  <div
                    key={row.identity_token || `hyb-${rIdx}`}
                    data-surface-row-idx={rIdx}
                    data-cdeadmin-qa-key="data-surface-hybrid-pinned-form"
                    style={{
                      position: 'sticky',
                      left: 0,
                      width: `${viewportWidth}px`,
                      maxWidth: `${viewportWidth}px`,
                      zIndex: 4,
                    }}
                  >
                    <AdaptiveRecordFormCard
                      row={row}
                      rowIndex={rIdx}
                      isCurrent
                      isEditing={isRowEdit}
                      isBookmarked={bookmarkedGlobals.has(
                        (hostData?.window_offset || 0) + rIdx
                      )}
                      draftValues={isRowEdit ? rowDraft : null}
                      columns={formColumns}
                      formLayout={sharedFormLayout}
                      formFieldPrefs={layout.formFieldPrefs}
                      fieldTypeDefaults={hostData?.field_type_defaults}
                      conversions={conversions}
                      booleanFormat={layout.booleanFormat}
                      localeDateFormat={layout.localeDateFormat}
                      maxHeight="46vh"
                      totalRowsInPage={rows.length}
                      onSelectRow={selectRowAtIndex}
                      onFocusField={setActiveColName}
                      onNavigateFormField={(nextRowIdx, nextCol, action) =>
                        handleKeyboardCellNavigate(
                          nextRowIdx,
                          nextCol,
                          action,
                          'form'
                        )
                      }
                      onToggleBookmark={toggleBookmarkAtRow}
                      onFieldChange={(cName, val) =>
                        setRowDraft((prev) => ({...(prev || {}), [cName]: val}))
                      }
                      onOpenComplexInDrawer={(idx, col) =>
                        openRightDrawerWith({
                          mode: 'complex_value',
                          rowIndex: idx,
                          column: col,
                        })
                      }
                      onFormContextMenu={openMiniFormContextMenu}
                      onFieldContextMenu={openFormFieldContextMenu}
                    />
                  </div>
                );
              }
              return renderStandardGridRow(row, rIdx);
            })
          )}
        </div>

        {/* Built-in Grid Selection & Copy Context Menu */}
        {gridMenu && (
          <div
            role="menu"
            data-cdeadmin-qa-key="grid-selection-context-menu"
            onClick={(ev) => ev.stopPropagation()}
            style={{
              position: 'fixed',
              left: Math.min(
                gridMenu.x,
                (typeof window !== 'undefined' ? window.innerWidth : 1024) - 230
              ),
              top: Math.min(
                gridMenu.y,
                (typeof window !== 'undefined' ? window.innerHeight : 768) - 270
              ),
              zIndex: 3200,
              minWidth: 215,
              padding: 4,
              borderRadius: 8,
              background: 'var(--sr-surface-elevated, var(--sr-surface-card, #ffffff))',
              border: '1px solid var(--sr-border-default, rgba(128,128,128,0.3))',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.18)',
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
              fontSize: '0.79rem',
            }}
          >
            {[
              {
                id: 'copy',
                label: gettext('Copy'),
                shortcut: 'Ctrl+C',
                action: () => invokeCopy('auto'),
              },
              {
                id: 'copy_tsv',
                label: gettext('Copy as TSV (with Headers)'),
                action: () => invokeCopy('tsv'),
              },
              {
                id: 'copy_csv',
                label: gettext('Copy as CSV'),
                shortcut: 'Ctrl+Shift+C',
                action: () => invokeCopy('csv'),
              },
              {
                id: 'copy_json',
                label: gettext('Copy as JSON'),
                action: () => invokeCopy('json'),
              },
              ...(typeof model.onOpenExportSelection === 'function'
                ? [
                  {
                    id: 'export_sel',
                    label: gettext('Export Selection…'),
                    action: () => model.onOpenExportSelection(),
                  },
                ]
                : []),
              {id: 'sep1', separator: true},
              {
                id: 'select_row',
                label: gettext('Select Row'),
                shortcut: 'Shift+Space',
                action: () =>
                  activeGridSelection.handleRowHeaderClick(
                    gridMenu.rowIndex,
                    {}
                  ),
              },
              ...(gridMenu.colName
                ? [
                  {
                    id: 'select_col',
                    label: gettext('Select Column (%s)', gridMenu.colName),
                    shortcut: 'Ctrl+Space',
                    action: () =>
                      activeGridSelection.handleColumnSelectClick(
                        gridMenu.colName,
                        {}
                      ),
                  },
                ]
                : []),
              {
                id: 'select_all',
                label: gettext('Select Entire Result Set'),
                shortcut: 'Ctrl+A',
                action: () => activeGridSelection.selectAll(),
              },
              ...(selectionSlice.hasMultiSelection
                ? [
                  {
                    id: 'clear_sel',
                    label: gettext('Clear Selection'),
                    shortcut: 'Esc',
                    action: () => activeGridSelection.clearSelection(),
                  },
                ]
                : []),
            ].map((item) =>
              item.separator ? (
                <div
                  key={item.id}
                  role="separator"
                  style={{
                    height: 1,
                    margin: '2px 4px',
                    background:
                      'var(--sr-border-subtle, rgba(128,128,128,0.22))',
                  }}
                />
              ) : (
                <button
                  key={item.id}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    item.action();
                    setGridMenu(null);
                  }}
                  style={{
                    border: 'none',
                    background: 'transparent',
                    color: 'inherit',
                    padding: '5px 8px',
                    borderRadius: 5,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 10,
                    textAlign: 'left',
                    fontSize: '0.79rem',
                  }}
                >
                  <span>{item.label}</span>
                  {item.shortcut && (
                    <span style={{opacity: 0.58, fontSize: '0.71rem'}}>
                      {item.shortcut}
                    </span>
                  )}
                </button>
              )
            )}
          </div>
        )}
      </ScratchScrollArea>
    );
  };

  return conversions?.error ? (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
        minHeight: 0,
        minWidth: 0,
      }}
    >
      <div role="alert">{conversions.error}</div>
      {renderDataView()}
    </div>
  ) : (
    renderDataView()
  );
}

RecordDataView.propTypes = {model: PropTypes.object.isRequired};
