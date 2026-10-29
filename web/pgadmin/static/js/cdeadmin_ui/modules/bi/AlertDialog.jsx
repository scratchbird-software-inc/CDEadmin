/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect, useReducer, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextField} from '../../primitives/Field';
import {Select} from '../../primitives/Choice';
import {Dialog} from '../../overlays/Dialog';
import {Badge, Banner} from '../../feedback/Indicators';
import AlertTestResult from './AlertTestResult';
import {
  AGAINST, AGGREGATES, FORMATS, OPERATORS, PRESETS, WEEKDAYS, draftReducer, expressionFor, isExternal,
  scheduleDefinition, testViewModel, toDefinition, validateDraft,
} from './alerts';

const SEARCH_DELAY = 200;
const message = (error) => error?.message || String(error);

const options = (values, labels) => values.map((value) => ({value, label: labels[value]()}));

const OPERATOR_LABELS = {
  '>': () => gettext('is greater than'), '>=': () => gettext('is at least'),
  '<': () => gettext('is less than'), '<=': () => gettext('is at most'),
  '==': () => gettext('equals'), '!=': () => gettext('does not equal'),
  'between': () => gettext('is between'),
};
const AGGREGATE_LABELS = {
  first: () => gettext('First value'), sum: () => gettext('Sum'), avg: () => gettext('Average'),
  min: () => gettext('Minimum'), max: () => gettext('Maximum'),
};
const AGAINST_LABELS = {
  constant: () => gettext('a fixed number'), previous_change: () => gettext('the change since the last check'),
  previous_percent: () => gettext('the percent change since the last check'),
};
const PRESET_LABELS = {
  hourly: () => gettext('Every hour'), daily: () => gettext('Every day'), weekdays: () => gettext('Weekdays'),
  weekly: () => gettext('Every week'), custom: () => gettext('Custom cron expression'),
};
const WEEKDAY_LABELS = [
  () => gettext('Sunday'), () => gettext('Monday'), () => gettext('Tuesday'), () => gettext('Wednesday'),
  () => gettext('Thursday'), () => gettext('Friday'), () => gettext('Saturday'),
];
const FORMAT_LABELS = {csv: () => 'CSV', xlsx: () => 'XLSX', pdf: () => 'PDF', svg: () => 'SVG'};
const CHANNEL_LABELS = {
  in_app: () => gettext('In-app notification'), email: () => gettext('Email'),
  s3: () => gettext('Object storage'), webhook: () => gettext('Signed webhook'),
};

function Section({title, children}) {
  return <Box component="section" aria-label={title} sx={{display: 'grid', gap: 0.75}}>
    <Box component="h4" sx={{m: 0, fontSize: '0.8125rem'}}>{title}</Box>
    {children}
  </Box>;
}

Section.propTypes = {title: PropTypes.string.isRequired, children: PropTypes.node};

function ConditionFields({condition, columns, dispatch, errors}) {
  const patch = (value) => dispatch({type: 'condition', patch: value});
  const column = condition.metricKind === 'column';
  const columnOptions = [{value: '', label: gettext('Choose a column')},
    ...columns.map((name) => ({value: name, label: name}))];
  return <Section title={gettext('Condition')}>
    <Select size="small" label={gettext('Notify when')} value={condition.type}
      options={[{value: 'metric', label: gettext('a measured value meets a threshold')},
        {value: 'results', label: gettext('the result has or lacks rows')}]}
      onChange={(type) => patch({type})} />
    {condition.type === 'results' ? <Select size="small" label={gettext('The result')} value={condition.state}
      options={[{value: 'exist', label: gettext('has rows')}, {value: 'empty', label: gettext('is empty')}]}
      onChange={(state) => patch({state})} /> : <>
      <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap', alignItems: 'flex-start'}}>
        <Select size="small" label={gettext('Measure')} value={condition.metricKind}
          options={[{value: 'row_count', label: gettext('Number of rows')},
            {value: 'column', label: gettext('A column')}]}
          onChange={(metricKind) => patch({metricKind})} sx={{minWidth: 160}} />
        {column && <>
          <Select size="small" label={gettext('Aggregate')} value={condition.aggregate}
            options={options(AGGREGATES, AGGREGATE_LABELS)} onChange={(aggregate) => patch({aggregate})}
            sx={{minWidth: 140}} />
          <Select size="small" label={gettext('Column')} value={condition.column} options={columnOptions}
            validationMessage={errors.column} onChange={(value) => patch({column: value})} sx={{minWidth: 160}} />
        </>}
      </Stack>
      <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap', alignItems: 'flex-start'}}>
        <Select size="small" label={gettext('Compare')} value={condition.against}
          options={options(AGAINST, AGAINST_LABELS)} onChange={(against) => patch({against})}
          sx={{minWidth: 200}} />
        <Select size="small" label={gettext('Operator')} value={condition.operator}
          options={options(OPERATORS, OPERATOR_LABELS)} onChange={(operator) => patch({operator})}
          sx={{minWidth: 150}} />
        <TextField size="small" label={condition.operator === 'between' ? gettext('From') : gettext('Value')}
          value={condition.value} validationMessage={errors.value} sx={{width: 120}}
          onChange={(event) => patch({value: event.target.value})} />
        {condition.operator === 'between' && <TextField size="small" label={gettext('To')}
          value={condition.high} validationMessage={errors.high} sx={{width: 120}}
          onChange={(event) => patch({high: event.target.value})} />}
      </Stack>
    </>}
  </Section>;
}

ConditionFields.propTypes = {
  condition: PropTypes.object.isRequired, columns: PropTypes.array.isRequired,
  dispatch: PropTypes.func.isRequired, errors: PropTypes.object.isRequired,
};

function ScheduleFields({schedule, dispatch, errors, preview}) {
  const patch = (value) => dispatch({type: 'schedule', patch: value});
  const numeric = (key, low, high) => (event) => {
    const value = Number.parseInt(event.target.value, 10);
    patch({[key]: Number.isInteger(value) ? Math.min(high, Math.max(low, value)) : low});
  };
  return <Section title={gettext('Schedule')}>
    <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap', alignItems: 'flex-start'}}>
      <Select size="small" label={gettext('Repeat')} value={schedule.preset}
        options={options(PRESETS, PRESET_LABELS)} onChange={(preset) => patch({preset})} sx={{minWidth: 200}} />
      {schedule.preset === 'weekly' && <Select size="small" label={gettext('On')} value={String(schedule.weekday)}
        options={WEEKDAYS.map((day) => ({value: String(day), label: WEEKDAY_LABELS[day]()}))}
        onChange={(day) => patch({weekday: Number(day)})} sx={{minWidth: 140}} />}
      {['daily', 'weekdays', 'weekly'].includes(schedule.preset) && <TextField size="small" type="number"
        label={gettext('Hour')} value={schedule.hour} onChange={numeric('hour', 0, 23)} sx={{width: 90}} />}
      {schedule.preset !== 'custom' && <TextField size="small" type="number" label={gettext('Minute')}
        value={schedule.minute} onChange={numeric('minute', 0, 59)} sx={{width: 90}} />}
      {schedule.preset === 'custom' && <TextField size="small" label={gettext('Cron expression')}
        value={schedule.custom} validationMessage={errors.schedule}
        onChange={(event) => patch({custom: event.target.value})} sx={{minWidth: 200}} />}
      <TextField size="small" label={gettext('Time zone')} value={schedule.timezone} validationMessage={errors.timezone}
        onChange={(event) => patch({timezone: event.target.value})} sx={{minWidth: 180}} />
    </Stack>
    <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {gettext('Runs on %s (%s).', expressionFor(schedule), schedule.timezone)}
    </Box>
    {preview.status === 'error' && <Banner status="warning">{preview.error}</Banner>}
    {preview.status === 'ready' && <Box component="ol" aria-label={gettext('Next runs')}
      sx={{m: 0, pl: 2.5, fontSize: '0.75rem'}}>
      {preview.runs.map((instant, index) => <li key={`${index}-${instant}`}>{new Date(instant).toLocaleString()}</li>)}
    </Box>}
    {preview.interval !== null && preview.minInterval > 0 && preview.interval < preview.minInterval &&
      <Banner status="warning">
        {gettext('This runs more often than the server allows (every %s seconds at most).', preview.minInterval)}
      </Banner>}
  </Section>;
}

ScheduleFields.propTypes = {
  schedule: PropTypes.object.isRequired, dispatch: PropTypes.func.isRequired, errors: PropTypes.object.isRequired,
  preview: PropTypes.object.isRequired,
};

function RecipientPicker({client, onPick, allowEmail, label}) {
  const [text, setText] = useState('');
  const [found, setFound] = useState([]);
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      client.searchPrincipals(text, {kinds: ['user'], limit: 10}).then(
        (results) => { if(!cancelled) setFound(results); },
        () => { if(!cancelled) setFound([]); });
    }, SEARCH_DELAY);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [client, text]);
  const looksLikeEmail = allowEmail && text.includes('@');
  return <Box sx={{display: 'grid', gap: 0.5}}>
    <TextField size="small" label={label} value={text} onChange={(event) => setText(event.target.value)} />
    {looksLikeEmail && <Stack direction="row"><Button size="small"
      aria-label={gettext('Add address %s', text.trim())}
      onClick={() => { onPick({type: 'email', address: text.trim()}); setText(''); }}>
      {gettext('Add %s', text.trim())}</Button></Stack>}
    {found.length > 0 && <Box component="ul" aria-label={gettext('Matching users')}
      sx={{m: 0, p: 0, listStyle: 'none', maxHeight: 120, overflow: 'auto', border: '1px solid', borderColor: 'divider'}}>
      {found.filter((item) => item.type === 'user').map((item) => <li key={item.id}>
        <Button size="small" aria-label={gettext('Choose user %s', item.name)}
          onClick={() => { onPick({type: 'user', user_id: item.id, name: item.name}); setText(''); }}>
          {item.name}</Button>
      </li>)}
    </Box>}
  </Box>;
}

RecipientPicker.propTypes = {
  client: PropTypes.object.isRequired, onPick: PropTypes.func.isRequired, allowEmail: PropTypes.bool,
  label: PropTypes.string.isRequired,
};

const recipientLabel = (entry) => entry.type === 'email' ? entry.address :
  entry.type === 'self' ? gettext('You') : (entry.name || gettext('User %s', entry.user_id));

function ChannelCard({client, channel, index, catalog, canExternal, dispatch, problem}) {
  const patch = (value) => dispatch({type: 'channel', index, patch: value});
  const profiles = channel.type === 'email' ? catalog.channels.email : catalog.channels.s3;
  const hosts = catalog.channels.webhook;
  const emailAllowed = canExternal && catalog.external_recipients;
  return <Box role="group" aria-label={gettext('Channel %s', index + 1)}
    sx={{display: 'grid', gap: 0.75, border: '1px solid', borderColor: 'divider', p: 1}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center'}}>
      <Badge status="info" label={CHANNEL_LABELS[channel.type]()} />
      <Box sx={{flex: 1}} />
      <Button size="small" intent="destructive" aria-label={gettext('Remove channel %s', index + 1)}
        onClick={() => dispatch({type: 'removeChannel', index})}>{gettext('Remove')}</Button>
    </Stack>
    {(channel.type === 'email' || channel.type === 's3') && <Select size="small"
      label={channel.type === 'email' ? gettext('Mail profile') : gettext('Storage profile')}
      value={channel.profile_id}
      options={[{value: '', label: gettext('Choose a profile')},
        ...profiles.map((item) => ({value: item.profile_id, label: item.label || item.profile_id}))]}
      onChange={(value) => patch({profile_id: value})} />}
    {channel.type === 's3' && <TextField size="small" label={gettext('Object name')} value={channel.object_name}
      onChange={(event) => patch({object_name: event.target.value})} />}
    {channel.type === 'webhook' && <>
      <TextField size="small" label={gettext('Webhook URL')} value={channel.url} placeholder="https://"
        onChange={(event) => patch({url: event.target.value})} />
      <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
        {hosts.length ? gettext('Allowed hosts: %s', hosts.map((item) => item.host).join(', ')) :
          gettext('No webhook hosts are allowed on this server.')}
      </Box>
    </>}
    {(channel.type === 'in_app' || channel.type === 'email') && <>
      <Box component="ul" aria-label={gettext('Recipients')} sx={{m: 0, p: 0, listStyle: 'none', display: 'flex',
        gap: 0.5, flexWrap: 'wrap'}}>
        {channel.recipients.map((entry, at) => <li key={`${entry.type}-${entry.user_id ?? entry.address ?? at}`}>
          <Button size="small" aria-label={gettext('Remove recipient %s', recipientLabel(entry))}
            onClick={() => dispatch({type: 'removeRecipient', index, at})}>
            {recipientLabel(entry)} {'×'}</Button>
        </li>)}
      </Box>
      <RecipientPicker client={client} label={channel.type === 'email' && emailAllowed ?
        gettext('Add a user or type an email address') : gettext('Add a user')}
      allowEmail={channel.type === 'email' && emailAllowed}
      onPick={(recipient) => dispatch({type: 'addRecipient', index, recipient})} />
    </>}
    {problem && <Banner status="warning">{problem}</Banner>}
  </Box>;
}

ChannelCard.propTypes = {
  client: PropTypes.object.isRequired, channel: PropTypes.object.isRequired, index: PropTypes.number.isRequired,
  catalog: PropTypes.object.isRequired, canExternal: PropTypes.bool, dispatch: PropTypes.func.isRequired,
  problem: PropTypes.string,
};

function ChannelFields({client, draft, catalog, canExternal, dispatch, errors}) {
  const choices = ['in_app', ...(canExternal ? ['email', 's3', 'webhook'] : ['email'])];
  const [adding, setAdding] = useState('in_app');
  return <Section title={gettext('Deliver to')}>
    {draft.channels.map((channel, index) => <ChannelCard key={index} client={client} channel={channel}
      index={index} catalog={catalog} canExternal={canExternal} dispatch={dispatch}
      problem={errors[`channel.${index}`]} />)}
    {errors.channels && <Banner status="warning">{errors.channels}</Banner>}
    <Stack direction="row" gap="compact" sx={{alignItems: 'flex-end'}}>
      <Select size="small" label={gettext('Add a channel')} value={adding}
        options={choices.map((value) => ({value, label: CHANNEL_LABELS[value]()}))}
        onChange={setAdding} sx={{minWidth: 200}} />
      <Button onClick={() => dispatch({type: 'addChannel', channel: adding})}>{gettext('Add channel')}</Button>
    </Stack>
    {!canExternal && <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {gettext('Email to other pgAdmin users and in-app notifications are available to you. ' +
        'Email to outside addresses, object storage and webhooks need manage access.')}</Box>}
    {draft.channels.some(isExternal) && <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {gettext('A message never carries more than %s rows. Redacted columns and the export policy still apply.',
        catalog.limits.max_message_rows)}</Box>}
  </Section>;
}

ChannelFields.propTypes = {
  client: PropTypes.object.isRequired, draft: PropTypes.object.isRequired, catalog: PropTypes.object.isRequired,
  canExternal: PropTypes.bool, dispatch: PropTypes.func.isRequired, errors: PropTypes.object.isRequired,
};

/** Debounced next-run preview from the server's own cron evaluation. */
function useSchedulePreview(client, schedule, minInterval) {
  const [preview, setPreview] = useState({status: 'idle', runs: [], error: '', interval: null, minInterval});
  const expression = scheduleDefinition(schedule);
  const key = `${expression.expression}|${expression.timezone}`;
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      client.schedulePreview(scheduleDefinition(schedule), 5).then(
        (result) => { if(!cancelled) setPreview({status: 'ready', runs: result.next_runs, error: '',
          interval: result.interval_seconds, minInterval}); },
        (error) => { if(!cancelled) setPreview({status: 'error', runs: [], error: message(error),
          interval: null, minInterval}); });
    }, SEARCH_DELAY);
    return () => { cancelled = true; clearTimeout(timer); };
    // key stands for the schedule's value, so the schedule object itself is not a dependency
  }, [client, key, minInterval]);
  return preview;
}

/**
 * Create or edit one alert (on a question) or subscription (of a question or
 * dashboard). Test evaluate runs the definition once with your own session and
 * shows the verdict and the message; nothing is sent and nothing is saved.
 */
export default function AlertDialog({
  client, catalog, initial, parameters = [], columns = [], canExternal, onClose,
}) {
  const [draft, dispatch] = useReducer(draftReducer, initial);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [test, setTest] = useState(null);
  const editing = draft.alertId !== null;
  const errors = validateDraft(draft);
  const valid = Object.keys(errors).length === 0;
  const preview = useSchedulePreview(client, draft.schedule, catalog.limits.min_interval_seconds);
  const definition = () => toDefinition(draft, {parameters});
  const alert = draft.kind === 'alert';

  const attempt = async (key, work) => {
    setBusy(key);
    setError('');
    try { await work(); } catch(caught) { setError(message(caught)); } finally { setBusy(''); }
  };
  const runTest = () => attempt('test', async () => {
    // an edited stored alert is tested as the definition now in the form
    setTest(testViewModel(await client.testAlert(null, definition())));
  });
  const save = () => attempt('save', async () => {
    const saved = editing ? await client.updateAlert(draft.alertId, draft.revision, definition()) :
      await client.createAlert(definition());
    onClose({saved});
  });

  const titleText = editing ? (alert ? gettext('Edit alert') : gettext('Edit subscription')) :
    (alert ? gettext('New alert') : gettext('New subscription'));

  return <Dialog open title={titleText} size="large" busy={busy !== ''} onClose={() => onClose({})}
    actions={<>
      <Button onClick={() => onClose({})}>{gettext('Cancel')}</Button>
      <Button disabled={!valid} loading={busy === 'test'} onClick={runTest}>{gettext('Test evaluate')}</Button>
      <Button intent="primary" disabled={!valid} loading={busy === 'save'} onClick={save}>
        {editing ? gettext('Save changes') : gettext('Create')}</Button>
    </>}>
    <Box data-cdeadmin-qa-key="bi.alert-form" sx={{display: 'grid', gap: 1.5}}>
      {!catalog.scheduling && <Banner status="warning">
        {gettext('Unattended scheduling is not configured on this server, so this cannot run on its own. ' +
          'You can still test it.')}</Banner>}
      <Banner status="info">
        {gettext('It runs with your own access, using credentials you delegate for a limited time. ' +
          'If you lose access to this content it pauses and says why.')}
      </Banner>
      {error && <Banner status="error" onClose={() => setError('')}>{error}</Banner>}
      <TextField size="small" label={gettext('Name')} value={draft.name} validationMessage={errors.name}
        onChange={(event) => dispatch({type: 'name', name: event.target.value})} />
      {alert && <ConditionFields condition={draft.condition} columns={columns} dispatch={dispatch}
        errors={errors} />}
      {alert && <Select size="small" label={gettext('How often to notify')} value={draft.fireOn}
        options={[{value: 'transition', label: gettext('When it first breaches, and again after it recovers')},
          {value: 'every_evaluation', label: gettext('Every check while it is in breach')}]}
        onChange={(fireOn) => dispatch({type: 'fireOn', fireOn})} />}
      {!alert && <Select size="small" label={gettext('Format')} value={draft.format}
        options={options(FORMATS, FORMAT_LABELS)} validationMessage={errors.format}
        onChange={(format) => dispatch({type: 'format', format})} sx={{maxWidth: 200}} />}
      {parameters.length > 0 && <Section title={draft.resource.type === 'dashboard' ? gettext('Filter values') :
        gettext('Parameter values')}>
        <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap'}}>
          {parameters.map((item) => <TextField key={item.id} size="small" label={item.name || item.id}
            value={draft.parameters[item.id] ?? ''} sx={{minWidth: 160}}
            onChange={(event) => dispatch({type: 'parameter', id: item.id, text: event.target.value})} />)}
        </Stack>
      </Section>}
      <ScheduleFields schedule={draft.schedule} dispatch={dispatch} errors={errors} preview={preview} />
      <ChannelFields client={client} draft={draft} catalog={catalog} canExternal={canExternal}
        dispatch={dispatch} errors={errors} />
      <Select size="small" label={gettext('Delegation lasts')} value={String(draft.expiresInDays)}
        options={[7, 30, 90, 365].map((days) => ({value: String(days), label: gettext('%s days', days)}))}
        onChange={(days) => dispatch({type: 'expires', days: Number(days)})} sx={{maxWidth: 200}} />
      <AlertTestResult view={test} />
    </Box>
  </Dialog>;
}

AlertDialog.propTypes = {
  client: PropTypes.object.isRequired,
  catalog: PropTypes.object.isRequired,
  initial: PropTypes.object.isRequired,
  parameters: PropTypes.array,
  columns: PropTypes.array,
  canExternal: PropTypes.bool,
  onClose: PropTypes.func.isRequired,
};
