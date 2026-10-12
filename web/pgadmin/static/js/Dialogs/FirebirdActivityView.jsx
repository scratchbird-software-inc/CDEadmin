import {useMemo, useState} from 'react';
import FirebirdStatementDetails from './FirebirdStatementDetails';
import PropTypes from 'prop-types';
import {Alert, Box, MenuItem, TextField} from '@mui/material';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {FIREBIRD_ACTIVITY, firebirdActivityFiles} from '../cdeadmin_ui/integrations/ddn/firebirdActivity';
import {RANK_FIELDS, firebirdRankingFiles} from '../cdeadmin_ui/integrations/ddn/firebirdRanking';
import {firebirdPublicationFiles} from '../cdeadmin_ui/integrations/ddn/firebirdPublications';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdActivityView({snapshot, serverId, targetId}) {
  const [category, setCategory] = useState('attachment_details');
  const [rankMetric, setRankMetric] = useState('');
  const [filter, setFilter] = useState('');
  const sample = snapshot.samples?.at(-1);
  const group = category === 'findings' && ['available', 'partial'].includes(sample?.status) ?
    {status: 'available', values: {rows: sample.findings || []}, observed_at: sample.ended_at} :
    sample?.groups?.[category];
  const files = useMemo(() => firebirdActivityFiles(sample, category, filter), [sample, category, filter]);
  const metric = RANK_FIELDS[category]?.includes(rankMetric) ? rankMetric : RANK_FIELDS[category]?.[0];
  const ranking = useMemo(() => firebirdRankingFiles(sample, category, metric), [sample, category, metric]);
  const publications = useMemo(() => firebirdPublicationFiles(sample), [sample]);
  const fresh = snapshot.state === 'collecting' && Number.isFinite(snapshot.sample_age_seconds) &&
    snapshot.sample_age_seconds <= snapshot.stale_after_seconds;
  return <Box sx={{minHeight: 350, flexShrink: 0}}>
    <FormReference formKey="firebird-activity-details" />
    <Alert severity={fresh ? 'info' : 'warning'}>
      {fresh ? 'Latest collector snapshot' : 'Past or unavailable collector snapshot'}: {sample?.ended_at || 'Unavailable'}.
      Coverage: {sample?.coverage || 'Unknown'}. Source: {group?.status || 'Unavailable'}.
      Group observed: {group?.observed_at || sample?.started_at || 'Unavailable'}.
      {group?.age_seconds != null && ` Inventory age at sample: ${group.age_seconds} seconds.`}
      Native timestamps retain their source timezone semantics.
      {group?.values?.collector_excluded && ' Collector excluded.'}
      {group?.values?.truncated && ' Truncated to 100 visible rows in native query order.'}
    </Alert>
    <TextField select size="small" label="Activity category" value={category}
      onChange={(event) => setCategory(event.target.value)} sx={{my: 1}}>
      {FIREBIRD_ACTIVITY.map((item) => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
    </TextField>
    {RANK_FIELDS[category] && <TextField select size="small" label="Rank captured observations by" value={metric}
      onChange={(event) => setRankMetric(event.target.value)} sx={{my: 1, ml: 1}}>
      {RANK_FIELDS[category].map((field) => <MenuItem key={field} value={field}>{field.replaceAll('_', ' ')}</MenuItem>)}
    </TextField>}
    {ranking && <DDNViewerSurface files={ranking} entry="ranking.ddn" view="ranking" presentation />}
    {['publication_details', 'publication_table_details'].includes(category) && <>
      <Alert severity="info">Publication and membership inventories are bounded independently.
        {sample?.groups?.publication_details?.values?.truncated && ' Publication inventory truncated.'}
        {sample?.groups?.publication_table_details?.values?.truncated && ' Membership inventory truncated.'}
        {sample?.groups?.publication_details?.status !== 'available' && ' Publication attributes unavailable.'}
        {sample?.groups?.publication_table_details?.status !== 'available' && ' Membership source unavailable.'}
      </Alert>
      <DDNViewerSurface files={publications} entry="publications.ddn" view="publications" presentation />
    </>}
    <TextField size="small" label="Filter captured detail rows (charts retain full capture)" value={filter}
      onChange={(event) => setFilter(event.target.value)} sx={{my: 1}} />
    <Box>Native state: 0 idle, 1 active; statement state 2 is stalled and does not establish a lock wait.</Box>
    {['statement_details', 'compiled_details'].includes(category) && serverId && targetId && <FirebirdStatementDetails
      key={`${serverId}:${targetId}:${category}`} serverId={serverId} targetId={targetId} sample={sample}
      compiled={category === 'compiled_details'} />}
    <DDNViewerSurface files={files} entry="activity.ddn" view="activity" presentation />
  </Box>;
}
FirebirdActivityView.propTypes = {snapshot: PropTypes.object.isRequired, serverId: PropTypes.number, targetId: PropTypes.string};
