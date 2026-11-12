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
  ERDDesignerSurface,
  ERDModelsNavigator,
  erdModuleDefinition,
  resetDDNLibraryLoaderForTests,
  setDDNLibraryLoaderForTests,
} from 'sources/cdeadmin_ui/integrations/ddn';

const SAMPLE_DDN = [
  'version ddn-next-1',
  '// ScratchRobin mapping: scratchrobin.erd.model',
  '',
  'view "erd_all_levels" as "ddn@1"',
  '    with',
  '        id "erd_all_levels"',
  '        title "Billing ERD"',
  '        selection',
  '            include empty list',
  '',
].join('\n');

function makeSession({suspect = true, version = 2} = {}) {
  return {
    design: {
      id: '019a0000-0000-7000-8000-000000000010',
      project_id: 'models',
      key: 'billing-erd',
      kind: 'erd',
      title: 'Billing ERD',
      head_version: version,
      active_version: 1,
      version: {
        version,
        status: 'draft',
        ddn_text: SAMPLE_DDN,
      },
      bindings: suspect
        ? [
          {
            id: '019a0000-0000-7000-8000-000000000099',
            state: 'suspect',
            target_ref: 'sqlite:table:main.customers',
          },
        ]
        : [],
    },
    workspace: {
      format: 'ddn-source-workspace@1',
      entry: 'billing-erd.ddn',
      view: 'erd_all_levels',
      files: {'billing-erd.ddn': SAMPLE_DDN},
    },
    layout: {
      algorithm: 'scratchrobin-server-layered@1',
      nodes: [{id: 'node-1', name: 'accounts', x: 48, y: 48}],
      edges: [],
      tiles: [{tx: 0, ty: 0, tile_key: 'tile-0'}],
    },
    resolved_includes: [],
    binding_summary: {
      total: 1,
      valid: suspect ? 0 : 1,
      suspect: suspect ? 1 : 0,
      unknown: 0,
    },
  };
}

describe('Task-specific ERD and data modelling designer', () => {
  beforeEach(() => {
    setupDDNDOM();
    setDDNLibraryLoaderForTests(async () => libraries);
  });

  afterEach(() => {
    resetDDNLibraryLoaderForTests();
  });

  it('renders 5-tab DesignerTabbedMenu, hides duplicate DDN view selector, confirms suspect bindings and previews alter plans', async () => {
    let suspect = true;
    const mockClient = {
      openSession: jest.fn(async () => makeSession({suspect})),
      confirmBinding: jest.fn(async () => {
        suspect = false;
        return {state: 'valid'};
      }),
      previewErdAlterPlan: jest.fn(async (_proj, _id, opts) => {
        const allDiffs = [
          {
            difference_id: 'rename_table:t1',
            change_kind: 'rename_table',
            object_name: 'customers -> accounts',
            destructive: false,
            statement: 'ALTER TABLE "customers" RENAME TO "accounts";',
          },
          {
            difference_id: 'drop_column:c1',
            change_kind: 'drop_column',
            object_name: 'accounts.legacy_code',
            destructive: true,
            statement: 'ALTER TABLE "accounts" DROP COLUMN "legacy_code";',
          },
        ];
        const selected = opts?.selectedDifferenceIds ?? [
          'rename_table:t1',
          'drop_column:c1',
        ];
        const chosen = allDiffs.filter((d) =>
          selected.includes(d.difference_id)
        );
        return {
          differences: allDiffs,
          selected_difference_ids: selected,
          script: chosen.map((d) => d.statement).join('\n'),
          has_destructive_changes: chosen.some((d) => d.destructive),
          requires_native_review: true,
          applied_immediately: false,
          destructive_warning:
            'Metadata changes may lose data and are not reversible.',
        };
      }),
      computeErdDrift: jest.fn(async () => ({
        has_drift: true,
        matched: [],
        missing_in_live: [],
        property_drift: [{element_id: 'node-1', name: 'db-primary'}],
      })),
      proposeErdDiagramChange: jest.fn(async () => ({
        proposal_id: 'prop-01',
        requires_native_review: true,
        applied_immediately: false,
      })),
    };

    const Surface = withTheme(ERDDesignerSurface);
    const {container} = render(
      <Surface
        projectId="models"
        designId="019a0000-0000-7000-8000-000000000010"
        client={mockClient}
      />
    );

    expect(await screen.findByTestId('erd-suspect-bindings')).toBeInTheDocument();
    await waitFor(() =>
      expect(
        container.querySelector('[data-cde-surface="diagram.ddn.viewer"]')
      ).not.toBeNull()
    );

    // No duplicate DDN view selector header inside DDNViewerSurface
    expect(screen.queryByLabelText('DDN view')).toBeNull();

    // Verify all 5 ribbon category tabs exist
    const menuCategories = screen.getByRole('tablist', {
      name: 'ERD designer commands categories',
    });
    for (const tabPattern of [
      /Model$/,
      /Author & Whiteboard$/,
      /Levels & Layout$/,
      /Validate & Standards$/,
      /Compare & Deploy$/,
    ]) {
      expect(
        within(menuCategories).getByRole('tab', {name: tabPattern})
      ).toBeInTheDocument();
    }

    // Confirm suspect binding (A5/A6)
    fireEvent.click(
      screen.getByRole('button', {
        name: 'Confirm sqlite:table:main.customers',
      })
    );
    await waitFor(() =>
      expect(mockClient.confirmBinding).toHaveBeenCalledWith(
        'models',
        '019a0000-0000-7000-8000-000000000010',
        '019a0000-0000-7000-8000-000000000099',
        {newTargetRef: null}
      )
    );
    await waitFor(() =>
      expect(
        screen.queryByTestId('erd-suspect-bindings')
      ).not.toBeInTheDocument()
    );

    // Switch to Compare & Deploy tab and open Alter Plan & Migration…
    fireEvent.click(
      within(menuCategories).getByRole('tab', {name: 'Compare & Deploy'})
    );
    fireEvent.click(
      screen.getByRole('button', {name: 'Alter Plan & Migration…'})
    );
    const alterDialog = await screen.findByRole('dialog', {
      name: 'Preview ERD alter plan',
    });
    expect(
      await within(alterDialog).findByTestId('erd-destructive-warning')
    ).toHaveTextContent('not reversible');
    expect(within(alterDialog).getByText('Loses Data: 1')).toBeInTheDocument();
    expect(
      within(alterDialog).getByText('Breaks Running Clients: 2')
    ).toBeInTheDocument();

    const dropBox = within(alterDialog).getByRole('checkbox', {
      name: /drop_column: accounts\.legacy_code/,
    });
    expect(dropBox).toBeChecked();
    fireEvent.click(dropBox);
    await waitFor(() =>
      expect(mockClient.previewErdAlterPlan).toHaveBeenLastCalledWith(
        'models',
        '019a0000-0000-7000-8000-000000000010',
        expect.objectContaining({
          selectedDifferenceIds: ['rename_table:t1'],
        })
      )
    );
    fireEvent.click(within(alterDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', {name: 'Preview ERD alter plan'})
      ).not.toBeInTheDocument()
    );

    // Open System Drift & submit diagram change proposal for native review (D1)
    fireEvent.click(screen.getByRole('button', {name: 'System Drift…'}));
    const driftDialog = await screen.findByRole('dialog', {
      name: 'System diagram drift and change review',
    });
    // Switch to Propose Native Review Change tab inside dialog
    fireEvent.click(
      within(driftDialog).getByRole('tab', {
        name: 'Propose Native Review Change',
      })
    );
    fireEvent.click(
      within(driftDialog).getByRole('button', {name: 'Request native review'})
    );
    expect(
      await within(driftDialog).findByTestId('erd-change-proposal')
    ).toHaveTextContent('applied immediately: false');
  });

  it('supports Property Inspector CRUD, Whiteboard Sketch & Promotion, Naming Standards auto-fix, conflict-free Engine Conversion, OperationBus review and Environment Matrix', async () => {
    let headVer = 2;
    let handdrawn = false;
    const elementsState = {
      look_handdrawn: false,
      conceptual_entities: [
        {id: '019a0000-0000-7000-8000-000000000201', name: 'Customer', area: 'CRM', note: ''},
      ],
      conceptual_relations: [],
      conceptual_notes: [],
      logical_entities: [],
      logical_relations: [],
      physical_tables: [
        {
          id: '019a0000-0000-7000-8000-000000000301',
          name: 'CustomerAccounts',
          schema: 'public',
          engine: 'postgresql',
          fields: [
            {
              id: '019a0000-0000-7000-8000-000000000302',
              name: 'AccountID',
              datatype: 'BIGINT',
              pk: true,
              nullable: false,
            },
          ],
          indexes: [],
          foreign_keys: [],
        },
      ],
      deployment_nodes: [],
      deployment_links: [],
      level_links: [],
      extensions: {},
    };

    const mockClient = {
      openSession: jest.fn(async (_p, _d, opts) =>
        makeSession({suspect: false, version: opts?.version || headVer})
      ),
      inspectErdElements: jest.fn(async () => ({
        ...elementsState,
        look_handdrawn: handdrawn,
      })),
      mutateErdElements: jest.fn(async (_p, _d, payload) => {
        headVer += 1;
        if (payload.operation === 'set_sketch_look') {
          handdrawn = Boolean(payload.look_handdrawn);
        }
        if (payload.operation === 'upsert_physical_table' && payload.table) {
          elementsState.physical_tables[0].name = payload.table.name;
        }
        return {
          design: makeSession({suspect: false, version: headVer}).design,
          layout: {nodes: [], edges: [], tiles: []},
          elements: {...elementsState, look_handdrawn: handdrawn},
        };
      }),
      promoteErdWhiteboard: jest.fn(async (_p, _d, payload) => {
        if (payload.save_version !== false) headVer += 1;
        return {
          design: makeSession({suspect: false, version: headVer}).design,
          promoted_logical_count: 1,
          promoted_physical_count: 1,
          inferred_foreign_keys: 0,
          matched_catalog_tables: [],
          ddn_text: SAMPLE_DDN,
        };
      }),
      evaluateErdStandards: jest.fn(async (_p, _d, payload) => {
        if (payload.action === 'apply_fixes') {
          headVer += 1;
          elementsState.physical_tables[0].name = 'customer_accounts';
          return {
            violations: [],
            active_count: 0,
            waived_count: 0,
            fixed_count: 2,
            rules: {table_case: 'snake_case'},
            waivers: [],
            design: makeSession({suspect: false, version: headVer}).design,
          };
        }
        return {
          violations: [
            {
              id: 'table_case:table:CustomerAccounts',
              rule: 'table_case',
              current_name: 'CustomerAccounts',
              suggested_name: 'customer_accounts',
              waived: false,
              target: 'table:CustomerAccounts',
            },
          ],
          active_count: 1,
          waived_count: 0,
          rules: {
            table_case: 'snake_case',
            column_case: 'snake_case',
            pk_pattern: 'pk_{table}',
            fk_pattern: 'fk_{table}_{ref}',
            ix_pattern: 'ix_{table}_{cols}',
          },
          waivers: [],
        };
      }),
      convertErdEngine: jest.fn(async () => ({
        ddn_text: SAMPLE_DDN,
        loss_report: {target_engine: 'duckdb', lossy_count: 0, items: []},
      })),
      saveVersion: jest.fn(async () => {
        headVer += 1;
        return makeSession({suspect: false, version: headVer});
      }),
      deployErdPlan: jest.fn(async (_p, _d, payload) => {
        if (payload.action === 'submit_review') {
          return {
            operation_id: 'op-review-77',
            status: 'awaiting_approval',
            statement_count: 2,
            applied_immediately: false,
          };
        }
        if (payload.action === 'record_environment_deployment') {
          return {
            status: 'recorded',
            environments: [
              {
                environment: 'dev',
                label: 'Development',
                endpoint_id: 'env-dev',
                database_target_id: 'dev_db',
                deployed_version: headVer,
                desired_version: headVer,
                drift_status: 'in_sync',
              },
            ],
          };
        }
        return {
          plan: {
            differences: [],
            selected_difference_ids: [],
            statements: [],
            script: '',
            destructive_warning: 'Destructive metadata warning.',
          },
          risk_summary: {
            loses_data: 0,
            may_fail_on_existing_data: 0,
            breaks_running_clients: 0,
            locks_or_copies_table: 0,
          },
          migration_scripts: {plain_sql: '-- SQL'},
          environments: [
            {
              environment: 'dev',
              label: 'Development',
              endpoint_id: 'env-dev',
              database_target_id: 'dev_db',
              deployed_version: null,
              desired_version: headVer,
              drift_status: 'not_deployed',
            },
            {
              environment: 'staging',
              label: 'Staging',
              endpoint_id: 'env-staging',
              database_target_id: 'staging_db',
              deployed_version: 1,
              desired_version: headVer,
              drift_status: 'behind',
            },
            {
              environment: 'prod',
              label: 'Production',
              endpoint_id: 'env-prod',
              database_target_id: 'prod_db',
              deployed_version: 1,
              desired_version: headVer,
              drift_status: 'behind',
            },
          ],
        };
      }),
    };

    const Surface = withTheme(ERDDesignerSurface);
    const {container} = render(
      <Surface
        projectId="models"
        designId="019a0000-0000-7000-8000-000000000010"
        client={mockClient}
      />
    );

    // 1. Property Inspector edits physical table and saves
    const inspector = await screen.findByTestId('erd-property-inspector');
    await waitFor(() =>
      expect(within(inspector).getByDisplayValue('CustomerAccounts')).toBeInTheDocument()
    );
    fireEvent.change(within(inspector).getByLabelText('Element Name'), {
      target: {value: 'customer_accounts_v2'},
    });
    fireEvent.click(
      within(inspector).getByRole('button', {name: 'Save Level Changes'})
    );
    await waitFor(() =>
      expect(mockClient.mutateErdElements).toHaveBeenCalledWith(
        'models',
        '019a0000-0000-7000-8000-000000000010',
        expect.objectContaining({
          operation: 'upsert_physical_table',
          table: expect.objectContaining({name: 'customer_accounts_v2'}),
        })
      )
    );

    // 2. Author & Whiteboard: Sketch Look toggle + Make it a design… promotion
    const menuCategories = screen.getByRole('tablist', {
      name: 'ERD designer commands categories',
    });
    fireEvent.click(
      within(menuCategories).getByRole('tab', {name: 'Author & Whiteboard'})
    );
    fireEvent.click(screen.getByRole('button', {name: 'Sketch Look'}));
    await waitFor(() =>
      expect(
        container.querySelector('[data-erd-sketch="handdrawn"]')
      ).not.toBeNull()
    );

    fireEvent.click(screen.getByRole('button', {name: 'Make it a design…'}));
    const promoDialog = await screen.findByRole('dialog', {
      name: /Make It a Design/,
    });
    fireEvent.click(
      within(promoDialog).getByRole('button', {
        name: 'Promote & Save Checkpoint',
      })
    );
    await waitFor(() =>
      expect(mockClient.promoteErdWhiteboard).toHaveBeenCalledWith(
        'models',
        '019a0000-0000-7000-8000-000000000010',
        expect.objectContaining({save_version: true})
      )
    );
    await waitFor(() =>
      expect(
        within(promoDialog).getByRole('button', {name: 'Close'})
      ).not.toBeDisabled()
    );
    fireEvent.click(within(promoDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', {name: /Make It a Design/})
      ).not.toBeInTheDocument()
    );

    // 3. Validate & Standards: Naming Standards violation badge & 1-Click Auto-Fix All
    fireEvent.click(
      within(menuCategories).getByRole('tab', {name: /Validate & Standards$/})
    );
    fireEvent.click(
      screen.getByRole('button', {name: /Naming Standards… \(1\)/})
    );
    const stdDialog = await screen.findByRole('dialog', {
      name: 'ERD Naming Standards & Waiver Inspector',
    });
    expect(within(stdDialog).getByText('customer_accounts')).toBeInTheDocument();
    const autoFixBtn = within(stdDialog).getByRole('button', {
      name: '1-Click Auto-Fix All',
    });
    await waitFor(() => expect(autoFixBtn).not.toBeDisabled());
    fireEvent.click(autoFixBtn);
    await waitFor(() =>
      expect(mockClient.evaluateErdStandards).toHaveBeenCalledWith(
        'models',
        '019a0000-0000-7000-8000-000000000010',
        expect.objectContaining({action: 'apply_fixes'})
      )
    );
    const stdCloseBtn = within(stdDialog).getByRole('button', {name: 'Close'});
    await waitFor(() => expect(stdCloseBtn).not.toBeDisabled());
    fireEvent.click(stdCloseBtn);
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', {
          name: 'ERD Naming Standards & Waiver Inspector',
        })
      ).not.toBeInTheDocument()
    );

    // 4. Compare & Deploy: Engine Conversion (zero raw JSON textareas, conflict-free save)
    fireEvent.click(
      within(menuCategories).getByRole('tab', {name: /Compare & Deploy$/})
    );
    fireEvent.click(screen.getByRole('button', {name: 'Engine Conversion…'}));
    const convDialog = await screen.findByRole('dialog', {
      name: 'Convert ERD Engine',
    });
    expect(within(convDialog).queryByLabelText(/JSON/i)).toBeNull();
    expect(
      within(convDialog).getByRole('group', {
        name: 'Custom Engine Type Overrides',
      })
    ).toBeInTheDocument();
    fireEvent.click(
      within(convDialog).getByRole('button', {name: 'Save Converted Version'})
    );
    await waitFor(() =>
      expect(mockClient.saveVersion).toHaveBeenCalledWith(
        'models',
        '019a0000-0000-7000-8000-000000000010',
        expect.objectContaining({allow_conflict_note: true})
      )
    );
    const convCloseBtn = within(convDialog).getByRole('button', {name: 'Close'});
    await waitFor(() => expect(convCloseBtn).not.toBeDisabled());
    fireEvent.click(convCloseBtn);
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', {name: 'Convert ERD Engine'})
      ).not.toBeInTheDocument()
    );

    // 5. Environment Matrix (Dev / Staging / Prod) + Queue Review + Record Verified
    fireEvent.click(
      screen.getByRole('button', {
        name: 'Environment Matrix (Dev/Stage/Prod)…',
      })
    );
    const envDialog = await screen.findByRole('dialog', {
      name: 'Multi-Target Deployment Environment Matrix',
    });
    expect(await within(envDialog).findByText('Development')).toBeInTheDocument();
    expect(within(envDialog).getByText('Staging')).toBeInTheDocument();
    expect(within(envDialog).getByText('Production')).toBeInTheDocument();

    const queueButtons = within(envDialog).getAllByRole('button', {
      name: 'Queue Review',
    });
    await waitFor(() => expect(queueButtons[0]).not.toBeDisabled());
    fireEvent.click(queueButtons[0]);
    await waitFor(() =>
      expect(within(envDialog).getByText(/op-review-77/)).toBeInTheDocument()
    );

    const verifyButtons = within(envDialog).getAllByRole('button', {
      name: 'Record Verified',
    });
    await waitFor(() => expect(verifyButtons[0]).not.toBeDisabled());
    fireEvent.click(verifyButtons[0]);
    await waitFor(() =>
      expect(within(envDialog).getByText('in_sync')).toBeInTheDocument()
    );
  });

  it('launches New Data Model (ERD), imports SQL/DBML with explicit loss reports, and handles cdeadmin:design-shortcut events', async () => {
    const def = erdModuleDefinition();
    const newCmd = def.contributions.commands.find(
      (c) => c.id === 'erd.designer.new'
    );
    expect(newCmd.surfaces).toContain('tools');
    const showActivity = jest.fn();
    newCmd.execute({}, {showActivity});
    expect(showActivity).toHaveBeenCalledWith('activity.erd_models');

    const projectClient = {
      listProjects: jest.fn(async () => [
        {project_id: 'models', name: 'Models', access: 'owner'},
      ]),
      createProject: jest.fn(),
    };
    const createdDesign = {
      id: '019a0000-0000-7000-8000-000000000055',
      title: 'Warehouse Model',
      head_version: 1,
    };
    const models = [];
    const designClient = {
      listDesigns: jest.fn(async () => [...models]),
      createErdDesign: jest.fn(async (_projId, payload) => {
        models.push({...createdDesign, title: payload.title});
        return {...createdDesign, title: payload.title};
      }),
      importErdExternal: jest.fn(async (_projId, payload) => ({
        design: {
          id: '019a0000-0000-7000-8000-000000000088',
          title: payload.title,
          head_version: 1,
        },
        summary: {
          tables_imported: 2,
          relationships_imported: 1,
          loss_count: 1,
        },
        loss_report: {
          loss_count: 1,
          items: [
            {
              code: 'sql_check_constraint_omitted',
              severity: 'info',
              object: 'orders',
              detail: 'CHECK constraint omitted from ERD diagram',
            },
          ],
        },
      })),
      queryWhereUsed: jest.fn(async () => ({
        usages: [
          {
            binding_id: 'b-1',
            design_kind: 'bi',
            design_title: 'Orders Revenue Dashboard',
            element_label: 'Revenue Card',
            target_ref: 'public.orders',
            validity: 'valid',
          },
        ],
      })),
    };
    const onOpenModel = jest.fn();

    const Nav = withTheme(ERDModelsNavigator);
    render(
      <Nav
        projectClient={projectClient}
        designClient={designClient}
        onOpenModel={onOpenModel}
      />
    );

    const dialog = await screen.findByRole('dialog', {
      name: 'New data model (ERD)',
    });
    fireEvent.change(within(dialog).getByLabelText(/Model title/), {
      target: {value: 'Warehouse Model'},
    });
    fireEvent.change(
      within(dialog).getByLabelText(/Initial entity or table name/),
      {target: {value: 'Shipment'}}
    );
    fireEvent.click(
      within(dialog).getByRole('button', {name: 'Create data model'})
    );

    await waitFor(() => expect(onOpenModel).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', {name: 'New data model (ERD)'})
      ).not.toBeInTheDocument()
    );
    expect(designClient.createErdDesign).toHaveBeenCalledWith(
      'models',
      expect.objectContaining({
        title: 'Warehouse Model',
        conceptualEntities: [{name: 'Shipment'}],
      })
    );

    // Import SQL DDL and verify explicit loss report rendering
    fireEvent.click(
      await screen.findByRole('button', {name: 'Import SQL / DBML / Catalog…'})
    );
    const importDialog = await screen.findByRole('dialog', {
      name: /Import SQL DDL, DBML or Live Catalog/,
    });
    fireEvent.change(within(importDialog).getByLabelText(/Model title/), {
      target: {value: 'Imported Commerce'},
    });
    fireEvent.change(within(importDialog).getByLabelText(/Schema source text/), {
      target: {value: 'CREATE TABLE orders (id BIGINT PRIMARY KEY, CHECK (id > 0));'},
    });
    fireEvent.click(
      within(importDialog).getByRole('button', {name: 'Import as Draft ERD'})
    );
    expect(
      await within(importDialog).findByTestId('erd-import-loss-report')
    ).toHaveTextContent('sql_check_constraint_omitted');
    fireEvent.click(
      within(importDialog).getByRole('button', {name: 'Open Imported Model'})
    );
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', {
          name: /Import SQL DDL, DBML or Live Catalog/,
        })
      ).not.toBeInTheDocument()
    );
    expect(onOpenModel).toHaveBeenLastCalledWith(
      'models',
      expect.objectContaining({title: 'Imported Commerce'})
    );

    // Dispatch cdeadmin:design-shortcut ('erd_from_database')
    act(() => {
      window.dispatchEvent(
        new CustomEvent('cdeadmin:design-shortcut', {
          detail: {
            design_shortcut: 'erd_from_database',
            endpointId: 'ep-live-pg',
            providerId: 'postgresql',
            endpointLabel: 'Prod PG',
          },
        })
      );
    });
    const shortcutImportDialog = await screen.findByRole('dialog', {
      name: /Import SQL DDL, DBML or Live Catalog/,
    });
    expect(
      within(shortcutImportDialog).getByDisplayValue('ep-live-pg')
    ).toBeInTheDocument();
    fireEvent.click(
      within(shortcutImportDialog).getByRole('button', {name: 'Close'})
    );
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', {
          name: /Import SQL DDL, DBML or Live Catalog/,
        })
      ).not.toBeInTheDocument()
    );

    // Dispatch cdeadmin:design-shortcut ('where_used')
    act(() => {
      window.dispatchEvent(
        new CustomEvent('cdeadmin:design-shortcut', {
          detail: {
            design_shortcut: 'where_used',
            targetRef: 'public.orders',
          },
        })
      );
    });
    const whereDialog = await screen.findByRole('dialog', {
      name: /Where Used Across Designs/,
    });
    expect(
      await within(whereDialog).findByText('Orders Revenue Dashboard')
    ).toBeInTheDocument();
  });
});
