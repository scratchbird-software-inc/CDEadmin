/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import Theme from 'sources/Theme';
import AlertsPanel from 'sources/cdeadmin_ui/modules/bi/AlertsPanel';
import {alertFixtures as fx} from './alertFixtures';

beforeEach(() => { window.innerHeight = 1200; });

function fakeClient(overrides = {}) {
  return {
    alertCatalog: jest.fn(async () => fx.catalog),
    schedulePreview: jest.fn(async () => fx.schedulePreview),
    listAlerts: jest.fn(async () => fx.list.items),
    getAlert: jest.fn(async () => fx.created),
    createAlert: jest.fn(async () => fx.created),
    updateAlert: jest.fn(async () => fx.created),
    deleteAlert: jest.fn(async () => ({})),
    testAlert: jest.fn(async (id) => id ? fx.testStored : fx.testAlert),
    runAlertNow: jest.fn(async () => ({state: 'delivered'})),
    muteAlert: jest.fn(async () => ({})),
    unmuteAlert: jest.fn(async () => ({})),
    rearmAlert: jest.fn(async () => ({})),
    pauseAlert: jest.fn(async () => ({})),
    resumeAlert: jest.fn(async () => ({})),
    alertHistory: jest.fn(async () => fx.history),
    searchPrincipals: jest.fn(async () => []),
    ...overrides,
  };
}

const open = async (client, props = {}) => {
  const onClose = jest.fn();
  render(<Theme><AlertsPanel client={client} resourceType="question" resourceId="q-detail"
    resourceName="Detail by region" columns={['region', 'product', 'amount']} onClose={onClose} {...props} /></Theme>);
  await screen.findByRole('region', {name: 'Alerts and subscriptions'});
  await waitFor(() => expect(screen.queryByText('Loading...')).not.toBeInTheDocument());
  return {onClose};
};

const row = (name) => within(screen.getByRole('list', {name: 'Alerts and subscriptions list'}))
  .getByRole('listitem', {name});

async function choose(label, option) {
  fireEvent.mouseDown(screen.getByRole('combobox', {name: label}));
  fireEvent.click(await screen.findByRole('option', {name: option}));
}

describe('AlertsPanel list', () => {
  it('lists alerts and subscriptions with their state', async () => {
    await open(fakeClient());
    expect(within(row('Many rows')).getByText('In breach')).toBeInTheDocument();
    expect(within(row('Amount')).getByText('OK')).toBeInTheDocument();
    expect(within(row('Daily digest')).getByText('Subscription')).toBeInTheDocument();
    expect(within(row('Many rows')).getByText(/row count > 3/)).toBeInTheDocument();
    expect(within(row('Viewer watch')).getByText('Paused')).toBeInTheDocument();
    expect(within(row('Viewer watch')).getByText('The owner can no longer view the resource.')).toBeInTheDocument();
  });

  it('gives another owner\'s alert only mute, pause, delete and history', async () => {
    await open(fakeClient());
    const theirs = row('Viewer watch');
    expect(within(theirs).queryByRole('button', {name: 'Edit Viewer watch'})).not.toBeInTheDocument();
    expect(within(theirs).queryByRole('button', {name: 'Test Viewer watch'})).not.toBeInTheDocument();
    expect(within(theirs).queryByRole('button', {name: 'Resume Viewer watch'})).not.toBeInTheDocument();
    expect(within(theirs).getByRole('button', {name: 'Delete Viewer watch'})).toBeInTheDocument();
    expect(within(theirs).getByRole('button', {name: 'History of Viewer watch'})).toBeInTheDocument();
    expect(within(row('Many rows')).getByRole('button', {name: 'Edit Many rows'})).toBeInTheDocument();
  });

  it('runs a row action and refreshes the list', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(within(row('Many rows')).getByRole('button', {name: 'Pause Many rows'}));
    await waitFor(() => expect(client.pauseAlert).toHaveBeenCalledWith(expect.any(String)));
    await waitFor(() => expect(client.listAlerts).toHaveBeenCalledTimes(2));
  });

  it('mutes for a chosen time', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(within(row('Many rows')).getByRole('button', {name: 'Mute for 4 hours: Many rows'}));
    await waitFor(() => expect(client.muteAlert).toHaveBeenCalledWith(expect.any(String), 240));
  });

  it('shows the dry run of a stored alert without running or changing it', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(within(row('Amount')).getByRole('button', {name: 'Test Amount'}));
    const result = await screen.findByRole('region', {name: 'Test result'});
    expect(within(result).getByText('Condition not met')).toBeInTheDocument();
    expect(within(result).getByText(/Nothing was sent/)).toBeInTheDocument();
    expect(client.runAlertNow).not.toHaveBeenCalled();
    expect(client.createAlert).not.toHaveBeenCalled();
  });

  it('shows the history table with the fixed texts', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(within(row('Many rows')).getByRole('button', {name: 'History of Many rows'}));
    const table = await screen.findByRole('table', {name: 'History'});
    expect(within(table).getAllByText('Condition met').length).toBeGreaterThan(0);
    expect(within(table).getByText('Notified')).toBeInTheDocument();
    fireEvent.click(within(row('Many rows')).getByRole('button', {name: 'History of Many rows'}));
    await waitFor(() => expect(screen.queryByRole('table', {name: 'History'})).not.toBeInTheDocument());
  });

  it('shows the server refusal and keeps the list', async () => {
    const client = fakeClient({deleteAlert: jest.fn(async () => { throw new Error('alert is unavailable'); })});
    await open(client);
    fireEvent.click(within(row('Amount')).getByRole('button', {name: 'Delete Amount'}));
    expect(await screen.findByText('alert is unavailable')).toBeInTheDocument();
    expect(row('Amount')).toBeInTheDocument();
  });

  it('offers no alerts on a dashboard, only subscriptions', async () => {
    await open(fakeClient({listAlerts: jest.fn(async () => [])}), {resourceType: 'dashboard', resourceId: 'd-1'});
    expect(screen.queryByRole('button', {name: 'New alert'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'New subscription'})).toBeInTheDocument();
  });

  it('disables creating when the server has no scheduler', async () => {
    await open(fakeClient({alertCatalog: jest.fn(async () => ({...fx.catalog, scheduling: false}))}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'New alert'})).toBeDisabled());
  });
});

describe('AlertDialog', () => {
  const startAlert = async (client, props) => {
    await open(client, props);
    await waitFor(() => expect(screen.getByRole('button', {name: 'New alert'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'New alert'}));
    return screen.findByRole('dialog');
  };

  it('previews the next runs from the server and warns about a too frequent schedule', async () => {
    const client = fakeClient({schedulePreview: jest.fn(async () => ({...fx.schedulePreview,
      interval_seconds: 60}))});
    const dialog = await startAlert(client);
    const runs = await within(dialog).findByRole('list', {name: 'Next runs'});
    expect(within(runs).getAllByRole('listitem')).toHaveLength(fx.schedulePreview.next_runs.length);
    expect(client.schedulePreview).toHaveBeenCalledWith({expression: '0 8 * * *', timezone: expect.any(String)}, 5);
    expect(await within(dialog).findByText(/more often than the server allows/)).toBeInTheDocument();
  });

  it('tests the unsaved definition without sending or saving it', async () => {
    const client = fakeClient();
    const dialog = await startAlert(client);
    expect(within(dialog).getByRole('button', {name: 'Test evaluate'})).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText('Value'), {target: {value: '3'}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Test evaluate'}));
    const result = await within(dialog).findByRole('region', {name: 'Test result'});
    expect(within(result).getByText('Would notify')).toBeInTheDocument();
    expect(within(result).getAllByText(/row count > 3/).length).toBeGreaterThan(0);
    expect(within(result).getByText('in_app user:1: would_send')).toBeInTheDocument();
    expect(client.testAlert).toHaveBeenCalledWith(null, expect.objectContaining({
      kind: 'alert', resource: {type: 'question', id: 'q-detail'},
      condition: {type: 'metric', metric: {kind: 'row_count'}, against: 'constant', operator: '>', value: 3}}));
    expect(client.createAlert).not.toHaveBeenCalled();
  });

  it('creates the alert with the definition from the form and refreshes', async () => {
    const client = fakeClient();
    const dialog = await startAlert(client);
    fireEvent.change(within(dialog).getByLabelText('Name'), {target: {value: ' Big board '}});
    await choose('Operator', 'is at least');
    fireEvent.change(within(dialog).getByLabelText('Value'), {target: {value: '7'}});
    await choose('Repeat', 'Weekdays');
    fireEvent.click(within(dialog).getByRole('button', {name: 'Create'}));
    await waitFor(() => expect(client.createAlert).toHaveBeenCalledTimes(1));
    const sent = client.createAlert.mock.calls[0][0];
    expect(sent).toMatchObject({kind: 'alert', name: 'Big board', fire_on: 'transition',
      condition: {operator: '>=', value: 7}, schedule: {expression: '0 8 * * 1-5'},
      channels: [{type: 'in_app', recipients: [{type: 'self'}]}]});
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(client.listAlerts).toHaveBeenCalledTimes(2);
  });

  it('shows the server refusal inside the dialog and keeps it open', async () => {
    const client = fakeClient({createAlert: jest.fn(async () => { throw new Error('the schedule runs more often than every 5 minutes'); })});
    const dialog = await startAlert(client);
    fireEvent.change(within(dialog).getByLabelText('Value'), {target: {value: '1'}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Create'}));
    expect(await within(dialog).findByText('the schedule runs more often than every 5 minutes')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('keeps Create disabled until the form is valid and says what is missing', async () => {
    const dialog = await startAlert(fakeClient());
    expect(within(dialog).getByRole('button', {name: 'Create'})).toBeDisabled();
    expect(within(dialog).getByText('Enter a number.')).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText('Value'), {target: {value: '2'}});
    expect(within(dialog).getByRole('button', {name: 'Create'})).toBeEnabled();
  });

  it('adds a searched user as a recipient of an email channel', async () => {
    const client = fakeClient({searchPrincipals: jest.fn(async () => [{type: 'user', id: 4, name: 'viewer'}])});
    const dialog = await startAlert(client);
    await choose('Add a channel', 'Email');
    fireEvent.click(within(dialog).getByRole('button', {name: 'Add channel'}));
    const channel = within(dialog).getByRole('group', {name: 'Channel 2'});
    await choose('Mail profile', 'Operations mail');
    fireEvent.click(await within(channel).findByRole('button', {name: 'Choose user viewer'}));
    expect(within(channel).getByRole('button', {name: 'Remove recipient viewer'})).toBeInTheDocument();
    fireEvent.change(within(channel).getByLabelText(/Add a user/), {target: {value: 'someone@corp.example'}});
    fireEvent.click(await within(channel).findByRole('button', {name: 'Add address someone@corp.example'}));
    expect(within(channel).getByRole('button', {name: 'Remove recipient someone@corp.example'})).toBeInTheDocument();
  });

  it('offers object storage and webhooks only at manage access', async () => {
    const dialog = await startAlert(fakeClient(), {access: 'view'});
    fireEvent.mouseDown(within(dialog).getByRole('combobox', {name: 'Add a channel'}));
    const options = (await screen.findAllByRole('option')).map((option) => option.textContent);
    expect(options).toEqual(['In-app notification', 'Email']);
    expect(within(dialog).getByText(/need manage access/)).toBeInTheDocument();
  });

  it('edits a stored alert and saves against its revision', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(within(row('Many rows')).getByRole('button', {name: 'Edit Many rows'}));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText('Name')).toHaveValue('Many rows');
    expect(within(dialog).getByLabelText('Value')).toHaveValue('3');
    fireEvent.change(within(dialog).getByLabelText('Value'), {target: {value: '9'}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Save changes'}));
    await waitFor(() => expect(client.updateAlert).toHaveBeenCalledWith(
      expect.any(String), expect.any(Number), expect.objectContaining({
        condition: expect.objectContaining({value: 9})})));
  });

  it('builds a subscription with a format and tests it', async () => {
    const client = fakeClient({testAlert: jest.fn(async () => fx.testSubscription)});
    await open(client);
    await waitFor(() => expect(screen.getByRole('button', {name: 'New subscription'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'New subscription'}));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByRole('combobox', {name: 'Notify when'})).not.toBeInTheDocument();
    await choose('Format', 'XLSX');
    fireEvent.click(within(dialog).getByRole('button', {name: 'Test evaluate'}));
    const result = await within(dialog).findByRole('region', {name: 'Test result'});
    expect(within(result).getAllByText(/Detail by region: 5 rows/).length).toBeGreaterThan(0);
    expect(client.testAlert).toHaveBeenCalledWith(null, expect.objectContaining({kind: 'subscription', format: 'xlsx'}));
  });
});
