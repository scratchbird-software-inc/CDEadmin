/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  act,
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
  lookHanddrawn = false,
  screenshotSha = 'a'.repeat(64),
  extraScreens = [],
  extraControls = [],
} = {}) {
  return {
    design: makeMeshSession({version}).design,
    mesh: {
      name: 'Orders Workbench',
      look_handdrawn: lookHanddrawn,
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
        ...extraScreens,
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
        ...extraControls,
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

function makeMockClient(overrides = {}) {
  let currentVersion = 1;
  let suspect = true;
  let lookHanddrawn = false;
  let extraScreens = [];
  let extraControls = [];

  return {
    openSession: jest.fn(async (_proj, _id, opts) =>
      makeMeshSession({version: opts?.version || currentVersion})
    ),
    getScreenMeshModel: jest.fn(async () =>
      makeMeshPayload({
        version: currentVersion,
        suspect,
        lookHanddrawn,
        extraScreens,
        extraControls,
      })
    ),
    saveScreenMeshModel: jest.fn(async (_proj, _id, payload) => {
      currentVersion += 1;
      lookHanddrawn = Boolean(payload?.mesh?.look_handdrawn);
      return makeMeshPayload({
        version: currentVersion,
        suspect,
        lookHanddrawn,
        extraScreens,
        extraControls,
      });
    }),
    confirmBinding: jest.fn(async () => {
      suspect = false;
      return {ok: true};
    }),
    uploadScreenMeshScreenshot: jest.fn(async () => {
      currentVersion += 1;
      return makeMeshPayload({
        version: currentVersion,
        suspect,
        lookHanddrawn,
        screenshotSha: 'c'.repeat(64),
      });
    }),
    redactScreenMeshScreenshot: jest.fn(async () => {
      currentVersion += 1;
      return {
        ...makeMeshPayload({
          version: currentVersion,
          suspect,
          lookHanddrawn,
          screenshotSha: 'b'.repeat(64),
        }),
        redaction: {purged_original: true},
      };
    }),
    traceScreenMeshScreenshot: jest.fn(async () => {
      currentVersion += 1;
      const tracedScreenId = '019a0000-0000-7000-8000-000000000190';
      extraScreens = [
        {
          id: tracedScreenId,
          name: 'Orders Screen (Traced Mesh)',
          width: 960,
          height: 640,
          form_reference: '',
          screenshot_path: '',
          screenshot_sha256: '',
          notes: '',
        },
      ];
      extraControls = [
        {
          id: '019a0000-0000-7000-8000-000000000191',
          screen_id: tracedScreenId,
          role: 'ui.input',
          name: 'KPI Summary Region',
          columns: [],
          options: [],
          placeholder: '',
          checked: false,
          bounds: {x: 20, y: 16, width: 240, height: 64},
          notes: '',
        },
      ];
      return {
        ...makeMeshPayload({
          version: currentVersion,
          suspect,
          lookHanddrawn,
          extraScreens,
          extraControls,
        }),
        traced_screen_id: tracedScreenId,
        controls_created: 1,
        bindings_preserved: 1,
      };
    }),
    compareScreenMeshScreenshots: jest.fn(async () => ({
      old_dimensions: {width: 960, height: 640},
      new_dimensions: {width: 960, height: 640},
      dimension_changed: false,
      changed_pixel_ratio: 0.142,
      diff_bounding_boxes: [{x: 24, y: 20, width: 180, height: 48}],
      affected_regions: [
        {
          region_id: '019a0000-0000-7000-8000-000000000104',
          name: 'KPI Summary Region',
          bounds: {x: 20, y: 16, width: 240, height: 64},
          overlap_ratio: 0.5625,
          out_of_bounds: false,
          recommendation: 'review_bounds',
        },
      ],
    })),
    getScreenMeshFieldSpec: jest.fn(async () => ({
      design_id: '019a0000-0000-7000-8000-000000000100',
      title: 'Orders Workbench',
      version: currentVersion,
      summary: {
        total_fields: 3,
        bound_fields: 2,
        suspect_fields: suspect ? 1 : 0,
        unbound_fields: 1,
      },
      rows: [
        {
          screen_title: 'Orders Screen',
          element_id: '019a0000-0000-7000-8000-000000000103:order_id',
          element_kind: 'ui.grid.column',
          label: 'Orders Grid.Order ID',
          access_mode: 'read_only',
          target_ref: 'sales.orders.id',
          catalog_type: 'INTEGER',
          nullable: false,
          default_value: null,
          binding_state: suspect ? 'suspect' : 'valid',
          notes: '',
        },
        {
          screen_title: 'Orders Screen',
          element_id: '019a0000-0000-7000-8000-000000000104',
          element_kind: 'ui.region',
          label: 'KPI Summary Region',
          access_mode: 'read_only',
          target_ref: 'sales.orders.total_amount',
          catalog_type: 'NUMERIC(12,2)',
          nullable: true,
          default_value: '0.00',
          binding_state: 'valid',
          notes: 'bounds=(20, 16, 240x64)',
        },
      ],
      markdown: '# Orders Workbench — Field Specification\n| Orders Screen | Orders Grid.Order ID |',
      csv: 'screen_title,label,target_ref\n"Orders Screen","Orders Grid.Order ID","sales.orders.id"',
      html: '<!doctype html><html><body><table><tr><td>Orders Grid.Order ID</td></tr></table></body></html>',
    })),
    listVersions: jest.fn(async () => [
      {version: 1, status: 'draft', note: 'Initial mesh'},
    ]),
    queryWhereUsed: jest.fn(async () => [
      {
        binding_id: '019a0000-0000-7000-8000-000000000199',
        design_kind: 'screen',
        design_title: 'Orders Workbench',
        element_label: 'Orders Grid.Order ID',
        target_ref: 'sales.orders.id',
        validity: 'valid',
      },
    ]),
    acceptVersion: jest.fn(async () => ({ok: true})),
    gitOperation: jest.fn(async () => ({ok: true})),
    exportDDN: jest.fn(async () => SAMPLE_MESH_DDN),
    computeLayout: jest.fn(async () => ({ok: true})),
    screenMeshBlobUrl: (p, d, sha) =>
      `/cdeadmin/api/projects/${p}/designs/${d}/blobs/${sha}`,
    ...overrides,
  };
}

describe('ScreenMeshDesignerSurface and ScreenMeshesNavigator', () => {
  const ThemedDesigner = withTheme(ScreenMeshDesignerSurface);
  const ThemedNavigator = withTheme(ScreenMeshesNavigator);

  const getInputIn = (scope, labelMatcher) => {
    const found = within(scope).getByLabelText(labelMatcher);
    return found.tagName === 'INPUT' ? found : found.querySelector('input');
  };

  beforeEach(() => {
    setupDDNDOM();
    setDDNLibraryLoaderForTests(async () => libraries);
  });

  afterEach(() => {
    resetDDNLibraryLoaderForTests();
  });

  it('renders 5-tab DesignerTabbedMenu with zero duplicate DDN view selector, confirms suspect bindings, checkpoints, where-used, git sync, and accepts', async () => {
    const mockClient = makeMockClient();

    const {container} = render(
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

    // Verify all 5 ribbon category tabs are rendered and NO duplicate DDNViewerSurface view selector exists
    const menuNav = screen.getByRole('navigation', {
      name: 'Screen Mesh designer menu',
    });
    for (const tabLabel of [
      'Mesh',
      'Screens & Controls',
      'Screenshots & Regions',
      'Views & Field Spec',
      'Validate & Export',
    ]) {
      expect(
        within(menuNav).getByRole('tab', {name: new RegExp(tabLabel)})
      ).toBeInTheDocument();
    }
    expect(screen.queryByLabelText('DDN view')).not.toBeInTheDocument();
    expect(container.querySelectorAll('textarea').length).toBe(0);

    // Confirm suspect binding
    fireEvent.click(screen.getByRole('button', {name: 'Confirm Binding'}));
    await waitFor(() => expect(mockClient.confirmBinding).toHaveBeenCalled());

    // Open Checkpoints & Diff drawer
    fireEvent.click(
      within(menuNav).getByRole('button', {name: 'Checkpoints & Diff…'})
    );
    const cpDialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(mockClient.listVersions).toHaveBeenCalled()
    );
    fireEvent.click(within(cpDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Open Where Used dialog
    fireEvent.click(
      within(menuNav).getByRole('button', {name: 'Where Used…'})
    );
    const whereDialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(
        within(whereDialog).getByText(/sales\.orders\.id/)
      ).toBeInTheDocument()
    );
    fireEvent.click(within(whereDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Run Git Sync
    fireEvent.click(within(menuNav).getByRole('button', {name: 'Git Sync…'}));
    const gitDialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(gitDialog).getByRole('button', {name: 'Run Git Action'})
    );
    await waitFor(() => expect(mockClient.gitOperation).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Accept version
    fireEvent.click(within(menuNav).getByRole('button', {name: 'Accept'}));
    const accDialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(accDialog).getByRole('button', {name: 'Accept Version'})
    );
    await waitFor(() => expect(mockClient.acceptVersion).toHaveBeenCalled());
  });

  it('toggles Sketch Look (look_handdrawn) and edits ui.grid columns via TypedRowsEditor without CSV/JSON textareas', async () => {
    const mockClient = makeMockClient();

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

    const menuNav = screen.getByRole('navigation', {
      name: 'Screen Mesh designer menu',
    });
    fireEvent.click(
      within(menuNav).getByRole('tab', {name: 'Screens & Controls'})
    );

    // Toggle Sketch Look on
    fireEvent.click(within(menuNav).getByRole('button', {name: 'Sketch Look'}));
    expect(
      within(menuNav).getByRole('button', {name: 'Sketch Look: On'})
    ).toBeInTheDocument();

    // Add a ui.grid control with TypedRowsEditor columns
    fireEvent.click(within(menuNav).getByRole('button', {name: '+ Grid'}));
    const ctrlDialog = await screen.findByRole('dialog');
    expect(ctrlDialog.querySelectorAll('textarea').length).toBe(0);

    fireEvent.change(within(ctrlDialog).getByLabelText('Control label'), {
      target: {value: 'Shipments Grid'},
    });

    fireEvent.click(
      within(ctrlDialog).getByRole('tab', {name: 'Grid Columns'})
    );
    fireEvent.change(getInputIn(ctrlDialog, 'Column ID row 1'), {
      target: {value: 'shipment_no'},
    });
    fireEvent.change(getInputIn(ctrlDialog, 'Header Label row 1'), {
      target: {value: 'Shipment #'},
    });
    fireEvent.change(getInputIn(ctrlDialog, 'Bound Column Ref row 1'), {
      target: {value: 'logistics.shipments.shipment_no'},
    });

    fireEvent.click(
      within(ctrlDialog).getByRole('button', {name: 'Add Control'})
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );
    expect(screen.getByText(/Shipments Grid/)).toBeInTheDocument();

    // Return to Mesh tab and save draft -> verifies look_handdrawn=true is persisted
    fireEvent.click(within(menuNav).getByRole('tab', {name: /^Mesh/}));
    fireEvent.click(
      within(menuNav).getByRole('button', {name: /Save Draft/})
    );
    await waitFor(() =>
      expect(mockClient.saveScreenMeshModel).toHaveBeenCalledWith(
        'ui-meshes',
        '019a0000-0000-7000-8000-000000000100',
        expect.objectContaining({
          mesh: expect.objectContaining({look_handdrawn: true}),
        })
      )
    );
  });

  it('supports drag-drop/sample screenshot upload, interactive rubber-band region & redaction drawing, Trace as Mesh, and Compare Newer Screenshot (SR-F-030021)', async () => {
    const mockClient = makeMockClient();

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

    const menuNav = screen.getByRole('navigation', {
      name: 'Screen Mesh designer menu',
    });
    fireEvent.click(
      within(menuNav).getByRole('tab', {name: 'Screenshots & Regions'})
    );

    // 1. Upload Screenshot via sample generator (zero Base64 paste textarea)
    fireEvent.click(
      within(menuNav).getByRole('button', {name: 'Upload Screenshot…'})
    );
    const uploadDialog = await screen.findByRole('dialog');
    expect(uploadDialog.querySelectorAll('textarea').length).toBe(0);
    expect(
      within(uploadDialog).getByLabelText('Choose screenshot image file')
    ).toHaveAttribute('type', 'file');

    fireEvent.click(
      within(uploadDialog).getByRole('button', {
        name: 'Use Sample Form Screenshot',
      })
    );
    fireEvent.click(
      within(uploadDialog).getByRole('button', {name: 'Upload Screenshot'})
    );
    await waitFor(() =>
      expect(mockClient.uploadScreenMeshScreenshot).toHaveBeenCalled()
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 2. Interactive rubber-band rectangle drawing for ui.region hotspots
    fireEvent.click(
      within(menuNav).getByRole('button', {name: 'Draw / Edit Regions…'})
    );
    const regionDialog = await screen.findByRole('dialog');
    const rubberSurface = within(regionDialog).getByTestId(
      'screenshot-rubberband-surface'
    );
    fireEvent.mouseDown(rubberSurface, {clientX: 40, clientY: 50});
    fireEvent.mouseMove(rubberSurface, {clientX: 240, clientY: 130});
    fireEvent.mouseUp(rubberSurface, {clientX: 240, clientY: 130});

    // Newly drawn Hotspot 2 row is synced into TypedRowsEditor with (40, 50, 200, 80)
    expect(getInputIn(regionDialog, 'X row 2')).toHaveValue(40);
    expect(getInputIn(regionDialog, 'Y row 2')).toHaveValue(50);
    expect(getInputIn(regionDialog, 'Width row 2')).toHaveValue(200);
    expect(getInputIn(regionDialog, 'Height row 2')).toHaveValue(80);

    fireEvent.change(getInputIn(regionDialog, 'Region Name row 2'), {
      target: {value: 'Drawn Totals Region'},
    });
    fireEvent.click(
      within(regionDialog).getByRole('button', {name: 'Apply Regions'})
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );
    expect(screen.getByText(/Drawn Totals Region/)).toBeInTheDocument();

    // 3. Destructive Redact Sensitive Regions via rubber-band + TypedRowsEditor
    fireEvent.click(
      within(menuNav).getByRole('button', {name: 'Redact Sensitive Regions…'})
    );
    const redactDialog = await screen.findByRole('dialog');
    const redactCanvas = within(redactDialog).getByTestId(
      'screenshot-rubberband-surface'
    );
    fireEvent.mouseDown(redactCanvas, {clientX: 12, clientY: 18});
    fireEvent.mouseMove(redactCanvas, {clientX: 112, clientY: 58});
    fireEvent.mouseUp(redactCanvas, {clientX: 112, clientY: 58});
    fireEvent.click(
      within(redactDialog).getByRole('button', {
        name: 'Redact & Purge Original',
      })
    );
    await waitFor(() =>
      expect(mockClient.redactScreenMeshScreenshot).toHaveBeenCalledWith(
        'ui-meshes',
        '019a0000-0000-7000-8000-000000000100',
        expect.objectContaining({
          regions: expect.arrayContaining([
            {x: 12, y: 18, width: 100, height: 40},
          ]),
        })
      )
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 4. Trace as Mesh
    fireEvent.click(
      within(menuNav).getByRole('button', {name: 'Trace as Mesh…'})
    );
    const traceDialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(traceDialog).getByRole('button', {name: 'Trace Regions to Mesh'})
    );
    await waitFor(() =>
      expect(mockClient.traceScreenMeshScreenshot).toHaveBeenCalled()
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );
    await waitFor(() =>
      expect(
        screen.getByText(/Orders Screen \(Traced Mesh\)/)
      ).toBeInTheDocument()
    );

    // 5. Compare Newer Screenshot
    fireEvent.click(
      within(menuNav).getByRole('button', {name: 'Compare Newer Screenshot…'})
    );
    const cmpDialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(cmpDialog).getByRole('button', {
        name: 'Use Sample Updated Screenshot',
      })
    );
    fireEvent.click(
      within(cmpDialog).getByRole('button', {name: 'Compare Screenshots'})
    );
    await waitFor(() =>
      expect(mockClient.compareScreenMeshScreenshots).toHaveBeenCalled()
    );
    expect(
      await within(cmpDialog).findByText(/Changed pixels: 14\.2%/)
    ).toBeInTheDocument();
    expect(within(cmpDialog).getByText('review_bounds')).toBeInTheDocument();
  });

  it('renders top-level Field Specification Table view mode (SR-F-030022) with filtering, export downloads and preview modal', async () => {
    const mockClient = makeMockClient();

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

    const menuNav = screen.getByRole('navigation', {
      name: 'Screen Mesh designer menu',
    });
    fireEvent.click(
      within(menuNav).getByRole('tab', {name: 'Views & Field Spec'})
    );

    // Switch to Screen Flow then Field Specification Table
    fireEvent.click(within(menuNav).getByRole('button', {name: 'Screen Flow'}));
    fireEvent.click(
      within(menuNav).getByRole('button', {name: 'Field Specification Table'})
    );

    await waitFor(() =>
      expect(mockClient.getScreenMeshFieldSpec).toHaveBeenCalled()
    );

    const specRegion = await screen.findByLabelText(
      'Screen Mesh Field Specification Table'
    );
    expect(
      within(specRegion).getByText('Orders Grid.Order ID')
    ).toBeInTheDocument();
    expect(within(specRegion).getByText('INTEGER')).toBeInTheDocument();
    expect(within(specRegion).getByText('NUMERIC(12,2)')).toBeInTheDocument();

    // Filter live table
    fireEvent.change(
      within(specRegion).getByLabelText('Filter field specification'),
      {target: {value: 'total_amount'}}
    );
    expect(
      within(specRegion).queryByText('Orders Grid.Order ID')
    ).not.toBeInTheDocument();
    expect(
      within(specRegion).getByText('KPI Summary Region')
    ).toBeInTheDocument();

    // 1-click Download buttons + Preview modal
    fireEvent.click(
      within(specRegion).getByRole('button', {name: 'Download Markdown'})
    );
    fireEvent.click(
      within(specRegion).getByRole('button', {name: 'Download CSV'})
    );
    fireEvent.click(
      within(specRegion).getByRole('button', {name: 'Download HTML'})
    );
    fireEvent.click(
      within(specRegion).getByRole('button', {name: 'Preview Spec…'})
    );
    const previewModal = await screen.findByRole('dialog');
    expect(
      within(previewModal).getByLabelText('Specification export format')
    ).toBeInTheDocument();
  });

  it('imports SR-F UI descriptor forms (SR-F-030023) without JSON textareas and handles cdeadmin:design-shortcut (screen_mesh_from_table)', async () => {
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
      createScreenMesh: jest.fn(async (_proj, payload) => ({
        id: '019a0000-0000-7000-8000-000000000299',
        kind: 'screen',
        title: payload.title,
        head_version: 1,
      })),
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

    // 1. SR-F UI descriptor import without raw JSON textarea
    fireEvent.click(screen.getByRole('button', {name: 'Import SR-F Form…'}));
    const dialog = await screen.findByRole('dialog');
    expect(dialog.querySelectorAll('textarea').length).toBe(0);

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

    // 2. Dispatch cdeadmin:design-shortcut (screen_mesh_from_table)
    act(() => {
      window.dispatchEvent(
        new CustomEvent('cdeadmin:design-shortcut', {
          detail: {
            design_shortcut: 'screen_mesh_from_table',
            schema: 'sales',
            table: 'work_orders',
            providerId: 'sqlite',
            endpointId: 'ep-local',
          },
        })
      );
    });

    const shortcutDialog = await screen.findByRole('dialog');
    expect(
      within(shortcutDialog).getByLabelText('Screen Mesh title')
    ).toHaveValue('work_orders Screen Mesh');
    expect(
      within(shortcutDialog).getByLabelText(
        'Seed from catalog table (optional)'
      )
    ).toHaveValue('sales.work_orders');

    fireEvent.click(
      within(shortcutDialog).getByRole('button', {name: 'Create Screen Mesh'})
    );
    await waitFor(() =>
      expect(designClient.createScreenMesh).toHaveBeenCalledWith(
        'ui-meshes',
        expect.objectContaining({
          title: 'work_orders Screen Mesh',
          mesh: expect.objectContaining({
            bindings: expect.arrayContaining([
              expect.objectContaining({
                target_kind: 'table',
                target_ref: 'sales.work_orders',
              }),
            ]),
          }),
        })
      )
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
