/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Tree-side glue for the family object editor (design phase 2): when a
 * provider resource is activated and its engine's descriptor bundle declares
 * a family editor for that kind, open the editor in a docked panel. Returns
 * false when no editor applies so the caller can fall back to the legacy
 * provider workspace. Holds no engine knowledge.
 */

import pgAdmin from 'sources/pgadmin';
import gettext from 'sources/gettext';
import getApiInstance from 'sources/api_instance';
import ErrorBoundary from 'sources/helpers/ErrorBoundary';
import {
  ProviderObjectEditorHost, descriptorClient, editorAvailable,
} from 'sources/cdeadmin_ui/objects';
import {providerEndpointSessionReady} from 'sources/cdeadmin_ui/navigation/providerDatabaseTree';
import {BROWSER_PANELS} from './constants';

let editorSequence = 0;

function serverFor(item) {
  const tree = pgAdmin.Browser.tree;
  let current = item;
  while(current) {
    const data = tree.itemData(current);
    if(data?._type === 'server') return {item: current, data};
    current = tree.hasParent(current) ? tree.parent(current) : null;
  }
  return {item: null, data: null};
}

export function providerEndpointUrl(serverNode, serverItem, serverData, databaseTargetId) {
  const generated = serverNode.generate_url(serverItem, 'cde_workspace', serverData, true);
  if(!databaseTargetId) return generated;
  return `${generated}${generated.includes('?') ? '&' : '?'}database_target_id=${encodeURIComponent(databaseTargetId)}`;
}

/**
 * Try to open the family editor for a tree resource. Resolves to the panel
 * id when it opened, or false when the legacy workspace should handle it.
 */
export async function tryOpenFamilyEditor(itemData, item, {mode='alter'}={}) {
  if(itemData?._type !== 'cde_resource' || !itemData.cde_resource_kind) return false;
  const endpoint = serverFor(item);
  if(!endpoint.data || !providerEndpointSessionReady(endpoint.data)) return false;
  const engine = itemData.cde_engine_id || endpoint.data.cde_engine_id;
  if(!engine) return false;
  const api = getApiInstance();
  let bundle;
  try {
    bundle = await descriptorClient(api).bundle(engine, {version: endpoint.data.verified_runtime_version});
  } catch {
    // No descriptors served for this engine: the legacy workspace still works.
    return false;
  }
  if(!editorAvailable(bundle, itemData.cde_resource_kind)) return false;

  const serverNode = pgAdmin.Browser.Nodes.server;
  const endpointUrl = providerEndpointUrl(serverNode, endpoint.item, endpoint.data, itemData.cde_database_target_id);
  const workspace = pgAdmin.Browser.docker.default_workspace;
  const panelId = `id-object-editor-${++editorSequence}`;
  const displayName = itemData.label || itemData._label;
  const onClose = () => workspace.close(panelId);
  const refreshParent = () => {
    const tree = pgAdmin.Browser.tree;
    const parent = tree.hasParent(item) ? tree.parent(item) : null;
    const node = parent ? pgAdmin.Browser.Nodes[tree.itemData(parent)?._type] : null;
    node?.callbacks?.refresh?.call(node, null, parent);
  };
  workspace.openTab({
    id: panelId,
    title: gettext('%s — %s', mode === 'create' ? gettext('Create') : gettext('Edit'), displayName),
    closable: true,
    floatable: true,
    content: <ErrorBoundary>
      <ProviderObjectEditorHost api={api} endpointUrl={endpointUrl} engine={engine}
        version={endpoint.data.verified_runtime_version} resourceId={itemData.cde_resource_id}
        resourceKind={itemData.cde_resource_kind} databaseTargetId={itemData.cde_database_target_id}
        mode={mode} displayName={displayName} onClose={onClose} onApplied={refreshParent} />
    </ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}
