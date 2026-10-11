import runtime from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {firebirdRankingFiles, rankingRows} from 'sources/cdeadmin_ui/integrations/ddn/firebirdRanking';

describe('native captured ranking', () => {
  beforeAll(() => runtime.setTextProvider((text, size) => ({width: String(text).length * size * 0.6,
    ascent: size * 0.8, descent: size * 0.2}), 'ranking-test'));
  afterAll(() => runtime.setTextProvider(null));
  it('sorts exact values before choosing geometry and preserves underflow/large values', () => {
    const rows = rankingRows([{table_name: 'first', count: '9007199254740992'},
      {table_name: 'larger', count: '9007199254740993'}, {table_name: 'tiny', count: '1e-999'},
      {table_name: 'missing', count: null}], 'count');
    expect(rows.map((row) => row.label)).toEqual(['larger', 'first', 'tiny']);
    expect(rows.every((row) => row.numeric === null)).toBe(true);
  });
  it('renders the paired DDN chart and exact table with explicit capture truncation', () => {
    const files = firebirdRankingFiles({groups: {schema_counts: {status: 'available', values: {
      truncated: true, rows: [{kind: 'table', system_flag: '0', count: '3'},
        {kind: 'view', system_flag: '0', count: '2'}]}}}}, 'schema_counts', 'count');
    const workspace = runtime.createWorkspace(files);
    try {
      const rendered = workspace.renderSync({entry: 'ranking.ddn', view: 'ranking'});
      expect(rendered.diagnostics.filter((item) => item.severity === 'error')).toEqual([]);
      expect(rendered.svg).toContain('capture truncated');
    } finally {workspace.destroy();}
  });
});
