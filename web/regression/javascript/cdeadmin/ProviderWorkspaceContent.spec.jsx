/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  act, fireEvent, screen, waitFor, useState, render, RecordListAdminField,
  VisualAdministration, VisualAdminField, initialObjectDraft, visibleFieldOptions,
  changedFieldDraft, administrationResourceId, administrationOutcomeValue, installSharedHooks,
} from './providerWorkspaceContentShared';

jest.mock('../../../pgadmin/static/js/api_instance');
// Execution contract tests use a text adapter; the native browser gate covers CodeMirror.
jest.mock('../../../pgadmin/static/js/cdeadmin_ui/editors/CodeEditor', () => ({__esModule: true,
  default: ({label, value, onChange, disabled}) => <textarea aria-label={label} value={value}
    disabled={disabled} onChange={event => onChange(event.target.value)} /> }));
// Hosted native renderers need a bounded readiness allowance; assertions and

installSharedHooks();

describe('provider structured record controls', () => {
  it('retains a receipt only for its original or verified renamed object in the same scope', () => {
    const original = {resource_id: 'column:T:A', resource_kind: 'column'};
    const renamed = {...original, resource_id: 'column:T:B'};
    const post = jest.fn();
    const transition = {resource_kind: 'column', previous_resource_id: original.resource_id,
      resource_id: renamed.resource_id, native_identity_verified: true, committed_by_provider: true};
    const value = {provider_result: {resource_identity_change: transition}};
    const outcome = {post, operationId: 'rename', resourceKind: 'column', targetResource: original, value};
    const context = {...outcome, targetResource: renamed};
    expect(administrationOutcomeValue(outcome, context)).toBe(value);
    expect(administrationOutcomeValue(outcome, {...context, targetResource: original})).toBe(value);
    for (const scope of [{post: jest.fn()}, {operationId: 'drop'}, {resourceKind: 'domain'},
      {targetResource: null}, {targetResource: {...renamed, resource_kind: 'domain'}},
      {targetResource: {...renamed, resource_id: 'column:T:C'}},
      {targetResource: {...renamed, resource_id: ''}}]) {
      expect(administrationOutcomeValue(outcome, {...context, ...scope})).toBeNull();
    }
    for (const invalid of [null, {native_identity_verified: false},
      {committed_by_provider: false}, {previous_resource_id: 'other'},
      {resource_kind: 'domain'}, {resource_id: ''}]) {
      const badValue = {provider_result: {resource_identity_change: invalid && {...transition, ...invalid}}};
      const badOutcome = {...outcome, value: badValue};
      expect(administrationOutcomeValue(badOutcome, context)).toBeNull();
      expect(administrationOutcomeValue(badOutcome, {...context, targetResource: original})).toBe(badValue);
    }
    expect(administrationOutcomeValue(null, context)).toBeNull();
    expect(administrationOutcomeValue({...outcome, targetResource: {}},
      {...context, targetResource: {}})).toBeNull();
    const creation = {...outcome, operationId: 'create', targetResource: null};
    expect(administrationOutcomeValue(creation, creation)).toBe(value);
    expect(administrationOutcomeValue(creation, {...creation, targetResource: renamed})).toBeNull();
  });

  it('uses only a verified provider rename identity', () => {
    const target = {resource_id: 'column:T:V', resource_kind: 'column'};
    const receipt = {previous_resource_id: 'column:T:V',
      resource_id: 'column:T:new%3Aname', resource_kind: 'column',
      native_identity_verified: true, committed_by_provider: true};
    expect(administrationResourceId(target, {})).toBe('column:T:V');
    expect(administrationResourceId(target, {provider_result: {
      resource_identity_change: receipt,
    }})).toBe('column:T:new%3Aname');
    for (const invalid of [
      {previous_resource_id: 'other'}, {resource_kind: 'table'},
      {native_identity_verified: false}, {committed_by_provider: false},
      {resource_id: ''}, {resource_id: null}, {resource_id: 42},
    ]) {
      expect(() => administrationResourceId(target, {provider_result: {
        resource_identity_change: {...receipt, ...invalid},
      }})).toThrow('identity transition could not be verified');
    }
  });
  it('preserves hidden computed result types and never guesses an explicit type choice', () => {
    const field = {field_id: 'data_type', control: 'select',
      require_explicit_choice: true,
      visible_when: {field_id: 'action', in: ['TYPE', 'TYPE COMPUTED']},
      options: [{value: 'INTEGER'}, {value: 'BLOB', visible_when: {
        field_id: 'action', equals: 'TYPE COMPUTED'}}]};
    let draft = {action: 'POSITION', data_type: 'BLOB'};
    draft = changedFieldDraft([field], draft, 'action', 'COMPUTED');
    expect(draft.data_type).toBe('BLOB');
    draft = changedFieldDraft([field], draft, 'action', 'TYPE COMPUTED');
    expect(draft.data_type).toBe('BLOB');
    draft = changedFieldDraft([field], draft, 'action', 'TYPE');
    expect(draft.data_type).toBe('');
    expect(changedFieldDraft([field], draft, 'action', 'TYPE COMPUTED').data_type).toBe('');
  });

  it('prefills precise provider type attributes without stringifying numbers', () => {
    const values = {data_type: 'NUMERIC', precision: 38, scale: 21};
    const fields = Object.keys(values).map((key) => ({field_id: key,
      initial_value_path: ['type_editor', key], submit_unchanged: true}));
    expect(initialObjectDraft(fields, {extensions: {firebird: {native: {
      type_editor: values,
    }}}})).toEqual(values);
    expect(initialObjectDraft([{field_id: 'data_type', default: null,
      initial_value_path: ['type_editor', 'data_type']}], {})).toEqual({data_type: ''});
  });

  it('filters actions using inspected native context and prefills column position', () => {
    const action = {field_id: 'action', control: 'select', default: 'COMPUTED',
      option_values_path: ['alteration', 'allowed_actions'], options:
        ['POSITION', 'COMPUTED', 'IDENTITY'].map((value) => ({value, label: value}))};
    const resource = {extensions: {firebird: {native: {alteration: {
      allowed_actions: ['POSITION', 'IDENTITY', 'UNDECLARED'], position: 8,
    }}}}};
    expect(visibleFieldOptions(action, {}, resource).options.map((o) => o.value))
      .toEqual(['POSITION', 'IDENTITY']);
    expect(initialObjectDraft([action, {field_id: 'position', control: 'number',
      initial_value_path: ['alteration', 'position']}], resource))
      .toEqual({action: 'POSITION', position: 8});
    for (const missing of [null, {}, {native: {alteration: {allowed_actions: []}}},
      {native: {alteration: {allowed_actions: 'POSITION'}}}]) {
      expect(visibleFieldOptions(action, {}, missing).options).toEqual([]);
      expect(initialObjectDraft([action], missing)).toEqual({action: ''});
    }
  });

  it('updates allowed actions when a different column is inspected', async () => {
    const field = {field_id: 'action', label: 'Alteration', control: 'select',
      required: true, default: 'POSITION',
      option_values_path: ['alteration', 'allowed_actions'],
      options: ['POSITION', 'IDENTITY', 'COMPUTED'].map((value) => ({value, label: value}))};
    const target = (name, allowed) => ({resource_id: 'column:T.' + name,
      resource_kind: 'column', display_name: name,
      extensions: {firebird: {native: {alteration: {allowed_actions: allowed}}}}});
    const first = target('A', ['POSITION', 'IDENTITY']);
    const second = target('B', ['COMPUTED']);
    const view = target('C', []);
    const resources = [first, second, view];
    const post = jest.fn(({target: requested}) => Promise.resolve(requested));
    const props = {resources, post, setError: jest.fn(), initialResourceKind: 'column',
      initialOperationId: 'alter', catalog: {objects: [{resource_kind: 'column',
        title: 'Column', operations: [{operation_id: 'alter', title: 'Alter',
          target_required: true, form: {fields: [field]}}]}]}};
    // The service returns an independently inspected resource, not the stale
    // values in a previously rendered draft.
    post.mockImplementation(() => Promise.resolve(first));
    const {rerender} = render(<VisualAdministration {...props} selectedResource={first} />);
    await waitFor(() => expect(screen.getByRole('combobox', {name: /Alteration/})).toHaveTextContent('POSITION'), {timeout: 5000});
    post.mockImplementation(() => Promise.resolve(second));
    rerender(<VisualAdministration {...props} selectedResource={second} />);
    await waitFor(() => expect(screen.getByRole('combobox', {name: /Alteration/})).toHaveTextContent('COMPUTED'), {timeout: 5000});
    post.mockImplementation(() => Promise.resolve(view));
    rerender(<VisualAdministration {...props} selectedResource={view} />);
    await waitFor(() => expect(screen.getByRole('combobox', {name: /Alteration/})).toHaveAttribute('aria-disabled', 'true'), {timeout: 5000});
  });

  it('requires both alteration and type selectors before showing a dependent field', async () => {
    const target = {resource_id: 'column:T.V', resource_kind: 'column', display_name: 'V'};
    render(<VisualAdministration selectedResource={target} resources={[target]}
      post={async () => target} setError={jest.fn()} initialResourceKind="column"
      initialOperationId="alter" catalog={{objects: [{resource_kind: 'column', operations: [
        {operation_id: 'alter', title: 'Alter', target_required: true, form: {fields: [
          {field_id: 'action', label: 'Alteration', control: 'select', default: 'POSITION',
            options: [{value: 'POSITION', label: 'Position'}, {value: 'TYPE', label: 'Type'}]},
          {field_id: 'data_type', label: 'Data type', control: 'select', default: 'INTEGER',
            options: [{value: 'INTEGER', label: 'Integer'}, {value: 'VARCHAR', label: 'Varchar'},
              {value: 'BLOB', label: 'Blob', visible_when: {field_id: 'action', equals: 'TYPE'}}]},
          {field_id: 'length', label: 'Length', control: 'number', visible_when: {all: [
            {field_id: 'action', equals: 'TYPE'}, {field_id: 'data_type', in: ['VARCHAR']},
          ]}},
        ]}},
      ]}]}} />);
    await waitFor(() => expect(screen.getByRole('combobox', {name: 'Alteration'})).not.toHaveAttribute('aria-disabled', 'true'));
    expect(screen.queryByLabelText('Length')).not.toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Data type'}));
    expect(screen.queryByRole('option', {name: 'Blob'})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('option', {name: 'Integer'}));
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Alteration'}));
    fireEvent.click(screen.getByRole('option', {name: 'Type'}));
    expect(screen.queryByLabelText('Length')).not.toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Data type'}));
    expect(screen.getByRole('option', {name: 'Blob'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('option', {name: 'Varchar'}));
    expect(screen.getByLabelText('Length')).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Data type'}));
    fireEvent.click(screen.getByRole('option', {name: 'Blob'}));
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Alteration'}));
    fireEvent.click(screen.getByRole('option', {name: 'Position'}));
    expect(screen.queryByLabelText('Length')).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', {name: 'Data type'})).toHaveTextContent('Integer');
  });

  it.each(['text', 'multiline', 'code', 'json', 'number', 'password', 'boolean'])('propagates disabled state to %s controls', (control) => {
    render(<VisualAdminField disabled field={{field_id: 'test', label: 'Field', control}}
      value={control === 'boolean' ? false : ''} onChange={jest.fn()} />);
    expect(screen.getByLabelText('Field')).toBeDisabled();
    if (control === 'password') expect(screen.getByRole('button', {name: 'Show password'})).toBeDisabled();
  });

  it('propagates disabled state through structured record controls', () => {
    render(<VisualAdminField disabled field={{field_id: 'items', label: 'Items',
      control: 'json', array_editor: {item_kind: 'object', fields: [
        {field_id: 'name', label: 'Name', control: 'text'},
        {field_id: 'choice', label: 'Choice', control: 'select', options: [{value: 'A', label: 'A'}]},
      ]}}} value={[{name: 'first', choice: 'A'}, {name: 'second', choice: 'A'}]} onChange={jest.fn()} />);
    for (const input of screen.getAllByRole('textbox')) expect(input).toBeDisabled();
    for (const button of screen.getAllByRole('button')) expect(button).toBeDisabled();
    for (const choice of screen.getAllByRole('combobox')) expect(choice).toHaveAttribute('aria-disabled', 'true');
  });

  it.each(['select', 'multiselect'])('disables %s during metadata loading and renders provider guidance', async (control) => {
    const target = {resource_id: 'role:RDB$ADMIN', resource_kind: 'role', display_name: 'RDB$ADMIN'};
    let finish;
    const pending = new Promise((resolve) => { finish = resolve; });
    render(<VisualAdministration selectedResource={target} resources={[target]}
      post={() => pending} setError={jest.fn()} initialResourceKind="role"
      initialOperationId="alter" catalog={{objects: [{resource_kind: 'role', operations: [
        {operation_id: 'alter', title: 'Alter', target_required: true, form: {fields: [
          {field_id: 'choice', label: 'Mapping choice', control, help: 'Replaces the reserved mapping.',
            default: control === 'select' ? 'SET' : [], options: [{value: 'SET', label: 'SET'}, {value: 'DROP', label: 'DROP'}]},
        ]}},
      ]}]}} />);
    const choice = screen.getByRole('combobox', {name: 'Mapping choice'});
    expect(choice).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText('Replaces the reserved mapping.')).toBeInTheDocument();
    fireEvent.mouseDown(choice);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    await act(async () => { finish(target); });
    await waitFor(() => expect(choice).not.toHaveAttribute('aria-disabled', 'true'));
    fireEvent.mouseDown(choice);
    expect(screen.getByRole('option', {name: /DROP/})).toBeInTheDocument();
  });

  it.each(['RDB$ADMIN', 'OTHER_SYSTEM', 'READER'])('limits named system-role operations for %s', async (name) => {
    const target = {resource_id: 'role:' + name, resource_kind: 'role', display_name: name,
      extensions: {firebird: {native: {system_object: name !== 'READER'}}}};
    const post = jest.fn(async () => target);
    render(<VisualAdministration selectedResource={target} resources={[target]}
      post={post} setError={jest.fn()} initialResourceKind="role"
      initialOperationId="configure_admin_mapping" catalog={{objects: [{resource_kind: 'role',
        operations: [
          {operation_id: 'inspect', title: 'Inspect', form: {fields: []}},
          {operation_id: 'configure_admin_mapping', title: 'Configure Windows administrator mapping',
            target_required: true, allow_system_target: true, target_resource_names: ['RDB$ADMIN'],
            form: {fields: [{field_id: 'mapping_action', label: 'Windows administrator mapping',
              control: 'select', default: 'SET', options: [{value: 'SET', label: 'SET'}, {value: 'DROP', label: 'DROP'}]}]}},
        ]}]}} />);
    await waitFor(() => expect(post).toHaveBeenCalled());
    if (name === 'RDB$ADMIN') {
      await waitFor(() => expect(screen.getByRole('combobox', {name: 'Windows administrator mapping'})).toBeInTheDocument());
    } else {
      expect(screen.queryByRole('combobox', {name: 'Windows administrator mapping'})).not.toBeInTheDocument();
      expect(screen.queryByRole('option', {name: 'Configure Windows administrator mapping'})).not.toBeInTheDocument();
    }
  });

  it('blocks role confirmation until asynchronous inspection is complete', async () => {
    const target = {resource_id: 'role:reader', resource_kind: 'role', display_name: 'reader'};
    let finishInspection;
    const inspection = new Promise((resolve) => { finishInspection = resolve; });
    const post = jest.fn(({action}) => {
      if (action === 'resource_inspect') return inspection;
      if (action === 'visual_admin_validate') return Promise.resolve({valid: true});
      return Promise.resolve({state: 'ready', plan_id: 'drop-role', execution_available: true});
    });
    render(<VisualAdministration resources={[target]} selectedResource={target}
      initialResourceKind="role" initialOperationId="drop" post={post}
      setError={jest.fn()} catalog={{objects: [{resource_kind: 'role', title: 'Role',
        operations: [{operation_id: 'drop', title: 'Drop', target_required: true,
          form: {fields: [{field_id: 'confirmation', label: 'Confirmation',
            control: 'text', required: true}]}}]}]}} />);
    const confirmation = screen.getByRole('textbox', {name: /Confirmation/});
    expect(confirmation).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeDisabled();
    await act(async () => { finishInspection(target); });
    await waitFor(() => expect(confirmation).toBeEnabled());
    fireEvent.change(confirmation, {target: {value: 'reader'}});
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'role', operation_id: 'drop', target_resource: target,
      draft: {confirmation: 'reader'},
    }}));
    expect(confirmation).toHaveValue('reader');
  });

  it('prefills Firebird system privileges as a typed selection, not JSON text', () => {
    const privileges = ['USER_MANAGEMENT', 'PROFILE_ANY_ATTACHMENT'];
    const fields = [{field_id: 'system_privileges', control: 'multiselect',
      initial_value_path: ['system_privileges']}];
    const result = initialObjectDraft(fields, {
      extensions: {firebird: {native: {system_privileges: privileges}}},
    });
    expect(result.system_privileges).toEqual(privileges);
    expect(Array.isArray(result.system_privileges)).toBe(true);
    expect(initialObjectDraft(fields, {extensions: {firebird: {native: {
      system_privileges: [],
    }}}}).system_privileges).toEqual([]);
  });
  it('keeps decimal-text integer fields exact across input and JSON transport', () => {
    const changed = jest.fn();
    render(<VisualAdminField field={{field_id: 'topology_version',
      label: 'Topology version', control: 'text', required: true}}
    value="" onChange={changed} />);
    const input = screen.getByLabelText(/Topology version/);
    expect(input.type).toBe('text');
    for (const value of ['9007199254740993', '9223372036854775807']) {
      fireEvent.change(input, {target: {value}});
      const result = changed.mock.calls.at(-1)[0];
      expect(result).toBe(value);
      expect(JSON.parse(JSON.stringify({value: result})).value).toBe(value);
    }
  });
  it('serializes native JSON text and clones native structured records', () => {
    const rule = {score: {$gte: 0}};
    const records = [{name: 'a', type: 'INTEGER'}];
    const source = {extensions: {mongodb: {native: {rule, records}}}};
    const result = initialObjectDraft([
      {field_id: 'rule', control: 'json', initial_value_path: ['rule']},
      {field_id: 'records', control: 'json', array_editor: {item_kind: 'object'},
        initial_value_path: ['records']},
      {field_id: 'object', control: 'json', object_editor: {fields: []},
        initial_value_path: ['rule']},
    ], source);
    expect(result.rule).toBe(JSON.stringify(rule, null, 2));
    expect(result.records).toEqual(records);
    expect(result.records).not.toBe(records);
    expect(result.records[0]).not.toBe(records[0]);
    expect(result.object).toEqual(rule);
    expect(result.object).not.toBe(rule);
  });
  it('submits a prefilled rule only when explicit replacement is selected', async () => {
    const rule = {score: {$gte: 0}};
    const target = {resource_id: 'validator:items', resource_kind: 'validator',
      display_name: 'Rule', extensions: {mongodb: {native: {options: {
        validator: rule, validationAction: 'error',
      }}}}};
    const post = jest.fn(async ({action}) => {
      if (action === 'resource_inspect') return target;
      if (action === 'visual_admin_validate') return {valid: true};
      return {state: 'ready', plan_id: 'replace-rule', plan_digest: 'digest',
        execution_available: true};
    });
    render(<VisualAdministration resources={[target]} selectedResource={target}
      initialResourceKind="validator" initialOperationId="alter" post={post}
      setError={jest.fn()} catalog={{objects: [{resource_kind: 'validator',
        title: 'Validator', operations: [{operation_id: 'alter', title: 'Alter',
          target_required: true, form: {fields: [
            {field_id: 'replace_rule', label: 'Replace rule', control: 'boolean', default: false},
            {field_id: 'validator', label: 'Rule', control: 'json', default: {},
              initial_value_path: ['options', 'validator'], submit_unchanged: true,
              visible_when: {field_id: 'replace_rule', equals: true}},
            {field_id: 'validation_action', label: 'Action', control: 'text',
              initial_value_path: ['options', 'validationAction']},
          ]}}]}]}} />);
    await waitFor(() => expect(screen.getByRole('textbox', {name: 'Action'})).toHaveValue('error'));
    expect(screen.queryByRole('textbox', {name: 'Rule'})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', {name: 'Replace rule'}));
    expect(screen.getByRole('textbox', {name: 'Rule'})).toHaveValue(JSON.stringify(rule, null, 2));
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'validator', operation_id: 'alter', target_resource: target,
      draft: {replace_rule: true, validator: JSON.stringify(rule, null, 2)},
    }}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Replace rule'}));
    fireEvent.change(screen.getByRole('textbox', {name: 'Action'}), {target: {value: 'warn'}});
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'validator', operation_id: 'alter', target_resource: target,
      draft: {replace_rule: false, validation_action: 'warn'},
    }}));
  });
  it('submits both Firebird role option removals without conflating them with membership removal', async () => {
    const target = {resource_id: 'role:readers', resource_kind: 'role', display_name: 'readers'};
    const post = jest.fn(async ({action}) => {
      if (action === 'resource_inspect') return target;
      if (action === 'visual_admin_validate') return {valid: true};
      return {state: 'ready', plan_id: 'role-options', plan_digest: 'digest', execution_available: true};
    });
    render(<VisualAdministration resources={[target]} selectedResource={target}
      initialResourceKind="role" initialOperationId="revoke" post={post}
      setError={jest.fn()} catalog={{objects: [{resource_kind: 'role', title: 'Role',
        operations: [{operation_id: 'revoke', title: 'Revoke', target_required: true,
          form: {fields: [
            {field_id: 'member', label: 'Member name', control: 'text', required: true},
            {field_id: 'default_role', label: 'Remove default status only', control: 'boolean', default: false},
            {field_id: 'admin_option_only', label: 'Revoke admin option only', control: 'boolean', default: false},
            {field_id: 'confirmation', label: 'Confirmation', control: 'text', required: true},
          ]}}]}]}} />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeEnabled());
    fireEvent.change(screen.getByRole('textbox', {name: /Member name/}), {target: {value: 'operator'}});
    fireEvent.change(screen.getByRole('textbox', {name: /Confirmation/}), {target: {value: 'readers'}});
    fireEvent.click(screen.getByRole('checkbox', {name: 'Remove default status only'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Revoke admin option only'}));
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'role', operation_id: 'revoke', target_resource: target,
      draft: {member: 'operator', confirmation: 'readers', default_role: true, admin_option_only: true},
    }}));
  });
  it('hides Firebird replacement privileges when clearing the complete set', async () => {
    const target = {resource_id: 'role:reader', resource_kind: 'role', display_name: 'reader'};
    const post = jest.fn(async ({action}) => {
      if (action === 'resource_inspect') return target;
      if (action === 'visual_admin_validate') return {valid: true};
      return {state: 'ready', plan_id: 'role-privileges', plan_digest: 'digest', execution_available: true};
    });
    render(<VisualAdministration resources={[target]} selectedResource={target}
      initialResourceKind="role" initialOperationId="alter" post={post}
      setError={jest.fn()} catalog={{objects: [{resource_kind: 'role', title: 'Role',
        operations: [{operation_id: 'alter', title: 'Alter', target_required: true,
          form: {fields: [
            {field_id: 'system_privileges', label: 'Replacement system privileges', control: 'multiselect', default: [],
              help_text: 'Replaces the entire privilege set.',
              options: [{value: 'USER_MANAGEMENT', label: 'USER_MANAGEMENT'}],
              visible_when: {field_id: 'drop_system_privileges', equals: false}},
            {field_id: 'drop_system_privileges', label: 'Drop all system privileges', control: 'boolean', default: false},
          ]}}]}]}} />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeEnabled());
    expect(screen.getByText('Replaces the entire privilege set.')).toBeInTheDocument();
    const selector = screen.getByRole('combobox', {name: 'Replacement system privileges'});
    fireEvent.change(selector.parentElement.querySelector('input'), {target: {value: 'USER_MANAGEMENT'}});
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'role', operation_id: 'alter', target_resource: target,
      draft: {system_privileges: ['USER_MANAGEMENT'], drop_system_privileges: false},
    }}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Drop all system privileges'}));
    expect(screen.queryByRole('combobox', {name: 'Replacement system privileges'})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'role', operation_id: 'alter', target_resource: target,
      draft: {drop_system_privileges: true},
    }}));
  });
  it('refreshes Firebird index statistics without replaying the catalog state', async () => {
    const target = {resource_id: 'index:items:ix', resource_kind: 'index',
      display_name: 'ix', extensions: {firebird: {native: {state: {active: true}}}}};
    const post = jest.fn(async ({action}) => {
      if (action === 'resource_inspect') return target;
      if (action === 'visual_admin_validate') return {valid: true};
      return {state: 'ready', plan_id: 'index-statistics', plan_digest: 'digest',
        execution_available: true};
    });
    render(<VisualAdministration resources={[target]} selectedResource={target}
      initialResourceKind="index" initialOperationId="alter" post={post}
      setError={jest.fn()} catalog={{objects: [{resource_kind: 'index',
        title: 'Index', operations: [{operation_id: 'alter', title: 'Alter',
          target_required: true, form: {fields: [
            {field_id: 'active', label: 'Active', control: 'boolean',
              initial_value_path: ['state', 'active']},
            {field_id: 'refresh_statistics', label: 'Recalculate index statistics',
              control: 'boolean', default: false},
          ]}}]}]}} />);
    await waitFor(() => expect(screen.getByRole('checkbox', {name: 'Active'})).toBeChecked());
    fireEvent.click(screen.getByRole('checkbox', {name: 'Recalculate index statistics'}));
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'index', operation_id: 'alter', target_resource: target,
      draft: {refresh_statistics: true},
    }}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Active'}));
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'index', operation_id: 'alter', target_resource: target,
      draft: {active: false, refresh_statistics: true},
    }}));
  });
  it('shows TTL input only when requested and preserves zero seconds in the draft', async () => {
    const target = {resource_id: 'index:ttl', resource_kind: 'index',
      display_name: 'ttl'};
    const post = jest.fn(async ({action}) => {
      if (action === 'resource_inspect') return target;
      if (action === 'visual_admin_validate') return {valid: true};
      return {state: 'ready', plan_id: 'ttl-plan', plan_digest: 'digest',
        execution_available: true};
    });
    render(<VisualAdministration resources={[target]} selectedResource={target}
      initialResourceKind="index" initialOperationId="alter" post={post}
      setError={jest.fn()} catalog={{objects: [{resource_kind: 'index',
        title: 'Index', operations: [{operation_id: 'alter', title: 'Alter',
          target_required: true, form: {fields: [
            {field_id: 'change_ttl', label: 'Change TTL', control: 'boolean', default: false},
            {field_id: 'ttl_seconds', label: 'Expire after seconds', control: 'number',
              required: true, visible_when: {field_id: 'change_ttl', equals: true}},
          ]}}]}]}} />);
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeEnabled());
    fireEvent.click(screen.getByRole('checkbox', {name: 'Change TTL'}));
    fireEvent.change(screen.getByRole('spinbutton', {name: /Expire after seconds/}),
      {target: {value: '0'}});
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'visual_admin_plan', request: {
      resource_kind: 'index', operation_id: 'alter', target_resource: target,
      draft: {change_ttl: true, ttl_seconds: 0},
    }}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Change TTL'}));
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
  });
  let originalHeight;
  beforeEach(() => {
    originalHeight = window.innerHeight;
    // The shared virtual-grid test setup assigns every element height 800.
    // Give select popovers a viewport that accommodates that mocked geometry.
    window.innerHeight = 1200;
  });
  afterEach(() => { window.innerHeight = originalHeight; });
  it('preserves MongoDB key order and selected native key types', () => {
    const field = {label: 'Ordered index keys', array_editor: {
      item_kind: 'object', fields: [
        {field_id: 'field', label: 'Document field path', control: 'text'},
        {field_id: 'kind', label: 'Key type', control: 'select',
          default: 'ascending', options: [
            {value: 'ascending', label: 'Ascending'},
            {value: 'descending', label: 'Descending'},
          ]},
      ],
    }};
    const onChange = jest.fn();
    render(<RecordListAdminField field={field} value={[
      {field: 'a', kind: 'ascending'}, {field: 'b', kind: 'descending'},
    ]} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', {name: 'Ordered index keys 2: Move up'}));
    expect(onChange).toHaveBeenLastCalledWith([
      {field: 'b', kind: 'descending'}, {field: 'a', kind: 'ascending'},
    ]);
    fireEvent.mouseDown(screen.getAllByRole('combobox', {name: 'Key type'})[0]);
    fireEvent.click(screen.getByRole('option', {name: 'Descending'}));
    expect(onChange).toHaveBeenLastCalledWith([
      {field: 'a', kind: 'descending'}, {field: 'b', kind: 'descending'},
    ]);
  });
  const properties = {field_id: 'properties', label: 'Constraint properties',
    control: 'json', default: {kind: 'CHECK', expression: ''},
    object_editor: {fields: [
      {field_id: 'kind', label: 'Constraint type', control: 'text'},
      {field_id: 'expression', label: 'Expression', control: 'text',
        visible_when: {field_id: 'kind', equals: 'CHECK'}},
    ]}};
  it('edits a single structured object without record-list actions', () => {
    const onChange = jest.fn();
    render(<VisualAdminField field={properties} value={undefined} onChange={onChange} />);
    expect(screen.getByLabelText('Constraint type')).toHaveValue('CHECK');
    fireEvent.change(screen.getByLabelText('Expression'), {target: {value: 'ID > 0'}});
    expect(onChange).toHaveBeenCalledWith({kind: 'CHECK', expression: 'ID > 0'});
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
  it('loads serialized objects and preserves invalid or unknown fields', () => {
    const onChange = jest.fn();
    const {rerender} = render(<VisualAdminField field={properties}
      value={'{"kind":"CHECK","expression":"ID > 0"}'} onChange={onChange} />);
    expect(screen.getByLabelText('Expression')).toHaveValue('ID > 0');
    for (const invalid of ['bad json', '[]', '{"unknown":true}', 'null']) {
      rerender(<VisualAdminField field={properties} value={invalid} onChange={onChange} />);
      expect(screen.getByRole('alert')).toHaveTextContent('original value has not been changed');
    }
    expect(onChange).not.toHaveBeenCalled();
  });
  it('submits an object draft to validation and planning and invalidates edited plans', async () => {
    const post = jest.fn(async ({action}) => action === 'visual_admin_validate' ?
      {valid: true} : {plan_id: 'constraint-plan', plan_digest: 'digest',
        state: 'ready', execution_available: true});
    render(<VisualAdministration resources={[]} post={post} setError={jest.fn()}
      initialResourceKind="constraint" initialOperationId="create"
      catalog={{objects: [{resource_kind: 'constraint', title: 'Constraint',
        operations: [{operation_id: 'create', title: 'Create', target_required: false,
          form: {fields: [properties]}}]}]}} />);
    fireEvent.change(screen.getByLabelText('Expression'), {target: {value: 'ID > 0'}});
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeEnabled());
    for (const action of ['visual_admin_validate', 'visual_admin_plan']) {
      expect(post).toHaveBeenCalledWith({action, request: {
        resource_kind: 'constraint', operation_id: 'create', target_resource: null,
        draft: {properties: {kind: 'CHECK', expression: 'ID > 0'}},
      }});
    }
    fireEvent.change(screen.getByLabelText('Expression'), {target: {value: 'ID > 10'}});
    expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
  });
  const field = {field_id: 'columns', label: 'Columns', array_editor: {
    item_kind: 'object', fields: [
      {field_id: 'name', label: 'Column name', control: 'text', required: true},
      {field_id: 'nullable', label: 'Nullable', control: 'boolean', default: true},
    ],
  }};
  function Harness() {
    const [value, setValue] = useState([]);
    return <><RecordListAdminField field={field} value={value} onChange={setValue} />
      <output data-testid="record-value">{JSON.stringify(value)}</output></>;
  }
  it('adds, edits, reorders and removes draft records with defaults', () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', {name: 'Add Columns item'}));
    fireEvent.change(screen.getByLabelText(/Column name/), {target: {value: 'A'}});
    expect(screen.getByTestId('record-value')).toHaveTextContent('"nullable":true');
    fireEvent.click(screen.getByRole('button', {name: 'Add Columns item'}));
    fireEvent.change(screen.getAllByLabelText(/Column name/)[1], {target: {value: 'B'}});
    fireEvent.click(screen.getByRole('button', {name: 'Columns 2: Move up'}));
    expect(screen.getAllByLabelText(/Column name/)[0]).toHaveValue('B');
    fireEvent.click(screen.getByRole('button', {name: 'Columns 1: Move down'}));
    expect(screen.getAllByLabelText(/Column name/)[0]).toHaveValue('A');
    fireEvent.click(screen.getByRole('button', {name: 'Columns 1: Remove'}));
    expect(screen.getByLabelText(/Column name/)).toHaveValue('B');
  });
  it('filters per-record type choices and resets them without changing other records', () => {
    const schema = {label: 'Columns', array_editor: {item_kind: 'object', fields: [
      {field_id: 'mode', label: 'Mode', control: 'text', default: 'stored'},
      {field_id: 'type', label: 'Type', control: 'select', default: 'INTEGER', options: [
        {value: 'INTEGER', label: 'Integer'},
        {value: 'DOMAIN', label: 'Domain', visible_when: {field_id: 'mode', equals: 'stored'}},
      ]},
    ]}};
    function Records() {
      const [value, setValue] = useState([{mode: 'stored', type: 'DOMAIN'},
        {mode: 'stored', type: 'DOMAIN'}]);
      return <><RecordListAdminField field={schema} value={value} onChange={setValue} />
        <output data-testid="record-types">{JSON.stringify(value)}</output></>;
    }
    render(<Records />);
    fireEvent.change(screen.getAllByLabelText('Mode')[0], {target: {value: 'computed'}});
    expect(JSON.parse(screen.getByTestId('record-types').textContent)).toEqual([
      {mode: 'computed', type: 'INTEGER'}, {mode: 'stored', type: 'DOMAIN'},
    ]);
    fireEvent.mouseDown(screen.getAllByLabelText('Type')[0]);
    expect(screen.queryByRole('option', {name: 'Domain'})).not.toBeInTheDocument();
    expect(screen.getByRole('option', {name: 'Integer'})).toBeInTheDocument();
  });
  it.each(['invalid JSON', '[42]', '[{"name":"A","unsupported":true}]']) (
    'preserves unsupported input %s without silently discarding it', (value) => {
      const onChange = jest.fn();
      render(<RecordListAdminField field={field} value={value} onChange={onChange} />);
      expect(screen.getByRole('alert')).toHaveTextContent('original value has not been changed');
      expect(onChange).not.toHaveBeenCalled();
      expect(screen.queryByRole('button')).not.toBeInTheDocument();
    });
  it('permits only reordering of fixed native column lists', () => {
    const onChange = jest.fn();
    render(<RecordListAdminField field={{label: 'Column order',
      array_editor: {item_kind: 'string', fixed_items: true}}}
    value={['A', 'B']} onChange={onChange} />);
    expect(screen.getByLabelText('Column order 1')).toBeDisabled();
    expect(screen.queryByRole('button', {name: 'Add Column order item'})).toBeNull();
    expect(screen.queryByRole('button', {name: /Remove/})).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Column order 2: Move up'}));
    expect(onChange).toHaveBeenCalledWith(['B', 'A']);
  });
  it('edits primitive lists and accepts serialized existing lists', () => {
    const onChange = jest.fn();
    render(<RecordListAdminField field={{label: 'Index columns',
      array_editor: {item_kind: 'string'}}} value={'["A"]'} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Index columns 1'), {target: {value: 'B'}});
    expect(onChange).toHaveBeenCalledWith(['B']);
  });
  it('renders only fields applicable to the selected constraint type', () => {
    const constraint = {label: 'Constraints', array_editor: {
      item_kind: 'object', fields: [
        {field_id: 'kind', label: 'Type', control: 'text'},
        {field_id: 'expression', label: 'Check expression', control: 'text',
          visible_when: {field_id: 'kind', equals: 'CHECK'}},
        {field_id: 'columns', label: 'Columns', control: 'json', default: [],
          array_editor: {item_kind: 'string'},
          visible_when: {field_id: 'kind', in: ['UNIQUE', 'FOREIGN KEY']}},
      ],
    }};
    const onChange = jest.fn();
    const {rerender} = render(<RecordListAdminField field={constraint}
      value={[{kind: 'CHECK', expression: 'A > 0'}]} onChange={onChange} />);
    expect(screen.getByLabelText('Check expression')).toHaveValue('A > 0');
    expect(screen.queryByRole('group', {name: 'Columns'})).not.toBeInTheDocument();
    rerender(<RecordListAdminField field={constraint}
      value={[{kind: 'UNIQUE', columns: ['A']}]} onChange={onChange} />);
    expect(screen.queryByLabelText('Check expression')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Columns 1'), {target: {value: 'B'}});
    expect(onChange).toHaveBeenCalledWith([{kind: 'UNIQUE', columns: ['B']}]);
  });
});


describe('administration refresh selection stability', () => {
  it('keeps user-selected kind and operation when catalog and inspected target refresh', async () => {
    const catalog = {objects: ['access-method', 'transform'].map(kind => ({
      resource_kind: kind, title: kind, operations: ['create', 'inspect', 'drop'].map(operation => ({
        operation_id: operation, title: operation, target_required: false, form: {fields: []},
      })),
    }))};
    const target = {resource_id: 'transform:42', resource_kind: 'transform', display_name: 'jsonb'};
    const post = jest.fn(async () => target);
    const props = {catalog, resources: [target], post, setError: jest.fn(),
      initialResourceKind: 'access-method', initialOperationId: 'create'};
    const view = render(<VisualAdministration {...props} />);
    fireEvent.change(screen.getByRole('combobox', {name: 'Object type'}).parentElement.querySelector('input'), {target: {value: 'transform'}});
    fireEvent.change(screen.getByRole('combobox', {name: 'Operation'}).parentElement.querySelector('input'), {target: {value: 'inspect'}});
    view.rerender(<VisualAdministration {...props} catalog={JSON.parse(JSON.stringify(catalog))}
      selectedResource={target} resourceGeneration="refreshed" />);
    await waitFor(() => expect(post).toHaveBeenCalledWith(expect.objectContaining({action: 'resource_inspect'})));
    expect(screen.getByRole('combobox', {name: 'Object type'})).toHaveTextContent('transform');
    expect(screen.getByRole('combobox', {name: 'Operation'})).toHaveTextContent('inspect');
    view.rerender(<VisualAdministration {...props} initialResourceKind="transform" initialOperationId="drop"
      selectedResource={target} resourceGeneration="refreshed" />);
    await waitFor(() => expect(screen.getByRole('combobox', {name: 'Operation'})).toHaveTextContent('drop'));
  });
});
