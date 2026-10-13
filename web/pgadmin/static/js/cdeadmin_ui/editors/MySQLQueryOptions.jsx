import PropTypes from 'prop-types';
import {Alert, Box, Table, TableBody, TableCell, TableRow} from '@mui/material';

export default function MySQLQueryOptions({transaction, engine='mysql'}) {
  const title = engine === 'mariadb' ? 'MariaDB' : 'MySQL';
  const native = transaction?.provider_payload;
  const observedBoolean = value => typeof value === 'boolean' ? (value ? 'On' : 'Off') : 'Not observed';
  return <Box aria-label={`${title} query options`}>
    <Table size="small" aria-label={`${title} session observation`} sx={{maxWidth: 520}}>
      <TableBody>
        <TableRow><TableCell component="th" scope="row">Session state</TableCell><TableCell>{native?.state || 'Not observed'}</TableCell></TableRow>
        <TableRow><TableCell component="th" scope="row">Autocommit (observed)</TableCell><TableCell>{observedBoolean(native?.autocommit)}</TableCell></TableRow>
        <TableRow><TableCell component="th" scope="row">In transaction (observed)</TableCell><TableCell>{observedBoolean(native?.in_transaction)}</TableCell></TableRow>
      </TableBody>
    </Table>
    <Box sx={{py: 0.5}}>Use the transaction-state toolbar button to refresh this observation. Values describe that observation, not a guarantee about later statements.</Box>
    <Alert severity="info">{title} DDL can implicitly commit. Rollback does not undo changes to nontransactional tables. {engine === 'mariadb' ? 'ANALYZE FORMAT=JSON executes the statement; EXPLAIN FORMAT=JSON requests its plan.' : 'EXPLAIN ANALYZE executes the statement; JSON EXPLAIN requests its plan.'}</Alert>
    <Box sx={{py: 0.5}}>Parameters use {engine === 'mariadb' ? '? or %s' : '%s'} with an ordered JSON array, or %(name)s with a JSON object. Script parsing and delimiters use the {title} language binding.</Box>
  </Box>;
}
MySQLQueryOptions.propTypes = {engine: PropTypes.oneOf(['mysql', 'mariadb']), transaction: PropTypes.object};
