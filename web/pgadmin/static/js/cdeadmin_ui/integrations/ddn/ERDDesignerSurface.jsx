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
import gettext from 'sources/gettext';
import {Box, ScrollArea, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Checkbox, Select} from '../../primitives/Choice';
import {TextArea, TextField} from '../../primitives/Field';
import {Dialog} from '../../overlays/Dialog';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import {StatusBadge} from '../../status/StatusBadge';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {t_actions} from '../../actions/t_actions';
import {DDNViewerSurface} from './DDNViewerSurface';
import {
  DesignCheckpointHistoryDrawer,
  DesignerElementNavigator,
  DesignerModalTabs,
  DesignerShellStatusBar,
  DesignerTabbedMenu,
  executeDesignerCommand,
  formatSavePointStatusLabel,
  FormGrid,
  KeyValuePairsEditor,
  TypedRowsEditor,
  useDesignerShellRegions,
  useDesignerWorkbenchEvents,
  WhereUsedDialog,
} from './DesignerChrome';
import {
  DesignStoreClient,
  SharedDDNTaskController,
} from './sharedDesignLibrary';

const LEVEL_CYCLE = Object.freeze([
  'all',
  'conceptual',
  'logical',
  'physical',
  'deployment',
]);

const UDT_SQL_TYPE_MAP = Object.freeze({
  uuidv7: {logical: 'uuid', physical: 'UUID'},
  'money-dec': {logical: 'decimal', physical: 'NUMERIC(19,4)'},
  'email-dom': {logical: 'string', physical: 'VARCHAR(320)'},
  'utc-ts': {logical: 'timestamptz', physical: 'TIMESTAMPTZ'},
  'json-doc': {logical: 'json', physical: 'JSONB'},
});

function getLevelOptions() {
  return [
    {value: 'all', label: gettext('All levels'), viewId: 'erd_all_levels'},
    {
      value: 'conceptual',
      label: gettext('Conceptual (Whiteboard)'),
      viewId: 'erd_conceptual',
    },
    {value: 'logical', label: gettext('Logical'), viewId: 'erd_logical'},
    {value: 'physical', label: gettext('Physical'), viewId: 'erd_physical'},
    {
      value: 'deployment',
      label: gettext('Deployment / System'),
      viewId: 'erd_deployment',
    },
  ];
}

function getInspectorLevelOptions() {
  return [
    {value: 'conceptual', label: gettext('Conceptual')},
    {value: 'logical', label: gettext('Logical')},
    {value: 'physical', label: gettext('Physical')},
    {value: 'deployment', label: gettext('Deployment')},
  ];
}

function getEngineOptions() {
  return [
    {value: 'postgresql', label: gettext('PostgreSQL')},
    {value: 'sqlite', label: gettext('SQLite')},
    {value: 'duckdb', label: gettext('DuckDB')},
    {value: 'firebird', label: gettext('Firebird 5')},
    {value: 'mysql', label: gettext('MySQL')},
    {value: 'mariadb', label: gettext('MariaDB')},
  ];
}

const LOGICAL_TYPE_OPTIONS = Object.freeze([
  {value: 'string', label: 'string'},
  {value: 'text', label: 'text'},
  {value: 'integer', label: 'integer'},
  {value: 'bigint', label: 'bigint'},
  {value: 'decimal', label: 'decimal'},
  {value: 'float', label: 'float'},
  {value: 'boolean', label: 'boolean'},
  {value: 'date', label: 'date'},
  {value: 'timestamptz', label: 'timestamptz'},
  {value: 'uuid', label: 'uuid'},
  {value: 'json', label: 'json'},
  {value: 'blob', label: 'blob'},
]);

const CASE_STYLE_OPTIONS = Object.freeze([
  {value: 'snake_case', label: 'snake_case'},
  {value: 'UPPER_SNAKE_CASE', label: 'UPPER_SNAKE_CASE'},
  {value: 'PascalCase', label: 'PascalCase'},
  {value: 'camelCase', label: 'camelCase'},
]);

function getMigrationFormatOptions() {
  return [
    {value: 'plain_sql', label: gettext('Plain Transactional SQL')},
    {value: 'flyway', label: gettext('Flyway (V{n}__{name}.sql)')},
    {value: 'liquibase', label: gettext('Liquibase Formatted SQL')},
    {value: 'atlas', label: gettext('Atlas Versioned SQL')},
  ];
}

function getBaselineModeOptions() {
  return [
    {value: 'active', label: gettext('Active Accepted Version')},
    {value: 'version', label: gettext('Specific Checkpoint')},
    {value: 'catalog', label: gettext('Live Catalog Baseline')},
  ];
}

function getTopologyActionOptions() {
  return [
    {value: 'relocate_replica', label: gettext('Relocate Replica')},
    {value: 'promote_failover', label: gettext('Promote Failover')},
    {value: 'provision_node', label: gettext('Provision Host / Instance')},
    {value: 'decommission_node', label: gettext('Decommission Node')},
  ];
}

const EMPTY_ERD_STATE = Object.freeze({
  look_handdrawn: false,
  conceptual_entities: [],
  conceptual_relations: [],
  conceptual_notes: [],
  logical_entities: [],
  logical_relations: [],
  physical_tables: [],
  deployment_nodes: [],
  deployment_links: [],
  level_links: [],
  extensions: {},
});

function resolveViewForLevel(workspace, level) {
  if (!workspace?.files) return workspace?.view || '';
  const target = getLevelOptions().find((opt) => opt.value === level)?.viewId;
  if (!target) return workspace.view;
  const entryText = workspace.files[workspace.entry] || '';
  if (
    entryText.includes(`view "${target}"`) ||
    entryText.includes(`view ${target}`)
  ) {
    return target;
  }
  return workspace.view;
}

function classifyClientFallbackRisks(diffs = [], targetEngine = 'sqlite') {
  const loses_data = [];
  const may_fail_on_existing_data = [];
  const breaks_running_clients = [];
  const locks_or_copies_table = [];
  for (const d of diffs) {
    const kind = String(d.change_kind || '');
    const stmt = String(d.statement || '').toUpperCase();
    if (kind === 'drop_table' || kind === 'drop_column') loses_data.push(d);
    if (
      kind === 'alter_column' ||
      kind === 'add_foreign_key' ||
      (kind === 'add_column' && stmt.includes('NOT NULL') && !stmt.includes('DEFAULT'))
    ) {
      may_fail_on_existing_data.push(d);
    }
    if (
      [
        'rename_table',
        'rename_column',
        'drop_table',
        'drop_column',
        'drop_foreign_key',
      ].includes(kind)
    ) {
      breaks_running_clients.push(d);
    }
    if (
      kind === 'alter_column' ||
      kind === 'add_foreign_key' ||
      (kind === 'drop_column' && targetEngine === 'sqlite')
    ) {
      locks_or_copies_table.push(d);
    }
  }
  return {
    categories: {
      loses_data,
      may_fail_on_existing_data,
      breaks_running_clients,
      locks_or_copies_table,
    },
    summary: {
      loses_data: loses_data.length,
      may_fail_on_existing_data: may_fail_on_existing_data.length,
      breaks_running_clients: breaks_running_clients.length,
      locks_or_copies_table: locks_or_copies_table.length,
      total_selected: diffs.length,
    },
  };
}

function listKeyForInspectorLevel(inspectorLevel) {
  if (inspectorLevel === 'conceptual') return 'conceptual_entities';
  if (inspectorLevel === 'logical') return 'logical_entities';
  if (inspectorLevel === 'deployment') return 'deployment_nodes';
  return 'physical_tables';
}

export function ERDDesignerSurface({
  projectId,
  designId,
  client: suppliedClient,
  controller: suppliedController,
  commands = t_actions,
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
        kind: 'erd',
      }),
    [suppliedController, client, projectId, designId]
  );

  const callbacks = useRef({executeCommand, onStateChange, onError});
  callbacks.current = {executeCommand, onStateChange, onError};
  const shellRegistryRef = useRef(null);
  const openPropertiesDrawerRef = useRef(() => {});
  const erdUndoStackRef = useRef([]);
  const erdRedoStackRef = useRef([]);
  const erdClipboardRef = useRef(null);

  const levelOptions = useMemo(() => getLevelOptions(), []);
  const inspectorLevelOptions = useMemo(() => getInspectorLevelOptions(), []);
  const engineOptions = useMemo(() => getEngineOptions(), []);
  const migrationFormatOptions = useMemo(() => getMigrationFormatOptions(), []);
  const baselineModeOptions = useMemo(() => getBaselineModeOptions(), []);
  const topologyActionOptions = useMemo(() => getTopologyActionOptions(), []);

  const [sessionState, setSessionState] = useState(() => controller.state());
  const [loading, setLoading] = useState(!sessionState.loaded);
  const [surfaceError, setSurfaceError] = useState('');
  const [surfaceNotice, setSurfaceNotice] = useState('');
  const [menuTab, setMenuTab] = useState('model');
  const [level, setLevel] = useState('all');
  const [busyAction, setBusyAction] = useState(false);
  const [canvasToolMode, setCanvasToolMode] = useState('pointer');

  // Structured 4-level ERD state + right-hand Property Inspector
  const [erdState, setErdState] = useState(EMPTY_ERD_STATE);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [inspectorLevel, setInspectorLevel] = useState('physical');
  const [selectedElementId, setSelectedElementId] = useState('');
  const [elementDraft, setElementDraft] = useState(null);

  const applyErdStateWithUndo = useCallback((updater) => {
    setErdState((cur) => {
      const next = typeof updater === 'function' ? updater(cur) : updater;
      if (next !== cur) {
        erdUndoStackRef.current.push(cur);
        erdRedoStackRef.current = [];
      }
      return next;
    });
  }, []);

  const handleUndoErd = useCallback(() => {
    if (readOnly || erdUndoStackRef.current.length === 0) return;
    const prev = erdUndoStackRef.current.pop();
    setErdState((cur) => {
      erdRedoStackRef.current.push(cur);
      return prev;
    });
    setSurfaceNotice(gettext('Reverted last ERD edit.'));
  }, [readOnly]);

  const handleRedoErd = useCallback(() => {
    if (readOnly || erdRedoStackRef.current.length === 0) return;
    const next = erdRedoStackRef.current.pop();
    setErdState((cur) => {
      erdUndoStackRef.current.push(cur);
      return next;
    });
    setSurfaceNotice(gettext('Restored ERD edit.'));
  }, [readOnly]);

  // Naming standards live summary badge + modal state (SR-F-030012)
  const [standardsOpen, setStandardsOpen] = useState(false);
  const [standardsTab, setStandardsTab] = useState('violations');
  const [standardsData, setStandardsData] = useState({
    violations: [],
    active_count: 0,
    waived_count: 0,
    rules: {
      table_case: 'snake_case',
      column_case: 'snake_case',
      pk_pattern: 'pk_{table}',
      fk_pattern: 'fk_{table}_{ref}',
      ix_pattern: 'ix_{table}_{cols}',
    },
    waivers: [],
  });

  // Save checkpoint modal
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveTab, setSaveTab] = useState('details');
  const [saveDraft, setSaveDraft] = useState({
    status: 'draft',
    note: '',
    ddnText: '',
  });

  // Accept version modal (A9)
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [acceptDraft, setAcceptDraft] = useState({
    requireGitReview: false,
    gitReviewRef: '',
    comment: '',
  });

  // Whiteboard quick-authoring modals (+ Connect Boxes, + Note) & Promotion Wizard (SR-F-030011)
  const [connectOpen, setConnectOpen] = useState(false);
  const [connectDraft, setConnectDraft] = useState({
    source: '',
    target: '',
    title: 'relates to',
  });
  const [noteOpen, setNoteOpen] = useState(false);
  const [noteDraft, setNoteDraft] = useState({
    title: 'Design Note',
    area: '',
    body: '',
  });
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [promoteTab, setPromoteTab] = useState('settings');
  const [promoteDraft, setPromoteDraft] = useState({
    targetEngine: 'postgresql',
    tableNaming: 'plural_snake',
    pkStyle: 'entity_id',
    pkType: 'bigint',
    includeAuditTimestamps: true,
    catalogRows: [],
  });
  const [promotePreview, setPromotePreview] = useState(null);

  // Engine Conversion modal (SR-F-030014, zero raw JSON textareas)
  const [convertOpen, setConvertOpen] = useState(false);
  const [convertTab, setConvertTab] = useState('engines');
  const [convertDraft, setConvertDraft] = useState({
    sourceEngine: 'firebird',
    targetEngine: 'sqlite',
    customTypeMap: {},
    lossChoices: {},
  });
  const [convertResult, setConvertResult] = useState(null);

  // Alter Plan, 4-Bucket Risk & Migration modal (SR-F-030013)
  const [alterOpen, setAlterOpen] = useState(false);
  const [alterTab, setAlterTab] = useState('risks');
  const [alterDraft, setAlterDraft] = useState({
    targetEngine: 'sqlite',
    baselineMode: 'active',
    baseVersion: 0,
    migrationFormat: 'plain_sql',
    environment: 'dev',
    endpointId: 'env-dev',
    approverPrincipal: '',
  });
  const [alterBundle, setAlterBundle] = useState(null);
  const [selectedDiffs, setSelectedDiffs] = useState([]);
  const [reviewReceipt, setReviewReceipt] = useState(null);

  // System Drift & Topology Change Review modal (SR-F-030014)
  const [driftOpen, setDriftOpen] = useState(false);
  const [driftTab, setDriftTab] = useState('topology');
  const [liveTopologyRows, setLiveTopologyRows] = useState([]);
  const [driftReport, setDriftReport] = useState(null);
  const [changeProposal, setChangeProposal] = useState(null);
  const [proposalDraft, setProposalDraft] = useState({
    elementId: '',
    action: 'relocate_replica',
    targetHost: '',
  });

  // Multi-Target Deployment Environment Matrix modal (SR-F-030014)
  const [envMatrixOpen, setEnvMatrixOpen] = useState(false);
  const [environments, setEnvironments] = useState([]);
  const [envReceipt, setEnvReceipt] = useState(null);

  // Git Sync, Checkpoint History & Where Used modals
  const [gitOpen, setGitOpen] = useState(false);
  const [gitDraft, setGitDraft] = useState({
    repository: '',
    path: `designs/${designId}.ddn`,
    branch: 'main',
    commit: false,
    note: '',
  });
  const [gitStatusInfo, setGitStatusInfo] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [whereUsedOpen, setWhereUsedOpen] = useState(false);
  const [whereUsedTarget, setWhereUsedTarget] = useState('');

  const refreshErdInsights = useCallback(
    async (versionArg = null) => {
      if (typeof client.inspectErdElements === 'function') {
        try {
          const inspected = await controller.inspectErdElements({
            version: versionArg,
          });
          if (inspected) {
            setErdState({
              ...EMPTY_ERD_STATE,
              ...inspected,
            });
          }
        } catch {
          // Non-fatal on minimal mock clients
        }
      }
      if (typeof client.evaluateErdStandards === 'function') {
        try {
          const std = await controller.evaluateErdStandards({action: 'check'});
          if (std) {
            setStandardsData((cur) => ({
              ...cur,
              ...std,
              rules: {...cur.rules, ...(std.rules || {})},
              waivers: std.waivers || cur.waivers || [],
            }));
          }
        } catch {
          // Non-fatal on minimal mock clients
        }
      }
    },
    [client, controller]
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
        setLoading(false);
        await refreshErdInsights(loaded.currentVersion);
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
  }, [controller, refreshErdInsights]);

  // Listen for provider context-menu Where Used shortcuts
  useEffect(() => {
    const onShortcut = (evt) => {
      const detail = evt?.detail || {};
      if (detail.design_shortcut === 'where_used') {
        setWhereUsedTarget(detail.targetRef || detail.endpointLabel || '');
        setWhereUsedOpen(true);
      }
    };
    window.addEventListener('cdeadmin:design-shortcut', onShortcut);
    return () =>
      window.removeEventListener('cdeadmin:design-shortcut', onShortcut);
  }, []);

  // Sync inspector level when user switches modelling level
  useEffect(() => {
    if (level !== 'all') {
      setInspectorLevel(level);
    }
  }, [level]);

  const fallbackPhysicalTables = useMemo(() => {
    const hasStructured =
      (erdState.conceptual_entities || []).length > 0 ||
      (erdState.logical_entities || []).length > 0 ||
      (erdState.physical_tables || []).length > 0 ||
      (erdState.deployment_nodes || []).length > 0;
    if (hasStructured) return erdState.physical_tables || [];
    const nodes = sessionState.layout?.nodes || [];
    return nodes.map((n, idx) => ({
      id: n.id || `layout-node-${idx + 1}`,
      name: n.name || n.label || n.id || `table_${idx + 1}`,
      schema: 'public',
      engine: 'postgresql',
      fields: [
        {name: 'id', datatype: 'BIGINT', pk: true, nullable: false, references: ''},
      ],
      indexes: [],
      foreign_keys: [],
    }));
  }, [erdState, sessionState.layout]);

  // Sync selected element draft when erdState or inspectorLevel changes
  const activeLevelItems = useMemo(() => {
    if (inspectorLevel === 'physical') {
      return (erdState.physical_tables || []).length > 0
        ? erdState.physical_tables
        : fallbackPhysicalTables;
    }
    const key = listKeyForInspectorLevel(inspectorLevel);
    return erdState[key] || [];
  }, [erdState, fallbackPhysicalTables, inspectorLevel]);

  useEffect(() => {
    if (!activeLevelItems.length) {
      setSelectedElementId('');
      setElementDraft(null);
      return;
    }
    const existing =
      activeLevelItems.find((it) => it.id === selectedElementId) ||
      activeLevelItems[0];
    if (existing.id !== selectedElementId) {
      setSelectedElementId(existing.id);
    }
    setElementDraft(hydrateElementDraft(inspectorLevel, existing));
  }, [activeLevelItems, inspectorLevel, selectedElementId]);

  const runToolbarCommand = useCallback(
    async (id, invoke) => {
      setSurfaceError('');
      try {
        return await executeDesignerCommand({
          commandId: id,
          invoke,
          executeCommand: callbacks.current.executeCommand,
          commands,
          shellRegistry: shellRegistryRef.current,
          enabled: true,
        });
      } catch (err) {
        setSurfaceError(err.message);
        callbacks.current.onError?.(err);
        return null;
      }
    },
    [commands]
  );

  // -------------------------------------------------------------------------
  // Authoring & Property Inspector actions
  // -------------------------------------------------------------------------

  const quickAddLevelElement = async (targetLevel, customName = null) => {
    setInspectorOpen(true);
    setInspectorLevel(targetLevel);
    openPropertiesDrawerRef.current?.();
    if (level !== 'all' && level !== targetLevel) {
      setLevel(targetLevel);
    }
    const key = listKeyForInspectorLevel(targetLevel);
    const existingList = erdState[key] || [];
    const idx = existingList.length + 1;
    if (typeof client.mutateErdElements !== 'function') {
      const fallbackDraft = {
        ...makeBlankElementDraft(targetLevel, idx),
        id: `local-${targetLevel}-${Date.now()}-${idx}`,
      };
      if (customName) fallbackDraft.name = customName;
      applyErdStateWithUndo((cur) => ({
        ...cur,
        [key]: [...(cur[key] || []), fallbackDraft],
      }));
      setSelectedElementId(fallbackDraft.id);
      setElementDraft(fallbackDraft);
      return;
    }
    setBusyAction(true);
    setSurfaceError('');
    try {
      let payload;
      if (targetLevel === 'conceptual') {
        payload = {
          operation: 'upsert_conceptual',
          entity: {name: customName || `Concept ${idx}`, area: 'Core'},
          note: `Added conceptual box ${customName || `Concept ${idx}`}`,
        };
      } else if (targetLevel === 'logical') {
        payload = {
          operation: 'upsert_logical',
          entity: {
            name: customName || `Entity${idx}`,
            fields: [{name: 'id', datatype: 'bigint', pk: true, nullable: false}],
          },
          note: `Added logical entity ${customName || `Entity${idx}`}`,
        };
      } else if (targetLevel === 'deployment') {
        payload = {
          operation: 'upsert_deployment_node',
          node: {
            name: customName || `db-node-${idx}`,
            engine: 'postgresql',
            role: 'primary',
            host: `db${idx}.internal`,
            location: 'us-east-1',
            tables: [],
          },
          note: `Added deployment node ${customName || `db-node-${idx}`}`,
        };
      } else {
        payload = {
          operation: 'upsert_physical_table',
          table: {
            name: customName || `table_${idx}`,
            schema: 'public',
            engine: 'postgresql',
            fields: [
              {
                name: 'id',
                datatype: 'BIGINT',
                pk: true,
                nullable: false,
              },
            ],
            indexes: [],
            foreign_keys: [],
          },
          note: `Added physical table ${customName || `table_${idx}`}`,
        };
      }
      const res = await controller.mutateErdElements(payload);
      if (res?.elements) {
        applyErdStateWithUndo({...EMPTY_ERD_STATE, ...res.elements});
        const items = res.elements[key] || [];
        if (items.length) {
          setSelectedElementId(items[items.length - 1].id);
        }
      } else {
        await refreshErdInsights();
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const toggleSketchLook = async () => {
    const nextVal = !erdState.look_handdrawn;
    applyErdStateWithUndo((cur) => ({...cur, look_handdrawn: nextVal}));
    if (typeof client.mutateErdElements !== 'function') return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.mutateErdElements({
        operation: 'set_sketch_look',
        look_handdrawn: nextVal,
        note: nextVal
          ? 'Enabled whiteboard hand-drawn sketch look'
          : 'Switched to crisp technical ERD look',
      });
      if (res?.elements) {
        setErdState({...EMPTY_ERD_STATE, ...res.elements});
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const saveInspectorChanges = async () => {
    if (!elementDraft) return;
    if (typeof client.mutateErdElements !== 'function') {
      const key = listKeyForInspectorLevel(inspectorLevel);
      applyErdStateWithUndo((cur) => {
        const currentList = cur[key] || [];
        const exists = currentList.some((item) => item.id === elementDraft.id);
        const nextList = exists
          ? currentList.map((item) =>
            item.id === elementDraft.id ? {...item, ...elementDraft} : item
          )
          : [...currentList, {...elementDraft, id: elementDraft.id || `el-${Date.now()}`}];
        return {...cur, [key]: nextList};
      });
      setSurfaceNotice(gettext('Saved element changes in local session.'));
      return;
    }
    setBusyAction(true);
    setSurfaceError('');
    try {
      const payload = serializeElementDraftPayload(inspectorLevel, elementDraft);
      const res = await controller.mutateErdElements(payload);
      if (res?.elements) {
        applyErdStateWithUndo({...EMPTY_ERD_STATE, ...res.elements});
      }
      await refreshErdInsights();
      setSurfaceNotice(
        gettext('Saved %s element "%s".', inspectorLevel, elementDraft.name)
      );
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const deleteSelectedInspectorElement = async () => {
    if (!selectedElementId) return;
    if (typeof client.mutateErdElements !== 'function') {
      const key = listKeyForInspectorLevel(inspectorLevel);
      applyErdStateWithUndo((cur) => ({
        ...cur,
        [key]: (cur[key] || []).filter((item) => item.id !== selectedElementId),
      }));
      return;
    }
    setBusyAction(true);
    setSurfaceError('');
    try {
      const opMap = {
        conceptual: 'delete_conceptual',
        logical: 'delete_logical',
        physical: 'delete_physical_table',
        deployment: 'delete_deployment_node',
      };
      const res = await controller.mutateErdElements({
        operation: opMap[inspectorLevel] || 'delete_physical_table',
        id: selectedElementId,
        note: `Removed ${inspectorLevel} element`,
      });
      if (res?.elements) {
        applyErdStateWithUndo({...EMPTY_ERD_STATE, ...res.elements});
      }
      await refreshErdInsights();
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const submitConnectBoxes = async () => {
    if (!connectDraft.source || !connectDraft.target) {
      setSurfaceError(gettext('Choose both source and target conceptual boxes.'));
      return;
    }
    if (typeof client.mutateErdElements !== 'function') {
      applyErdStateWithUndo((cur) => ({
        ...cur,
        conceptual_relations: [
          ...(cur.conceptual_relations || []),
          {
            id: `rel-${Date.now()}`,
            source: connectDraft.source,
            target: connectDraft.target,
            title: connectDraft.title || 'relates to',
          },
        ],
      }));
      setConnectOpen(false);
      return;
    }
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.mutateErdElements({
        operation: 'connect_conceptual',
        relation: {
          source: connectDraft.source,
          target: connectDraft.target,
          title: connectDraft.title || 'relates to',
        },
        note: 'Connected conceptual whiteboard boxes',
      });
      if (res?.elements) {
        applyErdStateWithUndo({...EMPTY_ERD_STATE, ...res.elements});
      }
      setConnectOpen(false);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const submitAddNote = async () => {
    if (!noteDraft.body.trim() && !noteDraft.title.trim()) {
      setSurfaceError(gettext('Enter a whiteboard note title or body.'));
      return;
    }
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.mutateErdElements({
        operation: 'upsert_conceptual_note',
        note_item: {
          title: noteDraft.title.trim() || 'Note',
          area: noteDraft.area.trim(),
          body: noteDraft.body.trim(),
        },
        note: 'Added conceptual whiteboard note',
      });
      if (res?.elements) {
        setErdState({...EMPTY_ERD_STATE, ...res.elements});
      }
      setNoteOpen(false);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  // -------------------------------------------------------------------------
  // Save / Status / Export / Layout actions
  // -------------------------------------------------------------------------

  const openSaveDialog = useCallback(() => {
    const ws = sessionState.workspace;
    const entryText = ws?.files?.[ws.entry] || '';
    setSaveDraft({
      status:
        sessionState.status === 'accepted'
          ? 'draft'
          : sessionState.status || 'draft',
      note: '',
      ddnText: entryText,
    });
    setSaveTab('details');
    setSaveOpen(true);
  }, [sessionState]);

  const submitSave = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      await controller.save({
        ddnOrWorkspace: saveDraft.ddnText,
        status: saveDraft.status,
        note: saveDraft.note,
        allowConflictNote: true,
      });
      await refreshErdInsights();
      setSaveOpen(false);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const submitAccept = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      await controller.accept({
        requireGitReview: acceptDraft.requireGitReview,
        gitReviewRef: acceptDraft.gitReviewRef.trim() || null,
        comment: acceptDraft.comment,
      });
      await refreshErdInsights();
      setAcceptOpen(false);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const handleExportDdn = () => {
    const ws = sessionState.workspace;
    const ddnText = ws?.files?.[ws.entry] || '';
    onExport?.(ddnText, {
      format: 'ddn',
      designId,
      version: sessionState.currentVersion,
    });
    setSurfaceNotice('Exported DDN document from active workspace.');
  };

  const handlePinSelected = () => {
    const nodes = sessionState.layout?.nodes || [];
    const match =
      nodes.find((n) => n.id === selectedElementId) || nodes[0] || null;
    if (!match) return;
    controller.pinNode(match.id, match.x ?? 64, match.y ?? 64, true);
    setSurfaceNotice(`Pinned node "${match.name || match.id}" at (${match.x ?? 64}, ${match.y ?? 64}).`);
  };

  const handleUnpinAll = () => {
    const pins = sessionState.pinnedPositions || {};
    for (const nodeId of Object.keys(pins)) {
      controller.pinNode(nodeId, pins[nodeId].x ?? 0, pins[nodeId].y ?? 0, false);
    }
    setSurfaceNotice('Cleared local node layout pins.');
  };

  // -------------------------------------------------------------------------
  // Whiteboard Promotion ("Make it a design...", SR-F-030011)
  // -------------------------------------------------------------------------

  const runPromoteWhiteboard = async (saveVersion) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const catalogTables = promoteDraft.catalogRows
        .filter((r) => String(r.name || '').trim())
        .map((r) => ({
          name: String(r.name).trim(),
          columns: [
            {
              name: String(r.pk_column || 'id').trim(),
              type: String(r.pk_type || 'BIGINT').trim(),
              pk: true,
              nullable: false,
            },
          ],
        }));
      const res = await controller.promoteErdWhiteboard({
        target_engine: promoteDraft.targetEngine,
        table_naming: promoteDraft.tableNaming,
        pk_style: promoteDraft.pkStyle,
        pk_type: promoteDraft.pkType,
        include_audit_timestamps: promoteDraft.includeAuditTimestamps,
        catalog_tables: catalogTables,
        save_version: saveVersion,
      });
      setPromotePreview(res);
      setPromoteTab('preview');
      if (saveVersion) {
        await refreshErdInsights();
        setSurfaceNotice(
          `Promoted ${res.promoted_physical_count || 0} table(s) to Logical + Physical design.`
        );
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  // -------------------------------------------------------------------------
  // Naming Standards, Auto-Fix & Waivers (SR-F-030012)
  // -------------------------------------------------------------------------

  const openStandardsDialog = async () => {
    setStandardsOpen(true);
    setStandardsTab('violations');
    if (typeof client.evaluateErdStandards !== 'function') return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.evaluateErdStandards({
        action: 'check',
        rules: standardsData.rules,
      });
      setStandardsData((cur) => ({
        ...cur,
        ...res,
        rules: {...cur.rules, ...(res.rules || {})},
        waivers: res.waivers || cur.waivers || [],
      }));
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const runStandardsAction = async (action, extra = {}) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.evaluateErdStandards({
        action,
        rules: standardsData.rules,
        waivers: standardsData.waivers,
        ...extra,
      });
      setStandardsData((cur) => ({
        ...cur,
        ...res,
        rules: {...cur.rules, ...(res.rules || {})},
        waivers: res.waivers || cur.waivers || [],
      }));
      if (action === 'apply_fixes' || action === 'save_waivers') {
        await refreshErdInsights();
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const quickWaiveViolation = async (violation) => {
    const nextWaivers = [
      ...(standardsData.waivers || []),
      {
        rule_id: violation.rule,
        target: violation.target,
        reason: 'Approved domain naming exception',
        waived_by: 'designer',
      },
    ];
    setStandardsData((cur) => ({...cur, waivers: nextWaivers}));
    await runStandardsAction('save_waivers', {waivers: nextWaivers});
  };

  // -------------------------------------------------------------------------
  // Engine Conversion (SR-F-030014, zero raw JSON textareas, zero 409 conflict)
  // -------------------------------------------------------------------------

  const runEngineConversion = async (saveConverted) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const customMapPayload = Object.keys(convertDraft.customTypeMap).length
        ? Object.fromEntries(
          Object.entries(convertDraft.customTypeMap).map(([k, v]) => [
            k,
            typeof v === 'object' && v !== null ? v : {physical: String(v), exact: true},
          ])
        )
        : null;
      const lossPayload = Object.keys(convertDraft.lossChoices).length
        ? convertDraft.lossChoices
        : null;

      // Always compute converted DDN cleanly first (saveVersion: false avoids 409 on active_version mismatch)
      const preview = await controller.convertErdEngine({
        sourceEngine: convertDraft.sourceEngine,
        targetEngine: convertDraft.targetEngine,
        customTypeMap: customMapPayload,
        lossChoices: lossPayload,
        strict: true,
        saveVersion: false,
      });
      setConvertResult(preview);
      setConvertTab('preview');

      if (saveConverted) {
        if (preview?.ddn_text && typeof client.saveVersion === 'function') {
          await controller.save({
            ddnOrWorkspace: preview.ddn_text,
            status: 'draft',
            note: `Converted ERD from ${convertDraft.sourceEngine} to ${convertDraft.targetEngine}`,
            allowConflictNote: true,
          });
        } else {
          await controller.convertErdEngine({
            sourceEngine: convertDraft.sourceEngine,
            targetEngine: convertDraft.targetEngine,
            customTypeMap: customMapPayload,
            lossChoices: lossPayload,
            strict: true,
            saveVersion: true,
          });
        }
        await refreshErdInsights();
        setSurfaceNotice(
          `Saved converted ${convertDraft.targetEngine} checkpoint.`
        );
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  // -------------------------------------------------------------------------
  // Alter Plan, 4-Bucket Risk & Migration Review (SR-F-030013)
  // -------------------------------------------------------------------------

  const loadAlterPlan = useCallback(
    async (overrides = {}, explicitDiffIds = undefined) => {
      const nextCfg = {...alterDraft, ...overrides};
      setBusyAction(true);
      setSurfaceError('');
      try {
        if (typeof client.deployErdPlan === 'function') {
          const bundle = await controller.deployErdPlan({
            action: 'preview',
            target_engine: nextCfg.targetEngine,
            baseline_mode: nextCfg.baselineMode,
            base_version:
              nextCfg.baselineMode === 'version'
                ? Number(nextCfg.baseVersion || 0)
                : undefined,
            migration_format: nextCfg.migrationFormat,
            selected_difference_ids:
              explicitDiffIds === undefined ? undefined : explicitDiffIds,
          });
          setAlterBundle(bundle);
          setSelectedDiffs(bundle.plan?.selected_difference_ids || []);
          if (Array.isArray(bundle.environments)) {
            setEnvironments(bundle.environments);
          }
        } else {
          const plan = await controller.previewErdAlterPlan({
            targetEngine: nextCfg.targetEngine,
            selectedDifferenceIds:
              explicitDiffIds === undefined ? null : explicitDiffIds,
          });
          const chosenIds = plan.selected_difference_ids || [];
          const chosenDiffs = (plan.differences || []).filter((d) =>
            chosenIds.includes(d.difference_id)
          );
          const {categories, summary} = classifyClientFallbackRisks(
            chosenDiffs,
            nextCfg.targetEngine
          );
          setAlterBundle({
            plan,
            baseline_mode: nextCfg.baselineMode,
            risk_categories: categories,
            risk_summary: summary,
            migration_format: nextCfg.migrationFormat,
            migration_sql: plan.script || '',
            migration_scripts: {
              plain_sql: plan.script || '',
              flyway: `-- Flyway Migration\n${plan.script || ''}`,
              liquibase: `--liquibase formatted sql\n${plan.script || ''}`,
              atlas: `-- Atlas Migration\n${plan.script || ''}`,
            },
            environments: [],
          });
          setSelectedDiffs(chosenIds);
        }
      } catch (err) {
        setSurfaceError(err.message);
      } finally {
        setBusyAction(false);
      }
    },
    [alterDraft, client, controller]
  );

  const openAlterDialog = useCallback(() => {
    setReviewReceipt(null);
    setAlterTab('risks');
    setAlterOpen(true);
    loadAlterPlan({}, undefined);
  }, [loadAlterPlan]);

  const toggleDifference = (diffId, checked) => {
    const next = checked
      ? [...new Set([...selectedDiffs, diffId])]
      : selectedDiffs.filter((id) => id !== diffId);
    setSelectedDiffs(next);
    loadAlterPlan({}, next);
  };

  const submitAlterToOperationReview = async (targetEnv = null) => {
    if (typeof client.deployErdPlan !== 'function') return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const envName = targetEnv || alterDraft.environment || 'dev';
      const approvers = alterDraft.approverPrincipal.trim()
        ? [alterDraft.approverPrincipal.trim()]
        : [];
      const receipt = await controller.deployErdPlan({
        action: 'submit_review',
        environment: envName,
        endpoint_id: targetEnv ? `env-${targetEnv}` : alterDraft.endpointId,
        target_engine: alterDraft.targetEngine,
        baseline_mode: alterDraft.baselineMode,
        migration_format: alterDraft.migrationFormat,
        selected_difference_ids: selectedDiffs,
        approvers,
      });
      setReviewReceipt(receipt);
      setEnvReceipt(receipt);
      if (Array.isArray(receipt?.environments) && receipt.environments.length > 0) {
        setEnvironments(receipt.environments);
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  // -------------------------------------------------------------------------
  // System Drift & Environment Matrix (SR-F-030014)
  // -------------------------------------------------------------------------

  const evaluateSystemDrift = useCallback(
    async (rows = liveTopologyRows) => {
      setBusyAction(true);
      setSurfaceError('');
      try {
        const liveNodes = rows
          .filter((r) => r.id || r.host)
          .map((r) => ({
            id: r.id,
            name: r.id || r.host,
            host: r.host,
            engine: r.engine || 'postgresql',
            role: r.role || 'primary',
            status: r.status || 'online',
          }));
        const report = await controller.computeErdDrift({liveNodes});
        setDriftReport(report);
        const firstNode =
          erdState.deployment_nodes?.[0]?.id ||
          sessionState.layout?.nodes?.[0]?.id ||
          '';
        setProposalDraft((cur) => ({
          ...cur,
          elementId: cur.elementId || firstNode,
        }));
      } catch (err) {
        setSurfaceError(err.message);
      } finally {
        setBusyAction(false);
      }
    },
    [controller, erdState.deployment_nodes, liveTopologyRows, sessionState.layout]
  );

  const openDriftDialog = useCallback(() => {
    setDriftOpen(true);
    setDriftTab('topology');
    setChangeProposal(null);
    evaluateSystemDrift(liveTopologyRows);
  }, [evaluateSystemDrift, liveTopologyRows]);

  const submitDiagramProposal = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const proposal = await controller.proposeErdDiagramChange({
        elementId: proposalDraft.elementId,
        action: proposalDraft.action,
        parameters: proposalDraft.targetHost
          ? {target_host: proposalDraft.targetHost}
          : {},
      });
      setChangeProposal(proposal);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const openEnvironmentMatrix = async () => {
    setEnvReceipt(null);
    setEnvMatrixOpen(true);
    if (typeof client.deployErdPlan !== 'function') return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.deployErdPlan({
        action: 'preview',
        target_engine: alterDraft.targetEngine,
      });
      if (Array.isArray(res?.environments) && res.environments.length > 0) {
        setEnvironments(res.environments);
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const recordVerifiedDeployment = async (envRow) => {
    if (typeof client.deployErdPlan !== 'function') return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.deployErdPlan({
        action: 'record_environment_deployment',
        environment: envRow.environment,
        endpoint_id: envRow.endpoint_id,
        database_target_id: envRow.database_target_id,
        deployed_version: sessionState.currentVersion,
        target_engine: envRow.engine || alterDraft.targetEngine,
      });
      if (Array.isArray(res?.environments) && res.environments.length > 0) {
        setEnvironments(res.environments);
      }
      setSurfaceNotice(
        `Recorded verified v${sessionState.currentVersion} deployment on ${envRow.label}.`
      );
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  // -------------------------------------------------------------------------
  // Git Sync Operations
  // -------------------------------------------------------------------------

  const runGitAction = async (action) => {
    if (typeof client.gitOperation !== 'function') return;
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.gitOperation({
        action,
        repository: gitDraft.repository,
        repoRoot: gitDraft.repository,
        path: gitDraft.path,
        branch: gitDraft.branch,
        commit: gitDraft.commit,
        note: gitDraft.note,
      });
      setGitStatusInfo(res);
      if (action === 'load') {
        await refreshErdInsights();
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  // -------------------------------------------------------------------------
  // Derived UI state & 5-Tab DesignerTabbedMenu definition
  // -------------------------------------------------------------------------

  const suspectBindings = useMemo(
    () =>
      (sessionState.bindings || []).filter((item) => item.state === 'suspect'),
    [sessionState.bindings]
  );

  const activeView = useMemo(
    () => resolveViewForLevel(sessionState.workspace, level),
    [sessionState.workspace, level]
  );

  const menuTabs = useMemo(
    () => [
      {
        id: 'model',
        label: gettext('Model'),
        groups: [
          {
            id: 'save',
            label: gettext('Save Draft'),
            items: [
              {
                id: 'erd.menu.save',
                actionId: 'erd.designer.save',
                label: gettext('Save Checkpoint'),
                intent: 'primary',
                disabled: readOnly || !sessionState.loaded,
                onClick: () =>
                  runToolbarCommand('erd.designer.save', openSaveDialog),
              },
            ],
          },
          {
            id: 'status',
            label: gettext('Status'),
            items: [
              {
                id: 'erd.menu.in_progress',
                label: gettext('Advance to In Progress'),
                disabled:
                  readOnly ||
                  !sessionState.loaded ||
                  sessionState.status !== 'draft',
                onClick: () => controller.advanceStatus('in_progress'),
              },
              {
                id: 'erd.menu.in_review',
                label: gettext('Submit for Review'),
                disabled:
                  readOnly ||
                  !sessionState.loaded ||
                  sessionState.status === 'accepted' ||
                  sessionState.status === 'in_review',
                onClick: () => controller.advanceStatus('in_review'),
              },
              {
                id: 'erd.menu.accept',
                actionId: 'erd.designer.accept',
                label: gettext('Accept'),
                disabled: readOnly || !sessionState.loaded,
                onClick: () =>
                  runToolbarCommand('erd.designer.accept', () =>
                    setAcceptOpen(true)
                  ),
              },
              {
                id: 'erd.menu.branch_draft',
                label: gettext('Branch Draft'),
                disabled:
                  readOnly ||
                  !sessionState.loaded ||
                  !sessionState.activeVersion,
                onClick: () =>
                  controller.branchDraft({
                    note: gettext('Branched draft from active'),
                  }),
              },
            ],
          },
          {
            id: 'history_git',
            label: gettext('History & Git'),
            items: [
              {
                id: 'erd.menu.checkpoints',
                label: gettext('Checkpoints & Diff…'),
                disabled: !sessionState.loaded,
                onClick: () => setHistoryOpen(true),
              },
              {
                id: 'erd.menu.git',
                label: gettext('Git Sync…'),
                disabled: !sessionState.loaded,
                onClick: () => setGitOpen(true),
              },
              {
                id: 'erd.menu.export',
                label: gettext('Export DDN'),
                disabled: !sessionState.loaded,
                onClick: handleExportDdn,
              },
              {
                id: 'erd.menu.where_used',
                label: gettext('Where Used…'),
                disabled: !sessionState.loaded,
                onClick: () => {
                  setWhereUsedTarget('');
                  setWhereUsedOpen(true);
                },
              },
            ],
          },
        ],
      },
      {
        id: 'author',
        label: gettext('Author & Whiteboard'),
        groups: [
          {
            id: 'whiteboard_sketch',
            label: gettext('Whiteboard Sketch'),
            items: [
              {
                id: 'erd.menu.add_conceptual',
                label: gettext('+ Conceptual Box'),
                disabled: readOnly || !sessionState.loaded,
                onClick: () => quickAddLevelElement('conceptual'),
              },
              {
                id: 'erd.menu.connect_boxes',
                label: gettext('+ Connect Boxes'),
                disabled:
                  readOnly ||
                  !sessionState.loaded ||
                  erdState.conceptual_entities.length < 2,
                onClick: () => {
                  setConnectDraft({
                    source: erdState.conceptual_entities[0]?.id || '',
                    target: erdState.conceptual_entities[1]?.id || '',
                    title: 'relates to',
                  });
                  setConnectOpen(true);
                },
              },
              {
                id: 'erd.menu.add_note',
                label: gettext('+ Note'),
                disabled: readOnly || !sessionState.loaded,
                onClick: () => {
                  setNoteDraft({
                    title: gettext('Whiteboard Note'),
                    area: '',
                    body: '',
                  });
                  setNoteOpen(true);
                },
              },
              {
                id: 'erd.menu.sketch_look',
                label: gettext('Sketch Look'),
                active: Boolean(erdState.look_handdrawn),
                disabled: readOnly || !sessionState.loaded,
                onClick: toggleSketchLook,
              },
              {
                id: 'erd.menu.promote_whiteboard',
                label: gettext('Make it a design…'),
                intent: 'primary',
                disabled: readOnly || !sessionState.loaded,
                onClick: () => {
                  setPromotePreview(null);
                  setPromoteTab('settings');
                  setPromoteOpen(true);
                },
              },
            ],
          },
          {
            id: 'structured_levels',
            label: gettext('Structured Levels'),
            items: [
              {
                id: 'erd.menu.add_logical',
                label: gettext('+ Logical Entity'),
                disabled: readOnly || !sessionState.loaded,
                onClick: () => quickAddLevelElement('logical'),
              },
              {
                id: 'erd.menu.add_physical',
                label: gettext('+ Physical Table'),
                disabled: readOnly || !sessionState.loaded,
                onClick: () => quickAddLevelElement('physical'),
              },
              {
                id: 'erd.menu.add_deployment',
                label: gettext('+ Deployment Node'),
                disabled: readOnly || !sessionState.loaded,
                onClick: () => quickAddLevelElement('deployment'),
              },
              {
                id: 'erd.menu.toggle_inspector',
                label: gettext('Toggle Inspector'),
                active: inspectorOpen,
                onClick: () => {
                  setInspectorOpen((v) => !v);
                  openPropertiesDrawerRef.current?.();
                },
              },
            ],
          },
        ],
      },
      {
        id: 'levels',
        label: gettext('Levels & Layout'),
        groups: [
          {
            id: 'level_switcher',
            label: gettext('Modelling Level'),
            items: [
              {
                id: 'erd.level.all',
                label: gettext('All Levels'),
                active: level === 'all',
                onClick: () => setLevel('all'),
              },
              {
                id: 'erd.level.conceptual',
                label: gettext('Conceptual'),
                active: level === 'conceptual',
                onClick: () => setLevel('conceptual'),
              },
              {
                id: 'erd.level.logical',
                label: gettext('Logical'),
                active: level === 'logical',
                onClick: () => setLevel('logical'),
              },
              {
                id: 'erd.level.physical',
                label: gettext('Physical'),
                active: level === 'physical',
                onClick: () => setLevel('physical'),
              },
              {
                id: 'erd.level.deployment',
                label: gettext('Deployment'),
                active: level === 'deployment',
                onClick: () => setLevel('deployment'),
              },
            ],
          },
          {
            id: 'layout_pins',
            label: gettext('Layered Layout & Pins'),
            items: [
              {
                id: 'erd.layout.recompute',
                label: gettext('Recompute Layered Layout'),
                disabled: !sessionState.loaded,
                onClick: () =>
                  controller.load({version: sessionState.currentVersion}),
              },
              {
                id: 'erd.layout.pin',
                label: gettext('Pin Selected / Unpin All'),
                disabled: !sessionState.loaded,
                onClick: () => {
                  const hasPins =
                    Object.values(sessionState.pinnedPositions || {}).some(
                      (p) => p?.pinned
                    );
                  if (hasPins) handleUnpinAll();
                  else handlePinSelected();
                },
              },
            ],
          },
        ],
      },
      {
        id: 'validate',
        label: gettext('Validate & Standards'),
        attention:
          standardsData.active_count > 0 || suspectBindings.length > 0,
        groups: [
          {
            id: 'standards_group',
            label: gettext('Standards & Bindings'),
            items: [
              {
                id: 'erd.menu.standards',
                label: gettext('Naming Standards…'),
                badge: standardsData.active_count,
                disabled: !sessionState.loaded,
                onClick: openStandardsDialog,
              },
              {
                id: 'erd.menu.suspect_bindings',
                label: gettext('Suspect Bindings'),
                badge: suspectBindings.length,
                disabled: !sessionState.loaded,
                onClick: () => {
                  if (suspectBindings.length === 0) {
                    setSurfaceNotice(gettext('All catalog bindings are valid.'));
                  }
                },
              },
              {
                id: 'erd.menu.refresh',
                label: gettext('Refresh Session'),
                disabled: !sessionState.loaded,
                onClick: async () => {
                  const next = await controller.load({
                    version: sessionState.currentVersion,
                  });
                  await refreshErdInsights(next.currentVersion);
                },
              },
            ],
          },
        ],
      },
      {
        id: 'deploy',
        label: gettext('Compare & Deploy'),
        groups: [
          {
            id: 'compare_convert',
            label: gettext('Conversion & Schema Plan'),
            items: [
              {
                id: 'erd.menu.convert',
                actionId: 'erd.designer.convert',
                label: gettext('Engine Conversion…'),
                disabled: !sessionState.loaded,
                onClick: () =>
                  runToolbarCommand('erd.designer.convert', () => {
                    setConvertResult(null);
                    setConvertTab('engines');
                    setConvertOpen(true);
                  }),
              },
              {
                id: 'erd.menu.alter_plan',
                actionId: 'erd.designer.alter_plan',
                label: gettext('Alter Plan & Migration…'),
                intent: 'primary',
                disabled: !sessionState.loaded,
                onClick: () =>
                  runToolbarCommand(
                    'erd.designer.alter_plan',
                    openAlterDialog
                  ),
              },
            ],
          },
          {
            id: 'topology_envs',
            label: gettext('Topology & Environments'),
            items: [
              {
                id: 'erd.menu.drift',
                label: gettext('System Drift…'),
                disabled: !sessionState.loaded,
                onClick: openDriftDialog,
              },
              {
                id: 'erd.menu.env_matrix',
                label: gettext('Environment Matrix (Dev/Stage/Prod)…'),
                disabled: !sessionState.loaded,
                onClick: openEnvironmentMatrix,
              },
            ],
          },
        ],
      },
    ],
    [
      controller,
      erdState.conceptual_entities,
      erdState.look_handdrawn,
      inspectorOpen,
      level,
      openAlterDialog,
      openDriftDialog,
      openSaveDialog,
      readOnly,
      refreshErdInsights,
      runToolbarCommand,
      sessionState,
      standardsData.active_count,
      suspectBindings.length,
    ]
  );

  const selectNavigatorElement = useCallback((targetLvl, itemId) => {
    setInspectorLevel(targetLvl);
    setSelectedElementId(itemId);
    setInspectorOpen(true);
    openPropertiesDrawerRef.current?.();
  }, []);

  const erdNavigatorSections = useMemo(() => {
    const entityItems = [
      ...(erdState.conceptual_entities || []).map((c) => ({
        id: c.id,
        label: c.name || c.id,
        sublabel: gettext('Conceptual'),
        active: inspectorLevel === 'conceptual' && selectedElementId === c.id,
        onSelect: () => selectNavigatorElement('conceptual', c.id),
      })),
      ...(erdState.logical_entities || []).map((e) => ({
        id: e.id,
        label: e.name || e.id,
        sublabel: gettext('Logical'),
        active: inspectorLevel === 'logical' && selectedElementId === e.id,
        onSelect: () => selectNavigatorElement('logical', e.id),
      })),
    ];

    const physTables =
      (erdState.physical_tables || []).length > 0
        ? erdState.physical_tables
        : fallbackPhysicalTables;
    const tableItems = [
      ...physTables.map((t) => ({
        id: t.id,
        label: t.name || t.id,
        sublabel: t.engine || gettext('Physical'),
        active: inspectorLevel === 'physical' && selectedElementId === t.id,
        onSelect: () => selectNavigatorElement('physical', t.id),
      })),
      ...(erdState.deployment_nodes || []).map((n) => ({
        id: n.id,
        label: n.name || n.id,
        sublabel: n.role || gettext('Node'),
        active: inspectorLevel === 'deployment' && selectedElementId === n.id,
        onSelect: () => selectNavigatorElement('deployment', n.id),
      })),
    ];

    const relItems = [
      ...(erdState.conceptual_relations || []).map((r, i) => ({
        id: r.id || `crel-${i}`,
        label: `${r.source} -> ${r.target}`,
        sublabel: r.title || gettext('Conceptual'),
        active: false,
        onSelect: () => selectNavigatorElement('conceptual', r.source),
      })),
      ...(erdState.logical_relations || []).map((r, i) => ({
        id: r.id || `lrel-${i}`,
        label: `${r.source} -> ${r.target}`,
        sublabel: gettext('Logical'),
        active: false,
        onSelect: () => selectNavigatorElement('logical', r.source),
      })),
      ...physTables.flatMap((t) =>
        (t.foreign_keys || []).map((fk, idx) => ({
          id: `${t.id}-fk-${idx}`,
          label: `${t.name} -> ${fk.ref_table}`,
          sublabel: gettext('FK'),
          active: false,
          onSelect: () => selectNavigatorElement('physical', t.id),
        }))
      ),
    ];

    return [
      {
        id: 'entities',
        label: gettext('Entities'),
        emptyText: gettext('No conceptual or logical entities.'),
        items: entityItems,
      },
      {
        id: 'tables',
        label: gettext('Tables'),
        emptyText: gettext('No physical tables or nodes.'),
        items: tableItems,
      },
      {
        id: 'relationships',
        label: gettext('Relationships'),
        emptyText: gettext('No relationships defined.'),
        items: relItems,
      },
    ];
  }, [
    erdState,
    fallbackPhysicalTables,
    inspectorLevel,
    selectNavigatorElement,
    selectedElementId,
  ]);

  const erdNavigatorNode = useMemo(
    () => (
      <DesignerElementNavigator
        title={gettext('ERD Model Navigator')}
        sections={erdNavigatorSections}
      />
    ),
    [erdNavigatorSections]
  );

  const erdTitle =
    sessionState.title ||
    sessionState.design?.title ||
    sessionState.design?.name ||
    designId ||
    gettext('ERD Design');
  const primaryEngine =
    erdState.physical_tables?.[0]?.engine ||
    erdState.deployment_nodes?.[0]?.engine ||
    alterDraft.targetEngine ||
    'postgresql';

  const erdStatusNode = useMemo(
    () => (
      <DesignerShellStatusBar
        title={erdTitle}
        version={sessionState.currentVersion}
        status={sessionState.status}
        engine={primaryEngine}
        suspectCount={suspectBindings.length}
        extra={
          erdState.look_handdrawn ? (
            <StatusBadge status="info" label={gettext('Sketch Look')} />
          ) : null
        }
      />
    ),
    [
      erdState.look_handdrawn,
      erdTitle,
      primaryEngine,
      sessionState.currentVersion,
      sessionState.status,
      suspectBindings.length,
    ]
  );

  const erdStatusText = `${erdTitle} · v${sessionState.currentVersion || 1} · ${formatSavePointStatusLabel(
    sessionState.status
  )} · ${primaryEngine} · ${
    suspectBindings.length > 0
      ? `${suspectBindings.length} ${gettext('suspect')}`
      : gettext('valid')
  }`;

  const renderErdInspectorBody = (standalone = false) => (
    <Box
      component={standalone ? 'aside' : 'section'}
      aria-label={gettext('ERD element property inspector')}
      data-testid="erd-property-inspector"
      sx={
        standalone
          ? {
            width: 320,
            flexShrink: 0,
            borderLeft: '1px solid',
            borderColor: 'divider',
            bgcolor: 'background.paper',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
          }
          : {
            display: 'flex',
            flexDirection: 'column',
            minHeight: '100%',
            bgcolor: 'background.paper',
          }
      }
    >
      <Box
        sx={{
          p: 1,
          borderBottom: '1px solid',
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 0.75,
        }}
      >
        <Select
          label={gettext('Inspector level')}
          size="small"
          value={inspectorLevel}
          options={inspectorLevelOptions}
          onChange={setInspectorLevel}
        />
        {!readOnly && (
          <Button
            size="small"
            onClick={() => quickAddLevelElement(inspectorLevel)}
          >
            {gettext('+ Add')}
          </Button>
        )}
      </Box>

      <ScrollArea
        label={gettext('Inspector elements and properties')}
        sx={{flex: 1, p: 1}}
      >
        <Stack gap="standard">
          <Box role="list" aria-label={`${inspectorLevel} elements`}>
            {activeLevelItems.length === 0 ? (
              <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
                {gettext(
                  'No %s elements yet. Use + Add to create one.',
                  inspectorLevel
                )}
              </Box>
            ) : (
              <Stack gap="compact">
                {activeLevelItems.map((item) => (
                  <Button
                    key={item.id}
                    size="small"
                    intent={
                      item.id === selectedElementId ? 'primary' : 'neutral'
                    }
                    onClick={() => setSelectedElementId(item.id)}
                  >
                    {item.name}
                  </Button>
                ))}
              </Stack>
            )}
          </Box>

          {elementDraft && (
            <Stack gap="compact">
              <TextField
                size="small"
                label={gettext('Element Name')}
                disabled={readOnly}
                value={elementDraft.name ?? ''}
                onChange={(e) =>
                  setElementDraft((cur) => ({
                    ...cur,
                    name: e.target.value,
                  }))
                }
              />

              {inspectorLevel === 'conceptual' && (
                <>
                  <TextField
                    size="small"
                    label={gettext('Domain / Bounded Area')}
                    disabled={readOnly}
                    value={elementDraft.area ?? ''}
                    onChange={(e) =>
                      setElementDraft((cur) => ({
                        ...cur,
                        area: e.target.value,
                      }))
                    }
                  />
                  <TextArea
                    rows={2}
                    label={gettext('Whiteboard Note')}
                    disabled={readOnly}
                    value={elementDraft.note ?? ''}
                    onChange={(e) =>
                      setElementDraft((cur) => ({
                        ...cur,
                        note: e.target.value,
                      }))
                    }
                  />
                </>
              )}

              {inspectorLevel === 'logical' && (
                <>
                  <TextField
                    size="small"
                    label={gettext('Subject Area')}
                    disabled={readOnly}
                    value={elementDraft.area ?? ''}
                    onChange={(e) =>
                      setElementDraft((cur) => ({
                        ...cur,
                        area: e.target.value,
                      }))
                    }
                  />
                  <TypedRowsEditor
                    label={gettext('Logical Attributes')}
                    addLabel={gettext('Attribute')}
                    disabled={readOnly}
                    rows={elementDraft.fields ?? []}
                    columns={[
                      {key: 'name', label: gettext('Name'), minWidth: 90},
                      {
                        key: 'datatype',
                        label: gettext('Type'),
                        type: 'select',
                        options: LOGICAL_TYPE_OPTIONS,
                        minWidth: 95,
                      },
                      {
                        key: 'pk',
                        label: gettext('PK'),
                        type: 'boolean',
                        minWidth: 50,
                      },
                      {
                        key: 'nullable',
                        label: gettext('Null'),
                        type: 'boolean',
                        default: true,
                        minWidth: 50,
                      },
                    ]}
                    onChange={(rows) =>
                      setElementDraft((cur) => ({...cur, fields: rows}))
                    }
                  />
                </>
              )}

              {inspectorLevel === 'physical' && (
                <>
                  <FormGrid columns={2}>
                    <TextField
                      size="small"
                      label={gettext('Schema')}
                      disabled={readOnly}
                      value={elementDraft.schema ?? ''}
                      onChange={(e) =>
                        setElementDraft((cur) => ({
                          ...cur,
                          schema: e.target.value,
                        }))
                      }
                    />
                    <Select
                      size="small"
                      label={gettext('Engine')}
                      disabled={readOnly}
                      value={elementDraft.engine ?? 'postgresql'}
                      options={engineOptions}
                      onChange={(val) =>
                        setElementDraft((cur) => ({...cur, engine: val}))
                      }
                    />
                  </FormGrid>
                  <TypedRowsEditor
                    label={gettext('Physical Columns')}
                    addLabel={gettext('Column')}
                    disabled={readOnly}
                    rows={elementDraft.fields ?? []}
                    columns={[
                      {key: 'name', label: gettext('Column'), minWidth: 90},
                      {
                        key: 'datatype',
                        label: gettext('SQL Type'),
                        default: 'VARCHAR(255)',
                        minWidth: 95,
                      },
                      {
                        key: 'pk',
                        label: gettext('PK'),
                        type: 'boolean',
                        minWidth: 48,
                      },
                      {
                        key: 'nullable',
                        label: gettext('Null'),
                        type: 'boolean',
                        default: true,
                        minWidth: 48,
                      },
                      {
                        key: 'references',
                        label: gettext('FK Ref (tbl.col)'),
                        minWidth: 110,
                      },
                    ]}
                    onChange={(rows) =>
                      setElementDraft((cur) => ({...cur, fields: rows}))
                    }
                  />
                  <TypedRowsEditor
                    label={gettext('Indexes')}
                    addLabel={gettext('Index')}
                    disabled={readOnly}
                    rows={elementDraft.indexes ?? []}
                    columns={[
                      {
                        key: 'name',
                        label: gettext('Index Name'),
                        minWidth: 100,
                      },
                      {key: 'column', label: gettext('Column'), minWidth: 85},
                      {
                        key: 'unique',
                        label: gettext('Unique'),
                        type: 'boolean',
                        minWidth: 55,
                      },
                    ]}
                    onChange={(rows) =>
                      setElementDraft((cur) => ({...cur, indexes: rows}))
                    }
                  />
                </>
              )}

              {inspectorLevel === 'deployment' && (
                <>
                  <FormGrid columns={2}>
                    <Select
                      size="small"
                      label={gettext('Engine')}
                      disabled={readOnly}
                      value={elementDraft.engine ?? 'postgresql'}
                      options={engineOptions}
                      onChange={(val) =>
                        setElementDraft((cur) => ({...cur, engine: val}))
                      }
                    />
                    <Select
                      size="small"
                      label={gettext('Node Role')}
                      disabled={readOnly}
                      value={elementDraft.role ?? 'primary'}
                      options={[
                        {value: 'primary', label: gettext('Primary')},
                        {value: 'replica', label: gettext('Replica')},
                        {value: 'cluster', label: gettext('Cluster')},
                        {value: 'analytics', label: gettext('Analytics')},
                      ]}
                      onChange={(val) =>
                        setElementDraft((cur) => ({...cur, role: val}))
                      }
                    />
                  </FormGrid>
                  <TextField
                    size="small"
                    label={gettext('Host / Address')}
                    disabled={readOnly}
                    value={elementDraft.host ?? ''}
                    onChange={(e) =>
                      setElementDraft((cur) => ({
                        ...cur,
                        host: e.target.value,
                      }))
                    }
                  />
                  <TextField
                    size="small"
                    label={gettext('Cloud Region / Rack')}
                    disabled={readOnly}
                    value={elementDraft.location ?? ''}
                    onChange={(e) =>
                      setElementDraft((cur) => ({
                        ...cur,
                        location: e.target.value,
                      }))
                    }
                  />
                  <TextField
                    size="small"
                    label={gettext('Endpoint ID')}
                    disabled={readOnly}
                    value={elementDraft.endpoint_id ?? ''}
                    onChange={(e) =>
                      setElementDraft((cur) => ({
                        ...cur,
                        endpoint_id: e.target.value,
                      }))
                    }
                  />
                </>
              )}

              {!readOnly && (
                <Stack direction="row" gap="compact">
                  <Button
                    size="small"
                    intent="primary"
                    loading={busyAction}
                    onClick={saveInspectorChanges}
                  >
                    {gettext('Save Level Changes')}
                  </Button>
                  <Button
                    size="small"
                    disabled={busyAction}
                    onClick={deleteSelectedInspectorElement}
                  >
                    {gettext('Delete')}
                  </Button>
                </Stack>
              )}
            </Stack>
          )}
        </Stack>
      </ScrollArea>
    </Box>
  );

  const erdShellInspectorNode = renderErdInspectorBody(false);

  const {inShell, shell, instanceId, openPropertiesDrawer} =
    useDesignerShellRegions({
      title: erdTitle,
      statusNode: erdStatusNode,
      statusText: erdStatusText,
      leftDrawerNode: erdNavigatorNode,
      rightDrawerNode: erdShellInspectorNode,
      rightOpen: inspectorOpen,
      quickActions: {
        onNew: readOnly
          ? undefined
          : () => quickAddLevelElement(level === 'all' ? inspectorLevel : level),
        onSave:
          readOnly || !sessionState.loaded
            ? undefined
            : () => runToolbarCommand('erd.designer.save', openSaveDialog),
        onUndo: readOnly ? undefined : handleUndoErd,
        onRedo: readOnly ? undefined : handleRedoErd,
      },
    });
  shellRegistryRef.current = shell?.actionsRegistry || null;
  openPropertiesDrawerRef.current = openPropertiesDrawer;

  useDesignerWorkbenchEvents({
    appId: 'erd-designer',
    instanceId,
    inShell,
    shell,
    onToolAction: (tool) => {
      if (tool === 'checkpoints') {
        setHistoryOpen(true);
        return;
      }
      if (tool === 'layers') {
        const idx = LEVEL_CYCLE.indexOf(level);
        const nextLevel = LEVEL_CYCLE[(idx + 1) % LEVEL_CYCLE.length];
        setLevel(nextLevel);
        setSurfaceNotice(
          gettext('Switched ERD modelling level to %s.', nextLevel)
        );
        return;
      }
      if (tool === 'align') {
        controller.load({version: sessionState.currentVersion});
        setSurfaceNotice(gettext('Recomputed layered ERD layout.'));
        return;
      }
      if (tool === 'pointer' || tool === 'marquee') {
        setCanvasToolMode(tool);
        setSurfaceNotice(gettext('Active canvas tool: %s.', tool));
        return;
      }
      if (tool === 'copy') {
        if (elementDraft) {
          erdClipboardRef.current = {
            level: inspectorLevel,
            draft: JSON.parse(JSON.stringify(elementDraft)),
          };
          setSurfaceNotice(
            gettext('Copied "%s" to designer clipboard.', elementDraft.name)
          );
        }
        return;
      }
      if (tool === 'cut') {
        if (!readOnly && elementDraft) {
          erdClipboardRef.current = {
            level: inspectorLevel,
            draft: JSON.parse(JSON.stringify(elementDraft)),
          };
          deleteSelectedInspectorElement();
          setSurfaceNotice(
            gettext('Cut "%s" to designer clipboard.', elementDraft.name)
          );
        }
        return;
      }
      if (tool === 'paste') {
        if (readOnly) return;
        const clip = erdClipboardRef.current;
        const targetLvl = clip?.level || (level === 'all' ? inspectorLevel : level);
        const baseName = clip?.draft?.name ? `${clip.draft.name}_copy` : null;
        quickAddLevelElement(targetLvl, baseName);
      }
    },
    onPaletteSelect: (kind, itemId) => {
      if (kind === 'stencil') {
        if (readOnly) return;
        if (itemId === 'concept') {
          quickAddLevelElement('conceptual');
          return;
        }
        if (itemId === 'deploy-node') {
          quickAddLevelElement('deployment');
          return;
        }
        if (itemId === 'rel-1n') {
          setConnectDraft({
            source: erdState.conceptual_entities[0]?.id || '',
            target: erdState.conceptual_entities[1]?.id || '',
            title: 'relates to',
          });
          setConnectOpen(true);
          return;
        }
        if (itemId === 'view') {
          quickAddLevelElement(
            'physical',
            `vw_${(erdState.physical_tables || []).length + 1}`
          );
          return;
        }
        quickAddLevelElement(level === 'logical' ? 'logical' : 'physical');
        return;
      }
      if (kind === 'udt') {
        if (itemId === 'type-map') {
          runToolbarCommand('erd.designer.convert', () => {
            setConvertResult(null);
            setConvertTab('engines');
            setConvertOpen(true);
          });
          return;
        }
        const mapped = UDT_SQL_TYPE_MAP[itemId] || {
          logical: 'string',
          physical: 'VARCHAR(255)',
        };
        if (!readOnly) {
          setInspectorOpen(true);
          openPropertiesDrawer();
          setElementDraft((cur) => {
            const base =
              cur || makeBlankElementDraft(inspectorLevel, activeLevelItems.length + 1);
            const colName = itemId.replace(/[^a-z0-9]+/gi, '_').toLowerCase();
            const nextField =
              inspectorLevel === 'logical'
                ? {name: colName, datatype: mapped.logical, pk: false, nullable: true}
                : {
                  name: colName,
                  datatype: mapped.physical,
                  pk: false,
                  nullable: true,
                  references: '',
                };
            return {
              ...base,
              fields: [...(base.fields || []), nextField],
            };
          });
          setConvertDraft((cur) => ({
            ...cur,
            customTypeMap: {
              ...cur.customTypeMap,
              [mapped.logical]: mapped.physical,
            },
          }));
          setSurfaceNotice(
            gettext('Applied UDT "%s" (%s).', itemId, mapped.physical)
          );
        }
      }
    },
  });

  const alterPlan = alterBundle?.plan || null;
  const riskSummary = alterBundle?.risk_summary || {
    loses_data: 0,
    may_fail_on_existing_data: 0,
    breaks_running_clients: 0,
    locks_or_copies_table: 0,
  };
  const activeMigrationSql =
    alterBundle?.migration_scripts?.[alterDraft.migrationFormat] ??
    alterBundle?.migration_sql ??
    alterPlan?.script ??
    '';

  return (
    <Box
      data-cde-surface="diagram.erd.designer"
      data-erd-sketch={erdState.look_handdrawn ? 'handdrawn' : 'crisp'}
      data-erd-tool-mode={canvasToolMode}
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="erd-designer-workspace" />

      <DesignerTabbedMenu
        label={gettext('ERD designer commands')}
        tabs={menuTabs}
        activeTab={menuTab}
        onTabChange={setMenuTab}
        commands={commands}
        leading={
          !inShell && sessionState.loaded ? (
            <Stack direction="row" gap="compact">
              <StatusBadge
                live
                status={
                  suspectBindings.length > 0
                    ? 'warning'
                    : sessionState.status === 'accepted'
                      ? 'success'
                      : 'info'
                }
                label={`v${sessionState.currentVersion} (${sessionState.status}) · ${
                  sessionState.layout?.nodes?.length || 0
                } nodes · ${sessionState.tiles?.length || 0} tiles`}
              />
              {erdState.look_handdrawn && (
                <StatusBadge status="info" label={gettext('Sketch Look')} />
              )}
            </Stack>
          ) : null
        }
        shellTrailing={
          <Select
            label={gettext('Modelling level')}
            size="small"
            value={level}
            options={levelOptions}
            onChange={setLevel}
          />
        }
        trailing={
          <Stack direction="row" gap="compact">
            <Select
              label={gettext('Modelling level')}
              size="small"
              value={level}
              options={levelOptions}
              onChange={setLevel}
            />
            <Button
              size="small"
              intent={inspectorOpen ? 'primary' : 'neutral'}
              onClick={() => setInspectorOpen((v) => !v)}
            >
              {inspectorOpen
                ? gettext('Hide Inspector')
                : gettext('Show Inspector')}
            </Button>
          </Stack>
        }
      />

      {surfaceError && (
        <Banner status="error" onClose={() => setSurfaceError('')}>
          {surfaceError}
        </Banner>
      )}
      {surfaceNotice && !surfaceError && (
        <Banner status="info" onClose={() => setSurfaceNotice('')}>
          {surfaceNotice}
        </Banner>
      )}

      {suspectBindings.length > 0 && (
        <Box data-testid="erd-suspect-bindings">
          <Banner status="warning">
            <Box
              sx={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 1,
                alignItems: 'center',
              }}
            >
              <span>
                {gettext(
                  '%s catalog binding(s) marked suspect after a rename or drop:',
                  suspectBindings.length
                )}
              </span>
              {suspectBindings.map((binding) => (
                <Button
                  key={binding.id}
                  size="small"
                  onClick={() => controller.confirmSuspectBinding(binding.id)}
                >
                  {gettext('Confirm %s', binding.target_ref)}
                </Button>
              ))}
            </Box>
          </Banner>
        </Box>
      )}

      {/* Main workspace: inside ProjectShell Area 3c owns the Property Inspector */}
      <Box
        sx={{
          position: 'relative',
          flex: 1,
          minHeight: 0,
          display: 'flex',
          overflow: 'hidden',
        }}
      >
        <Box
          sx={{
            position: 'relative',
            flex: 1,
            minWidth: 0,
            minHeight: 0,
            overflow: 'hidden',
          }}
        >
          {!loading && !sessionState.loaded && surfaceError && (
            <EmptyState message={surfaceError} />
          )}
          {sessionState.loaded && sessionState.workspace && (
            <DDNViewerSurface
              snapshot={{
                ...sessionState.workspace,
                view: activeView,
              }}
              view={activeView}
              showViewSelector={false}
              executeCommand={executeCommand}
              onExport={onExport}
              onError={onError}
            />
          )}
          <ProgressOverlay
            message={loading ? gettext('Loading ERD design') : ''}
          />
        </Box>

        {!inShell && inspectorOpen && renderErdInspectorBody(true)}
      </Box>

      {/* 1. Save Checkpoint Dialog */}
      <Dialog
        open={saveOpen}
        title={gettext('Save ERD checkpoint')}
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setSaveOpen(false)}
        defaultAction={submitSave}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setSaveOpen(false)}>
              {gettext('Cancel')}
            </Button>
            <Button intent="primary" loading={busyAction} onClick={submitSave}>
              {gettext('Save version')}
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="erd-designer-workspace"
          activeTab={saveTab}
          onTabChange={setSaveTab}
          tabs={[
            {
              id: 'details',
              label: gettext('Checkpoint Details'),
              render: () => (
                <FormGrid columns={2}>
                  <Select
                    label={gettext('Save-point status')}
                    value={saveDraft.status}
                    options={[
                      {value: 'draft', label: gettext('Draft')},
                      {value: 'in_progress', label: gettext('In progress')},
                      {value: 'in_review', label: gettext('In review')},
                    ]}
                    onChange={(val) =>
                      setSaveDraft((cur) => ({...cur, status: val}))
                    }
                  />
                  <TextField
                    label={gettext('Checkpoint note')}
                    value={saveDraft.note}
                    onChange={(e) =>
                      setSaveDraft((cur) => ({...cur, note: e.target.value}))
                    }
                  />
                </FormGrid>
              ),
            },
            {
              id: 'ddn',
              label: gettext('DDN Source'),
              render: () => (
                <Box sx={{height: 280}}>
                  <CodeEditor
                    label={gettext('DDN source')}
                    value={saveDraft.ddnText}
                    onChange={(val) =>
                      setSaveDraft((cur) => ({
                        ...cur,
                        ddnText: typeof val === 'string' ? val : cur.ddnText,
                      }))
                    }
                  />
                </Box>
              ),
            },
          ]}
        />
      </Dialog>

      {/* 2. Accept Version Dialog (A9) */}
      <Dialog
        open={acceptOpen}
        title={gettext('Accept ERD version')}
        size="medium"
        busy={busyAction}
        onClose={() => !busyAction && setAcceptOpen(false)}
        defaultAction={submitAccept}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setAcceptOpen(false)}>
              {gettext('Cancel')}
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitAccept}
            >
              {gettext('Accept version')}
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="erd-designer-workspace"
          minHeight={180}
          tabs={[
            {
              id: 'approval',
              label: gettext('Approval & Git Gate'),
              render: () => (
                <Stack gap="standard">
                  <Checkbox
                    label={gettext('Require Git review reference for this project')}
                    checked={acceptDraft.requireGitReview}
                    onChange={(checked) =>
                      setAcceptDraft((cur) => ({
                        ...cur,
                        requireGitReview: checked,
                      }))
                    }
                  />
                  <FormGrid columns={2}>
                    <TextField
                      label={gettext('Git review reference')}
                      value={acceptDraft.gitReviewRef}
                      onChange={(e) =>
                        setAcceptDraft((cur) => ({
                          ...cur,
                          gitReviewRef: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label={gettext('Approval comment')}
                      value={acceptDraft.comment}
                      onChange={(e) =>
                        setAcceptDraft((cur) => ({
                          ...cur,
                          comment: e.target.value,
                        }))
                      }
                    />
                  </FormGrid>
                </Stack>
              ),
            },
          ]}
        />
      </Dialog>

      {/* 3. Whiteboard Connect Boxes & Note Dialogs */}
      <Dialog
        open={connectOpen}
        title={gettext('Connect Conceptual Boxes')}
        size="medium"
        busy={busyAction}
        onClose={() => !busyAction && setConnectOpen(false)}
        defaultAction={submitConnectBoxes}
        actions={
          <>
            <Button onClick={() => setConnectOpen(false)}>
              {gettext('Cancel')}
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitConnectBoxes}
            >
              {gettext('Connect Boxes')}
            </Button>
          </>
        }
      >
        <FormReference formKey="erd-designer-whiteboard" />
        <FormGrid columns={2}>
          <Select
            label={gettext('From Conceptual Box')}
            value={connectDraft.source}
            options={erdState.conceptual_entities.map((c) => ({
              value: c.id,
              label: c.name,
            }))}
            onChange={(val) =>
              setConnectDraft((cur) => ({...cur, source: val}))
            }
          />
          <Select
            label={gettext('To Conceptual Box')}
            value={connectDraft.target}
            options={erdState.conceptual_entities.map((c) => ({
              value: c.id,
              label: c.name,
            }))}
            onChange={(val) =>
              setConnectDraft((cur) => ({...cur, target: val}))
            }
          />
          <TextField
            label={gettext('Relationship Verb / Phrase')}
            value={connectDraft.title}
            onChange={(e) =>
              setConnectDraft((cur) => ({...cur, title: e.target.value}))
            }
          />
        </FormGrid>
      </Dialog>

      <Dialog
        open={noteOpen}
        title={gettext('Add Conceptual Whiteboard Note')}
        size="medium"
        busy={busyAction}
        onClose={() => !busyAction && setNoteOpen(false)}
        defaultAction={submitAddNote}
        actions={
          <>
            <Button onClick={() => setNoteOpen(false)}>
              {gettext('Cancel')}
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitAddNote}
            >
              {gettext('Save Note')}
            </Button>
          </>
        }
      >
        <FormReference formKey="erd-designer-whiteboard" />
        <Stack gap="standard">
          <FormGrid columns={2}>
            <TextField
              label={gettext('Note Title')}
              value={noteDraft.title}
              onChange={(e) =>
                setNoteDraft((cur) => ({...cur, title: e.target.value}))
              }
            />
            <TextField
              label={gettext('Bounded Area')}
              value={noteDraft.area}
              onChange={(e) =>
                setNoteDraft((cur) => ({...cur, area: e.target.value}))
              }
            />
          </FormGrid>
          <TextArea
            rows={3}
            label={gettext('Note Text')}
            value={noteDraft.body}
            onChange={(e) =>
              setNoteDraft((cur) => ({...cur, body: e.target.value}))
            }
          />
        </Stack>
      </Dialog>

      {/* 4. Make It A Design — Whiteboard Promotion Wizard (SR-F-030011) */}
      <Dialog
        open={promoteOpen}
        title={gettext('Make It a Design — Promote Conceptual Whiteboard')}
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setPromoteOpen(false)}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setPromoteOpen(false)}>
              {gettext('Close')}
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => runPromoteWhiteboard(false)}
            >
              {gettext('Preview Promotion')}
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={() => runPromoteWhiteboard(true)}
            >
              {gettext('Promote & Save Checkpoint')}
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="erd-designer-whiteboard"
          activeTab={promoteTab}
          onTabChange={setPromoteTab}
          tabs={[
            {
              id: 'settings',
              label: gettext('Promotion Options & Catalog Match'),
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <Select
                      label={gettext('Target Physical Engine')}
                      value={promoteDraft.targetEngine}
                      options={engineOptions}
                      onChange={(val) =>
                        setPromoteDraft((cur) => ({...cur, targetEngine: val}))
                      }
                    />
                    <Select
                      label={gettext('Table Naming Convention')}
                      value={promoteDraft.tableNaming}
                      options={[
                        {
                          value: 'plural_snake',
                          label: gettext('Plural snake_case (customers)'),
                        },
                        {
                          value: 'singular_snake',
                          label: gettext('Singular snake_case (customer)'),
                        },
                        {
                          value: 'preserve',
                          label: gettext('Preserve normalized name'),
                        },
                      ]}
                      onChange={(val) =>
                        setPromoteDraft((cur) => ({...cur, tableNaming: val}))
                      }
                    />
                    <Select
                      label={gettext('Surrogate Primary Key Pattern')}
                      value={promoteDraft.pkStyle}
                      options={[
                        {
                          value: 'entity_id',
                          label: '<singular>_id (customer_id)',
                        },
                        {value: 'id', label: 'id'},
                      ]}
                      onChange={(val) =>
                        setPromoteDraft((cur) => ({...cur, pkStyle: val}))
                      }
                    />
                    <Select
                      label={gettext('Surrogate Key Logical Type')}
                      value={promoteDraft.pkType}
                      options={[
                        {value: 'bigint', label: 'bigint'},
                        {value: 'uuid', label: 'uuid'},
                        {value: 'integer', label: 'integer'},
                      ]}
                      onChange={(val) =>
                        setPromoteDraft((cur) => ({...cur, pkType: val}))
                      }
                    />
                  </FormGrid>
                  <Checkbox
                    label={gettext(
                      'Add created_at audit timestamp column to generated tables'
                    )}
                    checked={promoteDraft.includeAuditTimestamps}
                    onChange={(checked) =>
                      setPromoteDraft((cur) => ({
                        ...cur,
                        includeAuditTimestamps: checked,
                      }))
                    }
                  />
                  <TypedRowsEditor
                    label={gettext('Optional Existing Catalog Tables to Match')}
                    addLabel={gettext('Catalog Table')}
                    rows={promoteDraft.catalogRows}
                    columns={[
                      {
                        key: 'name',
                        label: gettext('Catalog Table Name'),
                        minWidth: 150,
                      },
                      {
                        key: 'pk_column',
                        label: gettext('PK Column'),
                        default: 'id',
                        minWidth: 110,
                      },
                      {
                        key: 'pk_type',
                        label: gettext('PK SQL Type'),
                        default: 'BIGINT',
                        minWidth: 110,
                      },
                    ]}
                    onChange={(rows) =>
                      setPromoteDraft((cur) => ({...cur, catalogRows: rows}))
                    }
                  />
                </Stack>
              ),
            },
            {
              id: 'preview',
              label: gettext('Promoted Model & DDN Preview'),
              render: () =>
                !promotePreview ? (
                  <EmptyState
                    message={gettext(
                      'Click Preview Promotion to inspect generated Logical entities, Physical tables, surrogate keys and inferred foreign keys.'
                    )}
                  />
                ) : (
                  <Stack gap="standard">
                    <Stack direction="row" gap="compact">
                      <StatusBadge
                        status="success"
                        label={gettext(
                          '%s Logical Entities',
                          promotePreview.promoted_logical_count
                        )}
                      />
                      <StatusBadge
                        status="success"
                        label={gettext(
                          '%s Physical Tables',
                          promotePreview.promoted_physical_count
                        )}
                      />
                      <StatusBadge
                        status="info"
                        label={gettext(
                          '%s Inferred FKs',
                          promotePreview.inferred_foreign_keys || 0
                        )}
                      />
                    </Stack>
                    <Box sx={{height: 220}}>
                      <CodeEditor
                        label={gettext('Promoted DDN preview')}
                        readonly
                        value={promotePreview.ddn_text || ''}
                      />
                    </Box>
                  </Stack>
                ),
            },
          ]}
        />
      </Dialog>

      {/* 5. Naming Standards, 1-Click Auto-Fix & Waivers Dialog (SR-F-030012) */}
      <Dialog
        open={standardsOpen}
        title={gettext('ERD Naming Standards & Waiver Inspector')}
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setStandardsOpen(false)}
        actions={
          <>
            <Button
              disabled={busyAction}
              onClick={() => setStandardsOpen(false)}
            >
              {gettext('Close')}
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => runStandardsAction('check')}
            >
              {gettext('Re-check Standards')}
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              disabled={readOnly || standardsData.active_count === 0}
              onClick={() => runStandardsAction('apply_fixes')}
            >
              {gettext('1-Click Auto-Fix All')}
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="erd-designer-standards"
          activeTab={standardsTab}
          onTabChange={setStandardsTab}
          tabs={[
            {
              id: 'violations',
              label: gettext('Violations (%s)', standardsData.active_count),
              attention: standardsData.active_count > 0,
              render: () =>
                (standardsData.violations || []).length === 0 ? (
                  <Banner status="success">
                    {gettext(
                      'All Logical and Physical names conform to active naming standards.'
                    )}
                  </Banner>
                ) : (
                  <ScrollArea
                    label={gettext('Naming violations')}
                    sx={{maxHeight: 320}}
                  >
                    <Box
                      component="table"
                      aria-label={gettext('Naming standard violations')}
                      sx={{
                        width: '100%',
                        borderCollapse: 'collapse',
                        fontSize: '0.8125rem',
                      }}
                    >
                      <Box component="thead">
                        <Box component="tr">
                          {[
                            gettext('Rule'),
                            gettext('Current Name'),
                            gettext('Suggested Fix'),
                            gettext('Status'),
                            gettext('Action'),
                          ].map((h) => (
                            <Box
                              key={h}
                              component="th"
                              sx={{
                                textAlign: 'left',
                                p: 0.75,
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
                        {standardsData.violations.map((v) => (
                          <Box key={v.id} component="tr">
                            <Box
                              component="td"
                              sx={{
                                p: 0.75,
                                borderBottom: '1px solid',
                                borderColor: 'divider',
                              }}
                            >
                              <code>{v.rule}</code>
                            </Box>
                            <Box
                              component="td"
                              sx={{
                                p: 0.75,
                                borderBottom: '1px solid',
                                borderColor: 'divider',
                              }}
                            >
                              {v.current_name}
                            </Box>
                            <Box
                              component="td"
                              sx={{
                                p: 0.75,
                                borderBottom: '1px solid',
                                borderColor: 'divider',
                              }}
                            >
                              <strong>{v.suggested_name}</strong>
                            </Box>
                            <Box
                              component="td"
                              sx={{
                                p: 0.75,
                                borderBottom: '1px solid',
                                borderColor: 'divider',
                              }}
                            >
                              <StatusBadge
                                status={v.waived ? 'info' : 'warning'}
                                label={
                                  v.waived
                                    ? gettext('Waived')
                                    : gettext('Violation')
                                }
                              />
                            </Box>
                            <Box
                              component="td"
                              sx={{
                                p: 0.75,
                                borderBottom: '1px solid',
                                borderColor: 'divider',
                              }}
                            >
                              {!v.waived && !readOnly && (
                                <Button
                                  size="small"
                                  onClick={() => quickWaiveViolation(v)}
                                >
                                  {gettext('Waive')}
                                </Button>
                              )}
                            </Box>
                          </Box>
                        ))}
                      </Box>
                    </Box>
                  </ScrollArea>
                ),
            },
            {
              id: 'rules',
              label: gettext('Rules Configuration'),
              render: () => (
                <FormGrid columns={2}>
                  <Select
                    label={gettext('Physical Table Case')}
                    value={standardsData.rules.table_case}
                    options={CASE_STYLE_OPTIONS}
                    onChange={(val) =>
                      setStandardsData((cur) => ({
                        ...cur,
                        rules: {...cur.rules, table_case: val},
                      }))
                    }
                  />
                  <Select
                    label={gettext('Column & Attribute Case')}
                    value={standardsData.rules.column_case}
                    options={CASE_STYLE_OPTIONS}
                    onChange={(val) =>
                      setStandardsData((cur) => ({
                        ...cur,
                        rules: {...cur.rules, column_case: val},
                      }))
                    }
                  />
                  <TextField
                    label={gettext('Primary Key Constraint Pattern')}
                    value={standardsData.rules.pk_pattern}
                    onChange={(e) =>
                      setStandardsData((cur) => ({
                        ...cur,
                        rules: {...cur.rules, pk_pattern: e.target.value},
                      }))
                    }
                  />
                  <TextField
                    label={gettext('Foreign Key Constraint Pattern')}
                    value={standardsData.rules.fk_pattern}
                    onChange={(e) =>
                      setStandardsData((cur) => ({
                        ...cur,
                        rules: {...cur.rules, fk_pattern: e.target.value},
                      }))
                    }
                  />
                  <TextField
                    label={gettext('Index Pattern')}
                    value={standardsData.rules.ix_pattern}
                    onChange={(e) =>
                      setStandardsData((cur) => ({
                        ...cur,
                        rules: {...cur.rules, ix_pattern: e.target.value},
                      }))
                    }
                  />
                </FormGrid>
              ),
            },
            {
              id: 'waivers',
              label: gettext(
                'Recorded Waivers (%s)',
                (standardsData.waivers || []).length
              ),
              render: () => (
                <Stack gap="standard">
                  <TypedRowsEditor
                    label={gettext('Persistent Naming Waivers')}
                    addLabel={gettext('Waiver')}
                    disabled={readOnly}
                    rows={standardsData.waivers}
                    columns={[
                      {
                        key: 'rule_id',
                        label: gettext('Rule'),
                        type: 'select',
                        options: [
                          {value: 'table_case', label: 'table_case'},
                          {value: 'column_case', label: 'column_case'},
                          {value: 'pk_pattern', label: 'pk_pattern'},
                          {value: 'fk_pattern', label: 'fk_pattern'},
                          {value: 'ix_pattern', label: 'ix_pattern'},
                          {value: '*', label: gettext('* (All rules)')},
                        ],
                        minWidth: 120,
                      },
                      {
                        key: 'target',
                        label: gettext('Target (e.g. table:LegacyTbl)'),
                        minWidth: 160,
                      },
                      {
                        key: 'reason',
                        label: gettext('Approval Reason'),
                        default: gettext('Legacy contract'),
                        minWidth: 160,
                      },
                    ]}
                    onChange={(rows) =>
                      setStandardsData((cur) => ({...cur, waivers: rows}))
                    }
                  />
                  {!readOnly && (
                    <Box>
                      <Button
                        intent="primary"
                        loading={busyAction}
                        onClick={() => runStandardsAction('save_waivers')}
                      >
                        {gettext('Save Waivers')}
                      </Button>
                    </Box>
                  )}
                </Stack>
              ),
            },
          ]}
        />
      </Dialog>

      {/* 6. Engine Conversion Dialog (SR-F-030014 — Typed KeyValuePairsEditor, zero raw JSON) */}
      <Dialog
        open={convertOpen}
        title={gettext('Convert ERD Engine')}
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setConvertOpen(false)}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setConvertOpen(false)}>
              {gettext('Close')}
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => runEngineConversion(false)}
            >
              {gettext('Preview Conversion')}
            </Button>
            {!readOnly && (
              <Button
                intent="primary"
                loading={busyAction}
                onClick={() => runEngineConversion(true)}
              >
                {gettext('Save Converted Version')}
              </Button>
            )}
          </>
        }
      >
        <DesignerModalTabs
          formKey="erd-designer-deploy"
          activeTab={convertTab}
          onTabChange={setConvertTab}
          tabs={[
            {
              id: 'engines',
              label: gettext('Engines & Type Overrides'),
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <Select
                      label={gettext('Source engine')}
                      value={convertDraft.sourceEngine}
                      options={engineOptions}
                      onChange={(val) =>
                        setConvertDraft((cur) => ({...cur, sourceEngine: val}))
                      }
                    />
                    <Select
                      label={gettext('Target engine')}
                      value={convertDraft.targetEngine}
                      options={engineOptions}
                      onChange={(val) =>
                        setConvertDraft((cur) => ({...cur, targetEngine: val}))
                      }
                    />
                  </FormGrid>
                  <KeyValuePairsEditor
                    label={gettext('Custom Engine Type Overrides')}
                    keyLabel={gettext('Logical Type')}
                    valueLabel={gettext('Target Physical SQL Type')}
                    keyPlaceholder="e.g. decimal"
                    valuePlaceholder="e.g. NUMERIC(20,4)"
                    value={convertDraft.customTypeMap}
                    onChange={(next) =>
                      setConvertDraft((cur) => ({...cur, customTypeMap: next}))
                    }
                  />
                  <KeyValuePairsEditor
                    label={gettext('Loss Choices')}
                    keyLabel={gettext('Lossy Item / Element ID')}
                    valueLabel={gettext('Explicit Conversion Choice')}
                    keyPlaceholder="e.g. json"
                    valuePlaceholder="e.g. store_as_text"
                    value={convertDraft.lossChoices}
                    onChange={(next) =>
                      setConvertDraft((cur) => ({...cur, lossChoices: next}))
                    }
                  />
                </Stack>
              ),
            },
            {
              id: 'preview',
              label: gettext('DDN Preview & Loss Report'),
              render: () =>
                !convertResult ? (
                  <EmptyState
                    message={gettext(
                      'Click Preview Conversion to inspect mapped physical types, lossy item warnings and DDN output.'
                    )}
                  />
                ) : (
                  <Stack gap="standard">
                    <Banner status="success">
                      {gettext(
                        'Converted to %s (lossy items: %s)',
                        convertResult.loss_report?.target_engine,
                        convertResult.loss_report?.lossy_count ?? 0
                      )}
                    </Banner>
                    <Box sx={{height: 240}}>
                      <CodeEditor
                        label={gettext('Converted DDN Preview')}
                        readonly
                        value={convertResult.ddn_text || ''}
                      />
                    </Box>
                  </Stack>
                ),
            },
          ]}
        />
      </Dialog>

      {/* 7. Alter Plan, 4-Bucket Risk & Migration Review Dialog (SR-F-030013) */}
      <Dialog
        open={alterOpen}
        title={gettext('Preview ERD alter plan')}
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setAlterOpen(false)}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setAlterOpen(false)}>
              {gettext('Close')}
            </Button>
            {!readOnly && typeof client.deployErdPlan === 'function' && (
              <Button
                intent="primary"
                loading={busyAction}
                onClick={() => submitAlterToOperationReview()}
              >
                {gettext('Submit to Native Operation Review')}
              </Button>
            )}
          </>
        }
      >
        <DesignerModalTabs
          formKey="erd-designer-alter-plan"
          activeTab={alterTab}
          onTabChange={setAlterTab}
          tabs={[
            {
              id: 'risks',
              label: gettext('Differences & 4 Risk Categories'),
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={3}>
                    <Select
                      label={gettext('Target SQL engine')}
                      value={alterDraft.targetEngine}
                      options={engineOptions}
                      onChange={(val) => {
                        setAlterDraft((cur) => ({...cur, targetEngine: val}));
                        loadAlterPlan({targetEngine: val}, selectedDiffs);
                      }}
                    />
                    <Select
                      label={gettext('Baseline Mode')}
                      value={alterDraft.baselineMode}
                      options={baselineModeOptions}
                      onChange={(val) => {
                        setAlterDraft((cur) => ({...cur, baselineMode: val}));
                        loadAlterPlan({baselineMode: val}, undefined);
                      }}
                    />
                    <Select
                      label={gettext('Migration Wrapper')}
                      value={alterDraft.migrationFormat}
                      options={migrationFormatOptions}
                      onChange={(val) => {
                        setAlterDraft((cur) => ({
                          ...cur,
                          migrationFormat: val,
                        }));
                        loadAlterPlan({migrationFormat: val}, selectedDiffs);
                      }}
                    />
                  </FormGrid>

                  {alterPlan && (
                    <>
                      <Box data-testid="erd-destructive-warning">
                        <Banner status="warning">
                          {alterPlan.destructive_warning}
                        </Banner>
                      </Box>

                      <Box
                        role="group"
                        aria-label={gettext('Risk classification summary')}
                        sx={{display: 'flex', flexWrap: 'wrap', gap: 1}}
                      >
                        <StatusBadge
                          status={
                            riskSummary.loses_data > 0 ? 'error' : 'success'
                          }
                          label={gettext('Loses Data: %s', riskSummary.loses_data)}
                        />
                        <StatusBadge
                          status={
                            riskSummary.may_fail_on_existing_data > 0
                              ? 'warning'
                              : 'success'
                          }
                          label={gettext(
                            'May Fail on Existing Data: %s',
                            riskSummary.may_fail_on_existing_data
                          )}
                        />
                        <StatusBadge
                          status={
                            riskSummary.breaks_running_clients > 0
                              ? 'error'
                              : 'success'
                          }
                          label={gettext(
                            'Breaks Running Clients: %s',
                            riskSummary.breaks_running_clients
                          )}
                        />
                        <StatusBadge
                          status={
                            riskSummary.locks_or_copies_table > 0
                              ? 'warning'
                              : 'success'
                          }
                          label={gettext(
                            'Locks / Copies Table: %s',
                            riskSummary.locks_or_copies_table
                          )}
                        />
                      </Box>

                      <ScrollArea
                        label={gettext('Detected schema differences')}
                        sx={{maxHeight: 220}}
                      >
                        <Box role="group" aria-label={gettext('Detected differences')}>
                          {(alterPlan.differences || []).length === 0 ? (
                            <Box sx={{fontSize: '0.8125rem', py: 0.5}}>
                              {gettext('No physical schema differences detected.')}
                            </Box>
                          ) : (
                            <Stack gap="compact">
                              {alterPlan.differences.map((diff) => (
                                <Checkbox
                                  key={diff.difference_id}
                                  label={`${diff.change_kind}: ${diff.object_name}${
                                    diff.destructive
                                      ? ` (${gettext('destructive')})`
                                      : ''
                                  }`}
                                  checked={selectedDiffs.includes(
                                    diff.difference_id
                                  )}
                                  onChange={(checked) =>
                                    toggleDifference(
                                      diff.difference_id,
                                      checked
                                    )
                                  }
                                />
                              ))}
                            </Stack>
                          )}
                        </Box>
                      </ScrollArea>
                    </>
                  )}
                </Stack>
              ),
            },
            {
              id: 'sql_preview',
              label: gettext('Migration SQL Preview'),
              render: () => (
                <Stack gap="standard">
                  <Select
                    label={gettext('Migration Output Format')}
                    value={alterDraft.migrationFormat}
                    options={migrationFormatOptions}
                    onChange={(val) =>
                      setAlterDraft((cur) => ({...cur, migrationFormat: val}))
                    }
                  />
                  <Box sx={{height: 250}}>
                    <CodeEditor
                      label={gettext(
                        'Generated change plan (native operation review required)'
                      )}
                      language="sql"
                      readonly
                      value={activeMigrationSql}
                    />
                  </Box>
                </Stack>
              ),
            },
            {
              id: 'submit_review',
              label: gettext('Native Operation Review'),
              render: () => (
                <Stack gap="standard">
                  <Banner status="info">
                    {gettext(
                      "Schema changes are queued into ScratchRobin's OperationBus in awaiting_approval state and are never executed directly by the ERD designer."
                    )}
                  </Banner>
                  <FormGrid columns={3}>
                    <Select
                      label={gettext('Target Environment')}
                      value={alterDraft.environment}
                      options={[
                        {value: 'dev', label: gettext('Development')},
                        {value: 'staging', label: gettext('Staging')},
                        {value: 'prod', label: gettext('Production')},
                      ]}
                      onChange={(val) =>
                        setAlterDraft((cur) => ({
                          ...cur,
                          environment: val,
                          endpointId: `env-${val}`,
                        }))
                      }
                    />
                    <TextField
                      label={gettext('Target Endpoint ID')}
                      value={alterDraft.endpointId}
                      onChange={(e) =>
                        setAlterDraft((cur) => ({
                          ...cur,
                          endpointId: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label={gettext('Required Approver Principal (optional)')}
                      placeholder="e.g. role:dba-lead"
                      value={alterDraft.approverPrincipal}
                      onChange={(e) =>
                        setAlterDraft((cur) => ({
                          ...cur,
                          approverPrincipal: e.target.value,
                        }))
                      }
                    />
                  </FormGrid>
                  {reviewReceipt && (
                    <Box data-testid="erd-operation-review-receipt">
                      <Banner status="success">
                        {gettext(
                          'Queued Operation %s in status %s (%s statements · applied immediately: %s).',
                          reviewReceipt.operation_id,
                          reviewReceipt.status,
                          reviewReceipt.statement_count,
                          String(reviewReceipt.applied_immediately)
                        )}
                      </Banner>
                    </Box>
                  )}
                </Stack>
              ),
            },
          ]}
        />
      </Dialog>

      {/* 8. System Diagram Drift & Topology Change Review Dialog (SR-F-030014) */}
      <Dialog
        open={driftOpen}
        title={gettext('System diagram drift and change review')}
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setDriftOpen(false)}
        defaultAction={submitDiagramProposal}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setDriftOpen(false)}>
              {gettext('Close')}
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => evaluateSystemDrift(liveTopologyRows)}
            >
              {gettext('Evaluate Drift')}
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitDiagramProposal}
            >
              {gettext('Request native review')}
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey="erd-designer-deploy"
          activeTab={driftTab}
          onTabChange={setDriftTab}
          tabs={[
            {
              id: 'topology',
              label: gettext('Live Topology & Drift'),
              render: () => (
                <Stack gap="standard">
                  {driftReport && (
                    <Banner
                      status={driftReport.has_drift ? 'warning' : 'success'}
                    >
                      {gettext(
                        'Drift status: %s (matched: %s, missing: %s, property drift: %s)',
                        driftReport.has_drift
                          ? gettext('Drift detected')
                          : gettext('In sync'),
                        driftReport.matched?.length || 0,
                        driftReport.missing_in_live?.length || 0,
                        driftReport.property_drift?.length || 0
                      )}
                    </Banner>
                  )}
                  <TypedRowsEditor
                    label={gettext('Live Topology Nodes')}
                    addLabel={gettext('Live Node')}
                    rows={liveTopologyRows}
                    columns={[
                      {key: 'id', label: gettext('Node ID'), minWidth: 110},
                      {key: 'host', label: gettext('Host'), minWidth: 120},
                      {
                        key: 'engine',
                        label: gettext('Engine'),
                        type: 'select',
                        options: engineOptions,
                        minWidth: 110,
                      },
                      {
                        key: 'role',
                        label: gettext('Role'),
                        default: 'primary',
                        minWidth: 95,
                      },
                      {
                        key: 'status',
                        label: gettext('Status'),
                        default: 'online',
                        minWidth: 90,
                      },
                    ]}
                    onChange={setLiveTopologyRows}
                  />
                </Stack>
              ),
            },
            {
              id: 'proposal',
              label: gettext('Propose Native Review Change'),
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={3}>
                    <TextField
                      label={gettext('Element ID')}
                      value={proposalDraft.elementId}
                      onChange={(e) =>
                        setProposalDraft((cur) => ({
                          ...cur,
                          elementId: e.target.value,
                        }))
                      }
                    />
                    <Select
                      label={gettext('Requested topology action')}
                      value={proposalDraft.action}
                      options={topologyActionOptions}
                      onChange={(val) =>
                        setProposalDraft((cur) => ({...cur, action: val}))
                      }
                    />
                    <TextField
                      label={gettext('Target host / rack')}
                      value={proposalDraft.targetHost}
                      onChange={(e) =>
                        setProposalDraft((cur) => ({
                          ...cur,
                          targetHost: e.target.value,
                        }))
                      }
                    />
                  </FormGrid>
                  {changeProposal && (
                    <Box data-testid="erd-change-proposal">
                      <Banner status="info">
                        {gettext(
                          'Proposal %s queued for ScratchRobin native-operation review (applied immediately: %s).',
                          changeProposal.proposal_id,
                          String(changeProposal.applied_immediately)
                        )}
                      </Banner>
                    </Box>
                  )}
                </Stack>
              ),
            },
          ]}
        />
      </Dialog>

      {/* 9. Multi-Target Deployment Environment Matrix (Dev / Staging / Prod, SR-F-030014) */}
      <Dialog
        open={envMatrixOpen}
        title={gettext('Multi-Target Deployment Environment Matrix')}
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setEnvMatrixOpen(false)}
        actions={
          <Button disabled={busyAction} onClick={() => setEnvMatrixOpen(false)}>
            {gettext('Close')}
          </Button>
        }
      >
        <DesignerModalTabs
          formKey="erd-designer-deploy"
          minHeight={240}
          tabs={[
            {
              id: 'matrix',
              label: gettext('Dev / Staging / Prod Matrix'),
              render: () => (
                <Stack gap="standard">
                  {envReceipt && (
                    <Banner status="success">
                      {gettext(
                        'Queued Operation %s for approval (%s).',
                        envReceipt.operation_id,
                        envReceipt.status
                      )}
                    </Banner>
                  )}
                  {environments.length === 0 ? (
                    <EmptyState
                      message={gettext('No environment records loaded yet.')}
                    />
                  ) : (
                    <ScrollArea
                      label={gettext('Environment matrix')}
                      sx={{maxHeight: 320}}
                    >
                      <Box
                        component="table"
                        aria-label={gettext('Deployment environment matrix')}
                        sx={{
                          width: '100%',
                          borderCollapse: 'collapse',
                          fontSize: '0.8125rem',
                        }}
                      >
                        <Box component="thead">
                          <Box component="tr">
                            {[
                              gettext('Environment'),
                              gettext('Endpoint / Target'),
                              gettext('Deployed'),
                              gettext('Desired'),
                              gettext('Drift Status'),
                              gettext('Actions'),
                            ].map((h) => (
                              <Box
                                key={h}
                                component="th"
                                sx={{
                                  textAlign: 'left',
                                  p: 0.75,
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
                          {environments.map((env) => (
                            <Box key={env.environment} component="tr">
                              <Box
                                component="td"
                                sx={{
                                  p: 0.75,
                                  borderBottom: '1px solid',
                                  borderColor: 'divider',
                                }}
                              >
                                <strong>{env.label}</strong>
                              </Box>
                              <Box
                                component="td"
                                sx={{
                                  p: 0.75,
                                  borderBottom: '1px solid',
                                  borderColor: 'divider',
                                }}
                              >
                                <code>
                                  {env.endpoint_id} / {env.database_target_id}
                                </code>
                              </Box>
                              <Box
                                component="td"
                                sx={{
                                  p: 0.75,
                                  borderBottom: '1px solid',
                                  borderColor: 'divider',
                                }}
                              >
                                {env.deployed_version
                                  ? `v${env.deployed_version}`
                                  : '—'}
                              </Box>
                              <Box
                                component="td"
                                sx={{
                                  p: 0.75,
                                  borderBottom: '1px solid',
                                  borderColor: 'divider',
                                }}
                              >
                                v{env.desired_version}
                              </Box>
                              <Box
                                component="td"
                                sx={{
                                  p: 0.75,
                                  borderBottom: '1px solid',
                                  borderColor: 'divider',
                                }}
                              >
                                <StatusBadge
                                  status={
                                    env.drift_status === 'in_sync'
                                      ? 'success'
                                      : env.drift_status === 'behind'
                                        ? 'warning'
                                        : 'info'
                                  }
                                  label={env.drift_status}
                                />
                              </Box>
                              <Box
                                component="td"
                                sx={{
                                  p: 0.75,
                                  borderBottom: '1px solid',
                                  borderColor: 'divider',
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                {!readOnly && (
                                  <Stack direction="row" gap="compact">
                                    <Button
                                      size="small"
                                      onClick={() =>
                                        submitAlterToOperationReview(
                                          env.environment
                                        )
                                      }
                                    >
                                      {gettext('Queue Review')}
                                    </Button>
                                    <Button
                                      size="small"
                                      intent="primary"
                                      onClick={() =>
                                        recordVerifiedDeployment(env)
                                      }
                                    >
                                      {gettext('Record Verified')}
                                    </Button>
                                  </Stack>
                                )}
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

      {/* 10. Git Sync Dialog */}
      <Dialog
        open={gitOpen}
        title={gettext('ERD Git Sync & Worktree Link')}
        size="medium"
        busy={busyAction}
        onClose={() => !busyAction && setGitOpen(false)}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setGitOpen(false)}>
              {gettext('Close')}
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => runGitAction('link')}
            >
              {gettext('Link Path')}
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => runGitAction('drift')}
            >
              {gettext('Check Drift')}
            </Button>
            {!readOnly && (
              <>
                <Button
                  disabled={busyAction}
                  onClick={() => runGitAction('load')}
                >
                  {gettext('Load from Git')}
                </Button>
                <Button
                  intent="primary"
                  loading={busyAction}
                  onClick={() => runGitAction('save')}
                >
                  {gettext('Save DDN to Git')}
                </Button>
              </>
            )}
          </>
        }
      >
        <FormReference formKey="erd-designer-workspace" />
        <Stack gap="standard">
          {gitStatusInfo && (
            <Banner status="info">
              {gettext(
                'Git sync state: %s',
                gitStatusInfo.sync_state || gitStatusInfo.status || 'updated'
              )}
            </Banner>
          )}
          <FormGrid columns={2}>
            <TextField
              label={gettext('Git Repository Worktree Path')}
              placeholder="/path/to/repo"
              value={gitDraft.repository}
              onChange={(e) =>
                setGitDraft((cur) => ({...cur, repository: e.target.value}))
              }
            />
            <TextField
              label={gettext('Relative DDN File Path')}
              value={gitDraft.path}
              onChange={(e) =>
                setGitDraft((cur) => ({...cur, path: e.target.value}))
              }
            />
            <TextField
              label={gettext('Branch')}
              value={gitDraft.branch}
              onChange={(e) =>
                setGitDraft((cur) => ({...cur, branch: e.target.value}))
              }
            />
            <TextField
              label={gettext('Note / Commit Summary')}
              value={gitDraft.note}
              onChange={(e) =>
                setGitDraft((cur) => ({...cur, note: e.target.value}))
              }
            />
          </FormGrid>
          <Checkbox
            label={gettext('Create Git commit when saving DDN to repository')}
            checked={gitDraft.commit}
            onChange={(checked) =>
              setGitDraft((cur) => ({...cur, commit: checked}))
            }
          />
        </Stack>
      </Dialog>

      {/* 11. Shared Checkpoint History & Diff Drawer (SR-F-030040) */}
      <DesignCheckpointHistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        client={client}
        projectId={projectId}
        designId={designId}
        currentVersion={sessionState.currentVersion}
        activeVersion={sessionState.activeVersion}
        onOpenVersion={async (ver) => {
          await controller.load({version: ver});
          await refreshErdInsights(ver);
        }}
        onRestored={async (newVer) => {
          await controller.load({version: newVer});
          await refreshErdInsights(newVer);
        }}
      />

      {/* 12. Shared Cross-Design Where Used Explorer (SR-F-030041) */}
      <WhereUsedDialog
        open={whereUsedOpen}
        onClose={() => setWhereUsedOpen(false)}
        client={client}
        projectId={projectId}
        designId={designId}
        initialTargetRef={whereUsedTarget}
      />
    </Box>
  );
}

function makeBlankElementDraft(level, index) {
  if (level === 'conceptual') {
    return {id: '', name: `Concept ${index}`, area: 'Core', note: ''};
  }
  if (level === 'logical') {
    return {
      id: '',
      name: `Entity${index}`,
      area: '',
      fields: [{name: 'id', datatype: 'bigint', pk: true, nullable: false}],
    };
  }
  if (level === 'deployment') {
    return {
      id: '',
      name: `db-node-${index}`,
      engine: 'postgresql',
      role: 'primary',
      host: '',
      location: '',
      endpoint_id: '',
    };
  }
  return {
    id: '',
    name: `table_${index}`,
    schema: 'public',
    engine: 'postgresql',
    fields: [{name: 'id', datatype: 'BIGINT', pk: true, nullable: false, references: ''}],
    indexes: [],
  };
}

function hydrateElementDraft(level, item) {
  if (!item) return null;
  if (level === 'conceptual') {
    return {
      id: item.id || '',
      name: item.name || '',
      area: item.area || '',
      note: item.note || '',
    };
  }
  if (level === 'logical') {
    return {
      id: item.id || '',
      name: item.name || '',
      area: item.area || '',
      fields: (item.fields || []).map((f) => ({
        id: f.id,
        name: f.name || '',
        datatype: f.datatype || 'string',
        pk: Boolean(f.pk),
        nullable: Boolean(f.nullable ?? !f.pk),
      })),
    };
  }
  if (level === 'deployment') {
    return {
      id: item.id || '',
      name: item.name || '',
      engine: item.engine || 'postgresql',
      role: item.role || item.node_role || 'primary',
      host: item.host || '',
      location: item.location || item.cloud_region || '',
      endpoint_id: item.endpoint_id || '',
      tables: item.tables || [],
    };
  }
  return {
    id: item.id || '',
    name: item.name || '',
    schema: item.schema || 'public',
    engine: item.engine || 'postgresql',
    fields: (item.fields || item.columns || []).map((c) => ({
      id: c.id,
      name: c.name || '',
      datatype: c.datatype || 'TEXT',
      pk: Boolean(c.pk),
      nullable: Boolean(c.nullable ?? !c.pk),
      references: c.references || '',
    })),
    indexes: (item.indexes || []).map((ix) => ({
      id: ix.id,
      name: ix.name || '',
      column: (ix.columns || [])[0] || '',
      unique: Boolean(ix.unique),
    })),
  };
}

function serializeElementDraftPayload(level, draft) {
  if (level === 'conceptual') {
    return {
      operation: 'upsert_conceptual',
      entity: {
        id: draft.id || undefined,
        name: draft.name,
        area: draft.area,
        note: draft.note,
      },
      note: `Updated conceptual box ${draft.name}`,
    };
  }
  if (level === 'logical') {
    return {
      operation: 'upsert_logical',
      entity: {
        id: draft.id || undefined,
        name: draft.name,
        area: draft.area,
        fields: (draft.fields || []).map((f) => ({
          id: f.id,
          name: f.name,
          datatype: f.datatype || 'string',
          pk: Boolean(f.pk),
          nullable: f.pk ? false : Boolean(f.nullable),
        })),
      },
      note: `Updated logical entity ${draft.name}`,
    };
  }
  if (level === 'deployment') {
    return {
      operation: 'upsert_deployment_node',
      node: {
        id: draft.id || undefined,
        name: draft.name,
        engine: draft.engine,
        role: draft.role,
        host: draft.host,
        location: draft.location,
        endpoint_id: draft.endpoint_id,
        tables: draft.tables || [],
      },
      note: `Updated deployment node ${draft.name}`,
    };
  }
  const fields = (draft.fields || []).map((c) => ({
    id: c.id,
    name: c.name,
    datatype: c.datatype || 'TEXT',
    pk: Boolean(c.pk),
    nullable: c.pk ? false : Boolean(c.nullable),
    references: c.references || '',
  }));
  const foreignKeys = fields
    .filter((c) => String(c.references || '').includes('.'))
    .map((c) => {
      const [refTable, refCol] = String(c.references).split('.', 2);
      return {
        columns: [c.name],
        ref_table: refTable.trim(),
        ref_columns: [refCol.trim() || 'id'],
      };
    });
  return {
    operation: 'upsert_physical_table',
    table: {
      id: draft.id || undefined,
      name: draft.name,
      schema: draft.schema || 'public',
      engine: draft.engine || 'postgresql',
      fields,
      indexes: (draft.indexes || [])
        .filter((ix) => ix.name || ix.column)
        .map((ix) => ({
          id: ix.id,
          name: ix.name,
          columns: ix.column ? [ix.column] : [],
          unique: Boolean(ix.unique),
        })),
      foreign_keys: foreignKeys,
    },
    note: `Updated physical table ${draft.name}`,
  };
}

ERDDesignerSurface.propTypes = {
  projectId: PropTypes.string.isRequired,
  designId: PropTypes.string.isRequired,
  client: PropTypes.object,
  controller: PropTypes.object,
  commands: PropTypes.object,
  readOnly: PropTypes.bool,
  executeCommand: PropTypes.func,
  onStateChange: PropTypes.func,
  onExport: PropTypes.func,
  onError: PropTypes.func,
};
