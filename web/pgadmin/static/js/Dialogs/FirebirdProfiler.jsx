import PropTypes from 'prop-types';
import {Box} from '../cdeadmin_ui/primitives/Layout';
import {Banner} from '../cdeadmin_ui/feedback/Indicators';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';

export default function FirebirdProfiler({report, statistics}) {
  if(!report && !statistics) return null;
  const counterNames = Object.keys(statistics?.before?.counters || statistics?.after?.counters || {});
  return <Box style={{marginTop: 8}}>
    {statistics && <Box>
      <FormReference formKey="firebird-query-statistics" />
      <Banner tone={statistics.complete ? 'info' : 'warning'}>
        {statistics.scope}. Host elapsed: {statistics.elapsed ?? 'unavailable'} nanoseconds.
        Timing covers native dispatch, execution, fetch and cursor release; it is not server CPU time.
      </Banner>
      <div>Sampled attachment: before {statistics.before?.attachment_id ?? 'unavailable'};
        after {statistics.after?.attachment_id ?? 'unavailable'}.</div>
      {(statistics.unavailable_reasons || []).length > 0 && <Banner tone="warning">
        Incomplete measurements: {statistics.unavailable_reasons.join(', ')}.
        {(statistics.reset_counters || []).length > 0 && ' Reset counters: ' + statistics.reset_counters.join(', ') + '.'}
      </Banner>}
      {(statistics.errors || []).map((error, index) => <Banner key={index} tone="warning">
        {error.stage}: {error.error_type}. Native status: {(error.native_status_codes || []).join(', ')}
      </Banner>)}
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Query attachment counters"
        rows={counterNames.map(name => ({
          id: name,
          counter: name,
          before: statistics.before?.counters[name] ?? 'Unavailable',
          after: statistics.after?.counters[name] ?? 'Unavailable',
          difference: statistics.deltas?.[name] ?? 'Unavailable / reset',
        }))}
        columns={[
          {key: 'counter', name: 'Counter'},
          {key: 'before', name: 'Before'},
          {key: 'after', name: 'After'},
          {key: 'difference', name: 'Difference'},
        ]}
        compact
        searchable={false}
        exportable={false}
      />
    </Box>}
    {report && <>
      <FormReference formKey="firebird-profiler" />
      <Banner tone={report.state === 'complete' ? 'info' : 'warning'}>
        Native profile {report.profile_id || 'unavailable'}: {report.state}. Elapsed values are nanoseconds.
        Measurements cover this attachment and the executed/fetched portion of the request.
      </Banner>
      {(report.errors || []).map((error, index) => <Banner tone="warning" key={index}>
        {error.stage}: {error.error_type} {(error.native_status_codes || []).join(', ')}.
        The SQL outcome is separate from profiling; do not rerun SQL to recover these measurements.
      </Banner>)}
      {Object.entries(report.sections || {}).map(([name, section]) => <Box key={name} style={{margin: '8px 0'}}>
        <div style={{fontWeight: 600, fontSize: '0.85rem'}}>{name.replaceAll('_', ' ')}</div>
        {section.truncated && <Banner tone="warning">Only the first {report.section_limit} native records are displayed.</Banner>}
        {!section.rows.length ? <div>No measurements in this section.</div> :
          <Box style={{maxHeight: 300, overflow: 'auto'}}>
            <UnifiedDataGrid
              gridRole="table"
              ariaLabel={'Profile ' + name}
              rows={section.rows.map((row, index) => ({
                id: String(index),
                ...Object.fromEntries(Object.entries(row).map(([k, v]) => [k, v == null ? 'NULL' : String(v)])),
              }))}
              columns={Object.keys(section.rows[0]).map(key => ({key, name: key}))}
              compact
              searchable={false}
              exportable={false}
            />
          </Box>}
      </Box>)}
    </>}
  </Box>;
}
FirebirdProfiler.propTypes = {report: PropTypes.object, statistics: PropTypes.object};
