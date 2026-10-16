import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, MenuItem, TextField} from '@mui/material';
import getApiInstance from '../api_instance';
import url_for from 'sources/url_for';
import FirebirdTrendView from './FirebirdTrendView';
import MySQLTrendView from './MySQLTrendView';

export default function FirebirdHistoryView({serverId, targetId, engine='firebird'}) {
  const serial = useRef(0);
  const [hours, setHours] = useState(24);
  const [tier, setTier] = useState('raw');
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [window, setWindow] = useState(null);
  useEffect(() => {
    serial.current++; setSnapshot(null); setError(''); setWindow(null); setBusy(false);
    return () => {serial.current++;};
  }, [serverId, targetId, hours, tier, engine]);
  const read = async (next=false) => {
    const token = ++serial.current;
    setBusy(true); setError(''); setSnapshot(null);
    const selected = next ? window : {start: new Date(Date.now()-hours*3600000).toISOString(), end: new Date().toISOString()};
    try {
      const params = {start: selected.start, end: selected.end, tier, limit: 720};
      if(targetId) params.target_id = targetId;
      if(next) params.after = selected.after;
      const route = engine === 'mysql' ? 'cdeadmin_mysql_monitoring.history' : 'cdeadmin_monitoring.history';
      const response = await getApiInstance().get(url_for(route, {sid: serverId}), {params});
      if(token === serial.current) {
        setSnapshot(response.data.data);
        setWindow({...selected, after: response.data.data.next});
      }
    } catch(err) {
      if(token === serial.current) setError(err.response?.data?.errormsg || 'Monitoring history is unavailable.');
    } finally {if(token === serial.current) setBusy(false);}
  };
  return <Box sx={{my: 2}}>
    <Alert severity="info">ScratchBird history is separate from current health. Empty windows do not prove continuous collection.
      Downsampled windows retain exact minima, maxima and counts in provenance; their representative rates are gaps.</Alert>
    <Box sx={{display: 'flex', gap: 1, my: 1}}>
      <TextField select size="small" label="History window" value={hours} disabled={busy} onChange={(event) => setHours(Number(event.target.value))}>
        {[1, 24, 168, 720, 2160].map((value) => <MenuItem key={value} value={value}>Last {value} hours</MenuItem>)}
      </TextField>
      <TextField select size="small" label="Resolution" value={tier} disabled={busy} onChange={(event) => setTier(event.target.value)}>
        <MenuItem value="raw">Original observations</MenuItem><MenuItem value="rollup">Downsampled windows</MenuItem>
      </TextField>
      <Button disabled={busy} onClick={() => read()}>Read history</Button>
      <Button disabled={busy || !window?.after} onClick={() => read(true)}>Next page</Button>
    </Box>
    {error && <Alert severity="error">{error}</Alert>}
    {snapshot && <>
      {engine === 'mysql' ? <MySQLTrendView snapshot={snapshot} scope={targetId ? 'database' : 'server'} engine="mysql" /> :
        <FirebirdTrendView snapshot={snapshot} scope={targetId ? 'database' : 'server'} />}
      <details><summary>Exact samples, window summaries and source provenance</summary>
        <Box component="pre" sx={{overflow: 'auto', maxHeight: 400}}>{JSON.stringify(snapshot.samples, null, 2)}</Box>
      </details>
    </>}
  </Box>;
}
FirebirdHistoryView.propTypes = {serverId: PropTypes.number.isRequired, targetId: PropTypes.string,
  engine: PropTypes.oneOf(['firebird', 'mysql'])};
