import viewer from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {firebirdDashboardFiles, firebirdFleetFiles} from 'sources/cdeadmin_ui/integrations/ddn/firebirdDashboard';

describe('Firebird native dashboard DDN bindings', () => {
  beforeAll(() => viewer.setTextProvider((text, size) => ({
    width: String(text).length * size * 0.6, ascent: size * 0.8, descent: size * 0.2,
  }), 'firebird-dashboard-test'));
  afterAll(() => viewer.setTextProvider(null));
  const sample = {status: 'available', scope: 'database', coverage: 'visible-to-collector',
    groups: {database: {status: 'available', values: {database_name: 'db " } view injected {}',
      page_size: '8192'}}, io: {status: 'available', values: {page_reads: '9007199254740993'}}},
    derived: {allocated_bytes: '9007199254740993000'}};
  it.each(['database', 'server'])('renders actual DDN panels for %s without editor dependencies', (scope) => {
    const files = firebirdDashboardFiles({state: 'collecting', sample_age_seconds: 1, stale_after_seconds: 15, samples: [sample]}, 'Native dashboard', scope);
    const workspace = viewer.createWorkspace(files);
    try {
      const rendered = workspace.renderSync({entry: 'dashboard.ddn', view: 'dashboard'});
      expect(rendered.svg).toContain('<svg');
      expect(rendered.diagnostics.filter((item) => item.severity === 'error')).toEqual([]);
      if(scope === 'database') {
        expect(rendered.svg).toContain('9007199254740993');
        expect(rendered.svg).toContain('visible-to-collector');
      } else expect(rendered.svg).toContain('Service manager');
    } finally { workspace.destroy(); }
  });
  it('does not present an earlier successful value as current after failure', () => {
    const files = firebirdDashboardFiles({samples: [sample, {status: 'unavailable'}]});
    expect(files['dashboard.ddn']).not.toContain('9007199254740993');
    expect(files['dashboard.ddn']).toContain('Unavailable');
  });

  it('renders a native fleet with isolated endpoint registrations and no invented metrics', () => {
    const files = firebirdFleetFiles({registered_endpoints: 2,
      status_counts: {reachable: 1, unknown: 1}, servers: [
        {server_id: 1, name: 'Same name', status: 'reachable', version: '5.0',
          known_databases: 2, monitored_databases: 1},
        {server_id: 2, name: 'Same name', status: 'unknown'},
      ]});
    const workspace = viewer.createWorkspace(files);
    try {
      const rendered = workspace.renderSync({entry: 'dashboard.ddn', view: 'dashboard'});
      expect(rendered.svg).toContain('Firebird engine dashboard');
      expect(rendered.svg).toContain('Unavailable');
      expect(rendered.diagnostics.filter((item) => item.severity === 'error')).toEqual([]);
    } finally { workspace.destroy(); }
  });

});
