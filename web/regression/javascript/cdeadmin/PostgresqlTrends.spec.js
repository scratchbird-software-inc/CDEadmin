import viewer from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {postgresqlTrendDatabases, postgresqlTrendObservations, postgresqlTrendFiles} from 'sources/cdeadmin_ui/integrations/ddn/postgresqlTrends';

const sample = (extra={}) => ({status: 'available', scope: 'server', transaction_completed: true,
  source_epoch: 'connection-a', runtime_elapsed_seconds: 5, ended_at: '2026-10-11T15:00:00Z',
  identity: {postmaster_started_at: '2026-10-11T01:00:00Z'},
  groups: {database: {status: 'available', visibility: 'native', rows: [
    {datid: '42', datname: 'duplicate', numbackends: '2', stats_reset: '2026-10-11T02:00:00Z', rate_state: 'available', rates_per_second: {xact_commit: '1.25000000000001'}},
    {datid: '43', datname: 'duplicate', numbackends: '7', stats_reset: '2026-10-11T02:00:00Z', rate_state: 'baseline-required'},
  ]}}, ...extra});

describe('PostgreSQL retained monitoring views', () => {
  beforeAll(() => viewer.setTextProvider((text, size) => ({width: String(text).length * size * 0.6,
    ascent: size * 0.8, descent: size * 0.2}), 'postgresql-trend-test'));
  afterAll(() => viewer.setTextProvider(null));
  it('separates equal names by OID and keeps exact rate strings', () => {
    const snapshot = {samples: [sample()]};
    expect(postgresqlTrendDatabases(snapshot)).toEqual([{id: '42', name: 'duplicate'}, {id: '43', name: 'duplicate'}]);
    const rows = postgresqlTrendObservations(snapshot, 'server', '42', 'xact_commit');
    expect(rows[0].exact).toBe('1.25000000000001');
    expect(rows[0].reason).toBe('observed');
    expect(postgresqlTrendObservations(snapshot, 'server', '43', 'xact_commit')[0].numeric).toBeNull();
    expect(postgresqlTrendObservations(snapshot, 'server', '44', 'numbackends')[0].reason).toBe('selected database not observed');
  });
  it('keeps transaction failures, permissions and unknown timing as gaps', () => {
    const snapshots = [sample({transaction_completed: false}), sample({status: 'unavailable'}),
      sample({groups: {database: {status: 'unavailable'}}}), sample({runtime_elapsed_seconds: null}),
      sample({source_epoch: null}), sample({scope: 'database'})];
    const rows = postgresqlTrendObservations({samples: snapshots}, 'server', '42', 'numbackends');
    expect(rows.every(row => row.numeric === null && row.reason !== 'observed')).toBe(true);
  });
  it('preserves values outside chart range and distinguishes reset epochs', () => {
    const first = sample(), second = sample({source_epoch: 'connection-b', runtime_elapsed_seconds: 10});
    second.groups.database.rows[0].numbackends = '9007199254740993';
    second.groups.database.rows[0].stats_reset = '2026-10-11T03:00:00Z';
    const rows = postgresqlTrendObservations({samples: [first, second]}, 'server', '42', 'numbackends');
    expect(rows[1].exact).toBe('9007199254740993');
    expect(rows[1].numeric).toBeNull();
    expect(rows[0].epoch).not.toBe(rows[1].epoch);
  });
  it('renders the full native DDN chart/table with no interpolation or administration', () => {
    const files = postgresqlTrendFiles({samples: [sample(), sample({status: 'unavailable'})]}, 'server', '42', 'xact_commit');
    expect(files['trends.ddn']).toContain('mark: point');
    expect(files['trends.ddn']).not.toContain('mark: line');
    const workspace = viewer.createWorkspace(files);
    try {
      const rendered = workspace.renderSync({entry: 'trends.ddn', view: 'trends'});
      expect(rendered.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
      expect(rendered.svg).toContain('1.25000000000001');
      const svg = new DOMParser().parseFromString(rendered.svg, 'image/svg+xml');
      const text = [...svg.querySelectorAll('text')].map(node => node.textContent).join(' ').replace(/\s+/g, ' ');
      expect(text).toContain('source unavailable or transaction incomplete');
    } finally {workspace.destroy();}
  });
  it('limits the selected window and rejects unknown native metrics', () => {
    const snapshot = {samples: Array.from({length: 50}, () => sample())};
    expect(postgresqlTrendObservations(snapshot, 'server', '42', 'numbackends', 30)).toHaveLength(30);
    expect(() => postgresqlTrendObservations(snapshot, 'server', '42', 'invented', 30)).toThrow();
    expect(() => postgresqlTrendObservations(snapshot, 'server', '42', 'numbackends', 999)).toThrow();
  });
});
