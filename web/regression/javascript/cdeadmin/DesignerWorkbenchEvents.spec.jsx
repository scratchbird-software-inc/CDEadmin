/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {act, render, screen, waitFor, within} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import {libraries, setupDDNDOM} from './ddnTestRuntime';
import {t_actions} from 'sources/cdeadmin_ui/actions/t_actions';
import {CommandRegistry} from 'sources/cdeadmin_ui/commands/CommandRegistry';
import {ModuleRegistry} from 'sources/cdeadmin_ui/platform/ModuleRegistry';
import {SurfaceRegistry} from 'sources/cdeadmin_ui/platform/SurfaceRegistry';
import {
  ContributionRegistry, PermissionRegistry, ServiceRegistry,
  WorkbenchContextService,
} from 'sources/cdeadmin_ui/platform/PlatformRegistry';
import {ToolFactoryRegistry} from 'sources/cdeadmin_ui/workspace/ToolRegistry';
import {SurfaceHost} from 'sources/cdeadmin_ui/workspace/SurfaceHost';
import {
  BIDesignerSurface,
  CubeDesignerSurface,
  ERDDesignerSurface,
  ScreenMeshDesignerSurface,
  resetDDNLibraryLoaderForTests,
  setDDNLibraryLoaderForTests,
} from 'sources/cdeadmin_ui/integrations/ddn';
import {ERD_MODULE_ID, registerERDModule} from
  'sources/cdeadmin_ui/integrations/ddn/erdModule';
import {CUBE_MODULE_ID, registerCubeModule} from
  'sources/cdeadmin_ui/integrations/ddn/cubeModule';
import {BI_DESIGNER_MODULE_ID, registerBIDesignerModule} from
  'sources/cdeadmin_ui/integrations/ddn/biDesignerModule';
import {SCREEN_MESH_MODULE_ID, registerScreenMeshModule} from
  'sources/cdeadmin_ui/integrations/ddn/screenMeshModule';
import {openERDModel} from
  'sources/cdeadmin_ui/integrations/ddn/ERDModelsNavigator';
import {openCubeDesign} from
  'sources/cdeadmin_ui/integrations/ddn/CubesNavigator';
import {openBIDesign} from
  'sources/cdeadmin_ui/integrations/ddn/BIDesignsNavigator';
import {openScreenMeshDesign} from
  'sources/cdeadmin_ui/integrations/ddn/ScreenMeshesNavigator';

// Extract bindDesignerOpenEvents without pulling heavyweight BrowserComponent
// workspace trees into jsdom.
import {bindDesignerOpenEvents} from 'sources/BrowserComponent';

function createMockDocker() {
  const panels = new Map();
  return {
    panels,
    openTab: jest.fn((panel) => panels.set(panel.id, panel)),
    close: jest.fn((id) => panels.delete(id)),
    find: jest.fn((id) => panels.get(id)),
    focus: jest.fn(),
    eventBus: {registerListener: jest.fn(() => jest.fn())},
  };
}

describe('BrowserComponent DDN designer open-event wiring', () => {
  it('opens ERD, Cube, BI (question & dashboard) and Screen Mesh surfaces in SurfaceHost', async () => {
    const tools = new ToolFactoryRegistry();
    const surfaces = new SurfaceRegistry(tools);
    const services = new ServiceRegistry();
    const modules = new ModuleRegistry({
      surfaces,
      services,
      commands: new CommandRegistry(),
      permissions: new PermissionRegistry(),
      inspector: new ContributionRegistry('inspector'),
      toolbox: new ContributionRegistry('toolbox'),
      status: new ContributionRegistry('status'),
      activity: new ContributionRegistry('activity'),
      bottom: new ContributionRegistry('bottom'),
    });
    const fakeDesignClient = {};

    registerERDModule({modules, services});
    registerCubeModule({modules, services});
    registerBIDesignerModule({modules, services});
    registerScreenMeshModule({modules, services});
    await modules.activate(ERD_MODULE_ID);
    await modules.activate(CUBE_MODULE_ID);
    await modules.activate(BI_DESIGNER_MODULE_ID);
    await modules.activate(SCREEN_MESH_MODULE_ID);

    const dock = createMockDocker();
    const host = new SurfaceHost(dock, surfaces, {
      referencePanelId: 'id-main',
      contextService: new WorkbenchContextService(),
      context: () => ({designStoreClient: fakeDesignClient}),
    });
    const notifyError = jest.fn();
    const unbind = bindDesignerOpenEvents(() => host, notifyError, window);

    try {
      openERDModel('proj-a', {id: 'erd-01', title: 'Billing ERD'});
      openCubeDesign('proj-a', {id: 'cube-01', title: 'Revenue Cube'});
      openBIDesign('proj-a', {
        id: 'dash-01',
        kind: 'dashboard',
        title: 'Executive Board',
      });
      openScreenMeshDesign('proj-a', {
        id: 'mesh-01',
        kind: 'screen',
        title: 'Order Entry Mesh',
      });

      await waitFor(() => {
        expect(dock.openTab).toHaveBeenCalledTimes(4);
      });
      expect(notifyError).not.toHaveBeenCalled();

      expect(
        dock.panels.get('diagram.erd.designer:proj-a:erd-01')?.title
      ).toBe('Billing ERD');
      expect(
        dock.panels.get('diagram.cube.designer:proj-a:cube-01')?.title
      ).toBe('Revenue Cube');
      const dashPanel = dock.panels.get('diagram.bi.designer:proj-a:dash-01');
      expect(dashPanel?.title).toBe('Executive Board');
      expect(dashPanel?.content?.props?.kind).toBe('dashboard');
      expect(
        dock.panels.get('diagram.screen_mesh.designer:proj-a:mesh-01')?.title
      ).toBe('Order Entry Mesh');
    } finally {
      unbind();
      host.dispose();
    }
  });

  describe('Workbench tool-action, palette-select, and default t_actions RBAC enforcement across all 4 designers', () => {
    const MIN_DDN = [
      'version ddn-next-1',
      'view "v_main" as "ddn@1"',
      '    with',
      '        id "v_main"',
      '        title "Main"',
      '        selection',
      '            include empty list',
      '',
    ].join('\n');

    beforeEach(() => {
      setupDDNDOM();
      setDDNLibraryLoaderForTests(async () => libraries);
      t_actions.setCurrentUser(null);
    });

    afterEach(() => {
      t_actions.setCurrentUser(null);
      resetDDNLibraryLoaderForTests();
    });

    it('handles scratchrobin:designer-tool-action and scratchrobin:designer-palette-select on ERD, Cube, BI, and Screen Mesh surfaces', async () => {
      // 1. ERDDesignerSurface: layers + checkpoints + palette stencil/udt
      const erdClient = {
        openSession: jest.fn(async () => ({
          design: {
            id: 'erd-1',
            project_id: 'models',
            kind: 'erd',
            title: 'Billing ERD',
            head_version: 1,
            active_version: null,
            version: {version: 1, status: 'draft', ddn_text: MIN_DDN},
            bindings: [],
          },
          workspace: {
            format: 'ddn-source-workspace@1',
            entry: 'erd.ddn',
            view: 'v_main',
            files: {'erd.ddn': MIN_DDN},
          },
          layout: {nodes: [], edges: [], tiles: []},
          binding_summary: {total: 0, valid: 0, suspect: 0, unknown: 0},
        })),
        inspectErdElements: jest.fn(async () => ({
          look_handdrawn: false,
          conceptual_entities: [{id: 'c1', name: 'Account', area: '', note: ''}],
          conceptual_relations: [],
          conceptual_notes: [],
          logical_entities: [],
          logical_relations: [],
          physical_tables: [],
          deployment_nodes: [],
          deployment_links: [],
          level_links: [],
          extensions: {},
        })),
        evaluateErdStandards: jest.fn(async () => ({
          violations: [],
          active_count: 0,
          waived_count: 0,
          rules: {},
          waivers: [],
        })),
        mutateErdElements: jest.fn(async () => ({
          design: {
            id: 'erd-1',
            title: 'Billing ERD',
            head_version: 2,
            version: {version: 2, status: 'draft', ddn_text: MIN_DDN},
          },
          elements: {
            look_handdrawn: false,
            conceptual_entities: [{id: 'c1', name: 'Account'}, {id: 'c2', name: 'Concept_2'}],
            physical_tables: [],
          },
        })),
        listVersions: jest.fn(async () => [{version: 1, status: 'draft', note: 'init'}]),
      };

      const ThemedErd = withTheme(ERDDesignerSurface);
      const {unmount: unmountErd} = render(
        <ThemedErd projectId="models" designId="erd-1" client={erdClient} />
      );
      await waitFor(() => expect(erdClient.openSession).toHaveBeenCalled());

      act(() => {
        window.dispatchEvent(
          new CustomEvent('scratchrobin:designer-tool-action', {
            detail: {appId: 'erd-designer', tool: 'layers'},
          })
        );
      });
      expect(
        await screen.findByText(/Switched ERD modelling level to conceptual/i)
      ).toBeInTheDocument();

      act(() => {
        window.dispatchEvent(
          new CustomEvent('scratchrobin:designer-palette-select', {
            detail: {appId: 'erd-designer', kind: 'stencil', itemId: 'concept'},
          })
        );
      });
      await waitFor(() => expect(erdClient.mutateErdElements).toHaveBeenCalled());

      act(() => {
        window.dispatchEvent(
          new CustomEvent('scratchrobin:designer-tool-action', {
            detail: {appId: 'erd-designer', tool: 'checkpoints'},
          })
        );
      });
      expect(await screen.findByRole('dialog')).toBeInTheDocument();
      unmountErd();

      // 2. CubeDesignerSurface: checkpoints + palette stencil ('measure')
      const cubeClient = {
        openSession: jest.fn(async () => ({
          design: {
            id: 'cube-1',
            project_id: 'analytics',
            kind: 'cube',
            title: 'Sales Cube',
            head_version: 1,
            version: {version: 1, status: 'draft', ddn_text: MIN_DDN},
            bindings: [],
          },
          workspace: {
            format: 'ddn-source-workspace@1',
            entry: 'cube.ddn',
            view: 'v_main',
            files: {'cube.ddn': MIN_DDN},
          },
          layout: {nodes: [], edges: [], tiles: []},
          binding_summary: {total: 0, valid: 0, suspect: 0, unknown: 0},
        })),
        getCubeModel: jest.fn(async () => ({
          cube: {
            model: {
              contract_version: '1.0.0',
              name: 'Sales Cube',
              sources: [{id: 'orders', kind: 'table', relation: ['orders'], grain: []}],
              dimensions: [],
              measures: [],
              measure_groups: [{id: 'mg1', name: 'Orders', fact_source: 'orders', measures: [], dimension_usage: []}],
            },
            element_ids: {},
            notes: [],
          },
        })),
        listVersions: jest.fn(async () => [{version: 1, status: 'draft', note: 'v1'}]),
      };

      const ThemedCube = withTheme(CubeDesignerSurface);
      const {unmount: unmountCube} = render(
        <ThemedCube projectId="analytics" designId="cube-1" client={cubeClient} />
      );
      await waitFor(() => expect(cubeClient.getCubeModel).toHaveBeenCalled());

      act(() => {
        window.dispatchEvent(
          new CustomEvent('scratchrobin:designer-palette-select', {
            detail: {appId: 'cube-designer', kind: 'stencil', itemId: 'measure'},
          })
        );
      });
      expect(await screen.findByRole('dialog')).toBeInTheDocument();
      unmountCube();

      // 3. BIDesignerSurface: checkpoints + palette stencil ('filter')
      const biClient = {
        openSession: jest.fn(async () => ({
          design: {
            id: 'bi-1',
            project_id: 'analytics',
            kind: 'dashboard',
            title: 'Exec Board',
            head_version: 1,
            version: {version: 1, status: 'draft', ddn_text: MIN_DDN},
            bindings: [],
          },
          workspace: {
            format: 'ddn-source-workspace@1',
            entry: 'bi.ddn',
            view: 'v_main',
            files: {'bi.ddn': MIN_DDN},
          },
          layout: {nodes: [], edges: [], tiles: []},
          binding_summary: {total: 0, valid: 0, suspect: 0, unknown: 0},
        })),
        getBiModel: jest.fn(async () => ({
          design: {id: 'bi-1', title: 'Exec Board', head_version: 1, version: {version: 1, status: 'draft'}},
          bi_kind: 'dashboard',
          bi: {
            dashboard: {
              contract_version: '1.0.0',
              name: 'Exec Board',
              tabs: [{id: 'main', name: 'Overview'}],
              cards: [],
              filters: [],
              links: [],
              interaction: {default_click_behavior: 'cross_filter'},
            },
          },
          outward_effects: [],
        })),
        listVersions: jest.fn(async () => [{version: 1, status: 'draft', note: 'v1'}]),
      };

      const ThemedBi = withTheme(BIDesignerSurface);
      const {unmount: unmountBi} = render(
        <ThemedBi projectId="analytics" designId="bi-1" kind="dashboard" client={biClient} />
      );
      await waitFor(() => expect(biClient.getBiModel).toHaveBeenCalled());

      act(() => {
        window.dispatchEvent(
          new CustomEvent('scratchrobin:designer-tool-action', {
            detail: {appId: 'bi-designer', tool: 'checkpoints'},
          })
        );
      });
      expect(await screen.findByRole('dialog')).toBeInTheDocument();
      unmountBi();

      // 4. ScreenMeshDesignerSurface: palette stencil ('grid') opens Add Control dialog
      const meshClient = {
        openSession: jest.fn(async () => ({
          design: {
            id: 'mesh-1',
            project_id: 'ui',
            kind: 'screen',
            title: 'Orders Mesh',
            head_version: 1,
            version: {version: 1, status: 'draft', ddn_text: MIN_DDN},
            bindings: [],
          },
          workspace: {
            format: 'ddn-source-workspace@1',
            entry: 'mesh.ddn',
            view: 'v_main',
            files: {'mesh.ddn': MIN_DDN},
          },
          layout: {nodes: [], edges: [], tiles: []},
          binding_summary: {total: 0, valid: 0, suspect: 0, unknown: 0},
        })),
        getScreenMeshModel: jest.fn(async () => ({
          design: {id: 'mesh-1', title: 'Orders Mesh', head_version: 1, version: {version: 1, status: 'draft'}},
          mesh: {
            name: 'Orders Mesh',
            look_handdrawn: false,
            screens: [{id: 's1', name: 'Main Screen', width: 960, height: 640}],
            controls: [],
            regions: [],
            bindings: [],
            navigations: [],
          },
          suspect_binding_count: 0,
        })),
      };

      const ThemedMesh = withTheme(ScreenMeshDesignerSurface);
      const {unmount: unmountMesh} = render(
        <ThemedMesh projectId="ui" designId="mesh-1" client={meshClient} />
      );
      await waitFor(() => expect(meshClient.getScreenMeshModel).toHaveBeenCalled());

      act(() => {
        window.dispatchEvent(
          new CustomEvent('scratchrobin:designer-palette-select', {
            detail: {appId: 'screen-mesh-designer', kind: 'stencil', itemId: 'grid'},
          })
        );
      });
      const ctrlDlg = await screen.findByRole('dialog');
      expect(within(ctrlDlg).getByLabelText('Control label')).toBeInTheDocument();
      unmountMesh();
    });

    it('enforces RBAC via default commands = t_actions when commands prop is omitted', async () => {
      // Restrict current user to save-only permissions (no *.accept or bi.designer.outward_review)
      t_actions.setCurrentUser({
        is_admin: false,
        permissions: [
          'erd.designer.save',
          'cube.designer.save',
          'bi.designer.save',
          'screen_mesh.designer.save',
        ],
      });

      const baseSession = {
        design: {
          id: 'd-1',
          project_id: 'p-1',
          title: 'RBAC Design',
          head_version: 1,
          version: {version: 1, status: 'draft', ddn_text: MIN_DDN},
          bindings: [],
        },
        workspace: {
          format: 'ddn-source-workspace@1',
          entry: 'd.ddn',
          view: 'v_main',
          files: {'d.ddn': MIN_DDN},
        },
        layout: {nodes: [], edges: [], tiles: []},
        binding_summary: {total: 0, valid: 0, suspect: 0, unknown: 0},
      };

      // 1. ERD Accept is disabled without erd.designer.accept, Save Checkpoint is enabled
      const erdClient = {openSession: jest.fn(async () => baseSession)};
      const ThemedErd = withTheme(ERDDesignerSurface);
      const {unmount: u1} = render(
        <ThemedErd projectId="p-1" designId="d-1" client={erdClient} />
      );
      await waitFor(() =>
        expect(screen.getByRole('button', {name: 'Save Checkpoint'})).not.toBeDisabled()
      );
      expect(screen.getByRole('button', {name: 'Accept'})).toBeDisabled();
      u1();

      // 2. Cube Accept Cube is disabled without cube.designer.accept
      const cubeClient = {
        openSession: jest.fn(async () => baseSession),
        getCubeModel: jest.fn(async () => ({
          cube: {
            model: {
              contract_version: '1.0.0',
              name: 'RBAC Cube',
              sources: [],
              dimensions: [],
              measures: [],
              measure_groups: [],
            },
            element_ids: {},
            notes: [],
          },
        })),
      };
      const ThemedCube = withTheme(CubeDesignerSurface);
      const {unmount: u2} = render(
        <ThemedCube projectId="p-1" designId="d-1" client={cubeClient} />
      );
      await waitFor(() =>
        expect(screen.getByRole('button', {name: 'Save Draft'})).not.toBeDisabled()
      );
      expect(screen.getByRole('button', {name: 'Accept Cube'})).toBeDisabled();
      u2();

      // 3. BI Accept is disabled without bi.designer.accept
      const biClient = {
        openSession: jest.fn(async () => baseSession),
        getBiModel: jest.fn(async () => ({
          design: baseSession.design,
          bi_kind: 'dashboard',
          bi: {
            dashboard: {
              contract_version: '1.0.0',
              name: 'RBAC Dash',
              tabs: [{id: 'main', name: 'Main'}],
              cards: [],
              filters: [],
              links: [],
            },
          },
          outward_effects: [],
        })),
      };
      const ThemedBi = withTheme(BIDesignerSurface);
      const {unmount: u3} = render(
        <ThemedBi projectId="p-1" designId="d-1" kind="dashboard" client={biClient} />
      );
      await waitFor(() =>
        expect(screen.getByRole('button', {name: 'Save Draft'})).not.toBeDisabled()
      );
      expect(screen.getByRole('button', {name: 'Accept'})).toBeDisabled();
      u3();

      // 4. Screen Mesh Accept is disabled without screen_mesh.designer.accept
      const meshClient = {
        openSession: jest.fn(async () => baseSession),
        getScreenMeshModel: jest.fn(async () => ({
          design: baseSession.design,
          mesh: {
            name: 'RBAC Mesh',
            screens: [{id: 's1', name: 'Screen 1', width: 800, height: 600}],
            controls: [],
            regions: [],
            bindings: [],
            navigations: [],
          },
          suspect_binding_count: 0,
        })),
      };
      const ThemedMesh = withTheme(ScreenMeshDesignerSurface);
      const {unmount: u4} = render(
        <ThemedMesh projectId="p-1" designId="d-1" client={meshClient} />
      );
      await waitFor(() =>
        expect(screen.getByRole('button', {name: 'Save Draft'})).not.toBeDisabled()
      );
      expect(screen.getByRole('button', {name: 'Accept'})).toBeDisabled();
      u4();
    });
  });
});
