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
import {Box, Divider, Panel, ScrollArea, Stack} from '../../primitives/Layout';
import {Badge, Banner} from '../../feedback/Indicators';
import {Button} from '../../primitives/Button';
import {NumberField, SecretField, TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {Dialog} from '../../overlays/Dialog';
import {StatusBadge} from '../../status/StatusBadge';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import CodeEditor from '../../editors/CodeEditor';
import FormReference from '../../navigation/FormReference';
import {
  useQueryExecutionController,
  QueryExecutionToolbarCluster,
  QueryStepStatusFooter,
} from '../../query';
import {DDNViewerSurface} from './DDNViewerSurface';
import {
  DesignCheckpointHistoryDrawer,
  DesignerModalTabs,
  DesignerTabbedMenu,
  FormGrid,
  KeyValuePairsEditor,
  TypedRowsEditor,
  WhereUsedDialog,
} from './DesignerChrome';
import {
  DesignStoreClient,
  SharedDDNTaskController,
} from './sharedDesignLibrary';

const CHART_TYPE_OPTIONS = Object.freeze([
  {value: 'bar', label: 'Bar (chart.basic@1)'},
  {value: 'line', label: 'Line (chart.basic@1)'},
  {value: 'area', label: 'Area (chart.basic@1)'},
  {value: 'pie', label: 'Pie (chart.basic@1)'},
  {value: 'kpi', label: 'KPI (chart.gauge@1)'},
  {value: 'table', label: 'Table (table.records@1)'},
  {value: 'funnel', label: 'Funnel (chart.basic@1)'},
  {value: 'scatter', label: 'Scatter (chart.basic@1)'},
  {value: 'metric', label: 'Gauge / Metric (chart.gauge@1)'},
  {value: 'pivot', label: 'Pivot (table.records@1)'},
  {value: 'histogram', label: 'Histogram (chart.histogram@1)'},
  {value: 'timeline', label: 'Timeline (timeline.basic@1)'},
  {value: 'graph', label: 'Graph (chart.force@1)'},
  {value: 'vector-neighbors', label: 'Vector Neighbors (chart.dotplot@1)'},
]);

const DIALECT_OPTIONS = Object.freeze([
  {value: 'sqlite', label: 'SQLite'},
  {value: 'duckdb', label: 'DuckDB'},
  {value: 'postgresql', label: 'PostgreSQL'},
  {value: 'firebird', label: 'Firebird 5'},
  {value: 'mysql', label: 'MySQL'},
  {value: 'mariadb', label: 'MariaDB'},
]);

const NUMBER_FORMAT_OPTIONS = Object.freeze([
  {value: 'standard', label: 'Standard (1,234.56)'},
  {value: 'currency', label: 'Currency ($1,234.56)'},
  {value: 'percent', label: 'Percent (12.3%)'},
  {value: 'compact', label: 'Compact (1.2K / 3.4M)'},
]);

const CURRENCY_CODE_OPTIONS = Object.freeze([
  {value: 'USD', label: 'USD ($)'},
  {value: 'EUR', label: 'EUR (€)'},
  {value: 'GBP', label: 'GBP (£)'},
  {value: 'CAD', label: 'CAD (CA$)'},
]);

const DATE_GRAIN_OPTIONS = Object.freeze([
  {value: 'auto', label: 'Auto'},
  {value: 'day', label: 'Day'},
  {value: 'week', label: 'Week'},
  {value: 'month', label: 'Month'},
  {value: 'quarter', label: 'Quarter'},
  {value: 'year', label: 'Year'},
]);

const AGG_FUNCTION_OPTIONS = Object.freeze([
  {value: 'sum', label: 'SUM'},
  {value: 'count', label: 'COUNT'},
  {value: 'avg', label: 'AVG'},
  {value: 'min', label: 'MIN'},
  {value: 'max', label: 'MAX'},
  {value: 'count_distinct', label: 'COUNT DISTINCT'},
]);

const FILTER_OPERATOR_OPTIONS = Object.freeze([
  {value: 'eq', label: '='},
  {value: 'ne', label: '!='},
  {value: 'gt', label: '>'},
  {value: 'gte', label: '>='},
  {value: 'lt', label: '<'},
  {value: 'lte', label: '<='},
  {value: 'like', label: 'LIKE'},
  {value: 'in', label: 'IN'},
]);

const JOIN_TYPE_OPTIONS = Object.freeze([
  {value: 'inner', label: 'INNER JOIN'},
  {value: 'left', label: 'LEFT JOIN'},
  {value: 'right', label: 'RIGHT JOIN'},
]);

const JOIN_CARDINALITY_OPTIONS = Object.freeze([
  {value: 'many_to_one', label: 'many_to_one (safe)'},
  {value: 'one_to_one', label: 'one_to_one (safe)'},
  {value: 'one_to_many', label: 'one_to_many (fan-out risk)'},
  {value: 'many_to_many', label: 'many_to_many (fan-out risk)'},
]);

const CLICK_BEHAVIOR_OPTIONS = Object.freeze([
  {value: 'inherit', label: 'Inherit dashboard default'},
  {value: 'cross_filter', label: 'Cross-filter'},
  {value: 'highlight', label: 'Highlight'},
  {value: 'none', label: 'None'},
]);

const FILTER_SCOPE_OPTIONS = Object.freeze([
  {value: 'personal', label: 'Personal per-viewer state'},
  {value: 'author_pinned', label: 'Author-pinned shared default'},
]);

const ACTION_OPERATION_OPTIONS = Object.freeze([
  {value: 'update_row', label: 'Update Row (keyed parameterized UPDATE)'},
  {value: 'insert_row', label: 'Insert Row (parameterized INSERT)'},
  {value: 'delete_row', label: 'Delete Row (keyed parameterized DELETE)'},
  {value: 'provider_operation', label: 'Provider Native Operation'},
]);

const SNAPSHOT_MODE_OPTIONS = Object.freeze([
  {value: 'static', label: 'Static snapshot (never polls collector)'},
  {value: 'collector_read_only', label: 'Read-only live collector binding'},
]);

function statusTone(status) {
  if (status === 'accepted') return 'success';
  if (status === 'in_review') return 'warning';
  return 'info';
}

function resolveBiView(workspace, requestedView) {
  if (!workspace?.files) return workspace?.view || '';
  const entryText = workspace.files[workspace.entry] || '';
  if (
    requestedView &&
    (entryText.includes(`view "${requestedView}"`) ||
      entryText.includes(`view ${requestedView}`))
  ) {
    return requestedView;
  }
  return workspace.view;
}

function slugId(raw, fallback = 'item') {
  return (
    String(raw || '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_]+/g, '_')
      .replace(/^_+|_+$/g, '') || fallback
  );
}

function normalizeFilterMapValues(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj || {})) {
    if (typeof v === 'string' && v.trim().startsWith('[')) {
      try {
        out[k] = JSON.parse(v);
        continue;
      } catch {
        // keep string value
      }
    }
    out[k] = v;
  }
  return out;
}

function formatQuestionCellValue(value, fmt) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'number' && Number.isFinite(value)) {
    const f = fmt || {};
    const dec = Number.isInteger(f.decimals) ? f.decimals : 2;
    const symbols = {USD: '$', EUR: '€', GBP: '£', CAD: 'CA$'};
    if (f.number_format === 'currency') {
      const sym = symbols[f.currency_code || 'USD'] || '$';
      return `${sym}${value.toFixed(dec)}`;
    }
    if (f.number_format === 'percent') {
      return `${(value * 100).toFixed(dec)}%`;
    }
    if (f.number_format === 'compact') {
      const abs = Math.abs(value);
      if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(Math.min(dec, 2))}M`;
      if (abs >= 1_000) return `${(value / 1_000).toFixed(Math.min(dec, 2))}K`;
    }
    return Number.isInteger(value) && dec === 0 ? String(value) : value.toFixed(dec);
  }
  return String(value);
}

function defaultVisFormat(raw) {
  return {
    number_format: raw?.number_format || 'standard',
    currency_code: raw?.currency_code || 'USD',
    decimals: Number.isInteger(raw?.decimals) ? raw.decimals : 2,
    date_grain: raw?.date_grain || 'auto',
    x_axis_label: raw?.x_axis_label || '',
    y_axis_label: raw?.y_axis_label || '',
    show_accessible_table_default: Boolean(raw?.show_accessible_table_default),
  };
}

function mergeKeyValueChange(prevObj, nextObj, prefix = 'param') {
  const prev = prevObj || {};
  const next = nextObj || {};
  const prevEntries = Object.entries(prev);
  const nextEntries = Object.entries(next);
  if (
    prevEntries.length === nextEntries.length &&
    prevEntries.every(
      ([k, v], idx) =>
        nextEntries[idx]?.[0] === k && nextEntries[idx]?.[1] === v
    )
  ) {
    let idx = prevEntries.length + 1;
    while (Object.prototype.hasOwnProperty.call(next, `${prefix}_${idx}`)) {
      idx += 1;
    }
    return {...next, [`${prefix}_${idx}`]: ''};
  }
  return next;
}

export function BIDesignerSurface({
  projectId,
  designId,
  kind = 'question',
  client: suppliedClient,
  controller: suppliedController,
  readOnly = false,
  executeCommand,
  onStateChange,
  onExport,
  onError,
}) {
  const client = useMemo(
    () => suppliedClient ?? new DesignStoreClient(),
    [suppliedClient]
  );
  const controller = useMemo(
    () =>
      suppliedController ??
      new SharedDDNTaskController({
        client,
        projectId,
        designId,
        kind,
      }),
    [suppliedController, client, projectId, designId, kind]
  );

  const callbacks = useRef({executeCommand, onStateChange, onExport, onError});
  callbacks.current = {executeCommand, onStateChange, onExport, onError};
  const biQueryController = useQueryExecutionController({
    engine: 'postgresql',
  });

  const [sessionState, setSessionState] = useState(() => controller.state());
  const [biPayload, setBiPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [surfaceError, setSurfaceError] = useState('');
  const [bannerMessage, setBannerMessage] = useState('');
  const [activeMenuTab, setActiveMenuTab] = useState('design');
  const [activeView, setActiveView] = useState('');
  const [showAccessibleTable, setShowAccessibleTable] = useState(false);
  const [showCrossFilterBar, setShowCrossFilterBar] = useState(true);

  // Dashboard interactive filter & cross-filter state
  const [activeDashFilters, setActiveDashFilters] = useState({});
  const [activeCrossFilters, setActiveCrossFilters] = useState({});
  const [cardClickOverrides, setCardClickOverrides] = useState({});
  const [drillContextResult, setDrillContextResult] = useState(null);

  // Shared Checkpoint History & Where Used dialogs
  const [checkpointOpen, setCheckpointOpen] = useState(false);
  const [whereUsedOpen, setWhereUsedOpen] = useState(false);

  // Structured SBsql Query & Parameters modal (`bi-designer-query`)
  const [queryOpen, setQueryOpen] = useState(false);
  const [queryModalTab, setQueryModalTab] = useState('joins');
  const [queryDraft, setQueryDraft] = useState({
    schema: 'main',
    table: 'orders',
    alias: 'orders',
    joinRows: [],
    dimensionRows: [],
    metricRows: [],
    filterRows: [],
    paramRows: [],
    limit: 100,
    endpointId: 'default-endpoint',
  });

  // Chart Axis & Number Formatters modal (`bi-designer-chart`)
  const [formatOpen, setFormatOpen] = useState(false);
  const [formatDraft, setFormatDraft] = useState(() => defaultVisFormat(null));

  // SQL Bridge modal (`bi-designer-query` / `bi-designer-import`)
  const [sqlOpen, setSqlOpen] = useState(false);
  const [sqlModalTab, setSqlModalTab] = useState('compile');
  const [sqlDraft, setSqlDraft] = useState({
    dialect: 'sqlite',
    compiledSql: '',
    boundParams: [],
    parameterValues: {},
    importSql: '',
    fidelity: '',
    lossItems: [],
    convertedQuestion: null,
  });
  const importSqlRef = useRef('');
  importSqlRef.current = sqlDraft.importSql;

  // BYOK AI Draft modal
  const [aiOpen, setAiOpen] = useState(false);
  const [aiDraft, setAiDraft] = useState({
    prompt: '',
    byokApiKey: '',
    result: null,
  });

  // Dashboard Cards & Layout modal
  const [cardOpen, setCardOpen] = useState(false);
  const [cardModalTab, setCardModalTab] = useState('manage');
  const [cardRows, setCardRows] = useState([]);
  const [cardDraft, setCardDraft] = useState({
    title: '',
    tabId: 'main',
    type: 'question',
    questionDesignId: '',
    pinnedVersion: 1,
    followLatestAccepted: false,
    visType: 'bar',
    clickBehavior: 'inherit',
    markdown: '',
    panelId: '',
    snapshotMode: 'static',
    collectorEngine: 'postgresql',
    collectorServerId: 1,
    collectorTargetId: '',
    collectorMetricGroup: 'throughput',
    collectorMetricKeyRows: [{metric_key: 'tps'}, {metric_key: 'active_sessions'}],
    collectorFreshnessBudget: 60,
  });

  // Dashboard Interaction & Pinned Filters modal
  const [interactionOpen, setInteractionOpen] = useState(false);
  const [interactionDraft, setInteractionDraft] = useState({
    defaultClickBehavior: 'cross_filter',
    autoApplyFilters: true,
    filterStateScope: 'personal',
    drillCarriesFilterContext: true,
    filterRows: [],
  });

  // Dashboard Write-Back Action Buttons & Native Operation Review modal
  const [actionBtnOpen, setActionBtnOpen] = useState(false);
  const [actionModalTab, setActionModalTab] = useState('review');
  const [actionBtnDraft, setActionBtnDraft] = useState({
    label: '',
    operationKind: 'update_row',
    targetEndpointId: 'default-endpoint',
    targetSchema: 'public',
    targetTable: 'orders',
    keyColumnRows: [{column: 'order_id'}],
    bindingRows: [
      {name: 'order_id', column: 'order_id', source: 'filter', source_ref: 'order_id', type: 'integer'},
      {name: 'status', column: 'status', source: 'prompt', source_ref: 'status', type: 'string'},
    ],
    selectedActionId: '',
    dialect: 'postgresql',
    promptValues: {},
    reviewResult: null,
  });

  // Read-only Collector Snapshot inspector modal
  const [collectorOpen, setCollectorOpen] = useState(false);
  const [collectorDraft, setCollectorDraft] = useState({
    cardId: '',
    snapshotResult: null,
  });

  // Accept dialog
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [acceptDraft, setAcceptDraft] = useState({
    approvalRef: '',
    comment: '',
  });

  // Outward Effects & Kiosk Device Fleet modal (`bi-designer-outward`)
  const [outwardOpen, setOutwardOpen] = useState(false);
  const [outwardTab, setOutwardTab] = useState('subscriptions');
  const [outwardDraft, setOutwardDraft] = useState({
    subscriptionEnabled: true,
    schedule: 'daily',
    recipientRows: [],
    webhookRows: [],
    embedEnabled: true,
    allowedOriginRows: [],
    serverEnabled: true,
    publisherUserId: 1,
    lockedFilters: {},
    reviewResult: null,
    publicationId: '',
    deviceLabel: 'lobby-kiosk',
    deviceExpiresAt: '',
    mintedToken: '',
    kioskUrl: '',
    fleetTokens: [],
  });

  // Git Sync modal
  const [gitOpen, setGitOpen] = useState(false);
  const [gitDraft, setGitDraft] = useState({
    repoRoot: '',
    path: 'bi/design.ddn',
    branch: 'main',
    note: '',
    driftResult: null,
  });

  const runToolbarCommand = useCallback((id, fn) => {
    if (callbacks.current.executeCommand) {
      return callbacks.current.executeCommand(id, {enabled: true, invoke: fn});
    }
    return fn();
  }, []);

  const refreshAll = useCallback(
    async (version = null) => {
      setLoading(true);
      setSurfaceError('');
      try {
        const nextState = await controller.load({version});
        const biData = await controller.getBiModel({
          version: nextState.currentVersion,
        });
        setSessionState(nextState);
        setBiPayload(biData);
        const qFmt = biData?.bi?.question?.visualization_format;
        if (qFmt) {
          setFormatDraft(defaultVisFormat(qFmt));
          if (qFmt.show_accessible_table_default) {
            setShowAccessibleTable(true);
          }
        }
        setActiveView((cur) => {
          if (cur) return cur;
          return biData?.bi_kind === 'dashboard'
            ? 'dashboard_composed'
            : 'question_chart';
        });
        callbacks.current.onStateChange?.(nextState);
      } catch (err) {
        const msg = err?.message || 'Unable to load BI design.';
        setSurfaceError(msg);
        callbacks.current.onError?.(err);
      } finally {
        setLoading(false);
      }
    },
    [controller]
  );

  useEffect(() => {
    const unsub = controller.subscribe((next) => {
      setSessionState(next);
      callbacks.current.onStateChange?.(next);
    });
    refreshAll();
    return unsub;
  }, [controller, refreshAll]);

  const biKind = biPayload?.bi_kind || sessionState.kind || kind;
  const questionModel =
    biKind === 'question' ? biPayload?.bi?.question || null : null;
  const dashboardModel =
    biKind === 'dashboard' ? biPayload?.bi?.dashboard || null : null;
  const outwardEffects = biPayload?.outward_effects || [];

  const viewOptions = useMemo(() => {
    if (biKind === 'dashboard') {
      const tabViews = (dashboardModel?.tabs || []).map((t) => ({
        value: `dashboard_tab_${t.id}`,
        label: `Tab: ${t.name}`,
      }));
      return [
        {value: 'dashboard_composed', label: 'Composed Dashboard'},
        ...tabViews,
        {value: 'dashboard_wiring', label: 'Wiring & Lineage'},
      ];
    }
    return [
      {value: 'question_chart', label: 'Chart Surface'},
      {value: 'question_lineage', label: 'Query Lineage'},
    ];
  }, [biKind, dashboardModel]);

  const viewerWorkspace = useMemo(() => {
    if (!sessionState.workspace) return null;
    const target = resolveBiView(sessionState.workspace, activeView);
    return {...sessionState.workspace, view: target};
  }, [sessionState.workspace, activeView]);

  const fanoutWarnings = questionModel?.review_flags?.fanout_warnings || [];
  const savedFilterFlags =
    questionModel?.review_flags?.saved_filter_values ||
    dashboardModel?.review_flags?.saved_filter_values ||
    [];
  const staticMetricCards = (dashboardModel?.cards || []).filter(
    (c) =>
      c.type === 'metric_panel' &&
      (c.metric_panel?.snapshot_mode || 'static') === 'static'
  );
  const collectorMetricCards = (dashboardModel?.cards || []).filter(
    (c) =>
      c.type === 'metric_panel' &&
      c.metric_panel?.snapshot_mode === 'collector_read_only'
  );
  const allMetricCards = (dashboardModel?.cards || []).filter(
    (c) => c.type === 'metric_panel'
  );
  const actionButtons = dashboardModel?.action_buttons || [];

  const accessibleTableData = useMemo(() => {
    if (biKind === 'question' && questionModel) {
      const qblock = questionModel.query || {};
      const headers =
        qblock.kind === 'sbsql'
          ? [
            ...(qblock.sbsql?.columns || []).map((c) => c.alias),
            ...(qblock.sbsql?.measures || []).map((m) => m.alias),
          ]
          : ['label', 'value'];
      const effectiveHeaders = headers.length ? headers : ['label', 'value'];
      const rawRows = questionModel.preview_rows?.length
        ? questionModel.preview_rows
        : [effectiveHeaders.map((_, i) => (i === 0 ? 'Sample A' : 10))];
      const fmt = questionModel.visualization_format || formatDraft;
      const rows = rawRows.map((r) =>
        effectiveHeaders.map((_, idx) => formatQuestionCellValue(r[idx], fmt))
      );
      return {headers: effectiveHeaders, rows};
    }
    if (biKind === 'dashboard' && dashboardModel) {
      return {
        headers: ['Card', 'Type', 'Click Override', 'Tab'],
        rows: (dashboardModel.cards || []).map((c) => [
          c.title || c.id,
          c.type,
          cardClickOverrides[c.id] || c.click_behavior || 'inherit',
          c.tab_id || 'main',
        ]),
      };
    }
    return {headers: ['Column'], rows: []};
  }, [biKind, questionModel, dashboardModel, formatDraft, cardClickOverrides]);

  // -----------------------------------------------------------------------
  // Design Lifecycle Handlers
  // -----------------------------------------------------------------------

  const handleSaveDraft = async () => {
    setBusy(true);
    setSurfaceError('');
    try {
      if (biKind === 'question' && questionModel) {
        await controller.saveBiModel({
          question: questionModel,
          status:
            sessionState.status === 'accepted' ? 'draft' : sessionState.status,
          note: 'Saved BI question checkpoint',
        });
      } else if (biKind === 'dashboard' && dashboardModel) {
        await controller.saveBiModel({
          dashboard: dashboardModel,
          status:
            sessionState.status === 'accepted' ? 'draft' : sessionState.status,
          note: 'Saved BI dashboard checkpoint',
        });
      } else {
        await controller.save({note: 'Saved BI design checkpoint'});
      }
      await refreshAll();
      setBannerMessage('Saved BI checkpoint.');
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleAdvanceStatus = async (targetStatus) => {
    setBusy(true);
    setSurfaceError('');
    try {
      await controller.advanceStatus(targetStatus);
      await refreshAll();
      setBannerMessage(`Advanced status to ${targetStatus}.`);
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleBranchDraft = async () => {
    setBusy(true);
    setSurfaceError('');
    try {
      if (biKind === 'question' && questionModel) {
        await controller.saveBiModel({
          question: questionModel,
          status: 'draft',
          note: 'Branched new draft from accepted version',
        });
      } else if (biKind === 'dashboard' && dashboardModel) {
        await controller.saveBiModel({
          dashboard: dashboardModel,
          status: 'draft',
          note: 'Branched new draft from accepted version',
        });
      }
      await refreshAll();
      setBannerMessage('Created new editable draft checkpoint.');
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleAcceptConfirm = async () => {
    setBusy(true);
    setSurfaceError('');
    try {
      const res = await controller.accept({
        gitReviewRef: acceptDraft.approvalRef.trim() || null,
        comment: acceptDraft.comment.trim() || null,
      });
      setAcceptOpen(false);
      const outwardFlag = res?.outward_effects_activated ?? false;
      setBannerMessage(
        `Version accepted. Outward effects activated: ${String(outwardFlag)}.`
      );
      await refreshAll();
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleExportDdn = async () => {
    setBusy(true);
    setSurfaceError('');
    try {
      if (typeof client.exportDesign === 'function') {
        const exported = await client.exportDesign(projectId, designId, {
          version: sessionState.currentVersion,
        });
        callbacks.current.onExport?.(exported);
      } else {
        callbacks.current.onExport?.({
          ddn_text:
            sessionState.workspace?.files?.[sessionState.workspace?.entry] || '',
        });
      }
      setBannerMessage('Exported BI DDN text.');
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  // -----------------------------------------------------------------------
  // Structured Query Builder & Parameters (`bi-designer-query`)
  // -----------------------------------------------------------------------

  const openQueryBuilder = (initialTab = 'joins') => {
    const sbsql = questionModel?.query?.sbsql || {
      from: {relation: ['main', 'orders'], alias: 'orders'},
      joins: [],
      columns: [{column: ['orders', 'region'], alias: 'region'}],
      measures: [{function: 'sum', column: ['orders', 'amount'], alias: 'total_amount'}],
      filters: [],
      limit: 100,
    };
    const rel = sbsql.from?.relation || ['main', 'orders'];
    const baseAlias = sbsql.from?.alias || rel[rel.length - 1] || 'orders';
    setQueryDraft({
      schema: rel.length > 1 ? rel[0] : 'main',
      table: rel[rel.length - 1] || 'orders',
      alias: baseAlias,
      joinRows: (sbsql.joins || []).map((j) => ({
        join_type: j.type || 'left',
        schema: j.relation?.length > 1 ? j.relation[0] : 'main',
        table: j.relation?.[j.relation.length - 1] || '',
        alias: j.alias || '',
        cardinality: j.cardinality || 'many_to_one',
        left_col: (j.on?.[0]?.left || []).join('.'),
        right_col: (j.on?.[0]?.right || []).join('.'),
      })),
      dimensionRows: (sbsql.columns || []).map((c) => ({
        table_alias: c.column?.[0] || baseAlias,
        column_name: c.column?.[c.column.length - 1] || '',
        alias: c.alias || '',
      })),
      metricRows: (sbsql.measures || []).map((m) => ({
        func: m.function || 'sum',
        table_alias: m.column?.[0] || baseAlias,
        column_name: m.column?.[m.column.length - 1] || '',
        alias: m.alias || '',
      })),
      filterRows: (sbsql.filters || []).map((f) => ({
        table_alias: f.column?.[0] || baseAlias,
        column_name: f.column?.[f.column.length - 1] || '',
        operator: f.operator || 'eq',
        param_or_value: f.parameter ? `:${f.parameter}` : String(f.value ?? ''),
        flag_for_review: !f.parameter && f.value !== undefined && f.value !== '',
      })),
      paramRows: (questionModel?.parameters || []).map((p) => ({
        id: p.id || '',
        name: p.name || '',
        type: p.type || 'string',
        required: Boolean(p.required),
        default_val: p.default !== undefined && p.default !== null ? String(p.default) : '',
      })),
      limit: Number(sbsql.limit || 100),
      endpointId: questionModel?.endpoint_id || 'default-endpoint',
    });
    setQueryModalTab(initialTab);
    setQueryOpen(true);
  };

  const draftHasFanoutJoin = useMemo(
    () =>
      queryDraft.joinRows.some(
        (j) =>
          j.cardinality === 'one_to_many' || j.cardinality === 'many_to_many'
      ),
    [queryDraft.joinRows]
  );

  const applyStructuredQuery = async () => {
    setBusy(true);
    setSurfaceError('');
    try {
      const baseAlias = slugId(queryDraft.alias || queryDraft.table, 'tbl');
      const fromRel = queryDraft.schema.trim()
        ? [queryDraft.schema.trim(), queryDraft.table.trim() || 'orders']
        : [queryDraft.table.trim() || 'orders'];

      const joins = queryDraft.joinRows
        .filter((j) => String(j.table || '').trim())
        .map((j, idx) => {
          const jAlias = slugId(j.alias || j.table, `j_${idx + 1}`);
          const leftParts = String(j.left_col || `${baseAlias}.id`)
            .split('.')
            .filter(Boolean);
          const rightParts = String(j.right_col || `${jAlias}.id`)
            .split('.')
            .filter(Boolean);
          return {
            type: j.join_type || 'left',
            relation: j.schema?.trim()
              ? [j.schema.trim(), j.table.trim()]
              : [j.table.trim()],
            alias: jAlias,
            cardinality: j.cardinality || 'many_to_one',
            on: [
              {
                left: leftParts.length >= 2 ? leftParts.slice(-2) : [baseAlias, leftParts[0] || 'id'],
                op: '=',
                right: rightParts.length >= 2 ? rightParts.slice(-2) : [jAlias, rightParts[0] || 'id'],
              },
            ],
          };
        });

      const columns = queryDraft.dimensionRows
        .filter((d) => String(d.column_name || '').trim())
        .map((d) => ({
          column: [
            String(d.table_alias || baseAlias).trim(),
            String(d.column_name).trim(),
          ],
          alias: slugId(d.alias || d.column_name, 'dim'),
        }));

      const measures = queryDraft.metricRows
        .filter((m) => String(m.func || '').trim())
        .map((m, idx) => {
          const colClean = String(m.column_name || '').trim();
          const hasCol = colClean && colClean !== '*';
          return {
            function: m.func || 'sum',
            column: hasCol
              ? [String(m.table_alias || baseAlias).trim(), colClean]
              : null,
            alias: slugId(
              m.alias || `${m.func}_${colClean || 'rows'}`,
              `metric_${idx + 1}`
            ),
          };
        });

      const filters = queryDraft.filterRows
        .filter((f) => String(f.column_name || '').trim())
        .map((f) => {
          const rawTarget = String(f.param_or_value ?? '').trim();
          const colSpec = [
            String(f.table_alias || baseAlias).trim(),
            String(f.column_name).trim(),
          ];
          if (rawTarget.startsWith(':') && !f.flag_for_review) {
            return {
              column: colSpec,
              operator: f.operator || 'eq',
              parameter: slugId(rawTarget.slice(1), 'param'),
            };
          }
          return {
            column: colSpec,
            operator: f.operator || 'eq',
            value: rawTarget,
          };
        });

      const parameters = queryDraft.paramRows
        .filter((p) => String(p.id || p.name || '').trim())
        .map((p, idx) => {
          const entry = {
            id: slugId(p.id || p.name, `param_${idx + 1}`),
            name: String(p.name || p.id || `Parameter ${idx + 1}`),
            type: p.type || 'string',
            required: Boolean(p.required),
          };
          if (String(p.default_val || '').trim() !== '') {
            entry.default = String(p.default_val).trim();
          }
          return entry;
        });

      const nextQuestion = {
        ...(questionModel || {}),
        name: questionModel?.name || sessionState.title || 'Question',
        endpoint_id: queryDraft.endpointId.trim() || 'default-endpoint',
        query: {
          kind: 'sbsql',
          sbsql: {
            dialect: 'sbsql@1',
            from: {relation: fromRel, alias: baseAlias},
            joins,
            columns,
            measures: measures.length
              ? measures
              : [{function: 'count', column: null, alias: 'row_count'}],
            filters,
            limit: Number(queryDraft.limit) || 100,
          },
        },
        parameters,
        visualization: questionModel?.visualization || {type: 'bar', settings: {}},
        visualization_format:
          questionModel?.visualization_format || formatDraft,
      };

      await controller.saveBiModel({
        question: nextQuestion,
        status: 'draft',
        note: 'Updated structured SBsql query model',
      });
      setQueryOpen(false);
      await refreshAll();
      setBannerMessage('Saved structured SBsql query checkpoint.');
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  // -----------------------------------------------------------------------
  // Chart Profile & Rich Formatters (`bi-designer-chart`)
  // -----------------------------------------------------------------------

  const handleChartProfileChange = async (nextType) => {
    if (!questionModel || readOnly) return;
    setBusy(true);
    setSurfaceError('');
    try {
      const nextQuestion = {
        ...questionModel,
        visualization: {
          ...(questionModel.visualization || {}),
          type: nextType,
        },
      };
      await controller.saveBiModel({
        question: nextQuestion,
        status: 'draft',
        note: `Changed BI chart profile to ${nextType}`,
      });
      await refreshAll();
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const applyVisualizationFormat = async () => {
    setBusy(true);
    setSurfaceError('');
    try {
      const normalized = {
        number_format: formatDraft.number_format,
        currency_code: formatDraft.currency_code,
        decimals: Math.max(0, Math.min(4, Number(formatDraft.decimals) || 0)),
        date_grain: formatDraft.date_grain,
        x_axis_label: String(formatDraft.x_axis_label || '').trim(),
        y_axis_label: String(formatDraft.y_axis_label || '').trim(),
        show_accessible_table_default: Boolean(
          formatDraft.show_accessible_table_default
        ),
      };
      if (biKind === 'question' && questionModel) {
        await controller.saveBiModel({
          question: {
            ...questionModel,
            visualization_format: normalized,
          },
          status: 'draft',
          note: 'Updated chart axis & number formatters',
        });
        await refreshAll();
      }
      if (normalized.show_accessible_table_default) {
        setShowAccessibleTable(true);
      }
      setFormatOpen(false);
      setBannerMessage('Saved axis, number, currency & date formatters.');
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  // -----------------------------------------------------------------------
  // SQL Bridge, Open in SQL Editor & BYOK AI Draft
  // -----------------------------------------------------------------------

  const runCompileSql = useCallback(
    async (dialectOverride, paramValsOverride) => {
      const targetDialect = dialectOverride ?? sqlDraft.dialect;
      const paramVals = paramValsOverride ?? sqlDraft.parameterValues;
      setBusy(true);
      setSurfaceError('');
      try {
        const res = await controller.biSqlBridge({
          action: 'compile_sql',
          dialect: targetDialect,
          parameterValues: paramVals,
        });
        setSqlDraft((cur) => ({
          ...cur,
          dialect: targetDialect,
          compiledSql: res?.sql || '',
          boundParams: res?.parameters || [],
        }));
        return res;
      } catch (err) {
        setSurfaceError(err?.message || String(err));
        return null;
      } finally {
        setBusy(false);
      }
    },
    [controller, sqlDraft.dialect, sqlDraft.parameterValues]
  );

  const openSqlModal = async (tab = 'compile') => {
    setSqlModalTab(tab);
    setSqlOpen(true);
    if (tab === 'compile' && biKind === 'question') {
      await runCompileSql(sqlDraft.dialect, sqlDraft.parameterValues);
    }
  };

  const handleOpenInSqlEditor = async () => {
    let sqlText = sqlDraft.compiledSql;
    let params = sqlDraft.boundParams;
    if (!sqlText && biKind === 'question') {
      const compiled = await runCompileSql(
        sqlDraft.dialect,
        sqlDraft.parameterValues
      );
      sqlText = compiled?.sql || '';
      params = compiled?.parameters || [];
    }
    const detail = {
      sql: sqlText || '-- Compiled BI query',
      dialect: sqlDraft.dialect || 'sqlite',
      parameters: params,
      title: sessionState.title || questionModel?.name || 'BI Question',
    };
    window.dispatchEvent(
      new CustomEvent('cdeadmin:open-sql-in-editor', {detail})
    );
    setBannerMessage('Sent parameterized SQL to SQL Editor.');
  };

  const handleConvertSqlToQuestion = async () => {
    setBusy(true);
    setSurfaceError('');
    try {
      const res = await controller.biSqlBridge({
        action: 'from_sql',
        sql: sqlDraft.importSql,
        name: questionModel?.name || sessionState.title || 'SQL Question',
        endpointId: questionModel?.endpoint_id || 'default-endpoint',
      });
      setSqlDraft((cur) => ({
        ...cur,
        fidelity: res?.fidelity || 'exact',
        lossItems: res?.loss || [],
        convertedQuestion: res?.question || null,
      }));
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyConvertedSql = async () => {
    if (!sqlDraft.convertedQuestion) return;
    setBusy(true);
    setSurfaceError('');
    try {
      await controller.saveBiModel({
        question: sqlDraft.convertedQuestion,
        status: 'draft',
        note: `Imported SQL (${sqlDraft.fidelity || 'exact'} fidelity)`,
      });
      setSqlOpen(false);
      await refreshAll();
      setBannerMessage(
        `Applied SQL import (${sqlDraft.fidelity || 'exact'} fidelity).`
      );
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleProposeAiDraft = async () => {
    setBusy(true);
    setSurfaceError('');
    try {
      const res = await client.proposeBiAiDraft(projectId, {
        prompt: aiDraft.prompt,
        endpointId: questionModel?.endpoint_id || 'default-endpoint',
        targetDesignId: designId,
        byokApiKey: aiDraft.byokApiKey || null,
      });
      setAiDraft((cur) => ({...cur, result: res}));
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleApplyAiDraft = async () => {
    const proposed =
      aiDraft.result?.draft_question || aiDraft.result?.question || null;
    if (!proposed) return;
    setBusy(true);
    setSurfaceError('');
    try {
      await controller.saveBiModel({
        question: proposed,
        status: 'draft',
        note: 'Applied BYOK AI draft for human review',
      });
      setAiOpen(false);
      await refreshAll();
      setBannerMessage('Applied AI draft as unapproved Draft checkpoint.');
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  // -----------------------------------------------------------------------
  // Dashboard Cross-Filter, Drill-Through, Cards, Filters & Action Buttons
  // -----------------------------------------------------------------------

  const handleDrillThroughWithContext = async () => {
    const firstCard = dashboardModel?.cards?.[0];
    setBusy(true);
    setSurfaceError('');
    try {
      const res = await controller.biSqlBridge({
        action: 'drill_context',
        cardId: firstCard?.id || '',
        activeFilters: activeDashFilters,
        crossFilters: activeCrossFilters,
      });
      setDrillContextResult(res);
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const openDashboardCardsModal = () => {
    setCardRows(
      (dashboardModel?.cards || []).map((c) => ({
        id: c.id,
        title: c.title || c.id,
        type: c.type || 'question',
        tab_id: c.tab_id || 'main',
        click_behavior: c.click_behavior || 'inherit',
      }))
    );
    setCardModalTab('manage');
    setCardOpen(true);
  };

  const handleSaveCardList = async () => {
    if (!dashboardModel) return;
    setBusy(true);
    setSurfaceError('');
    try {
      const existingById = new Map(
        (dashboardModel.cards || []).map((c) => [c.id, c])
      );
      const updatedCards = cardRows.map((row, idx) => {
        const prev = existingById.get(row.id) || {
          id: slugId(row.id || row.title, `card_${idx + 1}`),
          type: 'text',
          text: {markdown: row.title || ''},
          layout: {x: (idx % 2) * 12, y: Math.floor(idx / 2) * 8, w: 12, h: 8},
        };
        return {
          ...prev,
          title: row.title || prev.title,
          tab_id: row.tab_id || 'main',
          click_behavior: row.click_behavior || 'inherit',
        };
      });
      await controller.saveBiModel({
        dashboard: {...dashboardModel, cards: updatedCards},
        status: 'draft',
        note: 'Updated dashboard cards & click behaviors',
      });
      setCardOpen(false);
      await refreshAll();
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleAddDashboardCard = async () => {
    if (!dashboardModel) return;
    setBusy(true);
    setSurfaceError('');
    try {
      const cid = slugId(
        cardDraft.title,
        `card_${(dashboardModel.cards || []).length + 1}`
      );
      let newCard = {
        id: cid,
        tab_id: cardDraft.tabId || 'main',
        type: cardDraft.type,
        title: cardDraft.title || cid,
        click_behavior: cardDraft.clickBehavior || 'inherit',
        layout: {
          x: ((dashboardModel.cards || []).length % 2) * 12,
          y: Math.floor((dashboardModel.cards || []).length / 2) * 8,
          w: 12,
          h: 8,
        },
      };
      if (cardDraft.type === 'question') {
        newCard = {
          ...newCard,
          question: {
            question_design_id: cardDraft.questionDesignId.trim(),
            pinned_version: Number(cardDraft.pinnedVersion) || 1,
            follow_latest_accepted: Boolean(cardDraft.followLatestAccepted),
          },
          visualization: {type: cardDraft.visType || 'bar'},
        };
      } else if (cardDraft.type === 'text') {
        newCard = {
          ...newCard,
          text: {markdown: cardDraft.markdown || ''},
        };
      } else {
        const mp = {
          panel_id: slugId(cardDraft.panelId || cid, 'panel'),
          snapshot_mode: cardDraft.snapshotMode,
          columns: [
            {id: 'measure', label: 'Measure'},
            {id: 'value', label: 'Value'},
          ],
          rows: [],
        };
        if (cardDraft.snapshotMode === 'collector_read_only') {
          mp.collector_binding = {
            engine: cardDraft.collectorEngine,
            server_id: Number(cardDraft.collectorServerId) || 1,
            target_id: cardDraft.collectorTargetId.trim() || null,
            metric_group: cardDraft.collectorMetricGroup.trim() || 'throughput',
            metric_keys: cardDraft.collectorMetricKeyRows
              .map((r) => String(r.metric_key || '').trim())
              .filter(Boolean),
            freshness_budget_seconds:
              Number(cardDraft.collectorFreshnessBudget) || 60,
          };
        }
        newCard = {...newCard, metric_panel: mp};
      }
      await controller.saveBiModel({
        dashboard: {
          ...dashboardModel,
          cards: [...(dashboardModel.cards || []), newCard],
        },
        status: 'draft',
        note: `Added ${cardDraft.type} card ${newCard.title}`,
      });
      setCardOpen(false);
      await refreshAll();
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const openFiltersAndPinningModal = () => {
    const inter = dashboardModel?.interaction || {};
    setInteractionDraft({
      defaultClickBehavior: inter.default_click_behavior || 'cross_filter',
      autoApplyFilters: inter.auto_apply_filters !== false,
      filterStateScope: inter.filter_state_scope || 'personal',
      drillCarriesFilterContext: inter.drill_carries_filter_context !== false,
      filterRows: (dashboardModel?.filters || []).map((f) => ({
        id: f.id,
        name: f.name || f.id,
        operator: f.operator || 'eq',
        default_val: f.default !== undefined && f.default !== null ? String(f.default) : '',
        pinned_by_author: Boolean(f.pinned_by_author),
      })),
    });
    setInteractionOpen(true);
  };

  const applyFiltersAndPinning = async () => {
    if (!dashboardModel) return;
    setBusy(true);
    setSurfaceError('');
    try {
      const filters = interactionDraft.filterRows
        .filter((f) => String(f.id || f.name || '').trim())
        .map((f, idx) => {
          const item = {
            id: slugId(f.id || f.name, `flt_${idx + 1}`),
            name: String(f.name || f.id || `Filter ${idx + 1}`),
            type: 'string',
            widget: 'select',
            operator: f.operator || 'eq',
            pinned_by_author: Boolean(f.pinned_by_author),
            targets: [],
          };
          if (String(f.default_val || '').trim() !== '') {
            item.default = String(f.default_val).trim();
          }
          return item;
        });
      await controller.saveBiModel({
        dashboard: {
          ...dashboardModel,
          filters,
          interaction: {
            default_click_behavior: interactionDraft.defaultClickBehavior,
            auto_apply_filters: Boolean(interactionDraft.autoApplyFilters),
            filter_state_scope: interactionDraft.filterStateScope,
            drill_carries_filter_context: Boolean(
              interactionDraft.drillCarriesFilterContext
            ),
          },
        },
        status: 'draft',
        note: 'Updated dashboard filters & pinning policy',
      });
      setInteractionOpen(false);
      await refreshAll();
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  // -----------------------------------------------------------------------
  // Collector Binding & Write-Back Action Buttons
  // -----------------------------------------------------------------------

  const openCollectorInspector = async () => {
    const preferred = collectorMetricCards[0] || allMetricCards[0] || null;
    const cid = preferred?.id || '';
    setCollectorDraft({cardId: cid, snapshotResult: null});
    setCollectorOpen(true);
    if (cid) {
      setBusy(true);
      try {
        const snap = await controller.readBiCollectorPanel({cardId: cid});
        setCollectorDraft({cardId: cid, snapshotResult: snap});
      } catch (err) {
        setSurfaceError(err?.message || String(err));
      } finally {
        setBusy(false);
      }
    }
  };

  const openActionButtonsModal = (tab = 'review') => {
    setActionBtnDraft((cur) => ({
      ...cur,
      selectedActionId:
        cur.selectedActionId || actionButtons[0]?.id || '',
    }));
    setActionModalTab(tab);
    setActionBtnOpen(true);
  };

  const handleAddActionButton = async () => {
    if (!dashboardModel) return;
    setBusy(true);
    setSurfaceError('');
    try {
      const aid = slugId(
        actionBtnDraft.label,
        `act_${actionButtons.length + 1}`
      );
      const newAction = {
        id: aid,
        label: actionBtnDraft.label.trim() || aid,
        operation_kind: actionBtnDraft.operationKind,
        capability_id: `table.${actionBtnDraft.operationKind}`,
        risk_class:
          actionBtnDraft.operationKind === 'delete_row'
            ? 'destructive'
            : 'write',
        target_endpoint_id:
          actionBtnDraft.targetEndpointId.trim() || 'default-endpoint',
        target_relation: [
          actionBtnDraft.targetSchema.trim() || 'public',
          actionBtnDraft.targetTable.trim() || 'orders',
        ],
        key_columns: actionBtnDraft.keyColumnRows
          .map((r) => String(r.column || '').trim())
          .filter(Boolean),
        parameter_bindings: actionBtnDraft.bindingRows
          .filter((b) => String(b.name || b.column || '').trim())
          .map((b) => ({
            name: slugId(b.name || b.column, 'param'),
            column: slugId(b.column || b.name, 'col'),
            source: b.source || 'prompt',
            source_ref: String(b.source_ref || b.name || '').trim(),
            type: b.type || 'string',
            required: true,
          })),
        approval_required: true,
      };
      await controller.saveBiModel({
        dashboard: {
          ...dashboardModel,
          action_buttons: [...actionButtons, newAction],
        },
        status: 'draft',
        note: `Added reviewed action button ${newAction.label}`,
      });
      setActionBtnDraft((cur) => ({...cur, selectedActionId: aid}));
      setActionModalTab('review');
      await refreshAll();
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRunActionReview = async (dryRun) => {
    const targetId =
      actionBtnDraft.selectedActionId || actionButtons[0]?.id || '';
    if (!targetId) return;
    setBusy(true);
    setSurfaceError('');
    try {
      const res = await controller.submitBiActionReview({
        actionButtonId: targetId,
        parameterValues: actionBtnDraft.promptValues,
        dialect: actionBtnDraft.dialect,
        dryRun,
      });
      setActionBtnDraft((cur) => ({...cur, reviewResult: res}));
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  // -----------------------------------------------------------------------
  // Outward Effects & Kiosk Device Fleet (`bi-designer-outward`)
  // -----------------------------------------------------------------------

  const refreshDeviceFleet = useCallback(async () => {
    if (typeof client.listBiDeviceTokens !== 'function') return;
    try {
      const res = await controller.listBiDeviceTokens();
      setOutwardDraft((cur) => ({
        ...cur,
        fleetTokens: res?.tokens || [],
        publicationId:
          cur.publicationId || res?.active_publication_id || '',
      }));
    } catch {
      // ignore if design has no tokens yet
    }
  }, [client, controller]);

  const openOutwardModal = async (tab = 'subscriptions') => {
    const pubEff = outwardEffects.find(
      (e) => e.effect_kind === 'dashboard_server' && e.enabled
    );
    setOutwardDraft((cur) => ({
      ...cur,
      publicationId: pubEff?.id || cur.publicationId || '',
    }));
    setOutwardTab(tab);
    setOutwardOpen(true);
    if (biKind === 'dashboard') {
      await refreshDeviceFleet();
    }
  };

  const handleReviewOutwardSwitch = async (effectKind) => {
    setBusy(true);
    setSurfaceError('');
    try {
      let enabled = true;
      let config = {};
      let publisherUserId = null;
      if (effectKind === 'subscription') {
        enabled = Boolean(outwardDraft.subscriptionEnabled);
        config = {
          schedule: outwardDraft.schedule || 'daily',
          recipients: outwardDraft.recipientRows
            .map((r) => String(r.recipient || '').trim())
            .filter(Boolean),
          webhooks: outwardDraft.webhookRows
            .map((w) => String(w.url || '').trim())
            .filter(Boolean),
        };
      } else if (effectKind === 'embed') {
        enabled = Boolean(outwardDraft.embedEnabled);
        config = {
          allowed_origins: outwardDraft.allowedOriginRows
            .map((o) => String(o.origin || '').trim())
            .filter(Boolean),
        };
      } else {
        enabled = Boolean(outwardDraft.serverEnabled);
        publisherUserId = Number(outwardDraft.publisherUserId) || 1;
        config = {
          display_only: true,
          locked_filters: normalizeFilterMapValues(outwardDraft.lockedFilters),
        };
      }
      const res = await controller.reviewBiOutwardEffect({
        effectKind,
        enabled,
        config,
        publisherUserId,
      });
      const pubId =
        res?.effect?.id || res?.id || outwardDraft.publicationId || '';
      setOutwardDraft((cur) => ({
        ...cur,
        reviewResult: res,
        publicationId: effectKind === 'dashboard_server' ? pubId : cur.publicationId,
      }));
      await refreshAll();
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleMintDeviceToken = async () => {
    setBusy(true);
    setSurfaceError('');
    try {
      const locked = normalizeFilterMapValues(outwardDraft.lockedFilters);
      const pubId = outwardDraft.publicationId;
      if (typeof client.manageBiDeviceTokens === 'function') {
        const res = await controller.manageBiDeviceTokens({
          action: 'mint',
          publication_id: pubId || undefined,
          device_label: outwardDraft.deviceLabel || 'kiosk',
          locked_filters: locked,
          expires_at: outwardDraft.deviceExpiresAt.trim() || null,
        });
        const tok = res?.device_token || '';
        const resolvedPub = res?.publication_id || pubId;
        setOutwardDraft((cur) => ({
          ...cur,
          publicationId: resolvedPub,
          mintedToken: tok,
          kioskUrl:
            res?.kiosk_url ||
            `/cdeadmin/designs/kiosk/${resolvedPub}#token=${tok}`,
          fleetTokens: res?.tokens || cur.fleetTokens,
        }));
      } else {
        const res = await controller.mintBiDeviceToken({
          publicationId: pubId,
          deviceLabel: outwardDraft.deviceLabel || 'kiosk',
          lockedFilters: locked,
          expiresAt: outwardDraft.deviceExpiresAt.trim() || null,
        });
        const tok = res?.device_token || '';
        setOutwardDraft((cur) => ({
          ...cur,
          mintedToken: tok,
          kioskUrl: `/cdeadmin/designs/kiosk/${pubId}#token=${tok}`,
        }));
      }
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRevokeDeviceToken = async (tokenId) => {
    if (typeof client.manageBiDeviceTokens !== 'function') return;
    setBusy(true);
    setSurfaceError('');
    try {
      const res = await controller.manageBiDeviceTokens({
        action: 'revoke',
        token_id: tokenId,
      });
      setOutwardDraft((cur) => ({
        ...cur,
        fleetTokens: res?.tokens || cur.fleetTokens,
      }));
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  // -----------------------------------------------------------------------
  // Git Sync
  // -----------------------------------------------------------------------

  const handleGitAction = async (action) => {
    setBusy(true);
    setSurfaceError('');
    try {
      const res = await controller.gitOperation({
        action,
        repoRoot: gitDraft.repoRoot,
        path: gitDraft.path,
        branch: gitDraft.branch,
        note: gitDraft.note,
      });
      if (action === 'drift') {
        setGitDraft((cur) => ({...cur, driftResult: res}));
      } else {
        setGitOpen(false);
        await refreshAll();
        setBannerMessage(`Completed Git ${action} operation.`);
      }
    } catch (err) {
      setSurfaceError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  // -----------------------------------------------------------------------
  // 5-Tab DesignerTabbedMenu Definition
  // -----------------------------------------------------------------------

  const ribbonTabs = useMemo(() => {
    const status = sessionState.status || 'draft';
    return [
      {
        id: 'design',
        label: 'Design',
        groups: [
          {
            id: 'checkpoint',
            label: 'Checkpoint & Advance Status',
            items: [
              {
                id: 'bi-save-draft',
                label: 'Save Draft',
                intent: 'primary',
                disabled: readOnly || busy,
                onClick: () =>
                  runToolbarCommand('bi.designer.save', handleSaveDraft),
              },
              {
                id: 'bi-status-in-progress',
                label: 'In Progress',
                disabled: readOnly || busy || status !== 'draft',
                onClick: () => handleAdvanceStatus('in_progress'),
              },
              {
                id: 'bi-status-in-review',
                label: 'In Review',
                disabled:
                  readOnly ||
                  busy ||
                  (status !== 'draft' && status !== 'in_progress'),
                onClick: () => handleAdvanceStatus('in_review'),
              },
              {
                id: 'bi-accept',
                label: 'Accept',
                disabled: readOnly || busy || status === 'accepted',
                onClick: () =>
                  runToolbarCommand('bi.designer.accept', () =>
                    setAcceptOpen(true)
                  ),
              },
              {
                id: 'bi-branch-draft',
                label: 'Branch Draft',
                disabled: readOnly || busy || status !== 'accepted',
                onClick: handleBranchDraft,
              },
            ],
          },
          {
            id: 'provenance',
            label: 'History & Provenance',
            items: [
              {
                id: 'bi-checkpoints',
                label: 'Checkpoints & Diff…',
                onClick: () => setCheckpointOpen(true),
              },
              {
                id: 'bi-git-sync',
                label: 'Git Sync…',
                onClick: () => setGitOpen(true),
              },
              {
                id: 'bi-export-ddn',
                label: 'Export DDN',
                onClick: handleExportDdn,
              },
              {
                id: 'bi-where-used',
                label: 'Where Used…',
                onClick: () => setWhereUsedOpen(true),
              },
            ],
          },
        ],
      },
      {
        id: 'query',
        label: 'Query & Cards',
        attention: fanoutWarnings.length > 0 || savedFilterFlags.length > 0,
        groups:
          biKind === 'question'
            ? [
              {
                id: 'sbsql-builder',
                label: 'Question Query',
                items: [
                  {
                    id: 'bi-structured-query',
                    label: 'Structured Query Builder…',
                    disabled: readOnly,
                    onClick: () => openQueryBuilder('joins'),
                  },
                  {
                    id: 'bi-params-flags',
                    label: 'Parameters & Review Flags…',
                    badge: savedFilterFlags.length || undefined,
                    disabled: readOnly,
                    onClick: () => openQueryBuilder('parameters'),
                  },
                ],
              },
            ]
            : [
              {
                id: 'dashboard-cards',
                label: 'Dashboard Composition',
                items: [
                  {
                    id: 'bi-cards-layout',
                    label: 'Dashboard Cards & Layout…',
                    badge: (dashboardModel?.cards || []).length,
                    disabled: readOnly,
                    onClick: openDashboardCardsModal,
                  },
                  {
                    id: 'bi-filters-pinning',
                    label: 'Filters & Pinning…',
                    disabled: readOnly,
                    onClick: openFiltersAndPinningModal,
                  },
                  {
                    id: 'bi-cross-filter-toggle',
                    label: 'Cross-Filter Bar',
                    active: showCrossFilterBar,
                    onClick: () => setShowCrossFilterBar((v) => !v),
                  },
                  {
                    id: 'bi-writeback-buttons',
                    label: 'Write-Back Action Buttons…',
                    badge: actionButtons.length || undefined,
                    disabled: readOnly,
                    onClick: () => openActionButtonsModal('configure'),
                  },
                ],
              },
            ],
      },
      {
        id: 'chart',
        label: 'Chart & Accessibility',
        groups: [
          {
            id: 'chart-profile',
            label: 'Visualization Profile',
            items: [
              {
                id: 'bi-chart-profile-select',
                render: () => (
                  <Box sx={{minWidth: 200}}>
                    <Select
                      label="Chart profile"
                      size="small"
                      disabled={readOnly || biKind !== 'question'}
                      value={questionModel?.visualization?.type || 'bar'}
                      options={CHART_TYPE_OPTIONS}
                      onChange={handleChartProfileChange}
                    />
                  </Box>
                ),
              },
              {
                id: 'bi-axis-formatters',
                label: 'Axis & Number Formatters…',
                disabled: readOnly,
                onClick: () => setFormatOpen(true),
              },
              {
                id: 'bi-accessible-table-toggle',
                label: 'Accessible Data Table',
                active: showAccessibleTable,
                onClick: () => setShowAccessibleTable((v) => !v),
              },
            ],
          },
          ...(biKind === 'dashboard'
            ? [
              {
                id: 'collector-binding',
                label: 'Monitoring Snapshot',
                items: [
                  {
                    id: 'bi-live-collector',
                    label: 'Live Collector Binding…',
                    badge: allMetricCards.length || undefined,
                    onClick: openCollectorInspector,
                  },
                ],
              },
            ]
            : []),
        ],
      },
      {
        id: 'sql',
        label: 'SQL & AI Draft',
        groups: [
          {
            id: 'sql-bridge-group',
            label: 'Dialect SQL Handoff',
            items: [
              {
                id: 'bi-compile-sql',
                label: 'Compile Dialect SQL…',
                onClick: () =>
                  runToolbarCommand('bi.designer.sql_bridge', () =>
                    openSqlModal('compile')
                  ),
              },
              {
                id: 'bi-open-sql-editor',
                label: 'Open in SQL Editor',
                onClick: handleOpenInSqlEditor,
              },
              {
                id: 'bi-import-sql',
                label: 'Import SQL into Question…',
                disabled: readOnly || biKind !== 'question',
                onClick: () => openSqlModal('import'),
              },
            ],
          },
          {
            id: 'ai-draft-group',
            label: 'Assisted Authoring',
            items: [
              {
                id: 'bi-byok-ai',
                label: 'BYOK AI Draft…',
                disabled: readOnly,
                onClick: () => setAiOpen(true),
              },
            ],
          },
        ],
      },
      {
        id: 'outward',
        label: 'Outward & Kiosk',
        groups: [
          {
            id: 'outward-switches',
            label: 'Reviewed Outward Exposure',
            items: [
              {
                id: 'bi-subscriptions',
                label: 'Subscriptions & Alerts…',
                onClick: () =>
                  runToolbarCommand('bi.designer.outward_review', () =>
                    openOutwardModal('subscriptions')
                  ),
              },
              {
                id: 'bi-embed-switch',
                label: 'Embed Switch…',
                onClick: () => openOutwardModal('embed'),
              },
              {
                id: 'bi-kiosk-fleet',
                label: 'Dashboard Server & Kiosk Fleet…',
                onClick: () => openOutwardModal('kiosk'),
              },
            ],
          },
          ...(biKind === 'dashboard'
            ? [
              {
                id: 'native-action-review',
                label: 'OperationBus Gate',
                items: [
                  {
                    id: 'bi-test-action-review',
                    label: 'Test Action Button Native Review…',
                    badge: actionButtons.length || undefined,
                    onClick: () => openActionButtonsModal('review'),
                  },
                ],
              },
            ]
            : []),
        ],
      },
    ];
  }, [
    sessionState.status,
    readOnly,
    busy,
    biKind,
    fanoutWarnings.length,
    savedFilterFlags.length,
    dashboardModel,
    showCrossFilterBar,
    actionButtons.length,
    questionModel,
    showAccessibleTable,
    allMetricCards.length,
  ]);

  const scopeIsPinned =
    dashboardModel?.interaction?.filter_state_scope === 'author_pinned';

  return (
    <Box
      component="section"
      aria-label="BI Designer Surface"
      sx={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
      }}
    >
      <FormReference formKey="bi-designer" />
      <FormReference formKey="bi-designer-workspace" />

      <DesignerTabbedMenu
        label="BI designer menu"
        tabs={ribbonTabs}
        activeTab={activeMenuTab}
        onTabChange={setActiveMenuTab}
        leading={
          <StatusBadge
            status={statusTone(sessionState.status)}
            label={`${biKind === 'dashboard' ? 'Dashboard' : 'Question'} v${
              sessionState.currentVersion || 1
            } · ${sessionState.status || 'draft'}`}
          />
        }
        trailing={
          <Stack direction="row" gap="compact" alignItems="center">
            {sessionState.activeVersion && (
              <Badge
                status="success"
                label={`Active v${sessionState.activeVersion}`}
              />
            )}
            <Box sx={{minWidth: 180}}>
              <Select
                label="DDN view"
                size="small"
                value={
                  activeView ||
                  (biKind === 'dashboard'
                    ? 'dashboard_composed'
                    : 'question_chart')
                }
                options={viewOptions}
                onChange={setActiveView}
              />
            </Box>
          </Stack>
        }
      />

      {/* Governance, Fan-Out, Saved Filter & Collector Snapshot Banners */}
      <Stack gap="compact" sx={{px: 1, pt: 0.5}}>
        {surfaceError && (
          <Banner status="error" onClose={() => setSurfaceError('')}>
            {surfaceError}
          </Banner>
        )}
        {bannerMessage && (
          <Banner status="info" onClose={() => setBannerMessage('')}>
            {bannerMessage}
          </Banner>
        )}
        {fanoutWarnings.length > 0 && (
          <Banner status="warning">
            SBsql join fan-out warning: {fanoutWarnings[0].detail}
          </Banner>
        )}
        {savedFilterFlags.length > 0 && (
          <Banner status="warning">
            Review saved filter literal/default values ({savedFilterFlags.length}{' '}
            flagged) before accepting or publishing.
          </Banner>
        )}
        {staticMetricCards.length > 0 && (
          <Banner status="info">
            Monitoring metric_panel card(s) ({staticMetricCards.length}) hold
            static snapshots in BI and do not poll live collectors.
          </Banner>
        )}
        {collectorMetricCards.length > 0 && (
          <Banner status="info">
            Read-only collector metric_panel card(s) (
            {collectorMetricCards.length}) read MonitoringHost.snapshot without
            mutating any collector.
          </Banner>
        )}
      </Stack>

      {/* Interactive Dashboard Active Filter & Cross-Filter Strip */}
      {biKind === 'dashboard' && showCrossFilterBar && (
        <Panel
          aria-label="Active Filter and Cross-Filter Strip"
          sx={{mx: 1, mt: 0.75, p: 1}}
        >
          <Stack gap="compact">
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 1,
              }}
            >
              <Box component="span" sx={{fontSize: '0.75rem', fontWeight: 600}}>
                Interactive Cross-Filter & Drill-Through
              </Box>
              <Badge
                status={scopeIsPinned ? 'warning' : 'info'}
                label={scopeIsPinned ? 'Author-Pinned' : 'Personal'}
              />
              {(dashboardModel?.cards || []).map((card) => {
                const effClick =
                  cardClickOverrides[card.id] ||
                  (card.click_behavior && card.click_behavior !== 'inherit'
                    ? card.click_behavior
                    : dashboardModel?.interaction?.default_click_behavior ||
                      'cross_filter');
                const isActive = Boolean(activeCrossFilters[card.id]);
                return (
                  <Stack
                    key={card.id}
                    direction="row"
                    gap="compact"
                    alignItems="center"
                  >
                    <Button
                      size="small"
                      intent={isActive ? 'primary' : 'neutral'}
                      disabled={effClick === 'none'}
                      onClick={() => {
                        if (effClick === 'none') return;
                        setActiveCrossFilters((cur) => {
                          const next = {...cur};
                          if (next[card.id]) delete next[card.id];
                          else next[card.id] = `${card.title || card.id}:selected`;
                          return next;
                        });
                      }}
                    >
                      {card.title || card.id} ({effClick})
                    </Button>
                    <Box sx={{minWidth: 128}}>
                      <Select
                        aria-label={`Click override for ${card.title || card.id}`}
                        size="small"
                        value={cardClickOverrides[card.id] || card.click_behavior || 'inherit'}
                        options={CLICK_BEHAVIOR_OPTIONS}
                        onChange={(val) =>
                          setCardClickOverrides((cur) => ({
                            ...cur,
                            [card.id]: val,
                          }))
                        }
                      />
                    </Box>
                  </Stack>
                );
              })}
              <Box sx={{ml: 'auto', display: 'flex', gap: 0.75}}>
                {Object.keys(activeCrossFilters).length > 0 && (
                  <Button
                    size="small"
                    onClick={() => {
                      setActiveCrossFilters({});
                      setDrillContextResult(null);
                    }}
                  >
                    Clear Cross-Filters
                  </Button>
                )}
                <Button
                  size="small"
                  intent="primary"
                  onClick={handleDrillThroughWithContext}
                >
                  Drill-Through with Context
                </Button>
              </Box>
            </Box>
            {(dashboardModel?.filters || []).length > 0 && (
              <FormGrid columns={4}>
                {(dashboardModel?.filters || []).map((flt) => (
                  <TextField
                    key={flt.id}
                    size="small"
                    label={`${flt.name || flt.id} (${
                      flt.pinned_by_author ? 'Author-Pinned' : 'Personal'
                    })`}
                    value={activeDashFilters[flt.id] ?? flt.default ?? ''}
                    onChange={(e) =>
                      setActiveDashFilters((cur) => ({
                        ...cur,
                        [flt.id]: e.target.value,
                      }))
                    }
                  />
                ))}
              </FormGrid>
            )}
            {drillContextResult && (
              <Box
                role="status"
                aria-label="Carried drill-through context"
                sx={{fontSize: '0.75rem'}}
              >
                Carried drill context:{' '}
                <code>
                  {JSON.stringify(
                    drillContextResult.carried_filters ||
                      drillContextResult.bound_parameters ||
                      drillContextResult
                  )}
                </code>
              </Box>
            )}
          </Stack>
        </Panel>
      )}

      {/* Main DDN Viewer Surface + Optional Accessible Data Table */}
      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          display: 'grid',
          gridTemplateColumns: showAccessibleTable ? '1fr 1fr' : '1fr',
          gap: 1,
          p: 1,
        }}
      >
        <Box
          sx={{
            position: 'relative',
            minWidth: 0,
            minHeight: 0,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {viewerWorkspace && (
            <DDNViewerSurface
              snapshot={viewerWorkspace.format ? viewerWorkspace : undefined}
              files={!viewerWorkspace.format ? viewerWorkspace.files : undefined}
              entry={viewerWorkspace.entry}
              view={viewerWorkspace.view}
              showViewSelector={false}
              onExport={onExport}
              onError={onError}
            />
          )}
        </Box>
        {showAccessibleTable && (
          <Panel
            sx={{
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
              p: 1,
            }}
          >
            <Stack
              direction="row"
              gap="compact"
              alignItems="center"
              sx={{mb: 1}}
            >
              <Box component="span" sx={{fontSize: '0.8125rem', fontWeight: 600}}>
                Accessible Data Table
              </Box>
              {questionModel?.visualization_format?.x_axis_label && (
                <Badge
                  status="neutral"
                  label={`X: ${questionModel.visualization_format.x_axis_label}`}
                />
              )}
              {questionModel?.visualization_format?.y_axis_label && (
                <Badge
                  status="neutral"
                  label={`Y: ${questionModel.visualization_format.y_axis_label}`}
                />
              )}
            </Stack>
            <Box sx={{px: 1, py: 0.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1}}>
              <QueryExecutionToolbarCluster
                controller={biQueryController}
                qaKeyPrefix="bi-question-preview"
              />
            </Box>
            <ScrollArea label="Accessible BI data table region" sx={{flex: 1}}>
              <Box className="sr-bui-table-card">
                <Box
                  component="table"
                  role="table"
                  className="sr-bui-table"
                  aria-label="Accessible BI data table"
                  sx={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    fontSize: '0.8125rem',
                  }}
                >
                  <Box component="thead">
                    <Box component="tr">
                      {accessibleTableData.headers.map((h) => (
                        <Box
                          key={h}
                          component="th"
                          className="sr-bui-th"
                          scope="col"
                          sx={{textAlign: 'left'}}
                        >
                          {h}
                        </Box>
                      ))}
                    </Box>
                  </Box>
                  <Box component="tbody">
                    {accessibleTableData.rows
                      .slice(0, biQueryController.maxRows)
                      .map((r, rIdx) => (
                        <Box key={rIdx} component="tr" className="sr-bui-tr">
                          {r.map((cell, cIdx) => (
                            <Box
                              key={cIdx}
                              component="td"
                              className="sr-bui-td"
                            >
                              {cell}
                            </Box>
                          ))}
                        </Box>
                      ))}
                  </Box>
                </Box>
                <QueryStepStatusFooter
                  controller={biQueryController}
                  qaKey="bi-question-preview-footer"
                />
              </Box>
            </ScrollArea>
          </Panel>
        )}
      </Box>

      <ProgressOverlay message={loading ? 'Loading BI design…' : ''} />

      {/* 1. Structured Query Builder & Parameters Dialog (`bi-designer-query`) */}
      <Dialog
        open={queryOpen}
        title="Structured SBsql Query & Parameters"
        size="large"
        busy={busy}
        onClose={() => setQueryOpen(false)}
        actions={
          <>
            <Button onClick={() => setQueryOpen(false)}>Cancel</Button>
            <Button intent="primary" loading={busy} onClick={applyStructuredQuery}>
              Save Query Checkpoint
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="bi-designer-query"
          activeTab={queryModalTab}
          onTabChange={setQueryModalTab}
          banner={
            draftHasFanoutJoin ? (
              <Box sx={{mb: 1}}>
                <Banner status="warning">
                  Fan-out warning: one_to_many / many_to_many join cardinality
                  can duplicate aggregated metric rows.
                </Banner>
              </Box>
            ) : null
          }
          tabs={[
            {
              id: 'joins',
              label: 'Tables & Joins',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={4}>
                    <TextField
                      label="Base Schema"
                      value={queryDraft.schema}
                      onChange={(e) =>
                        setQueryDraft((c) => ({...c, schema: e.target.value}))
                      }
                    />
                    <TextField
                      label="Base Table"
                      value={queryDraft.table}
                      onChange={(e) =>
                        setQueryDraft((c) => ({...c, table: e.target.value}))
                      }
                    />
                    <TextField
                      label="Base Alias"
                      value={queryDraft.alias}
                      onChange={(e) =>
                        setQueryDraft((c) => ({...c, alias: e.target.value}))
                      }
                    />
                    <TextField
                      label="Endpoint ID"
                      value={queryDraft.endpointId}
                      onChange={(e) =>
                        setQueryDraft((c) => ({...c, endpointId: e.target.value}))
                      }
                    />
                  </FormGrid>
                  <TypedRowsEditor
                    label="Joined Tables"
                    addLabel="Add join"
                    rows={queryDraft.joinRows}
                    onChange={(joinRows) =>
                      setQueryDraft((c) => ({...c, joinRows}))
                    }
                    columns={[
                      {
                        key: 'join_type',
                        label: 'Join Type',
                        type: 'select',
                        options: JOIN_TYPE_OPTIONS,
                        default: 'left',
                      },
                      {key: 'schema', label: 'Schema', default: 'main'},
                      {key: 'table', label: 'Table', placeholder: 'order_items'},
                      {key: 'alias', label: 'Alias', placeholder: 'items'},
                      {
                        key: 'cardinality',
                        label: 'Cardinality',
                        type: 'select',
                        options: JOIN_CARDINALITY_OPTIONS,
                        default: 'many_to_one',
                      },
                      {key: 'left_col', label: 'Left Key', placeholder: 'orders.id'},
                      {key: 'right_col', label: 'Right Key', placeholder: 'items.order_id'},
                    ]}
                  />
                </Stack>
              ),
            },
            {
              id: 'dimensions_metrics',
              label: 'Dimensions & Metrics',
              render: () => (
                <Stack gap="standard">
                  <TypedRowsEditor
                    label="Dimension Columns"
                    addLabel="Add dimension"
                    rows={queryDraft.dimensionRows}
                    onChange={(dimensionRows) =>
                      setQueryDraft((c) => ({...c, dimensionRows}))
                    }
                    columns={[
                      {
                        key: 'table_alias',
                        label: 'Table Alias',
                        default: queryDraft.alias || 'orders',
                      },
                      {key: 'column_name', label: 'Column', placeholder: 'region'},
                      {key: 'alias', label: 'Output Label', placeholder: 'region'},
                    ]}
                  />
                  <TypedRowsEditor
                    label="Aggregated Metrics"
                    addLabel="Add metric"
                    rows={queryDraft.metricRows}
                    onChange={(metricRows) =>
                      setQueryDraft((c) => ({...c, metricRows}))
                    }
                    columns={[
                      {
                        key: 'func',
                        label: 'Aggregation',
                        type: 'select',
                        options: AGG_FUNCTION_OPTIONS,
                        default: 'sum',
                      },
                      {
                        key: 'table_alias',
                        label: 'Table Alias',
                        default: queryDraft.alias || 'orders',
                      },
                      {key: 'column_name', label: 'Column', placeholder: 'amount'},
                      {
                        key: 'alias',
                        label: 'Metric Alias',
                        placeholder: 'total_amount',
                      },
                    ]}
                  />
                </Stack>
              ),
            },
            {
              id: 'filters',
              label: 'Filters & Row Limit',
              render: () => (
                <Stack gap="standard">
                  <TypedRowsEditor
                    label="Filter Predicates"
                    addLabel="Add filter"
                    rows={queryDraft.filterRows}
                    onChange={(filterRows) =>
                      setQueryDraft((c) => ({...c, filterRows}))
                    }
                    columns={[
                      {
                        key: 'table_alias',
                        label: 'Table Alias',
                        default: queryDraft.alias || 'orders',
                      },
                      {key: 'column_name', label: 'Column', placeholder: 'status'},
                      {
                        key: 'operator',
                        label: 'Operator',
                        type: 'select',
                        options: FILTER_OPERATOR_OPTIONS,
                        default: 'eq',
                      },
                      {
                        key: 'param_or_value',
                        label: ':param or Literal',
                        placeholder: ':status_param',
                      },
                      {
                        key: 'flag_for_review',
                        label: 'Review Flag',
                        type: 'boolean',
                        checkboxLabel: 'Flag saved value for review',
                        default: false,
                      },
                    ]}
                  />
                  <FormGrid columns={3}>
                    <NumberField
                      label="Row Limit"
                      value={queryDraft.limit}
                      onChange={(e) =>
                        setQueryDraft((c) => ({
                          ...c,
                          limit: Number(e.target.value) || 100,
                        }))
                      }
                    />
                  </FormGrid>
                </Stack>
              ),
            },
            {
              id: 'parameters',
              label: 'Parameters & Review Flags',
              render: () => (
                <Stack gap="standard">
                  <TypedRowsEditor
                    label="Declared Parameters"
                    addLabel="Add parameter"
                    rows={queryDraft.paramRows}
                    onChange={(paramRows) =>
                      setQueryDraft((c) => ({...c, paramRows}))
                    }
                    columns={[
                      {key: 'id', label: 'Parameter ID', placeholder: 'region_p'},
                      {key: 'name', label: 'Display Name', placeholder: 'Region'},
                      {
                        key: 'type',
                        label: 'Type',
                        type: 'select',
                        options: [
                          {value: 'string', label: 'String'},
                          {value: 'integer', label: 'Integer'},
                          {value: 'number', label: 'Number'},
                          {value: 'date', label: 'Date'},
                          {value: 'boolean', label: 'Boolean'},
                        ],
                        default: 'string',
                      },
                      {
                        key: 'required',
                        label: 'Required',
                        type: 'boolean',
                        checkboxLabel: 'Required',
                      },
                      {
                        key: 'default_val',
                        label: 'Saved Default',
                        placeholder: 'Optional default',
                      },
                    ]}
                  />
                  {savedFilterFlags.length > 0 && (
                    <Banner status="warning">
                      Flagged literal/default filter values:{' '}
                      {savedFilterFlags.map((f) => f.path).join(', ')}
                    </Banner>
                  )}
                </Stack>
              ),
            },
          ]}
        />
      </Dialog>

      {/* 2. Axis & Number Formatters Dialog (`bi-designer-chart`) */}
      <Dialog
        open={formatOpen}
        title="Axis, Number, Currency & Date Formatters"
        size="medium"
        busy={busy}
        onClose={() => setFormatOpen(false)}
        actions={
          <>
            <Button onClick={() => setFormatOpen(false)}>Cancel</Button>
            <Button
              intent="primary"
              loading={busy}
              onClick={applyVisualizationFormat}
            >
              Apply Formatters
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="bi-designer-chart" />
          <FormGrid columns={2}>
            <Select
              label="Number Format"
              value={formatDraft.number_format}
              options={NUMBER_FORMAT_OPTIONS}
              onChange={(val) =>
                setFormatDraft((c) => ({...c, number_format: val}))
              }
            />
            <Select
              label="Currency Code"
              value={formatDraft.currency_code}
              options={CURRENCY_CODE_OPTIONS}
              disabled={formatDraft.number_format !== 'currency'}
              onChange={(val) =>
                setFormatDraft((c) => ({...c, currency_code: val}))
              }
            />
            <NumberField
              label="Decimal Places (0–4)"
              value={formatDraft.decimals}
              onChange={(e) =>
                setFormatDraft((c) => ({
                  ...c,
                  decimals: Math.max(
                    0,
                    Math.min(4, Number(e.target.value) || 0)
                  ),
                }))
              }
            />
            <Select
              label="Date Grain"
              value={formatDraft.date_grain}
              options={DATE_GRAIN_OPTIONS}
              onChange={(val) =>
                setFormatDraft((c) => ({...c, date_grain: val}))
              }
            />
            <TextField
              label="X-Axis Label"
              value={formatDraft.x_axis_label}
              onChange={(e) =>
                setFormatDraft((c) => ({...c, x_axis_label: e.target.value}))
              }
            />
            <TextField
              label="Y-Axis Label"
              value={formatDraft.y_axis_label}
              onChange={(e) =>
                setFormatDraft((c) => ({...c, y_axis_label: e.target.value}))
              }
            />
          </FormGrid>
          <Checkbox
            label="Show Accessible Data Table alongside chart by default"
            checked={Boolean(formatDraft.show_accessible_table_default)}
            onChange={(checked) =>
              setFormatDraft((c) => ({
                ...c,
                show_accessible_table_default: checked,
              }))
            }
          />
        </Stack>
      </Dialog>

      {/* 3. SQL Bridge Dialog (Compile Dialect SQL & Import SQL into Question) */}
      <Dialog
        open={sqlOpen}
        title="BI Dialect SQL Bridge"
        size="large"
        busy={busy}
        onClose={() => setSqlOpen(false)}
        actions={
          <>
            <Button onClick={handleOpenInSqlEditor}>Open in SQL Editor</Button>
            <Button onClick={() => setSqlOpen(false)}>Close</Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey={
            sqlModalTab === 'import'
              ? 'bi-designer-import'
              : 'bi-designer-query'
          }
          activeTab={sqlModalTab}
          onTabChange={setSqlModalTab}
          tabs={[
            {
              id: 'compile',
              label: 'Compile Dialect SQL',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <Select
                      label="Target SQL Dialect"
                      value={sqlDraft.dialect}
                      options={DIALECT_OPTIONS}
                      onChange={(val) => runCompileSql(val, sqlDraft.parameterValues)}
                    />
                    <Box sx={{pt: 2.25}}>
                      <Button
                        intent="primary"
                        onClick={() =>
                          runCompileSql(sqlDraft.dialect, sqlDraft.parameterValues)
                        }
                      >
                        Recompile SQL
                      </Button>
                    </Box>
                  </FormGrid>
                  <KeyValuePairsEditor
                    label="Bound Parameter Values"
                    keyLabel="Parameter"
                    valueLabel="Bound Value"
                    value={sqlDraft.parameterValues}
                    onChange={(parameterValues) =>
                      setSqlDraft((c) => ({
                        ...c,
                        parameterValues: mergeKeyValueChange(
                          c.parameterValues,
                          parameterValues,
                          'param'
                        ),
                      }))
                    }
                  />
                  <Box sx={{fontSize: '0.75rem'}}>
                    Bound parameters: {JSON.stringify(sqlDraft.boundParams)}
                  </Box>
                  <Box sx={{height: 190}}>
                    <CodeEditor
                      label="Compiled Parameterized SQL"
                      language="sql"
                      readonly
                      value={sqlDraft.compiledSql || '-- Click Recompile SQL'}
                    />
                  </Box>
                </Stack>
              ),
            },
            {
              id: 'import',
              label: 'Import SQL into Question',
              render: () => (
                <Stack gap="standard">
                  <Box sx={{height: 160}}>
                    <CodeEditor
                      label="Source SELECT Statement"
                      language="sql"
                      value={sqlDraft.importSql}
                      onChange={(val) => {
                        const next =
                          typeof val === 'string'
                            ? val
                            : val?.target?.value ?? '';
                        if (next === importSqlRef.current) return;
                        importSqlRef.current = next;
                        setSqlDraft((c) => ({
                          ...c,
                          importSql: next,
                        }));
                      }}
                    />
                  </Box>
                  <Stack direction="row" gap="standard" alignItems="center">
                    <Button
                      intent="primary"
                      onClick={handleConvertSqlToQuestion}
                    >
                      Convert SQL to Question
                    </Button>
                    {sqlDraft.fidelity && (
                      <Badge
                        status={
                          sqlDraft.fidelity === 'exact'
                            ? 'success'
                            : sqlDraft.fidelity === 'lossy'
                              ? 'warning'
                              : 'info'
                        }
                        label={`Fidelity: ${sqlDraft.fidelity}`}
                      />
                    )}
                    {sqlDraft.convertedQuestion && (
                      <Button onClick={handleApplyConvertedSql}>
                        Apply Converted Question
                      </Button>
                    )}
                  </Stack>
                  {sqlDraft.lossItems.length > 0 && (
                    <Banner status="warning">
                      Conversion notes:{' '}
                      {sqlDraft.lossItems
                        .map((l) => l.detail || l.code)
                        .join('; ')}
                    </Banner>
                  )}
                </Stack>
              ),
            },
          ]}
        />
      </Dialog>

      {/* 4. BYOK AI Draft Dialog */}
      <Dialog
        open={aiOpen}
        title="BYOK AI Question Draft (Human Review Required)"
        size="medium"
        busy={busy}
        onClose={() => setAiOpen(false)}
        actions={
          <>
            <Button onClick={() => setAiOpen(false)}>Close</Button>
            {aiDraft.result && (
              <Button intent="primary" onClick={handleApplyAiDraft}>
                Apply as Draft
              </Button>
            )}
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="bi-designer-query" />
          <Banner status="info">
            Searches existing BI questions first and proposes only a Draft DDN
            checkpoint. AI agents never accept, merge or publish.
          </Banner>
          <TextField
            label="Analytical Question Prompt"
            value={aiDraft.prompt}
            onChange={(e) =>
              setAiDraft((c) => ({...c, prompt: e.target.value}))
            }
          />
          <SecretField
            label="Bring-Your-Own-Key (never persisted in DDN or store)"
            allowReveal
            value={aiDraft.byokApiKey}
            onChange={(e) =>
              setAiDraft((c) => ({...c, byokApiKey: e.target.value}))
            }
          />
          <Button intent="primary" onClick={handleProposeAiDraft}>
            Search Existing & Draft Question
          </Button>
          {aiDraft.result && (
            <Banner status="success">
              Existing matches:{' '}
              {(aiDraft.result.existing_matches || []).length}. Draft status:
              draft (human review required).
            </Banner>
          )}
        </Stack>
      </Dialog>

      {/* 5. Dashboard Cards & Layout Dialog */}
      <Dialog
        open={cardOpen}
        title="Dashboard Cards & Layout"
        size="large"
        busy={busy}
        onClose={() => setCardOpen(false)}
        actions={
          <>
            <Button onClick={() => setCardOpen(false)}>Cancel</Button>
            {cardModalTab === 'manage' ? (
              <Button intent="primary" onClick={handleSaveCardList}>
                Save Cards
              </Button>
            ) : (
              <Button intent="primary" onClick={handleAddDashboardCard}>
                Add Card
              </Button>
            )}
          </>
        }
      >
        <DesignerModalTabs
          formKey="bi-designer-query"
          activeTab={cardModalTab}
          onTabChange={setCardModalTab}
          tabs={[
            {
              id: 'manage',
              label: 'Manage Cards',
              render: () => (
                <TypedRowsEditor
                  label="Dashboard Cards"
                  addLabel="Add note card"
                  reorderable
                  rows={cardRows}
                  onChange={setCardRows}
                  columns={[
                    {key: 'id', label: 'Card ID', placeholder: 'card_1'},
                    {key: 'title', label: 'Title', placeholder: 'Sales'},
                    {key: 'tab_id', label: 'Tab ID', default: 'main'},
                    {
                      key: 'click_behavior',
                      label: 'Click Override',
                      type: 'select',
                      options: CLICK_BEHAVIOR_OPTIONS,
                      default: 'inherit',
                    },
                  ]}
                />
              ),
            },
            {
              id: 'add',
              label: 'Add Question / Note / Collector Card',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={3}>
                    <Select
                      label="Card Type"
                      value={cardDraft.type}
                      options={[
                        {value: 'question', label: 'Saved BI Question'},
                        {value: 'text', label: 'Commentary Note'},
                        {value: 'metric_panel', label: 'Monitoring Metric Panel'},
                      ]}
                      onChange={(val) =>
                        setCardDraft((c) => ({...c, type: val}))
                      }
                    />
                    <TextField
                      label="Card Title"
                      value={cardDraft.title}
                      onChange={(e) =>
                        setCardDraft((c) => ({...c, title: e.target.value}))
                      }
                    />
                    <Select
                      label="Card Click Override"
                      value={cardDraft.clickBehavior}
                      options={CLICK_BEHAVIOR_OPTIONS}
                      onChange={(val) =>
                        setCardDraft((c) => ({...c, clickBehavior: val}))
                      }
                    />
                  </FormGrid>
                  {cardDraft.type === 'question' && (
                    <FormGrid columns={3}>
                      <TextField
                        label="Question Design ID"
                        value={cardDraft.questionDesignId}
                        onChange={(e) =>
                          setCardDraft((c) => ({
                            ...c,
                            questionDesignId: e.target.value,
                          }))
                        }
                      />
                      <NumberField
                        label="Pinned Version"
                        value={cardDraft.pinnedVersion}
                        disabled={cardDraft.followLatestAccepted}
                        onChange={(e) =>
                          setCardDraft((c) => ({
                            ...c,
                            pinnedVersion: Number(e.target.value) || 1,
                          }))
                        }
                      />
                      <Select
                        label="Chart Profile"
                        value={cardDraft.visType}
                        options={CHART_TYPE_OPTIONS}
                        onChange={(val) =>
                          setCardDraft((c) => ({...c, visType: val}))
                        }
                      />
                    </FormGrid>
                  )}
                  {cardDraft.type === 'text' && (
                    <TextField
                      label="Note Text"
                      value={cardDraft.markdown}
                      onChange={(e) =>
                        setCardDraft((c) => ({...c, markdown: e.target.value}))
                      }
                    />
                  )}
                  {cardDraft.type === 'metric_panel' && (
                    <Stack gap="standard">
                      <FormGrid columns={2}>
                        <TextField
                          label="Panel ID"
                          value={cardDraft.panelId}
                          onChange={(e) =>
                            setCardDraft((c) => ({...c, panelId: e.target.value}))
                          }
                        />
                        <Select
                          label="Snapshot Mode"
                          value={cardDraft.snapshotMode}
                          options={SNAPSHOT_MODE_OPTIONS}
                          onChange={(val) =>
                            setCardDraft((c) => ({...c, snapshotMode: val}))
                          }
                        />
                      </FormGrid>
                      {cardDraft.snapshotMode === 'collector_read_only' && (
                        <>
                          <FormGrid columns={4}>
                            <Select
                              label="Engine"
                              value={cardDraft.collectorEngine}
                              options={DIALECT_OPTIONS}
                              onChange={(val) =>
                                setCardDraft((c) => ({
                                  ...c,
                                  collectorEngine: val,
                                }))
                              }
                            />
                            <NumberField
                              label="Server ID"
                              value={cardDraft.collectorServerId}
                              onChange={(e) =>
                                setCardDraft((c) => ({
                                  ...c,
                                  collectorServerId: Number(e.target.value) || 1,
                                }))
                              }
                            />
                            <TextField
                              label="Metric Group"
                              value={cardDraft.collectorMetricGroup}
                              onChange={(e) =>
                                setCardDraft((c) => ({
                                  ...c,
                                  collectorMetricGroup: e.target.value,
                                }))
                              }
                            />
                            <NumberField
                              label="Freshness Budget (s)"
                              value={cardDraft.collectorFreshnessBudget}
                              onChange={(e) =>
                                setCardDraft((c) => ({
                                  ...c,
                                  collectorFreshnessBudget:
                                    Number(e.target.value) || 60,
                                }))
                              }
                            />
                          </FormGrid>
                          <TypedRowsEditor
                            label="Collector Metric Keys"
                            addLabel="Add metric key"
                            rows={cardDraft.collectorMetricKeyRows}
                            onChange={(collectorMetricKeyRows) =>
                              setCardDraft((c) => ({
                                ...c,
                                collectorMetricKeyRows,
                              }))
                            }
                            columns={[
                              {
                                key: 'metric_key',
                                label: 'Metric Key',
                                placeholder: 'tps',
                              },
                            ]}
                          />
                        </>
                      )}
                    </Stack>
                  )}
                </Stack>
              ),
            },
          ]}
        />
      </Dialog>

      {/* 6. Dashboard Filters & Pinning Dialog */}
      <Dialog
        open={interactionOpen}
        title="Dashboard Filters, Pinning & Interaction Policy"
        size="large"
        busy={busy}
        onClose={() => setInteractionOpen(false)}
        actions={
          <>
            <Button onClick={() => setInteractionOpen(false)}>Cancel</Button>
            <Button intent="primary" onClick={applyFiltersAndPinning}>
              Save Filter Policy
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="bi-designer-query" />
          <FormGrid columns={2}>
            <Select
              label="Default Card Click Behavior"
              value={interactionDraft.defaultClickBehavior}
              options={CLICK_BEHAVIOR_OPTIONS.filter((o) => o.value !== 'inherit')}
              onChange={(val) =>
                setInteractionDraft((c) => ({...c, defaultClickBehavior: val}))
              }
            />
            <Select
              label="Filter State Scope"
              value={interactionDraft.filterStateScope}
              options={FILTER_SCOPE_OPTIONS}
              onChange={(val) =>
                setInteractionDraft((c) => ({...c, filterStateScope: val}))
              }
            />
          </FormGrid>
          <Stack direction="row" gap="comfortable">
            <Checkbox
              label="Auto-apply dashboard filters"
              checked={Boolean(interactionDraft.autoApplyFilters)}
              onChange={(v) =>
                setInteractionDraft((c) => ({...c, autoApplyFilters: v}))
              }
            />
            <Checkbox
              label="Carry full active filter context on drill-through"
              checked={Boolean(interactionDraft.drillCarriesFilterContext)}
              onChange={(v) =>
                setInteractionDraft((c) => ({
                  ...c,
                  drillCarriesFilterContext: v,
                }))
              }
            />
          </Stack>
          <TypedRowsEditor
            label="Dashboard Filters"
            addLabel="Add filter"
            rows={interactionDraft.filterRows}
            onChange={(filterRows) =>
              setInteractionDraft((c) => ({...c, filterRows}))
            }
            columns={[
              {key: 'id', label: 'Filter ID', placeholder: 'region'},
              {key: 'name', label: 'Label', placeholder: 'Region'},
              {
                key: 'operator',
                label: 'Operator',
                type: 'select',
                options: FILTER_OPERATOR_OPTIONS,
                default: 'eq',
              },
              {key: 'default_val', label: 'Default Value', placeholder: ''},
              {
                key: 'pinned_by_author',
                label: 'Pinning',
                type: 'boolean',
                checkboxLabel: 'Author-Pinned',
              },
            ]}
          />
        </Stack>
      </Dialog>

      {/* 7. Live Collector Binding Snapshot Inspector Dialog */}
      <Dialog
        open={collectorOpen}
        title="Read-Only Monitoring Collector Binding"
        size="medium"
        busy={busy}
        onClose={() => setCollectorOpen(false)}
        actions={<Button onClick={() => setCollectorOpen(false)}>Close</Button>}
      >
        <Stack gap="standard">
          <FormReference formKey="bi-designer-chart" />
          <Select
            label="Metric Panel Card"
            value={collectorDraft.cardId}
            options={allMetricCards.map((c) => ({
              value: c.id,
              label: `${c.title} (${c.metric_panel?.snapshot_mode || 'static'})`,
            }))}
            onChange={async (cid) => {
              const snap = await controller.readBiCollectorPanel({cardId: cid});
              setCollectorDraft({cardId: cid, snapshotResult: snap});
            }}
          />
          {collectorDraft.snapshotResult && (
            <Stack gap="compact">
              <Banner status="info">
                Mode: {collectorDraft.snapshotResult.snapshot_mode} · Collector
                state: {collectorDraft.snapshotResult.collector_state} ·
                Freshness: {collectorDraft.snapshotResult.freshness_status}
              </Banner>
              <Box sx={{height: 150}}>
                <CodeEditor
                  label="Collector Snapshot Payload"
                  language="sql"
                  readonly
                  value={JSON.stringify(
                    collectorDraft.snapshotResult.rows || [],
                    null,
                    2
                  )}
                />
              </Box>
            </Stack>
          )}
        </Stack>
      </Dialog>

      {/* 8. Write-Back Action Buttons & Native Review Dialog */}
      <Dialog
        open={actionBtnOpen}
        title="BI Write-Back Action Buttons & Native Operation Review"
        size="large"
        busy={busy}
        onClose={() => setActionBtnOpen(false)}
        actions={<Button onClick={() => setActionBtnOpen(false)}>Close</Button>}
      >
        <DesignerModalTabs
          formKey="bi-designer-outward"
          activeTab={actionModalTab}
          onTabChange={setActionModalTab}
          tabs={[
            {
              id: 'review',
              label: 'Test Native Operation Review',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <Select
                      label="Action Button"
                      value={
                        actionBtnDraft.selectedActionId ||
                        actionButtons[0]?.id ||
                        ''
                      }
                      options={actionButtons.map((a) => ({
                        value: a.id,
                        label: `${a.label} (${a.operation_kind})`,
                      }))}
                      onChange={(val) =>
                        setActionBtnDraft((c) => ({
                          ...c,
                          selectedActionId: val,
                        }))
                      }
                    />
                    <Select
                      label="Preview SQL Dialect"
                      value={actionBtnDraft.dialect}
                      options={DIALECT_OPTIONS}
                      onChange={(val) =>
                        setActionBtnDraft((c) => ({...c, dialect: val}))
                      }
                    />
                  </FormGrid>
                  <KeyValuePairsEditor
                    label="Action Prompt Values"
                    keyLabel="Parameter"
                    valueLabel="Value"
                    value={actionBtnDraft.promptValues}
                    onChange={(promptValues) =>
                      setActionBtnDraft((c) => ({
                        ...c,
                        promptValues: mergeKeyValueChange(
                          c.promptValues,
                          promptValues,
                          'param'
                        ),
                      }))
                    }
                  />
                  <Stack direction="row" gap="standard">
                    <Button
                      disabled={!actionButtons.length}
                      onClick={() => handleRunActionReview(true)}
                    >
                      Preview Parameterized SQL
                    </Button>
                    <Button
                      intent="primary"
                      disabled={!actionButtons.length}
                      onClick={() => handleRunActionReview(false)}
                    >
                      Submit to Native Review
                    </Button>
                  </Stack>
                  {actionBtnDraft.reviewResult && (
                    <Stack gap="compact">
                      {actionBtnDraft.reviewResult.operation_id && (
                        <Banner status="success">
                          Operation queued:{' '}
                          {actionBtnDraft.reviewResult.operation_id} · Stage:{' '}
                          {actionBtnDraft.reviewResult.stage}
                        </Banner>
                      )}
                      {actionBtnDraft.reviewResult.destructive_warning && (
                        <Banner status="warning">
                          {actionBtnDraft.reviewResult.destructive_warning}
                        </Banner>
                      )}
                      <Box sx={{height: 140}}>
                        <CodeEditor
                          label="Parameterized Mutation Preview"
                          language="sql"
                          readonly
                          value={actionBtnDraft.reviewResult.sql || ''}
                        />
                      </Box>
                    </Stack>
                  )}
                </Stack>
              ),
            },
            {
              id: 'configure',
              label: 'Configure Action Button',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={3}>
                    <TextField
                      label="Button Label"
                      value={actionBtnDraft.label}
                      onChange={(e) =>
                        setActionBtnDraft((c) => ({...c, label: e.target.value}))
                      }
                    />
                    <Select
                      label="Operation Kind"
                      value={actionBtnDraft.operationKind}
                      options={ACTION_OPERATION_OPTIONS}
                      onChange={(val) =>
                        setActionBtnDraft((c) => ({
                          ...c,
                          operationKind: val,
                        }))
                      }
                    />
                    <TextField
                      label="Target Endpoint ID"
                      value={actionBtnDraft.targetEndpointId}
                      onChange={(e) =>
                        setActionBtnDraft((c) => ({
                          ...c,
                          targetEndpointId: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Target Schema"
                      value={actionBtnDraft.targetSchema}
                      onChange={(e) =>
                        setActionBtnDraft((c) => ({
                          ...c,
                          targetSchema: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Target Table"
                      value={actionBtnDraft.targetTable}
                      onChange={(e) =>
                        setActionBtnDraft((c) => ({
                          ...c,
                          targetTable: e.target.value,
                        }))
                      }
                    />
                  </FormGrid>
                  <TypedRowsEditor
                    label="Key Columns"
                    addLabel="Add key column"
                    rows={actionBtnDraft.keyColumnRows}
                    onChange={(keyColumnRows) =>
                      setActionBtnDraft((c) => ({...c, keyColumnRows}))
                    }
                    columns={[
                      {key: 'column', label: 'Key Column', placeholder: 'order_id'},
                    ]}
                  />
                  <TypedRowsEditor
                    label="Parameter Bindings"
                    addLabel="Add parameter binding"
                    rows={actionBtnDraft.bindingRows}
                    onChange={(bindingRows) =>
                      setActionBtnDraft((c) => ({...c, bindingRows}))
                    }
                    columns={[
                      {key: 'name', label: 'Param Name', placeholder: 'order_id'},
                      {key: 'column', label: 'Target Column', placeholder: 'order_id'},
                      {
                        key: 'source',
                        label: 'Source',
                        type: 'select',
                        options: [
                          {value: 'prompt', label: 'User Prompt'},
                          {value: 'filter', label: 'Dashboard Filter'},
                          {value: 'selected_row', label: 'Selected Row'},
                          {value: 'literal', label: 'Literal'},
                        ],
                        default: 'prompt',
                      },
                      {key: 'source_ref', label: 'Source Ref', placeholder: 'order_id'},
                    ]}
                  />
                  <Box>
                    <Button intent="primary" onClick={handleAddActionButton}>
                      Add Reviewed Action Button
                    </Button>
                  </Box>
                </Stack>
              ),
            },
          ]}
        />
      </Dialog>

      {/* 9. Accept BI Version Dialog */}
      <Dialog
        open={acceptOpen}
        title="Accept BI Design Version"
        size="small"
        busy={busy}
        onClose={() => setAcceptOpen(false)}
        actions={
          <>
            <Button onClick={() => setAcceptOpen(false)}>Cancel</Button>
            <Button intent="primary" onClick={handleAcceptConfirm}>
              Accept Version
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="bi-designer-workspace" />
          <Banner status="info">
            Accepting activates this version in the store without switching on
            subscriptions, embeds or remote dashboard-server publication.
          </Banner>
          <TextField
            label="Optional Git / Approval Reference"
            value={acceptDraft.approvalRef}
            onChange={(e) =>
              setAcceptDraft((c) => ({...c, approvalRef: e.target.value}))
            }
          />
        </Stack>
      </Dialog>

      {/* 10. Outward Exposure & Kiosk Device Fleet Dialog (`bi-designer-outward`) */}
      <Dialog
        open={outwardOpen}
        title="Outward Exposure Switches & Kiosk Device Fleet"
        size="large"
        busy={busy}
        onClose={() => setOutwardOpen(false)}
        actions={<Button onClick={() => setOutwardOpen(false)}>Close</Button>}
      >
        <DesignerModalTabs
          formKey="bi-designer-outward"
          activeTab={outwardTab}
          onTabChange={setOutwardTab}
          tabs={[
            {
              id: 'subscriptions',
              label: 'Subscriptions & Alerts',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <Select
                      label="Delivery Schedule"
                      value={outwardDraft.schedule}
                      options={[
                        {value: 'hourly', label: 'Hourly'},
                        {value: 'daily', label: 'Daily'},
                        {value: 'weekly', label: 'Weekly'},
                      ]}
                      onChange={(val) =>
                        setOutwardDraft((c) => ({...c, schedule: val}))
                      }
                    />
                    <Box sx={{pt: 1}}>
                      <Checkbox
                        label="Enable Subscription / Alert Delivery"
                        checked={Boolean(outwardDraft.subscriptionEnabled)}
                        onChange={(v) =>
                          setOutwardDraft((c) => ({
                            ...c,
                            subscriptionEnabled: v,
                          }))
                        }
                      />
                    </Box>
                  </FormGrid>
                  <TypedRowsEditor
                    label="Subscription Recipients"
                    addLabel="Add recipient"
                    rows={outwardDraft.recipientRows}
                    onChange={(recipientRows) =>
                      setOutwardDraft((c) => ({...c, recipientRows}))
                    }
                    columns={[
                      {
                        key: 'recipient',
                        label: 'Recipient Address',
                        placeholder: 'ops-team@example.org',
                      },
                    ]}
                  />
                  <TypedRowsEditor
                    label="Alert Webhook Channels"
                    addLabel="Add webhook"
                    rows={outwardDraft.webhookRows}
                    onChange={(webhookRows) =>
                      setOutwardDraft((c) => ({...c, webhookRows}))
                    }
                    columns={[
                      {
                        key: 'url',
                        label: 'Webhook Destination URL',
                        placeholder: 'https://hooks.example.org/bi',
                      },
                    ]}
                  />
                  <Box>
                    <Button
                      intent="primary"
                      onClick={() => handleReviewOutwardSwitch('subscription')}
                    >
                      Review & Apply Subscription Switch
                    </Button>
                  </Box>
                </Stack>
              ),
            },
            {
              id: 'embed',
              label: 'Embed Switch',
              render: () => (
                <Stack gap="standard">
                  <Checkbox
                    label="Enable External Read-Only Embed"
                    checked={Boolean(outwardDraft.embedEnabled)}
                    onChange={(v) =>
                      setOutwardDraft((c) => ({...c, embedEnabled: v}))
                    }
                  />
                  <TypedRowsEditor
                    label="Allowed Embed Origins"
                    addLabel="Add origin"
                    rows={outwardDraft.allowedOriginRows}
                    onChange={(allowedOriginRows) =>
                      setOutwardDraft((c) => ({...c, allowedOriginRows}))
                    }
                    columns={[
                      {
                        key: 'origin',
                        label: 'Origin',
                        placeholder: 'https://portal.example.org',
                      },
                    ]}
                  />
                  <Box>
                    <Button
                      intent="primary"
                      onClick={() => handleReviewOutwardSwitch('embed')}
                    >
                      Review & Apply Embed Switch
                    </Button>
                  </Box>
                </Stack>
              ),
            },
            {
              id: 'kiosk',
              label: 'Kiosk Device Fleet',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={3}>
                    <NumberField
                      label="Publishing Identity (User ID)"
                      value={outwardDraft.publisherUserId}
                      onChange={(e) =>
                        setOutwardDraft((c) => ({
                          ...c,
                          publisherUserId: Number(e.target.value) || 1,
                        }))
                      }
                    />
                    <Box sx={{pt: 1}}>
                      <Checkbox
                        label="Enable Remote Dashboard Server"
                        checked={Boolean(outwardDraft.serverEnabled)}
                        onChange={(v) =>
                          setOutwardDraft((c) => ({...c, serverEnabled: v}))
                        }
                      />
                    </Box>
                    <Box sx={{pt: 2.25}}>
                      <Button
                        intent="primary"
                        onClick={() =>
                          handleReviewOutwardSwitch('dashboard_server')
                        }
                      >
                        Review & Apply Server Publication
                      </Button>
                    </Box>
                  </FormGrid>
                  <KeyValuePairsEditor
                    label="Locked Filters"
                    keyLabel="Filter Key"
                    valueLabel="Fixed / Allowed Value"
                    value={outwardDraft.lockedFilters}
                    onChange={(lockedFilters) =>
                      setOutwardDraft((c) => ({
                        ...c,
                        lockedFilters: mergeKeyValueChange(
                          c.lockedFilters,
                          lockedFilters,
                          'filter'
                        ),
                      }))
                    }
                  />
                  <Divider />
                  <FormGrid columns={3}>
                    <TextField
                      label="Publication ID"
                      value={outwardDraft.publicationId}
                      onChange={(e) =>
                        setOutwardDraft((c) => ({
                          ...c,
                          publicationId: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Device Label"
                      value={outwardDraft.deviceLabel}
                      onChange={(e) =>
                        setOutwardDraft((c) => ({
                          ...c,
                          deviceLabel: e.target.value,
                        }))
                      }
                    />
                    <Box sx={{pt: 2.25}}>
                      <Button
                        intent="primary"
                        onClick={handleMintDeviceToken}
                      >
                        Mint Device Token
                      </Button>
                    </Box>
                  </FormGrid>
                  {outwardDraft.kioskUrl && (
                    <FormGrid columns={2}>
                      <TextField
                        label="Display-Only Kiosk URL (#token fragment)"
                        value={outwardDraft.kioskUrl}
                        InputProps={{readOnly: true}}
                      />
                      <Box sx={{pt: 2.25}}>
                        <Button
                          onClick={() =>
                            navigator.clipboard?.writeText?.(
                              outwardDraft.kioskUrl
                            )
                          }
                        >
                          Copy Kiosk Link
                        </Button>
                      </Box>
                    </FormGrid>
                  )}
                  <ScrollArea label="Kiosk device token fleet" sx={{maxHeight: 200}}>
                    <Box
                      component="table"
                      aria-label="Kiosk device fleet"
                      sx={{
                        width: '100%',
                        borderCollapse: 'collapse',
                        fontSize: '0.8125rem',
                      }}
                    >
                      <Box component="thead">
                        <Box component="tr">
                          {[
                            'Device',
                            'Status',
                            'Locked Filters',
                            'Last Used',
                            'Action',
                          ].map((h) => (
                            <Box
                              key={h}
                              component="th"
                              scope="col"
                              sx={{
                                textAlign: 'left',
                                p: 0.5,
                                borderBottom: '1px solid',
                                borderColor: 'divider',
                              }}
                            >
                              {h}
                            </Box>
                          ))}
                        </Box>
                      </Box>
                      <Box component="tbody">
                        {outwardDraft.fleetTokens.map((tok) => (
                          <Box key={tok.token_id} component="tr">
                            <Box component="td" sx={{p: 0.5}}>
                              {tok.device_label}
                            </Box>
                            <Box component="td" sx={{p: 0.5}}>
                              <StatusBadge
                                status={
                                  tok.status === 'active'
                                    ? 'success'
                                    : tok.status === 'revoked'
                                      ? 'error'
                                      : 'warning'
                                }
                                label={tok.status}
                              />
                            </Box>
                            <Box component="td" sx={{p: 0.5}}>
                              <code>
                                {JSON.stringify(tok.locked_filters || {})}
                              </code>
                            </Box>
                            <Box component="td" sx={{p: 0.5}}>
                              {tok.last_used_at || 'Never'}
                            </Box>
                            <Box component="td" sx={{p: 0.5}}>
                              <Button
                                size="small"
                                intent="destructive"
                                disabled={tok.status === 'revoked'}
                                onClick={() =>
                                  handleRevokeDeviceToken(tok.token_id)
                                }
                              >
                                Revoke
                              </Button>
                            </Box>
                          </Box>
                        ))}
                      </Box>
                    </Box>
                  </ScrollArea>
                </Stack>
              ),
            },
          ]}
        />
      </Dialog>

      {/* 11. Git Sync Dialog */}
      <Dialog
        open={gitOpen}
        title="BI DDN Git Synchronization (Secrets Excluded)"
        size="medium"
        busy={busy}
        onClose={() => setGitOpen(false)}
        actions={
          <>
            <Button onClick={() => setGitOpen(false)}>Close</Button>
            <Button onClick={() => handleGitAction('drift')}>Check Drift</Button>
            <Button onClick={() => handleGitAction('load')}>Load from Git</Button>
            <Button intent="primary" onClick={() => handleGitAction('save')}>
              Save DDN to Git
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="bi-designer-workspace" />
          <FormGrid columns={2}>
            <TextField
              label="Git Repository Root"
              value={gitDraft.repoRoot}
              onChange={(e) =>
                setGitDraft((c) => ({...c, repoRoot: e.target.value}))
              }
            />
            <TextField
              label="DDN Relative Path"
              value={gitDraft.path}
              onChange={(e) =>
                setGitDraft((c) => ({...c, path: e.target.value}))
              }
            />
            <TextField
              label="Branch"
              value={gitDraft.branch}
              onChange={(e) =>
                setGitDraft((c) => ({...c, branch: e.target.value}))
              }
            />
            <TextField
              label="Commit / Sync Note"
              value={gitDraft.note}
              onChange={(e) =>
                setGitDraft((c) => ({...c, note: e.target.value}))
              }
            />
          </FormGrid>
          {gitDraft.driftResult && (
            <Banner status="info">
              Git drift state: {JSON.stringify(gitDraft.driftResult)}
            </Banner>
          )}
        </Stack>
      </Dialog>

      {/* 12. Shared Checkpoints & Diff + Where Used Dialogs */}
      <DesignCheckpointHistoryDrawer
        open={checkpointOpen}
        onClose={() => setCheckpointOpen(false)}
        client={client}
        projectId={projectId}
        designId={designId}
        currentVersion={sessionState.currentVersion}
        activeVersion={sessionState.activeVersion}
        onOpenVersion={(ver) => refreshAll(ver)}
        onRestored={(ver) => refreshAll(ver)}
      />

      <WhereUsedDialog
        open={whereUsedOpen}
        onClose={() => setWhereUsedOpen(false)}
        client={client}
        projectId={projectId}
        designId={designId}
      />
    </Box>
  );
}

BIDesignerSurface.propTypes = {
  projectId: PropTypes.string.isRequired,
  designId: PropTypes.string.isRequired,
  kind: PropTypes.oneOf(['question', 'dashboard']),
  client: PropTypes.object,
  controller: PropTypes.object,
  readOnly: PropTypes.bool,
  executeCommand: PropTypes.func,
  onStateChange: PropTypes.func,
  onExport: PropTypes.func,
  onError: PropTypes.func,
};

export default BIDesignerSurface;
