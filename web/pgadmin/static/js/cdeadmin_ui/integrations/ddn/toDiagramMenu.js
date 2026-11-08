/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The "To Diagram" submenu: the diagrams the user can edit, kept between
// menu openings (a context menu is built synchronously), plus New diagram.

import gettext from 'sources/gettext';
import pgAdmin from 'sources/pgadmin';
import getApiInstance from '../../../api_instance';
import {ProjectAssetClient} from '../../projects/ProjectAssetClient';
import {listDiagrams} from './diagrams';
import {loadDDNLibraries} from './library';
import {addToDiagram} from './toDiagram';

export const PROJECT_ASSET_OPEN_EVENT = 'cdeadmin:open-project-asset';

// Opened by the workbench's project-asset opener (BrowserComponent).
export function openProjectAsset(project, asset) {
  window.dispatchEvent(new CustomEvent(PROJECT_ASSET_OPEN_EVENT, {detail: {project, asset}}));
}

const WRITABLE = new Set(['owner', 'manager', 'editor']);
let choices = null;
let loading = null;

export function setDiagramChoices(groups) {
  choices = groups.filter(({project}) => WRITABLE.has(project.access))
    .flatMap(({project, diagrams}) => diagrams
      .filter((asset) => asset.editor_capable !== false && asset.access !== 'viewer')
      .map((asset) => ({project, asset})));
  return choices;
}

export function refreshDiagramChoices(client=new ProjectAssetClient()) {
  loading ??= listDiagrams(client).then(setDiagramChoices)
    .finally(() => { loading = null; });
  return loading;
}

// null while the first list is loading.
export function diagramChoices() {
  if(choices === null) refreshDiagramChoices().catch(() => {});
  return choices;
}

// Run a To Diagram choice: the node's database (or one of its tables and
// views) goes into the chosen diagram, which then opens.
export async function addNodeToDiagram({endpointUrl, args, client=new ProjectAssetClient(),
  libraries, post}) {
  const {project, asset} = args.diagram;
  const send = post ?? ((payload) => getApiInstance().post(endpointUrl, payload)
    .then((response) => response.data.data));
  const result = await addToDiagram({client, post: send,
    libraries: libraries ?? await loadDDNLibraries(),
    projectId: project.project_id, assetId: asset.asset_id,
    databaseTargetId: args.database_target_id,
    resourceIds: args.resource_kind ? [args.resource_id] : null});
  refreshDiagramChoices(client).catch(() => {});
  const message = result.added ?
    gettext('Added %s object(s) to %s.', result.added, asset.name) :
    gettext('%s already shows these objects; their definitions were refreshed.', asset.name);
  pgAdmin.Browser?.notifier?.success(result.dropped ?
    `${message} ${gettext('%s object(s) no longer in the database were removed.', result.dropped)}` : message);
  openProjectAsset(project, {...asset, version: result.saved?.version ?? asset.version});
  return result;
}

export function resetDiagramChoicesForTests() {
  choices = null; loading = null;
}
