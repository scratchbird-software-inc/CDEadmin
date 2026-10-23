import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, MenuItem, TextField, Typography} from '@mui/material';
import getApiInstance from '../api_instance';

export default function MySQLAlerts({endpoint, catalog, rules, onChange, active, busy, alerts}) {
  const [error, setError] = useState(''), [pending, setPending] = useState(false);
  const [seconds, setSeconds] = useState(3600), [live, setLive] = useState(alerts);
  const serial = useRef(0);
  useEffect(() => {serial.current++; setLive(alerts); setPending(false); setError('');}, [endpoint]);
  useEffect(() => {setLive(alerts);}, [alerts]);
  const metrics = catalog?.metrics || [], routes = catalog?.routes || [];
  const update = (index, patch) => onChange(rules.map((rule, i) => i === index ? {...rule, ...patch} : rule));
  const silence = async (rule, duration) => {
    const token = ++serial.current;
    setPending(true); setError('');
    try {
      const result = await getApiInstance().post(endpoint, {action: 'silence', rule_id: rule, seconds: duration});
      if(token === serial.current) setLive(result.data.data);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || 'Alert change failed');}
    finally {if(token === serial.current) setPending(false);}
  };
  return <Box sx={{my: 1}}>
    <Typography variant="h6">MySQL alert policies</Typography>
    <Alert severity="info">Rules evaluate server observations on the dedicated collector, including when this screen is closed.
      Thresholds use greater than; duration requires consecutive observations in one source epoch. Missing data stays unknown unless explicitly configured to alert.
      State and silences last for this process and collection lease. Notifications contain numeric evidence and channel identifiers; configured routes fix recipients on the server.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {rules.map((rule, index) => <Box key={rule.id} sx={{display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center', my: 1}}>
      <Typography>{rule.id}</Typography>
      <TextField select size="small" label={`Metric ${index+1}`} value={rule.metric} disabled={busy || active}
        onChange={event => update(index, {metric: event.target.value})}>
        {metrics.map(metric => <MenuItem key={metric.id} value={metric.id}>{metric.label} ({metric.unit})</MenuItem>)}
      </TextField>
      <TextField size="small" label={`Threshold ${index+1}`} value={rule.threshold} disabled={busy || active}
        onChange={event => update(index, {threshold: event.target.value})} />
      <TextField size="small" type="number" label={`Duration seconds ${index+1}`} value={rule.duration_seconds} disabled={busy || active}
        onChange={event => update(index, {duration_seconds: Number(event.target.value)})} />
      <TextField select size="small" label={`Missing observations ${index+1}`} value={rule.missing} disabled={busy || active}
        onChange={event => update(index, {missing: event.target.value})}>
        <MenuItem value="unknown">Unknown; retain unresolved incidents</MenuItem><MenuItem value="alert">Alert after duration</MenuItem>
      </TextField>
      <TextField select size="small" label={`Severity ${index+1}`} value={rule.severity} disabled={busy || active}
        onChange={event => update(index, {severity: event.target.value})}>
        <MenuItem value="warning">Warning</MenuItem><MenuItem value="critical">Critical</MenuItem>
      </TextField>
      <TextField select size="small" label={`Notification route ${index+1}`} value={rule.route_id} disabled={busy || active}
        onChange={event => update(index, {route_id: event.target.value})}>
        <MenuItem value="">No delivery</MenuItem>{routes.map(route => <MenuItem key={route.id} value={route.id}>{route.label}</MenuItem>)}
      </TextField>
      <Button size="small" disabled={busy || active} onClick={() => onChange(rules.filter((_, i) => i !== index))}>Remove {rule.id}</Button>
    </Box>)}
    <Button size="small" disabled={busy || active || rules.length >= 32 || !metrics.length} onClick={() => {
      let id = 1; while(rules.some(rule => rule.id === `rule-${id}`)) id++;
      onChange([...rules, {id: `rule-${id}`, metric: metrics[0].id, threshold: '0', duration_seconds: 0, missing: 'unknown', severity: 'warning', route_id: ''}]);
    }}>Add alert rule</Button>
    {live && <>
      <Typography>Alert state: {active ? live.storage : 'Collector stopped'}. Delivery attempts have no automatic retry.</Typography>
      <TextField size="small" type="number" label="Silence seconds" value={seconds} disabled={pending || busy || !active}
        onChange={event => setSeconds(Number(event.target.value))} />
      {(live.rules || []).map(item => <Box key={item.rule.id} sx={{my: 1}}>
        <Typography>{item.rule.id}: {item.state} — {item.evidence?.metric || item.rule.metric}: {item.evidence?.value ?? 'unavailable'}.
          Condition: {item.condition}. Continuous breach: {item.breach_seconds || 0}s. Silence remaining: {Math.ceil(item.silence_remaining_seconds || 0)}s.</Typography>
        <Typography>Source: {item.evidence?.source}. Server: {item.evidence?.server_uuid || 'unobserved'}.
          Sample: {item.evidence?.sample_id || 'unobserved'}. {item.evidence?.reason || ''}</Typography>
        <Typography>{metrics.find(metric => metric.id === item.rule.metric)?.action}</Typography>
        <Button size="small" disabled={!active || busy || pending} onClick={() => silence(item.rule.id, seconds)}>Silence {item.rule.id}</Button>
        <Button size="small" disabled={!active || busy || pending || item.state !== 'silenced'} onClick={() => silence(item.rule.id, 0)}>Unsilence {item.rule.id}</Button>
      </Box>)}
      <Typography variant="subtitle2">Recent transitions (up to {live.event_limit})</Typography>
      {(live.events || []).slice().reverse().map(event => <Typography key={event.event_id}>
        {event.created_at} · {event.rule_id} · {event.transition} · Delivery: {event.delivery.state}
        {event.delivery.error_type ? ` (${event.delivery.error_type})` : ''}
        {event.delivery.reason ? ` (${event.delivery.reason})` : ''}
        {event.delivery.occurrence_id ? ` · Receipt ${event.delivery.occurrence_id}` : ''}
      </Typography>)}
    </>}
  </Box>;
}
MySQLAlerts.propTypes = {endpoint: PropTypes.string.isRequired, catalog: PropTypes.object, rules: PropTypes.array.isRequired,
  onChange: PropTypes.func.isRequired, active: PropTypes.bool, busy: PropTypes.bool, alerts: PropTypes.object};
