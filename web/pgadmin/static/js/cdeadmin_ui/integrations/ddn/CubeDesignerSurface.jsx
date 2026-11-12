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
import {Box, ScrollArea, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Checkbox, Select} from '../../primitives/Choice';
import {NumberField, TextField} from '../../primitives/Field';
import {Dialog} from '../../overlays/Dialog';
import {EmptyState} from '../../feedback/EmptyState';
import {Banner} from '../../feedback/Indicators';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import {StatusBadge} from '../../status/StatusBadge';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {
  useQueryExecutionController,
  QueryExecutionToolbarCluster,
  QueryStepStatusFooter,
} from '../../query';
import {
  DesignCheckpointHistoryDrawer,
  DesignerModalTabs,
  DesignerTabbedMenu,
  FormGrid,
  TypedRowsEditor,
  WhereUsedDialog,
} from './DesignerChrome';
import {DDNViewerSurface} from './DDNViewerSurface';
import {
  DesignStoreClient,
  SharedDDNTaskController,
} from './sharedDesignLibrary';

const CUBE_VIEW_OPTIONS = Object.freeze([
  {
    value: 'cube_star',
    label: 'Dimensional Star (cube.dimensional@1)',
  },
  {
    value: 'cube_usage_matrix',
    label: 'Dimension Usage Matrix (matrix.relations@1)',
  },
  {
    value: 'cube_aggregation_grid',
    label: 'Aggregation Grid (table.records@1)',
  },
]);

const ENGINE_OPTIONS = Object.freeze([
  {value: 'postgresql', label: 'PostgreSQL'},
  {value: 'duckdb', label: 'DuckDB'},
  {value: 'sqlite', label: 'SQLite'},
  {value: 'firebird', label: 'Firebird 5'},
  {value: 'mysql', label: 'MySQL'},
  {value: 'mariadb', label: 'MariaDB'},
]);

const AGGREGATION_OPTIONS = Object.freeze([
  {value: 'sum', label: 'SUM'},
  {value: 'count', label: 'COUNT'},
  {value: 'count_distinct', label: 'COUNT DISTINCT'},
  {value: 'avg', label: 'AVG'},
  {value: 'min', label: 'MIN'},
  {value: 'max', label: 'MAX'},
  {value: 'last_value', label: 'LAST VALUE (semi-additive)'},
  {value: 'first_value', label: 'FIRST VALUE (semi-additive)'},
  {value: 'last_non_empty', label: 'LAST NON-EMPTY (semi-additive)'},
  {value: 'first_non_empty', label: 'FIRST NON-EMPTY (semi-additive)'},
  {value: 'avg_over_time', label: 'AVG OVER TIME (semi-additive)'},
]);

const SEMI_ADDITIVE_SET = new Set([
  'last_value',
  'first_value',
  'last_non_empty',
  'first_non_empty',
  'avg_over_time',
]);

const HIERARCHY_KIND_OPTIONS = Object.freeze([
  {value: 'none', label: 'None'},
  {value: 'level', label: 'Level hierarchy'},
  {value: 'parent_child', label: 'Parent-child recursive hierarchy'},
]);

const UNKNOWN_MEMBER_POLICY_OPTIONS = Object.freeze([
  {value: 'unknown', label: 'Map to Unknown member (COALESCE)'},
  {value: 'hide', label: 'Hide orphan rows (INNER JOIN)'},
  {value: 'error', label: 'Reject orphan rows (Error)'},
]);

const ATTRIBUTE_REL_OPTIONS = Object.freeze([
  {value: 'changing', label: 'Changing (SCD Type 1/2)'},
  {value: 'fixed', label: 'Fixed (Immutable relationship)'},
]);

const PARTITION_GRAIN_OPTIONS = Object.freeze([
  {value: 'none', label: 'None (unpartitioned)'},
  {value: 'day', label: 'Day'},
  {value: 'month', label: 'Month'},
  {value: 'year', label: 'Year'},
]);

const REFRESH_POLICY_OPTIONS = Object.freeze([
  {value: 'manual', label: 'Manual'},
  {value: 'incremental', label: 'Incremental'},
  {value: 'full_rebuild', label: 'Full rebuild'},
]);

const INTERCHANGE_FORMAT_OPTIONS = Object.freeze([
  {
    value: 'sml',
    label: 'SML v1.8 (Semantic Modeling Language YAML bundle — primary)',
  },
  {
    value: 'ossie',
    label: 'Apache Ossie v0.2.0 (lossy YAML/JSON export with loss report)',
  },
]);

const TRANSLATION_TARGET_KIND_OPTIONS = Object.freeze([
  {value: 'measure', label: 'Measure'},
  {value: 'dimension', label: 'Dimension'},
  {value: 'attribute', label: 'Attribute'},
  {value: 'hierarchy', label: 'Hierarchy'},
  {value: 'level', label: 'Level'},
  {value: 'measure_group', label: 'Measure Group'},
  {value: 'perspective', label: 'Perspective'},
]);

function resolveCubeView(workspace, requestedView) {
  if (!workspace?.files) return workspace?.view || '';
  const entryText = workspace.files[workspace.entry] || '';
  if (
    entryText.includes(`view "${requestedView}"`) ||
    entryText.includes(`view ${requestedView}`)
  ) {
    return requestedView;
  }
  return workspace.view;
}

function slugId(raw, fallback = 'item') {
  const cleaned = String(raw || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '');
  if (!cleaned) return fallback;
  return /^[a-z]/.test(cleaned) ? cleaned : `${fallback}_${cleaned}`;
}

function computeLocalCuboidReduction({
  candidates,
  mandatory,
  hierarchyChains,
  jointGroups,
  maxCap,
}) {
  const dedup = [];
  for (const item of [
    ...candidates,
    ...mandatory,
    ...hierarchyChains.flat(),
    ...jointGroups.flat(),
  ]) {
    if (item && !dedup.includes(item)) dedup.push(item);
  }
  if (!dedup.length || dedup.length > 14) {
    const n = Math.min(dedup.length, 14);
    const naive = 2 ** n;
    return {naive, afterMj: naive, finalCount: Math.max(0, naive - 1)};
  }
  const total = 1 << dedup.length;
  const mandatorySet = new Set(mandatory);
  let afterMj = 0;
  let finalCount = 0;
  for (let mask = 0; mask < total; mask += 1) {
    const subset = [];
    for (let bit = 0; bit < dedup.length; bit += 1) {
      if (mask & (1 << bit)) subset.push(dedup[bit]);
    }
    const subSet = new Set(subset);
    let mandOk = true;
    for (const m of mandatorySet) {
      if (!subSet.has(m)) {
        mandOk = false;
        break;
      }
    }
    if (!mandOk) continue;
    let jointOk = true;
    for (const grp of jointGroups) {
      if (!grp.length) continue;
      const hits = grp.filter((g) => subSet.has(g)).length;
      if (hits > 0 && hits < grp.length) {
        jointOk = false;
        break;
      }
    }
    if (!jointOk) continue;
    afterMj += 1;
    if (subset.length === 0) continue;
    let hierOk = true;
    for (const chain of hierarchyChains) {
      const present = chain.filter((c) => subSet.has(c));
      for (let i = 0; i < present.length; i += 1) {
        if (present[i] !== chain[i]) {
          hierOk = false;
          break;
        }
      }
      if (!hierOk) break;
    }
    if (!hierOk) continue;
    if (maxCap !== null && maxCap !== undefined && maxCap !== '' && subset.length > Number(maxCap)) {
      continue;
    }
    finalCount += 1;
  }
  return {naive: total, afterMj, finalCount};
}

function ensureMeasureGroups(cubeModel) {
  if (cubeModel?.measure_groups?.length) {
    return cubeModel.measure_groups.map((g) => ({
      ...g,
      measures: [...(g.measures || [])],
      dimension_usage: [...(g.dimension_usage || [])],
    }));
  }
  const factSrc =
    cubeModel?.sources?.find((s) => s.classification === 'fact') ||
    cubeModel?.sources?.[0] ||
    {id: 'fact_rows'};
  return [
    {
      id: `mg_${factSrc.id}`,
      name: `${cubeModel?.name || 'Cube'} Measures`,
      fact_source: factSrc.id,
      measures: (cubeModel?.measures || []).map((m) => m.id),
      dimension_usage: (cubeModel?.dimensions || []).map((d) => ({
        dimension_id: d.id,
        relationship_kind: 'regular',
        active: d.active !== false,
        ...(d.join_id ? {join_id: d.join_id} : {}),
      })),
    },
  ];
}

export function CubeDesignerSurface({
  projectId,
  designId,
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
        kind: 'cube',
      }),
    [suppliedController, client, projectId, designId]
  );

  const callbacks = useRef({executeCommand, onStateChange, onError});
  callbacks.current = {executeCommand, onStateChange, onError};

  const [sessionState, setSessionState] = useState(() => controller.state());
  const [cubePayload, setCubePayload] = useState(null);
  const [localizedPreviewModel, setLocalizedPreviewModel] = useState(null);
  const [previewLocale, setPreviewLocale] = useState('');
  const [loading, setLoading] = useState(!sessionState.loaded);
  const [surfaceError, setSurfaceError] = useState('');
  const [cubeView, setCubeView] = useState('cube_star');
  const [activeRibbonTab, setActiveRibbonTab] = useState('cube');
  const [busyAction, setBusyAction] = useState(false);
  const [activeDrift, setActiveDrift] = useState(null);
  const [appliedInfo, setAppliedInfo] = useState(null);

  // Shared cross-designer dialogs
  const [checkpointsOpen, setCheckpointsOpen] = useState(false);
  const [whereUsedOpen, setWhereUsedOpen] = useState(false);

  // Cube Properties modal (cube-designer-star)
  const [propsOpen, setPropsOpen] = useState(false);
  const [propsDraft, setPropsDraft] = useState({
    name: '',
    description: '',
    semanticFamily: 'relational',
    versionLabel: '1.0',
    factSourceId: 'orders',
    factRelationCsv: 'orders',
    noteRows: [],
  });

  // Dimension editor modal (cube-designer-dimension)
  const [dimOpen, setDimOpen] = useState(false);
  const [dimDraft, setDimDraft] = useState({
    selectedExistingId: '__new__',
    id: '',
    name: '',
    sourceId: '',
    keyField: '',
    nameField: '',
    sortField: '',
    isTime: false,
    unknownMemberPolicy: 'unknown',
    unknownMemberCaption: 'Unknown',
    roleOf: '',
    active: true,
    attributeRows: [],
    hierarchyKind: 'none',
    hierarchyName: '',
    levelRows: [],
    parentField: '',
    maxDepth: 8,
    ragged: false,
    roleRows: [],
  });

  // Measure editor modal (cube-designer-measures)
  const [measureOpen, setMeasureOpen] = useState(false);
  const [measureDraft, setMeasureDraft] = useState({
    selectedExistingId: '__new__',
    id: '',
    name: '',
    aggregation: 'sum',
    sourceId: '',
    field: '',
    format: '#,##0.00',
    certification: 'uncertified',
    measureGroupId: '',
    displayFolder: '',
    semiAdditiveDimension: '',
    withinGroupAggregation: 'sum',
    filterRows: [],
    roleRows: [],
  });

  // Interactive Dimension Usage Matrix modal (cube-designer-measures)
  const [matrixOpen, setMatrixOpen] = useState(false);
  const [matrixGroups, setMatrixGroups] = useState([]);

  // AI Draft Proposal modal (cube-designer-measures)
  const [aiOpen, setAiOpen] = useState(false);
  const [aiTab, setAiTab] = useState('request');
  const [aiDraftReq, setAiDraftReq] = useState({
    prompt: '',
    factTable: 'main.orders',
    apiKey: '',
    columnRows: [
      {name: 'order_id', type: 'integer'},
      {name: 'customer_id', type: 'integer'},
      {name: 'order_date', type: 'date'},
      {name: 'region', type: 'text'},
      {name: 'amount', type: 'numeric'},
    ],
  });
  const [aiProposal, setAiProposal] = useState(null);

  // Try a Query modal (cube-designer-star)
  const cubeQueryController = useQueryExecutionController({
    engine: 'sqlite',
  });
  const [tryOpen, setTryOpen] = useState(false);
  const [tryTab, setTryTab] = useState('builder');
  const [tryDraft, setTryDraft] = useState({
    selectedDims: [],
    selectedMeasures: [],
    dialect: 'sqlite',
    role: '',
    locale: '',
    sqlitePath: '',
  });
  const [tryResult, setTryResult] = useState(null);

  // Combinatorial Rule Reducer modal (cube-designer-aggregations)
  const [reducerOpen, setReducerOpen] = useState(false);
  const [reducerTab, setReducerTab] = useState('rules');
  const [reducerDraft, setReducerDraft] = useState({
    candidatesCsv: '',
    mandatoryCsv: '',
    maxCombinations: 3,
    hierarchyRows: [],
    jointRows: [],
    partitionField: '',
    partitionGrain: 'none',
    refreshPolicy: 'manual',
    strategy: 'aggregate_table',
  });
  const [reducerResult, setReducerResult] = useState(null);

  // Aggregation Plan editor modal (cube-designer-aggregations)
  const [aggRuleOpen, setAggRuleOpen] = useState(false);
  const [aggRuleDraft, setAggRuleDraft] = useState({
    selectedExistingId: '__new__',
    id: '',
    name: '',
    measureGroupId: '',
    grainDimensionsCsv: '',
    measuresCsv: '',
    strategy: 'materialized_view',
    targetRelationCsv: '',
    partitionField: '',
    partitionGrain: 'none',
    refreshPolicy: 'manual',
    enabled: true,
  });

  // Check Against Connection modal (cube-designer-star)
  const [checkConnOpen, setCheckConnOpen] = useState(false);
  const [checkConnPath, setCheckConnPath] = useState('');
  const [checkConnResult, setCheckConnResult] = useState(null);

  // Materialization DDL Plan modal (cube-designer-aggregations)
  const [matPlanOpen, setMatPlanOpen] = useState(false);
  const [matEngine, setMatEngine] = useState('postgresql');
  const [matPlan, setMatPlan] = useState(null);

  // Perspectives & Role Visibility modal (cube-designer-governance)
  const [perspOpen, setPerspOpen] = useState(false);
  const [perspDraft, setPerspDraft] = useState({
    id: '',
    name: '',
    description: '',
    dimensionsCsv: '',
    measuresCsv: '',
    defaultMeasure: '',
    roleRows: [],
  });

  // Translations modal (cube-designer-governance)
  const [transOpen, setTransOpen] = useState(false);
  const [transDraft, setTransDraft] = useState({
    locale: 'fr-CA',
    caption: '',
    description: '',
    entryRows: [],
  });

  // External SML / Apache Ossie Export modal (cube-designer-governance)
  const [exportOpen, setExportOpen] = useState(false);
  const [exportFormat, setExportFormat] = useState('sml');
  const [exportIncludeExtensions, setExportIncludeExtensions] = useState(true);
  const [exportResult, setExportResult] = useState(null);

  // Save checkpoint modal
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveDraft, setSaveDraft] = useState({
    status: 'draft',
    note: '',
    noteRows: [],
    ddnText: '',
  });

  // Accept (= Apply to Store) modal
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [acceptDraft, setAcceptDraft] = useState({
    requireGitReview: false,
    gitReviewRef: '',
    endpointId: '',
    targetEngine: 'postgresql',
    comment: '',
  });

  // Leave Accepted modal
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [leaveDraft, setLeaveDraft] = useState({
    mode: 'branch_minor_draft',
    targetVersion: '1',
    note: '',
  });

  // Git Sync modal
  const [gitOpen, setGitOpen] = useState(false);
  const [gitDraft, setGitDraft] = useState({
    action: 'save',
    repository: '',
    path: '',
    branch: 'main',
    commit: false,
    note: '',
  });
  const [gitStatus, setGitStatus] = useState(null);

  const refreshCubeModel = useCallback(
    async (ver = null, loc = '') => {
      try {
        const res = await controller.getCubeModel({
          version: ver,
          locale: loc || null,
        });
        if (res?.cube) {
          setCubePayload(res.cube);
        }
        if (res?.localized_model && loc) {
          setLocalizedPreviewModel(res.localized_model);
        } else if (!loc) {
          setLocalizedPreviewModel(null);
        }
      } catch {
        // Session workspace remains valid even if optional model fetch fails.
      }
    },
    [controller]
  );

  useEffect(() => {
    let active = true;
    const unsubscribe = controller.subscribe((next) => {
      if (!active) return;
      setSessionState(next);
      callbacks.current.onStateChange?.(next);
    });
    setLoading(true);
    setSurfaceError('');
    controller
      .load()
      .then(async (loaded) => {
        if (!active) return;
        setSessionState(loaded);
        await refreshCubeModel(loaded.currentVersion, '');
        if (active) setLoading(false);
      })
      .catch((err) => {
        if (!active) return;
        setSurfaceError(err.message);
        setLoading(false);
        callbacks.current.onError?.(err);
      });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [controller, refreshCubeModel]);

  const runToolbarCommand = useCallback(async (id, invoke) => {
    setSurfaceError('');
    try {
      if (callbacks.current.executeCommand) {
        return await callbacks.current.executeCommand(id, {
          invoke,
          enabled: true,
        });
      }
      return await invoke();
    } catch (err) {
      setSurfaceError(err.message);
      callbacks.current.onError?.(err);
      return null;
    }
  }, []);

  const cubeModel = cubePayload?.model || null;
  const defaultSourceId = cubeModel?.sources?.[0]?.id || 'fact_rows';
  const currentDdnText =
    sessionState.workspace?.files?.[sessionState.workspace.entry] || '';

  const persistUpdatedModel = async (nextModel, noteText, customNotes = null) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const saved = await controller.saveCubeModel({
        model: nextModel,
        cubeNotes: customNotes ?? cubePayload?.notes ?? [],
        status:
          sessionState.status === 'accepted'
            ? 'draft'
            : sessionState.status || 'draft',
        note: noteText,
      });
      if (saved?.cube) setCubePayload(saved.cube);
      if (saved?.active_drift?.has_active_changes) {
        setActiveDrift(saved.active_drift);
      } else {
        setActiveDrift(null);
      }
      if (previewLocale) {
        await refreshCubeModel(saved?.design?.head_version ?? null, previewLocale);
      }
      return true;
    } catch (err) {
      setSurfaceError(err.message);
      return false;
    } finally {
      setBusyAction(false);
    }
  };

  // --- Cube Properties ---
  const openPropertiesDialog = () => {
    const primarySrc = cubeModel?.sources?.[0] || {
      id: 'orders',
      relation: ['orders'],
    };
    setPropsDraft({
      name: cubeModel?.name || sessionState.design?.title || 'Cube',
      description: cubeModel?.description || '',
      semanticFamily: cubeModel?.semantic_family || 'relational',
      versionLabel:
        cubeModel?.annotations?.cube_version_label || '1.0',
      factSourceId: primarySrc.id || 'orders',
      factRelationCsv: (primarySrc.relation || ['orders']).join('.'),
      noteRows: (cubePayload?.notes || []).map((n) => ({note: n})),
    });
    setPropsOpen(true);
  };

  const submitProperties = async () => {
    if (!cubeModel) return;
    const trimmedName = propsDraft.name.trim();
    if (!trimmedName) {
      setSurfaceError('Cube name is required.');
      return;
    }
    const relParts = propsDraft.factRelationCsv
      .split('.')
      .map((s) => s.trim())
      .filter(Boolean);
    const nextSources = [...(cubeModel.sources || [])];
    if (nextSources.length > 0 && relParts.length > 0) {
      nextSources[0] = {
        ...nextSources[0],
        relation: relParts,
      };
    }
    const nextNotes = propsDraft.noteRows
      .map((r) => String(r.note || '').trim())
      .filter(Boolean);
    const nextModel = {
      ...cubeModel,
      name: trimmedName,
      description: propsDraft.description.trim(),
      semantic_family: propsDraft.semanticFamily || 'relational',
      sources: nextSources,
      annotations: {
        ...(cubeModel.annotations || {}),
        cube_version_label: propsDraft.versionLabel.trim() || '1.0',
      },
    };
    const ok = await persistUpdatedModel(
      nextModel,
      `Updated cube properties (${trimmedName})`,
      nextNotes
    );
    if (ok) setPropsOpen(false);
  };

  // --- Dimension Editor ---
  const loadDimensionIntoDraft = (dimObj) => {
    if (!dimObj) {
      setDimDraft({
        selectedExistingId: '__new__',
        id: '',
        name: '',
        sourceId: defaultSourceId,
        keyField: '',
        nameField: '',
        sortField: '',
        isTime: false,
        unknownMemberPolicy: 'unknown',
        unknownMemberCaption: 'Unknown',
        roleOf: '',
        active: true,
        attributeRows: [],
        hierarchyKind: 'none',
        hierarchyName: '',
        levelRows: [],
        parentField: '',
        maxDepth: 8,
        ragged: false,
        roleRows: [],
      });
      return;
    }
    const firstHier = dimObj.hierarchies?.[0] || null;
    const hKind = firstHier
      ? firstHier.hierarchy_kind || 'level'
      : 'none';
    setDimDraft({
      selectedExistingId: dimObj.id,
      id: dimObj.id,
      name: dimObj.name || '',
      sourceId:
        dimObj.key_field?.source_id ||
        dimObj.field?.source_id ||
        defaultSourceId,
      keyField: dimObj.key_field?.field || dimObj.field?.field || '',
      nameField: dimObj.name_field?.field || '',
      sortField: dimObj.sort_field?.field || '',
      isTime: Boolean(dimObj.is_time),
      unknownMemberPolicy: dimObj.unknown_member_policy || 'unknown',
      unknownMemberCaption: dimObj.unknown_member_caption || 'Unknown',
      roleOf: dimObj.role_of || '',
      active: dimObj.active !== false,
      attributeRows: (dimObj.attributes || []).map((a) => ({
        name: a.name || a.id,
        column: a.field?.field || '',
        sortColumn: a.sort_field?.field || '',
        relationshipType: a.relationship_type || 'changing',
      })),
      hierarchyKind: hKind,
      hierarchyName: firstHier?.name || '',
      levelRows:
        hKind === 'level'
          ? (firstHier?.levels || []).map((lvl) => ({
            name: lvl.name || lvl.id,
            column: lvl.field?.field || '',
            relationshipType: lvl.relationship_type || 'changing',
          }))
          : [],
      parentField: firstHier?.parent_field?.field || '',
      maxDepth: firstHier?.max_depth ?? 8,
      ragged: Boolean(firstHier?.ragged),
      roleRows: (dimObj.visible_roles || []).map((r) => ({role: r})),
    });
  };

  const openDimensionDialog = () => {
    loadDimensionIntoDraft(null);
    setDimOpen(true);
  };

  const submitDimension = async () => {
    if (!cubeModel) return;
    const trimmedName = dimDraft.name.trim();
    const keyCol = dimDraft.keyField.trim();
    if (!trimmedName || !keyCol) {
      setSurfaceError('Dimension name and key column are required.');
      return;
    }
    const dimId = slugId(dimDraft.id || trimmedName, 'dimension');
    const srcId = dimDraft.sourceId.trim() || defaultSourceId;
    const hierarchies = [];
    if (dimDraft.hierarchyKind === 'parent_child') {
      const parentCol = dimDraft.parentField.trim();
      if (!parentCol) {
        setSurfaceError(
          'Parent key column is required for a parent-child hierarchy.'
        );
        return;
      }
      const hName = dimDraft.hierarchyName.trim() || `${trimmedName} Tree`;
      const hObj = {
        id: `${dimId}_pc`,
        name: hName,
        hierarchy_kind: 'parent_child',
        child_field: {source_id: srcId, field: keyCol},
        parent_field: {source_id: srcId, field: parentCol},
        max_depth: Math.max(1, Number(dimDraft.maxDepth) || 8),
        ragged: Boolean(dimDraft.ragged),
      };
      if (dimDraft.nameField.trim()) {
        hObj.name_field = {
          source_id: srcId,
          field: dimDraft.nameField.trim(),
        };
      }
      hierarchies.push(hObj);
    } else if (dimDraft.hierarchyKind === 'level') {
      const validLvls = dimDraft.levelRows.filter((r) =>
        String(r.column || r.name || '').trim()
      );
      const lvlItems = validLvls.length
        ? validLvls
        : [{name: trimmedName, column: keyCol, relationshipType: 'changing'}];
      const hName =
        dimDraft.hierarchyName.trim() || `${trimmedName} Hierarchy`;
      hierarchies.push({
        id: `${dimId}_hier`,
        name: hName,
        hierarchy_kind: 'level',
        ragged: Boolean(dimDraft.ragged),
        levels: lvlItems.map((lvl) => {
          const col = String(lvl.column || lvl.name).trim();
          const lbl = String(lvl.name || col).trim();
          return {
            id: `${dimId}_${slugId(lbl, 'lvl')}`,
            name: lbl,
            field: {source_id: srcId, field: col},
            relationship_type: lvl.relationshipType || 'changing',
          };
        }),
      });
    } else {
      hierarchies.push({
        id: `${dimId}_default`,
        name: trimmedName,
        hierarchy_kind: 'level',
        levels: [
          {
            id: `${dimId}_member`,
            name: trimmedName,
            field: {source_id: srcId, field: keyCol},
            relationship_type: 'changing',
          },
        ],
      });
    }

    const newDim = {
      id: dimId,
      name: trimmedName,
      field: {source_id: srcId, field: keyCol},
      key_field: {source_id: srcId, field: keyCol},
      is_time: Boolean(dimDraft.isTime),
      time_role: dimDraft.isTime ? 'event-time' : null,
      hierarchies,
      active: Boolean(dimDraft.active),
      unknown_member_policy: dimDraft.unknownMemberPolicy || 'unknown',
      unknown_member_caption:
        dimDraft.unknownMemberCaption.trim() || 'Unknown',
    };
    if (dimDraft.nameField.trim()) {
      newDim.name_field = {
        source_id: srcId,
        field: dimDraft.nameField.trim(),
      };
    }
    if (dimDraft.sortField.trim()) {
      newDim.sort_field = {
        source_id: srcId,
        field: dimDraft.sortField.trim(),
      };
    }
    const attrs = dimDraft.attributeRows
      .filter((r) => String(r.column || r.name || '').trim())
      .map((r) => {
        const col = String(r.column || r.name).trim();
        const lbl = String(r.name || col).trim();
        const attrObj = {
          id: `${dimId}_${slugId(lbl, 'attr')}`,
          name: lbl,
          field: {source_id: srcId, field: col},
          relationship_type: r.relationshipType || 'changing',
        };
        if (String(r.sortColumn || '').trim()) {
          attrObj.sort_field = {
            source_id: srcId,
            field: String(r.sortColumn).trim(),
          };
        }
        return attrObj;
      });
    if (attrs.length) {
      newDim.attributes = attrs;
    }
    if (dimDraft.roleOf.trim()) {
      newDim.role_of = dimDraft.roleOf.trim();
    }
    const roles = dimDraft.roleRows
      .map((r) => String(r.role || '').trim())
      .filter(Boolean);
    if (roles.length) {
      newDim.visible_roles = roles;
    }

    const nextDims = [
      ...(cubeModel.dimensions || []).filter((d) => d.id !== dimId),
      newDim,
    ];
    const ok = await persistUpdatedModel(
      {...cubeModel, dimensions: nextDims},
      `Saved dimension ${trimmedName}`
    );
    if (ok) setDimOpen(false);
  };

  // --- Measure Editor ---
  const loadMeasureIntoDraft = (mObj) => {
    const firstDimId = cubeModel?.dimensions?.[0]?.id || '';
    if (!mObj) {
      setMeasureDraft({
        selectedExistingId: '__new__',
        id: '',
        name: '',
        aggregation: 'sum',
        sourceId: defaultSourceId,
        field: '',
        format: '#,##0.00',
        certification: 'uncertified',
        measureGroupId: cubeModel?.measure_groups?.[0]?.id || '',
        displayFolder: '',
        semiAdditiveDimension: firstDimId,
        withinGroupAggregation: 'sum',
        filterRows: [],
        roleRows: [],
      });
      return;
    }
    setMeasureDraft({
      selectedExistingId: mObj.id,
      id: mObj.id,
      name: mObj.name || '',
      aggregation: mObj.aggregation || 'sum',
      sourceId: mObj.field?.source_id || defaultSourceId,
      field: mObj.field?.field || '',
      format: mObj.format || '',
      certification: mObj.certification?.status || 'uncertified',
      measureGroupId:
        mObj.measure_group_id || cubeModel?.measure_groups?.[0]?.id || '',
      displayFolder: mObj.display_folder || '',
      semiAdditiveDimension: mObj.semi_additive_dimension || firstDimId,
      withinGroupAggregation: mObj.within_group_aggregation || 'sum',
      filterRows: (mObj.filters || []).map((f) => ({
        column: f.field?.field || '',
        operator: f.operator || 'eq',
        value: f.value !== undefined ? String(f.value) : '',
      })),
      roleRows: (mObj.visible_roles || []).map((r) => ({role: r})),
    });
  };

  const openMeasureDialog = () => {
    loadMeasureIntoDraft(null);
    setMeasureOpen(true);
  };

  const submitMeasure = async () => {
    if (!cubeModel) return;
    const trimmedName = measureDraft.name.trim();
    if (!trimmedName) {
      setSurfaceError('Measure name is required.');
      return;
    }
    const isSemiAdditive = SEMI_ADDITIVE_SET.has(measureDraft.aggregation);
    if (isSemiAdditive && !measureDraft.semiAdditiveDimension.trim()) {
      setSurfaceError(
        'Semi-additive measures require a time/order dimension ID.'
      );
      return;
    }
    const mId = slugId(measureDraft.id || trimmedName, 'measure');
    const srcId = measureDraft.sourceId.trim() || defaultSourceId;
    const fieldCol = measureDraft.field.trim();
    if (measureDraft.aggregation !== 'count' && !fieldCol) {
      setSurfaceError(
        'Measure column is required unless aggregation is COUNT.'
      );
      return;
    }
    const newMeasure = {
      id: mId,
      name: trimmedName,
      aggregation: measureDraft.aggregation,
      field: fieldCol ? {source_id: srcId, field: fieldCol} : null,
      format: measureDraft.format.trim() || 'number',
      certification: {status: measureDraft.certification},
    };
    if (isSemiAdditive) {
      newMeasure.semi_additive_dimension =
        measureDraft.semiAdditiveDimension.trim();
      newMeasure.within_group_aggregation =
        measureDraft.withinGroupAggregation || 'sum';
    }
    if (measureDraft.displayFolder.trim()) {
      newMeasure.display_folder = measureDraft.displayFolder.trim();
    }
    if (measureDraft.measureGroupId.trim()) {
      newMeasure.measure_group_id = measureDraft.measureGroupId.trim();
    }
    const filters = measureDraft.filterRows
      .filter((r) => String(r.column || '').trim())
      .map((r) => ({
        field: {source_id: srcId, field: String(r.column).trim()},
        operator: r.operator || 'eq',
        value: String(r.value ?? ''),
      }));
    if (filters.length) {
      newMeasure.filters = filters;
    }
    const roles = measureDraft.roleRows
      .map((r) => String(r.role || '').trim())
      .filter(Boolean);
    if (roles.length) {
      newMeasure.visible_roles = roles;
    }

    const nextMeasures = [
      ...(cubeModel.measures || []).filter((m) => m.id !== mId),
      newMeasure,
    ];
    let nextGroups = cubeModel.measure_groups;
    if (Array.isArray(nextGroups) && newMeasure.measure_group_id) {
      nextGroups = nextGroups.map((grp) =>
        grp.id === newMeasure.measure_group_id && !grp.measures.includes(mId)
          ? {...grp, measures: [...grp.measures, mId]}
          : grp
      );
    }
    const ok = await persistUpdatedModel(
      {
        ...cubeModel,
        measures: nextMeasures,
        ...(nextGroups ? {measure_groups: nextGroups} : {}),
      },
      `Saved measure ${trimmedName}`
    );
    if (ok) setMeasureOpen(false);
  };

  // --- Interactive Dimension Usage Matrix ---
  const openUsageMatrixDialog = () => {
    setMatrixGroups(ensureMeasureGroups(cubeModel));
    setMatrixOpen(true);
  };

  const cycleMatrixCell = (groupId, dimObj) => {
    setMatrixGroups((prev) =>
      prev.map((grp) => {
        if (grp.id !== groupId) return grp;
        const usages = [...(grp.dimension_usage || [])];
        const idx = usages.findIndex((u) => u.dimension_id === dimObj.id);
        if (idx === -1) {
          usages.push({
            dimension_id: dimObj.id,
            relationship_kind: 'regular',
            active: true,
            ...(dimObj.join_id ? {join_id: dimObj.join_id} : {}),
          });
        } else if (usages[idx].active !== false) {
          usages[idx] = {
            ...usages[idx],
            active: false,
          };
        } else {
          usages.splice(idx, 1);
        }
        return {...grp, dimension_usage: usages};
      })
    );
  };

  const submitUsageMatrix = async () => {
    if (!cubeModel) return;
    const ok = await persistUpdatedModel(
      {...cubeModel, measure_groups: matrixGroups},
      'Updated interactive dimension usage matrix'
    );
    if (ok) setMatrixOpen(false);
  };

  // --- AI Draft Proposal ---
  const openAiDraftDialog = () => {
    setAiProposal(null);
    setAiTab('request');
    setAiOpen(true);
  };

  const runAiDraftProposal = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const columns = aiDraftReq.columnRows
        .filter((r) => String(r.name || '').trim())
        .map((r) => ({
          name: String(r.name).trim(),
          type: String(r.type || 'text').trim(),
        }));
      const proposal = await (typeof controller.proposeCubeAiDraft ===
      'function'
        ? controller.proposeCubeAiDraft({
          prompt: aiDraftReq.prompt.trim(),
          fact_table: aiDraftReq.factTable.trim() || 'main.orders',
          columns,
          api_key: aiDraftReq.apiKey.trim() || undefined,
        })
        : client.proposeCubeAiDraft(projectId, {
          prompt: aiDraftReq.prompt.trim(),
          fact_table: aiDraftReq.factTable.trim() || 'main.orders',
          columns,
          api_key: aiDraftReq.apiKey.trim() || undefined,
        }));
      setAiProposal(proposal);
      setAiTab('proposal');
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const applyAiProposalToDraft = async () => {
    if (!aiProposal?.proposed_model) return;
    const ok = await persistUpdatedModel(
      aiProposal.proposed_model,
      'Applied reviewed AI cube draft proposal'
    );
    if (ok) setAiOpen(false);
  };

  // --- Try a Query ---
  const openTryQueryDialog = () => {
    setTryDraft({
      selectedDims: (cubeModel?.dimensions || []).slice(0, 1).map((d) => d.id),
      selectedMeasures: (cubeModel?.measures || [])
        .slice(0, 2)
        .map((m) => m.id),
      dialect: 'sqlite',
      role: '',
      locale: previewLocale || '',
      sqlitePath: '',
    });
    setTryResult(null);
    setTryTab('builder');
    setTryOpen(true);
  };

  const runTryQuery = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.tryCubeQuery({
        dimensions: tryDraft.selectedDims,
        measures: tryDraft.selectedMeasures,
        dialect: tryDraft.dialect,
        role: tryDraft.role.trim() || undefined,
        locale: tryDraft.locale.trim() || undefined,
        sqlite_path: tryDraft.sqlitePath.trim() || undefined,
      });
      setTryResult(res);
      setTryTab('sql_results');
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  // --- Combinatorial Rule Reducer ---
  const openReducerDialog = () => {
    const dimIds = (cubeModel?.dimensions || [])
      .filter((d) => d.active !== false)
      .map((d) => d.id);
    const hierChains = [];
    for (const d of cubeModel?.dimensions || []) {
      for (const h of d.hierarchies || []) {
        if ((h.levels || []).length > 1) {
          hierChains.push({
            chain: h.levels.map((lvl) => lvl.id).join(', '),
          });
        }
      }
    }
    setReducerDraft({
      candidatesCsv: dimIds.join(', '),
      mandatoryCsv: dimIds[0] || '',
      maxCombinations: Math.max(2, Math.min(4, dimIds.length || 3)),
      hierarchyRows: hierChains,
      jointRows: [],
      partitionField: '',
      partitionGrain: 'none',
      refreshPolicy: 'incremental',
      strategy: 'aggregate_table',
    });
    setReducerResult(null);
    setReducerTab('rules');
    setReducerOpen(true);
  };

  const parsedReducerInputs = useMemo(() => {
    const splitCsv = (raw) =>
      String(raw || '')
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
    const candidates = splitCsv(reducerDraft.candidatesCsv);
    const mandatory = splitCsv(reducerDraft.mandatoryCsv);
    const hierarchyChains = reducerDraft.hierarchyRows
      .map((r) => splitCsv(r.chain))
      .filter((arr) => arr.length > 0);
    const jointGroups = reducerDraft.jointRows
      .map((r) => splitCsv(r.group))
      .filter((arr) => arr.length > 0);
    const maxCap =
      reducerDraft.maxCombinations === '' ||
      reducerDraft.maxCombinations === null
        ? null
        : Number(reducerDraft.maxCombinations);
    return {candidates, mandatory, hierarchyChains, jointGroups, maxCap};
  }, [reducerDraft]);

  const liveReductionPreview = useMemo(
    () => computeLocalCuboidReduction(parsedReducerInputs),
    [parsedReducerInputs]
  );

  const invokeReducer = async (saveVersion) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.reduceCubeAggregations({
        candidate_dimensions: parsedReducerInputs.candidates,
        mandatory_dimensions: parsedReducerInputs.mandatory,
        hierarchy_sets: parsedReducerInputs.hierarchyChains,
        joint_sets: parsedReducerInputs.jointGroups,
        max_dimension_combinations: parsedReducerInputs.maxCap,
        partition_field: reducerDraft.partitionField.trim() || undefined,
        partition_grain: reducerDraft.partitionGrain || 'none',
        refresh_policy: reducerDraft.refreshPolicy || 'manual',
        strategy: reducerDraft.strategy || 'aggregate_table',
        save_version: Boolean(saveVersion),
      });
      setReducerResult(res);
      if (saveVersion) {
        if (res?.cube) setCubePayload(res.cube);
        await controller.load();
        setReducerOpen(false);
      } else {
        setReducerTab('partition');
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  // --- Edit Single Aggregation Plan ---
  const openAggRuleDialog = () => {
    setAggRuleDraft({
      selectedExistingId: '__new__',
      id: '',
      name: '',
      measureGroupId: cubeModel?.measure_groups?.[0]?.id || '',
      grainDimensionsCsv: '',
      measuresCsv: '',
      strategy: 'materialized_view',
      targetRelationCsv: '',
      partitionField: '',
      partitionGrain: 'none',
      refreshPolicy: 'manual',
      enabled: true,
    });
    setAggRuleOpen(true);
  };

  const submitAggRule = async () => {
    if (!cubeModel) return;
    const trimmedName = aggRuleDraft.name.trim();
    if (!trimmedName) {
      setSurfaceError('Aggregation rule name is required.');
      return;
    }
    const rId = slugId(aggRuleDraft.id || trimmedName, 'agg');
    const grain = aggRuleDraft.grainDimensionsCsv
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const meas = aggRuleDraft.measuresCsv
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const targetRel = aggRuleDraft.targetRelationCsv
      .split('.')
      .map((s) => s.trim())
      .filter(Boolean);
    const newRule = {
      id: rId,
      name: trimmedName,
      strategy: aggRuleDraft.strategy,
      enabled: Boolean(aggRuleDraft.enabled),
      grain_dimensions: grain,
      measures:
        meas.length > 0
          ? meas
          : (cubeModel.measures || []).slice(0, 1).map((m) => m.id),
      target_relation: targetRel.length > 0 ? targetRel : [rId],
      partition_grain: aggRuleDraft.partitionGrain || 'none',
      refresh_policy: aggRuleDraft.refreshPolicy || 'manual',
    };
    if (aggRuleDraft.measureGroupId.trim()) {
      newRule.measure_group_id = aggRuleDraft.measureGroupId.trim();
    }
    if (aggRuleDraft.partitionField.trim()) {
      newRule.partition_field = aggRuleDraft.partitionField.trim();
    }
    const nextMats = [
      ...(cubeModel.materializations || []).filter((m) => m.id !== rId),
      newRule,
    ];
    const ok = await persistUpdatedModel(
      {...cubeModel, materializations: nextMats},
      `Saved aggregation rule ${trimmedName}`
    );
    if (ok) setAggRuleOpen(false);
  };

  // --- Check Against Connection ---
  const openCheckConnectionDialog = async () => {
    setCheckConnOpen(true);
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.checkCubeConnection({
        sqlite_path: checkConnPath.trim() || undefined,
      });
      setCheckConnResult(res);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const runCheckConnection = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.checkCubeConnection({
        sqlite_path: checkConnPath.trim() || undefined,
      });
      setCheckConnResult(res);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  // --- Materialization Plan ---
  const openMaterializationPlan = async (engine = matEngine) => {
    setMatPlanOpen(true);
    setBusyAction(true);
    setSurfaceError('');
    try {
      const plan = await controller.previewCubeMaterializationPlan({
        targetEngine: engine,
      });
      setMatPlan(plan);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  // --- Perspectives & Role Visibility ---
  const openPerspectiveDialog = () => {
    const allDims = (cubeModel?.dimensions || []).map((d) => d.id).join(', ');
    const allMeas = (cubeModel?.measures || []).map((m) => m.id).join(', ');
    setPerspDraft({
      id: '',
      name: '',
      description: '',
      dimensionsCsv: allDims,
      measuresCsv: allMeas,
      defaultMeasure: cubeModel?.measures?.[0]?.id || '',
      roleRows: [],
    });
    setPerspOpen(true);
  };

  const submitPerspective = async () => {
    if (!cubeModel) return;
    const trimmedName = perspDraft.name.trim();
    if (!trimmedName) {
      setSurfaceError('Perspective name is required.');
      return;
    }
    const pId = slugId(perspDraft.id || trimmedName, 'perspective');
    const dims = perspDraft.dimensionsCsv
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const meas = perspDraft.measuresCsv
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const effectiveMeas =
      meas.length > 0
        ? meas
        : (cubeModel.measures || []).slice(0, 1).map((m) => m.id);
    if (!effectiveMeas.length) {
      setSurfaceError(
        'Perspective requires at least one measure in the cube.'
      );
      return;
    }
    const newPersp = {
      id: pId,
      name: trimmedName,
      description: perspDraft.description.trim(),
      dimensions: dims,
      measures: effectiveMeas,
    };
    const defM = perspDraft.defaultMeasure.trim();
    if (defM && effectiveMeas.includes(defM)) {
      newPersp.default_measure = defM;
    }
    const roles = perspDraft.roleRows
      .map((r) => String(r.role || '').trim())
      .filter(Boolean);
    if (roles.length) {
      newPersp.visible_roles = roles;
    }
    const nextPersps = [
      ...(cubeModel.perspectives || []).filter((p) => p.id !== pId),
      newPersp,
    ];
    const ok = await persistUpdatedModel(
      {...cubeModel, perspectives: nextPersps},
      `Saved perspective ${trimmedName}`
    );
    if (ok) setPerspOpen(false);
  };

  // --- Locale Translations ---
  const openTranslationDialog = () => {
    const existing = cubeModel?.translations?.[0] || null;
    setTransDraft({
      locale: existing?.locale || 'fr-CA',
      caption: existing?.caption || '',
      description: existing?.description || '',
      entryRows: (existing?.entries || []).map((e) => ({
        targetKind: e.target_kind || 'measure',
        targetId: e.target_id || '',
        caption: e.caption || '',
        displayFolder: e.display_folder || '',
      })),
    });
    setTransOpen(true);
  };

  const submitTranslation = async () => {
    if (!cubeModel) return;
    const loc = transDraft.locale.trim();
    if (!loc) {
      setSurfaceError('BCP-47 locale tag (e.g. fr-CA) is required.');
      return;
    }
    const entries = transDraft.entryRows
      .filter((r) => String(r.targetId || '').trim())
      .map((r) => ({
        target_kind: r.targetKind || 'measure',
        target_id: String(r.targetId).trim(),
        caption: String(r.caption || '').trim(),
        ...(String(r.displayFolder || '').trim()
          ? {display_folder: String(r.displayFolder).trim()}
          : {}),
      }));
    const trObj = {
      id: `loc_${slugId(loc, 'locale')}`,
      locale: loc,
      caption: transDraft.caption.trim(),
      description: transDraft.description.trim(),
      entries,
    };
    const nextTrans = [
      ...(cubeModel.translations || []).filter(
        (t) => t.locale.toLowerCase() !== loc.toLowerCase()
      ),
      trObj,
    ];
    const ok = await persistUpdatedModel(
      {...cubeModel, translations: nextTrans},
      `Saved ${loc} translation`
    );
    if (ok) setTransOpen(false);
  };

  // --- Interchange Export (SML v1.8 / Apache Ossie v0.2.0) ---
  const runInterchangeExport = async (
    fmt = exportFormat,
    incExt = exportIncludeExtensions
  ) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.exportCubeInterchange({
        format: fmt,
        includeCustomExtensions: incExt,
      });
      setExportResult(res);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const openExportDialog = async () => {
    setExportOpen(true);
    await runInterchangeExport(exportFormat, exportIncludeExtensions);
  };

  // --- Lifecycle & Checkpoints ---
  const openSaveDialog = () => {
    setSaveDraft({
      status:
        sessionState.status === 'accepted'
          ? 'draft'
          : sessionState.status || 'draft',
      note: '',
      noteRows: (cubePayload?.notes || []).map((n) => ({note: n})),
      ddnText: currentDdnText,
    });
    setSaveOpen(true);
  };

  const submitSaveCheckpoint = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const notes = saveDraft.noteRows
        .map((r) => String(r.note || '').trim())
        .filter(Boolean);
      const editedDdn = saveDraft.ddnText !== currentDdnText;
      const saved = await controller.saveCubeModel({
        ddnText: editedDdn ? saveDraft.ddnText : null,
        model: editedDdn ? null : cubeModel,
        cubeNotes: notes,
        status: saveDraft.status,
        note: saveDraft.note.trim() || `Saved ${saveDraft.status} checkpoint`,
      });
      if (saved?.cube) setCubePayload(saved.cube);
      if (saved?.active_drift?.has_active_changes) {
        setActiveDrift(saved.active_drift);
      } else {
        setActiveDrift(null);
      }
      setSaveOpen(false);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const handleAdvanceStatus = async (nextStatus) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      await controller.advanceStatus(nextStatus);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const openAcceptDialog = () => {
    setAcceptDraft({
      requireGitReview: false,
      gitReviewRef: '',
      endpointId: cubeModel?.annotations?.semantic_endpoint_id || '',
      targetEngine: matEngine || 'postgresql',
      comment: '',
    });
    setAcceptOpen(true);
  };

  const submitAccept = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const accepted = await controller.accept({
        comment: acceptDraft.comment.trim(),
        requireGitReview: acceptDraft.requireGitReview,
        gitReviewRef: acceptDraft.gitReviewRef.trim() || null,
        endpointId: acceptDraft.endpointId.trim() || null,
        targetEngine: acceptDraft.targetEngine,
      });
      setAppliedInfo(accepted?.applied_semantic_model || null);
      if (accepted?.materialization_review_plan?.has_database_changes) {
        setMatPlan(accepted.materialization_review_plan);
      }
      await refreshCubeModel(sessionState.currentVersion, previewLocale);
      setAcceptOpen(false);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const submitLeaveAccepted = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.leaveCubeAccepted({
        mode: leaveDraft.mode,
        targetVersion:
          leaveDraft.mode === 'rollback'
            ? Number(leaveDraft.targetVersion) || 1
            : null,
        note: leaveDraft.note.trim(),
      });
      if (res?.cube) setCubePayload(res.cube);
      setLeaveOpen(false);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const handleSyncWithActive = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.syncCubeActive({
        note: 'Merged active cube changes into draft',
      });
      if (res?.merged === false) {
        setSurfaceError(
          `Active cube has ${res.merge?.conflicts?.length || 1} conflicting change(s) requiring manual resolution.`
        );
      } else {
        if (res?.cube) setCubePayload(res.cube);
        setActiveDrift(null);
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const handleExportDDN = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const exported = await client.exportDDN(projectId, designId, {
        version: sessionState.currentVersion ?? null,
        view: cubeView,
      });
      onExport?.(exported);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const handleRecomputeLayout = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      await client.computeLayout(projectId, designId, {
        version: sessionState.currentVersion ?? null,
        viewId: cubeView,
        pinnedPositions: sessionState.pinnedPositions || null,
      });
      await controller.load({version: sessionState.currentVersion ?? null});
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const submitGitOperation = async () => {
    if (!gitDraft.repository.trim() || !gitDraft.path.trim()) {
      setSurfaceError('Git repository directory and DDN file path are required.');
      return;
    }
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.gitOperation({
        action: gitDraft.action,
        repository: gitDraft.repository.trim(),
        path: gitDraft.path.trim(),
        branch: gitDraft.branch.trim() || 'main',
        commit: gitDraft.commit,
        note: gitDraft.note.trim(),
      });
      setGitStatus(
        gitDraft.action === 'save'
          ? `Saved DDN to ${res.path} (${res.sha256?.slice(0, 12) || 'ok'})`
          : `Loaded DDN from Git into v${res.design?.head_version || ''}`
      );
      if (gitDraft.action === 'load') {
        await refreshCubeModel(null, previewLocale);
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const handlePreviewLocaleChange = async (loc) => {
    setPreviewLocale(loc);
    await refreshCubeModel(sessionState.currentVersion, loc);
  };

  const viewerSnapshot = useMemo(() => {
    if (!sessionState.workspace) return null;
    return {
      ...sessionState.workspace,
      view: resolveCubeView(sessionState.workspace, cubeView),
    };
  }, [sessionState.workspace, cubeView]);

  const versionLabel =
    cubeModel?.annotations?.cube_version_label || '1.0';
  const curStatus = sessionState.status || 'draft';

  const localeOptions = useMemo(() => {
    const opts = [{value: '', label: 'Default authoring labels'}];
    for (const tr of cubeModel?.translations || []) {
      opts.push({
        value: tr.locale,
        label: `${tr.locale}${tr.caption ? ` (${tr.caption})` : ''}`,
      });
    }
    return opts;
  }, [cubeModel?.translations]);

  // Build 5-tab DesignerTabbedMenu configuration
  const ribbonTabs = useMemo(
    () => [
      {
        id: 'cube',
        label: 'Cube',
        dirty: Boolean(activeDrift?.has_active_changes),
        groups: [
          {
            id: 'cube-save',
            label: 'Checkpoints',
            items: [
              {
                id: 'cube.designer.save',
                label: 'Save Draft',
                intent: 'primary',
                disabled: readOnly || busyAction || loading,
                onClick: () =>
                  runToolbarCommand('cube.designer.save', openSaveDialog),
              },
              {
                id: 'cube.designer.checkpoints',
                label: 'Checkpoints & Diff…',
                disabled: busyAction || loading,
                onClick: () => setCheckpointsOpen(true),
              },
            ],
          },
          {
            id: 'cube-lifecycle',
            label: 'Advance Status',
            items: [
              {
                id: 'cube.designer.in_progress',
                label: 'In Progress',
                disabled:
                  readOnly ||
                  busyAction ||
                  loading ||
                  curStatus === 'accepted' ||
                  curStatus === 'in_progress',
                onClick: () => handleAdvanceStatus('in_progress'),
              },
              {
                id: 'cube.designer.in_review',
                label: 'In Review',
                disabled:
                  readOnly ||
                  busyAction ||
                  loading ||
                  curStatus === 'accepted' ||
                  curStatus === 'in_review',
                onClick: () => handleAdvanceStatus('in_review'),
              },
              {
                id: 'cube.designer.accept',
                label: 'Accept Cube',
                intent: curStatus === 'accepted' ? 'neutral' : 'primary',
                disabled:
                  readOnly || busyAction || loading || curStatus === 'accepted',
                onClick: () =>
                  runToolbarCommand('cube.designer.accept', openAcceptDialog),
              },
              ...(curStatus === 'accepted'
                ? [
                  {
                    id: 'cube.designer.leave_accepted',
                    label: 'Leave Accepted…',
                    disabled: readOnly || busyAction || loading,
                    onClick: () => setLeaveOpen(true),
                  },
                ]
                : []),
              {
                id: 'cube.designer.sync_active',
                label: 'Sync Active',
                disabled:
                  readOnly ||
                  busyAction ||
                  loading ||
                  (!activeDrift?.has_active_changes &&
                    !sessionState.activeVersion),
                onClick: handleSyncWithActive,
              },
            ],
          },
          {
            id: 'cube-exchange',
            label: 'Git & Lineage',
            items: [
              {
                id: 'cube.designer.git',
                label: 'Git Sync…',
                disabled: busyAction || loading,
                onClick: () => {
                  setGitStatus(null);
                  setGitOpen(true);
                },
              },
              {
                id: 'cube.designer.export_ddn',
                label: 'Export DDN',
                disabled: busyAction || loading,
                onClick: handleExportDDN,
              },
              {
                id: 'cube.designer.where_used',
                label: 'Used By (Where Used)…',
                disabled: busyAction || loading,
                onClick: () => setWhereUsedOpen(true),
              },
            ],
          },
        ],
      },
      {
        id: 'model',
        label: 'Dimensions & Measures',
        groups: [
          {
            id: 'model-elements',
            label: 'Dimensional Model',
            items: [
              {
                id: 'cube.designer.properties',
                label: 'Cube Properties…',
                disabled: readOnly || busyAction || loading || !cubeModel,
                onClick: openPropertiesDialog,
              },
              {
                id: 'cube.designer.measures',
                label: '+ Measure / Edit Measures…',
                badge: cubeModel?.measures?.length ?? 0,
                disabled: readOnly || busyAction || loading || !cubeModel,
                onClick: openMeasureDialog,
              },
              {
                id: 'cube.designer.dimensions',
                label: '+ Dimension / Hierarchies…',
                badge: cubeModel?.dimensions?.length ?? 0,
                disabled: readOnly || busyAction || loading || !cubeModel,
                onClick: openDimensionDialog,
              },
            ],
          },
          {
            id: 'model-matrix-ai',
            label: 'Bindings & Drafting',
            items: [
              {
                id: 'cube.designer.usage_matrix',
                label: 'Interactive Usage Matrix…',
                disabled: readOnly || busyAction || loading || !cubeModel,
                onClick: openUsageMatrixDialog,
              },
              {
                id: 'cube.designer.ai_draft',
                label: 'AI Draft Proposal…',
                disabled: readOnly || busyAction || loading,
                onClick: openAiDraftDialog,
              },
            ],
          },
        ],
      },
      {
        id: 'views',
        label: 'Views & Try Query',
        groups: [
          {
            id: 'views-switcher',
            label: 'DDN Views',
            items: [
              {
                id: 'cube.designer.view_select',
                render: () => (
                  <Box sx={{minWidth: 250}}>
                    <Select
                      label="Cube DDN view"
                      value={cubeView}
                      options={CUBE_VIEW_OPTIONS}
                      onChange={setCubeView}
                    />
                  </Box>
                ),
              },
              {
                id: 'cube.designer.view_star',
                label: 'Star Schema',
                active: cubeView === 'cube_star',
                onClick: () => setCubeView('cube_star'),
              },
              {
                id: 'cube.designer.view_matrix',
                label: 'Dimension Usage Matrix',
                active: cubeView === 'cube_usage_matrix',
                onClick: () => setCubeView('cube_usage_matrix'),
              },
              {
                id: 'cube.designer.view_agg_grid',
                label: 'Aggregation Grid',
                active: cubeView === 'cube_aggregation_grid',
                onClick: () => setCubeView('cube_aggregation_grid'),
              },
            ],
          },
          {
            id: 'views-layout-query',
            label: 'Layout & Slice',
            items: [
              {
                id: 'cube.designer.recompute_layout',
                label: 'Recompute Layout',
                disabled: busyAction || loading,
                onClick: handleRecomputeLayout,
              },
              {
                id: 'cube.designer.try_query',
                label: 'Try a Query…',
                intent: 'primary',
                disabled: busyAction || loading || !cubeModel,
                onClick: openTryQueryDialog,
              },
            ],
          },
        ],
      },
      {
        id: 'aggregations',
        label: 'Aggregations & Check',
        groups: [
          {
            id: 'agg-rules',
            label: 'Aggregation Rules',
            items: [
              {
                id: 'cube.designer.reducer',
                label: 'Combinatorial Rule Reducer…',
                disabled: readOnly || busyAction || loading || !cubeModel,
                onClick: openReducerDialog,
              },
              {
                id: 'cube.designer.agg_plans',
                label: 'Edit Aggregation Plans…',
                badge: cubeModel?.materializations?.length ?? 0,
                disabled: readOnly || busyAction || loading || !cubeModel,
                onClick: openAggRuleDialog,
              },
            ],
          },
          {
            id: 'agg-validation',
            label: 'Connection & Native DDL',
            items: [
              {
                id: 'cube.designer.check_connection',
                label: 'Check Against Connection…',
                disabled: busyAction || loading || !cubeModel,
                onClick: openCheckConnectionDialog,
              },
              {
                id: 'cube.designer.materialization_plan',
                label: 'Materialization DDL Plan…',
                disabled: busyAction || loading,
                onClick: () =>
                  runToolbarCommand(
                    'cube.designer.materialization_plan',
                    () => openMaterializationPlan(matEngine)
                  ),
              },
            ],
          },
        ],
      },
      {
        id: 'governance',
        label: 'Governance & Export',
        groups: [
          {
            id: 'gov-roles-locales',
            label: 'Perspectives & Translations',
            items: [
              {
                id: 'cube.designer.perspectives',
                label: 'Perspectives & Role Visibility…',
                badge: cubeModel?.perspectives?.length ?? 0,
                disabled: readOnly || busyAction || loading || !cubeModel,
                onClick: openPerspectiveDialog,
              },
              {
                id: 'cube.designer.translations',
                label: 'Locale Translations…',
                badge: cubeModel?.translations?.length ?? 0,
                disabled: readOnly || busyAction || loading || !cubeModel,
                onClick: openTranslationDialog,
              },
            ],
          },
          {
            id: 'gov-preview-export',
            label: 'Locale Preview & Interchange',
            items: [
              {
                id: 'cube.designer.preview_locale',
                render: () => (
                  <Box sx={{minWidth: 190}}>
                    <Select
                      label="Preview Locale"
                      value={previewLocale}
                      options={localeOptions}
                      onChange={handlePreviewLocaleChange}
                    />
                  </Box>
                ),
              },
              {
                id: 'cube.designer.export_interchange',
                label: 'Export SML / Ossie…',
                disabled: busyAction || loading || !cubeModel,
                onClick: openExportDialog,
              },
            ],
          },
        ],
      },
    ],
    [
      activeDrift?.has_active_changes,
      busyAction,
      cubeModel,
      cubeView,
      curStatus,
      loading,
      localeOptions,
      matEngine,
      previewLocale,
      readOnly,
      runToolbarCommand,
      sessionState.activeVersion,
    ]
  );

  return (
    <Box
      role="region"
      aria-label="Cube Designer"
      sx={{
        position: 'relative',
        height: '100%',
        minHeight: 360,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="cube-designer-workspace" />
      <DesignerTabbedMenu
        label="Cube Designer"
        tabs={ribbonTabs}
        activeTab={activeRibbonTab}
        onTabChange={setActiveRibbonTab}
        leading={
          <StatusBadge
            status={curStatus === 'accepted' ? 'success' : 'info'}
            label={`${curStatus} · v${sessionState.currentVersion || 1} (${versionLabel})`}
          />
        }
        trailing={
          localizedPreviewModel && previewLocale ? (
            <StatusBadge
              status="info"
              label={`Locale: ${previewLocale} — ${localizedPreviewModel.name}`}
            />
          ) : null
        }
      />

      {surfaceError && (
        <Banner status="error" onClose={() => setSurfaceError('')}>
          {surfaceError}
        </Banner>
      )}

      {activeDrift?.has_active_changes && (
        <Banner status="warning">
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1.5,
              flexWrap: 'wrap',
            }}
          >
            <span>
              Another version was accepted while this draft was edited (
              {activeDrift.active_changes?.length || 1} active change(s)). Merge
              active changes via DDN diff before accepting.
            </span>
            <Button
              size="small"
              disabled={busyAction}
              onClick={handleSyncWithActive}
            >
              Sync active changes
            </Button>
          </Box>
        </Banner>
      )}

      {appliedInfo && (
        <Banner status="success" onClose={() => setAppliedInfo(null)}>
          Accepted version applied to semantic-model store (
          {appliedInfo.model_id} rev {appliedInfo.revision}).
        </Banner>
      )}

      <Box sx={{position: 'relative', flex: 1, minHeight: 0}}>
        {viewerSnapshot ? (
          <DDNViewerSurface
            key={`${sessionState.currentVersion}:${viewerSnapshot.view}`}
            snapshot={viewerSnapshot}
            title={
              localizedPreviewModel?.name ||
              sessionState.design?.title ||
              'Cube Designer'
            }
            showViewSelector={false}
          />
        ) : (
          !loading && (
            <EmptyState message="Load or create a Cube design to begin modelling." />
          )
        )}
        <ProgressOverlay
          message={loading ? 'Loading Cube Designer' : ''}
        />
      </Box>

      {/* Shared Checkpoint History & Diff Drawer */}
      <DesignCheckpointHistoryDrawer
        open={checkpointsOpen}
        onClose={() => setCheckpointsOpen(false)}
        client={client}
        projectId={projectId}
        designId={designId}
        currentVersion={sessionState.currentVersion}
        activeVersion={sessionState.activeVersion}
        onOpenVersion={async (ver) => {
          await controller.load({version: ver});
          await refreshCubeModel(ver, previewLocale);
          setCheckpointsOpen(false);
        }}
        onRestored={async () => {
          await controller.load();
          await refreshCubeModel(null, previewLocale);
          setCheckpointsOpen(false);
        }}
      />

      {/* Shared Cross-Design Where-Used Impact Explorer */}
      <WhereUsedDialog
        open={whereUsedOpen}
        onClose={() => setWhereUsedOpen(false)}
        client={client}
        projectId={projectId}
        designId={designId}
        initialTargetRef={sessionState.design?.key || ''}
      />

      {/* Cube Properties Modal (cube-designer-star) */}
      <Dialog
        open={propsOpen}
        title="Cube properties & design notes"
        size="large"
        onClose={() => !busyAction && setPropsOpen(false)}
        busy={busyAction}
        defaultAction={submitProperties}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setPropsOpen(false)}>
              Cancel
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitProperties}
            >
              Save properties
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="cube-designer-star"
          tabs={[
            {
              id: 'general',
              label: 'General & Fact Source',
              render: () => (
                <FormGrid columns={2}>
                  <TextField
                    label="Cube name"
                    required
                    value={propsDraft.name}
                    onChange={(e) =>
                      setPropsDraft((cur) => ({...cur, name: e.target.value}))
                    }
                  />
                  <TextField
                    label="Minor version label"
                    value={propsDraft.versionLabel}
                    onChange={(e) =>
                      setPropsDraft((cur) => ({
                        ...cur,
                        versionLabel: e.target.value,
                      }))
                    }
                  />
                  <Box sx={{gridColumn: '1 / -1'}}>
                    <TextField
                      label="Cube description (serialized safely via @cube.description)"
                      value={propsDraft.description}
                      onChange={(e) =>
                        setPropsDraft((cur) => ({
                          ...cur,
                          description: e.target.value,
                        }))
                      }
                    />
                  </Box>
                  <TextField
                    label="Primary fact source ID"
                    disabled
                    value={propsDraft.factSourceId}
                  />
                  <TextField
                    label="Fact table relation (schema.table)"
                    value={propsDraft.factRelationCsv}
                    onChange={(e) =>
                      setPropsDraft((cur) => ({
                        ...cur,
                        factRelationCsv: e.target.value,
                      }))
                    }
                  />
                </FormGrid>
              ),
            },
            {
              id: 'notes',
              label: 'DDN Design Notes',
              render: () => (
                <TypedRowsEditor
                  label="Cube DDN Notes"
                  rows={propsDraft.noteRows}
                  addLabel="Add note"
                  columns={[
                    {
                      key: 'note',
                      label: 'Design Note',
                      placeholder: 'e.g. Grain verified with finance team',
                      minWidth: 320,
                    },
                  ]}
                  onChange={(rows) =>
                    setPropsDraft((cur) => ({...cur, noteRows: rows}))
                  }
                />
              ),
            },
          ]}
        />
      </Dialog>

      {/* Dimension Tabbed Editor Modal (cube-designer-dimension) */}
      <Dialog
        open={dimOpen}
        title="Dimension, unknown member policy & hierarchies"
        size="large"
        onClose={() => !busyAction && setDimOpen(false)}
        busy={busyAction}
        defaultAction={submitDimension}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setDimOpen(false)}>
              Cancel
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitDimension}
            >
              Save dimension
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <Select
            label="Select dimension to edit"
            value={dimDraft.selectedExistingId}
            options={[
              {value: '__new__', label: '+ Create new dimension'},
              ...(cubeModel?.dimensions || []).map((d) => ({
                value: d.id,
                label: `${d.name} (${d.id})`,
              })),
            ]}
            onChange={(val) => {
              if (val === '__new__') {
                loadDimensionIntoDraft(null);
              } else {
                const found = (cubeModel?.dimensions || []).find(
                  (d) => d.id === val
                );
                loadDimensionIntoDraft(found || null);
              }
            }}
          />
          <DesignerModalTabs
            formKey="cube-designer-dimension"
            tabs={[
              {
                id: 'general',
                label: 'General & Unknown Member Policy',
                render: () => (
                  <FormGrid columns={2}>
                    <TextField
                      label="Dimension name"
                      required
                      value={dimDraft.name}
                      onChange={(e) =>
                        setDimDraft((cur) => ({...cur, name: e.target.value}))
                      }
                    />
                    <TextField
                      label="Dimension ID (optional)"
                      value={dimDraft.id}
                      onChange={(e) =>
                        setDimDraft((cur) => ({...cur, id: e.target.value}))
                      }
                    />
                    <TextField
                      label="Source table ID"
                      value={dimDraft.sourceId}
                      onChange={(e) =>
                        setDimDraft((cur) => ({
                          ...cur,
                          sourceId: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Key column"
                      required
                      value={dimDraft.keyField}
                      onChange={(e) =>
                        setDimDraft((cur) => ({
                          ...cur,
                          keyField: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Display name column (optional)"
                      value={dimDraft.nameField}
                      onChange={(e) =>
                        setDimDraft((cur) => ({
                          ...cur,
                          nameField: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Sort column (optional)"
                      value={dimDraft.sortField}
                      onChange={(e) =>
                        setDimDraft((cur) => ({
                          ...cur,
                          sortField: e.target.value,
                        }))
                      }
                    />
                    <Select
                      label="Unknown member policy"
                      value={dimDraft.unknownMemberPolicy}
                      options={UNKNOWN_MEMBER_POLICY_OPTIONS}
                      onChange={(val) =>
                        setDimDraft((cur) => ({
                          ...cur,
                          unknownMemberPolicy: val,
                        }))
                      }
                    />
                    <TextField
                      label="Unknown member caption"
                      disabled={dimDraft.unknownMemberPolicy !== 'unknown'}
                      value={dimDraft.unknownMemberCaption}
                      onChange={(e) =>
                        setDimDraft((cur) => ({
                          ...cur,
                          unknownMemberCaption: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Role-playing base dimension ID (optional)"
                      value={dimDraft.roleOf}
                      onChange={(e) =>
                        setDimDraft((cur) => ({...cur, roleOf: e.target.value}))
                      }
                    />
                    <Stack gap="compact" sx={{pt: 1}}>
                      <Checkbox
                        label="Active relationship in default queries"
                        checked={dimDraft.active}
                        onChange={(checked) =>
                          setDimDraft((cur) => ({
                            ...cur,
                            active: Boolean(checked),
                          }))
                        }
                      />
                      <Checkbox
                        label="Mark as Time dimension"
                        checked={dimDraft.isTime}
                        onChange={(checked) =>
                          setDimDraft((cur) => ({
                            ...cur,
                            isTime: Boolean(checked),
                          }))
                        }
                      />
                    </Stack>
                  </FormGrid>
                ),
              },
              {
                id: 'attributes',
                label: 'Attributes & Fixed/Changing Relationships',
                render: () => (
                  <TypedRowsEditor
                    label="Dimension Attributes"
                    rows={dimDraft.attributeRows}
                    addLabel="Add attribute"
                    columns={[
                      {
                        key: 'name',
                        label: 'Attribute Name',
                        placeholder: 'Customer Segment',
                        minWidth: 150,
                      },
                      {
                        key: 'column',
                        label: 'Source Column',
                        placeholder: 'segment',
                        minWidth: 130,
                      },
                      {
                        key: 'sortColumn',
                        label: 'Sort Column',
                        placeholder: 'segment_order',
                        minWidth: 120,
                      },
                      {
                        key: 'relationshipType',
                        label: 'Relationship Type',
                        type: 'select',
                        default: 'changing',
                        options: ATTRIBUTE_REL_OPTIONS,
                        minWidth: 180,
                      },
                    ]}
                    onChange={(rows) =>
                      setDimDraft((cur) => ({...cur, attributeRows: rows}))
                    }
                  />
                ),
              },
              {
                id: 'hierarchies',
                label: 'Hierarchies & Parent-Child',
                render: () => (
                  <Stack gap="standard">
                    <FormGrid columns={2}>
                      <Select
                        label="Hierarchy kind"
                        value={dimDraft.hierarchyKind}
                        options={HIERARCHY_KIND_OPTIONS}
                        onChange={(val) =>
                          setDimDraft((cur) => ({...cur, hierarchyKind: val}))
                        }
                      />
                      {dimDraft.hierarchyKind !== 'none' && (
                        <TextField
                          label="Hierarchy name"
                          value={dimDraft.hierarchyName}
                          onChange={(e) =>
                            setDimDraft((cur) => ({
                              ...cur,
                              hierarchyName: e.target.value,
                            }))
                          }
                        />
                      )}
                    </FormGrid>
                    {dimDraft.hierarchyKind === 'level' && (
                      <TypedRowsEditor
                        label="Ordered Hierarchy Levels"
                        rows={dimDraft.levelRows}
                        reorderable
                        addLabel="Add level"
                        columns={[
                          {
                            key: 'name',
                            label: 'Level Name',
                            placeholder: 'Country',
                            minWidth: 150,
                          },
                          {
                            key: 'column',
                            label: 'Level Column',
                            placeholder: 'country',
                            minWidth: 150,
                          },
                          {
                            key: 'relationshipType',
                            label: 'Relationship Type',
                            type: 'select',
                            default: 'changing',
                            options: ATTRIBUTE_REL_OPTIONS,
                            minWidth: 180,
                          },
                        ]}
                        onChange={(rows) =>
                          setDimDraft((cur) => ({...cur, levelRows: rows}))
                        }
                      />
                    )}
                    {dimDraft.hierarchyKind === 'parent_child' && (
                      <FormGrid columns={2}>
                        <TextField
                          label="Parent key column"
                          required
                          value={dimDraft.parentField}
                          onChange={(e) =>
                            setDimDraft((cur) => ({
                              ...cur,
                              parentField: e.target.value,
                            }))
                          }
                        />
                        <NumberField
                          label="Max recursion depth"
                          value={dimDraft.maxDepth}
                          onChange={(e) =>
                            setDimDraft((cur) => ({
                              ...cur,
                              maxDepth: Number(e.target.value) || 8,
                            }))
                          }
                        />
                      </FormGrid>
                    )}
                    {dimDraft.hierarchyKind !== 'none' && (
                      <Checkbox
                        label="Allow ragged / unbalanced members"
                        checked={dimDraft.ragged}
                        onChange={(checked) =>
                          setDimDraft((cur) => ({
                            ...cur,
                            ragged: Boolean(checked),
                          }))
                        }
                      />
                    )}
                  </Stack>
                ),
              },
              {
                id: 'roles',
                label: 'Role Visibility',
                render: () => (
                  <Stack gap="standard">
                    <Banner status="info">
                      Store portable role identifiers only (e.g.{' '}
                      <code>analyst</code>, <code>finance_exec</code>). User
                      emails, grants, and secrets are excluded from DDN.
                    </Banner>
                    <TypedRowsEditor
                      label="Visible Roles"
                      rows={dimDraft.roleRows}
                      addLabel="Add role"
                      columns={[
                        {
                          key: 'role',
                          label: 'Portable Role Identifier',
                          placeholder: 'analyst',
                          minWidth: 240,
                        },
                      ]}
                      onChange={(rows) =>
                        setDimDraft((cur) => ({...cur, roleRows: rows}))
                      }
                    />
                  </Stack>
                ),
              },
            ]}
          />
        </Stack>
      </Dialog>

      {/* Measure Tabbed Editor Modal (cube-designer-measures) */}
      <Dialog
        open={measureOpen}
        title="Measure, semi-additive & filter editor"
        size="large"
        onClose={() => !busyAction && setMeasureOpen(false)}
        busy={busyAction}
        defaultAction={submitMeasure}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setMeasureOpen(false)}>
              Cancel
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitMeasure}
            >
              Save measure
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <Select
            label="Select measure to edit"
            value={measureDraft.selectedExistingId}
            options={[
              {value: '__new__', label: '+ Create new measure'},
              ...(cubeModel?.measures || []).map((m) => ({
                value: m.id,
                label: `${m.name} (${m.aggregation})`,
              })),
            ]}
            onChange={(val) => {
              if (val === '__new__') {
                loadMeasureIntoDraft(null);
              } else {
                const found = (cubeModel?.measures || []).find(
                  (m) => m.id === val
                );
                loadMeasureIntoDraft(found || null);
              }
            }}
          />
          <DesignerModalTabs
            formKey="cube-designer-measures"
            tabs={[
              {
                id: 'aggregation',
                label: 'Aggregation & Expression',
                render: () => (
                  <FormGrid columns={2}>
                    <TextField
                      label="Measure name"
                      required
                      value={measureDraft.name}
                      onChange={(e) =>
                        setMeasureDraft((cur) => ({
                          ...cur,
                          name: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Measure ID (optional)"
                      value={measureDraft.id}
                      onChange={(e) =>
                        setMeasureDraft((cur) => ({...cur, id: e.target.value}))
                      }
                    />
                    <Select
                      label="Aggregation"
                      value={measureDraft.aggregation}
                      options={AGGREGATION_OPTIONS}
                      onChange={(val) =>
                        setMeasureDraft((cur) => ({...cur, aggregation: val}))
                      }
                    />
                    <TextField
                      label="Source table ID"
                      value={measureDraft.sourceId}
                      onChange={(e) =>
                        setMeasureDraft((cur) => ({
                          ...cur,
                          sourceId: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Measure column"
                      value={measureDraft.field}
                      onChange={(e) =>
                        setMeasureDraft((cur) => ({
                          ...cur,
                          field: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Measure group ID"
                      value={measureDraft.measureGroupId}
                      onChange={(e) =>
                        setMeasureDraft((cur) => ({
                          ...cur,
                          measureGroupId: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Display folder (optional)"
                      value={measureDraft.displayFolder}
                      onChange={(e) =>
                        setMeasureDraft((cur) => ({
                          ...cur,
                          displayFolder: e.target.value,
                        }))
                      }
                    />
                  </FormGrid>
                ),
              },
              {
                id: 'semi_filter',
                label: 'Semi-Additive & Filter',
                render: () => (
                  <Stack gap="standard">
                    {SEMI_ADDITIVE_SET.has(measureDraft.aggregation) ? (
                      <FormGrid columns={2}>
                        <TextField
                          label="Semi-additive time dimension ID"
                          required
                          value={measureDraft.semiAdditiveDimension}
                          onChange={(e) =>
                            setMeasureDraft((cur) => ({
                              ...cur,
                              semiAdditiveDimension: e.target.value,
                            }))
                          }
                        />
                        <Select
                          label="Within-period aggregation"
                          value={measureDraft.withinGroupAggregation}
                          options={[
                            {value: 'sum', label: 'SUM'},
                            {value: 'min', label: 'MIN'},
                            {value: 'max', label: 'MAX'},
                            {value: 'avg', label: 'AVG'},
                            {value: 'count', label: 'COUNT'},
                          ]}
                          onChange={(val) =>
                            setMeasureDraft((cur) => ({
                              ...cur,
                              withinGroupAggregation: val,
                            }))
                          }
                        />
                      </FormGrid>
                    ) : (
                      <Banner status="info">
                        Select a semi-additive aggregation on the first tab (e.g.{' '}
                        <code>LAST NON-EMPTY</code>) to configure snapshot time
                        rollup rules.
                      </Banner>
                    )}
                    <TypedRowsEditor
                      label="Filtered Measure Row Predicates"
                      rows={measureDraft.filterRows}
                      addLabel="Add filter"
                      columns={[
                        {
                          key: 'column',
                          label: 'Fact Column',
                          placeholder: 'status',
                          minWidth: 140,
                        },
                        {
                          key: 'operator',
                          label: 'Operator',
                          type: 'select',
                          default: 'eq',
                          options: [
                            {value: 'eq', label: '= (eq)'},
                            {value: 'ne', label: '!= (ne)'},
                            {value: 'gt', label: '> (gt)'},
                            {value: 'gte', label: '>= (gte)'},
                            {value: 'lt', label: '< (lt)'},
                            {value: 'lte', label: '<= (lte)'},
                          ],
                          minWidth: 120,
                        },
                        {
                          key: 'value',
                          label: 'Literal Value',
                          placeholder: 'PRIORITY',
                          minWidth: 150,
                        },
                      ]}
                      onChange={(rows) =>
                        setMeasureDraft((cur) => ({...cur, filterRows: rows}))
                      }
                    />
                  </Stack>
                ),
              },
              {
                id: 'format_roles',
                label: 'Format & Role Visibility',
                render: () => (
                  <Stack gap="standard">
                    <FormGrid columns={2}>
                      <TextField
                        label="Display format"
                        value={measureDraft.format}
                        onChange={(e) =>
                          setMeasureDraft((cur) => ({
                            ...cur,
                            format: e.target.value,
                          }))
                        }
                      />
                      <Select
                        label="Certification status"
                        value={measureDraft.certification}
                        options={[
                          {value: 'uncertified', label: 'Uncertified'},
                          {value: 'candidate', label: 'Candidate'},
                          {value: 'certified', label: 'Certified'},
                          {value: 'deprecated', label: 'Deprecated'},
                        ]}
                        onChange={(val) =>
                          setMeasureDraft((cur) => ({
                            ...cur,
                            certification: val,
                          }))
                        }
                      />
                    </FormGrid>
                    <TypedRowsEditor
                      label="Visible Roles"
                      rows={measureDraft.roleRows}
                      addLabel="Add role"
                      columns={[
                        {
                          key: 'role',
                          label: 'Portable Role Identifier',
                          placeholder: 'finance_exec',
                          minWidth: 240,
                        },
                      ]}
                      onChange={(rows) =>
                        setMeasureDraft((cur) => ({...cur, roleRows: rows}))
                      }
                    />
                  </Stack>
                ),
              },
            ]}
          />
        </Stack>
      </Dialog>

      {/* Interactive Dimension Usage Matrix Modal (cube-designer-measures) */}
      <Dialog
        open={matrixOpen}
        title="Interactive dimension usage matrix"
        size="large"
        onClose={() => !busyAction && setMatrixOpen(false)}
        busy={busyAction}
        defaultAction={submitUsageMatrix}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setMatrixOpen(false)}>
              Cancel
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitUsageMatrix}
            >
              Save usage matrix
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="cube-designer-measures" />
          <Banner status="info">
            Click any cell to cycle binding state:{' '}
            <strong>Bound (active)</strong> →{' '}
            <strong>Role-playing (inactive)</strong> →{' '}
            <strong>Unbound (—)</strong>.
          </Banner>
          {!(cubeModel?.dimensions || []).length ? (
            <EmptyState message="Add at least one dimension to edit measure-group bindings." />
          ) : (
            <ScrollArea label="Dimension usage matrix editor" sx={{maxHeight: 360}}>
              <Box
                component="table"
                aria-label="Interactive dimension usage matrix"
                sx={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: '0.8125rem',
                }}
              >
                <Box component="thead">
                  <Box component="tr">
                    <Box
                      component="th"
                      sx={{
                        textAlign: 'left',
                        p: 0.75,
                        borderBottom: '1px solid',
                        borderColor: 'divider',
                      }}
                    >
                      Measure Group (Measures)
                    </Box>
                    {(cubeModel?.dimensions || []).map((dim) => (
                      <Box
                        key={dim.id}
                        component="th"
                        sx={{
                          textAlign: 'center',
                          p: 0.75,
                          borderBottom: '1px solid',
                          borderColor: 'divider',
                        }}
                      >
                        {dim.name}
                      </Box>
                    ))}
                  </Box>
                </Box>
                <Box component="tbody">
                  {matrixGroups.map((grp) => (
                    <Box key={grp.id} component="tr">
                      <Box
                        component="td"
                        sx={{
                          p: 0.75,
                          borderBottom: '1px solid',
                          borderColor: 'divider',
                        }}
                      >
                        <strong>{grp.name}</strong>
                        <Box
                          component="div"
                          sx={{fontSize: '0.75rem', color: 'text.secondary'}}
                        >
                          {(grp.measures || []).join(', ') || '(no measures)'}
                        </Box>
                      </Box>
                      {(cubeModel?.dimensions || []).map((dim) => {
                        const usage = (grp.dimension_usage || []).find(
                          (u) => u.dimension_id === dim.id
                        );
                        const keyName =
                          dim.key_field?.field || dim.field?.field || dim.id;
                        let cellLabel = '—';
                        let intent = 'neutral';
                        if (usage && usage.active !== false) {
                          cellLabel = `${keyName} (active)`;
                          intent = 'primary';
                        } else if (usage) {
                          cellLabel = `${keyName} (role-playing)`;
                        }
                        return (
                          <Box
                            key={dim.id}
                            component="td"
                            sx={{
                              textAlign: 'center',
                              p: 0.5,
                              borderBottom: '1px solid',
                              borderColor: 'divider',
                            }}
                          >
                            <Button
                              size="small"
                              intent={intent}
                              aria-label={`Usage ${grp.name} × ${dim.name}`}
                              onClick={() => cycleMatrixCell(grp.id, dim)}
                            >
                              {cellLabel}
                            </Button>
                          </Box>
                        );
                      })}
                    </Box>
                  ))}
                </Box>
              </Box>
            </ScrollArea>
          )}
        </Stack>
      </Dialog>

      {/* AI Draft Proposal Modal (cube-designer-measures) */}
      <Dialog
        open={aiOpen}
        title="BYOK AI cube draft assistant (human review required)"
        size="large"
        onClose={() => !busyAction && setAiOpen(false)}
        busy={busyAction}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setAiOpen(false)}>
              Close
            </Button>
            {aiProposal?.proposed_model && (
              <Button
                intent="primary"
                loading={busyAction}
                onClick={applyAiProposalToDraft}
              >
                Apply proposal into draft
              </Button>
            )}
          </>
        }
      >
        <DesignerModalTabs
          formKey="cube-designer-measures"
          activeTab={aiTab}
          onTabChange={setAiTab}
          tabs={[
            {
              id: 'request',
              label: 'Question & Table Schema',
              render: () => (
                <Stack gap="standard">
                  <Banner status="info">
                    Searches existing project cubes first and produces only a{' '}
                    <strong>Draft</strong> proposal for human review. Agents
                    never accept, merge, or publish.
                  </Banner>
                  <FormGrid columns={2}>
                    <TextField
                      label="Business question / modelling goal"
                      placeholder="Analyze order revenue by customer and month"
                      value={aiDraftReq.prompt}
                      onChange={(e) =>
                        setAiDraftReq((cur) => ({
                          ...cur,
                          prompt: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Fact table (schema.table)"
                      value={aiDraftReq.factTable}
                      onChange={(e) =>
                        setAiDraftReq((cur) => ({
                          ...cur,
                          factTable: e.target.value,
                        }))
                      }
                    />
                    <Box sx={{gridColumn: '1 / -1'}}>
                      <TextField
                        type="password"
                        label="Optional BYOK API key (ephemeral — never stored)"
                        value={aiDraftReq.apiKey}
                        onChange={(e) =>
                          setAiDraftReq((cur) => ({
                            ...cur,
                            apiKey: e.target.value,
                          }))
                        }
                      />
                    </Box>
                  </FormGrid>
                  <TypedRowsEditor
                    label="Fact Table Columns"
                    rows={aiDraftReq.columnRows}
                    addLabel="Add column"
                    columns={[
                      {
                        key: 'name',
                        label: 'Column Name',
                        placeholder: 'amount',
                        minWidth: 160,
                      },
                      {
                        key: 'type',
                        label: 'SQL Type',
                        type: 'select',
                        default: 'text',
                        options: [
                          {value: 'integer', label: 'integer'},
                          {value: 'numeric', label: 'numeric'},
                          {value: 'date', label: 'date'},
                          {value: 'timestamp', label: 'timestamp'},
                          {value: 'text', label: 'text'},
                        ],
                        minWidth: 140,
                      },
                    ]}
                    onChange={(rows) =>
                      setAiDraftReq((cur) => ({...cur, columnRows: rows}))
                    }
                  />
                  <Box>
                    <Button
                      intent="primary"
                      loading={busyAction}
                      onClick={runAiDraftProposal}
                    >
                      Generate draft proposal
                    </Button>
                  </Box>
                </Stack>
              ),
            },
            {
              id: 'proposal',
              label: 'Matched Cubes & Draft Diff',
              render: () =>
                !aiProposal ? (
                  <EmptyState message="Run Generate draft proposal to search existing cubes and preview a Draft diff." />
                ) : (
                  <Stack gap="standard">
                    <Banner status="warning">
                      Human review required: status is{' '}
                      <strong>{aiProposal.status}</strong> (
                      {aiProposal.diff_summary?.measures_added || 0} measure(s),{' '}
                      {aiProposal.diff_summary?.dimensions_added || 0}{' '}
                      dimension(s),{' '}
                      {aiProposal.diff_summary?.aggregations_added || 0}{' '}
                      aggregation plan(s)).
                    </Banner>
                    {aiProposal.matched_existing_cubes?.length > 0 && (
                      <Banner status="info">
                        Matched existing project cube(s):{' '}
                        {aiProposal.matched_existing_cubes
                          .map((c) => `${c.title} (v${c.head_version || 1})`)
                          .join(', ')}
                      </Banner>
                    )}
                    <Box sx={{height: 220}}>
                      <CodeEditor
                        label="Proposed Cube DDN Draft"
                        value={aiProposal.proposed_ddn_text || ''}
                        readonly
                        language="sql"
                      />
                    </Box>
                  </Stack>
                ),
            },
          ]}
        />
      </Dialog>

      {/* Try a Query Slice-and-Dice Modal (cube-designer-star) */}
      <Dialog
        open={tryOpen}
        title="Try a slice-and-dice cube query"
        size="large"
        onClose={() => !busyAction && setTryOpen(false)}
        busy={busyAction}
        actions={
          <>
            <QueryExecutionToolbarCluster
              controller={cubeQueryController}
              onRun={runTryQuery}
              qaKeyPrefix="cube-try-query"
            />
            <Button disabled={busyAction} onClick={() => setTryOpen(false)}>
              Close
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={runTryQuery}
            >
              Compile & run query
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="cube-designer-star"
          activeTab={tryTab}
          onTabChange={setTryTab}
          tabs={[
            {
              id: 'builder',
              label: 'Dimensions, Measures & Context',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <Box>
                      <Box
                        component="div"
                        sx={{fontWeight: 600, fontSize: '0.8125rem', mb: 0.5}}
                      >
                        Group-By Dimensions
                      </Box>
                      <Stack gap="compact">
                        {(cubeModel?.dimensions || []).map((dim) => (
                          <Checkbox
                            key={dim.id}
                            label={`${dim.name} (${dim.id})`}
                            checked={tryDraft.selectedDims.includes(dim.id)}
                            onChange={(checked) =>
                              setTryDraft((cur) => ({
                                ...cur,
                                selectedDims: checked
                                  ? [...cur.selectedDims, dim.id]
                                  : cur.selectedDims.filter(
                                    (id) => id !== dim.id
                                  ),
                              }))
                            }
                          />
                        ))}
                      </Stack>
                    </Box>
                    <Box>
                      <Box
                        component="div"
                        sx={{fontWeight: 600, fontSize: '0.8125rem', mb: 0.5}}
                      >
                        Aggregated Measures
                      </Box>
                      <Stack gap="compact">
                        {(cubeModel?.measures || []).map((m) => (
                          <Checkbox
                            key={m.id}
                            label={`${m.name} (${m.aggregation})`}
                            checked={tryDraft.selectedMeasures.includes(m.id)}
                            onChange={(checked) =>
                              setTryDraft((cur) => ({
                                ...cur,
                                selectedMeasures: checked
                                  ? [...cur.selectedMeasures, m.id]
                                  : cur.selectedMeasures.filter(
                                    (id) => id !== m.id
                                  ),
                              }))
                            }
                          />
                        ))}
                      </Stack>
                    </Box>
                    <Select
                      label="Target SQL dialect"
                      value={tryDraft.dialect}
                      options={ENGINE_OPTIONS}
                      onChange={(val) =>
                        setTryDraft((cur) => ({...cur, dialect: val}))
                      }
                    />
                    <TextField
                      label="Evaluate as Role (optional)"
                      placeholder="e.g. analyst"
                      value={tryDraft.role}
                      onChange={(e) =>
                        setTryDraft((cur) => ({...cur, role: e.target.value}))
                      }
                    />
                    <TextField
                      label="Locale overlay (optional)"
                      placeholder="e.g. fr-CA"
                      value={tryDraft.locale}
                      onChange={(e) =>
                        setTryDraft((cur) => ({...cur, locale: e.target.value}))
                      }
                    />
                    <TextField
                      label="Optional SQLite database path"
                      value={tryDraft.sqlitePath}
                      onChange={(e) =>
                        setTryDraft((cur) => ({
                          ...cur,
                          sqlitePath: e.target.value,
                        }))
                      }
                    />
                  </FormGrid>
                </Stack>
              ),
            },
            {
              id: 'sql_results',
              label: 'Compiled SQL & Results',
              render: () =>
                !tryResult ? (
                  <EmptyState message="Click Compile & run query to inspect compiled SQL and aggregate routing." />
                ) : (
                  <Stack gap="standard">
                    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap'}}>
                      <StatusBadge
                        status={
                          tryResult.aggregate_routing_hit?.matched
                            ? 'success'
                            : 'info'
                        }
                        label={
                          tryResult.aggregate_routing_hit?.matched
                            ? `Aggregate Hit: ${tryResult.aggregate_routing_hit.name}`
                            : 'Base Fact Table Scan'
                        }
                      />
                      <StatusBadge
                        status="neutral"
                        label={`Dialect: ${tryResult.dialect}`}
                      />
                    </Box>
                    <Box sx={{height: 180}}>
                      <CodeEditor
                        label="Compiled Slice-and-Dice SQL"
                        value={tryResult.compiled_sql || ''}
                        readonly
                        language="sql"
                      />
                    </Box>
                    {tryResult.preview_rows?.length > 0 && (
                      <ScrollArea label="Query preview rows" sx={{maxHeight: 180}}>
                        <Box className="sr-bui-table-card">
                          <Box
                            component="table"
                            className="sr-bui-table"
                            sx={{
                              width: '100%',
                              borderCollapse: 'collapse',
                              fontSize: '0.8125rem',
                            }}
                          >
                            <Box component="thead">
                              <Box component="tr">
                                {(tryResult.columns || []).map((col) => (
                                  <Box
                                    key={col.id}
                                    component="th"
                                    className="sr-bui-th"
                                    sx={{textAlign: 'left'}}
                                  >
                                    {col.label}
                                  </Box>
                                ))}
                              </Box>
                            </Box>
                            <Box component="tbody">
                              {tryResult.preview_rows
                                .slice(0, cubeQueryController.maxRows)
                                .map((row, rIdx) => (
                                  <Box key={rIdx} component="tr" className="sr-bui-tr">
                                    {(tryResult.columns || []).map((col) => (
                                      <Box
                                        key={col.id}
                                        component="td"
                                        className="sr-bui-td"
                                      >
                                        {String(row[col.id] ?? 'NULL')}
                                      </Box>
                                    ))}
                                  </Box>
                                ))}
                            </Box>
                          </Box>
                          <QueryStepStatusFooter
                            controller={cubeQueryController}
                            qaKey="cube-try-query-footer"
                          />
                        </Box>
                      </ScrollArea>
                    )}
                  </Stack>
                ),
            },
          ]}
        />
      </Dialog>

      {/* Combinatorial Rule Reducer Modal (cube-designer-aggregations) */}
      <Dialog
        open={reducerOpen}
        title="Combinatorial aggregation rule-group reducer"
        size="large"
        onClose={() => !busyAction && setReducerOpen(false)}
        busy={busyAction}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setReducerOpen(false)}>
              Close
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => invokeReducer(false)}
            >
              Preview reduced cuboids
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={() => invokeReducer(true)}
            >
              Apply reduced plans & save draft
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="cube-designer-aggregations"
          activeTab={reducerTab}
          onTabChange={setReducerTab}
          banner={
            <Box sx={{mb: 1, display: 'flex', gap: 1, alignItems: 'center'}}>
              <StatusBadge
                status="success"
                label={`Cuboid Reduction: ${
                  reducerResult
                    ? `${reducerResult.naive_cuboid_count} → ${reducerResult.after_mandatory_and_joint_count} → ${reducerResult.final_cuboid_count}`
                    : `${liveReductionPreview.naive} → ${liveReductionPreview.afterMj} → ${liveReductionPreview.finalCount}`
                }`}
              />
            </Box>
          }
          tabs={[
            {
              id: 'rules',
              label: 'Mandatory, Hierarchy & Joint Rules',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <TextField
                      label="Candidate dimensions (comma-separated)"
                      value={reducerDraft.candidatesCsv}
                      onChange={(e) =>
                        setReducerDraft((cur) => ({
                          ...cur,
                          candidatesCsv: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Mandatory dimensions (comma-separated)"
                      value={reducerDraft.mandatoryCsv}
                      onChange={(e) =>
                        setReducerDraft((cur) => ({
                          ...cur,
                          mandatoryCsv: e.target.value,
                        }))
                      }
                    />
                    <NumberField
                      label="Max dimension combinations (cap N)"
                      value={reducerDraft.maxCombinations}
                      onChange={(e) =>
                        setReducerDraft((cur) => ({
                          ...cur,
                          maxCombinations:
                            e.target.value === ''
                              ? ''
                              : Number(e.target.value),
                        }))
                      }
                    />
                  </FormGrid>
                  <TypedRowsEditor
                    label="Hierarchy Prefix Sets (only contiguous prefix chains allowed)"
                    rows={reducerDraft.hierarchyRows}
                    addLabel="Add hierarchy chain"
                    columns={[
                      {
                        key: 'chain',
                        label: 'Ordered Level / Dimension IDs (comma-separated)',
                        placeholder: 'cal_year, cal_quarter, cal_month',
                        minWidth: 320,
                      },
                    ]}
                    onChange={(rows) =>
                      setReducerDraft((cur) => ({...cur, hierarchyRows: rows}))
                    }
                  />
                  <TypedRowsEditor
                    label="Joint Sets (all-or-nothing dimension groups)"
                    rows={reducerDraft.jointRows}
                    addLabel="Add joint group"
                    columns={[
                      {
                        key: 'group',
                        label: 'Joint Dimension IDs (comma-separated)',
                        placeholder: 'channel, promotion_type',
                        minWidth: 320,
                      },
                    ]}
                    onChange={(rows) =>
                      setReducerDraft((cur) => ({...cur, jointRows: rows}))
                    }
                  />
                </Stack>
              ),
            },
            {
              id: 'partition',
              label: 'Partitioning, Refresh & Generated Plans',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <TextField
                      label="Partition field (optional)"
                      placeholder="order_date"
                      value={reducerDraft.partitionField}
                      onChange={(e) =>
                        setReducerDraft((cur) => ({
                          ...cur,
                          partitionField: e.target.value,
                        }))
                      }
                    />
                    <Select
                      label="Partition grain"
                      value={reducerDraft.partitionGrain}
                      options={PARTITION_GRAIN_OPTIONS}
                      onChange={(val) =>
                        setReducerDraft((cur) => ({
                          ...cur,
                          partitionGrain: val,
                        }))
                      }
                    />
                    <Select
                      label="Refresh policy"
                      value={reducerDraft.refreshPolicy}
                      options={REFRESH_POLICY_OPTIONS}
                      onChange={(val) =>
                        setReducerDraft((cur) => ({
                          ...cur,
                          refreshPolicy: val,
                        }))
                      }
                    />
                    <Select
                      label="Materialization strategy"
                      value={reducerDraft.strategy}
                      options={[
                        {value: 'aggregate_table', label: 'Aggregate table'},
                        {value: 'materialized_view', label: 'Materialized view'},
                      ]}
                      onChange={(val) =>
                        setReducerDraft((cur) => ({...cur, strategy: val}))
                      }
                    />
                  </FormGrid>
                  {reducerResult?.generated_plans?.length > 0 && (
                    <ScrollArea label="Generated cuboid plans" sx={{maxHeight: 200}}>
                      <Box
                        component="table"
                        sx={{
                          width: '100%',
                          borderCollapse: 'collapse',
                          fontSize: '0.8125rem',
                        }}
                      >
                        <Box component="thead">
                          <Box component="tr">
                            {['Plan ID', 'Grain Dimensions', 'Refresh'].map(
                              (h) => (
                                <Box
                                  key={h}
                                  component="th"
                                  sx={{
                                    textAlign: 'left',
                                    p: 0.5,
                                    borderBottom: '1px solid',
                                    borderColor: 'divider',
                                  }}
                                >
                                  {h}
                                </Box>
                              )
                            )}
                          </Box>
                        </Box>
                        <Box component="tbody">
                          {reducerResult.generated_plans.map((p) => (
                            <Box key={p.id} component="tr">
                              <Box component="td" sx={{p: 0.5}}>
                                <code>{p.id}</code>
                              </Box>
                              <Box component="td" sx={{p: 0.5}}>
                                {(p.grain_dimensions || []).join(' × ')}
                              </Box>
                              <Box component="td" sx={{p: 0.5}}>
                                {p.refresh_policy} ({p.partition_grain})
                              </Box>
                            </Box>
                          ))}
                        </Box>
                      </Box>
                    </ScrollArea>
                  )}
                </Stack>
              ),
            },
          ]}
        />
      </Dialog>

      {/* Edit Single Aggregation Plan Modal (cube-designer-aggregations) */}
      <Dialog
        open={aggRuleOpen}
        title="Edit aggregation / materialization plan"
        size="medium"
        onClose={() => !busyAction && setAggRuleOpen(false)}
        busy={busyAction}
        defaultAction={submitAggRule}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setAggRuleOpen(false)}>
              Cancel
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitAggRule}
            >
              Save aggregation rule
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="cube-designer-aggregations"
          tabs={[
            {
              id: 'rule',
              label: 'Rule & Grain',
              render: () => (
                <FormGrid columns={2}>
                  <TextField
                    label="Rule name"
                    required
                    value={aggRuleDraft.name}
                    onChange={(e) =>
                      setAggRuleDraft((cur) => ({
                        ...cur,
                        name: e.target.value,
                      }))
                    }
                  />
                  <Select
                    label="Strategy"
                    value={aggRuleDraft.strategy}
                    options={[
                      {value: 'materialized_view', label: 'Materialized view'},
                      {value: 'aggregate_table', label: 'Aggregate table'},
                      {value: 'provider_managed', label: 'Provider managed'},
                    ]}
                    onChange={(val) =>
                      setAggRuleDraft((cur) => ({...cur, strategy: val}))
                    }
                  />
                  <TextField
                    label="Grain dimensions (comma-separated IDs)"
                    value={aggRuleDraft.grainDimensionsCsv}
                    onChange={(e) =>
                      setAggRuleDraft((cur) => ({
                        ...cur,
                        grainDimensionsCsv: e.target.value,
                      }))
                    }
                  />
                  <TextField
                    label="Measures (comma-separated IDs)"
                    value={aggRuleDraft.measuresCsv}
                    onChange={(e) =>
                      setAggRuleDraft((cur) => ({
                        ...cur,
                        measuresCsv: e.target.value,
                      }))
                    }
                  />
                  <TextField
                    label="Target relation (schema.object)"
                    value={aggRuleDraft.targetRelationCsv}
                    onChange={(e) =>
                      setAggRuleDraft((cur) => ({
                        ...cur,
                        targetRelationCsv: e.target.value,
                      }))
                    }
                  />
                  <Box sx={{pt: 1.5}}>
                    <Checkbox
                      label="Enabled upon version acceptance"
                      checked={aggRuleDraft.enabled}
                      onChange={(checked) =>
                        setAggRuleDraft((cur) => ({
                          ...cur,
                          enabled: Boolean(checked),
                        }))
                      }
                    />
                  </Box>
                </FormGrid>
              ),
            },
            {
              id: 'partition_refresh',
              label: 'Partitioning & Refresh',
              render: () => (
                <FormGrid columns={2}>
                  <TextField
                    label="Partition column (optional)"
                    value={aggRuleDraft.partitionField}
                    onChange={(e) =>
                      setAggRuleDraft((cur) => ({
                        ...cur,
                        partitionField: e.target.value,
                      }))
                    }
                  />
                  <Select
                    label="Partition grain"
                    value={aggRuleDraft.partitionGrain}
                    options={PARTITION_GRAIN_OPTIONS}
                    onChange={(val) =>
                      setAggRuleDraft((cur) => ({
                        ...cur,
                        partitionGrain: val,
                      }))
                    }
                  />
                  <Select
                    label="Refresh policy"
                    value={aggRuleDraft.refreshPolicy}
                    options={REFRESH_POLICY_OPTIONS}
                    onChange={(val) =>
                      setAggRuleDraft((cur) => ({
                        ...cur,
                        refreshPolicy: val,
                      }))
                    }
                  />
                </FormGrid>
              ),
            },
          ]}
        />
      </Dialog>

      {/* Check Against Connection Modal (cube-designer-star) */}
      <Dialog
        open={checkConnOpen}
        title="Check cube keys, joins & fan-out against connection"
        size="large"
        onClose={() => !busyAction && setCheckConnOpen(false)}
        busy={busyAction}
        actions={
          <>
            <Button
              disabled={busyAction}
              onClick={() => setCheckConnOpen(false)}
            >
              Close
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={runCheckConnection}
            >
              Run connection check
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="cube-designer-star" />
          <FormGrid columns={2}>
            <TextField
              label="Optional SQLite file path for live verification"
              value={checkConnPath}
              onChange={(e) => setCheckConnPath(e.target.value)}
            />
            {checkConnResult && (
              <Box sx={{pt: 2.25}}>
                <StatusBadge
                  status={
                    checkConnResult.overall_status === 'valid'
                      ? 'success'
                      : checkConnResult.overall_status === 'fanout_risk'
                        ? 'error'
                        : 'warning'
                  }
                  label={`Status: ${checkConnResult.overall_status}`}
                />
              </Box>
            )}
          </FormGrid>
          {checkConnResult?.dimensions?.length > 0 && (
            <>
              <ScrollArea label="Dimension probe results" sx={{maxHeight: 200}}>
                <Box
                  component="table"
                  sx={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    fontSize: '0.8125rem',
                  }}
                >
                  <Box component="thead">
                    <Box component="tr">
                      {[
                        'Dimension',
                        'Key',
                        'Status',
                        'Dup Keys',
                        'Orphan FKs',
                        'Diagnostic',
                      ].map((h) => (
                        <Box
                          key={h}
                          component="th"
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
                    {checkConnResult.dimensions.map((d) => (
                      <Box key={d.dimension_id} component="tr">
                        <Box component="td" sx={{p: 0.5}}>
                          <strong>{d.dimension_name || d.dimension_id}</strong>
                        </Box>
                        <Box component="td" sx={{p: 0.5}}>
                          <code>{d.key_field}</code>
                        </Box>
                        <Box component="td" sx={{p: 0.5}}>
                          <StatusBadge
                            status={
                              d.status === 'valid'
                                ? 'success'
                                : d.status === 'fanout_risk'
                                  ? 'error'
                                  : 'warning'
                            }
                            label={d.status}
                          />
                        </Box>
                        <Box component="td" sx={{p: 0.5}}>
                          {d.duplicate_keys}
                        </Box>
                        <Box component="td" sx={{p: 0.5}}>
                          {d.orphan_fact_rows}
                        </Box>
                        <Box component="td" sx={{p: 0.5}}>
                          {d.message}
                        </Box>
                      </Box>
                    ))}
                  </Box>
                </Box>
              </ScrollArea>
              <Box sx={{height: 160}}>
                <CodeEditor
                  label="Generated Connection Probe SQL"
                  value={checkConnResult.dimensions
                    .map((d) => `-- ${d.dimension_id}\n${d.probe_sql}`)
                    .join('\n\n')}
                  readonly
                  language="sql"
                />
              </Box>
            </>
          )}
        </Stack>
      </Dialog>

      {/* Materialization DDL Plan Modal (cube-designer-aggregations) */}
      <Dialog
        open={matPlanOpen}
        title="Materialized aggregate native-operation review plan"
        size="large"
        onClose={() => !busyAction && setMatPlanOpen(false)}
        busy={busyAction}
        actions={<Button onClick={() => setMatPlanOpen(false)}>Close</Button>}
      >
        <Stack gap="standard">
          <FormReference formKey="cube-designer-aggregations" />
          <Select
            label="Target SQL dialect"
            value={matEngine}
            options={ENGINE_OPTIONS}
            onChange={(val) => {
              setMatEngine(val);
              openMaterializationPlan(val);
            }}
          />
          {matPlan && (
            <>
              {matPlan.destructive_warning && (
                <Banner status="warning">{matPlan.destructive_warning}</Banner>
              )}
              {matPlan.grain_warnings?.length > 0 && (
                <Banner status="error">
                  Semi-additive grain warning:{' '}
                  {matPlan.grain_warnings.join(' · ')}
                </Banner>
              )}
              <Box sx={{height: 240}}>
                <CodeEditor
                  label="Native Review SQL Preview"
                  value={
                    matPlan.sql_preview ||
                    '-- No materialized-aggregate database changes detected.'
                  }
                  readonly
                  language="sql"
                />
              </Box>
            </>
          )}
        </Stack>
      </Dialog>

      {/* Perspectives & Role Visibility Modal (cube-designer-governance) */}
      <Dialog
        open={perspOpen}
        title="Add or update cube perspective & role visibility"
        size="medium"
        onClose={() => !busyAction && setPerspOpen(false)}
        busy={busyAction}
        defaultAction={submitPerspective}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setPerspOpen(false)}>
              Cancel
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitPerspective}
            >
              Save perspective
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="cube-designer-governance"
          tabs={[
            {
              id: 'scope',
              label: 'Included Scope',
              render: () => (
                <FormGrid columns={2}>
                  <TextField
                    label="Perspective name"
                    required
                    value={perspDraft.name}
                    onChange={(e) =>
                      setPerspDraft((cur) => ({...cur, name: e.target.value}))
                    }
                  />
                  <TextField
                    label="Default measure ID (optional)"
                    value={perspDraft.defaultMeasure}
                    onChange={(e) =>
                      setPerspDraft((cur) => ({
                        ...cur,
                        defaultMeasure: e.target.value,
                      }))
                    }
                  />
                  <Box sx={{gridColumn: '1 / -1'}}>
                    <TextField
                      label="Description (optional)"
                      value={perspDraft.description}
                      onChange={(e) =>
                        setPerspDraft((cur) => ({
                          ...cur,
                          description: e.target.value,
                        }))
                      }
                    />
                  </Box>
                  <TextField
                    label="Included dimensions (comma-separated IDs)"
                    value={perspDraft.dimensionsCsv}
                    onChange={(e) =>
                      setPerspDraft((cur) => ({
                        ...cur,
                        dimensionsCsv: e.target.value,
                      }))
                    }
                  />
                  <TextField
                    label="Included measures (comma-separated IDs)"
                    value={perspDraft.measuresCsv}
                    onChange={(e) =>
                      setPerspDraft((cur) => ({
                        ...cur,
                        measuresCsv: e.target.value,
                      }))
                    }
                  />
                </FormGrid>
              ),
            },
            {
              id: 'roles',
              label: 'Role Visibility',
              render: () => (
                <TypedRowsEditor
                  label="Perspective Visible Roles"
                  rows={perspDraft.roleRows}
                  addLabel="Add role"
                  columns={[
                    {
                      key: 'role',
                      label: 'Portable Role Identifier',
                      placeholder: 'finance_exec',
                      minWidth: 240,
                    },
                  ]}
                  onChange={(rows) =>
                    setPerspDraft((cur) => ({...cur, roleRows: rows}))
                  }
                />
              ),
            },
          ]}
        />
      </Dialog>

      {/* Locale Translations Modal (cube-designer-governance) */}
      <Dialog
        open={transOpen}
        title="Locale translations (BCP-47 captions & folders)"
        size="large"
        onClose={() => !busyAction && setTransOpen(false)}
        busy={busyAction}
        defaultAction={submitTranslation}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setTransOpen(false)}>
              Cancel
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitTranslation}
            >
              Save translation
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="cube-designer-governance" />
          <FormGrid columns={2}>
            <TextField
              label="BCP-47 locale tag"
              required
              value={transDraft.locale}
              onChange={(e) =>
                setTransDraft((cur) => ({...cur, locale: e.target.value}))
              }
            />
            <TextField
              label="Localized cube caption"
              value={transDraft.caption}
              onChange={(e) =>
                setTransDraft((cur) => ({...cur, caption: e.target.value}))
              }
            />
          </FormGrid>
          <TypedRowsEditor
            label="Translated Object Captions"
            rows={transDraft.entryRows}
            addLabel="Add translated entry"
            columns={[
              {
                key: 'targetKind',
                label: 'Object Kind',
                type: 'select',
                default: 'measure',
                options: TRANSLATION_TARGET_KIND_OPTIONS,
                minWidth: 130,
              },
              {
                key: 'targetId',
                label: 'Target ID',
                placeholder: 'gross_sales',
                minWidth: 140,
              },
              {
                key: 'caption',
                label: 'Translated Caption',
                placeholder: 'Ventes brutes',
                minWidth: 160,
              },
              {
                key: 'displayFolder',
                label: 'Display Folder',
                placeholder: 'Finance',
                minWidth: 120,
              },
            ]}
            onChange={(rows) =>
              setTransDraft((cur) => ({...cur, entryRows: rows}))
            }
          />
        </Stack>
      </Dialog>

      {/* External SML v1.8 / Apache Ossie v0.2.0 Export Modal (cube-designer-governance) */}
      <Dialog
        open={exportOpen}
        title="Export cube to SML v1.8 or Apache Ossie"
        size="large"
        onClose={() => !busyAction && setExportOpen(false)}
        busy={busyAction}
        actions={<Button onClick={() => setExportOpen(false)}>Close</Button>}
      >
        <Stack gap="standard">
          <FormReference formKey="cube-designer-governance" />
          <FormGrid columns={2}>
            <Select
              label="Interchange format"
              value={exportFormat}
              options={INTERCHANGE_FORMAT_OPTIONS}
              onChange={(val) => {
                setExportFormat(val);
                runInterchangeExport(val, exportIncludeExtensions);
              }}
            />
            {exportFormat === 'ossie' && (
              <Box sx={{pt: 1.5}}>
                <Checkbox
                  label="Include secret-free ScratchRobin custom_extensions"
                  checked={exportIncludeExtensions}
                  onChange={(checked) => {
                    const inc = Boolean(checked);
                    setExportIncludeExtensions(inc);
                    runInterchangeExport(exportFormat, inc);
                  }}
                />
              </Box>
            )}
          </FormGrid>
          {exportResult && (
            <>
              <Banner
                status={
                  exportResult.loss_report?.fidelity === 'exact'
                    ? 'success'
                    : 'warning'
                }
              >
                Export format: {exportResult.format} · Fidelity:{' '}
                {exportResult.loss_report?.fidelity || 'exact'} (
                {exportResult.loss_report?.loss_count ??
                  exportResult.loss_report?.items?.length ??
                  0}{' '}
                reported item(s))
              </Banner>
              {exportResult.loss_report?.items?.length > 0 && (
                <Stack gap="compact">
                  <Box sx={{display: 'flex', gap: 0.75, flexWrap: 'wrap'}}>
                    {exportResult.loss_report.items.map((item, idx) => (
                      <StatusBadge
                        key={`${item.category}:${idx}`}
                        status="warning"
                        label={`${item.category}: ${item.item_name}`}
                      />
                    ))}
                  </Box>
                  <Box sx={{height: 120}}>
                    <CodeEditor
                      label="Explicit Loss Report"
                      value={exportResult.loss_report.items
                        .map(
                          (item) =>
                            `[${item.category}] ${item.item_name}: ${item.reason}`
                        )
                        .join('\n')}
                      readonly
                      language="yaml"
                    />
                  </Box>
                </Stack>
              )}
              <Box sx={{height: 220}}>
                <CodeEditor
                  label="Generated Interchange YAML"
                  value={
                    exportResult.yaml ||
                    [
                      exportResult.manifest_yaml || '',
                      ...Object.entries(exportResult.files || {}).map(
                        ([path, body]) => `# --- ${path} ---\n${body}`
                      ),
                    ]
                      .filter(Boolean)
                      .join('\n\n')
                  }
                  readonly
                  language="yaml"
                />
              </Box>
            </>
          )}
        </Stack>
      </Dialog>

      {/* Save Directed Checkpoint Modal */}
      <Dialog
        open={saveOpen}
        title="Save cube checkpoint"
        size="large"
        onClose={() => !busyAction && setSaveOpen(false)}
        busy={busyAction}
        defaultAction={submitSaveCheckpoint}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setSaveOpen(false)}>
              Cancel
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitSaveCheckpoint}
            >
              Save checkpoint
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="cube-designer-workspace"
          tabs={[
            {
              id: 'checkpoint',
              label: 'Checkpoint & Notes',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <Select
                      label="Save-point status"
                      value={saveDraft.status}
                      options={[
                        {value: 'draft', label: 'Draft'},
                        {value: 'in_progress', label: 'In-progress'},
                        {value: 'in_review', label: 'In-review'},
                      ]}
                      onChange={(val) =>
                        setSaveDraft((cur) => ({...cur, status: val}))
                      }
                    />
                    <TextField
                      label="Checkpoint note"
                      value={saveDraft.note}
                      onChange={(e) =>
                        setSaveDraft((cur) => ({...cur, note: e.target.value}))
                      }
                    />
                  </FormGrid>
                  <TypedRowsEditor
                    label="DDN Design Notes"
                    rows={saveDraft.noteRows}
                    addLabel="Add note"
                    columns={[
                      {
                        key: 'note',
                        label: 'Note',
                        placeholder: 'Describe modelling checkpoint',
                        minWidth: 320,
                      },
                    ]}
                    onChange={(rows) =>
                      setSaveDraft((cur) => ({...cur, noteRows: rows}))
                    }
                  />
                </Stack>
              ),
            },
            {
              id: 'ddn_source',
              label: 'Cube DDN Source',
              render: () => (
                <Box sx={{height: 260}}>
                  <CodeEditor
                    label="Cube DDN Source"
                    value={saveDraft.ddnText}
                    onChange={(val) =>
                      setSaveDraft((cur) => ({
                        ...cur,
                        ddnText: typeof val === 'string' ? val : cur.ddnText,
                      }))
                    }
                    language="sql"
                  />
                </Box>
              ),
            },
          ]}
        />
      </Dialog>

      {/* Accept & Apply to Semantic-Model Store Modal */}
      <Dialog
        open={acceptOpen}
        title="Accept cube version & apply to semantic-model store"
        size="medium"
        onClose={() => !busyAction && setAcceptOpen(false)}
        busy={busyAction}
        defaultAction={submitAccept}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setAcceptOpen(false)}>
              Cancel
            </Button>
            <Button intent="primary" loading={busyAction} onClick={submitAccept}>
              Accept & apply
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          <FormReference formKey="cube-designer-governance" />
          <Banner status="info">
            Accepting makes this version the active cube in the ScratchRobin
            semantic-model store. Materialized aggregate DDL is never executed
            automatically and goes through native-operation review.
          </Banner>
          <FormGrid columns={2}>
            <TextField
              label="Semantic-model store Endpoint ID"
              value={acceptDraft.endpointId}
              onChange={(e) =>
                setAcceptDraft((cur) => ({
                  ...cur,
                  endpointId: e.target.value,
                }))
              }
            />
            <Select
              label="Target SQL engine for aggregate review"
              value={acceptDraft.targetEngine}
              options={ENGINE_OPTIONS}
              onChange={(val) =>
                setAcceptDraft((cur) => ({...cur, targetEngine: val}))
              }
            />
            <Box sx={{gridColumn: '1 / -1'}}>
              <Checkbox
                label="Require Git review reference"
                checked={acceptDraft.requireGitReview}
                onChange={(checked) =>
                  setAcceptDraft((cur) => ({
                    ...cur,
                    requireGitReview: Boolean(checked),
                  }))
                }
              />
            </Box>
            {acceptDraft.requireGitReview && (
              <TextField
                label="Git review / commit ref"
                required
                value={acceptDraft.gitReviewRef}
                onChange={(e) =>
                  setAcceptDraft((cur) => ({
                    ...cur,
                    gitReviewRef: e.target.value,
                  }))
                }
              />
            )}
            <TextField
              label="Approval comment"
              value={acceptDraft.comment}
              onChange={(e) =>
                setAcceptDraft((cur) => ({...cur, comment: e.target.value}))
              }
            />
          </FormGrid>
        </Stack>
      </Dialog>

      {/* Leave Accepted Modal */}
      <Dialog
        open={leaveOpen}
        title="Leave accepted cube version"
        size="medium"
        onClose={() => !busyAction && setLeaveOpen(false)}
        busy={busyAction}
        defaultAction={submitLeaveAccepted}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setLeaveOpen(false)}>
              Cancel
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitLeaveAccepted}
            >
              Confirm
            </Button>
          </>
        }
      >
        <FormGrid columns={2}>
          <Select
            label="Action"
            value={leaveDraft.mode}
            options={[
              {
                value: 'branch_minor_draft',
                label: 'Force new draft version (minor version bump)',
              },
              {
                value: 'rollback',
                label: 'Roll back to an earlier accepted version',
              },
            ]}
            onChange={(val) =>
              setLeaveDraft((cur) => ({...cur, mode: val}))
            }
          />
          {leaveDraft.mode === 'rollback' && (
            <TextField
              label="Target accepted version number"
              value={leaveDraft.targetVersion}
              onChange={(e) =>
                setLeaveDraft((cur) => ({
                  ...cur,
                  targetVersion: e.target.value,
                }))
              }
            />
          )}
          <Box sx={{gridColumn: '1 / -1'}}>
            <TextField
              label="Reason / note"
              value={leaveDraft.note}
              onChange={(e) =>
                setLeaveDraft((cur) => ({...cur, note: e.target.value}))
              }
            />
          </Box>
        </FormGrid>
      </Dialog>

      {/* Git Save / Load Modal */}
      <Dialog
        open={gitOpen}
        title="Git DDN synchronization"
        size="medium"
        onClose={() => !busyAction && setGitOpen(false)}
        busy={busyAction}
        defaultAction={submitGitOperation}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setGitOpen(false)}>
              Close
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitGitOperation}
            >
              {gitDraft.action === 'save' ? 'Save to Git' : 'Load from Git'}
            </Button>
          </>
        }
      >
        <Stack gap="standard">
          {gitStatus && <Banner status="success">{gitStatus}</Banner>}
          <FormGrid columns={2}>
            <Select
              label="Git operation"
              value={gitDraft.action}
              options={[
                {value: 'save', label: 'Save Cube DDN text to Git'},
                {value: 'load', label: 'Load Cube DDN text from Git'},
              ]}
              onChange={(val) =>
                setGitDraft((cur) => ({...cur, action: val}))
              }
            />
            <TextField
              label="Branch"
              value={gitDraft.branch}
              onChange={(e) =>
                setGitDraft((cur) => ({...cur, branch: e.target.value}))
              }
            />
            <TextField
              label="Git repository directory"
              required
              value={gitDraft.repository}
              onChange={(e) =>
                setGitDraft((cur) => ({...cur, repository: e.target.value}))
              }
            />
            <TextField
              label="Relative DDN file path (e.g. cubes/sales.ddn)"
              required
              value={gitDraft.path}
              onChange={(e) =>
                setGitDraft((cur) => ({...cur, path: e.target.value}))
              }
            />
            {gitDraft.action === 'save' && (
              <Box sx={{gridColumn: '1 / -1'}}>
                <Checkbox
                  label="Create Git commit after writing DDN file"
                  checked={gitDraft.commit}
                  onChange={(checked) =>
                    setGitDraft((cur) => ({...cur, commit: Boolean(checked)}))
                  }
                />
              </Box>
            )}
          </FormGrid>
        </Stack>
      </Dialog>
    </Box>
  );
}

CubeDesignerSurface.propTypes = {
  projectId: PropTypes.string.isRequired,
  designId: PropTypes.string.isRequired,
  client: PropTypes.object,
  controller: PropTypes.object,
  readOnly: PropTypes.bool,
  executeCommand: PropTypes.func,
  onStateChange: PropTypes.func,
  onExport: PropTypes.func,
  onError: PropTypes.func,
};
