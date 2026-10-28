import { validatePublication, bindPublication } from 'sources/cdeadmin_ui/integrations/ddn/dashboardPublication.mjs';
import viewer, { setupDDNDOM, libraries } from './ddnTestRuntime';
import { postgresqlDashboardFiles, postgresqlFleetFiles } from 'sources/cdeadmin_ui/integrations/ddn/postgresqlDashboard';
describe('PostgreSQL native DDN dashboard', () => {
  beforeAll(setupDDNDOM);
  const group = (rows, extra = {}) => ({
    status: 'available',
    rows,
    scope: 'database',
    visibility: 'native',
    truncated: false,
    ...extra
  });
  const sample = {
    scope: 'database',
    status: 'partial',
    transaction_completed: true,
    identity: {
      database: 'postgres',
      statistics_visibility: 'permission-limited',
      in_recovery: false
    },
    groups: {
      database: group([{
        datid: '16384',
        datname: 'db " } view injected {}',
        xact_commit: '9007199254740993',
        rate_state: 'available',
        rates_per_second: {
          xact_commit: '1.5000000000001'
        }
      }]),
      activity: group([{
        visible_backends: '2',
        active: '0',
        restricted_or_unavailable: '1'
      }], {
        visibility: 'permission-limited'
      }),
      tables: group([{
        relid: '42',
        schemaname: 'public',
        relname: 'accounts',
        n_live_tup: '27'
      }], {
        truncated: true
      }),
      locks: group([{
        locktype: 'relation',
        mode: 'AccessShareLock',
        granted: true,
        count: '1'
      }]),
      replication: group([{
        pid: '123',
        application_name: 'replica',
        replay_lag: null
      }], {
        scope: 'server'
      }),
      io: group([{
        backend_type: 'client backend',
        object: 'relation',
        context: 'normal',
        read_bytes: '123'
      }], {
        scope: 'server'
      }),
      settings: group([{
        name: 'shared_buffers',
        setting: '16384',
        unit: '8kB'
      }], {
        scope: 'server'
      })
    }
  };
  const snapshot = (last = sample) => ({
    state: 'collecting',
    sample_age_seconds: 1,
    stale_after_seconds: 15,
    samples: [last]
  });
  it.each(['engine', 'server', 'database'])('admits PostgreSQL %s publications using only native bindings', async scope => {
    const files = scope === 'engine' ? postgresqlFleetFiles(null) : postgresqlDashboardFiles(snapshot({
      ...sample,
      scope
    }), 'Published', scope);
    const draft = {
      format: 'ddn-source-workspace@1',
      files,
      entry: 'dashboard.ddn',
      view: 'dashboard'
    };
    const clean = await validatePublication(libraries, draft, scope, 'postgresql');
    expect(clean.files['dashboard.ddn']).not.toContain('9007199254740993');
    await expect(bindPublication(libraries, clean, scope, files, 'postgresql')).resolves.toBeDefined();
    await expect(validatePublication(libraries, draft, scope, 'firebird')).rejects.toThrow();
  });
  it('retains every server observation across bounded dashboard pages', async () => {
    const files = postgresqlFleetFiles({
      registered_endpoints: 30,
      servers: Array.from({
        length: 30
      }, (_, index) => ({
        server_id: index + 1,
        name: `Endpoint ${index + 1}`,
        snapshot: {
          state: 'disabled'
        },
        databases: []
      }))
    });
    const workspace = await viewer.createWorkspace(files);
    try {
      const pages = workspace.entries()[0].views.filter(item => /^dashboard(?:_page_\d+)?$/.test(item.id));
      expect(pages).toHaveLength(3);
      const rendered=[];
      for(const item of pages) rendered.push(await workspace.render({entry:'dashboard.ddn',view:item.id}));
      rendered.forEach(result => expect(result.diagnostics.filter(item => item.severity === 'error')).toEqual([]));
      const output = rendered.map(result => result.svg).join('');
      for (let index = 1; index <= 30; index++) expect(output).toContain(`Endpoint ${index}`);
      await expect(validatePublication(libraries, {
        format: 'ddn-source-workspace@1',
        files,
        entry: 'dashboard.ddn',
        view: 'dashboard'
      }, 'engine', 'postgresql')).resolves.toBeDefined();
    } finally {
      workspace.destroy();
    }
  });
  it('binds by database identity rather than catalog row position and removes renamed observations', async () => {
    const one = {
      datid: '42',
      datname: 'alpha',
      xact_commit: '9007199254740993'
    };
    const two = {
      datid: '43',
      datname: 'beta',
      xact_commit: '9007199254740997'
    };
    const files = rows => postgresqlDashboardFiles(snapshot({
      ...sample,
      scope: 'server',
      groups: {
        database: group(rows)
      }
    }), 'Bindings', 'server');
    const draft = {
      format: 'ddn-source-workspace@1',
      files: files([one, two]),
      entry: 'dashboard.ddn',
      view: 'dashboard'
    };
    const before = await bindPublication(libraries, draft, 'server', files([one, two]), 'postgresql');
    expect(await bindPublication(libraries, draft, 'server', files([two, one]), 'postgresql')).toEqual(before);
    const renamed = await bindPublication(libraries, draft, 'server', files([{
      ...one,
      datname: 'renamed'
    }, two]), 'postgresql');
    expect(JSON.stringify(renamed.liveData)).not.toContain('9007199254740993');
    expect(JSON.stringify(renamed.liveData)).toContain('9007199254740997');
  });
  it('renders owner inventory with isolated server/database observations', async () => {
    const files = postgresqlFleetFiles({
      registered_endpoints: 2,
      servers: [{
        server_id: 7,
        name: 'Same name',
        snapshot: snapshot({
          ...sample,
          scope: 'server'
        }),
        databases: [{
          target_id: 'postgresql-database:42',
          name: 'qa',
          snapshot: snapshot()
        }]
      }, {
        server_id: 8,
        name: 'Same name',
        snapshot: {
          state: 'disabled'
        },
        databases: []
      }]
    });
    const workspace = await viewer.createWorkspace(files);
    try {
      const rendered = await workspace.render({
        entry: 'dashboard.ddn',
        view: 'dashboard'
      });
      expect(rendered.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
      expect(rendered.svg).toContain('Same name / qa');
      expect(rendered.svg).toContain('No current observation');
      expect(rendered.svg).toContain('permission-limited');
    } finally {
      workspace.destroy();
    }
  });
  it.each(['server', 'database'])('renders native %s data using the actual DDN runtime', async scope => {
    const files = postgresqlDashboardFiles(snapshot({
      ...sample,
      scope
    }), 'PostgreSQL dashboard', scope);
    const workspace = await viewer.createWorkspace(files);
    try {
      const rendered = await workspace.render({
        entry: 'dashboard.ddn',
        view: 'dashboard'
      });
      expect(rendered.diagnostics.filter(item => item.severity === 'error')).toEqual([]);
      expect(rendered.svg).toContain('<svg');
      expect(rendered.svg).toContain('9007199254740993');
      expect(rendered.svg).toContain('1.5000000000001');
      expect(rendered.svg).toContain('permission-limited');
      expect(rendered.svg).toContain('Unavailable');
      expect(rendered.svg).toContain('server scope');
      expect(rendered.svg.includes('public.accounts')).toBe(scope === 'database');
    } finally {
      workspace.destroy();
    }
  });
  it.each([{
    state: 'stopped'
  }, {
    sample_age_seconds: 16
  }, {
    sample_age_seconds: -1
  }, {
    stale_after_seconds: undefined
  }, {
    samples: [sample, {
      status: 'unavailable'
    }]
  }, {
    samples: [{
      ...sample,
      transaction_completed: false
    }]
  }, {
    samples: [{
      ...sample,
      scope: 'server'
    }]
  }])('does not display stale, failed, incomplete, or wrong-scope values: %j', override => {
    const files = postgresqlDashboardFiles({
      ...snapshot(),
      ...override
    });
    expect(files['dashboard.ddn']).not.toContain('9007199254740993');
    expect(files['dashboard.ddn']).toContain('No current observation');
  });
  it('does not fabricate a rate from a counter without a baseline', () => {
    const changed = {
      ...sample,
      groups: {
        ...sample.groups,
        database: group([{
          datid: '16384',
          xact_commit: '9007199254740993',
          rate_state: 'baseline-required',
          rates_per_second: {
            xact_commit: '123456789'
          }
        }])
      }
    };
    const source = postgresqlDashboardFiles(snapshot(changed))['dashboard.ddn'];
    expect(source).toContain('9007199254740993');
    expect(source).not.toContain('123456789');
  });
});
