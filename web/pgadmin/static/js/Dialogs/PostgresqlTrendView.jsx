import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, MenuItem, TextField} from '@mui/material';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {POSTGRESQL_TREND_METRICS, postgresqlTrendDatabases, postgresqlTrendFiles} from '../cdeadmin_ui/integrations/ddn/postgresqlTrends';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function PostgresqlTrendView({snapshot, scope}) {
  const choices = useMemo(() => postgresqlTrendDatabases(snapshot), [snapshot]);
  const [selected, setSelected] = useState('');
  const databaseId = choices.some(item => item.id === selected) ? selected : choices[0]?.id || '';
  const [metric, setMetric] = useState('xact_commit');
  const [limit, setLimit] = useState(120);
  const files = useMemo(() => postgresqlTrendFiles(snapshot, scope, databaseId, metric, limit), [snapshot, scope, databaseId, metric, limit]);
  return <Box sx={{minHeight: 450}}>
    <FormReference formKey="postgresql-recent-observations" />
    <Alert severity="info">Past observations from this process only. Collection: {snapshot?.state || 'Unknown'}.
      Retained: {snapshot?.samples?.length || 0}. Evicted: {snapshot?.retention_evictions || 0}.
      Latest sample age: {snapshot?.sample_age_seconds ?? 'Unknown'} seconds.
      Approximate points do not imply current availability. Exact values and gaps appear below.</Alert>
    <Box sx={{display: 'flex', gap: 1, my: 1, flexWrap: 'wrap'}}>
      <TextField select size="small" label="Observed database" value={databaseId} sx={{minWidth: 180}}
        onChange={event => setSelected(event.target.value)}>
        {!choices.length && <MenuItem value="">No observed database</MenuItem>}
        {choices.map(item => <MenuItem key={item.id} value={item.id}>{item.name} [OID {item.id}]</MenuItem>)}
      </TextField>
      <TextField select size="small" label="Measure" value={metric} onChange={event => setMetric(event.target.value)}>
        {POSTGRESQL_TREND_METRICS.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>
      <TextField select size="small" label="Retained window" value={limit} onChange={event => setLimit(Number(event.target.value))}>
        {[30, 120, 720].map(count => <MenuItem key={count} value={count}>Last {count} samples</MenuItem>)}
      </TextField>
    </Box>
    <DDNViewerSurface files={files} entry="trends.ddn" view="trends" presentation />
  </Box>;
}
PostgresqlTrendView.propTypes = {snapshot: PropTypes.object, scope: PropTypes.oneOf(['server', 'database']).isRequired};
