/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The Query Tool is launched from the Data Explorer (owner direction
// 2026-11-05): a CDE engine node opens its provider's SQL workspace with the
// closest connection context; PostgreSQL nodes keep the pgAdmin Query Tool.

import pgAdmin from 'sources/pgadmin';
import {providerQueryTool} from 'pgbrowser/ProviderContextMenu';

const action = (overrides={}) => ({
  schema: 'cdeadmin.context-action.v1', command_version: 1, icon_key: 'action.script',
  menu_group: 'object', priority: 5, mutation_class: 'read', enabled: true,
  macro_callable: true, arguments: {}, ...overrides,
});

// A minimal Data Explorer: ids map to node data and parents.
function tree(nodes) {
  return {
    itemData: (id) => nodes[id]?.data,
    hasParent: (id) => Boolean(nodes[id]?.parent),
    parent: (id) => nodes[id]?.parent,
    selected: () => null,
  };
}

const NODES = {
  connector: {data: {_type: 'engine_type', cde_context_actions: [action({
    command_id: 'connector.mysql.register', handler: 'register_endpoint',
    label: 'Register MySQL server...'})]}},
  server: {data: {_type: 'server', cde_endpoint: true, _id: 7,
    runtime_verification_state: 'verified', cde_context_actions: [action({
      command_id: 'endpoint.mysql.verify', handler: 'verify_endpoint',
      label: 'Connect to MySQL server...'})]}},
  database: {parent: 'server', data: {_type: 'cde_database_target', cde_endpoint: true,
    cde_context_actions: [action({command_id: 'database.mysql.studio',
      handler: 'open_workspace', label: 'Open MySQL SQL editor...',
      arguments: {resource_id: 'db1', database_target_id: 'db1', tab: 'studio'}})]}},
  group: {parent: 'database', data: {_type: 'cde_resource_group', cde_endpoint: true,
    cde_context_actions: []}},
  table: {parent: 'group', data: {_type: 'cde_resource', cde_endpoint: true,
    cde_context_actions: [action({command_id: 'resource.mysql.table.edit',
      handler: 'open_workspace', label: 'Properties...', arguments: {tab: 'resources'}})]}},
  roles: {parent: 'server', data: {_type: 'cde_resource', cde_endpoint: true,
    cde_context_actions: []}},
  pgserver: {data: {_type: 'server', cde_endpoint: false}},
  pgdatabase: {parent: 'pgserver', data: {_type: 'database'}},
};

describe('Query Tool routing from the Data Explorer', () => {
  let openWorkspace;
  beforeEach(() => {
    openWorkspace = jest.fn();
    pgAdmin.Browser = {...pgAdmin.Browser, tree: tree(NODES),
      Nodes: {server: {callbacks: {open_cde_workspace: openWorkspace}}},
      notifier: {confirm: jest.fn()}};
  });

  it('opens the nearest SQL workspace with its connection context', () => {
    const tool = providerQueryTool(NODES.table.data, 'table');
    expect(tool.enabled).toBe(true);
    tool.open();
    expect(openWorkspace).toHaveBeenCalledWith({item: 'server'}, 'studio',
      expect.objectContaining({database_target_id: 'db1', tab: 'studio'}));
  });

  it('opens a server-scope SQL workspace from a connected server', () => {
    const tool = providerQueryTool(NODES.server.data, 'server');
    expect(tool.enabled).toBe(true);
    tool.open();
    expect(openWorkspace).toHaveBeenCalledWith({item: 'server'}, 'studio',
      {task_title: 'Query Tool'});
    // An object outside any database reaches its server.
    providerQueryTool(NODES.roles.data, 'roles').open();
    expect(openWorkspace).toHaveBeenLastCalledWith({item: 'server'}, 'studio',
      {task_title: 'Query Tool'});
  });

  it('is unavailable until the server is connected, and above the server', () => {
    NODES.server.data.runtime_verification_state = 'unverified';
    try {
      const tool = providerQueryTool(NODES.server.data, 'server');
      expect(tool.enabled).toBe(false);
      expect(tool.disabledReason).toMatch(/Connect to this server/);
    } finally {
      NODES.server.data.runtime_verification_state = 'verified';
    }
    const engine = providerQueryTool(NODES.connector.data, 'connector');
    expect(engine.enabled).toBe(false);
    expect(engine.open()).toBe(false);
  });

  it('leaves PostgreSQL nodes to the pgAdmin Query Tool', () => {
    expect(providerQueryTool(NODES.pgdatabase.data, 'pgdatabase')).toBeNull();
    expect(providerQueryTool(NODES.pgserver.data, 'pgserver')).toBeNull();
    expect(providerQueryTool(undefined, null)).toBeNull();
  });
});
