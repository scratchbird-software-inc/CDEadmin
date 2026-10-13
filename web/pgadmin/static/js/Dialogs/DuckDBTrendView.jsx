import PropTypes from 'prop-types';
import {Box} from '@mui/material';
import PagedDataGrid from '../cdeadmin_ui/data/PagedDataGrid';

export default function DuckDBTrendView({snapshot}) {
  const rows = (snapshot?.samples || []).map(sample => ({
    sample_id: sample.sample_id, time: sample.ended_at, status: sample.status,
    database_size: sample.groups?.storage?.rows?.[0]?.database_size ?? 'Unavailable',
    used_blocks: sample.groups?.storage?.rows?.[0]?.used_blocks ?? 'Unavailable',
    memory_usage: sample.groups?.storage?.rows?.[0]?.memory_usage ?? 'Unavailable',
    extension_count: sample.groups?.extensions?.rows?.[0]?.loaded ?? 'Unavailable',
  }));
  return <Box sx={{height: 360, minWidth: 0, overflow: 'auto'}}>
    <PagedDataGrid readOnly gridId="duckdb/volatile-trends" aria-label="DuckDB retained observations"
      rows={rows} rowKeyGetter={row => row.sample_id} columns={[
        {key: 'time', name: 'Observed at', minWidth: 185},
        {key: 'status', name: 'Probe', width: 110},
        {key: 'database_size', name: 'Database size', minWidth: 130},
        {key: 'used_blocks', name: 'Used blocks', width: 110},
        {key: 'memory_usage', name: 'Memory used', minWidth: 130},
        {key: 'extension_count', name: 'Loaded extensions', width: 140},
      ]} />
  </Box>;
}
DuckDBTrendView.propTypes = {snapshot: PropTypes.object};
