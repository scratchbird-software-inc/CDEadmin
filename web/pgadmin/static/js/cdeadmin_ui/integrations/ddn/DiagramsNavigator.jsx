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
import {loadDDNLibraries} from './library';
import {
  DEFAULT_DIAGRAM_NOTATION, DIAGRAM_NOTATIONS, createDiagram, diagramNotation,
  listDiagrams,
} from './diagrams';

export const DIAGRAM_CREATE_EVENT = 'cdeadmin:diagram-create';
export const PROJECT_ASSET_OPEN_EVENT = 'cdeadmin:open-project-asset';
const NEW_PROJECT = '\u0000new-project';
let pendingCreate = false;

// Tools > New Diagram can run before this panel is mounted; the request is
// kept until the panel takes it.
export function requestDiagramCreate() {
  pendingCreate = true;
  window.dispatchEvent(new CustomEvent(DIAGRAM_CREATE_EVENT));
}

function takePendingCreate() {
  const pending = pendingCreate;
  pendingCreate = false;
  return pending;
}

export function openProjectAsset(project, asset) {
  window.dispatchEvent(new CustomEvent(PROJECT_ASSET_OPEN_EVENT, {detail: {project, asset}}));
}

const WRITABLE = new Set(['owner', 'manager', 'editor']);

export function DiagramsNavigator({client: suppliedClient, libraries,
  onOpenDiagram=openProjectAsset}) {
  const client = useMemo(() => suppliedClient ?? new ProjectAssetClient(), [suppliedClient]);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({name: '', project: '', projectId: 'diagrams',
    projectName: 'Diagrams', notation: DEFAULT_DIAGRAM_NOTATION});
  const [createError, setCreateError] = useState('');
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const loaded = await listDiagrams(client);
      setGroups(loaded);
      return loaded;
    } catch(loadError) {
      setError(loadError.message);
      return [];
    } finally { setLoading(false); }
  }, [client]);

  const writable = groups.filter(({project}) => WRITABLE.has(project.access));
  const beginCreate = useCallback(() => {
    setCreateError('');
    setDraft((current) => ({...current, name: '',
      project: current.project || writable[0]?.project.project_id || NEW_PROJECT}));
    setOpen(true);
  }, [writable]);

  useEffect(() => {
    refresh().then((loaded) => {
      if(takePendingCreate()) {
        const first = loaded.find(({project}) => WRITABLE.has(project.access));
        setDraft((current) => ({...current, name: '',
          project: first?.project.project_id || NEW_PROJECT}));
        setOpen(true);
      }
    });
  }, [refresh]);
  useEffect(() => {
    const listener = () => { takePendingCreate(); beginCreate(); };
    window.addEventListener(DIAGRAM_CREATE_EVENT, listener);
    return () => window.removeEventListener(DIAGRAM_CREATE_EVENT, listener);
  }, [beginCreate]);

  const create = async () => {
    setSaving(true); setCreateError('');
    try {
      let projectId = draft.project;
      if(projectId === NEW_PROJECT) {
        projectId = draft.projectId.trim();
        if(!/^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,255}$/.test(projectId)) {
          throw new Error('Project ID must be a stable identifier without spaces.');
        }
        await client.createProject(projectId, {name: draft.projectName.trim() || projectId});
      }
      const {payload} = await createDiagram(client, libraries ?? await loadDDNLibraries(), {
        projectId, name: draft.name, notation: draft.notation});
      const loaded = await refresh();
      setOpen(false);
      const group = loaded.find(({project}) => project.project_id === projectId);
      const asset = group?.diagrams.find((item) => item.asset_id === payload.assetRef.assetId);
      if(group && asset) onOpenDiagram(group.project, asset);
    } catch(saveError) {
      setCreateError(saveError.message);
    } finally { setSaving(false); }
  };

  const notation = diagramNotation(draft.notation);
  const total = groups.reduce((count, group) => count + group.diagrams.length, 0);
  return <Box component="section" aria-label="Diagrams"
    sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}>
    <FormReference formKey="diagrams" />
    <Toolbar label="Diagram commands">
      <Button onClick={beginCreate}>New diagram…</Button>
      <Button onClick={refresh}>Refresh</Button>
    </Toolbar>
    <Box role="tree" aria-label="Diagrams by project"
      sx={{position: 'relative', flex: 1, minHeight: 0, overflow: 'auto'}}>
      {error && <EmptyState role="alert" message={error} actionLabel="Retry" onAction={refresh} />}
      {!error && !loading && !total && <EmptyState
        message="No diagrams yet. A new diagram starts empty, in crow's foot notation by default."
        actionLabel="New diagram" onAction={beginCreate} />}
      {!error && groups.filter((group) => group.diagrams.length || group.error).map(({project, diagrams, error: projectError}) =>
        <Box key={project.project_id} role="group">
          <TreeRow level={1} label={project.name} expandable expanded
            warning={projectError} icon={<Icon iconKey="object.schema" decorative />} />
          {diagrams.map((asset) => <TreeRow level={2} key={asset.asset_id} label={asset.name}
            icon={<Icon iconKey="tool.erd" decorative />}
            trailing={diagramNotation(asset.metadata.diagram.notation)?.label ?? asset.metadata.diagram.notation}
            onOpen={() => onOpenDiagram(project, asset)} />)}
        </Box>)}
      <ProgressOverlay message={loading ? 'Loading diagrams' : ''} />
    </Box>
    <Dialog open={open} title="New diagram" size="medium"
      onClose={() => !saving && setOpen(false)} busy={saving}
      validationError={createError} defaultAction={create}
      actions={<><Button disabled={saving} onClick={() => setOpen(false)}>Cancel</Button>
        <Button intent="primary" loading={saving} onClick={create}>Create diagram</Button></>}>
      <FormReference formKey="diagram-create" />
      <Box sx={{display: 'grid', gap: 2}}>
        <TextField autoFocus required label="Diagram name" value={draft.name}
          onChange={(event) => setDraft((current) => ({...current, name: event.target.value}))} />
        <Select label="Project" value={draft.project}
          options={[...writable.map(({project}) => ({value: project.project_id, label: project.name})),
            {value: NEW_PROJECT, label: 'New project…'}]}
          onChange={(value) => setDraft((current) => ({...current, project: value}))} />
        {draft.project === NEW_PROJECT && <>
          <TextField required label="Project ID" value={draft.projectId}
            helperText="Stable identity used by assets and source control."
            onChange={(event) => setDraft((current) => ({...current, projectId: event.target.value}))} />
          <TextField label="Project name" value={draft.projectName}
            onChange={(event) => setDraft((current) => ({...current, projectName: event.target.value}))} />
        </>}
        <Select label="Notation" value={draft.notation}
          options={DIAGRAM_NOTATIONS.map((item) => ({value: item.id, disabled: !item.available,
            label: item.available ? item.label : `${item.label} (no catalog mapping yet)`}))}
          helperText={notation?.available ? 'The notation of the first view. DDN can add views in other notations later.' : notation?.reason}
          onChange={(value) => setDraft((current) => ({...current, notation: value}))} />
      </Box>
    </Dialog>
  </Box>;
}

DiagramsNavigator.propTypes = {
  client: PropTypes.object,
  libraries: PropTypes.object,
  onOpenDiagram: PropTypes.func,
};
