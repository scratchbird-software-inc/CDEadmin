import PropTypes from 'prop-types';
import {Alert, Box, Table, TableHead, TableBody, TableRow, TableCell, Typography} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdProfiler({report, statistics}) {
  if(!report && !statistics) return null;
  return <Box sx={{mt: 1}}>
    {statistics && <Box>
      <FormReference formKey="firebird-query-statistics" />
      <Alert severity={statistics.complete ? 'info' : 'warning'}>
        {statistics.scope}. Host elapsed: {statistics.elapsed ?? 'unavailable'} nanoseconds.
        Timing covers native dispatch, execution, fetch and cursor release; it is not server CPU time.
      </Alert>
      {(statistics.errors || []).map((error, index) => <Alert key={index} severity="warning">
        {error.stage}: {error.error_type}. Native status: {(error.native_status_codes || []).join(', ')}
      </Alert>)}
      <Table size="small" aria-label="Query attachment counters">
        <TableHead><TableRow>{['Counter', 'Before', 'After', 'Difference'].map(name => <TableCell key={name}>{name}</TableCell>)}</TableRow></TableHead>
        <TableBody>{Object.keys(statistics.before?.counters || statistics.after?.counters || {}).map(name => <TableRow key={name}>
          <TableCell>{name}</TableCell><TableCell>{statistics.before?.counters[name] ?? 'Unavailable'}</TableCell>
          <TableCell>{statistics.after?.counters[name] ?? 'Unavailable'}</TableCell>
          <TableCell>{statistics.deltas[name] ?? 'Unavailable / reset'}</TableCell>
        </TableRow>)}</TableBody>
      </Table>
    </Box>}
    {report && <>
      <FormReference formKey="firebird-profiler" />
      <Alert severity={report.state === 'complete' ? 'info' : 'warning'}>
      Native profile {report.profile_id || 'unavailable'}: {report.state}. Elapsed values are nanoseconds.
      Measurements cover this attachment and the executed/fetched portion of the request.
      </Alert>
      {(report.errors || []).map((error, index) => <Alert severity="warning" key={index}>
        {error.stage}: {error.error_type} {(error.native_status_codes || []).join(', ')}.
      The SQL outcome is separate from profiling; do not rerun SQL to recover these measurements.
      </Alert>)}
      {Object.entries(report.sections || {}).map(([name, section]) => <Box key={name} sx={{my: 1}}>
        <Typography variant="subtitle2">{name.replaceAll('_', ' ')}</Typography>
        {section.truncated && <Alert severity="warning">Only the first {report.section_limit} native records are displayed.</Alert>}
        {!section.rows.length ? <Typography>No measurements in this section.</Typography> :
          <Box sx={{maxHeight: 300, overflow: 'auto'}}><Table size="small" aria-label={'Profile ' + name}>
            <TableHead><TableRow>{Object.keys(section.rows[0]).map(key => <TableCell key={key}>{key}</TableCell>)}</TableRow></TableHead>
            <TableBody>{section.rows.map((row, index) => <TableRow key={index}>
              {Object.entries(row).map(([key, value]) => <TableCell key={key}>{value == null ? 'NULL' : String(value)}</TableCell>)}
            </TableRow>)}</TableBody>
          </Table></Box>}
      </Box>)}
    </>}
  </Box>;
}
FirebirdProfiler.propTypes = {report: PropTypes.object, statistics: PropTypes.object};
