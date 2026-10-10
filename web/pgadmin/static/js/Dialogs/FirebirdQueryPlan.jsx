// Native Firebird optimizer observations; never reconstructed from query rows.
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Alert, Box, Typography} from '@mui/material';

export default function FirebirdQueryPlan({result}) {
  if (!result) return null;
  return <Box aria-label={gettext('Firebird query plan')} sx={{mt: 1}}>
    <Alert severity="info">{gettext('Prepared only: the statement was not executed and parameter values were not bound. No commit or rollback was requested.')}
      {' '}{result.transaction_started ? gettext('Preparation started a retained transaction.') : gettext('Preparation used the existing transaction.')}
    </Alert>
    <Box>{gettext('Statement type:')} {result.statement_type}; {gettext('Parameters:')} {result.parameter_count}; {gettext('Output columns:')} {result.column_count}; {gettext('Client SQL dialect:')} {result.client_sql_dialect}</Box>
    {['legacy', 'detailed'].map((format) => <Box key={format}>
      <Typography component="h4">{format === 'legacy' ? gettext('Legacy optimizer plan') : gettext('Detailed optimizer plan')}</Typography>
      {result[format]?.truncated && <Alert severity="warning">{gettext('The native engine truncated this plan. The displayed text is incomplete.')}</Alert>}
      {!result[format]?.supplied && <Alert severity="info">{gettext('The native engine supplied no plan text for this format.')}</Alert>}
      <Box component="pre" aria-label={format === 'legacy' ? gettext('Legacy plan text') : gettext('Detailed plan text')}
        sx={{whiteSpace: 'pre-wrap', overflow: 'auto', maxHeight: 420}}>{result[format]?.text || ''}</Box>
    </Box>)}
  </Box>;
}
FirebirdQueryPlan.propTypes = {result: PropTypes.object};
