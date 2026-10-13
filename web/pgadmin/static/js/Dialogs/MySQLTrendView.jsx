import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, MenuItem, TextField} from '@mui/material';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {MYSQL_TREND_METRICS, mysqlTrendFiles} from '../cdeadmin_ui/integrations/ddn/mysqlTrends';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function MySQLTrendView({snapshot, scope, engine='mysql'}) {
  const [metric, setMetric] = useState('Questions'), [limit, setLimit] = useState(120);
  const files = useMemo(() => mysqlTrendFiles(snapshot, scope, metric, limit, engine), [snapshot, scope, metric, limit, engine]);
  return <Box sx={{minHeight: 450}}>
    <FormReference formKey={`${engine}-recent-observations`} />
    <Alert severity="info">Past observations from this process only. Collection: {snapshot?.state || 'Unknown'}.
      Retained: {snapshot?.samples?.length || 0}. Evicted: {snapshot?.retention_evictions || 0}.
      Server-wide counters include other databases and collectors. Chart values are approximate;
      exact values and gaps appear below. Past observations do not imply current availability.</Alert>
    <Box sx={{display: 'flex', gap: 1, my: 1, flexWrap: 'wrap'}}>
      <TextField select size="small" label="Measure" value={metric} onChange={event => setMetric(event.target.value)}>
        {MYSQL_TREND_METRICS.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>
      <TextField select size="small" label="Retained window" value={limit} onChange={event => setLimit(Number(event.target.value))}>
        {[30, 120, 720].map(count => <MenuItem key={count} value={count}>Last {count} samples</MenuItem>)}
      </TextField>
    </Box>
    <DDNViewerSurface files={files} entry="trends.ddn" view="trends" presentation />
  </Box>;
}
MySQLTrendView.propTypes = {snapshot: PropTypes.object, engine: PropTypes.oneOf(['mysql', 'mariadb']), scope: PropTypes.oneOf(['server', 'database']).isRequired};
