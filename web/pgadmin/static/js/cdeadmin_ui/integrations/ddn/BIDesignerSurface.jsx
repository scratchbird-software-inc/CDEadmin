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
import {Alert, Box} from '@mui/material';
import {Button} from '../../primitives/Button';
import {Checkbox, Select} from '../../primitives/Choice';
import {TextArea, TextField} from '../../primitives/Field';
import {Toolbar} from '../../layout/WorkbenchChrome';
import {Dialog} from '../../overlays/Dialog';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import {StatusBadge} from '../../status/StatusBadge';
import FormReference from '../../navigation/FormReference';
import {DDNViewerSurface} from './DDNViewerSurface';
import {
  DesignStoreClient,
  SharedDDNTaskController,
} from './sharedDesignLibrary';

export const BI_CHART_TYPE_OPTIONS = Object.freeze([
  {value: 'bar', label: 'Bar (chart.basic@1)'},
  {value: 'line', label: 'Line (chart.basic@1)'},
  {value: 'area', label: 'Area (chart.basic@1)'},
  {value: 'scatter', label: 'Scatter (chart.basic@1 point)'},
  {value: 'pie', label: 'Pie (chart.basic@1)'},
  {value: 'metric', label: 'Metric Gauge (chart.gauge@1)'},
  {value: 'histogram', label: 'Histogram (chart.histogram@1)'},
  {value: 'timeline', label: 'Timeline (timeline.basic@1)'},
  {value: 'graph', label: 'Force Graph (chart.force@1)'},
  {value: 'vector-neighbors', label: 'Vector Dotplot (chart.dotplot@1)'},
  {value: 'table', label: 'Table (table.records@1)'},
  {value: 'pivot', label: 'Pivot Records (table.records@1)'},
]);

const DIALECT_OPTIONS = Object.freeze([
  {value: 'sqlite', label: 'SQLite'},
  {value: 'duckdb', label: 'DuckDB'},
  {value: 'postgresql', label: 'PostgreSQL'},
  {value: 'firebird', label: 'Firebird 5'},
  {value: 'mysql', label: 'MySQL'},
  {value: 'mariadb', label: 'MariaDB'},
]);

const JOIN_TYPE_OPTIONS = Object.freeze([
  {value: 'left', label: 'LEFT JOIN'},
  {value: 'inner', label: 'INNER JOIN'},
  {value: 'right', label: 'RIGHT JOIN'},
  {value: 'full', label: 'FULL JOIN'},
]);

const JOIN_CARDINALITY_OPTIONS = Object.freeze([
  {value: 'many_to_one', label: 'Many-to-one (safe)'},
  {value: 'one_to_one', label: 'One-to-one (safe)'},
  {value: 'one_to_many', label: 'One-to-many (fan-out risk)'},
  {value: 'many_to_many', label: 'Many-to-many (fan-out risk)'},
  {value: 'undeclared', label: 'Undeclared'},
]);

const CLICK_BEHAVIOR_OPTIONS = Object.freeze([
  {value: 'inherit', label: 'Inherit dashboard default'},
  {value: 'cross_filter', label: 'Cross-filter cards'},
  {value: 'highlight', label: 'Highlight matching series'},
  {value: 'none', label: 'No click action'},
]);

const DASHBOARD_DEFAULT_CLICK_OPTIONS = Object.freeze([
  {value: 'cross_filter', label: 'Cross-filter cards'},
  {value: 'highlight', label: 'Highlight matching series'},
  {value: 'none', label: 'No click action'},
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
  {
    value: 'static',
    label: 'Static snapshot (default — never polls live collector)',
  },
  {
    value: 'collector_read_only',
    label: 'Read-only live collector binding (MonitoringHost.snapshot)',
  },
]);

function statusTone(status) {
  if (status === 'accepted') return 'success';
  if (status === 'in_review') return 'warning';
  if (status === 'in_progress') return 'info';
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

  const callbacks = useRef({executeCommand, onStateChange, onError});
  callbacks.current = {executeCommand, onStateChange, onError};

  const [sessionState, setSessionState] = useState(() => controller.state());
  const [biPayload, setBiPayload] = useState(null);
  const [loading, setLoading] = useState(!sessionState.loaded);
  const [surfaceError, setSurfaceError] = useState('');
  const [activeView, setActiveView] = useState('');
  const [busyAction, setBusyAction] = useState(false);
  const [acceptBanner, setAcceptBanner] = useState(null);

  // Question SBsql & Visualization editor dialog (E1 / E2)
  const [queryOpen, setQueryOpen] = useState(false);
  const [queryDraft, setQueryDraft] = useState({
    visType: 'bar',
    baseRelation: 'main.orders',
    baseAlias: 'orders',
    columnsCsv: 'orders.region:region',
    measuresCsv: 'sum:orders.amount:total_amount',
    joinRelation: '',
    joinAlias: '',
    joinType: 'left',
    joinCardinality: 'many_to_one',
    joinLeftCol: '',
    joinRightCol: '',
    limit: '100',
    note: '',
  });

  // SQL Bridge dialog (E2)
  const [sqlOpen, setSqlOpen] = useState(false);
  const [sqlDraft, setSqlDraft] = useState({
    dialect: 'sqlite',
    sqlInput: '',
    compiledSql: '',
    compiledParams: [],
    fidelityResult: null,
  });

  // Optional BYOK AI Draft dialog (E8)
  const [aiOpen, setAiOpen] = useState(false);
  const [aiDraft, setAiDraft] = useState({
    prompt: '',
    byokApiKey: '',
    result: null,
  });

  // Dashboard Card & Filter dialogs (E3 / E5 / E6 / E7)
  const [cardOpen, setCardOpen] = useState(false);
  const [cardDraft, setCardDraft] = useState({
    id: '',
    title: '',
    tabId: 'main',
    type: 'question',
    questionDesignId: '',
    pinnedVersion: '1',
    followLatestAccepted: false,
    visType: 'bar',
    clickBehavior: 'inherit',
    markdown: '',
    panelId: '',
    snapshotMode: 'static',
    collectorEngine: 'postgresql',
    collectorServerId: '1',
    collectorTargetId: '',
    collectorMetricGroup: 'throughput',
    collectorMetricKeysCsv: 'tps, active_sessions',
    collectorFreshnessBudget: '120',
  });

  // Dashboard Write-Back Action Buttons & Native Review dialog (E6)
  const [actionBtnOpen, setActionBtnOpen] = useState(false);
  const [actionBtnDraft, setActionBtnDraft] = useState({
    label: '',
    operationKind: 'update_row',
    targetEndpointId: 'default-endpoint',
    targetRelation: 'public.orders',
    keyColumnsCsv: 'order_id',
    bindingsCsv: 'order_id:filter:order_id, status:prompt:new_status',
    selectedActionId: '',
    dialect: 'postgresql',
    parameterValuesJson: '{}',
    reviewResult: null,
  });

  // Read-only Collector Metric Panel Snapshot dialog (E7)
  const [collectorOpen, setCollectorOpen] = useState(false);
  const [collectorDraft, setCollectorDraft] = useState({
    cardId: '',
    snapshotResult: null,
  });

  const [interactionOpen, setInteractionOpen] = useState(false);
  const [interactionDraft, setInteractionDraft] = useState({
    defaultClickBehavior: 'cross_filter',
    autoApplyFilters: true,
    filterStateScope: 'personal',
    drillCarriesFilterContext: true,
    newFilterId: '',
    newFilterName: '',
    newFilterPinned: false,
    newFilterDefault: '',
  });

  // Accept dialog (E4)
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [acceptDraft, setAcceptDraft] = useState({
    requireGitReview: false,
    gitReviewRef: '',
    comment: '',
  });

  // Outward Effects & Remote Dashboard Server dialog (E4 / E9)
  const [outwardOpen, setOutwardOpen] = useState(false);
  const [outwardDraft, setOutwardDraft] = useState({
    effectKind: 'subscription',
    enabled: true,
    publisherUserId: '1',
    configJson: '{"schedule": "daily"}',
    reviewResult: null,
    publicationId: '',
    deviceLabel: 'lobby-kiosk',
    lockedFiltersJson: '{}',
    mintedToken: '',
  });

  // Git sync dialog (E3)
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
      const tabs = dashboardModel?.tabs || [{id: 'main', name: 'Overview'}];
      const opts = tabs.map((tab, idx) => ({
        value: idx === 0 ? 'dashboard_composed' : `dashboard_tab_${tab.id}`,
        label: `Dashboard Tab: ${tab.name} (panels.composed@1)`,
      }));
      for (const card of dashboardModel?.cards || []) {
        opts.push({
          value: `card_view_${card.id}`,
          label: `Card: ${card.title}`,
        });
      }
      opts.push({
        value: 'dashboard_wiring',
        label: 'Wiring & Lineage (bi.analytics@1)',
      });
      return opts;
    }
    return [
      {
        value: 'question_chart',
        label: `Chart (${questionModel?.visualization?.type || 'bar'})`,
      },
      {
        value: 'question_lineage',
        label: 'Query Lineage (bi.analytics@1)',
      },
    ];
  }, [biKind, dashboardModel, questionModel]);

  const viewerWorkspace = useMemo(() => {
    if (!sessionState.workspace) return null;
    const resolvedView = resolveBiView(sessionState.workspace, activeView);
    return {
      ...sessionState.workspace,
      view: resolvedView,
    };
  }, [sessionState.workspace, activeView]);

  const suspectBindings = useMemo(
    () =>
      (sessionState.bindings || []).filter((b) => b.validity === 'suspect'),
    [sessionState.bindings]
  );

  const fanoutWarnings =
    questionModel?.review_flags?.fanout_warnings || [];
  const savedFilterFlags =
    questionModel?.review_flags?.saved_filter_values ||
    dashboardModel?.review_flags?.saved_filter_values ||
    [];
  const allMetricCards = useMemo(
    () =>
      (dashboardModel?.cards || []).filter((c) => c.type === 'metric_panel'),
    [dashboardModel]
  );
  const staticMetricCards = useMemo(
    () =>
      allMetricCards.filter(
        (c) => (c.metric_panel?.snapshot_mode || 'static') === 'static'
      ),
    [allMetricCards]
  );
  const collectorMetricCards = useMemo(
    () =>
      allMetricCards.filter(
        (c) => c.metric_panel?.snapshot_mode === 'collector_read_only'
      ),
    [allMetricCards]
  );

  const openQuestionEditor = () => {
    if (!questionModel) return;
    const sbsql = questionModel.query?.sbsql;
    const firstJoin = sbsql?.joins?.[0];
    setQueryDraft({
      visType: questionModel.visualization?.type || 'bar',
      baseRelation: sbsql ? sbsql.from.relation.join('.') : 'main.orders',
      baseAlias: sbsql?.from?.alias || 'orders',
      columnsCsv: sbsql
        ? sbsql.columns
          .map((c) => `${c.column.join('.')}:${c.alias}`)
          .join(', ')
        : 'orders.region:region',
      measuresCsv: sbsql
        ? sbsql.measures
          .map(
            (m) =>
              `${m.function}:${m.column ? m.column.join('.') : '*'}:${m.alias}`
          )
          .join(', ')
        : 'sum:orders.amount:total_amount',
      joinRelation: firstJoin ? firstJoin.relation.join('.') : '',
      joinAlias: firstJoin?.alias || '',
      joinType: firstJoin?.type || 'left',
      joinCardinality: firstJoin?.cardinality || 'many_to_one',
      joinLeftCol: firstJoin?.on?.[0]?.left
        ? firstJoin.on[0].left.join('.')
        : '',
      joinRightCol: firstJoin?.on?.[0]?.right
        ? firstJoin.on[0].right.join('.')
        : '',
      limit: String(sbsql?.limit ?? 100),
      note: '',
    });
    setQueryOpen(true);
  };

  const applyQuestionEdit = async () => {
    if (!questionModel) return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const columns = queryDraft.columnsCsv
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((entry) => {
          const [colPart, aliasPart] = entry.split(':').map((x) => x.trim());
          const parts = colPart.split('.').filter(Boolean);
          return {column: parts, alias: aliasPart || parts[parts.length - 1]};
        });
      const measures = queryDraft.measuresCsv
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((entry) => {
          const [fn, colPart, aliasPart] = entry
            .split(':')
            .map((x) => x.trim());
          const col =
            !colPart || colPart === '*'
              ? null
              : colPart.split('.').filter(Boolean);
          return {
            function: fn || 'sum',
            column: col,
            alias: aliasPart || `${fn || 'sum'}_${col ? col[col.length - 1] : 'rows'}`,
          };
        });
      const joins = [];
      if (queryDraft.joinRelation.trim()) {
        const jRel = queryDraft.joinRelation
          .trim()
          .split('.')
          .filter(Boolean);
        joins.push({
          type: queryDraft.joinType,
          relation: jRel,
          alias: queryDraft.joinAlias.trim() || jRel[jRel.length - 1],
          cardinality: queryDraft.joinCardinality,
          on: [
            {
              left: queryDraft.joinLeftCol.trim().split('.').filter(Boolean),
              op: '=',
              right: queryDraft.joinRightCol.trim().split('.').filter(Boolean),
            },
          ],
        });
      }
      const nextQuestion = {
        ...questionModel,
        visualization: {
          ...questionModel.visualization,
          type: queryDraft.visType,
        },
        query: {
          kind: 'sbsql',
          sbsql: {
            dialect: 'sbsql@1',
            from: {
              relation: queryDraft.baseRelation
                .trim()
                .split('.')
                .filter(Boolean),
              alias: queryDraft.baseAlias.trim() || 'base',
            },
            joins,
            columns,
            measures,
            limit: Number(queryDraft.limit) || 100,
          },
        },
      };
      const saved = await runToolbarCommand('bi.designer.save', () =>
        controller.saveBiModel({
          question: nextQuestion,
          note: queryDraft.note.trim() || 'Updated SBsql query & chart',
        })
      );
      setQueryOpen(false);
      await refreshAll(saved.design.version.version);
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to save question changes.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleVisualizationQuickChange = async (nextVisType) => {
    if (!questionModel || readOnly) return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const nextQuestion = {
        ...questionModel,
        visualization: {
          ...questionModel.visualization,
          type: nextVisType,
        },
      };
      const saved = await runToolbarCommand('bi.designer.save', () =>
        controller.saveBiModel({
          question: nextQuestion,
          note: `Changed visualization to ${nextVisType}`,
        })
      );
      await refreshAll(saved.design.version.version);
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to update chart profile.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleCompileSql = async (dialectOverride = null) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const dialect = dialectOverride || sqlDraft.dialect;
      const compiled = await runToolbarCommand('bi.designer.sql_bridge', () =>
        controller.biSqlBridge({
          action: 'compile_sql',
          dialect,
        })
      );
      setSqlDraft((cur) => ({
        ...cur,
        dialect,
        compiledSql: compiled.sql || '',
        compiledParams: compiled.parameters || [],
      }));
      setSqlOpen(true);
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to compile dialect SQL.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleImportSql = async (saveVersion = false) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const mapped = await runToolbarCommand('bi.designer.sql_bridge', () =>
        controller.biSqlBridge({
          action: 'from_sql',
          sql: sqlDraft.sqlInput,
          name: sessionState.title || 'Question',
          saveVersion,
        })
      );
      setSqlDraft((cur) => ({...cur, fidelityResult: mapped}));
      if (saveVersion && mapped?.saved?.design?.version?.version) {
        await refreshAll(mapped.saved.design.version.version);
      }
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to map SQL to SBsql.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleAiDraft = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await client.proposeBiAiDraft(projectId, {
        prompt: aiDraft.prompt,
        targetDesignId: biKind === 'question' ? designId : null,
        byokApiKey: aiDraft.byokApiKey.trim() || null,
      });
      setAiDraft((cur) => ({...cur, result: res}));
    } catch (err) {
      setSurfaceError(err?.message || 'AI draft proposal failed.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleAddCard = async () => {
    if (!dashboardModel) return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const cid = slugId(
        cardDraft.id || cardDraft.title,
        `card_${(dashboardModel.cards?.length || 0) + 1}`
      );
      const nextCard = {
        id: cid,
        tab_id: cardDraft.tabId || dashboardModel.tabs?.[0]?.id || 'main',
        type: cardDraft.type,
        title: cardDraft.title.trim() || cid,
        click_behavior: cardDraft.clickBehavior,
        layout: {
          x: 0,
          y: (dashboardModel.cards?.length || 0) * 8,
          w: 12,
          h: 8,
        },
      };
      if (cardDraft.type === 'question') {
        nextCard.question = {
          question_design_id: cardDraft.questionDesignId.trim(),
          pinned_version: cardDraft.followLatestAccepted
            ? null
            : Number(cardDraft.pinnedVersion) || 1,
          follow_latest_accepted: Boolean(cardDraft.followLatestAccepted),
        };
        nextCard.visualization = {type: cardDraft.visType, settings: {}};
      } else if (cardDraft.type === 'text') {
        nextCard.text = {markdown: cardDraft.markdown};
      } else {
        const mode = cardDraft.snapshotMode || 'static';
        nextCard.metric_panel = {
          panel_id: cardDraft.panelId.trim() || cid,
          snapshot_mode: mode,
        };
        if (mode === 'collector_read_only') {
          const metricKeys = cardDraft.collectorMetricKeysCsv
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean);
          nextCard.metric_panel.collector_binding = {
            engine: cardDraft.collectorEngine || 'postgresql',
            server_id: Math.max(1, Number(cardDraft.collectorServerId) || 1),
            target_id: cardDraft.collectorTargetId.trim() || null,
            metric_group:
              cardDraft.collectorMetricGroup.trim() || 'throughput',
            metric_keys: metricKeys.length ? metricKeys : ['tps'],
            freshness_budget_seconds: Math.max(
              5,
              Number(cardDraft.collectorFreshnessBudget) || 120
            ),
          };
        }
      }
      const nextDashboard = {
        ...dashboardModel,
        cards: [...(dashboardModel.cards || []), nextCard],
      };
      const saved = await runToolbarCommand('bi.designer.save', () =>
        controller.saveBiModel({
          dashboard: nextDashboard,
          note: `Added ${cardDraft.type} card ${nextCard.title}`,
        })
      );
      setCardOpen(false);
      await refreshAll(saved.design.version.version);
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to add dashboard card.');
    } finally {
      setBusyAction(false);
    }
  };

  const openInteractionDialog = () => {
    if (!dashboardModel) return;
    const inter = dashboardModel.interaction || {};
    setInteractionDraft({
      defaultClickBehavior: inter.default_click_behavior || 'cross_filter',
      autoApplyFilters: inter.auto_apply_filters !== false,
      filterStateScope: inter.filter_state_scope || 'personal',
      drillCarriesFilterContext: inter.drill_carries_filter_context !== false,
      newFilterId: '',
      newFilterName: '',
      newFilterPinned: false,
      newFilterDefault: '',
    });
    setInteractionOpen(true);
  };

  const handleSaveInteraction = async () => {
    if (!dashboardModel) return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const nextFilters = [...(dashboardModel.filters || [])];
      if (
        interactionDraft.newFilterId.trim() ||
        interactionDraft.newFilterName.trim()
      ) {
        const fid = slugId(
          interactionDraft.newFilterId || interactionDraft.newFilterName,
          'filter'
        );
        const fEntry = {
          id: fid,
          name: interactionDraft.newFilterName.trim() || fid,
          type: 'string',
          widget: 'text',
          operator: 'eq',
          pinned_by_author: Boolean(interactionDraft.newFilterPinned),
        };
        if (interactionDraft.newFilterDefault.trim()) {
          fEntry.default = interactionDraft.newFilterDefault.trim();
        }
        nextFilters.push(fEntry);
      }
      const nextDashboard = {
        ...dashboardModel,
        filters: nextFilters,
        interaction: {
          default_click_behavior: interactionDraft.defaultClickBehavior,
          auto_apply_filters: Boolean(interactionDraft.autoApplyFilters),
          filter_state_scope: interactionDraft.filterStateScope,
          drill_carries_filter_context: Boolean(
            interactionDraft.drillCarriesFilterContext
          ),
        },
      };
      const saved = await runToolbarCommand('bi.designer.save', () =>
        controller.saveBiModel({
          dashboard: nextDashboard,
          note: 'Updated dashboard interaction & filter behavior',
        })
      );
      setInteractionOpen(false);
      await refreshAll(saved.design.version.version);
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to update dashboard filters.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleSaveCheckpoint = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const saved = await runToolbarCommand('bi.designer.save', () =>
        controller.saveBiModel({
          question: questionModel,
          dashboard: dashboardModel,
          note: `Saved ${biKind} checkpoint`,
        })
      );
      await refreshAll(saved.design.version.version);
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to save checkpoint.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleAdvanceStatus = async (nextStatus) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      await controller.advanceStatus(nextStatus);
      await refreshAll(sessionState.currentVersion);
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to advance save-point status.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleAccept = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const accepted = await runToolbarCommand('bi.designer.accept', () =>
        controller.accept({
          requireGitReview: acceptDraft.requireGitReview,
          gitReviewRef: acceptDraft.gitReviewRef.trim() || null,
          comment: acceptDraft.comment.trim(),
        })
      );
      setAcceptBanner(accepted);
      setAcceptOpen(false);
      await refreshAll(sessionState.currentVersion);
    } catch (err) {
      setSurfaceError(err?.message || 'Acceptance failed.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleBranchDraft = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const branched = await controller.branchDraft({
        note: `Branched new draft from accepted ${biKind}`,
      });
      await refreshAll(branched.currentVersion);
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to branch draft.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleReviewOutward = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const cfg = JSON.parse(outwardDraft.configJson || '{}');
      const pubUid =
        outwardDraft.effectKind === 'dashboard_server'
          ? Number(outwardDraft.publisherUserId) || 1
          : null;
      const reviewed = await runToolbarCommand(
        'bi.designer.outward_review',
        () =>
          controller.reviewBiOutwardEffect({
            effectKind: outwardDraft.effectKind,
            enabled: outwardDraft.enabled,
            config: cfg,
            publisherUserId: pubUid,
          })
      );
      setOutwardDraft((cur) => ({
        ...cur,
        reviewResult: reviewed,
        publicationId:
          reviewed?.effect?.effect_kind === 'dashboard_server'
            ? reviewed.effect.id
            : cur.publicationId,
      }));
      await refreshAll(sessionState.currentVersion);
    } catch (err) {
      setSurfaceError(err?.message || 'Outward effect review failed.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleMintDeviceToken = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const locked = JSON.parse(outwardDraft.lockedFiltersJson || '{}');
      const minted = await controller.mintBiDeviceToken({
        publicationId: outwardDraft.publicationId.trim(),
        deviceLabel: outwardDraft.deviceLabel.trim() || 'kiosk',
        lockedFilters: locked,
      });
      setOutwardDraft((cur) => ({
        ...cur,
        mintedToken: minted?.device_token || '',
      }));
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to mint kiosk device token.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleAddActionButton = async () => {
    if (!dashboardModel) return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const aid = slugId(
        actionBtnDraft.label,
        `act_${(dashboardModel.action_buttons?.length || 0) + 1}`
      );
      const relParts = actionBtnDraft.targetRelation
        .split('.')
        .map((s) => s.trim())
        .filter(Boolean);
      const keyCols = actionBtnDraft.keyColumnsCsv
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const bindings = actionBtnDraft.bindingsCsv
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((entry) => {
          const [col, src, pName] = entry.split(':').map((x) => x.trim());
          return {
            column: col || 'id',
            source: src || 'prompt',
            parameter_name: pName || col || 'id',
            required: true,
          };
        });
      const nextBtn = {
        id: aid,
        label: actionBtnDraft.label.trim() || aid,
        operation_kind: actionBtnDraft.operationKind,
        target_endpoint_id:
          actionBtnDraft.targetEndpointId.trim() || 'default-endpoint',
        target_relation: relParts,
        key_columns: keyCols,
        parameter_bindings: bindings,
        approval_required: true,
      };
      const nextDashboard = {
        ...dashboardModel,
        action_buttons: [
          ...(dashboardModel.action_buttons || []).filter((b) => b.id !== aid),
          nextBtn,
        ],
      };
      const saved = await runToolbarCommand('bi.designer.save', () =>
        controller.saveBiModel({
          dashboard: nextDashboard,
          note: `Added write-back action button ${nextBtn.label}`,
        })
      );
      setActionBtnDraft((cur) => ({...cur, selectedActionId: aid, label: ''}));
      await refreshAll(saved.design.version.version);
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to save action button.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleTriggerActionReview = async (dryRun = false) => {
    const actionId =
      actionBtnDraft.selectedActionId ||
      dashboardModel?.action_buttons?.[0]?.id ||
      '';
    if (!actionId) return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const paramVals = JSON.parse(actionBtnDraft.parameterValuesJson || '{}');
      const res = await controller.submitBiActionReview({
        actionButtonId: actionId,
        parameterValues: paramVals,
        dialect: actionBtnDraft.dialect,
        dryRun,
      });
      setActionBtnDraft((cur) => ({...cur, reviewResult: res}));
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to prepare native review.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleReadCollectorSnapshot = async (explicitCardId = null) => {
    const targetCardId =
      explicitCardId ||
      collectorDraft.cardId ||
      allMetricCards[0]?.id ||
      '';
    if (!targetCardId) return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const snap = await controller.readBiCollectorPanel({
        cardId: targetCardId,
      });
      setCollectorDraft({
        cardId: targetCardId,
        snapshotResult: snap,
      });
    } catch (err) {
      setSurfaceError(err?.message || 'Failed to read collector snapshot.');
    } finally {
      setBusyAction(false);
    }
  };

  const handleGitAction = async (action) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.gitOperation({
        action,
        repository: gitDraft.repoRoot.trim(),
        repoRoot: gitDraft.repoRoot.trim(),
        path: gitDraft.path.trim() || `bi/${designId}.ddn`,
        branch: gitDraft.branch.trim() || 'main',
        note: gitDraft.note.trim(),
      });
      if (action === 'drift') {
        setGitDraft((cur) => ({...cur, driftResult: res}));
      } else {
        setGitOpen(false);
        await refreshAll();
      }
    } catch (err) {
      setSurfaceError(err?.message || `Git ${action} failed.`);
    } finally {
      setBusyAction(false);
    }
  };

  if (loading && !sessionState.loaded) {
    return (
      <Box
        sx={{position: 'relative', height: '100%', minHeight: 280}}
        aria-label="BI Designer loading"
      >
        <FormReference formKey="bi-designer" />
        <ProgressOverlay message="Loading BI design…" />
      </Box>
    );
  }

  if (!sessionState.loaded && surfaceError) {
    return (
      <Box sx={{p: 2}}>
        <FormReference formKey="bi-designer" />
        <EmptyState
          role="alert"
          message={surfaceError}
          actionLabel="Retry"
          onAction={() => refreshAll()}
        />
      </Box>
    );
  }

  const canEdit = !readOnly && sessionState.status !== 'accepted';

  return (
    <Box
      component="section"
      aria-label="BI Question and Dashboard Designer"
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="bi-designer" />
      <Toolbar label="BI designer toolbar">
        <StatusBadge
          status={statusTone(sessionState.status)}
          label={`${biKind === 'dashboard' ? 'Dashboard' : 'Question'} v${
            sessionState.currentVersion || 1
          } · ${sessionState.status || 'draft'}`}
        />
        {questionModel?.verification_tier && (
          <StatusBadge
            status={
              questionModel.verification_tier === 'endorsed'
                ? 'success'
                : 'info'
            }
            label={`Tier: ${questionModel.verification_tier}`}
          />
        )}
        <Select
          aria-label="BI DDN view"
          value={activeView}
          options={viewOptions}
          onChange={(val) => setActiveView(val)}
        />
        {biKind === 'question' && questionModel && (
          <>
            <Select
              aria-label="Chart visualization type"
              value={questionModel.visualization?.type || 'bar'}
              options={BI_CHART_TYPE_OPTIONS}
              disabled={!canEdit || busyAction}
              onChange={(val) => handleVisualizationQuickChange(val)}
            />
            <Button
              disabled={!canEdit || busyAction}
              onClick={openQuestionEditor}
            >
              Edit SBsql & Joins…
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => handleCompileSql(sqlDraft.dialect)}
            >
              SQL Bridge…
            </Button>
            <Button disabled={!canEdit || busyAction} onClick={() => setAiOpen(true)}>
              AI Draft…
            </Button>
          </>
        )}
        {biKind === 'dashboard' && dashboardModel && (
          <>
            <Button
              disabled={!canEdit || busyAction}
              onClick={() => setCardOpen(true)}
            >
              Add Card…
            </Button>
            <Button
              disabled={!canEdit || busyAction}
              onClick={openInteractionDialog}
            >
              Filters & Clicks…
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => {
                setActionBtnDraft((cur) => ({
                  ...cur,
                  selectedActionId:
                    cur.selectedActionId ||
                    dashboardModel.action_buttons?.[0]?.id ||
                    '',
                }));
                setActionBtnOpen(true);
              }}
            >
              Action Buttons ({dashboardModel.action_buttons?.length || 0})…
            </Button>
            {allMetricCards.length > 0 && (
              <Button
                disabled={busyAction}
                onClick={() => {
                  const firstId =
                    collectorDraft.cardId || allMetricCards[0]?.id || '';
                  setCollectorOpen(true);
                  if (firstId) handleReadCollectorSnapshot(firstId);
                }}
              >
                Collector Snapshots ({allMetricCards.length})…
              </Button>
            )}
          </>
        )}
        <Button
          disabled={!canEdit || busyAction}
          onClick={handleSaveCheckpoint}
        >
          Save Checkpoint
        </Button>
        {sessionState.status === 'draft' && !readOnly && (
          <Button
            disabled={busyAction}
            onClick={() => handleAdvanceStatus('in_progress')}
          >
            Mark In-Progress
          </Button>
        )}
        {sessionState.status === 'in_progress' && !readOnly && (
          <Button
            disabled={busyAction}
            onClick={() => handleAdvanceStatus('in_review')}
          >
            Submit for Review
          </Button>
        )}
        {sessionState.status !== 'accepted' && !readOnly && (
          <Button disabled={busyAction} onClick={() => setAcceptOpen(true)}>
            Accept…
          </Button>
        )}
        {sessionState.status === 'accepted' && !readOnly && (
          <Button disabled={busyAction} onClick={handleBranchDraft}>
            New Draft Version
          </Button>
        )}
        <Button disabled={busyAction} onClick={() => setOutwardOpen(true)}>
          Outward Effects ({outwardEffects.filter((e) => e.enabled).length})…
        </Button>
        <Button disabled={busyAction} onClick={() => setGitOpen(true)}>
          Git Sync…
        </Button>
      </Toolbar>

      {surfaceError && (
        <Alert severity="error" sx={{m: 1}}>
          {surfaceError}
        </Alert>
      )}

      {suspectBindings.length > 0 && (
        <Alert severity="warning" sx={{m: 1}}>
          {suspectBindings.length} catalog binding(s) are marked suspect after
          upstream schema changes.{' '}
          {!readOnly && (
            <Button
              onClick={() =>
                controller
                  .confirmSuspectBinding(suspectBindings[0].id)
                  .then(() => refreshAll())
              }
            >
              Confirm binding
            </Button>
          )}
        </Alert>
      )}

      {fanoutWarnings.length > 0 && (
        <Alert severity="warning" sx={{m: 1}}>
          SBsql join fan-out warning:{' '}
          {fanoutWarnings.map((w) => w.detail).join(' ')}
        </Alert>
      )}

      {savedFilterFlags.length > 0 && (
        <Alert severity="info" sx={{m: 1}}>
          Review saved filter literal/default values ({savedFilterFlags.length})
          before exporting DDN to Git or accepting.
        </Alert>
      )}

      {staticMetricCards.length > 0 && (
        <Alert severity="info" sx={{m: 1}}>
          Imported monitoring metric_panel card(s) ({staticMetricCards.length})
          hold static snapshots in BI and do not poll live collectors.
        </Alert>
      )}

      {collectorMetricCards.length > 0 && (
        <Alert severity="info" sx={{m: 1}}>
          Read-only collector metric_panel card(s) (
          {collectorMetricCards.length}) read MonitoringHost.snapshot on demand
          with viewer authorization and never start or mutate collectors.
        </Alert>
      )}

      {acceptBanner && (
        <Alert severity="success" sx={{m: 1}}>
          Version accepted and active in store. Outward effects activated:{' '}
          {String(Boolean(acceptBanner.outward_effects_activated))} (review
          subscriptions, embeds and dashboard-server publication separately).
        </Alert>
      )}

      <Box sx={{flex: 1, minHeight: 0, position: 'relative'}}>
        {viewerWorkspace && (
          <DDNViewerSurface
            snapshot={viewerWorkspace}
            title={sessionState.title || 'BI Design'}
            onExport={onExport}
            onError={onError}
          />
        )}
      </Box>

      {/* Question SBsql & Joins Dialog (E2) */}
      <Dialog
        open={queryOpen}
        title="Edit Unified SBsql Query & Joins"
        onClose={() => setQueryOpen(false)}
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 1.5, p: 1}}>
          <Select
            label="Chart Visualization"
            value={queryDraft.visType}
            options={BI_CHART_TYPE_OPTIONS}
            onChange={(val) => setQueryDraft((c) => ({...c, visType: val}))}
          />
          <TextField
            label="Base Relation (schema.table)"
            value={queryDraft.baseRelation}
            onChange={(e) =>
              setQueryDraft((c) => ({...c, baseRelation: e.target.value}))
            }
          />
          <TextField
            label="Base Alias"
            value={queryDraft.baseAlias}
            onChange={(e) =>
              setQueryDraft((c) => ({...c, baseAlias: e.target.value}))
            }
          />
          <TextField
            label="Columns (alias.col:label, comma-separated)"
            value={queryDraft.columnsCsv}
            onChange={(e) =>
              setQueryDraft((c) => ({...c, columnsCsv: e.target.value}))
            }
          />
          <TextField
            label="Measures (fn:alias.col:label, comma-separated)"
            value={queryDraft.measuresCsv}
            onChange={(e) =>
              setQueryDraft((c) => ({...c, measuresCsv: e.target.value}))
            }
          />
          <TextField
            label="Optional Join Relation (schema.table)"
            value={queryDraft.joinRelation}
            onChange={(e) =>
              setQueryDraft((c) => ({...c, joinRelation: e.target.value}))
            }
          />
          {queryDraft.joinRelation.trim() && (
            <>
              <Select
                label="Join Type"
                value={queryDraft.joinType}
                options={JOIN_TYPE_OPTIONS}
                onChange={(val) =>
                  setQueryDraft((c) => ({...c, joinType: val}))
                }
              />
              <Select
                label="Join Cardinality"
                value={queryDraft.joinCardinality}
                options={JOIN_CARDINALITY_OPTIONS}
                onChange={(val) =>
                  setQueryDraft((c) => ({...c, joinCardinality: val}))
                }
              />
              <TextField
                label="Join Left Key (alias.col)"
                value={queryDraft.joinLeftCol}
                onChange={(e) =>
                  setQueryDraft((c) => ({...c, joinLeftCol: e.target.value}))
                }
              />
              <TextField
                label="Join Right Key (alias.col)"
                value={queryDraft.joinRightCol}
                onChange={(e) =>
                  setQueryDraft((c) => ({...c, joinRightCol: e.target.value}))
                }
              />
            </>
          )}
          <TextField
            label="Row Limit"
            value={queryDraft.limit}
            onChange={(e) =>
              setQueryDraft((c) => ({...c, limit: e.target.value}))
            }
          />
          <Box sx={{display: 'flex', gap: 1, justifyContent: 'flex-end'}}>
            <Button onClick={() => setQueryOpen(false)}>Cancel</Button>
            <Button disabled={busyAction} onClick={applyQuestionEdit}>
              Save Query
            </Button>
          </Box>
        </Box>
      </Dialog>

      {/* SQL Bridge Dialog (E2) */}
      <Dialog
        open={sqlOpen}
        title="BI <-> Visual SQL Builder Bridge"
        onClose={() => setSqlOpen(false)}
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 1.5, p: 1}}>
          <Select
            label="Target SQL Dialect"
            value={sqlDraft.dialect}
            options={DIALECT_OPTIONS}
            onChange={(val) => handleCompileSql(val)}
          />
          <TextArea
            label="Compiled Dialect SQL (parameters always bound)"
            readOnly
            value={sqlDraft.compiledSql}
          />
          {sqlDraft.compiledParams.length > 0 && (
            <Alert severity="info">
              Bound parameters: {JSON.stringify(sqlDraft.compiledParams)}
            </Alert>
          )}
          {!readOnly && (
            <>
              <TextArea
                label="Import Read-Only SELECT SQL into Question"
                value={sqlDraft.sqlInput}
                onChange={(e) =>
                  setSqlDraft((c) => ({...c, sqlInput: e.target.value}))
                }
              />
              <Box sx={{display: 'flex', gap: 1}}>
                <Button
                  disabled={busyAction || !sqlDraft.sqlInput.trim()}
                  onClick={() => handleImportSql(false)}
                >
                  Check SQL Fidelity
                </Button>
                <Button
                  disabled={!canEdit || busyAction || !sqlDraft.sqlInput.trim()}
                  onClick={() => handleImportSql(true)}
                >
                  Apply SQL to Draft
                </Button>
              </Box>
            </>
          )}
          {sqlDraft.fidelityResult && (
            <Alert
              severity={
                sqlDraft.fidelityResult.fidelity === 'exact'
                  ? 'success'
                  : 'warning'
              }
            >
              SQL mapping fidelity: {sqlDraft.fidelityResult.fidelity}
              {sqlDraft.fidelityResult.loss?.length
                ? ` (${sqlDraft.fidelityResult.loss.join('; ')})`
                : ''}
            </Alert>
          )}
          <Box sx={{display: 'flex', gap: 1, justifyContent: 'flex-end'}}>
            <Button onClick={() => setSqlOpen(false)}>Close</Button>
          </Box>
        </Box>
      </Dialog>

      {/* Optional BYOK AI Draft Dialog (E8) */}
      <Dialog
        open={aiOpen}
        title="Draft BI Question with Optional BYOK AI"
        onClose={() => setAiOpen(false)}
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 1.5, p: 1}}>
          <Alert severity="info">
            Searches existing BI questions first and proposes only a draft or
            diff. AI agents never accept, merge or publish outward effects.
          </Alert>
          <TextArea
            label="Question Prompt"
            value={aiDraft.prompt}
            onChange={(e) =>
              setAiDraft((c) => ({...c, prompt: e.target.value}))
            }
          />
          <TextField
            label="Optional BYOK API Key (kept in memory only)"
            type="password"
            value={aiDraft.byokApiKey}
            onChange={(e) =>
              setAiDraft((c) => ({...c, byokApiKey: e.target.value}))
            }
          />
          <Box sx={{display: 'flex', gap: 1, justifyContent: 'flex-end'}}>
            <Button onClick={() => setAiOpen(false)}>Close</Button>
            <Button
              disabled={busyAction || !aiDraft.prompt.trim()}
              onClick={handleAiDraft}
            >
              Search & Propose Draft
            </Button>
          </Box>
          {aiDraft.result && (
            <Alert severity="success">
              Existing matches found:{' '}
              {aiDraft.result.existing_matches?.length || 0}. Proposed status:{' '}
              {aiDraft.result.status || 'draft'}.
            </Alert>
          )}
        </Box>
      </Dialog>

      {/* Dashboard Add Card Dialog (E3 / E5 / E6 / E7) */}
      <Dialog
        open={cardOpen}
        title="Add Dashboard Card"
        onClose={() => setCardOpen(false)}
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 1.5, p: 1}}>
          <Select
            label="Card Type"
            value={cardDraft.type}
            options={[
              {value: 'question', label: 'Question Card (by Design ID)'},
              {value: 'text', label: 'Markdown Note Card'},
              {
                value: 'metric_panel',
                label: 'Imported Monitoring Snapshot (static)',
              },
            ]}
            onChange={(val) => setCardDraft((c) => ({...c, type: val}))}
          />
          <TextField
            label="Card Title"
            value={cardDraft.title}
            onChange={(e) =>
              setCardDraft((c) => ({...c, title: e.target.value}))
            }
          />
          <Select
            label="Card Click Behavior"
            value={cardDraft.clickBehavior}
            options={CLICK_BEHAVIOR_OPTIONS}
            onChange={(val) =>
              setCardDraft((c) => ({...c, clickBehavior: val}))
            }
          />
          {cardDraft.type === 'question' && (
            <>
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
              <Select
                label="Card Visualization"
                value={cardDraft.visType}
                options={BI_CHART_TYPE_OPTIONS}
                onChange={(val) => setCardDraft((c) => ({...c, visType: val}))}
              />
              <Checkbox
                label="Follow latest accepted question version"
                checked={cardDraft.followLatestAccepted}
                onChange={(checked) =>
                  setCardDraft((c) => ({
                    ...c,
                    followLatestAccepted: Boolean(checked),
                  }))
                }
              />
              {!cardDraft.followLatestAccepted && (
                <TextField
                  label="Pinned Question Version"
                  value={cardDraft.pinnedVersion}
                  onChange={(e) =>
                    setCardDraft((c) => ({
                      ...c,
                      pinnedVersion: e.target.value,
                    }))
                  }
                />
              )}
            </>
          )}
          {cardDraft.type === 'text' && (
            <TextArea
              label="Markdown Text"
              value={cardDraft.markdown}
              onChange={(e) =>
                setCardDraft((c) => ({...c, markdown: e.target.value}))
              }
            />
          )}
          {cardDraft.type === 'metric_panel' && (
            <>
              <TextField
                label="Source Monitoring Panel ID"
                value={cardDraft.panelId}
                onChange={(e) =>
                  setCardDraft((c) => ({...c, panelId: e.target.value}))
                }
              />
              <Select
                label="Metric Panel Snapshot Mode"
                value={cardDraft.snapshotMode}
                options={SNAPSHOT_MODE_OPTIONS}
                onChange={(val) =>
                  setCardDraft((c) => ({...c, snapshotMode: val}))
                }
              />
              {cardDraft.snapshotMode === 'collector_read_only' && (
                <>
                  <Select
                    label="Collector Engine"
                    value={cardDraft.collectorEngine}
                    options={DIALECT_OPTIONS}
                    onChange={(val) =>
                      setCardDraft((c) => ({...c, collectorEngine: val}))
                    }
                  />
                  <TextField
                    label="Collector Server ID"
                    value={cardDraft.collectorServerId}
                    onChange={(e) =>
                      setCardDraft((c) => ({
                        ...c,
                        collectorServerId: e.target.value,
                      }))
                    }
                  />
                  <TextField
                    label="Collector Metric Group"
                    value={cardDraft.collectorMetricGroup}
                    onChange={(e) =>
                      setCardDraft((c) => ({
                        ...c,
                        collectorMetricGroup: e.target.value,
                      }))
                    }
                  />
                  <TextField
                    label="Collector Metric Keys (comma-separated)"
                    value={cardDraft.collectorMetricKeysCsv}
                    onChange={(e) =>
                      setCardDraft((c) => ({
                        ...c,
                        collectorMetricKeysCsv: e.target.value,
                      }))
                    }
                  />
                </>
              )}
            </>
          )}
          <Box sx={{display: 'flex', gap: 1, justifyContent: 'flex-end'}}>
            <Button onClick={() => setCardOpen(false)}>Cancel</Button>
            <Button disabled={busyAction} onClick={handleAddCard}>
              Add Card
            </Button>
          </Box>
        </Box>
      </Dialog>

      {/* Dashboard Filters & Interaction Dialog (E5) */}
      <Dialog
        open={interactionOpen}
        title="Dashboard Interaction & Filters"
        onClose={() => setInteractionOpen(false)}
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 1.5, p: 1}}>
          <Select
            label="Default Card Click Behavior"
            value={interactionDraft.defaultClickBehavior}
            options={DASHBOARD_DEFAULT_CLICK_OPTIONS}
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
          <Checkbox
            label="Auto-apply dashboard filters immediately"
            checked={interactionDraft.autoApplyFilters}
            onChange={(checked) =>
              setInteractionDraft((c) => ({
                ...c,
                autoApplyFilters: Boolean(checked),
              }))
            }
          />
          <Checkbox
            label="Drill-through carries active & cross-filter context"
            checked={interactionDraft.drillCarriesFilterContext}
            onChange={(checked) =>
              setInteractionDraft((c) => ({
                ...c,
                drillCarriesFilterContext: Boolean(checked),
              }))
            }
          />
          <TextField
            label="Add Filter Label (optional)"
            value={interactionDraft.newFilterName}
            onChange={(e) =>
              setInteractionDraft((c) => ({
                ...c,
                newFilterName: e.target.value,
              }))
            }
          />
          <Checkbox
            label="Pin new filter default for all viewers"
            checked={interactionDraft.newFilterPinned}
            onChange={(checked) =>
              setInteractionDraft((c) => ({
                ...c,
                newFilterPinned: Boolean(checked),
              }))
            }
          />
          <TextField
            label="New Filter Default Value (flagged for review)"
            value={interactionDraft.newFilterDefault}
            onChange={(e) =>
              setInteractionDraft((c) => ({
                ...c,
                newFilterDefault: e.target.value,
              }))
            }
          />
          <Box sx={{display: 'flex', gap: 1, justifyContent: 'flex-end'}}>
            <Button onClick={() => setInteractionOpen(false)}>Cancel</Button>
            <Button disabled={busyAction} onClick={handleSaveInteraction}>
              Save Interaction
            </Button>
          </Box>
        </Box>
      </Dialog>

      {/* Accept Version Dialog (E4) */}
      <Dialog
        open={acceptOpen}
        title="Accept BI Design Version"
        onClose={() => setAcceptOpen(false)}
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 1.5, p: 1}}>
          <Alert severity="info">
            Accepting makes this version active in the store. Subscriptions,
            embeds and dashboard-server publication stay off until separately
            reviewed.
          </Alert>
          <Checkbox
            label="Require Git review reference"
            checked={acceptDraft.requireGitReview}
            onChange={(checked) =>
              setAcceptDraft((c) => ({
                ...c,
                requireGitReview: Boolean(checked),
              }))
            }
          />
          {acceptDraft.requireGitReview && (
            <TextField
              label="Git Review Reference (PR / Commit)"
              value={acceptDraft.gitReviewRef}
              onChange={(e) =>
                setAcceptDraft((c) => ({...c, gitReviewRef: e.target.value}))
              }
            />
          )}
          <TextField
            label="Approval Comment"
            value={acceptDraft.comment}
            onChange={(e) =>
              setAcceptDraft((c) => ({...c, comment: e.target.value}))
            }
          />
          <Box sx={{display: 'flex', gap: 1, justifyContent: 'flex-end'}}>
            <Button onClick={() => setAcceptOpen(false)}>Cancel</Button>
            <Button disabled={busyAction} onClick={handleAccept}>
              Accept Version
            </Button>
          </Box>
        </Box>
      </Dialog>

      {/* Outward Effects & Remote Dashboard Server Dialog (E4 / E9) */}
      <Dialog
        open={outwardOpen}
        title="Outward Effects & Remote Dashboard Server"
        onClose={() => setOutwardOpen(false)}
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 1.5, p: 1}}>
          <Select
            label="Outward Effect"
            value={outwardDraft.effectKind}
            options={
              biKind === 'dashboard'
                ? [
                  {value: 'subscription', label: 'Scheduled Subscription / Alert'},
                  {value: 'embed', label: 'External Embed'},
                  {
                    value: 'dashboard_server',
                    label: 'Remote Dashboard Server Publication',
                  },
                ]
                : [
                  {value: 'subscription', label: 'Scheduled Subscription / Alert'},
                  {value: 'embed', label: 'External Embed'},
                ]
            }
            onChange={(val) =>
              setOutwardDraft((c) => ({...c, effectKind: val}))
            }
          />
          <Checkbox
            label="Enable outward effect for active accepted version"
            checked={outwardDraft.enabled}
            onChange={(checked) =>
              setOutwardDraft((c) => ({...c, enabled: Boolean(checked)}))
            }
          />
          {outwardDraft.effectKind === 'dashboard_server' && (
            <TextField
              label="Explicit Publisher User ID (display-only identity)"
              value={outwardDraft.publisherUserId}
              onChange={(e) =>
                setOutwardDraft((c) => ({
                  ...c,
                  publisherUserId: e.target.value,
                }))
              }
            />
          )}
          <TextArea
            label="Runtime Effect Configuration JSON (never stored in DDN/Git)"
            value={outwardDraft.configJson}
            onChange={(e) =>
              setOutwardDraft((c) => ({...c, configJson: e.target.value}))
            }
          />
          <Button disabled={busyAction} onClick={handleReviewOutward}>
            Review & Apply Switch
          </Button>
          {outwardDraft.reviewResult?.exposure_diff && (
            <Alert severity="info">
              Reviewed exposure change:{' '}
              {String(outwardDraft.reviewResult.exposure_diff.was_enabled)} →{' '}
              {String(outwardDraft.reviewResult.exposure_diff.now_enabled)}
            </Alert>
          )}
          {biKind === 'dashboard' && (
            <>
              <TextField
                label="Publication ID for Kiosk Device Token"
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
                  setOutwardDraft((c) => ({...c, deviceLabel: e.target.value}))
                }
              />
              <TextArea
                label="Locked Narrowing Filters JSON"
                value={outwardDraft.lockedFiltersJson}
                onChange={(e) =>
                  setOutwardDraft((c) => ({
                    ...c,
                    lockedFiltersJson: e.target.value,
                  }))
                }
              />
              <Button
                disabled={busyAction || !outwardDraft.publicationId.trim()}
                onClick={handleMintDeviceToken}
              >
                Mint Narrowing Device Token
              </Button>
              {outwardDraft.mintedToken && (
                <Alert severity="success">
                  Device token minted for{' '}
                  {`/cdeadmin/api/bi-server/dashboards/${outwardDraft.publicationId}`}
                  : {outwardDraft.mintedToken}
                </Alert>
              )}
            </>
          )}
          <Box sx={{display: 'flex', gap: 1, justifyContent: 'flex-end'}}>
            <Button onClick={() => setOutwardOpen(false)}>Close</Button>
          </Box>
        </Box>
      </Dialog>

      {/* Git Sync Dialog (E3) */}
      <Dialog
        open={gitOpen}
        title="BI Design Git Synchronization"
        onClose={() => setGitOpen(false)}
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 1.5, p: 1}}>
          <Alert severity="info">
            Only DDN design text is exchanged with Git; users, grants,
            recipients and secrets remain in the runtime store.
          </Alert>
          <TextField
            label="Local Git Repository Root"
            value={gitDraft.repoRoot}
            onChange={(e) =>
              setGitDraft((c) => ({...c, repoRoot: e.target.value}))
            }
          />
          <TextField
            label="DDN File Path in Repository"
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
          <Box sx={{display: 'flex', gap: 1, justifyContent: 'flex-end'}}>
            <Button
              disabled={busyAction}
              onClick={() => handleGitAction('drift')}
            >
              Check Drift
            </Button>
            <Button
              disabled={busyAction || readOnly}
              onClick={() => handleGitAction('load')}
            >
              Load from Git
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => handleGitAction('save')}
            >
              Save to Git
            </Button>
          </Box>
          {gitDraft.driftResult && (
            <Alert severity="info">
              Git status: {JSON.stringify(gitDraft.driftResult)}
            </Alert>
          )}
        </Box>
      </Dialog>

      {/* Dashboard Write-Back Action Buttons & Native Review Dialog (E6) */}
      <Dialog
        open={actionBtnOpen}
        title="BI Write-Back Action Buttons (Native-Operation Review)"
        onClose={() => setActionBtnOpen(false)}
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 1.5, p: 1}}>
          <Alert severity="warning">
            BI action buttons never execute SQL directly. Triggering an action
            submits a parameterized operation to OperationBus in
            awaiting_approval stage for human native-operation review.
          </Alert>
          {canEdit && (
            <>
              <TextField
                label="New Action Button Label"
                value={actionBtnDraft.label}
                onChange={(e) =>
                  setActionBtnDraft((c) => ({...c, label: e.target.value}))
                }
              />
              <Select
                label="Action Operation Kind"
                value={actionBtnDraft.operationKind}
                options={ACTION_OPERATION_OPTIONS}
                onChange={(val) =>
                  setActionBtnDraft((c) => ({...c, operationKind: val}))
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
                label="Target Relation (schema.table)"
                value={actionBtnDraft.targetRelation}
                onChange={(e) =>
                  setActionBtnDraft((c) => ({
                    ...c,
                    targetRelation: e.target.value,
                  }))
                }
              />
              <TextField
                label="Key Columns (comma-separated, required for UPDATE/DELETE)"
                value={actionBtnDraft.keyColumnsCsv}
                onChange={(e) =>
                  setActionBtnDraft((c) => ({
                    ...c,
                    keyColumnsCsv: e.target.value,
                  }))
                }
              />
              <TextField
                label="Parameter Bindings (col:source:param, comma-separated)"
                value={actionBtnDraft.bindingsCsv}
                onChange={(e) =>
                  setActionBtnDraft((c) => ({
                    ...c,
                    bindingsCsv: e.target.value,
                  }))
                }
              />
              <Button
                disabled={busyAction || !actionBtnDraft.label.trim()}
                onClick={handleAddActionButton}
              >
                Save Action Button to Draft
              </Button>
            </>
          )}
          {(dashboardModel?.action_buttons || []).length > 0 && (
            <>
              <Select
                label="Configured Action Button"
                value={
                  actionBtnDraft.selectedActionId ||
                  dashboardModel.action_buttons[0].id
                }
                options={dashboardModel.action_buttons.map((b) => ({
                  value: b.id,
                  label: `${b.label} (${b.operation_kind})`,
                }))}
                onChange={(val) =>
                  setActionBtnDraft((c) => ({...c, selectedActionId: val}))
                }
              />
              <Select
                label="SQL Preview Dialect"
                value={actionBtnDraft.dialect}
                options={DIALECT_OPTIONS}
                onChange={(val) =>
                  setActionBtnDraft((c) => ({...c, dialect: val}))
                }
              />
              <TextArea
                label="Bound Parameter Values JSON"
                value={actionBtnDraft.parameterValuesJson}
                onChange={(e) =>
                  setActionBtnDraft((c) => ({
                    ...c,
                    parameterValuesJson: e.target.value,
                  }))
                }
              />
              <Box sx={{display: 'flex', gap: 1}}>
                <Button
                  disabled={busyAction}
                  onClick={() => handleTriggerActionReview(true)}
                >
                  Preview Dry-Run SQL
                </Button>
                {!readOnly && sessionState.status === 'accepted' && (
                  <Button
                    disabled={busyAction}
                    onClick={() => handleTriggerActionReview(false)}
                  >
                    Submit to Native Review
                  </Button>
                )}
              </Box>
            </>
          )}
          {actionBtnDraft.reviewResult && (
            <>
              <Alert severity="warning">
                {actionBtnDraft.reviewResult.destructive_warning}
              </Alert>
              {actionBtnDraft.reviewResult.operation_id && (
                <Alert severity="success">
                  Operation queued: {actionBtnDraft.reviewResult.operation_id} ·
                  Stage: {actionBtnDraft.reviewResult.stage}
                </Alert>
              )}
              <TextArea
                label="Parameterized Native-Review SQL"
                readOnly
                value={actionBtnDraft.reviewResult.sql || ''}
              />
            </>
          )}
          <Box sx={{display: 'flex', gap: 1, justifyContent: 'flex-end'}}>
            <Button onClick={() => setActionBtnOpen(false)}>Close</Button>
          </Box>
        </Box>
      </Dialog>

      {/* Read-Only Collector Metric Panel Snapshot Dialog (E7) */}
      <Dialog
        open={collectorOpen}
        title="Metric Panel Collector Snapshot (Read-Only)"
        onClose={() => setCollectorOpen(false)}
      >
        <Box sx={{display: 'flex', flexDirection: 'column', gap: 1.5, p: 1}}>
          {allMetricCards.length > 0 && (
            <Select
              label="Metric Panel Card"
              value={collectorDraft.cardId || allMetricCards[0].id}
              options={allMetricCards.map((c) => ({
                value: c.id,
                label: `${c.title} (${
                  c.metric_panel?.snapshot_mode || 'static'
                })`,
              }))}
              onChange={(val) => handleReadCollectorSnapshot(val)}
            />
          )}
          <Button
            disabled={busyAction || !allMetricCards.length}
            onClick={() => handleReadCollectorSnapshot()}
          >
            Refresh Read-Only Snapshot
          </Button>
          {collectorDraft.snapshotResult && (
            <>
              <Alert
                severity={
                  collectorDraft.snapshotResult.freshness_status === 'live' ||
                  collectorDraft.snapshotResult.freshness_status ===
                    'static_snapshot'
                    ? 'success'
                    : 'warning'
                }
              >
                Mode: {collectorDraft.snapshotResult.snapshot_mode} · Collector
                state: {collectorDraft.snapshotResult.collector_state} ·
                Freshness: {collectorDraft.snapshotResult.freshness_status}
                {collectorDraft.snapshotResult.observed_at
                  ? ` · Observed: ${collectorDraft.snapshotResult.observed_at}`
                  : ''}
              </Alert>
              <TextArea
                label="Snapshot Rows JSON"
                readOnly
                value={JSON.stringify(
                  collectorDraft.snapshotResult.rows || [],
                  null,
                  2
                )}
              />
            </>
          )}
          <Box sx={{display: 'flex', gap: 1, justifyContent: 'flex-end'}}>
            <Button onClick={() => setCollectorOpen(false)}>Close</Button>
          </Box>
        </Box>
      </Dialog>
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
