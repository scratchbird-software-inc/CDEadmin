import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';
/* global BigInt */
import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, TextField, Typography} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdEvents({post, databaseTargetId}) {
  const [names, setNames] = useState('');
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [entries, setEntries] = useState([]);
  const previous = useRef(null);
  // Each owner retains its original endpoint and database through late replies.
  const owner = useMemo(() => ({active: true, running: false, id: null, released: false,
    unknownStart: false, fileRevision: 0,
    request: (action, values={}) => post({action: 'firebird_events',
      request: {action, database_target_id: databaseTargetId, ...values}}),
  }), [post, databaseTargetId]);
  const cleanup = scope => {
    if (scope.id && !scope.released && !scope.running) {
      scope.request('stop', {subscription_id: scope.id}).catch(() => {});
    }
  };
  const send = async action => {
    if (!owner.active || owner.running || (action === 'start' && owner.unknownStart)) return;
    owner.running = true;
    if (action === 'start') owner.unknownStart = true;
    setBusy(true); setError(null);
    try {
      const next = await owner.request(action, action === 'start' ?
        {names: names.split('\n').filter(name => name !== '')} : {subscription_id: owner.id});
      owner.id = next.subscription_id;
      owner.released = next.cleanup_confirmed === true;
      owner.unknownStart = false;
      if (owner.active) setReport(next);
    } catch {if (owner.active) setError('Event request failed or its response was lost. Do not assume release or continuous delivery. Retry polling the known subscription; a lost start response expires after 120 idle seconds.');}
    finally {
      owner.running = false;
      if (owner.active) setBusy(false);
      else if (action !== 'stop') cleanup(owner);
    }
  };
  useEffect(() => {
    owner.active = true;
    setNames(''); setReport(null); setEntries([]); setBusy(false); setError(null);
    previous.current = null;
    return () => {owner.active = false; owner.fileRevision++; cleanup(owner);};
  }, [owner]);
  useEffect(() => {
    if (!report || report.cleanup_confirmed || busy || error || !owner.id) return undefined;
    const timer = setTimeout(() => send('poll'), 2000);
    return () => clearTimeout(timer);
  }, [report, busy, error, owner]);
  useEffect(() => {
    if (!report || report.subscription_id !== owner.id) return;
    const old = previous.current;
    previous.current = report;
    const additions = Object.entries(report.counts).flatMap(([name, count]) => {
      const before = old?.subscription_id === report.subscription_id ? old.counts[name] || '0' : '0';
      const difference = BigInt(count) - BigInt(before);
      return difference > 0 ? [{subscription_id: report.subscription_id, observed_at: report.updated_at,
        name, count: difference.toString(), cumulative: count}] : [];
    });
    setEntries(current => [...(old?.subscription_id === report.subscription_id ? current : []), ...additions].slice(-1000));
  }, [report, owner]);
  const save = (filename, content) => {
    const url = URL.createObjectURL(new Blob([content], {type: 'text/plain;charset=utf-8'}));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename;
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box data-cde-compact-form sx={{p: 2, overflow: 'auto', ...compactFormSx}}>
    <FormReference formKey="firebird-event-monitor" />
    <Alert severity="info">Dedicated event attachment. Counts cover this subscription only. Events are published at commit; disconnected intervals cannot be replayed. Reconnect starts a new observation interval. Idle subscriptions expire after 120 seconds; this workflow requires server process affinity. Network events also require a reachable Firebird auxiliary event port.</Alert>
    <TextField multiline minRows={3} fullWidth label="Event names (one per line)" value={names} disabled={busy || (report && !report.cleanup_confirmed)} onChange={event => {owner.fileRevision++; setNames(event.target.value);}} />
    <Button component="label" disabled={busy || (report && !report.cleanup_confirmed)}>Load event names
      <input type="file" hidden aria-label="Event names file" disabled={busy || (report && !report.cleanup_confirmed)} onChange={async event => {
        const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
        const revision = ++owner.fileRevision;
        try {
          if (file.size > 4096) throw new Error('Event names file exceeds 4096 bytes.');
          const text = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
          if (owner.active && revision === owner.fileRevision) setNames(text.replace(/\r\n|\r/g, '\n'));
        } catch {if (owner.active && revision === owner.fileRevision) setError('Import requires a UTF-8 event-name file of at most 4096 bytes.');}
      }} />
    </Button>
    <Button disabled={!names} onClick={() => save('firebird-events.txt', names)}>Save event names</Button>
    <Button disabled={busy || !databaseTargetId || !names || owner.unknownStart || (report && !report.cleanup_confirmed)} onClick={() => send('start')}>Subscribe / reconnect</Button>
    <Button disabled={busy || !owner.id} onClick={() => send('poll')}>Refresh event counts</Button>
    <Button disabled={busy || !owner.id || report?.cleanup_confirmed} onClick={() => send('stop')}>Unsubscribe</Button>
    {error && <Alert severity="warning">{error}</Alert>}
    {entries.length > 0 && <Box>
      <Typography>Observed event log: latest {entries.length} entries, maximum 1000. Times are observations, not commit timestamps.</Typography>
      <Button onClick={() => save('firebird-event-observations.jsonl', entries.map(entry => JSON.stringify(entry)).join('\n') + '\n')}>Save event observations</Button>
      <Button onClick={() => setEntries([])}>Clear displayed event log</Button>
      <Box component="pre" sx={{maxHeight: 240, overflow: 'auto'}}>{entries.map(entry => JSON.stringify(entry)).join('\n')}</Box>
    </Box>}
    {report && <>
      <Typography>Subscription {report.subscription_id}: {report.state}</Typography>
      {report.delivery_gap && <Alert severity="warning">Delivery gap: missed events are unknown.</Alert>}
      {report.error_type && <Alert severity="warning">Native operation: {report.error_type}</Alert>}
      <Typography>Attachment release: {report.cleanup_confirmed ? 'confirmed' : 'not confirmed'}</Typography>
      {Object.entries(report.counts).map(([name, count]) => <Typography key={name}>{name}: {count}</Typography>)}
    </>}
  </Box>;
}
FirebirdEvents.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string};
