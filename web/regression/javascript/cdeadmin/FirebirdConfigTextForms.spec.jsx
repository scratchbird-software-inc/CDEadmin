// ScratchRobin CDE Admin. PostgreSQL Licence; pgAdmin attribution retained.
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {ServerProfileWorkspace}
  from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';
import manifest from '../../../pgadmin/cdeadmin/providers/firebird/provider_manifest.json';

const field = manifest.registration.connection_fields.find(f => f.field_id === 'wire_config');

describe('Firebird audited native client text', () => {
  it('preserves comments/newlines and explicitly clears the override', async () => {
    const text = '# operator text\nTcpNoNagle=false\nClientBatchBuffer=128K';
    const post = jest.fn().mockResolvedValue({});
    render(<ServerProfileWorkspace registration={{
      primary_route: {route_id: 'owned', configuration: {wire_config: text}},
      forms: {forms: {edit: {form_id: 'owned-config', fields: [field]}}},
    }} post={post} setError={jest.fn()} />);
    const editor = screen.getByRole('textbox', {name: field.label});
    expect(editor).toHaveAccessibleDescription(field.help);
    expect(editor).toHaveValue(text);
    const save = screen.getByRole('button', {name: 'Save endpoint profile'});
    fireEvent.click(save);
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({
      action: 'endpoint_profile_update', request: {wire_config: text},
    }));
    await waitFor(() => expect(save).not.toBeDisabled());
    fireEvent.change(editor, {target: {value: ''}});
    fireEvent.click(save);
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({
      action: 'endpoint_profile_update', request: {wire_config: ''},
    }));
    expect(post).toHaveBeenCalledTimes(2);
  });
});
