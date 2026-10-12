/////////////////////////////////////////////////////////////
// CDEadmin - Multi-engine Database Administration
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//////////////////////////////////////////////////////////////

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {VisualAdministration} from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';

jest.mock('../../../pgadmin/static/js/api_instance');

describe('provider plan-specific confirmation', () => {
  it.each([
    [true, 'reused-object'], [false, 'reused-object'],
    [true, 'new-id'], [false, 'new-id'],
    [true, 'new-digest'], [false, 'new-digest'],
  ])('requires fresh confirmation for target=%s and %s re-preview', async (targetRequired, mode) => {
    const first = {plan_id: 'first', plan_digest: 'digest-one',
      state: 'ready', execution_available: true};
    const second = mode === 'reused-object' ? first : {...first,
      plan_id: mode === 'new-id' ? 'second' : 'first', plan_digest: 'digest-two'};
    let plans = 0;
    const post = jest.fn(async ({action}) => {
      if (action === 'visual_admin_validate') return {valid: true};
      if (action === 'visual_admin_plan') return ++plans === 1 ? first : second;
      return {provider_result: {accepted: true}};
    });
    const refresh = jest.fn();
    render(<VisualAdministration post={post} setError={jest.fn()}
      onMutationApplied={refresh}
      resources={targetRequired ? [{resource_id: 'table:T', resource_kind: 'table', display_name: 'T'}] : []}
      catalog={{objects: [{resource_kind: 'table', title: 'Table', operations: [{
        operation_id: 'owned-test-operation', title: 'Owned test operation',
        target_required: targetRequired, confirmation_required: true, form: {fields: []},
      }]}]}} />);
    const preview = () => screen.getByRole('button', {name: 'Validate and preview'});
    const apply = () => screen.getByRole('button', {name: 'Apply provider plan'});
    const confirmation = () => screen.getByRole('checkbox',
      {name: 'I confirm this provider-planned operation.'});
    await act(async () => { fireEvent.click(preview()); });
    expect(apply()).toBeDisabled();
    fireEvent.click(confirmation());
    expect(apply()).toBeEnabled();
    await act(async () => { fireEvent.click(preview()); });
    await waitFor(() => expect(plans).toBe(2));
    expect(confirmation()).not.toBeChecked();
    expect(apply()).toBeDisabled();
    fireEvent.click(apply());
    expect(post.mock.calls.filter(([body]) => body.action === 'visual_admin_apply')).toHaveLength(0);
    fireEvent.click(confirmation());
    await act(async () => { fireEvent.click(apply()); });
    expect(post).toHaveBeenLastCalledWith({action: 'visual_admin_apply', request: {
      plan_id: second.plan_id, plan_digest: second.plan_digest, confirmed: true,
    }});
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(apply()).toBeDisabled();
  });

  it.each(['invalid-validation', 'validation-error', 'planning-error'])(
    'does not resurrect confirmation after %s and a fresh preview', async (failure) => {
      let validations = 0;
      let plans = 0;
      const setError = jest.fn();
      const post = jest.fn(async ({action}) => {
        if (action === 'visual_admin_validate') {
          validations++;
          if (validations === 2 && failure === 'invalid-validation') {
            return {valid: false, errors: [{message: 'Rejected draft'}]};
          }
          if (validations === 2 && failure === 'validation-error') throw new Error('Validation unavailable');
          return {valid: true};
        }
        if (action === 'visual_admin_plan') {
          plans++;
          if (plans === 2 && failure === 'planning-error') throw new Error('Planning unavailable');
          return {plan_id: 'plan-' + plans, plan_digest: 'digest-' + plans,
            state: 'ready', execution_available: true};
        }
        return {provider_result: {accepted: true}};
      });
      render(<VisualAdministration post={post} setError={setError} resources={[]}
        catalog={{objects: [{resource_kind: 'database', title: 'Database', operations: [{
          operation_id: 'owned-test-operation', title: 'Owned test operation',
          target_required: false, confirmation_required: true, form: {fields: []},
        }]}]}} />);
      const preview = () => screen.getByRole('button', {name: 'Validate and preview'});
      const apply = () => screen.getByRole('button', {name: 'Apply provider plan'});
      const confirmation = () => screen.getByRole('checkbox',
        {name: 'I confirm this provider-planned operation.'});
      await act(async () => { fireEvent.click(preview()); });
      fireEvent.click(confirmation());
      expect(apply()).toBeEnabled();
      // Explicit withdrawal also remains effective for the same preview.
      fireEvent.click(confirmation());
      expect(apply()).toBeDisabled();
      fireEvent.click(confirmation());
      await act(async () => { fireEvent.click(preview()); });
      expect(apply()).toBeDisabled();
      expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
      if (failure === 'invalid-validation') expect(screen.getByText('Rejected draft')).toBeInTheDocument();
      else expect(setError).toHaveBeenCalledWith(failure === 'validation-error' ?
        'Validation unavailable' : 'Planning unavailable');
      await act(async () => { fireEvent.click(preview()); });
      expect(confirmation()).not.toBeChecked();
      expect(apply()).toBeDisabled();
      expect(post.mock.calls.filter(([body]) => body.action === 'visual_admin_apply')).toHaveLength(0);
    });
});


describe('native Firebird privilege queue integration', () => {
  it('moves a native preview into the queue and prevents separate immediate apply', async () => {
    const target = {resource_id: 'table:T', resource_kind: 'table', display_name: 'T'};
    const post = jest.fn(async ({action}) => {
      if (action === 'visual_admin_validate') return {valid: true};
      if (action === 'visual_admin_plan') return {plan_id: 'grant', plan_digest: 'native',
        state: 'ready', execution_available: true, command_preview: {engine_id: 'firebird',
          statements: [{source: 'GRANT SELECT ON T TO U'}]}};
      return {provider_result: {accepted: true, commit_requested: true}};
    });
    render(<VisualAdministration post={post} setError={jest.fn()} resources={[target]}
      catalog={{engine_id: 'firebird', objects: [{resource_kind: 'table', title: 'Table', operations: [{
        operation_id: 'grant', title: 'Grant', target_required: true,
        confirmation_required: true, form: {fields: []},
      }]}]}} />);
    await act(async () => fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'})));
    fireEvent.click(screen.getByRole('button', {name: 'Add to statement list'}));
    expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
    expect(screen.getByText('GRANT SELECT ON T TO U')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', {name: 'I confirm execution of this ordered statement list.'}));
    await act(async () => fireEvent.click(screen.getByRole('button', {name: 'Execute all statements'})));
    expect(post.mock.calls.filter(([request]) => request.action === 'visual_admin_apply')).toHaveLength(1);
    expect(screen.getByLabelText('Privilege queue receipts')).toHaveTextContent('commit_requested');
  });
});
