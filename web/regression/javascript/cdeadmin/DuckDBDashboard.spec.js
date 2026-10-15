import viewer from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {duckdbDashboardFiles, duckdbFleetFiles, duckdbCurrentSample} from 'sources/cdeadmin_ui/integrations/ddn/duckdbDashboard';
import {validatePublication, bindPublication} from 'sources/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';

const sample = extra => ({scope: 'database', status: 'available', sample_id: 'native-one',
  transaction_refresh: {status: 'completed'}, ended_at: '2026-10-13T12:00:00Z',
  identity: {database_name: 'owned', target_id: 'file-one'},
  groups: {storage: {status: 'available', rows: [{database_name: 'owned',
    database_size: '1.0 GiB', used_blocks: '9007199254740993'}]},
  database: {status: 'available', rows: [{read_only: false, encrypted: false}]},
  extensions: {status: 'available', rows: [{available: 50, installed: 5, loaded: 2}]}}, ...extra});
const snapshot = extra => ({state: 'collecting', sample_age_seconds: 1,
  stale_after_seconds: 15, heartbeat: {status: 'observed'}, samples: [sample()], ...extra});
const envelope = files => ({format: 'ddn-workspace@1', entry: 'dashboard.ddn', view: 'dashboard', files});

describe('DuckDB public DDN dashboards', () => {
  beforeAll(() => viewer.setTextProvider((text, size) => ({width: String(text).length * size * 0.6,
    ascent: size * 0.8, descent: size * 0.2}), 'duckdb-dashboard-test'));
  afterAll(() => viewer.setTextProvider(null));
  it('binds only completed, current native file refreshes', () => {
    expect(duckdbCurrentSample(snapshot())).toBeTruthy();
    expect(duckdbCurrentSample(snapshot({sample_age_seconds: 100}))).toBeNull();
    expect(duckdbCurrentSample(snapshot({samples: [sample({transaction_refresh: {status: 'failed'}})]}))).toBeNull();
    const files = duckdbDashboardFiles(snapshot(), 'database');
    const draft = validatePublication(viewer, envelope(files), 'database', 'duckdb');
    expect(draft.files['dashboard.ddn']).not.toContain('9007199254740993');
    const rebound = bindPublication(viewer, draft, 'database', files, 'duckdb');
    expect(rebound.files['dashboard.ddn']).toContain('9007199254740993');
    const workspace = viewer.createWorkspace(rebound.files);
    try {expect(workspace.renderSync({entry: 'dashboard.ddn', view: 'dashboard'}).diagnostics.filter(row => row.severity === 'error')).toEqual([]);}
    finally {workspace.destroy();}
    expect(() => validatePublication(viewer, draft, 'database', 'mysql')).toThrow();
  });
  it('shows registered files without inventing remote server counters', () => {
    const server = duckdbDashboardFiles({state: 'aggregate', databases: [{snapshot: {state: 'collecting'}}]}, 'server');
    validatePublication(viewer, envelope(server), 'server', 'duckdb');
    const fleet = duckdbFleetFiles({registered_endpoints: 1, servers: [{server_id: 8,
      name: 'Local endpoint', snapshot: {state: 'aggregate'},
      databases: [{target_id: 'file-one', name: 'owned.duckdb', snapshot: snapshot()}]}]});
    validatePublication(viewer, envelope(fleet), 'engine', 'duckdb');
    expect(fleet['dashboard.ddn']).toContain('owned.duckdb');
    expect(fleet['dashboard.ddn']).toContain('aliases are not deduplicated');
  });
});
