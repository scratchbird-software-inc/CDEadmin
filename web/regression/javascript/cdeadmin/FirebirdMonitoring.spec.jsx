import runtime from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {loadDDNLibraries} from 'sources/cdeadmin_ui/integrations/ddn/library';
import {firebirdDashboardFiles} from 'sources/cdeadmin_ui/integrations/ddn/firebirdDashboard';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdMonitoring from 'sources/Dialogs/FirebirdMonitoring';
import url_for from 'sources/url_for';
import getApiInstance from 'sources/api_instance';
import {withTheme} from '../fake_theme';

jest.mock('sources/api_instance');
jest.mock('sources/url_for', () => jest.fn(() => '/monitoring/7'));
jest.mock('sources/cdeadmin_ui/integrations/ddn/library', () => ({loadDDNLibraries: jest.fn()}));
let mockViewerProps;
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: (props) => { mockViewerProps = props; return <div data-testid="read-only-ddn" />; },
}));

describe('Firebird monitoring destinations', () => {
  const Component = withTheme(FirebirdMonitoring);
  let api, originalHeight;
  beforeEach(() => {
    originalHeight = window.innerHeight; window.innerHeight = 1200;
    api = {get: jest.fn(async () => ({data: {data: {state: 'disabled', samples: []}}})),
      post: jest.fn(async () => ({data: {data: {state: 'starting'}}})),
      delete: jest.fn(async () => ({data: {data: {state: 'disabled'}}}))};
    getApiInstance.mockReturnValue(api);
  });
  afterEach(() => {window.innerHeight = originalHeight;});
  it('viewer reads only and exposes no policy or layout mutation controls', async () => {
    const {unmount} = render(<Component serverId={7} targetId="target" />);
    await screen.findAllByTestId('read-only-ddn');
    expect(api.get).toHaveBeenCalledWith('/monitoring/7?target_id=target');
    expect(screen.queryByRole('button', {name: 'Start collection'})).toBeNull();
    expect(screen.getByText('SR-F-001351')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
    unmount();
  });
  it('engine root uses a read-only fleet endpoint even if policy mode is requested', async () => {
    const {unmount} = render(<Component engineMode policyMode />);
    await screen.findAllByTestId('read-only-ddn');
    expect(url_for).toHaveBeenCalledWith('cdeadmin_monitoring.fleet');
    expect(screen.queryByRole('button')).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
    unmount();
  });
  it('loads a published revision and binds authorized live values without editor controls', async () => {
    loadDDNLibraries.mockResolvedValue({viewer: runtime});
    const published = {format: 'ddn-workspace@1', entry: 'dashboard.ddn', view: 'dashboard',
      files: firebirdDashboardFiles(null, 'Saved custom server layout', 'server')};
    api.get.mockImplementation(async (url) => ({data: {data: url.includes('published=1') ?
      {state: 'published', version: 3, snapshot: published} :
      {state: 'collecting', sample_age_seconds: 1, stale_after_seconds: 45,
        samples: [{status: 'available', groups: {version: {status: 'available', values: 'Live Firebird 5'}}}]}}}));
    const {unmount} = render(<Component serverId={7} />);
    await screen.findByText('Published layout revision 3');
    expect(mockViewerProps.presentation).toBe(true);
    expect(mockViewerProps.snapshot.files['dashboard.ddn']).toContain('Live Firebird 5');
    expect(mockViewerProps.snapshot.files['dashboard.ddn']).toContain('Saved custom server layout');
    expect(screen.getByRole('checkbox', {name: 'Recent observations'})).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    expect(published.files['dashboard.ddn']).not.toContain('Live Firebird 5');
    unmount();
  });
  it('drills down with registered target identities and never starts collection', async () => {
    const navigate = jest.fn();
    api.get.mockResolvedValue({data: {data: {state: 'disabled', servers: [{server_id: 7, name: 'Instance',
      databases: [{target_id: 'registered-id', name: 'Database alias'}]}]}}});
    const {unmount} = render(<Component engineMode onNavigate={navigate} />);
    fireEvent.mouseDown(await screen.findByRole('combobox', {name: 'Open dashboard'}));
    fireEvent.click(screen.getByRole('option', {name: /Database alias/}));
    expect(navigate).toHaveBeenCalledWith(7, 'registered-id', 'Database alias');
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Open dashboard'}));
    fireEvent.click(screen.getByRole('option', {name: 'Instance'}));
    expect(navigate).toHaveBeenCalledWith(7, undefined, 'Instance');
    expect(api.post).not.toHaveBeenCalled();
    unmount();
  });
  it('opens retained observations without a policy mutation', async () => {
    api.get.mockResolvedValue({data: {data: {state: 'stopped', samples: [{status: 'unavailable', scope: 'server'}]}}});
    const {unmount} = render(<Component serverId={7} />);
    fireEvent.click(await screen.findByRole('checkbox', {name: 'Recent observations'}));
    await screen.findByText('SR-F-001354');
    expect(screen.getByText(/Past observations from this process only/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
    unmount();
  });
  it('separate policy form explicitly starts and stops collection', async () => {
    const {unmount} = render(<Component serverId={7} policyMode />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.queryByTestId('read-only-ddn')).toBeNull();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', {name: 'Start collection'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/monitoring/7', {
      interval_seconds: 15, retain_samples: 120, lease_seconds: 3600,
      metadata_interval_seconds: 60,
      max_transaction_age_seconds: 0, max_backup_state_seconds: 0,
      require_wire_encryption: false, expected_encryption_state: null,
      heartbeat_enabled: true, heartbeat_timeout_seconds: null,
    }));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Stop collection'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Stop collection'}));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/monitoring/7'));
    expect(screen.getByText('SR-F-001352')).toBeInTheDocument();
    unmount();
  });
  it('admits an explicit heartbeat threshold and rejects values below the sampling interval plus five', async () => {
    const {unmount} = render(<Component serverId={7} policyMode />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.queryByLabelText('Heartbeat overdue after (seconds)')).toBeNull();
    fireEvent.click(screen.getByLabelText('Use completed refreshes as availability heartbeats'));
    const threshold = screen.getByLabelText('Heartbeat overdue after (seconds)');
    fireEvent.change(threshold, {target: {value: '19'}});
    expect(screen.getByRole('button', {name: 'Start collection'})).toBeDisabled();
    fireEvent.change(threshold, {target: {value: '60'}});
    fireEvent.click(screen.getByRole('button', {name: 'Start collection'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/monitoring/7', expect.objectContaining({
      heartbeat_enabled: true, heartbeat_timeout_seconds: 60,
    })));
    unmount();
  });
  it('submits a dedicated account only on explicit start and clears the password', async () => {
    const {unmount} = render(<Component serverId={7} policyMode />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    fireEvent.click(screen.getByLabelText('Use dedicated monitoring account'));
    expect(screen.getByRole('button', {name: 'Start collection'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Monitoring username'), {target: {value: 'COLLECTOR'}});
    fireEvent.change(screen.getByLabelText('Monitoring password'), {target: {value: 'test-secret'}});
    fireEvent.change(screen.getByLabelText('Monitoring role (optional)'), {target: {value: 'MONITOR'}});
    expect(screen.getByLabelText('Monitoring password')).toHaveAttribute('type', 'password');
    fireEvent.click(screen.getByRole('button', {name: 'Start collection'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/monitoring/7', expect.objectContaining({
      credentials: {username: 'COLLECTOR', password: 'test-secret', role: 'MONITOR'},
    })));
    await waitFor(() => expect(screen.getByLabelText('Monitoring password')).toHaveValue(''));
    unmount();
  });
  it('opens activity details using only the authorized snapshot', async () => {
    const {unmount} = render(<Component serverId={7} targetId="target" />);
    fireEvent.click(await screen.findByRole('checkbox', {name: 'Activity details'}));
    expect(screen.getByText('SR-F-001355')).toBeInTheDocument();
    expect(screen.getByText(/Past or unavailable collector snapshot/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
    unmount();
  });
  it('refused reads do not retain a previously authorized diagram', async () => {
    api.get.mockRejectedValue({response: {data: {errormsg: 'Not authorized'}}});
    const {unmount} = render(<Component serverId={7} />);
    await screen.findByText('Not authorized');
    expect(screen.queryByTestId('read-only-ddn')).toBeNull();
    unmount();
  });
});
