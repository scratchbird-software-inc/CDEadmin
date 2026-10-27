import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';

export default function MySQLDataImport({post, databaseTargetId, engine='mysql'}) {
  const label = engine === 'mariadb' ? 'MariaDB' : 'MySQL';
  const [source, setSource] = useState(''), [table, setTable] = useState('');
  const [allow, setAllow] = useState(false), [confirmed, setConfirmed] = useState(false);
  const [plan, setPlan] = useState(null), [review, setReview] = useState(null);
  const [receipts, setReceipts] = useState([]);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const serial = useRef(0);
  useEffect(() => {
    serial.current++; setSource(''); setTable(''); setAllow(false); setConfirmed(false);
    setPlan(null); setReview(null); setReceipts([]); setError(''); setBusy(false);
    return () => {serial.current++;};
  }, [post, databaseTargetId, engine]);
  const invalidate = () => {setPlan(null); setReview(null); setConfirmed(false);};
  const load = async event => {
    const file = event.target.files?.[0]; event.target.value = ''; if(!file) return;
    const token = serial.current;
    try {
      if(file.size > 8 * 1024 * 1024) throw new Error('Data DDN exceeds 8 MiB');
      const value = await file.text();
      if(token === serial.current) {setSource(value); invalidate(); setError('');}
    } catch(failure) {if(token === serial.current) setError(failure.message);}
  };
  const run = async action => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const request = action === 'receipts' ? {database_target_id: databaseTargetId} : action === 'plan' || action === 'review' ? {database_target_id: databaseTargetId, source,
        ...(table ? {table} : {}), allow_nontransactional: allow,
        ...(action === 'review' ? {execution_sha256: plan.execution_sha256} : {})} :
        {database_target_id: databaseTargetId, review_id: review.review_id,
          ...(action === 'apply' ? {review_digest: review.review_digest, confirmed} : {})};
      const result = await post({action: `${engine}_data_${action}`, request});
      if(token !== serial.current) return;
      if(action === 'plan') {setPlan(result); setReview(null); setConfirmed(false);}
      else if(action === 'receipts') setReceipts(result.receipts);
      else {
        setReview(result);
        setReceipts(values => [result, ...values.filter(item => item.review_id !== result.review_id)].slice(0, 20));
      }
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Native data import unavailable');}
    finally {if(token === serial.current) setBusy(false);}
  };
  return <Box component="details" sx={{my: 1}}>
    <summary>Import native {label} data DDN</summary>
    <Alert severity="info">Read a native relation data capture, review its exact destination and explicitly import and commit.
      Constraints and triggers remain active. This inserts rows; it never replaces or clears a table. Unknown outcomes cannot be retried.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={() => run('receipts')}>Load recent data receipts</Button>
    {receipts.length > 0 && <TextField select size="small" label="Saved data receipt" value={review?.review_id || ''} disabled={busy}
      onChange={event => {const selected = receipts.find(item => item.review_id === event.target.value);
        setReview(selected || null); setPlan(selected?.plan || null); setConfirmed(false);}}>
      <MenuItem value="">Select saved receipt</MenuItem>
      {receipts.map(item => <MenuItem key={item.review_id} value={item.review_id}>{item.review_id}: {item.state}</MenuItem>)}
    </TextField>}
    <Button component="label" disabled={busy}>Read native data DDN<input type="file" hidden accept=".json,.ddn" aria-label={`Native ${label} data DDN`} onChange={load} /></Button>
    <TextField size="small" label="Destination table (blank uses captured name)" value={table} disabled={busy}
      onChange={event => {setTable(event.target.value); invalidate();}} />
    <FormControlLabel label="Acknowledge nontransactional table effects" control={<Checkbox checked={allow} disabled={busy}
      onChange={event => {setAllow(event.target.checked); invalidate();}} />} />
    <Button disabled={busy || !source} onClick={() => run('plan')}>Preview native data import</Button>
    {plan && <>
      <Alert severity="info">Destination: {plan.database}.{plan.table}. Rows: {plan.row_count}. Storage: {plan.storage_engine}.</Alert>
      {plan.warnings?.map(warning => <Alert severity="warning" key={warning}>{warning}</Alert>)}
      <Button disabled={busy || !plan.ready_for_review || Boolean(review)} onClick={() => run('review')}>Prepare data review</Button>
    </>}
    {review && <>
      <Alert severity="info">Data receipt {review.review_id}: {review.state}.</Alert>
      <FormControlLabel label="Insert and commit these reviewed rows" control={<Checkbox checked={confirmed}
        disabled={busy || review.state !== 'reviewed'} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || !confirmed || review.state !== 'reviewed'} onClick={() => run('apply')}>Import and commit once</Button>
      <Button disabled={busy} onClick={() => run('receipt')}>Read data receipt</Button>
      {review.outcome && <Box component="pre" sx={{overflow: 'auto', maxHeight: 300}}>{JSON.stringify(review.outcome, null, 2)}</Box>}
    </>}
  </Box>;
}
MySQLDataImport.propTypes = {engine: PropTypes.oneOf(['mysql', 'mariadb']), post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired};
