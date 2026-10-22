import viewer from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {mysqlDashboardFiles, mysqlFleetFiles, mysqlFleetPublication} from 'sources/cdeadmin_ui/integrations/ddn/mysqlDashboard';
import {validatePublication, bindPublication} from 'sources/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
import {mysqlTrendObservations, mysqlTrendFiles} from 'sources/cdeadmin_ui/integrations/ddn/mysqlTrends';

const sample = extra => ({scope: 'database', transaction_completed: true, status: 'partial', source_epoch: 'a',
  runtime_elapsed_seconds: 5, identity: {server_uuid: 'native'}, ended_at: '2026-10-12T12:00:00Z',
  groups: {status: {status: 'available', scope: 'server', rows: [
    {variable_name: 'Questions', variable_value: '9007199254740993'},
    {variable_name: 'Threads_connected', variable_value: '2'},
  ]}}, rates: {status: 'available', per_second: {Questions: '1.25'}}, ...extra});
const snapshot = extra => ({state: 'collecting', sample_age_seconds: 1, stale_after_seconds: 15, samples: [sample()], ...extra});
const envelope = files => ({format: 'ddn-workspace@1', entry: 'dashboard.ddn', view: 'dashboard', files});
describe('MySQL native DDN dashboards and trends', () => {
  beforeAll(() => viewer.setTextProvider((text, size) => ({width: String(text).length * size * 0.6,
    ascent: size * 0.8, descent: size * 0.2}), 'mysql-monitor-test'));
  afterAll(() => viewer.setTextProvider(null));
  it('keeps native bindings stable across source order changes and removes draft telemetry', () => {
    const draft = validatePublication(viewer, envelope(mysqlDashboardFiles(snapshot(), 'database')), 'database', 'mysql');
    expect(draft.files['dashboard.ddn']).not.toContain('9007199254740993');
    const reordered = sample(); reordered.groups.status.rows.reverse();
    const rebound = bindPublication(viewer, draft, 'database', mysqlDashboardFiles(snapshot({samples: [reordered]}), 'database'), 'mysql');
    const parsed = viewer.parse(rebound.files['dashboard.ddn']);
    const rows = parsed.declarations.find(row => row.id === 'observations').children;
    expect(rows.find(row => row.label === 'Questions: variable_value').props.x_record.value).toBe('9007199254740993');
    const missing = sample(); missing.groups.status.rows = missing.groups.status.rows.slice(1);
    const unavailable = bindPublication(viewer, draft, 'database', mysqlDashboardFiles(snapshot({samples: [missing]}), 'database'), 'mysql');
    const lost = viewer.parse(unavailable.files['dashboard.ddn']).declarations.find(row => row.id === 'observations').children;
    expect(lost.find(row => row.label === 'Questions: variable_value').props.x_record.value).toBe('Unavailable');
    expect(() => validatePublication(viewer, draft, 'database', 'postgresql')).toThrow();
  });
  it('renders engine inventory without summing aliased server counters', () => {
    const files = mysqlFleetFiles({registered_endpoints: 2, servers: [
      {server_id: 1, name: 'Alias one', snapshot: snapshot({samples: [sample({scope: 'server'})]}), databases: []},
      {server_id: 2, name: 'Alias two', snapshot: snapshot({samples: [sample({scope: 'server'})]}), databases: []},
    ]});
    validatePublication(viewer, envelope(files), 'engine', 'mysql');
    const workspace = viewer.createWorkspace(files);
    try {expect(workspace.renderSync({entry: 'dashboard.ddn', view: 'dashboard'}).diagnostics.filter(row => row.severity === 'error')).toEqual([]);}
    finally {workspace.destroy();}
    expect(files['dashboard.ddn']).toContain('counters are not summed');
    expect(files['dashboard.ddn']).toContain('Alias one');
    expect(files['dashboard.ddn']).toContain('Alias two');
  });
  it('keeps workload bindings tied to native identities and excludes private sample bindings', () => {
    const native = sample();
    native.groups.workload_digests = {status: 'available', rows: [{schema_name: 'demo', digest: 'a'.repeat(64),
      sum_timer_wait: '9007199254740993', count_star: '7', sum_rows_examined: '9'}]};
    const files = mysqlDashboardFiles(snapshot({samples: [native]}), 'database');
    const clean = validatePublication(viewer, envelope(files), 'database', 'mysql');
    expect(clean.files['dashboard.ddn']).not.toContain('9007199254740993');
    const rebound = bindPublication(viewer, clean, 'database', files, 'mysql');
    expect(rebound.files['dashboard.ddn']).toContain('9007199254740993');
    expect(() => validatePublication(viewer, envelope(files), 'database', 'mariadb')).toThrow();
    const source = files['dashboard.ddn'].replace('73756d5f74696d65725f77616974', '71756572795f73616d706c655f74657874');
    expect(() => validatePublication(viewer, envelope({'dashboard.ddn': source}), 'database', 'mysql')).toThrow();
  });
  it('bounds engine publications and reports omitted scopes without parsing labels as page identities', () => {
    const publication = mysqlFleetPublication({registered_endpoints: 300, servers: Array.from({length: 300}, (_, index) => ({
      server_id: index + 1, name: 'Native view dashboard_page_999 ' + 'x'.repeat(1000), databases: [],
    }))});
    expect(new TextEncoder().encode(publication.files['dashboard.ddn']).length).toBeLessThanOrEqual(512 * 1024);
    expect(publication.pages).not.toContain('dashboard_page_999');
    const clean = validatePublication(viewer, envelope(publication.files), 'engine', 'mysql');
    expect(clean.files['dashboard.ddn']).toContain('Omitted scopes');
  });
  it('keeps exact counter values, approximate chart bounds and unavailable samples distinct', () => {
    const data = snapshot({samples: [sample(), sample({transaction_completed: false}), sample({source_epoch: null})]});
    const gauges = mysqlTrendObservations(data, 'database', 'Threads_connected');
    expect(gauges[0].numeric).toBe(2);
    expect(gauges.slice(1).every(row => row.numeric === null)).toBe(true);
    const rates = mysqlTrendObservations(data, 'database', 'Questions');
    expect(rates[0].exact).toBe('1.25');
    expect(rates[0].numeric).toBe(1.25);
    const workspace = viewer.createWorkspace(mysqlTrendFiles(data, 'database', 'Questions'));
    try {expect(workspace.renderSync({entry: 'trends.ddn', view: 'trends'}).diagnostics.filter(row => row.severity === 'error')).toEqual([]);}
    finally {workspace.destroy();}
  });
});
