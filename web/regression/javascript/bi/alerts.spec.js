/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {
  alertPermissions, describeCondition, draftFromAlert, draftReducer, expressionFor, historyRows, initialPanel,
  isExternal, newDraft, panelReducer, rowActions, scheduleFrom, statusLine, testViewModel, toDefinition,
  validateDraft,
} from 'sources/cdeadmin_ui/modules/bi/alerts';
import {createBIClient} from 'sources/cdeadmin_ui/modules/bi/biClient';
import {alertFixtures as fx} from './alertFixtures';

const draft = (patch = {}) => ({...newDraft({kind: 'alert', resourceType: 'question', resourceId: 'q-detail',
  resourceName: 'Detail'}), ...patch});
const byName = (items, name) => items.find((item) => item.name === name);

describe('schedule', () => {
  it('builds the cron expression of each preset', () => {
    const base = {preset: 'daily', minute: 30, hour: 7, weekday: 2, custom: ' 5   4 * * * ', timezone: 'UTC'};
    expect(expressionFor({...base, preset: 'hourly'})).toBe('30 * * * *');
    expect(expressionFor(base)).toBe('30 7 * * *');
    expect(expressionFor({...base, preset: 'weekdays'})).toBe('30 7 * * 1-5');
    expect(expressionFor({...base, preset: 'weekly'})).toBe('30 7 * * 2');
    expect(expressionFor({...base, preset: 'custom'})).toBe('5 4 * * *');
  });

  it('keeps hour and minute inside their range', () => {
    expect(expressionFor({preset: 'daily', minute: 99, hour: -4})).toBe('59 0 * * *');
  });

  it('recognises a preset in a stored expression and falls back to custom', () => {
    expect(scheduleFrom({expression: '0 * * * *', timezone: 'UTC'}).preset).toBe('hourly');
    expect(scheduleFrom({expression: '15 9 * * 1-5', timezone: 'UTC'})).toMatchObject({
      preset: 'weekdays', hour: 9, minute: 15});
    expect(scheduleFrom({expression: '0 6 * * 3', timezone: 'Europe/Berlin'})).toMatchObject({
      preset: 'weekly', weekday: 3, timezone: 'Europe/Berlin'});
    expect(scheduleFrom({expression: '*/5 * * * *', timezone: 'UTC'})).toMatchObject({
      preset: 'custom', custom: '*/5 * * * *'});
  });

  it('round-trips the expressions the backend accepted', () => {
    for(const item of [fx.created, fx.subscription, fx.quiet]) {
      const schedule = scheduleFrom(item.definition.schedule);
      expect(expressionFor(schedule)).toBe(item.definition.schedule.expression);
    }
  });
});

describe('condition text', () => {
  it('matches what the backend reports for the same condition', () => {
    expect(describeCondition(fx.created.definition.condition)).toBe(fx.testAlert.outcome.condition);
    expect(describeCondition({type: 'results', state: 'empty'})).toBe('the question returns no rows');
    expect(describeCondition({type: 'metric', metric: {kind: 'column', aggregate: 'sum', column: 'amount'},
      against: 'previous_percent', operator: 'between', value: [1, 5]}))
      .toBe('sum of amount (percent change since the previous evaluation) between 1 and 5');
  });
});

describe('draft to definition', () => {
  it('produces the definition the backend stored', () => {
    const stored = fx.created;
    const rebuilt = toDefinition(draftFromAlert(stored));
    expect(rebuilt.condition).toEqual(stored.definition.condition);
    expect(rebuilt.schedule).toEqual(stored.definition.schedule);
    expect(rebuilt.channels).toEqual(stored.definition.channels.map((channel) => ({
      type: channel.type, recipients: [{type: 'user', user_id: channel.recipients[0].user_id}]})));
    expect(rebuilt.fire_on).toBe('transition');
  });

  it('types the condition numbers and the between pair', () => {
    const value = toDefinition(draft({condition: {...draft().condition, type: 'metric', metricKind: 'column',
      aggregate: 'sum', column: ' amount ', operator: 'between', value: '10', high: '20.5'}}));
    expect(value.condition).toEqual({type: 'metric', metric: {kind: 'column', aggregate: 'sum', column: 'amount'},
      against: 'constant', operator: 'between', value: [10, 20.5]});
  });

  it('sends question parameters typed and dashboard values as filters, leaving blanks out', () => {
    const parameters = [{id: 'floor', type: 'integer'}, {id: 'tags', type: 'array'}, {id: 'on', type: 'boolean'}];
    const question = toDefinition(draft({parameters: {floor: '10', tags: 'a, b', on: 'true', empty: '  '}}),
      {parameters});
    expect(question.parameters).toEqual({floor: 10, tags: ['a', 'b'], on: true});
    expect(question.filters).toBeUndefined();
    const board = toDefinition(draft({kind: 'subscription', resource: {type: 'dashboard', id: 'd'},
      parameters: {region: 'east'}}));
    expect(board.filters).toEqual({region: 'east'});
    expect(board.parameters).toBeUndefined();
    expect(board.format).toBe('csv');
  });

  it('keeps a pinned revision when editing', () => {
    const edited = draftFromAlert({...fx.created, definition: {...fx.created.definition, revision: 3}});
    expect(toDefinition(edited).revision).toBe(3);
  });
});

describe('validation', () => {
  it('accepts a fresh valid draft only after it has a name and a resource', () => {
    expect(validateDraft(draft({name: '', resource: {type: 'question', id: ''}}))).toMatchObject({
      name: expect.any(String), resource: expect.any(String)});
    expect(validateDraft(draft({name: 'x', condition: {...draft().condition, value: '3'}}))).toEqual({});
  });

  it('checks the thresholds', () => {
    const base = draft({name: 'x'}).condition;
    expect(validateDraft(draft({name: 'x', condition: {...base, value: 'abc'}}))).toHaveProperty('value');
    expect(validateDraft(draft({name: 'x', condition: {...base, operator: 'between', value: '5', high: '2'}})))
      .toHaveProperty('high');
    expect(validateDraft(draft({name: 'x', condition: {...base, metricKind: 'column', column: ''}})))
      .toHaveProperty('column');
    expect(validateDraft(draft({name: 'x', condition: {type: 'results', state: 'exist'}}))).toEqual({});
  });

  it('checks channels', () => {
    const channels = [
      {type: 'email', profile_id: '', recipients: []},
      {type: 's3', profile_id: 'archive', object_name: 'bad name'},
      {type: 'webhook', url: 'http://plain.example'},
      {type: 'in_app', recipients: []},
    ];
    const errors = validateDraft(draft({name: 'x', channels, condition: {type: 'results', state: 'exist'}}));
    expect(Object.keys(errors).sort()).toEqual(['channel.0', 'channel.1', 'channel.2', 'channel.3']);
    expect(validateDraft(draft({name: 'x', channels: []}))).toHaveProperty('channels');
    expect(validateDraft(draft({name: 'x', channels: [{type: 'email', profile_id: 'mail',
      recipients: [{type: 'email', address: 'not-an-address'}]}]}))['channel.0']).toMatch(/invalid/);
  });

  it('marks channels that leave pgAdmin', () => {
    expect(isExternal({type: 'in_app', recipients: []})).toBe(false);
    expect(isExternal({type: 'email', profile_id: 'm', recipients: [{type: 'user', user_id: 1}]})).toBe(false);
    expect(isExternal({type: 'email', profile_id: 'm', recipients: [{type: 'email', address: 'a@b.example'}]})).toBe(true);
    expect(isExternal({type: 'webhook', url: 'https://x'})).toBe(true);
    expect(isExternal({type: 's3', profile_id: 'a', object_name: 'o'})).toBe(true);
  });
});

describe('draft reducer', () => {
  it('adds, edits and removes channels and recipients without duplicates', () => {
    let state = draft();
    state = draftReducer(state, {type: 'addChannel', channel: 'email'});
    expect(state.channels).toHaveLength(2);
    state = draftReducer(state, {type: 'channel', index: 1, patch: {profile_id: 'mail'}});
    const person = {type: 'user', user_id: 4, name: 'viewer'};
    state = draftReducer(state, {type: 'addRecipient', index: 1, recipient: person});
    state = draftReducer(state, {type: 'addRecipient', index: 1, recipient: {...person}});
    state = draftReducer(state, {type: 'addRecipient', index: 1, recipient: {type: 'email', address: 'A@B.example'}});
    state = draftReducer(state, {type: 'addRecipient', index: 1, recipient: {type: 'email', address: 'a@b.example'}});
    expect(state.channels[1].recipients).toHaveLength(2);
    state = draftReducer(state, {type: 'removeRecipient', index: 1, at: 0});
    expect(state.channels[1].recipients).toEqual([{type: 'email', address: 'A@B.example'}]);
    state = draftReducer(state, {type: 'removeChannel', index: 0});
    expect(state.channels.map((channel) => channel.type)).toEqual(['email']);
  });

  it('caps the number of channels', () => {
    let state = draft();
    for(let count = 0; count < 12; count += 1) state = draftReducer(state, {type: 'addChannel', channel: 'in_app'});
    expect(state.channels).toHaveLength(8);
  });
});

describe('row actions from the real list', () => {
  it('offers the owner everything that applies to the state', () => {
    const watch = byName(fx.list.items, 'Many rows');
    expect(rowActions(watch)).toMatchObject({edit: true, test: true, runNow: true, pause: true, mute: true,
      unmute: false, resume: false, remove: true, rearm: true});
  });

  it('lets a manager of the question mute, pause and delete another owner alert but not edit it', () => {
    const theirs = byName(fx.list.items, 'Viewer watch');
    expect(theirs.is_owner).toBe(false);
    expect(rowActions(theirs)).toMatchObject({edit: false, test: false, runNow: false, resume: false,
      remove: true, history: true});
  });

  it('offers resume, not pause, on a paused alert and says why', () => {
    const paused = fx.paused;
    expect(paused.status).toBe('paused');
    expect(rowActions(paused)).toMatchObject({resume: true, pause: false, runNow: false});
    expect(statusLine(paused)).toEqual({tone: 'warning', label: 'Paused',
      detail: 'The owner can no longer view the resource.'});
  });

  it('offers unmute on a muted alert', () => {
    expect(fx.muted.muted).toBe(true);
    expect(rowActions(fx.muted)).toMatchObject({mute: false, unmute: true});
    expect(statusLine(fx.muted).label).toBe('Muted');
  });

  it('shows the breach state', () => {
    expect(statusLine(byName(fx.list.items, 'Amount')).label).toBe('OK');
    expect(statusLine(byName(fx.list.items, 'Daily digest')).label).toBe('Active');
  });

  it('only offers external channels at manage access', () => {
    expect(alertPermissions('manage')).toMatchObject({canCreate: true, canExternal: true});
    expect(alertPermissions('edit').canExternal).toBe(false);
    expect(alertPermissions('view')).toMatchObject({canCreate: true, canExternal: false});
    expect(alertPermissions('manage', {scheduling: false}).canCreate).toBe(false);
  });
});

describe('history', () => {
  it('shows fixed texts and no secrets or SQL to a viewer', () => {
    const rows = historyRows(fx.pausedHistory);
    expect(rows.length).toBeGreaterThan(0);
    for(const row of rows) expect(row.detail).toBe('');
    const text = JSON.stringify(rows);
    expect(text).not.toMatch(/select|secret|password/i);
    expect(rows.some((row) => row.problem === 'The owner can no longer view the resource.')).toBe(true);
  });

  it('describes a fired check with its delivery', () => {
    const rows = historyRows(fx.history);
    expect(rows.map((row) => row.label)).toEqual(['Condition met', 'Condition met']);
    const fired = rows.find((row) => row.fired);
    expect(fired.deliveries[0]).toMatchObject({channel: 'in_app', state: 'delivered'});
    expect(fired.value).toBe('5');
    expect(rows.filter((row) => row.fired)).toHaveLength(1);
  });

  it('describes a check whose notification was held back by a mute', () => {
    const [row] = historyRows(fx.mutedHistory);
    expect(row).toMatchObject({fired: false, suppressed: 'muted'});
  });
});

describe('dry run', () => {
  it('summarises an alert test', () => {
    const view = testViewModel(fx.testAlert);
    expect(view).toMatchObject({kind: 'alert', verdict: 'breach', breached: true, wouldFire: true, value: 5,
      rowCount: 5, condition: 'row count > 3'});
    expect(view.preview.rows).toHaveLength(5);
    expect(view.deliveries[0].state).toBe('would_send');
  });

  it('summarises a stored alert that stays quiet', () => {
    const view = testViewModel(fx.testStored);
    expect(view.breached).toBe(false);
    expect(view.wouldFire).toBe(false);
  });

  it('summarises a subscription snapshot', () => {
    const view = testViewModel(fx.testSubscription);
    expect(view).toMatchObject({kind: 'subscription', wouldFire: true});
    expect(view.items).toEqual([expect.objectContaining({title: 'Detail by region', status: 'ok', rowCount: 5})]);
    expect(view.attachments[0].format).toBe('csv');
  });

  it('is empty without a report', () => {
    expect(testViewModel(null)).toBeNull();
  });
});

describe('panel reducer', () => {
  it('loads, fails and keeps the previous list on a later failure', () => {
    let state = panelReducer(initialPanel(), {type: 'loaded', items: fx.list.items});
    expect(state.status).toBe('ready');
    state = panelReducer(state, {type: 'failed', error: 'x'});
    expect(state.status).toBe('ready');
    expect(state.items).toHaveLength(fx.list.items.length);
    expect(panelReducer(initialPanel(), {type: 'failed', error: 'x'}).status).toBe('error');
  });

  it('ignores a history answer that arrives after another row was opened', () => {
    let state = panelReducer(initialPanel(), {type: 'openHistory', id: 'a'});
    state = panelReducer(state, {type: 'openHistory', id: 'b'});
    state = panelReducer(state, {type: 'historyLoaded', id: 'a', items: [1]});
    expect(state.history.status).toBe('loading');
    state = panelReducer(state, {type: 'historyLoaded', id: 'b', items: [2]});
    expect(state.history).toMatchObject({status: 'ready', items: [2]});
    expect(panelReducer(state, {type: 'closeHistory'}).openId).toBe('');
  });
});

describe('client', () => {
  const make = () => {
    const post = jest.fn(async () => ({items: []}));
    return {post, client: createBIClient(post)};
  };

  it('sends the action names and request bodies the backend dispatches', async () => {
    const {post, client} = make();
    await client.alertCatalog();
    await client.schedulePreview({expression: '0 * * * *', timezone: 'UTC'}, 3);
    await client.listAlerts('question', 'q1');
    await client.updateAlert('a1', 2, {name: 'n'});
    await client.testAlert('a1');
    await client.testAlert(null, {name: 'draft'});
    await client.muteAlert('a1', 60);
    await client.resumeAlert('a1');
    await client.alertHistory('a1');
    await client.markNotificationsRead();
    expect(post.mock.calls.map(([payload]) => payload)).toEqual([
      {action: 'bi_alert_catalog', request: {}},
      {action: 'bi_alert_schedule_preview', request: {schedule: {expression: '0 * * * *', timezone: 'UTC'}, count: 3}},
      {action: 'bi_alert_list', request: {resource_type: 'question', resource_id: 'q1'}},
      {action: 'bi_alert_update', request: {alert_id: 'a1', expected_revision: 2, alert: {name: 'n'}}},
      {action: 'bi_alert_test', request: {alert_id: 'a1'}},
      {action: 'bi_alert_test', request: {alert: {name: 'draft'}}},
      {action: 'bi_alert_mute', request: {alert_id: 'a1', duration_minutes: 60}},
      {action: 'bi_alert_resume', request: {alert_id: 'a1', reset: false}},
      {action: 'bi_alert_history', request: {alert_id: 'a1', limit: 50}},
      {action: 'bi_notification_read', request: {}},
    ]);
  });
});
