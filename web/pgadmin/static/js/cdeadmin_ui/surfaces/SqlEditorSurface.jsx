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
import {
  MariaSQL,
  MySQL,
  PostgreSQL,
  SQLDialect,
  SQLite,
  StandardSQL,
} from '@codemirror/lang-sql';
import {format as formatSqlPretty} from 'sql-formatter';
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
import CodeEditor from '../editors/CodeEditor';
import {firebirdSQLConfig} from '../editors/firebirdSyntax';
import {duckdbSQLConfig} from '../editors/duckdbSyntax';
import {RobinTiledCanvas} from '../integrations/ddn/RobinTiledCanvas';
import SurfaceExportDialog from './SurfaceExportDialog';
import {
  AdaptiveRecordFormCard,
  defaultLayoutState,
  orderedColumns,
} from './DataEditSurface';
import {
  BOOLEAN_FORMATS,
  DISPLAY_MODES,
  buildFormLayoutPlacements,
  coerceEditedValue,
  formatBytes,
  formatCellValue,
  formatRowsForExport,
  isComplexOrOversizedCell,
  serializeValueForEdit,
} from './dataEditSurfaceHelpers';

const DEFAULT_COL_WIDTH = 156;
const GUTTER_WIDTH = 58;
const EMPTY_ARRAY = Object.freeze([]);

export const SQL_SURFACE_VIEWS = Object.freeze({
  SQL: 'sql',
  VISUAL_BUILDER: 'visual_builder',
  SQL_DATA: 'sql_data',
  DATA: 'data',
  METRICS_PLAN: 'metrics_plan',
  FIELDS: 'fields',
  MESSAGES: 'messages',
});

function computeCursorOffset(sourceText, cursor) {
  if (!cursor || typeof cursor.line !== 'number') {
    return String(sourceText || '').length;
  }
  const lines = String(sourceText || '').split('\n');
  const lineIdx = Math.max(0, Math.min(lines.length - 1, (cursor.line || 1) - 1));
  let offset = 0;
  for (let i = 0; i < lineIdx; i += 1) {
    offset += lines[i].length + 1;
  }
  return offset + Math.max(0, cursor.ch ?? cursor.pos ?? 0);
}

function defaultVisualModel() {
  return {
    tables: [],
    projections: [],
    joins: [],
    where: [],
    group_by: [],
    having: [],
    order_by: [],
    distinct: false,
    limit: null,
  };
}

function coerceBoundParamValue(raw, paramType, isNull) {
  if (isNull) return null;
  const s = String(raw ?? '');
  if (paramType === 'integer') {
    const n = parseInt(s, 10);
    return Number.isNaN(n) ? 0 : n;
  }
  if (paramType === 'numeric') {
    const n = parseFloat(s);
    return Number.isNaN(n) ? 0 : n;
  }
  if (paramType === 'boolean') {
    return ['true', 't', '1', 'yes', 'y'].includes(s.trim().toLowerCase());
  }
  if (paramType === 'json') {
    try {
      return JSON.parse(s);
    } catch {
      return s;
    }
  }
  return s;
}

/**
 * Surface 2 — SQL Editor & Visual Query Builder (`sql: <DATABASE>`)
 *
 * Implements the strict Surface 1 UI standard:
 *   - Zero inline execution toolbars, connection banners, or sub-tabs inside Area 3e
 *   - TiB Pill 1 (7 full-Area-3e views):
 *       SQL | Visual Builder | SQL + Data | Data | Metrics & Plan | Fields | Messages
 *   - Visual Builder: 100% Area 3e shared DDN `<RobinTiledCanvas />` with Right Drawer
 *       clause/join inspector and bidirectional SQL sync (`exact` / `lossy` / `none`)
 *   - Data & SQL + Data: 100% Surface 1 Display Modes (`Standard Grid`, `Mini-Forms`,
 *       `Hybrid`, `Single Form`, `Hybrid-When-Editing`) + live row editing & batch staging
 *   - Execute Statement (`F9`) & Execute Script (`F5`) with Firebird `SET TERM` & active terminator
 *   - Modal Parameter Binding Dialog (`:param`, `?`, `$1`)
 *   - Multi-Tag SQL Snippets Library (`AND`/`OR` tag filter chips) & Quick Queries (SQL + layout)
 *   - Shared Multi-Format Export Dialog (`CSV/TSV`, `XLSX`, `ODS`, `PDF`, `JSON`, `SQL`)
 *   - Focus-merged Top Menus (`Query 15`, `Edit 20`, `View 25`, `Window 70`) + Firebird Close Guard
 */
export default function SqlEditorSurface({
  endpointLabel = '',
  engineId = 'relational',
  languageProfile = '',
  activeLanguage = null,
  databaseTargetId = null,
  targetResource = null,
  resources = EMPTY_ARRAY,
  initialScriptKind = '',
  initialSql = '',
  initialQuickQueryId = '',
  post,
}) {
  const shell = useProjectShell();
  const shellRef = useRef(shell);
  shellRef.current = shell;

  const instanceScope = useProjectInstanceScope();
  const instId = instanceScope?.instanceId || 'sql-surface-standalone';
  const surfaceIdRef = useRef(`ss-${instId}`);
  const editorRef = useRef(null);
  const fileInputRef = useRef(null);
  const canvasApiRef = useRef(null);
  const resourcesRef = useRef(resources);
  resourcesRef.current = resources;
  const postRef = useRef(post);
  postRef.current = post;

  const [surfaceView, setSurfaceView] = useState(SQL_SURFACE_VIEWS.SQL);
  const [splitOrientation, setSplitOrientation] = useState('vertical'); // 'vertical' (top/bottom) | 'horizontal' (left/right)
  const [splitRatio, setSplitRatio] = useState(46);

  const [sqlText, setSqlText] = useState(initialSql || '');
  const sqlTextRef = useRef(sqlText);
  sqlTextRef.current = sqlText;

  const [selectionText, setSelectionText] = useState('');
  const [cursorPos, setCursorPos] = useState({line: 1, col: 1});
  const [terminator, setTerminator] = useState(';');
  const [autocommit, setAutocommit] = useState(false);
  const [clientSqlDialect, setClientSqlDialect] = useState(3);
  const [limitsDraft, setLimitsDraft] = useState({pageSize: 200, maxRows: 1000});

  const [hostData, setHostData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [surfaceError, setSurfaceError] = useState('');

  // Surface 1 Display & Live Editing State for Data / SQL+Data
  const [layout, setLayout] = useState(defaultLayoutState);
  const [activeRowIndex, setActiveRowIndex] = useState(0);
  const [activeColName, setActiveColName] = useState('');
  const [isEditingRow, setIsEditingRow] = useState(false);
  const [editingRowIndex, setEditingRowIndex] = useState(null);
  const [isInsertDraft, setIsInsertDraft] = useState(false);
  const [rowDraft, setRowDraft] = useState(null);
  const [colPickerOpen, setColPickerOpen] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(960);
  const workAreaRef = useRef(null);

  // Visual Query Builder State (100% Area 3e RobinTiledCanvas + 3b Inspector)
  const [visualModel, setVisualModel] = useState(defaultVisualModel);
  const [visualScene, setVisualScene] = useState(null);
  const [visualFidelity, setVisualFidelity] = useState('exact');
  const [visualLossNotes, setVisualLossNotes] = useState(EMPTY_ARRAY);
  const [fanoutWarnings, setFanoutWarnings] = useState(EMPTY_ARRAY);
  const [selectedCanvasNodeId, setSelectedCanvasNodeId] = useState('');
  const [vbInspectorTab, setVbInspectorTab] = useState('tables');
  const [vbTableSearch, setVbTableSearch] = useState('');

  // Modal Parameter Binding Dialog State
  const [paramModalOpen, setParamModalOpen] = useState(false);
  const [detectedParams, setDetectedParams] = useState(EMPTY_ARRAY);
  const [paramDrafts, setParamDrafts] = useState({}); // { [key]: { value: '', type: 'text', isNull: false } }
  const pendingExecRef = useRef(null);

  // Tagged Snippets State (Right Drawer Area 3b)
  const [snippetsPayload, setSnippetsPayload] = useState({
    snippets: EMPTY_ARRAY,
    available_tags: EMPTY_ARRAY,
    active_tags: EMPTY_ARRAY,
    tag_mode: 'and',
  });
  const [snippetSearch, setSnippetSearch] = useState('');
  const [selectedTags, setSelectedTags] = useState(EMPTY_ARRAY);
  const [snippetTagMode, setSnippetTagMode] = useState('and');
  const [snippetFavoritesOnly, setSnippetFavoritesOnly] = useState(false);
  const [snippetAllEngines, setSnippetAllEngines] = useState(false);

  // Quick Queries & History State
  const [quickQueries, setQuickQueries] = useState(EMPTY_ARRAY);
  const [quickQueryModalOpen, setQuickQueryModalOpen] = useState(false);
  const [activeQuickQueryId, setActiveQuickQueryId] = useState(initialQuickQueryId || '');
  const [activeQuickQueryName, setActiveQuickQueryName] = useState('');
  const [localQueryHistory, setLocalQueryHistory] = useState(EMPTY_ARRAY);

  // Save / Snippet / Export / Limits / Connection Modals
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveKind, setSaveKind] = useState('quick_query'); // 'quick_query' | 'snippet' | 'sql_file' | 'bi_question' | 'layout'
  const [saveTitle, setSaveTitle] = useState('');
  const [saveDescription, setSaveDescription] = useState('');
  const [saveTagsText, setSaveTagsText] = useState('');
  const [saveShortcut, setSaveShortcut] = useState('');
  const [saveSnippetId, setSaveSnippetId] = useState('');
  const [saveUseSelection, setSaveUseSelection] = useState(false);

  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exportInitialFormat, setExportInitialFormat] = useState('csv');
  const [limitsModalOpen, setLimitsModalOpen] = useState(false);
  const [connectionModalOpen, setConnectionModalOpen] = useState(false);
  const [contextMenuState, setContextMenuState] = useState({
    open: false,
    x: 0,
    y: 0,
    items: EMPTY_ARRAY,
  });

  // Right Drawer (`Area 3b`) Contextual Panel State
  const [drawerState, setDrawerState] = useState({
    panel: 'snippets', // 'snippets' | 'visual_inspector' | 'history' | 'value_inspector' | 'staged_sql' | 'column_profile' | 'filter_builder'
    valueRowIndex: 0,
    valueColName: '',
    valueTab: 'text',
    profileData: null,
    filterColumn: '',
  });
  const drawerStateRef = useRef(drawerState);
  drawerStateRef.current = drawerState;

  // Coalesced ResizeObserver on Area 3e for responsive form wrapping
  useEffect(() => {
    const el = workAreaRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    let rafId = null;
    const obs = new ResizeObserver((entries) => {
      const w = entries?.[0]?.contentRect?.width;
      if (!w || w <= 80) return;
      const rounded = Math.round(w);
      const applyWidth = () => {
        rafId = null;
        setViewportWidth((prev) => (Math.abs(prev - rounded) >= 2 ? rounded : prev));
      };
      if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
        if (rafId !== null) window.cancelAnimationFrame(rafId);
        rafId = window.requestAnimationFrame(applyWidth);
      } else {
        applyWidth();
      }
    });
    obs.observe(el);
    return () => {
      if (rafId !== null && typeof window !== 'undefined' && typeof window.cancelAnimationFrame === 'function') {
        window.cancelAnimationFrame(rafId);
      }
      obs.disconnect();
    };
  }, []);

  const normEngine = useMemo(
    () => String(engineId || languageProfile || 'ansi').split('-')[0].toLowerCase(),
    [engineId, languageProfile]
  );
  const isFirebird = normEngine.includes('firebird') || languageProfile === 'firebird-sql';

  // CodeMirror SQL syntax dialect configuration
  const sqlEditorConfig = useMemo(() => {
    if (isFirebird) {
      return firebirdSQLConfig(
        activeLanguage?.editor?.keywords || '',
        clientSqlDialect,
        resources,
        activeLanguage?.editor?.reserved_words
      );
    }
    if (languageProfile === 'duckdb-sql') {
      return duckdbSQLConfig(activeLanguage?.editor, resources);
    }
    const nativeDialect =
      languageProfile === 'mariadb-sql'
        ? MariaSQL
        : /mysql|tidb|vitess|dolt/.test(languageProfile)
          ? MySQL
          : /postgres|cockroach|ysql|xtdb/.test(languageProfile)
            ? PostgreSQL
            : /sqlite/.test(languageProfile)
              ? SQLite
              : StandardSQL;
    return {
      dialect: activeLanguage?.editor?.keywords
        ? SQLDialect.define({
          ...nativeDialect.spec,
          keywords: activeLanguage.editor.keywords.toLowerCase(),
        })
        : nativeDialect,
    };
  }, [activeLanguage?.editor, clientSqlDialect, isFirebird, languageProfile, resources]);

  const callHost = useCallback(
    async (subAction, extra = {}) => {
      const payload = {
        action: 'sql_surface_action',
        request: {
          sub_action: subAction,
          surface_id: surfaceIdRef.current,
          database_target_id: databaseTargetId,
          language_profile: languageProfile,
          engine_id: engineId,
          resources: resourcesRef.current,
          window_offset: 0,
          window_size: 500,
          ...extra,
        },
      };
      return postRef.current(payload);
    },
    [databaseTargetId, engineId, languageProfile]
  );

  const openRightDrawerWith = useCallback(
    (patch) => {
      const merged = {...drawerStateRef.current, ...patch};
      drawerStateRef.current = merged;
      setDrawerState(merged);
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

  const refreshSnippets = useCallback(
    async (overrides = {}) => {
      try {
        const res = await callHost('list_snippets', {
          search_text: overrides.search_text ?? snippetSearch,
          selected_tags: overrides.selected_tags ?? selectedTags,
          tag_mode: overrides.tag_mode ?? snippetTagMode,
          favorites_only: overrides.favorites_only ?? snippetFavoritesOnly,
          include_all_engines: overrides.include_all_engines ?? snippetAllEngines,
        });
        if (Array.isArray(res?.snippets)) {
          setSnippetsPayload(res);
        } else if (Array.isArray(res?.snippets?.snippets)) {
          setSnippetsPayload(res.snippets);
        }
      } catch {
        // Non-fatal in offline/unit setups
      }
    },
    [callHost, selectedTags, snippetAllEngines, snippetFavoritesOnly, snippetSearch, snippetTagMode]
  );

  const applyHostState = useCallback((resp) => {
    if (!resp) return;
    setHostData(resp);
    if (resp.terminator) setTerminator(resp.terminator);
    if (typeof resp.autocommit === 'boolean') setAutocommit(resp.autocommit);
    if (Array.isArray(resp.quick_queries)) setQuickQueries(resp.quick_queries);
    if (Array.isArray(resp.snippets?.snippets)) setSnippetsPayload(resp.snippets);
    const activeCols = resp.active_result?.columns || EMPTY_ARRAY;
    if (activeCols.length > 0) {
      setActiveColName((cur) =>
        activeCols.some((c) => c.name === cur) ? cur : activeCols[0].name
      );
    }
  }, []);

  // Initial surface mount: open host SQL surface, optionally generating object SQL or loading Quick Query
  useEffect(() => {
    let active = true;
    const boot = async () => {
      setLoading(true);
      setSurfaceError('');
      try {
        const resp = await callHost('open', {
          sql_source: initialSql || '',
          target_resource: targetResource,
          generate_sql_kind: initialScriptKind || '',
          page_size: limitsDraft.pageSize,
          max_rows: limitsDraft.maxRows,
          autocommit,
        });
        if (!active) return;
        applyHostState(resp);
        if (resp?.sql_source && !initialSql) {
          setSqlText(resp.sql_source);
          editorRef.current?.setValue?.(resp.sql_source);
        }
        if (initialQuickQueryId) {
          const qqRes = await callHost('load_quick_query', {query_id: initialQuickQueryId});
          if (!active) return;
          if (qqRes?.loaded_quick_query) {
            const qq = qqRes.loaded_quick_query;
            setActiveQuickQueryId(qq.query_id);
            setActiveQuickQueryName(qq.name || '');
            setSqlText(qq.sql_text || '');
            editorRef.current?.setValue?.(qq.sql_text || '');
            if (qq.terminator) setTerminator(qq.terminator);
            if (qq.display_layout && Object.keys(qq.display_layout).length > 0) {
              setLayout((prev) => ({...prev, ...qq.display_layout}));
            }
          }
          if (qqRes?.state) applyHostState(qqRes.state);
        }
      } catch (err) {
        if (active) setSurfaceError(err?.message || String(err));
      } finally {
        if (active) setLoading(false);
      }
    };
    boot();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [databaseTargetId, targetResource?.resource_id, initialScriptKind, initialQuickQueryId]);

  useEffect(() => {
    refreshSnippets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snippetSearch, selectedTags, snippetTagMode, snippetFavoritesOnly, snippetAllEngines]);

  // Active Result Set & Surface 1 Data Columns / Rows
  const activeResult = hostData?.active_result || null;
  const columns = useMemo(
    () => activeResult?.columns || EMPTY_ARRAY,
    [activeResult?.columns]
  );
  const rows = useMemo(() => {
    const base = activeResult?.rows || EMPTY_ARRAY;
    if (isInsertDraft && rowDraft) {
      return [
        ...base,
        {
          row_number: (activeResult?.total_view_rows || base.length) + 1,
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
  }, [activeResult?.rows, activeResult?.total_view_rows, isInsertDraft, rowDraft]);

  const gridColumns = useMemo(
    () => orderedColumns(columns, layout.gridColOrder, layout.gridVisibleCols),
    [columns, layout.gridColOrder, layout.gridVisibleCols]
  );
  const formColumns = useMemo(
    () => orderedColumns(columns, layout.formColOrder, layout.formVisibleCols),
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
  const isEditableResult = Boolean(activeResult?.editable);
  const canInsertResult = Boolean(
    activeResult?.editable || (activeResult?.row_operations || []).includes('insert')
  );

  // Uncommitted transaction / staged edits close guard (`Yes` Commit / `No` Rollback / `Cancel`)
  const hasUncommitted = Boolean(
    hostData?.has_uncommitted_activity ||
    (hostData?.staged_count || 0) > 0 ||
    isEditingRow
  );
  const hasUncommittedRef = useRef(hasUncommitted);
  hasUncommittedRef.current = hasUncommitted;

  const confirmCloseGuard = useCallback(async () => {
    if (!hasUncommittedRef.current) {
      try {
        await callHost('close_surface');
      } catch {
        // Ignore teardown error
      }
      return true;
    }
    const decision = await promptAbandonUncommittedWork({
      surfaceTitle: endpointLabel ? `sql: ${endpointLabel}` : gettext('SQL Editor'),
      stagedCount: hostData?.staged_count || 0,
      isFirebird,
    });
    if (decision === 'cancel') return false;
    try {
      if (decision === 'commit') {
        await callHost('commit_batch');
      } else {
        await callHost('rollback_batch');
      }
      await callHost('close_surface');
    } catch {
      // Allow close after best-effort cleanup
    }
    return true;
  }, [callHost, endpointLabel, hostData?.staged_count, isFirebird]);

  const confirmCloseGuardRef = useRef(confirmCloseGuard);
  confirmCloseGuardRef.current = confirmCloseGuard;
  const stableConfirmCloseGuard = useCallback(
    () => confirmCloseGuardRef.current(),
    []
  );

  useModalCloseGuard(stableConfirmCloseGuard);

  // Visual Builder Sync Helpers
  const syncSqlIntoVisualBuilder = useCallback(
    async (sourceOverride) => {
      const src = sourceOverride ?? sqlTextRef.current;
      try {
        const res = await callHost('visual_builder_from_sql', {sql_text: src});
        if (res?.model) setVisualModel(res.model);
        if (res?.scene) setVisualScene(res.scene);
        setVisualFidelity(res?.fidelity || 'exact');
        setVisualLossNotes(res?.loss_notes || EMPTY_ARRAY);
        setFanoutWarnings(res?.fanout_warnings || EMPTY_ARRAY);
      } catch (err) {
        setSurfaceError(err?.message || String(err));
      }
    },
    [callHost]
  );

  const pushVisualModelUpdate = useCallback(
    async (nextModel, syncSqlNow = true) => {
      setVisualModel(nextModel);
      try {
        const res = await callHost('visual_builder_scene', {model: nextModel});
        if (res?.scene) setVisualScene(res.scene);
        setFanoutWarnings(res?.fanout_warnings || EMPTY_ARRAY);
        if (syncSqlNow && typeof res?.sql_text === 'string' && res.sql_text.trim()) {
          setSqlText(res.sql_text);
          editorRef.current?.setValue?.(res.sql_text);
          setVisualFidelity('exact');
          setVisualLossNotes(EMPTY_ARRAY);
        }
      } catch (err) {
        setSurfaceError(err?.message || String(err));
      }
    },
    [callHost]
  );

  const switchSurfaceView = useCallback(
    async (nextView) => {
      setSurfaceView(nextView);
      if (nextView === SQL_SURFACE_VIEWS.VISUAL_BUILDER) {
        await syncSqlIntoVisualBuilder(sqlTextRef.current);
        openRightDrawerWith({panel: 'visual_inspector'});
      }
    },
    [openRightDrawerWith, syncSqlIntoVisualBuilder]
  );

  // Core SQL Execution (`statement`, `script`, `explain`) + Automatic Parameter Detection
  const dispatchExecution = useCallback(
    async (execSpec, boundParams = null) => {
      setExecuting(true);
      setSurfaceError('');
      try {
        const resp = await callHost('execute', {
          mode: execSpec.mode,
          sql_source: execSpec.sqlSource,
          selection_text: execSpec.selectionText,
          cursor_offset: execSpec.cursorOffset,
          terminator,
          autocommit,
          client_sql_dialect: clientSqlDialect,
          page_size: limitsDraft.pageSize,
          max_rows: limitsDraft.maxRows,
          parameters: boundParams,
        });
        applyHostState(resp);
        setIsEditingRow(false);
        setEditingRowIndex(null);
        setIsInsertDraft(false);
        setRowDraft(null);
        setActiveRowIndex(0);

        setLocalQueryHistory((prev) => [
          {
            id: `qh-${Date.now()}`,
            timestamp: new Date().toISOString(),
            mode: execSpec.mode,
            sql: (execSpec.selectionText || execSpec.sqlSource || '').trim(),
            ok: !resp?.last_execution_had_error,
          },
          ...prev.slice(0, 99),
        ]);

        // Auto-switch view per Surface 2 specification:
        if (resp?.last_execution_had_error) {
          setSurfaceView(SQL_SURFACE_VIEWS.MESSAGES);
        } else if (execSpec.mode === 'explain') {
          setSurfaceView(SQL_SURFACE_VIEWS.METRICS_PLAN);
        } else if ((resp?.result_count || 0) > 0) {
          setSurfaceView((cur) =>
            cur === SQL_SURFACE_VIEWS.SQL_DATA ? SQL_SURFACE_VIEWS.SQL_DATA : SQL_SURFACE_VIEWS.DATA
          );
        } else {
          setSurfaceView(SQL_SURFACE_VIEWS.MESSAGES);
        }
      } catch (err) {
        setSurfaceError(err?.message || String(err));
        setSurfaceView(SQL_SURFACE_VIEWS.MESSAGES);
      } finally {
        setExecuting(false);
      }
    },
    [
      applyHostState,
      autocommit,
      callHost,
      clientSqlDialect,
      limitsDraft.maxRows,
      limitsDraft.pageSize,
      terminator,
    ]
  );

  const runSql = useCallback(
    async (mode = 'statement', skipParamPrompt = false) => {
      const liveText = editorRef.current?.getValue?.() ?? sqlTextRef.current;
      if (liveText !== sqlTextRef.current) {
        setSqlText(liveText);
      }
      const liveSel = editorRef.current?.getSelection?.() ?? selectionText;
      const cur = editorRef.current?.getCursor?.();
      const cursorOffset = computeCursorOffset(liveText, cur || {line: cursorPos.line, ch: cursorPos.col - 1});

      if (!String(liveText || '').trim()) return;

      const execSpec = {
        mode,
        sqlSource: liveText,
        selectionText: mode === 'statement' ? liveSel : '',
        cursorOffset,
      };

      if (!skipParamPrompt && mode !== 'explain') {
        try {
          const check = await callHost('check_parameters', {
            mode,
            sql_source: liveText,
            selection_text: execSpec.selectionText,
            cursor_offset: cursorOffset,
            terminator,
          });
          const params = check?.parameters || EMPTY_ARRAY;
          if (params.length > 0) {
            setDetectedParams(params);
            setParamDrafts((prev) => {
              const next = {...prev};
              for (const p of params) {
                const key = p.name || String(p.index);
                if (!next[key]) {
                  next[key] = {value: '', type: 'text', isNull: false};
                }
              }
              return next;
            });
            pendingExecRef.current = execSpec;
            setParamModalOpen(true);
            return;
          }
        } catch {
          // Proceed directly if parameter probe unavailable
        }
      }
      await dispatchExecution(execSpec, null);
    },
    [callHost, cursorPos.col, cursorPos.line, dispatchExecution, selectionText, terminator]
  );

  const openParametersDialog = useCallback(async () => {
    const liveText = editorRef.current?.getValue?.() ?? sqlTextRef.current;
    try {
      const check = await callHost('check_parameters', {
        mode: 'script',
        sql_source: liveText,
        terminator,
      });
      const params = check?.parameters || EMPTY_ARRAY;
      setDetectedParams(params);
      setParamDrafts((prev) => {
        const next = {...prev};
        for (const p of params) {
          const key = p.name || String(p.index);
          if (!next[key]) {
            next[key] = {value: '', type: 'text', isNull: false};
          }
        }
        return next;
      });
    } catch {
      setDetectedParams(EMPTY_ARRAY);
    }
    pendingExecRef.current = null;
    setParamModalOpen(true);
  }, [callHost, terminator]);

  const confirmParametersModal = useCallback(async () => {
    const hasNamed = detectedParams.some((p) => p.kind === 'named');
    let bound = null;
    if (detectedParams.length > 0) {
      if (hasNamed) {
        bound = {};
        for (const p of detectedParams) {
          const d = paramDrafts[p.name] || {value: '', type: 'text', isNull: false};
          bound[p.name] = coerceBoundParamValue(d.value, d.type, d.isNull);
        }
      } else {
        bound = detectedParams.map((p) => {
          const key = p.name || String(p.index);
          const d = paramDrafts[key] || {value: '', type: 'text', isNull: false};
          return coerceBoundParamValue(d.value, d.type, d.isNull);
        });
      }
    }
    const execSpec = pendingExecRef.current;
    pendingExecRef.current = null;
    setParamModalOpen(false);
    if (execSpec) {
      await dispatchExecution(execSpec, bound);
    }
  }, [detectedParams, dispatchExecution, paramDrafts]);

  // Surface 1 Live Row Editing & Batch Staging on Active Result Set
  const acceptCurrentRow = useCallback(async () => {
    if (!isEditingRow || !rowDraft) return true;
    setExecuting(true);
    try {
      const op = isInsertDraft ? 'insert' : 'update';
      const baseRow = !isInsertDraft ? rows[editingRowIndex] : null;
      const changes = {};
      for (const col of columns) {
        if (col.read_only && !isInsertDraft) continue;
        const nextVal = rowDraft[col.name];
        const origVal = baseRow?.values?.[col.name];
        if (isInsertDraft) {
          if (nextVal !== undefined) changes[col.name] = nextVal;
        } else if (JSON.stringify(nextVal) !== JSON.stringify(origVal)) {
          changes[col.name] = nextVal;
        }
      }
      if (Object.keys(changes).length > 0) {
        const resp = await callHost('stage_row', {
          op,
          base_row_index: baseRow?.base_row_index,
          changes,
        });
        applyHostState(resp);
      }
      setIsEditingRow(false);
      setEditingRowIndex(null);
      setIsInsertDraft(false);
      setRowDraft(null);
      return true;
    } catch (err) {
      setSurfaceError(err?.message || String(err));
      return false;
    } finally {
      setExecuting(false);
    }
  }, [applyHostState, callHost, columns, editingRowIndex, isEditingRow, isInsertDraft, rowDraft, rows]);

  const beginEditRow = useCallback(
    (targetIdx = activeRowIndex) => {
      if (!isEditableResult) return;
      const r = rows[targetIdx];
      if (!r) return;
      setActiveRowIndex(targetIdx);
      setEditingRowIndex(targetIdx);
      setRowDraft({...(r.values || {})});
      setIsInsertDraft(false);
      setIsEditingRow(true);
    },
    [activeRowIndex, isEditableResult, rows]
  );

  const beginInsertRow = useCallback(
    async (duplicateCurrent = false) => {
      if (!canInsertResult) return;
      if (isEditingRow) {
        const ok = await acceptCurrentRow();
        if (!ok) return;
      }
      const seed = {};
      if (duplicateCurrent && currentRow?.values) {
        for (const col of columns) {
          if (!col.key) seed[col.name] = currentRow.values[col.name];
        }
      }
      setRowDraft(seed);
      setIsInsertDraft(true);
      setIsEditingRow(true);
      const nextIdx = rows.length;
      setActiveRowIndex(nextIdx);
      setEditingRowIndex(nextIdx);
    },
    [acceptCurrentRow, canInsertResult, columns, currentRow?.values, isEditingRow, rows.length]
  );

  const stageDeleteRow = useCallback(
    async (targetIdx = activeRowIndex) => {
      if (!isEditableResult) return;
      const r = rows[targetIdx];
      if (!r || r.base_row_index === null || r.base_row_index === undefined) return;
      setExecuting(true);
      try {
        const resp = await callHost('stage_row', {
          op: 'delete',
          base_row_index: r.base_row_index,
        });
        applyHostState(resp);
      } catch (err) {
        setSurfaceError(err?.message || String(err));
      } finally {
        setExecuting(false);
      }
    },
    [activeRowIndex, applyHostState, callHost, isEditableResult, rows]
  );

  const handleCommit = useCallback(async () => {
    if (isEditingRow) {
      const ok = await acceptCurrentRow();
      if (!ok) return;
    }
    setExecuting(true);
    try {
      const resp = await callHost('commit_batch');
      applyHostState(resp);
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setExecuting(false);
    }
  }, [acceptCurrentRow, applyHostState, callHost, isEditingRow]);

  const handleRollback = useCallback(async () => {
    setIsEditingRow(false);
    setEditingRowIndex(null);
    setIsInsertDraft(false);
    setRowDraft(null);
    setExecuting(true);
    try {
      const resp = await callHost('rollback_batch');
      applyHostState(resp);
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setExecuting(false);
    }
  }, [applyHostState, callHost]);

  const handleToggleSort = useCallback(
    async (colName, additive = false) => {
      const curSort = activeResult?.sort || EMPTY_ARRAY;
      const existing = curSort.find((s) => s.column === colName);
      const nextDir = !existing ? 'asc' : existing.dir === 'asc' ? 'desc' : null;
      let nextSort;
      if (additive) {
        nextSort = curSort.filter((s) => s.column !== colName);
        if (nextDir) nextSort.push({column: colName, dir: nextDir});
      } else {
        nextSort = nextDir ? [{column: colName, dir: nextDir}] : [];
      }
      const resp = await callHost('query_view', {
        sort: nextSort,
        filters: activeResult?.filters || EMPTY_ARRAY,
      });
      applyHostState(resp);
    },
    [activeResult?.filters, activeResult?.sort, applyHostState, callHost]
  );

  const handleApplyFilters = useCallback(
    async (nextFilters) => {
      const resp = await callHost('query_view', {
        sort: activeResult?.sort || EMPTY_ARRAY,
        filters: nextFilters,
      });
      applyHostState(resp);
    },
    [activeResult?.sort, applyHostState, callHost]
  );

  const handleFormatSql = useCallback(() => {
    const cur = editorRef.current?.getValue?.() ?? sqlTextRef.current;
    if (!cur.trim()) return;
    try {
      const formatted = formatSqlPretty(cur, {
        language: isFirebird ? 'sql' : 'postgresql',
        keywordCase: 'upper',
      });
      setSqlText(formatted);
      editorRef.current?.setValue?.(formatted);
    } catch {
      // Leave unformatted when dialect uses non-standard procedural syntax
    }
  }, [isFirebird]);

  const insertSnippetText = useCallback((snippetSql, replaceAll = false) => {
    if (replaceAll || !sqlTextRef.current.trim()) {
      setSqlText(snippetSql);
      editorRef.current?.setValue?.(snippetSql);
    } else if (editorRef.current?.replaceSelection) {
      editorRef.current.replaceSelection(snippetSql);
      const updated = editorRef.current.getValue?.() ?? `${sqlTextRef.current}\n${snippetSql}`;
      setSqlText(updated);
    } else {
      const updated = `${sqlTextRef.current.replace(/\s*$/, '')}\n\n${snippetSql}`;
      setSqlText(updated);
      editorRef.current?.setValue?.(updated);
    }
    setSurfaceView((cur) =>
      cur === SQL_SURFACE_VIEWS.SQL_DATA ? SQL_SURFACE_VIEWS.SQL_DATA : SQL_SURFACE_VIEWS.SQL
    );
  }, []);

  const openSaveDialog = useCallback(
    (kind = 'quick_query', fromSelection = false) => {
      setSaveKind(kind);
      setSaveSnippetId('');
      setSaveUseSelection(Boolean(fromSelection && selectionText.trim()));
      setSaveTitle(
        kind === 'quick_query'
          ? activeQuickQueryName || targetResource?.display_name || 'Quick Query'
          : ''
      );
      setSaveDescription('');
      setSaveTagsText(isFirebird ? 'firebird, dml' : `${normEngine}, dml`);
      setSaveShortcut('');
      setSaveModalOpen(true);
    },
    [activeQuickQueryName, isFirebird, normEngine, selectionText, targetResource?.display_name]
  );

  const handleConfirmSave = useCallback(async () => {
    const fullSql = editorRef.current?.getValue?.() ?? sqlTextRef.current;
    const chosenSql = saveUseSelection && selectionText.trim() ? selectionText : fullSql;

    if (saveKind === 'sql_file') {
      if (typeof Blob !== 'undefined' && typeof URL?.createObjectURL === 'function') {
        const blob = new Blob([chosenSql], {type: 'application/sql;charset=utf-8'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(saveTitle || 'query').replace(/[^a-zA-Z0-9._-]+/g, '_')}.sql`;
        a.click();
        URL.revokeObjectURL(url);
      }
      setSaveModalOpen(false);
      return;
    }

    if (saveKind === 'bi_question') {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('scratchrobin:open-app-surface', {
            detail: {
              appId: 'bi-designer',
              payload: {
                title: saveTitle || gettext('Draft BI Question'),
                draft_sql: chosenSql,
                database_target_id: databaseTargetId,
              },
            },
          })
        );
      }
      setSaveModalOpen(false);
      return;
    }

    if (saveKind === 'snippet') {
      const tags = saveTagsText
        .split(',')
        .map((t) => t.trim().toLowerCase())
        .filter(Boolean);
      const res = await callHost('save_snippet', {
        snippet: {
          ...(saveSnippetId ? {snippet_id: saveSnippetId} : {}),
          title: saveTitle || 'SQL Snippet',
          description: saveDescription,
          shortcut: saveShortcut,
          engine_id: normEngine || 'ansi',
          scope: 'user',
          sql_text: chosenSql,
          tags,
        },
      });
      if (res?.snippets) setSnippetsPayload(res.snippets);
      setSaveModalOpen(false);
      openRightDrawerWith({panel: 'snippets'});
      return;
    }

    // Default: 'quick_query' (saves SQL + terminator + parameter defaults + full Surface 1 display layout!)
    const paramDefaults = Object.entries(paramDrafts).map(([name, d]) => ({
      name,
      type: d.type,
      value: d.value,
      isNull: d.isNull,
    }));
    const res = await callHost('save_quick_query', {
      quick_query: {
        ...(activeQuickQueryId ? {query_id: activeQuickQueryId} : {}),
        name: saveTitle || 'Quick Query',
        description: saveDescription,
        sql_text: chosenSql,
        terminator,
        parameters: paramDefaults,
        display_layout: layout,
      },
    });
    if (res?.saved_quick_query) {
      setActiveQuickQueryId(res.saved_quick_query.query_id);
      setActiveQuickQueryName(res.saved_quick_query.name);
    }
    if (Array.isArray(res?.quick_queries)) {
      setQuickQueries(res.quick_queries);
    }
    setSaveModalOpen(false);
  }, [
    activeQuickQueryId,
    callHost,
    databaseTargetId,
    layout,
    normEngine,
    openRightDrawerWith,
    paramDrafts,
    saveDescription,
    saveKind,
    saveShortcut,
    saveSnippetId,
    saveTagsText,
    saveTitle,
    saveUseSelection,
    selectionText,
    terminator,
  ]);

  const handleLoadQuickQuery = useCallback(
    async (queryId) => {
      const res = await callHost('load_quick_query', {query_id: queryId});
      if (res?.loaded_quick_query) {
        const qq = res.loaded_quick_query;
        setActiveQuickQueryId(qq.query_id);
        setActiveQuickQueryName(qq.name || '');
        setSqlText(qq.sql_text || '');
        editorRef.current?.setValue?.(qq.sql_text || '');
        if (qq.terminator) setTerminator(qq.terminator);
        if (qq.display_layout && Object.keys(qq.display_layout).length > 0) {
          setLayout((prev) => ({...prev, ...qq.display_layout}));
        }
        if (Array.isArray(qq.parameters) && qq.parameters.length > 0) {
          const restored = {};
          for (const p of qq.parameters) {
            if (p?.name) {
              restored[p.name] = {
                value: p.value ?? '',
                type: p.type || 'text',
                isNull: Boolean(p.isNull),
              };
            }
          }
          setParamDrafts(restored);
        }
      }
      if (res?.state) applyHostState(res.state);
      setQuickQueryModalOpen(false);
    },
    [applyHostState, callHost]
  );

  // Jump from Messages log back to SQL Line:Col or Data Row #
  const jumpToSqlPosition = useCallback((line, col = 1) => {
    setSurfaceView((cur) =>
      cur === SQL_SURFACE_VIEWS.SQL_DATA ? SQL_SURFACE_VIEWS.SQL_DATA : SQL_SURFACE_VIEWS.SQL
    );
    setCursorPos({line: line || 1, col: col || 1});
    setTimeout(() => {
      editorRef.current?.setCursor?.((line || 1) - 1, Math.max(0, (col || 1) - 1));
      editorRef.current?.focus?.();
    }, 20);
  }, []);

  // Handlers ref so TiB / Top Menu callbacks never trigger stale closures or re-registration loops
  const handlersRef = useRef({});
  handlersRef.current = {
    switchSurfaceView,
    runSql,
    openParametersDialog,
    handleCommit,
    handleRollback,
    beginEditRow,
    acceptCurrentRow,
    beginInsertRow,
    stageDeleteRow,
    handleFormatSql,
    openSaveDialog,
    openRightDrawerWith,
    setQuickQueryModalOpen,
    setExportDialogOpen,
    setExportInitialFormat,
    setLimitsModalOpen,
    setConnectionModalOpen,
    setTerminator,
    setAutocommit: async (nextVal) => {
      setAutocommit(nextVal);
      const resp = await callHost('set_options', {autocommit: nextVal});
      applyHostState(resp);
    },
    selectResultIndex: async (idx) => {
      const resp = await callHost('select_result', {result_index: idx});
      applyHostState(resp);
    },
    cancelExecution: async () => {
      const resp = await callHost('cancel');
      applyHostState(resp);
    },
    triggerFileOpen: () => fileInputRef.current?.click?.(),
    setLayout,
    setSplitOrientation,
    pushVisualModelUpdate,
    visualModel,
    isEditingRow,
    rows,
    gridColumns,
  };

  // Render Right Drawer (`Area 3b`) Content
  const renderRightDrawerContent = useCallback(() => {
    const ds = drawerStateRef.current;

    if (ds.panel === 'visual_inspector') {
      const catalogTables = (resources || []).filter((r) =>
        ['table', 'view', 'materialized-view', 'foreign-table'].includes(r.resource_kind)
      );
      const filteredCatalog = catalogTables.filter((t) =>
        !vbTableSearch.trim() ||
        String(t.display_name || t.name || '')
          .toLowerCase()
          .includes(vbTableSearch.trim().toLowerCase())
      );
      const availableCols = visualModel.tables.flatMap((tbl) =>
        (tbl.columns || []).map((c) => ({
          ref: `${tbl.alias || tbl.name}.${c.name}`,
          tableAlias: tbl.alias || tbl.name,
          colName: c.name,
          type: c.type || 'TEXT',
        }))
      );

      return (
        <Box
          data-cdeadmin-qa-key="sql-surface-3b-visual-inspector"
          sx={{p: 1.5, display: 'grid', gap: 1.25}}
        >
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
            <strong>{gettext('Visual Query Inspector')}</strong>
            <span
              data-cdeadmin-qa-key="visual-builder-fidelity-badge"
              style={{
                padding: '2px 8px',
                borderRadius: 999,
                fontSize: '0.72rem',
                fontWeight: 600,
                background:
                  visualFidelity === 'exact'
                    ? 'rgba(22, 163, 74, 0.14)'
                    : visualFidelity === 'lossy'
                      ? 'rgba(217, 119, 6, 0.16)'
                      : 'rgba(220, 38, 38, 0.14)',
              }}
            >
              {gettext('Sync: %s', visualFidelity)}
            </span>
          </div>

          {visualLossNotes.length > 0 && (
            <div
              style={{
                padding: '6px 8px',
                borderRadius: 6,
                background: 'rgba(217, 119, 6, 0.12)',
                fontSize: '0.75rem',
              }}
            >
              {visualLossNotes.join(' ')}
            </div>
          )}

          {fanoutWarnings.length > 0 && (
            <div
              data-cdeadmin-qa-key="visual-builder-fanout-warning"
              style={{
                padding: '6px 8px',
                borderRadius: 6,
                background: 'rgba(220, 38, 38, 0.12)',
                border: '1px solid var(--sr-status-danger, #dc2626)',
                fontSize: '0.75rem',
              }}
            >
              {fanoutWarnings.map((w, idx) => (
                <div key={idx}>⚠ {w}</div>
              ))}
            </div>
          )}

          <div style={{display: 'flex', gap: 4, flexWrap: 'wrap'}}>
            {[
              ['tables', gettext('Tables')],
              ['columns', gettext('Columns')],
              ['joins', gettext('Joins')],
              ['clauses', gettext('Clauses')],
            ].map(([tid, lbl]) => (
              <Button
                key={tid}
                size="small"
                intent={vbInspectorTab === tid ? 'primary' : 'neutral'}
                onClick={() => setVbInspectorTab(tid)}
              >
                {lbl}
              </Button>
            ))}
          </div>

          {vbInspectorTab === 'tables' && (
            <div style={{display: 'grid', gap: 8}}>
              <TextField
                label={gettext('Add Catalog Table / View')}
                placeholder={gettext('Filter tables…')}
                value={vbTableSearch}
                onChange={(e) => setVbTableSearch(e.target.value)}
              />
              <div style={{maxHeight: 160, overflow: 'auto', display: 'grid', gap: 4}}>
                {filteredCatalog.slice(0, 40).map((res) => {
                  const tname = res.display_name || res.name;
                  return (
                    <div
                      key={res.resource_id || tname}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '4px 8px',
                        borderRadius: 6,
                        border: '1px solid var(--sr-border-subtle)',
                        fontSize: '0.78rem',
                      }}
                    >
                      <span>{tname}</span>
                      <Button
                        size="small"
                        data-cdeadmin-qa-key={`vb-add-table-${tname}`}
                        onClick={() => {
                          const idx = visualModel.tables.length + 1;
                          const alias = `t${idx}`;
                          const rawCols =
                            res.extensions?.cdeadmin?.catalog_metadata?.columns ||
                            res.columns ||
                            [];
                          const cols = rawCols.map((c) => ({
                            name: c.name || c.column_name,
                            type: c.native_type || c.data_type || 'VARCHAR',
                            key: Boolean(c.primary_key || c.key),
                          }));
                          const next = {
                            ...visualModel,
                            tables: [
                              ...visualModel.tables,
                              {
                                id: `tbl_${alias}_${tname}`,
                                name: tname,
                                alias,
                                columns: cols,
                              },
                            ],
                          };
                          pushVisualModelUpdate(next, true);
                        }}
                      >
                        + {gettext('Add')}
                      </Button>
                    </div>
                  );
                })}
              </div>

              <strong>{gettext('Canvas Tables (%s)', visualModel.tables.length)}</strong>
              {visualModel.tables.map((t, idx) => (
                <div
                  key={t.id || idx}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '5px 8px',
                    borderRadius: 6,
                    background:
                      selectedCanvasNodeId === t.id
                        ? 'var(--sr-accent-muted, rgba(37,99,235,0.12))'
                        : 'transparent',
                    border: '1px solid var(--sr-border-subtle)',
                    fontSize: '0.78rem',
                  }}
                >
                  <span>
                    <strong>{t.name}</strong> ({t.alias})
                  </span>
                  <Button
                    size="small"
                    onClick={() => {
                      const next = {
                        ...visualModel,
                        tables: visualModel.tables.filter((_, i) => i !== idx),
                      };
                      pushVisualModelUpdate(next, true);
                    }}
                  >
                    ×
                  </Button>
                </div>
              ))}
            </div>
          )}

          {vbInspectorTab === 'columns' && (
            <div style={{display: 'grid', gap: 6}}>
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem'}}>
                  <input
                    type="checkbox"
                    checked={Boolean(visualModel.distinct)}
                    onChange={(e) =>
                      pushVisualModelUpdate({...visualModel, distinct: e.target.checked}, true)
                    }
                  />
                  DISTINCT
                </label>
                <Button
                  size="small"
                  onClick={() =>
                    pushVisualModelUpdate(
                      {
                        ...visualModel,
                        projections: [
                          ...visualModel.projections,
                          {expr: availableCols[0]?.ref || '*', alias: '', aggregate: ''},
                        ],
                      },
                      true
                    )
                  }
                >
                  + {gettext('Add Projection')}
                </Button>
              </div>
              {visualModel.projections.map((p, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 84px 28px',
                    gap: 4,
                    alignItems: 'center',
                  }}
                >
                  <input
                    className="sr-input"
                    value={p.expr || ''}
                    placeholder="t1.col"
                    onChange={(e) => {
                      const nextProjs = visualModel.projections.map((item, i) =>
                        i === idx ? {...item, expr: e.target.value} : item
                      );
                      pushVisualModelUpdate({...visualModel, projections: nextProjs}, true);
                    }}
                  />
                  <select
                    className="sr-input"
                    value={p.aggregate || ''}
                    onChange={(e) => {
                      const nextProjs = visualModel.projections.map((item, i) =>
                        i === idx ? {...item, aggregate: e.target.value} : item
                      );
                      pushVisualModelUpdate({...visualModel, projections: nextProjs}, true);
                    }}
                  >
                    <option value="">(raw)</option>
                    <option value="COUNT">COUNT</option>
                    <option value="SUM">SUM</option>
                    <option value="AVG">AVG</option>
                    <option value="MIN">MIN</option>
                    <option value="MAX">MAX</option>
                  </select>
                  <Button
                    size="small"
                    onClick={() =>
                      pushVisualModelUpdate(
                        {
                          ...visualModel,
                          projections: visualModel.projections.filter((_, i) => i !== idx),
                        },
                        true
                      )
                    }
                  >
                    ×
                  </Button>
                </div>
              ))}
            </div>
          )}

          {vbInspectorTab === 'joins' && (
            <div style={{display: 'grid', gap: 8}}>
              <Button
                size="small"
                disabled={visualModel.tables.length < 2}
                onClick={() => {
                  const leftT = visualModel.tables[0];
                  const rightT = visualModel.tables[visualModel.tables.length - 1];
                  const nextJoin = {
                    join_type: 'INNER',
                    left_table: leftT.alias || leftT.name,
                    left_column: leftT.columns?.[0]?.name || 'id',
                    right_table: rightT.alias || rightT.name,
                    right_column: rightT.columns?.[0]?.name || 'id',
                  };
                  pushVisualModelUpdate(
                    {...visualModel, joins: [...visualModel.joins, nextJoin]},
                    true
                  );
                }}
              >
                + {gettext('Add Join Relation')}
              </Button>
              {visualModel.joins.map((j, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: 8,
                    borderRadius: 6,
                    border: '1px solid var(--sr-border-subtle)',
                    display: 'grid',
                    gap: 6,
                  }}
                >
                  <div style={{display: 'flex', justifyContent: 'space-between', gap: 6}}>
                    <select
                      className="sr-input"
                      value={j.join_type || 'INNER'}
                      onChange={(e) => {
                        const nextJoins = visualModel.joins.map((item, i) =>
                          i === idx ? {...item, join_type: e.target.value} : item
                        );
                        pushVisualModelUpdate({...visualModel, joins: nextJoins}, true);
                      }}
                    >
                      <option value="INNER">INNER JOIN</option>
                      <option value="LEFT">LEFT JOIN</option>
                      <option value="RIGHT">RIGHT JOIN</option>
                      <option value="FULL">FULL JOIN</option>
                    </select>
                    <Button
                      size="small"
                      onClick={() =>
                        pushVisualModelUpdate(
                          {...visualModel, joins: visualModel.joins.filter((_, i) => i !== idx)},
                          true
                        )
                      }
                    >
                      ×
                    </Button>
                  </div>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4}}>
                    <input
                      className="sr-input"
                      value={`${j.left_table}.${j.left_column}`}
                      onChange={(e) => {
                        const [lt, lc] = e.target.value.split('.');
                        const nextJoins = visualModel.joins.map((item, i) =>
                          i === idx
                            ? {...item, left_table: lt || '', left_column: lc || ''}
                            : item
                        );
                        pushVisualModelUpdate({...visualModel, joins: nextJoins}, true);
                      }}
                    />
                    <input
                      className="sr-input"
                      value={`${j.right_table}.${j.right_column}`}
                      onChange={(e) => {
                        const [rt, rc] = e.target.value.split('.');
                        const nextJoins = visualModel.joins.map((item, i) =>
                          i === idx
                            ? {...item, right_table: rt || '', right_column: rc || ''}
                            : item
                        );
                        pushVisualModelUpdate({...visualModel, joins: nextJoins}, true);
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          {vbInspectorTab === 'clauses' && (
            <div style={{display: 'grid', gap: 8}}>
              <TextField
                label={gettext('WHERE Condition')}
                value={(visualModel.where || []).join(' AND ')}
                placeholder="t1.active = 1"
                onChange={(e) =>
                  pushVisualModelUpdate(
                    {
                      ...visualModel,
                      where: e.target.value.trim() ? [e.target.value] : [],
                    },
                    true
                  )
                }
              />
              <TextField
                label={gettext('GROUP BY')}
                value={(visualModel.group_by || []).join(', ')}
                placeholder="t1.department_id"
                onChange={(e) =>
                  pushVisualModelUpdate(
                    {
                      ...visualModel,
                      group_by: e.target.value
                        .split(',')
                        .map((s) => s.trim())
                        .filter(Boolean),
                    },
                    true
                  )
                }
              />
              <TextField
                label={gettext('ORDER BY')}
                value={(visualModel.order_by || [])
                  .map((o) => (typeof o === 'string' ? o : `${o.expr} ${o.dir || 'ASC'}`))
                  .join(', ')}
                placeholder="t1.id DESC"
                onChange={(e) =>
                  pushVisualModelUpdate(
                    {
                      ...visualModel,
                      order_by: e.target.value
                        .split(',')
                        .map((s) => s.trim())
                        .filter(Boolean),
                    },
                    true
                  )
                }
              />
              <TextField
                label={gettext('Row Limit')}
                value={visualModel.limit ?? ''}
                placeholder="100"
                onChange={(e) => {
                  const n = parseInt(e.target.value, 10);
                  pushVisualModelUpdate(
                    {...visualModel, limit: Number.isFinite(n) && n > 0 ? n : null},
                    true
                  );
                }}
              />
            </div>
          )}
        </Box>
      );
    }

    if (ds.panel === 'history') {
      return (
        <Box
          data-cdeadmin-qa-key="sql-surface-3b-history"
          sx={{p: 1.5, display: 'grid', gap: 1}}
        >
          <strong>{gettext('Executed SQL History')}</strong>
          {localQueryHistory.length === 0 ? (
            <div style={{fontSize: '0.78rem', opacity: 0.75}}>
              {gettext('Statements executed in this session appear here.')}
            </div>
          ) : (
            localQueryHistory.map((item) => (
              <div
                key={item.id}
                style={{
                  padding: 8,
                  borderRadius: 6,
                  border: '1px solid var(--sr-border-subtle)',
                  display: 'grid',
                  gap: 4,
                }}
              >
                <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', opacity: 0.75}}>
                  <span>{item.mode.toUpperCase()}</span>
                  <span>{item.timestamp.slice(11, 19)}</span>
                </div>
                <pre
                  style={{
                    margin: 0,
                    fontSize: '0.75rem',
                    whiteSpace: 'pre-wrap',
                    maxHeight: 90,
                    overflow: 'auto',
                  }}
                >
                  {item.sql}
                </pre>
                <div style={{display: 'flex', gap: 6}}>
                  <Button size="small" onClick={() => insertSnippetText(item.sql, true)}>
                    {gettext('Replace Editor')}
                  </Button>
                  <Button size="small" onClick={() => insertSnippetText(item.sql, false)}>
                    {gettext('Insert')}
                  </Button>
                </div>
              </div>
            ))
          )}
        </Box>
      );
    }

    if (ds.panel === 'value_inspector') {
      const targetRow = rows[ds.valueRowIndex] || currentRow;
      const colName = ds.valueColName || activeColName;
      const rawVal = targetRow?.values?.[colName];
      const textRepr = serializeValueForEdit(rawVal);
      return (
        <Box
          data-cdeadmin-qa-key="sql-surface-3b-value-inspector"
          sx={{p: 1.5, display: 'grid', gap: 1}}
        >
          <strong>
            {gettext('Cell Value')} — {colName}
          </strong>
          <div style={{fontSize: '0.74rem', opacity: 0.75}}>
            {formatBytes(textRepr.length)}
          </div>
          <TextArea
            rows={12}
            value={
              isEditingRow && editingRowIndex === ds.valueRowIndex
                ? serializeValueForEdit(rowDraft?.[colName])
                : textRepr
            }
            onChange={(e) => {
              if (!isEditableResult) return;
              if (!isEditingRow || editingRowIndex !== ds.valueRowIndex) {
                beginEditRow(ds.valueRowIndex);
              }
              const colObj = columns.find((c) => c.name === colName);
              setRowDraft((prev) => ({
                ...(prev || targetRow?.values || {}),
                [colName]: coerceEditedValue(e.target.value, colObj),
              }));
            }}
          />
        </Box>
      );
    }

    if (ds.panel === 'staged_sql') {
      const muts = activeResult?.staged_mutations || EMPTY_ARRAY;
      return (
        <Box
          data-cdeadmin-qa-key="sql-surface-3b-staged-sql"
          sx={{p: 1.5, display: 'grid', gap: 1}}
        >
          <strong>{gettext('Staged DML Batch (%s)', muts.length)}</strong>
          {muts.map((m) => (
            <div
              key={m.mutation_id}
              style={{
                padding: 8,
                borderRadius: 6,
                border: '1px solid var(--sr-border-subtle)',
                display: 'grid',
                gap: 4,
              }}
            >
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <strong style={{fontSize: '0.76rem'}}>{m.op.toUpperCase()}</strong>
                <Button
                  size="small"
                  onClick={async () => {
                    const resp = await callHost('revert_row', {row_key: m.row_key});
                    applyHostState(resp);
                  }}
                >
                  {gettext('Revert')}
                </Button>
              </div>
              <pre style={{margin: 0, fontSize: '0.74rem', whiteSpace: 'pre-wrap'}}>
                {m.preview_sql}
              </pre>
            </div>
          ))}
        </Box>
      );
    }

    if (ds.panel === 'column_profile' && ds.profileData) {
      const prof = ds.profileData;
      return (
        <Box
          data-cdeadmin-qa-key="sql-surface-3b-column-profile"
          sx={{p: 1.5, display: 'grid', gap: 1}}
        >
          <strong>
            {gettext('Column Profile')} — {prof.column}
          </strong>
          <div style={{fontSize: '0.78rem'}}>
            {gettext('Rows: %s · Nulls: %s · Distinct: %s', prof.total_rows, prof.null_count, prof.distinct_count)}
          </div>
          <div style={{display: 'grid', gap: 4}}>
            {(prof.top_values || []).map((tv, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '3px 6px',
                  borderRadius: 4,
                  border: '1px solid var(--sr-border-subtle)',
                  fontSize: '0.75rem',
                }}
              >
                <span>{tv.value}</span>
                <strong>{tv.count}</strong>
              </div>
            ))}
          </div>
        </Box>
      );
    }

    if (ds.panel === 'filter_builder') {
      const curFilters = activeResult?.filters || EMPTY_ARRAY;
      return (
        <SqlFilterBuilderDrawer
          columns={columns}
          initialColumn={ds.filterColumn || columns[0]?.name || ''}
          filters={curFilters}
          onApply={handleApplyFilters}
        />
      );
    }

    // Default Right Drawer Panel: Multi-Tag SQL Snippets Library!
    return (
      <Box
        data-cdeadmin-qa-key="sql-surface-3b-snippets"
        sx={{p: 1.5, display: 'grid', gap: 1}}
      >
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
          <strong>{gettext('SQL Snippets Library')}</strong>
          <Button
            size="small"
            intent="primary"
            data-cdeadmin-qa-key="snippets-new-btn"
            onClick={() => openSaveDialog('snippet', Boolean(selectionText.trim()))}
          >
            + {gettext('New')}
          </Button>
        </div>

        <TextField
          label={gettext('Search Snippets or #tag')}
          placeholder={gettext('e.g. #firebird #ddl or upsert')}
          value={snippetSearch}
          onChange={(e) => setSnippetSearch(e.target.value)}
        />

        <div style={{display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap'}}>
          <Button
            size="small"
            intent={snippetTagMode === 'and' ? 'primary' : 'neutral'}
            data-cdeadmin-qa-key="snippets-tag-mode-toggle"
            onClick={() => setSnippetTagMode((m) => (m === 'and' ? 'or' : 'and'))}
          >
            {snippetTagMode === 'and' ? gettext('Match ALL Tags (AND)') : gettext('Match ANY Tag (OR)')}
          </Button>
          <Button
            size="small"
            intent={snippetFavoritesOnly ? 'primary' : 'neutral'}
            onClick={() => setSnippetFavoritesOnly((f) => !f)}
          >
            ★ {gettext('Favorites')}
          </Button>
          <Button
            size="small"
            intent={snippetAllEngines ? 'primary' : 'neutral'}
            onClick={() => setSnippetAllEngines((a) => !a)}
          >
            {gettext('All Engines')}
          </Button>
          {selectedTags.length > 0 && (
            <Button size="small" onClick={() => setSelectedTags(EMPTY_ARRAY)}>
              {gettext('Clear Tags')}
            </Button>
          )}
        </div>

        {/* Clickable Multi-Tag Filter Chips with Live Counts */}
        <div
          role="group"
          aria-label={gettext('Snippet Tag Filters')}
          data-cdeadmin-qa-key="snippets-tag-chips"
          style={{display: 'flex', gap: 4, flexWrap: 'wrap'}}
        >
          {(snippetsPayload.available_tags || []).map((t) => {
            const active = selectedTags.includes(t.tag);
            return (
              <button
                key={t.tag}
                type="button"
                data-cdeadmin-qa-key={`snippet-tag-chip-${t.tag}`}
                aria-pressed={active}
                onClick={() =>
                  setSelectedTags((prev) =>
                    prev.includes(t.tag)
                      ? prev.filter((x) => x !== t.tag)
                      : [...prev, t.tag]
                  )
                }
                style={{
                  padding: '2px 8px',
                  borderRadius: 999,
                  fontSize: '0.72rem',
                  cursor: 'pointer',
                  border: '1px solid var(--sr-border-default, #cbd5e1)',
                  background: active
                    ? 'var(--sr-accent-primary, #2563eb)'
                    : 'var(--sr-surface-subtle, transparent)',
                  color: active ? '#ffffff' : 'inherit',
                }}
              >
                #{t.tag} ({t.count})
              </button>
            );
          })}
        </div>

        {/* Filtered Snippets Cards */}
        <div style={{display: 'grid', gap: 8}}>
          {(snippetsPayload.snippets || []).map((snip) => (
            <div
              key={snip.snippet_id}
              data-cdeadmin-qa-key={`snippet-card-${snip.snippet_id}`}
              style={{
                padding: 8,
                borderRadius: 8,
                border: '1px solid var(--sr-border-subtle)',
                display: 'grid',
                gap: 5,
              }}
            >
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6}}>
                <strong style={{fontSize: '0.8rem'}}>{snip.title}</strong>
                <button
                  type="button"
                  aria-label={gettext('Toggle Favorite')}
                  onClick={async () => {
                    const res = await callHost('toggle_snippet_favorite', {
                      snippet_id: snip.snippet_id,
                    });
                    if (res?.snippets) setSnippetsPayload(res.snippets);
                  }}
                  style={{
                    border: 0,
                    background: 'transparent',
                    cursor: 'pointer',
                    fontSize: '0.95rem',
                    color: snip.favorite ? '#eab308' : 'inherit',
                  }}
                >
                  {snip.favorite ? '★' : '☆'}
                </button>
              </div>
              {snip.description && (
                <div style={{fontSize: '0.74rem', opacity: 0.8}}>{snip.description}</div>
              )}
              <div style={{display: 'flex', gap: 4, flexWrap: 'wrap'}}>
                {(snip.tags || []).map((tg) => (
                  <span
                    key={tg}
                    style={{
                      padding: '1px 6px',
                      borderRadius: 999,
                      fontSize: '0.68rem',
                      background: 'var(--sr-surface-subtle, rgba(148,163,184,0.16))',
                    }}
                  >
                    #{tg}
                  </span>
                ))}
                {snip.shortcut && (
                  <code style={{fontSize: '0.68rem', opacity: 0.8}}>⇥ {snip.shortcut}</code>
                )}
              </div>
              <pre
                style={{
                  margin: 0,
                  padding: 6,
                  borderRadius: 4,
                  background: 'var(--sr-surface-subtle, rgba(15,23,42,0.04))',
                  fontSize: '0.72rem',
                  whiteSpace: 'pre-wrap',
                  maxHeight: 84,
                  overflow: 'auto',
                }}
              >
                {snip.sql_text}
              </pre>
              <div style={{display: 'flex', gap: 6, flexWrap: 'wrap'}}>
                <Button
                  size="small"
                  intent="primary"
                  data-cdeadmin-qa-key={`snippet-insert-${snip.snippet_id}`}
                  onClick={() => insertSnippetText(snip.sql_text, false)}
                >
                  {gettext('Insert')}
                </Button>
                <Button
                  size="small"
                  onClick={() => insertSnippetText(snip.sql_text, true)}
                >
                  {gettext('Replace')}
                </Button>
                {snip.scope !== 'builtin' && (
                  <Button
                    size="small"
                    onClick={async () => {
                      const res = await callHost('delete_snippet', {
                        snippet_id: snip.snippet_id,
                      });
                      if (res?.snippets) setSnippetsPayload(res.snippets);
                    }}
                  >
                    {gettext('Delete')}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </Box>
    );
  }, [
    activeColName,
    activeResult?.filters,
    activeResult?.staged_mutations,
    applyHostState,
    beginEditRow,
    callHost,
    columns,
    currentRow,
    editingRowIndex,
    fanoutWarnings,
    handleApplyFilters,
    insertSnippetText,
    isEditableResult,
    isEditingRow,
    localQueryHistory,
    openSaveDialog,
    pushVisualModelUpdate,
    resources,
    rowDraft,
    rows,
    selectedCanvasNodeId,
    selectedTags,
    selectionText,
    snippetAllEngines,
    snippetFavoritesOnly,
    snippetSearch,
    snippetTagMode,
    snippetsPayload,
    vbInspectorTab,
    vbTableSearch,
    visualFidelity,
    visualLossNotes,
    visualModel,
  ]);

  const renderRightDrawerRef = useRef(renderRightDrawerContent);
  renderRightDrawerRef.current = renderRightDrawerContent;
  const stableRenderRightDrawer = useCallback(() => renderRightDrawerRef.current(), []);

  // Compact Status Bar (`Area 4` / `3d`)
  const statusSummaryText = useMemo(() => {
    const parts = [];
    if (endpointLabel) parts.push(endpointLabel);
    parts.push(
      autocommit
        ? gettext('Tx: Auto-Commit')
        : hasUncommitted
          ? gettext('Tx: Uncommitted (%s staged)', hostData?.staged_count || 0)
          : gettext('Tx: Idle')
    );
    parts.push(gettext('Term: %s', terminator));
    if ((hostData?.result_count || 0) > 0) {
      parts.push(
        gettext(
          'Result %s/%s: %s rows',
          (hostData?.active_result_index ?? 0) + 1,
          hostData.result_count,
          activeResult?.total_view_rows ?? 0
        )
      );
    }
    if (hostData?.timings_ms?.total_ms) {
      parts.push(`${hostData.timings_ms.total_ms} ms`);
    }
    parts.push(`Ln ${cursorPos.line}, Col ${cursorPos.col}`);
    return parts.join(' · ');
  }, [
    activeResult?.total_view_rows,
    autocommit,
    cursorPos.col,
    cursorPos.line,
    endpointLabel,
    hasUncommitted,
    hostData?.active_result_index,
    hostData?.result_count,
    hostData?.staged_count,
    hostData?.timings_ms?.total_ms,
    terminator,
  ]);

  const renderStatusContent = useCallback(
    () => (
      <span data-cdeadmin-qa-key="sql-surface-status-summary">
        {statusSummaryText}
      </span>
    ),
    [statusSummaryText]
  );
  const renderStatusRef = useRef(renderStatusContent);
  renderStatusRef.current = renderStatusContent;
  const stableRenderStatus = useCallback(() => renderStatusRef.current(), []);

  // Register MS-Grouped TiB (3 Under-Tabs) + Focus-Merged Top Menus (`Query 15`, `Edit 20`, `View 25`, `Window 70`)
  useEffect(() => {
    const curShell = shellRef.current;
    if (!curShell || !instanceScope?.instanceId) return undefined;
    const pfx = `sql-surf.${instId}`;
    const regList = [];

    const reg = (
      suffix,
      icon,
      text,
      invoke,
      {
        status = T_ACTION_STATUS.ENABLED,
        checked = false,
        shortcut = '',
        hint = '',
      } = {}
    ) => {
      const id = `${pfx}.${suffix}`;
      regList.push({
        id,
        icon,
        application: 'sql-editor',
        defaultText: text,
        defaultHint: hint || text,
        focusScoped: true,
        status,
        checked,
        ...(shortcut ? {shortcut} : {}),
        target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke},
      });
      return id;
    };

    // Pill 1 — 7 Surface Views
    const viewSegId = reg('aspect_seg', 'tool.query', gettext('Surface View'), (detail) => {
      const chosen = detail?.item?.id || detail?.value;
      if (chosen) handlersRef.current.switchSurfaceView(chosen);
    });

    // Multi-Result Set Selector (when script returns > 1 result sets)
    const resultMenuId = reg(
      'result_set_menu',
      'action.layers',
      gettext(
        'Result %s/%s',
        (hostData?.active_result_index ?? 0) + 1,
        Math.max(1, hostData?.result_count || 1)
      ),
      (detail) => {
        const idx = Number(detail?.item?.id);
        if (Number.isFinite(idx)) handlersRef.current.selectResultIndex(idx);
      }
    );

    // Execute Group
    const execStmtId = reg(
      'exec_stmt',
      'action.execute',
      gettext('Execute Statement'),
      () => handlersRef.current.runSql('statement'),
      {
        shortcut: 'F9',
        status: executing ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED,
        hint: gettext('Execute selection or statement at cursor (F9)'),
      }
    );
    const execScriptId = reg(
      'exec_script',
      'action.script',
      gettext('Execute Script'),
      () => handlersRef.current.runSql('script'),
      {
        shortcut: 'F5',
        status: executing ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED,
        hint: gettext('Execute full script with active terminator / SET TERM (F5)'),
      }
    );
    const explainId = reg(
      'explain',
      'tool.dashboard',
      gettext('Explain Plan'),
      () => handlersRef.current.runSql('explain'),
      {status: executing ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED}
    );
    const cancelId = reg(
      'cancel',
      'action.close',
      gettext('Cancel'),
      () => handlersRef.current.cancelExecution(),
      {status: executing ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED}
    );
    const paramsId = reg(
      'parameters',
      'action.settings',
      gettext('Parameters…'),
      () => handlersRef.current.openParametersDialog()
    );
    const termMenuId = reg(
      'terminator_menu',
      'action.script',
      gettext('Term: %s', terminator),
      (detail) => {
        const chosen = detail?.item?.id;
        if (!chosen) return;
        if (chosen === 'set_term_block') {
          const cur = editorRef.current?.getValue?.() ?? sqlTextRef.current;
          const wrapped = `SET TERM ^ ;\n${cur}\n^\nSET TERM ; ^`;
          setSqlText(wrapped);
          editorRef.current?.setValue?.(wrapped);
          handlersRef.current.setTerminator('^');
        } else {
          handlersRef.current.setTerminator(chosen);
        }
      }
    );

    // Transaction Group
    const commitId = reg(
      'commit',
      'action.commit',
      gettext('Commit'),
      () => handlersRef.current.handleCommit(),
      {status: hasUncommitted && !autocommit ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.ENABLED}
    );
    const rollbackId = reg(
      'rollback',
      'action.rollback',
      gettext('Rollback'),
      () => handlersRef.current.handleRollback()
    );
    const autocommitId = reg(
      'autocommit',
      'action.check',
      gettext('Auto-Commit'),
      () => handlersRef.current.setAutocommit(!autocommit),
      {checked: autocommit}
    );

    // Live Row Editing Group (Surface 1 parity!)
    const editAcceptRowId = reg(
      'edit_accept_row',
      isEditingRow ? 'action.check' : 'action.edit',
      isEditingRow ? gettext('Accept Row') : gettext('Edit Row'),
      () =>
        handlersRef.current.isEditingRow
          ? handlersRef.current.acceptCurrentRow()
          : handlersRef.current.beginEditRow(),
      {status: isEditableResult || isEditingRow ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED}
    );
    const insertRowId = reg(
      'insert_row',
      'action.insert',
      gettext('Insert Row'),
      () => handlersRef.current.beginInsertRow(false),
      {status: canInsertResult ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED}
    );
    const duplicateRowId = reg(
      'duplicate_row',
      'action.copy',
      gettext('Duplicate Row'),
      () => handlersRef.current.beginInsertRow(true),
      {status: canInsertResult && rows.length > 0 ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED}
    );
    const deleteRowId = reg(
      'delete_row',
      'action.delete',
      gettext('Delete Row'),
      () => handlersRef.current.stageDeleteRow(),
      {status: isEditableResult && rows.length > 0 ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED}
    );

    // Library & Save Group
    const snippetsDrawerId = reg('snippets_drawer', 'action.script', gettext('Snippets'), () =>
      handlersRef.current.openRightDrawerWith({panel: 'snippets'})
    );
    const quickQueriesId = reg('quick_queries', 'tool.query', gettext('Quick Queries…'), () =>
      handlersRef.current.setQuickQueryModalOpen(true)
    );
    const historyDrawerId = reg('history_drawer', 'action.history', gettext('History'), () =>
      handlersRef.current.openRightDrawerWith({panel: 'history'})
    );
    const saveAnyId = reg('save_any', 'action.save', gettext('Save…'), () =>
      handlersRef.current.openSaveDialog('quick_query', false)
    );

    // Pill 2 — Surface 1 Display Modes
    const displaySegId = reg('display_seg', 'action.view', gettext('Data Display'), (detail) => {
      const chosen = detail?.item?.id || detail?.value;
      if (chosen) {
        handlersRef.current.setLayout((prev) => ({...prev, displayMode: chosen}));
      }
    });
    const splitDirId = reg(
      'split_dir',
      'action.columns',
      splitOrientation === 'vertical' ? gettext('Split: Top/Bottom') : gettext('Split: Left/Right'),
      () =>
        handlersRef.current.setSplitOrientation((o) =>
          o === 'vertical' ? 'horizontal' : 'vertical'
        )
    );
    const formatSqlId = reg('format_sql', 'action.edit', gettext('Format SQL'), () =>
      handlersRef.current.handleFormatSql()
    );
    const boolMenuId = reg('bool_menu', 'action.check', gettext('Boolean'), (detail) => {
      const chosen = detail?.item?.id;
      if (chosen) handlersRef.current.setLayout((prev) => ({...prev, booleanFormat: chosen}));
    });
    const vbInspectorId = reg('vb_inspector', 'tool.erd', gettext('Builder Inspector'), () => {
      setVbInspectorTab('tables');
      handlersRef.current.openRightDrawerWith({panel: 'visual_inspector'});
    });
    const limitsId = reg('limits', 'action.settings', gettext('Fetch Limits…'), () =>
      handlersRef.current.setLimitsModalOpen(true)
    );
    const connInfoId = reg('conn_info', 'action.info', gettext('Connection Details…'), () =>
      handlersRef.current.setConnectionModalOpen(true)
    );

    // Export & Files Under-Tab Actions
    const openSqlFileId = reg('open_sql_file', 'action.import', gettext('Open .sql File…'), () =>
      handlersRef.current.triggerFileOpen()
    );
    const saveSnippetSelId = reg(
      'save_snippet_sel',
      'action.script',
      gettext('Save as Snippet…'),
      () => handlersRef.current.openSaveDialog('snippet', true)
    );
    const saveBiQuestionId = reg(
      'save_bi_question',
      'tool.bi',
      gettext('Save as BI Question…'),
      () => handlersRef.current.openSaveDialog('bi_question', false)
    );
    const exportDataId = reg('export_data', 'action.export', gettext('Export Data…'), () => {
      handlersRef.current.setExportInitialFormat('csv');
      handlersRef.current.setExportDialogOpen(true);
    });
    const exportSpreadsheetId = reg(
      'export_xlsx_ods',
      'action.export',
      gettext('Excel / ODS…'),
      () => {
        handlersRef.current.setExportInitialFormat('xlsx');
        handlersRef.current.setExportDialogOpen(true);
      }
    );
    const exportPdfId = reg('export_pdf', 'tool.report', gettext('PDF Report…'), () => {
      handlersRef.current.setExportInitialFormat('pdf');
      handlersRef.current.setExportDialogOpen(true);
    });

    regList.forEach((a) => curShell.actionsRegistry?.upsert?.(a));

    const viewControlSpec = {
      id: viewSegId,
      actionId: viewSegId,
      type: 'segmented',
      value: surfaceView,
      items: [
        {
          id: SQL_SURFACE_VIEWS.SQL,
          label: gettext('SQL'),
          icon: 'tool.query',
          checked: surfaceView === SQL_SURFACE_VIEWS.SQL,
        },
        {
          id: SQL_SURFACE_VIEWS.VISUAL_BUILDER,
          label: gettext('Visual Builder'),
          icon: 'action.sql_builder',
          checked: surfaceView === SQL_SURFACE_VIEWS.VISUAL_BUILDER,
        },
        {
          id: SQL_SURFACE_VIEWS.SQL_DATA,
          label: gettext('SQL + Data'),
          icon: 'action.columns',
          checked: surfaceView === SQL_SURFACE_VIEWS.SQL_DATA,
        },
        {
          id: SQL_SURFACE_VIEWS.DATA,
          label: gettext('Data'),
          icon: 'action.browse_data',
          checked: surfaceView === SQL_SURFACE_VIEWS.DATA,
        },
        {
          id: SQL_SURFACE_VIEWS.METRICS_PLAN,
          label: gettext('Metrics & Plan'),
          icon: 'tool.dashboard',
          checked: surfaceView === SQL_SURFACE_VIEWS.METRICS_PLAN,
        },
        {
          id: SQL_SURFACE_VIEWS.FIELDS,
          label: gettext('Fields'),
          icon: 'action.properties',
          checked: surfaceView === SQL_SURFACE_VIEWS.FIELDS,
        },
        {
          id: SQL_SURFACE_VIEWS.MESSAGES,
          label: gettext('Messages'),
          icon: 'action.section_comments',
          checked: surfaceView === SQL_SURFACE_VIEWS.MESSAGES,
        },
      ],
    };

    const displayControlSpec = {
      id: displaySegId,
      actionId: displaySegId,
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
          label: gettext('Hybrid'),
          icon: 'action.layout_hybrid',
          checked: layout.displayMode === DISPLAY_MODES.HYBRID,
        },
        {
          id: DISPLAY_MODES.SINGLE_FORM,
          label: gettext('Single Form'),
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
    };

    const ribbonTabs = [
      {
        id: 'query',
        label: gettext('Query'),
        groups: [
          {
            id: 'surface_view',
            label: gettext('View'),
            controls: [
              viewControlSpec,
              ...((hostData?.result_count || 0) > 1
                ? [
                  {
                    id: `${pfx}.ctrl.result_set`,
                    type: 'menu',
                    actionId: resultMenuId,
                    items: (hostData?.result_summaries || []).map((rs) => ({
                      id: String(rs.index),
                      label: `${rs.title} (${rs.row_count})`,
                    })),
                  },
                ]
                : []),
            ],
          },
          {
            id: 'execute',
            label: gettext('Execute'),
            controls: [
              execStmtId,
              execScriptId,
              explainId,
              cancelId,
              paramsId,
              {
                id: `${pfx}.ctrl.term`,
                type: 'menu',
                actionId: termMenuId,
                items: [
                  {id: ';', label: gettext('Semicolon (;)')},
                  {id: '^', label: gettext('Caret (^) — Firebird PSQL')},
                  {id: '!!', label: gettext('Double Bang (!!)')},
                  {id: '~', label: gettext('Tilde (~)')},
                  {id: 'set_term_block', label: gettext('Wrap in SET TERM ^ ; … ^')},
                ],
              },
            ],
          },
          {
            id: 'transaction',
            label: gettext('Transaction'),
            controls: [commitId, rollbackId, autocommitId],
          },
          {
            id: 'live_edit',
            label: gettext('Edit Rows'),
            controls: [editAcceptRowId, insertRowId, duplicateRowId, deleteRowId],
          },
          {
            id: 'library',
            label: gettext('Snippets & Saved'),
            controls: [snippetsDrawerId, quickQueriesId, historyDrawerId, saveAnyId],
          },
        ],
      },
      {
        id: 'format_layout',
        label: gettext('Format & Layout'),
        groups: [
          {
            id: 'data_display',
            label: gettext('Data Display'),
            controls: [displayControlSpec, splitDirId],
          },
          {
            id: 'formatting',
            label: gettext('SQL & Values'),
            controls: [
              formatSqlId,
              {
                id: `${pfx}.ctrl.bool`,
                type: 'menu',
                actionId: boolMenuId,
                items: [
                  {id: BOOLEAN_FORMATS.TF, label: 'T / F'},
                  {id: BOOLEAN_FORMATS.TRUE_FALSE, label: 'True / False'},
                  {id: BOOLEAN_FORMATS.ONE_ZERO, label: '1 / 0'},
                  {id: BOOLEAN_FORMATS.YES_NO, label: 'Yes / No'},
                ],
              },
            ],
          },
          {
            id: 'builder_limits',
            label: gettext('Builder & Session'),
            controls: [vbInspectorId, limitsId, connInfoId],
          },
        ],
      },
      {
        id: 'export_files',
        label: gettext('Export & Files'),
        groups: [
          {
            id: 'sql_files',
            label: gettext('SQL & Snippets'),
            controls: [openSqlFileId, saveAnyId, saveSnippetSelId, saveBiQuestionId],
          },
          {
            id: 'data_exports',
            label: gettext('Result Export'),
            controls: [exportDataId, exportSpreadsheetId, exportPdfId],
          },
        ],
      },
    ];

    const menus = [
      {
        name: 'query',
        id: `${pfx}.menu.query`,
        index: PROJECT_TOP_MENU_INDICES.CONTEXT_PRIMARY, // 15
        label: gettext('Query'),
        items: [
          {id: `${pfx}.m.exec_stmt`, actionId: execStmtId, label: gettext('Execute Statement (F9)'), index: 10},
          {id: `${pfx}.m.exec_script`, actionId: execScriptId, label: gettext('Execute Script (F5)'), index: 20},
          {id: `${pfx}.m.explain`, actionId: explainId, label: gettext('Explain / Plan'), index: 30},
          {id: `${pfx}.m.params`, actionId: paramsId, label: gettext('Parameters…'), index: 40},
          {id: `${pfx}.m.sep1`, type: 'separator', index: 45},
          {id: `${pfx}.m.commit`, actionId: commitId, label: gettext('Commit Transaction'), index: 50},
          {id: `${pfx}.m.rollback`, actionId: rollbackId, label: gettext('Rollback Transaction'), index: 60},
          {id: `${pfx}.m.autocommit`, actionId: autocommitId, label: gettext('Auto-Commit'), index: 70},
          {id: `${pfx}.m.sep2`, type: 'separator', index: 75},
          {id: `${pfx}.m.open_sql`, actionId: openSqlFileId, label: gettext('Open .sql File…'), index: 80},
          {id: `${pfx}.m.qq`, actionId: quickQueriesId, label: gettext('Quick Queries…'), index: 90},
          {id: `${pfx}.m.save`, actionId: saveAnyId, label: gettext('Save Quick Query / File…'), index: 100},
          {id: `${pfx}.m.save_snip`, actionId: saveSnippetSelId, label: gettext('Save as Tagged Snippet…'), index: 110},
          {id: `${pfx}.m.export`, actionId: exportDataId, label: gettext('Export Data (CSV/XLSX/ODS/PDF)…'), index: 120},
        ],
      },
      {
        name: 'edit',
        id: `${pfx}.menu.edit`,
        index: 20,
        label: gettext('Edit'),
        items: [
          {id: `${pfx}.m.fmt`, actionId: formatSqlId, label: gettext('Format SQL'), index: 10},
          {id: `${pfx}.m.sep_e1`, type: 'separator', index: 15},
          {id: `${pfx}.m.edit_row`, actionId: editAcceptRowId, label: isEditingRow ? gettext('Accept Row') : gettext('Edit Row'), index: 20},
          {id: `${pfx}.m.ins_row`, actionId: insertRowId, label: gettext('Insert Row'), index: 30},
          {id: `${pfx}.m.dup_row`, actionId: duplicateRowId, label: gettext('Duplicate Row'), index: 40},
          {id: `${pfx}.m.del_row`, actionId: deleteRowId, label: gettext('Delete Row'), index: 50},
        ],
      },
      {
        name: 'view',
        id: `${pfx}.menu.view`,
        index: 25,
        label: gettext('View'),
        items: [
          ...[
            [SQL_SURFACE_VIEWS.SQL, gettext('SQL Editor')],
            [SQL_SURFACE_VIEWS.VISUAL_BUILDER, gettext('Visual Query Builder (DDN)')],
            [SQL_SURFACE_VIEWS.SQL_DATA, gettext('SQL + Data Split')],
            [SQL_SURFACE_VIEWS.DATA, gettext('Data View')],
            [SQL_SURFACE_VIEWS.METRICS_PLAN, gettext('Metrics & Plan')],
            [SQL_SURFACE_VIEWS.FIELDS, gettext('Result Fields')],
            [SQL_SURFACE_VIEWS.MESSAGES, gettext('Messages')],
          ].map(([vid, lbl], idx) => ({
            id: `${pfx}.m.v.${vid}`,
            label: lbl,
            checked: surfaceView === vid,
            index: (idx + 1) * 10,
            callback: () => handlersRef.current.switchSurfaceView(vid),
          })),
          {id: `${pfx}.m.sep_v1`, type: 'separator', index: 75},
          {id: `${pfx}.m.snips`, actionId: snippetsDrawerId, label: gettext('SQL Snippets Drawer'), index: 80},
          {id: `${pfx}.m.hist`, actionId: historyDrawerId, label: gettext('Query History Drawer'), index: 90},
          {id: `${pfx}.m.vbi`, actionId: vbInspectorId, label: gettext('Visual Builder Inspector'), index: 100},
        ],
      },
      {
        name: 'window',
        id: `${pfx}.menu.window`,
        index: PROJECT_TOP_MENU_INDICES.WINDOW, // 70
        label: gettext('Window'),
        items: [
          {id: `${pfx}.m.limits`, actionId: limitsId, label: gettext('Page & Fetch Limits…'), index: 80},
          {id: `${pfx}.m.conn`, actionId: connInfoId, label: gettext('Connection Details…'), index: 90},
        ],
      },
    ];

    curShell.updateInstance?.(instId, {
      ribbonMode: 'ms-grouped',
      useUnderTabs: true,
      supportsRightDrawer: true,
      rightViews: [
        {id: 'snippets', label: gettext('Snippets')},
        {id: 'visual_inspector', label: gettext('Builder')},
        {id: 'history', label: gettext('History')},
      ],
      actions: regList,
      ribbonTabs,
      menus,
      renderRightDrawer: stableRenderRightDrawer,
      renderStatus: stableRenderStatus,
      statusText: statusSummaryText,
      onBeforeClose: stableConfirmCloseGuard,
    });

    return () => {
      regList.forEach((a) => curShell.actionsRegistry?.unregister?.(a.id));
    };
  }, [
    autocommit,
    canInsertResult,
    executing,
    hasUncommitted,
    hostData?.active_result_index,
    hostData?.result_count,
    instId,
    instanceScope?.instanceId,
    isEditableResult,
    isEditingRow,
    layout.booleanFormat,
    layout.displayMode,
    rows.length,
    splitOrientation,
    stableConfirmCloseGuard,
    stableRenderRightDrawer,
    stableRenderStatus,
    statusSummaryText,
    surfaceView,
    terminator,
  ]);

  // CodeMirror custom keymap (`F9` Execute Statement, `F5` Execute Script)
  const editorKeyMap = useMemo(
    () => [
      {
        key: 'F9',
        run: () => {
          handlersRef.current.runSql('statement');
          return true;
        },
      },
      {
        key: 'F5',
        run: () => {
          handlersRef.current.runSql('script');
          return true;
        },
      },
      {
        key: 'Mod-Enter',
        run: () => {
          handlersRef.current.runSql('statement');
          return true;
        },
      },
    ],
    []
  );

  // Render SQL Editor Pane
  const renderSqlEditorPane = () => (
    <div
      data-cdeadmin-qa-key="sql-surface-editor-pane"
      onContextMenu={(e) => {
        e.preventDefault();
        setContextMenuState({
          open: true,
          x: e.clientX,
          y: e.clientY,
          items: [
            {
              id: 'ctx-exec-stmt',
              label: gettext('Execute Statement (F9)'),
              onSelect: () => runSql('statement'),
            },
            {
              id: 'ctx-exec-script',
              label: gettext('Execute Script (F5)'),
              onSelect: () => runSql('script'),
            },
            {
              id: 'ctx-explain',
              label: gettext('Explain / Plan'),
              onSelect: () => runSql('explain'),
            },
            {id: 'ctx-sep-1', separator: true},
            {
              id: 'ctx-params',
              label: gettext('Parameters…'),
              onSelect: () => openParametersDialog(),
            },
            {
              id: 'ctx-format',
              label: gettext('Format SQL'),
              onSelect: () => handleFormatSql(),
            },
            {
              id: 'ctx-save-snippet',
              label: gettext('Save Selection as Tagged Snippet…'),
              onSelect: () => openSaveDialog('snippet', true),
            },
            {
              id: 'ctx-save-qq',
              label: gettext('Save as Quick Query…'),
              onSelect: () => openSaveDialog('quick_query', false),
            },
          ],
        });
      }}
      onKeyUp={() => {
        const cur = editorRef.current?.getCursor?.();
        if (cur && typeof cur.line === 'number') {
          setCursorPos({line: (cur.line || 0) + 1, col: (cur.ch ?? cur.pos ?? 0) + 1});
        }
      }}
      onClick={() => {
        const cur = editorRef.current?.getCursor?.();
        if (cur && typeof cur.line === 'number') {
          setCursorPos({line: (cur.line || 0) + 1, col: (cur.ch ?? cur.pos ?? 0) + 1});
        }
      }}
      style={{
        flex: 1,
        minHeight: 0,
        minWidth: 0,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
      }}
    >
      <CodeEditor
        label={gettext('SQL source editor')}
        value={sqlText}
        onChange={(val) => setSqlText(val)}
        onTextSelect={(sel) => setSelectionText(sel || '')}
        language={isFirebird ? 'firebird' : 'sql'}
        sqlConfig={sqlEditorConfig}
        autocomplete
        autocompleteOnKeyPress
        customKeyMap={editorKeyMap}
        currEditor={(view) => {
          editorRef.current = view;
        }}
      />
    </div>
  );

  // Render Standard Grid Table (reused in Grid, Hybrid, and Hybrid-When-Editing)
  const renderGridTable = () => (
    <ScratchScrollArea fillViewport style={{flex: 1, minHeight: 0}}>
      <table
        data-cdeadmin-qa-key="sql-surface-data-grid"
        style={{
          width: '100%',
          borderCollapse: 'separate',
          borderSpacing: 0,
          fontSize: '0.8125rem',
        }}
      >
        <thead>
          <tr>
            <th
              style={{
                position: 'sticky',
                top: 0,
                left: 0,
                zIndex: 5,
                width: GUTTER_WIDTH,
                padding: '6px 8px',
                background: 'var(--sr-surface-subtle, #f8fafc)',
                borderBottom: '1px solid var(--sr-border-default, #cbd5e1)',
                borderRight: '1px solid var(--sr-border-subtle, #e2e8f0)',
                textAlign: 'center',
              }}
            >
              <button
                type="button"
                aria-label={gettext('Choose Visible Columns')}
                data-cdeadmin-qa-key="sql-grid-column-picker-btn"
                onClick={() => setColPickerOpen((o) => !o)}
                style={{
                  border: 0,
                  background: 'transparent',
                  cursor: 'pointer',
                  fontWeight: 700,
                }}
              >
                ☰
              </button>
            </th>
            {gridColumns.map((col) => {
              const sortSpec = (activeResult?.sort || []).find((s) => s.column === col.name);
              const filtered = (activeResult?.filters || []).some((f) => f.column === col.name);
              return (
                <th
                  key={col.name}
                  style={{
                    position: 'sticky',
                    top: 0,
                    zIndex: 4,
                    minWidth: layout.gridColPrefs?.[col.name]?.width || DEFAULT_COL_WIDTH,
                    padding: '6px 10px',
                    background: 'var(--sr-surface-subtle, #f8fafc)',
                    borderBottom: '1px solid var(--sr-border-default, #cbd5e1)',
                    borderRight: '1px solid var(--sr-border-subtle, #e2e8f0)',
                    textAlign: col.align || 'left',
                    cursor: 'pointer',
                    userSelect: 'none',
                    whiteSpace: 'nowrap',
                  }}
                  onClick={(e) => handleToggleSort(col.name, e.shiftKey)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    setContextMenuState({
                      open: true,
                      x: e.clientX,
                      y: e.clientY,
                      items: [
                        {
                          id: 'col-filter',
                          label: gettext('Filter on %s…', col.name),
                          onSelect: () =>
                            openRightDrawerWith({
                              panel: 'filter_builder',
                              filterColumn: col.name,
                            }),
                        },
                        {
                          id: 'col-profile',
                          label: gettext('Profile Column %s', col.name),
                          onSelect: async () => {
                            const prof = await callHost('column_profile', {column: col.name});
                            openRightDrawerWith({
                              panel: 'column_profile',
                              profileData: prof,
                            });
                          },
                        },
                      ],
                    });
                  }}
                >
                  <span>{col.name}</span>
                  {col.key && <span style={{marginLeft: 4, opacity: 0.7}}>🔑</span>}
                  {sortSpec && (
                    <span style={{marginLeft: 4}}>
                      {sortSpec.dir === 'asc' ? '▲' : '▼'}
                    </span>
                  )}
                  {filtered && <span style={{marginLeft: 4, color: '#2563eb'}}>⧩</span>}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rIdx) => {
            const isSelected = rIdx === activeRowIndex;
            const rowEditing = isEditingRow && editingRowIndex === rIdx;
            const stageBg =
              row.stage_state === 'inserted'
                ? 'rgba(22, 163, 74, 0.09)'
                : row.stage_state === 'updated'
                  ? 'rgba(217, 119, 6, 0.09)'
                  : row.stage_state === 'deleted'
                    ? 'rgba(220, 38, 38, 0.12)'
                    : isSelected
                      ? 'var(--sr-accent-muted, rgba(37, 99, 235, 0.08))'
                      : 'transparent';
            return (
              <tr
                key={row.identity_token || `r-${rIdx}`}
                data-cdeadmin-qa-key={`sql-grid-row-${rIdx}`}
                onClick={async () => {
                  if (isEditingRow && editingRowIndex !== null && editingRowIndex !== rIdx) {
                    const ok = await acceptCurrentRow();
                    if (!ok) return;
                  }
                  setActiveRowIndex(rIdx);
                }}
                onDoubleClick={() => beginEditRow(rIdx)}
                style={{
                  background: stageBg,
                  textDecoration: row.stage_state === 'deleted' ? 'line-through' : 'none',
                }}
              >
                <td
                  style={{
                    padding: '4px 8px',
                    borderBottom: '1px solid var(--sr-border-subtle, #e2e8f0)',
                    borderRight: '1px solid var(--sr-border-subtle, #e2e8f0)',
                    textAlign: 'right',
                    fontVariantNumeric: 'tabular-nums',
                    opacity: 0.75,
                  }}
                >
                  {row.row_number || rIdx + 1}
                </td>
                {gridColumns.map((col) => {
                  const val = rowEditing ? rowDraft?.[col.name] : row.values?.[col.name];
                  const isNull = val === null || val === undefined;
                  const complex = isComplexOrOversizedCell(val, col);
                  const formatted = formatCellValue(val, col, {
                    booleanFormat: layout.booleanFormat,
                    localeDateFormat: layout.localeDateFormat,
                  });
                  return (
                    <td
                      key={col.name}
                      onClick={() => setActiveColName(col.name)}
                      style={{
                        padding: '4px 10px',
                        borderBottom: '1px solid var(--sr-border-subtle, #e2e8f0)',
                        borderRight: '1px solid var(--sr-border-subtle, #e2e8f0)',
                        textAlign: col.align || 'left',
                        maxWidth: 340,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {rowEditing && !col.read_only ? (
                        <input
                          className="sr-input"
                          aria-label={`Edit ${col.name}`}
                          value={serializeValueForEdit(val)}
                          onChange={(e) =>
                            setRowDraft((prev) => ({
                              ...(prev || {}),
                              [col.name]: coerceEditedValue(e.target.value, col),
                            }))
                          }
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              acceptCurrentRow();
                            } else if (e.key === 'Escape') {
                              setIsEditingRow(false);
                              setEditingRowIndex(null);
                              setIsInsertDraft(false);
                              setRowDraft(null);
                            }
                          }}
                          style={{width: '100%', minHeight: 24, padding: '2px 6px'}}
                        />
                      ) : (
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 6,
                            fontStyle: isNull ? 'italic' : 'normal',
                            opacity: isNull ? 0.58 : 1,
                          }}
                        >
                          <span>{isNull ? '<null>' : formatted.text ?? String(formatted)}</span>
                          {complex && (
                            <button
                              type="button"
                              className="sr-btn"
                              aria-label={gettext('Inspect %s in Right Drawer', col.name)}
                              onClick={(ev) => {
                                ev.stopPropagation();
                                openRightDrawerWith({
                                  panel: 'value_inspector',
                                  valueRowIndex: rIdx,
                                  valueColName: col.name,
                                });
                              }}
                              style={{minHeight: 18, padding: '0 5px', fontSize: '0.7rem'}}
                            >
                              [...]
                            </button>
                          )}
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Column Visibility Popover */}
      {colPickerOpen && (
        <div
          role="dialog"
          aria-label={gettext('Visible Grid Columns')}
          style={{
            position: 'absolute',
            top: 34,
            left: 12,
            zIndex: 30,
            padding: 10,
            borderRadius: 8,
            background: 'var(--sr-island-bg, #ffffff)',
            border: '1px solid var(--sr-border-default, #cbd5e1)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.14)',
            maxHeight: 280,
            overflow: 'auto',
            display: 'grid',
            gap: 4,
          }}
        >
          <div style={{display: 'flex', justifyContent: 'space-between', gap: 12}}>
            <strong style={{fontSize: '0.78rem'}}>{gettext('Grid Columns')}</strong>
            <button
              type="button"
              onClick={() => setColPickerOpen(false)}
              style={{border: 0, background: 'transparent', cursor: 'pointer'}}
            >
              ×
            </button>
          </div>
          {columns.map((c) => {
            const vis =
              !Array.isArray(layout.gridVisibleCols) || layout.gridVisibleCols.includes(c.name);
            return (
              <label key={c.name} style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem'}}>
                <input
                  type="checkbox"
                  checked={vis}
                  onChange={(e) => {
                    const curSet = new Set(
                      Array.isArray(layout.gridVisibleCols)
                        ? layout.gridVisibleCols
                        : columns.map((col) => col.name)
                    );
                    if (e.target.checked) curSet.add(c.name);
                    else if (curSet.size > 1) curSet.delete(c.name);
                    setLayout((prev) => ({...prev, gridVisibleCols: Array.from(curSet)}));
                  }}
                />
                {c.name}
              </label>
            );
          })}
        </div>
      )}
    </ScratchScrollArea>
  );

  // Render Data Pane across all 5 Surface 1 Display Modes!
  const renderDataPane = () => {
    if (!activeResult || columns.length === 0) {
      return (
        <Box sx={{p: 3, flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
          <EmptyState
            title={gettext('No Result Set Active')}
            description={gettext('Execute a SELECT statement (F9) or Script (F5) to view and edit rows.')}
          />
        </Box>
      );
    }

    const mode = layout.displayMode;

    if (mode === DISPLAY_MODES.MINI_FORMS) {
      return (
        <div
          className="sr-left-hover-scroll"
          data-cdeadmin-qa-key="sql-surface-mini-forms"
          style={{flex: 1, minHeight: 0, overflow: 'auto', padding: 10, display: 'grid', gap: 10}}
        >
          {rows.map((row, idx) => (
            <AdaptiveRecordFormCard
              key={row.identity_token || `mf-${idx}`}
              row={row}
              rowIndex={idx}
              isCurrent={idx === activeRowIndex}
              isEditing={isEditingRow && editingRowIndex === idx}
              draftValues={rowDraft}
              columns={formColumns}
              formLayout={sharedFormLayout}
              formFieldPrefs={layout.formFieldPrefs}
              booleanFormat={layout.booleanFormat}
              localeDateFormat={layout.localeDateFormat}
              onSelectRow={(i) => setActiveRowIndex(i)}
              onFocusField={(cName) => setActiveColName(cName)}
              onFieldChange={(cName, val) =>
                setRowDraft((prev) => ({...(prev || {}), [cName]: val}))
              }
              onOpenComplexInDrawer={(rIdx, cName) =>
                openRightDrawerWith({
                  panel: 'value_inspector',
                  valueRowIndex: rIdx,
                  valueColName: cName,
                })
              }
            />
          ))}
        </div>
      );
    }

    if (mode === DISPLAY_MODES.SINGLE_FORM) {
      return (
        <div
          data-cdeadmin-qa-key="sql-surface-single-form"
          style={{flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: 10, gap: 8}}
        >
          <div style={{display: 'flex', alignItems: 'center', gap: 8}}>
            <Button
              size="small"
              disabled={activeRowIndex <= 0}
              onClick={() => setActiveRowIndex((i) => Math.max(0, i - 1))}
            >
              ◀ {gettext('Prev')}
            </Button>
            <span style={{fontSize: '0.8rem'}}>
              {gettext('Record %s of %s', rows.length ? activeRowIndex + 1 : 0, rows.length)}
            </span>
            <Button
              size="small"
              disabled={activeRowIndex >= rows.length - 1}
              onClick={() => setActiveRowIndex((i) => Math.min(rows.length - 1, i + 1))}
            >
              {gettext('Next')} ▶
            </Button>
          </div>
          {currentRow && (
            <AdaptiveRecordFormCard
              row={currentRow}
              rowIndex={activeRowIndex}
              isCurrent
              isEditing={isEditingRow && editingRowIndex === activeRowIndex}
              draftValues={rowDraft}
              columns={formColumns}
              formLayout={sharedFormLayout}
              formFieldPrefs={layout.formFieldPrefs}
              booleanFormat={layout.booleanFormat}
              localeDateFormat={layout.localeDateFormat}
              fullArea
              onSelectRow={(i) => setActiveRowIndex(i)}
              onFocusField={(cName) => setActiveColName(cName)}
              onFieldChange={(cName, val) =>
                setRowDraft((prev) => ({...(prev || {}), [cName]: val}))
              }
              onOpenComplexInDrawer={(rIdx, cName) =>
                openRightDrawerWith({
                  panel: 'value_inspector',
                  valueRowIndex: rIdx,
                  valueColName: cName,
                })
              }
            />
          )}
        </div>
      );
    }

    if (
      mode === DISPLAY_MODES.HYBRID ||
      (mode === DISPLAY_MODES.HYBRID_EDIT && isEditingRow)
    ) {
      return (
        <div
          data-cdeadmin-qa-key="sql-surface-hybrid"
          style={{flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column'}}
        >
          {currentRow && (
            <div style={{padding: 8, borderBottom: '1px solid var(--sr-border-default)', flexShrink: 0}}>
              <AdaptiveRecordFormCard
                row={currentRow}
                rowIndex={activeRowIndex}
                isCurrent
                isEditing={isEditingRow && editingRowIndex === activeRowIndex}
                draftValues={rowDraft}
                columns={formColumns}
                formLayout={sharedFormLayout}
                formFieldPrefs={layout.formFieldPrefs}
                booleanFormat={layout.booleanFormat}
                localeDateFormat={layout.localeDateFormat}
                maxHeight={220}
                onSelectRow={(i) => setActiveRowIndex(i)}
                onFocusField={(cName) => setActiveColName(cName)}
                onFieldChange={(cName, val) =>
                  setRowDraft((prev) => ({...(prev || {}), [cName]: val}))
                }
                onOpenComplexInDrawer={(rIdx, cName) =>
                  openRightDrawerWith({
                    panel: 'value_inspector',
                    valueRowIndex: rIdx,
                    valueColName: cName,
                  })
                }
              />
            </div>
          )}
          <div style={{flex: 1, minHeight: 0, position: 'relative', display: 'flex'}}>
            {renderGridTable()}
          </div>
        </div>
      );
    }

    return (
      <div style={{flex: 1, minHeight: 0, position: 'relative', display: 'flex'}}>
        {renderGridTable()}
      </div>
    );
  };

  return (
    <Box
      ref={workAreaRef}
      data-cdeadmin-qa-key="sql-editor-surface"
      data-surface-view={surfaceView}
      sx={{
        flex: 1,
        minHeight: 0,
        minWidth: 0,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
      }}
    >
      {/* Hidden local .sql file reader */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".sql,.txt,application/sql,text/plain"
        style={{display: 'none'}}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          const reader = new FileReader();
          reader.onload = () => {
            const text = String(reader.result || '');
            setSqlText(text);
            editorRef.current?.setValue?.(text);
          };
          reader.readAsText(file);
          e.target.value = '';
        }}
      />

      {/* View 1: 100% SQL Code Canvas */}
      {surfaceView === SQL_SURFACE_VIEWS.SQL && renderSqlEditorPane()}

      {/* View 2: 100% Area 3e Shared DDN Visual Query Builder Canvas */}
      {surfaceView === SQL_SURFACE_VIEWS.VISUAL_BUILDER && (
        <div
          data-cdeadmin-qa-key="sql-surface-visual-builder-canvas"
          style={{flex: 1, minHeight: 0, minWidth: 0, position: 'relative', display: 'flex'}}
        >
          <RobinTiledCanvas
            scene={visualScene}
            selectedNodeId={selectedCanvasNodeId}
            onSelectNode={(nodeId) => {
              setSelectedCanvasNodeId(nodeId || '');
              openRightDrawerWith({panel: 'visual_inspector'});
            }}
            editable
            onPinNode={(nodeId, x, y) => {
              const next = {
                ...visualModel,
                tables: visualModel.tables.map((t) =>
                  t.id === nodeId ? {...t, x, y} : t
                ),
              };
              pushVisualModelUpdate(next, false);
            }}
            canvasApiRef={canvasApiRef}
            ariaLabel={gettext('DDN Visual Query Builder Canvas')}
          />
          {visualModel.tables.length === 0 && (
            <div
              style={{
                position: 'absolute',
                top: 14,
                left: 14,
                padding: '6px 12px',
                borderRadius: 999,
                background: 'var(--sr-island-bg, rgba(255,255,255,0.94))',
                border: '1px solid var(--sr-border-default, #cbd5e1)',
                fontSize: '0.78rem',
                pointerEvents: 'none',
              }}
            >
              {gettext('Visual Builder Canvas — use the Right Drawer Inspector to add tables & joins')}
            </div>
          )}
        </div>
      )}

      {/* View 3: SQL + Data Split View */}
      {surfaceView === SQL_SURFACE_VIEWS.SQL_DATA && (
        <div
          data-cdeadmin-qa-key="sql-surface-split-view"
          style={{
            flex: 1,
            minHeight: 0,
            minWidth: 0,
            display: 'flex',
            flexDirection: splitOrientation === 'vertical' ? 'column' : 'row',
          }}
        >
          <div
            style={{
              flex: `0 0 ${splitRatio}%`,
              minHeight: 100,
              minWidth: 160,
              display: 'flex',
              borderBottom:
                splitOrientation === 'vertical'
                  ? '2px solid var(--sr-border-default, #cbd5e1)'
                  : 'none',
              borderRight:
                splitOrientation === 'horizontal'
                  ? '2px solid var(--sr-border-default, #cbd5e1)'
                  : 'none',
            }}
          >
            {renderSqlEditorPane()}
          </div>
          <div style={{flex: 1, minHeight: 100, minWidth: 160, display: 'flex'}}>
            {renderDataPane()}
          </div>
        </div>
      )}

      {/* View 4: 100% Data View (Surface 1 Engine) */}
      {surfaceView === SQL_SURFACE_VIEWS.DATA && renderDataPane()}

      {/* View 5: 100% Metrics & Execution Plan */}
      {surfaceView === SQL_SURFACE_VIEWS.METRICS_PLAN && (
        <ScratchScrollArea fillViewport style={{flex: 1, minHeight: 0}}>
          <Box
            data-cdeadmin-qa-key="sql-surface-metrics-plan"
            sx={{p: 2, display: 'grid', gap: 2}}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                gap: 10,
              }}
            >
              {[
                [gettext('Prepare'), `${hostData?.timings_ms?.prepare_ms ?? 0} ms`],
                [gettext('Execute'), `${hostData?.timings_ms?.execute_ms ?? 0} ms`],
                [gettext('Fetch'), `${hostData?.timings_ms?.fetch_ms ?? 0} ms`],
                [gettext('Total Elapsed'), `${hostData?.timings_ms?.total_ms ?? 0} ms`],
                [gettext('Active Terminator'), terminator],
                [gettext('Result Sets'), String(hostData?.result_count ?? 0)],
              ].map(([lbl, val]) => (
                <div
                  key={lbl}
                  style={{
                    padding: '10px 12px',
                    borderRadius: 8,
                    border: '1px solid var(--sr-border-subtle)',
                  }}
                >
                  <div style={{fontSize: '0.74rem', opacity: 0.72}}>{lbl}</div>
                  <strong style={{fontSize: '1rem'}}>{val}</strong>
                </div>
              ))}
            </div>

            <div>
              <strong>{gettext('Execution Plan')}</strong>
              <pre
                style={{
                  marginTop: 6,
                  padding: 12,
                  borderRadius: 8,
                  border: '1px solid var(--sr-border-subtle)',
                  background: 'var(--sr-surface-subtle, rgba(15,23,42,0.04))',
                  whiteSpace: 'pre-wrap',
                  fontSize: '0.8rem',
                }}
              >
                {activeResult?.plan_text ||
                  hostData?.plan_text ||
                  gettext('Run Explain Plan on the TiB or Query menu to capture the native execution plan.')}
              </pre>
            </div>

            {(hostData?.statement_summaries || []).length > 0 && (
              <div>
                <strong>{gettext('Script Statement Execution Summary')}</strong>
                <table style={{width: '100%', marginTop: 6, borderCollapse: 'collapse', fontSize: '0.8rem'}}>
                  <thead>
                    <tr style={{textAlign: 'left', borderBottom: '1px solid var(--sr-border-default)'}}>
                      <th style={{padding: 6}}>#</th>
                      <th style={{padding: 6}}>{gettext('Line')}</th>
                      <th style={{padding: 6}}>{gettext('Status')}</th>
                      <th style={{padding: 6}}>{gettext('Rows')}</th>
                      <th style={{padding: 6}}>{gettext('Elapsed')}</th>
                      <th style={{padding: 6}}>SQL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hostData.statement_summaries.map((st, idx) => (
                      <tr key={idx} style={{borderBottom: '1px solid var(--sr-border-subtle)'}}>
                        <td style={{padding: 6}}>{st.ordinal}</td>
                        <td style={{padding: 6}}>{st.start_line}</td>
                        <td style={{padding: 6}}>{st.status}</td>
                        <td style={{padding: 6}}>{st.rows_returned ?? st.rows_affected ?? 0}</td>
                        <td style={{padding: 6}}>{st.elapsed_ms} ms</td>
                        <td style={{padding: 6, maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>
                          {st.sql_preview}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Box>
        </ScratchScrollArea>
      )}

      {/* View 6: 100% Result Fields Metadata */}
      {surfaceView === SQL_SURFACE_VIEWS.FIELDS && (
        <ScratchScrollArea fillViewport style={{flex: 1, minHeight: 0}}>
          <Box data-cdeadmin-qa-key="sql-surface-fields" sx={{p: 2}}>
            {columns.length === 0 ? (
              <EmptyState
                title={gettext('No Result Columns')}
                description={gettext('Execute a query returning columns to inspect result field metadata.')}
              />
            ) : (
              <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem'}}>
                <thead>
                  <tr style={{textAlign: 'left', borderBottom: '1px solid var(--sr-border-default)'}}>
                    <th style={{padding: 8}}>#</th>
                    <th style={{padding: 8}}>{gettext('Column')}</th>
                    <th style={{padding: 8}}>{gettext('Native Type')}</th>
                    <th style={{padding: 8}}>{gettext('Domain')}</th>
                    <th style={{padding: 8}}>{gettext('Nullable')}</th>
                    <th style={{padding: 8}}>{gettext('Key')}</th>
                    <th style={{padding: 8}}>{gettext('Profile')}</th>
                  </tr>
                </thead>
                <tbody>
                  {columns.map((c, idx) => (
                    <tr key={c.name} style={{borderBottom: '1px solid var(--sr-border-subtle)'}}>
                      <td style={{padding: 8}}>{idx + 1}</td>
                      <td style={{padding: 8}}>
                        <strong>{c.name}</strong>
                      </td>
                      <td style={{padding: 8}}>{c.native_type || c.logical_type || 'TEXT'}</td>
                      <td style={{padding: 8}}>{c.domain_type || '—'}</td>
                      <td style={{padding: 8}}>{c.nullable === false ? 'NOT NULL' : 'NULL'}</td>
                      <td style={{padding: 8}}>{c.key ? 'PK' : '—'}</td>
                      <td style={{padding: 8}}>
                        <Button
                          size="small"
                          onClick={async () => {
                            const prof = await callHost('column_profile', {column: c.name});
                            openRightDrawerWith({panel: 'column_profile', profileData: prof});
                          }}
                        >
                          {gettext('Profile')}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Box>
        </ScratchScrollArea>
      )}

      {/* View 7: 100% Structured Chronological Messages Log */}
      {surfaceView === SQL_SURFACE_VIEWS.MESSAGES && (
        <ScratchScrollArea fillViewport style={{flex: 1, minHeight: 0}}>
          <Box data-cdeadmin-qa-key="sql-surface-messages" sx={{p: 2, display: 'grid', gap: 1}}>
            {surfaceError && (
              <div
                role="alert"
                style={{
                  padding: '10px 12px',
                  borderRadius: 8,
                  background: 'rgba(220, 38, 38, 0.1)',
                  border: '1px solid var(--sr-status-danger, #dc2626)',
                  color: 'var(--sr-status-danger, #dc2626)',
                }}
              >
                {surfaceError}
              </div>
            )}
            {(hostData?.messages || []).length === 0 && !surfaceError ? (
              <EmptyState
                title={gettext('No Execution Messages')}
                description={gettext('Statement diagnostics, row counts, and script logs appear here.')}
              />
            ) : (
              (hostData?.messages || []).map((msg) => (
                <div
                  key={msg.id}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 8,
                    border: '1px solid var(--sr-border-subtle)',
                    background:
                      msg.severity === 'error'
                        ? 'rgba(220, 38, 38, 0.08)'
                        : msg.severity === 'warning'
                          ? 'rgba(217, 119, 6, 0.08)'
                          : 'transparent',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 12,
                    fontSize: '0.8125rem',
                  }}
                >
                  <div>
                    <div style={{fontSize: '0.72rem', opacity: 0.72}}>
                      [{String(msg.timestamp || '').slice(11, 19)}] <strong>{msg.operation}</strong>
                      {msg.elapsed_ms != null ? ` · ${msg.elapsed_ms} ms` : ''}
                      {msg.sqlstate ? ` · SQLSTATE ${msg.sqlstate}` : ''}
                    </div>
                    <div>{msg.message}</div>
                  </div>
                  <div style={{display: 'flex', gap: 6, flexShrink: 0}}>
                    {msg.line ? (
                      <Button
                        size="small"
                        data-cdeadmin-qa-key={`msg-jump-line-${msg.line}`}
                        onClick={() => jumpToSqlPosition(msg.line, msg.column || 1)}
                      >
                        {gettext('Line %s:%s', msg.line, msg.column || 1)}
                      </Button>
                    ) : null}
                    {msg.row_index != null ? (
                      <Button
                        size="small"
                        onClick={() => {
                          setActiveRowIndex(msg.row_index);
                          setSurfaceView(SQL_SURFACE_VIEWS.DATA);
                        }}
                      >
                        {gettext('Row %s', msg.row_index + 1)}
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))
            )}
          </Box>
        </ScratchScrollArea>
      )}

      {(loading || executing) && (
        <ProgressOverlay message={executing ? gettext('Executing SQL…') : gettext('Opening SQL Surface…')} />
      )}

      {/* Right-Click Context Menu */}
      <ContextMenu
        open={contextMenuState.open}
        x={contextMenuState.x}
        y={contextMenuState.y}
        items={contextMenuState.items}
        onClose={() => setContextMenuState((prev) => ({...prev, open: false}))}
      />

      {/* Modal Parameter Binding Dialog */}
      <Dialog
        open={paramModalOpen}
        title={gettext('Bind Query Parameters')}
        size="medium"
        onClose={() => {
          pendingExecRef.current = null;
          setParamModalOpen(false);
        }}
        actions={
          <>
            <Button
              onClick={() => {
                pendingExecRef.current = null;
                setParamModalOpen(false);
              }}
            >
              {gettext('Cancel')}
            </Button>
            <Button
              intent="primary"
              data-cdeadmin-qa-key="sql-params-confirm-btn"
              onClick={confirmParametersModal}
            >
              {pendingExecRef.current ? gettext('Bind & Execute') : gettext('Save Parameters')}
            </Button>
          </>
        }
      >
        <Box data-cdeadmin-qa-key="sql-parameter-dialog" sx={{display: 'grid', gap: 1.25}}>
          {detectedParams.length === 0 ? (
            <div style={{fontSize: '0.82rem', opacity: 0.8}}>
              {gettext('No parameter placeholders (:name, ?, $1) detected in the current SQL.')}
            </div>
          ) : (
            detectedParams.map((p) => {
              const key = p.name || String(p.index);
              const draft = paramDrafts[key] || {value: '', type: 'text', isNull: false};
              return (
                <div
                  key={key}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '140px 110px 1fr 76px',
                    gap: 8,
                    alignItems: 'center',
                  }}
                >
                  <strong style={{fontSize: '0.82rem'}}>{p.token || `:${key}`}</strong>
                  <select
                    className="sr-input"
                    aria-label={`Type for ${key}`}
                    value={draft.type}
                    onChange={(e) =>
                      setParamDrafts((prev) => ({
                        ...prev,
                        [key]: {...draft, type: e.target.value},
                      }))
                    }
                  >
                    <option value="text">{gettext('Text')}</option>
                    <option value="integer">{gettext('Integer')}</option>
                    <option value="numeric">{gettext('Numeric')}</option>
                    <option value="boolean">{gettext('Boolean')}</option>
                    <option value="json">{gettext('JSON')}</option>
                  </select>
                  <input
                    className="sr-input"
                    aria-label={`Value for ${key}`}
                    disabled={draft.isNull}
                    value={draft.isNull ? '' : draft.value}
                    placeholder={draft.isNull ? '<null>' : gettext('Enter value…')}
                    onChange={(e) =>
                      setParamDrafts((prev) => ({
                        ...prev,
                        [key]: {...draft, value: e.target.value},
                      }))
                    }
                  />
                  <label style={{display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.78rem'}}>
                    <input
                      type="checkbox"
                      checked={Boolean(draft.isNull)}
                      onChange={(e) =>
                        setParamDrafts((prev) => ({
                          ...prev,
                          [key]: {...draft, isNull: e.target.checked},
                        }))
                      }
                    />
                    NULL
                  </label>
                </div>
              );
            })
          )}
        </Box>
      </Dialog>

      {/* Unified Save Dialog (Quick Query + Display Layout / Tagged Snippet / .sql File / BI Question) */}
      <Dialog
        open={saveModalOpen}
        title={gettext('Save SQL / Quick Query / Tagged Snippet')}
        size="medium"
        onClose={() => setSaveModalOpen(false)}
        actions={
          <>
            <Button onClick={() => setSaveModalOpen(false)}>{gettext('Cancel')}</Button>
            <Button
              intent="primary"
              data-cdeadmin-qa-key="sql-save-confirm-btn"
              onClick={handleConfirmSave}
            >
              {gettext('Save')}
            </Button>
          </>
        }
      >
        <Box data-cdeadmin-qa-key="sql-save-dialog" sx={{display: 'grid', gap: 1.25}}>
          <div style={{display: 'flex', gap: 6, flexWrap: 'wrap'}}>
            {[
              ['quick_query', gettext('Quick Query (+ Display Layout)')],
              ['snippet', gettext('Tagged SQL Snippet')],
              ['sql_file', gettext('Download .sql File')],
              ['bi_question', gettext('Draft BI Question')],
            ].map(([kid, lbl]) => (
              <Button
                key={kid}
                size="small"
                intent={saveKind === kid ? 'primary' : 'neutral'}
                data-cdeadmin-qa-key={`sql-save-kind-${kid}`}
                onClick={() => setSaveKind(kid)}
              >
                {lbl}
              </Button>
            ))}
          </div>

          <TextField
            label={gettext('Name / Title')}
            value={saveTitle}
            onChange={(e) => setSaveTitle(e.target.value)}
          />

          {(saveKind === 'quick_query' || saveKind === 'snippet') && (
            <TextField
              label={gettext('Description')}
              value={saveDescription}
              onChange={(e) => setSaveDescription(e.target.value)}
            />
          )}

          {saveKind === 'snippet' && (
            <div style={{display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10}}>
              <TextField
                label={gettext('Tags (comma-separated)')}
                placeholder="firebird, ddl, trigger"
                value={saveTagsText}
                onChange={(e) => setSaveTagsText(e.target.value)}
              />
              <TextField
                label={gettext('Tab Shortcut')}
                placeholder="fbtpl"
                value={saveShortcut}
                onChange={(e) => setSaveShortcut(e.target.value)}
              />
            </div>
          )}

          {selectionText.trim() && (
            <label style={{display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem'}}>
              <input
                type="checkbox"
                checked={saveUseSelection}
                onChange={(e) => setSaveUseSelection(e.target.checked)}
              />
              {gettext('Save highlighted selection only')}
            </label>
          )}
        </Box>
      </Dialog>

      {/* Quick Queries Library Loader Modal */}
      <Dialog
        open={quickQueryModalOpen}
        title={gettext('Saved Quick Queries')}
        size="medium"
        onClose={() => setQuickQueryModalOpen(false)}
        actions={
          <Button onClick={() => setQuickQueryModalOpen(false)}>{gettext('Close')}</Button>
        }
      >
        <Box data-cdeadmin-qa-key="sql-quick-queries-dialog" sx={{display: 'grid', gap: 1}}>
          {quickQueries.length === 0 ? (
            <div style={{fontSize: '0.82rem', opacity: 0.75}}>
              {gettext('No Quick Queries saved yet. Use Save → Quick Query to store SQL together with its display layout.')}
            </div>
          ) : (
            quickQueries.map((qq) => (
              <div
                key={qq.query_id}
                style={{
                  padding: 10,
                  borderRadius: 8,
                  border: '1px solid var(--sr-border-subtle)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 10,
                }}
              >
                <div style={{minWidth: 0}}>
                  <strong>{qq.name}</strong>
                  {qq.description && (
                    <div style={{fontSize: '0.75rem', opacity: 0.78}}>{qq.description}</div>
                  )}
                  <div style={{fontSize: '0.72rem', opacity: 0.68}}>
                    {gettext('Display: %s · Terminator: %s', qq.display_layout?.displayMode || 'grid', qq.terminator || ';')}
                  </div>
                </div>
                <div style={{display: 'flex', gap: 6, flexShrink: 0}}>
                  <Button
                    size="small"
                    intent="primary"
                    data-cdeadmin-qa-key={`load-quick-query-${qq.query_id}`}
                    onClick={() => handleLoadQuickQuery(qq.query_id)}
                  >
                    {gettext('Load')}
                  </Button>
                  <Button
                    size="small"
                    onClick={async () => {
                      const res = await callHost('delete_quick_query', {query_id: qq.query_id});
                      if (Array.isArray(res?.quick_queries)) setQuickQueries(res.quick_queries);
                    }}
                  >
                    {gettext('Delete')}
                  </Button>
                </div>
              </div>
            ))
          )}
        </Box>
      </Dialog>

      {/* Page & Fetch Limits Dialog */}
      <Dialog
        open={limitsModalOpen}
        title={gettext('SQL Session & Fetch Limits')}
        size="small"
        onClose={() => setLimitsModalOpen(false)}
        actions={
          <>
            <Button onClick={() => setLimitsModalOpen(false)}>{gettext('Cancel')}</Button>
            <Button
              intent="primary"
              onClick={async () => {
                const resp = await callHost('set_options', {
                  page_size: Number(limitsDraft.pageSize) || 200,
                  max_rows: Number(limitsDraft.maxRows) || 1000,
                });
                applyHostState(resp);
                setLimitsModalOpen(false);
              }}
            >
              {gettext('Apply')}
            </Button>
          </>
        }
      >
        <Box sx={{display: 'grid', gap: 1.25}}>
          <TextField
            label={gettext('Page Size')}
            value={String(limitsDraft.pageSize)}
            onChange={(e) =>
              setLimitsDraft((p) => ({...p, pageSize: Number(e.target.value) || 200}))
            }
          />
          <TextField
            label={gettext('Max Buffered Rows')}
            value={String(limitsDraft.maxRows)}
            onChange={(e) =>
              setLimitsDraft((p) => ({...p, maxRows: Number(e.target.value) || 1000}))
            }
          />
          {isFirebird && (
            <div className="sr-field">
              <label className="sr-field-label">{gettext('Firebird SQL Dialect')}</label>
              <select
                className="sr-input"
                value={clientSqlDialect}
                onChange={(e) => setClientSqlDialect(Number(e.target.value) || 3)}
              >
                <option value={3}>{gettext('Dialect 3 — Modern SQL')}</option>
                <option value={1}>{gettext('Dialect 1 — Legacy')}</option>
              </select>
            </div>
          )}
        </Box>
      </Dialog>

      {/* Connection Details Dialog */}
      <Dialog
        open={connectionModalOpen}
        title={gettext('Bound SQL Surface Connection')}
        size="small"
        onClose={() => setConnectionModalOpen(false)}
        actions={
          <Button onClick={() => setConnectionModalOpen(false)}>{gettext('Close')}</Button>
        }
      >
        <Box sx={{display: 'grid', gap: 0.75, fontSize: '0.84rem'}}>
          <div>
            <strong>{gettext('Database')}:</strong> {endpointLabel || databaseTargetId || '—'}
          </div>
          <div>
            <strong>{gettext('Engine / Profile')}:</strong> {engineId} ({languageProfile || 'sql'})
          </div>
          <div>
            <strong>{gettext('Host Session ID')}:</strong> {hostData?.session_id || gettext('Lazy (opens on first statement)')}
          </div>
          <div>
            <strong>{gettext('Active Statement Terminator')}:</strong> {terminator}
          </div>
        </Box>
      </Dialog>

      {/* Shared Multi-Format Export Dialog (`CSV/TSV`, `XLSX`, `ODS`, `PDF`, `JSON`, `SQL`) */}
      <SurfaceExportDialog
        open={exportDialogOpen}
        onClose={() => setExportDialogOpen(false)}
        initialFormat={exportInitialFormat}
        defaultFilename={activeQuickQueryName || targetResource?.display_name || 'sql_result'}
        defaultTitle={activeQuickQueryName || endpointLabel || 'SQL Query Report'}
        tableName={activeResult?.target_resource?.display_name || targetResource?.display_name || 'QUERY_RESULT'}
        rows={rows}
        columns={gridColumns}
        onExportHost={(req) => callHost('export_formatted', req)}
      />
    </Box>
  );
}

function SqlFilterBuilderDrawer({columns, initialColumn, filters, onApply}) {
  const [col, setCol] = useState(initialColumn || columns[0]?.name || '');
  const [op, setOp] = useState('contains');
  const [val, setVal] = useState('');

  useEffect(() => {
    if (initialColumn) setCol(initialColumn);
  }, [initialColumn]);

  return (
    <Box sx={{p: 1.5, display: 'grid', gap: 1}}>
      <strong>{gettext('Result Filter Builder')}</strong>
      <select className="sr-input" value={col} onChange={(e) => setCol(e.target.value)}>
        {(columns || []).map((c) => (
          <option key={c.name} value={c.name}>
            {c.name}
          </option>
        ))}
      </select>
      <select className="sr-input" value={op} onChange={(e) => setOp(e.target.value)}>
        <option value="contains">{gettext('Contains')}</option>
        <option value="eq">{gettext('Equals (=)')}</option>
        <option value="neq">{gettext('Not Equal (<>)')}</option>
        <option value="starts_with">{gettext('Starts With')}</option>
        <option value="gt">{gettext('Greater Than (>)')}</option>
        <option value="lt">{gettext('Less Than (<)')}</option>
        <option value="is_null">IS NULL</option>
        <option value="not_null">IS NOT NULL</option>
      </select>
      {!['is_null', 'not_null'].includes(op) && (
        <TextField label={gettext('Value')} value={val} onChange={(e) => setVal(e.target.value)} />
      )}
      <div style={{display: 'flex', gap: 6}}>
        <Button
          size="small"
          intent="primary"
          onClick={() => {
            if (!col) return;
            onApply([
              ...(filters || []).filter((f) => f.column !== col),
              {column: col, op, value: val},
            ]);
          }}
        >
          {gettext('Apply')}
        </Button>
        {(filters || []).length > 0 && (
          <Button size="small" onClick={() => onApply([])}>
            {gettext('Clear')}
          </Button>
        )}
      </div>
    </Box>
  );
}

SqlFilterBuilderDrawer.propTypes = {
  columns: PropTypes.array,
  initialColumn: PropTypes.string,
  filters: PropTypes.array,
  onApply: PropTypes.func.isRequired,
};

SqlEditorSurface.propTypes = {
  endpointLabel: PropTypes.string,
  engineId: PropTypes.string,
  languageProfile: PropTypes.string,
  activeLanguage: PropTypes.object,
  databaseTargetId: PropTypes.string,
  targetResource: PropTypes.object,
  resources: PropTypes.array,
  initialScriptKind: PropTypes.string,
  initialSql: PropTypes.string,
  initialQuickQueryId: PropTypes.string,
  post: PropTypes.func.isRequired,
};
