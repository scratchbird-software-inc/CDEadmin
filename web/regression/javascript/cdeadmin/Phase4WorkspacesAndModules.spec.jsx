/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import pgAdminSingleton from 'sources/pgadmin';
import {withTheme} from '../fake_theme';
import getApiInstance from '../../../pgadmin/static/js/api_instance';
import {initializeCDEadminPlatform} from 'sources/cdeadmin_ui/platform/bootstrap';
import {SurfaceHost} from 'sources/cdeadmin_ui/workspace/SurfaceHost';
import {ProjectExplorer} from 'sources/cdeadmin_ui/projects/ProjectExplorer';
import {
  activateSQLConnection,
  removeSQLConnections,
} from 'sources/cdeadmin_ui/editors/SQLConnections';
import {
  CommandLineWorkArea,
  PLATFORM_MODULE_DEFINITIONS,
  SQLStudioApplicationWorkArea,
  buildSqlStudioShellConfig,
} from '../../../pgadmin/static/js/BrowserComponent';
import {showProviderWorkspace} from '../../../pgadmin/static/js/Dialogs/index';
import ProviderWorkspaceContent from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';
import {bootstrap as sampleBootstrap} from './providerWorkspaceContentShared';

jest.mock('../../../pgadmin/static/js/api_instance');
jest.mock('../../../pgadmin/static/js/cdeadmin_ui/editors/CodeEditor', () => ({
  __esModule: true,
  default: ({label, value, onChange, disabled}) => (
    <textarea
      aria-label={label}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));

describe('Phase 4: SQL Studio, Dedicated Browse Data Grid, Command Line, and 14 Platform Modules', () => {
  let api;

  beforeEach(() => {
    api = {
      get: jest.fn(),
      post: jest.fn(),
    };
    getApiInstance.mockReturnValue(api);
    act(() => {
      removeSQLConnections('srv-phase4');
    });
  });

  afterEach(() => {
    act(() => {
      removeSQLConnections('srv-phase4');
    });
  });

  it('activates all 13 Platform Modules in bootstrap and enriches SurfaceHost tabs with 6-region chrome', async () => {
    const platform = await initializeCDEadminPlatform();
    expect(platform.mlVector).toBeDefined();
    expect(platform.aiInterface).toBeDefined();
    expect(platform.discoveryIntelligence).toBeDefined();

    const registeredSurfaces = platform.modules.surfaces.list();
    for (const mod of PLATFORM_MODULE_DEFINITIONS) {
      const found = mod.preferredSurfaceId
        ? registeredSurfaces.find((s) => s.id === mod.preferredSurfaceId)
        : registeredSurfaces.find((s) => s.moduleId === mod.moduleId);
      expect(found).toBeDefined();
    }

    const openedPanels = [];
    const stateUpdates = [];
    const docker = {
      openTab: jest.fn((panel) => openedPanels.push(panel)),
      close: jest.fn(),
      find: jest.fn(() => null),
      focus: jest.fn(),
      eventBus: {registerListener: jest.fn(() => () => {})},
    };
    const host = new SurfaceHost(docker, platform.modules.surfaces, {
      referencePanelId: 'id-main',
      context: () => ({
        services: {
          'project.assets': platform.projectAssets,
          'cdeadmin.ai_interface.runtime': platform.aiInterface,
          'cdeadmin.ml_vector.runtime': platform.mlVector,
        },
        commands: platform.modules.commands,
      }),
      enrichPanel: (descriptor) => ({
        appId: 'project-explorer',
        ribbonTabs: [{id: `ribbon-${descriptor.toolInstanceId}`, label: 'Workspace', groups: []}],
        statusText: `${descriptor.presentation.title} — Ready`,
      }),
      onStateUpdated: (toolId, state) => stateUpdates.push({toolId, state}),
    });

    const aiSurface = registeredSurfaces.find(
      (s) => s.id === 'cdeadmin.ai_interface.ai_workbench'
    );
    await host.open(aiSurface.id, {toolInstanceId: 'ai-test-tab', title: 'AI Assistant'});
    expect(openedPanels).toHaveLength(1);
    expect(openedPanels[0].appId).toBe('project-explorer');
    expect(openedPanels[0].ribbonTabs).toHaveLength(1);
    expect(openedPanels[0].statusText).toBe('AI Assistant — Ready');

    host.setSurfaceState('ai-test-tab', {persistence: 'dirty', problems: ['warn-1']});
    expect(stateUpdates).toHaveLength(1);
    expect(stateUpdates[0].state.persistence).toBe('dirty');
    host.dispose();
  });

  it('renders SQL Studio by default on sql-editor, switches to SQL Notebook via Area 3b, and receives SQL from BI', async () => {
    const projectAssets = {
      listProjects: jest.fn().mockResolvedValue([]),
    };
    const cfg = buildSqlStudioShellConfig({
      instanceId: 'sql-inst-1',
      title: 'SQL Editor',
      projectAssets,
      renderRightDrawer: () => null,
    });
    expect(cfg.ribbonTabs[0].groups).toHaveLength(3);
    expect(cfg.actions.some((a) => a.id === 'sql-editor.execute.sql-inst-1')).toBe(true);
    expect(cfg.actions.some((a) => a.id === 'sql-editor.mode.notebook.sql-inst-1')).toBe(true);

    const Wrapped = withTheme(SQLStudioApplicationWorkArea);
    render(<Wrapped instanceId="sql-inst-1" projectAssets={projectAssets} />);

    expect(await screen.findByLabelText('SQL source')).toBeInTheDocument();

    act(() => {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:open-sql-from-bi', {
          detail: {sql: 'SELECT COUNT(*) FROM ORDERS'},
        })
      );
    });
    await waitFor(() =>
      expect(screen.getByLabelText('SQL source')).toHaveValue('SELECT COUNT(*) FROM ORDERS')
    );

    act(() => {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:sql-editor-mode', {
          detail: {instanceId: 'sql-inst-1', mode: 'notebook'},
        })
      );
    });
    expect(await screen.findByText('SR-F-030058')).toBeInTheDocument();
  });

  it('opens a dedicated data: <table> tab on Browse Data and auto-loads StructuredDataGrid rows immediately', async () => {
    const openTab = jest.fn();
    pgAdminSingleton.Browser = pgAdminSingleton.Browser || {};
    pgAdminSingleton.Browser.docker = {
      default_workspace: {
        openTab,
        focus: jest.fn(),
        find: jest.fn(() => null),
        close: jest.fn(),
      },
    };
    showProviderWorkspace(
      'Browse Data',
      {generate_url: () => '/workspace/fb1'},
      {label: 'Demo FB', _id: 'srv-phase4'},
      {},
      'studio',
      {
        browse_data: true,
        resource_id: 'table:MON$ATTACHMENTS',
        display_name: 'MON$ATTACHMENTS',
        database_target_id: 'db-1',
      }
    );
    expect(openTab).toHaveBeenCalledTimes(1);
    const openedPanel = openTab.mock.calls[0][0];
    expect(openedPanel.title).toBe('data: MON$ATTACHMENTS');
    expect(openedPanel.iconKey).toBe('action.browse_data');

    api.get.mockResolvedValue({
      data: {
        data: {
          ...sampleBootstrap,
          resource_page: {
            generation: 1,
            items: [
              {
                resource_id: 'table:MON$ATTACHMENTS',
                resource_kind: 'table',
                display_name: 'MON$ATTACHMENTS',
                name: 'MON$ATTACHMENTS',
                database_target_id: 'db-1',
              },
            ],
          },
        },
      },
    });
    api.post.mockImplementation((_url, payload) => {
      if (payload.action === 'open_session') {
        return Promise.resolve({data: {data: {session_id: 'ds-1'}}});
      }
      if (payload.action === 'visual_admin_rows') {
        return Promise.resolve({
          data: {
            data: {
              columns: [{name: 'MON$ATTACHMENT_ID'}],
              rows: [{identity_token: 'row-1', values: {'MON$ATTACHMENT_ID': '10199'}}],
              continuation: null,
            },
          },
        });
      }
      return Promise.resolve({data: {data: {}}});
    });

    const WrappedContent = withTheme(() => openedPanel.content);
    render(<WrappedContent />);
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/workspace/fb1?database_target_id=db-1',
        expect.objectContaining({
          action: 'visual_admin_rows',
          request: expect.objectContaining({
            session_id: 'ds-1',
            database_target_id: 'db-1',
          }),
        })
      )
    );
    expect(await screen.findByText('10199')).toBeInTheDocument();
  });

  it('renders Command Line workspace (SR-F-030089) and executes interactive statements against active connection', async () => {
    activateSQLConnection({
      id: '/workspace/cli1',
      databaseTargetId: 'db-cli',
      serverId: 'srv-phase4',
      label: 'Demo Firebird CLI',
      engine: 'Firebird',
    });
    api.get.mockResolvedValue({
      data: {
        data: {
          languages: [{language_profile: 'firebird-sql', parameter_shape: 'array'}],
        },
      },
    });
    api.post.mockImplementation((_url, payload) => {
      if (payload.action === 'open_session') {
        return Promise.resolve({data: {data: {session_id: 'cli-sess-1'}}});
      }
      if (payload.action === 'execute') {
        return Promise.resolve({data: {data: {occurrence_id: 'cli-occ-1'}}});
      }
      if (payload.action === 'poll') {
        return Promise.resolve({
          data: {
            data: {
              occurrence: {operation: {terminal: true, status: 'completed'}},
              rendered_result: {
                view_model: {
                  columns: [{name: 'CURRENT_USER'}],
                  rows: [['SYSDBA']],
                  row_count: 1,
                },
              },
            },
          },
        });
      }
      return Promise.resolve({data: {data: {}}});
    });

    const WrappedCli = withTheme(CommandLineWorkArea);
    render(<WrappedCli instanceId="cli-inst-1" />);
    expect(screen.getByText('SR-F-030089')).toBeInTheDocument();
    expect(screen.getByText(/Demo Firebird CLI/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('CLI Statement'), {
      target: {value: 'SELECT CURRENT_USER FROM RDB$DATABASE'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Execute Statement'}));

    expect(await screen.findByText('SYSDBA')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith(
      '/workspace/cli1',
      expect.objectContaining({
        action: 'execute',
        session_id: 'cli-sess-1',
        source: 'SELECT CURRENT_USER FROM RDB$DATABASE',
        database_target_id: 'db-cli',
      })
    );
  });

  it('lists Platform Modules inside ProjectExplorer and invokes module launcher on open', async () => {
    const onOpenAi = jest.fn();
    const WrappedExplorer = withTheme(ProjectExplorer);
    render(
      <WrappedExplorer
        client={{listProjects: jest.fn().mockResolvedValue([])}}
        modules={[
          {id: 'module.open.ai', label: 'AI Assistant', iconKey: 'tool.ai', onOpen: onOpenAi},
          {id: 'module.open.ml_vector', label: 'ML & Vector', iconKey: 'tool.ml-vector', onOpen: jest.fn()},
        ]}
      />
    );
    expect(await screen.findByText('Platform Modules')).toBeInTheDocument();
    expect(screen.getByText('AI Assistant')).toBeInTheDocument();
    fireEvent.doubleClick(screen.getByRole('treeitem', {name: /AI Assistant/}));
    expect(onOpenAi).toHaveBeenCalledTimes(1);
  });
});
