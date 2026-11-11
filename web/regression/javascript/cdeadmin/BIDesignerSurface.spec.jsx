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
    filters: [],
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

describe('Task-specific BI Questions & Dashboards Designer', () => {
  beforeEach(() => {
    setupDDNDOM();
    setDDNLibraryLoaderForTests(() => Promise.resolve(libraries()));
  });

  afterEach(() => {
    resetDDNLibraryLoaderForTests();
  });

  it('renders question charts via DDNViewerSurface, flags fan-out & filter values, compiles SQL and accepts cleanly', async () => {
    const session = makeQuestionSession();
    const client = {
      openSession: jest.fn().mockResolvedValue(session),
      getBiModel: jest.fn().mockResolvedValue({
        design: session.design,
        bi_kind: 'question',
        bi: {question: sampleQuestionModel(), question_notes: ''},
        outward_effects: [],
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
    expect(screen.getByText(/SBsql join fan-out warning/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Review saved filter literal\/default values/i)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: /SQL Bridge/i}));
    const sqlDialog = await screen.findByRole('dialog');
    await waitFor(() => {
      expect(client.biSqlBridge).toHaveBeenCalledWith(
        'analytics',
        session.design.id,
        expect.objectContaining({action: 'compile_sql', dialect: 'sqlite'})
      );
      expect(within(sqlDialog).getByText(/Bound parameters:/i)).toBeInTheDocument();
    });
    fireEvent.click(within(sqlDialog).getByRole('button', {name: 'Close'}));
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole('button', {name: /^Accept…$/i}));
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

  it('renders composed dashboards, warns on static metric_panel snapshots and mints narrowing kiosk tokens', async () => {
    const session = makeDashboardSession({status: 'accepted'});
    const client = {
      openSession: jest.fn().mockResolvedValue(session),
      getBiModel: jest.fn().mockResolvedValue({
        design: session.design,
        bi_kind: 'dashboard',
        bi: {dashboard: sampleDashboardModel(), dashboard_notes: ''},
        outward_effects: [],
      }),
      reviewBiOutwardEffect: jest.fn().mockResolvedValue({
        effect: {
          id: 'pub-01',
          effect_kind: 'dashboard_server',
          enabled: true,
        },
        exposure_diff: {was_enabled: false, now_enabled: true},
      }),
      mintBiDeviceToken: jest.fn().mockResolvedValue({
        device_token: 'srbikiosk.v1.signedtoken',
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

    fireEvent.click(screen.getByRole('button', {name: /Outward Effects/i}));
    const outwardDialog = await screen.findByRole('dialog');
    const effectSelect = within(outwardDialog).getByLabelText(/^Outward Effect$/i);
    fireEvent.mouseDown(effectSelect);
    fireEvent.click(
      await screen.findByRole('option', {
        name: /Remote Dashboard Server Publication/i,
      })
    );
    fireEvent.click(
      within(outwardDialog).getByRole('button', {
        name: /Review & Apply Switch/i,
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
      screen.getByRole('button', {name: /Mint Narrowing Device Token/i})
    );
    await waitFor(() => {
      expect(client.mintBiDeviceToken).toHaveBeenCalledWith(
        'analytics',
        session.design.id,
        expect.objectContaining({publicationId: 'pub-01'})
      );
      expect(screen.getByText(/srbikiosk\.v1\.signedtoken/)).toBeInTheDocument();
    });
  });

  it('lists questions and dashboards in BIDesignsNavigator and imports Superset bundles into Draft', async () => {
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
        {
          id: 'd-1',
          kind: 'dashboard',
          title: 'Revenue Dashboard',
          head_version: 2,
        },
      ]),
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
    render(
      <ThemedNav
        designClient={designClient}
        projectClient={projectClient}
        onOpenDesign={onOpen}
      />
    );

    await waitFor(() => {
      expect(
        screen.getByText(/Orders by Region \(question\)/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Revenue Dashboard \(dashboard\)/i)
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/SR-F-010025/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: /New BI design…/i}));
    const createDialog = await screen.findByRole('dialog');
    expect(within(createDialog).getByText(/SR-F-010026/)).toBeInTheDocument();

    const modeSelect = within(createDialog).getByLabelText(/^Mode$/i);
    fireEvent.mouseDown(modeSelect);
    fireEvent.click(
      await screen.findByRole('option', {
        name: /Import Apache Superset YAML ZIP/i,
      })
    );
    fireEvent.change(
      within(createDialog).getByLabelText(/Bundle JSON or Base64 Archive/i),
      {target: {value: '{"datasets":[],"charts":[],"dashboards":[]}'}}
    );
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
});
