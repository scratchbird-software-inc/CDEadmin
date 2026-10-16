import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';

export default function NativeDataImport({post, databaseTargetId, engine, objects=[]}) {
  const [source, setSource] = useState(''), [destination, setDestination] = useState('');
  const [plan, setPlan] = useState(null), [review, setReview] = useState(null), [receipts, setReceipts] = useState([]);
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const generation = useRef(0);
  useEffect(() => {
    generation.current++; setSource(''); setDestination(''); setPlan(null); setReview(null);
    setReceipts([]); setConfirmed(false); setBusy(false); setError('');
    return () => {generation.current++;};
  }, [post, databaseTargetId, engine]);
  const invalidate = () => {generation.current++; setPlan(null); setReview(null); setConfirmed(false);};
  const read = async event => {
    const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
    invalidate(); const token = generation.current; setBusy(true); setError('');
    try {
      if (file.size > 8 * 1024 * 1024) throw new Error('Native data DDN exceeds 8 MiB');
      const text = await file.text();
      if (token === generation.current) setSource(text);
    } catch (failure) {if (token === generation.current) setError(failure.message);}
    finally {if (token === generation.current) setBusy(false);}
  };
  const run = async action => {
    const token = ++generation.current; setBusy(true); setError('');
    try {
      const request = {database_target_id: databaseTargetId,
        ...(['plan', 'review'].includes(action) ? {source, resource_id: destination,
          ...(action === 'review' ? {execution_sha256: plan.execution_sha256} : {})} :
          action === 'receipts' ? {} : {review_id: review.review_id,
            ...(action === 'apply' ? {review_digest: review.review_digest, confirmed} : {})})};
      const result = await post({action: `${engine}_data_${action}`, request});
      if (token !== generation.current) return;
      if (action === 'plan') {setPlan(result); setReview(null); setConfirmed(false);}
      else if (action === 'receipts') setReceipts(result.receipts);
      else {
        setReview(result); setConfirmed(false);
        setReceipts(values => [result, ...values.filter(item => item.review_id !== result.review_id)].slice(0, 20));
      }
    } catch (failure) {if (token === generation.current) setError(failure.response?.data?.errormsg || failure.message);}
    finally {if (token === generation.current) setBusy(false);}
  };
  let snapshot;
  try {snapshot = source.trim().startsWith('{') ? JSON.parse(source) :
    {format: 'ddn-workspace@1', entry: 'result-1.ddn', view: 'result_1', files: {'result-1.ddn': source}};} catch {snapshot = null;}
  return <Box component="details" sx={{my: 1}}>
    <summary>Import native data DDN</summary>
    <Alert severity="info">Select a native table, read the data capture and review its exact typed values before importing.
      The import inserts and commits once. Native constraints and triggers remain active.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} component="label">Read native data DDN<input hidden type="file" accept=".ddn,.json"
      aria-label={`${engine} native data DDN`} onChange={read} /></Button>
    <TextField select size="small" label="Native destination table" value={destination} disabled={busy}
      onChange={event => {setDestination(event.target.value); invalidate();}}>
      <MenuItem value="">Select a captured table</MenuItem>
      {objects.filter(item => ['table', 'partitioned-table'].includes(item.kind)).map(item =>
        <MenuItem key={item.resource_id} value={item.resource_id}>{(item.path || [item.name]).join('.')}</MenuItem>)}
    </TextField>
    <Button disabled={busy || !source || !destination} onClick={() => run('plan')}>Preview typed import</Button>
    <Button disabled={busy} onClick={() => run('receipts')}>Load data receipts</Button>
    {receipts.length > 0 && <TextField select size="small" label="Saved data receipt" value={review?.review_id || ''} disabled={busy}
      onChange={event => {generation.current++; setReview(receipts.find(item => item.review_id === event.target.value) || null); setConfirmed(false);}}>
      <MenuItem value="">Select saved receipt</MenuItem>
      {receipts.map(item => <MenuItem key={item.review_id} value={item.review_id}>{item.review_id}: {item.state}</MenuItem>)}
    </TextField>}
    {plan && <>
      <Alert severity="info">Destination: {plan.layout.path.join('.')}. Exact {engine} version: {plan.layout.native_version}. Rows: {plan.row_count}.</Alert>
      {plan.source_coverage.partial && <Alert severity="warning">The source contains a bounded sample; additional source rows are omitted.</Alert>}
      {plan.warnings.map(warning => <Alert key={warning} severity="warning">{warning}</Alert>)}
      {snapshot && <Box sx={{height: 350, overflow: 'auto'}}><DDNViewerSurface presentation snapshot={snapshot} /></Box>}
      <Button disabled={busy || !plan.ready_for_review || Boolean(review)} onClick={() => run('review')}>Prepare typed data review</Button>
    </>}
    {review && <>
      <Alert severity={review.state === 'unknown_outcome' ? 'warning' : 'info'}>Receipt {review.review_id}: {review.state}.</Alert>
      <FormControlLabel label="Insert and commit these reviewed rows" control={<Checkbox checked={confirmed}
        disabled={busy || review.state !== 'reviewed'} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || review.state !== 'reviewed' || !confirmed} onClick={() => run('apply')}>Import and commit once</Button>
      <Button disabled={busy} onClick={() => run('receipt')}>Read saved outcome</Button>
      {review.outcome && <Box component="pre" sx={{maxHeight: 260, overflow: 'auto'}}>{JSON.stringify(review.outcome, null, 2)}</Box>}
    </>}
  </Box>;
}
NativeDataImport.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired,
  engine: PropTypes.oneOf(['postgresql', 'duckdb', 'sqlite']).isRequired, objects: PropTypes.array};
