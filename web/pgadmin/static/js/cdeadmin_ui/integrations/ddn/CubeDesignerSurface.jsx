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
  return (
    String(raw || '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_]+/g, '_')
      .replace(/^_+|_+$/g, '') || fallback
  );
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
  const [loading, setLoading] = useState(!sessionState.loaded);
  const [surfaceError, setSurfaceError] = useState('');
  const [cubeView, setCubeView] = useState('cube_star');
  const [busyAction, setBusyAction] = useState(false);
  const [activeDrift, setActiveDrift] = useState(null);
  const [appliedInfo, setAppliedInfo] = useState(null);

  // Dimension & role-playing editor form (C2 / C3)
  const [dimOpen, setDimOpen] = useState(false);
  const [dimDraft, setDimDraft] = useState({
    id: '',
    name: '',
    sourceId: '',
    keyField: '',
    nameField: '',
    sortField: '',
    attributesCsv: '',
    roleOf: '',
    active: true,
  });

  // Measure & filtered measure editor form (C2 / C3)
  const [measureOpen, setMeasureOpen] = useState(false);
  const [measureDraft, setMeasureDraft] = useState({
    id: '',
    name: '',
    aggregation: 'sum',
    sourceId: '',
    field: '',
    format: 'number',
    certification: 'draft',
    measureGroupId: '',
    filterField: '',
    filterOperator: '=',
    filterValue: '',
  });

  // Aggregation / materialization rule form (C2 / C3)
  const [aggRuleOpen, setAggRuleOpen] = useState(false);
  const [aggRuleDraft, setAggRuleDraft] = useState({
    id: '',
    name: '',
    measureGroupId: '',
    grainDimensionsCsv: '',
    measuresCsv: '',
    strategy: 'materialized_view',
    targetRelationCsv: '',
    enabled: true,
  });

  // Save checkpoint dialog
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveDraft, setSaveDraft] = useState({
    status: 'draft',
    note: '',
    cubeNotesText: '',
    ddnText: '',
  });

  // Accept (= Apply to Store) dialog
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [acceptDraft, setAcceptDraft] = useState({
    requireGitReview: false,
    gitReviewRef: '',
    endpointId: '',
    targetEngine: 'postgresql',
    comment: '',
  });

  // Leave Accepted dialog (rollback or minor-bump draft)
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [leaveDraft, setLeaveDraft] = useState({
    mode: 'branch_minor_draft',
    targetVersion: '1',
    note: '',
  });

  // Materialization native-operation review dialog
  const [matPlanOpen, setMatPlanOpen] = useState(false);
  const [matEngine, setMatEngine] = useState('postgresql');
  const [matPlan, setMatPlan] = useState(null);

  // Git save/load dialog
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
    async (ver = null) => {
      try {
        const res = await controller.getCubeModel({version: ver});
        if (res?.cube) {
          setCubePayload(res.cube);
        }
      } catch (_err) {
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
        await refreshCubeModel(loaded.currentVersion);
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

  const persistUpdatedModel = async (nextModel, noteText) => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const saved = await controller.saveCubeModel({
        model: nextModel,
        cubeNotes: cubePayload?.notes || [],
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
      return true;
    } catch (err) {
      setSurfaceError(err.message);
      return false;
    } finally {
      setBusyAction(false);
    }
  };

  const openDimensionDialog = () => {
    setDimDraft({
      id: '',
      name: '',
      sourceId: defaultSourceId,
      keyField: '',
      nameField: '',
      sortField: '',
      attributesCsv: '',
      roleOf: '',
      active: true,
    });
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
    const newDim = {
      id: dimId,
      name: trimmedName,
      type: 'categorical',
      field: {source_id: srcId, field: keyCol},
      key_field: {source_id: srcId, field: keyCol},
      hierarchies: [],
      active: Boolean(dimDraft.active),
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
    const attrs = dimDraft.attributesCsv
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((col) => ({
        id: `${dimId}_${slugId(col, 'attr')}`,
        name: col,
        field: {source_id: srcId, field: col},
      }));
    if (attrs.length) {
      newDim.attributes = attrs;
    }
    if (dimDraft.roleOf.trim()) {
      newDim.role_of = dimDraft.roleOf.trim();
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

  const openMeasureDialog = () => {
    setMeasureDraft({
      id: '',
      name: '',
      aggregation: 'sum',
      sourceId: defaultSourceId,
      field: '',
      format: 'number',
      certification: 'draft',
      measureGroupId: cubeModel?.measure_groups?.[0]?.id || '',
      filterField: '',
      filterOperator: '=',
      filterValue: '',
    });
    setMeasureOpen(true);
  };

  const submitMeasure = async () => {
    if (!cubeModel) return;
    const trimmedName = measureDraft.name.trim();
    if (!trimmedName) {
      setSurfaceError('Measure name is required.');
      return;
    }
    const measId = slugId(measureDraft.id || trimmedName, 'measure');
    const srcId = measureDraft.sourceId.trim() || defaultSourceId;
    const fieldName = measureDraft.field.trim();
    const newMeasure = {
      id: measId,
      name: trimmedName,
      aggregation: measureDraft.aggregation,
      format: measureDraft.format.trim() || 'number',
      certification: measureDraft.certification,
      field:
        fieldName || measureDraft.aggregation !== 'count'
          ? {source_id: srcId, field: fieldName || 'id'}
          : null,
    };
    if (measureDraft.measureGroupId.trim()) {
      newMeasure.measure_group_id = measureDraft.measureGroupId.trim();
    }
    if (measureDraft.filterField.trim()) {
      newMeasure.filters = [
        {
          field: {
            source_id: srcId,
            field: measureDraft.filterField.trim(),
          },
          operator: measureDraft.filterOperator,
          value: measureDraft.filterValue,
        },
      ];
    }
    const nextMeasures = [
      ...(cubeModel.measures || []).filter((m) => m.id !== measId),
      newMeasure,
    ];
    const ok = await persistUpdatedModel(
      {...cubeModel, measures: nextMeasures},
      `Saved measure ${trimmedName}`
    );
    if (ok) setMeasureOpen(false);
  };

  const openAggRuleDialog = () => {
    setAggRuleDraft({
      id: '',
      name: '',
      measureGroupId: cubeModel?.measure_groups?.[0]?.id || '',
      grainDimensionsCsv: (cubeModel?.dimensions || [])
        .slice(0, 1)
        .map((d) => d.id)
        .join(', '),
      measuresCsv: (cubeModel?.measures || [])
        .slice(0, 2)
        .map((m) => m.id)
        .join(', '),
      strategy: 'materialized_view',
      targetRelationCsv: '',
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
    const ruleId = slugId(aggRuleDraft.id || trimmedName, 'agg_rule');
    const grain = aggRuleDraft.grainDimensionsCsv
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const meas = aggRuleDraft.measuresCsv
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const relParts = aggRuleDraft.targetRelationCsv
      .split('.')
      .map((s) => s.trim())
      .filter(Boolean);

    const newRule = {
      id: ruleId,
      name: trimmedName,
      strategy: aggRuleDraft.strategy,
      enabled: Boolean(aggRuleDraft.enabled),
      grain_dimensions: grain,
      measures: meas,
      target_relation: relParts.length ? relParts : [`agg_${ruleId}`],
    };
    if (aggRuleDraft.measureGroupId.trim()) {
      newRule.measure_group_id = aggRuleDraft.measureGroupId.trim();
    }
    const nextMats = [
      ...(cubeModel.materializations || []).filter((m) => m.id !== ruleId),
      newRule,
    ];
    const ok = await persistUpdatedModel(
      {...cubeModel, materializations: nextMats},
      `Saved aggregation rule ${trimmedName}`
    );
    if (ok) setAggRuleOpen(false);
  };

  const openSaveDialog = useCallback(() => {
    const ws = sessionState.workspace;
    const entryText = ws?.files?.[ws.entry] || '';
    setSaveDraft({
      status:
        sessionState.status === 'accepted'
          ? 'draft'
          : sessionState.status || 'draft',
      note: '',
      cubeNotesText: (cubePayload?.notes || []).join('\n'),
      ddnText: entryText,
    });
    setSaveOpen(true);
  }, [sessionState, cubePayload]);

  const submitSave = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const notesList = saveDraft.cubeNotesText
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
      const saved = await controller.saveCubeModel({
        ddnText: saveDraft.ddnText,
        cubeNotes: notesList,
        status: saveDraft.status,
        note: saveDraft.note || 'Saved cube checkpoint',
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

  const handleSyncActive = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const res = await controller.syncCubeActive({
        note: 'Merged active cube changes into draft',
      });
      if (res?.merged) {
        if (res.cube) setCubePayload(res.cube);
        setActiveDrift(null);
      } else if (res?.merge?.conflicts?.length) {
        setSurfaceError(
          `Cannot auto-merge ${res.merge.conflicts.length} conflicting cube item(s); reconcile in DDN.`
        );
      }
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
      const accepted = await controller.accept({
        requireGitReview: acceptDraft.requireGitReview,
        gitReviewRef: acceptDraft.gitReviewRef.trim() || null,
        endpointId:
          acceptDraft.endpointId.trim() ||
          cubeModel?.annotations?.semantic_endpoint_id ||
          null,
        targetEngine: acceptDraft.targetEngine,
        comment: acceptDraft.comment.trim(),
      });
      setAppliedInfo(accepted);
      if (accepted?.materialization_review_plan?.has_database_changes) {
        setMatPlan(accepted.materialization_review_plan);
      }
      await refreshCubeModel();
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
            ? Number(leaveDraft.targetVersion || 1)
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

  const openMaterializationPlanDialog = async () => {
    setMatPlanOpen(true);
    setBusyAction(true);
    setSurfaceError('');
    try {
      const plan = await controller.previewCubeMaterializationPlan({
        targetEngine: matEngine,
      });
      setMatPlan(plan);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const refreshMaterializationPlan = async (nextEngine) => {
    setMatEngine(nextEngine);
    setBusyAction(true);
    setSurfaceError('');
    try {
      const plan = await controller.previewCubeMaterializationPlan({
        targetEngine: nextEngine,
      });
      setMatPlan(plan);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const submitGitOperation = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const result = await controller.gitOperation({
        action: gitDraft.action,
        repository: gitDraft.repository.trim(),
        repoRoot: gitDraft.repository.trim(),
        path: gitDraft.path.trim() || `cubes/${designId}.ddn`,
        branch: gitDraft.branch.trim() || 'main',
        commit: Boolean(gitDraft.commit),
        note: gitDraft.note.trim(),
      });
      setGitStatus(result);
      if (gitDraft.action === 'load') {
        await refreshCubeModel();
      }
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const viewerSnapshot = useMemo(() => {
    if (!sessionState.loaded || !sessionState.workspace) return null;
    const view = resolveCubeView(sessionState.workspace, cubeView);
    return {
      ...sessionState.workspace,
      view,
    };
  }, [sessionState, cubeView]);

  const versionLabel =
    cubeModel?.annotations?.cube_version_label || '1.0';

  if (loading) {
    return (
      <Box sx={{position: 'relative', height: '100%', minHeight: 240}}>
        <FormReference formKey="cube-designer" />
        <ProgressOverlay message="Loading cube design" />
      </Box>
    );
  }

  if (!sessionState.loaded) {
    return (
      <Box sx={{height: '100%', p: 2}}>
        <FormReference formKey="cube-designer" />
        <EmptyState
          role="alert"
          message={surfaceError || 'Cube design could not be loaded.'}
          actionLabel="Retry"
          onAction={() => controller.load()}
        />
      </Box>
    );
  }

  return (
    <Box
      component="section"
      aria-label="Cube Designer"
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
      }}
    >
      <FormReference formKey="cube-designer" />
      <Toolbar label="Cube designer commands">
        <Select
          label="Cube DDN view"
          size="small"
          value={cubeView}
          options={CUBE_VIEW_OPTIONS}
          onChange={setCubeView}
        />
        <StatusBadge
          status={sessionState.status === 'accepted' ? 'success' : 'info'}
          label={`v${sessionState.currentVersion} (${sessionState.status}) · cube ${versionLabel}`}
        />
        {!readOnly && (
          <>
            <Button onClick={openDimensionDialog}>Add dimension…</Button>
            <Button onClick={openMeasureDialog}>Add measure…</Button>
            <Button onClick={openAggRuleDialog}>Add aggregation…</Button>
            <Button
              onClick={() =>
                runToolbarCommand('cube.designer.save', openSaveDialog)
              }
            >
              Save checkpoint…
            </Button>
            <Button
              onClick={() =>
                runToolbarCommand(
                  'cube.designer.materialization_plan',
                  openMaterializationPlanDialog
                )
              }
            >
              Materialization plan…
            </Button>
            <Button onClick={() => setGitOpen(true)}>Git…</Button>
            {sessionState.status !== 'accepted' ? (
              <Button
                intent="primary"
                onClick={() =>
                  runToolbarCommand('cube.designer.accept', () =>
                    setAcceptOpen(true)
                  )
                }
              >
                Accept & apply…
              </Button>
            ) : (
              <Button onClick={() => setLeaveOpen(true)}>
                Leave accepted…
              </Button>
            )}
          </>
        )}
      </Toolbar>

      {surfaceError && (
        <Alert severity="error" onClose={() => setSurfaceError('')}>
          {surfaceError}
        </Alert>
      )}

      {activeDrift?.has_active_changes && (
        <Alert
          severity="warning"
          action={
            <Button onClick={handleSyncActive} disabled={busyAction}>
              Sync active changes
            </Button>
          }
        >
          Another accepted cube version modified{' '}
          {activeDrift.active_changes?.length || 1} item(s) since this draft
          branched. Merge the active DDN changes before accepting.
        </Alert>
      )}

      {appliedInfo?.applied_semantic_model && (
        <Alert severity="success" onClose={() => setAppliedInfo(null)}>
          Accepted version applied to semantic-model store (
          {appliedInfo.applied_semantic_model.model_id} rev{' '}
          {appliedInfo.applied_semantic_model.revision}).
        </Alert>
      )}

      <Box sx={{flex: 1, minHeight: 0, position: 'relative'}}>
        {viewerSnapshot && (
          <DDNViewerSurface
            title={sessionState.title}
            snapshot={viewerSnapshot}
            onExport={onExport}
            onError={onError}
          />
        )}
      </Box>

      {/* Dimension & Role-Playing Form (C2 / C3) */}
      <Dialog
        open={dimOpen}
        title="Dimension & role-playing settings"
        size="medium"
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
        <Box sx={{display: 'grid', gap: 2}}>
          <TextField
            label="Dimension name"
            required
            value={dimDraft.name}
            onChange={(e) =>
              setDimDraft((cur) => ({...cur, name: e.target.value}))
            }
          />
          <TextField
            label="Source ID"
            value={dimDraft.sourceId}
            onChange={(e) =>
              setDimDraft((cur) => ({...cur, sourceId: e.target.value}))
            }
          />
          <TextField
            label="Key column"
            required
            value={dimDraft.keyField}
            onChange={(e) =>
              setDimDraft((cur) => ({...cur, keyField: e.target.value}))
            }
          />
          <TextField
            label="Display name column (optional)"
            value={dimDraft.nameField}
            onChange={(e) =>
              setDimDraft((cur) => ({...cur, nameField: e.target.value}))
            }
          />
          <TextField
            label="Sort column (optional)"
            value={dimDraft.sortField}
            onChange={(e) =>
              setDimDraft((cur) => ({...cur, sortField: e.target.value}))
            }
          />
          <TextField
            label="Attribute columns (comma-separated)"
            value={dimDraft.attributesCsv}
            onChange={(e) =>
              setDimDraft((cur) => ({...cur, attributesCsv: e.target.value}))
            }
          />
          <TextField
            label="Role-playing base dimension ID (optional)"
            value={dimDraft.roleOf}
            onChange={(e) =>
              setDimDraft((cur) => ({...cur, roleOf: e.target.value}))
            }
          />
          <Checkbox
            label="Active relationship (uncheck for inactive role-playing join)"
            checked={dimDraft.active}
            onChange={(checked) =>
              setDimDraft((cur) => ({...cur, active: checked}))
            }
          />
        </Box>
      </Dialog>

      {/* Measure & Filtered Measure Form (C2 / C3) */}
      <Dialog
        open={measureOpen}
        title="Measure & filtered-measure settings"
        size="medium"
        onClose={() => !busyAction && setMeasureOpen(false)}
        busy={busyAction}
        defaultAction={submitMeasure}
        actions={
          <>
            <Button
              disabled={busyAction}
              onClick={() => setMeasureOpen(false)}
            >
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
        <Box sx={{display: 'grid', gap: 2}}>
          <TextField
            label="Measure name"
            required
            value={measureDraft.name}
            onChange={(e) =>
              setMeasureDraft((cur) => ({...cur, name: e.target.value}))
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
            label="Source ID"
            value={measureDraft.sourceId}
            onChange={(e) =>
              setMeasureDraft((cur) => ({...cur, sourceId: e.target.value}))
            }
          />
          <TextField
            label="Measure column"
            value={measureDraft.field}
            onChange={(e) =>
              setMeasureDraft((cur) => ({...cur, field: e.target.value}))
            }
          />
          <TextField
            label="Format"
            value={measureDraft.format}
            onChange={(e) =>
              setMeasureDraft((cur) => ({...cur, format: e.target.value}))
            }
          />
          <TextField
            label="Filter column (optional filtered measure)"
            value={measureDraft.filterField}
            onChange={(e) =>
              setMeasureDraft((cur) => ({...cur, filterField: e.target.value}))
            }
          />
          <TextField
            label="Filter value"
            value={measureDraft.filterValue}
            onChange={(e) =>
              setMeasureDraft((cur) => ({...cur, filterValue: e.target.value}))
            }
          />
        </Box>
      </Dialog>

      {/* Aggregation / Materialization Rule Form (C2 / C3) */}
      <Dialog
        open={aggRuleOpen}
        title="Aggregation / materialization rule"
        size="medium"
        onClose={() => !busyAction && setAggRuleOpen(false)}
        busy={busyAction}
        defaultAction={submitAggRule}
        actions={
          <>
            <Button
              disabled={busyAction}
              onClick={() => setAggRuleOpen(false)}
            >
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
        <Box sx={{display: 'grid', gap: 2}}>
          <TextField
            label="Rule name"
            required
            value={aggRuleDraft.name}
            onChange={(e) =>
              setAggRuleDraft((cur) => ({...cur, name: e.target.value}))
            }
          />
          <TextField
            label="Grain dimension IDs (comma-separated)"
            value={aggRuleDraft.grainDimensionsCsv}
            onChange={(e) =>
              setAggRuleDraft((cur) => ({
                ...cur,
                grainDimensionsCsv: e.target.value,
              }))
            }
          />
          <TextField
            label="Measure IDs (comma-separated)"
            value={aggRuleDraft.measuresCsv}
            onChange={(e) =>
              setAggRuleDraft((cur) => ({...cur, measuresCsv: e.target.value}))
            }
          />
          <TextField
            label="Target relation (schema.table)"
            value={aggRuleDraft.targetRelationCsv}
            onChange={(e) =>
              setAggRuleDraft((cur) => ({
                ...cur,
                targetRelationCsv: e.target.value,
              }))
            }
          />
          <Checkbox
            label="Enable pre-aggregation materialization"
            checked={aggRuleDraft.enabled}
            onChange={(checked) =>
              setAggRuleDraft((cur) => ({...cur, enabled: checked}))
            }
          />
        </Box>
      </Dialog>

      {/* Save Cube Checkpoint Dialog */}
      <Dialog
        open={saveOpen}
        title="Save cube checkpoint"
        size="large"
        onClose={() => !busyAction && setSaveOpen(false)}
        busy={busyAction}
        defaultAction={submitSave}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setSaveOpen(false)}>
              Cancel
            </Button>
            <Button intent="primary" loading={busyAction} onClick={submitSave}>
              Save checkpoint
            </Button>
          </>
        }
      >
        <Box sx={{display: 'grid', gap: 2}}>
          <Select
            label="Save-point status"
            value={saveDraft.status}
            options={[
              {value: 'draft', label: 'Draft (does not change active store)'},
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
          <TextArea
            label="Cube DDN notes (one per line)"
            rows={3}
            value={saveDraft.cubeNotesText}
            onChange={(e) =>
              setSaveDraft((cur) => ({...cur, cubeNotesText: e.target.value}))
            }
          />
          <TextArea
            label="Cube DDN source"
            rows={8}
            value={saveDraft.ddnText}
            onChange={(e) =>
              setSaveDraft((cur) => ({...cur, ddnText: e.target.value}))
            }
          />
        </Box>
      </Dialog>

      {/* Accept & Apply to Semantic Store Dialog */}
      <Dialog
        open={acceptOpen}
        title="Accept cube version (apply to semantic-model store)"
        size="medium"
        onClose={() => !busyAction && setAcceptOpen(false)}
        busy={busyAction}
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
              Accept & apply
            </Button>
          </>
        }
      >
        <Box sx={{display: 'grid', gap: 2}}>
          <Alert severity="info">
            Accepting makes this version the active cube in the ScratchRobin
            semantic-model store. Any materialized aggregate DDL is routed
            exclusively through native-operation review.
          </Alert>
          <TextField
            label="Target semantic-store endpoint ID"
            value={acceptDraft.endpointId}
            onChange={(e) =>
              setAcceptDraft((cur) => ({...cur, endpointId: e.target.value}))
            }
          />
          <Select
            label="Target engine for materialization review"
            value={acceptDraft.targetEngine}
            options={ENGINE_OPTIONS}
            onChange={(val) =>
              setAcceptDraft((cur) => ({...cur, targetEngine: val}))
            }
          />
          <Checkbox
            label="Require Git review reference"
            checked={acceptDraft.requireGitReview}
            onChange={(checked) =>
              setAcceptDraft((cur) => ({
                ...cur,
                requireGitReview: checked,
              }))
            }
          />
          {acceptDraft.requireGitReview && (
            <TextField
              label="Git review reference"
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
        </Box>
      </Dialog>

      {/* Leave Accepted Dialog */}
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
        <Box sx={{display: 'grid', gap: 2}}>
          <Select
            label="Action"
            value={leaveDraft.mode}
            options={[
              {
                value: 'branch_minor_draft',
                label: 'Force new draft version with minor version bump',
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
          <TextField
            label="Reason / note"
            value={leaveDraft.note}
            onChange={(e) =>
              setLeaveDraft((cur) => ({...cur, note: e.target.value}))
            }
          />
        </Box>
      </Dialog>

      {/* Materialized Aggregate Native-Operation Review Dialog */}
      <Dialog
        open={matPlanOpen}
        title="Materialized aggregate native-operation review"
        size="large"
        onClose={() => !busyAction && setMatPlanOpen(false)}
        busy={busyAction}
        actions={
          <Button onClick={() => setMatPlanOpen(false)}>Close</Button>
        }
      >
        <Box sx={{display: 'grid', gap: 2}}>
          <Select
            label="Target database engine"
            value={matEngine}
            options={ENGINE_OPTIONS}
            onChange={(val) => refreshMaterializationPlan(val)}
          />
          {matPlan && (
            <>
              <Alert severity="warning">{matPlan.destructive_warning}</Alert>
              <TextArea
                label="Native-operation review SQL preview (not executed automatically)"
                rows={8}
                readOnly
                value={
                  matPlan.sql_preview ||
                  '-- No materialized aggregate database changes.'
                }
              />
            </>
          )}
        </Box>
      </Dialog>

      {/* Git Save / Load Dialog */}
      <Dialog
        open={gitOpen}
        title="Cube Git DDN sync"
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
              Run Git operation
            </Button>
          </>
        }
      >
        <Box sx={{display: 'grid', gap: 2}}>
          <Select
            label="Git action"
            value={gitDraft.action}
            options={[
              {value: 'save', label: 'Save DDN to Git'},
              {value: 'load', label: 'Load DDN from Git'},
              {value: 'drift', label: 'Check Git drift'},
            ]}
            onChange={(val) =>
              setGitDraft((cur) => ({...cur, action: val}))
            }
          />
          <TextField
            label="Repository path"
            value={gitDraft.repository}
            onChange={(e) =>
              setGitDraft((cur) => ({...cur, repository: e.target.value}))
            }
          />
          <TextField
            label="DDN file path in repository"
            value={gitDraft.path}
            placeholder={`cubes/${designId}.ddn`}
            onChange={(e) =>
              setGitDraft((cur) => ({...cur, path: e.target.value}))
            }
          />
          {gitDraft.action === 'save' && (
            <Checkbox
              label="Create Git commit after writing DDN"
              checked={gitDraft.commit}
              onChange={(checked) =>
                setGitDraft((cur) => ({...cur, commit: checked}))
              }
            />
          )}
          {gitStatus && (
            <Alert severity="info">
              Git sync state: {gitStatus.sync_state || 'updated'}
            </Alert>
          )}
        </Box>
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
