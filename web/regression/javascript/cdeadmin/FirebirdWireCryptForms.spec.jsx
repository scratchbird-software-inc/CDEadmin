// ScratchRobin CDE Admin. PostgreSQL Licence; pgAdmin attribution retained.
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {ServerProfileWorkspace}
  from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';
import manifest from '../../../pgadmin/cdeadmin/providers/firebird/provider_manifest.json';

const fields = manifest.registration.connection_fields.filter(
  field => ['wire_crypt', 'wire_crypt_plugins'].includes(field.field_id));

describe('Firebird wire encryption preferences', () => {
  it.each(['ChaCha64', 'ChaCha', 'VendorPlugin,ChaCha64'])(
    'saves and explicitly clears %s without retaining the old override', async plugins => {
      const post = jest.fn().mockResolvedValue({});
      render(<ServerProfileWorkspace registration={{
        primary_route: {route_id: 'owned', configuration: {
          wire_crypt: 'Required', wire_crypt_plugins: plugins}},
        forms: {forms: {edit: {form_id: 'owned-wire', fields}}},
      }} post={post} setError={jest.fn()} />);
      const save = screen.getByRole('button', {name: 'Save endpoint profile'});
      fireEvent.click(save);
      await waitFor(() => expect(post).toHaveBeenLastCalledWith({
        action: 'endpoint_profile_update', request: {
          wire_crypt: 'Required', wire_crypt_plugins: plugins},
      }));
      await waitFor(() => expect(save).not.toBeDisabled());
      fireEvent.change(screen.getByRole('textbox', {
        name: 'Wire encryption plugin preference list'}), {target: {value: ''}});
      fireEvent.click(save);
      await waitFor(() => expect(post).toHaveBeenLastCalledWith({
        action: 'endpoint_profile_update', request: {
          wire_crypt: 'Required', wire_crypt_plugins: ''},
      }));
      expect(post).toHaveBeenCalledTimes(2);
    });
});
