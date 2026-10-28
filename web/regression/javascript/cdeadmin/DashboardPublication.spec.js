import { libraries, setupDDNDOM, createTestWorkspace, metricRows } from './ddnTestRuntime';
import { firebirdDashboardFiles, firebirdFleetFiles } from 'sources/cdeadmin_ui/integrations/ddn/firebirdDashboard';
import { validatePublication, bindPublication } from 'sources/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
const source = scope => ({
  format: 'ddn-source-workspace@1',
  entry: 'dashboard.ddn',
  view: 'dashboard',
  files: scope === 'engine' ? firebirdFleetFiles(null) : firebirdDashboardFiles(null, 'Custom layout', scope)
});
describe('published DDN host observations', () => {
  beforeAll(setupDDNDOM);
  it.each(['engine', 'server', 'database'])('validates and captures %s through public DDN APIs', async scope => {
    const clean = await validatePublication(libraries, source(scope), scope);
    const bound = await bindPublication(libraries, clean, scope, source(scope).files),
      workspace = await createTestWorkspace(bound.files);
    try {
      const result = await workspace.render(bound);
      expect(result.svg).toContain('<svg');
      expect(result.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
    } finally {
      workspace.destroy();
    }
  });
  it('binds exact integers, removes stale metrics and retains authored source', async () => {
    const clean = await validatePublication(libraries, source('database'), 'database'),
      original = JSON.stringify(clean);
    const sample = {
      state: 'collecting',
      sample_age_seconds: 1,
      stale_after_seconds: 15,
      samples: [{
        status: 'available',
        groups: {
          io: {
            status: 'available',
            values: {
              page_reads: '9007199254740993'
            }
          }
        }
      }]
    };
    const bound = await bindPublication(libraries, clean, 'database', firebirdDashboardFiles(sample));
    expect(metricRows(bound).some(row => row[3] === '9007199254740993')).toBe(true);
    expect(bound.files).toEqual(clean.files);
    const stale = await bindPublication(libraries, clean, 'database', firebirdDashboardFiles({
      ...sample,
      sample_age_seconds: 20
    }));
    expect(metricRows(stale).some(row => row[3] === '9007199254740993')).toBe(false);
    expect(JSON.stringify(clean)).toBe(original);
  });
  it('preserves authored appearance and refuses obsolete transient overrides', async () => {
    const styled = source('server');
    styled.files['dashboard.ddn'] = styled.files['dashboard.ddn'].replace('title "Custom layout"', 'title "Authored layout"');
    expect((await validatePublication(libraries, styled, 'server')).files['dashboard.ddn']).toContain('Authored layout');
    await expect(validatePublication(libraries, {
      ...styled,
      overrides: {
        theme: 'dark'
      }
    }, 'server')).rejects.toThrow();
  });
  it('rejects invented bindings, extra providers and missing views', async () => {
    const bad = source('server');
    bad.files['dashboard.ddn'] = bad.files['dashboard.ddn'].replaceAll('server_0', 'evil_query');
    await expect(validatePublication(libraries, bad, 'server')).rejects.toThrow();
    await expect(validatePublication(libraries, {
      ...source('server'),
      view: 'missing'
    }, 'server')).rejects.toThrow();
    const extra = source('server');
    extra.files['dashboard.ddn'] += 'source evil as host\n    with\n        channel "foreign"\n';
    await expect(validatePublication(libraries, extra, 'server')).rejects.toThrow();
  });
});
