/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useReducer, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Box, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {Badge, Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import AlertDialog from './AlertDialog';
import AlertHistory from './AlertHistory';
import AlertTestResult from './AlertTestResult';
import {
  MUTE_MINUTES, alertPermissions, describeCondition, draftFromAlert, initialPanel, kindText, muteLabel,
  newDraft, panelReducer, rowActions, statusLine, testViewModel,
} from './alerts';

const message = (error) => error?.message || String(error);
const when = (value) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
};
const muteText = (minutes) => {
  const {unit, count} = muteLabel(minutes);
  return unit === 'days' ? gettext('Mute for %s days', count) : gettext('Mute for %s hours', count);
};

function localZone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch { return 'UTC'; }
}

function AlertRow({item, busy, actions, onAct, onEdit, onHistory, historyOpen}) {
  const status = statusLine(item);
  const act = (key, work) => onAct(`${key}-${item.alert_id}`, work);
  return <Box component="li" aria-label={item.name}
    sx={{display: 'grid', gap: 0.5, py: 0.75, borderBottom: '1px solid', borderColor: 'divider'}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
      <Box sx={{flex: 1, minWidth: 160}}><strong>{item.name}</strong></Box>
      <Badge status="neutral" label={kindText(item.kind)} />
      <Badge status={status.tone} label={status.label} />
      {item.muted_until && <Box sx={{fontSize: '0.7rem'}}>{gettext('until %s', when(item.muted_until))}</Box>}
    </Stack>
    <Box sx={{fontSize: '0.75rem', color: 'text.secondary'}}>
      {item.kind === 'alert' && item.definition?.condition ? describeCondition(item.definition.condition) :
        gettext('Snapshot as %s', String(item.definition?.format || '').toUpperCase() || gettext('a notification'))}
      {' · '}{item.definition?.schedule?.expression}{' '}({item.definition?.schedule?.timezone})
      {item.last_evaluated_at && ` · ${gettext('last checked %s', when(item.last_evaluated_at))}`}
      {item.next_runs?.[0] && ` · ${gettext('next %s', when(item.next_runs[0]))}`}
    </Box>
    {status.detail && item.status !== 'active' && <Banner status="warning">{status.detail}</Banner>}
    {!item.is_owner && <Box sx={{fontSize: '0.7rem', color: 'text.secondary'}}>
      {gettext('Owned by someone else. You can %s.', item.access === 'manage' ? gettext('mute, pause or delete it') :
        gettext('see its history'))}</Box>}
    <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap'}}>
      {actions.edit && <Button size="small" disabled={busy} aria-label={gettext('Edit %s', item.name)}
        onClick={() => onEdit(item)}>{gettext('Edit')}</Button>}
      {actions.test && <Button size="small" disabled={busy} aria-label={gettext('Test %s', item.name)}
        onClick={() => act('test', (client) => client.testAlert(item.alert_id))}>{gettext('Test evaluate')}</Button>}
      {actions.runNow && <Button size="small" disabled={busy} aria-label={gettext('Run %s now', item.name)}
        onClick={() => act('run', (client) => client.runAlertNow(item.alert_id))}>{gettext('Run now')}</Button>}
      {actions.mute && MUTE_MINUTES.slice(0, 3).map((minutes) => <Button size="small" key={minutes} disabled={busy}
        aria-label={`${muteText(minutes)}: ${item.name}`}
        onClick={() => act('mute', (client) => client.muteAlert(item.alert_id, minutes))}>
        {muteText(minutes)}</Button>)}
      {actions.unmute && <Button size="small" disabled={busy} aria-label={gettext('Unmute %s', item.name)}
        onClick={() => act('unmute', (client) => client.unmuteAlert(item.alert_id))}>{gettext('Unmute')}</Button>}
      {actions.rearm && <Button size="small" disabled={busy} aria-label={gettext('Re-arm %s', item.name)}
        onClick={() => act('rearm', (client) => client.rearmAlert(item.alert_id))}>{gettext('Re-arm')}</Button>}
      {actions.pause && <Button size="small" disabled={busy} aria-label={gettext('Pause %s', item.name)}
        onClick={() => act('pause', (client) => client.pauseAlert(item.alert_id))}>{gettext('Pause')}</Button>}
      {actions.resume && <Button size="small" disabled={busy} aria-label={gettext('Resume %s', item.name)}
        onClick={() => act('resume', (client) => client.resumeAlert(item.alert_id))}>{gettext('Resume')}</Button>}
      <Button size="small" aria-pressed={historyOpen} aria-label={gettext('History of %s', item.name)}
        onClick={() => onHistory(item)}>{historyOpen ? gettext('Hide history') : gettext('History')}</Button>
      {actions.remove && <Button size="small" intent="destructive" disabled={busy}
        aria-label={gettext('Delete %s', item.name)}
        onClick={() => act('delete', (client) => client.deleteAlert(item.alert_id))}>{gettext('Delete')}</Button>}
    </Stack>
  </Box>;
}

AlertRow.propTypes = {
  item: PropTypes.object.isRequired, busy: PropTypes.bool, actions: PropTypes.object.isRequired,
  onAct: PropTypes.func.isRequired, onEdit: PropTypes.func.isRequired, onHistory: PropTypes.func.isRequired,
  historyOpen: PropTypes.bool,
};

/**
 * Alerts and subscriptions of one saved question or dashboard. Questions
 * offer both; dashboards offer subscriptions. The list shows only what the
 * caller may see; the server decides every action again.
 */
export default function AlertsPanel({
  client, resourceType, resourceId, resourceName, access = 'manage', columns = [], parameters = [],
  seedValues = {}, onClose,
}) {
  const [state, dispatch] = useReducer(panelReducer, undefined, initialPanel);
  const [catalog, setCatalog] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [result, setResult] = useState(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const load = useCallback(async () => {
    try {
      const items = await client.listAlerts(resourceType, resourceId);
      if(alive.current) dispatch({type: 'loaded', items});
    } catch(error) {
      if(alive.current) dispatch({type: 'failed', error: message(error)});
    }
  }, [client, resourceType, resourceId]);
  useEffect(() => {
    dispatch({type: 'loading'});
    load();
    client.alertCatalog().then(
      (value) => { if(alive.current) setCatalog(value); },
      (error) => { if(alive.current) dispatch({type: 'failed', error: message(error)}); });
  }, [client, load]);

  const permissions = alertPermissions(access, {scheduling: catalog ? catalog.scheduling : true});

  const act = async (key, work) => {
    dispatch({type: 'busy', key});
    setResult(null);
    try {
      const outcome = await work(client);
      if(!alive.current) return;
      if(key.startsWith('test-')) {
        setResult(testViewModel(outcome));
        dispatch({type: 'notice', text: ''});
      } else if(key.startsWith('run-')) {
        dispatch({type: 'notice', text: gettext('The check ran. See the history for the result.')});
      } else {
        dispatch({type: 'notice', text: ''});
      }
      await load();
    } catch(error) {
      if(alive.current) dispatch({type: 'failed', error: message(error)});
    }
  };

  const openHistory = async (item) => {
    if(state.openId === item.alert_id) { dispatch({type: 'closeHistory'}); return; }
    dispatch({type: 'openHistory', id: item.alert_id});
    try {
      const items = await client.alertHistory(item.alert_id);
      if(alive.current) dispatch({type: 'historyLoaded', id: item.alert_id, items});
    } catch(error) {
      if(alive.current) dispatch({type: 'historyFailed', id: item.alert_id, error: message(error)});
    }
  };

  const create = (kind) => setDialog({initial: newDraft({
    kind, resourceType, resourceId, resourceName: kind === 'alert' ? gettext('Alert on %s', resourceName) :
      gettext('Snapshot of %s', resourceName),
    timezone: localZone(), parameters: seedValues})});
  const edit = (item) => setDialog({initial: draftFromAlert(item)});

  const closeDialog = (outcome) => {
    setDialog(null);
    if(outcome?.saved) {
      dispatch({type: 'notice', text: gettext('Saved.')});
      load();
    }
  };

  const busy = state.busy !== '';
  const alertsAllowed = resourceType === 'question';

  return <Box component="section" aria-label={gettext('Alerts and subscriptions')} data-cdeadmin-qa-key="bi.alerts"
    sx={{display: 'grid', gap: 1, border: '1px solid', borderColor: 'divider', p: 1}}>
    <Stack direction="row" gap="compact" sx={{alignItems: 'center', flexWrap: 'wrap'}}>
      <Box component="h3" sx={{m: 0, fontSize: '0.9375rem', flex: 1}}>{gettext('Alerts and subscriptions')}</Box>
      {alertsAllowed && <Button disabled={!catalog || !permissions.canCreate} onClick={() => create('alert')}>
        {gettext('New alert')}</Button>}
      <Button disabled={!catalog || !permissions.canCreate} onClick={() => create('subscription')}>
        {gettext('New subscription')}</Button>
      {onClose && <Button onClick={onClose}>{gettext('Close')}</Button>}
    </Stack>
    {state.error && <Banner status="error" onClose={() => dispatch({type: 'dismiss'})}>{state.error}</Banner>}
    {state.notice && <Banner status="info" onClose={() => dispatch({type: 'dismiss'})}>{state.notice}</Banner>}
    {state.status === 'loading' && <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Loading...')}</Box>}
    {state.status === 'ready' && state.items.length === 0 && <EmptyState message={alertsAllowed ?
      gettext('No alerts or subscriptions yet.') : gettext('No subscriptions yet.')} />}
    {state.items.length > 0 && <Box component="ul" aria-label={gettext('Alerts and subscriptions list')}
      sx={{m: 0, p: 0, listStyle: 'none'}}>
      {state.items.map((item) => <Box key={item.alert_id} sx={{display: 'contents'}}>
        <AlertRow item={item} busy={busy} actions={rowActions(item)} onAct={act} onEdit={edit}
          onHistory={openHistory} historyOpen={state.openId === item.alert_id} />
        {state.openId === item.alert_id && <Box component="li" sx={{listStyle: 'none', pb: 1}}>
          <AlertHistory history={state.history} /></Box>}
      </Box>)}
    </Box>}
    <AlertTestResult view={result} />
    {dialog && catalog && <AlertDialog client={client} catalog={catalog} initial={dialog.initial}
      parameters={parameters} columns={columns} canExternal={permissions.canExternal}
      onClose={closeDialog} />}
  </Box>;
}

AlertsPanel.propTypes = {
  client: PropTypes.object.isRequired,
  resourceType: PropTypes.oneOf(['question', 'dashboard']).isRequired,
  resourceId: PropTypes.string.isRequired,
  resourceName: PropTypes.string.isRequired,
  access: PropTypes.string,
  columns: PropTypes.array,
  parameters: PropTypes.array,
  seedValues: PropTypes.object,
  onClose: PropTypes.func,
};
