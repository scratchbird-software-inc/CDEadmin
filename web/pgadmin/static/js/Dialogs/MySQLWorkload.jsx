import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography} from '@mui/material';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {dashboardPanelFiles} from '../cdeadmin_ui/integrations/ddn/dashboardPanels';
import MySQLQueryPlan from './MySQLQueryPlan';

const rankings = {total_latency: 'Total latency', mean_latency: 'Mean latency', executions: 'Execution count',
  rows_examined: 'Rows examined', temporary_tables: 'Temporary tables', disk_temporary_tables: 'Disk temporary tables'};
const fields = {schema_name: 'Schema', digest_text: 'Native normalized SQL', count_star: 'Executions',
  sum_timer_wait: 'Total latency (ps)', avg_timer_wait: 'Mean latency (ps)', sum_rows_examined: 'Rows examined',
  sum_created_tmp_tables: 'Temporary tables', sum_created_tmp_disk_tables: 'Disk temporary tables', first_seen: 'First seen', last_seen: 'Last seen'};
const valueText = value => value == null ? 'Unavailable' : typeof value === 'object' ? JSON.stringify(value) : String(value);

export function workloadDashboardFiles(snapshot) {
  const rows = name => snapshot?.groups?.[name]?.status === 'available' ? snapshot.groups[name].rows : [];
  return dashboardPanelFiles([
    {id: 'coverage', title: 'MySQL workload coverage', rows: [
      ['Scope', snapshot?.schema_name ?? 'Server'], ['Native identity', snapshot?.identity?.server_uuid],
      ['Basis', 'Cumulative native summaries; timers in picoseconds; no inferred rates'],
      ['Reset observation', 'FIRST_SEEN / observed decreases; undetected resets remain possible'],
      ...Object.entries(snapshot?.groups || {}).map(([name, item]) => [name, item.status, item.scope, item.truncated ? 'Top 100; truncated' : '']),
      ...rows('workload_settings').flatMap(row => Object.entries(row).map(([key, value]) => [key, valueText(value)])),
      ...rows('workload_epoch').map(row => [row.variable_name, row.variable_value]),
      ...rows('workload_consumers').map(row => [row.name, row.enabled]),
      ...rows('workload_instruments').map(row => [row.family, `Enabled ${row.enabled_count}/${row.instrument_count}; timed ${row.timed_count}`]),
    ]},
    {id: 'waits', title: 'Server waits — not attributed to selected digest', rows:
      rows('workload_waits').slice(0, 10).map(row => [row.event_name, row.sum_timer_wait, `picoseconds; count ${row.count_star}`])},
    {id: 'indexes', title: 'Native index activity — not attributed to selected digest', rows:
      rows('workload_indexes').slice(0, 10).map(row => [`${row.object_schema}.${row.object_name} / ${row.index_name ?? 'no index'}`,
        row.sum_timer_wait, `picoseconds; reads ${row.count_read}; writes ${row.count_write}`])},
  ], 'MySQL workload observations', 'scratchrobin.mysql.workload');
}

function NativeRows({rows, label}) {
  const keys = [...new Set((rows || []).flatMap(Object.keys))];
  return <Box sx={{overflow: 'auto', maxHeight: 400}}><Table size="small" aria-label={label}>
    <TableHead><TableRow>{keys.map(key => <TableCell key={key}>{key}</TableCell>)}</TableRow></TableHead>
    <TableBody>{rows?.map((row, index) => <TableRow key={index}>{keys.map(key => <TableCell key={key}>{valueText(row[key])}</TableCell>)}</TableRow>)}</TableBody>
  </Table>{!rows?.length && <Typography>No retained native rows were observed. Check coverage.</Typography>}</Box>;
}
NativeRows.propTypes = {rows: PropTypes.array, label: PropTypes.string};

export default function MySQLWorkload({post, databaseTargetId=null}) {
  const [schema, setSchema] = useState(''), [rank, setRank] = useState('total_latency');
  const [snapshot, setSnapshot] = useState(null), [selected, setSelected] = useState(null);
  const [sample, setSample] = useState(null), [plan, setPlan] = useState(null), [waits, setWaits] = useState(null);
  const [slow, setSlow] = useState(null), [consent, setConsent] = useState(false);
  const [start, setStart] = useState(''), [end, setEnd] = useState(''), [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const generation = useRef(0);
  useEffect(() => {
    generation.current++; setSnapshot(null); setSelected(null); setSample(null); setPlan(null); setWaits(null);
    setSlow(null); setConsent(false); setFile(null); setBusy(false); setError('');
    return () => {generation.current++;};
  }, [schema, rank, databaseTargetId]);
  const clearPrivate = () => {generation.current++; setBusy(false); setSample(null); setPlan(null); setFile(null); setConsent(false);};
  const run = async (operation, request, accept) => {
    const token = ++generation.current;
    setBusy(true); setError('');
    try {
      const result = await post({action: `mysql_workload_${operation}`, request: {
        database_target_id: databaseTargetId, schema_name: schema || null, ...request}});
      if(token === generation.current) accept(result);
    } catch(failure) {
      if(token === generation.current) setError(failure?.response?.data?.errormsg || failure.message || 'Native workload observation failed');
    } finally {if(token === generation.current) setBusy(false);}
  };
  const digests = snapshot?.groups?.workload_digests;
  const files = useMemo(() => workloadDashboardFiles(snapshot), [snapshot]);
  const choose = row => {setSelected(row); setSample(null); setPlan(null); setWaits(null);};
  const selectedRequest = selected ? {schema_name: selected.schema_name, digest: selected.digest} : {};
  const slowRequest = {confirmed: true, start_utc: start, end_utc: end};
  return <Box sx={{p: 1, height: '100%', overflow: 'auto'}} aria-label="MySQL workload analysis">
    <Typography component="h3">MySQL workload analysis</Typography>
    <Alert severity="info">Observations use separate connections. Native summaries are cumulative and permission filtered. Timers are exact picoseconds.
      Reset detection cannot prove uninterrupted coverage. Collection policy continues separately from this workspace.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display: 'flex', gap: 1, my: 1, flexWrap: 'wrap'}}>
      <TextField size="small" label="Schema (blank for server)" value={schema} onChange={event => setSchema(event.target.value)} disabled={busy} />
      <TextField select size="small" label="Rank statements by" value={rank} onChange={event => setRank(event.target.value)} disabled={busy}>
        {Object.entries(rankings).map(([key, label]) => <MenuItem key={key} value={key}>{label}</MenuItem>)}
      </TextField>
      <Button disabled={busy} onClick={() => {setSelected(null); clearPrivate(); setWaits(null); run('snapshot', {rank}, setSnapshot);}}>Refresh workload</Button>
    </Box>
    {snapshot && <>
      <Alert severity={digests?.status === 'available' ? 'info' : 'warning'}>Digest source: {digests?.status || 'Unavailable'}.
        {digests?.truncated ? ' Showing the top 100; more native digests exist.' : ''}
        {' '}A NULL digest is the native overflow bucket and cannot be drilled into. Empty or disabled instrumentation does not mean no workload.</Alert>
      <Box sx={{overflow: 'auto', maxHeight: 440}}><Table size="small" aria-label="Ranked native statement digests">
        <TableHead><TableRow><TableCell>Inspect</TableCell>{Object.values(fields).map(label => <TableCell key={label} sx={{whiteSpace: 'nowrap'}}>{label}</TableCell>)}</TableRow></TableHead>
        <TableBody>{digests?.rows?.map((row, index) => <TableRow key={index} selected={selected === row}>
          <TableCell><Button size="small" disabled={busy || !row.digest} aria-label={`Inspect digest ${index + 1}`} onClick={() => choose(row)}>Inspect</Button></TableCell>
          {Object.keys(fields).map(key => <TableCell key={key} sx={{whiteSpace: key === 'digest_text' ? 'pre-wrap' : 'nowrap', minWidth: key === 'digest_text' ? 260 : undefined}}>{valueText(row[key])}</TableCell>)}
        </TableRow>)}</TableBody>
      </Table></Box>
      <Box sx={{height: 480, overflow: 'auto', my: 1}}><DDNViewerSurface presentation files={files} entry="dashboard.ddn" view="dashboard" /></Box>
      <Box component="details"><Box component="summary">All native wait and index observations / coverage</Box>
        {['workload_waits', 'workload_indexes', 'workload_consumers', 'workload_instruments', 'workload_settings', 'workload_epoch'].map(name => <Box key={name}>
          <Typography component="h4">{name}: {snapshot.groups[name]?.status} ({snapshot.groups[name]?.scope}){snapshot.groups[name]?.truncated ? ' — top 100, truncated' : ''}</Typography>
          <NativeRows label={name} rows={snapshot.groups[name]?.rows} />
        </Box>)}
      </Box>
    </>}
    {selected && <Box sx={{my: 1}}>
      <Typography component="h4">Selected digest: {selected.digest}</Typography>
      <NativeRows label="Selected digest native measurements" rows={[selected]} />
      <Button disabled={busy} onClick={() => run('waits', selectedRequest, setWaits)}>Inspect retained direct waits</Button>
      {waits && <><Alert severity="info">{waits.coverage}</Alert><NativeRows label="Selected digest waits" rows={waits.groups.direct_statement_waits?.rows} /></>}
    </Box>}
    <FormControlLabel label="Allow private SQL inspection for this request (native server logging still applies)" control={<Checkbox checked={consent}
      disabled={busy} onChange={event => {setConsent(event.target.checked); if(!event.target.checked) clearPrivate();}} />} />
    <Button disabled={busy} onClick={clearPrivate}>Clear private SQL</Button>
    {selected && <Button disabled={busy || !consent} onClick={() => {setPlan(null); run('sample', {...selectedRequest, confirmed: true}, setSample);}}>Inspect private native sample</Button>}
    {sample && <Box>
      <Alert severity="warning">This sample can contain literals and credentials. It is not stored in monitoring or SQL history.
        The sample may be truncated by MySQL. Native EXPLAIN uses current observer settings and may evaluate optimizer expressions.</Alert>
      <Box component="pre" aria-label="Private native SQL sample" sx={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{sample.query_sample_text}</Box>
      <Button disabled={busy || !consent} onClick={() => run('plan', {...selectedRequest, confirmed: true, sample_sha256: sample.sample_sha256}, setPlan)}>Capture native estimated plan</Button>
    </Box>}
    {plan && <><Alert severity="info">{plan.basis}</Alert><MySQLQueryPlan rendered={plan.rendered} /></>}
    <Typography component="h4">Scoped slow-log analysis</Typography>
    <Alert severity="info">Choose one schema and a UTC window of at most 24 hours. TABLE reads the latest 100 matching entries.
      File input accepts up to 1 MiB / 500 complete UTF-8 native long-format entries; include the preceding use statement for schema context.
      Native digest functions normalize bound SQL text without executing it. Raw SQL and uploads are not persisted.</Alert>
    <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 1, my: 1}}>
      <TextField size="small" label="Start UTC (ISO 8601)" value={start} disabled={busy} onChange={event => {setStart(event.target.value); setSlow(null);}} />
      <TextField size="small" label="End UTC (ISO 8601)" value={end} disabled={busy} onChange={event => {setEnd(event.target.value); setSlow(null);}} />
      <Button disabled={busy || !consent || !schema || !start || !end} onClick={() => run('slow_table', slowRequest, setSlow)}>Analyze native slow-log table</Button>
      <Button component="label" disabled={busy || !consent}>Choose private slow-log file<input aria-label="Private slow-log file" type="file" hidden
        onChange={event => {setFile(event.target.files?.[0] || null); event.target.value = '';}} /></Button>
      <Typography>{file?.name}</Typography>
      <Button disabled={busy || !consent || !file || !schema || !start || !end} onClick={async () => {
        if(file.size > 1024 * 1024) {setError('Upload at most 1 MiB of UTF-8 native MySQL slow-log text'); return;}
        const token = generation.current;
        try {
          const text = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
          if(token === generation.current) run('slow_file', {...slowRequest, text}, setSlow);
        } catch {if(token === generation.current) setError('The slow-log file is not valid UTF-8');}
      }}>Analyze selected slow-log file</Button>
    </Box>
    {slow && <><Alert severity="info">{slow.source}: {slow.entries} entries; {slow.normalized_entries} normalized, {slow.unparsed?.length || 0} could not be normalized by MySQL.
      {slow.truncated ? ' Input truncated to the latest 100 entries. ' : ' '}{slow.coverage} Window: {JSON.stringify(slow.window)}</Alert>
    <NativeRows label="Slow-log digest analysis" rows={slow.rows} /></>}
  </Box>;
}
MySQLWorkload.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string};
