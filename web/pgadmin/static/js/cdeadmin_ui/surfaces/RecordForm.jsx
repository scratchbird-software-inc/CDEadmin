/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {
  FIELD_FONTS,
  FIELD_FONT_SIZES,
  BOOLEAN_FORMATS,
  DISPLAY_MODES,
  buildFormLayoutPlacements,
  clampColumnWidth,
  formatCellValue,
  formatColumnCommentHint,
  inferColumnMeta,
  resolveEffectiveColumnPrefs,
  serializeValueForEdit,
} from './dataEditSurfaceHelpers';

const GUTTER_WIDTH = 62;

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
 * Includes left-side hover scrollbars on vertical overflow, prominent active-field
 * highlighting, and single-focused-field 128-character column comment hints
 * displayed directly underneath the focused editing field.
 */
export function AdaptiveRecordFormCard({
  row,
  rowIndex,
  activeColName = '',
  isCurrent,
  isEditing,
  isBookmarked = false,
  draftValues,
  columns,
  formLayout,
  formFieldPrefs,
  gridColPrefs = {},
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
  // Strictly track the single DOM-focused field inside this card ({colName, el})
  const [focusedField, setFocusedField] = useState(null);
  const [anchorRect, setAnchorRect] = useState(null);
  const focusedElRef = useRef(null);

  useEffect(() => {
    if (!focusedField?.colName || !focusedElRef.current) {
      setAnchorRect(null);
      return undefined;
    }
    const updateRect = () => {
      const el = focusedElRef.current;
      if (!el || typeof el.getBoundingClientRect !== 'function') return;
      const r = el.getBoundingClientRect();
      setAnchorRect(r);
    };
    updateRect();
    window.addEventListener('scroll', updateRect, true);
    window.addEventListener('resize', updateRect);
    return () => {
      window.removeEventListener('scroll', updateRect, true);
      window.removeEventListener('resize', updateRect);
    };
  }, [focusedField?.colName, isEditing]);

  const handleFieldFocus = (colName, el) => {
    focusedElRef.current = el || null;
    const rect =
      el && typeof el.getBoundingClientRect === 'function'
        ? el.getBoundingClientRect()
        : null;
    setFocusedField({colName});
    setAnchorRect(rect);
    onSelectRow?.(rowIndex);
    onFocusField?.(colName);
  };

  const handleFieldBlur = (colName) => {
    setFocusedField((prev) => (prev?.colName === colName ? null : prev));
  };

  const resolvedLayout = useMemo(
    () =>
      formLayout ||
      buildFormLayoutPlacements(
        columns,
        formFieldPrefs,
        720,
        null,
        row ? [row] : null,
        gridColPrefs
      ),
    [formLayout, columns, formFieldPrefs, gridColPrefs, row]
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

  const handleFieldKeyNav = (
    ev,
    colIdx,
    col,
    {isMultiline = false, isTextInput = false} = {}
  ) => {
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
      onNavigateFormField(
        maxRowIdx,
        columns[lastColIdx]?.name || col.name,
        'last_record'
      );
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
        ev.currentTarget.selectionEnd ===
          String(ev.currentTarget.value ?? '').length);

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
            ? gettext(
              'Row %s — Double-click gutter or click ! to toggle bookmark',
              row.row_number
            )
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
            const fPrefs = resolveEffectiveColumnPrefs(
              col,
              formFieldPrefs,
              fieldTypeDefaults,
              gridColPrefs
            );
            const placement = placementMap.get(col.name) || {
              row: 'auto',
              colStart: 1,
              span: 1,
            };
            const markdownEditor = fPrefs.editor === 'markdown';
            const useInlineEditor =
              fPrefs.inlineBox ||
              markdownEditor ||
              (isEditing && nativeMeta.clientType === 'json');
            const isFullRow = Boolean(useInlineEditor || placement.fullRow);
            const rawNatWidth =
              fPrefs.widthPx ||
              fPrefs.width ||
              resolvedLayout.adaptiveWidths?.[col.name] ||
              placement.naturalWidth ||
              156;
            const natWidth = clampColumnWidth(rawNatWidth, fPrefs, 156);
            const fontSizeCss = FIELD_FONT_SIZES[fPrefs.fontSize] || '0.8rem';
            const nativeValue =
              isEditing &&
              draftValues &&
              Object.prototype.hasOwnProperty.call(draftValues, col.name)
                ? draftValues[col.name]
                : row.values?.[col.name];
            const rawVal =
              conversions?.displayValue(col.name, nativeValue) ?? nativeValue;
            const colMeta =
              conversions?.pairFor(col.name) &&
              (typeof rawVal === 'string' || rawVal == null)
                ? {...nativeMeta, clientType: 'text', isComplex: false}
                : nativeMeta;
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

            const isFocusedThisCol = focusedField?.colName === col.name;
            const isSelectedField = Boolean(
              isCurrent &&
                (isFocusedThisCol ||
                  (!focusedField?.colName && activeColName === col.name))
            );
            const shouldAutoFocus = Boolean(
              isCurrent &&
                canEditField &&
                (activeColName ? activeColName === col.name : colIdx === 0)
            );

            // Strictly show ONLY ONE hint at a time, ONLY on the specific focused field while in edit mode,
            // capped to the first 128 characters of the column comment.
            const hintText = formatColumnCommentHint(col.comment);
            const showHint = Boolean(
              canEditField && isFocusedThisCol && hintText
            );
            const hasLiveRect = Boolean(
              anchorRect && (anchorRect.width > 0 || anchorRect.height > 0)
            );

            const selectedBoxBorder = isSelectedField
              ? '2px solid var(--sr-accent, #0284c7)'
              : '1px solid var(--sr-border-default, rgba(128,128,128,0.3))';
            const selectedBoxShadow = isSelectedField
              ? '0 0 0 3px rgba(2, 132, 199, 0.28)'
              : 'none';
            const readOnlyFieldBg = isSelectedField
              ? 'rgba(2, 132, 199, 0.12)'
              : fPrefs.bgColor || 'var(--sr-surface-card, rgba(255,255,255,0.75))';

            return (
              <div
                key={col.name}
                data-form-field-wrap={col.name}
                data-field-selected={isSelectedField ? 'true' : undefined}
                data-field-width-px={natWidth}
                onClick={(ev) => {
                  ev.stopPropagation();
                  onSelectRow?.(rowIndex);
                  onFocusField?.(col.name);
                }}
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
                  zIndex: showHint ? 45 : isSelectedField ? 5 : 1,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 2,
                }}
              >
                <label
                  style={{
                    fontSize: '0.71rem',
                    fontWeight: isSelectedField ? 700 : 600,
                    color: isSelectedField
                      ? 'var(--sr-accent, #0284c7)'
                      : 'var(--sr-text-secondary, #475569)',
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
                      opacity: isSelectedField ? 0.85 : 0.62,
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
                      border: selectedBoxBorder,
                      boxShadow: selectedBoxShadow,
                      background: isSelectedField
                        ? 'rgba(2, 132, 199, 0.12)'
                        : 'var(--sr-surface-subtle, rgba(128,128,128,0.05))',
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
                      onFocus={(ev) => handleFieldFocus(col.name, ev.currentTarget)}
                      onBlur={() => handleFieldBlur(col.name)}
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
                    autoFocus={shouldAutoFocus}
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
                    placeholder={
                      rawVal === null
                        ? '<null>'
                        : markdownEditor
                          ? gettext('Markdown')
                          : ''
                    }
                    onFocus={(ev) => handleFieldFocus(col.name, ev.currentTarget)}
                    onBlur={() => handleFieldBlur(col.name)}
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
                      border: selectedBoxBorder,
                      boxShadow: selectedBoxShadow,
                      outline: 'none',
                      background: canEditField
                        ? fPrefs.bgColor || 'var(--sr-surface-card, #ffffff)'
                        : readOnlyFieldBg,
                      color:
                        rawVal === null && !canEditField
                          ? 'var(--sr-text-muted, #64748b)'
                          : fPrefs.color || 'inherit',
                      fontStyle:
                        rawVal === null && !canEditField ? 'italic' : 'normal',
                      textAlign: hAlign,
                      fontFamily:
                        FIELD_FONTS[fPrefs.font] ||
                        (colMeta.clientType === 'json' || markdownEditor
                          ? 'var(--sr-font-mono, monospace)'
                          : 'inherit'),
                      fontSize: fontSizeCss,
                    }}
                  />
                ) : canEditField ? (
                  <input
                    type="text"
                    autoFocus={shouldAutoFocus}
                    aria-label={`${col.name}`}
                    data-form-nav-cell={`${rowIndex}:${col.name}`}
                    value={
                      rawVal === null || rawVal === undefined
                        ? ''
                        : serializeValueForEdit(rawVal)
                    }
                    placeholder={rawVal === null ? '<null>' : ''}
                    onFocus={(ev) => handleFieldFocus(col.name, ev.currentTarget)}
                    onBlur={() => handleFieldBlur(col.name)}
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
                      border: selectedBoxBorder,
                      boxShadow: selectedBoxShadow,
                      outline: 'none',
                      background: fPrefs.bgColor || 'var(--sr-surface-card, #ffffff)',
                      color: fPrefs.color || 'inherit',
                      textAlign: hAlign,
                      fontFamily: FIELD_FONTS[fPrefs.font],
                      fontSize: fontSizeCss,
                    }}
                  />
                ) : (
                  <div
                    tabIndex={0}
                    role="textbox"
                    aria-readonly="true"
                    aria-label={`${col.name}`}
                    data-form-nav-cell={`${rowIndex}:${col.name}`}
                    onFocus={(ev) => handleFieldFocus(col.name, ev.currentTarget)}
                    onBlur={() => handleFieldBlur(col.name)}
                    onKeyDown={(ev) => handleFieldKeyNav(ev, colIdx, col)}
                    style={{
                      minHeight: 26,
                      padding: '3px 7px',
                      borderRadius: 5,
                      border: selectedBoxBorder,
                      boxShadow: selectedBoxShadow,
                      background: readOnlyFieldBg,
                      color: formatted.isNull
                        ? 'var(--sr-text-muted, #64748b)'
                        : fPrefs.color || 'inherit',
                      fontStyle: formatted.isNull ? 'italic' : 'normal',
                      textAlign: hAlign,
                      fontFamily: FIELD_FONTS[fPrefs.font],
                      fontSize: fontSizeCss,
                      overflow: 'hidden',
                      textOverflow:
                        fPrefs.wrapMode && fPrefs.wrapMode !== 'none'
                          ? 'clip'
                          : 'ellipsis',
                      whiteSpace:
                        fPrefs.wrapMode && fPrefs.wrapMode !== 'none'
                          ? 'pre-wrap'
                          : 'nowrap',
                      display:
                        (fPrefs.wrapMode === 'clamp' ||
                          (fPrefs.wrapMode === 'wrap' &&
                            Number(fPrefs.maxWrapLines) >= 1))
                          ? '-webkit-box'
                          : 'block',
                      WebkitLineClamp:
                        fPrefs.wrapMode === 'clamp'
                          ? Math.max(1, Math.min(50, Number(fPrefs.maxWrapLines) || 3))
                          : fPrefs.wrapMode === 'wrap' &&
                              Number(fPrefs.maxWrapLines) >= 1
                            ? Math.max(1, Math.min(50, Number(fPrefs.maxWrapLines)))
                            : undefined,
                      WebkitBoxOrient:
                        (fPrefs.wrapMode === 'clamp' ||
                          (fPrefs.wrapMode === 'wrap' &&
                            Number(fPrefs.maxWrapLines) >= 1))
                          ? 'vertical'
                          : undefined,
                      wordBreak:
                        fPrefs.wrapMode && fPrefs.wrapMode !== 'none'
                          ? 'break-word'
                          : undefined,
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
                      position: hasLiveRect ? 'fixed' : 'absolute',
                      top: hasLiveRect
                        ? `${Math.round(anchorRect.bottom + 5)}px`
                        : 'calc(100% + 5px)',
                      left: hasLiveRect
                        ? `${Math.round(anchorRect.left)}px`
                        : 0,
                      width: hasLiveRect
                        ? `${Math.max(Math.round(anchorRect.width), 220)}px`
                        : 'max(100%, min(280px, 82vw))',
                      maxWidth: 'min(420px, 88vw)',
                      padding: '7px 10px',
                      borderRadius: 'var(--sr-control-radius, 7px)',
                      fontSize: '0.75rem',
                      lineHeight: 1.42,
                      background:
                        'var(--sr-surface-popover, var(--sr-surface-card, #ffffff))',
                      color: 'var(--sr-text-primary, #0f172a)',
                      border:
                        '1px solid var(--sr-border-default, rgba(128,128,128,0.35))',
                      boxShadow:
                        'var(--sr-shadow-popover, 0 8px 24px rgba(15, 23, 42, 0.18))',
                      pointerEvents: 'none',
                      zIndex: 2600,
                    }}
                  >
                    {hintText}
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
  activeColName: PropTypes.string,
  isCurrent: PropTypes.bool,
  isEditing: PropTypes.bool,
  isBookmarked: PropTypes.bool,
  draftValues: PropTypes.object,
  columns: PropTypes.array.isRequired,
  formLayout: PropTypes.object,
  formFieldPrefs: PropTypes.object.isRequired,
  gridColPrefs: PropTypes.object,
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
