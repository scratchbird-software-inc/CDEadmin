import pgAdmin from 'sources/pgadmin';
import {providerTreeContextActions} from 'pgbrowser/ProviderContextMenu';
import {
  familyEditorContextActions, operationTarget, providerEndpointUrl, tryOpenFamilyEditor,
} from 'pgbrowser/ProviderObjectEditor';
import {descriptorClient, resetDescriptorClient} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {loadEngineBundle} from './familyFixtures';

jest.mock('sources/api_instance', () => () => ({
  get: jest.fn(async (url) => ({data: {success: 1, data: {__url: url}}})),
  post: jest.fn(async () => ({data: {success: 1, data: {}}})),
}));

const serverData = {_type: 'server', _id: 7, cde_endpoint: true, cde_engine_id: 'firebird', cde_profile_id: 'firebird-native',
  runtime_verification_state: 'verified', cde_session_authenticated: true, verified_runtime_version: '5.0.4'};
const tableData = {_type: 'cde_resource', cde_resource_kind: 'table', cde_resource_id: 'tbl-1', cde_engine_id: 'firebird',
  cde_database_target_id: 'db-1', label: 'ORDERS', cde_context_actions: []};
const groupData = {_type: 'cde_resource_group', cde_resource_kind: 'table', cde_engine_id: 'firebird', label: 'Tables',
  cde_context_actions: []};
const databaseData = {_type: 'cde_database_target', _id: 'db-1', cde_engine_id: 'firebird', label: 'employee.fdb',
  cde_context_actions: []};

function installTree(items) {
  // items: map of item -> {data, parent}
  pgAdmin.Browser.tree = {
    itemData: (item) => items[item]?.data,
    hasParent: (item) => Boolean(items[item]?.parent),
    parent: (item) => items[item]?.parent,
    selected: () => 'table',
  };
  pgAdmin.Browser.Nodes.server.generate_url = jest.fn(() => '/browser/server/cde_workspace/1/7');
  pgAdmin.Browser.docker.default_workspace.openTab = jest.fn();
  pgAdmin.Browser.docker.default_workspace.close = jest.fn();
}

async function primeBundle(engine) {
  resetDescriptorClient();
  const client = descriptorClient({get: async () => ({data: {success: 1, data: loadEngineBundle(engine)}}), post: async () => ({})});
  await client.bundle(engine, {version: '5.0.4'});
  return client;
}

describe('family editor tree glue', () => {
  beforeEach(() => {
    installTree({server: {data: serverData}, table: {data: tableData, parent: 'server'},
      group: {data: groupData, parent: 'server'}, database: {data: databaseData, parent: 'server'}});
  });

  it('builds the workspace endpoint url with the database target', () => {
    expect(providerEndpointUrl(pgAdmin.Browser.Nodes.server, 'server', serverData, 'db 1'))
      .toBe('/browser/server/cde_workspace/1/7?database_target_id=db%201');
    expect(providerEndpointUrl(pgAdmin.Browser.Nodes.server, 'server', serverData, null))
      .toBe('/browser/server/cde_workspace/1/7');
  });

  it('offers nothing until the bundle has arrived, then Edit, Create and tier 2/3 operations', async () => {
    resetDescriptorClient();
    expect(familyEditorContextActions(tableData, 'table')).toEqual([]);
    await primeBundle('firebird');
    const entries = familyEditorContextActions(tableData, 'table');
    expect(entries.find((entry) => entry.id === 'family-editor-edit')).toMatchObject({category: 'common', label: 'Edit...'});
    const reorder = entries.find((entry) => entry.id === 'descriptor-op-reorder_columns');
    expect(reorder).toMatchObject({category: 'maintenance', label: 'Reorder columns'});
    // a group node offers create for its kind; a database offers a Create submenu
    expect(familyEditorContextActions(groupData, 'group').map((entry) => entry.id)).toEqual(['family-editor-create-table']);
    const create = familyEditorContextActions(databaseData, 'database').find((entry) => entry.id === 'family-editor-create');
    expect(create.children.map((child) => child.label)).toEqual(expect.arrayContaining(['Table...', 'View...']));
    // database-level descriptor operations land in their categories
    const dbEntries = familyEditorContextActions(databaseData, 'database');
    expect(dbEntries.find((entry) => entry.id === 'descriptor-op-backup_logical').category).toBe('backup');
  });

  it('merges into the Object Explorer menu and retires legacy entries for the same operation', async () => {
    await primeBundle('firebird');
    const legacy = (commandId, label, group) => ({schema: 'cdeadmin.context-action.v1', command_id: commandId,
      command_version: 1, label, handler: 'open_workspace', icon_key: '', menu_group: group, priority: 10,
      mutation_class: 'admin', arguments: {}, enabled: true, macro_callable: true});
    const menu = providerTreeContextActions({...databaseData, cde_context_actions: [
      legacy('resource.firebird.database.backup_logical', 'Legacy backup', 'backup'),
      legacy('resource.firebird.database.something_else', 'Something else', 'maintenance'),
    ]}, 'database');
    const labels = JSON.stringify(menu);
    expect(labels).toContain('Logical backup (gbak)');
    expect(labels).not.toContain('Legacy backup');
    expect(labels).toContain('Something else');
    expect(menu[0].label).toBe('Create');
  });

  it('opens the editor panel for a kind with a declared editor and falls back otherwise', async () => {
    await primeBundle('firebird');
    const panel = await tryOpenFamilyEditor(tableData, 'table');
    expect(panel).toMatch(/^id-object-editor-/);
    expect(pgAdmin.Browser.docker.default_workspace.openTab).toHaveBeenCalledWith(
      expect.objectContaining({id: panel, title: 'Edit — ORDERS'}), 'id-main', 'middle');
    expect(await tryOpenFamilyEditor({...tableData, cde_resource_kind: 'service-operation'}, 'table')).toBe(false);
    expect(await tryOpenFamilyEditor({_type: 'server'}, 'server')).toBe(false);
  });

  it('stays out of the way when the endpoint session is not verified', async () => {
    installTree({server: {data: {...serverData, cde_session_authenticated: false}}, table: {data: tableData, parent: 'server'}});
    await primeBundle('firebird');
    expect(familyEditorContextActions(tableData, 'table')).toEqual([]);
    expect(await tryOpenFamilyEditor(tableData, 'table')).toBe(false);
  });
});

describe('operation targets', () => {
  it('inspects a tree resource and resolves a database node to its one database resource', async () => {
    const calls = [];
    const post = async (payload) => {
      calls.push(payload.action);
      if(payload.action === 'resource_inspect') return {resource_id: payload.request.resource_id, resource_kind: 'table'};
      return {items: [{resource_id: 'database:main', resource_kind: 'database'}, {resource_id: 'table:t', resource_kind: 'table'}]};
    };
    expect(await operationTarget(post, tableData)).toEqual({resource_id: 'tbl-1', resource_kind: 'table'});
    expect(await operationTarget(post, databaseData)).toEqual({resource_id: 'database:main', resource_kind: 'database'});
    expect(await operationTarget(post, groupData)).toBeNull();
    expect(calls).toEqual(['resource_inspect', 'resource_page']);
  });
});
