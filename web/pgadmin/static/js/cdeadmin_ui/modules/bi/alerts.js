/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Pure model of BI alerts and subscriptions (docs/en_US/bi_alerts.rst): the
 * draft behind the create/edit form, the conversion to the backend
 * definition, client-side validation, and the view models of the list, the
 * history and a dry run. The server validates every request again; nothing
 * here is a gate, it only decides what the form offers and says early.
 */

import gettext from 'sources/gettext';
import {rank} from './sharing';

export const OPERATORS = ['>', '>=', '<', '<=', '==', '!=', 'between'];
export const AGGREGATES = ['first', 'sum', 'avg', 'min', 'max'];
export const AGAINST = ['constant', 'previous_change', 'previous_percent'];
export const FORMATS = ['csv', 'xlsx', 'pdf', 'svg'];
export const MUTE_MINUTES = [60, 240, 1440, 10080];

const MAX_NAME = 256;
const MAX_RECIPIENTS = 20;
const MAX_CHANNELS = 8;
const EMAIL = /^[^@\s,;<>()[\]\\"]{1,64}@[A-Za-z0-9.-]{1,253}$/;
const OBJECT_BASE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;

// ---------------------------------------------------------------------------
// schedule
// ---------------------------------------------------------------------------

export const PRESETS = ['hourly', 'daily', 'weekdays', 'weekly', 'custom'];
export const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];

const clampInt = (value, low, high, fallback) => {
  const number = Number.parseInt(value, 10);
  return Number.isInteger(number) ? Math.min(high, Math.max(low, number)) : fallback;
};

export function newSchedule(timezone = 'UTC') {
  return {preset: 'daily', minute: 0, hour: 8, weekday: 1, custom: '0 8 * * *', timezone};
}

/** The five-field cron expression a schedule draft stands for. */
export function expressionFor(schedule) {
  const minute = clampInt(schedule.minute, 0, 59, 0);
  const hour = clampInt(schedule.hour, 0, 23, 0);
  switch(schedule.preset) {
  case 'hourly': return `${minute} * * * *`;
  case 'daily': return `${minute} ${hour} * * *`;
  case 'weekdays': return `${minute} ${hour} * * 1-5`;
  case 'weekly': return `${minute} ${hour} * * ${clampInt(schedule.weekday, 0, 6, 1)}`;
  default: return String(schedule.custom || '').trim().split(/\s+/).join(' ');
  }
}

/** A draft for a stored expression: a preset when it is exactly one, else custom. */
export function scheduleFrom(stored) {
  const expression = stored?.expression || '0 8 * * *';
  const timezone = stored?.timezone || 'UTC';
  const base = {...newSchedule(timezone), custom: expression};
  let match = /^(\d{1,2}) \* \* \* \*$/.exec(expression);
  if(match) return {...base, preset: 'hourly', minute: Number(match[1])};
  match = /^(\d{1,2}) (\d{1,2}) \* \* (\*|1-5|[0-6])$/.exec(expression);
  if(match) {
    const timed = {...base, minute: Number(match[1]), hour: Number(match[2])};
    if(match[3] === '*') return {...timed, preset: 'daily'};
    if(match[3] === '1-5') return {...timed, preset: 'weekdays'};
    return {...timed, preset: 'weekly', weekday: Number(match[3])};
  }
  return {...base, preset: 'custom'};
}

export const scheduleDefinition = (schedule) => ({
  expression: expressionFor(schedule), timezone: String(schedule.timezone || 'UTC').trim(),
});

/** Whether two schedules would ask the server for the same preview. */
export const sameSchedule = (left, right) => {
  const a = scheduleDefinition(left);
  const b = scheduleDefinition(right);
  return a.expression === b.expression && a.timezone === b.timezone;
};

// ---------------------------------------------------------------------------
// draft
// ---------------------------------------------------------------------------

export const newCondition = () => ({
  type: 'metric', metricKind: 'row_count', aggregate: 'first', column: '', against: 'constant',
  operator: '>', value: '', high: '', state: 'exist',
});

/**
 * An empty draft for one resource. Alerts are defined on questions and
 * subscriptions on questions or dashboards, so `kind` decides which parts of
 * the form apply.
 */
export function newDraft({kind = 'alert', resourceType = 'question', resourceId = '', resourceName = '',
  timezone = 'UTC', parameters = {}} = {}) {
  return {
    alertId: null, revision: null, kind, name: resourceName ? `${resourceName}` : '',
    resource: {type: resourceType, id: resourceId}, schedule: newSchedule(timezone),
    condition: newCondition(), fireOn: 'transition', format: 'csv',
    channels: [{type: 'in_app', recipients: [{type: 'self'}]}],
    parameters: {...parameters}, expiresInDays: 30,
  };
}

function conditionDraft(stored) {
  if(!stored) return newCondition();
  if(stored.type === 'results') return {...newCondition(), type: 'results', state: stored.state};
  const metric = stored.metric || {};
  const between = stored.operator === 'between';
  return {
    ...newCondition(), type: 'metric', metricKind: metric.kind || 'row_count',
    aggregate: metric.aggregate || 'first', column: metric.column || '', against: stored.against || 'constant',
    operator: stored.operator, value: between ? String(stored.value[0]) : String(stored.value),
    high: between ? String(stored.value[1]) : '',
  };
}

function channelDraft(channel) {
  const recipients = (channel.recipients || []).map((entry) => entry.type === 'email' ?
    {type: 'email', address: entry.address} : {type: 'user', user_id: entry.user_id, name: entry.name || ''});
  switch(channel.type) {
  case 'email': return {type: 'email', profile_id: channel.profile_id || '', recipients};
  case 's3': return {type: 's3', profile_id: channel.profile_id || '', object_name: channel.object_name || ''};
  case 'webhook': return {type: 'webhook', url: channel.url || ''};
  default: return {type: 'in_app', recipients};
  }
}

/** A draft that edits a stored alert (the shape bi_alert_get returns). */
export function draftFromAlert(alert) {
  const definition = alert.definition;
  const parameters = {};
  for(const [key, value] of Object.entries(definition.parameters || {})) {
    parameters[key] = Array.isArray(value) ? value.join(', ') : String(value);
  }
  return {
    alertId: alert.alert_id, revision: alert.revision, kind: alert.kind, name: alert.name,
    resource: {type: alert.resource.type, id: alert.resource.id},
    schedule: scheduleFrom(definition.schedule), condition: conditionDraft(definition.condition),
    fireOn: definition.fire_on || 'transition', format: definition.format || 'csv',
    channels: (definition.channels || []).map(channelDraft),
    parameters, expiresInDays: definition.expires_in_days || 30,
    pinnedRevision: definition.revision || null,
  };
}

const emptyChannel = (type) => {
  switch(type) {
  case 'email': return {type, profile_id: '', recipients: []};
  case 's3': return {type, profile_id: '', object_name: ''};
  case 'webhook': return {type, url: ''};
  default: return {type: 'in_app', recipients: [{type: 'self'}]};
  }
};

export function draftReducer(state, action) {
  switch(action.type) {
  case 'replace':
    return action.draft;
  case 'name':
    return {...state, name: action.name};
  case 'fireOn':
    return {...state, fireOn: action.fireOn};
  case 'format':
    return {...state, format: action.format};
  case 'expires':
    return {...state, expiresInDays: action.days};
  case 'condition':
    return {...state, condition: {...state.condition, ...action.patch}};
  case 'schedule':
    return {...state, schedule: {...state.schedule, ...action.patch}};
  case 'parameter':
    return {...state, parameters: {...state.parameters, [action.id]: action.text}};
  case 'addChannel':
    return state.channels.length >= MAX_CHANNELS ? state :
      {...state, channels: [...state.channels, emptyChannel(action.channel)]};
  case 'removeChannel':
    return {...state, channels: state.channels.filter((_item, index) => index !== action.index)};
  case 'channel':
    return {...state, channels: state.channels.map((item, index) =>
      index === action.index ? {...item, ...action.patch} : item)};
  case 'addRecipient': {
    return {...state, channels: state.channels.map((item, index) => {
      if(index !== action.index || (item.recipients || []).length >= MAX_RECIPIENTS) return item;
      if(item.recipients.some((entry) => sameRecipient(entry, action.recipient))) return item;
      return {...item, recipients: [...item.recipients, action.recipient]};
    })};
  }
  case 'removeRecipient':
    return {...state, channels: state.channels.map((item, index) => index !== action.index ? item :
      {...item, recipients: item.recipients.filter((_entry, at) => at !== action.at)})};
  default:
    return state;
  }
}

export function sameRecipient(left, right) {
  if(left.type !== right.type) return false;
  if(left.type === 'email') return left.address.toLowerCase() === right.address.toLowerCase();
  if(left.type === 'self') return true;
  return left.user_id === right.user_id;
}

// ---------------------------------------------------------------------------
// draft -> definition
// ---------------------------------------------------------------------------

function typedValue(type, text) {
  const raw = String(text ?? '').trim();
  switch(type) {
  case 'integer': case 'number': {
    const number = Number(raw);
    return raw !== '' && Number.isFinite(number) ? number : raw;
  }
  case 'boolean': return raw === 'true' || raw === 'false' ? raw === 'true' : raw;
  case 'array': return raw.split(',').map((part) => part.trim()).filter(Boolean);
  default: return raw;
  }
}

/** Parameter values to send: only filled ones, typed by the question's parameters. */
export function parameterDefinition(values, parameters = []) {
  const types = Object.fromEntries(parameters.map((item) => [item.id, item.type]));
  const result = {};
  for(const [key, text] of Object.entries(values || {})) {
    if(String(text ?? '').trim() === '') continue;
    result[key] = typedValue(types[key] || 'string', text);
  }
  return result;
}

const number = (text) => {
  const raw = String(text ?? '').trim();
  const value = Number(raw);
  return raw !== '' && Number.isFinite(value) ? value : null;
};

function conditionDefinition(condition) {
  if(condition.type === 'results') return {type: 'results', state: condition.state};
  const metric = condition.metricKind === 'column' ?
    {kind: 'column', aggregate: condition.aggregate, column: condition.column.trim()} : {kind: 'row_count'};
  const low = number(condition.value);
  const value = condition.operator === 'between' ? [low, number(condition.high)] : low;
  return {type: 'metric', metric, against: condition.against, operator: condition.operator, value};
}

const recipientDefinition = (entry) => entry.type === 'email' ?
  {type: 'email', address: entry.address.trim()} :
  entry.type === 'self' ? {type: 'self'} : {type: 'user', user_id: entry.user_id};

function channelDefinition(channel) {
  switch(channel.type) {
  case 'email':
    return {type: 'email', profile_id: channel.profile_id, recipients: channel.recipients.map(recipientDefinition)};
  case 's3':
    return {type: 's3', profile_id: channel.profile_id, object_name: channel.object_name.trim()};
  case 'webhook':
    return {type: 'webhook', url: channel.url.trim()};
  default:
    return {type: 'in_app', recipients: channel.recipients.map(recipientDefinition)};
  }
}

/** The request body for bi_alert_create / update / test. */
export function toDefinition(draft, {parameters = []} = {}) {
  const dashboard = draft.resource.type === 'dashboard';
  const values = parameterDefinition(draft.parameters, parameters);
  const definition = {
    kind: draft.kind, name: draft.name.trim(), resource: {...draft.resource},
    schedule: scheduleDefinition(draft.schedule), channels: draft.channels.map(channelDefinition),
    expires_in_days: draft.expiresInDays, ...(dashboard ? {filters: values} : {parameters: values}),
  };
  if(draft.pinnedRevision) definition.revision = draft.pinnedRevision;
  if(draft.kind === 'alert') {
    definition.condition = conditionDefinition(draft.condition);
    definition.fire_on = draft.fireOn;
  } else {
    definition.format = draft.format;
  }
  return definition;
}

// ---------------------------------------------------------------------------
// validation
// ---------------------------------------------------------------------------

/** What the form can check without asking the server, keyed by field. */
export function validateDraft(draft) {
  const errors = {};
  if(!draft.name.trim()) errors.name = gettext('Give it a name.');
  else if(draft.name.trim().length > MAX_NAME) errors.name = gettext('The name is too long.');
  if(!draft.resource.id) errors.resource = gettext('Save the question or dashboard first.');
  const fields = String(expressionFor(draft.schedule)).split(' ');
  if(fields.length !== 5) errors.schedule = gettext('Use a five-field cron expression.');
  if(!String(draft.schedule.timezone || '').trim()) errors.timezone = gettext('Choose a time zone.');

  if(draft.kind === 'alert') {
    const condition = draft.condition;
    if(condition.type === 'metric') {
      if(condition.metricKind === 'column' && !condition.column.trim()) errors.column = gettext('Choose a column.');
      if(number(condition.value) === null) errors.value = gettext('Enter a number.');
      if(condition.operator === 'between') {
        if(number(condition.high) === null) errors.high = gettext('Enter a number.');
        else if(number(condition.value) !== null && number(condition.value) > number(condition.high)) {
          errors.high = gettext('The upper bound must not be below the lower bound.');
        }
      }
    }
  }

  if(!draft.channels.length) errors.channels = gettext('Add at least one channel.');
  draft.channels.forEach((channel, index) => {
    const problem = channelProblem(channel);
    if(problem) errors[`channel.${index}`] = problem;
  });
  if(draft.kind === 'subscription' && !FORMATS.includes(draft.format) &&
    draft.channels.some((channel) => channel.type !== 'in_app')) {
    errors.format = gettext('Choose a format.');
  }
  return errors;
}

function channelProblem(channel) {
  switch(channel.type) {
  case 'email':
    if(!channel.profile_id) return gettext('Choose an email profile.');
    if(!channel.recipients.length) return gettext('Add a recipient.');
    return channel.recipients.some((entry) => entry.type === 'email' && !EMAIL.test(entry.address.trim())) ?
      gettext('An email address is invalid.') : '';
  case 's3':
    if(!channel.profile_id) return gettext('Choose a storage profile.');
    return OBJECT_BASE.test(channel.object_name.trim()) ? '' :
      gettext('Use letters, digits, dot, dash and underscore for the object name.');
  case 'webhook':
    return /^https:\/\/\S+$/i.test(channel.url.trim()) ? '' : gettext('Enter an https URL.');
  default:
    return channel.recipients.length ? '' : gettext('Add a recipient.');
  }
}

export const isValid = (draft) => Object.keys(validateDraft(draft)).length === 0;

/** Channels that leave pgAdmin: the server only admits them for the owner or a manager. */
export const isExternal = (channel) => channel.type !== 'in_app' &&
  !(channel.type === 'email' && channel.recipients.every((entry) => entry.type !== 'email'));

// ---------------------------------------------------------------------------
// descriptions, list rows and history
// ---------------------------------------------------------------------------

const AGAINST_TEXT = {
  previous_change: ' (change since the previous evaluation)',
  previous_percent: ' (percent change since the previous evaluation)',
};

/** Mirrors alert_models.describe_condition; returns an untranslated string. */
export function describeCondition(condition) {
  if(!condition) return '';
  if(condition.type === 'results') {
    return condition.state === 'exist' ? 'the question returns rows' : 'the question returns no rows';
  }
  const metric = condition.metric;
  const name = (metric.kind === 'row_count' ? 'row count' : `${metric.aggregate} of ${metric.column}`) +
    (AGAINST_TEXT[condition.against] || '');
  const shown = condition.operator === 'between' ? `${condition.value[0]} and ${condition.value[1]}` : condition.value;
  return `${name} ${condition.operator} ${shown}`;
}

/** The permissions of the alerts section for the resource's own access level. */
export function alertPermissions(resourceAccess, {scheduling = true} = {}) {
  const level = rank(resourceAccess || 'manage');
  return {
    canCreate: scheduling && level >= rank('view'),
    canExternal: level >= rank('manage'),
    scheduling,
  };
}

/** Which row actions one alert offers its viewer. */
export function rowActions(alert) {
  const owner = Boolean(alert.is_owner);
  const manager = owner || alert.access === 'manage';
  const active = alert.status === 'active';
  const alertKind = alert.kind === 'alert';
  return {
    edit: owner,
    test: owner,
    runNow: owner && active,
    mute: manager && active && !alert.muted,
    unmute: manager && alert.muted,
    rearm: owner && alertKind && active && alert.breach_state === 'breach',
    pause: manager && active,
    resume: owner && !active,
    remove: manager,
    history: true,
  };
}

export const kindText = (kind) => kind === 'alert' ? gettext('Alert') : kind === 'subscription' ? gettext('Subscription') : kind;

/** One-line state of an alert for the list: status, tone and the reason. */
export function statusLine(alert) {
  if(alert.status !== 'active') {
    return {tone: 'warning', label: gettext('Paused'), detail: alert.pause_text || ''};
  }
  if(alert.muted) return {tone: 'neutral', label: gettext('Muted'), detail: alert.muted_until || ''};
  if(alert.kind === 'alert' && alert.breach_state === 'breach') {
    return {tone: 'error', label: gettext('In breach'), detail: ''};
  }
  if(alert.kind === 'alert' && alert.breach_state === 'ok') return {tone: 'success', label: gettext('OK'), detail: ''};
  return {tone: 'info', label: gettext('Active'), detail: ''};
}

const OUTCOME_TONE = {
  delivered: 'success', breach: 'warning', ok: 'success', error: 'error', paused: 'warning',
};

/** The history label of an event outcome; an unknown outcome is shown as the server wrote it. */
export function outcomeLabel(outcome) {
  switch(outcome) {
  case 'breach': return gettext('Condition met');
  case 'ok': return gettext('Condition not met');
  case 'delivered': return gettext('Delivered');
  case 'error': return gettext('Failed');
  case 'paused': return gettext('Paused');
  default: return String(outcome || '');
  }
}

/** Table rows for the history of one alert. */
export function historyRows(events) {
  return (events || []).map((event) => ({
    key: event.event_id, at: event.created_at, trigger: event.trigger, outcome: event.outcome,
    label: outcomeLabel(event.outcome),
    tone: OUTCOME_TONE[event.outcome] || 'neutral', fired: Boolean(event.fired),
    suppressed: event.suppressed || '', value: valueText(event.value),
    problem: event.error_text || '', detail: event.error_detail || '',
    deliveries: (event.deliveries || []).map((item) => ({
      key: `${item.channel}:${item.target}`, channel: item.channel, target: item.target, state: item.state,
      code: item.code || '',
    })),
  }));
}

function valueText(value) {
  if(value === null || value === undefined) return '';
  if(typeof value !== 'object') return String(value);
  if(value.detail && value.value === null) return String(value.detail);
  if(value.value !== undefined && value.value !== null) return String(value.value);
  if(value.items !== undefined) return `${value.items} items`;
  return '';
}

// ---------------------------------------------------------------------------
// dry run
// ---------------------------------------------------------------------------

/** What the test-evaluate button shows: the verdict and the message, never sent. */
export function testViewModel(report) {
  if(!report) return null;
  const deliveries = (report.deliveries || []).map((item) => ({
    key: `${item.channel}:${item.target}`, channel: item.channel, target: item.target, state: item.state,
    code: item.code || '',
  }));
  if(report.outcome) {
    const outcome = report.outcome;
    return {
      kind: 'alert', verdict: outcome.label, breached: outcome.breached, condition: outcome.condition,
      value: outcome.value, previous: outcome.previous, change: outcome.change, detail: outcome.detail,
      rowCount: report.row_count, truncated: Boolean(report.truncated),
      wouldFire: Boolean(report.would_fire), reason: report.reason || '', suppressed: report.suppressed || '',
      stateAfter: report.breach_state_after, message: report.message, preview: report.message?.preview || null,
      deliveries,
    };
  }
  return {
    kind: 'subscription', verdict: 'snapshot', wouldFire: Boolean(report.fire), message: report.message,
    items: (report.items || []).map((item, index) => ({
      key: `${item.title || index}`, title: item.title, status: item.status, rowCount: item.row_count,
      code: item.code || '',
    })),
    attachments: report.attachments || [], deliveries,
  };
}

// ---------------------------------------------------------------------------
// the section (list + history + notices)
// ---------------------------------------------------------------------------

export const initialPanel = () => ({
  status: 'loading', error: '', items: [], busy: '', notice: '', openId: '',
  history: {status: 'idle', items: [], error: ''},
});

export function panelReducer(state, action) {
  switch(action.type) {
  case 'loading':
    return {...state, status: 'loading', error: ''};
  case 'loaded':
    return {...state, status: 'ready', error: '', busy: '', items: action.items};
  case 'failed':
    return {...state, status: state.items.length ? 'ready' : 'error', busy: '', error: action.error};
  case 'busy':
    return {...state, busy: action.key, error: '', notice: ''};
  case 'notice':
    return {...state, busy: '', notice: action.text};
  case 'dismiss':
    return {...state, error: '', notice: ''};
  case 'openHistory':
    return {...state, openId: action.id, history: {status: 'loading', items: [], error: ''}};
  case 'closeHistory':
    return {...state, openId: '', history: {status: 'idle', items: [], error: ''}};
  case 'historyLoaded':
    return state.openId !== action.id ? state :
      {...state, history: {status: 'ready', items: action.items, error: ''}};
  case 'historyFailed':
    return state.openId !== action.id ? state :
      {...state, history: {status: 'error', items: [], error: action.error}};
  default:
    return state;
  }
}

/** The mute choices, as minutes with a label key the view translates. */
export const muteLabel = (minutes) => {
  if(minutes % 1440 === 0) return {unit: 'days', count: minutes / 1440};
  return {unit: 'hours', count: minutes / 60};
};
