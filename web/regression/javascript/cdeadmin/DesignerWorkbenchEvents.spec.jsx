/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {waitFor} from '@testing-library/react';
import {CommandRegistry} from 'sources/cdeadmin_ui/commands/CommandRegistry';
import {ModuleRegistry} from 'sources/cdeadmin_ui/platform/ModuleRegistry';
import {SurfaceRegistry} from 'sources/cdeadmin_ui/platform/SurfaceRegistry';
import {
  ContributionRegistry, PermissionRegistry, ServiceRegistry,
  WorkbenchContextService,
} from 'sources/cdeadmin_ui/platform/PlatformRegistry';
import {ToolFactoryRegistry} from 'sources/cdeadmin_ui/workspace/ToolRegistry';
import {SurfaceHost} from 'sources/cdeadmin_ui/workspace/SurfaceHost';
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
});
