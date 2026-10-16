import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import MySQLMonitoring, {mysqlDashboardFiles} from 'sources/Dialogs/MySQLMonitoring';
import getApiInstance from 'sources/api_instance';
import {withTheme} from '../fake_theme';

jest.mock('sources/api_instance');
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: props => <div data-testid="viewer" data-read-only={props.presentation} />,
}));

const Component = withTheme(MySQLMonitoring);
describe('MySQL dedicated monitoring controls', () => {
  let api, originalHeight;
  beforeEach(() => {
    originalHeight = window.innerHeight; window.innerHeight = 1200;
    api = {get: jest.fn(async () => ({data: {data: {state: 'disabled', samples: []}}})),
      post: jest.fn(async () => ({data: {data: {state: 'collecting'}}})),
      delete: jest.fn(async () => ({data: {data: {state: 'disabled'}}}))};
    getApiInstance.mockReturnValue(api);
  });
  afterEach(() => {window.innerHeight = originalHeight;});
  it('keeps native dashboard views display-only', async () => {
    render(<Component serverId={7} targetId="mysql:demo" />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/cdeadmin/api/monitoring/mysql/7?target_id=mysql%3Ademo'));
    expect(screen.getByTestId('viewer')).toHaveAttribute('data-read-only', 'true');
    expect(screen.queryByRole('button', {name: 'Start collection'})).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
  });
  it('engine dashboards stay display-only even if policyMode is supplied', async () => {
    render(<Component engineMode policyMode />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/cdeadmin/api/monitoring/mysql'));
    expect(screen.queryByRole('button', {name: 'Start collection'})).toBeNull();
    expect(screen.getByTestId('viewer')).toHaveAttribute('data-read-only', 'true');
    expect(api.post).not.toHaveBeenCalled();
  });
  it('opens retained trend views without changing collector policy', async () => {
    render(<Component serverId={7} targetId="mysql:demo" />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Display'}));
    fireEvent.click(await screen.findByRole('option', {name: 'Retained observations'}));
    expect(screen.getByText('SR-F-001397')).toBeVisible();
    expect(screen.getByRole('combobox', {name: 'Retained window'})).toBeVisible();
    expect(api.post).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });
  it('uses registered credentials by default and validates heartbeat timeout', async () => {
    render(<Component serverId={7} targetId="mysql:demo" policyMode />);
    const start = screen.getByRole('button', {name: 'Start collection'});
    await waitFor(() => expect(start).toBeEnabled());
    expect(screen.queryByLabelText('Monitoring password')).toBeNull();
    fireEvent.click(screen.getByRole('checkbox', {name: 'Use completed refreshes as availability heartbeats'}));
    const timeout = screen.getByLabelText('Heartbeat timeout (seconds; blank uses policy default)');
    fireEvent.change(timeout, {target: {value: '9'}});
    expect(start).toBeDisabled();
    fireEvent.change(timeout, {target: {value: '20'}});
    fireEvent.click(start);
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toEqual({interval_seconds: 5, retain_samples: 120,
      lease_seconds: 3600, metadata_interval_seconds: 60, heartbeat_enabled: true, heartbeat_timeout_seconds: 20, history_enabled: false});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Stop collection'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Stop collection'}));
    await waitFor(() => expect(api.delete).toHaveBeenCalled());
  });
  it('clears dedicated credentials on failure and preserves the action error after a poll', async () => {
    let poll;
    const timer = jest.spyOn(global, 'setInterval').mockImplementation(callback => {poll = callback; return 999;});
    api.post.mockRejectedValue({response: {data: {errormsg: 'Credentials unavailable'}}});
    const mounted = render(<Component serverId={7} policyMode />);
    try {
      await waitFor(() => expect(screen.getByRole('button', {name: 'Start collection'})).toBeEnabled());
      fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Monitoring credentials'}));
      fireEvent.click(await screen.findByRole('option', {name: 'Dedicated monitoring account'}));
      fireEvent.change(screen.getByLabelText('Monitoring username'), {target: {value: 'collector'}});
      fireEvent.change(screen.getByLabelText('Monitoring password'), {target: {value: 'private-fixture'}});
      fireEvent.click(screen.getByRole('checkbox', {name: 'Show password'}));
      expect(screen.getByLabelText('Monitoring password')).toHaveAttribute('type', 'text');
      fireEvent.click(screen.getByRole('button', {name: 'Start collection'}));
      await screen.findByText('Credentials unavailable');
      expect(screen.getByLabelText('Monitoring password')).toHaveValue('');
      await act(async () => {await poll();});
      expect(screen.getByText('Credentials unavailable')).toBeVisible();
      expect(api.post.mock.calls[0][1].credentials).toEqual({username: 'collector', password: 'private-fixture', role: ''});
    } finally {mounted.unmount(); timer.mockRestore();}
  });
  it('discards late policy responses and credentials when the selected database changes', async () => {
    let finish;
    api.post.mockImplementation(() => new Promise(resolve => {finish = resolve;}));
    const mounted = render(<Component serverId={7} targetId="old" policyMode />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Start collection'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Start collection'}));
    mounted.rerender(<Component serverId={7} targetId="new" policyMode />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/cdeadmin/api/monitoring/mysql/7?target_id=new'));
    await act(async () => {finish({data: {data: {state: 'collecting'}}});});
    expect(screen.getByRole('button', {name: 'Start collection'})).toBeEnabled();
    expect(screen.getByRole('button', {name: 'Stop collection'})).toBeDisabled();
  });
});

describe('MySQL native dashboard freshness', () => {
  const current = {state: 'collecting', sample_age_seconds: 1, stale_after_seconds: 15,
    samples: [{scope: 'database', status: 'partial', transaction_completed: true,
      identity: {database_name: 'demo'}, groups: {settings: {status: 'available', scope: 'server',
        rows: [{max_connections: 'NATIVE_VISIBLE_SETTING'}]}, activity: {status: 'unavailable'}}}]};
  it('publishes visible values and distinguishes unavailable groups', () => {
    const source = mysqlDashboardFiles(current, 'database')['dashboard.ddn'];
    expect(source).toContain('NATIVE_VISIBLE_SETTING');
    expect(source).toContain('unavailable');
  });
  it.each(['stale', 'incomplete', 'failed', 'scope'])('does not publish %s values as current', reason => {
    const snapshot = JSON.parse(JSON.stringify(current));
    if(reason === 'stale') snapshot.sample_age_seconds = 100;
    if(reason === 'incomplete') snapshot.samples[0].transaction_completed = false;
    if(reason === 'failed') snapshot.samples[0].status = 'unavailable';
    if(reason === 'scope') snapshot.samples[0].scope = 'server';
    expect(mysqlDashboardFiles(snapshot, 'database')['dashboard.ddn']).not.toContain('NATIVE_VISIBLE_SETTING');
  });
});
