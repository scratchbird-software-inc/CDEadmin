import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, MenuItem, TextField} from '@mui/material';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {RANK_FIELDS, firebirdRankingFiles, fleetRankingSample, fleetVersionSample} from '../cdeadmin_ui/integrations/ddn/firebirdRanking';

export default function FirebirdDatabaseRanking({snapshot, engineMode=false}) {
  const [metric, setMetric] = useState('allocated_bytes');
  const files = useMemo(() => metric === 'version_distribution' ?
    firebirdRankingFiles(fleetVersionSample(snapshot), 'version_distribution', 'count') :
    firebirdRankingFiles(fleetRankingSample(snapshot, engineMode), 'endpoint_databases', metric), [snapshot, engineMode, metric]);
  return <Box sx={{flexShrink: 0}}>
    <Alert severity="info">Rankings cover current identified database observations. Aliases are deduplicated within each
      registered endpoint; different endpoints may still reach the same physical database. Rates have independent
      observation windows, shown in database detail; they are not a synchronized cluster total.</Alert>
    <TextField select size="small" label="Rank observed databases by" value={metric}
      onChange={(event) => setMetric(event.target.value)} sx={{my: 1}}>
      {RANK_FIELDS.endpoint_databases.map((field) => <MenuItem key={field} value={field}>{field.replaceAll('_', ' ')}</MenuItem>)}
      {engineMode && <MenuItem value="version_distribution">Registered endpoint version / architecture distribution</MenuItem>}
    </TextField>
    <DDNViewerSurface files={files} entry="ranking.ddn" view="ranking" presentation />
  </Box>;
}
FirebirdDatabaseRanking.propTypes = {snapshot: PropTypes.object, engineMode: PropTypes.bool};
