import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, MenuItem, TextField} from '@mui/material';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {FIREBIRD_TREND_METRICS, firebirdTrendFiles} from '../cdeadmin_ui/integrations/ddn/firebirdTrends';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdTrendView({snapshot, scope}) {
  const choices = FIREBIRD_TREND_METRICS.filter((item) => item.scope === scope);
  const [metric, setMetric] = useState(choices[0].id);
  const [limit, setLimit] = useState(120);
  const files = useMemo(() => firebirdTrendFiles(snapshot, metric, limit), [snapshot, metric, limit]);
  return <Box sx={{minHeight: 450}}>
    <FormReference formKey="firebird-recent-observations" />
    <Alert severity="info">{snapshot.history === 'scratchbird' ? 'Archived ScratchBird observations.' : 'Past observations from this process only.'} Collection: {snapshot.state}.
      Retained: {snapshot.samples?.length || 0}. Evicted: {snapshot.retention_evictions || 0}.
      Latest sample age: {snapshot.sample_age_seconds ?? 'Unknown'} seconds.
      Points are approximate; the table preserves exact values and gaps.</Alert>
    <Box sx={{display: 'flex', gap: 1, my: 1}}>
      <TextField select size="small" label="Measure" value={metric} onChange={(event) => setMetric(event.target.value)}>
        {choices.map((item) => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>
      <TextField select size="small" label="Retained window" value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
        {[30, 120, 720].map((count) => <MenuItem key={count} value={count}>Last {count} samples</MenuItem>)}
      </TextField>
    </Box>
    <DDNViewerSurface files={files} entry="trends.ddn" view="trends" presentation />
  </Box>;
}
FirebirdTrendView.propTypes = {snapshot: PropTypes.object.isRequired,
  scope: PropTypes.oneOf(['server', 'database']).isRequired};
