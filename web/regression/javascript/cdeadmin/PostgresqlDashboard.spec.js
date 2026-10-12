import viewer from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {postgresqlDashboardFiles, postgresqlFleetFiles} from 'sources/cdeadmin_ui/integrations/ddn/postgresqlDashboard';

describe('PostgreSQL native DDN dashboard', () => {
  beforeAll(() => viewer.setTextProvider((text, size) => ({
    width: String(text).length * size * 0.6, ascent: size * 0.8, descent: size * 0.2,
  }), 'postgresql-dashboard-test'));
  afterAll(() => viewer.setTextProvider(null));
  const group = (rows, extra={}) => ({status: 'available', rows, scope: 'database',
    visibility: 'native', truncated: false, ...extra});
  const sample = {scope: 'database', status: 'partial', transaction_completed: true,
    identity: {database: 'postgres', statistics_visibility: 'permission-limited', in_recovery: false},
    groups: {
      database: group([{datid: '16384', datname: 'db " } view injected {}', xact_commit: '9007199254740993',
        rate_state: 'available', rates_per_second: {xact_commit: '1.5000000000001'}}]),
      activity: group([{visible_backends: '2', active: '0', restricted_or_unavailable: '1'}], {visibility: 'permission-limited'}),
      tables: group([{schemaname: 'public', relname: 'accounts', n_live_tup: '27'}], {truncated: true}),
      locks: group([{locktype: 'relation', mode: 'AccessShareLock', granted: true, count: '1'}]),
      replication: group([{application_name: 'replica', replay_lag: null}], {scope: 'server'}),
      io: group([{backend_type: 'client backend', object: 'relation', context: 'normal', read_bytes: '123'}], {scope: 'server'}),
      settings: group([{name: 'shared_buffers', setting: '16384', unit: '8kB'}], {scope: 'server'}),
    }};
  const snapshot = (last=sample) => ({state: 'collecting', sample_age_seconds: 1,
    stale_after_seconds: 15, samples: [last]});
  it('renders owner inventory with isolated server/database observations', () => {
    const files = postgresqlFleetFiles({registered_endpoints: 2, servers: [
      {server_id: 7, name: 'Same name', snapshot: snapshot({...sample, scope: 'server'}),
        databases: [{target_id: 'postgresql-database:42', name: 'qa', snapshot: snapshot()}]},
      {server_id: 8, name: 'Same name', snapshot: {state: 'disabled'}, databases: []},
    ]});
    const workspace = viewer.createWorkspace(files);
    try {
      const rendered = workspace.renderSync({entry: 'dashboard.ddn', view: 'dashboard'});
      expect(rendered.diagnostics.filter((item) => item.severity === 'error')).toEqual([]);
      expect(rendered.svg).toContain('Same name / qa');
      expect(rendered.svg).toContain('No current observation');
      expect(rendered.svg).toContain('permission-limited');
    } finally { workspace.destroy(); }
  });
  it.each(['server', 'database'])('renders native %s data using the actual DDN runtime', (scope) => {
    const files = postgresqlDashboardFiles(snapshot({...sample, scope}), 'PostgreSQL dashboard', scope);
    const workspace = viewer.createWorkspace(files);
    try {
      const rendered = workspace.renderSync({entry: 'dashboard.ddn', view: 'dashboard'});
      expect(rendered.diagnostics.filter((item) => item.severity === 'error')).toEqual([]);
      expect(rendered.svg).toContain('<svg');
      expect(rendered.svg).toContain('9007199254740993');
      expect(rendered.svg).toContain('1.5000000000001');
      expect(rendered.svg).toContain('permission-limited');
      expect(rendered.svg).toContain('Unavailable');
      expect(rendered.svg).toContain('server scope');
      expect(rendered.svg.includes('public.accounts')).toBe(scope === 'database');
    } finally { workspace.destroy(); }
  });
  it.each([
    {state: 'stopped'}, {sample_age_seconds: 16}, {sample_age_seconds: -1},
    {stale_after_seconds: undefined}, {samples: [sample, {status: 'unavailable'}]},
    {samples: [{...sample, transaction_completed: false}]},
    {samples: [{...sample, scope: 'server'}]},
  ])('does not display stale, failed, incomplete, or wrong-scope values: %j', (override) => {
    const files = postgresqlDashboardFiles({...snapshot(), ...override});
    expect(files['dashboard.ddn']).not.toContain('9007199254740993');
    expect(files['dashboard.ddn']).toContain('No current observation');
  });
  it('does not fabricate a rate from a counter without a baseline', () => {
    const changed = {...sample, groups: {...sample.groups,
      database: group([{datid: '16384', xact_commit: '9007199254740993',
        rate_state: 'baseline-required', rates_per_second: {xact_commit: '123456789'}}])}};
    const source = postgresqlDashboardFiles(snapshot(changed))['dashboard.ddn'];
    expect(source).toContain('9007199254740993');
    expect(source).not.toContain('123456789');
  });
});
