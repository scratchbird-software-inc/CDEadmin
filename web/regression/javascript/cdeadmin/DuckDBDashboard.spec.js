import viewer, { setupDDNDOM, libraries } from './ddnTestRuntime';
import { duckdbDashboardFiles, duckdbFleetFiles, duckdbCurrentSample } from 'sources/cdeadmin_ui/integrations/ddn/duckdbDashboard';
import { validatePublication, bindPublication } from 'sources/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
const sample = extra => ({
  scope: 'database',
  status: 'available',
  sample_id: 'native-one',
  transaction_refresh: {
    status: 'completed'
  },
  ended_at: '2026-10-13T12:00:00Z',
  identity: {
    database_name: 'owned',
    target_id: 'file-one'
  },
  groups: {
    storage: {
      status: 'available',
      rows: [{
        database_name: 'owned',
        database_size: '1.0 GiB',
        used_blocks: '9007199254740993'
      }]
    },
    database: {
      status: 'available',
      rows: [{
        read_only: false,
        encrypted: false
      }]
    },
    extensions: {
      status: 'available',
      rows: [{
        available: 50,
        installed: 5,
        loaded: 2
      }]
    }
  },
  ...extra
});
const snapshot = extra => ({
  state: 'collecting',
  sample_age_seconds: 1,
  stale_after_seconds: 15,
  heartbeat: {
    status: 'observed'
  },
  samples: [sample()],
  ...extra
});
const envelope = files => ({
  format: 'ddn-source-workspace@1',
  entry: 'dashboard.ddn',
  view: 'dashboard',
  files
});
describe('DuckDB public DDN dashboards', () => {
  beforeAll(setupDDNDOM);
  it('binds only completed, current native file refreshes', async () => {
    expect(duckdbCurrentSample(snapshot())).toBeTruthy();
    expect(duckdbCurrentSample(snapshot({
      sample_age_seconds: 100
    }))).toBeNull();
    expect(duckdbCurrentSample(snapshot({
      samples: [sample({
        transaction_refresh: {
          status: 'failed'
        }
      })]
    }))).toBeNull();
    const files = duckdbDashboardFiles(snapshot(), 'database');
    const draft = await validatePublication(libraries, envelope(files), 'database', 'duckdb');
    expect(draft.files['dashboard.ddn']).not.toContain('9007199254740993');
    const rebound = await bindPublication(libraries, draft, 'database', files, 'duckdb');
    expect(JSON.stringify(rebound.liveData)).toContain('9007199254740993');
    const workspace = await viewer.createWorkspace(rebound.files);
    try {
      expect((await workspace.render({
        entry: 'dashboard.ddn',
        view: 'dashboard'
      })).diagnostics.filter(row => row.severity === 'error')).toEqual([]);
    } finally {
      workspace.destroy();
    }
    await expect(validatePublication(libraries, draft, 'database', 'mysql')).rejects.toThrow();
  });
  it('shows registered files without inventing remote server counters', async () => {
    const server = duckdbDashboardFiles({
      state: 'aggregate',
      databases: [{
        snapshot: {
          state: 'collecting'
        }
      }]
    }, 'server');
    await validatePublication(libraries, envelope(server), 'server', 'duckdb');
    const fleet = duckdbFleetFiles({
      registered_endpoints: 1,
      servers: [{
        server_id: 8,
        name: 'Local endpoint',
        snapshot: {
          state: 'aggregate'
        },
        databases: [{
          target_id: 'file-one',
          name: 'owned.duckdb',
          snapshot: snapshot()
        }]
      }]
    });
    await validatePublication(libraries, envelope(fleet), 'engine', 'duckdb');
    expect(fleet['dashboard.ddn']).toContain('owned.duckdb');
    expect(fleet['dashboard.ddn']).toContain('aliases are not deduplicated');
  });
});
