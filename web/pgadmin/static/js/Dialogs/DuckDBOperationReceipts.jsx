import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Table, TableBody, TableCell, TableHead, TableRow, Typography} from '@mui/material';

export default function DuckDBOperationReceipts({post, databaseTargetId}) {
  const [page, setPage] = useState(null), [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const generation = useRef(0);
  useEffect(() => {
    generation.current++; setPage(null); setSelected(null); setBusy(false); setError('');
    return () => {generation.current++;};
  }, [post, databaseTargetId]);
  const read = async request => {
    const token = generation.current; setBusy(true); setError('');
    try {
      const value = await post({action: 'duckdb_session_receipts', database_target_id: databaseTargetId, request});
      if(token === generation.current) {
        if(request.operation === 'list') setPage(value);
        else setSelected(value);
      }
    } catch(failure) {
      if(token === generation.current) setError(failure.response?.data?.errormsg || failure.message || 'Native operation receipts are unavailable.');
    } finally {if(token === generation.current) setBusy(false);}
  };
  return <Box sx={{p: 1, borderTop: '1px solid', borderColor: 'divider'}}>
    <Typography variant="h6">Saved DuckDB operation receipts</Typography>
    <Alert severity="info">Inspect attachment, extension and database-copy observations after closing their original session.
      These records are read-only. Native acknowledgement and session release do not establish transaction commit.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={() => read({operation: 'list', offset: 0, limit: 25})}>Load saved DuckDB receipts</Button>
    {page && <>
      <Table size="small" aria-label="Saved DuckDB operation receipts"><TableHead><TableRow>
        <TableCell>Operation</TableCell><TableCell>Last recorded outcome</TableCell><TableCell>Original session</TableCell><TableCell />
      </TableRow></TableHead><TableBody>{page.receipts.map(item => <TableRow key={item.receipt.review_id}>
        <TableCell>{item.family}</TableCell><TableCell>{item.receipt.state}</TableCell>
        <TableCell>{item.original_session.state}</TableCell><TableCell><Button disabled={busy}
          aria-label={'Inspect saved DuckDB receipt ' + item.receipt.review_id}
          onClick={() => read({operation: 'get', review_id: item.receipt.review_id})}>Inspect saved receipt</Button></TableCell>
      </TableRow>)}</TableBody></Table>
      <Typography variant="body2">Recorded receipts: {page.total}. Session state shows the last persisted observation.</Typography>
      <Button disabled={busy || page.offset === 0} onClick={() => read({operation: 'list', offset: Math.max(0, page.offset - page.limit), limit: page.limit})}>Previous saved receipts</Button>
      <Button disabled={busy || !page.more} onClick={() => read({operation: 'list', offset: page.offset + page.limit, limit: page.limit})}>Next saved receipts</Button>
    </>}
    {selected && <>
      {['unknown', 'unresolved'].includes(selected.outcome_observation) && <Alert severity="warning">No terminal observation was saved.
        Inspect the recorded native acknowledgements. This archive cannot reconnect or repeat the operation.</Alert>}
      <Box component="pre" aria-label="Saved DuckDB receipt details" sx={{whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto'}}>
        {JSON.stringify(selected, null, 2)}</Box>
    </>}
  </Box>;
}

DuckDBOperationReceipts.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired};
