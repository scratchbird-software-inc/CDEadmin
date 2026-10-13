import viewer from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {mysqlDashboardFiles, mysqlFleetFiles} from 'sources/cdeadmin_ui/integrations/ddn/mysqlDashboard';
import {validatePublication, bindPublication} from 'sources/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
import {mysqlTrendObservations, mysqlTrendFiles} from 'sources/cdeadmin_ui/integrations/ddn/mysqlTrends';

const sample = extra => ({scope: 'database', transaction_completed: true, status: 'partial', source_epoch: 'a',
  runtime_elapsed_seconds: 5, identity: {server_uid: 'maria-native'}, ended_at: '2026-10-12T12:00:00Z',
  groups: {status: {status: 'available', scope: 'server', rows: [
    {variable_name: 'Questions', native_variable_name: 'QUESTIONS', variable_value: '9007199254740993'},
    {variable_name: 'Threads_connected', native_variable_name: 'THREADS_CONNECTED', variable_value: '2'},
  ]}}, rates: {status: 'available', per_second: {Questions: '1.25'}}, ...extra});
const snapshot = extra => ({state: 'collecting', sample_age_seconds: 1, stale_after_seconds: 15, samples: [sample()], ...extra});
const envelope = files => ({format: 'ddn-workspace@1', entry: 'dashboard.ddn', view: 'dashboard', files});

describe('MariaDB DDN native bindings', () => {
  beforeAll(() => viewer.setTextProvider((text, size) => ({width: String(text).length * size * 0.6,
    ascent: size * 0.8, descent: size * 0.2}), 'maria-monitor-test'));
  afterAll(() => viewer.setTextProvider(null));
  it('preserves MariaDB native labels and exact values across publication without retaining telemetry', () => {
    const files = mysqlDashboardFiles(snapshot(), 'database', 'mariadb');
    const draft = validatePublication(viewer, envelope(files), 'database', 'mariadb');
    expect(draft.files['dashboard.ddn']).not.toContain('9007199254740993');
    const rebound = bindPublication(viewer, draft, 'database', files, 'mariadb');
    expect(rebound.files['dashboard.ddn']).toContain('9007199254740993');
    expect(rebound.files['dashboard.ddn']).toContain('QUESTIONS');
    expect(() => validatePublication(viewer, draft, 'database', 'mysql')).toThrow();
    expect(() => validatePublication(viewer, draft, 'database', 'firebird')).toThrow();
    expect(() => validatePublication(viewer, draft, 'engine', 'mariadb')).toThrow();
  });
  it('admits native replication fields and refuses MySQL-only options', () => {
    const native = sample({groups: {replication: {status: 'available', scope: 'server', rows: [{
      channel_name: 'maria-channel', slave_io_running: 'Yes', slave_sql_running: 'Yes',
      last_io_errno: '0', last_sql_errno: '0', seconds_behind_master: null, gtid_io_pos: '0-1-2',
    }]}}});
    validatePublication(viewer, envelope(mysqlDashboardFiles(snapshot({samples: [native]}), 'database', 'mariadb')), 'database', 'mariadb');
    native.groups.settings = {status: 'available', rows: [{super_read_only: '1'}]};
    expect(() => validatePublication(viewer, envelope(mysqlDashboardFiles(snapshot({samples: [native]}), 'database', 'mariadb')), 'database', 'mariadb')).toThrow();
  });
  it('uses native UID and source epoch for trend continuity and native engine modules', () => {
    const data = snapshot({samples: [sample(), sample({identity: {server_uid: 'replacement'}})]});
    const points = mysqlTrendObservations(data, 'database', 'Threads_connected', 120, 'mariadb');
    expect(points[0].numeric).toBe(2);
    expect(points[0].epoch).not.toBe(points[1].epoch);
    const files = mysqlTrendFiles(data, 'database', 'Questions', 120, 'mariadb');
    expect(files['trends.ddn']).toContain('scratchrobin.mariadb.trends');
    const workspace = viewer.createWorkspace(files);
    try {expect(workspace.renderSync({entry: 'trends.ddn', view: 'trends'}).diagnostics.filter(row => row.severity === 'error')).toEqual([]);}
    finally {workspace.destroy();}
  });
  it('validates owner inventory against MariaDB namespace and native identity bindings', () => {
    const files = mysqlFleetFiles({registered_endpoints: 1, servers: [{server_id: 7, name: 'MariaDB',
      databases: [], snapshot: snapshot({samples: [sample({scope: 'server'})]})}]}, 'mariadb');
    validatePublication(viewer, envelope(files), 'engine', 'mariadb');
    expect(files['dashboard.ddn']).toContain('maria-native');
    expect(() => validatePublication(viewer, envelope(files), 'engine', 'mysql')).toThrow();
  });
});
