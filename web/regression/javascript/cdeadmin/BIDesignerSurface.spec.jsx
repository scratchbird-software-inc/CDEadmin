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
import SQLConnections from 'sources/cdeadmin_ui/editors/SQLConnections';
import {
  BIDesignerSurface,
  BIDesignsNavigator,
  biDesignerModuleDefinition,
  resetDDNLibraryLoaderForTests,
  setDDNLibraryLoaderForTests,
} from 'sources/cdeadmin_ui/integrations/ddn';

const SAMPLE_QUESTION_DDN = [
  'version ddn-next-1',
  '// ScratchRobin module: scratchrobin.bi.question@1',
  '',
  'data "question_preview"',
  '    with',
  '        columns',
  '            item',
  '                id "row_id"',
  '                type "text"',
  '            item',
  '                id "region"',
  '                type "text"',
  '            item',
  '                id "total_amount"',
  '                type "number"',
  '        rows',
  '            item ["r_1", "North", 120]',
  '',
  'view "question_chart" as "chart.basic@1"',
  '    with',
  '        id "question_chart"',
  '        title "Orders by Region"',
  '        selection',
  '            include empty list',
  '        projection',
  '            source "question_preview"',
  '            options',
  '                mark "bar"',
  '                x "region"',
  '                y "total_amount"',
  '',
  'view "question_lineage" as "bi.analytics@1"',
  '    with',
  '        id "question_lineage"',
  '        title "Orders by Region — Query Lineage"',
  '        selection',
  '            include empty list',
  '',
].join('\n');

const SAMPLE_DASHBOARD_DDN = [
  'version ddn-next-1',
  '// ScratchRobin module: scratchrobin.bi.dashboard@1',
  '',
  'view "dashboard_composed" as "panels.composed@1"',
  '    with',
  '        id "dashboard_composed"',
  '        title "Revenue Dashboard — Overview"',
  '        selection',
  '            include empty list',
  '        projection',
  '            options',
  '                columns 2',
  '                panels empty list',
  '',
  'view "dashboard_wiring" as "bi.analytics@1"',
  '    with',
  '        id "dashboard_wiring"',
  '        title "Revenue Dashboard — Wiring & Lineage"',
  '        selection',
  '            include empty list',
  '',
].join('\n');

function makeQuestionSession({status = 'draft', version = 1} = {}) {
  return {
    design: {
      id: '019a0000-0000-7000-8000-000000000050',
      project_id: 'analytics',
      key: 'orders-by-region',
      kind: 'question',
      title: 'Orders by Region',
      head_version: version,
      active_version: status === 'accepted' ? version : null,
      version: {
        version,
        status,
        ddn_text: SAMPLE_QUESTION_DDN,
      },
      bindings: [],
    },
    workspace: {
      format: 'ddn-source-workspace@1',
      entry: 'orders-by-region.ddn',
      view: 'question_chart',
      files: {'orders-by-region.ddn': SAMPLE_QUESTION_DDN},
    },
    layout: {
      algorithm: 'scratchrobin-server-layered@1',
      nodes: [],
      edges: [],
      tiles: [],
    },
    resolved_includes: [],
    binding_summary: {total: 0, valid: 0, suspect: 0, unknown: 0},
  };
}

function makeDashboardSession({status = 'draft', version = 1} = {}) {
  return {
    design: {
      id: '019a0000-0000-7000-8000-000000000051',
      project_id: 'analytics',
      key: 'revenue-dashboard',
      kind: 'dashboard',
      title: 'Revenue Dashboard',
      head_version: version,
      active_version: status === 'accepted' ? version : null,
      version: {
        version,
        status,
        ddn_text: SAMPLE_DASHBOARD_DDN,
      },
      bindings: [],
    },
    workspace: {
      format: 'ddn-source-workspace@1',
      entry: 'revenue-dashboard.ddn',
      view: 'dashboard_composed',
      files: {'revenue-dashboard.ddn': SAMPLE_DASHBOARD_DDN},
    },
    layout: {
      algorithm: 'scratchrobin-server-layered@1',
      nodes: [],
      edges: [],
      tiles: [],
    },
    resolved_includes: [],
    binding_summary: {total: 0, valid: 0, suspect: 0, unknown: 0},
  };
}

function sampleQuestionModel() {
  return {
    contract_version: '1.0.0',
    name: 'Orders by Region',
    description: '',
    endpoint_id: 'ep-1',
    verification_tier: 'draft',
    query: {
      kind: 'sbsql',
      sbsql: {
        dialect: 'sbsql@1',
        from: {relation: ['main', 'orders'], alias: 'orders'},
        joins: [
          {
            type: 'left',
            relation: ['main', 'order_items'],
            alias: 'items',
            cardinality: 'one_to_many',
            on: [{left: ['orders', 'id'], op: '=', right: ['items', 'order_id']}],
            using: [],
          },
        ],
        columns: [{column: ['orders', 'region'], alias: 'region'}],
        measures: [
          {function: 'sum', column: ['orders', 'amount'], alias: 'total_amount'},
        ],
        filters: [{column: ['orders', 'status'], operator: 'eq', value: 'paid'}],
        group_by: {kind: 'columns', columns: [['orders', 'region']]},
        order_by: [],
        limit: 100,
      },
    },
    parameters: [],
    visualization: {type: 'bar', settings: {}},
    visualization_format: {
      number_format: 'currency',
      currency_code: 'EUR',
      decimals: 2,
      date_grain: 'month',
      x_axis_label: 'Region',
      y_axis_label: 'Net EUR',
      show_accessible_table_default: false,
    },
    result_policy: {
      redact_columns: [],
      cache_ttl_seconds: 300,
      page_size: 100,
      export: {enabled: false, formats: []},
    },
    preview_rows: [['North', 120]],
    review_flags: {
      saved_filter_values: [{path: 'query.filters[0]', value: 'paid'}],
      fanout_warnings: [
        {
          code: 'one_to_many_fanout',
          severity: 'warning',
          detail: 'Join to main.order_items has one_to_many cardinality.',
        },
      ],
    },
  };
}

function sampleDashboardModel() {
  return {
    contract_version: '1.0.0',
    name: 'Revenue Dashboard',
    description: '',
    tabs: [{id: 'main', name: 'Overview'}],
    cards: [
      {
        id: 'snapshot_1',
        tab_id: 'main',
        type: 'metric_panel',
        title: 'Throughput Snapshot',
        click_behavior: 'inherit',
        layout: {x: 0, y: 0, w: 12, h: 8},
        metric_panel: {
          panel_id: 'pg_tps',
          snapshot_mode: 'static',
          columns: [{id: 'measure', label: 'Measure'}],
          rows: [],
        },
      },
    ],
    filters: [
      {
        id: 'region',
        name: 'Region',
        type: 'string',
        widget: 'select',
        operator: 'eq',
        pinned_by_author: true,
        default: 'North',
        targets: [],
      },
    ],
    links: [],
    interaction: {
      default_click_behavior: 'cross_filter',
      auto_apply_filters: true,
      filter_state_scope: 'personal',
      drill_carries_filter_context: true,
    },
    review_flags: {saved_filter_values: []},
  };
}

describe('Task-specific BI Questions & Dashboards Designer (Phase 1 & Phase 2)', () => {
  beforeEach(() => {
    setupDDNDOM();
    setDDNLibraryLoaderForTests(() => Promise.resolve(libraries()));
    window.__cdeadminPendingDesignShortcut = null;
  });

  afterEach(() => {
    resetDDNLibraryLoaderForTests();
    window.__cdeadminPendingDesignShortcut = null;
  });

  it('renders 5-tab DesignerTabbedMenu, single DDN view selector, structured SBsql builder, formatters, accessible data table, SQL compilation & Accept', async () => {
    const session = makeQuestionSession();
    const client = {
      openSession: jest.fn().mockResolvedValue(session),
      getBiModel: jest.fn().mockResolvedValue({
        design: session.design,
        bi_kind: 'question',
        bi: {question: sampleQuestionModel(), question_notes: ''},
        outward_effects: [],
      }),
      saveBiModel: jest.fn().mockResolvedValue({
        design: session.design,
      }),
      biSqlBridge: jest.fn().mockResolvedValue({
        sql: 'SELECT "orders"."region" AS "region" FROM "main"."orders" AS "orders" WHERE "orders"."status" = ?',
        parameters: ['paid'],
      }),
      acceptVersion: jest.fn().mockResolvedValue({
        ...makeQuestionSession({status: 'accepted'}).design,
        outward_effects_activated: false,
        active_outward_effects: [],
      }),
    };

    const Themed = withTheme(BIDesignerSurface);
    render(
      <Themed
        projectId="analytics"
        designId={session.design.id}
        kind="question"
        client={client}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Question v1 · draft/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/SR-F-010024/)).toBeInTheDocument();
    expect(screen.getByText(/SR-F-030030/)).toBeInTheDocument();

    // 5 ribbon category tabs + exactly ONE DDN view selector (showViewSelector={false})
    const menuNav = screen.getByRole('navigation', {name: /BI designer menu/i});
    for (const tabLabel of [
      'Design',
      'Query & Cards',
      'Chart & Accessibility',
      'SQL & AI Draft',
      'Outward & Kiosk',
    ]) {
      expect(
        within(menuNav).getByRole('tab', {name: new RegExp(tabLabel, 'i')})
      ).toBeInTheDocument();
    }
    expect(screen.getAllByRole('combobox', {name: /DDN view/i})).toHaveLength(1);

    expect(
      await screen.findByText(/SBsql join fan-out warning/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Review saved filter literal\/default values/i)
    ).toBeInTheDocument();

    // Tab 2: Structured Query Builder uses TypedRowsEditor (no CSV textfields)
    fireEvent.click(
      within(menuNav).getByRole('tab', {name: /Query & Cards/i})
    );
    fireEvent.click(
      screen.getByRole('button', {name: /Structured Query Builder…/i})
    );
    const qDialog = await screen.findByRole('dialog');
    expect(within(qDialog).getByText(/SR-F-030031/)).toBeInTheDocument();
    expect(
      within(qDialog).getByRole('group', {name: 'Joined Tables'})
    ).toBeInTheDocument();
    fireEvent.click(within(qDialog).getByRole('button', {name: 'Cancel'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Tab 3: Axis & Number Formatters + Accessible Data Table toggle
    fireEvent.click(
      within(menuNav).getByRole('tab', {name: 'Chart & Accessibility'})
    );
    fireEvent.click(
      screen.getByRole('button', {name: /Accessible Data Table/i})
    );
    const accTable = await screen.findByRole('table', {
      name: /Accessible BI data table/i,
    });
    expect(within(accTable).getByText('€120.00')).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', {name: /Axis & Number Formatters…/i})
    );
    const fmtDialog = await screen.findByRole('dialog');
    expect(within(fmtDialog).getByText(/SR-F-030032/)).toBeInTheDocument();
    fireEvent.click(
      within(fmtDialog).getByRole('button', {name: /Apply Formatters/i})
    );
    await waitFor(() => expect(client.saveBiModel).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Tab 4: Compile Dialect SQL inside CodeEditor
    fireEvent.click(within(menuNav).getByRole('tab', {name: 'SQL & AI Draft'}));
    fireEvent.click(
      screen.getByRole('button', {name: /Compile Dialect SQL…/i})
    );
    const sqlDialog = await screen.findByRole('dialog');
    await waitFor(() => {
      expect(client.biSqlBridge).toHaveBeenCalledWith(
        'analytics',
        session.design.id,
        expect.objectContaining({action: 'compile_sql', dialect: 'sqlite'})
      );
      expect(
        within(sqlDialog).getByText(/Bound parameters:/i)
      ).toBeInTheDocument();
    });
    fireEvent.click(within(sqlDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // Tab 1: Accept Version
    fireEvent.click(within(menuNav).getByRole('tab', {name: 'Design'}));
    fireEvent.click(screen.getByRole('button', {name: /^Accept$/i}));
    const acceptBtn = await screen.findByRole('button', {
      name: /^Accept Version$/i,
    });
    fireEvent.click(acceptBtn);
    await waitFor(() => {
      expect(client.acceptVersion).toHaveBeenCalled();
      expect(
        screen.getByText(/Outward effects activated: false/i)
      ).toBeInTheDocument();
    });
  });

  it('supports interactive dashboard cross-filter & drill-through bar and manages Kiosk Device Fleet (list, mint, revoke)', async () => {
    const session = makeDashboardSession({status: 'accepted'});
    const client = {
      openSession: jest.fn().mockResolvedValue(session),
      getBiModel: jest.fn().mockResolvedValue({
        design: session.design,
        bi_kind: 'dashboard',
        bi: {dashboard: sampleDashboardModel(), dashboard_notes: ''},
        outward_effects: [],
      }),
      biSqlBridge: jest.fn().mockResolvedValue({
        carried_filters: {
          region: 'North',
          snapshot_1: 'Throughput Snapshot:selected',
        },
      }),
      reviewBiOutwardEffect: jest.fn().mockResolvedValue({
        effect: {
          id: 'pub-01',
          effect_kind: 'dashboard_server',
          enabled: true,
        },
      }),
      listBiDeviceTokens: jest.fn().mockResolvedValue({
        active_publication_id: 'pub-01',
        tokens: [],
      }),
      manageBiDeviceTokens: jest
        .fn()
        .mockResolvedValueOnce({
          publication_id: 'pub-01',
          device_token: 'srbikiosk.v1.signedtoken',
          kiosk_url:
            '/cdeadmin/designs/kiosk/pub-01#token=srbikiosk.v1.signedtoken',
          tokens: [
            {
              token_id: 'tok-01',
              device_label: 'lobby-kiosk',
              status: 'active',
              locked_filters: {},
              last_used_at: null,
            },
          ],
        })
        .mockResolvedValueOnce({
          revoked: {token_id: 'tok-01', status: 'revoked'},
          tokens: [
            {
              token_id: 'tok-01',
              device_label: 'lobby-kiosk',
              status: 'revoked',
              locked_filters: {},
              last_used_at: null,
            },
          ],
        }),
    };

    const Themed = withTheme(BIDesignerSurface);
    render(
      <Themed
        projectId="analytics"
        designId={session.design.id}
        kind="dashboard"
        client={client}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Dashboard v1 · accepted/i)).toBeInTheDocument();
    });
    expect(
      screen.getByText(/hold static snapshots in BI and do not poll/i)
    ).toBeInTheDocument();

    // Interactive Cross-Filter & Drill-Through Bar
    const strip = screen.getByLabelText(/Active Filter and Cross-Filter Strip/i);
    expect(within(strip).getByText('Personal')).toBeInTheDocument();
    expect(
      within(strip).getByLabelText(/Region \(Author-Pinned\)/i)
    ).toHaveValue('North');
    fireEvent.click(
      within(strip).getByRole('button', {
        name: /Throughput Snapshot \(cross_filter\)/i,
      })
    );
    fireEvent.click(
      within(strip).getByRole('button', {name: /Drill-Through with Context/i})
    );
    await waitFor(() => {
      expect(client.biSqlBridge).toHaveBeenCalledWith(
        'analytics',
        session.design.id,
        expect.objectContaining({
          action: 'drill_context',
          crossFilters: {snapshot_1: 'Throughput Snapshot:selected'},
        })
      );
      expect(
        screen.getByLabelText(/Carried drill-through context/i)
      ).toHaveTextContent('Throughput Snapshot:selected');
    });

    // Outward & Kiosk Device Fleet
    const menuNav = screen.getByRole('navigation', {name: /BI designer menu/i});
    fireEvent.click(within(menuNav).getByRole('tab', {name: 'Outward & Kiosk'}));
    fireEvent.click(
      screen.getByRole('button', {name: /Dashboard Server & Kiosk Fleet…/i})
    );
    const outwardDialog = await screen.findByRole('dialog');
    expect(within(outwardDialog).getByText(/SR-F-030033/)).toBeInTheDocument();

    fireEvent.click(
      within(outwardDialog).getByRole('button', {
        name: /Review & Apply Server Publication/i,
      })
    );
    await waitFor(() => {
      expect(client.reviewBiOutwardEffect).toHaveBeenCalledWith(
        'analytics',
        session.design.id,
        expect.objectContaining({
          effectKind: 'dashboard_server',
          enabled: true,
          publisherUserId: 1,
        })
      );
    });

    fireEvent.click(
      within(outwardDialog).getByRole('button', {name: /Mint Device Token/i})
    );
    await waitFor(() => {
      expect(client.manageBiDeviceTokens).toHaveBeenCalledWith(
        'analytics',
        session.design.id,
        expect.objectContaining({action: 'mint', publication_id: 'pub-01'})
      );
      expect(
        within(outwardDialog).getByDisplayValue(
          /\/cdeadmin\/designs\/kiosk\/pub-01#token=srbikiosk\.v1\.signedtoken/
        )
      ).toBeInTheDocument();
    });

    const revokeBtn = await within(outwardDialog).findByRole('button', {
      name: 'Revoke',
    });
    fireEvent.click(revokeBtn);
    await waitFor(() => {
      expect(client.manageBiDeviceTokens).toHaveBeenCalledWith(
        'analytics',
        session.design.id,
        {action: 'revoke', token_id: 'tok-01'}
      );
    });
  });

  it('imports Superset .json/.zip files without raw JSON paste and supports bidirectional SQLConnections ↔ BI handoff', async () => {
    const onOpen = jest.fn();
    const projectClient = {
      listProjects: jest.fn().mockResolvedValue([
        {project_id: 'analytics', name: 'Analytics', access: 'owner'},
      ]),
    };
    const designClient = {
      listDesigns: jest.fn().mockResolvedValue([
        {
          id: 'q-1',
          kind: 'question',
          title: 'Orders by Region',
          head_version: 1,
        },
      ]),
      biSqlBridge: jest.fn().mockResolvedValue({
        fidelity: 'exact',
        loss: [],
        question: sampleQuestionModel(),
      }),
      createBiQuestion: jest.fn().mockResolvedValue({
        id: 'q-from-sql',
        kind: 'question',
        title: 'SQL Question',
      }),
      importBiSuperset: jest.fn().mockResolvedValue({
        source_format: 'superset_zip',
        status: 'draft',
        questions: [{id: 'q-imp', kind: 'question', title: 'Imported Chart'}],
        dashboards: [
          {id: 'd-imp', kind: 'dashboard', title: 'Imported Dashboard'},
        ],
        loss_report: {
          source_format: 'superset_zip',
          loss_count: 1,
          items: [{code: 'custom_plugin_fallback'}],
        },
      }),
    };

    const ThemedNav = withTheme(BIDesignsNavigator);
    const ThemedSql = withTheme(SQLConnections);
    render(
      <div>
        <ThemedSql />
        <ThemedNav
          designClient={designClient}
          projectClient={projectClient}
          onOpenDesign={onOpen}
        />
      </div>
    );

    await waitFor(() => {
      expect(
        screen.getByText(/Orders by Region \(question\)/i)
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/SR-F-010025/)).toBeInTheDocument();

    // 1. Open in SQL Editor event populates SQLConnections query editor
    act(() => {
      window.dispatchEvent(
        new CustomEvent('cdeadmin:open-sql-in-editor', {
          detail: {
            sql: 'SELECT region, SUM(amount) FROM orders GROUP BY region',
            dialect: 'postgresql',
          },
        })
      );
    });

    // 2. Clicking "Save as BI Question…" in SQLConnections opens BIDesignsNavigator pre-populated
    fireEvent.click(
      screen.getByRole('button', {name: /Save as BI Question…/i})
    );
    const sqlImportDialog = await screen.findByRole('dialog');
    expect(within(sqlImportDialog).getByText(/SR-F-030035/)).toBeInTheDocument();
    fireEvent.click(
      within(sqlImportDialog).getByRole('button', {name: /^Continue$/i})
    );
    await waitFor(() => {
      expect(designClient.biSqlBridge).toHaveBeenCalledWith(
        'analytics',
        expect.objectContaining({
          action: 'from_sql',
          sql: 'SELECT region, SUM(amount) FROM orders GROUP BY region',
        })
      );
      expect(designClient.createBiQuestion).toHaveBeenCalled();
    });
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 3. File-picker Superset bundle import (zero raw JSON paste textarea)
    fireEvent.click(screen.getByRole('button', {name: /New BI design…/i}));
    const createDialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(createDialog).getByLabelText(/^Mode$/i));
    fireEvent.click(
      await screen.findByRole('option', {
        name: /Import Apache Superset YAML ZIP/i,
      })
    );
    const fileInput = within(createDialog).getByLabelText(/Import bundle file/i);
    const jsonBytes = new TextEncoder().encode(
      '{"datasets":[],"charts":[],"dashboards":[]}'
    );
    const mockFile = new File([jsonBytes], 'superset-export.json', {
      type: 'application/json',
    });
    fireEvent.change(fileInput, {target: {files: [mockFile]}});
    await waitFor(() => {
      expect(
        within(createDialog).getByText(/Selected: superset-export\.json/i)
      ).toBeInTheDocument();
    });
    fireEvent.click(
      within(createDialog).getByRole('button', {name: /^Continue$/i})
    );
    await waitFor(() => {
      expect(designClient.importBiSuperset).toHaveBeenCalled();
      expect(onOpen).toHaveBeenCalledWith(
        'analytics',
        expect.objectContaining({id: 'd-imp', kind: 'dashboard'})
      );
    });

    const def = biDesignerModuleDefinition();
    expect(def.id).toBe('cdeadmin.bi_designer');
  });

  it('routes BI dashboard action buttons through native-operation review (KeyValuePairsEditor) and reads live collector snapshots', async () => {
    const session = makeDashboardSession({status: 'accepted'});
    const dashWithActionAndCollector = {
      ...sampleDashboardModel(),
      cards: [
        ...sampleDashboardModel().cards,
        {
          id: 'live_pg_panel',
          tab_id: 'main',
          type: 'metric_panel',
          title: 'PG Live Throughput',
          click_behavior: 'inherit',
          layout: {x: 12, y: 0, w: 12, h: 8},
          metric_panel: {
            panel_id: 'pg_live',
            snapshot_mode: 'collector_read_only',
            collector_binding: {
              engine: 'postgresql',
              server_id: 1,
              target_id: 'db-1',
              metric_group: 'throughput',
              metric_keys: ['tps'],
              freshness_budget_seconds: 120,
            },
            columns: [
              {id: 'measure', label: 'Measure'},
              {id: 'value', label: 'Value'},
            ],
            rows: [],
          },
        },
      ],
      action_buttons: [
        {
          id: 'purge_order',
          label: 'Purge Cancelled Order',
          operation_kind: 'delete_row',
          target_endpoint_id: 'ep-pg',
          target_relation: ['public', 'orders'],
          key_columns: ['order_id'],
          parameter_bindings: [
            {
              name: 'order_id',
              column: 'order_id',
              source: 'selected_row',
              source_ref: 'order_id',
              type: 'integer',
              required: true,
            },
          ],
          approval_required: true,
        },
      ],
    };

    const client = {
      openSession: jest.fn().mockResolvedValue(session),
      getBiModel: jest.fn().mockResolvedValue({
        design: session.design,
        bi_kind: 'dashboard',
        bi: {dashboard: dashWithActionAndCollector, dashboard_notes: ''},
        outward_effects: [],
      }),
      submitBiActionReview: jest.fn().mockResolvedValue({
        operation_id: 'op-review-99',
        stage: 'awaiting_approval',
        requires_native_review: true,
        executed_immediately: false,
        destructive_warning:
          'DESTRUCTIVE WARNING: Deleting from "public"."orders" permanently removes row data.',
        sql: 'DELETE FROM "public"."orders" WHERE "order_id" = :order_id;',
      }),
      readBiCollectorPanel: jest.fn().mockResolvedValue({
        card_id: 'live_pg_panel',
        snapshot_mode: 'collector_read_only',
        collector_state: 'running',
        freshness_status: 'live',
        observed_at: '2026-11-11T15:00:00Z',
        rows: [{id: 'tps', measure: 'tps', value: 412.5}],
      }),
    };

    const Themed = withTheme(BIDesignerSurface);
    render(
      <Themed
        projectId="analytics"
        designId={session.design.id}
        kind="dashboard"
        client={client}
      />
    );

    await waitFor(() =>
      expect(
        screen.getByText(/Read-only collector metric_panel card\(s\) \(1\)/i)
      ).toBeInTheDocument()
    );

    const menuNav = screen.getByRole('navigation', {name: /BI designer menu/i});

    // 1. Live Collector Binding snapshot via Chart & Accessibility tab
    fireEvent.click(
      within(menuNav).getByRole('tab', {name: 'Chart & Accessibility'})
    );
    fireEvent.click(
      screen.getByRole('button', {name: /Live Collector Binding…/i})
    );
    const colDialog = await screen.findByRole('dialog');
    expect(
      await within(colDialog).findByText(
        /Mode: collector_read_only · Collector state: running · Freshness: live/i
      )
    ).toBeInTheDocument();
    fireEvent.click(within(colDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    // 2. BI Action Button -> native-operation review via Outward & Kiosk tab + KeyValuePairsEditor
    fireEvent.click(within(menuNav).getByRole('tab', {name: 'Outward & Kiosk'}));
    fireEvent.click(
      screen.getByRole('button', {name: /Test Action Button Native Review…/i})
    );
    const actDialog = await screen.findByRole('dialog');
    const kvGroup = within(actDialog).getByRole('group', {
      name: 'Action Prompt Values',
    });
    fireEvent.click(within(kvGroup).getByRole('button', {name: /\+ Add parameter/i}));
    let kvInputs = within(kvGroup).getAllByRole('textbox');
    fireEvent.change(kvInputs[0], {
      target: {value: 'order_id'},
    });
    kvInputs = within(kvGroup).getAllByRole('textbox');
    fireEvent.change(kvInputs[1], {
      target: {value: '101'},
    });
    fireEvent.click(
      within(actDialog).getByRole('button', {name: /Submit to Native Review/i})
    );
    await waitFor(() =>
      expect(client.submitBiActionReview).toHaveBeenCalledWith(
        'analytics',
        session.design.id,
        expect.objectContaining({
          actionButtonId: 'purge_order',
          parameterValues: {order_id: 101},
          dryRun: false,
        })
      )
    );
    expect(
      await within(actDialog).findByText(
        /Operation queued: op-review-99 · Stage: awaiting_approval/i
      )
    ).toBeInTheDocument();
    expect(
      within(actDialog).getByText(/DESTRUCTIVE WARNING:/i)
    ).toBeInTheDocument();
    fireEvent.click(within(actDialog).getByRole('button', {name: 'Close'}));
  });
});
