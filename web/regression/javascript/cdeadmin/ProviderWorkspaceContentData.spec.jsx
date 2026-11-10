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

describe('ProviderWorkspaceContent (topology, data browsers and semantic)', () => {
  const workspace = installWorkspaceHooks();
  let api;
  beforeEach(() => { api = workspace.api; });

  it('visualizes provider-authoritative distributed topology paths', async () => {
    const topologyBootstrap = {
      ...bootstrap,
      resource_page: {generation: 'topology-one', items: [{
        resource_id: 'node:one', resource_kind: 'node',
        display_name: 'node-one',
        authority_path: ['cluster-a', 'zone-one', 'node-one'],
        extensions: {provider: {native: {
          status: 'provider-online', role: 'provider-leader',
        }}},
      }]},
      operational_workspace: {
        schema: 'cdeadmin.operational-workspace.v1',
        engine_id: 'distributed-test', distributed: true,
        categories: ['distributed'],
        topology: {available: true, authority:
          'provider-resource-authority-path', resource_kinds: ['node']},
        facets: [{
          facet_id: 'topology', title: 'Topology visualization',
          category: 'distributed', summary: 'Provider topology.',
          catalog_state: 'observable', unavailable_reason: null,
          resource_kinds: ['node'], discovered_resource_count: 1,
          operations: [],
        }],
      },
    };
    api.get.mockResolvedValue({data: {data: topologyBootstrap}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="operations" />);
    expect(await screen.findByLabelText('Provider topology visualization'))
      .toHaveTextContent('cluster-a → zone-one → node-one');
    expect(screen.getByText(/provider-leader/)).toBeInTheDocument();
  });

  it.each(['integer', 'decfloat', 'date', 'time', 'timestamp', 'text', 'binary', 'varying-binary', 'varying-text'].flatMap((kind) => [['insert', kind], ['update', kind]]))('submits coordinate array %s %s without numeric rounding', async (operation, kind) => {
    const elementKind = kind.replace('varying-', '');
    const nativeSpec = kind.startsWith('varying-') ? {type: 37, length: 16, charset: elementKind === 'binary' ? 'OCTETS' : 'UTF8'} : {};
    const temporalDefault = {text: '', binary: '', date: '2000-01-01', time: '00:00:00', timestamp: '2000-01-01 00:00:00'}[elementKind];
    const editedValue = {text: 'line1\né\0 ', binary: 'AP8=', decfloat: 'sNaN', date: '0001-01-01', time: '23:59:59.9999', timestamp: '0001-01-01 12:34:56.0001'}[elementKind] ?? '9223372036854775807';
    api.get.mockResolvedValue({data: {data: {...bootstrap,
      resource_page: {items: [{resource_id: 'array-table', resource_kind: 'table',
        display_name: 'arrays', display_path: ['arrays']}]},
      visual_admin: {...bootstrap.visual_admin, objects: [{resource_kind: 'table',
        title: 'Table', operations: ['insert', 'update'].map((operation_id) => ({operation_id, execution_available: true}))}]},
    }}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      open_session: {session_id: 'array-session'},
      visual_admin_rows: {columns: [{name: 'A', input_kind: 'array', editable: true, insertable: true,
        array_spec: {bounds: [[-1, 0]], element_kind: elementKind, scale: 0, ...nativeSpec}}],
      rows: [{values: {A: [temporalDefault ?? '1', temporalDefault ?? '2']}, identity_token: 'array-row'}],
      editable: true, row_operations: ['insert', 'update']},
      visual_admin_validate: {valid: true, errors: []},
      visual_admin_plan: {state: 'ready', execution_available: true, plan_id: 'array-plan', plan_digest: 'array-digest'},
      visual_admin_apply: {provider_result: {accepted: true, staged_in_provider_session: true}},
      transaction_action: {provider_payload: {driver_observation_only: true}},
      close_session: {provider_closed: true},
    }[payload.action]}}));
    const {unmount} = render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1" initialTab="data" />);
    fireEvent.click(await screen.findByText('Load rows'));
    await waitFor(() => expect(screen.getByRole('combobox', {name: 'Grid mode'})).not.toHaveAttribute('aria-disabled', 'true'));
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Grid mode'}));
    fireEvent.click(screen.getByRole('option', {name: 'Edit'}));
    const label = operation === 'insert' ? 'A new value' : 'A value';
    fireEvent.click(await screen.findByRole('button', {name: `${label} [-1:0]`}));
    if (operation === 'insert') fireEvent.click(screen.getByRole('button', {name: 'Initialize array'}));
    fireEvent.change(screen.getByRole('textbox', {name: `${label} [-1]`}), {target: {value: editedValue}});
    fireEvent.click(screen.getByRole('button', {name: 'Close array editor'}));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    fireEvent.click(screen.getByRole('button', {name: operation === 'insert' ? 'Insert row' : 'Save'}));
    await waitFor(() => expect(api.post.mock.calls.some(([, payload]) => payload.action === 'visual_admin_apply')).toBe(true));
    const planned = api.post.mock.calls.find(([, payload]) => payload.action === 'visual_admin_plan')[1];
    const expected = [editedValue, temporalDefault ?? (operation === 'insert' ? '0' : '2')];
    expect(planned.request.draft[operation === 'insert' ? 'values' : 'changes'].A).toEqual(elementKind === 'binary' ? expected.map((data) => ({encoding: 'base64', data, byte_length: atob(data).length})) : expected);
    expect(api.post.mock.calls.some(([, payload]) => payload.action === 'transaction_action')).toBe(false);
    unmount();
  });

  it.each([
    ['table', 'update'], ['table', 'insert'], ['table', 'defaults'], ['table', 'select-only'],
    ['view', 'update'], ['view', 'delete'], ['view', 'insert'], ['view', 'defaults'], ['view', 'keyless'],
    ['view', 'empty'], ['view', 'null'], ['view', 'omit'], ['view', 'array'],
    ['view', 'typed-text'], ['view', 'typed-integer'], ['view', 'typed-decimal'],
    ['view', 'typed-decfloat'], ['view', 'typed-null'], ['view', 'typed-date'],
    ['view', 'typed-time'], ['view', 'typed-timestamp'], ['view', 'typed-binary'],
    ['view', 'typed-float32'], ['view', 'typed-float64'],
  ])('runs %s %s through provider-issued identity plans', async (kind, operation) => {
    const typed = operation.startsWith('typed-');
    const scalarValue = {'typed-text': 'null', 'typed-integer': '170141183460469231731687303715884105727',
      'typed-decimal': '12345678901234567890.123456789012345678', 'typed-decfloat': 'NaN', 'typed-null': null,
      'typed-date': '0001-01-01', 'typed-time': '23:59:59.9999', 'typed-timestamp': '9999-12-31 23:59:59.9999',
      'typed-binary': {encoding: 'base64', data: 'AP9/', byte_length: 3},
      'typed-float32': {encoding: 'float32', data: '-0.0'},
      'typed-float64': {encoding: 'float64', data: '1.7976931348623157e308'}}[operation];
    const mutation = typed || ['defaults', 'empty', 'null', 'omit', 'array', 'keyless'].includes(operation) ? 'insert' : operation;
    const gridBootstrap = {
      ...bootstrap,
      resource_page: {items: [{
        resource_id: `${kind}:example:widgets`, resource_kind: kind,
        display_name: 'widgets', display_path: ['example', 'widgets'],
        authority_path: ['example', 'table', 'widgets'],
        extensions: {cdeadmin: {database_target_id: 'database-one'}},
      }]},
      visual_admin: {
        ...bootstrap.visual_admin,
        objects: [{
          resource_kind: kind, title: 'Relation', operations: [
            {operation_id: 'insert', execution_available: true},
            {operation_id: 'update', execution_available: true},
            {operation_id: 'delete', execution_available: true},
          ],
        }],
      },
    };
    api.get.mockResolvedValue({data: {data: gridBootstrap}});
    api.post.mockImplementation((_url, payload) => {
      const responses = {
        open_session: {session_id: 'grid-session'},
        visual_admin_rows: {
          columns: [
            {name: 'id', key: true, editable: operation === 'update', insertable: false},
            {name: 'second key', key: true, editable: false, insertable: false},
            {name: 'name', key: false, editable: operation === 'update', insertable: true,
              ...(typed ? {input_kind: ['typed-null', 'typed-date', 'typed-time', 'typed-timestamp'].includes(operation) ? 'text' : operation.slice(6)} : {})},
          ],
          rows: [{
            values: {id: 1, 'second key': 2, name: operation === 'typed-binary' ? scalarValue : 'first'}, identity_token: operation === 'keyless' ? null : 'row-one',
          }],
          editable: !(kind === 'table' && operation === 'defaults') && operation !== 'keyless',
          ...(kind === 'table' && operation !== 'update' ? {
            operation_authority: 'firebird-native-preparation',
          } : {}),
          row_operations: operation === 'select-only' ? [] : [mutation],
          insert_identity_token: 'insert-one',
          insert_default_values: ['defaults', 'omit'].includes(operation),
        },
        visual_admin_validate: {valid: true, errors: []},
        visual_admin_plan: {
          state: 'ready', execution_available: true,
          plan_id: 'plan-one', plan_digest: 'digest-one',
        },
        visual_admin_apply: {provider_result: {
          accepted: true, staged_in_provider_session: true,
        }},
        transaction_action: {provider_payload: {
          driver_observation_only: true,
          finality_interpreted_by_common_code: false,
        }},
        close_session: {
          session_id: 'grid-session', provider_closed: true,
        },
      };
      return Promise.resolve({data: {data: responses[payload.action]}});
    });
    const {unmount} = render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="data" />);
    fireEvent.click(await screen.findByText('Load rows'));
    await waitFor(() => expect(screen.getByRole('combobox', {name: 'Grid mode'})).not.toHaveAttribute('aria-disabled', 'true'));
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Grid mode'}));
    if (operation === 'select-only') {
      expect(screen.getByRole('option', {name: 'Edit'})).toHaveAttribute('aria-disabled', 'true');
      fireEvent.keyDown(screen.getByRole('listbox'), {key: 'Escape'});
      expect(screen.queryByRole('button', {name: 'Save'})).toBeNull();
      expect(screen.queryByRole('textbox', {name: 'name value'})).toBeNull();
      unmount(); return;
    }
    fireEvent.click(screen.getByRole('option', {name: 'Edit'}));
    const name = await screen.findByDisplayValue(operation === 'typed-binary' ? scalarValue.data : 'first');
    expect(screen.getByRole('textbox', {name: 'name value'})).toBe(name);
    expect(screen.getByRole('textbox', {name: 'id value'})).toHaveValue('1');
    expect(screen.getByRole('textbox', {name: 'second key value'})).toHaveValue('2');
    if ((kind === 'table' && operation === 'defaults') || operation === 'keyless') {
      expect(screen.getByText(/Insertion is available/)).toBeInTheDocument();
    }
    if (kind === 'table') {
      expect(screen.getByRole('textbox', {name: 'name new value'}))
        .toHaveAttribute('placeholder', 'New value');
    } else if (mutation !== 'insert') {
      expect(screen.queryByRole('textbox', {name: 'name new value'})).toBeNull();
      if (operation === 'update') {
        expect(screen.getByRole('button', {name: 'Delete'})).toBeDisabled();
      }
    }
    if (operation === 'delete') {
      expect(name).toBeDisabled();
      expect(screen.getByRole('button', {name: 'Save'})).toBeDisabled();
      const remove = screen.getByRole('button', {name: 'Delete'});
      const focus = jest.spyOn(remove, 'focus');
      fireEvent.mouseDown(remove, {button: 2});
      expect(focus).not.toHaveBeenCalled();
      fireEvent.mouseDown(remove, {button: 0});
      expect(focus).toHaveBeenCalledWith({preventScroll: true});
      expect(remove).toHaveFocus();
      expect(api.post).toHaveBeenCalledTimes(2);
      fireEvent.click(remove);
      expect(api.post).toHaveBeenCalledTimes(2);
      fireEvent.click(screen.getByRole('button', {name: 'Confirm delete'}));
    } else if (mutation === 'insert') {
      expect(screen.getByRole('textbox', {name: 'id new value'})).toBeDisabled();
      if (operation === 'omit') {
        fireEvent.change(screen.getByRole('textbox', {name: 'name new value'}),
          {target: {value: 'discard'}});
        fireEvent.click(screen.getByRole('button', {name: 'Omit name from insert'}));
        expect(screen.getByRole('textbox', {name: 'name new value'})).toHaveValue('');
        expect(screen.queryByRole('button', {name: 'Omit name from insert'})).toBeNull();
      }
      if (['defaults', 'omit'].includes(operation)) {
        fireEvent.click(screen.getByRole('button', {name: 'Insert default row'}));
      } else {
        fireEvent.change(screen.getByRole('textbox', {name: 'name new value'}),
          {target: {value: 'new'}});
        if (typed) {
          if (operation === 'typed-null') {
            fireEvent.mouseDown(screen.getByRole('combobox', {name: 'name new value mode'}));
            fireEvent.click(screen.getByRole('option', {name: 'NULL'}));
          } else {
            fireEvent.change(screen.getByRole('textbox', {name: 'name new value'}),
              {target: {value: scalarValue?.data ?? scalarValue}});
          }
        }
        if (['empty', 'null'].includes(operation)) {
          fireEvent.change(screen.getByRole('textbox', {name: 'name new value'}),
            {target: {value: operation === 'empty' ? '' : 'null'}});
        }
        if (operation === 'array') {
          fireEvent.change(screen.getByRole('textbox', {name: 'name new value'}),
            {target: {value: '[[1,2],[3,4]]'}});
        }
        fireEvent.click(screen.getByRole('button', {name: 'Insert row'}));
      }
    } else {
      fireEvent.change(name, {target: {value: 'second'}});
      fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    }
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(6));
    expect(api.post.mock.calls.map((call) => call[1].action)).toEqual([
      'open_session', 'visual_admin_rows', 'visual_admin_validate',
      'visual_admin_plan', 'visual_admin_apply', 'visual_admin_rows',
    ]);
    expect(api.post.mock.calls[2][1].request.draft).toEqual(mutation === 'insert' ? {
      values: ['defaults', 'omit'].includes(operation) ? {} : {
        name: typed ? scalarValue : operation === 'empty' ? '' : operation === 'null' ? null :
          operation === 'array' ? [[1, 2], [3, 4]] : 'new',
      },
      options: kind === 'view' ? {identity_token: 'insert-one'} : {},
    } : {
      selector: {identity_token: 'row-one'},
      ...(operation === 'delete' ? {confirmation: 'provider-row-delete'} :
        {changes: {name: 'second'}}),
      concurrency_token: 'row-one',
    });
    expect(api.post.mock.calls[2][1].request.resource_kind).toBe(kind);
    expect(api.post.mock.calls[2][1].request.operation_id).toBe(mutation);
    expect(api.post.mock.calls[0][1]).toEqual({
      action: 'open_session', language_profile: 'mysql-sql',
      database_target_id: 'database-one',
    });
    expect(api.post.mock.calls[1][1].request.continuation).toBeNull();
    expect(api.post.mock.calls[1][1].request.database_target_id)
      .toBe('database-one');
    expect(api.post.mock.calls[2][1].request.database_target_id)
      .toBe('database-one');
    expect(api.post.mock.calls[4][1].request.session_id)
      .toBe('grid-session');
    expect(api.post.mock.calls[4][1].request.database_target_id)
      .toBe('database-one');
    expect(await screen.findByLabelText('Staged provider grid changes'))
      .toHaveTextContent('1 grid change');
    fireEvent.click(screen.getByRole('button', {name: 'Rollback changes'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(8));
    expect(api.post.mock.calls[6][1]).toEqual({
      action: 'transaction_action', session_id: 'grid-session',
      transaction_action: 'rollback',
      database_target_id: 'database-one',
    });
    fireEvent.click(screen.getByText('Close data session'));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(9));
    expect(api.post.mock.calls[8][1]).toEqual({
      action: 'close_session', session_id: 'grid-session',
      database_target_id: 'database-one',
    });
    expect(screen.getByText('Close data session')).toBeDisabled();
    unmount();
  });

  it('opens the selected provider view in the owning database scope', async () => {
    const table = {
      resource_id: 'table:ASSETS', resource_kind: 'table',
      display_name: 'ASSETS', display_path: ['ASSETS'],
    };
    const view = {
      resource_id: 'view:OPEN_WORK_ORDERS', resource_kind: 'view',
      display_name: 'OPEN_WORK_ORDERS', display_path: ['OPEN_WORK_ORDERS'],
    };
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      resource_page: {items: [table, view]},
      visual_admin: {
        ...bootstrap.visual_admin,
        objects: [{resource_kind: 'table', operations: []}, {
          resource_kind: 'view', operations: [],
        }],
      },
    }}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {
      data: payload.action === 'open_session' ? {
        session_id: 'view-session',
      } : {
        columns: [{name: 'WORK_ORDER_ID', editable: false}],
        rows: [{values: {WORK_ORDER_ID: 1001}, identity_token: null}],
        editable: false, identity_policy: 'read-only-view',
      },
    }}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="data" initialContext={{
        resource_id: view.resource_id, resource_kind: 'view',
        database_target_id: 'firebird-database-one',
      }} />);
    expect(await screen.findByRole('combobox', {name: 'Table or view'}))
      .toHaveTextContent('OPEN_WORK_ORDERS');
    fireEvent.click(screen.getByText('Load rows'));
    expect(await screen.findByText('1001')).toBeInTheDocument();
    expect(api.post.mock.calls[0][1]).toEqual({
      action: 'open_session', language_profile: 'mysql-sql',
      database_target_id: 'firebird-database-one',
    });
    expect(api.post.mock.calls[1][1].request.target_resource).toEqual(view);
    expect(api.post.mock.calls[1][1].request.database_target_id)
      .toBe('firebird-database-one');
    expect(screen.getByText(/This grid is read-only because ScratchRobin/)).toBeInTheDocument();
    expect(screen.getByText(/The engine may support writes/)).toBeInTheDocument();
    expect(screen.queryByRole('textbox', {name: 'id value'})).toBeNull();
    expect(screen.queryByRole('button', {name: 'Save'})).toBeNull();
    expect(screen.queryByRole('button', {name: 'Delete'})).toBeNull();
    expect(screen.queryByRole('button', {name: 'Insert row'})).toBeNull();
  });

  it('loads and edits MongoDB documents through provider plans', async () => {
    const collection = {
      resource_id: 'mongodb:collection:example:widgets',
      resource_kind: 'collection', display_name: 'widgets',
      display_path: ['MongoDB', 'example', 'widgets'],
      authority_path: ['mongodb', 'collection', 'example', 'widgets'],
    };
    const documentBootstrap = {
      ...bootstrap,
      resource_page: {items: [collection]},
      visual_admin: {
        engine_id: 'mongodb', model_family: 'document',
        objects: [{
          resource_kind: 'document', title: 'Document', operations: [
            {operation_id: 'insert', execution_available: true},
            {operation_id: 'update', execution_available: true},
            {operation_id: 'delete', execution_available: true},
          ],
        }],
      },
    };
    api.get.mockResolvedValue({data: {data: documentBootstrap}});
    api.post.mockImplementation((_url, payload) => {
      const responses = {
        visual_admin_rows: {
          documents: [{
            _id: {$oid: '0123456789abcdef01234567'}, name: 'first',
          }],
        },
        visual_admin_validate: {valid: true, errors: []},
        visual_admin_plan: {
          state: 'ready', execution_available: true,
          plan_id: 'plan-one', plan_digest: 'digest-one',
        },
        visual_admin_apply: {provider_result: {acknowledged: true}},
      };
      return Promise.resolve({data: {data: responses[payload.action]}});
    });
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="data" />);
    fireEvent.click(await screen.findByText('Load documents'));
    await waitFor(() => expect(screen.getByRole('combobox', {name: 'Data mode'})).not.toHaveAttribute('aria-disabled', 'true'));
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Data mode'}));
    fireEvent.click(screen.getByRole('option', {name: 'Edit'}));
    const editor = await screen.findByRole('textbox', {
      name: 'Document JSON',
    });
    fireEvent.change(editor, {target: {value: JSON.stringify({
      _id: {$oid: '0123456789abcdef01234567'}, name: 'second',
    })}});
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(5));
    expect(api.post.mock.calls[1][1].request).toEqual({
      resource_kind: 'document', operation_id: 'update',
      target_resource: collection,
      draft: {
        selector: {_id: {$oid: '0123456789abcdef01234567'}},
        changes: {name: 'second'},
      },
    });
  });

  it('opens the MongoDB collection owning the selected child resource', async () => {
    const firstCollection = {
      resource_id: 'mongodb:collection:example:first',
      resource_kind: 'collection', display_name: 'first',
      display_path: ['MongoDB', 'example', 'first'],
    };
    const selectedCollection = {
      resource_id: 'mongodb:collection:example:selected',
      resource_kind: 'collection', display_name: 'selected',
      display_path: ['MongoDB', 'example', 'selected'],
    };
    const selectedIndex = {
      resource_id: 'mongodb:index:example:selected:lookup',
      resource_kind: 'index', display_name: 'lookup',
      display_path: ['MongoDB', 'example', 'selected', 'lookup'],
    };
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      resource_page: {items: [firstCollection, selectedCollection,
        selectedIndex]},
      visual_admin: {
        engine_id: 'mongodb', model_family: 'document',
        objects: [{resource_kind: 'document', operations: []}],
      },
    }}});
    api.post.mockResolvedValue({data: {data: {documents: []}}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="data" initialContext={{
        resource_id: selectedIndex.resource_id, resource_kind: 'index',
      }} />);
    const collectionSelector = await screen.findByRole('combobox', {
      name: 'Collection',
    });
    await waitFor(() => expect(collectionSelector)
      .toHaveTextContent('MongoDB.example.selected'));
    fireEvent.click(screen.getByText('Load documents'));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post.mock.calls[0][1].request.target_resource)
      .toEqual(selectedCollection);
  });

  it('loads and edits Neo4j nodes through provider-owned plans', async () => {
    const graph = {
      resource_id: 'neo4j:graph:neo4j', resource_kind: 'graph',
      display_name: 'neo4j', authority_path: ['neo4j', 'graph', 'neo4j'],
    };
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      resource_page: {items: [graph]},
      visual_admin: {
        engine_id: 'neo4j', model_family: 'graph', objects: [
          {resource_kind: 'node', operations: [
            {operation_id: 'insert', execution_available: true},
            {operation_id: 'update', execution_available: true},
            {operation_id: 'delete', execution_available: true},
          ]},
          {resource_kind: 'relationship', operations: [
            {operation_id: 'insert', execution_available: true},
            {operation_id: 'update', execution_available: true},
            {operation_id: 'delete', execution_available: true},
          ]},
        ],
      },
    }}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data: {
      visual_admin_rows: {records: [{n: {
        kind: 'node', element_id: '4:one', labels: ['Person'],
        properties: {name: 'Alice'},
      }}]},
      visual_admin_validate: {valid: true, errors: []},
      visual_admin_plan: {state: 'ready', execution_available: true,
        plan_id: 'graph-plan', plan_digest: 'graph-digest'},
      visual_admin_apply: {provider_result: {records: []}},
    }[payload.action]}}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="data" />);
    fireEvent.click(await screen.findByText('Load graph'));
    await waitFor(() => expect(screen.getByRole('combobox', {name: 'Data mode'})).not.toHaveAttribute('aria-disabled', 'true'));
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Data mode'}));
    fireEvent.click(screen.getByRole('option', {name: 'Edit'}));
    const editor = await screen.findByRole('textbox', {name: 'Node properties'});
    fireEvent.change(editor, {target: {value: '{"name":"Alicia"}'}});
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(5));
    expect(api.post.mock.calls[1][1].request).toEqual({
      resource_kind: 'node', operation_id: 'update',
      target_resource: {
        resource_kind: 'node', resource_id: 'neo4j:node:4:one',
        extensions: {neo4j: {native: {element_id: '4:one'}}},
        display_name: '4:one',
      },
      draft: {
        changes: {properties: {name: 'Alicia'}},
      },
    });
  });

  it.each([
    ['cdeadmin/results/TimeSeriesView', 'Time-series results', {
      schema: {time_field: 'time'},
      records: [{time: '2026-09-02T12:00:00Z', usage: 0.5}],
    }],
    ['cdeadmin/results/VectorView', 'Vector results', {
      records: [{id: 7, distance: 0.1, entity: {title: 'nearest'}}],
    }],
    ['cdeadmin/results/SearchView', 'Search results', {
      records: [{_index: 'docs', _id: 'one', _score: 1,
        _source: {title: 'matched'}}],
    }],
  ])('renders analytic result component %s', async (
    componentReference, accessibleName, viewModel
  ) => {
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {
      data: {
        open_session: {session_id: 'analytic-session'},
        execute: {occurrence_id: 'analytic-operation'},
        poll: {
          occurrence: {operation: {terminal: true}},
          rendered_result: {
            component_reference: componentReference,
            view_model: viewModel,
          },
        },
      }[payload.action],
    }}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    await screen.findByText('MySQL SQL');
    fireEvent.click(screen.getByRole('button', {name: 'Run', exact: true}));
    expect(await screen.findByLabelText(accessibleName)).toBeInTheDocument();
  });

  it('browses provider-owned analytic data pages', async () => {
    const table = {
      resource_id: 'influxdb:table:cpu', resource_kind: 'table',
      display_name: 'cpu', display_path: ['metrics', 'cpu'],
      authority_path: ['influxdb', 'table', 'metrics', 'cpu'],
    };
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      resource_page: {items: [table]},
      visual_admin: {
        engine_id: 'influxdb', model_family: 'time-series-analytic',
        objects: [{resource_kind: 'table', operations: []}],
      },
    }}});
    api.post.mockResolvedValue({data: {data: {
      records: [{time: '2026-09-02T12:00:00Z', usage: 0.5}],
      continuation: null,
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="data" />);
    fireEvent.click(await screen.findByText('Load data'));
    expect(await screen.findByText('0.5')).toBeInTheDocument();
    expect(api.post.mock.calls[0][1]).toEqual({
      action: 'visual_admin_rows',
      request: {target_resource: table, limit: 200, continuation: null},
    });
  });

  it('opens the analytic container owning the selected child resource', async () => {
    const firstTable = {
      resource_id: 'influxdb:table:metrics:first', resource_kind: 'table',
      display_name: 'first', display_path: ['metrics', 'first'],
    };
    const selectedTable = {
      resource_id: 'influxdb:table:metrics:selected', resource_kind: 'table',
      display_name: 'selected', display_path: ['metrics', 'selected'],
    };
    const selectedField = {
      resource_id: 'influxdb:field:metrics:selected:usage',
      resource_kind: 'field', display_name: 'usage',
      display_path: ['metrics', 'selected', 'usage'],
    };
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      resource_page: {items: [firstTable, selectedTable, selectedField]},
      visual_admin: {
        engine_id: 'influxdb', model_family: 'time-series-analytic',
        objects: [{resource_kind: 'table', operations: []}],
      },
    }}});
    api.post.mockResolvedValue({data: {data: {records: []}}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="data" initialContext={{
        resource_id: selectedField.resource_id, resource_kind: 'field',
      }} />);
    const containerSelector = await screen.findByRole('combobox', {
      name: 'Analytic data container',
    });
    await waitFor(() => expect(containerSelector)
      .toHaveTextContent('metrics.selected'));
    fireEvent.click(screen.getByText('Load data'));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post.mock.calls[0][1].request.target_resource)
      .toEqual(selectedTable);
  });

  it('previews and explicitly confirms provider bulk imports', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      visual_admin: {...bootstrap.visual_admin, objects: [{
        ...bootstrap.visual_admin.objects[0], operations: [{
          ...bootstrap.visual_admin.objects[0].operations[0], blockers: [],
          execution_available: true,
        }],
      }]},
    }}});
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {
      data: payload.action === 'visual_admin_bulk_plan' ? {
        ready: true, atomicity: 'not-claimed', plans: [{plan: {
          plan_id: 'plan-one', plan_digest: 'digest-one',
          command_preview: 'CREATE DATABASE imported',
        }}],
      } : {complete: true, applied_count: 1, automatic_retry: false},
    }}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="movement" />);
    const source = await screen.findByRole('textbox', {
      name: 'Import records / provider form drafts',
    });
    fireEvent.change(source, {target: {value: '[{"name":"imported"}]'}});
    fireEvent.click(screen.getByText('Validate and preview batch'));
    expect(await screen.findByLabelText('Bulk operation preview'))
      .toHaveTextContent('CREATE DATABASE imported');
    fireEvent.click(screen.getByLabelText(
      'I confirm every provider-planned mutation in this non-atomic batch.'
    ));
    fireEvent.click(screen.getByText('Apply confirmed batch'));
    expect(await screen.findByLabelText('Bulk operation result'))
      .toHaveTextContent('applied_count');
    expect(api.post).toHaveBeenLastCalledWith('/workspace/1', {
      action: 'visual_admin_bulk_apply', request: {
        confirmed: true,
        plans: [{plan_id: 'plan-one', plan_digest: 'digest-one'}],
      },
    });
  });

  describe('semantic tab', () => {
    const catalog = (profile = {}) => ({...modelFixtures.catalog, capabilities: {
      ...modelFixtures.catalog.capabilities, analytical_profile: {
        ...modelFixtures.catalog.capabilities.analytical_profile, ...profile}}});
    const resources = [{resource_id: 'table:sales', resource_kind: 'table', display_name: 'sales',
      display_path: ['analytics', 'sales']}];

    function answer(overrides = {}) {
      const handlers = {
        semantic_model_capabilities: () => catalog(),
        semantic_model_list: () => ({items: [{model_id: 'id-001', name: 'Sales cube', status: 'draft', revision: 1,
          updated_at: '2026-01-01T00:00:00+00:00'}]}),
        semantic_model_get: () => modelFixtures.draft,
        resource_page: () => ({items: resources}),
        semantic_query_diagnostics: () => ({schema: 'cdeadmin.semantic-query-diagnostics.v1',
          reproducibility: {model_digest: 'model-digest'}}),
        ...overrides,
      };
      api.post.mockImplementation((_url, payload) => Promise.resolve({data: {data:
        (handlers[payload.action] || (() => ({})))(payload.request)}}));
    }
    const actions = () => api.post.mock.calls.map(([, payload]) => payload.action);

    it('opens the BI Models view in place of the retired workspace', async () => {
      answer();
      render(<ProviderWorkspaceContent closeModal={jest.fn()}
        endpointUrl="/workspace/1" initialTab="semantic" />);
      const list = await screen.findByRole('navigation', {name: 'Semantic models'});
      expect(await within(list).findByRole('button', {name: /Sales cube/})).toBeInTheDocument();
      expect(screen.queryByLabelText('Semantic-model task')).not.toBeInTheDocument();
      expect(actions()).toEqual(expect.arrayContaining(['semantic_model_capabilities', 'semantic_model_list']));
      // the Models view reads its own catalog; the workspace bootstrap no longer has to carry it
      expect(api.post).toHaveBeenCalledWith('/workspace/1', {action: 'semantic_model_list', request: {}});
    });

    it('provides the complete semantic model designer', async () => {
      answer();
      render(<ProviderWorkspaceContent closeModal={jest.fn()}
        endpointUrl="/workspace/1" initialTab="semantic" />);
      fireEvent.click(await screen.findByRole('button', {name: /Sales cube/}));
      expect(await screen.findByLabelText(/^Model name/)).toHaveValue('Sales cube');
      expect(screen.getAllByRole('tab').map((item) => item.textContent)).toEqual(expect.arrayContaining([
        'Model', 'Dimensions', 'Measures', 'Security', 'Try it', 'Charts and reports', 'Lineage', 'Revisions',
        'Advanced JSON']));
      fireEvent.click(screen.getByRole('tab', {name: 'Try it'}));
      expect(screen.getByLabelText('Time operation')).toBeInTheDocument();
      expect(screen.getByText('Analytical windows')).toBeInTheDocument();
      expect(screen.getByLabelText(/^Drill mode/)).toBeInTheDocument();
    });

    it('uses provider-family vocabulary in the semantic model designer', async () => {
      const graph = {title: 'Graph analytics', semantic_family: 'graph',
        source_kinds: ['graph', 'node', 'relationship'],
        source_classifications: ['node-set', 'relationship-set', 'path-set'],
        dimension_kinds: ['label', 'property', 'path', 'community'],
        relationship_kinds: ['native-edge', 'path-pattern'],
        measure_kinds: ['property-aggregate', 'path-count', 'score'], grain_vocabulary: 'node-relationship-path'};
      answer({
        semantic_model_capabilities: () => catalog(graph),
        resource_page: () => ({items: [{resource_id: 'node:person', resource_kind: 'node',
          display_name: 'Person', display_path: ['graph', 'Person']}]}),
      });
      render(<ProviderWorkspaceContent closeModal={jest.fn()}
        endpointUrl="/workspace/1" initialTab="semantic" />);
      await screen.findByRole('button', {name: /Sales cube/});
      await waitFor(() => expect(actions()).toContain('resource_page'));
      await act(async () => {});
      fireEvent.click(screen.getByRole('button', {name: 'New model'}));
      expect(await screen.findByLabelText(/^Model name/)).toHaveValue('New semantic model');
      expect(screen.getByRole('table', {name: /Data sources/})).toBeInTheDocument();
      expect(screen.getByRole('combobox', {name: /^Source kind/})).toHaveTextContent('node');
      expect(screen.getByRole('combobox', {name: /^Classification/})).toHaveTextContent('node-set');
    });

    it('provides diagnostics through the Try it tab', async () => {
      answer();
      render(<ProviderWorkspaceContent closeModal={jest.fn()}
        endpointUrl="/workspace/1" initialTab="semantic" />);
      fireEvent.click(await screen.findByRole('button', {name: /Sales cube/}));
      await screen.findByLabelText(/^Model name/);
      fireEvent.click(screen.getByRole('tab', {name: 'Try it'}));
      fireEvent.mouseDown(screen.getByRole('combobox', {name: /^Measures/}));
      fireEvent.click(await screen.findByRole('option', {name: 'Revenue'}));
      fireEvent.click(screen.getByRole('button', {name: 'Query diagnostics'}));
      expect(await screen.findByText(/model-digest/)).toBeInTheDocument();
      expect(api.post).toHaveBeenLastCalledWith('/workspace/1', {
        action: 'semantic_query_diagnostics', request: expect.objectContaining({model_id: 'id-001'}),
      });
    });
  });

  it('renders semantic query results in the pivot workspace', async () => {
    api.post.mockImplementation((_url, payload) => Promise.resolve({data: {
      data: {
        open_session: {session_id: 'semantic-session'},
        execute: {occurrence_id: 'semantic-operation'},
        poll: {
          occurrence: {operation: {terminal: true}},
          rendered_result: {
            component_reference: 'cdeadmin/results/CubePivotView',
            view_model: {
              family: 'cellset',
              axes: {rows: ['region'], columns: [], pages: []},
              levels: ['region'], measures: ['revenue'],
              cells: [{coordinates: {region: 'North'},
                measures: {revenue: 42.5}}], slice: [],
            },
          },
        },
      }[payload.action],
    }}));
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Run', exact: true}));
    const pivot = await screen.findByLabelText('Cube pivot results');
    expect(pivot).toHaveTextContent('North');
    expect(pivot).toHaveTextContent('42.5');
    expect(pivot).toHaveTextContent('Drill down');
    expect(pivot).toHaveTextContent('Transpose axes');
  });
});
