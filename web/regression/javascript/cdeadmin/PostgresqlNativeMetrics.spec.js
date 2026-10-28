import viewer, { setupDDNDOM } from './ddnTestRuntime';
import { currentPostgresqlNativeMetrics, postgresqlNativeMetricFiles } from 'sources/cdeadmin_ui/integrations/ddn/postgresqlNativeMetrics';
describe('native PostgreSQL statistics DDN adapter', () => {
  const frame = {
    status: 'partial',
    scope: 'server',
    visibility: 'native_privilege_scope',
    truncated: true,
    visible_row_count: 21,
    columns: [{
      name: 'native_name',
      value_type: 'text',
      redaction: 'none'
    }, {
      name: 'query',
      value_type: 'text',
      redaction: 'query_or_credential_text'
    }, {
      name: 'count',
      value_type: 'bigint',
      redaction: 'none',
      metric: {
        unit: 'events'
      }
    }],
    rows: Array.from({
      length: 21
    }, (_unused, index) => ['  native row ' + index + '  ', 'private query', '9007199254740993'])
  };
  const snapshot = () => ({
    state: 'collecting',
    sample_age_seconds: 1,
    stale_after_seconds: 15,
    samples: [{
      status: 'partial',
      scope: 'server',
      transaction_completed: true,
      groups: {
        native_metrics: {
          schema: 'postgresql-native-metric-families@1',
          row_byte_limit: 524288,
          sources: {
            pg_stat_test: frame
          }
        }
      }
    }]
  });
  beforeAll(setupDDNDOM);
  it('renders all rows across bounded pages with exact wide integers, whitespace and redaction', async () => {
    const collected = [];
    for (let page = 0; page < 3; page++) {
      const files = postgresqlNativeMetricFiles(snapshot(), 'server', 'pg_stat_test', page);
      expect(files['dashboard.ddn']).not.toContain('private query');
      expect(files['dashboard.ddn']).toContain('9007199254740993');
      const workspace = await viewer.createWorkspace(files);
      try {
        const result = await workspace.render({
          entry: 'dashboard.ddn',
          view: 'dashboard'
        });
        expect(result.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
        collected.push(files['dashboard.ddn']);
      } finally {
        workspace.destroy();
      }
    }
    for (let index = 0; index < 21; index++) expect(collected.filter(source => source.includes(JSON.stringify('  native row ' + index + '  ')))).toHaveLength(1);
  });
  it.each(['stopped', 'stale', 'wrong_scope', 'incomplete', 'unsupported_schema'])('removes observations when %s', reason => {
    const value = snapshot();
    if (reason === 'stopped') value.state = 'stopped';
    if (reason === 'stale') value.sample_age_seconds = 16;
    if (reason === 'wrong_scope') value.samples[0].scope = 'database';
    if (reason === 'incomplete') value.samples[0].transaction_completed = false;
    if (reason === 'unsupported_schema') value.samples[0].groups.native_metrics.schema = 'unrecognized';
    expect(currentPostgresqlNativeMetrics(value, 'server')).toBeNull();
    expect(postgresqlNativeMetricFiles(value, 'server', 'pg_stat_test')['dashboard.ddn']).not.toContain('9007199254740993');
  });
  it('retains a denied source and its SQLSTATE without displaying rows', () => {
    const value = snapshot();
    value.samples[0].groups.native_metrics.sources = {
      pg_stat_test: {
        ...frame,
        status: 'denied',
        sqlstate: '42501'
      }
    };
    const source = postgresqlNativeMetricFiles(value, 'server', 'pg_stat_test')['dashboard.ddn'];
    expect(source).toContain('42501');
    expect(source).toContain('denied');
    expect(source).not.toContain('9007199254740993');
  });
});
