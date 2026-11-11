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
import {Alert} from '@mui/material';
import {Box} from '../../primitives/Layout';
import {Icon} from '../../icons';
import {ProjectAssetClient} from '../../projects/ProjectAssetClient';
import {Toolbar} from '../../layout/WorkbenchChrome';
import {Button} from '../../primitives/Button';
import {TextArea, TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {TreeRow} from '../../navigation/AdvancedNavigation';
import {Dialog} from '../../overlays/Dialog';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import FormReference from '../../navigation/FormReference';
import {DesignStoreClient} from './sharedDesignLibrary';

export const BI_DESIGN_CREATE_EVENT = 'cdeadmin:bi-design-create';
export const BI_DESIGN_OPEN_EVENT = 'cdeadmin:bi-design-open';
const NEW_PROJECT = '\u0000new-project';
const WRITABLE = new Set(['owner', 'manager', 'editor']);
let pendingCreate = false;

export function requestBIDesignCreate() {
  pendingCreate = true;
  window.dispatchEvent(new CustomEvent(BI_DESIGN_CREATE_EVENT));
}

function takePendingCreate() {
  const pending = pendingCreate;
  pendingCreate = false;
  return pending;
}

export function openBIDesign(projectId, design) {
  window.dispatchEvent(
    new CustomEvent(BI_DESIGN_OPEN_EVENT, {
      detail: {
        projectId,
        designId: design.id,
        kind: design.kind,
        title: design.title,
      },
    })
  );
}

function slugKey(name, fallback = 'bi') {
  return (
    String(name || '')
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 64) || fallback
  );
}

export function BIDesignsNavigator({
  designClient: suppliedDesignClient,
  projectClient: suppliedProjectClient,
  onOpenDesign = openBIDesign,
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
  const [importSummary, setImportSummary] = useState(null);
  const [draft, setDraft] = useState({
    mode: 'new_question',
    title: '',
    project: '',
    projectId: 'analytics',
    projectName: 'Analytics BI',
    endpointId: 'default-endpoint',
    bundleJsonOrBase64: '',
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
              (d) => d.kind === 'question' || d.kind === 'dashboard'
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

  const beginCreate = useCallback(() => {
    setCreateError('');
    setDraft((cur) => ({
      ...cur,
      mode: 'new_question',
      title: '',
      bundleJsonOrBase64: '',
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
          mode: 'new_question',
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
    window.addEventListener(BI_DESIGN_CREATE_EVENT, listener);
    return () => window.removeEventListener(BI_DESIGN_CREATE_EVENT, listener);
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

      if (draft.mode === 'import_superset' || draft.mode === 'import_metabase') {
        const rawText = draft.bundleJsonOrBase64.trim();
        if (!rawText) {
          throw new Error(
            'Provide a JSON bundle or base64-encoded export archive.'
          );
        }
        let parsedBundle = null;
        let encodedArchive = null;
        if (rawText.startsWith('{')) {
          parsedBundle = JSON.parse(rawText);
        } else {
          encodedArchive = rawText;
        }
        const imported =
          draft.mode === 'import_superset'
            ? await designClient.importBiSuperset(projectId, {
                bundle: parsedBundle,
                zipBase64: encodedArchive,
                endpointId: draft.endpointId.trim() || 'default-endpoint',
              })
            : await designClient.importBiMetabase(projectId, {
                bundle: parsedBundle,
                bundleBase64: encodedArchive,
                endpointId: draft.endpointId.trim() || 'default-endpoint',
              });
        setImportSummary(imported.loss_report || null);
        await refresh();
        setOpen(false);
        const firstTarget =
          imported.dashboards?.[0] || imported.questions?.[0] || null;
        if (firstTarget) {
          onOpenDesign(projectId, firstTarget);
        }
        return;
      }

      const trimmedTitle = draft.title.trim();
      if (!trimmedTitle) {
        throw new Error('A BI question or dashboard needs a title.');
      }
      const key = `${slugKey(trimmedTitle)}-${Date.now().toString(36)}`;
      const created =
        draft.mode === 'new_dashboard'
          ? await designClient.createBiDashboard(projectId, {
              key,
              title: trimmedTitle,
            })
          : await designClient.createBiQuestion(projectId, {
              key,
              title: trimmedTitle,
              endpointId: draft.endpointId.trim() || 'default-endpoint',
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

  return (
    <Box
      component="section"
      aria-label="BI Questions and Dashboards"
      sx={{
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <FormReference formKey="bi-designs-navigator" />
      <Toolbar label="BI design commands">
        <Button onClick={beginCreate}>New BI design…</Button>
        <Button onClick={refresh}>Refresh</Button>
      </Toolbar>
      {importSummary && (
        <Alert severity="info" sx={{m: 1}}>
          Imported {importSummary.source_format} into Draft DDN (loss items:{' '}
          {importSummary.loss_count || 0}).
        </Alert>
      )}
      <Box
        role="tree"
        aria-label="BI designs by project"
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
            message="No BI questions or dashboards yet. Create a question, compose a dashboard or import Superset / Metabase exports."
            actionLabel="New BI design"
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
                    label={`${item.title} (${item.kind})`}
                    icon={<Icon iconKey="tool.data-explorer" decorative />}
                    trailing={`v${item.head_version}`}
                    onOpen={() => onOpenDesign(project.project_id, item)}
                  />
                ))}
              </Box>
            ))}
        <ProgressOverlay message={loading ? 'Loading BI designs' : ''} />
      </Box>

      <Dialog
        open={open}
        title="New or imported BI question or dashboard"
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
              Continue
            </Button>
          </>
        }
      >
        <FormReference formKey="bi-design-create" />
        <Box sx={{display: 'grid', gap: 2}}>
          <Select
            label="Mode"
            value={draft.mode}
            options={[
              {value: 'new_question', label: 'New BI question'},
              {value: 'new_dashboard', label: 'New BI dashboard'},
              {
                value: 'import_superset',
                label: 'Import Apache Superset YAML ZIP / JSON (Draft)',
              },
              {
                value: 'import_metabase',
                label: 'Import Metabase serialization bundle (Draft)',
              },
            ]}
            onChange={(val) => setDraft((cur) => ({...cur, mode: val}))}
          />
          {draft.mode === 'new_question' || draft.mode === 'new_dashboard' ? (
            <TextField
              autoFocus
              required
              label="Design title"
              value={draft.title}
              onChange={(e) =>
                setDraft((cur) => ({...cur, title: e.target.value}))
              }
            />
          ) : (
            <TextArea
              autoFocus
              required
              label="Bundle JSON or Base64 Archive"
              value={draft.bundleJsonOrBase64}
              onChange={(e) =>
                setDraft((cur) => ({
                  ...cur,
                  bundleJsonOrBase64: e.target.value,
                }))
              }
            />
          )}
          {draft.mode !== 'new_dashboard' && (
            <TextField
              label="Target Endpoint ID"
              value={draft.endpointId}
              onChange={(e) =>
                setDraft((cur) => ({...cur, endpointId: e.target.value}))
              }
            />
          )}
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

BIDesignsNavigator.propTypes = {
  designClient: PropTypes.object,
  projectClient: PropTypes.object,
  onOpenDesign: PropTypes.func,
};
