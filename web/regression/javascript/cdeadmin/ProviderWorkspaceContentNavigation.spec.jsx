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

describe('ProviderWorkspaceContent (resources, navigation and tasks)', () => {
  const workspace = installWorkspaceHooks();
  let api;
  beforeEach(() => { api = workspace.api; });

  it('loads provider resources through the workspace endpoint and hands navigation to the tree', async () => {
    render(<ProviderWorkspaceContent
      closeModal={jest.fn()}
      endpointUrl="/workspace/1"
    />);
    // The Object Explorer tree is the navigator; the workspace carries no object list.
    expect(await screen.findByRole('region', {name: 'Object navigation'}))
      .toHaveTextContent('listed in the Object Explorer tree');
    expect(screen.getByText('1 objects in the current catalog page.')).toBeInTheDocument();
    expect(screen.queryByRole('treeitem')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Filter provider objects')).not.toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/workspace/1');
  });

  it.each(['first-page', 'outside-page'])(
    'retains the natively renamed domain on the %s for the next edit', async (location) => {
      const warnings = jest.spyOn(console, 'warn');
      const original = {resource_id: 'domain:D', resource_kind: 'domain',
        display_name: 'D', display_path: ['D']};
      const renamed = {...original, resource_id: 'domain:E',
        display_name: 'E', display_path: ['E']};
      api.get.mockResolvedValue({data: {data: {...bootstrap,
        resource_page: {generation: 'old', items: [original]},
        visual_admin: {objects: [{resource_kind: 'domain', title: 'Domain',
          operations: [{operation_id: 'rename', title: 'Rename domain',
            target_required: true, form: {fields: [{field_id: 'new_name',
              label: 'New name', control: 'text', required: true}]}}]}]},
      }}});
      api.post.mockImplementation(async (_url, {action, request}) => {
        let value;
        if (action === 'resource_inspect') {
          value = request.resource_id === renamed.resource_id ? renamed : original;
        } else if (action === 'visual_admin_validate') {
          value = {valid: true};
        } else if (action === 'visual_admin_plan') {
          value = {plan_id: 'plan', plan_digest: 'digest',
            state: 'ready', execution_available: true};
        } else if (action === 'visual_admin_apply') {
          value = {provider_result: {resource_identity_change: {
            resource_kind: 'domain', previous_resource_id: original.resource_id,
            resource_id: renamed.resource_id, native_identity_verified: true,
            committed_by_provider: true,
          }}};
        } else if (action === 'resource_page') {
          value = {generation: 'new', items: location === 'first-page' ?
            [renamed] : [], next_cursor: 'remaining'};
        } else {
          throw new Error('Unexpected action ' + action);
        }
        return {data: {data: value}};
      });
      render(<ProviderWorkspaceContent endpointUrl="/workspace/1"
        initialTab="administration" initialContext={{resource_id: 'domain:D',
          resource_kind: 'domain', operation_id: 'rename'}} />);
      fireEvent.change(await screen.findByRole('textbox', {name: 'New name'}),
        {target: {value: 'E'}});
      await waitFor(() => expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeEnabled());
      fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
      await waitFor(() => expect(screen.getByRole('button',
        {name: 'Apply provider plan'})).toBeEnabled());
      fireEvent.click(screen.getByRole('button', {name: 'Apply provider plan'}));
      await waitFor(() => expect(screen.getByRole('button',
        {name: 'Validate and preview'})).toBeEnabled());
      expect(screen.getByLabelText('Provider operation result')).toHaveTextContent('domain:E');
      expect(screen.queryByLabelText('Provider plan preview')).not.toBeInTheDocument();
      expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
      fireEvent.change(screen.getByRole('textbox', {name: 'New name'}),
        {target: {value: 'D'}});
      fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
      await waitFor(() => expect(api.post).toHaveBeenCalledWith('/workspace/1', {
        action: 'visual_admin_plan', request: {
          resource_kind: 'domain', operation_id: 'rename',
          target_resource: renamed, draft: {new_name: 'D'},
        },
      }));
      expect(screen.queryByText(/No discovered resource of this type/)).toBeNull();
      expect(warnings.mock.calls.filter(args =>
        String(args[0]).includes('out-of-range value'))).toHaveLength(0);
    });

  it.each(['domain', 'column', 'role'])(
    'blocks %s actions in the render where a selected target disappears', async (kind) => {
      const catalog = {objects: [{resource_kind: kind, title: kind,
        operations: [{operation_id: 'rename', title: 'Rename', target_required: true,
          form: {fields: [{field_id: 'new_name', label: 'New name', control: 'text'}]}}]}]};
      const post = jest.fn().mockImplementation(async ({action}) =>
        action === 'visual_admin_validate' ? {valid: true} :
          {plan_id: 'owned-plan', plan_digest: 'owned-digest', state: 'ready', execution_available: true});
      const snapshots = [];
      function Observe({resources}) {
        useLayoutEffect(() => {
          snapshots.push({
            target: screen.getByRole('combobox', {name: 'Target resource'}).textContent,
            previewDisabled: screen.getByRole('button', {name: 'Validate and preview'}).disabled,
            applyDisabled: screen.getByRole('button', {name: 'Apply provider plan'}).disabled,
          });
        }, [resources]);
        return <VisualAdministration catalog={catalog} resources={resources}
          post={post} setError={jest.fn()} />;
      }
      const {rerender} = render(<Observe resources={[{resource_id: kind + ':D',
        resource_kind: kind, display_name: 'D'}]} />);
      fireEvent.change(screen.getByRole('textbox', {name: 'New name'}),
        {target: {value: 'E'}});
      fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
      await waitFor(() => expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeEnabled());
      const calls = post.mock.calls.length;
      rerender(<Observe resources={[]} />);
      expect(snapshots.at(-1).target).not.toContain('D');
      expect(snapshots.at(-1).previewDisabled).toBe(true);
      expect(snapshots.at(-1).applyDisabled).toBe(true);
      fireEvent.click(screen.getByRole('button', {name: 'Apply provider plan'}));
      fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
      expect(post).toHaveBeenCalledTimes(calls);
    });

  it.each(['unrelated', 'unverified', 'different-operation', 'different-connection'])(
    'does not present a completed receipt under %s context', async (change) => {
      const original = {resource_id: 'domain:D', resource_kind: 'domain', display_name: 'D'};
      const renamed = {...original, resource_id: 'domain:E', display_name: 'E'};
      const unrelated = {...original, resource_id: 'domain:F', display_name: 'F'};
      const resources = [original, renamed, unrelated];
      const catalog = {objects: [{resource_kind: 'domain', title: 'Domain',
        operations: ['rename', 'alter'].map(operation_id => ({operation_id,
          title: operation_id, target_required: true, form: {fields: []}}))}]};
      const post = jest.fn(async ({action, request}) => {
        if (action === 'resource_inspect') return resources.find(item => item.resource_id === request.resource_id);
        if (action === 'visual_admin_validate') return {valid: true};
        if (action === 'visual_admin_plan') return {plan_id: 'plan', plan_digest: 'digest',
          state: 'ready', execution_available: true};
        return {provider_result: {accepted: true, resource_identity_change: {
          resource_kind: 'domain', previous_resource_id: original.resource_id,
          resource_id: renamed.resource_id, committed_by_provider: true,
          native_identity_verified: change !== 'unverified',
        }}};
      });
      const props = {catalog, resources, post, setError: jest.fn(),
        onMutationApplied: jest.fn(), initialOperationId: 'rename'};
      const {rerender} = render(<VisualAdministration {...props} selectedResource={original} />);
      await act(async () => {});
      fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
      await waitFor(() => expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeEnabled());
      fireEvent.click(screen.getByRole('button', {name: 'Apply provider plan'}));
      expect(await screen.findByLabelText('Provider operation result')).toHaveTextContent('"accepted": true');
      await act(async () => {
        rerender(<VisualAdministration {...props}
          initialOperationId={change === 'different-operation' ? 'alter' : 'rename'}
          post={change === 'different-connection' ? (body) => post(body) : post}
          selectedResource={change === 'unrelated' ? unrelated :
            change === 'unverified' ? renamed : original} />);
      });
      expect(screen.queryByLabelText('Provider operation result')).not.toBeInTheDocument();
      expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
      fireEvent.click(screen.getByRole('button', {name: 'Apply provider plan'}));
      expect(post.mock.calls.filter(([body]) => body.action === 'visual_admin_apply')).toHaveLength(1);
    });

  it.each([
    ['visual_admin_validate', 'target'], ['visual_admin_plan', 'target'],
    ['visual_admin_validate', 'generation'], ['visual_admin_plan', 'generation'],
    ['visual_admin_validate', 'transport'], ['visual_admin_plan', 'transport'],
    ['visual_admin_validate', 'catalog'], ['visual_admin_plan', 'catalog'],
  ])('discards delayed %s after %s changes', async (stage, change) => {
    const first = {resource_id: 'sequence:A', resource_kind: 'sequence', display_name: 'A'};
    const second = {...first, resource_id: 'sequence:B', display_name: 'B'};
    const catalog = {objects: [{resource_kind: 'sequence', title: 'Sequence',
      operations: [{operation_id: 'alter', title: 'Alter', target_required: true,
        form: {fields: [{field_id: 'description', label: 'Comment', control: 'text'}]}}]}]};
    let release;
    let held = false;
    const oldResponse = new Promise(resolve => { release = resolve; });
    const ready = {plan_id: 'fresh-plan', plan_digest: 'fresh-digest',
      state: 'ready', execution_available: true};
    const post = jest.fn(async ({action, request}) => {
      if (action === 'resource_inspect') return request.resource_id === first.resource_id ? first : second;
      if (action === stage && !held) {
        held = true;
        return oldResponse;
      }
      if (action === 'visual_admin_validate') return {valid: true};
      if (action === 'visual_admin_plan') return ready;
      return {provider_result: {accepted: true}};
    });
    const props = {catalog, resources: [first, second], post, setError: jest.fn(),
      initialOperationId: 'alter', initialResourceKind: 'sequence'};
    const {rerender} = render(<VisualAdministration {...props}
      selectedResource={first} resourceGeneration="g1" />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeEnabled());
    fireEvent.change(screen.getByRole('textbox', {name: 'Comment'}), {target: {value: 'original draft'}});
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(held).toBe(true));
    const next = change === 'target' ? second : first;
    rerender(<VisualAdministration {...props} selectedResource={next}
      post={change === 'transport' ? (body) => post(body) : post}
      catalog={change === 'catalog' ? {...catalog} : catalog}
      resourceGeneration={change === 'generation' ? 'g2' : 'g1'} />);
    await waitFor(() => expect(post.mock.calls.filter(([body]) =>
      body.action === 'resource_inspect')).toHaveLength(change === 'catalog' ? 1 : 2));
    await act(async () => {
      release(stage === 'visual_admin_validate' ? {valid: true} :
        {...ready, plan_id: 'obsolete-plan'});
    });
    expect(screen.queryByLabelText('Provider plan preview')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
    if (stage === 'visual_admin_validate') {
      expect(post.mock.calls.filter(([body]) => body.action === 'visual_admin_plan')).toHaveLength(0);
    }
    fireEvent.change(screen.getByRole('textbox', {name: 'Comment'}), {target: {value: 'new draft'}});
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeEnabled());
    expect(post).toHaveBeenLastCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'sequence', operation_id: 'alter', target_resource: next,
      draft: {description: 'new draft'},
    }});
  });

  it.each(['target', 'generation', 'transport', 'catalog'])(
    'retires an existing plan in the same render as a %s change', async (change) => {
      const first = {resource_id: 'sequence:A', resource_kind: 'sequence', display_name: 'A'};
      const second = {...first, resource_id: 'sequence:B', display_name: 'B'};
      const catalog = {objects: [{resource_kind: 'sequence', title: 'Sequence',
        operations: [{operation_id: 'alter', title: 'Alter', target_required: true,
          form: {fields: []}}]}]};
      const post = jest.fn(async ({action, request}) => {
        if (action === 'resource_inspect') return request.resource_id === first.resource_id ? first : second;
        if (action === 'visual_admin_validate') return {valid: true};
        return {plan_id: 'old-plan', plan_digest: 'old-digest', state: 'ready', execution_available: true};
      });
      const snapshots = [];
      const setError = jest.fn();
      function Observe({changed}) {
        useLayoutEffect(() => {
          snapshots.push({preview: screen.queryByLabelText('Provider plan preview'),
            disabled: screen.getByRole('button', {name: 'Apply provider plan'}).disabled});
        }, [changed]);
        return <VisualAdministration catalog={changed && change === 'catalog' ? {...catalog} : catalog}
          resources={[first, second]} selectedResource={changed && change === 'target' ? second : first}
          resourceGeneration={changed && change === 'generation' ? 'g2' : 'g1'}
          post={changed && change === 'transport' ? (body) => post(body) : post}
          setError={setError} />;
      }
      const {rerender} = render(<Observe changed={false} />);
      await waitFor(() => expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeEnabled());
      await act(async () => {});
      await act(async () => {
        fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
      });
      expect(setError.mock.calls).toEqual([[null]]);
      expect(post.mock.calls.map(([body]) => body.action)).toEqual([
        'resource_inspect', 'visual_admin_validate', 'visual_admin_plan']);
      await waitFor(() => expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeEnabled());
      await act(async () => { rerender(<Observe changed />); });
      expect(snapshots.at(-1)).toEqual({preview: null, disabled: true});
      fireEvent.click(screen.getByRole('button', {name: 'Apply provider plan'}));
      expect(post.mock.calls.filter(([body]) => body.action === 'visual_admin_apply')).toHaveLength(0);
    });

  it.each(['invalid', 'validate-error', 'plan-error', 'unmounted'])(
    'does not publish obsolete %s preview feedback', async (outcome) => {
      const catalog = {objects: [{resource_kind: 'database', title: 'Database',
        operations: [{operation_id: 'create', title: 'Create', target_required: false,
          form: {fields: []}}]}]};
      let release, reject;
      const pending = new Promise((resolve, fail) => { release = resolve; reject = fail; });
      const post = jest.fn(async ({action}) => {
        if (action === 'visual_admin_validate' && outcome === 'plan-error') return {valid: true};
        return pending;
      });
      const setError = jest.fn();
      const {rerender, unmount} = render(<VisualAdministration catalog={catalog}
        resources={[]} post={post} setError={setError} resourceGeneration="g1" />);
      fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
      await waitFor(() => expect(post).toHaveBeenCalledTimes(outcome === 'plan-error' ? 2 : 1));
      if (outcome === 'unmounted') unmount();
      else rerender(<VisualAdministration catalog={catalog} resources={[]}
        post={post} setError={setError} resourceGeneration="g2" />);
      await act(async () => {
        if (outcome.endsWith('-error')) reject(new Error('Obsolete failure'));
        else release(outcome === 'unmounted' ? {valid: true} :
          {valid: false, errors: [{message: 'Obsolete validation'}]});
      });
      expect(screen.queryByText('Obsolete validation')).not.toBeInTheDocument();
      expect(setError).not.toHaveBeenCalledWith('Obsolete failure');
      expect(post).toHaveBeenCalledTimes(outcome === 'plan-error' ? 2 : 1);
    });

  it('requests credentials and reloads after a workspace 401', async () => {
    const onCredentialRequired = jest.fn();
    api.get
      .mockRejectedValueOnce({response: {status: 401}})
      .mockResolvedValueOnce({data: {data: bootstrap}});
    render(<ProviderWorkspaceContent
      closeModal={jest.fn()}
      endpointUrl="/workspace/1"
      onCredentialRequired={onCredentialRequired}
    />);
    await waitFor(() => expect(onCredentialRequired).toHaveBeenCalledTimes(1));
    expect(onCredentialRequired).toHaveBeenCalledWith(expect.any(Function));
    await act(async () => {
      onCredentialRequired.mock.calls[0][0]();
    });
    expect(await screen.findByRole('region', {name: 'Object navigation'})).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it('does not invent a generic SQL starter for a provider dialect', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      languages: [{language_profile: 'unproven-sql', title: 'Unproven SQL'}],
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    expect(await screen.findByText(
      /has not supplied an evidence-bound query template/
    )).toBeInTheDocument();
    expect(screen.getByLabelText('Query source')).toHaveValue('');
    expect(screen.queryByDisplayValue('SELECT 1')).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', {name: 'Explain'})).not.toBeInTheDocument();
    expect(screen.getByRole('tab', {name: 'Data Output'})).toHaveAttribute('aria-selected', 'true');
    fireEvent.change(screen.getByLabelText('Query source'), {
      target: {value: 'provider-owned user source'},
    });
    expect(screen.queryByText(/editor is intentionally empty/)).not.toBeInTheDocument();
  });

  it('shows workspace tabs only for explicit drag-drop composition', async () => {
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1"
      initialContext={{composition_mode: 'tabbed'}} />);
    expect(await screen.findByRole('tab', {name: 'Resource Explorer'}))
      .toBeInTheDocument();
  });

  it('uses a focused provider database dialog without workspace tabs', async () => {
    const createFields = [
      {field_id: 'database_path', label: 'Absolute database filename on the Firebird server', control: 'text', required: true},
      {field_id: 'page_size', label: 'Page size', control: 'select', required: false, default: '8192', options: [
        {value: '4096', label: '4096'}, {value: '8192', label: '8192'},
      ]},
      {field_id: 'default_charset', label: 'Default character set', control: 'text', required: false, default: 'UTF8'},
      {field_id: 'sql_dialect', label: 'Database SQL dialect', control: 'select', required: false, default: '3', options: [
        {value: '1', label: '1'}, {value: '3', label: '3'},
      ]},
    ];
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      database_targets: {
        form_set_id: 'unused', target_management: true, targets: [],
        forms: {
          form_set_id: 'cdeadmin.firebird-native.database.forms.v1',
          lifecycle_resource_kind: 'database',
          forms: {create: {
            form_id: 'cdeadmin.firebird-native.database.create.v1',
            operation_id: 'create', title: 'Create Firebird database',
            supported: true, fields: createFields,
          }},
        },
      },
      visual_admin: {
        engine_id: 'firebird', engine_name: 'Firebird', objects: [{
          resource_kind: 'database', title: 'Database', operations: [{
            operation_id: 'create', title: 'Create Firebird database',
            execution_available: true, target_required: false,
            confirmation_required: false,
            form: {form_id: 'firebird_database_create', fields: createFields},
          }],
        }],
      },
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="connections"
      initialContext={{database_mode: 'create'}} />);
    expect(await screen.findByRole('heading', {
      name: 'Create Firebird database',
    })).toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', {name: 'Page size'}))
      .toHaveTextContent('8192');
    expect(screen.queryByText(/Cubes & Semantic Models/))
      .not.toBeInTheDocument();
  });

  it('maps a database target UUID to its sole provider database resource', async () => {
    const operation = {
      operation_id: 'backup_logical', title: 'Logical backup (gbak)',
      mutation_class: 'admin', target_required: true,
      target_resource_kinds: ['database'], confirmation_required: false,
      execution_available: true, graphical_ready: true, blockers: [],
      form: {form_id: 'firebird_backup_logical', fields: [{
        field_id: 'backup_file',
        label: 'Backup filename on the Firebird server',
        control: 'text', required: true,
      }]},
    };
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      database_targets: {targets: [{target_id: 'retained-database-target-uuid',
        database: '/owned/cdeadmin_demo.fdb'}]},
      endpoint: {
        provider_id: 'org.cdeadmin.firebird',
        verified_runtime_family: 'firebird',
      },
      resource_page: {items: [{
        resource_id: 'database:cdeadmin_demo.fdb',
        resource_kind: 'database', display_name: 'cdeadmin_demo.fdb',
        authority_path: ['database', 'cdeadmin_demo.fdb'],
      }]},
      visual_admin: {
        engine_id: 'firebird', engine_name: 'Firebird', objects: [{
          resource_kind: 'database', title: 'Database',
          operations: [operation],
        }],
      },
    }}});
    api.post.mockResolvedValue({data: {data: {
      resource_id: 'database:cdeadmin_demo.fdb',
      resource_kind: 'database', display_name: 'cdeadmin_demo.fdb',
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="administration"
      initialContext={{
        resource_id: 'retained-database-target-uuid',
        resource_kind: 'database', operation_id: 'backup_logical',
      }} />);
    expect(await screen.findByRole('heading', {
      name: 'Logical backup (gbak)',
    })).toBeInTheDocument();
    expect(screen.getByRole('combobox', {name: 'Target resource'}))
      .toHaveTextContent('cdeadmin_demo.fdb');
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/workspace/1', {action: 'resource_inspect', request: {
        resource_id: 'database:cdeadmin_demo.fdb', generation: undefined,
        database_target_id: 'retained-database-target-uuid',
      }}
    ));
  });

  it('keeps the context-selected provider resource when peers share its kind', async () => {
    const operation = {
      operation_id: 'set_global', title: 'Set runtime global value',
      mutation_class: 'admin', target_required: true,
      confirmation_required: false, execution_available: true,
      graphical_ready: true, blockers: [],
      form: {form_id: 'mariadb_set_global', fields: []},
    };
    const resources = [{
      resource_id: 'system-variable:READ_ONLY',
      resource_kind: 'system-variable', display_name: 'READ_ONLY',
      authority_path: ['Configuration', 'system-variable', 'READ_ONLY'],
    }, {
      resource_id: 'system-variable:MAX_CONNECTIONS',
      resource_kind: 'system-variable', display_name: 'MAX_CONNECTIONS',
      authority_path: [
        'Configuration', 'system-variable', 'MAX_CONNECTIONS',
      ],
    }];
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      resource_page: {items: resources},
      visual_admin: {
        engine_id: 'mariadb', engine_name: 'MariaDB', objects: [{
          resource_kind: 'system-variable', title: 'System variable',
          operations: [operation],
        }],
      },
    }}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {
      data: resources.find((item) =>
        item.resource_id === payload.request.resource_id),
    }}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="administration"
      initialContext={{
        resource_id: 'system-variable:MAX_CONNECTIONS',
        resource_kind: 'system-variable', operation_id: 'set_global',
      }} />);
    expect(await screen.findByRole('heading', {
      name: 'Set runtime global value',
    })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('combobox', {
      name: 'Target resource',
    })).toHaveTextContent('MAX_CONNECTIONS'));
  });

  it.each([false, true])('opens server-only recovery and handles failed response %s without replay', async (failed) => {
    const onCredentialRequired = jest.fn();
    const failureMessage = 'The provider operation outcome is unknown. Inspect native state. The plan will not be automatically retried. Native status codes: 335544788, 335545112';
    const operation = {
      operation_id: 'activate_shadow', title: 'Activate a Firebird database shadow',
      mutation_class: 'destructive', target_required: false,
      confirmation_required: true, execution_available: true,
      graphical_ready: true, blockers: [], workspace_scope: 'server_service',
      form: {form_id: 'firebird_activate_shadow', fields: [
        {field_id: 'shadow_filename', label: 'First shadow filename',
          control: 'text', required: true},
        {field_id: 'confirmation', label: 'Confirm shadow filename',
          control: 'text', required: true},
        {field_id: 'original_isolated', label: 'Original is isolated',
          control: 'boolean', required: true, default: false},
        {field_id: 'role', label: 'SQL role', control: 'text'},
      ]},
    };
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap, resource_page: {items: []},
      visual_admin: {engine_id: 'firebird', engine_name: 'Firebird', objects: [{
        resource_kind: 'database', title: 'Database', operations: [operation],
      }]},
    }}});
    api.post.mockImplementation((_url, payload) => {
      if (failed && payload.action === 'visual_admin_apply') {
        return Promise.reject({response: {status: 502, data: {
          errormsg: failureMessage,
          info: 'PROVIDER_OPERATION_RESPONSE_UNAVAILABLE',
          data: {control_operation: {unknown_outcome: true,
            native_status_codes: [335544788, 335545112],
            automatic_mutation_retry: false}},
        }}});
      }
      const responses = {
        visual_admin_validate: {valid: true, errors: []},
        visual_admin_plan: {state: 'ready', execution_available: true,
          plan_id: 'shadow-plan', plan_digest: 'shadow-digest'},
        visual_admin_apply: {accepted: true,
          driver_observation: {server_completed: true}},
      };
      return Promise.resolve({data: {data: responses[payload.action]}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/server?focused_operation_id=activate_shadow"
      onCredentialRequired={onCredentialRequired}
      initialTab="administration" initialContext={{
        database_target_id: null, resource_kind: 'database',
        operation_id: 'activate_shadow',
      }} />);
    const filename = '/owned/影\'s.shd';
    fireEvent.change(await screen.findByRole('textbox', {
      name: /First shadow filename/,
    }), {target: {value: filename}});
    fireEvent.change(screen.getByRole('textbox', {
      name: /Confirm shadow filename/,
    }), {target: {value: filename}});
    fireEvent.click(screen.getByRole('checkbox', {name: /Original is isolated/}));
    fireEvent.change(screen.getByRole('textbox', {name: 'SQL role'}),
      {target: {value: 'RECOVERY_OPERATOR'}});
    expect(screen.queryByRole('combobox', {name: 'Target resource'})).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Validate and preview'));
    await screen.findByLabelText('Provider plan preview');
    expect(api.post).toHaveBeenCalledWith(
      '/workspace/server?focused_operation_id=activate_shadow', {
        action: 'visual_admin_plan', request: {
          resource_kind: 'database', operation_id: 'activate_shadow',
          target_resource: null, draft: {shadow_filename: filename,
            confirmation: filename, original_isolated: true,
            role: 'RECOVERY_OPERATOR'},
        },
      });
    expect(screen.getByText('Apply provider plan').closest('button')).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', {
      name: 'I confirm this provider-planned operation.',
    }));
    fireEvent.click(screen.getByText('Apply provider plan'));
    if (failed) {
      expect(await screen.findByText(failureMessage)).toBeInTheDocument();
      expect(screen.queryByLabelText('Provider operation result')).toBeNull();
    } else {
      await screen.findByLabelText('Provider operation result');
    }
    expect(screen.getByText('Apply provider plan').closest('button')).toBeDisabled();
    fireEvent.click(screen.getByText('Apply provider plan'));
    expect(api.post.mock.calls.filter(([, payload]) =>
      payload.action === 'visual_admin_apply')).toHaveLength(1);
    expect(onCredentialRequired).not.toHaveBeenCalled();
    expect(api.post).toHaveBeenCalledWith(
      '/workspace/server?focused_operation_id=activate_shadow', {
        action: 'visual_admin_apply', request: {
          plan_id: 'shadow-plan', plan_digest: 'shadow-digest', confirmed: true,
        },
      });
    expect(api.post.mock.calls.some(([, payload]) =>
      payload.action === 'resource_inspect')).toBe(false);
  });

  it('does not inspect an attachment-free service-operation target', async () => {
    const onCredentialRequired = jest.fn((retry) => retry());
    let applyAttempts = 0;
    const operation = {
      operation_id: 'bring_online', title: 'Bring database online',
      mutation_class: 'admin', target_required: true,
      target_resource_kinds: ['database'], confirmation_required: false,
      execution_available: true, graphical_ready: true, blockers: [],
      workspace_scope: 'server_service',
      form: {form_id: 'firebird_bring_online', fields: []},
    };
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      database_targets: {targets: [{target_id: 'database-one',
        database: '/owned/offline.fdb'}]},
      resource_page: {items: [{
        resource_id: 'database-service-target:database-one',
        resource_kind: 'database', display_name: 'offline.fdb',
        extensions: {cdeadmin: {
          database_target_id: 'database-one', service_scope_only: true,
        }},
      }]},
      visual_admin: {
        engine_id: 'firebird', engine_name: 'Firebird', objects: [{
          resource_kind: 'database', title: 'Database',
          operations: [operation],
        }],
      },
    }}});
    api.post.mockImplementation((_url, payload) => {
      const responses = {
        visual_admin_validate: {valid: true, errors: []},
        visual_admin_plan: {
          state: 'ready', execution_available: true,
          plan_id: 'service-plan', plan_digest: 'service-digest',
        },
        visual_admin_apply: {
          accepted: true,
          driver_observation: {server_completed: true},
        },
      };
      if (payload.action === 'visual_admin_apply' && applyAttempts++ === 0) {
        return Promise.reject({response: {status: 401}});
      }
      return Promise.resolve({data: {data: responses[payload.action]}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="administration"
      onCredentialRequired={onCredentialRequired}
      initialContext={{
        resource_id: 'database-one', resource_kind: 'database',
        operation_id: 'bring_online',
      }} />);
    expect(await screen.findByRole('heading', {
      name: 'Bring database online',
    })).toBeInTheDocument();
    expect(screen.getByRole('combobox', {name: 'Target resource'}))
      .toHaveTextContent('offline.fdb');
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Validate and preview'));
    await screen.findByLabelText('Provider plan preview');
    fireEvent.click(screen.getByText('Apply provider plan'));
    await screen.findByLabelText('Provider operation result');
    expect(onCredentialRequired).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith('/workspace/1', {
      action: 'visual_admin_apply', request: {
        plan_id: 'service-plan', plan_digest: 'service-digest',
        confirmed: false, database_target_id: 'database-one',
      },
    });
  });

  it('opens provider-owned object actions for a tree-selected resource', async () => {
    const inspectOperation = {
      operation_id: 'inspect', title: 'Inspect MySQL database',
      mutation_class: 'read', target_required: true,
      target_resource_kinds: ['database'], confirmation_required: false,
      execution_available: true, graphical_ready: true, blockers: [],
      form: {form_id: 'mysql-database-inspect', fields: []},
    };
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      visual_admin: {
        ...bootstrap.visual_admin,
        objects: [{...bootstrap.visual_admin.objects[0],
          editor: {sections: ['definition']},
          operations: [inspectOperation]}],
      },
    }}});
    api.post.mockResolvedValue({data: {data: {
      ...bootstrap.resource_page.items[0], generation: 'generation-one',
      extensions: {mysql: {native: {
        definition: {character_set: 'utf8mb4'},
      }}},
    }}});
    // The tree's context menu opens the workspace on the administration tab with the resource.
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="administration"
      initialContext={{resource_id: 'database:example', resource_kind: 'database', operation_id: 'inspect'}} />);
    expect(await screen.findByRole('heading', {
      name: /Inspect MySQL database/,
    })).toBeInTheDocument();
    const tables = await screen.findAllByRole('table', {name: 'Native provider properties'});
    expect(tables.some((table) => table.textContent.includes('character set'))).toBe(true);
  });

  it('surfaces unique native tasks but omits unsupported tasks', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      visual_admin: {
        ...bootstrap.visual_admin,
        objects: [{...bootstrap.visual_admin.objects[0], operations: [{
          operation_id: 'flashback', title: 'Flashback database',
          mutation_class: 'admin', target_required: true,
          execution_available: true, graphical_ready: true,
          native_supported: true, blockers: [], form: {fields: []},
        }, {
          operation_id: 'vacuum', title: 'Vacuum database',
          mutation_class: 'admin', target_required: true,
          execution_available: false, graphical_ready: true,
          native_supported: false,
          blockers: ['provider_operation_unavailable'], form: {fields: []},
        }]}],
      },
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="administration" />);
    expect(await screen.findByText('Flashback database')).toBeInTheDocument();
    expect(screen.queryByText('Vacuum database')).not.toBeInTheDocument();
  });

  it('loads generation-bound navigator continuation pages', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      resource_page: {
        ...bootstrap.resource_page, generation: 'generation-one',
        next_cursor: 'cursor-one', total_count: 2,
      },
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" />);
    expect(await screen.findByRole('region', {name: 'Object navigation'})).toBeInTheDocument();
    expect(screen.queryByLabelText('Filter provider objects')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Load more provider objects'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/workspace/1', {
        action: 'resource_page', request: {
          continuation: 'cursor-one', generation: 'generation-one',
        },
      }
    ));
  });

  it('refreshes only the active provider generation', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      resource_page: {
        ...bootstrap.resource_page, generation: 'generation-one',
      },
    }}});
    api.post.mockResolvedValue({data: {data: {
      ...bootstrap.resource_page, generation: 'generation-two',
      items: [{
        ...bootstrap.resource_page.items[0], display_name: 'refreshed',
      }, {
        ...bootstrap.resource_page.items[0], resource_id: 'database:other', display_name: 'other',
      }],
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" />);
    fireEvent.click(await screen.findByText('Refresh provider objects'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/workspace/1', {
        action: 'resource_refresh', request: {
          generation: 'generation-one',
        },
      }
    ));
    expect(await screen.findByText('2 objects in the current catalog page.')).toBeInTheDocument();
  });

});

