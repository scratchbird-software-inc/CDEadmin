import {StrictMode} from 'react';
import {render, renderHook, fireEvent, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {useIsMounted} from 'sources/custom_hooks';
import BaseUISchema from 'sources/SchemaView/base_schema.ui';
import SchemaView from 'sources/SchemaView';
import {withBrowser} from '../genericFunctions';

class LifecycleSchema extends BaseUISchema {
  constructor() {super({gid: null, save_password: false});}
  get baseFields() {return [
    {id: 'gid', label: 'Server group', type: 'select',
      options: [{label: 'Connectors', value: '1'}]},
    {id: 'save_password', label: 'Save password', type: 'switch'},
  ];}
}

it('restores mounted state after effect replay and clears it on unmount', () => {
  const {result, unmount} = renderHook(() => useIsMounted(),
    {wrapper: StrictMode});
  expect(result.current()).toBe(true);
  unmount();
  expect(result.current()).toBe(false);
});

it.each([false, true])('retains select and switch changes (strict=%s)', async (strict) => {
  const schema = new LifecycleSchema();
  const Form = withBrowser(SchemaView);
  const form = <Form schema={schema} formType="dialog"
    viewHelperProps={{mode: 'create'}} onSave={jest.fn(async () => {})}
    onClose={jest.fn()} onHelp={jest.fn()}/>;
  const ui = render(strict ? <StrictMode>{form}</StrictMode> : form);
  await waitFor(() => expect(schema.state.isReady).toBe(true));
  await userEvent.click(ui.getByRole('combobox'));
  await userEvent.click(ui.getByText('Connectors'));
  await waitFor(() => expect(schema.state.data.gid).toBe('1'));
  fireEvent.click(ui.container.querySelector('input[name="save_password"]'));
  await waitFor(() => expect(schema.state.data.save_password).toBe(true));
  expect(schema.state.isDirty).toBe(true);
});
