/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  fireEvent, screen, waitFor, within, render, bootstrap, ProviderWorkspaceContent,
  DatabaseTargetWorkspace, ObjectInspectorSection, ResultControls, ServerProfileWorkspace,
  VisualAdministration, inspectorSections, initialObjectDraft, changedFieldDraft,
  ProviderWorkspaceModule, firebirdManifest, installSharedHooks, installWorkspaceHooks,
} from './providerWorkspaceContentShared';

jest.mock('../../../pgadmin/static/js/api_instance');
// Execution contract tests use a text adapter; the native browser gate covers CodeMirror.
jest.mock('../../../pgadmin/static/js/cdeadmin_ui/editors/CodeEditor', () => ({__esModule: true,
  default: ({label, value, onChange, disabled}) => <textarea aria-label={label} value={value}
    disabled={disabled} onChange={event => onChange(event.target.value)} /> }));
// Hosted native renderers need a bounded readiness allowance; assertions and

installSharedHooks();

describe('ProviderWorkspaceContent (properties, forms and catalogs)', () => {
  const workspace = installWorkspaceHooks();
  let api;
  beforeEach(() => { api = workspace.api; });

  it('shows only provider-evidenced property sections', () => {
    const resource = {extensions: {mongodb: {native: {
      definition: {validator: {$jsonSchema: {bsonType: 'object'}}},
      indexes: [],
    }}}};
    expect(inspectorSections(resource, {editor: {
      sections: ['properties', 'definition', 'dependencies', 'security',
        'data', 'operations'],
      data_presentation: null,
    }})).toEqual([
      'properties', 'definition', 'indexes', 'operations',
    ]);
  });

  it('preserves exact provider-declared empty property sections', () => {
    const resource = {extensions: {firebird: {native: {
      property_sections: [
        'properties', 'dependencies', 'dependents', 'operations',
      ],
      dependencies: [], dependents: [],
    }}}};
    expect(inspectorSections(resource, {})).toEqual([
      'properties', 'dependencies', 'dependents', 'operations',
    ]);
  });

  it('renders and submits an exact provider-owned endpoint form', async () => {
    const post = jest.fn().mockResolvedValue({display_name: 'SQLite local'});
    const onSaved = jest.fn();
    render(<ServerProfileWorkspace registration={{
      display_name: 'localhost',
      primary_route: {route_id: 'route-one', configuration: {timeout: 5}},
      forms: {forms: {edit: {
        form_id: 'cdeadmin.sqlite-native.server.edit.v1',
        operation_id: 'edit', title: 'Edit SQLite 3.53 server', fields: [
          {field_id: 'name', label: 'Connection profile name',
            control: 'text', required: true},
          {field_id: 'timeout', route_key: 'timeout',
            label: 'Busy timeout (seconds)', control: 'number',
            required: false, default: 5},
        ],
      }}}}} post={post} setError={jest.fn()} onSaved={onSaved} />);
    expect(screen.getByText('Edit SQLite 3.53 server')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', {
      name: 'Connection profile name',
    }), {target: {value: 'SQLite local'}});
    fireEvent.click(screen.getByRole('button', {
      name: 'Save endpoint profile',
    }));
    await waitFor(() => expect(post).toHaveBeenCalledWith({
      action: 'endpoint_profile_update', request: {
        name: 'SQLite local', timeout: 5,
      },
    }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith({
      display_name: 'SQLite local'}));
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  it('does not invalidate a profile when saving is rejected', async () => {
    const post = jest.fn().mockRejectedValue(new Error('Open sessions'));
    const onSaved = jest.fn();
    const setError = jest.fn();
    render(<ServerProfileWorkspace registration={{forms: {forms: {edit: {
      form_id: 'firebird-profile-edit', title: 'Edit Firebird profile', fields: [],
    }}}}} post={post} setError={setError} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', {name: 'Save endpoint profile'}));
    await waitFor(() => expect(setError).toHaveBeenCalledWith('Open sessions'));
    expect(onSaved).not.toHaveBeenCalled();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it.each(['edit', 'remove'])('does not prompt for engine credentials on a denied local profile %s', async (mode) => {
    const onCredentialRequired = jest.fn();
    api.post.mockRejectedValue({response: {status: 401,
      data: {errormsg: 'Application login required'}}});
    render(<ProviderWorkspaceContent endpointUrl="/workspace/1"
      initialTab="connections" initialContext={{server_mode: mode}}
      onCredentialRequired={onCredentialRequired} />);
    expect(await screen.findByText('Application login required')).toBeInTheDocument();
    expect(onCredentialRequired).not.toHaveBeenCalled();
    expect(api.get).not.toHaveBeenCalled();
  });

  it('forwards a successful focused endpoint edit through the workspace boundary', async () => {
    const result = {display_name: 'Owned Firebird'};
    const onEndpointProfileSaved = jest.fn();
    api.get.mockRejectedValue(new Error('Native Services API unavailable'));
    api.post.mockResolvedValueOnce({data: {data: {
      endpoint_registration: {forms: {forms: {edit: {
        form_id: 'owned-firebird-edit', title: 'Owned Firebird editor', fields: [],
      }}}},
    }}});
    api.post.mockResolvedValue({data: {data: result}});
    render(<ProviderWorkspaceContent endpointUrl="/workspace/1"
      initialTab="connections" initialContext={{server_mode: 'edit'}}
      onEndpointProfileSaved={onEndpointProfileSaved} />);
    fireEvent.click(await screen.findByRole('button', {
      name: 'Save endpoint profile',
    }));
    await waitFor(() => expect(onEndpointProfileSaved).toHaveBeenCalledWith(result));
    expect(onEndpointProfileSaved).toHaveBeenCalledTimes(1);
    expect(api.get).not.toHaveBeenCalled();
    expect(api.post).toHaveBeenCalledWith('/workspace/1', {
      action: 'endpoint_profile_read',
    });
    expect(api.post).toHaveBeenCalledWith('/workspace/1', {
      action: 'endpoint_profile_update', request: {},
    });
  });

  it.each(firebirdManifest.registration.connection_fields.find(
    (field) => field.field_id === 'decfloat_round').options)(
    'saves the declared Firebird endpoint rounding choice $label', async (option) => {
      const field = firebirdManifest.registration.connection_fields.find(
        (item) => item.field_id === 'decfloat_round');
      const post = jest.fn().mockResolvedValue({display_name: 'Firebird lab'});
      const setError = jest.fn();
      render(<ServerProfileWorkspace registration={{
        display_name: 'Firebird lab',
        primary_route: {route_id: 'owned-rounding', configuration: {
          decfloat_round: option.value === 'UP' ? 'DOWN' : 'UP',
        }},
        forms: {forms: {edit: {
          form_id: 'cdeadmin.firebird-native.server.edit.v1',
          operation_id: 'edit', title: 'Edit Firebird 5.0 server', fields: [field],
        }}},
      }} post={post} setError={setError} />);
      fireEvent.mouseDown(screen.getByRole('combobox', {
        name: 'Initial DECFLOAT rounding mode',
      }));
      fireEvent.click(await screen.findByRole('option', {name: option.label, exact: true}));
      fireEvent.click(screen.getByRole('button', {name: 'Save endpoint profile'}));
      await waitFor(() => expect(post).toHaveBeenCalledWith({
        action: 'endpoint_profile_update', request: {decfloat_round: option.value},
      }));
      expect(await screen.findByText('Endpoint profile saved. Verify it before reconnecting.'))
        .toBeInTheDocument();
      expect(setError).toHaveBeenCalledWith(null);
    });

  it('edits an explicit endpoint and reveals only the typed password', async () => {
    const post = jest.fn().mockResolvedValue({display_name: 'Firebird lab'});
    render(<ServerProfileWorkspace registration={{
      display_name: 'Firebird lab', is_password_saved: true,
      primary_route: {route_id: 'route-one', configuration: {
        host: '127.0.0.10', port: 53050, user: 'SYSDBA',
      }},
      forms: {forms: {edit: {
        form_id: 'cdeadmin.firebird-native.server.edit.v1',
        operation_id: 'edit', title: 'Edit Firebird 5.0 server', fields: [
          {field_id: 'name', label: 'Connection profile name',
            control: 'text', required: true},
          {field_id: 'host', label: 'Server host or address',
            control: 'text', required: true},
          {field_id: 'port', label: 'Server port', control: 'number',
            required: true},
          {field_id: 'username', label: 'User or principal',
            control: 'text', required: false},
          {field_id: 'password', label: 'Password', control: 'password',
            required: false},
          {field_id: 'save_password',
            label: 'Save default connection credentials',
            control: 'boolean', required: false, default: false},
        ],
      }}}}} post={post} setError={jest.fn()} />);

    expect(screen.getByRole('spinbutton', {name: 'Server port'}))
      .toHaveValue(53050);
    expect(screen.getByRole('textbox', {name: 'Server host or address'}))
      .toHaveValue('127.0.0.10');
    expect(screen.getByRole('textbox', {name: 'User or principal'}))
      .toHaveValue('SYSDBA');
    expect(screen.getByRole('checkbox', {
      name: 'Save default connection credentials',
    })).toBeChecked();
    const password = screen.getByLabelText('Password');
    expect(password).toHaveAttribute('type', 'password');
    fireEvent.change(password, {target: {value: 'typed-only-secret'}});
    fireEvent.click(screen.getByRole('button', {name: 'Show password'}));
    expect(password).toHaveAttribute('type', 'text');
    fireEvent.click(screen.getByRole('button', {name: 'Hide password'}));
    expect(password).toHaveAttribute('type', 'password');
    fireEvent.click(screen.getByRole('button', {
      name: 'Save endpoint profile',
    }));
    await waitFor(() => expect(post).toHaveBeenCalledWith({
      action: 'endpoint_profile_update', request: {
        name: 'Firebird lab', host: '127.0.0.10', port: 53050,
        username: 'SYSDBA', password: 'typed-only-secret',
        save_password: true,
      },
    }));
  });

  it('requires the exact profile name before removing an endpoint', async () => {
    const post = jest.fn().mockResolvedValue({removed: true});
    const onRemoved = jest.fn();
    render(<ServerProfileWorkspace registration={{
      display_name: 'SQLite local',
      primary_route: {route_id: 'route-one', configuration: {}},
      forms: {forms: {remove: {
        form_id: 'cdeadmin.sqlite-native.server.remove.v1',
        operation_id: 'remove', title: 'Remove SQLite 3.53 server', fields: [
          {field_id: 'confirmation',
            label: 'Type the connection profile name to confirm',
            control: 'text', required: true},
        ],
      }}}}} post={post} setError={jest.fn()} initialMode="remove"
    onRemoved={onRemoved} />);
    const remove = screen.getByRole('button', {
      name: 'Remove endpoint registration',
    });
    expect(remove).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', {
      name: 'Type the connection profile name to confirm',
    }), {target: {value: 'SQLite local'}});
    expect(remove).toBeEnabled();
    fireEvent.click(remove);
    await waitFor(() => expect(post).toHaveBeenCalledWith({
      action: 'endpoint_profile_remove', request: {
        confirmation: 'SQLite local',
      },
    }));
    expect(onRemoved).toHaveBeenCalledWith({removed: true});
  });

  it('warns that incomplete catalogs are not empty databases', () => {
    render(<ObjectInspectorSection resource={{display_name: 'Example',
      resource_kind: 'database', extensions: {mysql: {native: {
        catalog_coverage: {state: 'partial', failed_query_count: 1,
          failures: [{category: 'permission_denied', error_code: '1142'}]},
      }}}}} />);
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Catalog visibility is incomplete');
    expect(screen.getByRole('alert')).toHaveTextContent('permission_denied');
    expect(screen.getByRole('alert')).toHaveTextContent('1142');
  });

  it.each([false, true])('makes metadata panels keyboard focusable (tabbed=%s)', (tabbed) => {
    render(<ObjectInspectorSection tabbed={tabbed} resource={{
      display_name: 'V', resource_kind: 'view', extensions: {firebird: {native: {
        property_sections: ['ddl'], ddl: 'CREATE VIEW "LongName" AS SELECT 1;',
      }}},
    }} />);
    const panel = screen.getByRole('tabpanel', {name: 'ddl object section'});
    expect(panel).toHaveAttribute('tabindex', '0');
    expect(panel).toHaveTextContent('CREATE VIEW');
    if (!tabbed) {
      const style = getComputedStyle(screen.getByRole('combobox'));
      expect({whiteSpace: style.whiteSpace, textOverflow: style.textOverflow,
        overflowWrap: style.overflowWrap}).toEqual({
        whiteSpace: 'normal', textOverflow: 'clip', overflowWrap: 'anywhere'});
    }
    expect(panel.querySelector('span')).toHaveStyle({overflowWrap: 'anywhere'});
  });

  it('shows several statistics rows as one table', () => {
    render(<ObjectInspectorSection initialSection="statistics" resource={{
      display_name: 'nightly vacuum', resource_kind: 'pgagent-job',
      extensions: {postgresql: {native: {
        property_sections: ['properties', 'statistics'],
        statistics: [
          {Run: 2, Status: 's', Duration: '00:00:02'},
          {Run: 1, Status: 'f', Duration: '00:00:09', Note: 'retry'},
        ]}}}}} />);
    const table = screen.getByRole('table', {name: 'Statistics rows'});
    expect(within(table).getAllByRole('columnheader').map((cell) =>
      cell.textContent)).toEqual(['Run', 'Status', 'Duration', 'Note']);
    const cells = within(table).getAllByRole('cell').map((cell) =>
      cell.textContent);
    expect(cells).toEqual(['2', 's', '00:00:02', 'Not set',
      '1', 'f', '00:00:09', 'retry']);
    expect(screen.queryByRole('list')).toBeNull();
  });

  it('keeps one object\'s statistics as a name and value grid', () => {
    render(<ObjectInspectorSection initialSection="statistics" resource={{
      display_name: 'assets', resource_kind: 'table',
      extensions: {postgresql: {native: {
        property_sections: ['properties', 'statistics'],
        statistics: {'Table size': '16 kB', 'Live tuples': 3}}}}}} />);
    expect(screen.queryByRole('table', {name: 'Statistics rows'})).toBeNull();
    expect(screen.getByRole('table', {name: 'Native provider properties'}))
      .toHaveTextContent('Live tuples');
  });

  it.each([false, true])('supports host-owned or bounded scrolling (%s)', (containedScroll) => {
    render(<ObjectInspectorSection containedScroll={containedScroll}
      resource={{display_name: 'V', resource_kind: 'view',
        extensions: {firebird: {native: {property_sections: ['ddl'],
          ddl: 'CREATE VIEW V AS SELECT 1;'}}}}} />);
    expect(screen.getByRole('tabpanel')).toHaveStyle({
      overflow: containedScroll ? 'auto' : 'visible',
      maxHeight: containedScroll ? '320px' : 'none'});
  });

  it.each([false, true])('lays out nested column metadata for its host (%s)', (containedScroll) => {
    render(<ObjectInspectorSection containedScroll={containedScroll}
      resource={{display_name: 'T', resource_kind: 'table',
        extensions: {firebird: {native: {property_sections: ['columns'],
          columns: [{name: 'CUSTOMER_ID', details: {nullable: false,
            description: 'A long column description'}}]}}}}} />);
    const tables = screen.getAllByRole('table');
    expect(tables).toHaveLength(2);
    tables.forEach((table, index) => {
      const columns = getComputedStyle(table).gridTemplateColumns;
      expect(columns).toBe(containedScroll ?
        (index === 0 ? 'minmax(160px, 0.7fr) minmax(220px, 1fr)' :
          'minmax(100px, 0.7fr) minmax(140px, 1fr)') : 'minmax(0, 1fr)');
    });
    expect(screen.getByText('CUSTOMER_ID')).toBeVisible();
    expect(screen.getByText('No')).toBeVisible();
  });

  it('surfaces provider catalog warnings without interpreting markup', () => {
    render(<ObjectInspectorSection resource={{display_name: 'T',
      resource_kind: 'table', extensions: {firebird: {native: {
        catalog_warnings: [null, {}, '',
          'Unresolved grant: <script>do not execute</script>'],
      }}}}} />);
    expect(screen.getAllByRole('alert')).toHaveLength(1);
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Unresolved grant: <script>do not execute</script>');
    expect(screen.getByRole('alert').querySelector('script')).toBeNull();
  });

  it('refreshes Firebird view length warnings without executing an operation', () => {
    const onOperation = jest.fn();
    const view = (warnings) => ({display_name: 'V', resource_kind: 'view',
      extensions: {firebird: {native: {catalog_warnings: warnings}}}});
    const warning = 'View column B has inconsistent or missing native UTF8 CHAR length metadata. Firebird may reject result fetching with string truncation.';
    const {rerender} = render(<ObjectInspectorSection tabbed
      resource={view([warning])} onOperation={onOperation} />);
    expect(screen.getByRole('alert')).toHaveTextContent(warning);
    expect(onOperation).not.toHaveBeenCalled();
    rerender(<ObjectInspectorSection tabbed
      resource={view([])} onOperation={onOperation} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(onOperation).not.toHaveBeenCalled();
  });

  it('removes inapplicable multi-selection privileges after a target change', () => {
    const fields = [{field_id: 'privileges', control: 'multiselect', options: [
      {value: 'SELECT', visible_when: {field_id: 'kind', equals: 'TABLE'}},
      {value: 'EXECUTE', visible_when: {field_id: 'kind', equals: 'PROCEDURE'}},
    ]}];
    expect(changedFieldDraft(fields, {kind: 'TABLE', privileges: ['SELECT']},
      'kind', 'PROCEDURE').privileges).toEqual([]);
    expect(changedFieldDraft(fields, {kind: 'PROCEDURE', privileges: ['EXECUTE']},
      'kind', 'PROCEDURE').privileges).toEqual(['EXECUTE']);
    expect(changedFieldDraft(fields, {kind: 'TABLE', privileges: 'SELECT'},
      'kind', 'PROCEDURE').privileges).toEqual([]);
  });

  it('opens the selected object browser and its data view without mutations', async () => {
    const table = {resource_id: 'table:assets', resource_kind: 'table',
      display_name: 'ASSETS', authority_path: ['table', 'ASSETS']};
    api.get.mockResolvedValue({data: {data: {...bootstrap,
      resource_page: {items: [table]},
      visual_admin: {objects: [{resource_kind: 'table', title: 'Table',
        editor: {sections: ['properties', 'data']}, operations: [{
          operation_id: 'inspect', title: 'Inspect table',
          execution_available: true, target_required: true,
          mutation_class: 'read', form: {fields: []},
        }]}]},
    }}});
    api.post.mockResolvedValue({data: {data: table}});
    render(<ProviderWorkspaceContent endpointUrl="/workspace/1"
      initialTab="object" initialContext={{resource_id: table.resource_id,
        resource_kind: 'table', operation_id: 'inspect'}} />);
    fireEvent.click(await screen.findByRole('button', {
      name: 'Browse object data',
    }));
    expect(await screen.findByRole('button', {name: 'Load rows'}))
      .toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Back'}));
    expect(await screen.findByRole('button', {name: 'Browse object data'}))
      .toBeInTheDocument();
    expect(api.post.mock.calls.every(([, body]) =>
      body.action === 'resource_inspect')).toBe(true);
  });

  it('keeps a sequence editor on its object and invalidates edited plans', async () => {
    const sequence = {resource_id: 'sequence:one', resource_kind: 'sequence',
      display_name: 'Sequence one', extensions: {firebird: {native: {
        state: {value: 12}, ddl: 'CREATE SEQUENCE ONE;',
        dependencies: [], privileges: [],
      }}}};
    const post = jest.fn(async ({action}) => {
      if (action === 'resource_inspect') return sequence;
      if (action === 'visual_admin_validate') return {valid: true};
      if (action === 'visual_admin_plan') return {
        plan_id: 'plan-one', plan_digest: 'digest', state: 'ready',
        execution_available: true,
      };
      return {};
    });
    render(<VisualAdministration objectEditor selectedResource={sequence}
      initialResourceKind="sequence" initialOperationId="inspect"
      resources={[sequence, {...sequence, resource_id: 'sequence:two'}]}
      post={post} setError={jest.fn()} catalog={{objects: [{
        resource_kind: 'sequence', title: 'Sequence', operations: [
          {operation_id: 'inspect', title: 'Inspect sequence',
            target_required: true, form: {fields: []}},
          {operation_id: 'create', title: 'Create sequence',
            target_required: false, form: {fields: []}},
          {operation_id: 'alter', title: 'Alter sequence',
            target_required: true, form: {fields: [{
              field_id: 'restart', label: 'Restart value', control: 'number',
            }]}},
          {operation_id: 'unsupported', title: 'Unsupported operation',
            native_supported: false, form: {fields: []}},
        ],
      }, {resource_kind: 'table', title: 'Table', operations: [{
        operation_id: 'alter', title: 'Alter table', form: {fields: []},
      }]}]}} />);
    expect(await screen.findByRole('tab', {name: 'Creation statement (DDL)'}))
      .toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', {name: 'Creation statement (DDL)'}));
    expect(screen.getByRole('tabpanel')).toHaveTextContent('CREATE SEQUENCE ONE;');
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', {name: 'Create sequence'})).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', {name: 'Alter table'})).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', {name: 'Unsupported operation'})).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', {name: 'Target resource'})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', {name: 'Alter sequence'}));
    fireEvent.change(await screen.findByRole('spinbutton', {name: 'Restart value'}),
      {target: {value: '42'}});
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(screen.getByRole('button', {
      name: 'Apply provider plan',
    })).toBeEnabled());
    expect(post).toHaveBeenCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'sequence', operation_id: 'alter',
      target_resource: sequence, draft: {restart: 42},
    }});
    fireEvent.change(screen.getByRole('spinbutton', {name: 'Restart value'}),
      {target: {value: '43'}});
    expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
  });

  it('loads only explicit native field mappings without rounding int64 text', () => {
    const resource = {extensions: {firebird: {native: {
      increment: -3, state: {current_value: '9223372036854775807'},
      description: '  preserve spacing  ', restart: 'do not infer this',
    }}}};
    expect(initialObjectDraft([
      {field_id: 'increment', control: 'number', initial_value_path: ['increment']},
      {field_id: 'observed', control: 'text', initial_value_path: ['state', 'current_value']},
      {field_id: 'description', control: 'multiline', initial_value_path: ['description']},
      {field_id: 'restart', control: 'text'},
    ], resource)).toEqual({increment: -3, observed: '9223372036854775807',
      description: '  preserve spacing  ', restart: ''});
  });

  it('omits unchanged loaded values and refreshes state after applying an edit', async () => {
    const object = {resource_id: 'sequence:one', resource_kind: 'sequence',
      display_name: 'Sequence one', extensions: {firebird: {native: {
        increment: 2, description: 'existing comment',
      }}}};
    let refreshed = false;
    const post = jest.fn(async ({action}) => {
      if (action === 'resource_inspect') return refreshed ? {
        ...object, extensions: {firebird: {native: {
          increment: 2, description: 'updated comment',
        }}},
      } : object;
      if (action === 'visual_admin_validate') return {valid: true};
      if (action === 'visual_admin_plan') return {plan_id: 'p', plan_digest: 'd',
        state: 'ready', execution_available: true};
      refreshed = true;
      return {provider_result: {state: 'applied'}};
    });
    render(<VisualAdministration objectEditor selectedResource={object}
      resources={[object]} initialOperationId="alter" initialResourceKind="sequence"
      post={post} setError={jest.fn()} catalog={{objects: [{
        resource_kind: 'sequence', title: 'Sequence', operations: [{
          operation_id: 'alter', title: 'Alter', target_required: true,
          form: {fields: [
            {field_id: 'increment', label: 'Increment', control: 'number',
              initial_value_path: ['increment']},
            {field_id: 'description', label: 'Comment', control: 'multiline',
              initial_value_path: ['description']},
          ]},
        }],
      }]}} />);
    await waitFor(() => expect(screen.getByRole('textbox', {name: 'Comment'}))
      .toHaveValue('existing comment'));
    expect(screen.getByRole('spinbutton', {name: 'Increment'})).toHaveValue(2);
    fireEvent.change(screen.getByRole('textbox', {name: 'Comment'}),
      {target: {value: 'updated comment'}});
    expect(screen.queryByRole('button', {name: 'Refresh object properties'}))
      .not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Apply provider plan'}))
      .toBeEnabled());
    expect(post).toHaveBeenCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'sequence', operation_id: 'alter', target_resource: object,
      draft: {description: 'updated comment'},
    }});
    fireEvent.click(screen.getByRole('button', {name: 'Apply provider plan'}));
    await waitFor(() => expect(post.mock.calls.filter(([body]) =>
      body.action === 'resource_inspect')).toHaveLength(2));
    expect(await screen.findByRole('button', {name: 'Refresh object properties'}))
      .toBeEnabled();
    expect(screen.getByRole('textbox', {name: 'Comment'})).toHaveValue('updated comment');
    expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
  });

  it('shows local registration failure without discarding or replaying native success', async () => {
    const post = jest.fn(async ({action}) => {
      if (action === 'visual_admin_validate') return {valid: true};
      if (action === 'visual_admin_plan') return {plan_id: 'p', plan_digest: 'd',
        state: 'ready', execution_available: true};
      return {provider_result: {accepted: true, native_database_created: true},
        workspace_follow_up: [{action: 'register_created_database',
          state: 'failed', automatic_mutation_retry: false,
          message: 'Registration unavailable. Do not repeat the native operation.'}]};
    });
    render(<VisualAdministration resources={[]} post={post} setError={jest.fn()}
      initialResourceKind="database" initialOperationId="create"
      catalog={{objects: [{resource_kind: 'database', title: 'Database',
        operations: [{operation_id: 'create', title: 'Create database',
          target_required: false, form: {fields: []}}]}]}} />);
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(screen.getByRole('button',
      {name: 'Apply provider plan'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Apply provider plan'}));
    expect(await screen.findByLabelText('Connection registration follow-up required'))
      .toHaveTextContent('Do not repeat the native operation.');
    expect(screen.getByLabelText('Provider operation result'))
      .toHaveTextContent('"native_database_created": true');
    expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
    expect(post.mock.calls.filter(([body]) =>
      body.action === 'visual_admin_apply')).toHaveLength(1);
  });

  it.each([true, false])('preserves service outcome when released=%s', async (released) => {
    const post = jest.fn(async ({action}) => {
      if (action === 'visual_admin_validate') return {valid: true};
      if (action === 'visual_admin_plan') return {plan_id: 'p', plan_digest: 'd',
        state: 'ready', execution_available: true};
      return {provider_result: {accepted: true, driver_observation: {
        schema: 'cdeadmin.firebird-service-result.v1',
        server_completed: true, output: ['Native service result'],
        service_release: {service_handle_released: released},
      }}};
    });
    render(<VisualAdministration resources={[]} post={post} setError={jest.fn()}
      initialResourceKind="database" initialOperationId="database_statistics"
      catalog={{objects: [{resource_kind: 'database', title: 'Database',
        operations: [{operation_id: 'database_statistics', title: 'Database statistics',
          target_required: false, form: {fields: []}}]}]}} />);
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(screen.getByRole('button',
      {name: 'Apply provider plan'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Apply provider plan'}));
    expect(await screen.findByLabelText('Firebird native service output'))
      .toHaveTextContent('Native service result');
    if (released) {
      expect(screen.queryByLabelText('Firebird service cleanup required')).not.toBeInTheDocument();
    } else {
      expect(screen.getByLabelText('Firebird service cleanup required'))
        .toHaveTextContent('Do not replay the operation.');
    }
    expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
    expect(post.mock.calls.filter(([body]) =>
      body.action === 'visual_admin_apply')).toHaveLength(1);
  });

  it.each(['ok', 'reload', 'execute', 'deferred'])('does not replay an edit after %s outcome', async (outcome) => {
    const object = {resource_id: 'sequence:one', resource_kind: 'sequence',
      display_name: 'Sequence one'};
    const applied = {provider_result: {accepted: true,
      ...(outcome === 'deferred' ? {catalog_refresh_deferred: true} : {})}};
    const post = jest.fn(async ({action}) => {
      if (action === 'resource_inspect') return object;
      if (action === 'visual_admin_validate') return {valid: true};
      if (action === 'visual_admin_plan') return {plan_id: 'p', plan_digest: 'd',
        state: 'ready', execution_available: true};
      if (action === 'visual_admin_apply') {
        if (outcome === 'execute') throw new Error('Response lost');
        return applied;
      }
      throw new Error('Unexpected request ' + action);
    });
    const reload = jest.fn(async () => {
      if (outcome === 'reload') throw new Error('Catalog temporarily unavailable');
    });
    const setError = jest.fn();
    render(<VisualAdministration objectEditor selectedResource={object}
      resources={[object]} initialOperationId="alter" initialResourceKind="sequence"
      post={post} setError={setError} onMutationApplied={reload}
      catalog={{objects: [{resource_kind: 'sequence', operations: [{
        operation_id: 'alter', title: 'Alter', target_required: true,
        form: {fields: [{field_id: 'increment', label: 'Increment',
          control: 'number'}]},
      }]}]}} />);
    fireEvent.change(await screen.findByRole('spinbutton', {name: 'Increment'}),
      {target: {value: '3'}});
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Apply provider plan'}))
      .toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Apply provider plan'}));
    if (outcome === 'deferred') {
      expect(await screen.findByText(/Automatic metadata refresh is deferred/))
        .toHaveTextContent('Reconnect and refresh after the server is available. Do not repeat the request.');
      expect(reload).not.toHaveBeenCalled();
    } else if (outcome === 'execute') {
      await waitFor(() => expect(setError).toHaveBeenCalledWith('Response lost'));
      expect(reload).not.toHaveBeenCalled();
    } else {
      await waitFor(() => expect(reload).toHaveBeenCalledWith({
        targetResource: object, operationId: 'alter', result: applied,
      }));
    }
    expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
    expect(post.mock.calls.filter(([payload]) =>
      payload.action === 'visual_admin_apply')).toHaveLength(1);
    expect(post.mock.calls.filter(([payload]) =>
      payload.action === 'resource_inspect')).toHaveLength(1);
    if (outcome === 'reload') {
      expect(await screen.findByText(/Do not repeat the operation/))
        .toHaveTextContent('Catalog temporarily unavailable');
    } else {
      expect(screen.queryByText(/Do not repeat the operation/)).not.toBeInTheDocument();
    }
  });

  it.each(['procedure', 'function', 'package', 'collection', 'hash', 'relationship'])(
    'keeps %s native editing and security operations on the selected object', async (kind) => {
      const object = {resource_id: `${kind}:one`, resource_kind: kind,
        display_name: 'Object one', extensions: {test: {native: {
          definition: 'native definition', dependencies: ['dependency one'],
          dependents: ['dependent one'], privileges: [{principal: 'reader'}],
        }}}};
      const post = jest.fn(async ({action}) => {
        if (action === 'resource_inspect') return object;
        if (action === 'visual_admin_validate') return {valid: true};
        if (action === 'visual_admin_plan') return {
          plan_id: 'native-plan', plan_digest: 'native-digest',
          state: 'ready', execution_available: true,
        };
        return {provider_result: {state: 'applied'}};
      });
      render(<VisualAdministration objectEditor selectedResource={object}
        initialResourceKind={kind} initialOperationId="inspect"
        resources={[object]} post={post} setError={jest.fn()}
        catalog={{objects: [{resource_kind: kind, title: kind, operations: [
          {operation_id: 'inspect', title: 'Inspect', target_required: true,
            form: {fields: []}},
          {operation_id: 'alter', title: 'Edit native definition',
            target_required: true, confirmation_required: true,
            form: {fields: [{field_id: 'body', label: 'Native body',
              control: 'code'}]}},
          {operation_id: 'grant', title: 'Grant permissions',
            target_required: true, form: {fields: [{field_id: 'principal',
              label: 'Principal', control: 'text'}]}},
        ]}]}} />);
      fireEvent.click(await screen.findByRole('tab', {name: 'Depends on'}));
      expect(screen.getByRole('tabpanel')).toHaveTextContent('dependency one');
      fireEvent.click(screen.getByRole('tab', {name: 'Privileges and grants'}));
      expect(screen.getByRole('tabpanel')).toHaveTextContent('reader');
      fireEvent.click(screen.getByRole('tab', {name: 'Edit native definition'}));
      fireEvent.change(await screen.findByRole('textbox', {name: 'Native body'}),
        {target: {value: 'engine-native content'}});
      fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
      const confirm = await screen.findByRole('checkbox', {
        name: 'I confirm this provider-planned operation.',
      });
      expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
      fireEvent.click(confirm);
      fireEvent.click(screen.getByRole('button', {name: 'Apply provider plan'}));
      await waitFor(() => expect(post).toHaveBeenCalledWith({
        action: 'visual_admin_apply', request: {
          plan_id: 'native-plan', plan_digest: 'native-digest', confirmed: true,
        },
      }));
      fireEvent.click(screen.getByRole('tab', {name: 'Grant permissions'}));
      expect(await screen.findByRole('textbox', {name: 'Principal'})).toBeInTheDocument();
      expect(screen.queryByRole('textbox', {name: 'Native body'})).not.toBeInTheDocument();
      expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
    });

  it.each(['CEILING', 'UP', 'HALF_UP', 'HALF_EVEN', 'HALF_DOWN', 'DOWN',
    'FLOOR', 'REROUND', 'NATIVE_DEFAULT', 'SERVER_DEFAULT'].flatMap(rounding =>
    [undefined, 'NATIVE_DEFAULT', 'SERVER_DEFAULT', 'SUPPRESS'].map(linger =>
      [rounding, linger])))(
    'renders saved rounding %s and linger %s separately from native observations', async (rounding, linger) => {
      api.get.mockResolvedValue({data: {data: {
        ...bootstrap,
        endpoint: {
          ...bootstrap.endpoint,
          provider_id: 'org.cdeadmin.firebird',
          verified_runtime_family: 'firebird',
          verified_runtime_version: '5.0.4',
        },
        database_targets: {
          targets: [{target_id: 'database-one', display_name: 'example.fdb',
            database: '/firebird/data/example.fdb', active: true,
            configuration: {charset: 'UTF8', transaction_isolation: 'SNAPSHOT',
              decfloat_round: rounding, no_linger: linger}}],
        },
        resource_page: {items: [{
          resource_id: 'server:Firebird', resource_kind: 'server',
          display_name: 'Firebird',
          extensions: {firebird: {native: {architecture: 'Firebird/linux'}}},
        }, {
          resource_id: 'database:example.fdb', resource_kind: 'database',
          display_name: 'example.fdb',
          extensions: {firebird: {native: {page_size: '8192',
            ods_major: '13', ods_minor: '1', sql_dialect: '3',
            default_character_set: 'UTF8', forced_writes: '1'}}},
        }]},
      }}});
      render(<ProviderWorkspaceContent closeModal={jest.fn()}
        endpointUrl="/workspace/1" initialTab="properties"
        initialContext={{resource_id: 'database-one'}} />);
      expect(await screen.findByText('example.fdb — Firebird database properties'))
        .toBeInTheDocument();
      expect(screen.getByText('Firebird server observations')).toBeInTheDocument();
      expect(screen.getByText('Firebird/linux')).toBeInTheDocument();
      expect(screen.getByText('Firebird format and dialect')).toBeInTheDocument();
      expect(screen.getByText('Firebird storage and durability')).toBeInTheDocument();
      expect(screen.getByText('Firebird connection defaults')).toBeInTheDocument();
      expect(screen.getByText('Initial DECFLOAT rounding mode')).toBeInTheDocument();
      expect(screen.getByText('Initial DECFLOAT rounding mode').nextElementSibling)
        .toHaveTextContent(({NATIVE_DEFAULT: 'Native default',
          SERVER_DEFAULT: 'Use server preference'})[rounding] || rounding);
      if(linger === undefined) {
        expect(screen.queryByText('Attachment linger policy')).not.toBeInTheDocument();
      } else {
        expect(screen.getByText('Attachment linger policy').nextElementSibling)
          .toHaveTextContent(({NATIVE_DEFAULT: 'Native default',
            SERVER_DEFAULT: 'Use server preference',
            SUPPRESS: 'Suppress current cache linger (SuperServer)'})[linger]);
      }
      expect(screen.getByText('Database filename or alias')).toBeInTheDocument();
      expect(screen.getByText('/firebird/data/example.fdb')).toBeInTheDocument();
      expect(screen.getByText('8192')).toBeInTheDocument();
      expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    });

  it('does not call an engine-provided starter empty when there are no presets', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      languages: [{language_profile: 'firebird-sql', title: 'Firebird SQL',
        starter_source: 'SELECT 42 FROM RDB$DATABASE'}],
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    await waitFor(() => expect(screen.getByLabelText('Query source'))
      .toHaveValue('SELECT 42 FROM RDB$DATABASE'));
    expect(screen.getByRole('region', {name: 'Provider query workspace'}))
      .toHaveStyle({overflow: 'auto', minHeight: '0'});
    expect(screen.queryByText(/editor is intentionally empty/)).not.toBeInTheDocument();
  });

  it('renders MariaDB properties as exact provider-specific groups', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      endpoint: {
        ...bootstrap.endpoint,
        provider_id: 'org.cdeadmin.mariadb',
        profile_id: 'mariadb-native',
        verified_runtime_family: 'mariadb',
        verified_runtime_version: '12.2.2',
      },
      database_targets: {
        targets: [{target_id: 'database-one', display_name: 'cdeadmin_demo',
          database: 'cdeadmin_demo', active: true,
          configuration: {charset: 'utf8mb4',
            collation: 'utf8mb4_general_ci'}}],
      },
      resource_page: {items: [{
        resource_id: 'server:MariaDB', resource_kind: 'server',
        display_name: 'MariaDB',
        extensions: {mariadb: {native: {version: '12.2.2-MariaDB',
          hostname: 'mariadb-qa', server_id: 1,
          default_storage_engine: 'InnoDB', tx_isolation: 'REPEATABLE-READ',
          log_bin: 1, binlog_format: 'MIXED', wsrep_on: 0}}},
      }, {
        resource_id: 'database:cdeadmin_demo', resource_kind: 'database',
        display_name: 'cdeadmin_demo',
        extensions: {mariadb: {native: {
          default_character_set: 'utf8mb4',
          default_collation: 'utf8mb4_general_ci', schema_comment: ''}}},
      }]},
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="properties"
      initialContext={{resource_id: 'database-one'}} />);
    expect(await screen.findByText(
      'cdeadmin_demo — MariaDB database properties')).toBeInTheDocument();
    expect(screen.getByText('MariaDB database defaults')).toBeInTheDocument();
    expect(screen.getByText('Database comment').nextElementSibling).toHaveTextContent('');
    expect(screen.getByText('MariaDB server identity')).toBeInTheDocument();
    expect(screen.getByText('MariaDB server configuration')).toBeInTheDocument();
    expect(screen.getByText('MariaDB session and transaction state'))
      .toBeInTheDocument();
    expect(screen.getByText('MariaDB replication and binary logging'))
      .toBeInTheDocument();
    expect(screen.getByText('REPEATABLE-READ')).toBeInTheDocument();
    expect(screen.getByText('MIXED')).toBeInTheDocument();
    expect(screen.getAllByText('Yes').length).toBeGreaterThan(0);
    expect(screen.queryByText(/\{"/)).not.toBeInTheDocument();
  });

  it('shows exact dialect and metrics blockers without engine fallbacks', async () => {
    api.get.mockResolvedValue({data: {data: {
      ...bootstrap,
      engine_contracts: {
        state: 'blocked',
        dialect: {state: 'blocked'}, metrics: {state: 'blocked'},
      },
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()}
      endpointUrl="/workspace/1" initialTab="studio" />);
    expect(await screen.findByLabelText('Exact engine contract status'))
      .toHaveTextContent('dialect, metrics');
    expect(screen.getByLabelText('Exact engine contract status'))
      .toHaveTextContent('will not substitute another engine family');
  });

  it('renders and submits the exact provider-owned database form', async () => {
    const databaseForm = {
      form_set_id: 'cdeadmin.firebird-native.database.forms.v1',
      lifecycle_resource_kind: 'database',
      forms: {
        define: {
          form_id: 'cdeadmin.firebird-native.database.define.v1',
          operation_id: 'define', title: 'Define Firebird database',
          supported: true, fields: [
            {field_id: 'database', label: 'Firebird database filename or alias',
              control: 'text', required: true},
            {field_id: 'display_name', label: 'Navigator display name',
              control: 'text', required: false},
            {field_id: 'charset', label: 'Connection character set',
              control: 'text', required: false, default: 'UTF8'},
          ],
        },
        create: {form_id: 'firebird-create', operation_id: 'create',
          title: 'Create Firebird database', supported: false,
          disabled_reason: 'Unavailable in this test.', fields: []},
      },
    };
    const post = jest.fn().mockResolvedValue({
      forms: databaseForm, target_management: true,
      targets: [], active_target_id: '',
    });
    render(<DatabaseTargetWorkspace initialCatalog={{
      forms: databaseForm, target_management: true,
      targets: [], active_target_id: '',
    }} visualCatalog={{objects: []}} resources={[]} post={post}
    setError={jest.fn()} initialMode="attach" />);

    fireEvent.change(screen.getByRole('textbox', {
      name: /Firebird database filename or alias/,
    }), {target: {value: '/firebird/data/example.fdb'}});
    fireEvent.change(screen.getByRole('textbox', {
      name: /Navigator display name/,
    }), {
      target: {value: 'Example Firebird'},
    });
    fireEvent.click(screen.getByRole('button', {
      name: 'Define Firebird database',
    }));

    await waitFor(() => expect(post).toHaveBeenCalledWith({
      action: 'database_target_attach', request: {
        database: '/firebird/data/example.fdb',
        display_name: 'Example Firebird', charset: 'UTF8',
      },
    }));
    expect(screen.queryByLabelText(
      'Database filename, path, or native name'
    )).not.toBeInTheDocument();
  });

  it('no longer carries the retired semantic workspace helpers', () => {
    // chart selection filters moved to BI dashboard cross-filters (backend: convert_dashboard; see
    // tools/tests/test_cdeadmin_bi_model_migration.py) and the workspace opens the BI Models view instead
    expect(ProviderWorkspaceModule.semanticCrossFilter).toBeUndefined();
    expect(ProviderWorkspaceModule.default).toBeDefined();
  });

  it('delivers a retained export through a named server-side profile', async () => {
    const post = jest.fn().mockResolvedValue({
      state: 'delivered', automatic_retry: false,
    });
    render(<ResultControls rendered={{
      descriptor: {result_id: 'result-one', export_formats: ['pdf']},
      page: {},
    }} history={[]} post={post} onRendered={jest.fn()}
    setError={jest.fn()} setBusy={jest.fn()} allowedFormats={['pdf']}
    deliveryProfiles={[{
      profile_id: 'archive', label: 'Report archive', kind: 's3',
      allowed_formats: ['pdf'],
    }]} />);
    fireEvent.change(screen.getByLabelText('Object filename'), {
      target: {value: 'quarterly-report.pdf'},
    });
    fireEvent.click(screen.getByText('Deliver'));
    await waitFor(() => expect(post).toHaveBeenCalledWith({
      action: 'result_delivery', request: {
        request_key: expect.stringMatching(
          /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
        ),
        result_id: 'result-one', format: 'pdf', profile_id: 'archive',
        target: {object_name: 'quarterly-report.pdf'},
      },
    }));
    expect(await screen.findByText(/Delivery state.*delivered/))
      .toBeInTheDocument();
    expect(screen.getByText(/Automatic retry is disabled/))
      .toBeInTheDocument();
  });

  // Owner direction 2026-11-05: the bound endpoint, database and dialect
  // moved from a banner above the editor into a dialog opened by the
  // toolbar's info button; the content assertions are unchanged.
  it('shows the bound endpoint, database and admitted dialect from the info button', async () => {
    api.get.mockResolvedValue({data: {data: {...bootstrap,
      endpoint: {...bootstrap.endpoint, endpoint_id: 'endpoint-a', display_name: 'Reporting connection'},
      endpoint_registration: {primary_route: {configuration: {host: 'db.example', port: 3307}}},
      database_targets: {targets: [{target_id: 'db-a', display_name: 'Accounts'}]},
    }}});
    render(<ProviderWorkspaceContent closeModal={jest.fn()} endpointUrl="/workspace/1"
      initialTab="studio" initialContext={{database_target_id: 'db-a'}} />);
    const info = await screen.findByRole('button', {name: 'Connection details'});
    expect(screen.queryByRole('status', {name: 'SQL editor connection'})).not.toBeInTheDocument();
    const toolbar = screen.getByLabelText('SQL execution toolbar');
    const buttons = within(toolbar).getAllByRole('button');
    expect(buttons.indexOf(info)).toBe(buttons.indexOf(
      within(toolbar).getByRole('button', {name: 'Close query session'})) + 1);
    fireEvent.click(info);
    const banner = await screen.findByRole('status', {name: 'SQL editor connection'});
    expect(banner).toHaveTextContent('Reporting connection');
    expect(banner).toHaveTextContent('db.example:3307');
    expect(banner).toHaveTextContent('Accounts');
    expect(banner).toHaveTextContent('MySQL SQL');
    expect(banner).toHaveTextContent('Session not open');
    expect(screen.getByLabelText('Max rows')).toHaveValue(500);
  });

  it('requests the next provider-owned result page from its occurrence', async () => {
    const post = jest.fn();
    const onProviderContinuation = jest.fn().mockResolvedValue();
    render(<ResultControls rendered={{
      descriptor: {
        result_id: 'stream-page-one', export_formats: [],
        provider_continuation: 'operation-one',
      },
      page: {next_cursor: null, page_size: 500},
    }} history={[]} post={post} onRendered={jest.fn()}
    setError={jest.fn()} setBusy={jest.fn()}
    onProviderContinuation={onProviderContinuation} />);

    fireEvent.click(screen.getByRole('button', {name: 'Next result page'}));

    await waitFor(() => expect(onProviderContinuation).toHaveBeenCalled());
    expect(post).not.toHaveBeenCalled();
  });

});

