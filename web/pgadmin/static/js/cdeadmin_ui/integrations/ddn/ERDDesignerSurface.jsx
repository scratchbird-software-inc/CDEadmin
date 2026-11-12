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
import {TextArea, TextField} from '../../primitives/Field';
import {Dialog} from '../../overlays/Dialog';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import {StatusBadge} from '../../status/StatusBadge';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
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

const LEVEL_OPTIONS = Object.freeze([
  {value: 'all', label: 'All levels', viewId: 'erd_all_levels'},
  {
    value: 'conceptual',
    label: 'Conceptual (Whiteboard)',
    viewId: 'erd_conceptual',
  },
  {value: 'logical', label: 'Logical', viewId: 'erd_logical'},
  {value: 'physical', label: 'Physical', viewId: 'erd_physical'},
  {value: 'deployment', label: 'Deployment / System', viewId: 'erd_deployment'},
]);

const INSPECTOR_LEVEL_OPTIONS = Object.freeze([
  {value: 'conceptual', label: 'Conceptual'},
  {value: 'logical', label: 'Logical'},
  {value: 'physical', label: 'Physical'},
  {value: 'deployment', label: 'Deployment'},
]);

const ENGINE_OPTIONS = Object.freeze([
  {value: 'postgresql', label: 'PostgreSQL'},
  {value: 'sqlite', label: 'SQLite'},
  {value: 'duckdb', label: 'DuckDB'},
  {value: 'firebird', label: 'Firebird 5'},
  {value: 'mysql', label: 'MySQL'},
  {value: 'mariadb', label: 'MariaDB'},
]);

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

const MIGRATION_FORMAT_OPTIONS = Object.freeze([
  {value: 'plain_sql', label: 'Plain Transactional SQL'},
  {value: 'flyway', label: 'Flyway (V{n}__{name}.sql)'},
  {value: 'liquibase', label: 'Liquibase Formatted SQL'},
  {value: 'atlas', label: 'Atlas Versioned SQL'},
]);

const BASELINE_MODE_OPTIONS = Object.freeze([
  {value: 'active', label: 'Active Accepted Version'},
  {value: 'version', label: 'Specific Checkpoint'},
  {value: 'catalog', label: 'Live Catalog Baseline'},
]);

const TOPOLOGY_ACTION_OPTIONS = Object.freeze([
  {value: 'relocate_replica', label: 'Relocate Replica'},
  {value: 'promote_failover', label: 'Promote Failover'},
  {value: 'provision_node', label: 'Provision Host / Instance'},
  {value: 'decommission_node', label: 'Decommission Node'},
]);

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
  const target = LEVEL_OPTIONS.find((opt) => opt.value === level)?.viewId;
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

  const [sessionState, setSessionState] = useState(() => controller.state());
  const [loading, setLoading] = useState(!sessionState.loaded);
  const [surfaceError, setSurfaceError] = useState('');
  const [surfaceNotice, setSurfaceNotice] = useState('');
  const [menuTab, setMenuTab] = useState('model');
  const [level, setLevel] = useState('all');
  const [busyAction, setBusyAction] = useState(false);

  // Structured 4-level ERD state + right-hand Property Inspector
  const [erdState, setErdState] = useState(EMPTY_ERD_STATE);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [inspectorLevel, setInspectorLevel] = useState('physical');
  const [selectedElementId, setSelectedElementId] = useState('');
  const [elementDraft, setElementDraft] = useState(null);

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

  // Sync selected element draft when erdState or inspectorLevel changes
  const activeLevelItems = useMemo(() => {
    const key = listKeyForInspectorLevel(inspectorLevel);
    return erdState[key] || [];
  }, [erdState, inspectorLevel]);

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

  // -------------------------------------------------------------------------
  // Authoring & Property Inspector actions
  // -------------------------------------------------------------------------

  const quickAddLevelElement = async (targetLevel) => {
    setInspectorOpen(true);
    setInspectorLevel(targetLevel);
    if (level !== 'all' && level !== targetLevel) {
      setLevel(targetLevel);
    }
    if (typeof client.mutateErdElements !== 'function') {
      const fallbackDraft = makeBlankElementDraft(targetLevel, activeLevelItems.length + 1);
      setElementDraft(fallbackDraft);
      return;
    }
    setBusyAction(true);
    setSurfaceError('');
    try {
      const idx = (erdState[listKeyForInspectorLevel(targetLevel)] || []).length + 1;
      let payload;
      if (targetLevel === 'conceptual') {
        payload = {
          operation: 'upsert_conceptual',
          entity: {name: `Concept ${idx}`, area: 'Core'},
          note: `Added conceptual box Concept ${idx}`,
        };
      } else if (targetLevel === 'logical') {
        payload = {
          operation: 'upsert_logical',
          entity: {
            name: `Entity${idx}`,
            fields: [{name: 'id', datatype: 'bigint', pk: true, nullable: false}],
          },
          note: `Added logical entity Entity${idx}`,
        };
      } else if (targetLevel === 'deployment') {
        payload = {
          operation: 'upsert_deployment_node',
          node: {
            name: `db-node-${idx}`,
            engine: 'postgresql',
            role: 'primary',
            host: `db${idx}.internal`,
            location: 'us-east-1',
            tables: [],
          },
          note: `Added deployment node db-node-${idx}`,
        };
      } else {
        payload = {
          operation: 'upsert_physical_table',
          table: {
            name: `table_${idx}`,
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
          note: `Added physical table table_${idx}`,
        };
      }
      const res = await controller.mutateErdElements(payload);
      if (res?.elements) {
        setErdState({...EMPTY_ERD_STATE, ...res.elements});
        const items = res.elements[listKeyForInspectorLevel(targetLevel)] || [];
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
    setErdState((cur) => ({...cur, look_handdrawn: nextVal}));
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
      setSurfaceNotice('Saved element changes in local session.');
      return;
    }
    setBusyAction(true);
    setSurfaceError('');
    try {
      const payload = serializeElementDraftPayload(inspectorLevel, elementDraft);
      const res = await controller.mutateErdElements(payload);
      if (res?.elements) {
        setErdState({...EMPTY_ERD_STATE, ...res.elements});
      }
      await refreshErdInsights();
      setSurfaceNotice(`Saved ${inspectorLevel} element "${elementDraft.name}".`);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const deleteSelectedInspectorElement = async () => {
    if (!selectedElementId || typeof client.mutateErdElements !== 'function') {
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
        setErdState({...EMPTY_ERD_STATE, ...res.elements});
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
      setSurfaceError('Choose both source and target conceptual boxes.');
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
        setErdState({...EMPTY_ERD_STATE, ...res.elements});
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
      setSurfaceError('Enter a whiteboard note title or body.');
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
        label: 'Model',
        groups: [
          {
            id: 'save',
            label: 'Save Draft',
            items: [
              {
                id: 'erd.menu.save',
                label: 'Save Checkpoint',
                intent: 'primary',
                disabled: readOnly || !sessionState.loaded,
                onClick: () =>
                  runToolbarCommand('erd.designer.save', openSaveDialog),
              },
            ],
          },
          {
            id: 'status',
            label: 'Status',
            items: [
              {
                id: 'erd.menu.in_progress',
                label: 'Advance to In Progress',
                disabled:
                  readOnly ||
                  !sessionState.loaded ||
                  sessionState.status !== 'draft',
                onClick: () => controller.advanceStatus('in_progress'),
              },
              {
                id: 'erd.menu.in_review',
                label: 'Submit for Review',
                disabled:
                  readOnly ||
                  !sessionState.loaded ||
                  sessionState.status === 'accepted' ||
                  sessionState.status === 'in_review',
                onClick: () => controller.advanceStatus('in_review'),
              },
              {
                id: 'erd.menu.accept',
                label: 'Accept',
                disabled: readOnly || !sessionState.loaded,
                onClick: () =>
                  runToolbarCommand('erd.designer.accept', () =>
                    setAcceptOpen(true)
                  ),
              },
              {
                id: 'erd.menu.branch_draft',
                label: 'Branch Draft',
                disabled:
                  readOnly ||
                  !sessionState.loaded ||
                  !sessionState.activeVersion,
                onClick: () =>
                  controller.branchDraft({note: 'Branched draft from active'}),
              },
            ],
          },
          {
            id: 'history_git',
            label: 'History & Git',
            items: [
              {
                id: 'erd.menu.checkpoints',
                label: 'Checkpoints & Diff…',
                disabled: !sessionState.loaded,
                onClick: () => setHistoryOpen(true),
              },
              {
                id: 'erd.menu.git',
                label: 'Git Sync…',
                disabled: !sessionState.loaded,
                onClick: () => setGitOpen(true),
              },
              {
                id: 'erd.menu.export',
                label: 'Export DDN',
                disabled: !sessionState.loaded,
                onClick: handleExportDdn,
              },
              {
                id: 'erd.menu.where_used',
                label: 'Where Used…',
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
        label: 'Author & Whiteboard',
        groups: [
          {
            id: 'whiteboard_sketch',
            label: 'Whiteboard Sketch',
            items: [
              {
                id: 'erd.menu.add_conceptual',
                label: '+ Conceptual Box',
                disabled: readOnly || !sessionState.loaded,
                onClick: () => quickAddLevelElement('conceptual'),
              },
              {
                id: 'erd.menu.connect_boxes',
                label: '+ Connect Boxes',
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
                label: '+ Note',
                disabled: readOnly || !sessionState.loaded,
                onClick: () => {
                  setNoteDraft({title: 'Whiteboard Note', area: '', body: ''});
                  setNoteOpen(true);
                },
              },
              {
                id: 'erd.menu.sketch_look',
                label: 'Sketch Look',
                active: Boolean(erdState.look_handdrawn),
                disabled: readOnly || !sessionState.loaded,
                onClick: toggleSketchLook,
              },
              {
                id: 'erd.menu.promote_whiteboard',
                label: 'Make it a design…',
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
            label: 'Structured Levels',
            items: [
              {
                id: 'erd.menu.add_logical',
                label: '+ Logical Entity',
                disabled: readOnly || !sessionState.loaded,
                onClick: () => quickAddLevelElement('logical'),
              },
              {
                id: 'erd.menu.add_physical',
                label: '+ Physical Table',
                disabled: readOnly || !sessionState.loaded,
                onClick: () => quickAddLevelElement('physical'),
              },
              {
                id: 'erd.menu.add_deployment',
                label: '+ Deployment Node',
                disabled: readOnly || !sessionState.loaded,
                onClick: () => quickAddLevelElement('deployment'),
              },
              {
                id: 'erd.menu.toggle_inspector',
                label: 'Toggle Inspector',
                active: inspectorOpen,
                onClick: () => setInspectorOpen((v) => !v),
              },
            ],
          },
        ],
      },
      {
        id: 'levels',
        label: 'Levels & Layout',
        groups: [
          {
            id: 'level_switcher',
            label: 'Modelling Level',
            items: [
              {
                id: 'erd.level.all',
                label: 'All Levels',
                active: level === 'all',
                onClick: () => setLevel('all'),
              },
              {
                id: 'erd.level.conceptual',
                label: 'Conceptual',
                active: level === 'conceptual',
                onClick: () => setLevel('conceptual'),
              },
              {
                id: 'erd.level.logical',
                label: 'Logical',
                active: level === 'logical',
                onClick: () => setLevel('logical'),
              },
              {
                id: 'erd.level.physical',
                label: 'Physical',
                active: level === 'physical',
                onClick: () => setLevel('physical'),
              },
              {
                id: 'erd.level.deployment',
                label: 'Deployment',
                active: level === 'deployment',
                onClick: () => setLevel('deployment'),
              },
            ],
          },
          {
            id: 'layout_pins',
            label: 'Layered Layout & Pins',
            items: [
              {
                id: 'erd.layout.recompute',
                label: 'Recompute Layered Layout',
                disabled: !sessionState.loaded,
                onClick: () =>
                  controller.load({version: sessionState.currentVersion}),
              },
              {
                id: 'erd.layout.pin',
                label: 'Pin Selected / Unpin All',
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
        label: 'Validate & Standards',
        attention:
          standardsData.active_count > 0 || suspectBindings.length > 0,
        groups: [
          {
            id: 'standards_group',
            label: 'Standards & Bindings',
            items: [
              {
                id: 'erd.menu.standards',
                label: 'Naming Standards…',
                badge: standardsData.active_count,
                disabled: !sessionState.loaded,
                onClick: openStandardsDialog,
              },
              {
                id: 'erd.menu.suspect_bindings',
                label: 'Suspect Bindings',
                badge: suspectBindings.length,
                disabled: !sessionState.loaded,
                onClick: () => {
                  if (suspectBindings.length === 0) {
                    setSurfaceNotice('All catalog bindings are valid.');
                  }
                },
              },
              {
                id: 'erd.menu.refresh',
                label: 'Refresh Session',
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
        label: 'Compare & Deploy',
        groups: [
          {
            id: 'compare_convert',
            label: 'Conversion & Schema Plan',
            items: [
              {
                id: 'erd.menu.convert',
                label: 'Engine Conversion…',
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
                label: 'Alter Plan & Migration…',
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
            label: 'Topology & Environments',
            items: [
              {
                id: 'erd.menu.drift',
                label: 'System Drift…',
                disabled: !sessionState.loaded,
                onClick: openDriftDialog,
              },
              {
                id: 'erd.menu.env_matrix',
                label: 'Environment Matrix (Dev/Stage/Prod)…',
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
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="erd-designer-workspace" />

      <DesignerTabbedMenu
        label="ERD designer commands"
        tabs={menuTabs}
        activeTab={menuTab}
        onTabChange={setMenuTab}
        leading={
          sessionState.loaded ? (
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
                <StatusBadge status="info" label="Sketch Look" />
              )}
            </Stack>
          ) : null
        }
        trailing={
          <Stack direction="row" gap="compact">
            <Select
              label="Modelling level"
              size="small"
              value={level}
              options={LEVEL_OPTIONS}
              onChange={setLevel}
            />
            <Button
              size="small"
              intent={inspectorOpen ? 'primary' : 'neutral'}
              onClick={() => setInspectorOpen((v) => !v)}
            >
              {inspectorOpen ? 'Hide Inspector' : 'Show Inspector'}
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
                {suspectBindings.length} catalog binding(s) marked suspect after
                a rename or drop:
              </span>
              {suspectBindings.map((binding) => (
                <Button
                  key={binding.id}
                  size="small"
                  onClick={() => controller.confirmSuspectBinding(binding.id)}
                >
                  Confirm {binding.target_ref}
                </Button>
              ))}
            </Box>
          </Banner>
        </Box>
      )}

      {/* Main split workspace: Shared DDNViewerSurface + Collapsible 320px Property Inspector */}
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
          <ProgressOverlay message={loading ? 'Loading ERD design' : ''} />
        </Box>

        {inspectorOpen && (
          <Box
            component="aside"
            aria-label="ERD element property inspector"
            data-testid="erd-property-inspector"
            sx={{
              width: 320,
              flexShrink: 0,
              borderLeft: '1px solid',
              borderColor: 'divider',
              bgcolor: 'background.paper',
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
            }}
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
                label="Inspector level"
                size="small"
                value={inspectorLevel}
                options={INSPECTOR_LEVEL_OPTIONS}
                onChange={setInspectorLevel}
              />
              {!readOnly && (
                <Button
                  size="small"
                  onClick={() => quickAddLevelElement(inspectorLevel)}
                >
                  + Add
                </Button>
              )}
            </Box>

            <ScrollArea
              label="Inspector elements and properties"
              sx={{flex: 1, p: 1}}
            >
              <Stack gap="standard">
                <Box role="list" aria-label={`${inspectorLevel} elements`}>
                  {activeLevelItems.length === 0 ? (
                    <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
                      No {inspectorLevel} elements yet. Use + Add to create one.
                    </Box>
                  ) : (
                    <Stack gap="compact">
                      {activeLevelItems.map((item) => (
                        <Button
                          key={item.id}
                          size="small"
                          intent={
                            item.id === selectedElementId
                              ? 'primary'
                              : 'neutral'
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
                      label="Element Name"
                      disabled={readOnly}
                      value={elementDraft.name}
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
                          label="Domain / Bounded Area"
                          disabled={readOnly}
                          value={elementDraft.area}
                          onChange={(e) =>
                            setElementDraft((cur) => ({
                              ...cur,
                              area: e.target.value,
                            }))
                          }
                        />
                        <TextArea
                          rows={2}
                          label="Whiteboard Note"
                          disabled={readOnly}
                          value={elementDraft.note}
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
                          label="Subject Area"
                          disabled={readOnly}
                          value={elementDraft.area}
                          onChange={(e) =>
                            setElementDraft((cur) => ({
                              ...cur,
                              area: e.target.value,
                            }))
                          }
                        />
                        <TypedRowsEditor
                          label="Logical Attributes"
                          addLabel="Attribute"
                          disabled={readOnly}
                          rows={elementDraft.fields}
                          columns={[
                            {key: 'name', label: 'Name', minWidth: 90},
                            {
                              key: 'datatype',
                              label: 'Type',
                              type: 'select',
                              options: LOGICAL_TYPE_OPTIONS,
                              minWidth: 95,
                            },
                            {
                              key: 'pk',
                              label: 'PK',
                              type: 'boolean',
                              minWidth: 50,
                            },
                            {
                              key: 'nullable',
                              label: 'Null',
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
                            label="Schema"
                            disabled={readOnly}
                            value={elementDraft.schema}
                            onChange={(e) =>
                              setElementDraft((cur) => ({
                                ...cur,
                                schema: e.target.value,
                              }))
                            }
                          />
                          <Select
                            size="small"
                            label="Engine"
                            disabled={readOnly}
                            value={elementDraft.engine}
                            options={ENGINE_OPTIONS}
                            onChange={(val) =>
                              setElementDraft((cur) => ({...cur, engine: val}))
                            }
                          />
                        </FormGrid>
                        <TypedRowsEditor
                          label="Physical Columns"
                          addLabel="Column"
                          disabled={readOnly}
                          rows={elementDraft.fields}
                          columns={[
                            {key: 'name', label: 'Column', minWidth: 90},
                            {
                              key: 'datatype',
                              label: 'SQL Type',
                              default: 'VARCHAR(255)',
                              minWidth: 95,
                            },
                            {
                              key: 'pk',
                              label: 'PK',
                              type: 'boolean',
                              minWidth: 48,
                            },
                            {
                              key: 'nullable',
                              label: 'Null',
                              type: 'boolean',
                              default: true,
                              minWidth: 48,
                            },
                            {
                              key: 'references',
                              label: 'FK Ref (tbl.col)',
                              minWidth: 110,
                            },
                          ]}
                          onChange={(rows) =>
                            setElementDraft((cur) => ({...cur, fields: rows}))
                          }
                        />
                        <TypedRowsEditor
                          label="Indexes"
                          addLabel="Index"
                          disabled={readOnly}
                          rows={elementDraft.indexes}
                          columns={[
                            {key: 'name', label: 'Index Name', minWidth: 100},
                            {key: 'column', label: 'Column', minWidth: 85},
                            {
                              key: 'unique',
                              label: 'Unique',
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
                            label="Engine"
                            disabled={readOnly}
                            value={elementDraft.engine}
                            options={ENGINE_OPTIONS}
                            onChange={(val) =>
                              setElementDraft((cur) => ({...cur, engine: val}))
                            }
                          />
                          <Select
                            size="small"
                            label="Node Role"
                            disabled={readOnly}
                            value={elementDraft.role}
                            options={[
                              {value: 'primary', label: 'Primary'},
                              {value: 'replica', label: 'Replica'},
                              {value: 'cluster', label: 'Cluster'},
                              {value: 'analytics', label: 'Analytics'},
                            ]}
                            onChange={(val) =>
                              setElementDraft((cur) => ({...cur, role: val}))
                            }
                          />
                        </FormGrid>
                        <TextField
                          size="small"
                          label="Host / Address"
                          disabled={readOnly}
                          value={elementDraft.host}
                          onChange={(e) =>
                            setElementDraft((cur) => ({
                              ...cur,
                              host: e.target.value,
                            }))
                          }
                        />
                        <TextField
                          size="small"
                          label="Cloud Region / Rack"
                          disabled={readOnly}
                          value={elementDraft.location}
                          onChange={(e) =>
                            setElementDraft((cur) => ({
                              ...cur,
                              location: e.target.value,
                            }))
                          }
                        />
                        <TextField
                          size="small"
                          label="Endpoint ID"
                          disabled={readOnly}
                          value={elementDraft.endpoint_id}
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
                          Save Level Changes
                        </Button>
                        <Button
                          size="small"
                          disabled={busyAction}
                          onClick={deleteSelectedInspectorElement}
                        >
                          Delete
                        </Button>
                      </Stack>
                    )}
                  </Stack>
                )}
              </Stack>
            </ScrollArea>
          </Box>
        )}
      </Box>

      {/* 1. Save Checkpoint Dialog */}
      <Dialog
        open={saveOpen}
        title="Save ERD checkpoint"
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setSaveOpen(false)}
        defaultAction={submitSave}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setSaveOpen(false)}>
              Cancel
            </Button>
            <Button intent="primary" loading={busyAction} onClick={submitSave}>
              Save version
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
              label: 'Checkpoint Details',
              render: () => (
                <FormGrid columns={2}>
                  <Select
                    label="Save-point status"
                    value={saveDraft.status}
                    options={[
                      {value: 'draft', label: 'Draft'},
                      {value: 'in_progress', label: 'In progress'},
                      {value: 'in_review', label: 'In review'},
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
              ),
            },
            {
              id: 'ddn',
              label: 'DDN Source',
              render: () => (
                <Box sx={{height: 280}}>
                  <CodeEditor
                    label="DDN source"
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
        title="Accept ERD version"
        size="medium"
        busy={busyAction}
        onClose={() => !busyAction && setAcceptOpen(false)}
        defaultAction={submitAccept}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setAcceptOpen(false)}>
              Cancel
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitAccept}
            >
              Accept version
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
              label: 'Approval & Git Gate',
              render: () => (
                <Stack gap="standard">
                  <Checkbox
                    label="Require Git review reference for this project"
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
                      label="Git review reference"
                      value={acceptDraft.gitReviewRef}
                      onChange={(e) =>
                        setAcceptDraft((cur) => ({
                          ...cur,
                          gitReviewRef: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Approval comment"
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
        title="Connect Conceptual Boxes"
        size="medium"
        busy={busyAction}
        onClose={() => !busyAction && setConnectOpen(false)}
        defaultAction={submitConnectBoxes}
        actions={
          <>
            <Button onClick={() => setConnectOpen(false)}>Cancel</Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitConnectBoxes}
            >
              Connect Boxes
            </Button>
          </>
        }
      >
        <FormReference formKey="erd-designer-whiteboard" />
        <FormGrid columns={2}>
          <Select
            label="From Conceptual Box"
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
            label="To Conceptual Box"
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
            label="Relationship Verb / Phrase"
            value={connectDraft.title}
            onChange={(e) =>
              setConnectDraft((cur) => ({...cur, title: e.target.value}))
            }
          />
        </FormGrid>
      </Dialog>

      <Dialog
        open={noteOpen}
        title="Add Conceptual Whiteboard Note"
        size="medium"
        busy={busyAction}
        onClose={() => !busyAction && setNoteOpen(false)}
        defaultAction={submitAddNote}
        actions={
          <>
            <Button onClick={() => setNoteOpen(false)}>Cancel</Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitAddNote}
            >
              Save Note
            </Button>
          </>
        }
      >
        <FormReference formKey="erd-designer-whiteboard" />
        <Stack gap="standard">
          <FormGrid columns={2}>
            <TextField
              label="Note Title"
              value={noteDraft.title}
              onChange={(e) =>
                setNoteDraft((cur) => ({...cur, title: e.target.value}))
              }
            />
            <TextField
              label="Bounded Area"
              value={noteDraft.area}
              onChange={(e) =>
                setNoteDraft((cur) => ({...cur, area: e.target.value}))
              }
            />
          </FormGrid>
          <TextArea
            rows={3}
            label="Note Text"
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
        title="Make It a Design — Promote Conceptual Whiteboard"
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setPromoteOpen(false)}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setPromoteOpen(false)}>
              Close
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => runPromoteWhiteboard(false)}
            >
              Preview Promotion
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={() => runPromoteWhiteboard(true)}
            >
              Promote & Save Checkpoint
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
              label: 'Promotion Options & Catalog Match',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <Select
                      label="Target Physical Engine"
                      value={promoteDraft.targetEngine}
                      options={ENGINE_OPTIONS}
                      onChange={(val) =>
                        setPromoteDraft((cur) => ({...cur, targetEngine: val}))
                      }
                    />
                    <Select
                      label="Table Naming Convention"
                      value={promoteDraft.tableNaming}
                      options={[
                        {
                          value: 'plural_snake',
                          label: 'Plural snake_case (customers)',
                        },
                        {
                          value: 'singular_snake',
                          label: 'Singular snake_case (customer)',
                        },
                        {value: 'preserve', label: 'Preserve normalized name'},
                      ]}
                      onChange={(val) =>
                        setPromoteDraft((cur) => ({...cur, tableNaming: val}))
                      }
                    />
                    <Select
                      label="Surrogate Primary Key Pattern"
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
                      label="Surrogate Key Logical Type"
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
                    label="Add created_at audit timestamp column to generated tables"
                    checked={promoteDraft.includeAuditTimestamps}
                    onChange={(checked) =>
                      setPromoteDraft((cur) => ({
                        ...cur,
                        includeAuditTimestamps: checked,
                      }))
                    }
                  />
                  <TypedRowsEditor
                    label="Optional Existing Catalog Tables to Match"
                    addLabel="Catalog Table"
                    rows={promoteDraft.catalogRows}
                    columns={[
                      {key: 'name', label: 'Catalog Table Name', minWidth: 150},
                      {
                        key: 'pk_column',
                        label: 'PK Column',
                        default: 'id',
                        minWidth: 110,
                      },
                      {
                        key: 'pk_type',
                        label: 'PK SQL Type',
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
              label: 'Promoted Model & DDN Preview',
              render: () =>
                !promotePreview ? (
                  <EmptyState message="Click Preview Promotion to inspect generated Logical entities, Physical tables, surrogate keys and inferred foreign keys." />
                ) : (
                  <Stack gap="standard">
                    <Stack direction="row" gap="compact">
                      <StatusBadge
                        status="success"
                        label={`${promotePreview.promoted_logical_count} Logical Entities`}
                      />
                      <StatusBadge
                        status="success"
                        label={`${promotePreview.promoted_physical_count} Physical Tables`}
                      />
                      <StatusBadge
                        status="info"
                        label={`${promotePreview.inferred_foreign_keys || 0} Inferred FKs`}
                      />
                    </Stack>
                    <Box sx={{height: 220}}>
                      <CodeEditor
                        label="Promoted DDN preview"
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
        title="ERD Naming Standards & Waiver Inspector"
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setStandardsOpen(false)}
        actions={
          <>
            <Button
              disabled={busyAction}
              onClick={() => setStandardsOpen(false)}
            >
              Close
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => runStandardsAction('check')}
            >
              Re-check Standards
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              disabled={readOnly || standardsData.active_count === 0}
              onClick={() => runStandardsAction('apply_fixes')}
            >
              1-Click Auto-Fix All
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
              label: `Violations (${standardsData.active_count})`,
              attention: standardsData.active_count > 0,
              render: () =>
                (standardsData.violations || []).length === 0 ? (
                  <Banner status="success">
                    All Logical and Physical names conform to active naming
                    standards.
                  </Banner>
                ) : (
                  <ScrollArea label="Naming violations" sx={{maxHeight: 320}}>
                    <Box
                      component="table"
                      aria-label="Naming standard violations"
                      sx={{
                        width: '100%',
                        borderCollapse: 'collapse',
                        fontSize: '0.8125rem',
                      }}
                    >
                      <Box component="thead">
                        <Box component="tr">
                          {[
                            'Rule',
                            'Current Name',
                            'Suggested Fix',
                            'Status',
                            'Action',
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
                                label={v.waived ? 'Waived' : 'Violation'}
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
                                  Waive
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
              label: 'Rules Configuration',
              render: () => (
                <FormGrid columns={2}>
                  <Select
                    label="Physical Table Case"
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
                    label="Column & Attribute Case"
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
                    label="Primary Key Constraint Pattern"
                    value={standardsData.rules.pk_pattern}
                    onChange={(e) =>
                      setStandardsData((cur) => ({
                        ...cur,
                        rules: {...cur.rules, pk_pattern: e.target.value},
                      }))
                    }
                  />
                  <TextField
                    label="Foreign Key Constraint Pattern"
                    value={standardsData.rules.fk_pattern}
                    onChange={(e) =>
                      setStandardsData((cur) => ({
                        ...cur,
                        rules: {...cur.rules, fk_pattern: e.target.value},
                      }))
                    }
                  />
                  <TextField
                    label="Index Pattern"
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
              label: `Recorded Waivers (${(standardsData.waivers || []).length})`,
              render: () => (
                <Stack gap="standard">
                  <TypedRowsEditor
                    label="Persistent Naming Waivers"
                    addLabel="Waiver"
                    disabled={readOnly}
                    rows={standardsData.waivers}
                    columns={[
                      {
                        key: 'rule_id',
                        label: 'Rule',
                        type: 'select',
                        options: [
                          {value: 'table_case', label: 'table_case'},
                          {value: 'column_case', label: 'column_case'},
                          {value: 'pk_pattern', label: 'pk_pattern'},
                          {value: 'fk_pattern', label: 'fk_pattern'},
                          {value: 'ix_pattern', label: 'ix_pattern'},
                          {value: '*', label: '* (All rules)'},
                        ],
                        minWidth: 120,
                      },
                      {
                        key: 'target',
                        label: 'Target (e.g. table:LegacyTbl)',
                        minWidth: 160,
                      },
                      {
                        key: 'reason',
                        label: 'Approval Reason',
                        default: 'Legacy contract',
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
                        Save Waivers
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
        title="Convert ERD Engine"
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setConvertOpen(false)}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setConvertOpen(false)}>
              Close
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => runEngineConversion(false)}
            >
              Preview Conversion
            </Button>
            {!readOnly && (
              <Button
                intent="primary"
                loading={busyAction}
                onClick={() => runEngineConversion(true)}
              >
                Save Converted Version
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
              label: 'Engines & Type Overrides',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <Select
                      label="Source engine"
                      value={convertDraft.sourceEngine}
                      options={ENGINE_OPTIONS}
                      onChange={(val) =>
                        setConvertDraft((cur) => ({...cur, sourceEngine: val}))
                      }
                    />
                    <Select
                      label="Target engine"
                      value={convertDraft.targetEngine}
                      options={ENGINE_OPTIONS}
                      onChange={(val) =>
                        setConvertDraft((cur) => ({...cur, targetEngine: val}))
                      }
                    />
                  </FormGrid>
                  <KeyValuePairsEditor
                    label="Custom Engine Type Overrides"
                    keyLabel="Logical Type"
                    valueLabel="Target Physical SQL Type"
                    keyPlaceholder="e.g. decimal"
                    valuePlaceholder="e.g. NUMERIC(20,4)"
                    value={convertDraft.customTypeMap}
                    onChange={(next) =>
                      setConvertDraft((cur) => ({...cur, customTypeMap: next}))
                    }
                  />
                  <KeyValuePairsEditor
                    label="Loss Choices"
                    keyLabel="Lossy Item / Element ID"
                    valueLabel="Explicit Conversion Choice"
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
              label: 'DDN Preview & Loss Report',
              render: () =>
                !convertResult ? (
                  <EmptyState message="Click Preview Conversion to inspect mapped physical types, lossy item warnings and DDN output." />
                ) : (
                  <Stack gap="standard">
                    <Banner status="success">
                      Converted to {convertResult.loss_report?.target_engine}{' '}
                      (lossy items:{' '}
                      {convertResult.loss_report?.lossy_count ?? 0})
                    </Banner>
                    <Box sx={{height: 240}}>
                      <CodeEditor
                        label="Converted DDN Preview"
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
        title="Preview ERD alter plan"
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setAlterOpen(false)}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setAlterOpen(false)}>
              Close
            </Button>
            {!readOnly && typeof client.deployErdPlan === 'function' && (
              <Button
                intent="primary"
                loading={busyAction}
                onClick={() => submitAlterToOperationReview()}
              >
                Submit to Native Operation Review
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
              label: 'Differences & 4 Risk Categories',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={3}>
                    <Select
                      label="Target SQL engine"
                      value={alterDraft.targetEngine}
                      options={ENGINE_OPTIONS}
                      onChange={(val) => {
                        setAlterDraft((cur) => ({...cur, targetEngine: val}));
                        loadAlterPlan({targetEngine: val}, selectedDiffs);
                      }}
                    />
                    <Select
                      label="Baseline Mode"
                      value={alterDraft.baselineMode}
                      options={BASELINE_MODE_OPTIONS}
                      onChange={(val) => {
                        setAlterDraft((cur) => ({...cur, baselineMode: val}));
                        loadAlterPlan({baselineMode: val}, undefined);
                      }}
                    />
                    <Select
                      label="Migration Wrapper"
                      value={alterDraft.migrationFormat}
                      options={MIGRATION_FORMAT_OPTIONS}
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
                        aria-label="Risk classification summary"
                        sx={{display: 'flex', flexWrap: 'wrap', gap: 1}}
                      >
                        <StatusBadge
                          status={
                            riskSummary.loses_data > 0 ? 'error' : 'success'
                          }
                          label={`Loses Data: ${riskSummary.loses_data}`}
                        />
                        <StatusBadge
                          status={
                            riskSummary.may_fail_on_existing_data > 0
                              ? 'warning'
                              : 'success'
                          }
                          label={`May Fail on Existing Data: ${riskSummary.may_fail_on_existing_data}`}
                        />
                        <StatusBadge
                          status={
                            riskSummary.breaks_running_clients > 0
                              ? 'error'
                              : 'success'
                          }
                          label={`Breaks Running Clients: ${riskSummary.breaks_running_clients}`}
                        />
                        <StatusBadge
                          status={
                            riskSummary.locks_or_copies_table > 0
                              ? 'warning'
                              : 'success'
                          }
                          label={`Locks / Copies Table: ${riskSummary.locks_or_copies_table}`}
                        />
                      </Box>

                      <ScrollArea
                        label="Detected schema differences"
                        sx={{maxHeight: 220}}
                      >
                        <Box role="group" aria-label="Detected differences">
                          {(alterPlan.differences || []).length === 0 ? (
                            <Box sx={{fontSize: '0.8125rem', py: 0.5}}>
                              No physical schema differences detected.
                            </Box>
                          ) : (
                            <Stack gap="compact">
                              {alterPlan.differences.map((diff) => (
                                <Checkbox
                                  key={diff.difference_id}
                                  label={`${diff.change_kind}: ${diff.object_name}${
                                    diff.destructive ? ' (destructive)' : ''
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
              label: 'Migration SQL Preview',
              render: () => (
                <Stack gap="standard">
                  <Select
                    label="Migration Output Format"
                    value={alterDraft.migrationFormat}
                    options={MIGRATION_FORMAT_OPTIONS}
                    onChange={(val) =>
                      setAlterDraft((cur) => ({...cur, migrationFormat: val}))
                    }
                  />
                  <Box sx={{height: 250}}>
                    <CodeEditor
                      label="Generated change plan (native operation review required)"
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
              label: 'Native Operation Review',
              render: () => (
                <Stack gap="standard">
                  <Banner status="info">
                    Schema changes are queued into ScratchRobin&apos;s
                    OperationBus in <strong>awaiting_approval</strong> state and
                    are never executed directly by the ERD designer.
                  </Banner>
                  <FormGrid columns={3}>
                    <Select
                      label="Target Environment"
                      value={alterDraft.environment}
                      options={[
                        {value: 'dev', label: 'Development'},
                        {value: 'staging', label: 'Staging'},
                        {value: 'prod', label: 'Production'},
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
                      label="Target Endpoint ID"
                      value={alterDraft.endpointId}
                      onChange={(e) =>
                        setAlterDraft((cur) => ({
                          ...cur,
                          endpointId: e.target.value,
                        }))
                      }
                    />
                    <TextField
                      label="Required Approver Principal (optional)"
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
                        Queued Operation <code>{reviewReceipt.operation_id}</code>{' '}
                        in status <strong>{reviewReceipt.status}</strong> (
                        {reviewReceipt.statement_count} statements · applied
                        immediately: {String(reviewReceipt.applied_immediately)}
                        ).
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
        title="System diagram drift and change review"
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setDriftOpen(false)}
        defaultAction={submitDiagramProposal}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setDriftOpen(false)}>
              Close
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => evaluateSystemDrift(liveTopologyRows)}
            >
              Evaluate Drift
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitDiagramProposal}
            >
              Request native review
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
              label: 'Live Topology & Drift',
              render: () => (
                <Stack gap="standard">
                  {driftReport && (
                    <Banner
                      status={driftReport.has_drift ? 'warning' : 'success'}
                    >
                      Drift status:{' '}
                      {driftReport.has_drift ? 'Drift detected' : 'In sync'}{' '}
                      (matched: {driftReport.matched?.length || 0}, missing:{' '}
                      {driftReport.missing_in_live?.length || 0}, property
                      drift: {driftReport.property_drift?.length || 0})
                    </Banner>
                  )}
                  <TypedRowsEditor
                    label="Live Topology Nodes"
                    addLabel="Live Node"
                    rows={liveTopologyRows}
                    columns={[
                      {key: 'id', label: 'Node ID', minWidth: 110},
                      {key: 'host', label: 'Host', minWidth: 120},
                      {
                        key: 'engine',
                        label: 'Engine',
                        type: 'select',
                        options: ENGINE_OPTIONS,
                        minWidth: 110,
                      },
                      {
                        key: 'role',
                        label: 'Role',
                        default: 'primary',
                        minWidth: 95,
                      },
                      {
                        key: 'status',
                        label: 'Status',
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
              label: 'Propose Native Review Change',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={3}>
                    <TextField
                      label="Element ID"
                      value={proposalDraft.elementId}
                      onChange={(e) =>
                        setProposalDraft((cur) => ({
                          ...cur,
                          elementId: e.target.value,
                        }))
                      }
                    />
                    <Select
                      label="Requested topology action"
                      value={proposalDraft.action}
                      options={TOPOLOGY_ACTION_OPTIONS}
                      onChange={(val) =>
                        setProposalDraft((cur) => ({...cur, action: val}))
                      }
                    />
                    <TextField
                      label="Target host / rack"
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
                        Proposal {changeProposal.proposal_id} queued for
                        ScratchRobin native-operation review (applied
                        immediately:{' '}
                        {String(changeProposal.applied_immediately)}).
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
        title="Multi-Target Deployment Environment Matrix"
        size="large"
        busy={busyAction}
        onClose={() => !busyAction && setEnvMatrixOpen(false)}
        actions={
          <Button disabled={busyAction} onClick={() => setEnvMatrixOpen(false)}>
            Close
          </Button>
        }
      >
        <DesignerModalTabs
          formKey="erd-designer-deploy"
          minHeight={240}
          tabs={[
            {
              id: 'matrix',
              label: 'Dev / Staging / Prod Matrix',
              render: () => (
                <Stack gap="standard">
                  {envReceipt && (
                    <Banner status="success">
                      Queued Operation <code>{envReceipt.operation_id}</code>{' '}
                      for approval ({envReceipt.status}).
                    </Banner>
                  )}
                  {environments.length === 0 ? (
                    <EmptyState message="No environment records loaded yet." />
                  ) : (
                    <ScrollArea label="Environment matrix" sx={{maxHeight: 320}}>
                      <Box
                        component="table"
                        aria-label="Deployment environment matrix"
                        sx={{
                          width: '100%',
                          borderCollapse: 'collapse',
                          fontSize: '0.8125rem',
                        }}
                      >
                        <Box component="thead">
                          <Box component="tr">
                            {[
                              'Environment',
                              'Endpoint / Target',
                              'Deployed',
                              'Desired',
                              'Drift Status',
                              'Actions',
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
                                      Queue Review
                                    </Button>
                                    <Button
                                      size="small"
                                      intent="primary"
                                      onClick={() =>
                                        recordVerifiedDeployment(env)
                                      }
                                    >
                                      Record Verified
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
        title="ERD Git Sync & Worktree Link"
        size="medium"
        busy={busyAction}
        onClose={() => !busyAction && setGitOpen(false)}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setGitOpen(false)}>
              Close
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => runGitAction('link')}
            >
              Link Path
            </Button>
            <Button
              disabled={busyAction}
              onClick={() => runGitAction('drift')}
            >
              Check Drift
            </Button>
            {!readOnly && (
              <>
                <Button
                  disabled={busyAction}
                  onClick={() => runGitAction('load')}
                >
                  Load from Git
                </Button>
                <Button
                  intent="primary"
                  loading={busyAction}
                  onClick={() => runGitAction('save')}
                >
                  Save DDN to Git
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
              Git sync state:{' '}
              <strong>
                {gitStatusInfo.sync_state || gitStatusInfo.status || 'updated'}
              </strong>
            </Banner>
          )}
          <FormGrid columns={2}>
            <TextField
              label="Git Repository Worktree Path"
              placeholder="/path/to/repo"
              value={gitDraft.repository}
              onChange={(e) =>
                setGitDraft((cur) => ({...cur, repository: e.target.value}))
              }
            />
            <TextField
              label="Relative DDN File Path"
              value={gitDraft.path}
              onChange={(e) =>
                setGitDraft((cur) => ({...cur, path: e.target.value}))
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
              label="Note / Commit Summary"
              value={gitDraft.note}
              onChange={(e) =>
                setGitDraft((cur) => ({...cur, note: e.target.value}))
              }
            />
          </FormGrid>
          <Checkbox
            label="Create Git commit when saving DDN to repository"
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
  readOnly: PropTypes.bool,
  executeCommand: PropTypes.func,
  onStateChange: PropTypes.func,
  onExport: PropTypes.func,
  onError: PropTypes.func,
};
