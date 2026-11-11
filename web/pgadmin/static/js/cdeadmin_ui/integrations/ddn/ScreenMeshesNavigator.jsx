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
import {Icon} from '../../icons';
import {ProjectAssetClient} from '../../projects/ProjectAssetClient';
import {Toolbar} from '../../layout/WorkbenchChrome';
import {Button} from '../../primitives/Button';
import {TextArea, TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {TreeRow} from '../../navigation/AdvancedNavigation';
import {Dialog} from '../../overlays/Dialog';
import {Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import FormReference from '../../navigation/FormReference';
import {DesignStoreClient} from './sharedDesignLibrary';

export const SCREEN_MESH_CREATE_EVENT = 'cdeadmin:screen-mesh-create';
export const SCREEN_MESH_OPEN_EVENT = 'cdeadmin:screen-mesh-open';
const NEW_PROJECT = '\u0000new-project';
const WRITABLE = new Set(['owner', 'manager', 'editor']);
let pendingCreate = false;

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

  const [groups, setGroups] = useState([]);
  const [descriptorForms, setDescriptorForms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [importSummary, setImportSummary] = useState(null);
  const [draft, setDraft] = useState({
    mode: 'new_mesh',
    title: '',
    formReference: '',
    selectedDescriptorRef: '',
    qaManifestJson: '',
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

  const writable = groups.filter(({project}) => WRITABLE.has(project.access));

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

  const beginCreate = useCallback(() => {
    setCreateError('');
    loadDescriptorCatalog();
    setDraft((cur) => ({
      ...cur,
      mode: 'new_mesh',
      title: '',
      formReference: '',
      qaManifestJson: '',
      project: cur.project || writable[0]?.project.project_id || NEW_PROJECT,
    }));
    setOpen(true);
  }, [writable, loadDescriptorCatalog]);

  useEffect(() => {
    refresh().then((loaded) => {
      if (takePendingCreate()) {
        loadDescriptorCatalog();
        const first = loaded.find(({project}) => WRITABLE.has(project.access));
        setDraft((cur) => ({
          ...cur,
          mode: 'new_mesh',
          title: '',
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
        let parsedManifest = null;
        const rawManifest = draft.qaManifestJson.trim();
        if (rawManifest) {
          parsedManifest =
            rawManifest.startsWith('[') || rawManifest.startsWith('{')
              ? JSON.parse(rawManifest)
              : rawManifest;
        }
        const imported = await designClient.importDescriptorMesh(projectId, {
          formReference: refCode,
          qaManifest: parsedManifest,
        });
        setImportSummary(imported.loss_report || null);
        await refresh();
        setOpen(false);
        if (imported.design) {
          onOpenDesign(projectId, imported.design);
        }
        return;
      }

      const trimmedTitle = draft.title.trim();
      if (!trimmedTitle) {
        throw new Error('A Screen Mesh needs a title.');
      }
      const key = `${slugKey(trimmedTitle)}-${Date.now().toString(36)}`;
      const created = await designClient.createScreenMesh(projectId, {
        key,
        title: trimmedTitle,
        formReference: draft.formReference.trim() || null,
      });

      await refresh();
      setOpen(false);
      onOpenDesign(projectId, created);
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
        <Button onClick={beginCreate}>New Screen Mesh…</Button>
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
            onAction={beginCreate}
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
        size="medium"
        title="New or imported Screen Mesh"
        busy={saving}
        validationError={createError}
        onClose={() => setOpen(false)}
        defaultAction={create}
        actions={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="contained" disabled={saving} onClick={create}>
              {draft.mode === 'import_descriptor'
                ? 'Import SR-F Form'
                : 'Create Screen Mesh'}
            </Button>
          </>
        }
      >
        <FormReference formKey="screen-mesh-create" />
        <Stack spacing={1.5}>
          <Select
            label="Project"
            options={projectOptions}
            value={draft.project}
            onChange={(val) => setDraft((cur) => ({...cur, project: val}))}
          />
          {draft.project === NEW_PROJECT && (
            <>
              <TextField
                label="New project ID"
                value={draft.projectId}
                onChange={(e) =>
                  setDraft((cur) => ({...cur, projectId: e.target.value}))
                }
              />
              <TextField
                label="New project name"
                value={draft.projectName}
                onChange={(e) =>
                  setDraft((cur) => ({...cur, projectName: e.target.value}))
                }
              />
            </>
          )}
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
            onChange={(val) => setDraft((cur) => ({...cur, mode: val}))}
          />
          {draft.mode === 'new_mesh' ? (
            <>
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
                  setDraft((cur) => ({...cur, formReference: e.target.value}))
                }
              />
            </>
          ) : (
            <>
              {descriptorOptions.length > 0 ? (
                <Select
                  label="SR-F UI descriptor form"
                  options={descriptorOptions}
                  value={draft.selectedDescriptorRef}
                  onChange={(val) =>
                    setDraft((cur) => ({...cur, selectedDescriptorRef: val}))
                  }
                />
              ) : (
                <TextField
                  label="SR-F form reference (e.g. SR-F-020073)"
                  value={draft.formReference}
                  onChange={(e) =>
                    setDraft((cur) => ({...cur, formReference: e.target.value}))
                  }
                />
              )}
              <TextArea
                rows={3}
                label="Optional QA screenshot manifest (JSON or CSV)"
                value={draft.qaManifestJson}
                onChange={(e) =>
                  setDraft((cur) => ({...cur, qaManifestJson: e.target.value}))
                }
              />
            </>
          )}
        </Stack>
      </Dialog>
    </Box>
  );
}

ScreenMeshesNavigator.propTypes = {
  designClient: PropTypes.object,
  projectClient: PropTypes.object,
  onOpenDesign: PropTypes.func,
};
