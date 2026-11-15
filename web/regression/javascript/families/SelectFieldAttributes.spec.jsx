import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import Theme from 'sources/Theme';
import {Select} from '../../../pgadmin/static/js/cdeadmin_ui/primitives/Choice';
import FieldControl from '../../../pgadmin/static/js/cdeadmin_ui/objects/FieldControl';

it('preserves descriptor field identity and still dispatches the selected native value', async () => {
  const change = jest.fn();
  render(<Theme><FieldControl field={{field_id: 'method', label: 'Method', control: 'select',
    options: [{value: 'a', label: 'First'}, {value: 'b', label: 'Second'}]}}
  value="a" onChange={change} /></Theme>);
  const control = screen.getByRole('combobox', {name: 'Method'});
  expect(control).toHaveAttribute('data-cdeadmin-qa-key', 'object-editor.field.method');
  fireEvent.mouseDown(control, {button: 0});
  fireEvent.click(await screen.findByRole('option', {name: 'Second'}));
  await waitFor(() => expect(change).toHaveBeenCalledWith('b'));
});

it('preserves external descriptions and links the select helper text to its control', () => {
  render(<Theme><span id="external-help">External context</span><Select label="Mode" value="a"
    options={[{value: 'a', label: 'First'}]} helperText="Native mode"
    inputProps={{'data-cdeadmin-qa-key': 'select.probe', 'aria-describedby': 'external-help'}} /></Theme>);
  const control = screen.getByRole('combobox', {name: 'Mode'});
  expect(control).toHaveAttribute('data-cdeadmin-qa-key', 'select.probe');
  expect(control).toHaveAccessibleDescription('External context Native mode');
});

it('keeps unavailable descriptor choices disabled while preserving their identity', () => {
  render(<Theme><FieldControl field={{field_id: 'method', label: 'Method', control: 'select',
    available: false, unavailable_reason: 'Not installed', options: [{value: 'a', label: 'First'}]}}
  value="a" onChange={jest.fn()} /></Theme>);
  const control = screen.getByRole('combobox', {name: 'Method'});
  expect(control).toHaveAttribute('data-cdeadmin-qa-key', 'object-editor.field.method');
  expect(control).toHaveAttribute('aria-disabled', 'true');
  expect(control).toHaveAccessibleDescription('Not installed');
});
