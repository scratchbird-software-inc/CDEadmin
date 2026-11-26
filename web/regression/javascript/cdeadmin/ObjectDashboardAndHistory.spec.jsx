/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo} from 'react';
import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';
import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import '@testing-library/jest-dom';

import {withTheme} from '../fake_theme';
import {PgAdminProvider} from '../../../pgadmin/static/js/PgAdminProvider';
import {
  ProjectShellProvider,
  ProjectTopMenuBar,
  ProjectWorkbenchFrame,
  ProjectTopMenuRegistry,
  TActionsRegistry,
} from '../../../pgadmin/static/js/cdeadmin_ui';
import {
  CatalogPageCoordinator,
  DataNavigatorWorkArea,
  buildNavigatorSelectionConfig,
  catalogNodeIdentityKey,
} from '../../../pgadmin/static/js/BrowserComponent';

function createFakePgAdmin() {
  const listeners = new Map();
  const itemsById = new Map();
  let selectedItem = null;

  const events = {
    on(name, cb) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(cb);
    },
    off(name, cb) {
      listeners.get(name)?.delete(cb);
    },
    trigger(name, ...args) {
      Array.from(listeners.get(name) || []).forEach((cb) => cb(...args));
    },
  };

  return {
    Browser: {
      Events: events,
      Nodes: {
        server_group: {hasProperties: true},
        server: {hasProperties: true, hasStatistics: true, callbacks: {}},
        cde_database_target: {hasProperties: true, hasStatistics: true},
        cde_resource: {hasProperties: true, hasSQL: true, hasStatistics: true},
      },
      tree: {
        selected: () => selectedItem,
        itemData: (item) => item?._metadata?.data || null,
        select: jest.fn(async (item) => {
          selectedItem = item;
        }),
        refresh: jest.fn(),
        hasParent: () => false,
        getTreeNodeHierarchy: () => ({server_group: {_id: 1}}),
      },
    },
    __registerNode(id, data) {
      const item = {id, _metadata: {data}};
      itemsById.set(id, item);
      return item;
    },
    __selectInTree(item) {
      selectedItem = item;
      events.trigger('pgadmin-browser:tree:selected', item, item?._metadata?.data);
    },
  };
}

function DashboardShellHarness({pgAdmin}) {
  const actionsRegistry = useMemo(() => new TActionsRegistry(), []);
  const menuRegistry = useMemo(() => new ProjectTopMenuRegistry(), []);

  const applicationFactory = ({appId, instanceId, options = {}}) => {
    if (appId !== 'data-navigator') return null;
    const hasBoundNode = Boolean(options.boundNodeData && options.boundNodeData._type);
    const isUnboundNavigator =
      options.isUnboundNavigator !== undefined ? Boolean(options.isUnboundNavigator) : !hasBoundNode;
    const boundItem = isUnboundNavigator ? null : options.boundNodeItem || null;
    const boundData = isUnboundNavigator ? null : options.boundNodeData || null;
    const navConfig = buildNavigatorSelectionConfig(
      pgAdmin,
      instanceId,
      boundItem,
      boundData,
      options.activeView || null
    );
    return {
      title: isUnboundNavigator ? 'Data Navigator' : options.title || navConfig.title,
      supportsLeftDrawer: true,
      supportsRightDrawer: true,
      supportsTabbedIconBar: true,
      useUnderTabs: navConfig.useUnderTabs,
      selectedUnderTabId: navConfig.selectedUnderTabId,
      actions: navConfig.actions,
      menus: navConfig.menus,
      ribbonTabs: navConfig.ribbonTabs,
      meta: {
        isUnboundNavigator,
        catalogNodeKey: isUnboundNavigator ? null : catalogNodeIdentityKey(boundData),
        boundNodeItem: boundItem,
        boundNodeData: boundData,
        activeView: navConfig.activeView,
      },
      renderLeftDrawer: () => <div>Tree</div>,
      renderWorkArea: () => <DataNavigatorWorkArea instanceId={instanceId} />,
      renderRightDrawer: () => <div>Inspector</div>,
    };
  };

  return (
    <PgAdminProvider value={pgAdmin}>
      <ProjectShellProvider
        username="dba@scratchrobin.org"
        actionsRegistry={actionsRegistry}
        menuRegistry={menuRegistry}
        applicationFactory={applicationFactory}
        fetchImpl={global.fetch}
      >
        <CatalogPageCoordinator />
        <ProjectTopMenuBar />
        <div style={{height: 760}}>
          <ProjectWorkbenchFrame />
        </div>
      </ProjectShellProvider>
    </PgAdminProvider>
  );
}

describe('ObjectDashboardSurface, Historic Vault Windows, Deep Stats & Rich Properties', () => {
  const originalFetch = global.fetch;
  let networkMock = null;

  beforeEach(() => {
    networkMock = new MockAdapter(axios);
    networkMock.onAny().reply(200, {data: {}});
  });

  afterEach(() => {
    networkMock?.restore();
    global.fetch = originalFetch;
  });

  it('renders Dashboard by default with comment, KPIs, SVG historic graphs, storage bars, churn-protected Deep Stats, and switches to comprehensive Properties via Area 3b sub-tabs', async () => {
    const fetchCalls = [];
    global.fetch = jest.fn(async (url, opts = {}) => {
      const urlStr = String(url);
      fetchCalls.push({url: urlStr, method: opts.method || 'GET'});

      if (urlStr.includes('/cdeadmin/api/object_dashboard/snapshot')) {
        const winMatch = urlStr.match(/window=([^&]+)/);
        const win = winMatch ? winMatch[1] : '1h';
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object_identity: {
              object_kind: 'table',
              object_key: 'table:7:sales:public.orders',
              title: 'orders',
              subtitle: 'PostgreSQL · Table',
              engine_id: 'postgresql',
              engine_label: 'PostgreSQL',
              connected: true,
              verified_version: 'PostgreSQL 17.2',
            },
            comment: {
              text: 'Primary customer order ledger with fulfillment tracking.',
              supported: true,
            },
            kpis: [
              {
                id: 'total_size',
                label: 'Total Relation Size',
                value: 10485760,
                formatted: '10.00 MiB',
                unit: 'bytes',
                subtext: 'Heap 7.50 MiB · Indexes 2.50 MiB',
                status: 'ok',
              },
              {
                id: 'est_rows',
                label: 'Estimated Live Rows',
                value: 48200,
                formatted: '48,200',
                unit: 'count',
                subtext: '420 dead tuples (0.9%)',
                capacity_pct: 0.9,
                status: 'ok',
              },
            ],
            storage_bars: [
              {
                id: 'pg_table_composition',
                title: 'Relation Storage Composition',
                total_bytes: 10485760,
                total_formatted: '10.00 MiB',
                segments: [
                  {id: 'heap', label: 'Table Heap', bytes: 7864320, pct: 75, formatted: '7.50 MiB', tone: 'primary'},
                  {id: 'indexes', label: 'Indexes', bytes: 2621440, pct: 25, formatted: '2.50 MiB', tone: 'info'},
                ],
              },
            ],
            rankings: [],
            history: {
              window: win,
              resolution: win === '30d' ? '5m' : 'raw',
              retention_policy: {raw_hours: 24, rollup_5m_days: 30, rollup_1h_days: 365},
              series: [
                {
                  series_id: 's1',
                  metric_key: 'rows.estimated_live',
                  label: 'Estimated Live Rows',
                  group: 'rows',
                  kind: 'gauge',
                  unit: 'count',
                  resolution: win === '30d' ? '5m' : 'raw',
                  latest_value: 48200,
                  max_value: 48500,
                  sample_count: 2,
                  points: [
                    {ts: 1795490000000, value: 47900, min: 47900, max: 47900},
                    {ts: 1795493600000, value: 48200, min: 48100, max: 48500},
                  ],
                },
              ],
            },
            ddn: {ddn_text: '', scene: null},
            deep_stats: {
              available_actions: [{id: 'exact_row_count', label: 'Exact Row Count'}],
              cached: null,
            },
            reports: [
              {
                id: 'index_usage',
                title: 'Index Scan Activity & Unused Index Check',
                description: 'Zero-scan indexes check',
                columns: ['index_name', 'scans', 'size'],
                rows: [{index_name: 'orders_pkey', scans: 19420, size: '2.50 MiB'}],
              },
            ],
            customization: {
              show_comment_banner: true,
              show_kpi_strip: true,
              show_historic_charts: true,
              show_storage_and_rankings: true,
              show_deep_stats: true,
              show_diagnostic_reports: true,
              default_window: '1h',
            },
          }),
        };
      }

      if (urlStr.includes('/cdeadmin/api/object_dashboard/deep_refresh')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            deep_stats: {
              available_actions: [{id: 'exact_row_count', label: 'Exact Row Count'}],
              cached: {
                computed_at: '2026-11-24T05:10:00Z',
                stats: {
                  exact_row_count: 48219,
                  metrics: [{label: 'Exact Row Count (COUNT(*))', value: '48,219'}],
                  tables: [],
                },
              },
            },
            history: {series: []},
          }),
        };
      }

      if (urlStr.includes('/cdeadmin/api/object_dashboard/properties')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object_identity: {
              object_kind: 'table',
              title: 'orders',
              engine_id: 'postgresql',
              engine_label: 'PostgreSQL',
            },
            comment: {
              text: 'Primary customer order ledger with fulfillment tracking.',
            },
            summary_attributes: [
              {
                key: 'relpersistence',
                label: 'Persistence',
                value: 'Permanent (WAL-logged)',
                category: 'Storage',
                is_system: false,
                is_empty: false,
              },
            ],
            sections: [
              {
                id: 'columns',
                title: 'Columns',
                columns: ['column_name', 'data_type', 'comment'],
                rows: [
                  {column_name: 'order_id', data_type: 'bigint', comment: 'Surrogate key'},
                ],
              },
            ],
            ddl: {
              available: true,
              sql: 'CREATE TABLE public.orders (order_id BIGINT PRIMARY KEY);',
              source: 'pg_catalog',
            },
            dependencies: [],
            dependents: [],
            customization: {
              show_empty_attributes: false,
              show_system_attributes: true,
              show_native_registration_panel: true,
              default_section_filter: 'all',
            },
          }),
        };
      }

      return {ok: true, status: 200, json: async () => ({})};
    });

    const pgAdmin = createFakePgAdmin();
    const ordersTableItem = pgAdmin.__registerNode('tbl-orders', {
      _type: 'cde_resource',
      _id: 'table:public.orders',
      cde_resource_id: 'table:public.orders',
      cde_resource_kind: 'table',
      cde_engine_id: 'postgresql',
      server_id: 7,
      cde_database_target_id: 'sales',
      schema: 'public',
      label: 'orders',
      _label: 'orders',
      connected: true,
    });

    const Component = withTheme(DashboardShellHarness);
    render(<Component pgAdmin={pgAdmin} />);

    await act(async () => {
      pgAdmin.__selectInTree(ordersTableItem);
    });

    // 1. Default view is Dashboard under "table: orders", with Dashboard | Properties sub-tabs in Area 3b
    const underTabs = Array.from(
      document.querySelectorAll('[data-cdeadmin-qa-key="notebookbar-undertabs"] [role="tab"]')
    );
    expect(underTabs.map((t) => t.textContent)).toEqual(['Dashboard', 'Properties']);
    expect(underTabs[0]).toHaveAttribute('aria-selected', 'true');

    await waitFor(() => {
      expect(
        screen.getByText('Primary customer order ledger with fulfillment tracking.')
      ).toBeInTheDocument();
    });
    expect(screen.getAllByText('10.00 MiB').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Relation Storage Composition')).toBeInTheDocument();
    expect(screen.getByText('Row Cardinality & Dead Tuples')).toBeInTheDocument();
    expect(screen.getByText('Index Scan Activity & Unused Index Check')).toBeInTheDocument();

    // Verify zero involuntary deep_refresh calls occurred on initial selection!
    expect(fetchCalls.some((c) => c.url.includes('deep_refresh'))).toBe(false);

    // 2. Click "30 Days" on the historic window ribbon control -> queries 30d 5m rollups!
    const seg30d = document.querySelector('.sr-island-3b [aria-label="30 Days"]');
    expect(seg30d).toBeTruthy();
    await act(async () => {
      fireEvent.click(seg30d);
    });
    await waitFor(() => {
      expect(fetchCalls.some((c) => c.url.includes('window=30d'))).toBe(true);
    });

    // 3. Click "Compute Deep Stats" ribbon icon -> explicitly triggers POST /deep_refresh!
    const deepBtn = document.querySelector(
      '.sr-island-3b .snb-panel [aria-label="Compute Deep Stats"]'
    );
    await act(async () => {
      fireEvent.click(deepBtn);
    });
    await waitFor(() => {
      expect(screen.getByText('48,219')).toBeInTheDocument();
    });
    expect(screen.getByText(/Last computed: 2026-11-24T05:10:00Z/)).toBeInTheDocument();

    // 4. Click "Customize Dashboard" ribbon icon -> opens customization & retention modal!
    const custBtn = document.querySelector(
      '.sr-island-3b .snb-panel [aria-label="Customize Dashboard"]'
    );
    fireEvent.click(custBtn);
    expect(
      await screen.findByText('Customize Dashboard & Historic Metrics')
    ).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(
        document.querySelector('[data-cdeadmin-qa-key="save-dashboard-customization"]')
      );
    });
    expect(fetchCalls.some((c) => c.url.includes('/preferences') && c.method === 'POST')).toBe(
      true
    );

    // 5. Switch to "Properties" sub-tab in Area 3b -> shows comprehensive attributes, Columns, and DDL!
    await act(async () => {
      fireEvent.click(underTabs[1]);
    });
    await waitFor(() => {
      expect(screen.getByText('Comprehensive Object Attributes')).toBeInTheDocument();
    });
    expect(screen.getByText('Permanent (WAL-logged)')).toBeInTheDocument();
    expect(screen.getByText('DDL / SQL Definition')).toBeInTheDocument();
    expect(
      screen.getByText(/CREATE TABLE public\.orders \(order_id BIGINT PRIMARY KEY\);/)
    ).toBeInTheDocument();

    const island3e = document.querySelector('[data-area-part="3e"]');
    expect(within(island3e).queryByRole('tablist')).not.toBeInTheDocument();
  });
});
