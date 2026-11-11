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
  CubeDesignerSurface,
  CubesNavigator,
  cubeModuleDefinition,
  resetDDNLibraryLoaderForTests,
  setDDNLibraryLoaderForTests,
} from 'sources/cdeadmin_ui/integrations/ddn';

const SAMPLE_CUBE_DDN = [
  'version ddn-next-1',
  '// ScratchRobin mapping: scratchrobin.cube.dimensional',
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

describe('Task-specific Cube Designer', () => {
  beforeEach(() => {
    setupDDNDOM();
    setDDNLibraryLoaderForTests(async () => libraries);
  });

  afterEach(() => {
    resetDDNLibraryLoaderForTests();
  });

  it('switches across the three DDN views, edits C3 dimensions/measures via forms, previews materialization SQL and accepts to semantic store', async () => {
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
          design: makeCubeSession({status: payload.status || 'draft', version: curVer}).design,
          cube: {model: curModel, element_ids: {}, notes: payload.cubeNotes || []},
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

    // Switch between Dimensional Star, Usage Matrix, and Aggregation Grid DDN views.
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

    // Add a C3 role-playing dimension via ScratchRobin form (C2).
    fireEvent.click(screen.getByRole('button', {name: 'Add dimension…'}));
    const dimDialog = await screen.findByRole('dialog');
    fireEvent.change(within(dimDialog).getByLabelText(/Dimension name/i), {
      target: {value: 'Ship Date'},
    });
    fireEvent.change(within(dimDialog).getByLabelText(/Key column/i), {
      target: {value: 'ship_date'},
    });
    fireEvent.change(
      within(dimDialog).getByLabelText(/Role-playing base dimension ID/i),
      {target: {value: 'order_date'}}
    );
    fireEvent.click(
      within(dimDialog).getByRole('button', {name: 'Save dimension'})
    );
    await waitFor(() => expect(mockClient.saveCubeModel).toHaveBeenCalledTimes(1));
    expect(curModel.dimensions[0]).toMatchObject({
      id: 'ship_date',
      role_of: 'order_date',
    });

    // Active drift alert is surfaced and can be merged cleanly.
    const syncBtn = await screen.findByRole('button', {
      name: 'Sync active changes',
    });
    fireEvent.click(syncBtn);
    await waitFor(() =>
      expect(mockClient.syncCubeActive).toHaveBeenCalledTimes(1)
    );

    // Preview materialized aggregate native-operation review SQL.
    fireEvent.click(
      screen.getByRole('button', {name: 'Materialization plan…'})
    );
    const matDialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(
        within(matDialog).getByDisplayValue(/CREATE MATERIALIZED VIEW "agg_orders"/)
      ).toBeInTheDocument()
    );
    fireEvent.click(within(matDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Accept & apply to semantic-model store.
    fireEvent.click(screen.getByRole('button', {name: 'Accept & apply…'}));
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
    fireEvent.click(await screen.findByRole('button', {name: 'Leave accepted…'}));
    const leaveDialog = await screen.findByRole('dialog', {
      name: /Leave accepted cube version/i,
    });
    fireEvent.click(within(leaveDialog).getByRole('button', {name: 'Confirm'}));
    await waitFor(() =>
      expect(mockClient.leaveCubeAccepted).toHaveBeenCalledTimes(1)
    );
  });

  it('lists cube designs and creates or imports a cube from CubesNavigator', async () => {
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

  it('edits parent-child hierarchies, semi-additive measures, perspectives, translations and exports SML v1.8 & Apache Ossie with loss report', async () => {
    let curVer = 1;
    let curModel = sampleCubeModel();

    const mockClient = {
      openSession: jest.fn(async () =>
        makeCubeSession({status: 'draft', version: curVer})
      ),
      getCubeModel: jest.fn(async () => ({
        cube: {model: curModel, element_ids: {}, notes: []},
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
                  reason: 'Parent-child closure unsupported in Apache Ossie 0.2.0.',
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
    fireEvent.click(screen.getByRole('button', {name: 'Add dimension…'}));
    const dimDialog = await screen.findByRole('dialog');
    fireEvent.change(within(dimDialog).getByLabelText(/Dimension name/i), {
      target: {value: 'Org Rep'},
    });
    fireEvent.change(within(dimDialog).getByLabelText(/^Key column/i), {
      target: {value: 'rep_id'},
    });
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

    // 2. Semi-additive measure (LAST NON-EMPTY)
    fireEvent.click(screen.getByRole('button', {name: 'Add measure…'}));
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

    // 3. Perspectives & Translations dialogs
    fireEvent.click(screen.getByRole('button', {name: 'Perspectives…'}));
    const perspDialog = await screen.findByRole('dialog');
    fireEvent.change(within(perspDialog).getByLabelText(/Perspective name/i), {
      target: {value: 'Executive Sales'},
    });
    fireEvent.click(
      within(perspDialog).getByRole('button', {name: 'Save perspective'})
    );
    await waitFor(() =>
      expect(curModel.perspectives[0]).toMatchObject({
        id: 'executive_sales',
        name: 'Executive Sales',
      })
    );
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole('button', {name: 'Translations…'}));
    const transDialog = await screen.findByRole('dialog');
    fireEvent.change(
      within(transDialog).getByLabelText(/Localized cube caption/i),
      {target: {value: 'Cube des ventes'}}
    );
    fireEvent.change(within(transDialog).getByLabelText(/Translated entries/i), {
      target: {value: 'measure:closing_balance=Solde de cloture'},
    });
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

    // 4. Semi-additive grain warning in materialization plan
    fireEvent.click(
      screen.getByRole('button', {name: 'Materialization plan…'})
    );
    const matDialog = await screen.findByRole('dialog');
    expect(
      await within(matDialog).findByText(/Semi-additive grain warning:/i)
    ).toBeInTheDocument();
    fireEvent.click(within(matDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 5. External SML v1.8 (primary) and Apache Ossie v0.2.0 (lossy) export
    fireEvent.click(
      screen.getByRole('button', {name: 'Export SML / Ossie…'})
    );
    const expDialog = await screen.findByRole('dialog');
    expect(
      await within(expDialog).findByText(/Export format: sml@1\.8/i)
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
      within(expDialog).getByDisplayValue(/parent_child_hierarchy/)
    ).toBeInTheDocument();
    fireEvent.click(within(expDialog).getByRole('button', {name: 'Close'}));
  });
});
