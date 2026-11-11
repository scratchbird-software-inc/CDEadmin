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

export const ERD_MODEL_CREATE_EVENT = 'cdeadmin:erd-model-create';
export const ERD_MODEL_OPEN_EVENT = 'cdeadmin:erd-model-open';
const NEW_PROJECT = '\u0000new-project';
const WRITABLE = new Set(['owner', 'manager', 'editor']);
let pendingCreate = false;

export function requestERDModelCreate() {
  pendingCreate = true;
  window.dispatchEvent(new CustomEvent(ERD_MODEL_CREATE_EVENT));
}

function takePendingCreate() {
  const pending = pendingCreate;
  pendingCreate = false;
  return pending;
}

export function openERDModel(projectId, design) {
  window.dispatchEvent(
    new CustomEvent(ERD_MODEL_OPEN_EVENT, {
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
      .slice(0, 64) || 'data-model'
  );
}

export function ERDModelsNavigator({
  designClient: suppliedDesignClient,
  projectClient: suppliedProjectClient,
  onOpenModel = openERDModel,
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
    title: '',
    project: '',
    projectId: 'models',
    projectName: 'Data Models',
    initialRole: 'conceptual',
    firstEntityName: '',
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
            const models = await designClient.listDesigns(project.project_id, {
              kind: 'erd',
            });
            return {project, models: models || [], error: ''};
          } catch (loadErr) {
            return {project, models: [], error: loadErr.message};
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
      title: '',
      firstEntityName: '',
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
          title: '',
          firstEntityName: '',
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
    window.addEventListener(ERD_MODEL_CREATE_EVENT, listener);
    return () => window.removeEventListener(ERD_MODEL_CREATE_EVENT, listener);
  }, [beginCreate]);

  const create = async () => {
    const trimmedTitle = draft.title.trim();
    if (!trimmedTitle) {
      setCreateError('A data model needs a title.');
      return;
    }
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

      const entityName = draft.firstEntityName.trim();
      const created = await designClient.createErdDesign(projectId, {
        key: `${slugKey(trimmedTitle)}-${Date.now().toString(36)}`,
        title: trimmedTitle,
        conceptualEntities:
          entityName && draft.initialRole === 'conceptual'
            ? [{name: entityName}]
            : [],
        logicalEntities:
          entityName && draft.initialRole === 'logical'
            ? [{name: entityName, fields: [{name: 'id', datatype: 'uuid'}]}]
            : [],
        physicalTables:
          entityName && draft.initialRole === 'physical'
            ? [
              {
                name: entityName,
                engine: 'sqlite',
                fields: [{name: 'id', datatype: 'INTEGER', nullable: false}],
              },
            ]
            : [],
      });

      await refresh();
      setOpen(false);
      onOpenModel(projectId, created);
    } catch (saveErr) {
      setCreateError(saveErr.message);
    } finally {
      setSaving(false);
    }
  };

  const total = groups.reduce((count, g) => count + g.models.length, 0);

  return (
    <Box
      component="section"
      aria-label="Data Models (ERD)"
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="erd-models" />
      <Toolbar label="Data model commands">
        <Button onClick={beginCreate}>New data model…</Button>
        <Button onClick={refresh}>Refresh</Button>
      </Toolbar>
      <Box
        role="tree"
        aria-label="Data models by project"
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
            message="No data models yet. Start a conceptual whiteboard sketch, logical model or physical ERD."
            actionLabel="New data model"
            onAction={beginCreate}
          />
        )}
        {!error &&
          groups
            .filter((g) => g.models.length || g.error)
            .map(({project, models, error: projErr}) => (
              <Box key={project.project_id} role="group">
                <TreeRow
                  level={1}
                  label={project.name}
                  expandable
                  expanded
                  warning={projErr}
                  icon={<Icon iconKey="object.schema" decorative />}
                />
                {models.map((model) => (
                  <TreeRow
                    level={2}
                    key={model.id}
                    label={model.title}
                    icon={<Icon iconKey="tool.erd" decorative />}
                    trailing={`v${model.head_version}`}
                    onOpen={() => onOpenModel(project.project_id, model)}
                  />
                ))}
              </Box>
            ))}
        <ProgressOverlay message={loading ? 'Loading data models' : ''} />
      </Box>

      <Dialog
        open={open}
        title="New data model (ERD)"
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
              Create data model
            </Button>
          </>
        }
      >
        <FormReference formKey="erd-model-create" />
        <Box sx={{display: 'grid', gap: 2}}>
          <TextField
            autoFocus
            required
            label="Model title"
            value={draft.title}
            onChange={(e) =>
              setDraft((cur) => ({...cur, title: e.target.value}))
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
            onChange={(val) => setDraft((cur) => ({...cur, project: val}))}
          />
          {draft.project === NEW_PROJECT && (
            <>
              <TextField
                required
                label="Project ID"
                value={draft.projectId}
                onChange={(e) =>
                  setDraft((cur) => ({...cur, projectId: e.target.value}))
                }
              />
              <TextField
                label="Project name"
                value={draft.projectName}
                onChange={(e) =>
                  setDraft((cur) => ({...cur, projectName: e.target.value}))
                }
              />
            </>
          )}
          <Select
            label="Starting role"
            value={draft.initialRole}
            options={[
              {
                value: 'conceptual',
                label: 'Conceptual whiteboard (free-form drafting)',
              },
              {value: 'logical', label: 'Logical data model'},
              {value: 'physical', label: 'Physical ERD'},
            ]}
            onChange={(val) =>
              setDraft((cur) => ({...cur, initialRole: val}))
            }
          />
          <TextField
            label="Initial entity or table name (optional)"
            value={draft.firstEntityName}
            onChange={(e) =>
              setDraft((cur) => ({...cur, firstEntityName: e.target.value}))
            }
          />
        </Box>
      </Dialog>
    </Box>
  );
}

ERDModelsNavigator.propTypes = {
  designClient: PropTypes.object,
  projectClient: PropTypes.object,
  onOpenModel: PropTypes.func,
};
