// ScratchRobin CDE Admin. PostgreSQL Licence; pgAdmin attribution retained.
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {ServerProfileWorkspace, VisualAdminField}
  from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';
import manifest from '../../../pgadmin/cdeadmin/providers/firebird/provider_manifest.json';

const fields = manifest.registration.connection_fields.filter(
  field => ['wire_crypt', 'wire_compression'].includes(field.field_id));

describe('Firebird native compression preference', () => {
  it.each([true, false])('persists and reverses boolean %s', async initial => {
    const post = jest.fn().mockResolvedValue({});
    render(<ServerProfileWorkspace registration={{
      primary_route: {route_id: 'owned', configuration: {
        wire_crypt: 'Required', wire_compression: initial}},
      forms: {forms: {edit: {form_id: 'owned-compression', fields}}},
    }} post={post} setError={jest.fn()} />);
    const save = screen.getByRole('button', {name: 'Save endpoint profile'});
    const toggle = screen.getByRole('checkbox', {name: 'Enable wire compression'});
    expect(toggle).toHaveAccessibleDescription(fields.find(
      field => field.field_id === 'wire_compression').help);
    expect(toggle.checked).toBe(initial);
    for(const value of [initial, !initial, initial]) {
      if(toggle.checked !== value) fireEvent.click(toggle);
      fireEvent.click(save);
      await waitFor(() => expect(post).toHaveBeenLastCalledWith({
        action: 'endpoint_profile_update', request: {
          wire_crypt: 'Required', wire_compression: value},
      }));
      await waitFor(() => expect(save).not.toBeDisabled());
    }
    expect(post).toHaveBeenCalledTimes(3);
  });
  it('keeps checkbox help unique and supports legacy help_text', () => {
    const field = {control: 'boolean', label: 'Compression', help_text: 'Native help'};
    render(<><VisualAdminField field={field} value={false} onChange={jest.fn()} />
      <VisualAdminField field={field} value={true} disabled onChange={jest.fn()} /></>);
    const controls = screen.getAllByRole('checkbox');
    controls.forEach(control => expect(control).toHaveAccessibleDescription('Native help'));
    expect(controls[0].getAttribute('aria-describedby')).not.toBe(
      controls[1].getAttribute('aria-describedby'));
    expect(controls[1]).toBeDisabled();
  });
});
