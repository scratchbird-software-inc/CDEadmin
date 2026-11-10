/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {act, fireEvent, screen, waitFor, within, useLayoutEffect, useState, render, bootstrap,
  ProviderWorkspaceContent, DatabaseTargetWorkspace, ObjectInspectorSection, ResultControls,
  RecordListAdminField, ServerProfileWorkspace, VisualAdministration, VisualAdminField,
  inspectorSections, initialObjectDraft, visibleFieldOptions, changedFieldDraft,
  administrationResourceId, administrationOutcomeValue, ProviderWorkspaceModule, modelFixtures,
  getApiInstance, requestSQLSource, firebirdManifest, installSharedHooks, installWorkspaceHooks,
} from './providerWorkspaceContentShared';

jest.mock('../../../pgadmin/static/js/api_instance');
// Execution contract tests use a text adapter; the native browser gate covers CodeMirror.
jest.mock('../../../pgadmin/static/js/cdeadmin_ui/editors/CodeEditor', () => ({__esModule: true,
  default: ({label, value, onChange, disabled}) => <textarea aria-label={label} value={value}
    disabled={disabled} onChange={event => onChange(event.target.value)} /> }));
// Hosted native renderers need a bounded readiness allowance; assertions and

installSharedHooks();

describe('ProviderWorkspaceContent (sessions, results and administration)', () => {
  const workspace = installWorkspaceHooks();
  let api;
  beforeEach(() => { api = workspace.api; });

  it('opens a provider session, executes and renders rows', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap,
      database_targets: {targets: [{target_id: 'database-one', database: 'example'}]},
    }}});
    api.post.mockImplementation((_url, payload) => {
      const values = {
        open_session: {session_id: 'session-one'},
        execute: {occurrence_id: 'occurrence-one'},
        poll: {
          occurrence: {operation: {terminal: true}},
          rendered_result: {
            component_reference: 'SchemaView/DataGridView',
            view_model: {
              columns: [{name: 'answer'}],
              rows: [{answer: 42}],
            },
          },
        },
      };
      return Promise.resolve({data: {data: values[payload.action]}});
    });
    render(<ProviderWorkspaceContent
      closeModal={jest.fn()}
      endpointUrl="/workspace/1"
      initialTab="studio"
      initialContext={{resource_id: 'database-one'}}
    />);
    expect(await screen.findByText('MySQL SQL')).toBeInTheDocument();
    expect(screen.queryByLabelText('Provider grid activation status')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    expect(await screen.findByText('42')).toBeInTheDocument();
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(3));
    expect(api.post.mock.calls.map((call) => call[1].action)).toEqual([
      'open_session', 'execute', 'poll',
    ]);
    expect(api.post.mock.calls.map((call) =>
      call[1].database_target_id
    )).toEqual(['database-one', 'database-one', 'database-one']);
  });

  it.each(['runtime', 'structural'])('keeps %s grid failures visibly expanded', async (failure) => {
    api.get.mockResolvedValue({data: {data: {...bootstrap,
      grid_workspace: {...bootstrap.grid_workspace,
        ...(failure === 'runtime' ? {runtime_gate: {state: 'failed'}} : {
          activation_gates: [{gate_id: 'column_contract', state: 'failed'}],
        }),
      },
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    await screen.findByText('MySQL SQL');
    const warning = screen.getByRole('alert', {name: 'Provider grid activation status'});
    expect(warning).toBeVisible();
    expect(warning).toHaveTextContent(failure === 'runtime' ?
      'live provider verification' : 'column_contract');
    expect(screen.queryByText('Grid checks passed')).not.toBeInTheDocument();
  });

  it('preserves a DuckDB decision and blocks replay when the next transaction fails', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      languages: [{language_profile: 'duckdb-sql', title: 'DuckDB SQL',
        starter_source: 'SELECT 1', transaction_actions: ['commit', 'rollback']}],
    }}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {
      data: payload.action === 'open_session' ? {session_id: 'duck-session'} : {
        session_id: 'duck-session', transaction_model: 'duckdb-native-transaction',
        provider_payload: {last_decision: 'commit', decision_returned: true,
          next_transaction_started: false, session_reuse_blocked: true},
      },
    }}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'commit', exact: true}));
    fireEvent.click(screen.getByRole('tab', {name: 'Messages'}));
    expect(await screen.findByText(/next_transaction_started/)).toBeVisible();
    expect(screen.getByRole('button', {name: 'Run', exact: true})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'commit', exact: true})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Close query session', exact: true})).toBeEnabled();
    expect(api.post.mock.calls.filter(([, payload]) =>
      payload.action === 'transaction_action')).toHaveLength(1);
  });

  it('uses provider transaction controls without inferring finality', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      languages: [{language_profile: 'mysql-sql', title: 'MySQL SQL',
        transaction_actions: ['commit', 'rollback']}],
    }}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {
      data: payload.action === 'open_session' ? {session_id: 'session-one'} : {
        session_id: 'session-one', transaction_model: 'mysql-native',
        authority_reference: 'provider:org.cdeadmin.mysql',
        provider_payload: {driver_observation_only: true},
      },
    }}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'commit', exact: true}));
    await waitFor(() => expect(api.post).toHaveBeenLastCalledWith(
      '/workspace/1', {
        action: 'transaction_action', session_id: 'session-one',
        transaction_action: 'commit',
        database_target_id: null,
      }
    ));
    expect(await screen.findByText(/driver_observation_only/))
      .toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Close query session', exact: true}));
    await waitFor(() => expect(api.post).toHaveBeenLastCalledWith(
      '/workspace/1', {
        action: 'close_session', session_id: 'session-one',
        database_target_id: null,
      }
    ));
    expect(screen.getByRole('button', {name: 'Close query session', exact: true})).toBeDisabled();
  });

  it('pages, exports, and compares endpoint-bound retained results', async () => {
    const rendered = {
      descriptor: {result_id: 'result-two', export_formats: ['json']},
      component_reference: 'SchemaView/DataGridView',
      page: {next_cursor: 'cursor-two', page_size: 1},
      view_model: {columns: [{name: 'answer'}], rows: [{answer: 42}]},
    };
    api.post.mockImplementation((_url, payload) => {
      const values = {
        open_session: {session_id: 'session-one'},
        execute: {occurrence_id: 'occurrence-one'},
        poll: {occurrence: {operation: {terminal: true}}, rendered_result: rendered},
        result_page: {...rendered, page: {next_cursor: null, page_size: 1},
          view_model: {columns: [{name: 'answer'}], rows: [{answer: 43}]}},
        result_export: {content_base64: 'W3siYW5zd2VyIjo0Mn1d',
          media_type: 'application/json', filename: 'result.json'},
      };
      return Promise.resolve({data: {data: values[payload.action]}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    fireEvent.click(await screen.findByRole('button', {name: 'Next result page'}));
    expect(await screen.findByText('43')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Export JSON'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', {
      action: 'result_export', request: {
        result_id: 'result-two', format: 'json',
      },
    }));
  });

  it('renders document results as a structured JSON tree', async () => {
    const documentBootstrap = {
      ...bootstrap,
      endpoint: {
        provider_id: 'org.cdeadmin.mongodb',
        verified_runtime_family: 'mongodb',
      },
      languages: [{
        language_profile: 'mongodb-query-api-json',
        title: 'MongoDB Query API (JSON)',
        starter_source: '{"operation":"command","database":"admin","command":{"ping":1}}',
      }],
    };
    api.get.mockResolvedValue({data: {data: documentBootstrap}});
    api.post.mockImplementation((_url, payload) => {
      const values = {
        open_session: {session_id: 'mongo-session'},
        execute: {occurrence_id: 'mongo-operation'},
        poll: {
          occurrence: {operation: {terminal: true}},
          rendered_result: {
            component_reference: 'cdeadmin/results/DocumentTreeView',
            view_model: {
              family: 'document',
              records: [{_id: {$oid: '0123456789abcdef01234567'}, value: 42}],
            },
          },
        },
      };
      return Promise.resolve({data: {data: values[payload.action]}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    const results = await screen.findByLabelText('Document results');
    fireEvent.click(screen.getByRole('tab', {name: 'Messages'}));
    expect(results).not.toBeVisible();
    fireEvent.click(screen.getByRole('tab', {name: 'Data Output'}));
    expect(screen.getByLabelText('Document results')).toBe(results);
    expect(results).toBeVisible();
    expect(results).toHaveTextContent('0123456789abcdef01234567');
    expect(results).toHaveTextContent('42');
  });

  it('renders Neo4j graph results with an accessible element table', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      endpoint: {provider_id: 'org.cdeadmin.neo4j', verified_runtime_family: 'neo4j'},
      languages: [{
        language_profile: 'cypher', title: 'Cypher',
        starter_source: 'RETURN 1 AS value',
      }],
      visual_admin: {...bootstrap.visual_admin, model_family: 'graph'},
    }}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'neo4j-session'},
      execute: {occurrence_id: 'neo4j-operation'},
      poll: {
        occurrence: {operation: {terminal: true}},
        rendered_result: {
          component_reference: 'cdeadmin/results/GraphView',
          view_model: {family: 'graph', records: [{
            n: {kind: 'node', element_id: '4:one', labels: ['Person'],
              properties: {name: 'Alice'}},
          }]},
        },
      },
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    const results = await screen.findByLabelText('Graph results');
    expect(results).toHaveTextContent('Person');
    expect(results).toHaveTextContent('Alice');
    expect(screen.getByLabelText('Neo4j graph visualization')).toBeInTheDocument();
  });

  it('renders Cassandra wide-column results with native CQL types', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      endpoint: {
        provider_id: 'org.cdeadmin.cassandra',
        verified_runtime_family: 'cassandra',
      },
      languages: [{
        language_profile: 'cql-3', title: 'CQL 3',
        starter_source: 'SELECT cluster_name FROM system.local',
      }],
      visual_admin: {...bootstrap.visual_admin, model_family: 'wide-column'},
    }}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'cassandra-session'},
      execute: {occurrence_id: 'cassandra-operation'},
      poll: {
        occurrence: {operation: {terminal: true}},
        rendered_result: {
          component_reference: 'cdeadmin/results/WideColumnView',
          view_model: {
            family: 'wide_column',
            columns: [{name: 'tenant', type: 'text'},
              {name: 'payload', type: 'blob'}],
            rows: [{tenant: 'north', payload: {$binary: 'Ynl0ZXM='}}],
            native_observation: {warnings: ['Replica observation warning']},
          },
        },
      },
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    const results = await screen.findByLabelText('Wide-column results');
    expect(results).toHaveTextContent('tenant');
    expect(results).toHaveTextContent('blob');
    expect(results).toHaveTextContent('Ynl0ZXM=');
    expect(results).toHaveTextContent('Replica observation warning');
  });

  it('renders ClickHouse columnar results with native types', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      endpoint: {
        provider_id: 'org.cdeadmin.clickhouse',
        verified_runtime_family: 'clickhouse',
      },
      languages: [{
        language_profile: 'clickhouse-sql', title: 'ClickHouse SQL',
        starter_source: 'SELECT version() AS version',
      }],
      visual_admin: {
        ...bootstrap.visual_admin, model_family: 'columnar-analytic',
      },
    }}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'clickhouse-session'},
      execute: {occurrence_id: 'clickhouse-operation'},
      poll: {
        occurrence: {operation: {terminal: true}},
        rendered_result: {
          component_reference: 'cdeadmin/results/ColumnarView',
          view_model: {
            family: 'columnar',
            columns: [{name: 'category', type: 'LowCardinality(String)'},
              {name: 'total', type: 'Int64'}],
            rows: [{category: 'one', total: 30}],
            statistics: {rows_read: 3},
          },
        },
      },
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    const results = await screen.findByLabelText('Columnar results');
    expect(results).toHaveTextContent('category');
    expect(results).toHaveTextContent('LowCardinality(String)');
    expect(results).toHaveTextContent('one');
    expect(results).toHaveTextContent('30');
  });

  it.each([
    ['firebird-native', false], ['firebird-embedded', false],
    ['firebird-native', true], ['firebird-embedded', true],
    ['mysql-native', false], ['mysql-native', true],
  ])('surfaces prepared recovery only for its engine: %s tabbed=%s', async (profile, tabbed) => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap, endpoint: {...bootstrap.endpoint, profile_id: profile},
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="administration"
      initialContext={{composition_mode: tabbed ? 'tabbed' : 'focused'}} />);
    await screen.findByRole('textbox', {name: /Name/});
    const entry = screen.queryByRole(tabbed ? 'tab' : 'button', {name: 'Prepared Transaction Recovery'});
    if (profile.startsWith('firebird')) {
      expect(entry).toBeInTheDocument();
      fireEvent.click(entry);
      expect(await screen.findByRole('region', {name: 'Coordinated Firebird recovery'})).toBeInTheDocument();
    } else {
      expect(entry).not.toBeInTheDocument();
    }
  });

  it('renders provider-declared administration forms and blocked plans', async () => {
    api.post.mockImplementation((_url, payload) => {
      if (payload.action === 'visual_admin_validate') {
        return Promise.resolve({data: {data: {valid: true, errors: []}}});
      }
      return Promise.resolve({data: {data: {
        state: 'blocked',
        execution_available: false,
        blockers: ['provider_native_planner_unavailable'],
      }}});
    });
    render(<ProviderWorkspaceContent
      closeModal={jest.fn()}
      endpointUrl="/workspace/1"
      initialTab="administration"
    />);
    const nameField = await screen.findByRole('textbox', {name: /Name/});
    expect(nameField).toBeInTheDocument();
    fireEvent.change(nameField, {target: {value: 'sample'}});
    fireEvent.click(screen.getByText('Validate and preview'));
    expect(await screen.findByLabelText('Provider plan preview')).toHaveTextContent(
      'provider_native_planner_unavailable'
    );
    expect(screen.getByText('Apply provider plan')).toBeDisabled();
  });

  it('opens a context command as one focused provider task form', async () => {
    render(<ProviderWorkspaceContent
      closeModal={jest.fn()}
      endpointUrl="/workspace/1"
      initialTab="administration"
      initialContext={{resource_kind: 'database', operation_id: 'create'}}
    />);
    expect(await screen.findByRole('heading', {name: 'Create'}))
      .toBeInTheDocument();
    expect(screen.queryByLabelText('Object type')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Operation')).not.toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    const section = screen.getByRole('region', {name: 'Engine task form'});
    expect(section).toHaveStyle({minWidth: '0'});
    expect(section.parentElement).toHaveStyle({gridTemplateColumns: 'minmax(0, 1fr)'});
  });

  it('shows provider-owned administration observations', async () => {
    const readyBootstrap = {
      ...bootstrap,
      visual_admin: {
        ...bootstrap.visual_admin,
        objects: [{
          ...bootstrap.visual_admin.objects[0],
          operations: [{
            ...bootstrap.visual_admin.objects[0].operations[0], blockers: [],
          }],
        }],
      },
    };
    api.get.mockResolvedValue({data: {data: readyBootstrap}});
    api.post.mockImplementation((_url, payload) => {
      const responses = {
        visual_admin_validate: {valid: true, errors: []},
        visual_admin_plan: {
          state: 'ready', execution_available: true,
          plan_id: 'plan-one', plan_digest: 'digest-one',
        },
        visual_admin_apply: {
          provider_result: {
            acknowledged: true, local_process_observation_only: true,
          },
        },
      };
      return Promise.resolve({data: {data: responses[payload.action]}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="administration" />);
    fireEvent.change(await screen.findByRole('textbox', {name: /Name/}), {
      target: {value: 'sample'},
    });
    fireEvent.click(screen.getByText('Validate and preview'));
    await screen.findByLabelText('Provider plan preview');
    fireEvent.click(screen.getByText('Apply provider plan'));
    const result = await screen.findByLabelText('Provider operation result');
    expect(result).toHaveTextContent('local_process_observation_only');
    expect(result).toHaveTextContent('true');
  });

  it.each([false, true])('shows native completion and registration failure=%s separately', async (registrationFailed) => {
    const createForm = {
      form_id: 'cdeadmin.mysql-native.database.create.v1',
      operation_id: 'create', title: 'Create database', supported: true,
      fields: [{
        field_id: 'name', label: 'Name', control: 'text', required: true,
      }, {
        field_id: 'definition', label: 'Provider-native definition',
        control: 'code', required: false,
      }, {
        field_id: 'options', label: 'Execution options', control: 'json',
        required: false, default: {},
      }],
    };
    const databaseTargets = {
      multiple: true, target_management: true, server_verification: true,
      active_target_id: null, legacy_route_database: null, targets: [],
      forms: {
        form_set_id: 'cdeadmin.mysql-native.database.forms.v1',
        lifecycle_resource_kind: 'database',
        forms: {create: createForm},
      },
    };
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      endpoint: {
        ...bootstrap.endpoint, route_management_available: true,
      },
      database_targets: databaseTargets,
      visual_admin: {
        ...bootstrap.visual_admin,
        objects: [{
          ...bootstrap.visual_admin.objects[0],
          operations: [{
            ...bootstrap.visual_admin.objects[0].operations[0],
            blockers: [], execution_available: true,
          }],
        }],
      },
    }}});
    api.post.mockImplementation((_url, payload) => {
      const responses = {
        route_list: {
          supports_multiple_routes: false, default_port: 3050,
          database_targeting: {multiple: true}, connection_fields: [],
          routes: [{
            route_id: 'route-one', priority: 1,
            configuration: {host: 'localhost', port: 3050, user: 'SYSDBA'},
            health: {},
          }],
        },
        visual_admin_validate: {valid: true, errors: []},
        visual_admin_plan: {
          state: 'ready', execution_available: true,
          plan_id: 'database-plan', plan_digest: 'database-digest',
        },
        visual_admin_apply: {
          provider_result: {driver_returned: true},
          workspace_follow_up: registrationFailed ? [{
            action: 'register_created_database', state: 'failed',
            message: 'Local registration failed. Do not repeat native creation.',
          }] : [],
          database_targets: registrationFailed ? undefined : {
            ...databaseTargets, active_target_id: 'database-one',
            targets: [{
              target_id: 'database-one', active: true,
              display_name: 'sample.fdb', database: '/data/sample.fdb',
            }],
          },
        },
        resource_refresh: bootstrap.resource_page,
      };
      return Promise.resolve({data: {data: responses[payload.action]}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="connections" />);
    fireEvent.change(await screen.findByRole('textbox', {name: /Name/}), {
      target: {value: 'sample.fdb'},
    });
    fireEvent.click(screen.getByText('Validate and preview'));
    await screen.findByText(/database-plan/);
    fireEvent.click(screen.getByRole('button', {name: 'Create database'}));
    expect(await screen.findByText(/completed the native database operation/))
      .toBeInTheDocument();
    if(registrationFailed) {
      expect(screen.getByText('Local registration failed. Do not repeat native creation.'))
        .toBeInTheDocument();
    }
    expect(screen.getByRole('button', {name: 'Create database'})).toBeDisabled();
    expect(api.post).toHaveBeenCalledWith('/workspace/1', {
      action: 'visual_admin_apply', request: {
        plan_id: 'database-plan', plan_digest: 'database-digest',
        confirmed: false,
      },
    });
  });

  it('renders and submits typed provider multiselect fields', async () => {
    const readyBootstrap = {
      ...bootstrap,
      visual_admin: {
        ...bootstrap.visual_admin,
        objects: [{
          resource_kind: 'permission', title: 'Permission', operations: [{
            operation_id: 'grant_sql', title: 'Grant SQL privileges',
            mutation_class: 'security', target_required: false,
            confirmation_required: false, blockers: [],
            form: {fields: [
              {field_id: 'username', label: 'User', control: 'text',
                required: true},
              {field_id: 'privileges', label: 'Privileges',
                control: 'multiselect', required: true, options: [
                  {value: 'SELECT', label: 'SELECT'},
                  {value: 'INSERT', label: 'INSERT'},
                ]},
            ]},
          }],
        }],
      },
    };
    api.get.mockResolvedValue({data: {data: readyBootstrap}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {
      data: payload.action === 'visual_admin_validate' ?
        {valid: true, errors: []} : {
          state: 'ready', execution_available: true,
          plan_id: 'permission-plan', plan_digest: 'permission-digest',
        },
    }}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="administration" />);
    fireEvent.change(await screen.findByRole('textbox', {name: /User/}), {
      target: {value: 'operator'},
    });
    const privileges = screen.getByRole('combobox', {name: /Privileges/});
    const selectInput = privileges.parentElement.querySelector('input');
    fireEvent.change(selectInput, {target: {value: 'SELECT'}});
    fireEvent.click(screen.getByText('Validate and preview'));
    await screen.findByLabelText('Provider plan preview');
    expect(api.post.mock.calls[0][1].request.draft).toEqual({
      username: 'operator', privileges: ['SELECT'],
    });
  });

  it('shows durable operations as review-only after provider restart', async () => {
    api.post.mockResolvedValue({data: {data: {
      restart_safe_audit: true,
      items: [{
        operation_id: 'operation-one', operation_kind: 'backup',
        resource_kind: 'database', stage: 'completed', durable_audit: true,
        live_provider_handle_available: false, cancellable: true,
        provider_finality_authority: true,
        automatic_mutation_retry: false,
      }],
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="operations" />);
    fireEvent.mouseDown(await screen.findByRole('combobox', {name: 'Workspace'}));
    fireEvent.click(screen.getByRole('option', {name: 'Operation progress and history'}));
    expect(await screen.findByText(/restart-safe audit record/)).toBeInTheDocument();
    expect(screen.getByText('Observe provider state')).toBeDisabled();
    expect(screen.getByText('Request cancellation')).toBeDisabled();
    expect(screen.getByText('Validate post-state')).toBeDisabled();
  });

  it('renders provider-declared operational facets and commands', async () => {
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="operations" />);
    expect(await screen.findByRole('heading', {name: 'Server and cluster health'})).toBeInTheDocument();
    expect(screen.getByRole('combobox', {name: 'Workspace'})).toHaveTextContent('Server and cluster health');
    expect(screen.getByText('Provider observations')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Validate and preview'}))
      .toBeInTheDocument();
    expect(screen.getByText(/does not infer success/)).toBeInTheDocument();
  });

});

