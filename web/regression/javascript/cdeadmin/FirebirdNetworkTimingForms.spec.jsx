// ScratchRobin CDE Admin. PostgreSQL Licence; pgAdmin attribution retained.
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {ServerProfileWorkspace}
  from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';
import manifest from '../../../pgadmin/cdeadmin/providers/firebird/provider_manifest.json';

const fields = manifest.registration.connection_fields.filter(
  field => ['timeout', 'dummy_packet_interval'].includes(field.field_id));

describe('Firebird native network timing', () => {
  it.each([0, 1, 2147483647])('saves integer %s and clears to native defaults', async value => {
    const post = jest.fn().mockResolvedValue({});
    render(<ServerProfileWorkspace registration={{
      primary_route: {route_id: 'owned', configuration: {
        timeout: value, dummy_packet_interval: value}},
      forms: {forms: {edit: {form_id: 'owned-timing', fields}}},
    }} post={post} setError={jest.fn()} />);
    const save = screen.getByRole('button', {name: 'Save endpoint profile'});
    fireEvent.click(save);
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({
      action: 'endpoint_profile_update', request: {
        timeout: value, dummy_packet_interval: value},
    }));
    await waitFor(() => expect(save).not.toBeDisabled());
    fields.forEach(field => {
      const control = screen.getByRole('spinbutton', {name: field.label});
      expect(control).toHaveAccessibleDescription(field.help);
      fireEvent.change(control, {target: {value: ''}});
    });
    fireEvent.click(save);
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({
      action: 'endpoint_profile_update', request: {
        timeout: '', dummy_packet_interval: ''},
    }));
    expect(post).toHaveBeenCalledTimes(2);
  });
});
