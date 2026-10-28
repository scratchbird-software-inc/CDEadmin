import viewer, { setupDDNDOM, metricRows, libraries } from './ddnTestRuntime';
import { firebirdDashboardFiles, firebirdFleetFiles } from 'sources/cdeadmin_ui/integrations/ddn/firebirdDashboard';
import { validatePublication, bindPublication } from 'sources/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
describe('Firebird native dashboard DDN bindings', () => {
  beforeAll(setupDDNDOM);
  const sample = {
    status: 'available',
    scope: 'database',
    coverage: 'visible-to-collector',
    groups: {
      database: {
        status: 'available',
        values: {
          database_name: 'db " } view injected {}',
          page_size: '8192'
        }
      },
      io: {
        status: 'available',
        values: {
          page_reads: '9007199254740993'
        }
      }
    },
    derived: {
      allocated_bytes: '9007199254740993000'
    }
  };
  it.each(['database', 'server'])('renders actual DDN panels for %s without editor dependencies', async scope => {
    const files = firebirdDashboardFiles({
      state: 'collecting',
      sample_age_seconds: 1,
      stale_after_seconds: 15,
      samples: [sample]
    }, 'Native dashboard', scope);
    const workspace = await viewer.createWorkspace(files);
    try {
      const rendered = await workspace.render({
        entry: 'dashboard.ddn',
        view: 'dashboard'
      });
      expect(rendered.svg).toContain('<svg');
      expect(rendered.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
      if (scope === 'database') {
        expect(rendered.svg).toContain('9007199254740993');
        expect(rendered.svg).toContain('visible-to-collector');
      } else expect(rendered.svg).toContain('Service manager');
    } finally {
      workspace.destroy();
    }
  });
  it('does not present an earlier successful value as current after failure', () => {
    const files = firebirdDashboardFiles({
      samples: [sample, {
        status: 'unavailable'
      }]
    });
    expect(files['dashboard.ddn']).not.toContain('9007199254740993');
    expect(files['dashboard.ddn']).toContain('Unavailable');
  });
  it('renders a native fleet with isolated endpoint registrations and no invented metrics', async () => {
    const files = firebirdFleetFiles({
      registered_endpoints: 2,
      status_counts: {
        reachable: 1,
        unknown: 1
      },
      servers: [{
        server_id: 1,
        name: 'Same name',
        status: 'reachable',
        version: '5.0',
        known_databases: 2,
        monitored_databases: 1
      }, {
        server_id: 2,
        name: 'Same name',
        status: 'unknown'
      }]
    });
    const workspace = await viewer.createWorkspace(files);
    try {
      const rendered = await workspace.render({
        entry: 'dashboard.ddn',
        view: 'dashboard'
      });
      expect(rendered.svg).toContain('Firebird engine dashboard');
      expect(rendered.svg).toContain('Unavailable');
      expect(rendered.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
    } finally {
      workspace.destroy();
    }
  });
  it('keeps published endpoint/database bindings stable across reordering and removal', async () => {
    const database = (target_id, value) => ({
      target_id,
      name: 'Same database name',
      status: 'reachable',
      metrics: {
        allocated_bytes: value
      }
    });
    const server = (server_id, value) => ({
      server_id,
      name: 'Same server name',
      status: 'reachable',
      databases: [database('target-' + server_id, value)]
    });
    const original = {
      registered_endpoints: 2,
      servers: [server(7, '700'), server(8, '800')]
    };
    const files = firebirdFleetFiles(original);
    const clean = await validatePublication(libraries, {
      format: 'ddn-source-workspace@1',
      entry: 'dashboard.ddn',
      view: 'dashboard',
      files
    }, 'engine');
    const rebound = await bindPublication(libraries, clean, 'engine', firebirdFleetFiles({
      ...original,
      servers: [server(8, '801'), server(7, '701')]
    }));
    const rows = metricRows;
    const values = new Map(rows(rebound).map(row => [row[0], row[3]]));
    expect(values.get('fleetdb_7_7461726765742d37_3')).toBe('701');
    expect(values.get('fleetdb_8_7461726765742d38_3')).toBe('801');
    const removed = await bindPublication(libraries, clean, 'engine', firebirdFleetFiles({
      registered_endpoints: 1,
      servers: [server(8, '802')]
    }));
    expect(new Map(rows(removed).map(row => [row[0], row[3]])).get('fleetdb_7_7461726765742d37_3')).toBe('Unavailable');
    expect(rows(clean).every(row => row[3] === 'Unavailable')).toBe(true);
  });
  it('publishes registered database detail panels and validates every generated page', async () => {
    const snapshot = {
      databases: Array.from({
        length: 15
      }, (_, index) => ({
        target_id: 'db-' + index,
        name: 'DB ' + index,
        status: 'unknown',
        metrics: {}
      }))
    };
    const files = firebirdDashboardFiles(snapshot, 'Registered databases', 'server');
    expect(files['dashboard.ddn']).toContain('view "dashboard_page_2"');
    const clean = await validatePublication(libraries, {
      format: 'ddn-source-workspace@1',
      entry: 'dashboard.ddn',
      view: 'dashboard',
      files
    }, 'server');
    const ws = await viewer.createWorkspace(clean.files);
    try {
      for (const entry of ws.entries()) for (const view of entry.views) expect((await ws.validate(entry.file, view.id)).outcome).toBe('valid');
    } finally {
      ws.destroy();
    }
  });
});
