import {fireEvent, render as rtlRender, screen, waitFor} from '@testing-library/react';
import Theme from 'sources/Theme';
import ProviderWorkspaceContent from 'sources/Dialogs/ProviderWorkspaceContent';
import getApiInstance from 'sources/api_instance';
const render = ui => rtlRender(ui, {wrapper: Theme});
jest.mock('sources/api_instance');
jest.mock('sources/cdeadmin_ui/editors/CodeEditor', () => ({__esModule: true,
  default: ({label, value, onChange, disabled}) => <textarea aria-label={label} value={value}
    disabled={disabled} onChange={event => onChange(event.target.value)} /> }));
const bootstrap = {
  endpoint: {
    provider_id: 'org.cdeadmin.mariadb',
    verified_runtime_family: 'mariadb',
  },
  grid_workspace: {
    schema: 'cdeadmin.provider-grid-workspace.v1',
    adoption_state: 'passed',
    activation_gates: [{
      gate_id: 'public_grid_boundary', state: 'passed',
    }],
    runtime_gate: {
      gate_id: 'live_provider_verification', state: 'passed',
    },
  },
  languages: [{
    language_profile: 'mariadb-sql', title: 'MariaDB SQL',
    starter_source: 'SELECT 42',
    source_presets: [{label: 'MariaDB scalar query', source: 'SELECT 42'}],
  }],
  resource_page: {items: [{
    resource_id: 'database:example',
    resource_kind: 'database',
    display_name: 'example',
    authority_path: ['database', 'example'],
  }]},
  visual_admin: {
    engine_id: 'mariadb',
    engine_name: 'MariaDB',
    objects: [{
      resource_kind: 'database',
      title: 'Database',
      operations: [{
        operation_id: 'create',
        title: 'Create',
        mutation_class: 'admin',
        target_required: false,
        confirmation_required: false,
        blockers: ['provider_native_planner_unavailable'],
        form: {fields: [{
          field_id: 'name', label: 'Name', control: 'text', required: true,
        }]},
      }],
    }],
  },
  operational_workspace: {
    schema: 'cdeadmin.operational-workspace.v1',
    engine_id: 'mariadb',
    distributed: false,
    categories: ['runtime'],
    topology: {available: false, resource_kinds: []},
    facets: [{
      facet_id: 'health',
      title: 'Server and cluster health',
      category: 'runtime',
      summary: 'Provider-reported availability and health state.',
      catalog_state: 'operational',
      unavailable_reason: null,
      resource_kinds: ['database'],
      discovered_resource_count: 1,
      operations: [{
        operation_id: 'create', resource_kind: 'database', title: 'Create',
      }],
    }],
  },
  semantic_models: {
    items: [],
    capabilities: {
      designer: true, revision_history: true, validation: true,
      lineage: true, query_builder: true, pivot_cellset: true,
      execution_available: true,
      provider_compiler: {execution_available: true},
      time_intelligence_operations: ['as_of', 'range', 'period_to_date',
        'period_comparison'],
      time_intelligence_periods: ['day', 'week', 'month', 'quarter', 'year',
        'fiscal_quarter', 'fiscal_year'],
      analytical_window_operations: ['running_sum', 'moving_average', 'lag'],
      scheduled_report_execution: false,
      analytical_profile: {
        title: 'Relational and multidimensional',
        semantic_family: 'relational',
        source_kinds: ['table', 'view', 'materialized-view'],
        source_classifications: ['fact', 'dimension', 'bridge', 'lookup'],
        dimension_kinds: ['attribute', 'time', 'geography'],
        relationship_kinds: ['join', 'bridge'],
        measure_kinds: ['aggregate', 'calculated'],
        grain_vocabulary: 'fact-key',
      },
    },
  },
};
describe('MariaDB shared SQL session controls', () => {
  let api, observer;
  beforeEach(() => {
    observer = new MutationObserver(() => document.querySelectorAll('details').forEach(node => node.open = true));
    observer.observe(document.body, {childList: true, subtree: true});
    api = {get: jest.fn(), post: jest.fn()};
    getApiInstance.mockReturnValue(api);
    api.get.mockResolvedValue({data: {data: bootstrap}});
  });
  afterEach(() => observer.disconnect());
  it.each(['mariadb'])('observes %s autocommit and changes only acknowledged policy', async (engine) => {
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

  it('retains MariaDB dispatch timing and native diagnostics without inventing engine timing or a row result', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap, languages: [{
      language_profile: 'mariadb-sql', title: 'MariaDB SQL', starter_source: 'SELECT missing',
    }]}}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'mariadb-diagnostic'}, execute: {occurrence_id: 'mariadb-error'},
      poll: {occurrence: {operation: {terminal: true}, result: {extensions: {mariadb: {payload: {
        has_page: false, statement_metrics: {dispatch_ms: 12.5, prepare_ms: null, execute_ms: null, plan: null},
        error: {errno: 1054, sqlstate: '42S22', message_primary: 'Unknown column missing'},
      }}}}}, rendered_result: null},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1" initialTab="studio" />);
    const run = await screen.findByRole('button', {name: 'Run', exact: true});
    await waitFor(() => expect(run).toBeEnabled()); fireEvent.click(run);
    expect(await screen.findByLabelText('MariaDB diagnostic')).toHaveTextContent('1054');
    expect(screen.getByLabelText('MariaDB diagnostic')).toHaveTextContent('42S22');
    expect(screen.getByLabelText('MariaDB diagnostic')).toHaveTextContent('Unknown column missing');
    expect(screen.getByLabelText('Statement metrics')).toHaveTextContent('12.5 ms');
    expect(screen.getByLabelText('Statement metrics')).toHaveTextContent('Preparation: Unavailable');
    expect(screen.getByLabelText('Statement metrics')).toHaveTextContent('Execution: Unavailable');
    expect(screen.getByLabelText('Statement metrics')).toHaveTextContent('Plan used: Unavailable');
  });


});
