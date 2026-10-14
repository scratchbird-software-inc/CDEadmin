import PropTypes from 'prop-types';
import {Box} from '@mui/material';
import PagedDataGrid from '../cdeadmin_ui/data/PagedDataGrid';

export default function SQLiteTrendView({snapshot}) {
  const rows = (snapshot?.samples || []).map(sample => ({
    sample_id: sample.sample_id, time: sample.ended_at, status: sample.status,
    file_size: sample.groups?.storage?.rows?.[0]?.file_size_bytes ?? 'Unavailable',
    page_count: sample.groups?.storage?.rows?.[0]?.page_count ?? 'Unavailable',
    free_pages: sample.groups?.storage?.rows?.[0]?.freelist_pages ?? 'Unavailable',
    journal_mode: sample.groups?.database?.rows?.[0]?.journal_mode ?? 'Unavailable',
  }));
  return <Box sx={{height: 360, minWidth: 0, overflow: 'auto'}}>
    <PagedDataGrid readOnly gridId="sqlite/volatile-trends" aria-label="SQLite retained observations"
      rows={rows} rowKeyGetter={row => row.sample_id} columns={[
        {key: 'time', name: 'Observed at', minWidth: 185},
        {key: 'status', name: 'Probe', width: 110},
        {key: 'file_size', name: 'Main file bytes', minWidth: 130},
        {key: 'page_count', name: 'Pages', width: 110},
        {key: 'free_pages', name: 'Free-list pages', width: 140},
        {key: 'journal_mode', name: 'Journal mode', width: 140},
      ]} />
  </Box>;
}
SQLiteTrendView.propTypes = {snapshot: PropTypes.object};
