/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import pgAdmin from 'sources/pgadmin';
import {
  canLaunchServerMenu,
  isProviderContextNode, providerContextMenuItems,
  providerTreeContextActions, registerProviderMenuCategories, openInheritedTool} from 'pgbrowser/ProviderContextMenu';

const action = (overrides={}) => ({
  schema: 'cdeadmin.context-action.v1',
  command_id: 'endpoint.firebird.verify',
  command_version: 1,
  label: 'Verify Firebird endpoint...',
  handler: 'verify_endpoint',
  icon_key: 'action.connect',
  menu_group: 'connection',
  priority: 10,
  mutation_class: 'read',
  arguments: {profile_id: 'firebird-native'},
  enabled: true,
  macro_callable: true,
  ...overrides,
});

describe('provider-owned Object Explorer menus', () => {
  it('admits the MySQL native topology workspace through its declared handler', () => {
    const menus=providerContextMenuItems({cde_context_actions:[action({
      command_id:'endpoint.mysql.topologies',handler:'open_mysql_topologies',
      label:'MySQL native topologies...',menu_group:'availability',mutation_class:'admin',
    })]});
    expect(menus).toHaveLength(1);
    expect(menus[0].commandId).toBe('endpoint.mysql.topologies');
  });
  it('puts common object actions directly on the popup, not in a submenu', () => {
    const menus = providerTreeContextActions({cde_context_actions: [action({
      command_id: 'resource.sqlite.table.create', label: 'New Table',
      menu_group: 'common', handler: 'open_workspace',
    })]});
    expect(menus).toHaveLength(1);
    expect(menus[0].label).toBe('New Table');
    expect(menus[0].children).toBeUndefined();
    expect(typeof menus[0].execute).toBe('function');
  });
  it('recognizes an explicit empty provider menu as authoritative', () => {
    expect(isProviderContextNode({cde_context_actions: []})).toBe(true);
    expect(providerContextMenuItems({cde_context_actions: []})).toEqual([]);
    expect(isProviderContextNode({_type: 'server'})).toBe(false);
  });

  it('maps admitted descriptors into command-backed menu options', () => {
    const node = {cde_context_actions: [action()]};
    const menus = providerContextMenuItems(node);
    expect(menus).toHaveLength(1);
    expect(menus[0]).toEqual(expect.objectContaining({
      commandId: 'endpoint.firebird.verify',
      label: 'Verify Firebird endpoint...',
      iconKey: 'action.connect',
      category: 'connection',
      intent: 'read',
      macroCallable: true,
    }));
    expect(menus[0].enable(node)).toBe(true);
    expect(menus[0].commandArguments({itemData: node})).toEqual({
      profile_id: 'firebird-native',
    });
  });

  it('binds arguments to the context-clicked node', () => {
    const first = action({
      command_id: 'resource.mysql.table.alter',
      handler: 'open_workspace',
      arguments: {resource_id: 'table:first'},
    });
    const current = {cde_context_actions: [{...first,
      enabled: false,
      arguments: {resource_id: 'table:current'},
    }]};
    const menu = providerContextMenuItems({
      cde_context_actions: [first],
    })[0];
    expect(menu.enable(current)).toBe(true);
    expect(menu.commandArguments({itemData: current})).toEqual({
      resource_id: 'table:first',
    });
  });

  it('drops forged schemas and browser handlers', () => {
    const node = {cde_context_actions: [
      action({schema: 'attacker.action.v1'}),
      action({handler: 'eval'}),
    ]};
    expect(providerContextMenuItems(node)).toEqual([]);
  });

  it('registers stable user-facing provider menu group labels', () => {
    const browser = {menu_categories: {}};
    registerProviderMenuCategories(browser, [{category: 'diagnostics'}, {
      category: 'database-lifecycle',
    }]);
    expect(browser.menu_categories.diagnostics.label).toBe(
      'Diagnostics and verification'
    );
    expect(browser.menu_categories['database-lifecycle'].label).toBe(
      'Definition and lifecycle'
    );
  });

  it('adapts authoritative provider actions for the new tree menu', () => {
    const node = {cde_context_actions: [
      action({
        command_id: 'database.firebird.repair_database',
        label: 'Repair database (gfix)...',
        handler: 'open_workspace',
        menu_group: 'maintenance',
        mutation_class: 'destructive',
        requires_confirmation: true,
      }),
      action({
        command_id: 'database.firebird.backup_logical',
        label: 'Logical backup (gbak)...',
        handler: 'open_workspace',
        menu_group: 'backup',
      }),
    ]};
    const groups = providerTreeContextActions(node, {id: 'database'});
    expect(groups.map((group)=>group.label)).toEqual([
      'Backup', 'Maintenance',
    ]);
    expect(groups[1].children[0]).toEqual(expect.objectContaining({
      id: 'database.firebird.repair_database',
      label: 'Repair database (gfix)...',
      intent: 'destructive',
      requiresConfirmation: true,
    }));
    expect(typeof groups[1].children[0].execute).toBe('function');
  });
  it('admits native MariaDB fleet and dashboard-editor commands alongside the other engine handlers', () => {
    const menus = providerContextMenuItems({cde_context_actions: [
      action({command_id: 'engine.mariadb.dashboard', handler: 'open_mariadb_fleet', label: 'MariaDB engine dashboard...'}),
      action({command_id: 'database.mariadb.dashboard_editor', handler: 'open_mariadb_dashboard_editor', label: 'Edit MariaDB dashboard...'}),
      action({command_id: 'untrusted', handler: 'unregistered_handler'}),
    ]});
    expect(menus.map(menu => menu.commandId)).toEqual(['engine.mariadb.dashboard', 'database.mariadb.dashboard_editor']);
    expect(menus.every(menu => typeof menu.commandHandler === 'function')).toBe(true);
  });
  it('admits and dispatches the inherited PostgreSQL utilities declared for provider nodes', () => {
    // M6 (2026-11-11): backup, restore, import/export and psql open through the identity bridge.
    const menus = providerContextMenuItems({cde_context_actions: [
      action({command_id: 'database.postgresql.backup', handler: 'open_inherited_tool', label: 'Backup...',
        menu_group: 'backup', arguments: {tool: 'backup', database_target_id: 'postgresql-database:16384'}}),
    ]});
    expect(menus.map(menu => menu.commandId)).toEqual(['database.postgresql.backup']);
    const backupObjects = jest.fn();
    pgAdmin.Browser.Backup = {backupObjects};
    openInheritedTool('backup', 'item-1');
    expect(backupObjects).toHaveBeenCalledWith(null, 'item-1');
    const startGrantWizard = jest.fn();
    pgAdmin.Browser.GrantWizard = {start_grant_wizard: startGrantWizard};
    openInheritedTool('grant_wizard', 'item-2');
    expect(startGrantWizard).toHaveBeenCalledWith(null, 'item-2');
    const maintenance = jest.fn();
    pgAdmin.Tools = {...(pgAdmin.Tools || {}), maintenance: {callback_maintenance: maintenance}};
    openInheritedTool('maintenance', 'item-3');
    expect(maintenance).toHaveBeenCalledWith({}, 'item-3');
    const debug = jest.fn();
    const breakpoint = jest.fn();
    const schemaDiff = jest.fn();
    pgAdmin.Tools = {...(pgAdmin.Tools || {}), Debugger: {getFunctionInformation: debug, checkFuncDebuggable: breakpoint},
      SchemaDiff: {launchSchemaDiff: schemaDiff}};
    openInheritedTool('debugger', 'item-4');
    expect(debug).toHaveBeenCalledWith({data: {debug_type: 'direct'}}, 'item-4');
    openInheritedTool('debugger_indirect', 'item-4');
    expect(breakpoint).toHaveBeenCalledWith({data: {debug_type: 'indirect'}}, 'item-4');
    openInheritedTool('schema_diff', 'item-5');
    expect(schemaDiff).toHaveBeenCalled();
    expect(() => openInheritedTool('vacuum', 'item-1')).toThrow(/not known/);
  });
  it('admits the PostgreSQL per-database dashboard the provider tree declares', () => {
    // M2 (2026-11-10): the inherited database node's dashboard, re-declared for provider nodes.
    const menus = providerContextMenuItems({cde_context_actions: [
      action({command_id: 'database.postgresql.monitoring', handler: 'open_postgresql_monitor',
        label: 'PostgreSQL dashboard...', menu_group: 'availability',
        arguments: {database_target_id: 'postgresql-database:16384'}}),
      action({command_id: 'database.postgresql.monitoring_policy', handler: 'open_postgresql_monitor',
        label: 'Configure PostgreSQL monitoring...', menu_group: 'availability', mutation_class: 'admin',
        arguments: {database_target_id: 'postgresql-database:16384', policy_mode: true}}),
    ]});
    expect(menus.map(menu => menu.commandId)).toEqual([
      'database.postgresql.monitoring', 'database.postgresql.monitoring_policy']);
    expect(menus.every(menu => typeof menu.commandHandler === 'function')).toBe(true);
  });

  it('exposes top-level Properties... on greyed-out localhost_placeholder and server nodes', () => {
    const localhostMenu = providerTreeContextActions({
      _type: 'localhost_placeholder',
      engine_id: 'firebird',
      label: 'localhost (not detected)',
      cde_context_actions: [action({
        command_id: 'connector.firebird.register_endpoint.firebird-native',
        handler: 'register_endpoint',
        menu_group: 'register',
        enabled: false,
      })],
    }, {id: 'firebird__localhost'});
    expect(localhostMenu[0]).toEqual(expect.objectContaining({
      id: 'localhost-server-properties',
      label: 'Properties...',
      iconKey: 'action.properties',
      enabled: true,
    }));
    expect(localhostMenu[0].children).toBeUndefined();

    const serverMenu = providerTreeContextActions({
      _type: 'server',
      cde_engine_id: 'firebird',
      cde_profile_id: 'firebird-native',
      runtime_verification_state: 'unverified',
      label: 'Firebird 5.0 on localhost',
      cde_context_actions: [action()],
    }, {id: 'server-1'});
    expect(serverMenu[0]).toEqual(expect.objectContaining({
      id: 'server-endpoint-properties',
      label: 'Properties...',
      iconKey: 'action.properties',
      enabled: true,
    }));
    expect(serverMenu[0].children).toBeUndefined();
    expect(serverMenu.map((entry) => entry.id)).toContain('server-endpoint-remove');
  });

  it('enforces logical hierarchy across engine_type, server and cde_database_target menus', () => {
    const engineMenu = providerTreeContextActions({
      _type: 'engine_type',
      engine_id: 'firebird',
      cde_context_actions: [action({
        command_id: 'connector.firebird.register_endpoint.firebird-native',
        label: 'Register Firebird 5.0 server / instance...',
        handler: 'register_endpoint',
        menu_group: 'register',
      })],
    }, {id: 'engine_type_firebird'});
    expect(engineMenu.map((m) => m.label)).toContain('Register Firebird 5.0 server / instance...');
    expect(engineMenu[0].children).toBeUndefined();

    const serverMenu = providerTreeContextActions({
      _type: 'server',
      cde_engine_id: 'firebird',
      cde_profile_id: 'firebird-native',
      cde_context_actions: [
        action({command_id: 'endpoint.firebird.register_again', handler: 'register_endpoint', label: 'Register another server...', menu_group: 'register'}),
        action({command_id: 'endpoint.firebird.create_database', handler: 'open_workspace', label: 'Create Firebird 5.0 database...', menu_group: 'database'}),
        action({command_id: 'endpoint.firebird.register_database', handler: 'open_workspace', label: 'Register existing Firebird 5.0 database...', menu_group: 'database'}),
        action({command_id: 'endpoint.firebird.forget', handler: 'open_workspace', label: 'Remove endpoint registration...', menu_group: 'endpoint', mutation_class: 'destructive'}),
      ],
    }, {id: 'server-fb'});
    const serverLabels = serverMenu.map((m) => m.label);
    expect(serverLabels[0]).toBe('Properties...');
    expect(serverLabels).toContain('Create Firebird 5.0 database...');
    expect(serverLabels).toContain('Register existing Firebird 5.0 database...');
    expect(serverLabels).toContain('Remove Server...');
    expect(serverLabels).not.toContain('Register another server...');

    const dbMenu = providerTreeContextActions({
      _type: 'cde_database_target',
      cde_engine_id: 'firebird',
      cde_database_target_id: 'fb-db-1',
      cde_context_actions: [
        action({command_id: 'endpoint.firebird.register_again', handler: 'register_endpoint', label: 'Register server...', menu_group: 'register'}),
        action({command_id: 'database.firebird.studio', handler: 'open_workspace', label: 'Open Firebird SQL editor...', menu_group: 'database', arguments: {tab: 'studio'}}),
        action({command_id: 'database.firebird.remove', handler: 'open_workspace', label: 'Remove database registration...', menu_group: 'database-lifecycle', mutation_class: 'destructive'}),
      ],
    }, {id: 'db-1'});
    const dbLabels = dbMenu.map((m) => m.label);
    expect(dbLabels).toContain('Properties...');
    expect(dbLabels).toContain('Open Firebird SQL editor...');
    expect(dbLabels).toContain('Remove database registration...');
    expect(dbLabels).not.toContain('Register server...');
  });

  it('keeps Register Database and Create Database selectable on unverified server nodes', () => {
    const unverifiedServer = {
      _type: 'server',
      cde_endpoint: true,
      cde_engine_id: 'firebird',
      cde_profile_id: 'firebird-native',
      runtime_verification_state: 'unverified',
      cde_context_actions: [
        action({
          command_id: 'endpoint.firebird.create_database',
          handler: 'open_workspace',
          label: 'Create Firebird database...',
          menu_group: 'database',
          enabled: false,
          disabled_reason: 'Verify this endpoint before using it.',
        }),
        action({
          command_id: 'endpoint.firebird.register_database',
          handler: 'open_workspace',
          label: 'Register existing Firebird database...',
          menu_group: 'database',
          enabled: false,
          disabled_reason: 'Verify this endpoint before using it.',
        }),
      ],
    };
    const rawMenus = providerContextMenuItems(unverifiedServer, {id: 'srv-1'});
    expect(canLaunchServerMenu(rawMenus[0], unverifiedServer, {id: 'srv-1'})).toBe(true);
    expect(canLaunchServerMenu(rawMenus[1], unverifiedServer, {id: 'srv-1'})).toBe(true);

    const treeMenus = providerTreeContextActions(unverifiedServer, {id: 'srv-1'});
    const registerEntry = treeMenus.find((m) => m.id === 'endpoint.firebird.register_database');
    const createEntry = treeMenus.find((m) => m.id === 'endpoint.firebird.create_database');
    expect(registerEntry.enabled).toBe(true);
    expect(createEntry.enabled).toBe(true);
  });
});
