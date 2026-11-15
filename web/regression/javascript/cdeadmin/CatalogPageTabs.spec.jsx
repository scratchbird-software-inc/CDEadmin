/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo} from 'react';
import {act, fireEvent, render, screen, within} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import usePreferences from '../../../pgadmin/preferences/static/js/store';
import {PgAdminProvider} from 'sources/PgAdminProvider';
import {
  ProjectTopMenuRegistry,
  TActionsRegistry,
} from 'sources/cdeadmin_ui';
import {
  ProjectShellProvider,
  ProjectTopMenuBar,
  ProjectWorkbenchFrame,
} from 'sources/cdeadmin_ui/shell';
import {
  CatalogPageCoordinator,
  DataNavigatorWorkArea,
  ProjectShellDockerBridge,
  buildNavigatorSelectionConfig,
  catalogNodeIdentityKey,
  formatCatalogPageTitle,
} from 'sources/BrowserComponent';
import endpointProfiles from 'pgadmin.cdeadmin.endpoint_profiles';
import {BROWSER_PANELS} from '../../../pgadmin/browser/static/js/constants';
import {providerContextMenuItems} from '../../../pgadmin/browser/static/js/ProviderContextMenu';
import {ObjectEditor} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {ObjectInspectorSection} from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';
import uiCatalogs from '../../../pgadmin/static/js/cdeadmin_ui/i18n/ui_catalogs.json';

function createEventBus() {
  const listeners = new Map();
  return {
    on: jest.fn((event, handler) => {
      listeners.set(event, [...(listeners.get(event) || []), handler]);
    }),
    off: jest.fn((event, handler) => {
      listeners.set(
        event,
        (listeners.get(event) || []).filter((fn) => fn !== handler)
      );
    }),
    trigger: jest.fn((event, ...args) => {
      (listeners.get(event) || []).forEach((fn) => fn(...args));
    }),
  };
}

function makeAction({
  command_id,
  label,
  handler = 'open_workspace',
  menu_group = 'database',
  mutation_class = 'read',
  enabled = true,
  arguments: args = {},
}) {
  return {
    schema: 'cdeadmin.context-action.v1',
    command_id,
    label,
    menu_group,
    mutation_class,
    requires_confirmation: mutation_class === 'destructive',
    macro_callable: mutation_class !== 'destructive',
    enabled,
    disabled_reason: enabled ? null : 'Unavailable',
    handler,
    arguments: args,
  };
}

function createFakePgAdmin() {
  const events = createEventBus();
  let selectedItem = null;
  const itemDataMap = new Map();

  const registerNode = (id, data) => {
    const item = {
      id,
      _metadata: {data},
      getMetadata: () => data,
    };
    itemDataMap.set(item, data);
    return item;
  };

  const tree = {
    selected: jest.fn(() => selectedItem),
    itemData: jest.fn((item) => itemDataMap.get(item) || item?._metadata?.data || null),
    select: jest.fn(async (item) => {
      selectedItem = item;
    }),
    refresh: jest.fn(),
    getTreeNodeHierarchy: jest.fn(() => ({
      server: {_type: 'server', _id: 1, label: 'localhost'},
    })),
  };

  const pgAdmin = {
    Browser: {
      Events: events,
      tree,
      Nodes: {
        server: {
          hasStatistics: true,
          callbacks: {
            connect_server: jest.fn(),
            delete_obj: jest.fn(),
          },
        },
        database: {
          hasSQL: true,
          hasStatistics: true,
          callbacks: {
            connect_database: jest.fn(),
            show_obj_properties: jest.fn(),
            delete_obj: jest.fn(),
          },
        },
      },
    },
    DataGrid: {
      show_query_tool: jest.fn(),
    },
    __selectInTree: (item) => {
      selectedItem = item;
      const data = tree.itemData(item);
      events.trigger('pgadmin-browser:tree:selected', item, data);
    },
    __registerNode: registerNode,
  };

  return pgAdmin;
}

function CatalogShellHarness({pgAdmin, onExposeRegistries}) {
  const fetchImpl = useMemo(
    () => jest.fn().mockResolvedValue({ok: false, status: 404, json: async () => ({})}),
    []
  );
  const actionsRegistry = useMemo(() => new TActionsRegistry({fetchImpl}), [fetchImpl]);
  const menuRegistry = useMemo(() => new ProjectTopMenuRegistry(), []);

  if (onExposeRegistries) {
    onExposeRegistries({actionsRegistry, menuRegistry});
  }

  const applicationFactory = ({appId, instanceId, sequence, options = {}}) => {
    if (appId === 'data-navigator') {
      const hasBoundNode = Boolean(options.boundNodeData && options.boundNodeData._type);
      const isUnboundNavigator =
        options.isUnboundNavigator !== undefined
          ? Boolean(options.isUnboundNavigator)
          : !hasBoundNode;
      const boundItem = isUnboundNavigator ? null : options.boundNodeItem || null;
      const boundData = isUnboundNavigator ? null : options.boundNodeData || null;
      const navConfig = buildNavigatorSelectionConfig(
        pgAdmin,
        instanceId,
        boundItem,
        boundData,
        options.activeView || null
      );
      const resolvedTitle = isUnboundNavigator
        ? sequence > 1
          ? `Data Navigator #${sequence}`
          : 'Data Navigator'
        : options.title || navConfig.title;
      return {
        title: resolvedTitle,
        leftDrawerTitle: 'Data Navigator',
        leftDrawerSharedKey: 'data-navigator:shared-left-tree',
        supportsLeftDrawer: true,
        supportsRightDrawer: true,
        supportsTabbedIconBar: true,
        actions: navConfig.actions,
        menus: navConfig.menus,
        ribbonTabs: navConfig.ribbonTabs,
        meta: {
          isUnboundNavigator,
          catalogNodeKey: isUnboundNavigator
            ? null
            : options.catalogNodeKey || catalogNodeIdentityKey(boundData),
          boundNodeItem: boundItem,
          boundNodeData: boundData,
          activeView: navConfig.activeView,
        },
        renderLeftDrawer: () => <div data-testid="shared-navigator-tree">Catalog Tree</div>,
        renderWorkArea: () => <DataNavigatorWorkArea instanceId={instanceId} />,
        renderRightDrawer: () => <div>Inspector</div>,
      };
    }
    return null;
  };

  return (
    <PgAdminProvider value={pgAdmin}>
      <ProjectShellProvider
        username="dba@scratchrobin.org"
        actionsRegistry={actionsRegistry}
        menuRegistry={menuRegistry}
        applicationFactory={applicationFactory}
        fetchImpl={fetchImpl}
      >
        <ProjectShellDockerBridge />
        <CatalogPageCoordinator />
        <ProjectTopMenuBar />
        <div style={{height: 680}}>
          <ProjectWorkbenchFrame />
        </div>
      </ProjectShellProvider>
    </PgAdminProvider>
  );
}

describe('Catalog page tabs, active-page Tabbed-Icon-Bar icons, and work-area cleanup', () => {
  beforeEach(() => {
    window.localStorage.clear();
    usePreferences.setState({
      data: [{id: 1, cid: 1, mid: 1, module: 'misc', name: 'theme', value: 'light'}],
      version: 1,
      isLoading: false,
      failed: false,
    });
  });

  it('formats catalog page tab titles cleanly across database, server, connector, and object nodes', () => {
    expect(formatCatalogPageTitle(null)).toBe('Data Navigator');
    expect(
      formatCatalogPageTitle({_type: 'cde_database_target', label: 'firebird-demo'})
    ).toBe('database: firebird-demo');
    expect(formatCatalogPageTitle({_type: 'server', label: 'localhost'})).toBe(
      'server: localhost'
    );
    expect(formatCatalogPageTitle({_type: 'engine_type', label: 'Firebird'})).toBe(
      'connector: Firebird'
    );
    expect(
      formatCatalogPageTitle({
        _type: 'cde_resource',
        cde_resource_kind: 'table',
        label: 'MON$ATTACHMENTS',
      })
    ).toBe('table: MON$ATTACHMENTS');
  });

  it('binds first activation to "database: firebird-demo", puts all database/view icons + hints on the Tabbed-Icon-Bar with zero work-area tabs/buttons, switches multi-page icons, and cleans up on close', () => {
    const pgAdmin = createFakePgAdmin();
    let registries = null;

    const firebirdDbItem = pgAdmin.__registerNode('db-fb-demo', {
      _type: 'cde_database_target',
      _id: 'fb-demo-id',
      id: 'cde_database_target_fb_demo',
      label: 'firebird-demo',
      _label: 'firebird-demo',
      cde_engine_id: 'firebird',
      cde_profile_id: 'firebird-native',
      cde_database_target_id: 'fb-demo-id',
      cde_database: '/var/lib/firebird/data/firebird-demo.fdb',
      engine_display_name: 'Firebird 5.0',
      server_label: 'localhost',
      connected: true,
      cde_context_actions: [
        makeAction({
          command_id: 'database.firebird.connect',
          handler: 'verify_endpoint',
          label: 'Connect Firebird database...',
        }),
        makeAction({
          command_id: 'database.firebird.studio',
          handler: 'open_workspace',
          label: 'Open Firebird SQL editor...',
          arguments: {tab: 'studio'},
        }),
        makeAction({
          command_id: 'database.firebird.edit',
          handler: 'open_workspace',
          label: 'Edit Firebird database connection...',
          arguments: {tab: 'connections', database_mode: 'edit'},
        }),
        makeAction({
          command_id: 'database.firebird.drop',
          handler: 'open_workspace',
          label: 'Drop Firebird database...',
          mutation_class: 'destructive',
          arguments: {tab: 'connections', database_mode: 'drop'},
        }),
        // Even if a stale payload carried remove, Remove Database must NEVER appear
        makeAction({
          command_id: 'database.firebird.remove',
          handler: 'open_workspace',
          label: 'Remove database registration...',
          mutation_class: 'destructive',
        }),
      ],
    });

    const serverItem = pgAdmin.__registerNode('srv-localhost', {
      _type: 'server',
      _id: 101,
      id: 'server_101',
      label: 'localhost',
      _label: 'localhost',
      cde_endpoint: true,
      cde_endpoint_id: 'ep-fb-local',
      cde_engine_id: 'firebird',
      cde_profile_id: 'firebird-native',
      engine_display_name: 'Firebird 5.0',
      host: '127.0.0.1',
      port: 3050,
      username: 'SYSDBA',
      runtime_verification_state: 'verified',
      connected: true,
      cde_context_actions: [
        makeAction({
          command_id: 'endpoint.firebird.create_database',
          label: 'Create Firebird 5.0 database...',
        }),
        makeAction({
          command_id: 'endpoint.firebird.register_database',
          label: 'Register existing Firebird 5.0 database...',
        }),
        makeAction({
          command_id: 'endpoint.firebird.forget',
          label: 'Remove endpoint registration...',
          mutation_class: 'destructive',
        }),
      ],
    });

    const Component = withTheme(CatalogShellHarness);
    render(
      <Component
        pgAdmin={pgAdmin}
        onExposeRegistries={(r) => {
          registries = r;
        }}
      />
    );

    const getNotebookIcons = () =>
      Array.from(
        document.querySelectorAll('.sr-island-3b .snb-panel [data-snb-control]')
      ).map((el) => el.getAttribute('aria-label'));

    const getPageTabs = () =>
      within(screen.getByRole('tablist', {name: 'Open Pages'})).getAllByRole('tab');

    // 1. Open Data Navigator from Side Menu -> starts unbound ("Data Navigator")
    fireEvent.click(screen.getByRole('button', {name: 'Open Data Navigator'}));
    expect(getPageTabs().map((t) => t.getAttribute('aria-label'))).toEqual(['Data Navigator']);
    expect(getNotebookIcons()).toEqual(['Configure Database Engines', 'Refresh']);

    // 2. First activation: select firebird-demo -> renames tab in place to "database: firebird-demo"
    act(() => {
      pgAdmin.__selectInTree(firebirdDbItem);
    });

    expect(getPageTabs().map((t) => t.getAttribute('aria-label'))).toEqual([
      'database: firebird-demo',
    ]);
    expect(
      within(screen.getByRole('tablist', {name: 'Open Pages'})).getByRole('tab', {
        name: 'database: firebird-demo',
      })
    ).toHaveAttribute('aria-selected', 'true');

    // Database page icons on Tabbed-Icon-Bar: Properties, Statistics, Connect, Open SQL Editor,
    // Edit Connection / Settings, Drop Database, Refresh — and NO Remove Database!
    expect(getNotebookIcons()).toEqual([
      'Properties',
      'Statistics',
      'Connect',
      'Open SQL Editor',
      'Edit Connection / Settings',
      'Drop Database',
      'Refresh',
    ]);
    expect(getNotebookIcons()).not.toContain('Remove Database');

    // Hovering an icon on the Tabbed-Icon-Bar shows its hint with the action name
    const openSqlBtn = document.querySelector(
      '.sr-island-3b .snb-panel [aria-label="Open SQL Editor"]'
    );
    openSqlBtn.getBoundingClientRect = () => ({
      left: 200,
      right: 228,
      top: 80,
      bottom: 108,
      width: 28,
      height: 28,
    });
    fireEvent.mouseOver(openSqlBtn);
    const hoverHint = document.querySelector('[data-cdeadmin-qa-key="notebookbar-icon-hint"]');
    expect(hoverHint).toBeInTheDocument();
    expect(hoverHint).toHaveTextContent('Open SQL Editor');
    fireEvent.mouseLeave(document.querySelector('[data-cdeadmin-qa-key="project-application-notebookbar"]'));

    // Work Area (Area 3e) shows Database Properties with ZERO tabs and ZERO inline action buttons!
    const island3e = document.querySelector('[data-area-part="3e"]');
    expect(within(island3e).getByText(/Database Properties — firebird-demo/)).toBeInTheDocument();
    expect(within(island3e).getByText('/var/lib/firebird/data/firebird-demo.fdb')).toBeInTheDocument();
    expect(within(island3e).queryByRole('tablist')).not.toBeInTheDocument();
    expect(within(island3e).queryByRole('button', {name: /Connect/i})).not.toBeInTheDocument();
    expect(within(island3e).queryByRole('button', {name: /Open SQL Editor/i})).not.toBeInTheDocument();
    expect(within(island3e).queryByRole('button', {name: /Edit Connection/i})).not.toBeInTheDocument();
    expect(within(island3e).queryByRole('button', {name: /Remove Database/i})).not.toBeInTheDocument();
    expect(within(island3e).queryByRole('button', {name: /Drop Database/i})).not.toBeInTheDocument();

    // Object menu (Area 1) is populated with the database page's items (and NO Remove Database)
    fireEvent.click(screen.getByRole('menuitem', {name: 'Object'}));
    expect(screen.getByRole('menuitem', {name: 'Drop Database'})).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', {name: /Remove Database/i})).not.toBeInTheDocument();
    fireEvent.keyDown(document, {key: 'Escape'});

    // Clicking the Statistics icon on the Tabbed-Icon-Bar switches view without any work-area tabs
    const statsBtn = document.querySelector(
      '.sr-island-3b .snb-panel [aria-label="Statistics"]'
    );
    fireEvent.click(statsBtn);
    expect(
      document.querySelector('[data-cdeadmin-qa-key="data-navigator-work-area"]')
    ).toHaveAttribute('data-active-view', 'statistics');
    expect(within(island3e).queryByRole('tablist')).not.toBeInTheDocument();

    // 3. Load a second page ("server: localhost") without closing the first page ->
    //    adds its own tab and swaps Tabbed-Icon-Bar icons to ONLY the server page's icons!
    act(() => {
      pgAdmin.__selectInTree(serverItem);
    });

    expect(getPageTabs().map((t) => t.getAttribute('aria-label'))).toEqual([
      'database: firebird-demo',
      'server: localhost',
    ]);
    expect(
      within(screen.getByRole('tablist', {name: 'Open Pages'})).getByRole('tab', {
        name: 'server: localhost',
      })
    ).toHaveAttribute('aria-selected', 'true');

    // Tabbed-Icon-Bar icons are ALWAYS the ones for the currently active page ("server: localhost")
    expect(getNotebookIcons()).toEqual([
      'Properties',
      'Statistics',
      'Verify / Connect',
      'Create Database',
      'Register Database',
      'Remove Server',
      'Refresh',
    ]);
    expect(getNotebookIcons()).not.toContain('Drop Database');
    expect(getNotebookIcons()).not.toContain('Open SQL Editor');

    // 4. Switch back to "database: firebird-demo" via tab press ->
    //    restores database workarea (still on 'statistics' view!), database Object menu, and database icons!
    fireEvent.click(
      within(screen.getByRole('tablist', {name: 'Open Pages'})).getByRole('tab', {
        name: 'database: firebird-demo',
      })
    );
    expect(getNotebookIcons()).toEqual([
      'Properties',
      'Statistics',
      'Connect',
      'Open SQL Editor',
      'Edit Connection / Settings',
      'Drop Database',
      'Refresh',
    ]);
    expect(
      document.querySelector('[data-cdeadmin-qa-key="data-navigator-work-area"]')
    ).toHaveAttribute('data-active-view', 'statistics');

    // Switch back to Properties view via Properties icon on Tabbed-Icon-Bar
    fireEvent.click(
      document.querySelector('.sr-island-3b .snb-panel [aria-label="Properties"]')
    );
    expect(within(island3e).getByText(/Database Properties — firebird-demo/)).toBeInTheDocument();

    // 5. Close "database: firebird-demo" tab -> cleans up its actions/menus/icons and activates "server: localhost"
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="active-tab-close"]'));
    expect(getPageTabs().map((t) => t.getAttribute('aria-label'))).toEqual([
      'server: localhost',
    ]);
    expect(getNotebookIcons()).toEqual([
      'Properties',
      'Statistics',
      'Verify / Connect',
      'Create Database',
      'Register Database',
      'Remove Server',
      'Refresh',
    ]);
    // Verify closed database page actions were unregistered from TActionsRegistry
    expect(
      registries.actionsRegistry
        .list()
        .some((a) => a.id.includes('db_drop') || a.id.includes('db_open_sql'))
    ).toBe(false);

    // 6. Close "server: localhost" tab -> cleans up all remaining menus and icons and returns to User Dashboard
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="active-tab-close"]'));
    expect(screen.queryByRole('tablist', {name: 'Open Pages'})).not.toBeInTheDocument();
    expect(
      document.querySelector('[data-cdeadmin-qa-key="project-application-notebookbar"]')
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('menuitem', {name: 'Object'})).not.toBeInTheDocument();
    expect(
      registries.actionsRegistry.list().filter((a) => a.application === 'data-navigator')
    ).toHaveLength(0);
  });

  it('places connector profile/intent buttons onto the Tabbed-Icon-Bar and switches modes on click', () => {
    const fbServerProfile = {
      profile_id: 'firebird-native',
      display_name: 'Firebird 5.0',
      engine_display_name: 'Firebird 5.0',
      workflow: 'provider_endpoint',
      route_kind: 'network',
      default_port: 3050,
      engine_id: 'firebird',
      database_targeting: {
        mode: 'optional',
        multiple: true,
        create_and_activate: true,
      },
    };
    const fbEmbeddedProfile = {
      profile_id: 'firebird-embedded',
      display_name: 'Embedded (application host)',
      engine_display_name: 'Firebird 5.0',
      workflow: 'provider_endpoint',
      route_kind: 'embedded_file',
      default_port: null,
      engine_id: 'firebird',
    };
    endpointProfiles.profiles.push(fbServerProfile, fbEmbeddedProfile);

    try {
      const pgAdmin = createFakePgAdmin();
      pgAdmin.Browser.docker = {};
      const firebirdEngineItem = pgAdmin.__registerNode('eng-firebird', {
        _type: 'engine_type',
        _id: 'firebird',
        engine_id: 'firebird',
        label: 'Firebird',
        _label: 'Firebird',
      });

      const Component = withTheme(CatalogShellHarness);
      render(<Component pgAdmin={pgAdmin} />);

      act(() => {
        pgAdmin.__selectInTree(firebirdEngineItem);
      });

      const getNotebookIcons = () =>
        Array.from(
          document.querySelectorAll('.sr-island-3b .snb-panel [data-snb-control]')
        ).map((el) => el.getAttribute('aria-label'));

      const icons = getNotebookIcons();
      expect(icons).toContain('Firebird 5.0 (Server)');
      expect(icons).toContain('Embedded (application host) (This computer)');
      expect(icons).toContain('Register Server');
      expect(icons).toContain('Register Existing Database');
      expect(icons).toContain('Create Database');

      // Switch to Embedded host mode via the Tabbed-Icon-Bar icon -> updates intent icons to file intents!
      fireEvent.click(
        document.querySelector(
          '.sr-island-3b .snb-panel [aria-label="Embedded (application host) (This computer)"]'
        )
      );
      const embeddedIcons = getNotebookIcons();
      expect(embeddedIcons).toContain('Open Existing File');
      expect(embeddedIcons).toContain('Create New File');
      expect(embeddedIcons).not.toContain('Register Server');

      // Work Area (Area 3e) has zero inline mode buttons
      const island3e = document.querySelector('[data-area-part="3e"]');
      expect(
        within(island3e).queryByRole('button', {name: 'Firebird 5.0 (Server)'})
      ).not.toBeInTheDocument();
      expect(
        within(island3e).queryByRole('button', {name: 'Register Server'})
      ).not.toBeInTheDocument();
    } finally {
      const idx = endpointProfiles.profiles.indexOf(fbServerProfile);
      if (idx !== -1) endpointProfiles.profiles.splice(idx, 2);
    }
  });

  it('populates virtual tree spots (monitoring) with child item buttons that open the target page on click', async () => {
    const pgAdmin = createFakePgAdmin();
    pgAdmin.Browser.docker = {};

    const monAttachments = pgAdmin.__registerNode('mon-attachments', {
      _type: 'cde_resource',
      _id: 'table:MON$ATTACHMENTS',
      cde_resource_id: 'table:MON$ATTACHMENTS',
      cde_resource_kind: 'table',
      label: 'MON$ATTACHMENTS',
      _label: 'MON$ATTACHMENTS',
      icon: 'icon-table',
    });
    const monCallStack = pgAdmin.__registerNode('mon-call-stack', {
      _type: 'cde_resource',
      _id: 'table:MON$CALL_STACK',
      cde_resource_id: 'table:MON$CALL_STACK',
      cde_resource_kind: 'table',
      label: 'MON$CALL_STACK',
      _label: 'MON$CALL_STACK',
      icon: 'icon-table',
    });
    const monitoringGroup = pgAdmin.__registerNode('grp-monitoring', {
      _type: 'cde_resource_group',
      _id: 'grp_monitoring',
      label: 'monitoring',
      _label: 'monitoring',
      inode: true,
    });
    monitoringGroup.isExpanded = true;
    monitoringGroup.children = [monAttachments, monCallStack];

    const Component = withTheme(CatalogShellHarness);
    render(<Component pgAdmin={pgAdmin} />);

    act(() => {
      pgAdmin.__selectInTree(monitoringGroup);
    });

    const island3e = document.querySelector('[data-area-part="3e"]');
    expect(
      within(island3e).queryByText(/No information is available/i)
    ).not.toBeInTheDocument();
    const attachBtn = within(island3e).getByRole('button', {name: 'MON$ATTACHMENTS'});
    const callStackBtn = within(island3e).getByRole('button', {name: 'MON$CALL_STACK'});
    expect(attachBtn).toBeInTheDocument();
    expect(callStackBtn).toBeInTheDocument();

    // Clicking MON$CALL_STACK button selects it in the tree and opens its page tab!
    pgAdmin.Browser.tree.select.mockImplementation(async (item) => {
      pgAdmin.__selectInTree(item);
    });
    await act(async () => {
      fireEvent.click(callStackBtn);
    });

    const tabs = within(screen.getByRole('tablist', {name: 'Open Pages'})).getAllByRole('tab');
    expect(tabs.map((t) => t.getAttribute('aria-label'))).toContain('table: MON$CALL_STACK');
  });

  it('promotes ObjectEditor and ObjectInspectorSection tabs to Tabbed-Icon-Bar icons, renders auto-placing fields instead of tables, and opens context menu pages via ProjectShellDockerBridge', () => {
    const pgAdmin = createFakePgAdmin();
    pgAdmin.Browser.docker = {};

    const Component = withTheme(CatalogShellHarness);
    render(<Component pgAdmin={pgAdmin} />);

    // 1. Open an ObjectEditor tab through default_workspace (just as Edit... context menu does)
    const sampleForm = {
      family: 'server',
      family_title: 'Server',
      form_reference: 'SR-F-020033',
      tabs: [
        {
          tab: 'Connection',
          title: 'Connection',
          fields: [{field_id: 'host', label: 'Server host or address', control: 'text'}],
        },
        {
          tab: 'Authentication',
          title: 'Authentication',
          fields: [{field_id: 'username', label: 'User name', control: 'text'}],
        },
        {
          tab: 'SSL/TLS',
          title: 'SSL/TLS',
          fields: [{field_id: 'ssl_mode', label: 'SSL mode', control: 'text'}],
        },
      ],
    };

    act(() => {
      pgAdmin.Browser.docker.default_workspace.openTab({
        id: 'edit-server-1',
        title: 'Edit Server',
        content: (
          <ObjectEditor
            form={sampleForm}
            mode="edit"
            displayName="Server Properties — localhost"
            autoPlan={false}
          />
        ),
      });
    });

    const island3e = document.querySelector('[data-area-part="3e"]');
    // Internal horizontal tablist is gone from Area 3e!
    expect(within(island3e).queryByRole('tablist')).not.toBeInTheDocument();
    expect(within(island3e).getByLabelText(/Server host or address/i)).toBeInTheDocument();

    // Form tabs appear as icons on the Tabbed-Icon-Bar (Area 3b)!
    const getNotebookIcons = () =>
      Array.from(
        document.querySelectorAll('.sr-island-3b .snb-panel [data-snb-control]')
      ).map((el) => el.getAttribute('aria-label'));
    expect(getNotebookIcons()).toEqual(['Connection', 'Authentication', 'SSL/TLS']);

    // Clicking Authentication icon on Area 3b switches the active form section in Area 3e!
    fireEvent.click(
      document.querySelector('.sr-island-3b .snb-panel [aria-label="Authentication"]')
    );
    expect(within(island3e).getByLabelText(/User name/i)).toBeInTheDocument();

    // 2. Open an ObjectInspectorSection page (containedScroll=false) via default_workspace ->
    //    sections move to Area 3b icons and properties render as auto-placing fields with ZERO tables!
    act(() => {
      pgAdmin.Browser.docker.default_workspace.openTab({
        id: 'inspect-mon-call-stack',
        title: 'MON$CALL_STACK',
        content: (
          <ObjectInspectorSection
            containedScroll={false}
            resource={{
              resource_id: 'table:MON$CALL_STACK',
              display_name: 'MON$CALL_STACK',
              resource_kind: 'table',
              generation: 'current',
              provider_properties: {relation_id: 37, relation_type_name: 'monitoring'},
              extensions: {
                firebird: {
                  native: {
                    property_sections: ['properties', 'columns'],
                    columns: [{name: 'MON$CALL_ID', type: 'BIGINT'}],
                  },
                },
              },
            }}
          />
        ),
      });
    });

    expect(within(island3e).queryByRole('table')).not.toBeInTheDocument();
    expect(within(island3e).queryByLabelText('Object properties task')).not.toBeInTheDocument();
    expect(
      within(island3e).getAllByRole('group', {name: 'Native provider properties'}).length
    ).toBeGreaterThanOrEqual(1);
    expect(getNotebookIcons()).toEqual(['Summary', 'Columns']);

    // 3. Context menu Browse data / SQL editor calls workspace.focus(BROWSER_PANELS.SQL) -> opens SQL Editor page tab!
    act(() => {
      pgAdmin.Browser.docker.default_workspace.focus(BROWSER_PANELS.SQL);
    });
    const openTabNames = within(
      screen.getByRole('tablist', {name: 'Open Pages'})
    )
      .getAllByRole('tab')
      .map((t) => t.getAttribute('aria-label'));
    expect(openTabNames).toContain('SQL Editor');
  });

  it('ships complete 15-language catalogs and retranslates context menu items immediately on language switch', () => {
    const expectedLangs = [
      'en',
      'zh_Hans_CN',
      'zh_Hant_TW',
      'cs',
      'fr',
      'de',
      'id',
      'it',
      'ja',
      'ko',
      'pl',
      'pt_BR',
      'ru',
      'es',
      'sv',
    ];
    expect(Object.keys(uiCatalogs.shell)).toEqual(expect.arrayContaining(expectedLangs));
    const enShellKeys = Object.keys(uiCatalogs.shell.en);
    expect(enShellKeys.length).toBeGreaterThanOrEqual(95);
    expectedLangs.forEach((lang) => {
      expect(Object.keys(uiCatalogs.shell[lang])).toEqual(expect.arrayContaining(enShellKeys));
      if (lang !== 'en') {
        expect(Object.keys(uiCatalogs.gettext[lang]).length).toBeGreaterThanOrEqual(300);
      }
    });

    // Verify providerContextMenuItems dynamically retranslates stale backend strings
    const items = providerContextMenuItems({
      _type: 'cde_resource',
      cde_engine_id: 'firebird',
      cde_context_actions: [
        makeAction({
          command_id: 'object.firebird.browse',
          label: 'Procházet data',
          menu_group: 'object',
        }),
      ],
    });
    expect(items[0].label).toBe('Browse data');
  });
});
