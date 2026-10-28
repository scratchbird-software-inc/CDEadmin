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
  OperationDialog, ProviderObjectEditorHost, ServerRegistrationHost, descriptorClient, editorAvailable, makePost, menuForKind,
  visualAdminCalls,
} from 'sources/cdeadmin_ui/objects';
import {createRoot} from 'react-dom/client';
import Theme from 'sources/Theme';
import {providerEndpointSessionReady} from 'sources/cdeadmin_ui/navigation/providerDatabaseTree';
import {BROWSER_PANELS} from './constants';
import {generateNodeUrl} from './node_ajax';

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

function treeContext(itemData, item) {
  const endpoint = serverFor(item);
  if(!endpoint.data || !providerEndpointSessionReady(endpoint.data)) return null;
  const engine = itemData?.cde_engine_id || endpoint.data.cde_engine_id;
  if(!engine) return null;
  return {endpoint, engine, version: endpoint.data.verified_runtime_version, api: getApiInstance()};
}

function refreshNode(item, {parent=false}={}) {
  const tree = pgAdmin.Browser.tree;
  const target = parent && tree.hasParent(item) ? tree.parent(item) : item;
  const node = target ? pgAdmin.Browser.Nodes[tree.itemData(target)?._type] : null;
  node?.callbacks?.refresh?.call(node, null, target);
}

function openEditorPanel({context, itemData, item, resourceKind, resourceId, mode, displayName}) {
  const serverNode = pgAdmin.Browser.Nodes.server;
  const endpointUrl = providerEndpointUrl(serverNode, context.endpoint.item, context.endpoint.data,
    itemData.cde_database_target_id);
  const workspace = pgAdmin.Browser.docker.default_workspace;
  const panelId = `id-object-editor-${++editorSequence}`;
  const onClose = () => workspace.close(panelId);
  workspace.openTab({
    id: panelId,
    title: gettext('%s — %s', mode === 'create' ? gettext('Create') : gettext('Edit'), displayName),
    closable: true,
    floatable: true,
    content: <ErrorBoundary>
      <ProviderObjectEditorHost api={context.api} endpointUrl={endpointUrl} engine={context.engine}
        version={context.version} resourceId={resourceId} resourceKind={resourceKind}
        databaseTargetId={itemData.cde_database_target_id} mode={mode} displayName={displayName}
        onClose={onClose} onApplied={() => refreshNode(item, {parent: mode === 'alter'})}
        onOpenData={() => serverNode.callbacks.open_cde_workspace.call(serverNode, {item: context.endpoint.item}, 'data', {
          database_target_id: itemData.cde_database_target_id, resource_id: resourceId, resource_kind: resourceKind,
          display_name: displayName, task_title: gettext('Data')})} />
    </ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return panelId;
}

/**
 * Try to open the family editor for a tree resource. Resolves to the panel
 * id when it opened, or false when the legacy workspace should handle it.
 */
export async function tryOpenFamilyEditor(itemData, item, {mode='alter'}={}) {
  if(itemData?._type !== 'cde_resource' || !itemData.cde_resource_kind) return false;
  const context = treeContext(itemData, item);
  if(!context) return false;
  let bundle;
  try {
    bundle = await descriptorClient(context.api).bundle(context.engine, {version: context.version});
  } catch {
    // No descriptors served for this engine: the legacy workspace still works.
    return false;
  }
  if(!editorAvailable(bundle, itemData.cde_resource_kind)) return false;
  return openEditorPanel({context, itemData, item, resourceKind: itemData.cde_resource_kind,
    resourceId: itemData.cde_resource_id, mode, displayName: itemData.label || itemData._label});
}

/** Open the family editor in create mode for a child kind under a tree node. */
export function openFamilyCreate(itemData, item, resourceKind) {
  const context = treeContext(itemData, item);
  if(!context) return false;
  const bundle = descriptorClient(context.api).cached(context.engine, {version: context.version});
  if(!bundle || !editorAvailable(bundle, resourceKind)) return false;
  return openEditorPanel({context, itemData, item, resourceKind, resourceId: null, mode: 'create',
    displayName: `${itemData.label || itemData._label} / ${kindTitle(bundle, resourceKind)}`});
}

/** Run a tier 2/3 descriptor operation on a tree resource in the OperationDialog. */
export function openDescriptorOperation(itemData, item, operation) {
  const context = treeContext(itemData, item);
  if(!context) return false;
  const serverNode = pgAdmin.Browser.Nodes.server;
  const endpointUrl = providerEndpointUrl(serverNode, context.endpoint.item, context.endpoint.data,
    itemData.cde_database_target_id);
  const post = makePost(context.api, endpointUrl, itemData.cde_database_target_id);
  const mount = document.createElement('div');
  document.body.appendChild(mount);
  const root = createRoot(mount);
  const close = () => {
    root.unmount();
    mount.remove();
  };
  const run = async () => {
    const target = await operationTarget(post, itemData);
    const calls = visualAdminCalls(post, {resourceKind: itemData.cde_resource_kind, operationId: operation.operation_id, target});
    // Typed confirmations compare against the route database for database
    // nodes and the object name otherwise (what the providers validate).
    const targetName = itemData._type === 'cde_database_target' ?
      (itemData.cde_database || itemData.label || itemData._label) : (itemData.label || itemData._label);
    root.render(<Theme><OperationDialog open operation={operation} targetName={targetName}
      plan={({draft}) => calls.plan({draft})} apply={({plan}) => calls.apply({plan})}
      onClose={close} onApplied={() => refreshNode(item)} /></Theme>);
  };
  run();
  return true;
}

/**
 * The provider resource an operation targets. A tree resource inspects
 * itself; a database node carries a registration target id, not a provider
 * resource id, so it resolves to the one database resource of the page
 * scoped to that target (the legacy workspace resolves it the same way).
 */
export async function operationTarget(post, itemData) {
  if(itemData.cde_resource_id) {
    return post({action: 'resource_inspect', request: {resource_id: itemData.cde_resource_id}}).catch(() => null);
  }
  if(itemData._type !== 'cde_database_target') return null;
  const page = await post({action: 'resource_page', request: {}}).catch(() => null);
  const databases = (page?.items || []).filter((row) => row.resource_kind === 'database');
  return databases.length === 1 ? databases[0] : null;
}

function kindTitle(bundle, kind) {
  const title = bundle.kinds[kind]?.title || kind.replace(/-/g, ' ');
  return title.charAt(0).toUpperCase() + title.slice(1);
}

const CATEGORY_MAP = {
  create: 'common', open: 'common', lifecycle: 'database-lifecycle', maintenance: 'maintenance',
  backup_restore: 'backup', replication: 'availability', security: 'security', diagnostics: 'diagnostics',
  refresh: 'common',
};

/**
 * Context-menu entries from the engine's descriptor bundle for a tree node, in
 * the shape ObjectExplorer consumes. Returns [] until the bundle has arrived
 * (the first request starts the fetch) or when the kind declares nothing.
 */
export function familyEditorContextActions(itemData, item) {
  if(!['cde_resource', 'cde_resource_group', 'cde_database_target'].includes(itemData?._type)) return [];
  const context = treeContext(itemData, item);
  if(!context) return [];
  const bundle = descriptorClient(context.api).cached(context.engine, {version: context.version});
  if(!bundle) return [];
  const entries = [];
  const resourceKind = itemData._type === 'cde_database_target' ? 'database' : itemData.cde_resource_kind;
  if(itemData._type === 'cde_resource' && editorAvailable(bundle, resourceKind)) {
    entries.push({category: 'common', id: 'family-editor-edit', label: gettext('Edit...'), iconKey: 'action.edit',
      intent: 'default', enabled: true, execute: () => tryOpenFamilyEditor(itemData, item, {mode: 'alter'})});
  }
  // Create entries: a group node creates its own kind; a database creates any top-level kind.
  const childKinds = itemData._type === 'cde_resource_group' ? [itemData.cde_resource_kind] :
    itemData._type === 'cde_database_target' ?
      Object.values(bundle.kinds).filter((kind) => kind.family !== 'engine_object' && kind.tier1.includes('create') &&
        !['database', 'server'].includes(kind.resource_kind)).map((kind) => kind.resource_kind) : [];
  const creatable = childKinds.filter((kind) => editorAvailable(bundle, kind) && bundle.kinds[kind]?.tier1.includes('create'));
  if(creatable.length === 1) {
    entries.push({category: 'common', id: `family-editor-create-${creatable[0]}`,
      label: gettext('Create %s...', kindTitle(bundle, creatable[0])), iconKey: 'action.create',
      intent: 'default', enabled: true, execute: () => openFamilyCreate(itemData, item, creatable[0])});
  } else if(creatable.length > 1) {
    entries.push({category: 'common', id: 'family-editor-create', label: gettext('Create'), iconKey: 'action.create',
      intent: 'default', enabled: true, children: creatable.map((kind) => ({
        id: `family-editor-create-${kind}`, label: `${kindTitle(bundle, kind)}...`, iconKey: 'action.create',
        intent: 'default', enabled: true, execute: () => openFamilyCreate(itemData, item, kind)}))});
  }
  if(itemData._type !== 'cde_resource_group') {
    for(const group of menuForKind(bundle, resourceKind)) {
      for(const entry of group.items) {
        if(!entry.tier || entry.tier === 1) continue; // tier 1 is the editor; legacy items cover the rest for now
        entries.push({category: CATEGORY_MAP[group.category] || 'operations', id: `descriptor-op-${entry.operation_id}`,
          label: entry.label, iconKey: 'action.operation', intent: entry.tier === 3 ? 'default' : 'default',
          enabled: entry.enabled !== false, disabledReason: entry.disabled_reason,
          execute: () => openDescriptorOperation(itemData, item,
            bundle.kinds[resourceKind].operations.find((op) => op.operation_id === entry.operation_id))});
      }
    }
  }
  return entries;
}

/**
 * Open the descriptor Server editor for registering ('create', under a server group item) or
 * editing ('alter', on a server item) a provider endpoint. Resolves true when it opened and false
 * when the legacy dialog must handle it: no bundle, or the engine's server form is not complete.
 */
export async function tryOpenServerForm({item, mode='create', engine, profileId, initialData={}, intent='endpoint',
  verifyNow=true, panelTitle}) {
  if(!engine || !item) return false;
  const api = getApiInstance();
  let bundle;
  try {
    bundle = await descriptorClient(api).bundle(engine);
  } catch {
    return false;
  }
  const form = bundle?.forms?.server;
  if(!form || form.status !== 'complete' || !editorAvailable(bundle, 'server')) return false;
  const tree = pgAdmin.Browser.tree;
  const serverNode = pgAdmin.Browser.Nodes.server;
  const nodeData = tree.itemData(item);
  const treeNodeInfo = tree.getTreeNodeHierarchy(item);
  const base = generateNodeUrl.call(serverNode, treeNodeInfo, mode === 'create' ? 'create' : 'edit', nodeData, false,
    serverNode.url_jump_after_node);
  const urlFor = (isNew) => base + (isNew ? '' : nodeData._id);
  const workspace = pgAdmin.Browser.docker.default_workspace;
  const panelId = mode === 'create' ? `id-server-register-${++editorSequence}` : `id-server-edit-${nodeData._id}`;
  const onClose = () => workspace.close(panelId);
  const onSaved = (response) => {
    setTimeout(() => serverNode.clear_cache?.(item), 0);
    if(mode === 'create') {
      pgAdmin.Browser.Events.trigger('pgadmin:browser:tree:add', {...response.node}, {...treeNodeInfo});
    } else {
      pgAdmin.Browser.Events.trigger('pgadmin:browser:tree:update', nodeData, response.node, treeNodeInfo, {
        success: (updated, next, previous) => {
          pgAdmin.Browser.Events.trigger('pgadmin:browser:node:updated', updated, next, previous);
          pgAdmin.Browser.Events.trigger('pgadmin:browser:node:server:updated', updated, next, previous);
        },
      });
    }
    onClose();
  };
  workspace.openTab({
    id: panelId, title: panelTitle || gettext('Register server'), closable: true, floatable: true,
    content: <ErrorBoundary>
      <ServerRegistrationHost api={api} engine={engine} version={nodeData.verified_runtime_version}
        mode={mode === 'create' ? 'create' : 'alter'} urlFor={urlFor} initialData={initialData} profileId={profileId}
        intent={intent} verifyNow={verifyNow} displayName={panelTitle} onClose={onClose} onSaved={onSaved} />
    </ErrorBoundary>,
  }, BROWSER_PANELS.MAIN, 'middle');
  return true;
}
