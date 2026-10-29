import viewer, { setupDDNDOM, metricRows, libraries } from './ddnTestRuntime';
import { mysqlDashboardFiles, mysqlFleetFiles, mysqlFleetPublication } from 'sources/cdeadmin_ui/integrations/ddn/mysqlDashboard';
import { validatePublication, bindPublication } from 'sources/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
import { mysqlTrendObservations, mysqlTrendFiles } from 'sources/cdeadmin_ui/integrations/ddn/mysqlTrends';
const sample = extra => ({
  scope: 'database',
  transaction_completed: true,
  status: 'partial',
  source_epoch: 'a',
  runtime_elapsed_seconds: 5,
  identity: {
    server_uuid: 'native'
  },
  ended_at: '2026-10-12T12:00:00Z',
  groups: {
    status: {
      status: 'available',
      scope: 'server',
      rows: [{
        variable_name: 'Questions',
        variable_value: '9007199254740993'
      }, {
        variable_name: 'Threads_connected',
        variable_value: '2'
      }]
    }
  },
  rates: {
    status: 'available',
    per_second: {
      Questions: '1.25'
    }
  },
  ...extra
});
const snapshot = extra => ({
  state: 'collecting',
  sample_age_seconds: 1,
  stale_after_seconds: 15,
  samples: [sample()],
  ...extra
});
const envelope = files => ({
  format: 'ddn-source-workspace@1',
  entry: 'dashboard.ddn',
  view: 'dashboard',
  files
});
describe('MySQL native DDN dashboards and trends', () => {
  beforeAll(setupDDNDOM);
  it('keeps native bindings stable across source order changes and removes draft telemetry', async () => {
    const draft = await validatePublication(libraries, envelope(mysqlDashboardFiles(snapshot(), 'database')), 'database', 'mysql');
    expect(draft.files['dashboard.ddn']).not.toContain('9007199254740993');
    const reordered = sample();
    reordered.groups.status.rows.reverse();
    const rebound = await bindPublication(libraries, draft, 'database', mysqlDashboardFiles(snapshot({
      samples: [reordered]
    }), 'database'), 'mysql');
    const rows = metricRows(rebound);
    expect(rows.find(row => row[2] === 'Questions: variable_value')[3]).toBe('9007199254740993');
    const missing = sample();
    missing.groups.status.rows = missing.groups.status.rows.slice(1);
    const unavailable = await bindPublication(libraries, draft, 'database', mysqlDashboardFiles(snapshot({
      samples: [missing]
    }), 'database'), 'mysql');
    const lost = metricRows(unavailable);
    expect(lost.find(row => row[2] === 'Questions: variable_value')[3]).toBe('Unavailable');
    await expect(validatePublication(libraries, draft, 'database', 'postgresql')).rejects.toThrow();
  });
  it('renders engine inventory without summing aliased server counters', async () => {
    const files = mysqlFleetFiles({
      registered_endpoints: 2,
      servers: [{
        server_id: 1,
        name: 'Alias one',
        snapshot: snapshot({
          samples: [sample({
            scope: 'server'
          })]
        }),
        databases: []
      }, {
        server_id: 2,
        name: 'Alias two',
        snapshot: snapshot({
          samples: [sample({
            scope: 'server'
          })]
        }),
        databases: []
      }]
    });
    await validatePublication(libraries, envelope(files), 'engine', 'mysql');
    const workspace = await viewer.createWorkspace(files);
    try {
      expect((await workspace.render({
        entry: 'dashboard.ddn',
        view: 'dashboard'
      })).diagnostics.filter(row => row.severity === 'error')).toEqual([]);
    } finally {
      workspace.destroy();
    }
    expect(files['dashboard.ddn']).toContain('counters are not summed');
    expect(files['dashboard.ddn']).toContain('Alias one');
    expect(files['dashboard.ddn']).toContain('Alias two');
  });
  it('keeps workload bindings tied to native identities and excludes private sample bindings', async () => {
    const native = sample();
    native.groups.workload_digests = {
      status: 'available',
      rows: [{
        schema_name: 'demo',
        digest: 'a'.repeat(64),
        sum_timer_wait: '9007199254740993',
        count_star: '7',
        sum_rows_examined: '9'
      }]
    };
    const files = mysqlDashboardFiles(snapshot({
      samples: [native]
    }), 'database');
    const clean = await validatePublication(libraries, envelope(files), 'database', 'mysql');
    expect(clean.files['dashboard.ddn']).not.toContain('9007199254740993');
    const rebound = await bindPublication(libraries, clean, 'database', files, 'mysql');
    expect(JSON.stringify(rebound.liveData)).toContain('9007199254740993');
    await expect(validatePublication(libraries, envelope(files), 'database', 'mariadb')).rejects.toThrow();
    const source = files['dashboard.ddn'].replace('73756d5f74696d65725f77616974', '71756572795f73616d706c655f74657874');
    await expect(validatePublication(libraries, envelope({
      'dashboard.ddn': source
    }), 'database', 'mysql')).rejects.toThrow();
  });
  it('publishes read-only alert findings with stable admitted bindings and suppresses stale values', async () => {
    const live = snapshot({
      alerts: {
        rules: [{
          rule: {
            id: 'ops',
            metric: 'threads_running'
          },
          state: 'firing',
          condition: 'threshold',
          evidence: {
            value: '9007199254740993',
            source: 'native',
            observed_at: 'now'
          }
        }],
        events: [{
          rule_id: 'ops',
          delivery: {
            state: 'delivered'
          }
        }]
      }
    });
    const files = mysqlDashboardFiles(live, 'database');
    const clean = await validatePublication(libraries, envelope(files), 'database', 'mysql');
    expect(clean.files['dashboard.ddn']).not.toContain('9007199254740993');
    expect(JSON.stringify((await bindPublication(libraries, clean, 'database', files, 'mysql')).liveData)).toContain('9007199254740993');
    expect(mysqlDashboardFiles({
      ...live,
      sample_age_seconds: 100
    }, 'database')['dashboard.ddn']).not.toContain('9007199254740993');
    await expect(validatePublication(libraries, envelope({
      'dashboard.ddn': files['dashboard.ddn'].replace('mysql_alert_6f7073_value', 'mysql_alert_6f7073_password')
    }), 'database', 'mysql')).rejects.toThrow();
    await expect(validatePublication(libraries, envelope(files), 'engine', 'mysql')).rejects.toThrow();
  });
  it('bounds engine publications and reports omitted scopes without parsing labels as page identities', async () => {
    const publication = mysqlFleetPublication({
      registered_endpoints: 300,
      servers: Array.from({
        length: 300
      }, (_, index) => ({
        server_id: index + 1,
        name: 'Native view dashboard_page_999 ' + 'x'.repeat(1000),
        databases: []
      }))
    });
    expect(new TextEncoder().encode(publication.files['dashboard.ddn']).length).toBeLessThanOrEqual(512 * 1024);
    expect(publication.pages).not.toContain('dashboard_page_999');
    const clean = await validatePublication(libraries, envelope(publication.files), 'engine', 'mysql');
    expect(clean.files['dashboard.ddn']).toContain('Omitted scopes');
  });
  it('keeps exact counter values, approximate chart bounds and unavailable samples distinct', async () => {
    const data = snapshot({
      samples: [sample(), sample({
        transaction_completed: false
      }), sample({
        source_epoch: null
      })]
    });
    const gauges = mysqlTrendObservations(data, 'database', 'Threads_connected');
    expect(gauges[0].numeric).toBe(2);
    expect(gauges.slice(1).every(row => row.numeric === null)).toBe(true);
    const rates = mysqlTrendObservations(data, 'database', 'Questions');
    expect(rates[0].exact).toBe('1.25');
    expect(rates[0].numeric).toBe(1.25);
    const workspace = await viewer.createWorkspace(mysqlTrendFiles(data, 'database', 'Questions'));
    try {
      expect((await workspace.render({
        entry: 'trends.ddn',
        view: 'trends'
      })).diagnostics.filter(row => row.severity === 'error')).toEqual([]);
    } finally {
      workspace.destroy();
    }
  });
});
