/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Checkbox, Select} from '../../primitives/Choice';
import {NumberField, TextArea, TextField} from '../../primitives/Field';
import {Toolbar} from '../../layout/WorkbenchChrome';
import {Dialog} from '../../overlays/Dialog';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import {StatusBadge} from '../../status/StatusBadge';
import FormReference from '../../navigation/FormReference';
import {DDNViewerSurface} from './DDNViewerSurface';
import {
  DesignStoreClient,
  SharedDDNTaskController,
} from './sharedDesignLibrary';

export const SCREEN_MESH_CONTROL_ROLE_OPTIONS = Object.freeze([
  {value: 'ui.grid', label: 'Data Grid (ui.grid)'},
  {value: 'ui.dropdown', label: 'Dropdown Select (ui.dropdown)'},
  {value: 'ui.radio', label: 'Radio Choice (ui.radio)'},
  {value: 'ui.tabs', label: 'Tab Bar (ui.tabs)'},
  {value: 'ui.input', label: 'Text Input (ui.input)'},
  {value: 'ui.button', label: 'Button (ui.button)'},
  {value: 'ui.checkbox', label: 'Checkbox (ui.checkbox)'},
  {value: 'ui.list', label: 'List Box (ui.list)'},
  {value: 'ui.label', label: 'Label (ui.label)'},
  {value: 'ui.image', label: 'Image Placeholder (ui.image)'},
]);

export const SCREEN_MESH_BINDING_KIND_OPTIONS = Object.freeze([
  {value: 'column', label: 'Catalog Column'},
  {value: 'table', label: 'Catalog Table / View'},
  {value: 'question', label: 'BI Question'},
  {value: 'dashboard', label: 'BI Dashboard'},
  {value: 'cube', label: 'Semantic Cube / Measure'},
  {value: 'sql_query', label: 'Named SQL Query'},
  {value: 'diagram', label: 'Diagram Element'},
  {value: 'screen', label: 'Screen Reference'},
]);

export const SCREEN_MESH_ACCESS_OPTIONS = Object.freeze([
  {value: 'read', label: 'Read-only display (read)'},
  {value: 'write', label: 'Input write target (write)'},
  {value: 'read_write', label: 'Read & write (read_write)'},
]);

export const SCREEN_MESH_TRIGGER_OPTIONS = Object.freeze([
  {value: 'click', label: 'Click'},
  {value: 'hover', label: 'Hover'},
  {value: 'delay', label: 'Timed delay'},
]);

export const SCREEN_MESH_ACTION_OPTIONS = Object.freeze([
  {value: 'navigate', label: 'Navigate to screen'},
  {value: 'overlay', label: 'Open modal / overlay screen'},
  {value: 'back', label: 'Navigate back'},
  {value: 'url', label: 'External reference URL'},
]);

function badgeStatus(status) {
  if (status === 'accepted') return 'success';
  if (status === 'in_review') return 'warning';
  if (status === 'in_progress') return 'information';
  return 'neutral';
}

function nextWorkflowStatus(currentStatus) {
  if (currentStatus === 'draft') return 'in_progress';
  if (currentStatus === 'in_progress') return 'in_review';
  return null;
}

function resolveMeshView(workspace, requestedView) {
  if (!workspace?.files) return workspace?.view || 'screen_mesh_main';
  const entryText = workspace.files[workspace.entry] || '';
  if (
    requestedView &&
    (entryText.includes(`view "${requestedView}"`) ||
      entryText.includes(`view ${requestedView}`))
  ) {
    return requestedView;
  }
  return workspace.view || 'screen_mesh_main';
}

function parseCsvList(raw) {
  return String(raw || '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

export function ScreenMeshDesignerSurface({
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
        kind: 'screen',
      }),
    [suppliedController, client, projectId, designId]
  );

  const [sessionState, setSessionState] = useState(() => controller.state());
  const [meshPayload, setMeshPayload] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyMessage, setBusyMessage] = useState('');
  const [error, setError] = useState('');
  const [bannerInfo, setBannerInfo] = useState('');
  const [selectedView, setSelectedView] = useState('screen_mesh_main');

  // Dialog states
  const [screenDialogOpen, setScreenDialogOpen] = useState(false);
  const [newScreen, setNewScreen] = useState({
    name: '',
    width: '960',
    height: '640',
    formReference: '',
  });

  const [controlDialogOpen, setControlDialogOpen] = useState(false);
  const [newControl, setNewControl] = useState({
    screenId: '',
    role: 'ui.grid',
    name: '',
    columnsCsv: 'id, name, status',
    optionsCsv: 'Option A, Option B',
    placeholder: '',
    checked: false,
  });

  const [regionDialogOpen, setRegionDialogOpen] = useState(false);
  const [newRegion, setNewRegion] = useState({
    screenId: '',
    name: '',
    x: '24',
    y: '24',
    width: '240',
    height: '64',
  });

  const [bindingDialogOpen, setBindingDialogOpen] = useState(false);
  const [newBinding, setNewBinding] = useState({
    sourceId: '',
    columnId: '',
    targetKind: 'column',
    targetRef: '',
    accessMode: 'read',
  });

  const [navDialogOpen, setNavDialogOpen] = useState(false);
  const [newNav, setNewNav] = useState({
    fromId: '',
    toScreenId: '',
    trigger: 'click',
    action: 'navigate',
    label: '',
  });

  const [screenshotDialogOpen, setScreenshotDialogOpen] = useState(false);
  const [screenshotForm, setScreenshotForm] = useState({
    screenId: '',
    mediaType: 'image/png',
    imageBase64: '',
  });

  const [redactDialogOpen, setRedactDialogOpen] = useState(false);
  const [redactForm, setRedactForm] = useState({
    screenId: '',
    x: '16',
    y: '16',
    width: '160',
    height: '40',
  });

  const [usageDialogOpen, setUsageDialogOpen] = useState(false);
  const [usageFilter, setUsageFilter] = useState('');
  const [usageResults, setUsageResults] = useState([]);

  const [acceptDialogOpen, setAcceptDialogOpen] = useState(false);
  const [acceptForm, setAcceptForm] = useState({
    requireGitReview: false,
    gitReviewRef: '',
    comment: '',
  });

  const [gitDialogOpen, setGitDialogOpen] = useState(false);
  const [gitForm, setGitForm] = useState({
    action: 'save',
    repoRoot: '',
    path: '',
    branch: 'main',
    note: '',
  });

  const loadAll = useCallback(
    async (version = null) => {
      setLoading(true);
      setError('');
      try {
        const nextSession = await controller.load({version});
        const hydrated = await controller.getScreenMeshModel({
          version: nextSession.currentVersion,
        });
        setSessionState(nextSession);
        setMeshPayload(hydrated);
        setDirty(false);
        onStateChange?.({
          ...nextSession,
          suspectBindingCount: hydrated.suspect_binding_count ?? 0,
        });
      } catch (loadErr) {
        const msg = loadErr?.message || 'Failed to load Screen Mesh.';
        setError(msg);
        onError?.(loadErr);
      } finally {
        setLoading(false);
      }
    },
    [controller, onStateChange, onError]
  );

  useEffect(() => {
    const unsub = controller.subscribe((next) => setSessionState(next));
    loadAll();
    return unsub;
  }, [controller, loadAll]);

  const mesh = meshPayload?.mesh ?? null;
  const screens = mesh?.screens ?? [];
  const controls = mesh?.controls ?? [];
  const regions = mesh?.regions ?? [];
  const bindings = mesh?.bindings ?? [];
  const navigations = mesh?.navigations ?? [];
  const suspectCount = meshPayload?.suspect_binding_count ?? 0;

  const viewOptions = useMemo(() => {
    const opts = [
      {value: 'screen_mesh_main', label: 'Wireframe & Data Bindings'},
    ];
    if (screens.length > 1) {
      screens.forEach((scr, idx) => {
        opts.push({
          value: `screen_${idx + 1}`,
          label: `Screen ${idx + 1}: ${scr.name}`,
        });
      });
    }
    opts.push({
      value: 'screen_flow',
      label: 'Screen-to-Screen Flow (navigation)',
    });
    return opts;
  }, [screens]);

  const viewerSnapshot = useMemo(() => {
    if (!sessionState.loaded || !sessionState.workspace) return null;
    const resolvedView = resolveMeshView(sessionState.workspace, selectedView);
    return {
      ...sessionState.workspace,
      view: resolvedView,
    };
  }, [sessionState, selectedView]);

  const screenOptions = useMemo(
    () => screens.map((s) => ({value: s.id, label: s.name})),
    [screens]
  );

  const bindableSourceOptions = useMemo(() => {
    const list = [];
    screens.forEach((s) =>
      list.push({value: s.id, label: `Screen: ${s.name}`})
    );
    controls.forEach((c) =>
      list.push({value: c.id, label: `${c.role}: ${c.name}`})
    );
    regions.forEach((r) =>
      list.push({value: r.id, label: `ui.region: ${r.name}`})
    );
    return list;
  }, [screens, controls, regions]);

  const updateDraftMesh = useCallback((mutator) => {
    setMeshPayload((prev) => {
      if (!prev?.mesh) return prev;
      const nextMesh = mutator({
        ...prev.mesh,
        screens: [...(prev.mesh.screens || [])],
        controls: [...(prev.mesh.controls || [])],
        regions: [...(prev.mesh.regions || [])],
        bindings: [...(prev.mesh.bindings || [])],
        navigations: [...(prev.mesh.navigations || [])],
      });
      return {...prev, mesh: nextMesh};
    });
    setDirty(true);
  }, []);

  const handleSaveCheckpoint = useCallback(async () => {
    if (!mesh) return;
    setBusyMessage('Saving Screen Mesh checkpoint');
    setError('');
    try {
      const saved = await controller.saveScreenMeshModel({
        mesh,
        status:
          sessionState.status === 'accepted' ? 'draft' : sessionState.status,
        note: 'Saved Screen Mesh checkpoint',
      });
      setMeshPayload(saved);
      setDirty(false);
      setBannerInfo(
        `Saved Screen Mesh checkpoint v${saved.design.version.version}.`
      );
      onStateChange?.({
        ...controller.state(),
        suspectBindingCount: saved.suspect_binding_count ?? 0,
      });
    } catch (saveErr) {
      setError(saveErr.message);
      onError?.(saveErr);
    } finally {
      setBusyMessage('');
    }
  }, [controller, mesh, sessionState.status, onStateChange, onError]);

  const handleAdvanceStatus = useCallback(async () => {
    const next = nextWorkflowStatus(sessionState.status);
    if (!next) return;
    setBusyMessage(`Advancing status to ${next}`);
    setError('');
    try {
      const updated = await controller.advanceStatus(next);
      setSessionState(updated);
      setBannerInfo(`Advanced save point to ${next}.`);
    } catch (advErr) {
      setError(advErr.message);
    } finally {
      setBusyMessage('');
    }
  }, [controller, sessionState.status]);

  const handleAddScreen = () => {
    const trimmed = newScreen.name.trim();
    if (!trimmed) {
      setError('Screen name is required.');
      return;
    }
    const tempId = `019a0000-0000-7000-8000-${String(Date.now())
      .slice(-12)
      .padStart(12, '0')}`;
    updateDraftMesh((cur) => ({
      ...cur,
      screens: [
        ...cur.screens,
        {
          id: tempId,
          name: trimmed,
          width: Math.max(120, Number(newScreen.width) || 960),
          height: Math.max(80, Number(newScreen.height) || 640),
          form_reference: newScreen.formReference.trim(),
          screenshot_path: '',
          screenshot_sha256: '',
          notes: '',
        },
      ],
    }));
    setScreenDialogOpen(false);
  };

  const handleAddControl = () => {
    const trimmed = newControl.name.trim();
    if (!trimmed) {
      setError('Control label is required.');
      return;
    }
    const targetScreenId = newControl.screenId || screens[0]?.id || '';
    const tempId = `019b0000-0000-7000-8000-${String(Date.now())
      .slice(-12)
      .padStart(12, '0')}`;
    const columns =
      newControl.role === 'ui.grid'
        ? parseCsvList(newControl.columnsCsv).map((colName, idx) => ({
            id:
              colName
                .toLowerCase()
                .replace(/[^a-z0-9_]+/g, '_')
                .replace(/^_+|_+$/g, '') || `col_${idx + 1}`,
            name: colName,
            width: 140,
            datatype: 'text',
          }))
        : [];
    const options = ['ui.dropdown', 'ui.radio', 'ui.tabs', 'ui.list'].includes(
      newControl.role
    )
      ? parseCsvList(newControl.optionsCsv)
      : [];

    updateDraftMesh((cur) => ({
      ...cur,
      controls: [
        ...cur.controls,
        {
          id: tempId,
          screen_id: targetScreenId,
          role: newControl.role,
          name: trimmed,
          columns,
          options,
          placeholder: newControl.placeholder.trim(),
          checked: Boolean(newControl.checked),
          notes: '',
        },
      ],
    }));
    setControlDialogOpen(false);
  };

  const handleAddRegion = () => {
    const trimmed = newRegion.name.trim();
    if (!trimmed) {
      setError('Region hotspot name is required.');
      return;
    }
    const targetScreenId = newRegion.screenId || screens[0]?.id || '';
    const tempId = `019c0000-0000-7000-8000-${String(Date.now())
      .slice(-12)
      .padStart(12, '0')}`;
    updateDraftMesh((cur) => ({
      ...cur,
      regions: [
        ...cur.regions,
        {
          id: tempId,
          screen_id: targetScreenId,
          role: 'ui.region',
          name: trimmed,
          bounds: {
            x: Math.max(0, Number(newRegion.x) || 0),
            y: Math.max(0, Number(newRegion.y) || 0),
            width: Math.max(1, Number(newRegion.width) || 120),
            height: Math.max(1, Number(newRegion.height) || 40),
          },
          notes: '',
        },
      ],
    }));
    setRegionDialogOpen(false);
  };

  const handleAddBinding = () => {
    const srcId = newBinding.sourceId || bindableSourceOptions[0]?.value || '';
    const tref = newBinding.targetRef.trim();
    if (!srcId || !tref) {
      setError('Binding source and target reference are required.');
      return;
    }
    const tempId = `019d0000-0000-7000-8000-${String(Date.now())
      .slice(-12)
      .padStart(12, '0')}`;
    updateDraftMesh((cur) => ({
      ...cur,
      bindings: [
        ...cur.bindings,
        {
          id: tempId,
          source_id: srcId,
          column_id: newBinding.columnId.trim() || null,
          target_kind: newBinding.targetKind,
          target_ref: tref,
          access_mode: newBinding.accessMode,
          state: 'unknown',
        },
      ],
    }));
    setBindingDialogOpen(false);
  };

  const handleAddNavigation = () => {
    const fromId = newNav.fromId || bindableSourceOptions[0]?.value || '';
    const toScreenId = newNav.toScreenId || screens[0]?.id || '';
    if (!fromId || !toScreenId) {
      setError('Navigation source and target screen are required.');
      return;
    }
    const tempId = `019e0000-0000-7000-8000-${String(Date.now())
      .slice(-12)
      .padStart(12, '0')}`;
    updateDraftMesh((cur) => ({
      ...cur,
      navigations: [
        ...cur.navigations,
        {
          id: tempId,
          from_id: fromId,
          to_screen_id: toScreenId,
          trigger: newNav.trigger,
          action: newNav.action,
          delay_ms: 0,
          url: '',
          label:
            newNav.label.trim() || `${newNav.trigger} -> ${newNav.action}`,
        },
      ],
    }));
    setNavDialogOpen(false);
  };

  const handleUploadScreenshot = async () => {
    const b64 = screenshotForm.imageBase64.trim();
    if (!b64) {
      setError('Provide base64 PNG/WebP screenshot data.');
      return;
    }
    setBusyMessage('Attaching screenshot to Screen Mesh');
    setError('');
    try {
      const updated = await controller.uploadScreenMeshScreenshot({
        imageBase64: b64,
        mediaType: screenshotForm.mediaType,
        screenId: screenshotForm.screenId || screens[0]?.id || null,
      });
      setMeshPayload(updated);
      setDirty(false);
      setScreenshotDialogOpen(false);
      setBannerInfo('Attached screenshot to Screen Mesh.');
    } catch (upErr) {
      setError(upErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleRedactScreenshot = async () => {
    setBusyMessage('Destructively redacting screenshot region');
    setError('');
    try {
      const updated = await controller.redactScreenMeshScreenshot({
        screenId: redactForm.screenId || screens[0]?.id || null,
        regions: [
          {
            x: Math.max(0, Number(redactForm.x) || 0),
            y: Math.max(0, Number(redactForm.y) || 0),
            width: Math.max(1, Number(redactForm.width) || 80),
            height: Math.max(1, Number(redactForm.height) || 30),
          },
        ],
      });
      setMeshPayload(updated);
      setDirty(false);
      setRedactDialogOpen(false);
      setBannerInfo(
        'Redacted screenshot region and purged original unredacted bytes from designs.db.'
      );
    } catch (redErr) {
      setError(redErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleConfirmSuspect = async (storeBindingId, targetRef) => {
    if (!storeBindingId) return;
    setBusyMessage('Confirming suspect binding');
    setError('');
    try {
      await controller.confirmSuspectBinding(storeBindingId, targetRef);
      await loadAll(controller.state().currentVersion);
      setBannerInfo(`Confirmed binding ${targetRef}.`);
    } catch (confErr) {
      setError(confErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleQueryUsage = async () => {
    setBusyMessage('Querying Screen Mesh bindings');
    setError('');
    try {
      const rows = await controller.queryScreenMeshUsage({
        targetRef: usageFilter.trim(),
        includeSuspect: true,
      });
      setUsageResults(rows || []);
    } catch (qErr) {
      setError(qErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleAccept = async () => {
    setBusyMessage('Accepting Screen Mesh version');
    setError('');
    try {
      await controller.accept({
        requireGitReview: acceptForm.requireGitReview,
        gitReviewRef: acceptForm.gitReviewRef.trim() || null,
        comment: acceptForm.comment.trim(),
      });
      await loadAll(controller.state().currentVersion);
      setAcceptDialogOpen(false);
      setBannerInfo('Accepted Screen Mesh version.');
    } catch (accErr) {
      setError(accErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const handleGitSync = async () => {
    setBusyMessage('Running Git operation');
    setError('');
    try {
      await controller.gitOperation({
        action: gitForm.action,
        repoRoot: gitForm.repoRoot.trim(),
        path: gitForm.path.trim() || `${designId}.ddn`,
        branch: gitForm.branch.trim() || 'main',
        note: gitForm.note.trim(),
      });
      await loadAll();
      setGitDialogOpen(false);
      setBannerInfo(`Completed Git ${gitForm.action} operation.`);
    } catch (gitErr) {
      setError(gitErr.message);
    } finally {
      setBusyMessage('');
    }
  };

  const runToolbarCommand = (commandId, invoke) => {
    if (typeof executeCommand === 'function') {
      return executeCommand(commandId, {enabled: !readOnly, invoke});
    }
    return invoke();
  };

  if (!loading && error && !mesh) {
    return (
      <Box component="section" aria-label="Screen Mesh Designer">
        <FormReference formKey="screen-mesh-designer" />
        <EmptyState
          role="alert"
          message={error}
          actionLabel="Retry"
          onAction={() => loadAll()}
        />
      </Box>
    );
  }

  const nextStatus = nextWorkflowStatus(sessionState.status);
  const activeScreenshots = screens.filter((s) => s.screenshot_sha256);

  return (
    <Box
      component="section"
      aria-label="Screen Mesh Designer"
      sx={{
        position: 'relative',
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="screen-mesh-designer" />
      <Toolbar label="Screen Mesh designer commands">
        <StatusBadge
          label={
            sessionState.loaded
              ? `v${sessionState.currentVersion} (${sessionState.status})`
              : 'loading'
          }
          status={badgeStatus(sessionState.status)}
        />
        <Select
          aria-label="Screen Mesh DDN view"
          label="View"
          size="small"
          options={viewOptions}
          value={selectedView}
          onChange={(val) => setSelectedView(val)}
        />
        {!readOnly && (
          <>
            <Button
              onClick={() => {
                setNewScreen({
                  name: '',
                  width: '960',
                  height: '640',
                  formReference: '',
                });
                setScreenDialogOpen(true);
              }}
            >
              Add Screen…
            </Button>
            <Button
              onClick={() => {
                setNewControl((cur) => ({
                  ...cur,
                  screenId: screens[0]?.id || '',
                  name: '',
                }));
                setControlDialogOpen(true);
              }}
            >
              Add Control…
            </Button>
            <Button
              onClick={() => {
                setNewRegion((cur) => ({
                  ...cur,
                  screenId: screens[0]?.id || '',
                  name: '',
                }));
                setRegionDialogOpen(true);
              }}
            >
              Add Region…
            </Button>
            <Button
              onClick={() => {
                setNewBinding((cur) => ({
                  ...cur,
                  sourceId: bindableSourceOptions[0]?.value || '',
                  targetRef: '',
                }));
                setBindingDialogOpen(true);
              }}
            >
              Add Binding…
            </Button>
            <Button
              onClick={() => {
                setNewNav((cur) => ({
                  ...cur,
                  fromId: bindableSourceOptions[0]?.value || '',
                  toScreenId: screens[screens.length - 1]?.id || '',
                  label: '',
                }));
                setNavDialogOpen(true);
              }}
            >
              Add Navigation…
            </Button>
            <Button
              onClick={() => {
                setScreenshotForm({
                  screenId: screens[0]?.id || '',
                  mediaType: 'image/png',
                  imageBase64: '',
                });
                setScreenshotDialogOpen(true);
              }}
            >
              Attach Screenshot…
            </Button>
            <Button
              disabled={!activeScreenshots.length}
              onClick={() =>
                runToolbarCommand('screen_mesh.designer.redact', () => {
                  setRedactForm((cur) => ({
                    ...cur,
                    screenId: activeScreenshots[0]?.id || '',
                  }));
                  setRedactDialogOpen(true);
                })
              }
            >
              Redact Screenshot…
            </Button>
            <Button
              onClick={() =>
                runToolbarCommand(
                  'screen_mesh.designer.save',
                  handleSaveCheckpoint
                )
              }
            >
              Save Checkpoint{dirty ? ' *' : ''}
            </Button>
            {nextStatus && (
              <Button onClick={handleAdvanceStatus}>
                Advance to {nextStatus}
              </Button>
            )}
            <Button
              onClick={() =>
                runToolbarCommand('screen_mesh.designer.accept', () =>
                  setAcceptDialogOpen(true)
                )
              }
            >
              Accept…
            </Button>
            <Button onClick={() => setGitDialogOpen(true)}>Git…</Button>
          </>
        )}
        <Button
          onClick={() => {
            setUsageDialogOpen(true);
            handleQueryUsage();
          }}
        >
          Where Used…
        </Button>
      </Toolbar>

      <Banner status="info">
        Screen Mesh scope: low-fidelity wireframes, annotated screenshots (
        <code>ui.region</code>), data bindings and screen-to-screen flows (
        <code>wireframe.ui@1</code>). Executable working forms are outside
        ScratchRobin scope.
      </Banner>

      {error && (
        <Banner status="error" onClose={() => setError('')}>
          {error}
        </Banner>
      )}
      {bannerInfo && (
        <Banner status="success" onClose={() => setBannerInfo('')}>
          {bannerInfo}
        </Banner>
      )}
      {suspectCount > 0 && (
        <Banner status="warning">
          {suspectCount} binding(s) are marked suspect after a catalog rename or
          drop. Review and confirm affected bindings below.
        </Banner>
      )}

      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          display: 'grid',
          gridTemplateColumns: 'minmax(280px, 340px) 1fr',
          gap: 1,
          p: 1,
          overflow: 'hidden',
        }}
      >
        <Box
          aria-label="Screen Mesh inspector"
          sx={{
            overflow: 'auto',
            border: '1px solid',
            borderColor: 'divider',
            p: 1,
          }}
        >
          <Stack spacing={1.5}>
            <Box>
              <strong>{mesh?.name || sessionState.title || 'Screen Mesh'}</strong>
              <div>
                Screens: {screens.length} · Controls: {controls.length} ·
                Regions: {regions.length} · Bindings: {bindings.length} ·
                Flows: {navigations.length}
              </div>
            </Box>

            <Box>
              <strong>Screens (ui.frame)</strong>
              {screens.map((scr) => (
                <Box key={scr.id} sx={{mt: 0.5, fontSize: '0.85rem'}}>
                  {scr.name} ({scr.width}×{scr.height})
                  {scr.form_reference ? ` [${scr.form_reference}]` : ''}
                  {scr.screenshot_sha256 ? (
                    <div>
                      Screenshot attached (
                      <a
                        href={controller.screenMeshBlobUrl(
                          scr.screenshot_sha256
                        )}
                        target="_blank"
                        rel="noreferrer"
                      >
                        blob {scr.screenshot_sha256.slice(0, 12)}…
                      </a>
                      )
                    </div>
                  ) : null}
                </Box>
              ))}
            </Box>

            {controls.length > 0 && (
              <Box>
                <strong>Wireframe Controls</strong>
                {controls.map((ctrl) => (
                  <Box key={ctrl.id} sx={{mt: 0.5, fontSize: '0.85rem'}}>
                    <code>{ctrl.role}</code>: {ctrl.name}
                    {ctrl.columns?.length
                      ? ` (${ctrl.columns.map((c) => c.name).join(', ')})`
                      : ''}
                  </Box>
                ))}
              </Box>
            )}

            {regions.length > 0 && (
              <Box>
                <strong>Screenshot Hotspots (ui.region)</strong>
                {regions.map((reg) => (
                  <Box key={reg.id} sx={{mt: 0.5, fontSize: '0.85rem'}}>
                    {reg.name} ({reg.bounds.x}, {reg.bounds.y},{' '}
                    {reg.bounds.width}×{reg.bounds.height})
                  </Box>
                ))}
              </Box>
            )}

            {bindings.length > 0 && (
              <Box>
                <strong>Data &amp; Resource Bindings</strong>
                {bindings.map((bnd) => (
                  <Box key={bnd.id} sx={{mt: 0.5, fontSize: '0.85rem'}}>
                    <span>
                      [{bnd.state || 'unknown'}] {bnd.access_mode} →{' '}
                      {bnd.target_kind}:{bnd.target_ref}
                    </span>
                    {bnd.state === 'suspect' && bnd.store_binding_id && !readOnly && (
                      <Box sx={{mt: 0.5}}>
                        <Button
                          size="small"
                          onClick={() =>
                            handleConfirmSuspect(
                              bnd.store_binding_id,
                              bnd.target_ref
                            )
                          }
                        >
                          Confirm Binding
                        </Button>
                      </Box>
                    )}
                  </Box>
                ))}
              </Box>
            )}

            {navigations.length > 0 && (
              <Box>
                <strong>Screen Navigation Links</strong>
                {navigations.map((nav) => (
                  <Box key={nav.id} sx={{mt: 0.5, fontSize: '0.85rem'}}>
                    {nav.label} ({nav.trigger} → {nav.action})
                  </Box>
                ))}
              </Box>
            )}
          </Stack>
        </Box>

        <Box
          aria-label="Screen Mesh DDN canvas"
          sx={{
            minHeight: 0,
            border: '1px solid',
            borderColor: 'divider',
            overflow: 'hidden',
          }}
        >
          {viewerSnapshot && (
            <DDNViewerSurface
              snapshot={viewerSnapshot}
              onExport={onExport}
              onError={onError}
            />
          )}
        </Box>
      </Box>

      <ProgressOverlay
        message={loading ? 'Loading Screen Mesh' : busyMessage}
      />

      {/* Add Screen Dialog */}
      <Dialog
        open={screenDialogOpen}
        title="Add Screen (ui.frame)"
        onClose={() => setScreenDialogOpen(false)}
        defaultAction={handleAddScreen}
        actions={
          <>
            <Button onClick={() => setScreenDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={handleAddScreen}>
              Add Screen
            </Button>
          </>
        }
      >
        <Stack spacing={1.5}>
          <TextField
            label="Screen name"
            value={newScreen.name}
            onChange={(e) =>
              setNewScreen((cur) => ({...cur, name: e.target.value}))
            }
          />
          <NumberField
            label="Width (px)"
            value={newScreen.width}
            onChange={(e) =>
              setNewScreen((cur) => ({...cur, width: e.target.value}))
            }
          />
          <NumberField
            label="Height (px)"
            value={newScreen.height}
            onChange={(e) =>
              setNewScreen((cur) => ({...cur, height: e.target.value}))
            }
          />
          <TextField
            label="Form reference (optional SR-F code)"
            value={newScreen.formReference}
            onChange={(e) =>
              setNewScreen((cur) => ({...cur, formReference: e.target.value}))
            }
          />
        </Stack>
      </Dialog>

      {/* Add Control Dialog */}
      <Dialog
        open={controlDialogOpen}
        title="Add Wireframe Control"
        onClose={() => setControlDialogOpen(false)}
        defaultAction={handleAddControl}
        actions={
          <>
            <Button onClick={() => setControlDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={handleAddControl}>
              Add Control
            </Button>
          </>
        }
      >
        <Stack spacing={1.5}>
          <Select
            label="Target screen"
            options={screenOptions}
            value={newControl.screenId}
            onChange={(val) =>
              setNewControl((cur) => ({...cur, screenId: val}))
            }
          />
          <Select
            label="Control role"
            options={SCREEN_MESH_CONTROL_ROLE_OPTIONS}
            value={newControl.role}
            onChange={(val) => setNewControl((cur) => ({...cur, role: val}))}
          />
          <TextField
            label="Control label"
            value={newControl.name}
            onChange={(e) =>
              setNewControl((cur) => ({...cur, name: e.target.value}))
            }
          />
          {newControl.role === 'ui.grid' && (
            <TextField
              label="Grid columns (comma-separated)"
              value={newControl.columnsCsv}
              onChange={(e) =>
                setNewControl((cur) => ({...cur, columnsCsv: e.target.value}))
              }
            />
          )}
          {['ui.dropdown', 'ui.radio', 'ui.tabs', 'ui.list'].includes(
            newControl.role
          ) && (
            <TextField
              label="Choices / tabs (comma-separated)"
              value={newControl.optionsCsv}
              onChange={(e) =>
                setNewControl((cur) => ({...cur, optionsCsv: e.target.value}))
              }
            />
          )}
          {newControl.role === 'ui.input' && (
            <TextField
              label="Placeholder"
              value={newControl.placeholder}
              onChange={(e) =>
                setNewControl((cur) => ({...cur, placeholder: e.target.value}))
              }
            />
          )}
          {['ui.checkbox', 'ui.radio'].includes(newControl.role) && (
            <Checkbox
              label="Checked by default"
              checked={newControl.checked}
              onChange={(checked) =>
                setNewControl((cur) => ({...cur, checked}))
              }
            />
          )}
        </Stack>
      </Dialog>

      {/* Add Region Dialog (F1) */}
      <Dialog
        open={regionDialogOpen}
        title="Add Screenshot Hotspot Region (ui.region)"
        onClose={() => setRegionDialogOpen(false)}
        defaultAction={handleAddRegion}
        actions={
          <>
            <Button onClick={() => setRegionDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={handleAddRegion}>
              Add Region
            </Button>
          </>
        }
      >
        <Stack spacing={1.5}>
          <Select
            label="Target screen"
            options={screenOptions}
            value={newRegion.screenId}
            onChange={(val) => setNewRegion((cur) => ({...cur, screenId: val}))}
          />
          <TextField
            label="Region name"
            value={newRegion.name}
            onChange={(e) =>
              setNewRegion((cur) => ({...cur, name: e.target.value}))
            }
          />
          <NumberField
            label="Bounds X"
            value={newRegion.x}
            onChange={(e) =>
              setNewRegion((cur) => ({...cur, x: e.target.value}))
            }
          />
          <NumberField
            label="Bounds Y"
            value={newRegion.y}
            onChange={(e) =>
              setNewRegion((cur) => ({...cur, y: e.target.value}))
            }
          />
          <NumberField
            label="Bounds Width"
            value={newRegion.width}
            onChange={(e) =>
              setNewRegion((cur) => ({...cur, width: e.target.value}))
            }
          />
          <NumberField
            label="Bounds Height"
            value={newRegion.height}
            onChange={(e) =>
              setNewRegion((cur) => ({...cur, height: e.target.value}))
            }
          />
        </Stack>
      </Dialog>

      {/* Add Binding Dialog */}
      <Dialog
        open={bindingDialogOpen}
        title="Bind Control or Region to Data"
        onClose={() => setBindingDialogOpen(false)}
        defaultAction={handleAddBinding}
        actions={
          <>
            <Button onClick={() => setBindingDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={handleAddBinding}>
              Add Binding
            </Button>
          </>
        }
      >
        <Stack spacing={1.5}>
          <Select
            label="Source element"
            options={bindableSourceOptions}
            value={newBinding.sourceId}
            onChange={(val) =>
              setNewBinding((cur) => ({...cur, sourceId: val}))
            }
          />
          <TextField
            label="Grid column ID (optional)"
            value={newBinding.columnId}
            onChange={(e) =>
              setNewBinding((cur) => ({...cur, columnId: e.target.value}))
            }
          />
          <Select
            label="Target kind"
            options={SCREEN_MESH_BINDING_KIND_OPTIONS}
            value={newBinding.targetKind}
            onChange={(val) =>
              setNewBinding((cur) => ({...cur, targetKind: val}))
            }
          />
          <TextField
            label="Target reference (e.g. sales.orders.customer_id)"
            value={newBinding.targetRef}
            onChange={(e) =>
              setNewBinding((cur) => ({...cur, targetRef: e.target.value}))
            }
          />
          <Select
            label="Access mode"
            options={SCREEN_MESH_ACCESS_OPTIONS}
            value={newBinding.accessMode}
            onChange={(val) =>
              setNewBinding((cur) => ({...cur, accessMode: val}))
            }
          />
        </Stack>
      </Dialog>

      {/* Add Navigation Dialog (F2) */}
      <Dialog
        open={navDialogOpen}
        title="Add Screen-to-Screen Navigation"
        onClose={() => setNavDialogOpen(false)}
        defaultAction={handleAddNavigation}
        actions={
          <>
            <Button onClick={() => setNavDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={handleAddNavigation}>
              Add Navigation
            </Button>
          </>
        }
      >
        <Stack spacing={1.5}>
          <Select
            label="From control or region"
            options={bindableSourceOptions}
            value={newNav.fromId}
            onChange={(val) => setNewNav((cur) => ({...cur, fromId: val}))}
          />
          <Select
            label="Destination screen"
            options={screenOptions}
            value={newNav.toScreenId}
            onChange={(val) => setNewNav((cur) => ({...cur, toScreenId: val}))}
          />
          <Select
            label="Trigger"
            options={SCREEN_MESH_TRIGGER_OPTIONS}
            value={newNav.trigger}
            onChange={(val) => setNewNav((cur) => ({...cur, trigger: val}))}
          />
          <Select
            label="Bounded non-executable action"
            options={SCREEN_MESH_ACTION_OPTIONS}
            value={newNav.action}
            onChange={(val) => setNewNav((cur) => ({...cur, action: val}))}
          />
          <TextField
            label="Flow label"
            value={newNav.label}
            onChange={(e) =>
              setNewNav((cur) => ({...cur, label: e.target.value}))
            }
          />
        </Stack>
      </Dialog>

      {/* Attach Screenshot Dialog */}
      <Dialog
        open={screenshotDialogOpen}
        title="Attach Screenshot (PNG / WebP)"
        onClose={() => setScreenshotDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setScreenshotDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="contained" onClick={handleUploadScreenshot}>
              Upload Screenshot
            </Button>
          </>
        }
      >
        <Stack spacing={1.5}>
          <Select
            label="Target screen"
            options={screenOptions}
            value={screenshotForm.screenId}
            onChange={(val) =>
              setScreenshotForm((cur) => ({...cur, screenId: val}))
            }
          />
          <Select
            label="Media type"
            options={[
              {value: 'image/png', label: 'PNG (image/png)'},
              {value: 'image/webp', label: 'WebP (image/webp)'},
            ]}
            value={screenshotForm.mediaType}
            onChange={(val) =>
              setScreenshotForm((cur) => ({...cur, mediaType: val}))
            }
          />
          <TextArea
            rows={4}
            label="Base64 image data"
            value={screenshotForm.imageBase64}
            onChange={(e) =>
              setScreenshotForm((cur) => ({
                ...cur,
                imageBase64: e.target.value,
              }))
            }
          />
        </Stack>
      </Dialog>

      {/* Destructive Redact Screenshot Dialog (F4) */}
      <Dialog
        open={redactDialogOpen}
        title="Destructively Redact Screenshot Region"
        onClose={() => setRedactDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setRedactDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={handleRedactScreenshot}>
              Redact &amp; Purge Original
            </Button>
          </>
        }
      >
        <Stack spacing={1.5}>
          <Banner status="warning">
            Irreversible operation: redacting overwrites the pixels in the PNG
            and purges the unredacted image bytes from <code>asset_blob</code>{' '}
            in <code>designs.db</code>.
          </Banner>
          <NumberField
            label="Region X"
            value={redactForm.x}
            onChange={(e) =>
              setRedactForm((cur) => ({...cur, x: e.target.value}))
            }
          />
          <NumberField
            label="Region Y"
            value={redactForm.y}
            onChange={(e) =>
              setRedactForm((cur) => ({...cur, y: e.target.value}))
            }
          />
          <NumberField
            label="Region Width"
            value={redactForm.width}
            onChange={(e) =>
              setRedactForm((cur) => ({...cur, width: e.target.value}))
            }
          />
          <NumberField
            label="Region Height"
            value={redactForm.height}
            onChange={(e) =>
              setRedactForm((cur) => ({...cur, height: e.target.value}))
            }
          />
        </Stack>
      </Dialog>

      {/* Where Used Dialog */}
      <Dialog
        open={usageDialogOpen}
        size="medium"
        title="Where Used Across Screen Meshes"
        onClose={() => setUsageDialogOpen(false)}
        actions={
          <>
            <Button onClick={handleQueryUsage}>Search</Button>
            <Button onClick={() => setUsageDialogOpen(false)}>Close</Button>
          </>
        }
      >
        <Stack spacing={1.5}>
          <TextField
            label="Filter by table, column, question or cube reference"
            value={usageFilter}
            onChange={(e) => setUsageFilter(e.target.value)}
          />
          {usageResults.length === 0 ? (
            <div>No matching Screen Mesh bindings found.</div>
          ) : (
            usageResults.map((row, idx) => (
              <Box
                key={`${row.design_id}-${row.element_id}-${idx}`}
                sx={{fontSize: '0.85rem'}}
              >
                <strong>{row.design_title}</strong> · {row.screen_name} ·{' '}
                <code>{row.element_role}</code> {row.element_name} →{' '}
                {row.target_kind}:{row.target_ref} ({row.state})
              </Box>
            ))
          )}
        </Stack>
      </Dialog>

      {/* Accept Dialog */}
      <Dialog
        open={acceptDialogOpen}
        title="Accept Screen Mesh Version"
        onClose={() => setAcceptDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setAcceptDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={handleAccept}>
              Accept Version
            </Button>
          </>
        }
      >
        <Stack spacing={1.5}>
          <Checkbox
            label="Require Git review reference"
            checked={acceptForm.requireGitReview}
            onChange={(checked) =>
              setAcceptForm((cur) => ({...cur, requireGitReview: checked}))
            }
          />
          {acceptForm.requireGitReview && (
            <TextField
              label="Git review reference"
              value={acceptForm.gitReviewRef}
              onChange={(e) =>
                setAcceptForm((cur) => ({
                  ...cur,
                  gitReviewRef: e.target.value,
                }))
              }
            />
          )}
          <TextField
            label="Approval comment"
            value={acceptForm.comment}
            onChange={(e) =>
              setAcceptForm((cur) => ({...cur, comment: e.target.value}))
            }
          />
        </Stack>
      </Dialog>

      {/* Git Dialog */}
      <Dialog
        open={gitDialogOpen}
        title="Screen Mesh Git Sync"
        onClose={() => setGitDialogOpen(false)}
        actions={
          <>
            <Button onClick={() => setGitDialogOpen(false)}>Close</Button>
            <Button variant="contained" onClick={handleGitSync}>
              Run Git Action
            </Button>
          </>
        }
      >
        <Stack spacing={1.5}>
          <Select
            label="Git action"
            options={[
              {value: 'save', label: 'Save DDN to Git'},
              {value: 'load', label: 'Load DDN from Git'},
              {value: 'drift', label: 'Check Git Drift'},
            ]}
            value={gitForm.action}
            onChange={(val) => setGitForm((cur) => ({...cur, action: val}))}
          />
          <TextField
            label="Repository root"
            value={gitForm.repoRoot}
            onChange={(e) =>
              setGitForm((cur) => ({...cur, repoRoot: e.target.value}))
            }
          />
          <TextField
            label="Relative DDN path"
            value={gitForm.path}
            onChange={(e) =>
              setGitForm((cur) => ({...cur, path: e.target.value}))
            }
          />
          <TextField
            label="Branch"
            value={gitForm.branch}
            onChange={(e) =>
              setGitForm((cur) => ({...cur, branch: e.target.value}))
            }
          />
        </Stack>
      </Dialog>
    </Box>
  );
}

ScreenMeshDesignerSurface.propTypes = {
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
