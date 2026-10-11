import runtime from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {firebirdDashboardFiles, firebirdFleetFiles} from 'sources/cdeadmin_ui/integrations/ddn/firebirdDashboard';
import {validatePublication, bindPublication} from 'sources/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';

describe('published DDN observation bindings', () => {
  beforeAll(() => runtime.setTextProvider((text, size) => ({width: String(text).length * size * 0.6,
    ascent: size * 0.8, descent: size * 0.2}), 'publication-test'));
  afterAll(() => runtime.setTextProvider(null));
  const source = (scope) => ({format: 'ddn-workspace@1', entry: 'dashboard.ddn', view: 'dashboard',
    files: scope === 'engine' ? firebirdFleetFiles(null) : firebirdDashboardFiles(null, 'Custom layout', scope)});
  it.each(['engine', 'server', 'database'])('validates and renders the %s template through the real DDN runtime', (scope) => {
    const clean = validatePublication(runtime, source(scope), scope);
    const bound = bindPublication(runtime, clean, scope, source(scope).files);
    const workspace = runtime.createWorkspace(bound.files);
    try {
      const result = workspace.renderSync(bound);
      expect(result.svg).toContain('<svg');
      expect(result.diagnostics.filter((item) => item.severity === 'error')).toEqual([]);
    } finally { workspace.destroy(); }
  });
  it('binds exact integers by key and removes stale metrics without changing the publication', () => {
    const clean = validatePublication(runtime, source('database'), 'database');
    const original = JSON.stringify(clean);
    const sample = {state: 'collecting', sample_age_seconds: 1, stale_after_seconds: 15,
      samples: [{status: 'available', groups: {io: {status: 'available', values: {page_reads: '9007199254740993'}}}}]};
    const live = firebirdDashboardFiles(sample);
    expect(bindPublication(runtime, clean, 'database', live).files['dashboard.ddn']).toContain('9007199254740993');
    const stale = firebirdDashboardFiles({...sample, sample_age_seconds: 20});
    expect(bindPublication(runtime, clean, 'database', stale).files['dashboard.ddn']).not.toContain('9007199254740993');
    expect(JSON.stringify(clean)).toBe(original);
  });
  it('preserves validated appearance and rejects invalid options', () => {
    const styled = {...source('server'), overrides: {theme: 'dark'}};
    expect(validatePublication(runtime, styled, 'server').overrides.theme).toBe('dark');
    expect(() => validatePublication(runtime, {...styled, overrides: {notAnOption: true}}, 'server')).toThrow();
  });
  it('rejects invented bindings and missing selected views', () => {
    const bad = source('server');
    bad.files['dashboard.ddn'] = bad.files['dashboard.ddn'].replaceAll('server_0', 'evil_query');
    expect(() => validatePublication(runtime, bad, 'server')).toThrow();
    expect(() => validatePublication(runtime, {...source('server'), view: 'missing'}, 'server')).toThrow();
  });
});
