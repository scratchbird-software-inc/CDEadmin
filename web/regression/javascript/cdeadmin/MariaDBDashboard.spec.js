import viewer, { setupDDNDOM, libraries } from './ddnTestRuntime';
import { mysqlDashboardFiles, mysqlFleetFiles } from 'sources/cdeadmin_ui/integrations/ddn/mysqlDashboard';
import { validatePublication, bindPublication } from 'sources/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
import { mysqlTrendObservations, mysqlTrendFiles } from 'sources/cdeadmin_ui/integrations/ddn/mysqlTrends';
const sample = extra => ({
  scope: 'database',
  transaction_completed: true,
  status: 'partial',
  source_epoch: 'a',
  runtime_elapsed_seconds: 5,
  identity: {
    server_uid: 'maria-native'
  },
  ended_at: '2026-10-12T12:00:00Z',
  groups: {
    status: {
      status: 'available',
      scope: 'server',
      rows: [{
        variable_name: 'Questions',
        native_variable_name: 'QUESTIONS',
        variable_value: '9007199254740993'
      }, {
        variable_name: 'Threads_connected',
        native_variable_name: 'THREADS_CONNECTED',
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
describe('MariaDB DDN native bindings', () => {
  beforeAll(setupDDNDOM);
  it('preserves MariaDB native labels and exact values across publication without retaining telemetry', async () => {
    const files = mysqlDashboardFiles(snapshot(), 'database', 'mariadb');
    const draft = await validatePublication(libraries, envelope(files), 'database', 'mariadb');
    expect(draft.files['dashboard.ddn']).not.toContain('9007199254740993');
    const rebound = await bindPublication(libraries, draft, 'database', files, 'mariadb');
    expect(JSON.stringify(rebound.liveData)).toContain('9007199254740993');
    expect(JSON.stringify(rebound.liveData)).toContain('QUESTIONS');
    await expect(validatePublication(libraries, draft, 'database', 'mysql')).rejects.toThrow();
    await expect(validatePublication(libraries, draft, 'database', 'firebird')).rejects.toThrow();
    await expect(validatePublication(libraries, draft, 'engine', 'mariadb')).rejects.toThrow();
  });
  it('admits native replication fields and refuses MySQL-only options', async () => {
    const native = sample({
      groups: {
        replication: {
          status: 'available',
          scope: 'server',
          rows: [{
            channel_name: 'maria-channel',
            slave_io_running: 'Yes',
            slave_sql_running: 'Yes',
            last_io_errno: '0',
            last_sql_errno: '0',
            seconds_behind_master: null,
            gtid_io_pos: '0-1-2'
          }]
        }
      }
    });
    await validatePublication(libraries, envelope(mysqlDashboardFiles(snapshot({
      samples: [native]
    }), 'database', 'mariadb')), 'database', 'mariadb');
    native.groups.settings = {
      status: 'available',
      rows: [{
        super_read_only: '1'
      }]
    };
    await expect(validatePublication(libraries, envelope(mysqlDashboardFiles(snapshot({
      samples: [native]
    }), 'database', 'mariadb')), 'database', 'mariadb')).rejects.toThrow();
  });
  it('uses native UID and source epoch for trend continuity and native engine modules', async () => {
    const data = snapshot({
      samples: [sample(), sample({
        identity: {
          server_uid: 'replacement'
        }
      })]
    });
    const points = mysqlTrendObservations(data, 'database', 'Threads_connected', 120, 'mariadb');
    expect(points[0].numeric).toBe(2);
    expect(points[0].epoch).not.toBe(points[1].epoch);
    const files = mysqlTrendFiles(data, 'database', 'Questions', 120, 'mariadb');
    expect(files['trends.ddn']).toContain('scratchrobin.mariadb.trends');
    const workspace = await viewer.createWorkspace(files);
    try {
      expect((await workspace.render({
        entry: 'trends.ddn',
        view: 'trends'
      })).diagnostics.filter(row => row.severity === 'error')).toEqual([]);
    } finally {
      workspace.destroy();
    }
  });
  it('validates owner inventory against MariaDB namespace and native identity bindings', async () => {
    const files = mysqlFleetFiles({
      registered_endpoints: 1,
      servers: [{
        server_id: 7,
        name: 'MariaDB',
        databases: [],
        snapshot: snapshot({
          samples: [sample({
            scope: 'server'
          })]
        })
      }]
    }, 'mariadb');
    await validatePublication(libraries, envelope(files), 'engine', 'mariadb');
    expect(files['dashboard.ddn']).toContain('maria-native');
    await expect(validatePublication(libraries, envelope(files), 'engine', 'mysql')).rejects.toThrow();
  });
});
