/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {FIELD_FONTS, BOOLEAN_FORMATS, DISPLAY_MODES, buildFormLayoutPlacements, formatCellValue,
  inferColumnMeta, serializeValueForEdit} from './dataEditSurfaceHelpers';
const GUTTER_WIDTH = 58;

export function defaultLayoutState() {
  return {
    displayMode: DISPLAY_MODES.GRID,
    hybridEditTarget: 'mini_form', // 'mini_form' | 'single_form'
    booleanFormat: BOOLEAN_FORMATS.TF,
    localeDateFormat: true,
    gridVisibleCols: null, // null = all
    gridColOrder: [],
    gridColPrefs: {}, // { [colName]: { width, hAlign, vAlign, wrapMode, pinned, decimals } }
    formVisibleCols: null, // independent from grid!
    formColOrder: [],
    formFieldPrefs: {}, // { [colName]: { inlineBox, rows, hAlign, vAlign, widthPx } }
  };
}

export function orderedColumns(allColumns, orderList, visibleList) {
  const byName = new Map((allColumns || []).map((c) => [c.name, c]));
  const ordered = [];
  for (const name of orderList || []) {
    if (byName.has(name)) {
      ordered.push(byName.get(name));
      byName.delete(name);
    }
  }
  for (const col of byName.values()) {
    ordered.push(col);
  }
  if (Array.isArray(visibleList)) {
    const visSet = new Set(visibleList);
    return ordered.filter((c) => visSet.has(c.name));
  }
  return ordered;
}

/**
 * SR-F-020033-compatible wrapping record form used by:
 *   - (b) Mini-Forms
 *   - (c) Hybrid (pinned to Area 3e visible viewport width)
 *   - (d) Single Form (100% of Area 3e)
 *   - (e) Hybrid-When-Editing
 * Includes left-side hover scrollbars on vertical overflow and strict
 * focus-visibility guarantee (focused field is always scrolled into view).
 */
export function AdaptiveRecordFormCard({
  row,
  rowIndex,
  isCurrent,
  isEditing,
  isBookmarked = false,
  draftValues,
  columns,
  formLayout,
  formFieldPrefs,
  fieldTypeDefaults,
  conversions,
  booleanFormat,
  localeDateFormat,
  maxHeight,
  fullArea = false,
  totalRowsInPage = 0,
  onSelectRow,
  onFocusField,
  onFieldChange,
  onNavigateFormField,
  onToggleBookmark,
  onOpenComplexInDrawer,
  onFormContextMenu,
  onFieldContextMenu,
}) {
  const [focusedColName, setFocusedColName] = useState(null);

  const resolvedLayout = useMemo(
    () =>
      formLayout ||
      buildFormLayoutPlacements(columns, formFieldPrefs, 720, null, row ? [row] : null),
    [formLayout, columns, formFieldPrefs, row]
  );

  const placementMap = useMemo(() => {
    const m = new Map();
    for (const p of resolvedLayout.placements || []) {
      m.set(p.fieldId, p);
    }
    return m;
  }, [resolvedLayout.placements]);

  const stageMarker =
    row.stage_state === 'inserted'
      ? '+'
      : row.stage_state === 'updated'
        ? '✎'
        : row.stage_state === 'deleted'
          ? '−'
          : '';

  const handleFieldKeyNav = (ev, colIdx, col, {isMultiline = false, isTextInput = false} = {}) => {
    if (!onNavigateFormField) return;
    const lastColIdx = columns.length - 1;
    const maxRowIdx = Math.max(0, (totalRowsInPage || rowIndex + 1) - 1);

    if (ev.key === 'Tab' && !ev.altKey && !ev.ctrlKey && !ev.metaKey) {
      if (!ev.shiftKey && colIdx < lastColIdx) {
        ev.preventDefault();
        onNavigateFormField(rowIndex, columns[colIdx + 1].name);
        return;
      }
      if (!ev.shiftKey && colIdx === lastColIdx && rowIndex < maxRowIdx) {
        ev.preventDefault();
        onNavigateFormField(rowIndex + 1, columns[0].name);
        return;
      }
      if (ev.shiftKey && colIdx > 0) {
        ev.preventDefault();
        onNavigateFormField(rowIndex, columns[colIdx - 1].name);
        return;
      }
      if (ev.shiftKey && colIdx === 0 && rowIndex > 0) {
        ev.preventDefault();
        onNavigateFormField(rowIndex - 1, columns[lastColIdx].name);
        return;
      }
    }

    if (ev.key === 'ArrowDown' && !isMultiline) {
      ev.preventDefault();
      onNavigateFormField(rowIndex + 1, col.name);
      return;
    }
    if (ev.key === 'ArrowUp' && !isMultiline) {
      ev.preventDefault();
      onNavigateFormField(rowIndex - 1, col.name);
      return;
    }
    if (ev.key === 'PageDown') {
      ev.preventDefault();
      onNavigateFormField(rowIndex, col.name, 'next_page');
      return;
    }
    if (ev.key === 'PageUp') {
      ev.preventDefault();
      onNavigateFormField(rowIndex, col.name, 'prev_page');
      return;
    }
    if (ev.key === 'Home' && (ev.ctrlKey || ev.metaKey)) {
      ev.preventDefault();
      onNavigateFormField(0, columns[0]?.name || col.name, 'first_record');
      return;
    }
    if (ev.key === 'End' && (ev.ctrlKey || ev.metaKey)) {
      ev.preventDefault();
      onNavigateFormField(maxRowIdx, columns[lastColIdx]?.name || col.name, 'last_record');
      return;
    }

    const atLeftEdge =
      !isTextInput ||
      (typeof ev.currentTarget?.selectionStart === 'number' &&
        ev.currentTarget.selectionStart === 0 &&
        ev.currentTarget.selectionEnd === 0);
    const atRightEdge =
      !isTextInput ||
      (typeof ev.currentTarget?.selectionEnd === 'number' &&
        ev.currentTarget.selectionEnd === String(ev.currentTarget.value ?? '').length);

    if (ev.key === 'ArrowRight' && atRightEdge && !isMultiline) {
      ev.preventDefault();
      if (colIdx < lastColIdx) {
        onNavigateFormField(rowIndex, columns[colIdx + 1].name);
      } else if (rowIndex < maxRowIdx) {
        onNavigateFormField(rowIndex + 1, columns[0].name);
      }
      return;
    }
    if (ev.key === 'ArrowLeft' && atLeftEdge && !isMultiline) {
      ev.preventDefault();
      if (colIdx > 0) {
        onNavigateFormField(rowIndex, columns[colIdx - 1].name);
      } else if (rowIndex > 0) {
        onNavigateFormField(rowIndex - 1, columns[lastColIdx].name);
      }
    }
  };

  return (
    <div
      data-cdeadmin-qa-key={`data-surface-record-form-${row.row_number}`}
      onClick={() => onSelectRow?.(rowIndex)}
      onContextMenu={(ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        onSelectRow?.(rowIndex);
        onFormContextMenu?.(ev, rowIndex);
      }}
      style={{
        display: 'flex',
        alignItems: 'stretch',
        alignSelf: 'start',
        width: '100%',
        height: fullArea ? '100%' : 'auto',
        borderBottom: fullArea
          ? 'none'
          : '1px solid var(--sr-border-default, rgba(128,128,128,0.25))',
        background: isCurrent
          ? 'var(--sr-surface-selected, rgba(2,132,199,0.06))'
          : 'var(--sr-surface-card, transparent)',
        boxShadow: isCurrent
          ? 'inset 3px 0 0 var(--sr-accent, #0284c7)'
          : 'none',
      }}
    >
      {/* Left row-number, bookmark (`!`), & status badge */}
      <div
        onClick={(ev) => {
          if (ev.detail === 2 && onToggleBookmark) {
            ev.stopPropagation();
            onToggleBookmark(rowIndex);
          }
        }}
        title={
          onToggleBookmark
            ? gettext('Row %s — Double-click gutter or click ! to toggle bookmark', row.row_number)
            : undefined
        }
        style={{
          width: GUTTER_WIDTH,
          flex: `0 0 ${GUTTER_WIDTH}px`,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'flex-start',
          paddingTop: 7,
          paddingBottom: 6,
          gap: 3,
          fontSize: '0.75rem',
          fontWeight: isCurrent ? 700 : 500,
          color: 'var(--sr-text-muted, #64748b)',
          background: 'var(--sr-surface-subtle, rgba(128,128,128,0.06))',
          borderRight:
            '1px solid var(--sr-border-subtle, rgba(128,128,128,0.2))',
          userSelect: 'none',
        }}
      >
        <span>
          {isCurrent ? '▶ ' : ''}
          {row.row_number}
        </span>
        {isBookmarked && (
          <span
            data-cdeadmin-qa-key={`row-bookmark-badge-${rowIndex}`}
            style={{
              fontSize: '0.68rem',
              fontWeight: 800,
              padding: '0 5px',
              borderRadius: 999,
              background: '#f59e0b',
              color: '#fff',
              lineHeight: 1.35,
            }}
          >
            !
          </span>
        )}
        {stageMarker && (
          <span
            style={{
              fontSize: '0.7rem',
              padding: '1px 5px',
              borderRadius: 999,
              background: 'var(--sr-accent, #0284c7)',
              color: '#fff',
            }}
          >
            {stageMarker}
          </span>
        )}
      </div>

      {/* Zero-ResizeObserver left-side hover scrollbar + strict focus-visibility guarantee */}
      <div
        className="sr-left-hover-scroll"
        data-vertical-side="left"
        style={{
          flex: 1,
          minWidth: 0,
          maxHeight: fullArea ? '100%' : maxHeight || '52vh',
        }}
        onFocusCapture={(ev) => {
          const fieldWrap = ev.target?.closest?.('[data-form-field-wrap]');
          if (fieldWrap && typeof fieldWrap.scrollIntoView === 'function') {
            fieldWrap.scrollIntoView({block: 'nearest', inline: 'nearest'});
          }
        }}
      >
        <div
          data-cell-columns={resolvedLayout.numCols}
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            columnGap: '12px',
            rowGap: '7px',
            padding: '6px 12px 8px 10px',
            alignItems: 'flex-start',
            alignContent: 'flex-start',
            width: '100%',
            boxSizing: 'border-box',
          }}
        >
          {columns.map((col, colIdx) => {
            const nativeMeta = inferColumnMeta(col);
            const fPrefs = {
              ...fieldTypeDefaults?.[nativeMeta.clientType],
              ...formFieldPrefs[col.name],
              font: formFieldPrefs[col.name]?.font || fieldTypeDefaults?.[nativeMeta.clientType]?.font,
              hAlign: formFieldPrefs[col.name]?.hAlign || fieldTypeDefaults?.[nativeMeta.clientType]?.hAlign,
            };
            const placement = placementMap.get(col.name) || {
              row: 'auto',
              colStart: 1,
              span: 1,
            };
            const markdownEditor = fPrefs.editor === 'markdown';
            const useInlineEditor = fPrefs.inlineBox || markdownEditor || (isEditing && nativeMeta.clientType === 'json');
            const isFullRow = Boolean(useInlineEditor || placement.fullRow);
            const natWidth =
              fPrefs.widthPx ||
              resolvedLayout.adaptiveWidths?.[col.name] ||
              placement.naturalWidth ||
              156;
            const nativeValue =
              isEditing &&
              draftValues &&
              Object.prototype.hasOwnProperty.call(draftValues, col.name)
                ? draftValues[col.name]
                : row.values?.[col.name];
            const rawVal = conversions?.displayValue(col.name, nativeValue) ?? nativeValue;
            const colMeta = conversions?.pairFor(col.name) && (typeof rawVal === 'string' || rawVal == null)
              ? {...nativeMeta, clientType: 'text', isComplex: false} : nativeMeta;
            const formatted = formatCellValue(rawVal, colMeta, {
              booleanFormat,
              localeDateFormat,
              colPrefs: fPrefs,
            });
            const hAlign = fPrefs.hAlign || colMeta.defaultAlignment || 'left';
            const canEditField =
              isEditing &&
              (row.stage_state === 'inserted'
                ? col.insertable !== false
                : col.editable !== false);
            const showHint =
              focusedColName === col.name && Boolean(col.comment);

            return (
              <div
                key={col.name}
                data-form-field-wrap={col.name}
                data-field-width-px={natWidth}
                onContextMenu={(ev) => {
                  ev.preventDefault();
                  ev.stopPropagation();
                  onSelectRow?.(rowIndex);
                  onFocusField?.(col.name);
                  onFieldContextMenu?.(ev, col, rowIndex);
                }}
                style={{
                  flex: isFullRow ? '1 1 100%' : `0 1 ${natWidth}px`,
                  width: isFullRow ? '100%' : `${natWidth}px`,
                  minWidth: isFullRow ? '100%' : `${Math.min(natWidth, 84)}px`,
                  maxWidth: '100%',
                  position: 'relative',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 2,
                }}
              >
                <label
                  style={{
                    fontSize: '0.71rem',
                    fontWeight: 600,
                    color: 'var(--sr-text-secondary, #475569)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 6,
                    lineHeight: 1.2,
                  }}
                >
                  <span
                    style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {col.label || col.name}
                    {col.key ? ' 🔑' : ''}
                  </span>
                  <span
                    style={{
                      fontSize: '0.64rem',
                      opacity: 0.62,
                      fontWeight: 400,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {col.native_type || ''}
                  </span>
                </label>

                {formatted.isComplex && !useInlineEditor ? (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      minHeight: 26,
                      padding: '2px 7px',
                      borderRadius: 5,
                      border:
                        '1px solid var(--sr-border-default, rgba(128,128,128,0.3))',
                      background: 'var(--sr-surface-subtle, rgba(128,128,128,0.05))',
                    }}
                  >
                    <span style={{fontSize: '0.74rem', opacity: 0.8}}>
                      {colMeta.clientType.toUpperCase()}
                    </span>
                    <button
                      type="button"
                      className="sr-btn"
                      data-form-nav-cell={`${rowIndex}:${col.name}`}
                      style={{minHeight: 20, padding: '1px 7px', fontSize: '0.73rem'}}
                      tabIndex={0}
                      onFocus={() => {
                        setFocusedColName(col.name);
                        onSelectRow?.(rowIndex);
                        onFocusField?.(col.name);
                      }}
                      onBlur={() => setFocusedColName(null)}
                      onKeyDown={(ev) => handleFieldKeyNav(ev, colIdx, col)}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        onOpenComplexInDrawer?.(rowIndex, col);
                      }}
                    >
                      [...]
                    </button>
                  </div>
                ) : useInlineEditor ? (
                  <textarea
                    aria-label={`${col.name}`}
                    data-form-nav-cell={`${rowIndex}:${col.name}`}
                    readOnly={!canEditField}
                    rows={fPrefs.rows || (markdownEditor ? 5 : 3)}
                    spellCheck={markdownEditor}
                    value={
                      rawVal === null || rawVal === undefined
                        ? canEditField
                          ? ''
                          : '<null>'
                        : serializeValueForEdit(rawVal)
                    }
                    placeholder={rawVal === null ? '<null>' : markdownEditor ? gettext('Markdown') : ''}
                    onFocus={() => {
                      setFocusedColName(col.name);
                      onSelectRow?.(rowIndex);
                      onFocusField?.(col.name);
                    }}
                    onBlur={() => setFocusedColName(null)}
                    onKeyDown={(ev) =>
                      handleFieldKeyNav(ev, colIdx, col, {
                        isMultiline: true,
                        isTextInput: true,
                      })
                    }
                    onChange={(ev) =>
                      canEditField && onFieldChange?.(col.name, ev.target.value)
                    }
                    style={{
                      width: '100%',
                      resize: 'vertical',
                      minHeight: 58,
                      padding: '4px 7px',
                      borderRadius: 5,
                      border: canEditField
                        ? '1px solid var(--sr-accent, #0284c7)'
                        : '1px solid var(--sr-border-default, rgba(128,128,128,0.28))',
                      background: 'var(--sr-surface-card, transparent)',
                      color:
                        rawVal === null && !canEditField
                          ? 'var(--sr-text-muted, #64748b)'
                          : 'inherit',
                      fontStyle:
                        rawVal === null && !canEditField ? 'italic' : 'normal',
                      textAlign: hAlign,
                      fontFamily: FIELD_FONTS[fPrefs.font] || (
                        colMeta.clientType === 'json' || markdownEditor
                          ? 'var(--sr-font-mono, monospace)'
                          : 'inherit'),
                      fontSize: '0.8rem',
                    }}
                  />
                ) : canEditField ? (
                  <input
                    type="text"
                    aria-label={`${col.name}`}
                    data-form-nav-cell={`${rowIndex}:${col.name}`}
                    value={
                      rawVal === null || rawVal === undefined
                        ? ''
                        : serializeValueForEdit(rawVal)
                    }
                    placeholder={rawVal === null ? '<null>' : ''}
                    onFocus={() => {
                      setFocusedColName(col.name);
                      onSelectRow?.(rowIndex);
                      onFocusField?.(col.name);
                    }}
                    onBlur={() => setFocusedColName(null)}
                    onKeyDown={(ev) =>
                      handleFieldKeyNav(ev, colIdx, col, {
                        isMultiline: false,
                        isTextInput: true,
                      })
                    }
                    onChange={(ev) =>
                      onFieldChange?.(col.name, ev.target.value)
                    }
                    style={{
                      width: '100%',
                      minHeight: 26,
                      padding: '3px 7px',
                      borderRadius: 5,
                      border: '1px solid var(--sr-accent, #0284c7)',
                      background: 'var(--sr-surface-card, transparent)',
                      color: 'inherit',
                      textAlign: hAlign,
                      fontFamily: FIELD_FONTS[fPrefs.font],
                      fontSize: '0.8rem',
                    }}
                  />
                ) : (
                  <div
                    tabIndex={0}
                    role="textbox"
                    aria-readonly="true"
                    aria-label={`${col.name}`}
                    data-form-nav-cell={`${rowIndex}:${col.name}`}
                    onFocus={() => {
                      setFocusedColName(col.name);
                      onSelectRow?.(rowIndex);
                      onFocusField?.(col.name);
                    }}
                    onBlur={() => setFocusedColName(null)}
                    onKeyDown={(ev) => handleFieldKeyNav(ev, colIdx, col)}
                    style={{
                      minHeight: 26,
                      padding: '3px 7px',
                      borderRadius: 5,
                      border:
                        focusedColName === col.name
                          ? '1.5px solid var(--sr-accent, #0284c7)'
                          : '1px solid var(--sr-border-subtle, rgba(128,128,128,0.28))',
                      background:
                        'var(--sr-surface-card, rgba(255,255,255,0.6))',
                      color: formatted.isNull
                        ? 'var(--sr-text-muted, #64748b)'
                        : 'inherit',
                      fontStyle: formatted.isNull ? 'italic' : 'normal',
                      textAlign: hAlign,
                      fontFamily: FIELD_FONTS[fPrefs.font],
                      fontSize: '0.8rem',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      outline: 'none',
                    }}
                  >
                    {formatted.text}
                  </div>
                )}

                {showHint && (
                  <div
                    role="note"
                    data-cdeadmin-qa-key={`field-comment-hint-${col.name}`}
                    style={{
                      marginTop: 2,
                      padding: '5px 8px',
                      borderRadius: 6,
                      fontSize: '0.74rem',
                      background: 'var(--sr-surface-elevated, #1e293b)',
                      color: 'var(--sr-text-primary, #f8fafc)',
                      border:
                        '1px solid var(--sr-border-default, rgba(128,128,128,0.35))',
                      boxShadow: 'var(--sr-popup-shadow)',
                      zIndex: 8,
                    }}
                  >
                    {col.comment}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

AdaptiveRecordFormCard.propTypes = {
  row: PropTypes.object.isRequired,
  rowIndex: PropTypes.number.isRequired,
  isCurrent: PropTypes.bool,
  isEditing: PropTypes.bool,
  isBookmarked: PropTypes.bool,
  draftValues: PropTypes.object,
  columns: PropTypes.array.isRequired,
  formLayout: PropTypes.object,
  formFieldPrefs: PropTypes.object.isRequired,
  fieldTypeDefaults: PropTypes.object,
  conversions: PropTypes.object,
  booleanFormat: PropTypes.string,
  localeDateFormat: PropTypes.bool,
  maxHeight: PropTypes.string,
  fullArea: PropTypes.bool,
  totalRowsInPage: PropTypes.number,
  onSelectRow: PropTypes.func,
  onFocusField: PropTypes.func,
  onFieldChange: PropTypes.func,
  onNavigateFormField: PropTypes.func,
  onToggleBookmark: PropTypes.func,
  onOpenComplexInDrawer: PropTypes.func,
  onFormContextMenu: PropTypes.func,
  onFieldContextMenu: PropTypes.func,
};
