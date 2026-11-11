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
import {Box} from '../../primitives/Layout';
import {Icon} from '../../icons';
import {ProjectAssetClient} from '../../projects/ProjectAssetClient';
import {Toolbar} from '../../layout/WorkbenchChrome';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {TreeRow} from '../../navigation/AdvancedNavigation';
import {Dialog} from '../../overlays/Dialog';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import FormReference from '../../navigation/FormReference';
import {DesignStoreClient} from './sharedDesignLibrary';

export const CUBE_CREATE_EVENT = 'cdeadmin:cube-create';
export const CUBE_OPEN_EVENT = 'cdeadmin:cube-open';
const NEW_PROJECT = '\u0000new-project';
const WRITABLE = new Set(['owner', 'manager', 'editor']);
let pendingCreate = false;

export function requestCubeCreate() {
  pendingCreate = true;
  window.dispatchEvent(new CustomEvent(CUBE_CREATE_EVENT));
}

function takePendingCreate() {
  const pending = pendingCreate;
  pendingCreate = false;
  return pending;
}

export function openCubeDesign(projectId, design) {
  window.dispatchEvent(
    new CustomEvent(CUBE_OPEN_EVENT, {
      detail: {
        projectId,
        designId: design.id,
        title: design.title,
      },
    })
  );
}

function slugKey(name) {
  return (
    String(name || '')
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 64) || 'cube'
  );
}

export function CubesNavigator({
  designClient: suppliedDesignClient,
  projectClient: suppliedProjectClient,
  onOpenCube = openCubeDesign,
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({
    mode: 'new',
    title: '',
    project: '',
    projectId: 'analytics',
    projectName: 'Analytics Cubes',
    endpointId: '',
    modelId: '',
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
            const cubes = await designClient.listDesigns(project.project_id, {
              kind: 'cube',
            });
            return {project, cubes: cubes || [], error: ''};
          } catch (loadErr) {
            return {project, cubes: [], error: loadErr.message};
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

  const beginCreate = useCallback(() => {
    setCreateError('');
    setDraft((cur) => ({
      ...cur,
      mode: 'new',
      title: '',
      modelId: '',
      project: cur.project || writable[0]?.project.project_id || NEW_PROJECT,
    }));
    setOpen(true);
  }, [writable]);

  useEffect(() => {
    refresh().then((loaded) => {
      if (takePendingCreate()) {
        const first = loaded.find(({project}) => WRITABLE.has(project.access));
        setDraft((cur) => ({
          ...cur,
          mode: 'new',
          title: '',
          project: first?.project.project_id || NEW_PROJECT,
        }));
        setOpen(true);
      }
    });
  }, [refresh]);

  useEffect(() => {
    const listener = () => {
      takePendingCreate();
      beginCreate();
    };
    window.addEventListener(CUBE_CREATE_EVENT, listener);
    return () => window.removeEventListener(CUBE_CREATE_EVENT, listener);
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

      let created;
      if (draft.mode === 'import_store') {
        if (!draft.endpointId.trim() || !draft.modelId.trim()) {
          throw new Error(
            'Endpoint ID and semantic-store Model ID are required to load an existing cube.'
          );
        }
        created = await designClient.importCubeFromStore(projectId, {
          key: `${slugKey(draft.modelId)}-${Date.now().toString(36)}`,
          endpointId: draft.endpointId.trim(),
          modelId: draft.modelId.trim(),
        });
      } else {
        const trimmedTitle = draft.title.trim();
        if (!trimmedTitle) {
          throw new Error('A cube needs a title.');
        }
        created = await designClient.createCubeDesign(projectId, {
          key: `${slugKey(trimmedTitle)}-${Date.now().toString(36)}`,
          title: trimmedTitle,
          endpointId: draft.endpointId.trim() || null,
        });
      }

      await refresh();
      setOpen(false);
      onOpenCube(projectId, created);
    } catch (saveErr) {
      setCreateError(saveErr.message);
    } finally {
      setSaving(false);
    }
  };

  const total = groups.reduce((count, g) => count + g.cubes.length, 0);

  return (
    <Box
      component="section"
      aria-label="Cubes"
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="cubes-navigator" />
      <Toolbar label="Cube commands">
        <Button onClick={beginCreate}>New cube…</Button>
        <Button onClick={refresh}>Refresh</Button>
      </Toolbar>
      <Box
        role="tree"
        aria-label="Cubes by project"
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
            message="No cube designs yet. Create a new cube or load one from the semantic-model store."
            actionLabel="New cube"
            onAction={beginCreate}
          />
        )}
        {!error &&
          groups
            .filter((g) => g.cubes.length || g.error)
            .map(({project, cubes, error: projErr}) => (
              <Box key={project.project_id} role="group">
                <TreeRow
                  level={1}
                  label={project.name}
                  expandable
                  expanded
                  warning={projErr}
                  icon={<Icon iconKey="object.schema" decorative />}
                />
                {cubes.map((cube) => (
                  <TreeRow
                    level={2}
                    key={cube.id}
                    label={cube.title}
                    icon={<Icon iconKey="object.cube" decorative />}
                    trailing={`v${cube.head_version}`}
                    onOpen={() => onOpenCube(project.project_id, cube)}
                  />
                ))}
              </Box>
            ))}
        <ProgressOverlay message={loading ? 'Loading cubes' : ''} />
      </Box>

      <Dialog
        open={open}
        title="New or imported cube"
        size="medium"
        onClose={() => !saving && setOpen(false)}
        busy={saving}
        validationError={createError}
        defaultAction={create}
        actions={
          <>
            <Button disabled={saving} onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button intent="primary" loading={saving} onClick={create}>
              Create cube
            </Button>
          </>
        }
      >
        <FormReference formKey="cube-create" />
        <Box sx={{display: 'grid', gap: 2}}>
          <Select
            label="Source"
            value={draft.mode}
            options={[
              {value: 'new', label: 'New cube design'},
              {
                value: 'import_store',
                label: 'Load existing cube from semantic-model store',
              },
            ]}
            onChange={(val) =>
              setDraft((cur) => ({...cur, mode: val}))
            }
          />
          {draft.mode === 'new' ? (
            <TextField
              autoFocus
              required
              label="Cube title"
              value={draft.title}
              onChange={(e) =>
                setDraft((cur) => ({...cur, title: e.target.value}))
              }
            />
          ) : (
            <TextField
              autoFocus
              required
              label="Semantic-store Model ID"
              value={draft.modelId}
              onChange={(e) =>
                setDraft((cur) => ({...cur, modelId: e.target.value}))
              }
            />
          )}
          <TextField
            label="Semantic-store Endpoint ID (optional)"
            value={draft.endpointId}
            onChange={(e) =>
              setDraft((cur) => ({...cur, endpointId: e.target.value}))
            }
          />
          <Select
            label="Project"
            value={draft.project}
            options={[
              ...writable.map(({project}) => ({
                value: project.project_id,
                label: project.name,
              })),
              {value: NEW_PROJECT, label: 'New project…'},
            ]}
            onChange={(val) =>
              setDraft((cur) => ({...cur, project: val}))
            }
          />
          {draft.project === NEW_PROJECT && (
            <>
              <TextField
                label="New project ID"
                required
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
        </Box>
      </Dialog>
    </Box>
  );
}

CubesNavigator.propTypes = {
  designClient: PropTypes.object,
  projectClient: PropTypes.object,
  onOpenCube: PropTypes.func,
};
