import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import Alerts from 'sources/Dialogs/MySQLAlerts';
import MySQLMonitoring from 'sources/Dialogs/MySQLMonitoring';
import getApiInstance from 'sources/api_instance';
import {withTheme} from '../fake_theme';
jest.mock('sources/api_instance');
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({DDNViewerSurface: () => <div data-testid="viewer" />}));
const Component = withTheme(Alerts), Policy = withTheme(MySQLMonitoring);
const rule = {id: 'rule-1', metric: 'threads_running', threshold: '0', duration_seconds: 5, missing: 'unknown', severity: 'warning', route_id: 'ops'};
const catalog = {metrics: [{id: 'threads_running', label: 'Running threads', unit: 'threads', action: 'Inspect native workload.'}], routes: [{id: 'ops', label: 'Operations'}]};
const alerts = {storage: 'volatile-policy-lease', event_limit: 100, rules: [{rule, state: 'firing', condition: 'threshold', evidence: {metric: 'threads_running', value: '9007199254740993', source: 'native status', sample_id: 'sample', server_uuid: 'native'}}],
  events: [{event_id: 'event', rule_id: 'rule-1', transition: 'firing', created_at: 'now', delivery: {state: 'outcome_unknown', error_type: 'NativeTransportError'}}]};
let height;
beforeEach(() => {height = window.innerHeight; window.innerHeight = 2400;});
afterEach(() => {window.innerHeight = height;});

it('configures native rules in policy mode and sends the complete typed policy', async () => {
  const api = {get: jest.fn(async () => ({data: {data: {state: 'disabled', samples: [], alert_catalog: catalog}}})),
    post: jest.fn(async () => ({data: {data: {state: 'collecting', alerts}}}))};
  getApiInstance.mockReturnValue(api); render(<Policy serverId={7} targetId="db" policyMode />);
  await waitFor(() => expect(screen.getByRole('button', {name: 'Add alert rule'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button', {name: 'Add alert rule'}));
  fireEvent.change(screen.getByLabelText('Threshold 1'), {target: {value: '9007199254740992'}});
  fireEvent.change(screen.getByLabelText('Duration seconds 1'), {target: {value: '10'}});
  fireEvent.click(screen.getByRole('button', {name: 'Start collection'}));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/cdeadmin/api/monitoring/mysql/7?target_id=db', expect.objectContaining({mysql_alert_rules: [expect.objectContaining({threshold: '9007199254740992', duration_seconds: 10})]})));
  await screen.findByText(/rule-1: firing/);
  expect(screen.getByLabelText('Threshold 1')).toBeDisabled();
  expect(screen.getByText(/9007199254740993/)).toBeVisible();
  expect(screen.getByText(/outcome_unknown/)).toBeVisible();
});

it('binds silence to the exact collector scope and preserves transport errors', async () => {
  const post = jest.fn().mockResolvedValue({data: {data: {...alerts, rules: [{...alerts.rules[0], state: 'silenced'}]}}});
  getApiInstance.mockReturnValue({post});
  render(<Component endpoint="/monitor/mysql/7?target_id=db%2Fone" catalog={catalog} rules={[rule]} onChange={jest.fn()} active alerts={alerts} />);
  fireEvent.change(screen.getByLabelText('Silence seconds'), {target: {value: '45'}});
  fireEvent.click(screen.getByRole('button', {name: 'Silence rule-1'}));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/monitor/mysql/7?target_id=db%2Fone', {action: 'silence', rule_id: 'rule-1', seconds: 45}));
  await screen.findByText(/rule-1: silenced/);
  post.mockRejectedValue({response: {data: {errormsg: 'Current grant ended'}}});
  fireEvent.click(screen.getByRole('button', {name: 'Unsilence rule-1'}));
  await screen.findByText('Current grant ended');
  expect(screen.getByText(/outcome_unknown/)).toBeVisible();
});

it('drops late silence responses after the endpoint changes', async () => {
  let finish; const post = jest.fn(() => new Promise(resolve => {finish = resolve;}));
  getApiInstance.mockReturnValue({post});
  const mounted = render(<Component endpoint="/first" catalog={catalog} rules={[rule]} onChange={jest.fn()} active alerts={alerts} />);
  fireEvent.click(screen.getByRole('button', {name: 'Silence rule-1'}));
  mounted.rerender(<Component endpoint="/second" catalog={catalog} rules={[]} onChange={jest.fn()} alerts={null} />);
  await act(async () => {finish({data: {data: alerts}});});
  expect(screen.queryByText(/9007199254740993/)).toBeNull();
});

it('never exposes alert administration in a dashboard viewer', async () => {
  getApiInstance.mockReturnValue({get: jest.fn(async () => ({data: {data: {state: 'collecting', alerts, alert_catalog: catalog}}}))});
  render(<Policy serverId={7} />);
  await screen.findByTestId('viewer');
  expect(screen.queryByRole('button', {name: 'Add alert rule'})).toBeNull();
  expect(screen.queryByRole('button', {name: 'Silence rule-1'})).toBeNull();
});
