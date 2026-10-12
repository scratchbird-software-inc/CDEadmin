import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdDesignStorage from 'sources/Dialogs/FirebirdDesignStorage';
import {withTheme} from '../fake_theme';

describe('Firebird versioned design storage', () => {
  const Component = withTheme(FirebirdDesignStorage);
  it('saves exact workspace and original baseline only after explicit version observation', async () => {
    const assetRef = {assetVersion: 4};
    const capture = jest.fn(() => ({snapshot: {files: {a: 'authored'}}, baseline: {files: {a: 'original'}}}));
    const post = jest.fn().mockResolvedValueOnce({assetRef, version: 4}).mockResolvedValueOnce({assetRef: {assetVersion: 5}, version: 5});
    render(<Component post={post} databaseTargetId="db" kind="catalog" capture={capture} onLoad={jest.fn()} />);
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByText('Save catalog design revision')).toBeDisabled();
    fireEvent.click(screen.getByText('Check saved catalog design'));
    await waitFor(() => expect(screen.getByText('Save catalog design revision')).toBeEnabled());
    fireEvent.click(screen.getByText('Save catalog design revision'));
    expect(await screen.findByText('Saved catalog design revision 5; current revision 5.')).toBeVisible();
    expect(post.mock.calls[1][0]).toEqual({action: 'firebird_design_save', request: {
      database_target_id: 'db', kind: 'catalog', assetRef, ...capture.mock.results[0].value}});
  });
  it('loads a requested immutable revision and retains the current version for future saves', async () => {
    const value = {assetRef: {assetVersion: 5}, version: 2, snapshot: {files: {}}, baseline: {files: {}}};
    const post = jest.fn().mockResolvedValue(value), onLoad = jest.fn();
    render(<Component post={post} databaseTargetId="db" kind="relations" capture={jest.fn()} onLoad={onLoad} />);
    fireEvent.change(screen.getByLabelText('Relational design revision (blank for latest)'), {target: {value: '2'}});
    fireEvent.click(screen.getByText('Load saved relational design'));
    expect(await screen.findByText('Loaded relational design revision 2; current revision 5.')).toBeVisible();
    expect(post).toHaveBeenCalledWith({action: 'firebird_design_read', request: {kind: 'relations', database_target_id: 'db', version: 2}});
    expect(onLoad).toHaveBeenCalledWith(value);
  });
  it('binds MySQL saves to their engine and clears the observed version when the engine changes', async () => {
    const assetRef = {assetVersion: 1}, post = jest.fn().mockResolvedValue({assetRef, version: 1});
    const capture = jest.fn(() => ({snapshot: {files: {}}, baseline: {files: {}}}));
    const rendered = render(<Component engine="mysql" post={post} databaseTargetId="db" kind="relations" capture={capture} onLoad={jest.fn()} />);
    fireEvent.click(screen.getByText('Check saved relational design'));
    await waitFor(() => expect(screen.getByText('Save relational design revision')).toBeEnabled());
    fireEvent.click(screen.getByText('Save relational design revision'));
    await screen.findByText('Saved relational design revision 1; current revision 1.');
    expect(post).toHaveBeenLastCalledWith({action: 'mysql_design_save', request: {
      database_target_id: 'db', kind: 'relations', assetRef, ...capture.mock.results[0].value}});
    rendered.rerender(<Component engine="firebird" post={post} databaseTargetId="db" kind="relations" capture={capture} onLoad={jest.fn()} />);
    expect(screen.getByText('Save relational design revision')).toBeDisabled();
  });

});
