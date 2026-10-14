import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import PostgresqlMonitoring from 'sources/Dialogs/PostgresqlMonitoring';
import getApiInstance from 'sources/api_instance';
import {withTheme} from '../fake_theme';

jest.mock('sources/api_instance');
jest.mock('sources/url_for', () => jest.fn(() => '/monitoring/postgresql/7'));
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: (props) => <div data-testid="viewer" data-read-only={props.presentation} />,
}));
describe('PostgreSQL monitoring controls', () => {
  const Component = withTheme(PostgresqlMonitoring);
  let api, originalHeight;
  beforeEach(() => {
    originalHeight = window.innerHeight; window.innerHeight = 1200;
    api = {get: jest.fn(async () => ({data: {data: {state: 'disabled', samples: []}}})),
      post: jest.fn(async () => ({data: {data: {state: 'collecting'}}})),
      delete: jest.fn(async () => ({data: {data: {state: 'disabled'}}}))};
    getApiInstance.mockReturnValue(api);
  });
  afterEach(() => { window.innerHeight = originalHeight; });
  it('engine scope stays read-only even when policyMode is supplied', async () => {
    const {unmount} = render(<Component engineMode policyMode />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.getByTestId('viewer')).toHaveAttribute('data-read-only', 'true');
    expect(screen.queryByRole('button', {name: 'Start collection'})).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
    unmount();
  });
  it('opens retained observations without changing collector policy or editing a dashboard', async () => {
    const {unmount} = render(<Component serverId={7} targetId="postgresql-database:42" />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Display'}));
    fireEvent.click(await screen.findByRole('option', {name: 'Retained observations'}));
    expect(screen.getByText('SR-F-001382')).toBeInTheDocument();
    expect(screen.getByRole('combobox', {name: 'Observed database'})).toBeInTheDocument();
    expect(screen.getByTestId('viewer')).toHaveAttribute('data-read-only', 'true');
    expect(screen.queryByRole('button', {name: 'Start collection'})).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
    unmount();
  });
  it('keeps the viewer display-only and binds the selected database', async () => {
    const {unmount} = render(<Component serverId={7} targetId="postgresql-database:42" />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/monitoring/postgresql/7?target_id=postgresql-database%3A42'));
    expect(screen.getByTestId('viewer')).toHaveAttribute('data-read-only', 'true');
    expect(screen.queryByRole('button', {name: 'Start collection'})).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
    unmount();
  });
  it('starts with current credentials and sends native heartbeat policy without browser route data', async () => {
    const {unmount} = render(<Component serverId={7} policyMode />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Start collection'})).toBeEnabled());
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', {name: 'Start collection'}));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const body = api.post.mock.calls[0][1];
    expect(body.heartbeat_enabled).toBe(true);
    expect(body.interval_seconds).toBe(15);
    expect(body.credentials).toBeUndefined();
    expect(body.route).toBeUndefined();
    await waitFor(() => expect(screen.getByRole('button', {name: 'Stop collection'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Stop collection'}));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/monitoring/postgresql/7'));
    unmount();
  });
  it('retains an action failure when a later background read succeeds', async () => {
    let poll;
    const timer = jest.spyOn(global, 'setInterval').mockImplementation(callback => {
      poll = callback;
      return 123;
    });
    api.post.mockRejectedValue({response: {data: {errormsg: 'Credential unavailable'}}});
    const {unmount} = render(<Component serverId={7} policyMode />);
    try {
      await waitFor(() => expect(screen.getByRole('button', {name: 'Start collection'})).toBeEnabled());
      fireEvent.click(screen.getByRole('button', {name: 'Start collection'}));
      await screen.findByText('Credential unavailable');
      await act(async () => { await poll(); });
      expect(screen.getByText('Credential unavailable')).toBeInTheDocument();
    } finally { unmount(); timer.mockRestore(); }
  });
  it('clears dedicated passwords after a failed start', async () => {
    api.post.mockRejectedValue({response: {data: {errormsg: 'Refused'}}});
    const {unmount} = render(<Component serverId={7} policyMode />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Start collection'})).toBeEnabled());
    fireEvent.mouseDown(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', {name: 'Dedicated monitoring account'}));
    fireEvent.change(screen.getByLabelText('Monitoring username'), {target: {value: 'collector'}});
    fireEvent.change(screen.getByLabelText('Monitoring password'), {target: {value: 'private-test'}});
    fireEvent.click(screen.getByRole('button', {name: 'Start collection'}));
    await screen.findByText('Refused');
    expect(screen.getByLabelText('Monitoring password')).toHaveValue('');
    expect(api.post.mock.calls[0][1].credentials.username).toBe('collector');
    unmount();
  });
});
