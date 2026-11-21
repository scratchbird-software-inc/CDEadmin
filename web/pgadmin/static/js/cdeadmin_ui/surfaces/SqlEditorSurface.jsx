/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {setQuickQueryShortcut, useQuickQueryShortcuts} from '../editors/QuickQueryShortcuts';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import PropTypes from 'prop-types';

import {formatNative} from '../editors/nativeFormatting';
import {formatFirebird, firebirdTokens} from '../editors/firebirdFormatting';
import {firebirdFragments} from '../editors/firebirdExecution';
import gettext from 'sources/gettext';
import SurfaceLayoutTemplateList from './SurfaceLayoutTemplateList';
import {sqlEditorActionHints} from './surfaceActionHints';
import {Box} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextArea, TextField} from '../primitives/Field';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import ContextMenu from '../navigation/ContextMenu';
import {Dialog} from '../overlays/Dialog';
import {EmptyState} from '../feedback/EmptyState';
import {ProgressOverlay} from '../feedback/ProgressOverlay';
import {
  T_ACTION_STATUS,
  T_ACTION_TARGET_KIND,
  useLocaleRevision,
} from '../actions/t_actions';
import {PROJECT_TOP_MENU_INDICES} from '../commands/MenuStructure';
import {
  useProjectInstanceScope,
  useProjectShell,
} from '../shell/ProjectShell';
import {useModalCloseGuard} from '../../helpers/ModalCloseGuard';
import {promptAbandonUncommittedWork} from '../overlays/UncommittedWorkDialog';
import CodeEditor from '../editors/CodeEditor';
import {sqlLanguageConfig, sqlLanguageProfile} from '../editors/sqlLanguageProfiles';
import {RobinTiledCanvas} from '../integrations/ddn/RobinTiledCanvas';
import SurfaceExportDialog from './SurfaceExportDialog';
import RecordDataView from './RecordDataView';
import SurfaceDisplayAreas from './SurfaceDisplayAreas';
import {displayAreaControl, presentationChoices} from './displayAreaControls';
import SurfaceInformation from './SurfaceInformation';
import FieldTypeDefaultsDialog from './FieldTypeDefaultsDialog';
import SurfaceMetadata from './SurfaceMetadata';
import {convertRecordField, recordConversionPair, useRecordConversions} from './recordConversions';
import ColumnOrderDialog from './RecordColumnOrderDialog';
import {
  SqlFirebirdSessionToolsDialog,
  SqlPersistentHistoryPanel,
  SqlProfilerAndStatsView,
  SqlProfilerConsentDialog,
} from './SqlFirebirdDiagnostics';
import {
  SqlMySQLAnalyzeConsentDialog,
  SqlMySQLPlanGraphView,
  SqlMySQLQueryAttributesDialog,
} from './SqlMySQLDiagnostics';
import {
  SqlMariaDBAnalyzeConsentDialog,
  SqlMariaDBSessionDialog,
} from './SqlMariaDBDiagnostics';
import {
  defaultLayoutState,
  orderedColumns,
} from './RecordForm';
import {
  BOOLEAN_FORMATS,
  DISPLAY_MODES,
  resolveRecordPresentation,
  buildFormLayoutPlacements,
  coerceEditedValue,
  isValidJsonDraft,
  inferColumnMeta,
  formatBytes,
  serializeValueForEdit,
} from './dataEditSurfaceHelpers';

const GUTTER_WIDTH = 58;
const EMPTY_ARRAY = Object.freeze([]);
const MYSQL_SURFACE_KEYS = new Set(['mysql', 'mysql-native', 'mysql-sql']);
const MARIADB_SURFACE_KEYS = new Set(['mariadb', 'mariadb-native', 'mariadb-sql']);

export const SQL_SURFACE_VIEWS = Object.freeze({
  SQL: 'sql',
  VISUAL_BUILDER: 'visual_builder',
  SQL_DATA: 'sql_data',
  DATA: 'data',
  METRICS_PLAN: 'metrics_plan',
  FIELDS: 'fields',
  INFORMATION: 'information',
  METADATA: 'metadata',
  MESSAGES: 'messages',
});

function transactionStartOptions(family) {
  if (family === 'sqlite') {
    return [['mode', gettext('Transaction Mode'), [
      ['deferred', gettext('Deferred')], ['immediate', gettext('Immediate')], ['exclusive', gettext('Exclusive')],
    ]]];
  }
  const access = ['access', gettext('Access'), [
    ['read_write', gettext('Read write')], ['read_only', gettext('Read only')],
  ]];
  const readCommitted = ['read_committed', gettext('Read committed')];
  if (family === 'firebird') {
    return [
      access,
      ['isolation', gettext('Isolation'), [['snapshot', gettext('Snapshot')], readCommitted]],
      ['wait', gettext('Lock wait'), [['wait', gettext('Wait')], ['no_wait', gettext('No wait')]]],
    ];
  }
  const isolation = [
    readCommitted, ['repeatable_read', gettext('Repeatable read')], ['serializable', gettext('Serializable')],
  ];
  if (family === 'mysql' || family === 'mariadb') {
    isolation.unshift(['read_uncommitted', gettext('Read uncommitted')]);
  }
  return [access, ['isolation', gettext('Isolation'), isolation]];
}

function quickQueryDisplayLabel(mode) {
  switch (mode) {
  case DISPLAY_MODES.MINI_FORMS: return gettext('Mini-Forms');
  case DISPLAY_MODES.HYBRID: return gettext('Hybrid');
  case DISPLAY_MODES.SINGLE_FORM: return gettext('Single Form');
  case DISPLAY_MODES.HYBRID_EDIT: return gettext('Hybrid-When-Editing');
  default: return gettext('Standard Grid');
  }
}

function restoreQuickQueryParameters(parameters) {
  const restored = {};
  for (const parameter of Array.isArray(parameters) ? parameters : []) {
    if (parameter?.name) {
      restored[parameter.name] = {
        value: parameter.value ?? '',
        type: parameter.type || 'text',
        isNull: Boolean(parameter.isNull),
      };
    }
  }
  return restored;
}

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

function LiveDrawerView({subscribe, renderRef}) {
  const [, bump] = useState(0);
  useEffect(() => subscribe(() => bump((n) => n + 1)), [subscribe]);
  return renderRef.current ? renderRef.current() : null;
}
LiveDrawerView.propTypes = {
  subscribe: PropTypes.func.isRequired,
  renderRef: PropTypes.object.isRequired,
};

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
  initialSessionToolsTab = '',
  post,
}) {
  const shell = useProjectShell();
  const localeRevision = useLocaleRevision();
  const quickQueryShortcuts = useQuickQueryShortcuts();
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
  const [metadataSelection, setMetadataSelection] = useState(null);
  const [upperView, setUpperView] = useState(SQL_SURFACE_VIEWS.SQL);
  const [lowerView, setLowerView] = useState(SQL_SURFACE_VIEWS.DATA);
  const [upperMode, setUpperMode] = useState('');
  const [lowerMode, setLowerMode] = useState('');

  const [sqlText, setSqlText] = useState(initialSql || '');
  const sqlTextRef = useRef(sqlText);
  sqlTextRef.current = sqlText;
  const lastInitialSqlRef = useRef(initialSql || '');
  useEffect(() => {
    if (initialSql && initialSql !== lastInitialSqlRef.current) {
      lastInitialSqlRef.current = initialSql;
      setSqlText(initialSql);
    }
  }, [initialSql]);

  const [selectionText, setSelectionText] = useState('');
  const [cursorPos, setCursorPos] = useState({line: 1, col: 1});
  const [terminator, setTerminator] = useState(';');
  const [autocommit, setAutocommit] = useState(false);
  const [clientSqlDialect, setClientSqlDialect] = useState(3);
  const [limitsDraft, setLimitsDraft] = useState({pageSize: 200, maxRows: 1000});

  const [hostData, setHostData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const executionRef = useRef(null);
  const executionSequence = useRef(0);
  const [canCancel, setCanCancel] = useState(false);
  const [cancelPending, setCancelPending] = useState(false);
  const [surfaceError, setSurfaceError] = useState('');

  // Surface 1 Display & Live Editing State for Data / SQL+Data
  const [layout, setLayout] = useState(defaultLayoutState);
  const [fieldDefaultsOpen, setFieldDefaultsOpen] = useState(false);
  const [templatePickerOpen, setTemplatePickerOpen] = useState(false);
  const [availableTemplates, setAvailableTemplates] = useState(null);
  const [templateLoadError, setTemplateLoadError] = useState('');
  const [formatFieldName, setFormatFieldName] = useState(null);
  const loadedObjectLayoutRef = useRef(null);
  const explicitLayoutRef = useRef(false);
  const savedResultViewRef = useRef(null);
  const [activeRowIndex, setActiveRowIndex] = useState(0);
  const [activeColName, setActiveColName] = useState('');
  const [isEditingRow, setIsEditingRow] = useState(false);
  const [editingRowIndex, setEditingRowIndex] = useState(null);
  const [isInsertDraft, setIsInsertDraft] = useState(false);
  const [rowDraft, setRowDraft] = useState(null);
  const [bookmarksByResult, setBookmarksByResult] = useState({});
  const pendingCellFocusRef = useRef(null);
  const [colPickerOpen, setColPickerOpen] = useState(false);
  const [columnPickerScope, setColumnPickerScope] = useState('grid');
  const [selectedCells, setSelectedCells] = useState([]);
  const gridViewportRef = useRef(null);
  const companionGridRef = useRef(null);
  const focusedDisplayAreaRef = useRef(null);
  const [, setScrollRowRange] = useState({start:0,end:30});
  const [viewportWidth, setViewportWidth] = useState(960);
  const workAreaRef = useRef(null);

  // Visual Query Builder State (100% Area 3e RobinTiledCanvas + 3b Inspector)
  const [visualModel, setVisualModel] = useState(defaultVisualModel);
  const visualModelRef = useRef(visualModel);
  visualModelRef.current = visualModel;
  const [visualScene, setVisualScene] = useState(null);
  const [visualCatalogObjects, setVisualCatalogObjects] = useState(EMPTY_ARRAY);
  const [visualFidelity, setVisualFidelity] = useState('exact');
  const [visualLossNotes, setVisualLossNotes] = useState(EMPTY_ARRAY);
  const [fanoutWarnings, setFanoutWarnings] = useState(EMPTY_ARRAY);
  const [selectedCanvasNodeId, setSelectedCanvasNodeId] = useState('');
  const [vbInspectorTab, setVbInspectorTab] = useState('tables');
  const [vbTableSearch, setVbTableSearch] = useState('');
  const [vbKindFilter, setVbKindFilter] = useState('all'); // 'all' | 'table' | 'view' | 'procedure'
  const [canvasDropActive, setCanvasDropActive] = useState(false);
  const [canvasNotice, setCanvasNotice] = useState('');

  // Modal Parameter Binding Dialog State
  const [paramModalOpen, setParamModalOpen] = useState(false);
  const [preparedStatement, setPreparedStatement] = useState(null);
  const [startTransactionOpen, setStartTransactionOpen] = useState(false);
  const [prepareTransactionOpen, setPrepareTransactionOpen] = useState(false);
  const [recovery, setRecovery] = useState(null);
  const [transactionOptions, setTransactionOptions] = useState({});
  const [transactionStartError, setTransactionStartError] = useState('');
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
  const saveEffectiveQueryRef = useRef(null);
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
  const [collectStatistics, setCollectStatistics] = useState(false);
  const [historySensitive, setHistorySensitive] = useState(false);
  const [profilerConsentOpen, setProfilerConsentOpen] = useState(false);
  const [mysqlAttributesOpen, setMysqlAttributesOpen] = useState(false);
  const [mysqlQueryAttrs, setMysqlQueryAttrs] = useState({});
  const [mysqlAnalyzeConsentOpen, setMysqlAnalyzeConsentOpen] = useState(false);
  const [mariadbSessionOpen, setMariadbSessionOpen] = useState(false);
  const [mariadbAnalyzeConsentOpen, setMariadbAnalyzeConsentOpen] = useState(false);
  const [sessionToolsOpen, setSessionToolsOpen] = useState(Boolean(initialSessionToolsTab));
  const [sessionToolsTab, setSessionToolsTab] = useState(initialSessionToolsTab || 'eds_pool');
  useEffect(() => {
    if (initialSessionToolsTab) {
      setSessionToolsTab(initialSessionToolsTab);
      setSessionToolsOpen(true);
    }
  }, [initialSessionToolsTab]);
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
  const languageOptions = useMemo(() => sqlLanguageProfile(languageProfile, engineId), [languageProfile, engineId]);
  const isFirebird = languageOptions.native_transaction_close_warning;
  const isMySQL = MYSQL_SURFACE_KEYS.has(languageProfile) || MYSQL_SURFACE_KEYS.has(engineId);
  const isMariaDB = MARIADB_SURFACE_KEYS.has(languageProfile) || MARIADB_SURFACE_KEYS.has(engineId);
  const sqlEditorConfig = useMemo(() => sqlLanguageConfig(languageOptions, activeLanguage?.editor, clientSqlDialect, resources),
    [languageOptions, activeLanguage?.editor, clientSqlDialect, resources]);

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

  const ensureSurfaceSession = useCallback(async () => {
    if (hostData?.session_id) return hostData.session_id;
    const resp = await callHost('ensure_session');
    if (resp) setHostData(resp);
    return resp?.session_id || null;
  }, [callHost, hostData?.session_id]);

  useEffect(() => {
    if (!templatePickerOpen) return undefined;
    let active = true;
    setAvailableTemplates(null);
    setTemplateLoadError('');
    callHost('list_templates').then((response) => {
      if (!Array.isArray(response?.templates)) throw new Error(gettext('Invalid template list.'));
      if (active) setAvailableTemplates(response.templates);
    }).catch((error) => {
      if (active) setTemplateLoadError(error?.message || String(error));
    });
    return () => { active = false; };
  }, [callHost, templatePickerOpen]);

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

  const restoreNamedLayout = useCallback((savedLayout) => {
    const {upperArea, lowerArea, upperPresentation, lowerPresentation, surfaceContent, resultView, effectiveSqlDialect, ...recordLayout} = savedLayout || {};
    explicitLayoutRef.current = Boolean(Object.keys(recordLayout).length);
    savedResultViewRef.current = resultView || null;
    if ([1, 2, 3].includes(effectiveSqlDialect)) setClientSqlDialect(effectiveSqlDialect);
    setLayout({...defaultLayoutState(), ...recordLayout});
    const views = Object.values(SQL_SURFACE_VIEWS);
    const validPane = (view) => views.includes(view) && view !== SQL_SURFACE_VIEWS.SQL_DATA;
    if (validPane(upperArea) && validPane(lowerArea) && (upperArea !== lowerArea || upperArea === SQL_SURFACE_VIEWS.DATA)) {
      setUpperView(upperArea);
      setLowerView(lowerArea);
    } else {
      setUpperView(SQL_SURFACE_VIEWS.SQL);
      setLowerView(SQL_SURFACE_VIEWS.DATA);
    }
    const modes = Object.values(DISPLAY_MODES);
    setUpperMode(modes.includes(upperPresentation) ? upperPresentation : '');
    setLowerMode(modes.includes(lowerPresentation) ? lowerPresentation : '');
    if (views.includes(surfaceContent)) setSurfaceView(surfaceContent);
  }, []);

  const saveObjectLayout = async () => {
    try {
      await callHost('save_object_layout', {object_layout_key: hostData?.object_layout_key, layout});
    } catch (error) {
      setSurfaceError(error?.message || String(error));
    }
  };

  const applyHostState = useCallback((resp) => {
    if (!resp) return;
    setHostData(resp);
    const objectKey = resp.object_layout_key || null;
    if (loadedObjectLayoutRef.current !== objectKey) {
      loadedObjectLayoutRef.current = objectKey;
      if (!explicitLayoutRef.current) {
        setLayout({...defaultLayoutState(), ...resp.saved_specific_layout});
      }
    }
    if (resp.terminator) setTerminator(resp.terminator);
    if (typeof resp.autocommit === 'boolean') setAutocommit(resp.autocommit);
    if (Array.isArray(resp.quick_queries)) setQuickQueries(resp.quick_queries);
    if (Array.isArray(resp.snippets?.snippets)) setSnippetsPayload(resp.snippets);
    if (resp.visual_builder?.ddn_scene) setVisualScene(resp.visual_builder.ddn_scene);
    if (resp.visual_builder?.model) setVisualModel(resp.visual_builder.model);
    if (Array.isArray(resp.visual_builder?.catalog_objects)) {
      setVisualCatalogObjects(resp.visual_builder.catalog_objects);
    } else if (Array.isArray(resp.catalog_objects)) {
      setVisualCatalogObjects(resp.catalog_objects);
    }
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
            setParamDrafts(restoreQuickQueryParameters(qq.parameters));
            restoreNamedLayout(qq.display_layout);
          } else {
            setSurfaceError(gettext('This saved query is unavailable for the current database.'));
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

  // Auto-heal initial opaque UUID tab title (`sql: 146d6c07-...`) to human-readable database name
  useEffect(() => {
    if (!endpointLabel || !instId) return;
    const curShell = shellRef.current;
    const curInst = curShell?.instances?.find((i) => i.instanceId === instId);
    if (curInst && !curInst.customTitle && /^sql:\s*[0-9a-f]{8}-[0-9a-f]{4}-/i.test(curInst.title || '')) {
      const cleanName = endpointLabel.split('/').pop()?.trim() || endpointLabel.trim();
      if (cleanName) {
        curShell.updateInstance?.(instId, {title: `sql: ${cleanName}`});
      }
    }
  }, [endpointLabel, instId]);

  useEffect(() => {
    refreshSnippets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snippetSearch, selectedTags, snippetTagMode, snippetFavoritesOnly, snippetAllEngines]);

  // Active Result Set & Surface 1 Data Columns / Rows
  const activeResult = hostData?.active_result || null;
  const columns = useMemo(
    () => (activeResult?.columns || EMPTY_ARRAY).map(col => ({...col, editable: col.editable ?? !col.read_only})),
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
      prevFormColsRef.current,
      rows
    );
    prevFormColsRef.current = computed.numCols;
    return computed;
  }, [formColumns, layout.formFieldPrefs, viewportWidth, rows]);

  const currentRow = rows[activeRowIndex] || null;
  const isEditableResult = Boolean(activeResult?.editable && !hostData?.transaction_prepare_state);
  const canInsertResult = Boolean(
    !hostData?.transaction_prepare_state &&
    (activeResult?.editable || (activeResult?.row_operations || []).includes('insert'))
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
    if (!hasUncommittedRef.current || hostData?.xa_state === 'unknown') {
      try {
        await callHost('close_surface');
      } catch (error) {
        setSurfaceError(error?.message || String(error));
        return false;
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
    } catch (error) {
      setSurfaceError(error?.message || String(error));
      return false;
    }
    return true;
  }, [callHost, endpointLabel, hostData?.staged_count, hostData?.xa_state, isFirebird]);

  const confirmCloseGuardRef = useRef(confirmCloseGuard);
  confirmCloseGuardRef.current = confirmCloseGuard;
  const stableConfirmCloseGuard = useCallback(
    () => confirmCloseGuardRef.current(),
    []
  );

  useModalCloseGuard(stableConfirmCloseGuard);

  // Visual Builder Sync & Interactive Canvas Helpers
  const syncSqlIntoVisualBuilder = useCallback(
    async (sourceOverride) => {
      const liveText = editorRef.current?.getValue?.() ?? sqlTextRef.current;
      const src = sourceOverride ?? liveText;
      try {
        const res = await callHost('visual_builder_from_sql', {sql_text: src});
        if (res?.model) setVisualModel(res.model);
        if (res?.scene) setVisualScene(res.scene);
        if (Array.isArray(res?.catalog_objects)) {
          setVisualCatalogObjects(res.catalog_objects);
        } else if (Array.isArray(res?.visual_builder?.catalog_objects)) {
          setVisualCatalogObjects(res.visual_builder.catalog_objects);
        }
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
      visualModelRef.current = nextModel;
      setVisualModel(nextModel);
      try {
        const res = await callHost('visual_builder_scene', {model: nextModel});
        if (res?.scene) setVisualScene(res.scene);
        if (Array.isArray(res?.catalog_objects)) {
          setVisualCatalogObjects(res.catalog_objects);
        }
        setFanoutWarnings(res?.fanout_warnings || EMPTY_ARRAY);
        if (syncSqlNow && typeof res?.sql_text === 'string') {
          if (res.sql_text.trim() || (nextModel.tables || []).length === 0) {
            setSqlText(res.sql_text);
            editorRef.current?.setValue?.(res.sql_text);
            setVisualFidelity('exact');
            setVisualLossNotes(EMPTY_ARRAY);
          }
        }
      } catch (err) {
        setSurfaceError(err?.message || String(err));
      }
    },
    [callHost]
  );

  const addCatalogObjectToCanvas = useCallback(
    async (rawResource, dropCoords = null) => {
      if (!rawResource) return;
      const curModel = visualModelRef.current;
      const rkind = String(rawResource.resource_kind || 'table').toLowerCase();
      const rname = String(rawResource.display_name || rawResource.name || '').trim();
      if (!rname) return;

      if (rkind === 'column') {
        setCanvasNotice(
          gettext('Drag a Table, View, or Selectable Stored Procedure onto the canvas to add it.')
        );
        return;
      }

      setCanvasNotice('');
      let resolvedNode = null;
      let suggestedJoins = [];

      try {
        const res = await callHost('resolve_visual_object', {
          target_resource: {
            resource_id: rawResource.resource_id || '',
            resource_kind: rkind,
            display_name: rname,
            schema_name: rawResource.schema_name || '',
            columns: rawResource.columns,
            input_parameters: rawResource.input_parameters,
            extensions: rawResource.extensions,
          },
          existing_tables: curModel.tables || [],
        });
        if (Array.isArray(res?.catalog_objects)) {
          setVisualCatalogObjects(res.catalog_objects);
        }
        if (res?.object_node) {
          resolvedNode = res.object_node;
          suggestedJoins = Array.isArray(res.suggested_joins) ? res.suggested_joins : [];
        }
      } catch (err) {
        const msg = err?.message || String(err);
        setCanvasNotice(msg);
        return;
      }

      if (!resolvedNode) {
        setCanvasNotice(gettext('The server did not return catalog metadata for this object. Refresh the catalog and try again.'));
        return;
      }

      const idx = (curModel.tables || []).length;
      const posX =
        dropCoords && Number.isFinite(dropCoords.x)
          ? Math.round(dropCoords.x)
          : 90 + (idx % 3) * 320;
      const posY =
        dropCoords && Number.isFinite(dropCoords.y)
          ? Math.round(dropCoords.y)
          : 72 + Math.floor(idx / 3) * 280;

      const positionedNode = {
        ...resolvedNode,
        x: posX,
        y: posY,
      };

      const existingJoinSigs = new Set(
        (curModel.joins || []).map(
          (j) => `${j.left_table}.${j.left_column}->${j.right_table}.${j.right_column}`
        )
      );
      const dedupedNewJoins = suggestedJoins.filter((sj) => {
        const sig = `${sj.left_table}.${sj.left_column}->${sj.right_table}.${sj.right_column}`;
        if (existingJoinSigs.has(sig)) return false;
        existingJoinSigs.add(sig);
        return true;
      });

      const nextModel = {
        ...curModel,
        tables: [...(curModel.tables || []), positionedNode],
        joins: [...(curModel.joins || []), ...dedupedNewJoins],
      };
      setSelectedCanvasNodeId(positionedNode.id);
      await pushVisualModelUpdate(nextModel, true);
    },
    [callHost, pushVisualModelUpdate]
  );

  const handleToggleCanvasField = useCallback(
    (nodeId, colName, nextSelected) => {
      const curModel = visualModelRef.current;
      const tables = curModel.tables || [];
      const targetTbl = tables.find((t) => t.id === nodeId);
      if (!targetTbl) return;
      const tRef = targetTbl.alias || targetTbl.name || targetTbl.id;

      let nextProjections = Array.isArray(curModel.projections)
        ? [...curModel.projections]
        : [];

      // When starting from implicit `SELECT *` (`projections === []`) and unchecking one column,
      // materialize all other canvas columns explicitly first.
      if (nextProjections.length === 0 && !nextSelected) {
        const expanded = [];
        for (const tbl of tables) {
          const refPrefix = tbl.alias || tbl.name || tbl.id;
          for (const col of tbl.columns || []) {
            const cname = col.name || col;
            if (tbl.id === nodeId && cname === colName) continue;
            expanded.push({
              table: refPrefix,
              column: cname,
              expr: `${refPrefix}.${cname}`,
              alias: '',
              aggregate: '',
            });
          }
        }
        nextProjections = expanded;
      } else if (nextSelected) {
        const exists = nextProjections.some(
          (p) =>
            (p.table === nodeId || p.table === targetTbl.alias || p.table === targetTbl.name) &&
            p.column === colName
        );
        if (!exists) {
          nextProjections.push({
            table: tRef,
            column: colName,
            expr: `${tRef}.${colName}`,
            alias: '',
            aggregate: '',
          });
        }
      } else {
        nextProjections = nextProjections.filter((p) => {
          if (
            (p.table === nodeId || p.table === targetTbl.alias || p.table === targetTbl.name) &&
            p.column === colName
          ) {
            return false;
          }
          const cleanExpr = String(p.expr || p.expression || '')
            .replaceAll('"', '')
            .replaceAll('`', '')
            .trim();
          return cleanExpr !== `${tRef}.${colName}` && cleanExpr !== `${targetTbl.name}.${colName}`;
        });
      }

      pushVisualModelUpdate({...curModel, projections: nextProjections}, true);
    },
    [pushVisualModelUpdate]
  );

  const handleCreateCanvasJoin = useCallback(
    (sourceNodeId, sourceField, targetNodeId, targetField) => {
      if (!sourceNodeId || !targetNodeId || sourceNodeId === targetNodeId) return;
      const curModel = visualModelRef.current;
      const srcTbl = (curModel.tables || []).find((t) => t.id === sourceNodeId);
      const dstTbl = (curModel.tables || []).find((t) => t.id === targetNodeId);
      if (!srcTbl || !dstTbl) return;

      const exists = (curModel.joins || []).some(
        (j) =>
          (j.left_table === srcTbl.id || j.left_table === srcTbl.alias) &&
          j.left_column === sourceField &&
          (j.right_table === dstTbl.id || j.right_table === dstTbl.alias) &&
          j.right_column === targetField
      );
      if (exists) return;

      const newJoin = {
        id: `join_${Date.now()}`,
        join_type: 'INNER',
        left_table: srcTbl.id,
        left_column: sourceField,
        right_table: dstTbl.id,
        right_column: targetField,
        cardinality: '1:N',
      };
      pushVisualModelUpdate(
        {...curModel, joins: [...(curModel.joins || []), newJoin]},
        true
      );
    },
    [pushVisualModelUpdate]
  );

  const handleRemoveCanvasNode = useCallback(
    (nodeId) => {
      const curModel = visualModelRef.current;
      const targetTbl = (curModel.tables || []).find((t) => t.id === nodeId);
      if (!targetTbl) return;
      const matchKeys = new Set(
        [targetTbl.id, targetTbl.alias, targetTbl.name].filter(Boolean)
      );
      const nextTables = (curModel.tables || []).filter((t) => t.id !== nodeId);
      const nextJoins = (curModel.joins || []).filter(
        (j) => !matchKeys.has(j.left_table) && !matchKeys.has(j.right_table)
      );
      const nextProjections = (curModel.projections || []).filter((p) => {
        if (matchKeys.has(p.table)) return false;
        const expr = String(p.expr || p.expression || '');
        if (targetTbl.alias && expr.startsWith(`${targetTbl.alias}.`)) return false;
        return true;
      });
      if (selectedCanvasNodeId === nodeId) {
        setSelectedCanvasNodeId('');
      }
      pushVisualModelUpdate(
        {
          ...curModel,
          tables: nextTables,
          joins: nextJoins,
          projections: nextProjections,
        },
        true
      );
    },
    [pushVisualModelUpdate, selectedCanvasNodeId]
  );

  const activateVisualBuilder = useCallback(async () => {
    const curShell = shellRef.current;
    if (curShell && curShell.shellLeftDrawerOpen === false) {
      curShell.toggleLeftDrawer?.();
    }
    await syncSqlIntoVisualBuilder();
    openRightDrawerWith({panel: 'visual_inspector'});
  }, [openRightDrawerWith, syncSqlIntoVisualBuilder]);

  const switchSurfaceView = useCallback(async (nextView) => {
    setSurfaceView(nextView);
    if (nextView === SQL_SURFACE_VIEWS.VISUAL_BUILDER) {
      await activateVisualBuilder();
    }
  }, [activateVisualBuilder]);

  // Core SQL Execution (`statement`, `script`, `explain`) + Automatic Parameter Detection
  const dispatchExecution = useCallback(
    async (execSpec, boundParams = null) => {
      if (executionRef.current) return;
      const executionId = `${Date.now()}-${++executionSequence.current}`;
      executionRef.current = executionId;
      setCanCancel(true);
      setExecuting(true);
      setSurfaceError('');
      try {
        let resp = await callHost('execute', {
          execution_id: executionId,
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
          ...(execSpec.profileMode ? {profile_mode: true} : {}),
          ...(execSpec.analyzeMode ? {analyze_mode: true} : {}),
          ...(isMySQL && Object.keys(mysqlQueryAttrs).length > 0 && execSpec.mode !== 'explain'
            ? {mysql_query_attributes: mysqlQueryAttrs}
            : {}),
          ...(isFirebird && collectStatistics && execSpec.mode === 'statement'
            ? {statistics_mode: true}
            : {}),
          ...(historySensitive ? {history_sensitive: true} : {}),
        });
        const savedView = savedResultViewRef.current;
        const result = resp?.active_result;
        if (!resp?.last_execution_cancelled && savedView && result && savedView.statement === resp?.sql_view?.server_sql) {
          const names = new Set((result.columns || []).map((column) => column.name));
          try {
            resp = await callHost('query_view', {
              active_result_index: resp.active_result_index,
              sort: (savedView.sort || []).filter((item) => names.has(item.column)),
              filters: (savedView.filters || []).filter((item) => names.has(item.column)),
            });
          } catch (error) {
            setSurfaceError(error?.message || String(error));
          }
        }
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
            ok: !resp?.last_execution_had_error && !resp?.last_execution_cancelled,
          },
          ...prev.slice(0, 99),
        ]);

        // Auto-switch view per Surface 2 specification:
        if (resp?.last_execution_had_error || resp?.last_execution_cancelled) {
          setSurfaceView(SQL_SURFACE_VIEWS.MESSAGES);
        } else if (execSpec.mode === 'explain' || execSpec.profileMode || execSpec.analyzeMode) {
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
        executionRef.current = null;
        setCanCancel(false);
        setCancelPending(false);
        setExecuting(false);
      }
    },
    [
      applyHostState,
      autocommit,
      callHost,
      clientSqlDialect,
      collectStatistics,
      historySensitive,
      isFirebird,
      isMySQL,
      limitsDraft.maxRows,
      limitsDraft.pageSize,
      mysqlQueryAttrs,
      terminator,
    ]
  );

  const runSql = useCallback(
    async (mode = 'statement', skipParamPrompt = false, extraExecFlags = {}) => {
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
        ...extraExecFlags,
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
        } catch (error) {
          if (String(languageProfile || engineId).replace(/-sql$/, '') === 'mysql') {
            setSurfaceError(error?.message || String(error));
            setSurfaceView(SQL_SURFACE_VIEWS.MESSAGES);
            return;
          }
        }
      }
      await dispatchExecution(execSpec, null);
    },
    [callHost, cursorPos.col, cursorPos.line, dispatchExecution, engineId, languageProfile, selectionText, terminator]
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
  const conversionPairs = languageOptions.field_conversion_pairs;
  const conversions = useRecordConversions(rows, columns, layout.formFieldPrefs, conversionPairs, callHost);

  const acceptCurrentRow = useCallback(async () => {
    if (!isEditingRow || !rowDraft) return true;
    setExecuting(true);
    try {
      const op = isInsertDraft ? 'insert' : 'update';
      const baseRow = !isInsertDraft ? rows[editingRowIndex] : null;
      const changes = {};
      for (const col of columns) {
        if ((col.read_only || col.editable === false) && !isInsertDraft) continue;
        if (!isInsertDraft && JSON.stringify(rowDraft[col.name]) === JSON.stringify(baseRow?.values?.[col.name])) continue;
        if (!isValidJsonDraft(rowDraft[col.name], col)) {
          setSurfaceError(gettext('Enter valid JSON for %s.', col.name));
          return false;
        }
        const nextVal = await convertRecordField(
          callHost, conversionPairs, layout.formFieldPrefs, col, coerceEditedValue(rowDraft[col.name], col)
        );
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
  }, [applyHostState, callHost, conversionPairs, layout.formFieldPrefs, columns, editingRowIndex, isEditingRow, isInsertDraft, rowDraft, rows]);

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
      if (hostData?.prepared_transaction_id) {
        try {
          applyHostState(await callHost('read_window'));
        } catch {
          // Keep the original transaction error.
        }
      }
      setSurfaceError(err?.message || String(err));
    } finally {
      setExecuting(false);
    }
  }, [acceptCurrentRow, applyHostState, callHost, hostData?.prepared_transaction_id, isEditingRow]);

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
      if (hostData?.prepared_transaction_id) {
        try {
          applyHostState(await callHost('read_window'));
        } catch {
          // Keep the original transaction error.
        }
      }
      setSurfaceError(err?.message || String(err));
    } finally {
      setExecuting(false);
    }
  }, [applyHostState, callHost, hostData?.prepared_transaction_id]);

  const activeResultIdxKey = String(hostData?.active_result_index ?? 0);
  const activeBookmarks = useMemo(
    () => bookmarksByResult[activeResultIdxKey] || new Set(),
    [bookmarksByResult, activeResultIdxKey]
  );

  const navigateResultPage = useCallback(
    async (nextOffset, selectLocalIdx = 0, focusTarget = null) => {
      if (isEditingRow) {
        const ok = await acceptCurrentRow();
        if (!ok) return;
      }
      const wSize = hostData?.window_size || limitsDraft.pageSize || 200;
      const clampedOffset = Math.max(0, nextOffset);
      setExecuting(true);
      try {
        const resp = await callHost('read_window', {
          window_offset: clampedOffset,
          window_size: wSize,
        });
        applyHostState(resp);
        const pageLen = (resp?.active_result?.rows || resp?.rows || []).length;
        const resolvedIdx =
          selectLocalIdx === 'last'
            ? Math.max(0, pageLen - 1)
            : Math.max(0, Math.min(pageLen > 0 ? pageLen - 1 : 0, selectLocalIdx));
        setActiveRowIndex(resolvedIdx);
        if (focusTarget) {
          pendingCellFocusRef.current = {
            ...focusTarget,
            rowIndex: resolvedIdx,
          };
        }
      } catch (err) {
        setSurfaceError(err?.message || String(err));
      } finally {
        setExecuting(false);
      }
    },
    [acceptCurrentRow, applyHostState, callHost, hostData?.window_size, isEditingRow, limitsDraft.pageSize]
  );

  const selectSqlRowAtIndex = useCallback(
    async (nextIdx, nextColName) => {
      if (rows.length === 0) return;
      const clamped = Math.max(0, Math.min(rows.length - 1, nextIdx));
      if (isEditingRow && editingRowIndex !== null && clamped !== editingRowIndex) {
        const ok = await acceptCurrentRow();
        if (!ok) return;
      }
      setActiveRowIndex(clamped);
      if (nextColName) {
        setActiveColName(nextColName);
      }
    },
    [acceptCurrentRow, editingRowIndex, isEditingRow, rows.length]
  );

  const toggleSqlBookmark = useCallback(
    (localIdx = activeRowIndex) => {
      if (rows.length === 0) return;
      const clamped = Math.max(0, Math.min(rows.length - 1, localIdx));
      const globalIdx = (hostData?.window_offset || 0) + clamped;
      setBookmarksByResult((prev) => {
        const nextSet = new Set(prev[activeResultIdxKey] || []);
        if (nextSet.has(globalIdx)) nextSet.delete(globalIdx);
        else nextSet.add(globalIdx);
        return {...prev, [activeResultIdxKey]: nextSet};
      });
    },
    [activeResultIdxKey, activeRowIndex, hostData?.window_offset, rows.length]
  );

  const jumpSqlBookmark = useCallback(
    async (direction = 1) => {
      if (activeBookmarks.size === 0) return;
      const sorted = Array.from(activeBookmarks).sort((a, b) => a - b);
      const winOff = hostData?.window_offset || 0;
      const winSz = hostData?.window_size || limitsDraft.pageSize || 200;
      const curGlobal = winOff + activeRowIndex;
      let targetGlobal;
      if (direction > 0) {
        targetGlobal = sorted.find((g) => g > curGlobal) ?? sorted[0];
      } else {
        const earlier = sorted.filter((g) => g < curGlobal);
        targetGlobal = earlier.length > 0 ? earlier[earlier.length - 1] : sorted[sorted.length - 1];
      }
      if (targetGlobal >= winOff && targetGlobal < winOff + rows.length) {
        const localIdx = targetGlobal - winOff;
        pendingCellFocusRef.current = {
          kind: layout.displayMode === DISPLAY_MODES.GRID ? 'grid' : 'form',
          rowIndex: localIdx,
          colName: activeColName || columns[0]?.name || '',
        };
        await selectSqlRowAtIndex(localIdx, activeColName);
      } else {
        const pageStart = Math.floor(targetGlobal / winSz) * winSz;
        const localIdx = targetGlobal - pageStart;
        await navigateResultPage(pageStart, localIdx, {
          kind: layout.displayMode === DISPLAY_MODES.GRID ? 'grid' : 'form',
          colName: activeColName || columns[0]?.name || '',
        });
      }
    },
    [
      activeBookmarks,
      activeColName,
      activeRowIndex,
      columns,
      hostData?.window_offset,
      hostData?.window_size,
      layout.displayMode,
      limitsDraft.pageSize,
      navigateResultPage,
      rows.length,
      selectSqlRowAtIndex,
    ]
  );

  const handleSqlKeyboardCellNavigate = useCallback(
    async (targetRowIdx, targetColName, action = 'focus', kind = 'grid') => {
      const winOff = hostData?.window_offset || 0;
      const winSz = hostData?.window_size || limitsDraft.pageSize || 200;
      const totalRows = hostData?.total_view_rows ?? rows.length;
      const colToKeep = targetColName || activeColName || columns[0]?.name || '';

      if (action === 'first_record') {
        if (winOff > 0) {
          await navigateResultPage(0, 0, {kind, colName: colToKeep});
        } else {
          pendingCellFocusRef.current = {kind, rowIndex: 0, colName: colToKeep};
          await selectSqlRowAtIndex(0, colToKeep);
        }
        return;
      }
      if (action === 'last_record') {
        const lastPageOff = Math.max(0, Math.floor(Math.max(0, totalRows - 1) / winSz) * winSz);
        if (winOff !== lastPageOff && totalRows > rows.length) {
          await navigateResultPage(lastPageOff, 'last', {kind, colName: colToKeep});
        } else {
          const lastIdx = Math.max(0, rows.length - 1);
          pendingCellFocusRef.current = {kind, rowIndex: lastIdx, colName: colToKeep};
          await selectSqlRowAtIndex(lastIdx, colToKeep);
        }
        return;
      }
      if (action === 'page_up' || action === 'prev_page') {
        if (winOff > 0) {
          await navigateResultPage(Math.max(0, winOff - winSz), 0, {kind, colName: colToKeep});
        } else {
          pendingCellFocusRef.current = {kind, rowIndex: 0, colName: colToKeep};
          await selectSqlRowAtIndex(0, colToKeep);
        }
        return;
      }
      if (action === 'page_down' || action === 'next_page') {
        if (winOff + winSz < totalRows) {
          await navigateResultPage(winOff + winSz, 0, {kind, colName: colToKeep});
        } else {
          const lastIdx = Math.max(0, rows.length - 1);
          pendingCellFocusRef.current = {kind, rowIndex: lastIdx, colName: colToKeep};
          await selectSqlRowAtIndex(lastIdx, colToKeep);
        }
        return;
      }
      if (action === 'prev_row_boundary') {
        if (activeRowIndex > 0) {
          const prevIdx = activeRowIndex - 1;
          pendingCellFocusRef.current = {kind, rowIndex: prevIdx, colName: colToKeep};
          await selectSqlRowAtIndex(prevIdx, colToKeep);
        } else if (winOff > 0) {
          await navigateResultPage(Math.max(0, winOff - winSz), 'last', {kind, colName: colToKeep});
        }
        return;
      }
      if (action === 'next_row_boundary') {
        if (activeRowIndex < rows.length - 1) {
          const nextIdx = activeRowIndex + 1;
          pendingCellFocusRef.current = {kind, rowIndex: nextIdx, colName: colToKeep};
          await selectSqlRowAtIndex(nextIdx, colToKeep);
        } else if (winOff + winSz < totalRows) {
          await navigateResultPage(winOff + winSz, 0, {kind, colName: colToKeep});
        }
        return;
      }

      pendingCellFocusRef.current = {kind, rowIndex: targetRowIdx, colName: colToKeep};
      await selectSqlRowAtIndex(targetRowIdx, colToKeep);
    },
    [
      activeColName,
      activeRowIndex,
      columns,
      hostData?.total_view_rows,
      hostData?.window_offset,
      hostData?.window_size,
      limitsDraft.pageSize,
      navigateResultPage,
      rows.length,
      selectSqlRowAtIndex,
    ]
  );

  // Restore DOM keyboard focus onto target grid/form cell after React updates `activeRowIndex` / `activeColName`
  useEffect(() => {
    const req = pendingCellFocusRef.current;
    if (!req || !workAreaRef.current) return;
    pendingCellFocusRef.current = null;
    const attr = req.kind === 'form' ? 'data-form-nav-cell' : 'data-grid-nav-cell';
    const escCol = String(req.colName || '').replaceAll('"', '\\"');
    const focusedArea = focusedDisplayAreaRef.current;
    const focusRoot = workAreaRef.current.contains(focusedArea) ? focusedArea : workAreaRef.current;
    const selector = `[${attr}="${req.rowIndex}:${escCol}"]`;
    const el = focusRoot.querySelector(selector) || workAreaRef.current.querySelector(selector);
    if (el && typeof el.focus === 'function') {
      el.focus({preventScroll: false});
      el.scrollIntoView?.({block: 'nearest', inline: 'nearest'});
    }
  }, [activeRowIndex, activeColName, rows, isEditingRow]);

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

  const handleFormatSql = useCallback(async () => {
    const currentSource = () => editorRef.current?.getValue?.() ?? sqlTextRef.current;
    const source = currentSource();
    if (executing || !source.trim()) return;
    const family = languageOptions.syntax_family;
    const request = {sql_source: source, client_sql_dialect: clientSqlDialect};
    setExecuting(true);
    try {
      let formatted;
      let script = false;
      if (family === 'firebird') {
        const signature = (text) => firebirdFragments(text).map(({source: entry, kind}) => [
          kind, firebirdTokens(entry).map(({kind: tokenKind, text: value}) => [tokenKind, value]),
        ]);
        const entries = signature(source);
        script = entries.length > 1 || entries.some(([kind]) => kind !== 'sql');
        formatted = formatFirebird(source);
        if (JSON.stringify(entries) !== JSON.stringify(signature(formatted))) {
          throw new Error(gettext('Formatting would change Firebird statement boundaries.'));
        }
      } else {
        if (/^\s*DELIMITER\b/im.test(source)) {
          throw new Error(gettext('Format statements separately when a script uses DELIMITER.'));
        }
        const {context} = await callHost('format_context', request);
        if (!context || context.engine !== family || context.observation?.available === false) {
          throw new Error(gettext('The native SQL formatting context is unavailable.'));
        }
        formatted = formatNative(source, context);
      }
      if (formatted === source || currentSource() !== source) return;
      const checked = await callHost('validate_format', {...request, sql_source: formatted, script});
      if (checked?.grammar_valid !== true) {
        throw new Error(gettext('Native validation could not confirm the formatted SQL.'));
      }
      if (currentSource() === source) {
        setSqlText(formatted);
        editorRef.current?.setValue?.(formatted);
        setSurfaceError('');
      }
    } catch (error) {
      setSurfaceError(gettext('SQL was preserved. %s', error?.message || String(error)));
      setSurfaceView(SQL_SURFACE_VIEWS.MESSAGES);
    } finally {
      setExecuting(false);
    }
  }, [callHost, clientSqlDialect, executing, languageOptions.syntax_family]);

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
    (kind = 'quick_query', fromSelection = false, effectiveQuery = null) => {
      saveEffectiveQueryRef.current = effectiveQuery;
      setSaveKind(kind);
      setSaveSnippetId('');
      setSaveUseSelection(Boolean(fromSelection && selectionText.trim()));
      setSaveTitle(
        kind === 'quick_query'
          ? (effectiveQuery ? gettext('Quick Query') : activeQuickQueryName || targetResource?.display_name || 'Quick Query')
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
    const effectiveQuery = saveEffectiveQueryRef.current;
    const chosenSql = effectiveQuery?.sql ?? (saveUseSelection && selectionText.trim() ? selectionText : fullSql);

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
    const paramDefaults = effectiveQuery?.parameters ?? Object.entries(paramDrafts).map(([name, d]) => ({
      name,
      type: d.type,
      value: d.value,
      isNull: d.isNull,
    }));
    const res = await callHost('save_quick_query', {
      quick_query: {
        ...(activeQuickQueryId && !effectiveQuery ? {query_id: activeQuickQueryId} : {}),
        name: saveTitle || 'Quick Query',
        description: saveDescription,
        sql_text: chosenSql,
        terminator: effectiveQuery ? ';' : terminator,
        parameters: paramDefaults,
        display_layout: {
          ...layout,
          upperArea: upperView,
          lowerArea: lowerView,
          upperPresentation: upperMode,
          lowerPresentation: lowerMode,
          surfaceContent: surfaceView,
          effectiveSqlDialect: effectiveQuery?.client_sql_dialect ?? undefined,
          resultView: !effectiveQuery && activeResult && hostData?.sql_view?.server_sql
            ? {statement: hostData.sql_view.server_sql, sort: activeResult.sort || [],
              filters: activeResult.filters || []}
            : null,
        },
      },
    });
    if (res?.saved_quick_query) {
      const savedName = res.saved_quick_query.name || '';
      setActiveQuickQueryId(res.saved_quick_query.query_id);
      setActiveQuickQueryName(savedName);
      if (savedName) {
        const curShell = shellRef.current;
        const curInst = curShell?.instances?.find((i) => i.instanceId === instId);
        if (curShell && (!curInst || !curInst.customTitle)) {
          curShell.updateInstance?.(instId, {title: `sql: ${savedName}`});
        }
      }
    }
    if (Array.isArray(res?.quick_queries)) {
      setQuickQueries(res.quick_queries);
    }
    setSaveModalOpen(false);
  }, [
    activeQuickQueryId,
    activeResult,
    hostData?.sql_view?.server_sql,
    callHost,
    databaseTargetId,
    layout,
    lowerMode,
    lowerView,
    surfaceView,
    upperMode,
    upperView,
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
        if (qq.name) {
          const curShell = shellRef.current;
          const curInst = curShell?.instances?.find((i) => i.instanceId === instId);
          if (curShell && (!curInst || !curInst.customTitle)) {
            curShell.updateInstance?.(instId, {title: `sql: ${qq.name}`});
          }
        }
        setSqlText(qq.sql_text || '');
        editorRef.current?.setValue?.(qq.sql_text || '');
        if (qq.terminator) setTerminator(qq.terminator);
        restoreNamedLayout(qq.display_layout);
        setParamDrafts(restoreQuickQueryParameters(qq.parameters));
      }
      if (res?.state) applyHostState(res.state);
      setQuickQueryModalOpen(false);
    },
    [applyHostState, callHost, restoreNamedLayout]
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
  const prepareStatement = async () => {
    setExecuting(true);
    setSurfaceError('');
    try {
      const result = await callHost('prepare_statement', {
        sql_source: editorRef.current?.getValue?.() ?? sqlTextRef.current,
        selection_text: selectionText,
        client_sql_dialect: clientSqlDialect,
      });
      if (!result?.prepared_statement) throw new Error(gettext('No preparation receipt returned.'));
      setPreparedStatement(result.prepared_statement);
    } catch (error) {
      setSurfaceError(error?.message || String(error));
    } finally {
      setExecuting(false);
    }
  };

  const handlersRef = useRef({});
  handlersRef.current = {
    selectDisplayArea: (area, view) => {
      const split = surfaceView === SQL_SURFACE_VIEWS.SQL_DATA;
      if (area === 'first' && !split) {
        switchSurfaceView(view);
        return;
      }
      if (view === 'off') {
        if (split) setSurfaceView(upperView);
        return;
      }
      if (area === 'first') {
        setUpperView(view);
      } else {
        if (!split) setUpperView(surfaceView);
        setLowerView(view);
        setSurfaceView(SQL_SURFACE_VIEWS.SQL_DATA);
      }
      if (view === SQL_SURFACE_VIEWS.VISUAL_BUILDER) activateVisualBuilder();
    },
    saveObjectLayout,
    prepareStatement,
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
      setSurfaceError('');
      try {
        applyHostState(await callHost('set_options', {autocommit: nextVal}));
      } catch (error) {
        setSurfaceError(error?.message || String(error));
      }
    },
    selectResultIndex: async (idx) => {
      const resp = await callHost('select_result', {result_index: idx});
      applyHostState(resp);
    },
    cancelExecution: async () => {
      const executionId = executionRef.current;
      if (!executionId) return;
      setCancelPending(true);
      try {
        const response = await callHost('cancel', {execution_id: executionId});
        if (response?.cancel_status === 'idle' && executionRef.current === executionId) {
          setCancelPending(false);
        }
      } catch (error) {
        if (executionRef.current === executionId) {
          setSurfaceError(error?.message || String(error));
          setSurfaceView(SQL_SURFACE_VIEWS.MESSAGES);
          setCancelPending(false);
        }
      }
    },
    triggerFileOpen: () => fileInputRef.current?.click?.(),
    setLayout,
    pushVisualModelUpdate,
    visualModel,
    isEditingRow,
    rows,
    gridColumns,
    activeRowIndex,
    activeColName,
    navigateResultPage,
    selectSqlRowAtIndex,
    toggleSqlBookmark,
    jumpSqlBookmark,
    handleSqlKeyboardCellNavigate,
  };

  // Render Right Drawer (`Area 3b`) Content
  const renderRightDrawerContent = useCallback(() => {
    const ds = drawerStateRef.current;

    if (ds.panel === 'visual_inspector') {
      const mergedCatalogMap = new Map();
      for (const item of visualCatalogObjects || []) {
        const key = item.resource_id || `${item.resource_kind}:${item.display_name || item.name}`;
        mergedCatalogMap.set(key, item);
      }
      for (const r of resources || []) {
        if (
          ![
            'table',
            'view',
            'materialized-view',
            'foreign-table',
            'partitioned-table',
            'procedure',
            'function',
            'routine',
          ].includes(r.resource_kind)
        ) {
          continue;
        }
        const key = r.resource_id || `${r.resource_kind}:${r.display_name || r.name}`;
        if (!mergedCatalogMap.has(key)) {
          mergedCatalogMap.set(key, r);
        }
      }
      const catalogItems = Array.from(mergedCatalogMap.values());
      const filteredCatalog = catalogItems.filter((t) => {
        const rk = String(t.resource_kind || 'table').toLowerCase();
        if (vbKindFilter === 'table' && !['table', 'foreign-table', 'partitioned-table'].includes(rk)) {
          return false;
        }
        if (vbKindFilter === 'view' && !rk.includes('view')) {
          return false;
        }
        if (vbKindFilter === 'procedure' && !['procedure', 'function', 'routine', 'table-function'].includes(rk)) {
          return false;
        }
        if (!vbTableSearch.trim()) return true;
        return String(t.display_name || t.name || '')
          .toLowerCase()
          .includes(vbTableSearch.trim().toLowerCase());
      });
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
              ['tables', gettext('Sources')],
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
                label={gettext('Drag or Add Table / View / Procedure')}
                placeholder={gettext('Filter tables, views, procedures…')}
                value={vbTableSearch}
                onChange={(e) => setVbTableSearch(e.target.value)}
              />
              <div style={{display: 'flex', gap: 4, flexWrap: 'wrap'}}>
                {[
                  ['all', gettext('All')],
                  ['table', gettext('Tables')],
                  ['view', gettext('Views')],
                  ['procedure', gettext('Procedures')],
                ].map(([kid, klbl]) => (
                  <button
                    key={kid}
                    type="button"
                    data-cdeadmin-qa-key={`vb-kind-filter-${kid}`}
                    onClick={() => setVbKindFilter(kid)}
                    style={{
                      padding: '2px 8px',
                      borderRadius: 999,
                      fontSize: '0.71rem',
                      cursor: 'pointer',
                      border: '1px solid var(--sr-border-default, #cbd5e1)',
                      background:
                        vbKindFilter === kid
                          ? 'var(--sr-accent-primary, #2563eb)'
                          : 'transparent',
                      color: vbKindFilter === kid ? '#ffffff' : 'inherit',
                    }}
                  >
                    {klbl}
                  </button>
                ))}
              </div>
              <div style={{maxHeight: 190, overflow: 'auto', display: 'grid', gap: 4}}>
                {filteredCatalog.slice(0, 60).map((res) => {
                  const tname = res.display_name || res.name;
                  const rk = String(res.resource_kind || 'table').toLowerCase();
                  const isProc = ['procedure', 'function', 'routine', 'table-function'].includes(rk);
                  const isView = rk.includes('view');
                  const badgeText = isProc ? 'PROC' : isView ? 'VIEW' : 'TABLE';
                  const badgeBg = isProc
                    ? 'rgba(124, 58, 237, 0.14)'
                    : isView
                      ? 'rgba(13, 148, 136, 0.14)'
                      : 'rgba(37, 99, 235, 0.12)';
                  return (
                    <div
                      key={res.resource_id || `${rk}:${tname}`}
                      draggable
                      title={gettext('Drag onto Visual Builder canvas or click + Add')}
                      onDragStart={(e) => {
                        const dragPayload = {
                          resource_id: res.resource_id || '',
                          resource_kind: rk,
                          display_name: tname,
                          schema_name: res.schema_name || '',
                          columns: res.columns,
                          input_parameters: res.input_parameters,
                        };
                        e.dataTransfer.effectAllowed = 'copy';
                        try {
                          e.dataTransfer.setData(
                            'application/x-scratchrobin-catalog-object',
                            JSON.stringify(dragPayload)
                          );
                        } catch {
                          // Ignore custom MIME restriction
                        }
                        e.dataTransfer.setData(
                          'text',
                          JSON.stringify({
                            text: tname,
                            nodeType: rk,
                            scratchrobinCatalogObject: dragPayload,
                          })
                        );
                      }}
                      onDoubleClick={() => addCatalogObjectToCanvas(res)}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: 6,
                        padding: '4px 8px',
                        borderRadius: 6,
                        border: '1px solid var(--sr-border-subtle)',
                        fontSize: '0.78rem',
                        cursor: 'grab',
                      }}
                    >
                      <span style={{display: 'flex', alignItems: 'center', gap: 6, minWidth: 0}}>
                        <span
                          style={{
                            padding: '1px 5px',
                            borderRadius: 4,
                            fontSize: '0.66rem',
                            fontWeight: 700,
                            background: badgeBg,
                          }}
                        >
                          {badgeText}
                        </span>
                        <span style={{overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>
                          {tname}
                        </span>
                      </span>
                      <Button
                        size="small"
                        data-cdeadmin-qa-key={`vb-add-table-${tname}`}
                        onClick={() => addCatalogObjectToCanvas(res)}
                      >
                        + {gettext('Add')}
                      </Button>
                    </div>
                  );
                })}
              </div>

              <strong>{gettext('Canvas Sources (%s)', visualModel.tables.length)}</strong>
              {visualModel.tables.map((t, idx) => {
                const isProc = ['procedure', 'function', 'routine', 'table-function'].includes(
                  String(t.resource_kind || '').toLowerCase()
                );
                const inParams = Array.isArray(t.input_parameters) ? t.input_parameters : [];
                return (
                  <div
                    key={t.id || idx}
                    style={{
                      display: 'grid',
                      gap: 6,
                      padding: '6px 8px',
                      borderRadius: 6,
                      background:
                        selectedCanvasNodeId === t.id
                          ? 'var(--sr-accent-muted, rgba(37,99,235,0.12))'
                          : 'transparent',
                      border: '1px solid var(--sr-border-subtle)',
                      fontSize: '0.78rem',
                    }}
                  >
                    <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                      <span
                        style={{cursor: 'pointer'}}
                        onClick={() => setSelectedCanvasNodeId(t.id)}
                      >
                        <strong>{t.name}</strong> ({t.alias})
                        {isProc && (
                          <span style={{marginLeft: 6, fontSize: '0.68rem', opacity: 0.8}}>
                            [PROC]
                          </span>
                        )}
                      </span>
                      <Button
                        size="small"
                        onClick={() => handleRemoveCanvasNode(t.id)}
                      >
                        ×
                      </Button>
                    </div>
                    {isProc && inParams.length > 0 && (
                      <div
                        data-cdeadmin-qa-key={`vb-proc-params-${t.id}`}
                        style={{display: 'grid', gap: 4, paddingTop: 2}}
                      >
                        <div style={{fontSize: '0.71rem', opacity: 0.8}}>
                          {gettext('Procedure Input Arguments:')}
                        </div>
                        {inParams.map((param, pIdx) => (
                          <div
                            key={param.name || pIdx}
                            style={{
                              display: 'grid',
                              gridTemplateColumns: '92px 1fr',
                              gap: 4,
                              alignItems: 'center',
                            }}
                          >
                            <span style={{fontSize: '0.72rem', fontWeight: 600}}>
                              {param.name}
                            </span>
                            <input
                              className="sr-input"
                              aria-label={`Argument ${param.name}`}
                              value={param.expr ?? `:${param.name}`}
                              onChange={(ev) => {
                                const nextVal = ev.target.value;
                                const nextTables = visualModel.tables.map((tblItem, ti) =>
                                  ti === idx
                                    ? {
                                      ...tblItem,
                                      input_parameters: inParams.map((pi, k) =>
                                        k === pIdx ? {...pi, expr: nextVal} : pi
                                      ),
                                    }
                                    : tblItem
                                );
                                pushVisualModelUpdate({...visualModel, tables: nextTables}, true);
                              }}
                              style={{minHeight: 24, padding: '2px 6px', fontSize: '0.74rem'}}
                            />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
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
          sx={{p: 1.5, display: 'grid', gap: 1.5}}
        >
          <SqlPersistentHistoryPanel
            post={post}
            databaseTargetId={databaseTargetId}
            clientSqlDialect={clientSqlDialect}
            supportsDialectScope={isFirebird}
            onLoadSql={(src) => insertSnippetText(src, true)}
            disabled={executing}
          />
          <strong>{gettext('Current Session SQL History')}</strong>
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
              setRowDraft((prev) => ({
                ...(prev || targetRow?.values || {}),
                [colName]: e.target.value,
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
    addCatalogObjectToCanvas,
    applyHostState,
    beginEditRow,
    callHost,
    columns,
    currentRow,
    editingRowIndex,
    fanoutWarnings,
    handleApplyFilters,
    handleRemoveCanvasNode,
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
    vbKindFilter,
    localeRevision,
    vbTableSearch,
    visualCatalogObjects,
    visualFidelity,
    visualLossNotes,
    visualModel,
  ]);

  const renderRightDrawerRef = useRef(renderRightDrawerContent);
  renderRightDrawerRef.current = renderRightDrawerContent;
  const drawerListenersRef = useRef(new Set());
  const subscribeDrawer = useCallback((listener) => {
    drawerListenersRef.current.add(listener);
    return () => {
      drawerListenersRef.current.delete(listener);
    };
  }, []);
  useEffect(() => {
    drawerListenersRef.current.forEach((fn) => fn());
  }, [renderRightDrawerContent]);
  const stableRenderRightDrawer = useCallback(
    () => <LiveDrawerView subscribe={subscribeDrawer} renderRef={renderRightDrawerRef} />,
    [subscribeDrawer]
  );

  // Compact Status Bar (`Area 4` / `3d`)
  const statusSummaryText = useMemo(() => {
    const parts = [];
    if (endpointLabel) parts.push(endpointLabel);
    parts.push(
      autocommit
        ? gettext('Tx: Auto-Commit')
        : hasUncommitted
          ? hostData?.transaction_prepare_state === 'prepared'
            ? gettext('Tx: Prepared')
            : gettext('Tx: Uncommitted (%s staged)', hostData?.staged_count || 0)
          : gettext('Tx: Idle')
    );
    if (hostData?.prepared_transaction_id) parts.push(hostData.prepared_transaction_id);
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
    parts.push(gettext('Ln %s, Col %s', cursorPos.line, cursorPos.col));
    return parts.join(' · ');
  }, [
    localeRevision,
    activeResult?.total_view_rows,
    autocommit,
    cursorPos.col,
    cursorPos.line,
    endpointLabel,
    hasUncommitted,
    hostData?.active_result_index,
    hostData?.object_layout_key,
    hostData?.prepared_transaction_id,
    hostData?.result_count,
    hostData?.staged_count,
    hostData?.transaction_prepare_state,
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
    const actionHints = sqlEditorActionHints();

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
        defaultHint: hint || actionHints[suffix] || text,
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
      'action.section_indexes',
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
        hint: gettext('Execute selection or statement at cursor'),
      }
    );
    const execScriptId = reg(
      'exec_script',
      'action.terminal',
      gettext('Execute Script'),
      () => handlersRef.current.runSql('script'),
      {
        shortcut: 'F5',
        status: executing ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED,
        hint: gettext('Execute full script with active terminator / SET TERM'),
      }
    );
    const explainId = reg(
      'explain',
      'action.explain',
      gettext('Explain Plan'),
      () => handlersRef.current.runSql('explain'),
      {status: executing ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED}
    );
    const prepareId = languageOptions.native_statement_prepare && reg(
      'prepare_statement',
      'action.prepare_statement',
      gettext('Prepare Statement'),
      () => handlersRef.current.prepareStatement(),
      {status: executing ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED}
    );
    const cancelId = reg(
      'cancel',
      'action.stop',
      gettext('Cancel'),
      () => handlersRef.current.cancelExecution(),
      {status: canCancel && !cancelPending ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED}
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
    const startTransactionId = languageOptions.native_transaction_start && reg(
      'start_transaction',
      'action.transaction',
      gettext('Start Transaction…'),
      () => {
        setTransactionStartError('');
        const fields = transactionStartOptions(languageOptions.syntax_family);
        setTransactionOptions(Object.fromEntries(fields.map(([key, , values]) => [
          key, key === 'isolation' && ['mysql', 'mariadb'].includes(languageOptions.syntax_family)
            ? 'repeatable_read' : values[0][0],
        ])));
        setStartTransactionOpen(true);
      },
      {status: executing || autocommit || hasUncommitted ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED}
    );
    const prepareTransactionId = languageOptions.native_transaction_prepare && reg(
      'prepare_transaction',
      'action.prepare_transaction',
      gettext('Prepare Transaction…'),
      () => {
        setTransactionStartError('');
        setPrepareTransactionOpen(true);
      },
      {status: executing || autocommit || !hostData?.session_id || isEditingRow ||
        hostData?.staged_count > 0 || hostData?.transaction_prepare_state ||
        (['mysql', 'mariadb'].includes(languageOptions.syntax_family) && hostData?.xa_state !== 'active')
        ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED}
    );
    const recoveryId = languageOptions.syntax_family === 'postgresql' &&
      languageOptions.native_transaction_prepare && reg(
        'recover_prepared_transaction',
        'action.prepare_transaction',
        gettext('Recover Prepared Transaction…'),
        () => {
          setTransactionStartError('');
          setRecovery({transactions: [], gid: ''});
          setExecuting(true);
          callHost('recover_prepared_transaction').then((response) => {
            setRecovery({transactions: response.transactions || [], gid: ''});
          }).catch((error) => setTransactionStartError(error?.message || String(error)))
            .finally(() => setExecuting(false));
        },
        {status: executing ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED}
      );
    const commitId = reg(
      'commit',
      'action.commit',
      gettext('Commit'),
      () => handlersRef.current.handleCommit(),
      {status: hostData?.prepared_transaction_id && hostData?.transaction_prepare_state === 'unknown'
        ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED}
    );
    const rollbackId = reg(
      'rollback',
      'action.rollback',
      gettext('Rollback'),
      () => handlersRef.current.handleRollback(),
      {status: hostData?.prepared_transaction_id && hostData?.transaction_prepare_state === 'unknown'
        ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED}
    );
    const autocommitId = reg(
      'autocommit',
      'action.check',
      gettext('Auto-Commit'),
      () => handlersRef.current.setAutocommit(!autocommit),
      {checked: autocommit, status: executing || hostData?.transaction_prepare_state || hostData?.xa_state
        ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED}
    );

    // Record & Bookmark Navigation Group (|< << < > >> >| ! !< !>) — Surface 1 parity!
    const winOff = hostData?.window_offset || 0;
    const winSz = hostData?.window_size || limitsDraft.pageSize || 200;
    const totalRows = hostData?.total_view_rows ?? rows.length;
    const curGlobalRow = winOff + activeRowIndex;
    const isCurrentBookmarked = rows.length > 0 && activeBookmarks.has(curGlobalRow);
    const hasBookmarks = activeBookmarks.size > 0;
    const navKind = layout.displayMode === DISPLAY_MODES.GRID ? 'grid' : 'form';

    const navFirstId = reg(
      'nav_first',
      'action.nav_first',
      gettext('First Record (|<)'),
      () =>
        handlersRef.current.handleSqlKeyboardCellNavigate(
          0,
          handlersRef.current.activeColName,
          'first_record',
          navKind
        ),
      {status: winOff > 0 || activeRowIndex > 0 ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED}
    );
    const navPrevPageId = reg(
      'nav_prev_page',
      'action.nav_prev_page',
      gettext('Previous Page (<<)'),
      () =>
        handlersRef.current.handleSqlKeyboardCellNavigate(
          0,
          handlersRef.current.activeColName,
          'page_up',
          navKind
        ),
      {status: winOff > 0 || activeRowIndex > 0 ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED}
    );
    const navPrevRowId = reg(
      'nav_prev_row',
      'action.nav_prev_row',
      gettext('Previous Row (<)'),
      () =>
        handlersRef.current.handleSqlKeyboardCellNavigate(
          Math.max(0, handlersRef.current.activeRowIndex - 1),
          handlersRef.current.activeColName,
          'prev_row_boundary',
          navKind
        ),
      {status: winOff > 0 || activeRowIndex > 0 ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED}
    );
    const navNextRowId = reg(
      'nav_next_row',
      'action.nav_next_row',
      gettext('Next Row (>)'),
      () =>
        handlersRef.current.handleSqlKeyboardCellNavigate(
          handlersRef.current.activeRowIndex + 1,
          handlersRef.current.activeColName,
          'next_row_boundary',
          navKind
        ),
      {
        status:
          activeRowIndex < rows.length - 1 || winOff + winSz < totalRows
            ? T_ACTION_STATUS.ENABLED
            : T_ACTION_STATUS.DISABLED,
      }
    );
    const navNextPageId = reg(
      'nav_next_page',
      'action.nav_next_page',
      gettext('Next Page (>>)'),
      () =>
        handlersRef.current.handleSqlKeyboardCellNavigate(
          rows.length - 1,
          handlersRef.current.activeColName,
          'page_down',
          navKind
        ),
      {
        status:
          winOff + winSz < totalRows || activeRowIndex < rows.length - 1
            ? T_ACTION_STATUS.ENABLED
            : T_ACTION_STATUS.DISABLED,
      }
    );
    const navLastId = reg(
      'nav_last',
      'action.nav_last',
      gettext('Last Record (>|)'),
      () =>
        handlersRef.current.handleSqlKeyboardCellNavigate(
          rows.length - 1,
          handlersRef.current.activeColName,
          'last_record',
          navKind
        ),
      {
        status:
          totalRows > 0 && (winOff + winSz < totalRows || activeRowIndex < rows.length - 1)
            ? T_ACTION_STATUS.ENABLED
            : T_ACTION_STATUS.DISABLED,
      }
    );
    const bookmarkToggleId = reg(
      'bookmark_toggle',
      'action.bookmark_toggle',
      gettext('Bookmark Record (!)'),
      () => handlersRef.current.toggleSqlBookmark(),
      {
        status: rows.length > 0 ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
        checked: isCurrentBookmarked,
        shortcut: 'Ctrl+B',
      }
    );
    const bookmarkPrevId = reg(
      'bookmark_prev',
      'action.bookmark_prev',
      gettext('Previous Bookmark (!<)'),
      () => handlersRef.current.jumpSqlBookmark(-1),
      {status: hasBookmarks ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED}
    );
    const bookmarkNextId = reg(
      'bookmark_next',
      'action.bookmark_next',
      gettext('Next Bookmark (!>)'),
      () => handlersRef.current.jumpSqlBookmark(1),
      {status: hasBookmarks ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED}
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
      {
        status: isEditableResult || isEditingRow ? T_ACTION_STATUS.ENABLED : T_ACTION_STATUS.DISABLED,
        hint: isEditingRow ? gettext('Accept changes to the current row') : gettext('Edit the current result row'),
      }
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
      'action.duplicate',
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
    const quickQueriesId = reg('quick_queries', 'action.savepoint', gettext('Quick Queries…'), () =>
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
    const applyTemplateId = reg(
      'apply_layout_template',
      'action.layout_grid',
      gettext('Apply Layout Template…'),
      () => setTemplatePickerOpen(true),
      {hint: gettext('Choose a shared layout for the query results')}
    );
    const formatSqlId = reg('format_sql', 'action.align', gettext('Format SQL'),
      () => handlersRef.current.handleFormatSql(),
      {status: executing ? T_ACTION_STATUS.DISABLED : T_ACTION_STATUS.ENABLED}
    );
    const boolMenuId = reg('bool_menu', 'action.check', gettext('Boolean'), (detail) => {
      const chosen = detail?.item?.id;
      if (chosen) handlersRef.current.setLayout((prev) => ({...prev, booleanFormat: chosen}));
    });
    const vbInspectorId = reg('vb_inspector', 'action.inspector_drawer', gettext('Builder Inspector'), () => {
      setVbInspectorTab('tables');
      handlersRef.current.openRightDrawerWith({panel: 'visual_inspector'});
    });
    const limitsId = reg('limits', 'action.fetch_limits', gettext('Fetch Limits…'), () =>
      handlersRef.current.setLimitsModalOpen(true)
    );
    const connInfoId = reg('conn_info', 'action.properties', gettext('Connection Details…'), () =>
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
      'action.accessible_table',
      gettext('Excel / ODS…'),
      () => {
        handlersRef.current.setExportInitialFormat('xlsx');
        handlersRef.current.setExportDialogOpen(true);
      }
    );
    const exportPdfId = reg('export_pdf', 'action.print', gettext('PDF Report…'), () => {
      handlersRef.current.setExportInitialFormat('pdf');
      handlersRef.current.setExportDialogOpen(true);
    });

    const areaOptions = [
      [SQL_SURFACE_VIEWS.SQL, gettext('SQL')],
      [SQL_SURFACE_VIEWS.VISUAL_BUILDER, gettext('Visual Query Builder (DDN)')],
      [SQL_SURFACE_VIEWS.DATA, gettext('Data')],
      [SQL_SURFACE_VIEWS.METRICS_PLAN, gettext('Metrics & Plan')],
      [SQL_SURFACE_VIEWS.FIELDS, gettext('Result Fields')],
      [SQL_SURFACE_VIEWS.INFORMATION, gettext('Information')],
      [SQL_SURFACE_VIEWS.METADATA, gettext('Metadata')],
      [SQL_SURFACE_VIEWS.MESSAGES, gettext('Messages')],
    ];
    const split = surfaceView === SQL_SURFACE_VIEWS.SQL_DATA;
    const firstView = split ? upperView : surfaceView;
    const displayAreas = [
      displayAreaControl(reg, pfx, 'first_area', gettext('First Display Area'),
        areaOptions.filter(([view]) => !split || view !== lowerView || view === SQL_SURFACE_VIEWS.DATA),
        firstView, (view) => handlersRef.current.selectDisplayArea('first', view), 120),
      displayAreaControl(reg, pfx, 'second_area', gettext('Second Display Area'), [
        ['off', gettext('Off')],
        ...areaOptions.filter(([view]) => view !== firstView || view === SQL_SURFACE_VIEWS.DATA),
      ], split ? lowerView : 'off', (view) => handlersRef.current.selectDisplayArea('second', view), 121),
    ];
    if (firstView === SQL_SURFACE_VIEWS.DATA) {
      displayAreas.push(displayAreaControl(reg, pfx, 'first_presentation', gettext('First Area Presentation'),
        split ? presentationChoices() : presentationChoices().slice(1),
        split ? upperMode || 'default' : layout.displayMode,
        (mode) => {
          if (split) setUpperMode(mode === 'default' ? '' : mode);
          else setLayout((current) => ({...current, displayMode: mode}));
        }, 122));
    }
    if (split && lowerView === SQL_SURFACE_VIEWS.DATA) {
      displayAreas.push(displayAreaControl(reg, pfx, 'second_presentation', gettext('Second Area Presentation'),
        presentationChoices(), lowerMode || 'default',
        (mode) => setLowerMode(mode === 'default' ? '' : mode), 123));
    }

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
          tooltip: gettext('Open the SQL text editor'),
          icon: 'action.sql_preview',
          checked: surfaceView === SQL_SURFACE_VIEWS.SQL,
        },
        {
          id: SQL_SURFACE_VIEWS.VISUAL_BUILDER,
          label: gettext('Visual Builder'),
          tooltip: gettext('Design a query visually'),
          icon: 'action.sql_builder',
          checked: surfaceView === SQL_SURFACE_VIEWS.VISUAL_BUILDER,
        },
        {
          id: SQL_SURFACE_VIEWS.SQL_DATA,
          label: gettext('SQL + Data'),
          tooltip: gettext('Show the SQL editor above the query results'),
          icon: 'action.layout_hybrid',
          checked: surfaceView === SQL_SURFACE_VIEWS.SQL_DATA,
        },
        {
          id: SQL_SURFACE_VIEWS.DATA,
          label: gettext('Data'),
          tooltip: gettext('Show the rows returned by the query'),
          icon: 'action.browse_data',
          checked: surfaceView === SQL_SURFACE_VIEWS.DATA,
        },
        {
          id: SQL_SURFACE_VIEWS.METRICS_PLAN,
          label: gettext('Metrics & Plan'),
          tooltip: gettext('Inspect execution statistics and the available plan'),
          icon: 'action.statistics',
          checked: surfaceView === SQL_SURFACE_VIEWS.METRICS_PLAN,
        },
        {
          id: SQL_SURFACE_VIEWS.FIELDS,
          label: gettext('Fields'),
          tooltip: gettext('Inspect column names and data types'),
          icon: 'action.section_columns',
          checked: surfaceView === SQL_SURFACE_VIEWS.FIELDS,
        },
        {
          id: SQL_SURFACE_VIEWS.INFORMATION,
          label: gettext('Information'),
          tooltip: gettext('Review information about the selected object or query'),
          icon: 'action.properties',
          checked: surfaceView === SQL_SURFACE_VIEWS.INFORMATION,
        },
        {
          id: SQL_SURFACE_VIEWS.METADATA,
          label: gettext('Metadata'),
          tooltip: gettext('Inspect the object definition, comment and dependencies'),
          icon: 'action.dependencies',
          checked: surfaceView === SQL_SURFACE_VIEWS.METADATA,
        },
        {
          id: SQL_SURFACE_VIEWS.MESSAGES,
          label: gettext('Messages'),
          tooltip: gettext('Review execution messages and errors'),
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
          tooltip: gettext('Show records in a table with one row per record'),
          icon: 'action.layout_grid',
          checked: layout.displayMode === DISPLAY_MODES.GRID,
        },
        {
          id: DISPLAY_MODES.MINI_FORMS,
          label: gettext('Mini-Forms'),
          tooltip: gettext('Show each record in a compact form'),
          icon: 'action.layout_mini_forms',
          checked: layout.displayMode === DISPLAY_MODES.MINI_FORMS,
        },
        {
          id: DISPLAY_MODES.HYBRID,
          label: gettext('Hybrid'),
          tooltip: gettext('Show the current record in a mini-form below the grid'),
          icon: 'action.layout_hybrid',
          checked: layout.displayMode === DISPLAY_MODES.HYBRID,
        },
        {
          id: DISPLAY_MODES.SINGLE_FORM,
          label: gettext('Single Form'),
          tooltip: gettext('Fill the data area with a form for the current record'),
          icon: 'action.layout_single_form',
          checked: layout.displayMode === DISPLAY_MODES.SINGLE_FORM,
        },
        {
          id: DISPLAY_MODES.HYBRID_EDIT,
          label: gettext('Hybrid-When-Editing'),
          tooltip: gettext('Show the grid while browsing and switch to a form when editing'),
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
              ...(prepareId ? [prepareId] : []),
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
            controls: [
              ...(startTransactionId ? [startTransactionId] : []),
              ...(prepareTransactionId ? [prepareTransactionId] : []),
              commitId, rollbackId, autocommitId,
            ],
          },
          {
            id: 'navigate',
            label: gettext('Navigate'),
            controls: [
              navFirstId,
              navPrevPageId,
              navPrevRowId,
              bookmarkToggleId,
              navNextRowId,
              navNextPageId,
              navLastId,
              bookmarkPrevId,
              bookmarkNextId,
            ],
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
            id: 'display_areas',
            label: gettext('Display Areas'),
            controls: displayAreas.map(({control}) => control),
          },
          {
            id: 'data_display',
            label: gettext('Data Display'),
            controls: [displayControlSpec, applyTemplateId],
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
          ...(prepareId ? [{
            id: `${pfx}.m.prepare_statement`, actionId: prepareId, label: gettext('Prepare Statement'), index: 35,
          }] : []),
          ...(isFirebird ? [
            {
              id: `${pfx}.m.fb_profile`,
              label: gettext('Profile Statement (RDB$PROFILER)…'),
              index: 36,
              disabled: executing,
              callback: () => setProfilerConsentOpen(true),
            },
            {
              id: `${pfx}.m.fb_stats`,
              label: gettext('Collect Attachment Statistics (MON$)'),
              checked: collectStatistics,
              index: 37,
              callback: () => setCollectStatistics((v) => !v),
            },
            {
              id: `${pfx}.m.fb_session_tools`,
              label: gettext('EDS Pool, Session Traps & Stream Reader…'),
              index: 38,
              callback: () => {
                setSessionToolsTab('eds_pool');
                setSessionToolsOpen(true);
              },
            },
          ] : []),
          ...(isMySQL ? [
            {
              id: `${pfx}.m.mysql_explain_analyze`,
              label: gettext('Run EXPLAIN ANALYZE (Executes Statement)…'),
              index: 36,
              disabled: executing,
              callback: () => setMysqlAnalyzeConsentOpen(true),
            },
            {
              id: `${pfx}.m.mysql_query_attrs`,
              label: gettext('MySQL Query Attributes & Session Observation…'),
              index: 37,
              callback: () => setMysqlAttributesOpen(true),
            },
          ] : []),
          ...(isMariaDB ? [
            {
              id: `${pfx}.m.mariadb_analyze_json`,
              label: gettext('Run ANALYZE FORMAT=JSON (Executes Statement)…'),
              index: 36,
              disabled: executing,
              callback: () => setMariadbAnalyzeConsentOpen(true),
            },
            {
              id: `${pfx}.m.mariadb_session_diag`,
              label: gettext('MariaDB Session Variables, Flagsets & Context…'),
              index: 37,
              callback: () => setMariadbSessionOpen(true),
            },
          ] : []),
          {
            id: `${pfx}.m.hist_sensitive`,
            label: gettext('Suppress Sensitive SQL from Persistent History'),
            checked: historySensitive,
            index: 39,
            callback: () => setHistorySensitive((v) => !v),
          },
          {id: `${pfx}.m.params`, actionId: paramsId, label: gettext('Parameters…'), index: 40},
          {id: `${pfx}.m.sep1`, type: 'separator', index: 45},
          ...(startTransactionId ? [{
            id: `${pfx}.m.start_transaction`, actionId: startTransactionId,
            label: gettext('Start Transaction…'), index: 46,
          }] : []),
          ...(prepareTransactionId ? [{
            id: `${pfx}.m.prepare_transaction`, actionId: prepareTransactionId,
            label: gettext('Prepare Transaction…'), index: 48,
          }] : []),
          ...(recoveryId ? [{
            id: `${pfx}.m.recover_prepared_transaction`, actionId: recoveryId,
            label: gettext('Recover Prepared Transaction…'), index: 49,
          }] : []),
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
          {id: `${pfx}.m.sep_e2`, type: 'separator', index: 55},
          {id: `${pfx}.m.nav_first`, actionId: navFirstId, label: gettext('First Record (|<)'), index: 60},
          {id: `${pfx}.m.nav_prev_page`, actionId: navPrevPageId, label: gettext('Previous Page (<<)'), index: 62},
          {id: `${pfx}.m.nav_prev_row`, actionId: navPrevRowId, label: gettext('Previous Row (<)'), index: 64},
          {id: `${pfx}.m.nav_next_row`, actionId: navNextRowId, label: gettext('Next Row (>)'), index: 66},
          {id: `${pfx}.m.nav_next_page`, actionId: navNextPageId, label: gettext('Next Page (>>)'), index: 68},
          {id: `${pfx}.m.nav_last`, actionId: navLastId, label: gettext('Last Record (>|)'), index: 70},
          {id: `${pfx}.m.bm_toggle`, actionId: bookmarkToggleId, label: gettext('Bookmark Record (!)'), index: 65},
          {id: `${pfx}.m.bm_prev`, actionId: bookmarkPrevId, label: gettext('Previous Bookmark (!<)'), index: 74},
          {id: `${pfx}.m.bm_next`, actionId: bookmarkNextId, label: gettext('Next Bookmark (!>)'), index: 76},
        ],
      },
      {
        name: 'view',
        id: `${pfx}.menu.view`,
        index: 25,
        label: gettext('View'),
        items: [
          ...displayAreas.map(({menu}) => menu),
          {
            id: `${pfx}.m.apply_layout_template`, actionId: applyTemplateId,
            label: gettext('Apply Layout Template…'), index: 115,
          },
          ...[
            [SQL_SURFACE_VIEWS.SQL, gettext('SQL Editor')],
            [SQL_SURFACE_VIEWS.VISUAL_BUILDER, gettext('Visual Query Builder (DDN)')],
            [SQL_SURFACE_VIEWS.SQL_DATA, gettext('SQL + Data Split')],
            [SQL_SURFACE_VIEWS.DATA, gettext('Data View')],
            [SQL_SURFACE_VIEWS.METRICS_PLAN, gettext('Metrics & Plan')],
            [SQL_SURFACE_VIEWS.FIELDS, gettext('Result Fields')],
            [SQL_SURFACE_VIEWS.INFORMATION, gettext('Information')],
            [SQL_SURFACE_VIEWS.METADATA, gettext('Metadata')],
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
          {
            id: `${pfx}.field_type_defaults`,
            label: gettext('Field Type Defaults…'),
            index: 110,
            callback: () => setFieldDefaultsOpen(true),
          },
          {
            id: `${pfx}.m.save_object_layout`,
            label: gettext('Save Layout for This Object'),
            index: 105,
            disabled: !hostData?.object_layout_key,
            callback: () => handlersRef.current.saveObjectLayout(),
          },
          {id: `${pfx}.m.vbi`, actionId: vbInspectorId, label: gettext('Visual Builder Inspector'), index: 100},
        ],
      },
      {
        name: 'window',
        id: `${pfx}.menu.window`,
        index: PROJECT_TOP_MENU_INDICES.WINDOW, // 70
        label: gettext('Window'),
        items: [
          {
            id: `${pfx}.m.rename_tab`,
            label: gettext('Rename Tab… (F2)'),
            index: 75,
            callback: () => shellRef.current?.requestTabRename?.(instId),
          },
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
    localeRevision,
    activeBookmarks,
    activeRowIndex,
    autocommit,
    canCancel,
    callHost,
    cancelPending,
    canInsertResult,
    collectStatistics,
    executing,
    hasUncommitted,
    historySensitive,
    isFirebird,
    hostData?.active_result_index,
    hostData?.object_layout_key,
    hostData?.result_count,
    hostData?.total_view_rows,
    hostData?.window_offset,
    hostData?.window_size,
    instId,
    instanceScope?.instanceId,
    isEditableResult,
    isEditingRow,
    layout.booleanFormat,
    layout.displayMode,
    languageOptions.native_statement_prepare,
    languageOptions.native_transaction_start,
    languageOptions.syntax_family,
    languageOptions.native_transaction_prepare,
    hostData?.session_id,
    hostData?.xa_state,
    hostData?.staged_count,
    hostData?.prepared_transaction_id,
    hostData?.transaction_prepare_state,
    limitsDraft.pageSize,
    rows.length,
    stableConfirmCloseGuard,
    stableRenderRightDrawer,
    stableRenderStatus,
    statusSummaryText,
    surfaceView,
    upperView,
    lowerView,
    upperMode,
    lowerMode,
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

  const setRecordColumnPref = (name, patch) => setLayout(prev => ({...prev,
    gridColPrefs: {...prev.gridColPrefs, [name]: {...prev.gridColPrefs[name], ...patch}},
    formFieldPrefs: {...prev.formFieldPrefs, [name]: {...prev.formFieldPrefs[name], ...patch}},
  }));
  const cancelRecordDraft = () => {setIsEditingRow(false); setEditingRowIndex(null); setRowDraft(null); setIsInsertDraft(false);};
  const recordDrawer = patch => openRightDrawerWith({
    panel: patch.mode === 'complex_value' ? 'value_inspector' : patch.mode,
    valueRowIndex: patch.rowIndex, valueColName: patch.column?.name || patch.column,
  });
  const recordHeaderMenu = (event, col) => {
    event.preventDefault();
    setActiveColName(col.name);
    setContextMenuState({open:true,x:event.clientX,y:event.clientY,items:[
      {id:'columns',label:gettext('Visible Columns & Field Order…'),onSelect:()=>{setColumnPickerScope('grid');setColPickerOpen(true);}},
      {id:'freeze',label:gettext('Freeze / Unfreeze Column'),onSelect:()=>setRecordColumnPref(col.name,{pinned:!layout.gridColPrefs[col.name]?.pinned})},
      {id:'filter',label:gettext('Filter Options…'),onSelect:()=>openRightDrawerWith({panel:'filter_builder',filterColumn:col.name})},
      {id:'profile',label:gettext('Column Profile / Distinct Values'),onSelect:async()=>openRightDrawerWith({panel:'column_profile',profileData:await callHost('column_profile',{column:col.name})})},
    ]});
  };
  const recordFormMenu = (event) => {
    event.preventDefault();setContextMenuState({open:true,x:event.clientX,y:event.clientY,items:[
      {id:'edit',label:isEditingRow?gettext('Accept Row'):gettext('Edit Row'),disabled: !isEditableResult, onSelect:()=>isEditingRow?acceptCurrentRow():beginEditRow()},
      {id:'columns',label:gettext('Form Fields & Order…'),onSelect:()=>{setColumnPickerScope('form');setColPickerOpen(true);}},
    ]});
  };
  const recordFieldMenu = (event, column, rowIndex) => {
    event.preventDefault();
    const markdown = layout.formFieldPrefs[column.name]?.editor === 'markdown';
    const items = [{
      id: 'inspect',
      label: gettext('Open in Right Drawer'),
      onSelect: () => openRightDrawerWith({
        panel: 'value_inspector', valueRowIndex: rowIndex, valueColName: column.name,
      }),
    }];
    const pair = recordConversionPair(column, conversionPairs);
    const selectedPair = layout.formFieldPrefs[column.name]?.conversionPair;
    if (pair) {
      items.push({
        id: 'field_conversion',
        label: selectedPair ? gettext('Show Native Binary') : gettext('Display as UUID'),
        onSelect: () => setRecordColumnPref(column.name, {conversionPair: selectedPair ? undefined : pair.id}),
      });
    }
    items.push({
      id: 'field_format',
      label: gettext('Font & Alignment…'),
      onSelect: () => setFormatFieldName(column.name),
    });
    if (inferColumnMeta(column).clientType === 'text') {
      items.push({
        id: 'field_editor',
        label: markdown ? gettext('Use Plain Text Editor') : gettext('Use Markdown Editor'),
        onSelect: () => setRecordColumnPref(column.name, {editor: markdown ? 'text' : 'markdown'}),
      });
    }
    setContextMenuState({open: true, x: event.clientX, y: event.clientY, items});
  };

  const renderDataPane = (mode, secondary) => <RecordDataView model={{
    acceptCurrentRow,
    activeColName,
    activeRowIndex,
    beginEditRow,
    bookmarkedGlobals: activeBookmarks,
    cancelRowDraft: cancelRecordDraft,
    currentRow,
    conversions,
    editingRowIndex,
    effectiveDisplayMode: resolveRecordPresentation(mode || layout.displayMode, isEditingRow, layout.hybridEditTarget),
    formColumns,
    gridColumns,
    gridViewportRef: secondary ? companionGridRef : gridViewportRef,
    handleKeyboardCellNavigate: handleSqlKeyboardCellNavigate,
    handleToggleColumnSort: handleToggleSort,
    hostData: {...hostData,sorts:(activeResult?.sort || []).map(s=>({...s,direction:s.dir||s.direction})),filters:activeResult?.filters||[]},
    isEditingRow,
    layout,
    openFormFieldContextMenu: recordFieldMenu,
    openHeaderContextMenu: recordHeaderMenu,
    openMiniFormContextMenu: recordFormMenu,
    openRightDrawerWith: recordDrawer,
    quickFindText: '',
    rowDraft,
    rows,
    selectRowAtIndex: selectSqlRowAtIndex,
    selectedCells,
    setActiveColName,
    setColumnPickerOpen: setColPickerOpen,
    setColumnPickerScope,
    setColumnPref: setRecordColumnPref,
    setRowDraft,
    setScrollRowRange,
    setSelectedCells,
    sharedFormLayout,
    toggleBookmarkAtRow: toggleSqlBookmark,
    viewportWidth
  }}/>;

  const renderDesigner = () => (
        <div
          data-cdeadmin-qa-key="sql-surface-visual-builder-canvas"
          onDragEnter={(e) => {
            e.preventDefault();
            setCanvasDropActive(true);
          }}
          onDragOver={(e) => {
            e.preventDefault();
            if (e.dataTransfer) {
              e.dataTransfer.dropEffect = 'copy';
            }
            if (!canvasDropActive) setCanvasDropActive(true);
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget)) {
              setCanvasDropActive(false);
            }
          }}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setCanvasDropActive(false);
            if (!e.dataTransfer) return;

            let droppedObj = null;
            try {
              const rawCustom = e.dataTransfer.getData(
                'application/x-scratchrobin-catalog-object'
              );
              if (rawCustom) {
                droppedObj = JSON.parse(rawCustom);
              }
            } catch {
              droppedObj = null;
            }

            if (!droppedObj) {
              let rawText = '';
              try {
                rawText =
                  e.dataTransfer.getData('text') ||
                  e.dataTransfer.getData('text/plain') ||
                  '';
              } catch {
                rawText = '';
              }
              if (rawText) {
                try {
                  const parsed = JSON.parse(rawText);
                  if (parsed?.scratchrobinCatalogObject) {
                    droppedObj = parsed.scratchrobinCatalogObject;
                  } else if (parsed?.text) {
                    const ident = String(parsed.text)
                      .split('.')
                      .pop()
                      .replace(/^["`]|["`]$/g, '')
                      .replace(/\([^)]*\)\s*$/, '')
                      .trim();
                    const kindAliases = {
                      mview: 'materialized-view',
                      foreign_table: 'foreign-table',
                      partition: 'partitioned-table',
                      edbfunc: 'function',
                      edbproc: 'procedure',
                    };
                    const rk = String(parsed.nodeType || 'table').toLowerCase();
                    droppedObj = {
                      resource_id: '',
                      resource_kind: kindAliases[rk] || rk,
                      display_name: ident,
                    };
                  }
                } catch {
                  const ident = rawText
                    .split('.')
                    .pop()
                    .replace(/^["`]|["`]$/g, '')
                    .trim();
                  if (ident) {
                    droppedObj = {
                      resource_id: '',
                      resource_kind: 'table',
                      display_name: ident,
                    };
                  }
                }
              }
            }

            if (!droppedObj?.display_name) return;
            const wp = canvasApiRef.current?.clientToWorld?.(e.clientX, e.clientY);
            const dropCoords = wp
              ? {x: Math.max(24, wp.x - 90), y: Math.max(24, wp.y - 18)}
              : null;
            addCatalogObjectToCanvas(droppedObj, dropCoords);
          }}
          style={{
            flex: 1,
            minHeight: 0,
            minWidth: 0,
            position: 'relative',
            display: 'flex',
            outline: canvasDropActive
              ? '2px dashed var(--sr-accent-primary, #2563eb)'
              : 'none',
            outlineOffset: -4,
          }}
        >
          <RobinTiledCanvas
            scene={visualScene}
            selectedNodeId={selectedCanvasNodeId}
            onSelectNode={(node) => {
              const nid = typeof node === 'object' ? node?.id || '' : String(node || '');
              setSelectedCanvasNodeId(nid);
            }}
            onSelectEdge={() => {
              setVbInspectorTab('joins');
              openRightDrawerWith({panel: 'visual_inspector'});
            }}
            onToggleField={handleToggleCanvasField}
            onCreateFieldJoin={handleCreateCanvasJoin}
            onRemoveNode={handleRemoveCanvasNode}
            editable
            onPinNode={(nodeId, x, y) => {
              const cur = visualModelRef.current;
              const next = {
                ...cur,
                tables: (cur.tables || []).map((t) =>
                  t.id === nodeId ? {...t, x, y} : t
                ),
              };
              pushVisualModelUpdate(next, false);
            }}
            canvasApiRef={canvasApiRef}
            ariaLabel={gettext('DDN Visual Query Builder Canvas')}
          />

          {canvasDropActive && (
            <div
              data-cdeadmin-qa-key="visual-builder-drop-indicator"
              style={{
                position: 'absolute',
                top: 14,
                right: 16,
                padding: '6px 14px',
                borderRadius: 999,
                background: 'var(--sr-accent-primary, #2563eb)',
                color: '#ffffff',
                fontWeight: 600,
                fontSize: '0.78rem',
                boxShadow: '0 4px 14px rgba(37, 99, 235, 0.28)',
                pointerEvents: 'none',
              }}
            >
              {gettext('Drop Table, View, or Selectable Procedure onto Canvas')}
            </div>
          )}

          {canvasNotice && (
            <div
              role="alert"
              data-cdeadmin-qa-key="visual-builder-canvas-notice"
              style={{
                position: 'absolute',
                top: 14,
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 12,
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '7px 14px',
                borderRadius: 8,
                background: 'rgba(254, 242, 242, 0.97)',
                border: '1px solid #ef4444',
                color: '#991b1b',
                fontSize: '0.78rem',
                fontWeight: 500,
                boxShadow: '0 6px 18px rgba(0, 0, 0, 0.12)',
              }}
            >
              <span>⚠ {canvasNotice}</span>
              <button
                type="button"
                aria-label={gettext('Dismiss')}
                onClick={() => setCanvasNotice('')}
                style={{
                  border: 0,
                  background: 'transparent',
                  color: '#991b1b',
                  cursor: 'pointer',
                  fontWeight: 700,
                  fontSize: '0.95rem',
                }}
              >
                ×
              </button>
            </div>
          )}

          {visualModel.tables.length === 0 && !canvasNotice && (
            <div
              style={{
                position: 'absolute',
                top: 14,
                left: 14,
                padding: '7px 14px',
                borderRadius: 999,
                background: 'var(--sr-island-bg, rgba(255,255,255,0.95))',
                border: '1px solid var(--sr-border-default, #cbd5e1)',
                fontSize: '0.78rem',
                pointerEvents: 'none',
              }}
            >
              {gettext(
                'Drag Tables, Views, or Selectable Stored Procedures from Data Navigator (left) or Builder Palette (right) onto this canvas'
              )}
            </div>
          )}
        </div>
  );
  const renderMetrics = () => (
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

            <SqlProfilerAndStatsView
              profiling={hostData?.profiling}
              statistics={hostData?.query_statistics}
            />

            {(isMySQL || isMariaDB) && (
              <SqlMySQLPlanGraphView
                planText={activeResult?.plan_text || hostData?.plan_text || ''}
                mysqlDiagnostics={hostData?.mysql_diagnostics || null}
              />
            )}

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
  );
  const renderFields = () => (
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
  );
  const renderMessages = () => (
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
  );

  const metadataResources = activeResult?.metadata_resources || EMPTY_ARRAY;
  const selectedMetadata = metadataSelection?.result === activeResult?.index
    && metadataResources.find(({resource_id}) => resource_id === metadataSelection?.id);

  const renderMetadata = () => (
    <div style={{display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, minWidth: 0}}>
      {!activeResult?.target_resource && metadataResources.length > 0 && (
        <label style={{padding: 8}}>
          {gettext('Referenced object')}{' '}
          <select className="sr-input" value={selectedMetadata?.resource_id || ''}
            onChange={(event) => setMetadataSelection({result: activeResult.index, id: event.target.value})}>
            <option value="">{gettext('Select an object')}</option>
            {metadataResources.map(({resource_id, display_name}) => (
              <option key={resource_id} value={resource_id}>{display_name}</option>
            ))}
          </select>
        </label>
      )}
      <SurfaceMetadata post={post} databaseTargetId={databaseTargetId}
        resource={activeResult?.target_resource || selectedMetadata || null} />
    </div>
  );

  const renderView = (view, mode, secondary = false) => {
    switch (view) {
    case SQL_SURFACE_VIEWS.METADATA: return renderMetadata();
    case SQL_SURFACE_VIEWS.INFORMATION: {
      const effectiveQuery = hostData?.sql_view?.effective_query;
      return <SurfaceInformation
        fields={hostData?.object_layout_key ? hostData?.fields_grid || EMPTY_ARRAY : EMPTY_ARRAY}
        effectiveQuery={effectiveQuery}
        filters={activeResult?.filters}
        sorts={activeResult?.sort}
        onSave={effectiveQuery?.sql ? () => openSaveDialog('quick_query', false, effectiveQuery) : undefined}
      />;
    }
    case SQL_SURFACE_VIEWS.DATA: return renderDataPane(mode, secondary);
    case SQL_SURFACE_VIEWS.VISUAL_BUILDER: return renderDesigner();
    case SQL_SURFACE_VIEWS.METRICS_PLAN: return renderMetrics();
    case SQL_SURFACE_VIEWS.FIELDS: return renderFields();
    case SQL_SURFACE_VIEWS.MESSAGES: return renderMessages();
    default: return renderSqlEditorPane();
    }
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
      <ColumnOrderDialog open={colPickerOpen} scope={columnPickerScope} allColumns={columns}
        visibleNames={columnPickerScope === 'form' ? layout.formVisibleCols : layout.gridVisibleCols}
        orderNames={columnPickerScope === 'form' ? layout.formColOrder : layout.gridColOrder}
        onClose={()=>setColPickerOpen(false)} onApply={(order,visible)=>{
          setLayout(prev=>columnPickerScope==='form'?{...prev,formColOrder:order,formVisibleCols:visible}:{...prev,gridColOrder:order,gridVisibleCols:visible});setColPickerOpen(false);
        }}/>
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

      {surfaceView === SQL_SURFACE_VIEWS.SQL_DATA ? (
          <SurfaceDisplayAreas
            first={renderView(upperView, upperMode)}
            second={renderView(lowerView, lowerMode, true)}
            onActivate={(event) => { focusedDisplayAreaRef.current = event.currentTarget; }}
            ratio={46}
          />
      ) : renderView(surfaceView)}

      {/* Right-Click Context Menu */}
      {formatFieldName && (
        <FieldTypeDefaultsDialog
          fieldName={formatFieldName}
          types={[formatFieldName]}
          defaults={{[formatFieldName]: layout.formFieldPrefs[formatFieldName] || {}}}
          onClose={() => setFormatFieldName(null)}
          onSave={(values) => {
            const {font, hAlign} = values[formatFieldName];
            setRecordColumnPref(formatFieldName, {font: font || undefined, hAlign: hAlign || undefined});
          }}
        />
      )}
      <Dialog
        open={templatePickerOpen}
        title={gettext('Apply Layout Template')}
        size="medium"
        onClose={() => setTemplatePickerOpen(false)}
        actions={<Button onClick={() => setTemplatePickerOpen(false)}>{gettext('Close')}</Button>}
      >
        {templateLoadError ? (
          <p role="alert">{gettext('Could not load layout templates: %s', templateLoadError)}</p>
        ) : availableTemplates ? (
          <SurfaceLayoutTemplateList
            templates={availableTemplates}
            onSelect={(template) => {
              explicitLayoutRef.current = true;
              setLayout((previous) => ({...previous, ...(template.layout || {})}));
              setUpperMode('');
              setLowerMode('');
              setTemplatePickerOpen(false);
            }}
          />
        ) : <p role="status">{gettext('Loading layout templates…')}</p>}
      </Dialog>
      {fieldDefaultsOpen && (
        <FieldTypeDefaultsDialog
          types={[...new Set(['text', ...columns.map((column) => inferColumnMeta(column).clientType)])]}
          defaults={hostData?.field_type_defaults || {}}
          onClose={() => setFieldDefaultsOpen(false)}
          onSave={async (defaults) => {
            const response = await callHost('save_field_type_defaults', {field_type_defaults: defaults});
            setHostData((current) => ({...current, field_type_defaults: response.field_type_defaults}));
          }}
        />
      )}
      <ContextMenu
        open={contextMenuState.open}
        x={contextMenuState.x}
        y={contextMenuState.y}
        items={contextMenuState.items}
        onClose={() => setContextMenuState((prev) => ({...prev, open: false}))}
      />

      {recovery && (
        <Dialog open title={gettext('Recover Prepared Transaction')} size="medium"
          onClose={() => { if (!executing) setRecovery(null); }}
          actions={<>
            <Button disabled={executing} onClick={() => setRecovery(null)}>{gettext('Close')}</Button>
            {['commit', 'rollback'].map((resolution) => (
              <Button key={resolution} disabled={executing || !recovery.gid}
                onClick={async () => {
                  setExecuting(true);
                  setTransactionStartError('');
                  try {
                    const response = await callHost('recover_prepared_transaction', {
                      resolution, gid: recovery.gid,
                    });
                    applyHostState(response.state);
                    setRecovery(null);
                  } catch (error) {
                    setTransactionStartError(error?.message || String(error));
                    setRecovery((current) => ({...current, transactions: [], gid: ''}));
                  } finally {
                    setExecuting(false);
                  }
                }}>{resolution === 'commit' ? gettext('Commit') : gettext('Rollback')}</Button>
            ))}
          </>}>
          <label>
            {gettext('Prepared Transaction')}
            <select value={recovery.gid} disabled={executing}
              onChange={(event) => setRecovery({...recovery, gid: event.target.value})}>
              <option value="">{gettext('Select a transaction')}</option>
              {recovery.transactions.map(({gid, prepared_at}) => (
                <option key={gid} value={gid}>{gid} · {prepared_at}</option>
              ))}
            </select>
          </label>
          {transactionStartError && <p role="alert">{transactionStartError}</p>}
        </Dialog>
      )}
      {prepareTransactionOpen && (
        <Dialog open title={gettext('Prepare Transaction')} size="small"
          onClose={() => { if (!executing) setPrepareTransactionOpen(false); }}
          actions={<>
            <Button disabled={executing} onClick={() => setPrepareTransactionOpen(false)}>{gettext('Cancel')}</Button>
            <Button intent="primary" disabled={executing || Boolean(hostData?.transaction_prepare_state)}
              onClick={async () => {
                setExecuting(true);
                setTransactionStartError('');
                try {
                  applyHostState(await callHost('prepare_transaction'));
                  setPrepareTransactionOpen(false);
                } catch (error) {
                  setTransactionStartError(error?.message || String(error));
                  try {
                    applyHostState(await callHost('read_window'));
                  } catch {
                    // Preserve the provider error.
                  }
                } finally {
                  setExecuting(false);
                }
              }}>{gettext('Prepare')}</Button>
          </>}>
          <p>{gettext('Prepare the active transaction for two-phase commit. After preparing, use Commit or Rollback to resolve it.')}</p>
          {transactionStartError && <p role="alert">{transactionStartError}</p>}
        </Dialog>
      )}
      {startTransactionOpen && (
        <Dialog open title={gettext('Start Transaction')} size="small"
          onClose={() => { if (!executing) setStartTransactionOpen(false); }}
          actions={<>
            <Button disabled={executing} onClick={() => setStartTransactionOpen(false)}>{gettext('Cancel')}</Button>
            {['mysql', 'mariadb'].includes(languageOptions.syntax_family) && languageOptions.native_transaction_prepare && (
              <Button disabled={executing} onClick={async () => {
                setExecuting(true);
                setTransactionStartError('');
                try {
                  applyHostState(await callHost('start_xa_transaction'));
                  setStartTransactionOpen(false);
                } catch (error) {
                  setTransactionStartError(error?.message || String(error));
                  try {
                    applyHostState(await callHost('read_window'));
                  } catch {
                    // Keep the original XA error.
                  }
                } finally {
                  setExecuting(false);
                }
              }}>{gettext('Start XA Transaction')}</Button>
            )}
            <Button intent="primary" disabled={executing} onClick={async () => {
              setExecuting(true);
              setTransactionStartError('');
              try {
                const response = await callHost('start_transaction', {
                  transaction_options: transactionOptions, client_sql_dialect: clientSqlDialect,
                });
                applyHostState(response);
                setStartTransactionOpen(false);
              } catch (error) {
                setTransactionStartError(error?.message || String(error));
                try {
                  applyHostState(await callHost('read_window'));
                } catch {
                  // Retain the native error when state observation fails.
                }
              } finally {
                setExecuting(false);
              }
            }}>{gettext('Start')}</Button>
          </>}>
          <div style={{display: 'grid', gap: 8}}>
            {transactionStartOptions(languageOptions.syntax_family).map(([key, label, values]) => (
              <label key={key}>{label}{' '}
                <select className="sr-input" value={transactionOptions[key]} disabled={executing}
                  onChange={(event) => setTransactionOptions({...transactionOptions, [key]: event.target.value})}>
                  {values.map(([value, title]) => <option key={value} value={value}>{title}</option>)}
                </select>
              </label>
            ))}
            {transactionStartError && <p role="alert">{transactionStartError}</p>}
          </div>
        </Dialog>
      )}
      {preparedStatement && (
        <Dialog open title={gettext('Prepared Statement')} size="medium"
          onClose={() => setPreparedStatement(null)}
          actions={<Button onClick={() => setPreparedStatement(null)}>{gettext('Close')}</Button>}>
          <div style={{display: 'grid', gap: 8}}>
            <p>{preparedStatement.statement_type}</p>
            {[
              [gettext('Result Columns'), preparedStatement.columns, preparedStatement.columns_complete],
              [gettext('Parameters'), preparedStatement.parameters, preparedStatement.parameters_complete],
            ].map(([label, items, complete]) => (
              <section key={label}>
                <h3>{label}</h3>
                {!complete && <p>{gettext('The provider supplied incomplete metadata.')}</p>}
                <ol>{(items || []).map((item) => (
                  <li key={item.position}>
                    {[item.name || item.field, item.native_type].filter(Boolean).join(' · ')}
                  </li>
                ))}</ol>
              </section>
            ))}
            <pre style={{whiteSpace: 'pre-wrap'}}>
              {preparedStatement.detailed?.text || preparedStatement.legacy?.text || gettext('No plan supplied.')}
            </pre>
          </div>
        </Dialog>
      )}
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
                    aria-label={gettext('Type for %s', key)}
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
                    aria-label={gettext('Value for %s', key)}
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
                    {gettext('Display: %s · Terminator: %s', quickQueryDisplayLabel(qq.display_layout?.displayMode), qq.terminator || ';')}
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
                  {qq.server_id > 0 && (
                    <Button size="small" onClick={() => {
                      const pinned = quickQueryShortcuts.some((query) => query.query_id === qq.query_id);
                      try {
                        setQuickQueryShortcut(qq, !pinned);
                      } catch (error) {
                        setSurfaceError(error?.message || String(error));
                      }
                    }}>
                      {quickQueryShortcuts.some((query) => query.query_id === qq.query_id)
                        ? gettext('Remove from Dashboard') : gettext('Pin to Dashboard')}
                    </Button>
                  )}
                  <Button
                    size="small"
                    onClick={async () => {
                      try {
                        const res = await callHost('delete_quick_query', {query_id: qq.query_id});
                        if (Array.isArray(res?.quick_queries)) setQuickQueries(res.quick_queries);
                        setQuickQueryShortcut(qq, false);
                      } catch (error) {
                        setSurfaceError(error?.message || String(error));
                      }
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
            <>
              <div className="sr-field">
                <label className="sr-field-label" htmlFor={`${surfaceIdRef.current}-sql-dialect`}>
                  {gettext('Firebird SQL Dialect')}
                </label>
                <select
                  id={`${surfaceIdRef.current}-sql-dialect`}
                  className="sr-input"
                  value={clientSqlDialect}
                  onChange={(e) => setClientSqlDialect(Number(e.target.value) || 3)}
                >
                  <option value={3}>{gettext('Dialect 3 — Modern SQL')}</option>
                  <option value={1}>{gettext('Dialect 1 — Legacy')}</option>
                </select>
              </div>
              <label style={{display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.82rem'}}>
                <input
                  type="checkbox"
                  checked={collectStatistics}
                  onChange={(e) => setCollectStatistics(e.target.checked)}
                />
                {gettext('Capture attachment MON$ query statistics on single-statement runs')}
              </label>
              <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
                <Button
                  size="small"
                  onClick={() => {
                    setLimitsModalOpen(false);
                    setProfilerConsentOpen(true);
                  }}
                >
                  {gettext('Run Profiled Statement (RDB$PROFILER)…')}
                </Button>
                <Button
                  size="small"
                  onClick={() => {
                    setLimitsModalOpen(false);
                    setSessionToolsTab('eds_pool');
                    setSessionToolsOpen(true);
                  }}
                >
                  {gettext('EDS Pool / Traps / Stream Reader…')}
                </Button>
              </div>
            </>
          )}
          <label style={{display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.82rem'}}>
            <input
              type="checkbox"
              checked={historySensitive}
              onChange={(e) => setHistorySensitive(e.target.checked)}
            />
            {gettext('Suppress SQL source from persistent history (sensitive literals)')}
          </label>
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

      {isFirebird && (
        <>
          <SqlProfilerConsentDialog
            open={profilerConsentOpen}
            busy={executing}
            onClose={() => setProfilerConsentOpen(false)}
            onConfirm={() => {
              setProfilerConsentOpen(false);
              runSql('statement', false, {profileMode: true});
            }}
          />
          <SqlFirebirdSessionToolsDialog
            open={sessionToolsOpen}
            onClose={() => setSessionToolsOpen(false)}
            post={post}
            databaseTargetId={databaseTargetId}
            sessionId={hostData?.session_id || null}
            ensureSession={ensureSurfaceSession}
            sqlSource={sqlText}
            clientSqlDialect={clientSqlDialect}
            initialTab={sessionToolsTab}
            onExecuteTrapSql={(trapSql) => {
              setSqlText(trapSql);
              editorRef.current?.setValue?.(trapSql);
              dispatchExecution({
                mode: 'statement',
                sqlSource: trapSql,
                selectionText: trapSql,
                cursorOffset: 0,
              });
            }}
          />
        </>
      )}
      {isMySQL && (
        <>
          <SqlMySQLQueryAttributesDialog
            open={mysqlAttributesOpen}
            attributesObject={mysqlQueryAttrs}
            transaction={hostData?.transaction || null}
            onSaveAttributes={setMysqlQueryAttrs}
            onClose={() => setMysqlAttributesOpen(false)}
          />
          <SqlMySQLAnalyzeConsentDialog
            open={mysqlAnalyzeConsentOpen}
            busy={executing}
            onClose={() => setMysqlAnalyzeConsentOpen(false)}
            onConfirm={() => {
              setMysqlAnalyzeConsentOpen(false);
              runSql('statement', false, {analyzeMode: true});
            }}
          />
        </>
      )}
      {isMariaDB && (
        <>
          <SqlMariaDBSessionDialog
            open={mariadbSessionOpen}
            transaction={hostData?.transaction || null}
            callHost={callHost}
            onClose={() => setMariadbSessionOpen(false)}
          />
          <SqlMariaDBAnalyzeConsentDialog
            open={mariadbAnalyzeConsentOpen}
            busy={executing}
            onClose={() => setMariadbAnalyzeConsentOpen(false)}
            onConfirm={() => {
              setMariadbAnalyzeConsentOpen(false);
              runSql('statement', false, {analyzeMode: true});
            }}
          />
        </>
      )}
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
  initialSessionToolsTab: PropTypes.string,
  post: PropTypes.func.isRequired,
};
