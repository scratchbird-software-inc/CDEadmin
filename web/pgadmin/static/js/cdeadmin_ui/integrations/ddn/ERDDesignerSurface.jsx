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

const ENGINE_OPTIONS = Object.freeze([
  {value: 'sqlite', label: 'SQLite'},
  {value: 'duckdb', label: 'DuckDB'},
  {value: 'firebird', label: 'Firebird 5'},
  {value: 'mysql', label: 'MySQL'},
  {value: 'mariadb', label: 'MariaDB'},
]);

function resolveViewForLevel(workspace, level) {
  if (!workspace?.files) return workspace?.view || '';
  const target = LEVEL_OPTIONS.find((opt) => opt.value === level)?.viewId;
  if (!target) return workspace.view;
  const entryText = workspace.files[workspace.entry] || '';
  if (entryText.includes(`view "${target}"`) || entryText.includes(`view ${target}`)) {
    return target;
  }
  return workspace.view;
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
  const [level, setLevel] = useState('all');

  // Save checkpoint dialog state
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveDraft, setSaveDraft] = useState({
    status: 'draft',
    note: '',
    ddnText: '',
  });
  const [busyAction, setBusyAction] = useState(false);

  // Accept version dialog state (A9)
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [acceptDraft, setAcceptDraft] = useState({
    requireGitReview: false,
    gitReviewRef: '',
    comment: '',
  });

  // Engine conversion dialog state (D4)
  const [convertOpen, setConvertOpen] = useState(false);
  const [convertDraft, setConvertDraft] = useState({
    sourceEngine: 'firebird',
    targetEngine: 'sqlite',
    customTypeMapJson: '{}',
    lossChoicesJson: '{}',
    saveVersion: true,
  });
  const [convertResult, setConvertResult] = useState(null);

  // Alter-plan preview dialog state (Role 4 Modification)
  const [alterOpen, setAlterOpen] = useState(false);
  const [alterEngine, setAlterEngine] = useState('sqlite');
  const [alterPlan, setAlterPlan] = useState(null);
  const [selectedDiffs, setSelectedDiffs] = useState([]);

  // System diagram drift & change proposal dialog state (D1)
  const [driftOpen, setDriftOpen] = useState(false);
  const [driftReport, setDriftReport] = useState(null);
  const [changeProposal, setChangeProposal] = useState(null);
  const [proposalDraft, setProposalDraft] = useState({
    elementId: '',
    action: 'relocate_replica',
    targetHost: '',
  });

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
      .then((loaded) => {
        if (!active) return;
        setSessionState(loaded);
        setLoading(false);
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
  }, [controller]);

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

  const openSaveDialog = useCallback(() => {
    const ws = sessionState.workspace;
    const entryText = ws?.files?.[ws.entry] || '';
    setSaveDraft({
      status:
        sessionState.status === 'accepted' ? 'draft' : sessionState.status || 'draft',
      note: '',
      ddnText: entryText,
    });
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
      });
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
      setAcceptOpen(false);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const submitConvert = async () => {
    setBusyAction(true);
    setSurfaceError('');
    try {
      const customTypeMap = JSON.parse(convertDraft.customTypeMapJson || '{}');
      const lossChoices = JSON.parse(convertDraft.lossChoicesJson || '{}');
      const res = await controller.convertErdEngine({
        sourceEngine: convertDraft.sourceEngine,
        targetEngine: convertDraft.targetEngine,
        customTypeMap: Object.keys(customTypeMap).length ? customTypeMap : null,
        lossChoices: Object.keys(lossChoices).length ? lossChoices : null,
        strict: true,
        saveVersion: convertDraft.saveVersion,
      });
      setConvertResult(res);
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  };

  const loadAlterPlan = useCallback(
    async (engineName, diffIds = null) => {
      setBusyAction(true);
      setSurfaceError('');
      try {
        const plan = await controller.previewErdAlterPlan({
          targetEngine: engineName,
          selectedDifferenceIds: diffIds,
        });
        setAlterPlan(plan);
        setSelectedDiffs(plan.selected_difference_ids || []);
      } catch (err) {
        setSurfaceError(err.message);
      } finally {
        setBusyAction(false);
      }
    },
    [controller]
  );

  const openAlterDialog = useCallback(() => {
    setAlterOpen(true);
    loadAlterPlan(alterEngine, null);
  }, [alterEngine, loadAlterPlan]);

  const toggleDifference = (diffId, checked) => {
    const next = checked
      ? [...new Set([...selectedDiffs, diffId])]
      : selectedDiffs.filter((id) => id !== diffId);
    setSelectedDiffs(next);
    loadAlterPlan(alterEngine, next);
  };

  const openDriftDialog = useCallback(async () => {
    setDriftOpen(true);
    setChangeProposal(null);
    setBusyAction(true);
    try {
      const report = await controller.computeErdDrift({liveNodes: []});
      setDriftReport(report);
      const firstNode = sessionState.layout?.nodes?.[0]?.id || '';
      setProposalDraft((cur) => ({...cur, elementId: cur.elementId || firstNode}));
    } catch (err) {
      setSurfaceError(err.message);
    } finally {
      setBusyAction(false);
    }
  }, [controller, sessionState.layout]);

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

  const suspectBindings = useMemo(
    () =>
      (sessionState.bindings || []).filter((item) => item.state === 'suspect'),
    [sessionState.bindings]
  );

  const activeView = useMemo(
    () => resolveViewForLevel(sessionState.workspace, level),
    [sessionState.workspace, level]
  );

  return (
    <Box
      data-cde-surface="diagram.erd.designer"
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="erd-designer" />
      <Toolbar label="ERD designer commands">
        <Select
          label="Modelling level"
          size="small"
          value={level}
          options={LEVEL_OPTIONS}
          onChange={setLevel}
        />
        {!readOnly && (
          <>
            <Button
              disabled={!sessionState.loaded}
              onClick={() =>
                runToolbarCommand('erd.designer.save', openSaveDialog)
              }
            >
              Save checkpoint…
            </Button>
            <Button
              disabled={!sessionState.loaded}
              onClick={() =>
                runToolbarCommand('erd.designer.convert', () => {
                  setConvertResult(null);
                  setConvertOpen(true);
                })
              }
            >
              Convert engine…
            </Button>
            <Button
              disabled={!sessionState.loaded}
              onClick={() =>
                runToolbarCommand('erd.designer.alter_plan', openAlterDialog)
              }
            >
              Preview alter plan…
            </Button>
            <Button
              disabled={!sessionState.loaded}
              onClick={() =>
                runToolbarCommand('erd.designer.accept', () =>
                  setAcceptOpen(true)
                )
              }
            >
              Accept version…
            </Button>
            {sessionState.activeVersion && (
              <Button
                disabled={!sessionState.loaded || busyAction}
                onClick={() => controller.branchDraft({note: 'Branched draft'})}
              >
                Branch draft
              </Button>
            )}
          </>
        )}
        <Button disabled={!sessionState.loaded} onClick={openDriftDialog}>
          System drift…
        </Button>
        {sessionState.loaded && (
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
        )}
      </Toolbar>

      {surfaceError && (
        <Alert severity="error" role="alert">
          {surfaceError}
        </Alert>
      )}

      {suspectBindings.length > 0 && (
        <Alert severity="warning" data-testid="erd-suspect-bindings">
          <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center'}}>
            <span>
              {suspectBindings.length} catalog binding(s) marked suspect after a
              rename or drop:
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
        </Alert>
      )}

      <Box sx={{position: 'relative', flex: 1, minHeight: 0, overflow: 'hidden'}}>
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
            executeCommand={executeCommand}
            onExport={onExport}
            onError={onError}
          />
        )}
        <ProgressOverlay message={loading ? 'Loading ERD design' : ''} />
      </Box>

      {/* Save checkpoint dialog */}
      <Dialog
        open={saveOpen}
        title="Save ERD checkpoint"
        size="medium"
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
        <Box sx={{display: 'grid', gap: 2}}>
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
          <TextArea
            label="DDN source"
            rows={8}
            value={saveDraft.ddnText}
            onChange={(e) =>
              setSaveDraft((cur) => ({...cur, ddnText: e.target.value}))
            }
          />
        </Box>
      </Dialog>

      {/* Accept version dialog (A9) */}
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
        <Box sx={{display: 'grid', gap: 2}}>
          <Checkbox
            label="Require Git review reference for this project"
            checked={acceptDraft.requireGitReview}
            onChange={(checked) =>
              setAcceptDraft((cur) => ({...cur, requireGitReview: checked}))
            }
          />
          <TextField
            label="Git review reference"
            value={acceptDraft.gitReviewRef}
            onChange={(e) =>
              setAcceptDraft((cur) => ({...cur, gitReviewRef: e.target.value}))
            }
          />
          <TextField
            label="Approval comment"
            value={acceptDraft.comment}
            onChange={(e) =>
              setAcceptDraft((cur) => ({...cur, comment: e.target.value}))
            }
          />
        </Box>
      </Dialog>

      {/* Engine conversion dialog (D4) */}
      <Dialog
        open={convertOpen}
        title="Convert ERD engine"
        size="medium"
        busy={busyAction}
        onClose={() => !busyAction && setConvertOpen(false)}
        defaultAction={submitConvert}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setConvertOpen(false)}>
              Close
            </Button>
            <Button
              intent="primary"
              loading={busyAction}
              onClick={submitConvert}
            >
              Convert model
            </Button>
          </>
        }
      >
        <Box sx={{display: 'grid', gap: 2}}>
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
          <TextArea
            label="Custom logical-to-physical type map (JSON)"
            rows={3}
            value={convertDraft.customTypeMapJson}
            onChange={(e) =>
              setConvertDraft((cur) => ({
                ...cur,
                customTypeMapJson: e.target.value,
              }))
            }
          />
          <TextArea
            label="Explicit lossy item choices (JSON)"
            rows={3}
            value={convertDraft.lossChoicesJson}
            onChange={(e) =>
              setConvertDraft((cur) => ({
                ...cur,
                lossChoicesJson: e.target.value,
              }))
            }
          />
          <Checkbox
            label="Save converted model as new checkpoint"
            checked={convertDraft.saveVersion}
            onChange={(checked) =>
              setConvertDraft((cur) => ({...cur, saveVersion: checked}))
            }
          />
          {convertResult && (
            <Alert severity="success">
              Converted to {convertResult.loss_report?.target_engine} (lossy
              items: {convertResult.loss_report?.lossy_count ?? 0})
            </Alert>
          )}
        </Box>
      </Dialog>

      {/* Alter-plan preview dialog (Role 4 Modification) */}
      <Dialog
        open={alterOpen}
        title="Preview ERD alter plan"
        size="medium"
        busy={busyAction}
        onClose={() => !busyAction && setAlterOpen(false)}
        actions={
          <Button disabled={busyAction} onClick={() => setAlterOpen(false)}>
            Close
          </Button>
        }
      >
        <Box sx={{display: 'grid', gap: 2}}>
          <Select
            label="Target SQL engine"
            value={alterEngine}
            options={ENGINE_OPTIONS}
            onChange={(val) => {
              setAlterEngine(val);
              loadAlterPlan(val, selectedDiffs);
            }}
          />
          {alterPlan && (
            <>
              <Alert severity="warning" data-testid="erd-destructive-warning">
                {alterPlan.destructive_warning}
              </Alert>
              <Box role="group" aria-label="Detected differences">
                {(alterPlan.differences || []).length === 0 ? (
                  <div>No physical schema differences detected.</div>
                ) : (
                  alterPlan.differences.map((diff) => (
                    <Checkbox
                      key={diff.difference_id}
                      label={`${diff.change_kind}: ${diff.object_name}${
                        diff.destructive ? ' (destructive)' : ''
                      }`}
                      checked={selectedDiffs.includes(diff.difference_id)}
                      onChange={(checked) =>
                        toggleDifference(diff.difference_id, checked)
                      }
                    />
                  ))
                )}
              </Box>
              <TextArea
                label="Generated change plan (native operation review required)"
                rows={6}
                value={alterPlan.script || ''}
                InputProps={{readOnly: true}}
              />
            </>
          )}
        </Box>
      </Dialog>

      {/* System diagram drift & proposal dialog (D1) */}
      <Dialog
        open={driftOpen}
        title="System diagram drift and change review"
        size="medium"
        busy={busyAction}
        onClose={() => !busyAction && setDriftOpen(false)}
        defaultAction={submitDiagramProposal}
        actions={
          <>
            <Button disabled={busyAction} onClick={() => setDriftOpen(false)}>
              Close
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
        <Box sx={{display: 'grid', gap: 2}}>
          {driftReport && (
            <Alert severity={driftReport.has_drift ? 'warning' : 'success'}>
              Drift status:{' '}
              {driftReport.has_drift ? 'Drift detected' : 'In sync'} (matched:{' '}
              {driftReport.matched?.length || 0}, missing:{' '}
              {driftReport.missing_in_live?.length || 0}, property drift:{' '}
              {driftReport.property_drift?.length || 0})
            </Alert>
          )}
          <TextField
            label="Element ID"
            value={proposalDraft.elementId}
            onChange={(e) =>
              setProposalDraft((cur) => ({...cur, elementId: e.target.value}))
            }
          />
          <TextField
            label="Requested topology action"
            value={proposalDraft.action}
            onChange={(e) =>
              setProposalDraft((cur) => ({...cur, action: e.target.value}))
            }
          />
          <TextField
            label="Target host / rack"
            value={proposalDraft.targetHost}
            onChange={(e) =>
              setProposalDraft((cur) => ({...cur, targetHost: e.target.value}))
            }
          />
          {changeProposal && (
            <Alert severity="info" data-testid="erd-change-proposal">
              Proposal {changeProposal.proposal_id} queued for ScratchRobin
              native-operation review (applied immediately:{' '}
              {String(changeProposal.applied_immediately)}).
            </Alert>
          )}
        </Box>
      </Dialog>
    </Box>
  );
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
