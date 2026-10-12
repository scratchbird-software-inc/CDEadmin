import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, MenuItem, TextField} from '@mui/material';
import getApiInstance from '../api_instance';
import url_for from 'sources/url_for';
import FirebirdTrendView from './FirebirdTrendView';

export default function FirebirdEngineTrends({fleet}) {
  const [selected, setSelected] = useState('');
  const [observation, setObservation] = useState(null);
  const [error, setError] = useState('');
  const choices = (fleet?.servers || []).flatMap((server) => (server.databases || []).map((database) => ({
    key: `${server.server_id}:${database.target_id}`, sid: server.server_id, target: database.target_id,
    label: `${server.name} [${server.server_id}] / ${database.name}`,
  })));
  const chosen = choices.find((item) => item.key === selected);
  const sid = chosen?.sid, target = chosen?.target;
  useEffect(() => {
    let active = true, reading = false;
    setObservation(null); setError('');
    if(!sid || !target) return () => {active = false;};
    const read = async () => {
      if(reading) return;
      reading = true;
      try {
        const response = await getApiInstance().get(url_for('cdeadmin_monitoring.monitoring', {sid}) +
          '?target_id=' + encodeURIComponent(target));
        if(active) {setObservation(response.data.data); setError('');}
      } catch(exception) {
        if(active) {setObservation(null); setError(exception.response?.data?.errormsg || 'Retained observations are unavailable.');}
      } finally {reading = false;}
    };
    read();
    const timer = setInterval(read, 5000);
    return () => {active = false; clearInterval(timer);};
  }, [sid, target]);
  return <Box sx={{flexShrink: 0}}>
    <TextField select size="small" label="Engine workload history: database" value={chosen ? selected : ''}
      onChange={(event) => setSelected(event.target.value)} sx={{my: 1, minWidth: 300}}>
      <MenuItem value="">Select retained database observations</MenuItem>
      {choices.map((item) => <MenuItem key={item.key} value={item.key}>{item.label}</MenuItem>)}
    </TextField>
    {error && <Alert severity="warning">{error}</Alert>}
    {observation && <FirebirdTrendView key={selected} snapshot={observation} scope="database" />}
  </Box>;
}
FirebirdEngineTrends.propTypes = {fleet: PropTypes.object};
