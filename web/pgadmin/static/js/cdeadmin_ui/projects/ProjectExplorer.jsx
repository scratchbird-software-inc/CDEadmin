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
import gettext from 'sources/gettext';
import {useLocaleRevision} from '../actions/t_actions';
import {Box} from '../primitives/Layout';
import {ScratchScrollArea} from '../base/ScratchScrollArea';
import {Icon} from '../icons';
import {ProjectAssetClient} from './ProjectAssetClient';
import {Toolbar} from '../layout/WorkbenchChrome';
import {Button} from '../primitives/Button';
import {TextArea, TextField} from '../primitives/Field';
import {SearchField} from '../primitives/AdvancedControls';
import {TreeRow} from '../navigation/AdvancedNavigation';
import {Dialog} from '../overlays/Dialog';
import {EmptyState} from '../feedback/EmptyState';
import {ProgressOverlay} from '../feedback/ProgressOverlay';
import FormReference from '../navigation/FormReference';

function assetIcon(assetType) {
  if(assetType === 'ddn-workspace') return 'tool.erd';
  if(assetType === 'query' || assetType === 'script' || assetType === 'cdeadmin.sql-notebook.v1') return 'tool.query';
  if(assetType === 'semantic-model') return 'object.semantic_model';
  if(assetType === 'cube') return 'object.cube';
  return 'object.unknown';
}

export function ProjectExplorer({client: suppliedClient, onOpenAsset,
  onSelectAsset, onCreateProject, modules = []}) {
  useLocaleRevision();
  const client = useMemo(
    () => suppliedClient ?? new ProjectAssetClient(), [suppliedClient]
  );
  const [projects, setProjects] = useState([]);
  const [expanded, setExpanded] = useState(new Set(['__platform_modules__']));
  const [states, setStates] = useState({});
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [createDraft, setCreateDraft] = useState({id: '', name: '', description: ''});
  const [createError, setCreateError] = useState('');
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setProjects(await client.listProjects());
    } catch(loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => { refresh(); }, [refresh]);

  const beginCreate = useCallback(() => {
    if(onCreateProject) return onCreateProject();
    setCreateDraft({id: '', name: '', description: ''});
    setCreateError('');
    setCreateOpen(true);
  }, [onCreateProject]);

  useEffect(() => {
    const listener = () => beginCreate();
    window.addEventListener('cdeadmin:project-create', listener);
    return () => window.removeEventListener('cdeadmin:project-create', listener);
  }, [beginCreate]);

  const createProject = async () => {
    const id = createDraft.id.trim();
    if(!/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,255}$/.test(id)) {
      setCreateError('Project ID must be a stable identifier without spaces.');
      return;
    }
    setSaving(true);
    setCreateError('');
    try {
      await client.createProject(id, {
        name: createDraft.name.trim() || id,
        description: createDraft.description,
      });
      setCreateOpen(false);
      await refresh();
    } catch(saveError) {
      setCreateError(saveError.message);
    } finally {
      setSaving(false);
    }
  };

  const loadProject = async (project) => {
    setStates((current) => ({...current, [project.project_id]: {loading: true}}));
    try {
      const state = await client.project(project.project_id);
      setStates((current) => ({...current, [project.project_id]: state}));
    } catch(loadError) {
      setStates((current) => ({...current, [project.project_id]: {
        error: loadError.message,
      }}));
    }
  };

  const toggle = async (project) => {
    const next = new Set(expanded);
    if(next.has(project.project_id)) {
      next.delete(project.project_id);
      setExpanded(next);
      return;
    }
    next.add(project.project_id);
    setExpanded(next);
    if(states[project.project_id]) return;
    await loadProject(project);
  };

  const filter = query.trim().toLowerCase();
  const visibleProjects = projects.filter((project) =>
    `${project.name} ${project.project_id}`.toLowerCase().includes(filter) ||
    (states[project.project_id]?.assets ?? []).some((asset) =>
      `${asset.name} ${asset.path} ${asset.asset_type}`.toLowerCase().includes(filter)
    )
  );

  return <Box component="section" aria-label={gettext('Project Explorer')}
    sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}>
    <Toolbar label={gettext('Project Explorer commands')} trailing={<FormReference formKey="project-explorer" />}>
      <Button onClick={beginCreate}>{gettext('New project')}</Button>
      <Button onClick={refresh}>{gettext('Refresh')}</Button>
    </Toolbar>
    <Box sx={{p: 0.5}}><SearchField label={gettext('Filter projects and assets')}
      value={query} onChange={setQuery} resultCount={visibleProjects.length} /></Box>
    <ScratchScrollArea orientation="both" style={{flex: 1, minHeight: 0}}>
      <Box role="tree" aria-label={gettext('Projects and authored assets')}
        sx={{position: 'relative', minHeight: 120, p: 0.5}}>
        {error && <EmptyState role="alert" message={error} actionLabel={gettext('Retry')}
          onAction={refresh} />}
        {!error && !loading && !visibleProjects.length && <EmptyState
          message={gettext('No projects match this view. Create a project to store queries, diagrams, models, and other authored assets.')}
          actionLabel={gettext('New project')} onAction={beginCreate} />}
        {!error && visibleProjects.map((project, pIdx) => {
          const isExpanded = expanded.has(project.project_id);
          const state = states[project.project_id];
          const assets = (state?.assets ?? []).filter((asset) => !filter ||
            `${asset.name} ${asset.path} ${asset.asset_type}`.toLowerCase().includes(filter));
          return <Box key={project.project_id} role="group">
            <TreeRow level={1} label={project.name} expandable expanded={isExpanded}
              isLast={pIdx === visibleProjects.length - 1 && !modules.length}
              loading={state?.loading} warning={state?.error ?? ''}
              icon={<Icon iconKey="object.schema" decorative />}
              trailing={project.access === 'owner' ? gettext('Owner') : project.access}
              onToggle={() => toggle(project)} onOpen={() => toggle(project)} />
            {isExpanded && state?.error && <Box role="alert" sx={{pl: 4, py: 1}}>
              {state.error} <Button onClick={() => loadProject(project)}>
                {gettext('Retry')}
              </Button>
            </Box>}
            {isExpanded && !state?.loading && !state?.error && !assets.length &&
              <Box sx={{pl: 5, py: 1}}>{gettext('This project has no matching assets.')}</Box>}
            {isExpanded && assets.map((asset, aIdx) => <TreeRow level={2}
              key={asset.asset_id} label={asset.name}
              isLast={aIdx === assets.length - 1}
              icon={<Icon iconKey={assetIcon(asset.asset_type)} decorative />}
              warning={asset.validation_state === 'invalid' ? gettext('Validation failed') : ''}
              trailing={`v${asset.version}`}
              onSelect={() => onSelectAsset?.(project, asset)}
              onOpen={() => onOpenAsset?.(project, asset)} />)}
          </Box>;
        })}
        {modules.length > 0 && (() => {
          const visibleModules = modules.filter((mod) =>
            !filter || `${mod.label} ${mod.id}`.toLowerCase().includes(filter)
          );
          if (!visibleModules.length) return null;
          const modulesExpanded = expanded.has('__platform_modules__');
          const toggleModules = () => {
            const next = new Set(expanded);
            if (next.has('__platform_modules__')) next.delete('__platform_modules__');
            else next.add('__platform_modules__');
            setExpanded(next);
          };
          return <Box key="__platform_modules__" role="group">
            <TreeRow level={1} label={gettext('Platform Modules')} expandable
              expanded={modulesExpanded} isLast
              icon={<Icon iconKey="tool.project-explorer" decorative />}
              trailing={`${visibleModules.length}`}
              onToggle={toggleModules} onOpen={toggleModules} />
            {modulesExpanded && visibleModules.map((mod, mIdx) => (
              <TreeRow level={2} key={mod.id} label={mod.label}
                isLast={mIdx === visibleModules.length - 1}
                icon={<Icon iconKey={mod.iconKey || 'command.default'} decorative />}
                onSelect={() => mod.onOpen?.()}
                onOpen={() => mod.onOpen?.()} />
            ))}
          </Box>;
        })()}
        <ProgressOverlay message={loading ? gettext('Loading projects') : ''} />
      </Box>
    </ScratchScrollArea>
    <Dialog open={createOpen} title={gettext('New project')} size="medium" formKey="project-explorer"
      onClose={() => !saving && setCreateOpen(false)} busy={saving}
      validationError={createError} defaultAction={createProject}
      actions={<><Button disabled={saving}
        onClick={() => setCreateOpen(false)}>{gettext('Cancel')}</Button>
      <Button intent="primary" loading={saving}
        onClick={createProject}>{gettext('Create project')}</Button></>}>
      <Box sx={{display: 'grid', gap: 2}}>
        <TextField autoFocus required label={gettext('Project ID')} value={createDraft.id}
          onChange={(event) => setCreateDraft((current) => ({
            ...current, id: event.target.value,
          }))} helperText={gettext('Stable identity used by assets and source control.')} />
        <TextField label={gettext('Project name')} value={createDraft.name}
          onChange={(event) => setCreateDraft((current) => ({
            ...current, name: event.target.value,
          }))} />
        <TextArea label={gettext('Description')} value={createDraft.description}
          onChange={(event) => setCreateDraft((current) => ({
            ...current, description: event.target.value,
          }))} />
      </Box>
    </Dialog>
  </Box>;
}

ProjectExplorer.propTypes = {
  client: PropTypes.object,
  onOpenAsset: PropTypes.func,
  onSelectAsset: PropTypes.func,
  onCreateProject: PropTypes.func,
  modules: PropTypes.array,
};
