import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Box} from '../cdeadmin_ui/primitives/Layout';
import {Button} from '../cdeadmin_ui/primitives/Button';
import {Banner} from '../cdeadmin_ui/feedback/Indicators';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';

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
  return <Box style={{padding: 8, borderTop: '1px solid var(--sr-border, rgba(128,128,128,0.25))'}}>
    <h6 style={{margin: '4px 0', fontSize: '0.95rem'}}>Saved DuckDB operation receipts</h6>
    <Banner tone="info">Inspect attachment, extension and database-copy observations after closing their original session.
      These records are read-only. Native acknowledgement and session release do not establish transaction commit.</Banner>
    {error && <Banner tone="error">{error}</Banner>}
    <Button disabled={busy} onClick={() => read({operation: 'list', offset: 0, limit: 25})}>Load saved DuckDB receipts</Button>
    {page && <>
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Saved DuckDB operation receipts"
        rows={(page.receipts || []).map(item => ({
          id: item.receipt.review_id,
          family: item.family,
          state: item.receipt.state,
          session_state: item.original_session.state,
          _raw: item,
        }))}
        columns={[
          {key: 'family', name: 'Operation'},
          {key: 'state', name: 'Last recorded outcome'},
          {key: 'session_state', name: 'Original session'},
          {
            key: '_inspect',
            name: 'Inspect',
            render: (_val, row) => <Button disabled={busy}
              aria-label={'Inspect saved DuckDB receipt ' + row._raw.receipt.review_id}
              onClick={() => read({operation: 'get', review_id: row._raw.receipt.review_id})}>Inspect saved receipt</Button>,
          },
        ]}
        compact
        searchable={false}
        exportable={false}
      />
      <div style={{fontSize: '0.85rem', margin: '4px 0'}}>Recorded receipts: {page.total}. Session state shows the last persisted observation.</div>
      <Button disabled={busy || page.offset === 0} onClick={() => read({operation: 'list', offset: Math.max(0, page.offset - page.limit), limit: page.limit})}>Previous saved receipts</Button>
      <Button disabled={busy || !page.more} onClick={() => read({operation: 'list', offset: page.offset + page.limit, limit: page.limit})}>Next saved receipts</Button>
    </>}
    {selected && <>
      {['unknown', 'unresolved'].includes(selected.outcome_observation) && <Banner tone="warning">No terminal observation was saved.
        Inspect the recorded native acknowledgements. This archive cannot reconnect or repeat the operation.</Banner>}
      <pre aria-label="Saved DuckDB receipt details" style={{whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto'}}>
        {JSON.stringify(selected, null, 2)}</pre>
    </>}
  </Box>;
}

DuckDBOperationReceipts.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired};
