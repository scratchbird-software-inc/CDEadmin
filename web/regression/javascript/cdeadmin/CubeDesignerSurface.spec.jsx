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
  CubeDesignerSurface,
  CubesNavigator,
  cubeModuleDefinition,
  resetDDNLibraryLoaderForTests,
  setDDNLibraryLoaderForTests,
} from 'sources/cdeadmin_ui/integrations/ddn';

const SAMPLE_CUBE_DDN = [
  'version ddn-next-1',
  '// ScratchRobin mapping: scratchrobin.cube.dimensional',
  '// @cube.description: "Order fulfillment dimensional model"',
  '',
  'view "cube_star" as "cube.dimensional@1"',
  '    with',
  '        id "cube_star"',
  '        title "Sales Cube — Dimensional Star"',
  '        selection',
  '            include empty list',
  '',
  'view "cube_usage_matrix" as "matrix.relations@1"',
  '    with',
  '        id "cube_usage_matrix"',
  '        title "Sales Cube — Usage Matrix"',
  '        selection',
  '            include empty list',
  '',
  'view "cube_aggregation_grid" as "table.records@1"',
  '    with',
  '        id "cube_aggregation_grid"',
  '        title "Sales Cube — Aggregation Grid"',
  '        selection',
  '            include empty list',
  '',
].join('\n');

function makeCubeSession({status = 'draft', version = 1} = {}) {
  return {
    design: {
      id: '019a0000-0000-7000-8000-000000000020',
      project_id: 'analytics',
      key: 'sales-cube',
      kind: 'cube',
      title: 'Sales Cube',
      head_version: version,
      active_version: status === 'accepted' ? version : null,
      version: {
        version,
        status,
        ddn_text: SAMPLE_CUBE_DDN,
      },
      bindings: [],
    },
    workspace: {
      format: 'ddn-source-workspace@1',
      entry: 'sales-cube.ddn',
      view: 'cube_star',
      files: {'sales-cube.ddn': SAMPLE_CUBE_DDN},
    },
    layout: {
      algorithm: 'scratchrobin-server-layered@1',
      nodes: [{id: 'cube-1', name: 'Sales Cube', x: 48, y: 48}],
      edges: [],
      tiles: [{tx: 0, ty: 0, tile_key: 'tile-0'}],
    },
    resolved_includes: [],
    binding_summary: {total: 0, valid: 0, suspect: 0, unknown: 0},
  };
}

function sampleCubeModel() {
  return {
    contract_version: '1.0.0',
    name: 'Sales Cube',
    description: 'Order fulfillment dimensional model',
    semantic_family: 'relational',
    sources: [{id: 'orders', kind: 'table', relation: ['orders'], grain: []}],
    joins: [],
    relationships: [],
    dimensions: [],
    measures: [],
    measure_groups: [
      {
        id: 'orders_group',
        name: 'Orders',
        fact_source: 'orders',
        measures: [],
        dimension_usage: [],
      },
    ],
    parameters: [],
    default_filters: [],
    materializations: [],
    security: {row_filters: [], tenant_filter: null, roles: []},
    visualizations: [],
    dashboards: [],
    schedules: [],
    reports: [],
    annotations: {cube_version_label: '1.0', semantic_endpoint_id: 'ep-1'},
  };
}

function switchRibbonTab(tabLabel) {
  const nav = screen.getByRole('navigation', {name: 'Cube Designer'});
  fireEvent.click(within(nav).getByRole('tab', {name: tabLabel}));
}

function changeRowText(container, labelPattern, value) {
  const wrapper = within(container).getByLabelText(labelPattern);
  const input =
    wrapper.tagName === 'INPUT'
      ? wrapper
      : within(wrapper).getByRole('textbox');
  fireEvent.change(input, {target: {value}});
}

async function changeRowSelect(container, labelPattern, optionPattern) {
  const wrapper = within(container).getByLabelText(labelPattern);
  const combo =
    wrapper.getAttribute('role') === 'combobox'
      ? wrapper
      : within(wrapper).getByRole('combobox');
  fireEvent.mouseDown(combo);
  fireEvent.click(await screen.findByRole('option', {name: optionPattern}));
}

describe('Task-specific Cube Designer', () => {
  beforeEach(() => {
    setupDDNDOM();
    setDDNLibraryLoaderForTests(async () => libraries);
  });

  afterEach(() => {
    resetDDNLibraryLoaderForTests();
  });

  it('renders the 5-tab DesignerTabbedMenu without duplicate DDN view selector, switches DDN views, edits dimensions, syncs active drift, previews DDL in CodeEditor and accepts/leaves accepted', async () => {
    let curStatus = 'draft';
    let curVer = 1;
    let curModel = sampleCubeModel();

    const mockClient = {
      openSession: jest.fn(async () =>
        makeCubeSession({status: curStatus, version: curVer})
      ),
      getCubeModel: jest.fn(async () => ({
        cube: {model: curModel, element_ids: {}, notes: ['Initial note']},
      })),
      saveCubeModel: jest.fn(async (_proj, _id, payload) => {
        curVer += 1;
        if (payload.model) curModel = payload.model;
        return {
          design: makeCubeSession({
            status: payload.status || 'draft',
            version: curVer,
          }).design,
          cube: {
            model: curModel,
            element_ids: {},
            notes: payload.cubeNotes || [],
          },
          active_drift: {
            has_active_changes: true,
            active_changes: [{section: 'parameters', item_id: 'currency'}],
          },
        };
      }),
      syncCubeActive: jest.fn(async () => {
        curVer += 1;
        return {
          merged: true,
          design: makeCubeSession({status: 'draft', version: curVer}).design,
          cube: {model: curModel, element_ids: {}, notes: []},
        };
      }),
      previewCubeMaterializationPlan: jest.fn(async () => ({
        has_database_changes: true,
        requires_native_review: true,
        applied_immediately: false,
        destructive_warning:
          'Materialized aggregate changes alter physical database objects.',
        sql_preview:
          'CREATE MATERIALIZED VIEW "agg_orders" AS SELECT COUNT(1) FROM "orders";',
      })),
      acceptVersion: jest.fn(async () => {
        curStatus = 'accepted';
        return {
          ...makeCubeSession({status: 'accepted', version: curVer}).design,
          applied_semantic_model: {model_id: 'sm-sales', revision: 1},
          materialization_review_plan: {has_database_changes: false},
        };
      }),
      leaveCubeAccepted: jest.fn(async () => {
        curStatus = 'draft';
        curVer += 1;
        curModel = {
          ...curModel,
          annotations: {...curModel.annotations, cube_version_label: '1.1'},
        };
        return {
          design: makeCubeSession({status: 'draft', version: curVer}).design,
          cube: {model: curModel, element_ids: {}, notes: []},
        };
      }),
    };

    const Themed = withTheme(CubeDesignerSurface);
    render(
      <Themed
        projectId="analytics"
        designId="019a0000-0000-7000-8000-000000000020"
        client={mockClient}
      />
    );

    await waitFor(() =>
      expect(
        screen.getByRole('region', {name: 'Cube Designer'})
      ).toBeInTheDocument()
    );

    // Verify all 5 ribbon tabs exist and DDNViewerSurface's inner view selector is hidden.
    const nav = screen.getByRole('navigation', {name: 'Cube Designer'});
    expect(within(nav).getByRole('tab', {name: 'Cube'})).toBeInTheDocument();
    expect(
      within(nav).getByRole('tab', {name: 'Dimensions & Measures'})
    ).toBeInTheDocument();
    expect(
      within(nav).getByRole('tab', {name: 'Views & Try Query'})
    ).toBeInTheDocument();
    expect(
      within(nav).getByRole('tab', {name: 'Aggregations & Check'})
    ).toBeInTheDocument();
    expect(
      within(nav).getByRole('tab', {name: 'Governance & Export'})
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('DDN view')).not.toBeInTheDocument();

    // Switch between Dimensional Star, Usage Matrix, and Aggregation Grid on Views & Try Query tab.
    switchRibbonTab('Views & Try Query');
    const viewSelect = screen.getByLabelText('Cube DDN view');
    fireEvent.mouseDown(viewSelect);
    fireEvent.click(
      await screen.findByRole('option', {
        name: /Dimension Usage Matrix/i,
      })
    );
    expect(viewSelect).toHaveTextContent(/Dimension Usage Matrix/i);
    fireEvent.mouseDown(viewSelect);
    fireEvent.click(
      await screen.findByRole('option', {
        name: /Aggregation Grid/i,
      })
    );
    expect(viewSelect).toHaveTextContent(/Aggregation Grid/i);

    // Add a C3 role-playing dimension with unknown_member_policy, fixed/changing attributes & visible_roles.
    switchRibbonTab('Dimensions & Measures');
    fireEvent.click(
      screen.getByRole('button', {name: /\+ Dimension \/ Hierarchies…/i})
    );
    const dimDialog = await screen.findByRole('dialog');
    fireEvent.change(within(dimDialog).getByLabelText(/Dimension name/i), {
      target: {value: 'Ship Date'},
    });
    fireEvent.change(within(dimDialog).getByLabelText(/^Key column/i), {
      target: {value: 'ship_date'},
    });
    const unkSelect = within(dimDialog).getByLabelText(
      /^Unknown member policy$/i
    );
    fireEvent.mouseDown(unkSelect);
    fireEvent.click(
      await screen.findByRole('option', {
        name: /Hide orphan rows \(INNER JOIN\)/i,
      })
    );
    fireEvent.change(
      within(dimDialog).getByLabelText(/Role-playing base dimension ID/i),
      {target: {value: 'order_date'}}
    );

    // Attributes & Fixed/Changing Relationships tab
    fireEvent.click(
      within(dimDialog).getByRole('tab', {
        name: /Attributes & Fixed\/Changing Relationships/i,
      })
    );
    fireEvent.click(
      within(dimDialog).getByRole('button', {name: /\+ Add attribute/i})
    );
    changeRowText(dimDialog, /Attribute Name row 1/i, 'Fiscal Year');
    changeRowText(dimDialog, /Source Column row 1/i, 'fiscal_year');
    await changeRowSelect(
      dimDialog,
      /Relationship Type row 1/i,
      /Fixed \(Immutable relationship\)/i
    );

    // Role Visibility tab
    fireEvent.click(
      within(dimDialog).getByRole('tab', {name: /Role Visibility/i})
    );
    fireEvent.click(
      within(dimDialog).getByRole('button', {name: /\+ Add role/i})
    );
    changeRowText(
      dimDialog,
      /Portable Role Identifier row 1/i,
      'logistics_analyst'
    );

    fireEvent.click(
      within(dimDialog).getByRole('button', {name: 'Save dimension'})
    );
    await waitFor(() =>
      expect(mockClient.saveCubeModel).toHaveBeenCalledTimes(1)
    );
    expect(curModel.dimensions[0]).toMatchObject({
      id: 'ship_date',
      role_of: 'order_date',
      unknown_member_policy: 'hide',
      visible_roles: ['logistics_analyst'],
      attributes: [
        expect.objectContaining({
          name: 'Fiscal Year',
          relationship_type: 'fixed',
        }),
      ],
    });

    // Active drift alert is surfaced and can be merged cleanly.
    const syncBtn = await screen.findByRole('button', {
      name: 'Sync active changes',
    });
    fireEvent.click(syncBtn);
    await waitFor(() =>
      expect(mockClient.syncCubeActive).toHaveBeenCalledTimes(1)
    );

    // Preview materialized aggregate native-operation review SQL in CodeEditor (never TextArea).
    switchRibbonTab('Aggregations & Check');
    fireEvent.click(
      screen.getByRole('button', {name: 'Materialization DDL Plan…'})
    );
    const matDialog = await screen.findByRole('dialog');
    const sqlRegion = await within(matDialog).findByRole('region', {
      name: 'Native Review SQL Preview',
    });
    expect(sqlRegion).toBeInTheDocument();
    expect(mockClient.previewCubeMaterializationPlan).toHaveBeenCalledTimes(1);
    fireEvent.click(within(matDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Accept & apply to semantic-model store from Tab 1 Cube.
    switchRibbonTab('Cube');
    fireEvent.click(screen.getByRole('button', {name: 'Accept Cube'}));
    const acceptDialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(acceptDialog).getByRole('button', {name: 'Accept & apply'})
    );
    await waitFor(() =>
      expect(mockClient.acceptVersion).toHaveBeenCalledTimes(1)
    );
    expect(
      await screen.findByText(/Accepted version applied to semantic-model store/)
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Leave accepted -> branch minor-bump draft (1.0 -> 1.1).
    fireEvent.click(
      await screen.findByRole('button', {name: 'Leave Accepted…'})
    );
    const leaveDialog = await screen.findByRole('dialog', {
      name: /Leave accepted cube version/i,
    });
    fireEvent.click(within(leaveDialog).getByRole('button', {name: 'Confirm'}));
    await waitFor(() =>
      expect(mockClient.leaveCubeAccepted).toHaveBeenCalledTimes(1)
    );
  });

  it('lists cube designs, creates a cube manually, and seeds a fact-table cube on cdeadmin:design-shortcut (cube_from_table)', async () => {
    const onOpenCube = jest.fn();
    const projectClient = {
      listProjects: jest.fn(async () => [
        {project_id: 'analytics', name: 'Analytics', access: 'owner'},
      ]),
    };
    const designClient = {
      listDesigns: jest.fn(async () => [
        {
          id: '019a0000-0000-7000-8000-000000000021',
          title: 'Revenue Cube',
          head_version: 3,
        },
      ]),
      createCubeDesign: jest.fn(async (_proj, payload) => ({
        id: '019a0000-0000-7000-8000-000000000022',
        title: payload.title,
        head_version: 1,
      })),
    };

    const ThemedNav = withTheme(CubesNavigator);
    render(
      <ThemedNav
        projectClient={projectClient}
        designClient={designClient}
        onOpenCube={onOpenCube}
      />
    );

    expect(await screen.findByText('Revenue Cube')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'New cube…'}));
    const dlg = await screen.findByRole('dialog');
    fireEvent.change(within(dlg).getByLabelText(/Cube title/i), {
      target: {value: 'Margin Cube'},
    });
    fireEvent.click(within(dlg).getByRole('button', {name: 'Create cube'}));
    await waitFor(() =>
      expect(onOpenCube).toHaveBeenCalledWith(
        'analytics',
        expect.objectContaining({title: 'Margin Cube'})
      )
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Dispatch context-menu design_shortcut === 'cube_from_table'
    act(() => {
      window.dispatchEvent(
        new CustomEvent('cdeadmin:design-shortcut', {
          detail: {
            design_shortcut: 'cube_from_table',
            schema: 'sales',
            table: 'order_lines',
            endpoint_id: 'ep-warehouse',
          },
        })
      );
    });

    const shortcutDlg = await screen.findByRole('dialog');
    expect(within(shortcutDlg).getByLabelText(/Cube title/i)).toHaveValue(
      'Order Lines Cube'
    );
    expect(within(shortcutDlg).getByLabelText(/Fact table/i)).toHaveValue(
      'sales.order_lines'
    );
    fireEvent.click(
      within(shortcutDlg).getByRole('button', {name: 'Create cube'})
    );
    await waitFor(() =>
      expect(designClient.createCubeDesign).toHaveBeenLastCalledWith(
        'analytics',
        expect.objectContaining({
          title: 'Order Lines Cube',
          endpointId: 'ep-warehouse',
          model: expect.objectContaining({
            sources: [
              expect.objectContaining({
                relation: ['sales', 'order_lines'],
                classification: 'fact',
              }),
            ],
          }),
        })
      )
    );
  });

  it('registers Cube module launcher commands on Tools and keeps open-cube actions on toolbar', () => {
    const def = cubeModuleDefinition();
    const byId = Object.fromEntries(
      def.contributions.commands.map((c) => [c.id, c])
    );
    expect(byId['cube.designer.new'].surfaces).toContain('tools');
    expect(byId['cube.designer.show'].surfaces).toContain('tools');
    expect(byId['cube.designer.open'].surfaces).toEqual(['toolbar']);
    expect(byId['cube.designer.save'].surfaces).toEqual(['toolbar']);
    expect(byId['cube.designer.materialization_plan'].surfaces).toEqual([
      'toolbar',
    ]);
    expect(byId['cube.designer.accept'].surfaces).toEqual(['toolbar']);
  });

  it('edits parent-child hierarchies, semi-additive measures, interactive usage matrix, perspectives, translations, locale preview and SML / Ossie export', async () => {
    let curVer = 1;
    let curModel = sampleCubeModel();

    const mockClient = {
      openSession: jest.fn(async () =>
        makeCubeSession({status: 'draft', version: curVer})
      ),
      getCubeModel: jest.fn(async (_proj, _id, opts) => ({
        cube: {model: curModel, element_ids: {}, notes: []},
        ...(opts?.locale
          ? {localized_model: {...curModel, name: 'Cube des ventes'}}
          : {}),
      })),
      saveCubeModel: jest.fn(async (_proj, _id, payload) => {
        curVer += 1;
        if (payload.model) curModel = payload.model;
        return {
          design: makeCubeSession({status: 'draft', version: curVer}).design,
          cube: {model: curModel, element_ids: {}, notes: []},
          active_drift: {has_active_changes: false, active_changes: []},
        };
      }),
      previewCubeMaterializationPlan: jest.fn(async () => ({
        has_database_changes: true,
        requires_native_review: true,
        applied_immediately: false,
        destructive_warning: 'Materialization changes require native review.',
        grain_warnings: [
          'Materialization agg_bad omits semi-additive time dimension snap_date.',
        ],
        sql_preview: '-- review SQL',
      })),
      exportCubeInterchange: jest.fn(async (_proj, _id, opts) => {
        if (opts?.format === 'ossie') {
          return {
            format: 'apache-ossie@0.2.0',
            yaml: 'version: 0.2.0\nsemantic_models:\n  - name: sales_cube\n',
            loss_report: {
              format: 'apache-ossie@0.2.0',
              fidelity: 'lossy',
              loss_count: 2,
              items: [
                {
                  category: 'parent_child_hierarchy',
                  item_name: 'Reporting Line',
                  reason:
                    'Parent-child closure unsupported in Apache Ossie 0.2.0.',
                },
                {
                  category: 'semi_additive_measure',
                  item_name: 'Closing Balance',
                  reason: 'Semi-additive time semantics degraded.',
                },
              ],
            },
          };
        }
        return {
          format: 'sml@1.8',
          manifest_yaml: 'sml_version: "1.8"\nmodel: sales_cube\n',
          files: {'models/sales_cube.yml': 'unique_name: sales_cube\n'},
          loss_report: {
            format: 'sml@1.8',
            fidelity: 'exact',
            loss_count: 0,
            items: [],
          },
        };
      }),
    };

    const Themed = withTheme(CubeDesignerSurface);
    render(
      <Themed
        projectId="analytics"
        designId="019a0000-0000-7000-8000-000000000020"
        client={mockClient}
      />
    );

    await waitFor(() =>
      expect(
        screen.getByRole('region', {name: 'Cube Designer'})
      ).toBeInTheDocument()
    );

    // 1. Parent-child ragged hierarchy dimension
    switchRibbonTab('Dimensions & Measures');
    fireEvent.click(
      screen.getByRole('button', {name: /\+ Dimension \/ Hierarchies…/i})
    );
    const dimDialog = await screen.findByRole('dialog');
    fireEvent.change(within(dimDialog).getByLabelText(/Dimension name/i), {
      target: {value: 'Org Rep'},
    });
    fireEvent.change(within(dimDialog).getByLabelText(/^Key column/i), {
      target: {value: 'rep_id'},
    });
    fireEvent.click(
      within(dimDialog).getByRole('tab', {
        name: /Hierarchies & Parent-Child/i,
      })
    );
    const hierSelect = within(dimDialog).getByLabelText(/Hierarchy kind/i);
    fireEvent.mouseDown(hierSelect);
    fireEvent.click(
      await screen.findByRole('option', {
        name: /Parent-child recursive hierarchy/i,
      })
    );
    fireEvent.change(within(dimDialog).getByLabelText(/Parent key column/i), {
      target: {value: 'manager_id'},
    });
    fireEvent.click(
      within(dimDialog).getByLabelText(/Allow ragged \/ unbalanced/i)
    );
    fireEvent.click(
      within(dimDialog).getByRole('button', {name: 'Save dimension'})
    );
    await waitFor(() =>
      expect(curModel.dimensions[0]?.hierarchies[0]).toMatchObject({
        hierarchy_kind: 'parent_child',
        parent_field: {source_id: 'orders', field: 'manager_id'},
        ragged: true,
      })
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 2. Semi-additive measure (LAST NON-EMPTY) across tabbed measure modal
    fireEvent.click(
      screen.getByRole('button', {name: /\+ Measure \/ Edit Measures…/i})
    );
    const measDialog = await screen.findByRole('dialog');
    fireEvent.change(within(measDialog).getByLabelText(/Measure name/i), {
      target: {value: 'Closing Balance'},
    });
    const aggSelect = within(measDialog).getByLabelText(/^Aggregation$/i);
    fireEvent.mouseDown(aggSelect);
    fireEvent.click(
      await screen.findByRole('option', {
        name: /LAST NON-EMPTY \(semi-additive\)/i,
      })
    );
    fireEvent.change(within(measDialog).getByLabelText(/Measure column/i), {
      target: {value: 'balance_amt'},
    });
    fireEvent.click(
      within(measDialog).getByRole('tab', {name: /Semi-Additive & Filter/i})
    );
    fireEvent.change(
      within(measDialog).getByLabelText(/Semi-additive time dimension ID/i),
      {target: {value: 'org_rep'}}
    );
    fireEvent.click(
      within(measDialog).getByRole('button', {name: 'Save measure'})
    );
    await waitFor(() =>
      expect(curModel.measures[0]).toMatchObject({
        id: 'closing_balance',
        aggregation: 'last_non_empty',
        semi_additive_dimension: 'org_rep',
        certification: {status: 'uncertified'},
      })
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 3. Interactive Dimension Usage Matrix cell cycling (unbound -> active -> role-playing)
    fireEvent.click(
      screen.getByRole('button', {name: /Interactive Usage Matrix…/i})
    );
    const matrixDialog = await screen.findByRole('dialog');
    const getCellBtn = () =>
      within(matrixDialog).getByRole('button', {
        name: 'Usage Orders × Org Rep',
      });
    expect(getCellBtn()).toHaveTextContent('—');
    fireEvent.click(getCellBtn());
    expect(getCellBtn()).toHaveTextContent('rep_id (active)');
    fireEvent.click(getCellBtn());
    expect(getCellBtn()).toHaveTextContent('rep_id (role-playing)');
    fireEvent.click(
      within(matrixDialog).getByRole('button', {name: 'Save usage matrix'})
    );
    await waitFor(() =>
      expect(curModel.measure_groups[0].dimension_usage).toEqual([
        {
          dimension_id: 'org_rep',
          relationship_kind: 'regular',
          active: false,
        },
      ])
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 4. Perspectives & Locale Translations on Governance & Export tab
    switchRibbonTab('Governance & Export');
    fireEvent.click(
      screen.getByRole('button', {name: /Perspectives & Role Visibility…/i})
    );
    const perspDialog = await screen.findByRole('dialog');
    fireEvent.change(within(perspDialog).getByLabelText(/Perspective name/i), {
      target: {value: 'Executive Sales'},
    });
    fireEvent.click(
      within(perspDialog).getByRole('tab', {name: /Role Visibility/i})
    );
    fireEvent.click(
      within(perspDialog).getByRole('button', {name: /\+ Add role/i})
    );
    changeRowText(
      perspDialog,
      /Portable Role Identifier row 1/i,
      'exec_board'
    );
    fireEvent.click(
      within(perspDialog).getByRole('button', {name: 'Save perspective'})
    );
    await waitFor(() =>
      expect(curModel.perspectives[0]).toMatchObject({
        id: 'executive_sales',
        name: 'Executive Sales',
        visible_roles: ['exec_board'],
      })
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    fireEvent.click(
      screen.getByRole('button', {name: /Locale Translations…/i})
    );
    const transDialog = await screen.findByRole('dialog');
    fireEvent.change(
      within(transDialog).getByLabelText(/Localized cube caption/i),
      {target: {value: 'Cube des ventes'}}
    );
    fireEvent.click(
      within(transDialog).getByRole('button', {
        name: /\+ Add translated entry/i,
      })
    );
    changeRowText(transDialog, /Target ID row 1/i, 'closing_balance');
    changeRowText(transDialog, /Translated Caption row 1/i, 'Solde de cloture');
    fireEvent.click(
      within(transDialog).getByRole('button', {name: 'Save translation'})
    );
    await waitFor(() =>
      expect(curModel.translations[0]).toMatchObject({
        locale: 'fr-CA',
        caption: 'Cube des ventes',
        entries: [
          {
            target_kind: 'measure',
            target_id: 'closing_balance',
            caption: 'Solde de cloture',
          },
        ],
      })
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Switch Preview Locale in Governance & Export ribbon
    const previewLocSelect = screen.getByLabelText('Preview Locale');
    fireEvent.mouseDown(previewLocSelect);
    fireEvent.click(await screen.findByRole('option', {name: /fr-CA/i}));
    expect(
      await screen.findByText(/Locale: fr-CA — Cube des ventes/i)
    ).toBeInTheDocument();

    // 5. Semi-additive grain warning in materialization plan
    switchRibbonTab('Aggregations & Check');
    fireEvent.click(
      screen.getByRole('button', {name: 'Materialization DDL Plan…'})
    );
    const matDialog = await screen.findByRole('dialog');
    expect(
      await within(matDialog).findByText(/Semi-additive grain warning:/i)
    ).toBeInTheDocument();
    fireEvent.click(within(matDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 6. External SML v1.8 (primary) and Apache Ossie v0.2.0 (lossy) export with explicit loss badges & CodeEditor
    switchRibbonTab('Governance & Export');
    fireEvent.click(screen.getByRole('button', {name: 'Export SML / Ossie…'}));
    const expDialog = await screen.findByRole('dialog');
    expect(
      await within(expDialog).findByText(/Export format: sml@1\.8/i)
    ).toBeInTheDocument();
    expect(
      within(expDialog).getByRole('region', {
        name: 'Generated Interchange YAML',
      })
    ).toBeInTheDocument();

    const fmtSelect = within(expDialog).getByLabelText(/Interchange format/i);
    fireEvent.mouseDown(fmtSelect);
    fireEvent.click(
      await screen.findByRole('option', {
        name: /Apache Ossie v0\.2\.0/i,
      })
    );
    expect(
      await within(expDialog).findByText(/Export format: apache-ossie@0\.2\.0/i)
    ).toBeInTheDocument();
    expect(
      within(expDialog).getByText(/parent_child_hierarchy: Reporting Line/i)
    ).toBeInTheDocument();
    expect(
      within(expDialog).getByRole('region', {name: 'Explicit Loss Report'})
    ).toBeInTheDocument();
    fireEvent.click(within(expDialog).getByRole('button', {name: 'Close'}));
  });

  it('exercises Combinatorial Rule Reducer (16 → 8 → 5), Check Against Connection, Try a Query, BYOK AI Draft Proposal, Checkpoints & Where Used', async () => {
    const seededModel = {
      ...sampleCubeModel(),
      dimensions: [
        {
          id: 'region',
          name: 'Region',
          field: {source_id: 'orders', field: 'region'},
          key_field: {source_id: 'orders', field: 'region'},
          hierarchies: [],
          active: true,
        },
        {
          id: 'cal_year',
          name: 'Year',
          field: {source_id: 'orders', field: 'cal_year'},
          key_field: {source_id: 'orders', field: 'cal_year'},
          hierarchies: [],
          active: true,
        },
        {
          id: 'cal_quarter',
          name: 'Quarter',
          field: {source_id: 'orders', field: 'cal_quarter'},
          key_field: {source_id: 'orders', field: 'cal_quarter'},
          hierarchies: [],
          active: true,
        },
        {
          id: 'cal_month',
          name: 'Month',
          field: {source_id: 'orders', field: 'cal_month'},
          key_field: {source_id: 'orders', field: 'cal_month'},
          hierarchies: [],
          active: true,
        },
      ],
      measures: [
        {
          id: 'revenue',
          name: 'Revenue',
          aggregation: 'sum',
          field: {source_id: 'orders', field: 'amount'},
          format: '#,##0.00',
        },
      ],
    };

    const mockClient = {
      openSession: jest.fn(async () =>
        makeCubeSession({status: 'draft', version: 2})
      ),
      getCubeModel: jest.fn(async () => ({
        cube: {model: seededModel, element_ids: {}, notes: []},
      })),
      reduceCubeAggregations: jest.fn(async () => ({
        naive_cuboid_count: 16,
        after_mandatory_and_joint_count: 8,
        final_cuboid_count: 4,
        reduction_summary: '16 -> 8 -> 4',
        generated_plans: [
          {
            id: 'cuboid_region_cal_year',
            grain_dimensions: ['region', 'cal_year'],
            refresh_policy: 'incremental',
            partition_grain: 'month',
          },
        ],
        design: makeCubeSession({status: 'draft', version: 3}).design,
        cube: {model: seededModel, element_ids: {}, notes: []},
      })),
      checkCubeConnection: jest.fn(async () => ({
        overall_status: 'valid',
        dimensions: [
          {
            dimension_id: 'region',
            dimension_name: 'Region',
            key_field: 'region',
            status: 'valid',
            duplicate_keys: 0,
            orphan_fact_rows: 0,
            probe_sql:
              'SELECT COUNT(*) AS total_rows, COUNT(DISTINCT "region") AS distinct_keys FROM "orders";',
            message: 'Unique key verified with 0 fan-out.',
          },
        ],
      })),
      tryCubeQuery: jest.fn(async () => ({
        dialect: 'sqlite',
        compiled_sql:
          'SELECT COALESCE(orders."region", \'Unknown\') AS "region", SUM(orders."amount") AS "revenue" FROM "orders" GROUP BY 1;',
        aggregate_routing_hit: {
          matched: true,
          id: 'cuboid_region',
          name: 'Cuboid: region',
        },
        columns: [
          {id: 'region', label: 'Region'},
          {id: 'revenue', label: 'Revenue'},
        ],
        preview_rows: [{region: 'NA', revenue: 12500}],
      })),
      proposeCubeAiDraft: jest.fn(async () => ({
        status: 'draft',
        requires_human_review: true,
        matched_existing_cubes: [{title: 'Sales Cube', head_version: 2}],
        diff_summary: {
          measures_added: 2,
          dimensions_added: 2,
          aggregations_added: 1,
        },
        proposed_ddn_text: 'version ddn-next-1\n// draft proposal\n',
        proposed_model: seededModel,
      })),
      listVersions: jest.fn(async () => [
        {version: 1, status: 'draft', note: 'Seeded cube'},
        {version: 2, status: 'in_review', parent_version: 1, note: 'Added dims'},
      ]),
      queryWhereUsed: jest.fn(async () => [
        {
          binding_id: 'b-1',
          design_kind: 'bi_dashboard',
          design_title: 'Executive Revenue Dashboard',
          element_label: 'Revenue KPI Card',
          target_ref: 'cube:sales-cube',
          validity: 'valid',
        },
      ]),
    };

    const Themed = withTheme(CubeDesignerSurface);
    render(
      <Themed
        projectId="analytics"
        designId="019a0000-0000-7000-8000-000000000020"
        client={mockClient}
      />
    );

    await waitFor(() =>
      expect(
        screen.getByRole('region', {name: 'Cube Designer'})
      ).toBeInTheDocument()
    );

    // 1. Combinatorial Rule Reducer (live 16 → 8 → 4 with hierarchy chain)
    switchRibbonTab('Aggregations & Check');
    fireEvent.click(
      screen.getByRole('button', {name: /Combinatorial Rule Reducer…/i})
    );
    const redDialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(redDialog).getByRole('button', {name: /\+ Add hierarchy chain/i})
    );
    changeRowText(
      redDialog,
      /Ordered Level \/ Dimension IDs \(comma-separated\) row 1/i,
      'cal_year, cal_quarter, cal_month'
    );
    fireEvent.change(
      within(redDialog).getByLabelText(/Max dimension combinations/i),
      {target: {value: '4'}}
    );
    expect(
      within(redDialog).getByText(/Cuboid Reduction: 16 → 8 → 4/)
    ).toBeInTheDocument();
    fireEvent.click(
      within(redDialog).getByRole('button', {
        name: /Apply reduced plans & save draft/i,
      })
    );
    await waitFor(() =>
      expect(mockClient.reduceCubeAggregations).toHaveBeenCalledWith(
        'analytics',
        '019a0000-0000-7000-8000-000000000020',
        expect.objectContaining({
          mandatory_dimensions: ['region'],
          hierarchy_sets: [['cal_year', 'cal_quarter', 'cal_month']],
          save_version: true,
        })
      )
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 2. Check Against Connection
    fireEvent.click(
      screen.getByRole('button', {name: /Check Against Connection…/i})
    );
    const connDialog = await screen.findByRole('dialog');
    expect(
      await within(connDialog).findByText(/Unique key verified with 0 fan-out/i)
    ).toBeInTheDocument();
    expect(
      within(connDialog).getByRole('region', {
        name: 'Generated Connection Probe SQL',
      })
    ).toBeInTheDocument();
    fireEvent.click(within(connDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 3. Try a Query with compiled SQL & aggregate routing hit
    switchRibbonTab('Views & Try Query');
    fireEvent.click(screen.getByRole('button', {name: 'Try a Query…'}));
    const tryDialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(tryDialog).getByRole('button', {name: 'Compile & run query'})
    );
    expect(
      await within(tryDialog).findByText(/Aggregate Hit: Cuboid: region/i)
    ).toBeInTheDocument();
    expect(
      within(tryDialog).getByRole('region', {
        name: 'Compiled Slice-and-Dice SQL',
      })
    ).toBeInTheDocument();
    expect(within(tryDialog).getByText('12500')).toBeInTheDocument();
    fireEvent.click(within(tryDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 4. BYOK AI Draft Proposal (searches existing cubes first, requires human review)
    switchRibbonTab('Dimensions & Measures');
    fireEvent.click(screen.getByRole('button', {name: 'AI Draft Proposal…'}));
    const aiDialog = await screen.findByRole('dialog');
    fireEvent.change(
      within(aiDialog).getByLabelText(/Business question \/ modelling goal/i),
      {target: {value: 'Track order revenue by region'}}
    );
    fireEvent.click(
      within(aiDialog).getByRole('button', {name: 'Generate draft proposal'})
    );
    expect(
      await within(aiDialog).findByText(/Human review required:/i)
    ).toBeInTheDocument();
    expect(
      within(aiDialog).getByText(/Matched existing project cube\(s\): Sales Cube/i)
    ).toBeInTheDocument();
    expect(
      within(aiDialog).getByRole('region', {name: 'Proposed Cube DDN Draft'})
    ).toBeInTheDocument();
    fireEvent.click(within(aiDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 5. Checkpoints & Diff drawer + Where Used dialog on Cube tab
    switchRibbonTab('Cube');
    fireEvent.click(screen.getByRole('button', {name: 'Checkpoints & Diff…'}));
    const cpDialog = await screen.findByRole('dialog');
    expect(
      await within(cpDialog).findByText('Added dims')
    ).toBeInTheDocument();
    fireEvent.click(within(cpDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    fireEvent.click(
      screen.getByRole('button', {name: /Used By \(Where Used\)…/i})
    );
    const wuDialog = await screen.findByRole('dialog');
    expect(
      await within(wuDialog).findByText('Executive Revenue Dashboard')
    ).toBeInTheDocument();
    fireEvent.click(within(wuDialog).getByRole('button', {name: 'Close'}));
  });
});
