/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextArea, TextField} from '../primitives/Field';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {Icon} from '../icons';
import ContextMenu from '../navigation/ContextMenu';
import {Dialog} from '../overlays/Dialog';
import {EmptyState} from '../feedback/EmptyState';
import {ProgressOverlay} from '../feedback/ProgressOverlay';
import {
  T_ACTION_STATUS,
  T_ACTION_TARGET_KIND,
} from '../actions/t_actions';
import {PROJECT_TOP_MENU_INDICES} from '../commands/MenuStructure';
import {
  useProjectInstanceScope,
  useProjectShell,
} from '../shell/ProjectShell';
import {useModalCloseGuard} from '../../helpers/ModalCloseGuard';
import {promptAbandonUncommittedWork} from '../overlays/UncommittedWorkDialog';
import SurfaceExportDialog from './SurfaceExportDialog';
import {
  BOOLEAN_FORMATS,
  DISPLAY_MODES,
  SURFACE_VIEWS,
  buildFormLayoutPlacements,
  coerceEditedValue,
  formatBytes,
  formatCellValue,
  formatRowsForExport,
  inferColumnMeta,
  isComplexOrOversizedCell,
  parseImportedRecords,
  serializeValueForEdit,
} from './dataEditSurfaceHelpers';

const DEFAULT_COL_WIDTH = 156;
const GUTTER_WIDTH = 58;
const EMPTY_ARRAY = Object.freeze([]);

function identityPolicyLabel(editable, policy, resourceKind) {
  if (editable) {
    if (String(policy).includes('db-key')) {
      return gettext('Editable (RDB$DB_KEY)');
    }
    if (String(policy).includes('view')) {
      return gettext('Editable View (PK)');
    }
    return gettext('Editable (PK)');
  }
  if (String(policy).includes('insert-without-row-identity')) {
    return gettext('Insert-only (no row identity)');
  }
  if (resourceKind === 'view') {
    return gettext('Read-only (view without mutation identity)');
  }
  return gettext('Read-only (no primary key / row identity)');
}

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
  draftValues,
  columns,
  formLayout,
  formFieldPrefs,
  booleanFormat,
  localeDateFormat,
  maxHeight,
  fullArea = false,
  onSelectRow,
  onFocusField,
  onFieldChange,
  onOpenComplexInDrawer,
  onFormContextMenu,
  onFieldContextMenu,
}) {
  const [focusedColName, setFocusedColName] = useState(null);

  const resolvedLayout = useMemo(
    () =>
      formLayout ||
      buildFormLayoutPlacements(columns, formFieldPrefs, 720),
    [formLayout, columns, formFieldPrefs]
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
        width: '100%',
        height: fullArea ? '100%' : undefined,
        minHeight: fullArea ? '100%' : undefined,
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
      {/* Left row-number & status badge */}
      <div
        style={{
          width: GUTTER_WIDTH,
          flex: `0 0 ${GUTTER_WIDTH}px`,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'flex-start',
          paddingTop: 10,
          gap: 4,
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
            display: 'grid',
            gridTemplateColumns: `repeat(${resolvedLayout.numCols}, minmax(0, 1fr))`,
            columnGap: '14px',
            rowGap: '12px',
            padding: '10px 14px 14px 10px',
            alignItems: 'start',
            width: '100%',
            boxSizing: 'border-box',
          }}
        >
          {columns.map((col) => {
            const colMeta = inferColumnMeta(col);
            const fPrefs = formFieldPrefs[col.name] || {};
            const placement = placementMap.get(col.name) || {
              row: 'auto',
              colStart: 1,
              span: 1,
            };
            const effectiveSpan = fPrefs.inlineBox
              ? resolvedLayout.numCols
              : Math.min(resolvedLayout.numCols, placement.span || 1);
            const rawVal =
              isEditing &&
              draftValues &&
              Object.prototype.hasOwnProperty.call(draftValues, col.name)
                ? draftValues[col.name]
                : row.values?.[col.name];
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
                onContextMenu={(ev) => {
                  ev.preventDefault();
                  ev.stopPropagation();
                  onSelectRow?.(rowIndex);
                  onFocusField?.(col.name);
                  onFieldContextMenu?.(ev, col, rowIndex);
                }}
                style={{
                  gridColumn: `span ${effectiveSpan}`,
                  minWidth: 0,
                  position: 'relative',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 3,
                }}
              >
                <label
                  style={{
                    fontSize: '0.73rem',
                    fontWeight: 600,
                    color: 'var(--sr-text-secondary, #475569)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 4,
                  }}
                >
                  <span
                    style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {col.name}
                    {col.key ? ' 🔑' : ''}
                  </span>
                  <span
                    style={{
                      fontSize: '0.66rem',
                      opacity: 0.65,
                      fontWeight: 400,
                    }}
                  >
                    {col.native_type || ''}
                  </span>
                </label>

                {formatted.isComplex && !fPrefs.inlineBox ? (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      minHeight: 30,
                      padding: '3px 8px',
                      borderRadius: 6,
                      border:
                        '1px solid var(--sr-border-default, rgba(128,128,128,0.3))',
                      background: 'var(--sr-surface-subtle, rgba(128,128,128,0.05))',
                    }}
                  >
                    <span style={{fontSize: '0.76rem', opacity: 0.8}}>
                      {colMeta.clientType.toUpperCase()}
                    </span>
                    <button
                      type="button"
                      className="sr-btn"
                      style={{minHeight: 22, padding: '1px 8px', fontSize: '0.75rem'}}
                      tabIndex={0}
                      onFocus={() => {
                        setFocusedColName(col.name);
                        onFocusField?.(col.name);
                      }}
                      onBlur={() => setFocusedColName(null)}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        onOpenComplexInDrawer?.(rowIndex, col);
                      }}
                    >
                      [...]
                    </button>
                  </div>
                ) : fPrefs.inlineBox ? (
                  <textarea
                    aria-label={`${col.name}`}
                    readOnly={!canEditField}
                    rows={fPrefs.rows || 4}
                    value={
                      rawVal === null || rawVal === undefined
                        ? canEditField
                          ? ''
                          : '<null>'
                        : serializeValueForEdit(rawVal)
                    }
                    placeholder={rawVal === null ? '<null>' : ''}
                    onFocus={() => {
                      setFocusedColName(col.name);
                      onFocusField?.(col.name);
                    }}
                    onBlur={() => setFocusedColName(null)}
                    onChange={(ev) =>
                      canEditField && onFieldChange?.(col.name, ev.target.value)
                    }
                    style={{
                      width: '100%',
                      resize: 'vertical',
                      minHeight: 68,
                      padding: '6px 8px',
                      borderRadius: 6,
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
                      fontFamily:
                        colMeta.clientType === 'json'
                          ? 'var(--sr-font-mono, monospace)'
                          : 'inherit',
                      fontSize: '0.8125rem',
                    }}
                  />
                ) : canEditField ? (
                  <input
                    type="text"
                    aria-label={`${col.name}`}
                    value={
                      rawVal === null || rawVal === undefined
                        ? ''
                        : serializeValueForEdit(rawVal)
                    }
                    placeholder={rawVal === null ? '<null>' : ''}
                    onFocus={() => {
                      setFocusedColName(col.name);
                      onFocusField?.(col.name);
                    }}
                    onBlur={() => setFocusedColName(null)}
                    onChange={(ev) =>
                      onFieldChange?.(col.name, ev.target.value)
                    }
                    style={{
                      width: '100%',
                      minHeight: 30,
                      padding: '4px 8px',
                      borderRadius: 6,
                      border: '1px solid var(--sr-accent, #0284c7)',
                      background: 'var(--sr-surface-card, transparent)',
                      color: 'inherit',
                      textAlign: hAlign,
                      fontSize: '0.8125rem',
                    }}
                  />
                ) : (
                  <div
                    tabIndex={0}
                    role="textbox"
                    aria-readonly="true"
                    aria-label={`${col.name}`}
                    onFocus={() => {
                      setFocusedColName(col.name);
                      onFocusField?.(col.name);
                    }}
                    onBlur={() => setFocusedColName(null)}
                    style={{
                      minHeight: 30,
                      padding: '5px 8px',
                      borderRadius: 6,
                      border:
                        '1px solid var(--sr-border-subtle, rgba(128,128,128,0.24))',
                      background:
                        'var(--sr-surface-subtle, rgba(128,128,128,0.035))',
                      color: formatted.isNull
                        ? 'var(--sr-text-muted, #64748b)'
                        : 'inherit',
                      fontStyle: formatted.isNull ? 'italic' : 'normal',
                      textAlign: hAlign,
                      fontSize: '0.8125rem',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
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
  draftValues: PropTypes.object,
  columns: PropTypes.array.isRequired,
  formLayout: PropTypes.object,
  formFieldPrefs: PropTypes.object.isRequired,
  booleanFormat: PropTypes.string,
  localeDateFormat: PropTypes.bool,
  maxHeight: PropTypes.string,
  fullArea: PropTypes.bool,
  onSelectRow: PropTypes.func,
  onFocusField: PropTypes.func,
  onFieldChange: PropTypes.func,
  onOpenComplexInDrawer: PropTypes.func,
  onFormContextMenu: PropTypes.func,
  onFieldContextMenu: PropTypes.func,
};

export default function DataEditSurface({
  endpointLabel = '',
  engineId = 'relational',
  languageProfile = '',
  databaseTargetId = null,
  targetResource = null,
  post,
  onOpenInVisualSql,
  onOpenInSqlEditor,
}) {
  const shell = useProjectShell();
  const shellRef = useRef(shell);
  shellRef.current = shell;
  const instanceScope = useProjectInstanceScope();
  const instId = instanceScope?.instanceId || 'data-surface';
  const surfaceIdRef = useRef(`ds-${instId}`);

  const [surfaceView, setSurfaceView] = useState(SURFACE_VIEWS.DATA);
  const [layout, setLayout] = useState(defaultLayoutState);
  const layoutInitializedRef = useRef(false);

  const [hostData, setHostData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [surfaceError, setSurfaceError] = useState('');

  // Navigation & Editing state
  const [activeRowIndex, setActiveRowIndex] = useState(0);
  const [activeColName, setActiveColName] = useState('');
  const [selectedCells, setSelectedCells] = useState([]); // [{rowIndex, colName}]
  const [isEditingRow, setIsEditingRow] = useState(false);
  const [editingRowIndex, setEditingRowIndex] = useState(null);
  const [rowDraft, setRowDraft] = useState(null); // { [colName]: rawValue }
  const [isInsertDraft, setIsInsertDraft] = useState(false);
  const [undoStack, setUndoStack] = useState([]);
  const [redoStack, setRedoStack] = useState([]);

  // Viewport tracking (decoupled from activeRowIndex!)
  const gridViewportRef = useRef(null);
  const areaRef = useRef(null);
  const [viewportWidth, setViewportWidth] = useState(860);
  const [scrollRowRange, setScrollRowRange] = useState({start: 0, end: 30});

  // Right Drawer (`Area 3b`) activity state
  const [drawerState, setDrawerState] = useState({
    mode: 'staged_sql', // 'complex_value' | 'column_profile' | 'filter_builder' | 'column_format' | 'staged_sql' | 'field_detail' | 'plan_detail' | 'message_detail'
    rowIndex: 0,
    column: null,
    profileData: null,
    selectedField: null,
    selectedPlanNode: null,
    selectedMessage: null,
  });

  // Popovers, Context Menus & Dialogs
  const [contextPos, setContextPos] = useState(null);
  const [contextMenuItems, setContextMenuItems] = useState([]);
  const [columnPickerOpen, setColumnPickerOpen] = useState(false);
  const [columnPickerScope, setColumnPickerScope] = useState('grid'); // 'grid' | 'form'
  const [extendedSortOpen, setExtendedSortOpen] = useState(false);
  const [extendedSortDraft, setExtendedSortDraft] = useState([]);
  const [limitsDialogOpen, setLimitsDialogOpen] = useState(false);
  const [limitsDraft, setLimitsDraft] = useState({pageSize: 200, maxRows: 1000});
  const [jumpDialogOpen, setJumpDialogOpen] = useState(false);
  const [jumpRowDraft, setJumpRowDraft] = useState('1');
  const [quickFindOpen, setQuickFindOpen] = useState(false);
  const [quickFindText, setQuickFindText] = useState('');
  const [saveLayoutDialogOpen, setSaveLayoutDialogOpen] = useState(false);
  const [layoutSaveScope, setLayoutSaveScope] = useState('specific'); // 'specific' | 'template' | 'apply_template'
  const [templateNameDraft, setTemplateNameDraft] = useState('');
  const [availableTemplates, setAvailableTemplates] = useState([]);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importTextDraft, setImportTextDraft] = useState('');
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exportFormat, setExportFormat] = useState('csv');
  const [msgSeverityFilter, setMsgSeverityFilter] = useState('all');

  useEffect(() => {
    const el = areaRef.current;
    if (!el) return undefined;
    let rafId = null;
    const isJsdom =
      typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent || '');

    const applyWidth = (rawW) => {
      const w = Math.floor(rawW || el.clientWidth || el.getBoundingClientRect?.().width || 0);
      if (w > 120) {
        setViewportWidth((prev) => (Math.abs(prev - w) >= 8 ? w : prev));
      }
    };

    const scheduleMeasure = (entries) => {
      const entryW = entries?.[0]?.contentRect?.width;
      if (isJsdom || typeof requestAnimationFrame !== 'function') {
        applyWidth(entryW);
        return;
      }
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        applyWidth(el.clientWidth || entryW);
      });
    };

    applyWidth(el.clientWidth);
    if (typeof ResizeObserver === 'function') {
      const ro = new ResizeObserver(scheduleMeasure);
      ro.observe(el);
      return () => {
        if (rafId !== null && typeof cancelAnimationFrame === 'function') {
          cancelAnimationFrame(rafId);
        }
        ro.disconnect();
      };
    }
    return undefined;
  }, []);

  const targetResourceRef = useRef(targetResource);
  targetResourceRef.current = targetResource;
  const postRef = useRef(post);
  postRef.current = post;
  const targetResourceId = targetResource?.resource_id || '';

  const callHost = useCallback(
    async (surfaceAction, extra = {}) => {
      const resp = await postRef.current({
        action: 'data_surface_action',
        request: {
          surface_id: surfaceIdRef.current,
          surface_action: surfaceAction,
          target_resource: targetResourceRef.current,
          database_target_id: databaseTargetId,
          language_profile: languageProfile,
          engine_id: engineId,
          ...extra,
        },
      });
      return resp;
    },
    [targetResourceId, databaseTargetId, languageProfile, engineId]
  );

  const applyHostResponse = useCallback((resp) => {
    if (!resp) return;
    setHostData(resp);
    setLimitsDraft({
      pageSize: resp.page_size || 200,
      maxRows: resp.max_rows || 1000,
    });
    if (!layoutInitializedRef.current && resp.saved_specific_layout) {
      layoutInitializedRef.current = true;
      setLayout((prev) => ({...prev, ...resp.saved_specific_layout}));
    } else if (!layoutInitializedRef.current && resp.columns?.length) {
      layoutInitializedRef.current = true;
      setActiveColName((cur) => cur || resp.columns[0].name);
    }
  }, []);

  const initialLoad = useCallback(async () => {
    if (!targetResourceRef.current) return;
    setLoading(true);
    setSurfaceError('');
    try {
      const resp = await callHost('open', {
        page_size: limitsDraft.pageSize,
        max_rows: limitsDraft.maxRows,
      });
      applyHostResponse(resp);
      setActiveRowIndex(0);
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setLoading(false);
    }
  }, [callHost, limitsDraft.pageSize, limitsDraft.maxRows, applyHostResponse]);

  const refreshFromServer = useCallback(async () => {
    if (!targetResourceRef.current) return;
    setWorking(true);
    setSurfaceError('');
    try {
      const resp = await callHost('refresh', {
        page_size: limitsDraft.pageSize,
        max_rows: limitsDraft.maxRows,
      });
      applyHostResponse(resp);
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setWorking(false);
    }
  }, [callHost, limitsDraft.pageSize, limitsDraft.maxRows, applyHostResponse]);

  useEffect(() => {
    initialLoad();
    // Do NOT close_surface on React unmount: switching Surface tabs in ProjectShell
    // unmounts inactive work areas while preserving the host session, buffered rows,
    // and uncommitted Firebird transaction state until explicit Surface close.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetResourceId, databaseTargetId]);

  const columns = useMemo(
    () => hostData?.columns || EMPTY_ARRAY,
    [hostData?.columns]
  );
  const rows = useMemo(() => {
    const base = hostData?.rows || EMPTY_ARRAY;
    if (isInsertDraft && rowDraft) {
      return [
        ...base,
        {
          row_number: (hostData?.total_view_rows || base.length) + 1,
          base_row_index: null,
          identity_token: '__draft_insert__',
          values: {...rowDraft},
          original_values: {},
          stage_state: 'inserted',
          isDraftInsert: true,
        },
      ];
    }
    return base;
  }, [hostData?.rows, hostData?.total_view_rows, isInsertDraft, rowDraft]);

  const gridColumns = useMemo(
    () =>
      orderedColumns(columns, layout.gridColOrder, layout.gridVisibleCols),
    [columns, layout.gridColOrder, layout.gridVisibleCols]
  );

  const formColumns = useMemo(
    () =>
      orderedColumns(columns, layout.formColOrder, layout.formVisibleCols),
    [columns, layout.formColOrder, layout.formVisibleCols]
  );

  const prevFormColsRef = useRef(null);
  const sharedFormLayout = useMemo(() => {
    const computed = buildFormLayoutPlacements(
      formColumns,
      layout.formFieldPrefs,
      viewportWidth - GUTTER_WIDTH - 36,
      prevFormColsRef.current
    );
    prevFormColsRef.current = computed.numCols;
    return computed;
  }, [formColumns, layout.formFieldPrefs, viewportWidth]);

  const currentRow = rows[activeRowIndex] || null;
  const activeColObj = useMemo(
    () => columns.find((c) => c.name === activeColName) || columns[0] || null,
    [columns, activeColName]
  );

  const openRightDrawerWith = useCallback(
    (nextDrawerPatch) => {
      setDrawerState((prev) => ({...prev, ...nextDrawerPatch}));
      const curShell = shellRef.current;
      if (curShell && instId) {
        const curInst = curShell.instances?.find((i) => i.instanceId === instId);
        if (curInst && !curInst.rightOpen) {
          curShell.toggleInstanceRightDrawer?.(instId);
        }
      }
    },
    [instId]
  );

  // Accept current row edits (explicit Accept button OR automatic on row-leave!)
  const acceptCurrentRow = useCallback(async () => {
    if (!isEditingRow || !rowDraft) {
      setIsEditingRow(false);
      setEditingRowIndex(null);
      return true;
    }
    const targetIdx = editingRowIndex ?? activeRowIndex;
    const targetRow = rows[targetIdx];
    if (!targetRow) {
      setIsEditingRow(false);
      setRowDraft(null);
      setIsInsertDraft(false);
      return true;
    }

    const coercedChanges = {};
    for (const [colName, val] of Object.entries(rowDraft)) {
      const colDef = columns.find((c) => c.name === colName);
      if (!colDef) continue;
      const meta = inferColumnMeta(colDef);
      const coerced = coerceEditedValue(val, colDef, meta);
      if (isInsertDraft || coerced !== targetRow.values?.[colName]) {
        coercedChanges[colName] = coerced;
      }
    }

    if (!isInsertDraft && Object.keys(coercedChanges).length === 0) {
      setIsEditingRow(false);
      setEditingRowIndex(null);
      setRowDraft(null);
      return true;
    }

    setWorking(true);
    try {
      const prevSnapshot = {
        rowIndex: targetIdx,
        beforeValues: {...(targetRow.values || {})},
      };
      const resp = await callHost('stage_row', {
        op: isInsertDraft ? 'insert' : 'update',
        base_row_index: isInsertDraft ? null : targetRow.base_row_index,
        identity_token: isInsertDraft ? null : targetRow.identity_token,
        changes: coercedChanges,
        window_offset: hostData?.window_offset || 0,
        window_size: hostData?.window_size || 200,
      });
      applyHostResponse(resp);
      setUndoStack((prev) => [...prev, prevSnapshot]);
      setRedoStack([]);
      setIsEditingRow(false);
      setEditingRowIndex(null);
      setRowDraft(null);
      setIsInsertDraft(false);
      return true;
    } catch (err) {
      setSurfaceError(err?.message || String(err));
      return false;
    } finally {
      setWorking(false);
    }
  }, [
    isEditingRow,
    rowDraft,
    editingRowIndex,
    activeRowIndex,
    rows,
    columns,
    isInsertDraft,
    callHost,
    hostData?.window_offset,
    hostData?.window_size,
    applyHostResponse,
  ]);

  // Select row — automatically accepts any modified row draft when leaving the row!
  const selectRowAtIndex = useCallback(
    async (nextIdx, nextColName = undefined) => {
      const clamped = Math.max(0, Math.min(nextIdx, Math.max(0, rows.length - 1)));
      if (
        isEditingRow &&
        editingRowIndex !== null &&
        editingRowIndex !== clamped
      ) {
        const ok = await acceptCurrentRow();
        if (!ok) return;
      }
      setActiveRowIndex(clamped);
      if (nextColName) {
        setActiveColName(nextColName);
        setSelectedCells([{rowIndex: clamped, colName: nextColName}]);
      }
    },
    [rows.length, isEditingRow, editingRowIndex, acceptCurrentRow]
  );

  const beginEditRow = useCallback(
    (targetIdx = activeRowIndex) => {
      if (!hostData?.editable) return;
      const r = rows[targetIdx];
      if (!r) return;
      setActiveRowIndex(targetIdx);
      setEditingRowIndex(targetIdx);
      setRowDraft({...(r.values || {})});
      setIsInsertDraft(false);
      setIsEditingRow(true);
    },
    [activeRowIndex, hostData?.editable, rows]
  );

  const beginInsertRow = useCallback(
    async (duplicateCurrent = false) => {
      if (isEditingRow) {
        const ok = await acceptCurrentRow();
        if (!ok) return;
      }
      const seed = {};
      if (duplicateCurrent && currentRow?.values) {
        for (const col of columns) {
          if (!col.key) {
            seed[col.name] = currentRow.values[col.name];
          }
        }
      }
      setRowDraft(seed);
      setIsInsertDraft(true);
      setIsEditingRow(true);
      const nextIdx = rows.length;
      setActiveRowIndex(nextIdx);
      setEditingRowIndex(nextIdx);
    },
    [isEditingRow, acceptCurrentRow, currentRow, columns, rows.length]
  );

  const cancelRowDraft = useCallback(() => {
    setIsEditingRow(false);
    setEditingRowIndex(null);
    setRowDraft(null);
    if (isInsertDraft) {
      setIsInsertDraft(false);
      setActiveRowIndex((idx) => Math.max(0, idx - 1));
    }
  }, [isInsertDraft]);

  const handleDeleteCurrentRow = useCallback(async () => {
    if (!currentRow || currentRow.base_row_index === null) return;
    setWorking(true);
    try {
      const resp = await callHost('stage_row', {
        op: 'delete',
        base_row_index: currentRow.base_row_index,
        identity_token: currentRow.identity_token,
        window_offset: hostData?.window_offset || 0,
        window_size: hostData?.window_size || 200,
      });
      applyHostResponse(resp);
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setWorking(false);
    }
  }, [currentRow, callHost, hostData?.window_offset, hostData?.window_size, applyHostResponse]);

  const handleRevertCurrentRow = useCallback(async () => {
    if (isEditingRow) {
      cancelRowDraft();
      return;
    }
    if (currentRow?.mutation_id) {
      setWorking(true);
      try {
        const resp = await callHost('revert_row', {
          row_key: currentRow.mutation_id,
          window_offset: hostData?.window_offset || 0,
          window_size: hostData?.window_size || 200,
        });
        applyHostResponse(resp);
      } catch (err) {
        setSurfaceError(err?.message || String(err));
      } finally {
        setWorking(false);
      }
    }
  }, [
    isEditingRow,
    cancelRowDraft,
    currentRow?.mutation_id,
    callHost,
    hostData?.window_offset,
    hostData?.window_size,
    applyHostResponse,
  ]);

  const handleCommitBatch = useCallback(async () => {
    if (isEditingRow) {
      const ok = await acceptCurrentRow();
      if (!ok) return;
    }
    setWorking(true);
    try {
      const resp = await callHost('commit_batch', {
        window_offset: hostData?.window_offset || 0,
        window_size: hostData?.window_size || 200,
      });
      applyHostResponse(resp);
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setWorking(false);
    }
  }, [isEditingRow, acceptCurrentRow, callHost, hostData?.window_offset, hostData?.window_size, applyHostResponse]);

  const handleRollbackBatch = useCallback(async () => {
    cancelRowDraft();
    setWorking(true);
    try {
      const resp = await callHost('rollback_batch', {
        window_offset: 0,
        window_size: hostData?.window_size || 200,
      });
      applyHostResponse(resp);
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setWorking(false);
    }
  }, [cancelRowDraft, callHost, hostData?.window_size, applyHostResponse]);

  const handleToggleColumnSort = useCallback(
    async (colName) => {
      const curSorts = hostData?.sorts || [];
      const existing = curSorts.find((s) => s.column === colName);
      let nextSorts;
      if (!existing) {
        nextSorts = [{column: colName, direction: 'asc'}];
      } else if (existing.direction === 'asc') {
        nextSorts = [{column: colName, direction: 'desc'}];
      } else {
        nextSorts = [];
      }
      setWorking(true);
      try {
        const resp = await callHost('sort_filter', {
          sorts: nextSorts,
          window_offset: 0,
          window_size: hostData?.window_size || 200,
        });
        applyHostResponse(resp);
      } catch (err) {
        setSurfaceError(err?.message || String(err));
      } finally {
        setWorking(false);
      }
    },
    [hostData?.sorts, hostData?.window_size, callHost, applyHostResponse]
  );

  const handleToggleSortLocation = useCallback(async () => {
    const currentExec = hostData?.sort_execution || 'local';
    const nextMode = currentExec === 'local' ? 'server' : 'local';
    setWorking(true);
    try {
      const resp = await callHost(nextMode === 'server' ? 'refresh' : 'sort_filter', {
        sort_mode: nextMode,
      });
      applyHostResponse(resp);
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setWorking(false);
    }
  }, [hostData?.sort_execution, callHost, applyHostResponse]);

  const locateCurrentRow = useCallback(() => {
    const vp = gridViewportRef.current;
    if (!vp) return;
    const rowEl = vp.querySelector(`[data-surface-row-idx="${activeRowIndex}"]`);
    if (rowEl && typeof rowEl.scrollIntoView === 'function') {
      rowEl.scrollIntoView({block: 'center', inline: 'nearest'});
    }
  }, [activeRowIndex]);

  const navigatePage = useCallback(
    async (nextOffset) => {
      if (isEditingRow) {
        const ok = await acceptCurrentRow();
        if (!ok) return;
      }
      setWorking(true);
      try {
        const resp = await callHost('read_window', {
          window_offset: Math.max(0, nextOffset),
          window_size: hostData?.window_size || 200,
        });
        applyHostResponse(resp);
        setActiveRowIndex(0);
      } catch (err) {
        setSurfaceError(err?.message || String(err));
      } finally {
        setWorking(false);
      }
    },
    [isEditingRow, acceptCurrentRow, callHost, hostData?.window_size, applyHostResponse]
  );

  const setColumnPref = useCallback((colName, patch) => {
    if (!colName) return;
    setLayout((prev) => ({
      ...prev,
      gridColPrefs: {
        ...prev.gridColPrefs,
        [colName]: {...(prev.gridColPrefs[colName] || {}), ...patch},
      },
      formFieldPrefs: {
        ...prev.formFieldPrefs,
        [colName]: {...(prev.formFieldPrefs[colName] || {}), ...patch},
      },
    }));
  }, []);

  const copySelection = useCallback(
    (fmt = 'tsv') => {
      const targetRows = currentRow ? [currentRow] : rows;
      const text = formatRowsForExport(
        fmt === 'tsv' && currentRow && activeColName
          ? [{values: {[activeColName]: currentRow.values?.[activeColName]}}]
          : targetRows,
        fmt === 'tsv' && currentRow && activeColName && activeColObj
          ? [activeColObj]
          : gridColumns,
        fmt,
        targetResource?.display_name || 'TABLE'
      );
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(text).catch(() => {});
      }
    },
    [currentRow, rows, activeColName, activeColObj, gridColumns, targetResource?.display_name]
  );

  // Determine effective layout mode (handling (e) Hybrid-When-Editing!)
  const effectiveDisplayMode = useMemo(() => {
    if (layout.displayMode !== DISPLAY_MODES.HYBRID_EDIT) {
      return layout.displayMode;
    }
    if (!isEditingRow) {
      return DISPLAY_MODES.GRID;
    }
    return layout.hybridEditTarget === 'single_form'
      ? DISPLAY_MODES.SINGLE_FORM
      : DISPLAY_MODES.HYBRID;
  }, [layout.displayMode, layout.hybridEditTarget, isEditingRow]);

  const stagedTotal = hostData?.metrics_view?.transaction?.staged_total || 0;
  const isRowDraftDirty = useMemo(() => {
    if (!isEditingRow || !rowDraft) return false;
    if (isInsertDraft) {
      return Object.values(rowDraft).some(
        (v) => v !== null && v !== undefined && v !== ''
      );
    }
    const baseVals = rows[editingRowIndex ?? activeRowIndex]?.values || {};
    return Object.keys(rowDraft).some((k) => {
      const a = rowDraft[k];
      const b = baseVals[k];
      if (a === b) return false;
      if ((a === null || a === undefined || a === '') && (b === null || b === undefined)) {
        return false;
      }
      return String(a ?? '') !== String(b ?? '');
    });
  }, [isEditingRow, rowDraft, isInsertDraft, rows, editingRowIndex, activeRowIndex]);

  const beforeSurfaceClose = useCallback(async () => {
    if (handlersRef.current.working) return false;
    const curHost = handlersRef.current.hostData;
    const curStaged = curHost?.metrics_view?.transaction?.staged_total || 0;
    const hostDirty = Boolean(
      curHost?.has_uncommitted_activity ||
      curHost?.metrics_view?.transaction?.has_uncommitted_activity
    );
    const draftDirty = Boolean(handlersRef.current.isRowDraftDirty);
    const hasUncommittedActivity = Boolean(
      (!curHost?.autocommit && (curStaged > 0 || hostDirty || draftDirty)) ||
      (curHost?.autocommit && draftDirty)
    );

    if (!hasUncommittedActivity) {
      await handlersRef.current.callHost('close_surface').catch(() => {});
      return true;
    }

    const isFirebird =
      languageProfile === 'firebird-sql' ||
      String(engineId).toLowerCase().includes('firebird');
    const objTitle =
      targetResourceRef.current?.display_name ||
      String(targetResourceRef.current?.resource_id || '').split(':').pop() ||
      '';
    const decision = await promptAbandonUncommittedWork({
      surfaceTitle: objTitle ? `data: ${objTitle}` : '',
      isFirebird,
    });

    if (decision === 'cancel') {
      return false;
    }
    if (decision === 'yes') {
      setIsEditingRow(false);
      setEditingRowIndex(null);
      setRowDraft(null);
      setIsInsertDraft(false);
      await handlersRef.current.callHost('rollback_batch').catch(() => {});
      await handlersRef.current.callHost('close_surface').catch(() => {});
      return true;
    }
    if (decision === 'no') {
      try {
        if (handlersRef.current.isEditingRow && handlersRef.current.isRowDraftDirty) {
          const ok = await handlersRef.current.acceptCurrentRow();
          if (!ok) return false;
        }
        if (!handlersRef.current.hostData?.autocommit) {
          await handlersRef.current.callHost('commit_batch');
        }
        await handlersRef.current.callHost('close_surface').catch(() => {});
        return true;
      } catch (err) {
        setSurfaceError(err?.message || String(err));
        return false;
      }
    }
    return false;
  }, [engineId, languageProfile]);

  useModalCloseGuard(() => (shell ? true : handlersRef.current.beforeSurfaceClose()));
  const errorWarnCount = useMemo(
    () =>
      (hostData?.messages || []).filter(
        (m) => m.severity === 'error' || m.severity === 'warning'
      ).length,
    [hostData?.messages]
  );

  const activeColPrefs = (activeColName && layout.gridColPrefs[activeColName]) || {};
  const activeColHAlign =
    activeColPrefs.hAlign ||
    (activeColObj ? inferColumnMeta(activeColObj).defaultAlignment : 'left');
  const activeColVAlign = activeColPrefs.vAlign || 'middle';
  const activeColWrap = activeColPrefs.wrapMode || 'none';

  // Keep a mutable ref to latest handlers so TiB actions never go stale
  const handlersRef = useRef({});
  handlersRef.current = {
    setSurfaceView,
    setLayout,
    locateCurrentRow,
    selectRowAtIndex,
    navigatePage,
    acceptCurrentRow,
    beginEditRow,
    beginInsertRow,
    handleDeleteCurrentRow,
    handleRevertCurrentRow,
    handleCommitBatch,
    handleRollbackBatch,
    handleToggleSortLocation,
    setColumnPref,
    copySelection,
    initialLoad,
    refreshFromServer,
    beforeSurfaceClose,
    openRightDrawerWith,
    setColumnPickerScope,
    setColumnPickerOpen,
    setLimitsDialogOpen,
    setJumpDialogOpen,
    setQuickFindOpen,
    setSaveLayoutDialogOpen,
    setImportDialogOpen,
    setExportDialogOpen,
    callHost,
    applyHostResponse,
    activeRowIndex,
    activeColName,
    isEditingRow,
    isRowDraftDirty,
    working,
    rows,
    hostData,
    layout,
  };

  // =========================================================================
  // Right Drawer (`Area 3b`) Renderer — Context-Adaptive to Current Activity
  // =========================================================================
  const renderRightDrawerContent = useCallback(() => {
    const stagedList = hostData?.sql_view?.staged_sql || [];

    if (drawerState.mode === 'complex_value' && drawerState.column) {
      const col = drawerState.column;
      const meta = inferColumnMeta(col);
      const rIdx = drawerState.rowIndex ?? activeRowIndex;
      const row = rows[rIdx];
      const canEdit =
        isEditingRow &&
        (editingRowIndex ?? activeRowIndex) === rIdx &&
        col.editable !== false;
      const val =
        canEdit &&
        rowDraft &&
        Object.prototype.hasOwnProperty.call(rowDraft, col.name)
          ? rowDraft[col.name]
          : row?.values?.[col.name];
      const textRepr = serializeValueForEdit(val);

      return (
        <Box
          data-cdeadmin-qa-key="data-surface-3b-complex-viewer"
          sx={{p: 1.5, display: 'flex', flexDirection: 'column', gap: 1.25, height: '100%'}}
        >
          <Box sx={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1}}>
            <div>
              <strong style={{fontSize: '0.86rem'}}>{col.name}</strong>
              <div style={{fontSize: '0.72rem', opacity: 0.7}}>
                {col.native_type || meta.clientType.toUpperCase()} · {gettext('Row')} #{row?.row_number || rIdx + 1} ·{' '}
                <strong>{canEdit ? gettext('Editing Mode') : gettext('Viewing Mode')}</strong>
              </div>
            </div>
            {!canEdit && hostData?.editable && (
              <Button size="small" onClick={() => beginEditRow(rIdx)}>
                {gettext('Edit Row')}
              </Button>
            )}
          </Box>

          {val === null || val === undefined ? (
            <Box
              sx={{
                p: 2,
                borderRadius: 1.5,
                border: '1px dashed var(--sr-border-default)',
                fontStyle: 'italic',
                color: 'var(--sr-text-muted)',
              }}
            >
              {'<null>'}
            </Box>
          ) : null}

          <textarea
            aria-label={`${col.name} ${canEdit ? 'editor' : 'viewer'}`}
            readOnly={!canEdit}
            value={val === null || val === undefined ? '' : textRepr}
            placeholder={val === null ? '<null>' : ''}
            onChange={(ev) => {
              if (!canEdit) return;
              setRowDraft((prev) => ({...(prev || {}), [col.name]: ev.target.value}));
            }}
            style={{
              flex: 1,
              minHeight: 220,
              width: '100%',
              padding: '8px 10px',
              borderRadius: 8,
              border: '1px solid var(--sr-border-default)',
              background: 'var(--sr-surface-card)',
              color: 'inherit',
              fontFamily: 'var(--sr-font-mono, monospace)',
              fontSize: '0.8rem',
              resize: 'vertical',
            }}
          />

          <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap'}}>
            {canEdit && col.nullable !== false && (
              <Button
                size="small"
                onClick={() =>
                  setRowDraft((prev) => ({...(prev || {}), [col.name]: null}))
                }
              >
                {gettext('Set <null>')}
              </Button>
            )}
            {canEdit && meta.clientType === 'json' && (
              <Button
                size="small"
                onClick={() => {
                  try {
                    const pretty = JSON.stringify(JSON.parse(textRepr), null, 2);
                    setRowDraft((prev) => ({...(prev || {}), [col.name]: pretty}));
                  } catch {
                    // Leave invalid JSON as-is so user can fix syntax
                  }
                }}
              >
                {gettext('Format JSON')}
              </Button>
            )}
            {canEdit && (
              <Button intent="primary" size="small" onClick={acceptCurrentRow}>
                {gettext('Accept Row')}
              </Button>
            )}
          </Box>
        </Box>
      );
    }

    if (drawerState.mode === 'column_profile' && drawerState.profileData) {
      const prof = drawerState.profileData;
      return (
        <Box
          data-cdeadmin-qa-key="data-surface-3b-column-profile"
          sx={{p: 1.5, display: 'grid', gap: 1.25}}
        >
          <strong>
            {gettext('Column Profile')}: {prof.column}
          </strong>
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: '0.78rem'}}>
            <div>{gettext('Total Rows')}: <strong>{prof.total_rows}</strong></div>
            <div>{gettext('Distinct')}: <strong>{prof.distinct_count}</strong></div>
            <div>{gettext('Nulls')}: <strong>{prof.null_count}</strong></div>
            <div>{gettext('Non-Null')}: <strong>{prof.non_null_count}</strong></div>
            <div>{gettext('Min')}: <strong>{prof.min_value ?? '<null>'}</strong></div>
            <div>{gettext('Max')}: <strong>{prof.max_value ?? '<null>'}</strong></div>
          </div>
          <div style={{fontSize: '0.76rem', fontWeight: 600, marginTop: 4}}>
            {gettext('Top Distinct Values')}
          </div>
          <div style={{display: 'grid', gap: 4}}>
            {(prof.top_values || []).map((tv, i) => (
              <button
                key={i}
                type="button"
                className="sr-btn"
                style={{justifyContent: 'space-between', fontSize: '0.75rem'}}
                onClick={async () => {
                  const nextFilters = [
                    ...(hostData?.filters || []).filter((f) => f.column !== prof.column),
                    {column: prof.column, op: 'eq', value: tv.value},
                  ];
                  const resp = await callHost('sort_filter', {filters: nextFilters});
                  applyHostResponse(resp);
                }}
              >
                <span style={{overflow: 'hidden', textOverflow: 'ellipsis'}}>{tv.value}</span>
                <span>{tv.count}</span>
              </button>
            ))}
          </div>
        </Box>
      );
    }

    if (drawerState.mode === 'filter_builder') {
      const curFilters = hostData?.filters || [];
      return (
        <FilterBuilderDrawerPanel
          columns={columns}
          initialColumn={drawerState.column?.name || activeColName}
          filters={curFilters}
          onApply={async (nextFilters) => {
            setWorking(true);
            try {
              const resp = await callHost('sort_filter', {filters: nextFilters});
              applyHostResponse(resp);
            } catch (err) {
              setSurfaceError(err?.message || String(err));
            } finally {
              setWorking(false);
            }
          }}
        />
      );
    }

    if (drawerState.mode === 'column_format' && drawerState.column) {
      const col = drawerState.column;
      const cPrefs = layout.gridColPrefs[col.name] || {};
      return (
        <Box sx={{p: 1.5, display: 'grid', gap: 1.5}}>
          <strong>
            {gettext('Display Format')}: {col.name}
          </strong>
          <div className="sr-field">
            <label className="sr-field-label">{gettext('Boolean Style')}</label>
            <select
              className="sr-input"
              value={layout.booleanFormat}
              onChange={(e) =>
                setLayout((prev) => ({...prev, booleanFormat: e.target.value}))
              }
            >
              {Object.values(BOOLEAN_FORMATS).map((bf) => (
                <option key={bf} value={bf}>
                  {bf}
                </option>
              ))}
            </select>
          </div>
          <div className="sr-field">
            <label className="sr-field-label">{gettext('Numeric Decimals')}</label>
            <input
              type="number"
              className="sr-input"
              min={0}
              max={12}
              value={cPrefs.decimals ?? ''}
              placeholder={gettext('Native')}
              onChange={(e) =>
                setColumnPref(col.name, {
                  decimals:
                    e.target.value === '' ? undefined : Number(e.target.value),
                })
              }
            />
          </div>
          <label style={{display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.8rem'}}>
            <input
              type="checkbox"
              checked={Boolean(layout.localeDateFormat)}
              onChange={(e) =>
                setLayout((prev) => ({
                  ...prev,
                  localeDateFormat: e.target.checked,
                }))
              }
            />
            {gettext('Format Dates/Timestamps using user locale & timezone')}
          </label>
        </Box>
      );
    }

    if (drawerState.mode === 'field_detail' && drawerState.selectedField) {
      const fld = drawerState.selectedField;
      return (
        <Box sx={{p: 1.5, display: 'grid', gap: 1}}>
          <strong>
            {fld.name} ({fld.native_type})
          </strong>
          <div style={{fontSize: '0.78rem', display: 'grid', gap: 6}}>
            <div>{gettext('Domain / UDT')}: <strong>{fld.domain_type}</strong></div>
            <div>{gettext('Client Mapping')}: <strong>{fld.client_type}</strong></div>
            <div>{gettext('Key / Role')}: <strong>{fld.key_role || '—'}</strong></div>
            <div>{gettext('Nullable')}: <strong>{fld.nullable ? 'YES' : 'NO'}</strong></div>
            <div>{gettext('Default')}: <code>{fld.default_expression || '—'}</code></div>
            <div>{gettext('Computed')}: <code>{fld.computed_expression || '—'}</code></div>
            <div>{gettext('Charset / Collation')}: <strong>{fld.charset} / {fld.collation}</strong></div>
            {fld.comment && <div>{gettext('Comment')}: {fld.comment}</div>}
          </div>
        </Box>
      );
    }

    if (drawerState.mode === 'message_detail' && drawerState.selectedMessage) {
      const m = drawerState.selectedMessage;
      return (
        <Box sx={{p: 1.5, display: 'grid', gap: 1}}>
          <strong>
            [{m.severity?.toUpperCase()}] {m.operation}
          </strong>
          <div style={{fontSize: '0.75rem', opacity: 0.75}}>{m.timestamp}</div>
          <div style={{whiteSpace: 'pre-wrap', fontSize: '0.82rem'}}>{m.message}</div>
          {m.sqlstate && <div style={{fontSize: '0.78rem'}}>SQLSTATE: <code>{m.sqlstate}</code></div>}
          {typeof m.row_index === 'number' && (
            <Button
              size="small"
              intent="primary"
              onClick={() => {
                setSurfaceView(SURFACE_VIEWS.DATA);
                setActiveRowIndex(m.row_index);
                if (m.column_name) setActiveColName(m.column_name);
              }}
            >
              {gettext('Jump to Row #%s', m.row_index + 1)}
            </Button>
          )}
        </Box>
      );
    }

    // Default / SQL / Staged Batch Inspector in Right Drawer (`3b`)
    return (
      <Box
        data-cdeadmin-qa-key="data-surface-3b-staged-sql"
        sx={{p: 1.5, display: 'grid', gap: 1.25}}
      >
        <Box sx={{display: 'flex', alignItems: 'center', justifyContent: 'space-between'}}>
          <strong style={{fontSize: '0.85rem'}}>
            {gettext('Staged Batch SQL (%s)', stagedList.length)}
          </strong>
          {stagedList.length > 0 && (
            <Box sx={{display: 'flex', gap: 0.5}}>
              <Button size="small" intent="primary" onClick={handleCommitBatch}>
                {gettext('Commit')}
              </Button>
              <Button size="small" onClick={handleRollbackBatch}>
                {gettext('Rollback')}
              </Button>
            </Box>
          )}
        </Box>
        {stagedList.length === 0 ? (
          <div style={{fontSize: '0.78rem', opacity: 0.75}}>
            {gettext(
              'No pending staged row mutations. Accepted edits accumulate here when Autocommit is OFF.'
            )}
          </div>
        ) : (
          stagedList.map((st) => (
            <div
              key={st.mutation_id}
              style={{
                padding: '8px 10px',
                borderRadius: 8,
                border: '1px solid var(--sr-border-default)',
                background: 'var(--sr-surface-card)',
                display: 'grid',
                gap: 6,
              }}
            >
              <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.74rem'}}>
                <strong>{st.op.toUpperCase()} · {st.row_key}</strong>
                <button
                  type="button"
                  className="sr-btn"
                  style={{minHeight: 20, padding: '0 6px', fontSize: '0.7rem'}}
                  onClick={async () => {
                    const resp = await callHost('revert_row', {
                      row_key: st.mutation_id,
                    });
                    applyHostResponse(resp);
                  }}
                >
                  {gettext('Revert')}
                </button>
              </div>
              <pre
                style={{
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'var(--sr-font-mono, monospace)',
                  fontSize: '0.74rem',
                }}
              >
                {st.sql || `${st.op.toUpperCase()} (${st.row_key})`}
              </pre>
            </div>
          ))
        )}
      </Box>
    );
  }, [
    hostData,
    drawerState,
    activeRowIndex,
    rows,
    isEditingRow,
    editingRowIndex,
    rowDraft,
    beginEditRow,
    acceptCurrentRow,
    callHost,
    applyHostResponse,
    columns,
    activeColName,
    layout.gridColPrefs,
    layout.booleanFormat,
    layout.localeDateFormat,
    setColumnPref,
    handleCommitBatch,
    handleRollbackBatch,
  ]);

  // =========================================================================
  // Bottom Status Bar (`Area 4`) Renderer
  // =========================================================================
  const renderStatusBarContent = useCallback(() => {
    const objName =
      targetResource?.display_name ||
      String(targetResource?.resource_id || '').split(':').pop() ||
      'Object';
    const targetPath = [endpointLabel, objName].filter(Boolean).join(' · ');
    const idLabel = identityPolicyLabel(
      hostData?.editable,
      hostData?.identity_policy,
      targetResource?.resource_kind
    );
    const totalRows = hostData?.total_view_rows ?? rows.length;
    const winOffset = hostData?.window_offset || 0;
    const winSize = hostData?.window_size || 200;
    const totalPages = Math.max(1, Math.ceil(Math.max(1, totalRows) / winSize));
    const curPage = Math.floor(winOffset / winSize) + 1;
    const globalRowNum = totalRows > 0 ? winOffset + activeRowIndex + 1 : 0;
    const isRowOffscreen =
      surfaceView === SURFACE_VIEWS.DATA &&
      effectiveDisplayMode === DISPLAY_MODES.GRID &&
      rows.length > 0 &&
      (activeRowIndex < scrollRowRange.start || activeRowIndex > scrollRowRange.end);

    const timings = hostData?.metrics_view?.timings_ms || {};
    const autoCommitOn = Boolean(hostData?.autocommit);

    // Multi-cell numeric selection summary
    let selectionLabel = activeColName
      ? `${gettext('Row')} ${globalRowNum} · ${activeColName}`
      : `${gettext('Row')} ${globalRowNum}`;
    if (selectedCells.length > 1) {
      let sum = 0;
      let numCnt = 0;
      for (const sc of selectedCells) {
        const v = rows[sc.rowIndex]?.values?.[sc.colName];
        if (v !== null && v !== undefined && Number.isFinite(Number(v))) {
          sum += Number(v);
          numCnt += 1;
        }
      }
      selectionLabel =
        numCnt > 0
          ? `${selectedCells.length} ${gettext('cells')} · ${gettext('Sum')}: ${sum.toLocaleString()}`
          : `${selectedCells.length} ${gettext('cells selected')}`;
    }

    const chipStyle = {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '1px 7px',
      borderRadius: 999,
      border: '1px solid var(--sr-border-subtle, rgba(128,128,128,0.25))',
      fontSize: '0.73rem',
      whiteSpace: 'nowrap',
    };

    return (
      <div
        data-cdeadmin-qa-key="data-surface-status-bar"
        style={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 6,
          width: '100%',
        }}
      >
        <span style={chipStyle}>
          <strong>{targetPath}</strong>
        </span>
        <span style={chipStyle}>{idLabel}</span>
        <span style={chipStyle}>
          {gettext('Row')} {globalRowNum}/{totalRows} · {gettext('Page')} {curPage}/{totalPages} · {gettext('Limit')} {hostData?.max_rows || 1000}
        </span>
        {isRowOffscreen && (
          <button
            type="button"
            onClick={locateCurrentRow}
            style={{
              ...chipStyle,
              cursor: 'pointer',
              background: 'var(--sr-surface-selected)',
              color: 'var(--sr-accent)',
              fontWeight: 600,
            }}
          >
            ⌖ {gettext('Jump to Row %s', globalRowNum)}
          </button>
        )}
        <span style={chipStyle}>
          {gettext('Sort')}: {hostData?.sort_execution === 'server' ? gettext('Server') : gettext('Local (Host)')}
        </span>
        <span style={chipStyle}>
          {gettext('Fetch')}: {timings.execute_ms ?? 0} ms · {gettext('Total')}: {timings.total_ms ?? 0} ms
        </span>
        <span style={chipStyle}>
          {isEditingRow ? `${gettext('Editing Row')} ${globalRowNum} · ` : ''}
          {gettext('Staged')}: {stagedTotal} · {gettext('Autocommit')} {autoCommitOn ? 'ON' : 'OFF'}
        </span>
        <span style={chipStyle}>{selectionLabel}</span>
        {errorWarnCount > 0 && (
          <button
            type="button"
            onClick={() => setSurfaceView(SURFACE_VIEWS.MESSAGES)}
            style={{
              ...chipStyle,
              cursor: 'pointer',
              borderColor: 'var(--sr-warning)',
              fontWeight: 600,
            }}
          >
            ⚠ {errorWarnCount} {gettext('Log Alerts')}
          </button>
        )}
      </div>
    );
  }, [
    targetResource,
    endpointLabel,
    hostData,
    rows,
    activeRowIndex,
    surfaceView,
    effectiveDisplayMode,
    scrollRowRange,
    activeColName,
    selectedCells,
    isEditingRow,
    stagedTotal,
    errorWarnCount,
    locateCurrentRow,
  ]);

  // =========================================================================
  // Register MS-Grouped Tabbed-Icon-Bar (`Area 2`), Quick Save/Undo/Redo, 3b & 4
  // =========================================================================
  const renderRightDrawerRef = useRef(renderRightDrawerContent);
  renderRightDrawerRef.current = renderRightDrawerContent;
  const renderStatusBarRef = useRef(renderStatusBarContent);
  renderStatusBarRef.current = renderStatusBarContent;
  const stableRenderRightDrawer = useCallback(
    () => renderRightDrawerRef.current(),
    []
  );
  const stableRenderStatusBar = useCallback(
    () => renderStatusBarRef.current(),
    []
  );

  const registeredActionIdsRef = useRef([]);

  useEffect(
    () => () => {
      const curShell = shellRef.current;
      (registeredActionIdsRef.current || []).forEach((id) =>
        curShell?.actionsRegistry?.unregister?.(id)
      );
    },
    [instId]
  );

  useEffect(() => {
    const curShell = shellRef.current;
    if (!curShell || !instId) return undefined;
    const pfx = `ds.${instId}`;
    const regActions = [];

    const reg = (
      suffix,
      icon,
      text,
      invoke,
      {
        enabled = true,
        checked = undefined,
        value = undefined,
        shortcut = undefined,
      } = {}
    ) => {
      const id = `${pfx}.${suffix}`;
      regActions.push({
        id,
        icon,
        application: 'data-navigator',
        defaultText: text,
        defaultHint: text,
        focusScoped: true,
        status: enabled ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
        ...(typeof checked === 'boolean' ? {checked} : {}),
        ...(value !== undefined ? {value} : {}),
        ...(shortcut ? {shortcut} : {}),
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke},
      });
      return id;
    };

    // Delegate upper-left Quick-Access Save / Undo / Redo to this Surface!
    regActions.push({
      id: `file.save.${instId}`,
      icon: 'action.save',
      defaultText: gettext('Save Surface Layout / Template'),
      status: T_ACTION_STATUS.ENABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: async () => {
          const tplResp = await handlersRef.current
            .callHost('list_templates')
            .catch(() => ({templates: []}));
          setAvailableTemplates(tplResp?.templates || []);
          setSaveLayoutDialogOpen(true);
        },
      },
    });
    regActions.push({
      id: `edit.undo.${instId}`,
      icon: 'action.undo',
      defaultText: gettext('Undo Row Edit'),
      status:
        isEditingRow || undoStack.length > 0
          ? T_ACTION_STATUS.ENABLED
          : T_ACTION_STATUS.DISABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        invoke: () => handlersRef.current.handleRevertCurrentRow(),
      },
    });
    regActions.push({
      id: `edit.redo.${instId}`,
      icon: 'action.redo',
      defaultText: gettext('Redo'),
      status:
        redoStack.length > 0
          ? T_ACTION_STATUS.ENABLED
          : T_ACTION_STATUS.DISABLED,
      target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => {}},
    });

    // Pill 1: Surface Content Requested Pill ([ Data | Metrics | SQL | Fields | Messages ])
    const contentPillId = reg(
      'content_pill',
      'action.browse_data',
      gettext('Surface Aspect'),
      (detail) => {
        if (detail?.item) handlersRef.current.setSurfaceView(detail.item);
      },
      {value: surfaceView}
    );

    // Pill 2: Data Display Layout Pill ([ Grid | Mini-Forms | Hybrid | Single Form | Hybrid-on-Edit ])
    const displayPillId = reg(
      'display_pill',
      'action.layout_grid',
      gettext('Display Layout'),
      (detail) => {
        if (detail?.item) {
          handlersRef.current.setLayout((prev) => ({
            ...prev,
            displayMode: detail.item,
          }));
          handlersRef.current.setSurfaceView(SURFACE_VIEWS.DATA);
        }
      },
      {value: layout.displayMode}
    );

    // Hybrid-on-Edit Target Pill ([ Mini-Form | Single Form ])
    const hybridTargetPillId = reg(
      'hybrid_target_pill',
      'action.layout_mini_forms',
      gettext('Edit Form Target'),
      (detail) => {
        if (detail?.item) {
          handlersRef.current.setLayout((prev) => ({
            ...prev,
            hybridEditTarget: detail.item,
          }));
        }
      },
      {
        enabled: layout.displayMode === DISPLAY_MODES.HYBRID_EDIT,
        value: layout.hybridEditTarget,
      }
    );

    // Navigate Group
    const totalRows = hostData?.total_view_rows ?? rows.length;
    const winOff = hostData?.window_offset || 0;
    const winSz = hostData?.window_size || 200;
    const locateId = reg(
      'locate_row',
      'action.locate_row',
      gettext('Locate Row'),
      () => handlersRef.current.locateCurrentRow(),
      {enabled: rows.length > 0}
    );
    const navFirstId = reg(
      'nav_first',
      'action.nav_first',
      gettext('First Row'),
      () => {
        if (winOff > 0) handlersRef.current.navigatePage(0);
        else handlersRef.current.selectRowAtIndex(0);
      },
      {enabled: totalRows > 0 && (winOff > 0 || activeRowIndex > 0)}
    );
    const navPrevPageId = reg(
      'nav_prev_page',
      'action.nav_prev_page',
      gettext('Previous Page'),
      () => handlersRef.current.navigatePage(Math.max(0, winOff - winSz)),
      {enabled: winOff > 0}
    );
    const navPrevRowId = reg(
      'nav_prev_row',
      'action.nav_prev_row',
      gettext('Previous Row'),
      () => handlersRef.current.selectRowAtIndex(activeRowIndex - 1),
      {enabled: activeRowIndex > 0}
    );
    const navNextRowId = reg(
      'nav_next_row',
      'action.nav_next_row',
      gettext('Next Row'),
      () => handlersRef.current.selectRowAtIndex(activeRowIndex + 1),
      {enabled: activeRowIndex < rows.length - 1}
    );
    const navNextPageId = reg(
      'nav_next_page',
      'action.nav_next_page',
      gettext('Next Page'),
      () => handlersRef.current.navigatePage(winOff + winSz),
      {enabled: winOff + winSz < totalRows}
    );
    const navLastId = reg(
      'nav_last',
      'action.nav_last',
      gettext('Last Row'),
      () => {
        const lastPageOff = Math.floor(Math.max(0, totalRows - 1) / winSz) * winSz;
        if (lastPageOff !== winOff) handlersRef.current.navigatePage(lastPageOff);
        else handlersRef.current.selectRowAtIndex(rows.length - 1);
      },
      {enabled: totalRows > 0 && (winOff + winSz < totalRows || activeRowIndex < rows.length - 1)}
    );
    const jumpRowId = reg(
      'jump_row',
      'action.search',
      gettext('Jump to Row #'),
      () => handlersRef.current.setJumpDialogOpen(true),
      {enabled: totalRows > 0}
    );

    // Record Group (Edit / Accept primary icon!)
    const canMutate = Boolean(hostData?.editable);
    const canInsert = Boolean(hostData?.row_operations?.includes('insert'));
    const canDelete = Boolean(hostData?.row_operations?.includes('delete'));
    const editAcceptId = reg(
      'edit_accept',
      isEditingRow ? 'action.accept_version' : 'action.edit',
      isEditingRow ? gettext('Accept') : gettext('Edit'),
      () => {
        if (handlersRef.current.isEditingRow) {
          handlersRef.current.acceptCurrentRow();
        } else {
          handlersRef.current.beginEditRow();
        }
      },
      {enabled: canMutate || isEditingRow}
    );
    const insRowId = reg(
      'insert_row',
      'action.add',
      gettext('Insert Row'),
      () => handlersRef.current.beginInsertRow(false),
      {enabled: canInsert}
    );
    const dupRowId = reg(
      'duplicate_row',
      'action.copy',
      gettext('Duplicate Current Row'),
      () => handlersRef.current.beginInsertRow(true),
      {enabled: canInsert && Boolean(currentRow)}
    );
    const delRowId = reg(
      'delete_row',
      'action.delete',
      gettext('Delete Row'),
      () => handlersRef.current.handleDeleteCurrentRow(),
      {enabled: canDelete && Boolean(currentRow) && !isInsertDraft}
    );
    const setNullId = reg(
      'set_null',
      'action.set_null',
      gettext('Set Field to <null>'),
      () => {
        const col = handlersRef.current.activeColName;
        if (!col) return;
        if (!handlersRef.current.isEditingRow) {
          handlersRef.current.beginEditRow();
        }
        setRowDraft((prev) => ({...(prev || {}), [col]: null}));
      },
      {enabled: canMutate && Boolean(activeColName)}
    );
    const revertRowId = reg(
      'revert_row',
      'action.undo',
      gettext('Undo / Revert Row'),
      () => handlersRef.current.handleRevertCurrentRow(),
      {enabled: isEditingRow || Boolean(currentRow?.mutation_id)}
    );

    // Transaction Group
    const commitId = reg(
      'commit',
      'action.commit',
      gettext('Commit'),
      () => handlersRef.current.handleCommitBatch(),
      {enabled: !hostData?.autocommit && (stagedTotal > 0 || isEditingRow)}
    );
    const rollbackId = reg(
      'rollback',
      'action.rollback',
      gettext('Rollback'),
      () => handlersRef.current.handleRollbackBatch(),
      {enabled: !hostData?.autocommit && (stagedTotal > 0 || isEditingRow)}
    );
    const autocommitId = reg(
      'autocommit',
      'action.transaction',
      gettext('Autocommit'),
      async () => {
        const nextAc = !handlersRef.current.hostData?.autocommit;
        const resp = await handlersRef.current.callHost('read_window', {
          autocommit: nextAc,
          window_offset: handlersRef.current.hostData?.window_offset || 0,
        });
        handlersRef.current.applyHostResponse(resp);
      },
      {checked: Boolean(hostData?.autocommit), enabled: stagedTotal === 0}
    );
    const inspectStagedId = reg(
      'inspect_staged',
      'action.sql_preview',
      gettext('Inspect Staged SQL in Right Drawer'),
      () => handlersRef.current.openRightDrawerWith({mode: 'staged_sql'})
    );

    // Clipboard Group
    const copyId = reg(
      'copy',
      'action.copy',
      gettext('Copy'),
      () => handlersRef.current.copySelection('tsv'),
      {enabled: rows.length > 0}
    );
    const cutId = reg(
      'cut',
      'action.cut',
      gettext('Cut Cell Value'),
      () => {
        handlersRef.current.copySelection('tsv');
        const col = handlersRef.current.activeColName;
        if (col && canMutate) {
          if (!handlersRef.current.isEditingRow) handlersRef.current.beginEditRow();
          setRowDraft((prev) => ({...(prev || {}), [col]: ''}));
        }
      },
      {enabled: canMutate && Boolean(activeColName)}
    );
    const pasteId = reg(
      'paste',
      'action.paste',
      gettext('Paste Cell Value'),
      async () => {
        const col = handlersRef.current.activeColName;
        if (!col || !canMutate || !navigator.clipboard?.readText) return;
        const clip = await navigator.clipboard.readText().catch(() => '');
        if (!handlersRef.current.isEditingRow) handlersRef.current.beginEditRow();
        setRowDraft((prev) => ({...(prev || {}), [col]: clip}));
      },
      {enabled: canMutate && Boolean(activeColName)}
    );
    const copySpecialId = reg(
      'copy_special',
      'action.export_csv',
      gettext('Copy Special'),
      (detail) => {
        if (detail?.item) handlersRef.current.copySelection(detail.item);
      },
      {enabled: rows.length > 0}
    );

    // Fetch & Sort Group
    const refreshId = reg(
      'refresh',
      'action.refresh',
      gettext('Refresh'),
      () => handlersRef.current.refreshFromServer()
    );
    const sortLocId = reg(
      'sort_loc',
      'action.sort',
      hostData?.sort_execution === 'server'
        ? gettext('Server Sort Active (Click for Local Host Sort)')
        : gettext('Local Host Sort Active (Click for Server Sort)'),
      () => handlersRef.current.handleToggleSortLocation(),
      {checked: hostData?.sort_execution === 'server'}
    );
    const quickFindId = reg(
      'quick_find',
      'action.search',
      gettext('Quick Find'),
      () => handlersRef.current.setQuickFindOpen((v) => !v)
    );
    const filterBuilderId = reg(
      'filter_builder',
      'action.filter',
      gettext('Filter Builder'),
      () => handlersRef.current.openRightDrawerWith({mode: 'filter_builder'}),
      {checked: Boolean(hostData?.filters?.length)}
    );
    const clearFiltersId = reg(
      'clear_filters',
      'action.close',
      gettext('Clear All Filters & Sorts'),
      async () => {
        const resp = await handlersRef.current.callHost('sort_filter', {
          sorts: [],
          filters: [],
        });
        handlersRef.current.applyHostResponse(resp);
      },
      {enabled: Boolean(hostData?.filters?.length || hostData?.sorts?.length)}
    );
    const fetchLimitsId = reg(
      'fetch_limits',
      'action.fetch_limits',
      gettext('Fetch & Page Limits'),
      () => handlersRef.current.setLimitsDialogOpen(true)
    );

    // Under-Tab 2: Format & Layout (Alignment Pills + Sizing & Wrap)
    const hAlignPillId = reg(
      'halign_pill',
      'action.align_left',
      gettext('Horizontal Alignment'),
      (detail) => {
        if (detail?.item && handlersRef.current.activeColName) {
          handlersRef.current.setColumnPref(handlersRef.current.activeColName, {
            hAlign: detail.item,
          });
        }
      },
      {value: activeColHAlign, enabled: Boolean(activeColName)}
    );
    const vAlignPillId = reg(
      'valign_pill',
      'action.valign_middle',
      gettext('Vertical Alignment'),
      (detail) => {
        if (detail?.item && handlersRef.current.activeColName) {
          handlersRef.current.setColumnPref(handlersRef.current.activeColName, {
            vAlign: detail.item,
          });
        }
      },
      {value: activeColVAlign, enabled: Boolean(activeColName)}
    );
    const wrapPillId = reg(
      'wrap_pill',
      'action.wrap_none',
      gettext('Cell Text Wrap'),
      (detail) => {
        if (detail?.item && handlersRef.current.activeColName) {
          handlersRef.current.setColumnPref(handlersRef.current.activeColName, {
            wrapMode: detail.item,
          });
        }
      },
      {value: activeColWrap, enabled: Boolean(activeColName)}
    );
    const autoFitId = reg(
      'auto_fit',
      'action.recompute_layout',
      gettext('Auto-Fit'),
      () => {
        const nextPrefs = {...handlersRef.current.layout.gridColPrefs};
        for (const col of columns) {
          let maxChars = col.name.length + 4;
          for (const r of rows.slice(0, 100)) {
            const txt = String(r.values?.[col.name] ?? '');
            maxChars = Math.max(maxChars, Math.min(48, txt.length));
          }
          nextPrefs[col.name] = {
            ...(nextPrefs[col.name] || {}),
            width: Math.max(88, Math.min(380, maxChars * 8 + 26)),
          };
        }
        handlersRef.current.setLayout((prev) => ({
          ...prev,
          gridColPrefs: nextPrefs,
        }));
      }
    );
    const pinColId = reg(
      'pin_col',
      'action.pin_node',
      gettext('Pin / Freeze Selected Column'),
      () => {
        const col = handlersRef.current.activeColName;
        if (!col) return;
        const curPinned = Boolean(
          handlersRef.current.layout.gridColPrefs[col]?.pinned
        );
        handlersRef.current.setColumnPref(col, {pinned: !curPinned});
      },
      {
        checked: Boolean(activeColPrefs.pinned),
        enabled: Boolean(activeColName),
      }
    );
    const colSelectorId = reg(
      'col_selector',
      'action.section_columns',
      gettext('Visible Columns & Field Order (☰)'),
      () => {
        handlersRef.current.setColumnPickerScope('grid');
        handlersRef.current.setColumnPickerOpen(true);
      }
    );
    const resetLayoutId = reg(
      'reset_layout',
      'action.rollback',
      gettext('Reset Layout Defaults'),
      () => handlersRef.current.setLayout(defaultLayoutState())
    );

    // Under-Tab 3: Transfer & SQL
    const exportDataId = reg(
      'export_data',
      'action.export',
      gettext('Export Data'),
      () => handlersRef.current.setExportDialogOpen(true),
      {enabled: rows.length > 0}
    );
    const importDataId = reg(
      'import_data',
      'action.import',
      gettext('Import Data'),
      () => handlersRef.current.setImportDialogOpen(true),
      {enabled: canInsert}
    );
    const visualSqlId = reg(
      'open_visual_sql',
      'action.sql_builder',
      gettext('Visual SQL'),
      () => {
        if (onOpenInVisualSql) {
          onOpenInVisualSql(hostData?.sql_view?.server_sql || '');
        } else if (typeof window !== 'undefined') {
          window.dispatchEvent(
            new CustomEvent('scratchrobin:open-app-surface', {
              detail: {
                appId: 'bi-analytics',
                options: {initialSql: hostData?.sql_view?.server_sql || ''},
              },
            })
          );
        }
      }
    );
    const openSqlEdId = reg(
      'open_sql_editor',
      'tool.query',
      gettext('Open in SQL Editor'),
      () =>
        onOpenInSqlEditor?.({
          source: hostData?.sql_view?.server_sql || '',
          parameters: hostData?.sql_view?.parameters || [],
        })
    );
    const genInsertSqlId = reg(
      'gen_insert_sql',
      'action.script',
      gettext('Copy SQL INSERTs'),
      () => handlersRef.current.copySelection('sql_insert'),
      {enabled: rows.length > 0}
    );
    const genUpdateSqlId = reg(
      'gen_update_sql',
      'action.sql_preview',
      gettext('Copy SQL UPDATEs'),
      () => handlersRef.current.copySelection('sql_update'),
      {enabled: rows.length > 0}
    );

    const ribbonTabs = [
      {
        id: `${pfx}.tab.data`,
        label: gettext('Data'),
        groups: [
          {
            id: 'content_view',
            label: gettext('Surface & View'),
            controls: [
              {
                id: contentPillId,
                actionId: contentPillId,
                type: 'segmented',
                value: surfaceView,
                items: [
                  {
                    id: SURFACE_VIEWS.DATA,
                    label: gettext('Data'),
                    icon: 'action.browse_data',
                    checked: surfaceView === SURFACE_VIEWS.DATA,
                  },
                  {
                    id: SURFACE_VIEWS.METRICS,
                    label: gettext('Metrics & Plan'),
                    icon: 'action.statistics',
                    checked: surfaceView === SURFACE_VIEWS.METRICS,
                  },
                  {
                    id: SURFACE_VIEWS.SQL,
                    label: gettext('SQL'),
                    icon: 'action.sql_preview',
                    checked: surfaceView === SURFACE_VIEWS.SQL,
                  },
                  {
                    id: SURFACE_VIEWS.FIELDS,
                    label: gettext('Fields'),
                    icon: 'action.section_columns',
                    checked: surfaceView === SURFACE_VIEWS.FIELDS,
                  },
                  {
                    id: SURFACE_VIEWS.MESSAGES,
                    label: gettext('Messages & Log'),
                    icon: 'action.section_comments',
                    badge: errorWarnCount > 0 ? String(errorWarnCount) : undefined,
                    checked: surfaceView === SURFACE_VIEWS.MESSAGES,
                  },
                ],
              },
              {
                id: displayPillId,
                actionId: displayPillId,
                type: 'segmented',
                value: layout.displayMode,
                items: [
                  {
                    id: DISPLAY_MODES.GRID,
                    label: gettext('Standard Grid'),
                    icon: 'action.layout_grid',
                    checked: layout.displayMode === DISPLAY_MODES.GRID,
                  },
                  {
                    id: DISPLAY_MODES.MINI_FORMS,
                    label: gettext('Mini-Forms'),
                    icon: 'action.layout_mini_forms',
                    checked: layout.displayMode === DISPLAY_MODES.MINI_FORMS,
                  },
                  {
                    id: DISPLAY_MODES.HYBRID,
                    label: gettext('Hybrid (Grid + Current Mini-Form)'),
                    icon: 'action.layout_hybrid',
                    checked: layout.displayMode === DISPLAY_MODES.HYBRID,
                  },
                  {
                    id: DISPLAY_MODES.SINGLE_FORM,
                    label: gettext('Single Form (100% Area)'),
                    icon: 'action.layout_single_form',
                    checked: layout.displayMode === DISPLAY_MODES.SINGLE_FORM,
                  },
                  {
                    id: DISPLAY_MODES.HYBRID_EDIT,
                    label: gettext('Hybrid-When-Editing'),
                    icon: 'action.layout_hybrid_edit',
                    checked: layout.displayMode === DISPLAY_MODES.HYBRID_EDIT,
                  },
                ],
              },
              ...(layout.displayMode === DISPLAY_MODES.HYBRID_EDIT
                ? [
                  {
                    id: hybridTargetPillId,
                    actionId: hybridTargetPillId,
                    type: 'segmented',
                    value: layout.hybridEditTarget,
                    items: [
                      {
                        id: 'mini_form',
                        label: gettext('Edit as Mini-Form'),
                        icon: 'action.layout_mini_forms',
                        checked: layout.hybridEditTarget === 'mini_form',
                      },
                      {
                        id: 'single_form',
                        label: gettext('Edit as Single Form'),
                        icon: 'action.layout_single_form',
                        checked: layout.hybridEditTarget === 'single_form',
                      },
                    ],
                  },
                ]
                : []),
            ],
          },
          {
            id: 'navigate',
            label: gettext('Navigate'),
            controls: [
              {id: locateId, actionId: locateId, size: 'large', showLabel: true},
              {
                type: 'stack',
                id: `${pfx}.nav_stack`,
                controls: [
                  navFirstId,
                  navPrevPageId,
                  navPrevRowId,
                  navNextRowId,
                  navNextPageId,
                  navLastId,
                  jumpRowId,
                ],
              },
            ],
          },
          {
            id: 'record',
            label: gettext('Record'),
            controls: [
              {
                id: editAcceptId,
                actionId: editAcceptId,
                size: 'large',
                showLabel: true,
              },
              {
                type: 'stack',
                id: `${pfx}.rec_stack`,
                controls: [insRowId, dupRowId, delRowId, setNullId, revertRowId],
              },
            ],
          },
          {
            id: 'transaction',
            label: gettext('Transaction'),
            controls: [
              {id: commitId, actionId: commitId, size: 'large', showLabel: true},
              {
                type: 'stack',
                id: `${pfx}.tx_stack`,
                controls: [rollbackId, autocommitId, inspectStagedId],
              },
            ],
          },
          {
            id: 'clipboard',
            label: gettext('Clipboard'),
            controls: [
              {id: copyId, actionId: copyId, size: 'large', showLabel: true},
              {
                type: 'stack',
                id: `${pfx}.clip_stack`,
                controls: [
                  cutId,
                  pasteId,
                  {
                    id: copySpecialId,
                    actionId: copySpecialId,
                    type: 'menu',
                    items: [
                      {id: 'tsv', label: gettext('Copy as TSV'), icon: 'action.copy'},
                      {id: 'csv', label: gettext('Copy as CSV'), icon: 'action.export_csv'},
                      {id: 'json', label: gettext('Copy as JSON'), icon: 'action.export_json'},
                      {id: 'sql_insert', label: gettext('Copy as SQL INSERT'), icon: 'action.script'},
                      {id: 'sql_update', label: gettext('Copy as SQL UPDATE'), icon: 'action.sql_preview'},
                    ],
                  },
                ],
              },
            ],
          },
          {
            id: 'fetch_sort',
            label: gettext('Fetch & Sort'),
            controls: [
              {id: refreshId, actionId: refreshId, size: 'large', showLabel: true},
              {
                type: 'stack',
                id: `${pfx}.fetch_stack`,
                controls: [
                  sortLocId,
                  quickFindId,
                  filterBuilderId,
                  clearFiltersId,
                  fetchLimitsId,
                ],
              },
            ],
          },
        ],
      },
      {
        id: `${pfx}.tab.format`,
        label: gettext('Format & Layout'),
        groups: [
          {
            id: 'alignment',
            label: gettext('Alignment'),
            controls: [
              {
                id: hAlignPillId,
                actionId: hAlignPillId,
                type: 'segmented',
                value: activeColHAlign,
                items: [
                  {id: 'left', label: gettext('Align Left'), icon: 'action.align_left', checked: activeColHAlign === 'left'},
                  {id: 'center', label: gettext('Align Centre'), icon: 'action.align_center', checked: activeColHAlign === 'center'},
                  {id: 'right', label: gettext('Align Right'), icon: 'action.align_right', checked: activeColHAlign === 'right'},
                  {id: 'justify', label: gettext('Justified'), icon: 'action.align_justify', checked: activeColHAlign === 'justify'},
                ],
              },
              {
                id: vAlignPillId,
                actionId: vAlignPillId,
                type: 'segmented',
                value: activeColVAlign,
                items: [
                  {id: 'top', label: gettext('Vertical Top'), icon: 'action.valign_top', checked: activeColVAlign === 'top'},
                  {id: 'middle', label: gettext('Vertical Centre'), icon: 'action.valign_middle', checked: activeColVAlign === 'middle'},
                  {id: 'bottom', label: gettext('Vertical Bottom'), icon: 'action.valign_bottom', checked: activeColVAlign === 'bottom'},
                ],
              },
            ],
          },
          {
            id: 'sizing_wrap',
            label: gettext('Sizing & Columns'),
            controls: [
              {id: autoFitId, actionId: autoFitId, size: 'large', showLabel: true},
              {
                id: wrapPillId,
                actionId: wrapPillId,
                type: 'segmented',
                value: activeColWrap,
                items: [
                  {id: 'none', label: gettext('Single-Line Scroll'), icon: 'action.wrap_none', checked: activeColWrap === 'none'},
                  {id: 'clamp', label: gettext('Clamped Multi-Line'), icon: 'action.wrap_clamp', checked: activeColWrap === 'clamp'},
                  {id: 'full', label: gettext('Full Auto-Wrap'), icon: 'action.wrap_full', checked: activeColWrap === 'full'},
                ],
              },
              {
                type: 'stack',
                id: `${pfx}.size_stack`,
                controls: [pinColId, colSelectorId, resetLayoutId],
              },
            ],
          },
        ],
      },
      {
        id: `${pfx}.tab.transfer`,
        label: gettext('Transfer & SQL'),
        groups: [
          {
            id: 'import_export',
            label: gettext('Import & Export'),
            controls: [
              {
                id: exportDataId,
                actionId: exportDataId,
                size: 'large',
                showLabel: true,
              },
              {
                type: 'stack',
                id: `${pfx}.io_stack`,
                controls: [importDataId],
              },
            ],
          },
          {
            id: 'sql_tools',
            label: gettext('SQL Tools'),
            controls: [
              {
                id: visualSqlId,
                actionId: visualSqlId,
                size: 'large',
                showLabel: true,
              },
              {
                type: 'stack',
                id: `${pfx}.sql_stack`,
                controls: [openSqlEdId, genInsertSqlId, genUpdateSqlId],
              },
            ],
          },
        ],
      },
    ];

    // Surface-specific Top Menu entries merged by unsigned index on focus
    // and automatically removed by ProjectTopMenuRegistry when focus leaves.
    const menus = [
      {
        name: 'data',
        label: gettext('Data'),
        index: 15,
        items: [
          {
            id: `${pfx}.mnu.commit`,
            actionId: commitId,
            label: gettext('Commit Transaction'),
            iconKey: 'action.commit',
            shortcut: 'F9',
            index: 10,
            disabled: Boolean(hostData?.autocommit) || (stagedTotal === 0 && !isEditingRow),
          },
          {
            id: `${pfx}.mnu.rollback`,
            actionId: rollbackId,
            label: gettext('Rollback Transaction'),
            iconKey: 'action.rollback',
            index: 20,
            disabled: Boolean(hostData?.autocommit) || (stagedTotal === 0 && !isEditingRow),
          },
          {
            id: `${pfx}.mnu.autocommit`,
            actionId: autocommitId,
            label: gettext('Autocommit'),
            iconKey: 'action.transaction',
            checked: Boolean(hostData?.autocommit),
            disabled: stagedTotal > 0,
            index: 30,
          },
          {
            id: `${pfx}.mnu.inspect_staged`,
            actionId: inspectStagedId,
            label: gettext('Inspect Staged SQL (Right Drawer)'),
            iconKey: 'action.sql_preview',
            index: 40,
          },
          {id: `${pfx}.sep.tx`, type: 'separator', index: 45},
          {
            id: `${pfx}.mnu.edit_accept`,
            actionId: editAcceptId,
            label: isEditingRow ? gettext('Accept Row') : gettext('Edit Row'),
            iconKey: isEditingRow ? 'action.accept_version' : 'action.edit',
            shortcut: 'F2',
            disabled: !(canMutate || isEditingRow),
            index: 50,
          },
          {
            id: `${pfx}.mnu.insert_row`,
            actionId: insRowId,
            label: gettext('Insert Row'),
            iconKey: 'action.add',
            shortcut: 'Ctrl+Insert',
            disabled: !canInsert,
            index: 60,
          },
          {
            id: `${pfx}.mnu.dup_row`,
            actionId: dupRowId,
            label: gettext('Duplicate Current Row'),
            iconKey: 'action.copy',
            shortcut: 'Ctrl+D',
            disabled: !(canInsert && Boolean(currentRow)),
            index: 70,
          },
          {
            id: `${pfx}.mnu.del_row`,
            actionId: delRowId,
            label: gettext('Delete Row'),
            iconKey: 'action.delete',
            shortcut: 'Ctrl+Delete',
            disabled: !(canDelete && Boolean(currentRow) && !isInsertDraft),
            index: 80,
          },
          {
            id: `${pfx}.mnu.set_null`,
            actionId: setNullId,
            label: gettext('Set Field to <null>'),
            iconKey: 'action.set_null',
            shortcut: 'Ctrl+0',
            disabled: !(canMutate && Boolean(activeColName)),
            index: 90,
          },
          {
            id: `${pfx}.mnu.revert_row`,
            actionId: revertRowId,
            label: gettext('Revert / Undo Row'),
            iconKey: 'action.undo',
            shortcut: 'Esc',
            disabled: !(isEditingRow || Boolean(currentRow?.mutation_id)),
            index: 100,
          },
          {id: `${pfx}.sep.rec`, type: 'separator', index: 105},
          {
            id: `${pfx}.mnu.nav`,
            name: 'navigate',
            label: gettext('Navigate'),
            iconKey: 'action.locate_row',
            index: 110,
            items: [
              {id: `${pfx}.mnu.locate`, actionId: locateId, label: gettext('Locate Current Row'), iconKey: 'action.locate_row', index: 10, disabled: rows.length === 0},
              {id: `${pfx}.mnu.first`, actionId: navFirstId, label: gettext('First Row'), iconKey: 'action.nav_first', index: 20},
              {id: `${pfx}.mnu.prev_page`, actionId: navPrevPageId, label: gettext('Previous Page'), iconKey: 'action.nav_prev_page', index: 30},
              {id: `${pfx}.mnu.prev_row`, actionId: navPrevRowId, label: gettext('Previous Row'), iconKey: 'action.nav_prev_row', index: 40},
              {id: `${pfx}.mnu.next_row`, actionId: navNextRowId, label: gettext('Next Row'), iconKey: 'action.nav_next_row', index: 50},
              {id: `${pfx}.mnu.next_page`, actionId: navNextPageId, label: gettext('Next Page'), iconKey: 'action.nav_next_page', index: 60},
              {id: `${pfx}.mnu.last`, actionId: navLastId, label: gettext('Last Row'), iconKey: 'action.nav_last', index: 70},
              {id: `${pfx}.mnu.jump`, actionId: jumpRowId, label: gettext('Jump to Row #…'), iconKey: 'action.search', shortcut: 'Ctrl+G', index: 80},
            ],
          },
          {id: `${pfx}.sep.nav`, type: 'separator', index: 115},
          {
            id: `${pfx}.mnu.refresh`,
            actionId: refreshId,
            label: gettext('Refresh from Server'),
            iconKey: 'action.refresh',
            shortcut: 'F5',
            index: 120,
          },
          {
            id: `${pfx}.mnu.sort_exec`,
            name: 'sort_execution',
            label: gettext('Sort Execution'),
            iconKey: 'action.sort',
            index: 130,
            items: [
              {
                id: `${pfx}.mnu.sort_auto`,
                label: gettext('Auto (Smart Threshold)'),
                checked: (hostData?.sort_mode || 'auto') === 'auto',
                index: 10,
                callback: async () => {
                  const resp = await handlersRef.current.callHost('sort_filter', {sort_mode: 'auto'});
                  handlersRef.current.applyHostResponse(resp);
                },
              },
              {
                id: `${pfx}.mnu.sort_local`,
                label: gettext('Local (Host-Cached)'),
                checked: hostData?.sort_execution === 'local' && hostData?.sort_mode === 'local',
                index: 20,
                callback: async () => {
                  const resp = await handlersRef.current.callHost('sort_filter', {sort_mode: 'local'});
                  handlersRef.current.applyHostResponse(resp);
                },
              },
              {
                id: `${pfx}.mnu.sort_server`,
                label: gettext('Server Sort'),
                checked: hostData?.sort_execution === 'server' && hostData?.sort_mode === 'server',
                index: 30,
                callback: async () => {
                  const resp = await handlersRef.current.callHost('refresh', {sort_mode: 'server'});
                  handlersRef.current.applyHostResponse(resp);
                },
              },
            ],
          },
          {
            id: `${pfx}.mnu.ext_sort`,
            label: gettext('Extended Multi-Column Sort…'),
            iconKey: 'action.sort',
            index: 140,
            callback: () => {
              setExtendedSortDraft([...(hostData?.sorts || [])]);
              setExtendedSortOpen(true);
            },
          },
          {
            id: `${pfx}.mnu.filter_builder`,
            actionId: filterBuilderId,
            label: gettext('Filter Builder…'),
            iconKey: 'action.filter',
            index: 150,
          },
          {
            id: `${pfx}.mnu.quick_find`,
            actionId: quickFindId,
            label: gettext('Quick Find…'),
            iconKey: 'action.search',
            shortcut: 'Ctrl+F',
            index: 160,
          },
          {
            id: `${pfx}.mnu.clear_filters`,
            actionId: clearFiltersId,
            label: gettext('Clear All Filters & Sorts'),
            iconKey: 'action.close',
            disabled: !Boolean(hostData?.filters?.length || hostData?.sorts?.length),
            index: 170,
          },
          {
            id: `${pfx}.mnu.fetch_limits`,
            actionId: fetchLimitsId,
            label: gettext('Fetch & Page Limits…'),
            iconKey: 'action.fetch_limits',
            index: 180,
          },
          {id: `${pfx}.sep.io`, type: 'separator', index: 185},
          {
            id: `${pfx}.mnu.import`,
            actionId: importDataId,
            label: gettext('Import Data…'),
            iconKey: 'action.import',
            disabled: !canInsert,
            index: 190,
          },
          {
            id: `${pfx}.mnu.export`,
            actionId: exportDataId,
            label: gettext('Export Data…'),
            iconKey: 'action.export',
            disabled: rows.length === 0,
            index: 200,
          },
          {
            id: `${pfx}.mnu.visual_sql`,
            actionId: visualSqlId,
            label: gettext('Open in Visual SQL'),
            iconKey: 'action.sql_builder',
            index: 210,
          },
          {
            id: `${pfx}.mnu.sql_editor`,
            actionId: openSqlEdId,
            label: gettext('Open in SQL Editor'),
            iconKey: 'tool.query',
            index: 220,
          },
        ],
      },
      {
        name: 'edit',
        label: gettext('Edit'),
        index: 20,
        items: [
          {
            id: `${pfx}.mnu.undo`,
            actionId: `edit.undo.${instId}`,
            label: gettext('Undo'),
            iconKey: 'action.undo',
            shortcut: 'Ctrl+Z',
            disabled: !(isEditingRow || undoStack.length > 0),
            index: 10,
          },
          {
            id: `${pfx}.mnu.redo`,
            actionId: `edit.redo.${instId}`,
            label: gettext('Redo'),
            iconKey: 'action.redo',
            shortcut: 'Ctrl+Y',
            disabled: redoStack.length === 0,
            index: 20,
          },
          {id: `${pfx}.sep.clip`, type: 'separator', index: 25},
          {
            id: `${pfx}.mnu.cut`,
            actionId: cutId,
            label: gettext('Cut Cell'),
            iconKey: 'action.cut',
            shortcut: 'Ctrl+X',
            disabled: !(canMutate && Boolean(activeColName)),
            index: 30,
          },
          {
            id: `${pfx}.mnu.copy`,
            actionId: copyId,
            label: gettext('Copy'),
            iconKey: 'action.copy',
            shortcut: 'Ctrl+C',
            disabled: rows.length === 0,
            index: 40,
          },
          {
            id: `${pfx}.mnu.paste`,
            actionId: pasteId,
            label: gettext('Paste'),
            iconKey: 'action.paste',
            shortcut: 'Ctrl+V',
            disabled: !(canMutate && Boolean(activeColName)),
            index: 50,
          },
          {
            id: `${pfx}.mnu.copy_special`,
            name: 'copy_special',
            label: gettext('Copy Special'),
            iconKey: 'action.export_csv',
            index: 60,
            items: [
              {id: `${pfx}.mnu.cp_tsv`, label: gettext('Copy as TSV'), index: 10, callback: () => handlersRef.current.copySelection('tsv')},
              {id: `${pfx}.mnu.cp_csv`, label: gettext('Copy as CSV'), index: 20, callback: () => handlersRef.current.copySelection('csv')},
              {id: `${pfx}.mnu.cp_json`, label: gettext('Copy as JSON'), index: 30, callback: () => handlersRef.current.copySelection('json')},
              {id: `${pfx}.mnu.cp_ins`, label: gettext('Copy as SQL INSERT'), index: 40, callback: () => handlersRef.current.copySelection('sql_insert')},
              {id: `${pfx}.mnu.cp_upd`, label: gettext('Copy as SQL UPDATE'), index: 50, callback: () => handlersRef.current.copySelection('sql_update')},
            ],
          },
          {id: `${pfx}.sep.sel`, type: 'separator', index: 65},
          {
            id: `${pfx}.mnu.sel_row`,
            label: gettext('Select Current Row'),
            index: 70,
            disabled: rows.length === 0,
            callback: () => {
              const rIdx = handlersRef.current.activeRowIndex;
              setSelectedCells(
                (handlersRef.current.hostData?.columns || []).map((c) => ({
                  rowIndex: rIdx,
                  colName: c.name,
                }))
              );
            },
          },
          {
            id: `${pfx}.mnu.sel_all`,
            label: gettext('Select All Visible'),
            shortcut: 'Ctrl+A',
            index: 80,
            disabled: rows.length === 0,
            callback: () => {
              const all = [];
              rows.forEach((_r, rIdx) => {
                gridColumns.forEach((c) => {
                  all.push({rowIndex: rIdx, colName: c.name});
                });
              });
              setSelectedCells(all);
            },
          },
        ],
      },
      {
        name: 'view',
        label: gettext('View'),
        index: 25,
        items: [
          {
            id: `${pfx}.mnu.v_data`,
            label: gettext('Data View'),
            iconKey: 'action.browse_data',
            checked: surfaceView === SURFACE_VIEWS.DATA,
            index: 10,
            callback: () => handlersRef.current.setSurfaceView(SURFACE_VIEWS.DATA),
          },
          {
            id: `${pfx}.mnu.v_metrics`,
            label: gettext('Metrics & Plan View'),
            iconKey: 'action.statistics',
            checked: surfaceView === SURFACE_VIEWS.METRICS,
            index: 20,
            callback: () => handlersRef.current.setSurfaceView(SURFACE_VIEWS.METRICS),
          },
          {
            id: `${pfx}.mnu.v_sql`,
            label: gettext('SQL View'),
            iconKey: 'action.sql_preview',
            checked: surfaceView === SURFACE_VIEWS.SQL,
            index: 30,
            callback: () => handlersRef.current.setSurfaceView(SURFACE_VIEWS.SQL),
          },
          {
            id: `${pfx}.mnu.v_fields`,
            label: gettext('Fields View'),
            iconKey: 'action.section_columns',
            checked: surfaceView === SURFACE_VIEWS.FIELDS,
            index: 40,
            callback: () => handlersRef.current.setSurfaceView(SURFACE_VIEWS.FIELDS),
          },
          {
            id: `${pfx}.mnu.v_messages`,
            label: gettext('Messages & Log View'),
            iconKey: 'action.section_comments',
            checked: surfaceView === SURFACE_VIEWS.MESSAGES,
            index: 50,
            callback: () => handlersRef.current.setSurfaceView(SURFACE_VIEWS.MESSAGES),
          },
          {id: `${pfx}.sep.disp`, type: 'separator', index: 55},
          {
            id: `${pfx}.mnu.d_grid`,
            label: gettext('Standard Grid'),
            iconKey: 'action.layout_grid',
            checked: layout.displayMode === DISPLAY_MODES.GRID,
            index: 60,
            callback: () => {
              handlersRef.current.setLayout((prev) => ({...prev, displayMode: DISPLAY_MODES.GRID}));
              handlersRef.current.setSurfaceView(SURFACE_VIEWS.DATA);
            },
          },
          {
            id: `${pfx}.mnu.d_mini`,
            label: gettext('Mini-Forms'),
            iconKey: 'action.layout_mini_forms',
            checked: layout.displayMode === DISPLAY_MODES.MINI_FORMS,
            index: 70,
            callback: () => {
              handlersRef.current.setLayout((prev) => ({...prev, displayMode: DISPLAY_MODES.MINI_FORMS}));
              handlersRef.current.setSurfaceView(SURFACE_VIEWS.DATA);
            },
          },
          {
            id: `${pfx}.mnu.d_hybrid`,
            label: gettext('Hybrid (Grid + Current Mini-Form)'),
            iconKey: 'action.layout_hybrid',
            checked: layout.displayMode === DISPLAY_MODES.HYBRID,
            index: 80,
            callback: () => {
              handlersRef.current.setLayout((prev) => ({...prev, displayMode: DISPLAY_MODES.HYBRID}));
              handlersRef.current.setSurfaceView(SURFACE_VIEWS.DATA);
            },
          },
          {
            id: `${pfx}.mnu.d_single`,
            label: gettext('Single Form'),
            iconKey: 'action.layout_single_form',
            checked: layout.displayMode === DISPLAY_MODES.SINGLE_FORM,
            index: 90,
            callback: () => {
              handlersRef.current.setLayout((prev) => ({...prev, displayMode: DISPLAY_MODES.SINGLE_FORM}));
              handlersRef.current.setSurfaceView(SURFACE_VIEWS.DATA);
            },
          },
          {
            id: `${pfx}.mnu.d_hybrid_edit`,
            label: gettext('Hybrid-When-Editing'),
            iconKey: 'action.layout_hybrid_edit',
            checked: layout.displayMode === DISPLAY_MODES.HYBRID_EDIT,
            index: 100,
            callback: () => {
              handlersRef.current.setLayout((prev) => ({...prev, displayMode: DISPLAY_MODES.HYBRID_EDIT}));
              handlersRef.current.setSurfaceView(SURFACE_VIEWS.DATA);
            },
          },
          {id: `${pfx}.sep.cols`, type: 'separator', index: 105},
          {
            id: `${pfx}.mnu.col_selector`,
            actionId: colSelectorId,
            label: gettext('Visible Columns & Field Order…'),
            iconKey: 'action.section_columns',
            index: 110,
          },
          {
            id: `${pfx}.mnu.auto_fit`,
            actionId: autoFitId,
            label: gettext('Auto-Fit Columns'),
            iconKey: 'action.recompute_layout',
            index: 120,
          },
          {
            id: `${pfx}.mnu.pin_col`,
            actionId: pinColId,
            label: gettext('Pin / Freeze Selected Column'),
            iconKey: 'action.pin_node',
            checked: Boolean(activeColPrefs.pinned),
            disabled: !Boolean(activeColName),
            index: 130,
          },
          {
            id: `${pfx}.mnu.bool_fmt`,
            name: 'boolean_format',
            label: gettext('Boolean Format'),
            index: 140,
            items: [
              {id: `${pfx}.mnu.bf_tf`, label: 'T / F', checked: layout.booleanFormat === BOOLEAN_FORMATS.TF, index: 10, callback: () => handlersRef.current.setLayout((p) => ({...p, booleanFormat: BOOLEAN_FORMATS.TF}))},
              {id: `${pfx}.mnu.bf_yn`, label: 'Y / N', checked: layout.booleanFormat === BOOLEAN_FORMATS.YN, index: 20, callback: () => handlersRef.current.setLayout((p) => ({...p, booleanFormat: BOOLEAN_FORMATS.YN}))},
              {id: `${pfx}.mnu.bf_true`, label: 'True / False', checked: layout.booleanFormat === BOOLEAN_FORMATS.TRUE_FALSE, index: 30, callback: () => handlersRef.current.setLayout((p) => ({...p, booleanFormat: BOOLEAN_FORMATS.TRUE_FALSE}))},
              {id: `${pfx}.mnu.bf_10`, label: '1 / 0', checked: layout.booleanFormat === BOOLEAN_FORMATS.ONE_ZERO, index: 40, callback: () => handlersRef.current.setLayout((p) => ({...p, booleanFormat: BOOLEAN_FORMATS.ONE_ZERO}))},
            ],
          },
          {id: `${pfx}.sep.lay`, type: 'separator', index: 155},
          {
            id: `${pfx}.mnu.save_layout`,
            actionId: `file.save.${instId}`,
            label: gettext('Save Layout / Template…'),
            iconKey: 'action.save',
            shortcut: 'Ctrl+S',
            index: 160,
          },
          {
            id: `${pfx}.mnu.reset_layout`,
            actionId: resetLayoutId,
            label: gettext('Reset Layout Defaults'),
            iconKey: 'action.rollback',
            index: 170,
          },
        ],
      },
      {
        // Merges into permanent Window menu (index 70) on focus, removed on blur!
        name: 'window',
        label: gettext('Window'),
        index: PROJECT_TOP_MENU_INDICES.WINDOW,
        items: [
          {
            id: `${pfx}.mnu.toggle_3b`,
            label: gettext('Toggle Right Inspector Drawer'),
            iconKey: 'action.inspector_drawer',
            index: 15,
            callback: () => shellRef.current?.toggleInstanceRightDrawer?.(instId),
          },
          {
            id: `${pfx}.mnu.close_surface`,
            label: gettext('Close Data Surface'),
            iconKey: 'action.close',
            index: 95,
            callback: () => shellRef.current?.closeInstance?.(instId),
          },
        ],
      },
    ];

    registeredActionIdsRef.current = regActions.map((a) => a.id);

    curShell.updateInstance?.(instId, {
      actions: regActions,
      menus,
      ribbonTabs,
      ribbonMode: 'ms-grouped',
      useUnderTabs: true,
      supportsRightDrawer: true,
      renderRightDrawer: stableRenderRightDrawer,
      renderStatus: stableRenderStatusBar,
      onBeforeClose: () => handlersRef.current.beforeSurfaceClose(),
    });
    return undefined;
  }, [
    instId,
    surfaceView,
    layout,
    hostData,
    rows,
    columns,
    activeRowIndex,
    activeColName,
    activeColHAlign,
    activeColVAlign,
    activeColWrap,
    activeColPrefs.pinned,
    isEditingRow,
    isInsertDraft,
    rowDraft,
    drawerState,
    selectedCells.length,
    scrollRowRange.start,
    scrollRowRange.end,
    currentRow,
    stagedTotal,
    errorWarnCount,
    undoStack.length,
    redoStack.length,
    stableRenderRightDrawer,
    stableRenderStatusBar,
  ]);

  // =========================================================================
  // Context Menu Builders (Column Header, Mini-Form, Form Field)
  // =========================================================================
  const openHeaderContextMenu = useCallback(
    (ev, col) => {
      ev.preventDefault();
      ev.stopPropagation();
      setActiveColName(col.name);
      const isPinned = Boolean(layout.gridColPrefs[col.name]?.pinned);
      setContextMenuItems([
        {
          label: gettext('Filter Options…'),
          icon: 'action.filter',
          callback: () => openRightDrawerWith({mode: 'filter_builder', column: col}),
        },
        {
          label: gettext('Extended Sort…'),
          icon: 'action.sort',
          callback: () => {
            setExtendedSortDraft(
              hostData?.sorts?.length
                ? [...hostData.sorts]
                : [{column: col.name, direction: 'asc'}]
            );
            setExtendedSortOpen(true);
          },
        },
        {type: 'separator'},
        {
          label: isPinned
            ? gettext('Unfreeze / Unpin Column')
            : gettext('Freeze / Pin Column Left'),
          icon: 'action.pin_node',
          callback: () => setColumnPref(col.name, {pinned: !isPinned}),
        },
        {
          label: gettext('Hide Column'),
          icon: 'action.close',
          callback: () => {
            const currentVis =
              layout.gridVisibleCols || columns.map((c) => c.name);
            const nextVis = currentVis.filter((n) => n !== col.name);
            if (nextVis.length > 0) {
              setLayout((prev) => ({...prev, gridVisibleCols: nextVis}));
            }
          },
        },
        {
          label: gettext('Auto-Fit Column'),
          icon: 'action.recompute_layout',
          callback: () => {
            let maxChars = col.name.length + 4;
            for (const r of rows.slice(0, 100)) {
              maxChars = Math.max(
                maxChars,
                Math.min(50, String(r.values?.[col.name] ?? '').length)
              );
            }
            setColumnPref(col.name, {
              width: Math.max(88, Math.min(400, maxChars * 8 + 26)),
            });
          },
        },
        {
          label: gettext('Auto-Fit All Columns'),
          icon: 'action.align',
          callback: () => {
            const nextPrefs = {...layout.gridColPrefs};
            for (const c of columns) {
              let maxChars = c.name.length + 4;
              for (const r of rows.slice(0, 100)) {
                maxChars = Math.max(
                  maxChars,
                  Math.min(50, String(r.values?.[c.name] ?? '').length)
                );
              }
              nextPrefs[c.name] = {
                ...(nextPrefs[c.name] || {}),
                width: Math.max(88, Math.min(400, maxChars * 8 + 26)),
              };
            }
            setLayout((prev) => ({...prev, gridColPrefs: nextPrefs}));
          },
        },
        {type: 'separator'},
        {
          label: gettext('Display Format…'),
          icon: 'action.settings',
          callback: () => openRightDrawerWith({mode: 'column_format', column: col}),
        },
        {
          label: gettext('Column Profile / Distinct Values'),
          icon: 'action.statistics',
          callback: async () => {
            const prof = await callHost('column_profile', {column: col.name});
            openRightDrawerWith({
              mode: 'column_profile',
              column: col,
              profileData: prof,
            });
          },
        },
        {type: 'separator'},
        {
          label: gettext('Copy Column Name'),
          icon: 'action.copy',
          callback: () =>
            navigator.clipboard?.writeText?.(col.name).catch(() => {}),
        },
        {
          label: gettext('Select Column Values'),
          icon: 'action.select_marquee',
          callback: () =>
            setSelectedCells(
              rows.map((_, idx) => ({rowIndex: idx, colName: col.name}))
            ),
        },
      ]);
      setContextPos({x: ev.clientX, y: ev.clientY});
    },
    [
      layout.gridColPrefs,
      layout.gridVisibleCols,
      openRightDrawerWith,
      hostData?.sorts,
      setColumnPref,
      columns,
      rows,
      callHost,
    ]
  );

  const openMiniFormContextMenu = useCallback(
    (ev, rIdx) => {
      setContextMenuItems([
        {
          label: isEditingRow ? gettext('Accept Row Edits') : gettext('Edit Row'),
          icon: isEditingRow ? 'action.accept_version' : 'action.edit',
          callback: () =>
            isEditingRow ? acceptCurrentRow() : beginEditRow(rIdx),
        },
        {
          label: gettext('Configure Form Fields & Order…'),
          icon: 'action.section_columns',
          callback: () => {
            setColumnPickerScope('form');
            setColumnPickerOpen(true);
          },
        },
        {
          label: gettext('Filter Options…'),
          icon: 'action.filter',
          callback: () => openRightDrawerWith({mode: 'filter_builder'}),
        },
        {
          label: gettext('Extended Sort…'),
          icon: 'action.sort',
          callback: () => {
            setExtendedSortDraft(
              hostData?.sorts?.length
                ? [...hostData.sorts]
                : columns[0]
                  ? [{column: columns[0].name, direction: 'asc'}]
                  : []
            );
            setExtendedSortOpen(true);
          },
        },
      ]);
      setContextPos({x: ev.clientX, y: ev.clientY});
    },
    [
      isEditingRow,
      acceptCurrentRow,
      beginEditRow,
      openRightDrawerWith,
      hostData?.sorts,
      columns,
    ]
  );

  const openFormFieldContextMenu = useCallback(
    (ev, col, rIdx) => {
      const curInline = Boolean(layout.formFieldPrefs[col.name]?.inlineBox);
      setContextMenuItems([
        {
          label: curInline
            ? gettext('Use [...] Right-Drawer Viewer')
            : gettext('Use Sizable Inline Text-Edit Box'),
          icon: 'action.edit',
          callback: () =>
            setLayout((prev) => ({
              ...prev,
              formFieldPrefs: {
                ...prev.formFieldPrefs,
                [col.name]: {
                  ...(prev.formFieldPrefs[col.name] || {}),
                  inlineBox: !curInline,
                },
              },
            })),
        },
        {
          label: gettext('Open in Right Drawer (3b)'),
          icon: 'action.inspector_drawer',
          callback: () =>
            openRightDrawerWith({
              mode: 'complex_value',
              rowIndex: rIdx,
              column: col,
            }),
        },
        {
          label: gettext('Display Format…'),
          icon: 'action.settings',
          callback: () => openRightDrawerWith({mode: 'column_format', column: col}),
        },
      ]);
      setContextPos({x: ev.clientX, y: ev.clientY});
    },
    [layout.formFieldPrefs, openRightDrawerWith]
  );

  // =========================================================================
  // View Renderers (`Area 3e` = 100% Surface Content!)
  // =========================================================================
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
          <span>{isCurrent ? '▶' : stageMarker}</span>
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
                if (canEditCell) {
                  if (ev.key === 'Escape') {
                    ev.preventDefault();
                    cancelRowDraft();
                  } else if (ev.key === 'Enter') {
                    ev.preventDefault();
                    acceptCurrentRow();
                  }
                  return;
                }
                const colIdx = gridColumns.findIndex((c) => c.name === col.name);
                if (ev.key === 'ArrowDown') {
                  ev.preventDefault();
                  selectRowAtIndex(rIdx + 1, col.name);
                } else if (ev.key === 'ArrowUp') {
                  ev.preventDefault();
                  selectRowAtIndex(rIdx - 1, col.name);
                } else if (ev.key === 'ArrowRight' && colIdx < gridColumns.length - 1) {
                  ev.preventDefault();
                  setActiveColName(gridColumns[colIdx + 1].name);
                } else if (ev.key === 'ArrowLeft' && colIdx > 0) {
                  ev.preventDefault();
                  setActiveColName(gridColumns[colIdx - 1].name);
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
          draftValues={isRowEdit ? rowDraft : null}
          columns={formColumns}
          formLayout={sharedFormLayout}
          formFieldPrefs={layout.formFieldPrefs}
          booleanFormat={layout.booleanFormat}
          localeDateFormat={layout.localeDateFormat}
          fullArea
          onSelectRow={selectRowAtIndex}
          onFocusField={setActiveColName}
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
                    draftValues={isRowEdit ? rowDraft : null}
                    columns={formColumns}
                    formLayout={sharedFormLayout}
                    formFieldPrefs={layout.formFieldPrefs}
                    booleanFormat={layout.booleanFormat}
                    localeDateFormat={layout.localeDateFormat}
                    onSelectRow={selectRowAtIndex}
                    onFocusField={setActiveColName}
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
                      draftValues={isRowEdit ? rowDraft : null}
                      columns={formColumns}
                      formLayout={sharedFormLayout}
                      formFieldPrefs={layout.formFieldPrefs}
                      booleanFormat={layout.booleanFormat}
                      localeDateFormat={layout.localeDateFormat}
                      maxHeight="46vh"
                      onSelectRow={selectRowAtIndex}
                      onFocusField={setActiveColName}
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

  const renderMetricsView = () => {
    const mv = hostData?.metrics_view || {};
    const t = mv.timings_ms || {};
    const buf = mv.buffer || {};
    const tx = mv.transaction || {};
    const cardStyle = {
      padding: '12px 14px',
      borderRadius: 10,
      border: '1px solid var(--sr-border-default)',
      background: 'var(--sr-surface-card)',
      display: 'grid',
      gap: 4,
    };

    return (
      <ScratchScrollArea orientation="vertical" fillViewport style={{flex: 1, minHeight: 0}}>
        <div
          data-cdeadmin-qa-key="data-surface-metrics-view"
          style={{padding: 16, display: 'grid', gap: 16}}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
              gap: 12,
            }}
          >
            <div style={cardStyle}>
              <span style={{fontSize: '0.73rem', opacity: 0.7}}>{gettext('Server Execute Time')}</span>
              <strong style={{fontSize: '1.05rem'}}>{t.execute_ms ?? 0} ms</strong>
            </div>
            <div style={cardStyle}>
              <span style={{fontSize: '0.73rem', opacity: 0.7}}>{gettext('Fetch & Transfer Time')}</span>
              <strong style={{fontSize: '1.05rem'}}>{t.fetch_ms ?? 0} ms</strong>
            </div>
            <div style={cardStyle}>
              <span style={{fontSize: '0.73rem', opacity: 0.7}}>{gettext('Host Sort / Filter Time')}</span>
              <strong style={{fontSize: '1.05rem'}}>{t.host_sort_filter_ms ?? 0} ms</strong>
            </div>
            <div style={cardStyle}>
              <span style={{fontSize: '0.73rem', opacity: 0.7}}>{gettext('Total Activity Time')}</span>
              <strong style={{fontSize: '1.05rem'}}>{t.total_ms ?? 0} ms</strong>
            </div>
            <div style={cardStyle}>
              <span style={{fontSize: '0.73rem', opacity: 0.7}}>{gettext('Host Buffer Memory')}</span>
              <strong style={{fontSize: '1.05rem'}}>{formatBytes(buf.host_memory_bytes)}</strong>
              <span style={{fontSize: '0.72rem', opacity: 0.7}}>
                {buf.buffered_rows ?? 0} {gettext('rows cached')} ({buf.complete_in_buffer ? gettext('Complete') : gettext('Partial / Capped')})
              </span>
            </div>
            <div style={cardStyle}>
              <span style={{fontSize: '0.73rem', opacity: 0.7}}>{gettext('Session & Transaction')}</span>
              <strong style={{fontSize: '0.92rem'}}>{tx.session_id || gettext('Pooled')}</strong>
              <span style={{fontSize: '0.72rem', opacity: 0.7}}>
                {gettext('Autocommit')}: {tx.autocommit ? 'ON' : 'OFF'} · {gettext('Staged')}: +{tx.staged_inserts || 0} / ~{tx.staged_updates || 0} / −{tx.staged_deletes || 0}
              </span>
            </div>
          </div>

          <div style={cardStyle}>
            <strong style={{fontSize: '0.86rem'}}>{gettext('Execution Plan')}</strong>
            <pre
              style={{
                margin: 0,
                padding: '8px 10px',
                borderRadius: 6,
                background: 'var(--sr-surface-subtle)',
                fontFamily: 'var(--sr-font-mono, monospace)',
                fontSize: '0.8rem',
                whiteSpace: 'pre-wrap',
              }}
            >
              {mv.plan_text || gettext('No plan observation reported.')}
            </pre>
            {(mv.plan_nodes || []).map((pn) => (
              <div
                key={pn.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '6px 8px',
                  fontSize: '0.78rem',
                  borderTop: '1px solid var(--sr-border-subtle)',
                }}
              >
                <span>
                  <strong>{pn.operation}</strong> → {pn.target} ({pn.strategy})
                </span>
                <span>{pn.sort_location}</span>
              </div>
            ))}
          </div>
        </div>
      </ScratchScrollArea>
    );
  };

  const renderSqlView = () => {
    const sv = hostData?.sql_view || {};
    const isLocal = sv.sort_execution === 'local';
    return (
      <ScratchScrollArea orientation="vertical" fillViewport style={{flex: 1, minHeight: 0}}>
        <div
          data-cdeadmin-qa-key="data-surface-sql-view"
          style={{padding: 16, display: 'grid', gap: 12}}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 8,
              padding: '8px 12px',
              borderRadius: 8,
              border: '1px solid var(--sr-border-default)',
              background: 'var(--sr-surface-subtle)',
            }}
          >
            <div style={{display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.8rem'}}>
              <span
                style={{
                  padding: '2px 8px',
                  borderRadius: 999,
                  fontWeight: 700,
                  background: isLocal ? 'var(--sr-surface-selected)' : 'var(--sr-accent)',
                  color: isLocal ? 'var(--sr-accent)' : '#fff',
                }}
              >
                {isLocal ? gettext('LOCAL HOST-CACHED SORT / FILTER') : gettext('SERVER-SIDE SORT / FILTER')}
              </span>
              <span>{sv.local_operations_summary}</span>
            </div>
            <div style={{display: 'flex', gap: 8}}>
              <Button size="small" onClick={handleToggleSortLocation}>
                {isLocal ? gettext('Switch to Server Sort') : gettext('Switch to Local Host Sort')}
              </Button>
              {stagedTotal > 0 && (
                <Button
                  size="small"
                  intent="primary"
                  onClick={() => openRightDrawerWith({mode: 'staged_sql'})}
                >
                  {gettext('View %s Staged DML in Right Drawer', stagedTotal)}
                </Button>
              )}
            </div>
          </div>

          <textarea
            aria-label={gettext('Active Server Retrieval SQL')}
            readOnly
            value={sv.server_sql || ''}
            style={{
              minHeight: 280,
              width: '100%',
              padding: '12px 14px',
              borderRadius: 10,
              border: '1px solid var(--sr-border-default)',
              background: 'var(--sr-surface-card)',
              color: 'inherit',
              fontFamily: 'var(--sr-font-mono, monospace)',
              fontSize: '0.84rem',
              resize: 'vertical',
            }}
          />
        </div>
      </ScratchScrollArea>
    );
  };

  const renderFieldsView = () => {
    const fieldsList = hostData?.fields_grid || [];
    return (
      <ScratchScrollArea orientation="both" fillViewport style={{flex: 1, minHeight: 0}}>
        <table
          data-cdeadmin-qa-key="data-surface-fields-view"
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '0.8rem',
          }}
        >
          <thead>
            <tr
              style={{
                position: 'sticky',
                top: 0,
                background: 'var(--sr-surface-subtle)',
                borderBottom: '1px solid var(--sr-border-default)',
                textAlign: 'left',
              }}
            >
              <th style={{padding: '7px 10px'}}>#</th>
              <th style={{padding: '7px 10px'}}>{gettext('Field Name')}</th>
              <th style={{padding: '7px 10px'}}>{gettext('Key')}</th>
              <th style={{padding: '7px 10px'}}>{gettext('Server Native Type')}</th>
              <th style={{padding: '7px 10px'}}>{gettext('Domain / UDT')}</th>
              <th style={{padding: '7px 10px'}}>{gettext('Nullable')}</th>
              <th style={{padding: '7px 10px'}}>{gettext('Charset / Collation')}</th>
              <th style={{padding: '7px 10px'}}>{gettext('Client Type')}</th>
              <th style={{padding: '7px 10px'}}>{gettext('Alignment')}</th>
              <th style={{padding: '7px 10px'}}>{gettext('Editable')}</th>
              <th style={{padding: '7px 10px'}}>{gettext('Comment')}</th>
            </tr>
          </thead>
          <tbody>
            {fieldsList.map((fld) => (
              <tr
                key={fld.name}
                onClick={() =>
                  openRightDrawerWith({
                    mode: 'field_detail',
                    selectedField: fld,
                  })
                }
                style={{
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--sr-border-subtle)',
                }}
              >
                <td style={{padding: '6px 10px', opacity: 0.7}}>{fld.ordinal}</td>
                <td style={{padding: '6px 10px', fontWeight: 600}}>{fld.name}</td>
                <td style={{padding: '6px 10px'}}>{fld.key_role || '—'}</td>
                <td style={{padding: '6px 10px', fontFamily: 'var(--sr-font-mono, monospace)'}}>
                  {fld.native_type}
                </td>
                <td style={{padding: '6px 10px'}}>{fld.domain_type}</td>
                <td style={{padding: '6px 10px'}}>{fld.nullable ? 'YES' : 'NO'}</td>
                <td style={{padding: '6px 10px'}}>{fld.charset} / {fld.collation}</td>
                <td style={{padding: '6px 10px'}}>{fld.client_type}</td>
                <td style={{padding: '6px 10px'}}>
                  {layout.gridColPrefs[fld.name]?.hAlign || fld.default_alignment}
                </td>
                <td style={{padding: '6px 10px'}}>{fld.editable ? 'YES' : 'NO'}</td>
                <td style={{padding: '6px 10px', opacity: 0.8}}>{fld.comment || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScratchScrollArea>
    );
  };

  const renderMessagesView = () => {
    const allMsgs = hostData?.messages || [];
    const filteredMsgs =
      msgSeverityFilter === 'all'
        ? allMsgs
        : allMsgs.filter((m) => m.severity === msgSeverityFilter);

    return (
      <div
        data-cdeadmin-qa-key="data-surface-messages-view"
        style={{display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0}}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '6px 12px',
            borderBottom: '1px solid var(--sr-border-subtle)',
            flexShrink: 0,
          }}
        >
          <div style={{display: 'flex', gap: 6}}>
            {['all', 'error', 'warning', 'info'].map((sev) => (
              <Button
                key={sev}
                size="small"
                intent={msgSeverityFilter === sev ? 'primary' : 'neutral'}
                onClick={() => setMsgSeverityFilter(sev)}
              >
                {sev.toUpperCase()}
              </Button>
            ))}
          </div>
          <Button
            size="small"
            onClick={() => {
              const text = filteredMsgs
                .map((m) => `[${m.timestamp}] [${m.severity}] ${m.operation}: ${m.message}`)
                .join('\n');
              navigator.clipboard?.writeText?.(text).catch(() => {});
            }}
          >
            {gettext('Copy Log')}
          </Button>
        </div>

        <ScratchScrollArea orientation="vertical" fillViewport style={{flex: 1, minHeight: 0}}>
          <div style={{padding: 10, display: 'grid', gap: 6}}>
            {filteredMsgs.length === 0 ? (
              <EmptyState message={gettext('No log messages recorded yet.')} />
            ) : (
              filteredMsgs.map((m) => (
                <div
                  key={m.id}
                  onClick={() => {
                    openRightDrawerWith({
                      mode: 'message_detail',
                      selectedMessage: m,
                    });
                    if (typeof m.row_index === 'number') {
                      setSurfaceView(SURFACE_VIEWS.DATA);
                      setActiveRowIndex(m.row_index);
                      if (m.column_name) setActiveColName(m.column_name);
                    }
                  }}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 8,
                    border: '1px solid var(--sr-border-default)',
                    borderLeftWidth: 4,
                    borderLeftColor:
                      m.severity === 'error'
                        ? 'var(--sr-danger)'
                        : m.severity === 'warning'
                          ? 'var(--sr-warning)'
                          : 'var(--sr-accent)',
                    background: 'var(--sr-surface-card)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 10,
                    fontSize: '0.8rem',
                  }}
                >
                  <div style={{minWidth: 0}}>
                    <div>
                      <strong>{m.operation}</strong> — {m.message}
                    </div>
                    <div style={{fontSize: '0.72rem', opacity: 0.7}}>
                      {m.timestamp}
                      {m.elapsed_ms !== null && m.elapsed_ms !== undefined
                        ? ` · ${m.elapsed_ms} ms`
                        : ''}
                    </div>
                  </div>
                  {typeof m.row_index === 'number' && (
                    <span
                      style={{
                        fontSize: '0.73rem',
                        fontWeight: 600,
                        color: 'var(--sr-accent)',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {gettext('Jump to Row #%s →', m.row_index + 1)}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        </ScratchScrollArea>
      </div>
    );
  };

  return (
    <div
      ref={areaRef}
      data-cdeadmin-qa-key="data-edit-surface"
      style={{
        height: '100%',
        width: '100%',
        minHeight: 0,
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
      }}
    >
      {/* Floating Quick-Find overlay pill (only when invoked from TiB) */}
      {quickFindOpen && (
        <div
          style={{
            position: 'absolute',
            top: 8,
            right: 12,
            zIndex: 20,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 8px',
            borderRadius: 8,
            border: '1px solid var(--sr-border-default)',
            background: 'var(--sr-surface-elevated)',
            boxShadow: 'var(--sr-popup-shadow)',
          }}
        >
          <input
            type="text"
            autoFocus
            aria-label={gettext('Quick Find in loaded rows')}
            placeholder={gettext('Find in cells…')}
            value={quickFindText}
            onChange={(e) => setQuickFindText(e.target.value)}
            style={{
              border: '1px solid var(--sr-border-subtle)',
              borderRadius: 5,
              padding: '2px 7px',
              fontSize: '0.78rem',
              background: 'var(--sr-surface-card)',
              color: 'inherit',
            }}
          />
          <button
            type="button"
            className="sr-btn"
            style={{minHeight: 22, padding: '0 6px'}}
            onClick={() => {
              setQuickFindOpen(false);
              setQuickFindText('');
            }}
          >
            ×
          </button>
        </div>
      )}

      {surfaceError && (
        <div
          role="alert"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '6px 12px',
            background: 'rgba(220, 38, 38, 0.12)',
            borderBottom: '1px solid var(--sr-danger)',
            fontSize: '0.8rem',
            flexShrink: 0,
          }}
        >
          <span>{surfaceError}</span>
          <button
            type="button"
            className="sr-btn"
            style={{minHeight: 22, padding: '0 8px'}}
            onClick={() => setSurfaceError('')}
          >
            {gettext('Dismiss')}
          </button>
        </div>
      )}

      {loading ? (
        <ProgressOverlay message={gettext('Buffering rows on host…')} />
      ) : surfaceView === SURFACE_VIEWS.METRICS ? (
        renderMetricsView()
      ) : surfaceView === SURFACE_VIEWS.SQL ? (
        renderSqlView()
      ) : surfaceView === SURFACE_VIEWS.FIELDS ? (
        renderFieldsView()
      ) : surfaceView === SURFACE_VIEWS.MESSAGES ? (
        renderMessagesView()
      ) : (
        renderDataView()
      )}

      <ContextMenu
        position={contextPos}
        onClose={() => setContextPos(null)}
        menuItems={contextMenuItems}
        label={gettext('Data Surface Context Menu')}
      />

      {/* Hamburger (☰) Column Visibility & Field Order Dialog */}
      <ColumnOrderDialog
        open={columnPickerOpen}
        scope={columnPickerScope}
        allColumns={columns}
        visibleNames={
          columnPickerScope === 'form'
            ? layout.formVisibleCols
            : layout.gridVisibleCols
        }
        orderNames={
          columnPickerScope === 'form' ? layout.formColOrder : layout.gridColOrder
        }
        onClose={() => setColumnPickerOpen(false)}
        onApply={(nextOrder, nextVis) => {
          setLayout((prev) =>
            columnPickerScope === 'form'
              ? {
                ...prev,
                formColOrder: nextOrder,
                formVisibleCols: nextVis,
              }
              : {
                ...prev,
                gridColOrder: nextOrder,
                gridVisibleCols: nextVis,
              }
          );
          setColumnPickerOpen(false);
        }}
      />

      {/* Extended Multi-Column Sort Dialog */}
      <ExtendedSortDialog
        open={extendedSortOpen}
        columns={columns}
        draft={extendedSortDraft}
        onChangeDraft={setExtendedSortDraft}
        onClose={() => setExtendedSortOpen(false)}
        onApply={async (nextSorts) => {
          setExtendedSortOpen(false);
          setWorking(true);
          try {
            const resp = await callHost('sort_filter', {sorts: nextSorts});
            applyHostResponse(resp);
          } catch (err) {
            setSurfaceError(err?.message || String(err));
          } finally {
            setWorking(false);
          }
        }}
      />

      {/* Fetch & Page Size Limits Dialog */}
      <Dialog
        open={limitsDialogOpen}
        title={gettext('Host Buffer & Page Limits')}
        size="small"
        onClose={() => setLimitsDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setLimitsDialogOpen(false)}>
              {gettext('Cancel')}
            </Button>
            <Button
              intent="primary"
              onClick={async () => {
                setLimitsDialogOpen(false);
                setLoading(true);
                try {
                  const resp = await callHost('refresh', {
                    page_size: Number(limitsDraft.pageSize) || 200,
                    max_rows: Number(limitsDraft.maxRows) || 1000,
                  });
                  applyHostResponse(resp);
                } catch (err) {
                  setSurfaceError(err?.message || String(err));
                } finally {
                  setLoading(false);
                }
              }}
            >
              {gettext('Apply & Reload')}
            </Button>
          </>
        }
      >
        <Box sx={{display: 'grid', gap: 1.5}}>
          <TextField
            type="number"
            label={gettext('Window / Page Size')}
            value={String(limitsDraft.pageSize)}
            onChange={(e) =>
              setLimitsDraft((p) => ({...p, pageSize: Number(e.target.value)}))
            }
          />
          <TextField
            type="number"
            label={gettext('Maximum Host Buffered Rows')}
            value={String(limitsDraft.maxRows)}
            onChange={(e) =>
              setLimitsDraft((p) => ({...p, maxRows: Number(e.target.value)}))
            }
          />
        </Box>
      </Dialog>

      {/* Jump to Row # Dialog */}
      <Dialog
        open={jumpDialogOpen}
        title={gettext('Jump to Row #')}
        size="small"
        onClose={() => setJumpDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setJumpDialogOpen(false)}>
              {gettext('Cancel')}
            </Button>
            <Button
              intent="primary"
              onClick={async () => {
                const targetNum = Math.max(1, Number(jumpRowDraft) || 1);
                const winSz = hostData?.window_size || 200;
                const desiredPageOff = Math.floor((targetNum - 1) / winSz) * winSz;
                const localIdx = (targetNum - 1) % winSz;
                setJumpDialogOpen(false);
                if (desiredPageOff !== (hostData?.window_offset || 0)) {
                  await navigatePage(desiredPageOff);
                }
                setActiveRowIndex(localIdx);
                setTimeout(() => locateCurrentRow(), 30);
              }}
            >
              {gettext('Jump')}
            </Button>
          </>
        }
      >
        <TextField
          type="number"
          autoFocus
          label={gettext('Row Number (1-based)')}
          value={jumpRowDraft}
          onChange={(e) => setJumpRowDraft(e.target.value)}
        />
      </Dialog>

      {/* Save Specific Layout / Save or Apply Template Dialog */}
      <Dialog
        open={saveLayoutDialogOpen}
        title={gettext('Surface Layout & Templates')}
        size="medium"
        onClose={() => setSaveLayoutDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setSaveLayoutDialogOpen(false)}>
              {gettext('Close')}
            </Button>
            {layoutSaveScope !== 'apply_template' && (
              <Button
                intent="primary"
                onClick={async () => {
                  await callHost('save_layout', {
                    scope: layoutSaveScope,
                    template_name: templateNameDraft || 'Team Grid Layout',
                    layout,
                  });
                  setSaveLayoutDialogOpen(false);
                }}
              >
                {layoutSaveScope === 'template'
                  ? gettext('Save Template')
                  : gettext('Save Specific Layout')}
              </Button>
            )}
          </>
        }
      >
        <Box sx={{display: 'grid', gap: 1.5}}>
          <div style={{display: 'flex', gap: 8}}>
            <Button
              size="small"
              intent={layoutSaveScope === 'specific' ? 'primary' : 'neutral'}
              onClick={() => setLayoutSaveScope('specific')}
            >
              {gettext('Save Specific Layout (This Table)')}
            </Button>
            <Button
              size="small"
              intent={layoutSaveScope === 'template' ? 'primary' : 'neutral'}
              onClick={() => setLayoutSaveScope('template')}
            >
              {gettext('Save Shareable Template')}
            </Button>
            <Button
              size="small"
              intent={layoutSaveScope === 'apply_template' ? 'primary' : 'neutral'}
              onClick={() => setLayoutSaveScope('apply_template')}
            >
              {gettext('Apply Template (%s)', availableTemplates.length)}
            </Button>
          </div>
          {layoutSaveScope === 'template' && (
            <TextField
              label={gettext('Template Name')}
              value={templateNameDraft}
              onChange={(e) => setTemplateNameDraft(e.target.value)}
            />
          )}
          {layoutSaveScope === 'apply_template' && (
            <div style={{display: 'grid', gap: 6}}>
              {availableTemplates.length === 0 ? (
                <div style={{fontSize: '0.8rem', opacity: 0.75}}>
                  {gettext('No saved templates yet.')}
                </div>
              ) : (
                availableTemplates.map((tpl) => (
                  <button
                    key={tpl.template_id}
                    type="button"
                    className="sr-btn"
                    style={{justifyContent: 'space-between'}}
                    onClick={() => {
                      setLayout((prev) => ({...prev, ...(tpl.layout || {})}));
                      setSaveLayoutDialogOpen(false);
                    }}
                  >
                    <strong>{tpl.name}</strong>
                    <span style={{fontSize: '0.72rem', opacity: 0.7}}>
                      {tpl.updated_at}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </Box>
      </Dialog>

      {/* Shared Multi-Format Export Dialog (CSV/TSV, XLSX, ODS, PDF, JSON, SQL) */}
      <SurfaceExportDialog
        open={exportDialogOpen}
        onClose={() => setExportDialogOpen(false)}
        initialFormat={exportFormat}
        defaultFilename={targetResource?.display_name || 'rows'}
        defaultTitle={
          targetResource?.display_name
            ? `${targetResource.display_name} — Data Export`
            : 'Data Export'
        }
        tableName={targetResource?.display_name || 'EXPORT_TABLE'}
        rows={rows}
        columns={gridColumns}
        onExportHost={(req) => callHost('export_formatted', req)}
      />

      {/* Import Dialog (Stages imported rows into host batch!) */}
      <Dialog
        open={importDialogOpen}
        title={gettext('Import Rows (CSV / TSV / JSON) into Staged Batch')}
        size="medium"
        onClose={() => setImportDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setImportDialogOpen(false)}>
              {gettext('Cancel')}
            </Button>
            <Button
              intent="primary"
              loading={working}
              onClick={async () => {
                try {
                  const recs = parseImportedRecords(importTextDraft);
                  setWorking(true);
                  let lastResp = null;
                  for (const rec of recs) {
                    lastResp = await callHost('stage_row', {
                      op: 'insert',
                      changes: rec,
                    });
                  }
                  if (lastResp) applyHostResponse(lastResp);
                  setImportDialogOpen(false);
                  setImportTextDraft('');
                } catch (err) {
                  setSurfaceError(err?.message || String(err));
                } finally {
                  setWorking(false);
                }
              }}
            >
              {gettext('Stage Imported Rows')}
            </Button>
          </>
        }
      >
        <TextArea
          rows={9}
          label={gettext('Paste CSV, TSV (with header row), or JSON array')}
          value={importTextDraft}
          onChange={(e) => setImportTextDraft(e.target.value)}
        />
      </Dialog>
    </div>
  );
}

DataEditSurface.propTypes = {
  endpointLabel: PropTypes.string,
  engineId: PropTypes.string,
  languageProfile: PropTypes.string,
  databaseTargetId: PropTypes.string,
  targetResource: PropTypes.object,
  post: PropTypes.func.isRequired,
  onOpenInVisualSql: PropTypes.func,
  onOpenInSqlEditor: PropTypes.func,
};

function ColumnOrderDialog({
  open,
  scope,
  allColumns,
  visibleNames,
  orderNames,
  onClose,
  onApply,
}) {
  const [order, setOrder] = useState([]);
  const [checkedSet, setCheckedSet] = useState(new Set());

  useEffect(() => {
    if (!open) return;
    const allNames = (allColumns || []).map((c) => c.name);
    const mergedOrder = [
      ...(orderNames || []).filter((n) => allNames.includes(n)),
      ...allNames.filter((n) => !(orderNames || []).includes(n)),
    ];
    setOrder(mergedOrder);
    setCheckedSet(new Set(visibleNames || allNames));
  }, [open, allColumns, visibleNames, orderNames]);

  const move = (idx, dir) => {
    const dst = idx + dir;
    if (dst < 0 || dst >= order.length) return;
    const copy = [...order];
    const [item] = copy.splice(idx, 1);
    copy.splice(dst, 0, item);
    setOrder(copy);
  };

  return (
    <Dialog
      open={open}
      title={
        scope === 'form'
          ? gettext('Mini-Form / Single-Form Fields & Order')
          : gettext('Grid Columns & Field Order')
      }
      size="small"
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>{gettext('Cancel')}</Button>
          <Button
            intent="primary"
            onClick={() => {
              const vis = order.filter((n) => checkedSet.has(n));
              onApply(order, vis.length > 0 ? vis : [order[0]].filter(Boolean));
            }}
          >
            {gettext('Apply')}
          </Button>
        </>
      }
    >
      <Box sx={{display: 'grid', gap: 0.75, maxHeight: '55vh', overflowY: 'auto'}}>
        <Box sx={{display: 'flex', gap: 1, mb: 0.5}}>
          <Button size="small" onClick={() => setCheckedSet(new Set(order))}>
            {gettext('Select All')}
          </Button>
          <Button
            size="small"
            onClick={() => setOrder((allColumns || []).map((c) => c.name))}
          >
            {gettext('Reset Order')}
          </Button>
        </Box>
        {order.map((name, idx) => (
          <div
            key={name}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '4px 8px',
              borderRadius: 6,
              border: '1px solid var(--sr-border-subtle)',
            }}
          >
            <label style={{display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.82rem'}}>
              <input
                type="checkbox"
                checked={checkedSet.has(name)}
                onChange={(e) => {
                  const next = new Set(checkedSet);
                  if (e.target.checked) next.add(name);
                  else next.delete(name);
                  setCheckedSet(next);
                }}
              />
              <span>{name}</span>
            </label>
            <div style={{display: 'flex', gap: 4}}>
              <button
                type="button"
                className="sr-btn"
                aria-label={`Move ${name} up`}
                style={{minHeight: 22, padding: '0 6px'}}
                disabled={idx === 0}
                onClick={() => move(idx, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="sr-btn"
                aria-label={`Move ${name} down`}
                style={{minHeight: 22, padding: '0 6px'}}
                disabled={idx === order.length - 1}
                onClick={() => move(idx, 1)}
              >
                ↓
              </button>
            </div>
          </div>
        ))}
      </Box>
    </Dialog>
  );
}

ColumnOrderDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  scope: PropTypes.string,
  allColumns: PropTypes.array,
  visibleNames: PropTypes.array,
  orderNames: PropTypes.array,
  onClose: PropTypes.func.isRequired,
  onApply: PropTypes.func.isRequired,
};

function ExtendedSortDialog({open, columns, draft, onChangeDraft, onClose, onApply}) {
  const checkedMap = new Map((draft || []).map((s) => [s.column, s.direction]));
  return (
    <Dialog
      open={open}
      title={gettext('Extended Multi-Column Sort')}
      size="small"
      onClose={onClose}
      actions={
        <>
          <Button onClick={() => onApply([])}>{gettext('Clear Sort')}</Button>
          <Button onClick={onClose}>{gettext('Cancel')}</Button>
          <Button intent="primary" onClick={() => onApply(draft)}>
            {gettext('Apply Sort')}
          </Button>
        </>
      }
    >
      <Box sx={{display: 'grid', gap: 0.75, maxHeight: '55vh', overflowY: 'auto'}}>
        {(columns || []).map((col) => {
          const isChecked = checkedMap.has(col.name);
          const dir = checkedMap.get(col.name) || 'asc';
          const priority = (draft || []).findIndex((s) => s.column === col.name) + 1;
          return (
            <div
              key={col.name}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '4px 8px',
                borderRadius: 6,
                border: '1px solid var(--sr-border-subtle)',
              }}
            >
              <label style={{display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.82rem'}}>
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={(e) => {
                    if (e.target.checked) {
                      onChangeDraft([
                        ...(draft || []),
                        {column: col.name, direction: 'asc'},
                      ]);
                    } else {
                      onChangeDraft(
                        (draft || []).filter((s) => s.column !== col.name)
                      );
                    }
                  }}
                />
                <span>
                  {col.name} {isChecked ? `(#${priority})` : ''}
                </span>
              </label>
              {isChecked && (
                <select
                  className="sr-input"
                  style={{width: 96, minHeight: 24, padding: '1px 6px'}}
                  value={dir}
                  onChange={(e) =>
                    onChangeDraft(
                      (draft || []).map((s) =>
                        s.column === col.name
                          ? {...s, direction: e.target.value}
                          : s
                      )
                    )
                  }
                >
                  <option value="asc">ASC ↑</option>
                  <option value="desc">DESC ↓</option>
                </select>
              )}
            </div>
          );
        })}
      </Box>
    </Dialog>
  );
}

ExtendedSortDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  columns: PropTypes.array,
  draft: PropTypes.array,
  onChangeDraft: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
  onApply: PropTypes.func.isRequired,
};

function FilterBuilderDrawerPanel({columns, initialColumn, filters, onApply}) {
  const [col, setCol] = useState(initialColumn || columns[0]?.name || '');
  const [op, setOp] = useState('contains');
  const [val, setVal] = useState('');

  useEffect(() => {
    if (initialColumn) setCol(initialColumn);
  }, [initialColumn]);

  return (
    <Box
      data-cdeadmin-qa-key="data-surface-3b-filter-builder"
      sx={{p: 1.5, display: 'grid', gap: 1.25}}
    >
      <strong>{gettext('Column Filter Builder')}</strong>
      <div className="sr-field">
        <label className="sr-field-label">{gettext('Field')}</label>
        <select
          className="sr-input"
          value={col}
          onChange={(e) => setCol(e.target.value)}
        >
          {(columns || []).map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
      <div className="sr-field">
        <label className="sr-field-label">{gettext('Condition')}</label>
        <select
          className="sr-input"
          value={op}
          onChange={(e) => setOp(e.target.value)}
        >
          <option value="contains">{gettext('Contains')}</option>
          <option value="eq">{gettext('Equals (=)')}</option>
          <option value="neq">{gettext('Not Equal (<>)')}</option>
          <option value="starts_with">{gettext('Starts With')}</option>
          <option value="gt">{gettext('Greater Than (>)')}</option>
          <option value="gte">{gettext('Greater or Equal (>=)')}</option>
          <option value="lt">{gettext('Less Than (<)')}</option>
          <option value="lte">{gettext('Less or Equal (<=)')}</option>
          <option value="is_null">{gettext('IS NULL')}</option>
          <option value="not_null">{gettext('IS NOT NULL')}</option>
        </select>
      </div>
      {!['is_null', 'not_null'].includes(op) && (
        <TextField
          label={gettext('Value')}
          value={val}
          onChange={(e) => setVal(e.target.value)}
        />
      )}
      <Box sx={{display: 'flex', gap: 1}}>
        <Button
          intent="primary"
          size="small"
          onClick={() => {
            if (!col) return;
            onApply([
              ...(filters || []).filter((f) => f.column !== col),
              {column: col, op, value: val},
            ]);
          }}
        >
          {gettext('Add / Update Filter')}
        </Button>
        {(filters || []).length > 0 && (
          <Button size="small" onClick={() => onApply([])}>
            {gettext('Clear All')}
          </Button>
        )}
      </Box>
      <div style={{display: 'grid', gap: 4}}>
        {(filters || []).map((f, idx) => (
          <div
            key={`${f.column}-${idx}`}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '4px 8px',
              borderRadius: 6,
              border: '1px solid var(--sr-border-subtle)',
              fontSize: '0.76rem',
            }}
          >
            <span>
              <strong>{f.column}</strong> {f.op} {f.value}
            </span>
            <button
              type="button"
              className="sr-btn"
              style={{minHeight: 20, padding: '0 6px'}}
              onClick={() =>
                onApply((filters || []).filter((_, i) => i !== idx))
              }
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </Box>
  );
}

FilterBuilderDrawerPanel.propTypes = {
  columns: PropTypes.array,
  initialColumn: PropTypes.string,
  filters: PropTypes.array,
  onApply: PropTypes.func.isRequired,
};
