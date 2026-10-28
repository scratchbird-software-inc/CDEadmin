import runtime, { setupDDNDOM } from './ddnTestRuntime';
import { trendObservations, firebirdTrendFiles } from 'sources/cdeadmin_ui/integrations/ddn/firebirdTrends';
describe('retained Firebird trends', () => {
  beforeAll(setupDDNDOM);
  const sample = (value, second = 5) => ({
    scope: 'database',
    status: 'available',
    ended_at: '2026-10-10T10:00:00Z',
    coverage: 'visible-to-collector',
    runtime_elapsed_seconds: second,
    rates: {
      status: 'available',
      epoch: 'one',
      per_second: {
        'io.page_reads': value
      }
    }
  });
  it('keeps exact decimals, rejects unsafe geometry and preserves explicit rate gaps', () => {
    const result = trendObservations({
      samples: [sample('1.234567890123456789'), sample('9007199254740993'), {
        ...sample('4'),
        rates: {
          status: 'gap',
          reason: 'counter-decreased'
        }
      }, {
        ...sample('3'),
        status: 'unavailable'
      }]
    }, 'io.page_reads');
    expect(result[0].exact).toBe('1.234567890123456789');
    expect(result[1]).toMatchObject({
      exact: '9007199254740993',
      numeric: null,
      reason: 'outside chart numeric range'
    });
    expect(result[2].reason).toBe('counter-decreased');
    expect(result[3].numeric).toBeNull();
  });
  it('renders a real DDN point chart and audit table without interpolated lines', async () => {
    const files = firebirdTrendFiles({
      samples: [sample('10'), sample('20', 10), {
        ...sample('30', 15),
        rates: {
          status: 'gap',
          reason: 'reconnect'
        }
      }]
    }, 'io.page_reads');
    const workspace = await runtime.createWorkspace(files);
    try {
      const result = await workspace.render({
        entry: 'trends.ddn',
        view: 'trends'
      });
      expect(result.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
      expect(result.svg).toContain('reconnect');
      const renderedText = new DOMParser().parseFromString(result.svg, 'image/svg+xml').documentElement.textContent;
      expect(renderedText).toContain('visible-to-collector');
      expect(files['trends.ddn']).toContain('mark "point"');
    } finally {
      workspace.destroy();
    }
  });
  it('plots MGA distances as gauges and preserves unrepresentable tiny decimals', () => {
    const snapshot = {
      samples: [{
        ...sample('1e-999'),
        source_epoch: 'connection',
        derived: {
          next_minus_oit: '9000'
        }
      }]
    };
    expect(trendObservations(snapshot, 'derived.next_minus_oit')[0]).toMatchObject({
      numeric: 9000,
      epoch: 'connection'
    });
    expect(trendObservations(snapshot, 'io.page_reads')[0]).toMatchObject({
      exact: '1e-999',
      numeric: null
    });
  });
  it('limits the retained window and rejects unsupported selections', () => {
    expect(trendObservations({
      samples: Array.from({
        length: 40
      }, (_, i) => sample(String(i), i))
    }, 'io.page_reads', 30)[0].elapsed).toBe(10);
    expect(() => trendObservations({}, 'free-form-query')).toThrow();
    expect(() => trendObservations({}, 'io.page_reads', 1000000)).toThrow();
  });
  it('renders empty and unavailable observations as tables without invented points', async () => {
    for (const samples of [[], [{
      scope: 'server',
      status: 'unavailable'
    }]]) {
      const files = firebirdTrendFiles({
        samples
      }, 'connection_count');
      const workspace = await runtime.createWorkspace(files);
      try {
        expect((await workspace.render({
          entry: 'trends.ddn',
          view: 'trends'
        })).diagnostics.filter(item => item.severity === 'error')).toEqual([]);
        expect(files['trends.ddn']).not.toContain('mark "point"');
      } finally {
        workspace.destroy();
      }
    }
  });
});
