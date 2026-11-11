/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  act, fireEvent, screen, waitFor, render, bootstrap, ProviderWorkspaceContent,
  requestSQLSource, installSharedHooks, installWorkspaceHooks,
} from './providerWorkspaceContentShared';

jest.mock('../../../pgadmin/static/js/api_instance');
// Execution contract tests use a text adapter; the native browser gate covers CodeMirror.
jest.mock('../../../pgadmin/static/js/cdeadmin_ui/editors/CodeEditor', () => ({__esModule: true,
  default: ({label, value, onChange, disabled}) => <textarea aria-label={label} value={value}
    disabled={disabled} onChange={event => onChange(event.target.value)} /> }));
// Hosted native renderers need a bounded readiness allowance; assertions and

installSharedHooks();

describe('ProviderWorkspaceContent (SQL sessions and execution)', () => {
  const workspace = installWorkspaceHooks();
  let api;
  beforeEach(() => { api = workspace.api; });

  it('keeps a DuckDB registered-file DDN request at endpoint scope', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap,
      endpoint: {...bootstrap.endpoint, profile_id: 'duckdb-native'}}}});
    api.post.mockResolvedValue({data: {data: {format: 'scratchrobin.duckdb.registered-files@1',
      files: [], capture_limit: 32}}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="export"
      initialContext={{server_catalog: true, database_target_id: 'active-file'}} />);
    fireEvent.click(await screen.findByRole('button', {name: 'Load registered files'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', {
      action: 'duckdb_catalog_export', request: {},
    }));
  });

  it('keeps stacked status messages in a keyboard-accessible bounded region', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap,
      engine_contracts: {state: 'blocked', dialect: {state: 'blocked'},
        metrics: {state: 'passed'}}, languages: [{
        language_profile: 'firebird-sql', title: 'Firebird SQL',
        starter_source: 'SELECT 1 FROM RDB$DATABASE',
      }]}}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    const limit = await screen.findByLabelText('Maximum fetched rows');
    fireEvent.change(limit, {target: {value: '1000001'}});
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    const status = screen.getByRole('region', {name: 'Provider workspace status'});
    expect(status).toHaveAttribute('tabindex', '0');
    expect(status).toHaveStyle({maxHeight: '40%', overflow: 'auto', flexShrink: '0'});
    expect(status).toContainElement(screen.getByText(/Maximum fetched rows must be an integer/));
    expect(status).toContainElement(screen.getByLabelText('Exact engine contract status'));
    expect(screen.queryByLabelText('Provider grid activation status')).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
  });

  it.each([[false, false], [true, false], [false, true]])('submits ordered Firebird parameters with profiling=%s statistics=%s', async (profiling, statistics) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT CAST(? AS INTEGER) FROM RDB$DATABASE',
      parameter_shape: 'array', parameter_hint: 'Ordered ? placeholders',
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'firebird-session'},
      execute: {occurrence_id: 'firebird-occurrence'},
      poll: {occurrence: {operation: {terminal: true}}, rendered_result: null},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio"
      initialContext={{database_target_id: 'firebird-target'}} />);
    fireEvent.click(await screen.findByRole('tab', {name: 'Engine options'}));
    const input = await screen.findByLabelText('Query parameters (JSON array)');
    expect(input).toHaveValue('[]');
    expect(screen.getByText('Ordered ? placeholders')).toBeInTheDocument();
    expect(screen.getByText(/Driver prefetch may execute more procedure work/)).toBeInTheDocument();
    fireEvent.change(input, {target: {value: '[42,"text",null]'}});
    if(statistics) fireEvent.click(screen.getByLabelText('Collect fresh attachment query statistics'));
    if(profiling) {
      expect(screen.getByRole('button', {name: 'Run with native profiling'})).toBeDisabled();
      fireEvent.click(screen.getByLabelText('Allow native profiler storage and replacement of any active profile on this attachment'));
      fireEvent.click(screen.getByRole('button', {name: 'Run with native profiling'}));
    } else fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', {
      action: 'execute', session_id: 'firebird-session',
      source: 'SELECT CAST(? AS INTEGER) FROM RDB$DATABASE',
      parameters: [42, 'text', null], database_target_id: 'firebird-target',
      max_rows: 1000, client_sql_dialect: 3, history_sensitive: false,
      ...(profiling ? {profile_mode: true} : {}),
      ...(statistics ? {statistics_mode: true} : {}),
    }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(3));
  });

  it('shares a pending PostgreSQL session and policy observation between validation and execution', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'postgresql-sql', title: 'PostgreSQL SQL', starter_source: 'SELECT 1',
    }]}}});
    let opened;
    const opening = new Promise(resolve => {opened = resolve;});
    api.post.mockImplementation((_url, payload) => payload.action === 'open_session' ? opening : Promise.resolve({data: {data: {
      transaction: {provider_payload: {autocommit: true}},
      source_validate: {grammar_valid: true, diagnostics: []},
      execute: {occurrence_id: 'pg-concurrent'},
      poll: {occurrence: {operation: {terminal: true}}, rendered_result: null},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Check source'}));
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    expect(api.post.mock.calls.filter(([, payload]) => payload.action === 'open_session')).toHaveLength(1);
    opened({data: {data: {session_id: 'pg-shared-opening'}}});
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', expect.objectContaining({
      action: 'execute', session_id: 'pg-shared-opening',
    })));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', expect.objectContaining({
      action: 'source_validate', session_id: 'pg-shared-opening',
    })));
    expect(api.post.mock.calls.filter(([, payload]) => payload.action === 'open_session')).toHaveLength(1);
    expect(api.post.mock.calls.filter(([, payload]) => payload.action === 'transaction')).toHaveLength(1);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Run', exact: true})).toBeEnabled());
  });

  it('binds PostgreSQL plan parameters and displays native diagnostics and scoped timings', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'postgresql-sql', title: 'PostgreSQL SQL', starter_source: 'SELECT %s',
      parameter_shape: 'object-or-array', query_plan_templates: [
        {label: 'Estimated plan', source_template: 'EXPLAIN (FORMAT JSON) {source}'},
      ],
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'pg-plan'}, transaction: {provider_payload: {autocommit: true}},
      execute: {occurrence_id: 'plan-one'},
      poll: {occurrence: {operation: {terminal: true}, result: {extensions: {postgresql: {payload: {
        has_page: false, statement_metrics: {dispatch_ms: 12.5},
        error: {sqlstate: '42601', message_primary: 'Native syntax error', message_hint: 'Check source', statement_position: '8'},
      }}}}}, rendered_result: null},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.change(await screen.findByLabelText('Query parameters (JSON object or array)'), {target: {value: '[42]'}});
    fireEvent.click(screen.getByRole('button', {name: 'Explain / query plan'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', expect.objectContaining({
      action: 'execute', source: 'EXPLAIN (FORMAT JSON) SELECT %s', parameters: [42], plan_mode: true,
    })));
    expect(await screen.findByLabelText('Statement metrics')).toHaveTextContent('12.5 ms');
    fireEvent.click(screen.getByRole('tab', {name: 'Messages'}));
    expect(screen.getByLabelText('PostgreSQL diagnostic')).toHaveTextContent('Check source');
    expect(screen.getByLabelText('PostgreSQL diagnostic')).toHaveTextContent('statement_position: 8');
    await waitFor(() => expect(screen.getByRole('button', {name: 'Run', exact: true})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', expect.objectContaining({action: 'execute', source: 'SELECT %s'})));
    fireEvent.click(screen.getByRole('tab', {name: 'Explain'}));
    expect(screen.getByText('No plan requested for this execution. Use Explain or explicitly run Explain Analyze.')).toBeVisible();
  });

  it.each(['postgresql', 'mysql'])('keeps %s source editing stable while its first session policy is loading', async (engine) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: `${engine}-sql`, title: `${engine} SQL`, starter_source: 'SELECT 1',
      transaction_actions: ['commit', 'rollback', 'autocommit_on', 'autocommit_off'],
    }]}}});
    let resolvePolicy;
    const policy=new Promise(resolve=>{resolvePolicy=resolve;});
    api.post.mockImplementation((_url,payload)=> {
      if(payload.action==='open_session') return Promise.resolve({data:{data:{session_id:'opening-policy'}}});
      if(payload.action==='transaction') return policy;
      if(payload.action==='source_validate') return Promise.resolve({data:{data:{grammar_valid:true}}});
      return Promise.resolve({data:{data:{}}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1" initialTab="studio"
      initialContext={{database_target_id:'42'}} />);
    fireEvent.click(await screen.findByRole('button',{name:'Check source'}));
    await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/workspace/1',expect.objectContaining({action:'transaction'})));
    expect(screen.getByRole('textbox',{name:'Query source'})).toBeEnabled();
    await act(async()=>resolvePolicy({data:{data:{provider_payload:{autocommit:true}}}}));
    await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/workspace/1',expect.objectContaining({action:'source_validate',session_id:'opening-policy'})));
    expect(screen.getByRole('checkbox',{name:'Autocommit'})).toBeChecked();
  });

  it.each(['postgresql', 'mysql'])('observes %s autocommit and changes only acknowledged policy', async (engine) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: `${engine}-sql`, title: `${engine} SQL`, starter_source: 'SELECT 1',
      transaction_actions: ['commit', 'rollback', 'autocommit_on', 'autocommit_off'],
    }]}}});
    let policy = true;
    api.post.mockImplementation((_url, payload) => {
      if (payload.action === 'transaction_action') policy = payload.transaction_action === 'autocommit_on';
      return Promise.resolve({data: {data: payload.action === 'open_session' ?
        {session_id: 'pg-policy'} : {provider_payload: {autocommit: policy}}}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1" initialTab="studio"
      initialContext={{database_target_id: '42'}} />);
    expect(await screen.findByRole('button', {name: 'commit', exact: true})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Provider transaction state'}));
    await waitFor(() => expect(screen.getByRole('checkbox', {name: 'Autocommit'})).toBeChecked());
    expect(screen.getByRole('button', {name: 'rollback', exact: true})).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', {name: 'Autocommit'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'commit', exact: true})).toBeEnabled());
    expect(api.post).toHaveBeenCalledWith('/workspace/1', expect.objectContaining({
      action: 'transaction_action', session_id: 'pg-policy', transaction_action: 'autocommit_off',
    }));
    expect(screen.getByRole('checkbox', {name: 'Autocommit'})).not.toBeChecked();
    api.post.mockRejectedValueOnce(new Error('Unacknowledged policy change'));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Autocommit'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'commit', exact: true})).toBeDisabled());
    await waitFor(() => expect(screen.getByRole('button', {name: 'Provider transaction state'})).toBeEnabled());
    expect(screen.getByRole('button', {name: 'Run', exact: true})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Provider transaction state'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'commit', exact: true})).toBeEnabled());
    expect(screen.getByRole('checkbox', {name: 'Autocommit'})).not.toBeChecked();
    expect(api.post.mock.calls.some(([, payload]) => payload.action === 'execute')).toBe(false);
  });

  it.each(['mysql', 'mariadb'])('allows %s native diagnostics after ERR without assuming transaction policy', async (engine) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: `${engine}-sql`, title: `${engine} SQL`, starter_source: 'SELECT missing_column',
      transaction_actions: ['commit', 'rollback', 'autocommit_on', 'autocommit_off'],
    }]}}});
    let executed = false;
    api.post.mockImplementation((_url, payload) => {
      if (payload.action === 'execute') executed = true;
      const data = {
        open_session: {session_id: 'diagnostic-session'},
        execute: {occurrence_id: 'native-error'},
        poll: {occurrence: {operation: {terminal: true}}, rendered_result: null},
        transaction: {provider_payload: executed ? {
          state: 'unknown', connection_usable: true, status_current: false,
        } : {state: 'idle', autocommit: true, connection_usable: true, status_current: true}},
      }[payload.action];
      return Promise.resolve({data: {data}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1" initialTab="studio"
      initialContext={{database_target_id: '42'}} />);
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', expect.objectContaining({action: 'poll'})));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Run', exact: true})).toBeEnabled());
    expect(screen.getByRole('checkbox', {name: 'Autocommit'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'commit', exact: true})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'rollback', exact: true})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    await waitFor(() => expect(api.post.mock.calls.filter(([, p]) => p.action === 'execute')).toHaveLength(2));
    expect(api.post.mock.calls.filter(([, p]) => p.action === 'open_session')).toHaveLength(1);
    expect(api.post.mock.calls.some(([, p]) => p.action === 'transaction_action')).toBe(false);
  });

  it.each([
    ['MySQL JSON query plan', 'EXPLAIN FORMAT=JSON {source}'],
    ['MySQL execution plan', 'EXPLAIN ANALYZE {source}'],
  ])('uses the shared query form for %s without Firebird controls', async (label, template) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'mysql-sql', title: 'MySQL SQL', starter_source: 'SELECT %s',
      parameter_shape: 'object-or-array', transaction_actions: ['commit', 'rollback'],
      query_plan_templates: [{label, source_template: template}],
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'mysql-session'},
      execute: {occurrence_id: 'mysql-plan'},
      poll: {occurrence: {operation: {terminal: true}}, rendered_result: null},
      transaction: {provider_payload: {state: 'active', autocommit: false, in_transaction: true}},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1" initialTab="studio"
      initialContext={{database_target_id: 'mysql-target'}} />);
    fireEvent.click(await screen.findByRole('tab', {name: 'Engine options'}));
    expect(screen.getByLabelText('MySQL session observation')).toHaveTextContent('Not observed');
    expect(screen.queryByLabelText('Statement SQL dialect')).not.toBeInTheDocument();
    expect(screen.queryByText('Run with native profiling')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Query parameters (JSON object or array)'), {target: {value: '[42]'}});
    fireEvent.click(screen.getByRole('button', {name: 'Provider transaction state'}));
    await waitFor(() => expect(screen.getByLabelText('MySQL session observation')).toHaveTextContent('active'));
    expect(screen.getByLabelText('MySQL session observation')).toHaveTextContent('Autocommit (observed)Off');
    fireEvent.click(screen.getByRole('button', {name: label}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', {
      action: 'execute', session_id: 'mysql-session', database_target_id: 'mysql-target',
      source: template.replace('{source}', 'SELECT %s'), parameters: [42],
      history_sensitive: false,
    }));
    expect(screen.getByRole('tab', {name: 'Explain'})).toHaveAttribute('aria-selected', 'true');
    await waitFor(() => expect(screen.getByRole('button', {name: 'Run', exact: true})).toBeEnabled());
    expect(api.post.mock.calls.some(([, value]) => value.action === 'transaction_action')).toBe(false);
  });

  it('presents native MySQL operators from the plan response without another SQL dispatch', async () => {
    const text = '{"query_plan":{"operation":"Table scan on native_plan_t","estimated_rows":9007199254740993}}';
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'mysql-sql', title: 'MySQL SQL', starter_source: 'SELECT * FROM native_plan_t',
      parameter_shape: 'object-or-array', query_plan_templates: [
        {label: 'MySQL JSON query plan', source_template: 'EXPLAIN FORMAT=JSON {source}'},
      ],
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'mysql-graph'}, execute: {occurrence_id: 'mysql-plan-graph'},
      poll: {occurrence: {operation: {terminal: true}, result: {extensions: {mysql: {payload: {
        has_page: true, rows: [[text]], result_set_end: true,
      }}}}}, rendered_result: {result_id: 'native-graph-result', view_model: {
        columns: [{name: 'EXPLAIN'}], rows: [{EXPLAIN: text}],
      }}},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1" initialTab="studio"
      initialContext={{database_target_id: 'mysql-target'}} />);
    fireEvent.click(await screen.findByRole('button', {name: 'MySQL JSON query plan'}));
    expect(await screen.findByRole('tree', {name: 'Native MySQL operator graph'})).toBeVisible();
    expect(screen.getByLabelText('Original MySQL plan text').textContent).toBe(text);
    expect(screen.getByLabelText('Selected native operator')).toHaveTextContent('9007199254740993');
    fireEvent.click(screen.getByRole('button', {name: 'Inspect operator 1'}));
    expect(api.post.mock.calls.filter(([, value]) => value.action === 'execute')).toHaveLength(1);
    expect(api.post.mock.calls.some(([, value]) => value.action === 'transaction_action')).toBe(false);
  });

  it('retains MySQL dispatch timing and native diagnostics without inventing engine timing or a row result', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'mysql-sql', title: 'MySQL SQL', starter_source: 'SELECT missing',
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'mysql-diagnostic'}, execute: {occurrence_id: 'mysql-error'},
      poll: {occurrence: {operation: {terminal: true}, result: {extensions: {mysql: {payload: {
        has_page: false, statement_metrics: {dispatch_ms: 12.5, prepare_ms: null, execute_ms: null, plan: null},
        error: {errno: 1054, sqlstate: '42S22', message_primary: 'Unknown column missing'},
      }}}}}, rendered_result: null},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1" initialTab="studio" />);
    const run = await screen.findByRole('button', {name: 'Run', exact: true});
    await waitFor(() => expect(run).toBeEnabled()); fireEvent.click(run);
    expect(await screen.findByLabelText('MySQL diagnostic')).toHaveTextContent('1054');
    expect(screen.getByLabelText('MySQL diagnostic')).toHaveTextContent('42S22');
    expect(screen.getByLabelText('MySQL diagnostic')).toHaveTextContent('Unknown column missing');
    expect(screen.getByLabelText('Statement metrics')).toHaveTextContent('12.5 ms');
    expect(screen.getByLabelText('Statement metrics')).toHaveTextContent('Preparation: Unavailable');
    expect(screen.getByLabelText('Statement metrics')).toHaveTextContent('Execution: Unavailable');
    expect(screen.getByLabelText('Statement metrics')).toHaveTextContent('Plan used: Unavailable');
  });

  it('shows partial MySQL dispatch without retrying or deciding the transaction', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'mysql-sql', title: 'MySQL SQL', starter_source: 'SELECT 1;SELECT %s',
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'mysql-partial'}, execute: {occurrence_id: 'mysql-partial-execution'},
      poll: {occurrence: {operation: {terminal: true}, result: {extensions: {mysql: {payload: {
        has_page: false, error: {type:'MySQLParameterAdmissionError', query_dispatch:'partially_started',
          commands_dispatched:1, message_primary:'Earlier commands ran.'}, session_reuse_blocked:false,
      }}}}}, rendered_result:null},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1" initialTab="studio" />);
    const run=await screen.findByRole('button',{name:'Run',exact:true});
    await waitFor(() => expect(run).toBeEnabled()); fireEvent.click(run);
    expect(await screen.findByLabelText('MySQL partial execution')).toHaveTextContent('Earlier commands ran. The next command was not sent.');
    await waitFor(() => expect(run).toBeEnabled());
    expect(api.post.mock.calls.filter(([,value]) => value.action==='execute')).toHaveLength(1);
    expect(api.post.mock.calls.some(([,value]) => value.action==='transaction_action')).toBe(false);
  });

  it.each(['[42,null]', '{"id":42}'])('submits MySQL native parameter shape %s', async (parameters) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'mysql-sql', title: 'MySQL SQL',
      starter_source: 'SELECT 1', parameter_shape: 'object-or-array',
      parameter_hint: 'Native MySQL named or positional placeholders',
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'mysql-session'},
      execute: {occurrence_id: 'mysql-occurrence'},
      poll: {occurrence: {operation: {terminal: true}}, rendered_result: null},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio"
      initialContext={{database_target_id: 'mysql-target'}} />);
    const input = await screen.findByLabelText('Query parameters (JSON object or array)');
    fireEvent.change(input, {target: {value: parameters}});
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', {
      action: 'execute', session_id: 'mysql-session', source: 'SELECT 1',
      parameters: JSON.parse(parameters), database_target_id: 'mysql-target', history_sensitive: false,
    }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(3));
  });

  it.each([['mysql', 'MySQL'], ['mariadb', 'MariaDB'], ['postgresql', 'PostgreSQL'], ['sqlite', 'SQLite'], ['duckdb', 'DuckDB'], ['cockroachdb', 'CockroachDB'], ['yugabytedb', 'YugabyteDB YSQL'], ['ycql', 'YugabyteDB YCQL'], ['tidb', 'TiDB'], ['vitess', 'Vitess'], ['dolt', 'Dolt'], ['xtdb', 'XTDB'], ['immudb', 'immudb'], ['apache_ignite', 'Ignite'], ['cassandra', 'Cassandra'], ['foundationdb', 'FoundationDB'], ['tikv', 'TiKV'], ['redis', 'Redis'], ['mongodb', 'MongoDB'], ['clickhouse', 'ClickHouse'], ['influxdb', 'InfluxDB'], ['neo4j', 'Neo4j'], ['milvus', 'Milvus'], ['opensearch', 'OpenSearch'], ['opensearch_sql_ppl', 'OpenSearch SQL/PPL']])('polls %s pages and retains page identity after a terminal status', async (engine, title) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: engine === 'opensearch_sql_ppl' ? 'opensearch-sql-ppl' : engine === 'opensearch' ? 'opensearch-query-dsl' : engine === 'milvus' ? 'milvus-query-search-api' : engine === 'neo4j' ? 'cypher' : engine === 'influxdb' ? 'influxdb3-sql-influxql' : engine === 'mongodb' ? 'mongodb-query-api-json' : engine === 'redis' ? 'redis-resp3-command' : engine === 'tikv' ? 'tikv-keyvalue-json' : engine === 'foundationdb' ? 'foundationdb-keyvalue-json' : engine === 'cassandra' ? 'cql-3' : engine === 'apache_ignite' ? 'ignite-sql-keyvalue' : engine === 'xtdb' ? 'xtdb-sql-2.1' : engine === 'ycql' ? 'ycql' : engine === 'yugabytedb' ? 'ysql' : `${engine}-sql`, title: `${title} SQL`,
      starter_source: engine === 'sqlite' ? 'SELECT 2' : 'SELECT 1; SELECT 2', parameter_shape: 'object-or-array',
    }]}}});
    let polls = 0;
    api.post.mockImplementation((_url, payload) => {
      const result = payload.action === 'poll' ? {
        occurrence: {operation: {terminal: ++polls > 1}, result: {
          complete: polls > 1, extensions: {[engine === 'ycql' ? 'yugabytedb' : engine]: {payload: polls === 1 ? {
            has_page: true, [['apache_ignite', 'foundationdb', 'tikv', 'redis'].includes(engine) ? 'entries' : 'rows']: [[2]], result_set_index: engine === 'sqlite' ? 0 : 1,
            row_offset: 256, result_set_end: true,
          } : {has_page: false, rows: [], error: engine === 'sqlite' ? {type: 'OperationalError', sqlite_errorcode: 8, sqlite_errorname: 'SQLITE_READONLY'} : engine === 'cassandra' ? {type: 'SyntaxException', native_code: 8192} : {type: 'ProgrammingError',
            errno: 1146, sqlstate: '42S02'}}}},
        }}, rendered_result: null,
      } : {open_session: {session_id: 'mysql-session'},
        transaction: {provider_payload: {autocommit: true}},
        execute: {occurrence_id: 'mysql-occurrence'}}[payload.action];
      return Promise.resolve({data: {data: result}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    expect(await screen.findByLabelText(`${title} result page`))
      .toHaveTextContent(`Result set: ${engine === 'sqlite' ? 1 : 2} Row offset: 256 Rows on this page: 1`);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Poll', exact: true})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Poll', exact: true}));
    expect(await screen.findByText(`${title} ${['foundationdb', 'tikv', 'redis'].includes(engine) ? 'operation' : 'query'} did not complete. ${engine === 'sqlite' ? 'OperationalError 8 SQLITE_READONLY' : engine === 'cassandra' ? 'SyntaxException 8192' : 'ProgrammingError 1146 42S02'}`))
      .toBeInTheDocument();
    expect(screen.getByLabelText(`${title} result page`)).toHaveTextContent('End of result set.');
  });

  it('runs confirmed trap control on the existing session without editor parameters or a new attachment', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'firebird-session'},
      transaction: {provider_payload: {state: 'idle'}},
      execute: {occurrence_id: 'firebird-occurrence'},
      poll: {occurrence: {operation: {terminal: true}}, rendered_result: null},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio"
      initialContext={{database_target_id: 'firebird-target'}} />);
    fireEvent.click(await screen.findByRole('tab', {name: 'Engine options'}));
    expect(await screen.findByRole('button', {name: 'Disable all DECFLOAT traps'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Provider transaction state'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Inspect DECFLOAT traps'})).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Query parameters (JSON array)'), {target: {value: 'invalid json'}});
    fireEvent.change(screen.getByLabelText('Maximum fetched rows'), {target: {value: '-1'}});
    fireEvent.mouseDown(screen.getByLabelText('Statement SQL dialect'));
    fireEvent.click(screen.getByRole('option', {name: '1 — legacy SQL'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Confirm disabling all DECFLOAT traps in this session'}));
    fireEvent.click(screen.getByRole('button', {name: 'Disable all DECFLOAT traps'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', {
      action: 'execute', session_id: 'firebird-session', source: 'SET DECFLOAT TRAPS TO',
      parameters: [], database_target_id: 'firebird-target', client_sql_dialect: 3, history_sensitive: false,
    }));
    fireEvent.click(screen.getByRole('tab', {name: 'Engine options'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Inspect DECFLOAT traps'})).toBeEnabled());
    expect(api.post.mock.calls.filter(([, value]) => value.action === 'open_session')).toHaveLength(1);
    expect(screen.getByRole('button', {name: 'Disable all DECFLOAT traps'})).toBeDisabled();
    expect(screen.getByLabelText('Query parameters (JSON array)')).toHaveValue('invalid json');
    fireEvent.click(screen.getByRole('button', {name: 'Inspect DECFLOAT traps'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', expect.objectContaining({
      action: 'execute', session_id: 'firebird-session', parameters: [],
      source: 'SELECT RDB$GET_CONTEXT(\'SYSTEM\', \'DECFLOAT_TRAPS\') AS DECFLOAT_TRAPS FROM RDB$DATABASE',
    })));
  });

  it.each([[1, '1 — legacy SQL'], [2, '2 — transition diagnostics'], [3, '3 — modern SQL']])('selects statement dialect %s without changing the session-opening request', async (dialect, label) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'fb'}, execute: {occurrence_id: 'query'},
      poll: {occurrence: {operation: {terminal: true}}, rendered_result: null},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.mouseDown(await screen.findByLabelText('Statement SQL dialect'));
    fireEvent.click(screen.getByRole('option', {name: label}));
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', expect.objectContaining({
      action: 'execute', client_sql_dialect: dialect, source: 'SELECT 1 FROM RDB$DATABASE',
    })));
    const opening = api.post.mock.calls.find(([, payload]) => payload.action === 'open_session')[1];
    expect(opening).not.toHaveProperty('client_sql_dialect');
    expect(api.post.mock.calls.some(([, payload]) => payload.action === 'transaction_control')).toBe(false);
  });

  it('prepares Firebird plans through the retained session without bindings, row limits or source rewriting', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'DELETE FROM T WHERE ID=?', parameter_shape: 'array',
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'fb'}, execute: {occurrence_id: 'query'},
      poll: {occurrence: {operation: {terminal: true}}, rendered_result: null},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.change(await screen.findByLabelText('Maximum fetched rows'), {target: {value: '-1'}});
    fireEvent.click(screen.getByRole('button', {name: 'Explain / query plan'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', expect.objectContaining({
      action: 'execute', plan_mode: true, parameters: [], session_id: 'fb',
      source: 'DELETE FROM T WHERE ID=?', client_sql_dialect: 3,
    })));
    const request = api.post.mock.calls.find(([, payload]) => payload.action === 'execute')[1];
    expect(request).not.toHaveProperty('max_rows');
    expect(request).not.toHaveProperty('script_mode');
    expect(screen.getByRole('tab', {name: 'Explain'})).toHaveAttribute('aria-selected', 'true');
  });

  it.each(['', '-1', '1.5', '1000001'])('rejects invalid Firebird row bound %s before opening a session', async (value) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
    }]}}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.change(await screen.findByLabelText('Maximum fetched rows'), {target: {value}});
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    expect(await screen.findByText('Maximum fetched rows must be an integer from 0 to 1000000.'))
      .toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it.each([['0', null], ['7', 7], ['1000000', 1000000]])('transports Firebird fetch bound %s without modifying source', async (value, expected) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'fb'}, execute: {occurrence_id: 'query'},
      poll: {occurrence: {operation: {terminal: true}, result: {complete: true,
        extensions: {firebird: {payload: {fetch_observation: {
          limit_reached: true, rows_returned: 7, total_rows: null,
        }}}}}}},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.change(await screen.findByLabelText('Maximum fetched rows'), {target: {value}});
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', expect.objectContaining({
      action: 'execute', max_rows: expected, source: 'SELECT 1 FROM RDB$DATABASE',
    })));
    expect(await screen.findByLabelText('Firebird fetch observation'))
      .toHaveTextContent('Further rows may exist; the total was not counted.');
    expect(screen.getByLabelText('Firebird fetch observation'))
      .toHaveTextContent('Driver prefetch may execute more procedure work than the displayed rows.');
    expect(api.post.mock.calls.some(([, payload]) => payload.action === 'transaction_control')).toBe(false);
  });

  it.each(['{"one":42}', 'null', '42'])('rejects %s before opening a positional query session', async (value) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT ? FROM RDB$DATABASE', parameter_shape: 'array',
    }]}}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.change(await screen.findByLabelText('Query parameters (JSON array)'),
      {target: {value}});
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    expect(await screen.findByText('This provider requires an ordered JSON parameter array.'))
      .toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('polls a running Firebird query and blocks competing transaction actions', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
      transaction_actions: ['commit', 'rollback'],
    }]}}});
    let polls = 0;
    api.post.mockImplementation((_url, payload) => {
      if(payload.action === 'open_session') return Promise.resolve({data: {data: {session_id: 'fb-session'}}});
      if(payload.action === 'execute') return Promise.resolve({data: {data: {occurrence_id: 'fb-query'}}});
      if(payload.action === 'close_session') return Promise.resolve({data: {data: {provider_closed: true}}});
      if(payload.action === 'transaction') return Promise.resolve({data: {data: {previous_observation_marker: true}}});
      if(payload.action === 'poll') {
        polls += 1;
        const complete = polls > 1;
        return Promise.resolve({data: {data: {occurrence: {
          operation: {terminal: complete}, result: {complete, extensions: {
            firebird: {payload: complete ? {error: {
              native_status_codes: [335544665],
            }} : {execution_state: 'running'}},
          }},
        }, rendered_result: null}}});
      }
      throw new Error('Unexpected action ' + payload.action);
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Provider transaction state'}));
    expect(await screen.findByLabelText('Provider query transaction state')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', {name: 'Run', exact: true})).not.toBeDisabled());
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    expect(await screen.findByText('Waiting for provider query completion. A cancellation request does not confirm commit or rollback.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Provider query transaction state')).not.toBeInTheDocument();
    for(const name of ['Run', 'commit', 'rollback', 'Provider transaction state', 'Close query session']) {
      expect(screen.getByRole('button', {name, exact: true})).toBeDisabled();
    }
    expect(await screen.findByText('Firebird query did not complete. Native status codes: 335544665')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Run', exact: true})).not.toBeDisabled();
    expect(api.post.mock.calls.filter(([, payload]) => payload.action === 'execute')).toHaveLength(1);
    expect(polls).toBe(2);
  });

  it('sends cancellation without implicit commit or rollback and observes its result', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
      transaction_actions: ['commit', 'rollback'],
    }]}}});
    let cancelled = false;
    api.post.mockImplementation((_url, payload) => {
      const responses = {
        open_session: {session_id: 'fb-session'},
        execute: {occurrence_id: 'fb-query'},
        close_session: {provider_closed: true},
      };
      if(payload.action === 'cancel') {
        cancelled = true;
        return Promise.resolve({data: {data: {cancel_request_accepted: true}}});
      }
      if(payload.action === 'poll') return Promise.resolve({data: {data: {
        occurrence: {operation: {terminal: cancelled}, result: {
          complete: cancelled, extensions: {firebird: {payload: cancelled ? {
            execution_state: 'cancelled', error: {native_status_codes: [335544794]},
          } : {execution_state: 'running'}}},
        }}, rendered_result: null,
      }}});
      if(responses[payload.action]) return Promise.resolve({data: {data: responses[payload.action]}});
      throw new Error('Unexpected transaction or replay action');
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Cancel request'})).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', {name: 'Cancel request'}));
    expect(await screen.findByText('Firebird query did not complete. Native status codes: 335544794')).toBeInTheDocument();
    expect(api.post.mock.calls.filter(([, payload]) => payload.action === 'execute')).toHaveLength(1);
    expect(api.post.mock.calls.some(([, payload]) => payload.action === 'transaction_control')).toBe(false);
  });

  it.each([
    [{}, 'This Firebird query session cannot be reused. Close it and explicitly reconnect.'],
    [{session_reuse_blocked_reason: 'result_cleanup_failed'}, 'Firebird result cleanup failed. Do not replay the statement. Close this query session and explicitly reconnect.'],
    [{session_reuse_blocked_reason: 'cancellation_state_unknown'}, 'Firebird cancellation state is unknown. Close this query session and explicitly reconnect.'],
    [{cancel_cleanup_error_type: 'RuntimeError'}, 'Firebird cancellation state is unknown. Close this query session and explicitly reconnect.'],
  ])('blocks a poisoned Firebird session until successful release: %j', async (reason, message) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
      transaction_actions: ['commit', 'rollback'],
    }]}}});
    let releaseFails = true;
    api.post.mockImplementation((_url, payload) => {
      if(payload.action === 'close_session' && releaseFails) return Promise.reject(new Error('Release unavailable'));
      return Promise.resolve({data: {data: {
        open_session: {session_id: 'fb-session'},
        execute: {occurrence_id: 'fb-query'},
        poll: {occurrence: {operation: {terminal: true}, result: {
          complete: true, extensions: {firebird: {payload: {session_reuse_blocked: true, ...reason}}},
        }}, rendered_result: null},
        close_session: {provider_closed: true},
      }[payload.action]}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    expect(await screen.findByText(message)).toBeInTheDocument();
    for(const name of ['Run', 'commit', 'rollback', 'Provider transaction state']) {
      expect(screen.getByRole('button', {name, exact: true})).toBeDisabled();
    }
    fireEvent.click(screen.getByRole('button', {name: 'Close query session'}));
    expect(await screen.findByText('Release unavailable')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Run', exact: true})).toBeDisabled();
    releaseFails = false;
    fireEvent.click(screen.getByRole('button', {name: 'Close query session'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Run', exact: true})).not.toBeDisabled());
    expect(screen.getByRole('button', {name: 'Close query session'})).toBeDisabled();
    expect(api.post.mock.calls.filter(([, payload]) => payload.action === 'execute')).toHaveLength(1);
  });

  // Owner direction 2026-11-05, 2026-11-06: Browse data from a resource's
  // context menu fills this connection's editor with text its provider builds
  // (action browse_source). The request can reach an editor that is already
  // open, and the statement is not run.
  it('fills the open editor with the provider Browse data text and does not run it', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
    }]}}});
    let answerBrowse;
    const browsed = new Promise((resolve) => {answerBrowse = resolve;});
    api.post.mockImplementation((_url, payload) => {
      if (payload.action === 'browse_source') {
        return browsed.then(() => ({data: {data: {resource_id: 'table:ASSETS',
          source: 'SELECT ASSET_ID, TAG\nFROM ASSETS', language_profile: 'firebird-sql'}}}));
      }
      return Promise.resolve({data: {data: {}}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/browse" initialTab="studio" />);
    await waitFor(() => expect(screen.getByLabelText('Query source')).toHaveValue('SELECT 1 FROM RDB$DATABASE'));
    act(() => requestSQLSource('/workspace/browse', {resource_id: 'table:ASSETS'}));
    await waitFor(() => expect(api.post.mock.calls.some(([, payload]) => payload.action === 'browse_source')).toBe(true));
    // Other activity re-renders the workspace while the request is out.
    act(() => requestSQLSource('/workspace/another-connection', {resource_id: 'table:OTHER'}));
    await act(async () => {answerBrowse();});
    await waitFor(() => expect(screen.getByLabelText('Query source')).toHaveValue(
      'SELECT ASSET_ID, TAG\nFROM ASSETS'));
    expect(api.post.mock.calls.map(([, payload]) => payload.action)).not.toContain('execute');
    expect(api.post.mock.calls.filter(([, payload]) => payload.action === 'browse_source')).toHaveLength(1);
    expect(api.post.mock.calls.find(([, payload]) => payload.action === 'browse_source')[1].request)
      .toEqual({resource_id: 'table:ASSETS', language_profile: 'firebird-sql', client_sql_dialect: 3});
  });

  // Owner direction 2026-11-06 (option b), 2026-11-08: the SQL tab offers
  // the visual SQL builder only when the engine declares it (workspace
  // payload sql_builder). Its query reaches the editor like Browse data and
  // is not run.
  it('offers Build query only when the engine declares the SQL builder', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
    }]}}});
    api.post.mockResolvedValue({data: {data: {}}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/no-builder" initialTab="studio" />);
    await waitFor(() => expect(screen.getByLabelText('Query source')).toHaveValue('SELECT 1 FROM RDB$DATABASE'));
    expect(screen.queryByRole('button', {name: 'Build query…'})).not.toBeInTheDocument();
  });

  it('puts the built query in the editor and does not run it', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, sql_builder: true, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
    }]}}});
    api.post.mockImplementation((_url, payload) => {
      if (payload.action === 'sql_builder' && payload.request.operation === 'options') {
        return Promise.resolve({data: {data: {runtime_version: '5.0.4', options: {},
          relations: [{path: ['ASSETS'], kind: 'table', name: 'ASSETS', columns: ['ASSET_ID']}]}}});
      }
      if (payload.action === 'sql_builder') {
        return Promise.resolve({data: {data: {source: 'SELECT\n  *\nFROM ASSETS',
          language_profile: 'firebird-sql'}}});
      }
      return Promise.resolve({data: {data: {}}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/builder" initialTab="studio" />);
    await waitFor(() => expect(screen.getByLabelText('Query source')).toHaveValue('SELECT 1 FROM RDB$DATABASE'));
    fireEvent.click(screen.getByRole('button', {name: 'Build query…'}));
    await screen.findByRole('combobox', {name: 'Query FROM'});
    fireEvent.click(screen.getByRole('button', {name: 'Insert into editor'}));
    await waitFor(() => expect(screen.getByLabelText('Query source')).toHaveValue('SELECT\n  *\nFROM ASSETS'));
    const sent = api.post.mock.calls.filter(([, payload]) => payload.action === 'sql_builder')
      .map(([, payload]) => payload.request);
    expect(sent).toEqual([{operation: 'options'}, {operation: 'source',
      model: {query: {selects: [{from: {source: {relation: ['ASSETS']}}}]}}}]);
    expect(api.post.mock.calls.map(([, payload]) => payload.action)).not.toContain('execute');
  });

  it('keeps the old language and owned session if language-switch release fails', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
    }, {language_profile: 'another-language', title: 'Another language',
      starter_source: 'native command'}]}}});
    let releaseFails = true;
    api.post.mockImplementation((_url, payload) => {
      if(payload.action === 'close_session' && releaseFails) return Promise.reject(new Error('Release unavailable'));
      return Promise.resolve({data: {data: {
        open_session: {session_id: 'fb-session'},
        execute: {occurrence_id: 'fb-query'},
        poll: {occurrence: {operation: {terminal: true}}, rendered_result: null},
        close_session: {provider_closed: true},
      }[payload.action]}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Run', exact: true})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Close query session'})).not.toBeDisabled());
    fireEvent.mouseDown(screen.getByLabelText('Dialect'));
    fireEvent.click(await screen.findByRole('option', {name: 'Another language'}));
    expect(await screen.findByText('Release unavailable')).toBeInTheDocument();
    expect(screen.getByLabelText('Query source')).toHaveValue('SELECT 1 FROM RDB$DATABASE');
    expect(screen.getByRole('button', {name: 'Close query session'})).not.toBeDisabled();
    releaseFails = false;
    fireEvent.mouseDown(screen.getByLabelText('Dialect'));
    fireEvent.click(await screen.findByRole('option', {name: 'Another language'}));
    await waitFor(() => expect(screen.getByLabelText('Query source')).toHaveValue('native command'));
    expect(screen.getByRole('button', {name: 'Close query session'})).toBeDisabled();
  });

  it('pauses Firebird automatic polling after transport failure without replaying execution', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'firebird-sql', title: 'Firebird SQL',
      starter_source: 'SELECT 1 FROM RDB$DATABASE', parameter_shape: 'array',
    }]}}});
    let polls = 0;
    api.post.mockImplementation((_url, payload) => {
      if(payload.action === 'poll' && ++polls === 1) return Promise.reject(new Error('offline'));
      return Promise.resolve({data: {data: {
        open_session: {session_id: 'fb-session'},
        execute: {occurrence_id: 'fb-query'},
        poll: {occurrence: {operation: {terminal: true}}, rendered_result: null},
        close_session: {provider_closed: true},
      }[payload.action]}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    expect(await screen.findByText('offline')).toBeInTheDocument();
    await act(async () => new Promise((resolve) => setTimeout(resolve, 650)));
    expect(polls).toBe(1);
    expect(screen.getByRole('button', {name: 'Run', exact: true})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Poll', exact: true}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Run', exact: true})).not.toBeDisabled());
    expect(polls).toBe(2);
    expect(api.post.mock.calls.filter(([, payload]) => payload.action === 'execute')).toHaveLength(1);
  });

});

