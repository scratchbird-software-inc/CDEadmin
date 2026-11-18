/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {EmptyState} from '../feedback/EmptyState';
import {AdaptiveRecordFormCard} from './RecordForm';
import {DISPLAY_MODES, formatCellValue, inferColumnMeta,
  isComplexOrOversizedCell, serializeValueForEdit} from './dataEditSurfaceHelpers';
const DEFAULT_COL_WIDTH = 156;
const GUTTER_WIDTH = 58;

/** Shared record viewport. Controllers own sessions, drafts, authorization and
 * provider effects; this component owns the existing Data Viewer presentation. */
export default function RecordDataView({model}) {
  const {acceptCurrentRow,
    activeColName,
    activeRowIndex,
    beginEditRow,
    bookmarkedGlobals,
    cancelRowDraft,
    currentRow,
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
    selectedCells,
    setActiveColName,
    setColumnPickerOpen,
    setColumnPickerScope,
    setColumnPref,
    setRowDraft,
    setScrollRowRange,
    setSelectedCells,
    sharedFormLayout,
    toggleBookmarkAtRow,
    viewportWidth} = model;
  const renderStandardGridRow = (row, rIdx) => {
    const isCurrent = rIdx === activeRowIndex;
    const isRowEdit = isEditingRow && (editingRowIndex ?? activeRowIndex) === rIdx;
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
        aria-selected={isCurrent}
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
              : isCurrent
                ? 'var(--sr-surface-selected, rgba(2,132,199,0.11))'
                : 'transparent',
          textDecoration:
            row.stage_state === 'deleted' ? 'line-through' : 'none',
        }}
      >
        {/* Left Row Number Gutter (visually distinct, no heading) */}
        <div
          role="rowheader"
          onDoubleClick={(ev) => {
            ev.stopPropagation();
            toggleBookmarkAtRow(rIdx);
          }}
          title={gettext('Double-click or press ! to toggle bookmark')}
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
            fontWeight: isCurrent ? 700 : 500,
            color: 'var(--sr-text-muted, #64748b)',
            background: 'var(--sr-surface-subtle, #f1f5f9)',
            borderRight:
              '1px solid var(--sr-border-default, rgba(128,128,128,0.28))',
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
          const colMeta = inferColumnMeta(col);
          const cPrefs = layout.gridColPrefs[col.name] || {};
          const w = cPrefs.width || DEFAULT_COL_WIDTH;
          const hAlign = cPrefs.hAlign || colMeta.defaultAlignment || 'left';
          const vAlign = cPrefs.vAlign || 'middle';
          const wrapMode = cPrefs.wrapMode || 'none';
          const isPinned = Boolean(cPrefs.pinned);
          const stickyLeft = isPinned ? pinnedLeftAcc : undefined;
          if (isPinned) pinnedLeftAcc += w;

          const isActiveCell = isCurrent && activeColName === col.name;
          const rawVal =
            isRowEdit &&
            rowDraft &&
            Object.prototype.hasOwnProperty.call(rowDraft, col.name)
              ? rowDraft[col.name]
              : row.values?.[col.name];
          const formatted = formatCellValue(rawVal, colMeta, {
            booleanFormat: layout.booleanFormat,
            localeDateFormat: layout.localeDateFormat,
            colPrefs: cPrefs,
          });
          const canEditCell =
            isRowEdit &&
            layout.displayMode === DISPLAY_MODES.GRID &&
            (row.stage_state === 'inserted'
              ? col.insertable !== false
              : col.editable !== false) &&
            !isComplexOrOversizedCell(rawVal, colMeta, cPrefs);

          const quickMatch =
            quickFindText &&
            formatted.text
              .toLowerCase()
              .includes(quickFindText.trim().toLowerCase());

          return (
            <div
              key={col.name}
              role="gridcell"
              data-grid-nav-cell={`${rIdx}:${col.name}`}
              tabIndex={isActiveCell ? 0 : -1}
              onClick={(ev) => {
                ev.stopPropagation();
                if (ev.shiftKey && selectedCells.length > 0) {
                  setSelectedCells((prev) => [
                    ...prev,
                    {rowIndex: rIdx, colName: col.name},
                  ]);
                } else {
                  selectRowAtIndex(rIdx, col.name);
                }
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
                const colIdx = gridColumns.findIndex((c) => c.name === col.name);
                const lastColIdx = gridColumns.length - 1;

                if (ev.key === 'Tab' && !ev.altKey && !ev.ctrlKey && !ev.metaKey) {
                  ev.preventDefault();
                  if (!ev.shiftKey) {
                    if (colIdx < lastColIdx) {
                      handleKeyboardCellNavigate(rIdx, gridColumns[colIdx + 1].name, null, 'grid');
                    } else {
                      handleKeyboardCellNavigate(rIdx + 1, gridColumns[0]?.name || col.name, null, 'grid');
                    }
                  } else if (colIdx > 0) {
                    handleKeyboardCellNavigate(rIdx, gridColumns[colIdx - 1].name, null, 'grid');
                  } else {
                    handleKeyboardCellNavigate(rIdx - 1, gridColumns[lastColIdx]?.name || col.name, null, 'grid');
                  }
                  return;
                }

                if (canEditCell) {
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

                if (ev.key === 'ArrowDown') {
                  ev.preventDefault();
                  handleKeyboardCellNavigate(rIdx + 1, col.name, null, 'grid');
                } else if (ev.key === 'ArrowUp') {
                  ev.preventDefault();
                  handleKeyboardCellNavigate(rIdx - 1, col.name, null, 'grid');
                } else if (ev.key === 'ArrowRight') {
                  ev.preventDefault();
                  if (colIdx < lastColIdx) {
                    handleKeyboardCellNavigate(rIdx, gridColumns[colIdx + 1].name, null, 'grid');
                  } else {
                    handleKeyboardCellNavigate(rIdx + 1, gridColumns[0]?.name || col.name, null, 'grid');
                  }
                } else if (ev.key === 'ArrowLeft') {
                  ev.preventDefault();
                  if (colIdx > 0) {
                    handleKeyboardCellNavigate(rIdx, gridColumns[colIdx - 1].name, null, 'grid');
                  } else {
                    handleKeyboardCellNavigate(rIdx - 1, gridColumns[lastColIdx]?.name || col.name, null, 'grid');
                  }
                } else if (ev.key === 'PageDown') {
                  ev.preventDefault();
                  handleKeyboardCellNavigate(rIdx, col.name, 'next_page', 'grid');
                } else if (ev.key === 'PageUp') {
                  ev.preventDefault();
                  handleKeyboardCellNavigate(rIdx, col.name, 'prev_page', 'grid');
                } else if (ev.key === 'Home') {
                  ev.preventDefault();
                  if (ev.ctrlKey || ev.metaKey) {
                    handleKeyboardCellNavigate(0, gridColumns[0]?.name || col.name, 'first_record', 'grid');
                  } else {
                    handleKeyboardCellNavigate(rIdx, gridColumns[0]?.name || col.name, null, 'grid');
                  }
                } else if (ev.key === 'End') {
                  ev.preventDefault();
                  if (ev.ctrlKey || ev.metaKey) {
                    handleKeyboardCellNavigate(rows.length - 1, gridColumns[lastColIdx]?.name || col.name, 'last_record', 'grid');
                  } else {
                    handleKeyboardCellNavigate(rIdx, gridColumns[lastColIdx]?.name || col.name, null, 'grid');
                  }
                } else if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'b') {
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
                borderRight:
                  '1px solid var(--sr-border-subtle, rgba(128,128,128,0.16))',
                outline: isActiveCell
                  ? '2px solid var(--sr-accent, #0284c7)'
                  : 'none',
                outlineOffset: -2,
                position: isPinned ? 'sticky' : 'relative',
                left: stickyLeft,
                zIndex: isPinned ? 2 : 1,
                background: quickMatch
                  ? 'rgba(250, 204, 21, 0.24)'
                  : isPinned
                    ? 'var(--sr-surface-card)'
                    : undefined,
                overflow: 'hidden',
              }}
            >
              {formatted.isComplex ? (
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
          isBookmarked={bookmarkedGlobals.has((hostData?.window_offset || 0) + activeRowIndex)}
          draftValues={isRowEdit ? rowDraft : null}
          columns={formColumns}
          formLayout={sharedFormLayout}
          formFieldPrefs={layout.formFieldPrefs}
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
            openRightDrawerWith({mode: 'complex_value', rowIndex: rIdx, column: col})
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
        <ScratchScrollArea orientation="vertical" fillViewport style={{flex: 1, minHeight: 0}}>
          <div data-cdeadmin-qa-key="data-surface-mini-forms-list">
            {rows.map((row, rIdx) => {
              const isRowEdit =
                isEditingRow && (editingRowIndex ?? activeRowIndex) === rIdx;
              return (
                <div key={row.identity_token || `mf-${rIdx}`} data-surface-row-idx={rIdx}>
                  <AdaptiveRecordFormCard
                    row={row}
                    rowIndex={rIdx}
                    isCurrent={rIdx === activeRowIndex}
                    isEditing={isRowEdit}
                    isBookmarked={bookmarkedGlobals.has((hostData?.window_offset || 0) + rIdx)}
                    draftValues={isRowEdit ? rowDraft : null}
                    columns={formColumns}
                    formLayout={sharedFormLayout}
                    formFieldPrefs={layout.formFieldPrefs}
                    booleanFormat={layout.booleanFormat}
                    localeDateFormat={layout.localeDateFormat}
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
        style={{flex: 1, minHeight: 0}}
        onScroll={(ev) => {
          const vp = ev.currentTarget;
          if (!vp) return;
          const start = Math.floor((vp.scrollTop || 0) / 28);
          const visibleCount = Math.ceil((vp.clientHeight || 600) / 28);
          setScrollRowRange({start, end: start + visibleCount});
        }}
      >
        <div
          role="grid"
          aria-label={gettext('Data Surface Grid')}
          data-cdeadmin-qa-key="data-surface-standard-grid"
          style={{minWidth: 'max-content', width: '100%'}}
        >
          {/* Sticky Column Header Bar with Top-Left Hamburger (☰) */}
          <div
            role="row"
            style={{
              position: 'sticky',
              top: 0,
              zIndex: 6,
              display: 'flex',
              alignItems: 'stretch',
              minHeight: 30,
              background: 'var(--sr-surface-subtle, #f1f5f9)',
              borderBottom:
                '1px solid var(--sr-border-default, rgba(128,128,128,0.32))',
            }}
          >
            {/* Top-left Hamburger button above Row Number Gutter */}
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
                justifyContent: 'center',
                background: 'var(--sr-surface-subtle, #f1f5f9)',
                borderRight:
                  '1px solid var(--sr-border-default, rgba(128,128,128,0.28))',
              }}
            >
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
                  fontSize: '0.95rem',
                  lineHeight: 1,
                  padding: '2px 6px',
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
                  aria-sort={
                    !sortEntry
                      ? 'none'
                      : sortEntry.direction === 'desc'
                        ? 'descending'
                        : 'ascending'
                  }
                  onContextMenu={(ev) => openHeaderContextMenu(ev, col)}
                  style={{
                    width: w,
                    flex: `0 0 ${w}px`,
                    position: isPinned ? 'sticky' : 'relative',
                    left: stickyLeft,
                    zIndex: isPinned ? 7 : 5,
                    background: 'var(--sr-surface-subtle, #f1f5f9)',
                    borderRight:
                      '1px solid var(--sr-border-default, rgba(128,128,128,0.24))',
                    display: 'flex',
                    alignItems: 'center',
                  }}
                >
                  <button
                    type="button"
                    onClick={() => {
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
                        activeColName === col.name
                          ? 'var(--sr-surface-selected, rgba(2,132,199,0.1))'
                          : 'transparent',
                      color: 'inherit',
                      fontWeight: 600,
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
                      {col.name}
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
              );
            })}
          </div>

          {!rows.length ? (
            <EmptyState message={gettext('No matching rows.')} />
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
                      isBookmarked={bookmarkedGlobals.has((hostData?.window_offset || 0) + rIdx)}
                      draftValues={isRowEdit ? rowDraft : null}
                      columns={formColumns}
                      formLayout={sharedFormLayout}
                      formFieldPrefs={layout.formFieldPrefs}
                      booleanFormat={layout.booleanFormat}
                      localeDateFormat={layout.localeDateFormat}
                      maxHeight="46vh"
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
      </ScratchScrollArea>
    );
  };


  return renderDataView();
}
RecordDataView.propTypes = {model: PropTypes.object.isRequired};
