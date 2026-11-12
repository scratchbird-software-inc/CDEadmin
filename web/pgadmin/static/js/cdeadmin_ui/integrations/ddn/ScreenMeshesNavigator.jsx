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
import {Box, Stack} from '../../primitives/Layout';
import {Icon} from '../../icons';
import {ProjectAssetClient} from '../../projects/ProjectAssetClient';
import {Toolbar} from '../../layout/WorkbenchChrome';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Checkbox, Select} from '../../primitives/Choice';
import {TreeRow} from '../../navigation/AdvancedNavigation';
import {Dialog} from '../../overlays/Dialog';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import FormReference from '../../navigation/FormReference';
import {DesignerModalTabs, FormGrid, TypedRowsEditor} from './DesignerChrome';
import {DesignStoreClient} from './sharedDesignLibrary';

export const SCREEN_MESH_CREATE_EVENT = 'cdeadmin:screen-mesh-create';
export const SCREEN_MESH_OPEN_EVENT = 'cdeadmin:screen-mesh-open';
export const DESIGN_SHORTCUT_EVENT = 'cdeadmin:design-shortcut';

const NEW_PROJECT = '\u0000new-project';
const WRITABLE = new Set(['owner', 'manager', 'editor']);
let pendingCreate = false;

// Valid 16x12 minimal RGB PNG used only when the user opts into a synthetic QA sample capture
const SAMPLE_QA_PNG_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAABAAAAAMCAYAAABr5z2BAAAAFElEQVR42mP4//8/AyUYtfBoGAAANBYM8f0t8rAAAAAElFTkSuQmCC';

export function requestScreenMeshCreate() {
  pendingCreate = true;
  window.dispatchEvent(new CustomEvent(SCREEN_MESH_CREATE_EVENT));
}

function takePendingCreate() {
  const pending = pendingCreate;
  pendingCreate = false;
  return pending;
}

export function openScreenMeshDesign(projectId, design) {
  if (!design) return;
  window.dispatchEvent(
    new CustomEvent(SCREEN_MESH_OPEN_EVENT, {
      detail: {
        projectId,
        designId: design.id,
        kind: design.kind,
        title: design.title,
      },
    })
  );
}

function slugKey(name, fallback = 'screen-mesh') {
  return (
    String(name || '')
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 64) || fallback
  );
}

function makeSeededTableMesh({
  title,
  tableRef,
  formReference = '',
  engine = '',
  endpointId = '',
  databaseTargetId = '',
}) {
  const baseStamp = Date.now().toString(16).padStart(12, '0').slice(-12);
  const screenId = `019a0000-0000-7000-8001-${baseStamp}`;
  const filterId = `019a0000-0000-7000-8002-${baseStamp}`;
  const gridId = `019a0000-0000-7000-8003-${baseStamp}`;
  const btnId = `019a0000-0000-7000-8004-${baseStamp}`;
  const bndId = `019a0000-0000-7000-8005-${baseStamp}`;
  const shortName = String(tableRef || 'records')
    .split('.')
    .filter(Boolean)
    .pop();

  return {
    name: title,
    look_handdrawn: false,
    screens: [
      {
        id: screenId,
        name: `${shortName} Screen`,
        width: 960,
        height: 640,
        form_reference: formReference || '',
      },
    ],
    controls: [
      {
        id: filterId,
        screen_id: screenId,
        role: 'ui.input',
        name: `Filter ${shortName}`,
        placeholder: `Search ${tableRef}…`,
        bounds: {x: 24, y: 24, width: 320, height: 36},
      },
      {
        id: btnId,
        screen_id: screenId,
        role: 'ui.button',
        name: 'Refresh Records',
        bounds: {x: 360, y: 24, width: 148, height: 36},
      },
      {
        id: gridId,
        screen_id: screenId,
        role: 'ui.grid',
        name: `${shortName} Grid`,
        bounds: {x: 24, y: 80, width: 880, height: 420},
        columns: [
          {id: 'id', name: 'ID', width: 110, datatype: 'integer'},
          {id: 'name', name: 'Name', width: 220, datatype: 'text'},
        ],
      },
    ],
    regions: [],
    bindings: [
      {
        id: bndId,
        source_id: gridId,
        target_kind: 'table',
        target_ref: tableRef,
        access_mode: 'read',
        ...(engine ? {target_engine: engine} : {}),
        ...(endpointId ? {target_endpoint_id: endpointId} : {}),
        ...(databaseTargetId ? {target_database_target_id: databaseTargetId} : {}),
      },
    ],
    navigations: [],
  };
}

function extractShortcutTableRef(detail = {}) {
  if (!detail || typeof detail !== 'object') return '';
  if (detail.resource_id) return String(detail.resource_id).trim();
  if (detail.qualified_name) return String(detail.qualified_name).trim();
  if (detail.target_ref) return String(detail.target_ref).trim();
  if (detail.schema && (detail.table || detail.table_name || detail.name)) {
    return `${detail.schema}.${detail.table || detail.table_name || detail.name}`;
  }
  return String(
    detail.table || detail.table_name || detail.name || detail.label || ''
  ).trim();
}

export function ScreenMeshesNavigator({
  designClient: suppliedDesignClient,
  projectClient: suppliedProjectClient,
  onOpenDesign = openScreenMeshDesign,
}) {
  const designClient = useMemo(
    () => suppliedDesignClient ?? new DesignStoreClient(),
    [suppliedDesignClient]
  );
  const projectClient = useMemo(
    () => suppliedProjectClient ?? new ProjectAssetClient(),
    [suppliedProjectClient]
  );

  const manifestInputRef = useRef(null);
  const [groups, setGroups] = useState([]);
  const [descriptorForms, setDescriptorForms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [dialogTab, setDialogTab] = useState('source');
  const [importSummary, setImportSummary] = useState(null);
  const [draft, setDraft] = useState({
    mode: 'new_mesh',
    title: '',
    formReference: '',
    selectedDescriptorRef: '',
    qaManifestPayload: null,
    qaManifestFileName: '',
    qaRegions: [],
    includeSampleQaCapture: false,
    seededTableRef: '',
    seededEngine: '',
    seededEndpointId: '',
    seededDatabaseTargetId: '',
    project: '',
    projectId: 'ui-meshes',
    projectName: 'Screen Meshes',
  });
  const [createError, setCreateError] = useState('');
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const projects = await projectClient.listProjects();
      const loaded = await Promise.all(
        projects.map(async (project) => {
          try {
            const all = await designClient.listDesigns(project.project_id);
            const items = (all || []).filter(
              (d) => d.kind === 'screen' || d.kind === 'screen_flow'
            );
            return {project, items, error: ''};
          } catch (loadErr) {
            return {project, items: [], error: loadErr.message};
          }
        })
      );
      setGroups(loaded);
      return loaded;
    } catch (loadErr) {
      setError(loadErr.message);
      return [];
    } finally {
      setLoading(false);
    }
  }, [designClient, projectClient]);

  const writable = useMemo(
    () => groups.filter(({project}) => WRITABLE.has(project.access)),
    [groups]
  );

  const loadDescriptorCatalog = useCallback(async () => {
    if (typeof designClient.listDescriptorForms !== 'function') return;
    try {
      const forms = await designClient.listDescriptorForms();
      setDescriptorForms(forms || []);
      if (forms?.length) {
        setDraft((cur) => ({
          ...cur,
          selectedDescriptorRef:
            cur.selectedDescriptorRef || forms[0].form_reference,
        }));
      }
    } catch {
      // Optional catalog prefill; explicit SR-F input still works.
    }
  }, [designClient]);

  const beginCreate = useCallback(
    (overrides = {}) => {
      setCreateError('');
      setDialogTab('source');
      loadDescriptorCatalog();
      setDraft((cur) => ({
        ...cur,
        mode: overrides.mode || 'new_mesh',
        title: overrides.title ?? '',
        formReference: overrides.formReference ?? '',
        qaManifestPayload: null,
        qaManifestFileName: '',
        qaRegions: [],
        includeSampleQaCapture: false,
        seededTableRef: overrides.seededTableRef ?? '',
        seededEngine: overrides.seededEngine ?? '',
        seededEndpointId: overrides.seededEndpointId ?? '',
        seededDatabaseTargetId: overrides.seededDatabaseTargetId ?? '',
        project: cur.project || writable[0]?.project.project_id || NEW_PROJECT,
      }));
      setOpen(true);
    },
    [writable, loadDescriptorCatalog]
  );

  useEffect(() => {
    refresh().then((loaded) => {
      if (takePendingCreate()) {
        loadDescriptorCatalog();
        const first = loaded.find(({project}) => WRITABLE.has(project.access));
        setDraft((cur) => ({
          ...cur,
          mode: 'new_mesh',
          title: '',
          seededTableRef: '',
          project: first?.project.project_id || NEW_PROJECT,
        }));
        setOpen(true);
      }
    });
  }, [refresh, loadDescriptorCatalog]);

  useEffect(() => {
    const listener = () => {
      takePendingCreate();
      beginCreate();
    };
    window.addEventListener(SCREEN_MESH_CREATE_EVENT, listener);
    return () => window.removeEventListener(SCREEN_MESH_CREATE_EVENT, listener);
  }, [beginCreate]);

  useEffect(() => {
    const onShortcut = (event) => {
      const detail = event?.detail || {};
      const shortcut =
        detail.design_shortcut || detail.shortcut || detail.action || '';
      if (shortcut !== 'screen_mesh_from_table') return;
      const tableRef = extractShortcutTableRef(detail) || 'main.records';
      const shortTable = tableRef.split('.').filter(Boolean).pop() || 'Table';
      beginCreate({
        mode: 'new_mesh',
        title: `${shortTable} Screen Mesh`,
        seededTableRef: tableRef,
        seededEngine: String(detail.providerId || detail.engine || ''),
        seededEndpointId: String(detail.endpointId || detail.endpoint_id || ''),
        seededDatabaseTargetId: String(
          detail.database_target_id || detail.databaseId || ''
        ),
      });
    };
    window.addEventListener(DESIGN_SHORTCUT_EVENT, onShortcut);
    return () => window.removeEventListener(DESIGN_SHORTCUT_EVENT, onShortcut);
  }, [beginCreate]);

  const handleQaManifestFile = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || '').trim();
      try {
        const parsed =
          text.startsWith('[') || text.startsWith('{') ? JSON.parse(text) : text;
        setDraft((cur) => ({
          ...cur,
          qaManifestPayload: parsed,
          qaManifestFileName: file.name,
        }));
        setCreateError('');
      } catch (parseErr) {
        setCreateError(`Invalid QA manifest file: ${parseErr.message}`);
      }
    };
    reader.readAsText(file);
  };

  const create = async () => {
    setSaving(true);
    setCreateError('');
    try {
      let projectId = draft.project;
      if (projectId === NEW_PROJECT) {
        projectId = draft.projectId.trim();
        if (!/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,255}$/.test(projectId)) {
          throw new Error(
            'Project ID must be a stable identifier without spaces.'
          );
        }
        await projectClient.createProject(projectId, {
          name: draft.projectName.trim() || projectId,
        });
      }

      if (draft.mode === 'import_descriptor') {
        const refCode = (
          draft.selectedDescriptorRef || draft.formReference
        ).trim();
        if (!refCode) {
          throw new Error(
            'Select or enter an SR-F descriptor form reference to import.'
          );
        }
        let qaManifest = draft.qaManifestPayload;
        if (
          !qaManifest &&
          (draft.qaRegions.length > 0 || draft.includeSampleQaCapture)
        ) {
          qaManifest = [
            {
              form_reference: refCode,
              media_type: 'image/png',
              image_base64: draft.includeSampleQaCapture
                ? SAMPLE_QA_PNG_BASE64
                : '',
              regions: draft.qaRegions
                .filter((r) => String(r.name || '').trim())
                .map((r) => ({
                  name: String(r.name).trim(),
                  bounds: {
                    x: Math.max(0, Number(r.x) || 0),
                    y: Math.max(0, Number(r.y) || 0),
                    width: Math.max(1, Number(r.width) || 160),
                    height: Math.max(1, Number(r.height) || 48),
                  },
                })),
            },
          ];
        }
        const imported = await designClient.importDescriptorMesh(projectId, {
          formReference: refCode,
          qaManifest,
        });
        setImportSummary(imported.loss_report || null);
        await refresh();
        setOpen(false);
        if (imported?.design) {
          onOpenDesign(projectId, imported.design);
        }
        return;
      }

      const trimmedTitle = draft.title.trim();
      if (!trimmedTitle) {
        throw new Error('A Screen Mesh needs a title.');
      }
      const key = `${slugKey(trimmedTitle)}-${Date.now().toString(36)}`;
      const seededMesh = draft.seededTableRef.trim()
        ? makeSeededTableMesh({
          title: trimmedTitle,
          tableRef: draft.seededTableRef.trim(),
          formReference: draft.formReference.trim(),
          engine: draft.seededEngine,
          endpointId: draft.seededEndpointId,
          databaseTargetId: draft.seededDatabaseTargetId,
        })
        : null;

      const created = await designClient.createScreenMesh(projectId, {
        key,
        title: trimmedTitle,
        mesh: seededMesh,
        formReference: draft.formReference.trim() || null,
      });

      await refresh();
      setOpen(false);
      onOpenDesign(projectId, created?.design || created);
    } catch (saveErr) {
      setCreateError(saveErr.message);
    } finally {
      setSaving(false);
    }
  };

  const total = groups.reduce((count, g) => count + g.items.length, 0);
  const projectOptions = [
    ...writable.map(({project}) => ({
      value: project.project_id,
      label: project.name,
    })),
    {value: NEW_PROJECT, label: 'Create new project…'},
  ];
  const descriptorOptions = descriptorForms.map((item) => ({
    value: item.form_reference,
    label: `${item.form_reference} — ${item.engine}/${item.form_key} (${item.field_count} fields)`,
  }));

  return (
    <Box
      component="section"
      aria-label="Screen Meshes"
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="screen-meshes-navigator" />
      <Toolbar label="Screen Mesh commands">
        <Button onClick={() => beginCreate()}>New Screen Mesh…</Button>
        <Button
          onClick={() => beginCreate({mode: 'import_descriptor'})}
        >
          Import SR-F Form…
        </Button>
        <Button onClick={refresh}>Refresh</Button>
      </Toolbar>
      {importSummary && (
        <Banner status="info" onClose={() => setImportSummary(null)}>
          Imported descriptor form {importSummary.form_reference} (
          {importSummary.engine}/{importSummary.form_key}) into Draft DDN (
          {importSummary.preserved_controls || 0} controls,{' '}
          {importSummary.preserved_bindings || 0} bindings,{' '}
          {importSummary.omitted_dynamic_rules?.length || 0} dynamic form rules
          reported).
        </Banner>
      )}
      <Box
        role="tree"
        aria-label="Screen Meshes by project"
        sx={{position: 'relative', flex: 1, minHeight: 0, overflow: 'auto'}}
      >
        {error && (
          <EmptyState
            role="alert"
            message={error}
            actionLabel="Retry"
            onAction={refresh}
          />
        )}
        {!error && !loading && !total && (
          <EmptyState
            message="No Screen Meshes yet. Create a wireframe mesh or import an SR-F UI descriptor form into Draft DDN."
            actionLabel="New Screen Mesh"
            onAction={() => beginCreate()}
          />
        )}
        {!error &&
          groups
            .filter((g) => g.items.length || g.error)
            .map(({project, items, error: projErr}) => (
              <Box key={project.project_id} role="group">
                <TreeRow
                  level={1}
                  label={project.name}
                  expandable
                  expanded
                  warning={projErr}
                  icon={<Icon iconKey="object.schema" decorative />}
                />
                {items.map((item) => (
                  <TreeRow
                    level={2}
                    key={item.id}
                    label={item.title}
                    icon={<Icon iconKey="tool.erd" decorative />}
                    trailing={`v${item.head_version}`}
                    onOpen={() => onOpenDesign(project.project_id, item)}
                  />
                ))}
              </Box>
            ))}
        <ProgressOverlay message={loading ? 'Loading Screen Meshes' : ''} />
      </Box>

      <Dialog
        open={open}
        size="large"
        title="New or Imported Screen Mesh"
        busy={saving}
        validationError={createError}
        onClose={() => setOpen(false)}
        defaultAction={create}
        actions={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button intent="primary" disabled={saving} onClick={create}>
              {draft.mode === 'import_descriptor'
                ? 'Import SR-F Form'
                : 'Create Screen Mesh'}
            </Button>
          </>
        }
      >
        <DesignerModalTabs
          formKey={
            draft.mode === 'import_descriptor'
              ? 'screen-mesh-import'
              : 'screen-mesh-workspace'
          }
          activeTab={dialogTab}
          onTabChange={setDialogTab}
          minHeight={240}
          tabs={[
            {
              id: 'source',
              label: 'Mesh & Source',
              render: () => (
                <Stack gap="standard">
                  <FormGrid columns={2}>
                    <Select
                      label="Project"
                      options={projectOptions}
                      value={draft.project}
                      onChange={(val) =>
                        setDraft((cur) => ({...cur, project: val}))
                      }
                    />
                    <Select
                      label="Source"
                      options={[
                        {
                          value: 'new_mesh',
                          label: 'Blank Wireframe Screen Mesh (wireframe.ui@1)',
                        },
                        {
                          value: 'import_descriptor',
                          label: 'Import ScratchRobin SR-F UI Descriptor Form',
                        },
                      ]}
                      value={draft.mode}
                      onChange={(val) =>
                        setDraft((cur) => ({...cur, mode: val}))
                      }
                    />
                  </FormGrid>

                  {draft.project === NEW_PROJECT && (
                    <FormGrid columns={2}>
                      <TextField
                        label="New project ID"
                        value={draft.projectId}
                        onChange={(e) =>
                          setDraft((cur) => ({
                            ...cur,
                            projectId: e.target.value,
                          }))
                        }
                      />
                      <TextField
                        label="New project name"
                        value={draft.projectName}
                        onChange={(e) =>
                          setDraft((cur) => ({
                            ...cur,
                            projectName: e.target.value,
                          }))
                        }
                      />
                    </FormGrid>
                  )}

                  {draft.mode === 'new_mesh' ? (
                    <FormGrid columns={2}>
                      <TextField
                        label="Screen Mesh title"
                        value={draft.title}
                        onChange={(e) =>
                          setDraft((cur) => ({...cur, title: e.target.value}))
                        }
                      />
                      <TextField
                        label="Optional SR-F form reference"
                        value={draft.formReference}
                        onChange={(e) =>
                          setDraft((cur) => ({
                            ...cur,
                            formReference: e.target.value,
                          }))
                        }
                      />
                      <TextField
                        label="Seed from catalog table (optional)"
                        placeholder="e.g. main.orders"
                        value={draft.seededTableRef}
                        onChange={(e) =>
                          setDraft((cur) => ({
                            ...cur,
                            seededTableRef: e.target.value,
                          }))
                        }
                      />
                    </FormGrid>
                  ) : (
                    <FormGrid columns={2}>
                      {descriptorOptions.length > 0 ? (
                        <Select
                          label="SR-F UI descriptor form"
                          options={descriptorOptions}
                          value={draft.selectedDescriptorRef}
                          onChange={(val) =>
                            setDraft((cur) => ({
                              ...cur,
                              selectedDescriptorRef: val,
                            }))
                          }
                        />
                      ) : (
                        <TextField
                          label="SR-F form reference (e.g. SR-F-020073)"
                          value={draft.formReference}
                          onChange={(e) =>
                            setDraft((cur) => ({
                              ...cur,
                              formReference: e.target.value,
                            }))
                          }
                        />
                      )}
                      <Box sx={{pt: 0.5}}>
                        <Checkbox
                          label="Attach sample QA screenshot frame"
                          checked={Boolean(draft.includeSampleQaCapture)}
                          onChange={(checked) =>
                            setDraft((cur) => ({
                              ...cur,
                              includeSampleQaCapture: checked,
                            }))
                          }
                        />
                      </Box>
                    </FormGrid>
                  )}
                </Stack>
              ),
            },
            ...(draft.mode === 'import_descriptor'
              ? [
                {
                  id: 'qa_manifest',
                  label: 'QA Manifest & Regions',
                  render: () => (
                    <Stack gap="standard">
                      <Box
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault();
                          const file = e.dataTransfer?.files?.[0];
                          if (file) handleQaManifestFile(file);
                        }}
                        sx={{
                          border: '1px dashed',
                          borderColor: 'divider',
                          p: 1.5,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          flexWrap: 'wrap',
                          gap: 1,
                        }}
                      >
                        <Box sx={{fontSize: '0.8125rem'}}>
                          {draft.qaManifestFileName ? (
                            <>
                                Loaded QA manifest:{' '}
                              <strong>{draft.qaManifestFileName}</strong>
                            </>
                          ) : (
                            'Drop a QA screenshot manifest (.json or .csv) here or choose a file.'
                          )}
                        </Box>
                        <Stack direction="row" gap="compact">
                          <input
                            ref={manifestInputRef}
                            type="file"
                            aria-label="Upload QA screenshot manifest file"
                            accept=".json,.csv,application/json,text/csv"
                            style={{display: 'none'}}
                            onChange={(e) =>
                              handleQaManifestFile(e.target.files?.[0])
                            }
                          />
                          <Button
                            size="small"
                            onClick={() => manifestInputRef.current?.click()}
                          >
                              Choose Manifest File…
                          </Button>
                          {draft.qaManifestFileName && (
                            <Button
                              size="small"
                              onClick={() =>
                                setDraft((cur) => ({
                                  ...cur,
                                  qaManifestPayload: null,
                                  qaManifestFileName: '',
                                }))
                              }
                            >
                                Clear File
                            </Button>
                          )}
                        </Stack>
                      </Box>

                      <TypedRowsEditor
                        label="QA Hotspot Regions"
                        addLabel="Add QA Region"
                        rows={draft.qaRegions}
                        onChange={(rows) =>
                          setDraft((cur) => ({...cur, qaRegions: rows}))
                        }
                        columns={[
                          {
                            key: 'name',
                            label: 'Region Name',
                            placeholder: 'Columns Grid Area',
                            minWidth: 160,
                          },
                          {
                            key: 'x',
                            label: 'X',
                            type: 'number',
                            default: 20,
                            minWidth: 72,
                          },
                          {
                            key: 'y',
                            label: 'Y',
                            type: 'number',
                            default: 60,
                            minWidth: 72,
                          },
                          {
                            key: 'width',
                            label: 'Width',
                            type: 'number',
                            default: 280,
                            minWidth: 84,
                          },
                          {
                            key: 'height',
                            label: 'Height',
                            type: 'number',
                            default: 96,
                            minWidth: 84,
                          },
                        ]}
                      />
                    </Stack>
                  ),
                },
              ]
              : []),
          ]}
        />
      </Dialog>
    </Box>
  );
}

ScreenMeshesNavigator.propTypes = {
  designClient: PropTypes.object,
  projectClient: PropTypes.object,
  onOpenDesign: PropTypes.func,
};
