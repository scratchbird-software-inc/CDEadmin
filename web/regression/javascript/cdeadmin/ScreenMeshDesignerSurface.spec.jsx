/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import {libraries, setupDDNDOM} from './ddnTestRuntime';
import {
  ScreenMeshDesignerSurface,
  ScreenMeshesNavigator,
  resetDDNLibraryLoaderForTests,
  screenMeshModuleDefinition,
  setDDNLibraryLoaderForTests,
} from 'sources/cdeadmin_ui/integrations/ddn';

const SAMPLE_MESH_DDN = [
  'version ddn-next-1',
  '// ScratchRobin module: scratchrobin.screen.mesh@1',
  '',
  'element "019a0000-0000-7000-8000-000000000101" as "ui.frame"',
  '    with',
  '        id "019a0000-0000-7000-8000-000000000101"',
  '        title "Orders Screen"',
  '        metadata',
  '            x_ui',
  '                form_reference "SR-F-020073"',
  '',
  'element "019a0000-0000-7000-8000-000000000102" as "ui.frame"',
  '    with',
  '        id "019a0000-0000-7000-8000-000000000102"',
  '        title "Order Detail Modal"',
  '',
  'element "019a0000-0000-7000-8000-000000000103" as "ui.grid"',
  '    with',
  '        id "019a0000-0000-7000-8000-000000000103"',
  '        title "Orders Grid"',
  '        metadata',
  '            x_diagram',
  '                owner "019a0000-0000-7000-8000-000000000101"',
  '            x_ui',
  '                columns',
  '                    item',
  '                        id "order_id"',
  '                        name "Order ID"',
  '                        width 120',
  '                        datatype "integer"',
  '',
  'element "019a0000-0000-7000-8000-000000000104" as "ui.region"',
  '    with',
  '        id "019a0000-0000-7000-8000-000000000104"',
  '        title "KPI Summary Region"',
  '        metadata',
  '            x_diagram',
  '                owner "019a0000-0000-7000-8000-000000000101"',
  '            x_ui',
  '                bounds',
  '                    x 20',
  '                    y 16',
  '                    width 240',
  '                    height 64',
  '',
  'relation "019a0000-0000-7000-8000-000000000105" as "navigation"',
  '    endpoint "019a0000-0000-7000-8000-000000000103"',
  '    endpoint "019a0000-0000-7000-8000-000000000102"',
  '    with',
  '        id "019a0000-0000-7000-8000-000000000105"',
  '        title "Open Detail"',
  '        metadata',
  '            x_ui',
  '                trigger "click"',
  '                action "overlay"',
  '',
  'view "screen_mesh_main" as "wireframe.ui@1"',
  '    with',
  '        id "screen_mesh_main"',
  '        title "Orders Workbench"',
  '        selection',
  '            include',
  '                item',
  '                    id "019a0000-0000-7000-8000-000000000101"',
  '                item',
  '                    id "019a0000-0000-7000-8000-000000000102"',
  '                item',
  '                    id "019a0000-0000-7000-8000-000000000103"',
  '                item',
  '                    id "019a0000-0000-7000-8000-000000000104"',
  '                item',
  '                    id "019a0000-0000-7000-8000-000000000105"',
  '',
  'view "screen_flow" as "wireframe.ui@1"',
  '    with',
  '        id "screen_flow"',
  '        title "Orders Workbench — Screen Flow"',
  '        selection',
  '            include',
  '                item',
  '                    id "019a0000-0000-7000-8000-000000000101"',
  '                item',
  '                    id "019a0000-0000-7000-8000-000000000102"',
  '                item',
  '                    id "019a0000-0000-7000-8000-000000000103"',
  '                item',
  '                    id "019a0000-0000-7000-8000-000000000105"',
  '',
].join('\n');

function makeMeshSession({status = 'draft', version = 1} = {}) {
  return {
    design: {
      id: '019a0000-0000-7000-8000-000000000100',
      project_id: 'ui-meshes',
      key: 'orders-workbench',
      kind: 'screen',
      title: 'Orders Workbench',
      head_version: version,
      active_version: status === 'accepted' ? version : null,
      version: {
        version,
        status,
        ddn_text: SAMPLE_MESH_DDN,
      },
      bindings: [],
    },
    workspace: {
      format: 'ddn-source-workspace@1',
      entry: 'orders-workbench.ddn',
      view: 'screen_mesh_main',
      files: {'orders-workbench.ddn': SAMPLE_MESH_DDN},
    },
    layout: {
      algorithm: 'scratchrobin-server-layered@1',
      nodes: [],
      edges: [],
      tiles: [],
    },
    resolved_includes: [],
    binding_summary: {total: 1, valid: 0, suspect: 1, unknown: 0},
  };
}

function makeMeshPayload({
  version = 1,
  suspect = true,
  screenshotSha = 'a'.repeat(64),
} = {}) {
  return {
    design: makeMeshSession({version}).design,
    mesh: {
      name: 'Orders Workbench',
      screens: [
        {
          id: '019a0000-0000-7000-8000-000000000101',
          name: 'Orders Screen',
          width: 960,
          height: 640,
          form_reference: 'SR-F-020073',
          screenshot_path: 'screenshots/019a0000-0000-7000-8000-000000000101.png',
          screenshot_sha256: screenshotSha,
          notes: '',
        },
        {
          id: '019a0000-0000-7000-8000-000000000102',
          name: 'Order Detail Modal',
          width: 640,
          height: 480,
          form_reference: '',
          screenshot_path: '',
          screenshot_sha256: '',
          notes: '',
        },
      ],
      controls: [
        {
          id: '019a0000-0000-7000-8000-000000000103',
          screen_id: '019a0000-0000-7000-8000-000000000101',
          role: 'ui.grid',
          name: 'Orders Grid',
          columns: [
            {
              id: 'order_id',
              name: 'Order ID',
              width: 120,
              datatype: 'integer',
            },
          ],
          options: [],
          placeholder: '',
          checked: false,
          notes: '',
        },
      ],
      regions: [
        {
          id: '019a0000-0000-7000-8000-000000000104',
          screen_id: '019a0000-0000-7000-8000-000000000101',
          role: 'ui.region',
          name: 'KPI Summary Region',
          bounds: {x: 20, y: 16, width: 240, height: 64},
          notes: '',
        },
      ],
      bindings: [
        {
          id: '019a0000-0000-7000-8000-000000000106',
          store_binding_id: '019a0000-0000-7000-8000-000000000199',
          source_id: '019a0000-0000-7000-8000-000000000103',
          column_id: 'order_id',
          target_kind: 'column',
          target_ref: 'sales.orders.id',
          access_mode: 'read',
          state: suspect ? 'suspect' : 'valid',
        },
      ],
      navigations: [
        {
          id: '019a0000-0000-7000-8000-000000000105',
          from_id: '019a0000-0000-7000-8000-000000000103',
          to_screen_id: '019a0000-0000-7000-8000-000000000102',
          trigger: 'click',
          action: 'overlay',
          delay_ms: 0,
          url: '',
          label: 'Open Detail',
        },
      ],
      notes: '',
    },
    assets: [],
    store_bindings: [],
    suspect_binding_count: suspect ? 1 : 0,
  };
}

describe('ScreenMeshDesignerSurface and ScreenMeshesNavigator', () => {
  const ThemedDesigner = withTheme(ScreenMeshDesignerSurface);
  const ThemedNavigator = withTheme(ScreenMeshesNavigator);

  beforeEach(() => {
    setupDDNDOM();
    setDDNLibraryLoaderForTests(async () => libraries);
  });

  afterEach(() => {
    resetDDNLibraryLoaderForTests();
  });

  it('renders wireframe.ui@1 views via DDNViewerSurface, confirms suspect bindings, redacts screenshots (F4), saves and accepts', async () => {
    let currentVersion = 1;
    let suspect = true;
    const mockClient = {
      openSession: jest.fn(async (_proj, _id, opts) =>
        makeMeshSession({version: opts?.version || currentVersion})
      ),
      getScreenMeshModel: jest.fn(async () =>
        makeMeshPayload({version: currentVersion, suspect})
      ),
      saveScreenMeshModel: jest.fn(async () => {
        currentVersion += 1;
        return makeMeshPayload({version: currentVersion, suspect});
      }),
      confirmBinding: jest.fn(async () => {
        suspect = false;
        return {ok: true};
      }),
      redactScreenMeshScreenshot: jest.fn(async () => {
        currentVersion += 1;
        return {
          ...makeMeshPayload({
            version: currentVersion,
            suspect,
            screenshotSha: 'b'.repeat(64),
          }),
          redaction: {purged_original: true},
        };
      }),
      queryScreenMeshUsage: jest.fn(async () => [
        {
          design_id: '019a0000-0000-7000-8000-000000000100',
          design_title: 'Orders Workbench',
          screen_name: 'Orders Screen',
          element_id: '019a0000-0000-7000-8000-000000000103',
          element_role: 'ui.grid',
          element_name: 'Orders Grid',
          target_kind: 'column',
          target_ref: 'sales.orders.id',
          state: 'valid',
        },
      ]),
      acceptVersion: jest.fn(async () => ({ok: true})),
      screenMeshBlobUrl: (p, d, sha) =>
        `/cdeadmin/api/projects/${p}/designs/${d}/blobs/${sha}`,
    };

    render(
      <ThemedDesigner
        projectId="ui-meshes"
        designId="019a0000-0000-7000-8000-000000000100"
        client={mockClient}
      />
    );

    await waitFor(() =>
      expect(screen.getByText(/Orders Workbench/)).toBeInTheDocument()
    );
    expect(
      screen.getByText(/Executable working forms are outside ScratchRobin scope/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/1 binding\(s\) are marked suspect/)
    ).toBeInTheDocument();

    // Confirm suspect binding (A5/A6)
    fireEvent.click(screen.getByRole('button', {name: 'Confirm Binding'}));
    await waitFor(() => expect(mockClient.confirmBinding).toHaveBeenCalled());

    // Add a ui.region hotspot (F1) and save checkpoint
    fireEvent.click(screen.getByRole('button', {name: 'Add Region…'}));
    const regDialog = await screen.findByRole('dialog');
    fireEvent.change(within(regDialog).getByLabelText('Region name'), {
      target: {value: 'Footer Totals Hotspot'},
    });
    fireEvent.click(
      within(regDialog).getByRole('button', {name: 'Add Region'})
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );
    expect(screen.getByText(/Footer Totals Hotspot/)).toBeInTheDocument();

    fireEvent.click(
      await screen.findByRole('button', {name: /Save Checkpoint/})
    );
    await waitFor(() =>
      expect(mockClient.saveScreenMeshModel).toHaveBeenCalled()
    );

    // Switch to derived screen_flow view (F2)
    const viewCombo = screen.getByLabelText('View');
    fireEvent.mouseDown(viewCombo);
    const flowOpt = await screen.findByRole('option', {
      name: /Screen-to-Screen Flow/,
    });
    fireEvent.click(flowOpt);

    // Destructively redact screenshot region (F4)
    fireEvent.click(
      await screen.findByRole('button', {name: 'Redact Screenshot…'})
    );
    const redactDialog = await screen.findByRole('dialog');
    expect(
      within(redactDialog).getByText(/purges the unredacted image bytes/)
    ).toBeInTheDocument();
    fireEvent.click(
      within(redactDialog).getByRole('button', {
        name: 'Redact & Purge Original',
      })
    );
    await waitFor(() =>
      expect(mockClient.redactScreenMeshScreenshot).toHaveBeenCalled()
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Query Where Used
    fireEvent.click(await screen.findByRole('button', {name: 'Where Used…'}));
    const usageDialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(
        within(usageDialog).getByText(/sales\.orders\.id/)
      ).toBeInTheDocument()
    );
    fireEvent.click(within(usageDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Accept version
    fireEvent.click(await screen.findByRole('button', {name: 'Accept…'}));
    const accDialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(accDialog).getByRole('button', {name: 'Accept Version'})
    );
    await waitFor(() => expect(mockClient.acceptVersion).toHaveBeenCalled());
  });

  it('imports ScratchRobin SR-F UI descriptor forms into Draft DDN (F3)', async () => {
    const onOpenDesign = jest.fn();
    const projectClient = {
      listProjects: jest.fn(async () => [
        {project_id: 'ui-meshes', name: 'UI Meshes', access: 'owner'},
      ]),
    };
    const designClient = {
      listDesigns: jest.fn(async () => []),
      listDescriptorForms: jest.fn(async () => [
        {
          engine: 'sqlite',
          form_key: 'table',
          family: 'table',
          form_reference: 'SR-F-020073',
          field_count: 14,
        },
      ]),
      importDescriptorMesh: jest.fn(async () => ({
        design: {
          id: '019a0000-0000-7000-8000-000000000201',
          kind: 'screen',
          title: 'SQLITE Table (SR-F-020073)',
          head_version: 1,
        },
        loss_report: {
          engine: 'sqlite',
          form_key: 'table',
          form_reference: 'SR-F-020073',
          preserved_controls: 18,
          preserved_bindings: 12,
          omitted_dynamic_rules: [{field_id: 'strict', attribute: 'visible_when'}],
        },
      })),
    };

    render(
      <ThemedNavigator
        designClient={designClient}
        projectClient={projectClient}
        onOpenDesign={onOpenDesign}
      />
    );

    await waitFor(() =>
      expect(screen.getByText(/No Screen Meshes yet/)).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole('button', {name: 'New Screen Mesh…'}));
    const dialog = await screen.findByRole('dialog');

    const sourceSelect = within(dialog).getByLabelText('Source');
    fireEvent.mouseDown(sourceSelect);
    const importOpt = await screen.findByRole('option', {
      name: /Import ScratchRobin SR-F UI Descriptor Form/,
    });
    fireEvent.click(importOpt);

    await waitFor(() =>
      expect(designClient.listDescriptorForms).toHaveBeenCalled()
    );

    fireEvent.click(
      within(dialog).getByRole('button', {name: 'Import SR-F Form'})
    );
    await waitFor(() =>
      expect(designClient.importDescriptorMesh).toHaveBeenCalledWith(
        'ui-meshes',
        expect.objectContaining({formReference: 'SR-F-020073'})
      )
    );
    expect(onOpenDesign).toHaveBeenCalledWith(
      'ui-meshes',
      expect.objectContaining({id: '019a0000-0000-7000-8000-000000000201'})
    );
  });

  it('registers Tools menu launchers only for bare-click entry commands', () => {
    const def = screenMeshModuleDefinition();
    const toolsIds = def.contributions.commands
      .filter((c) => c.surfaces.includes('tools'))
      .map((c) => c.id);
    expect(toolsIds).toEqual([
      'screen_mesh.designer.new',
      'screen_mesh.designer.show',
    ]);
    const toolbarOnlyIds = def.contributions.commands
      .filter((c) => !c.surfaces.includes('tools'))
      .map((c) => c.id);
    expect(toolbarOnlyIds).toEqual([
      'screen_mesh.designer.open',
      'screen_mesh.designer.save',
      'screen_mesh.designer.redact',
      'screen_mesh.designer.accept',
    ]);
  });
});
