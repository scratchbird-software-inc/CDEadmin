import viewer, { setupDDNDOM, libraries } from './ddnTestRuntime';
import { sqliteDashboardFiles, sqliteFleetFiles, sqliteCurrentSample } from 'sources/cdeadmin_ui/integrations/ddn/sqliteDashboard';
import { validatePublication, bindPublication } from 'sources/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
const sample = extra => ({
  scope: 'database',
  status: 'available',
  sample_id: 'native-one',
  transaction_refresh: {
    status: 'completed'
  },
  ended_at: '2026-10-14T12:00:00Z',
  identity: {
    database_name: 'owned.sqlite',
    target_id: 'file-one'
  },
  groups: {
    storage: {
      status: 'available',
      rows: [{
        page_size_bytes: 4096,
        page_count: '9007199254740993',
        freelist_pages: 2
      }]
    },
    database: {
      status: 'available',
      rows: [{
        journal_mode: 'wal'
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
describe('SQLite public DDN dashboards', () => {
  beforeAll(setupDDNDOM);
  it('binds only completed, current native file refreshes', async () => {
    expect(sqliteCurrentSample(snapshot())).toBeTruthy();
    expect(sqliteCurrentSample(snapshot({
      sample_age_seconds: 100
    }))).toBeNull();
    expect(sqliteCurrentSample(snapshot({
      samples: [sample({
        transaction_refresh: {
          status: 'failed'
        }
      })]
    }))).toBeNull();
    const files = sqliteDashboardFiles(snapshot(), 'database');
    const draft = await validatePublication(libraries, envelope(files), 'database', 'sqlite');
    expect(draft.files['dashboard.ddn']).not.toContain('9007199254740993');
    const rebound = await bindPublication(libraries, draft, 'database', files, 'sqlite');
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
    await expect(validatePublication(libraries, draft, 'database', 'duckdb')).rejects.toThrow();
  });
  it('lists registered files without inventing server metrics', async () => {
    const server = sqliteDashboardFiles({
      state: 'aggregate',
      databases: [{
        snapshot: {
          state: 'collecting'
        }
      }]
    }, 'server');
    await validatePublication(libraries, envelope(server), 'server', 'sqlite');
    const fleet = sqliteFleetFiles({
      registered_endpoints: 1,
      servers: [{
        server_id: 8,
        name: 'Local endpoint',
        snapshot: {
          state: 'aggregate'
        },
        databases: [{
          target_id: 'file-one',
          name: 'owned.sqlite',
          snapshot: snapshot()
        }]
      }]
    });
    await validatePublication(libraries, envelope(fleet), 'engine', 'sqlite');
    expect(fleet['dashboard.ddn']).toContain('owned.sqlite');
    expect(fleet['dashboard.ddn']).toContain('aliases are not deduplicated');
  });
});
