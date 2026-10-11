import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdDashboardEditor from 'sources/Dialogs/FirebirdDashboardEditor';
import getApiInstance from 'sources/api_instance';
import pgAdmin from 'sources/pgadmin';
import {withTheme} from '../fake_theme';

jest.mock('sources/api_instance');
jest.mock('sources/url_for', () => () => '/definition');
let mockProps;
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNDesignerSurface: (props) => {
    mockProps = props;
    return <button onClick={() => props.saveAsset({schema: 'draft'})}>Save test draft</button>;
  },
}));

describe('separate Firebird dashboard draft editor', () => {
  const Component = withTheme(FirebirdDashboardEditor);
  let api, close, closing, remove;
  beforeEach(() => {
    close = jest.fn(); remove = jest.fn();
    pgAdmin.Browser = {docker: {default_workspace: {close,
      eventBus: {registerListener: (_event, callback) => { closing = callback; return remove; }}}},
    notifier: {confirm: jest.fn(), alert: jest.fn()}};
    api = {get: jest.fn(async () => ({data: {data: {assetRef: {assetVersion: 0}, snapshot: null}}})),
      put: jest.fn(async () => ({data: {data: {assetRef: {assetVersion: 1}, state: 'draft'}}}))};
    getApiInstance.mockReturnValue(api);
  });
  it('loads scoped definitions, seeds no live telemetry, saves only through definition route', async () => {
    const {unmount} = render(<Component serverId={7} targetId="db" panelId="editor" />);
    await screen.findByRole('button', {name: 'Save test draft'});
    expect(api.get).toHaveBeenCalledWith('/definition?sid=7&target_id=db');
    expect(mockProps.snapshot.files['dashboard.ddn']).toContain('Unavailable');
    expect(screen.getByText('SR-F-001353')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Save test draft'}));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/definition?sid=7&target_id=db', {schema: 'draft'}));
    unmount();
    expect(remove).toHaveBeenCalled();
  });
  it('guards dirty and unapplied drafts while allowing clean close', async () => {
    const {unmount} = render(<Component panelId="editor" />);
    await screen.findByRole('button', {name: 'Save test draft'});
    act(() => mockProps.onReady({isDirty: () => true}));
    closing('another');
    expect(close).not.toHaveBeenCalled();
    closing('editor');
    expect(pgAdmin.Browser.notifier.confirm).toHaveBeenCalled();
    expect(close).not.toHaveBeenCalled();
    act(() => mockProps.onReady({isDirty: () => false}));
    closing('editor');
    expect(close).toHaveBeenCalledWith('editor', true);
    unmount();
  });
  it('does not offer discard while a save is in flight', async () => {
    const {unmount} = render(<Component panelId="editor" />);
    await screen.findByRole('button', {name: 'Save test draft'});
    let complete;
    api.put.mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    const pending = mockProps.saveAsset({});
    closing('editor');
    expect(pgAdmin.Browser.notifier.alert).toHaveBeenCalled();
    expect(pgAdmin.Browser.notifier.confirm).not.toHaveBeenCalled();
    expect(close).not.toHaveBeenCalled();
    complete({data: {data: {assetRef: {assetVersion: 1}}}});
    await act(async () => { await pending; });
    unmount();
  });
  it('publishes the exact saved revision only after the draft is clean', async () => {
    const {unmount} = render(<Component panelId="editor" />);
    await screen.findByRole('button', {name: 'Save test draft'});
    act(() => mockProps.onReady({isDirty: () => true}));
    await act(async () => { await mockProps.saveAsset({}); });
    fireEvent.click(screen.getByRole('button', {name: 'Publish saved revision'}));
    await screen.findByText('Save the current draft before publishing.');
    api.post = jest.fn(async () => ({data: {data: {version: 1}}}));
    act(() => mockProps.onReady({isDirty: () => false}));
    fireEvent.click(screen.getByRole('button', {name: 'Publish saved revision'}));
    await screen.findByText('Published revision 1');
    expect(api.post).toHaveBeenCalledWith('/definition', {source_version: 1, expected_version: 0});
    unmount();
  });
  it('preserves conflict codes for DDN session conflict handling', async () => {
    const {unmount} = render(<Component panelId="editor" />);
    await screen.findByRole('button', {name: 'Save test draft'});
    api.put.mockRejectedValue({response: {data: {code: 'asset_conflict', errormsg: 'Changed'}}});
    await expect(mockProps.saveAsset({})).rejects.toMatchObject({code: 'asset_conflict', message: 'Changed'});
    unmount();
  });
});
