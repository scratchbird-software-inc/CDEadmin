import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdRegistration from 'sources/Dialogs/FirebirdRegistration';
import {withTheme} from '../fake_theme';
const Component = withTheme(FirebirdRegistration);
const catalog = {source_server_id: 10, source_generation: 'source-generation', source: {display_name: 'Owned', database: '/db/owned.fdb'},
  destinations: [{server_id: 10, name: 'Source', generation: 'source-generation'}, {server_id: 11, name: 'Destination', generation: 'destination-generation'}]};
describe('Firebird registration identity transfer', () => {
  let height;
  beforeEach(() => { height = window.innerHeight; window.innerHeight = 1200; });
  afterEach(() => { window.innerHeight = height; });
  it('requires confirmation and creates an inactive alias without a native operation', async () => {
    const post = jest.fn().mockResolvedValueOnce(catalog).mockResolvedValueOnce({target: {display_name: 'Owned clone'}, native_database_changed: false});
    const changed = jest.fn();
    render(<Component post={post} targetId="exact-target" onChanged={changed} />);
    const button = await screen.findByRole('button', {name: 'Clone registration'});
    expect(button).toBeDisabled();
    expect(screen.getByLabelText('Registration display name')).toHaveValue('Owned clone');
    fireEvent.click(screen.getByLabelText('I confirm this registration change'));
    fireEvent.click(button);
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(post.mock.calls[1][0]).toEqual({action: 'database_target_transfer', request: {
      target_id: 'exact-target', destination_server_id: 10, operation: 'clone',
      display_name: 'Owned clone', credentials: 'source', confirmed: true, source_generation: 'source-generation',
      destination_generation: 'source-generation'}});
    expect(button).toBeDisabled();
  });
  it('requires a distinct destination for a move and exposes the credential choice', async () => {
    const post = jest.fn().mockResolvedValue(catalog);
    render(<Component post={post} targetId="exact-target" operation="move" />);
    await screen.findByRole('button', {name: 'Move registration'});
    fireEvent.mouseDown(screen.getByLabelText('Destination server'));
    expect(screen.queryByRole('option', {name: 'Source (registration 10)'})).toBeNull();
    fireEvent.click(screen.getByRole('option', {name: 'Destination (registration 11)'}));
    fireEvent.mouseDown(screen.getByLabelText('Credentials'));
    fireEvent.click(screen.getByRole('option', {name: 'Use destination endpoint credentials'}));
    fireEvent.click(screen.getByLabelText('I confirm this registration change'));
    expect(screen.getByRole('button', {name: 'Move registration'})).toBeEnabled();
    expect(post).toHaveBeenCalledTimes(1);
  });
  it('does not retry a lost mutation response', async () => {
    const post = jest.fn().mockResolvedValueOnce(catalog).mockRejectedValueOnce(new Error('Connection lost'));
    render(<Component post={post} targetId="exact-target" />);
    const button = await screen.findByRole('button', {name: 'Clone registration'});
    fireEvent.click(screen.getByLabelText('I confirm this registration change')); fireEvent.click(button);
    await screen.findByText(/Inspect and refresh both server registrations/);
    expect(button).toBeDisabled(); expect(post).toHaveBeenCalledTimes(2);
  });
  it('discards an old transfer response after selecting another registration', async () => {
    let complete;
    const pending = new Promise(resolve => {complete = resolve;});
    const post = jest.fn(payload => payload.action === 'database_target_transfer' ? pending : Promise.resolve(catalog));
    const changed = jest.fn();
    const {rerender} = render(<Component post={post} targetId="original" onChanged={changed} />);
    await screen.findByRole('button', {name: 'Clone registration'});
    fireEvent.click(screen.getByLabelText('I confirm this registration change'));
    fireEvent.click(screen.getByRole('button', {name: 'Clone registration'}));
    rerender(<Component post={post} targetId="replacement" onChanged={changed} />);
    await screen.findByLabelText('Registration display name');
    await act(async () => {complete({target: {display_name: 'Old completion'}});});
    expect(changed).not.toHaveBeenCalled();
    expect(screen.queryByText(/Old completion/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('I confirm this registration change')).not.toBeChecked();
    expect(post.mock.calls.filter(([value]) => value.action === 'database_target_transfer')).toHaveLength(1);
  });

});
