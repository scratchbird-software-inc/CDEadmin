/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useCallback, useEffect, useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import getApiInstance from 'sources/api_instance';
import {Box, Grid, Stack} from '../../primitives/Layout';
import {Button} from '../../primitives/Button';
import {TextArea, TextField} from '../../primitives/Field';
import {Badge, Banner, ValidationMessage} from '../../feedback/Indicators';
import FormReference from '../../navigation/FormReference';
import CodeEditor from '../../editors/CodeEditor';
import {PostgresqlSectionCard, createPostgresqlServerCaller} from './postgresqlAdminHelpers';

/**
 * PG-UI-11 (SR-F-030541): PostgreSQL Asynchronous LISTEN / NOTIFY Pub-Sub Channel Workspace.
 */
export default function PostgresqlListenNotifyWorkspace({
  endpointUrl,
  api: injectedApi = null,
}) {
  const api = useMemo(() => injectedApi || getApiInstance(), [injectedApi]);
  const callServer = useMemo(
    () => createPostgresqlServerCaller(api, endpointUrl),
    [api, endpointUrl]
  );

  const [channelInput, setChannelInput] = useState('sr_events');
  const [notifyChannel, setNotifyChannel] = useState('sr_events');
  const [notifyPayload, setNotifyPayload] = useState('');
  const [state, setState] = useState({subscribed_channels: [], backend_pid: null, notifications: []});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const pollNotifications = useCallback(async () => {
    try {
      const res = await callServer({action: 'postgresql_ops_pubsub_poll', request: {}});
      setState(res || {subscribed_channels: [], backend_pid: null, notifications: []});
    } catch (err) {
      setError(err?.message || String(err));
    }
  }, [callServer]);

  useEffect(() => {
    pollNotifications();
  }, [pollNotifications]);

  const handleSubscribe = async () => {
    if (!channelInput.trim()) return;
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_ops_pubsub_subscribe',
        request: {channel: channelInput.trim()},
      });
      setState(res);
      setNotifyChannel(channelInput.trim());
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleUnsubscribe = async (ch = null) => {
    setBusy(true);
    setError('');
    try {
      const res = await callServer({
        action: 'postgresql_ops_pubsub_unsubscribe',
        request: ch ? {channel: ch} : {},
      });
      setState(res);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleSendNotify = async () => {
    if (!notifyChannel.trim()) return;
    setBusy(true);
    setError('');
    try {
      await callServer({
        action: 'postgresql_ops_pubsub_notify',
        request: {channel: notifyChannel.trim(), payload: notifyPayload},
      });
      await pollNotifications();
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const channels = state.subscribed_channels || [];
  const notifications = state.notifications || [];

  return (
    <Stack gap="md">
      <PostgresqlSectionCard
        title={gettext('Asynchronous LISTEN / NOTIFY Channel Subscriber')}
        actions={<FormReference reference="SR-F-030541" />}
      >
        <Stack gap="sm">
          <Banner status="info">
            {gettext(
              'Subscribes a dedicated autocommit PostgreSQL listener connection via LISTEN <channel> and captures live pg_notify() payloads with sender PIDs.'
            )}
          </Banner>
          {error && <ValidationMessage status="error">{error}</ValidationMessage>}
          <Grid columns={2} gap="sm">
            <TextField
              label={gettext('Channel Identifier')}
              value={channelInput}
              onChange={(e) => setChannelInput(e?.target ? e.target.value : e)}
            />
            <Stack direction="row" gap="sm">
              <Button variant="primary" disabled={busy || !channelInput.trim()} onClick={handleSubscribe}>
                {gettext('Subscribe (LISTEN)')}
              </Button>
              <Button variant="secondary" disabled={busy} onClick={pollNotifications}>
                {gettext('Poll Notifications')}
              </Button>
              {channels.length > 0 && (
                <Button variant="secondary" disabled={busy} onClick={() => handleUnsubscribe(null)}>
                  {gettext('Unlisten All')}
                </Button>
              )}
            </Stack>
          </Grid>
          <Stack direction="row" gap="sm">
            {state.backend_pid && <Badge status="success" label={`Listener PID ${state.backend_pid}`} />}
            {channels.map((ch) => (
              <Button key={ch} variant="secondary" disabled={busy} onClick={() => handleUnsubscribe(ch)}>
                {`${gettext('UNLISTEN')} ${ch}`}
              </Button>
            ))}
          </Stack>
        </Stack>
      </PostgresqlSectionCard>

      <PostgresqlSectionCard title={gettext('Publish Notification (pg_notify)')}>
        <Stack gap="sm">
          <Grid columns={2} gap="sm">
            <TextField
              label={gettext('Target Channel')}
              value={notifyChannel}
              onChange={(e) => setNotifyChannel(e?.target ? e.target.value : e)}
            />
            <Box>
              <Button variant="primary" disabled={busy || !notifyChannel.trim()} onClick={handleSendNotify}>
                {gettext('Send pg_notify')}
              </Button>
            </Box>
          </Grid>
          <TextArea
            label={gettext('Notification Payload (up to 7999 UTF-8 bytes)')}
            rows={3}
            value={notifyPayload}
            onChange={(e) => setNotifyPayload(e?.target ? e.target.value : e)}
          />
        </Stack>
      </PostgresqlSectionCard>

      <PostgresqlSectionCard title={gettext('Received Channel Notifications')}>
        <CodeEditor
          value={JSON.stringify(notifications, null, 2)}
          language="json"
          readOnly
          height="200px"
        />
      </PostgresqlSectionCard>
    </Stack>
  );
}

PostgresqlListenNotifyWorkspace.propTypes = {
  endpointUrl: PropTypes.string.isRequired,
  api: PropTypes.object,
};
