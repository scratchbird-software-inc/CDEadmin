import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FirebirdERD from './FirebirdERD';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import PagedDataGrid from '../cdeadmin_ui/data/PagedDataGrid';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function MySQLCatalog({post, databaseTargetId}) {
  const [result, setResult] = useState(null), [error, setError] = useState('');
  const [requestBusy, setBusy] = useState(false), [includeSystem, setIncludeSystem] = useState(false);
  const [source, setSource] = useState(''), [comparison, setComparison] = useState(null);
  const [baseline, setBaseline] = useState(''), [schemaPlan, setSchemaPlan] = useState(null);
  const [review, setReview] = useState(null), [confirmed, setConfirmed] = useState(false), [receiptId, setReceiptId] = useState('');
  const [metadata, setMetadata] = useState(null), [dataCapture, setDataCapture] = useState(null);
  const [relation, setRelation] = useState(''), [dataMode, setDataMode] = useState('sample'), [rowLimit, setRowLimit] = useState('100');
  const [display, setDisplay] = useState('inventory'), [view, setView] = useState('inventory_1');
  const [relationalReviewBusy, setRelationalReviewBusy] = useState(false);
  const busy = requestBusy || relationalReviewBusy;
  const serial = useRef(0);
  useEffect(() => {
    serial.current++; setDataCapture(null); setRelation(''); setMetadata(null); setResult(null); setSource(''); setComparison(null); setError(''); setBusy(false);
    setBaseline(''); setSchemaPlan(null); setReview(null); setConfirmed(false); setReceiptId('');
    setDisplay('inventory'); setView('inventory_1');
    return () => {serial.current++;};
  }, [post, databaseTargetId]);
  const run = async (compare=false) => {
    const token = ++serial.current;
    setBusy(true); setError('');
    if(!compare) {setReview(null); setConfirmed(false);}
    try {
      const response = await post({action: compare ? 'mysql_catalog_compare' : 'mysql_catalog_export',
        request: {database_target_id: databaseTargetId, include_system: includeSystem, ...(compare ? {source} : {})}});
      if(token !== serial.current) return;
      if(compare) setComparison(response);
      else {setSource(''); setMetadata(null); setDataCapture(null);
        setBaseline(JSON.stringify(response.snapshot)); setSchemaPlan(null);
        setRelation(response.objects?.find(item => ['table', 'view', 'materialized-view'].includes(item.kind))?.resource_id || ''); setResult(response); setComparison(null); setDisplay('inventory'); setView(response.snapshot.view);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'MySQL catalog capture failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const generate = async () => {
    const token = ++serial.current;
    setBusy(true); setError(''); setMetadata(null);
    try {
      const response = await post({action: 'mysql_sql_export', request: {database_target_id: databaseTargetId,
        source: source || JSON.stringify(result.snapshot)}});
      if(token === serial.current) setMetadata(response);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'MySQL metadata generation failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const downloadSQL = () => {
    const payload = metadata.encoded_script ? Uint8Array.from(atob(metadata.encoded_script.data_base64), value => value.charCodeAt(0)) : metadata.script;
    const url = URL.createObjectURL(new Blob([payload], {type: metadata.encoded_script ? 'application/octet-stream' : 'text/plain;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = 'mysql-native-metadata.sql'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const previewChanges = async (validate=false) => {
    const token = ++serial.current;
    setBusy(true); setError(''); setSchemaPlan(null); setReview(null); setConfirmed(false);
    try {
      const response = await post({action: validate ? 'mysql_schema_validate' : 'mysql_schema_plan', request: {database_target_id: databaseTargetId,
        baseline, source: source || JSON.stringify(result.snapshot)}});
      if(token === serial.current) setSchemaPlan(response);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'MySQL native change preview failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const schemaApplication = async action => {
    const token = ++serial.current;
    setBusy(true); setError('');
    try {
      const request = {database_target_id: databaseTargetId};
      if(action === 'mysql_schema_review') Object.assign(request, {
        baseline, source: source || JSON.stringify(result.snapshot), execution_sha256: schemaPlan.execution_sha256});
      else if(action === 'mysql_schema_apply') Object.assign(request, {
        review_id: review.review_id, review_digest: review.review_digest, confirmed});
      else request.review_id = receiptId;
      const response = await post({action, request});
      if(token === serial.current) {setReview(response); setReceiptId(response.review_id); setConfirmed(false);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'MySQL schema receipt request failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const captureData = async () => {
    const token = ++serial.current;
    setBusy(true); setError(''); setDataCapture(null);
    try {
      const response = await post({action: 'mysql_data_capture', request: {database_target_id: databaseTargetId,
        resource_id: relation, mode: dataMode, row_limit: Number(rowLimit)}});
      if(token === serial.current) {setDataCapture(response); setDisplay('data'); setView(response.snapshot.view);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'MySQL relation data capture failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const shown = display === 'relations' ? result?.diagram : display === 'data' ? dataCapture : result;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(shown.snapshot)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = `mysql-${display}.ddn-workspace.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{...compactFormSx, p: 1, overflow: 'auto', flex: 1}}>
    <FormReference formKey="mysql-catalog-ddn" />
    {error && <Alert severity="error">{error}</Alert>}
    <Alert severity="info">Native MySQL metadata on a separate connection. Catalog visibility is privilege filtered and concurrent DDL is not fenced. Documentary comparison does not authorize migration or deletion.</Alert>
    <Box sx={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1}}>
      <FormControlLabel label="Include system objects" control={<Checkbox checked={includeSystem} disabled={busy}
        onChange={event => setIncludeSystem(event.target.checked)} />} />
      <Button disabled={busy || !databaseTargetId} onClick={() => run()}>Capture metadata</Button>
      <Button disabled={busy || !shown?.snapshot} onClick={download}>Download DDN</Button>
      <Button component="label" disabled={busy}>Read DDN<input hidden disabled={busy} type="file" accept=".ddn,.json" aria-label="MySQL catalog DDN file"
        onChange={async event => {
          const file = event.target.files?.[0], token = ++serial.current;
          event.target.value = '';
          if(!file) return;
          setReview(null); setConfirmed(false); setSchemaPlan(null);
          if(file.size > 8 * 1024 * 1024) {setError('Catalog file exceeds 8 MiB'); return;}
          try {const text = await file.text(); if(token === serial.current) {setSource(text); setMetadata(null); setComparison(null); setSchemaPlan(null); setReview(null); setConfirmed(false);}}
          catch {if(token === serial.current) setError('Unable to read catalog file');}
        }} /></Button>
      <Button disabled={busy || !source || !databaseTargetId} onClick={() => run(true)}>Compare with live catalog</Button>
      <Button disabled={busy || !(source || result?.snapshot) || !databaseTargetId} onClick={generate}>Generate native SQL</Button>
      <Button disabled={busy || !metadata?.script_available} onClick={downloadSQL}>Download native SQL</Button>
      <Button component="label" disabled={busy}>Read baseline DDN<input hidden disabled={busy} type="file" accept=".ddn,.json" aria-label="MySQL baseline DDN file"
        onChange={async event => {
          const file = event.target.files?.[0], token = ++serial.current; event.target.value = '';
          if(!file) return;
          setReview(null); setConfirmed(false); setSchemaPlan(null);
          if(file.size > 8 * 1024 * 1024) {setError('Baseline exceeds 8 MiB'); return;}
          try {const text = await file.text(); if(token === serial.current) {setBaseline(text); setSchemaPlan(null); setReview(null); setConfirmed(false);}}
          catch {if(token === serial.current) setError('Unable to read baseline');}
        }} /></Button>
      <Button disabled={busy || !baseline || !(source || result?.snapshot)} onClick={() => previewChanges()}>Preview native changes</Button>
      <Button disabled={busy || !schemaPlan?.ready_for_review} onClick={() => previewChanges(true)}>Validate native changes</Button>
      <TextField select size="small" label="Display" value={display} disabled={busy || !result}
        onChange={event => {setDisplay(event.target.value); setView(event.target.value === 'relations' ? result.diagram.snapshot.view : event.target.value === 'data' ? dataCapture.snapshot.view : result.snapshot.view);}}>
        <MenuItem value="inventory">Native inventory</MenuItem>
        <MenuItem value="relations" disabled={!result?.diagram?.snapshot}>Relations</MenuItem>
        <MenuItem value="data" disabled={!dataCapture?.snapshot}>Captured relation data</MenuItem>
      </TextField>
      {shown?.views && display !== 'relations' && <TextField select size="small" label="DDN view" value={view} disabled={busy} onChange={event => setView(event.target.value)}>
        {shown.views.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>}
    </Box>
    {result && <FormReference formKey="mysql-data-capture">
      <Box sx={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1}}>
        <TextField select size="small" label="Native table or view" value={relation} disabled={busy} sx={{minWidth: 220}}
          onChange={event => setRelation(event.target.value)}>
          {(result.objects || []).filter(item => ['table', 'view', 'materialized-view'].includes(item.kind)).map(item =>
            <MenuItem key={item.resource_id} value={item.resource_id}>{item.kind}: {item.name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Data capture mode" value={dataMode} disabled={busy}
          onChange={event => setDataMode(event.target.value)}>
          <MenuItem value="sample">Bounded sample</MenuItem><MenuItem value="full">Full relation within budget</MenuItem>
        </TextField>
        <TextField size="small" type="number" label="Data row budget" value={rowLimit} disabled={busy} sx={{width: 150}}
          slotProps={{htmlInput: {min: 1, max: 6000, step: 1}}} onChange={event => setRowLimit(event.target.value)} />
        <Button disabled={busy || !relation || !Number.isSafeInteger(Number(rowLimit)) || Number(rowLimit) < 1 || Number(rowLimit) > 6000}
          onClick={captureData}>Capture selected data</Button>
      </Box>
      <Alert severity="info">Data inclusion is explicit. Capture uses a separate read-only transaction; nontransactional tables and view dependencies may have weaker consistency.</Alert>
    </FormReference>}
    {display === 'data' && dataCapture?.warnings?.map(warning => <Alert key={warning} severity="warning">{warning}</Alert>)}
    {(result?.provenance?.warnings || []).map(warning => <Alert key={warning} severity="warning">{warning}</Alert>)}
    {metadata && <Box>
      <Alert severity="info">Native SQL export only. Imported definitions have not been validated against the live server and this does not execute a migration.</Alert>
      {metadata.warnings?.map(warning => <Alert severity="warning" key={warning}>{warning}</Alert>)}
      {metadata.blockers?.map(item => <Alert severity="error" key={item.resource_id + item.reason}>{item.name}: {item.reason}</Alert>)}
      {metadata.encoded_script && <Alert severity="info">Mixed native encodings: download the original bytes and run with mysql --binary-mode --default-character-set=utf8mb4 in a fresh session. This UTF-8 display is a preview.</Alert>}
      {(metadata.script || metadata.script_preview) && <TextField label="Native MySQL metadata script" multiline minRows={6} maxRows={16}
        value={metadata.script || metadata.script_preview} slotProps={{input: {readOnly: true}}} sx={{width: '100%'}} />}
      {!!metadata.prerequisites?.length && <Box sx={{height: 220, overflow: 'auto'}}>
        <PagedDataGrid readOnly gridId="mysql/native-prerequisites" aria-label="MySQL native prerequisites"
          rows={metadata.prerequisites.map((item, index) => ({...item, id: index}))} rowKeyGetter={row => row.id}
          columns={[{key: 'database', name: 'Database', width: 160}, {key: 'name', name: 'Prerequisite', minWidth: 180},
            {key: 'kind', name: 'Kind', minWidth: 160}]} />
      </Box>}
    </Box>}
    {comparison && <Box sx={{height: 280, overflow: 'auto'}}>
      <PagedDataGrid readOnly gridId="mysql/catalog-comparison" aria-label="MySQL catalog differences"
        rows={comparison.changes} rowKeyGetter={row => row.resource_id} columns={[
          {key: 'name', name: 'Native object', minWidth: 180}, {key: 'kind', name: 'Kind', width: 140},
          {key: 'status', name: 'Difference', width: 140},
          {key: 'fields', name: 'Changed native fields', minWidth: 260, renderCell: ({row}) => row.fields.join(', ')},
        ]} />
    </Box>}
    {schemaPlan && <Box>
      <FormReference formKey="mysql-native-schema-preview" />
      <Alert severity="info">Review the displayed native CREATE/ALTER/DROP statements in order. Earlier committed statements remain committed if a later step stops. MySQL DDL commits implicitly. Existing tables use native table locks; views, libraries, events, routines and triggers use cooperating advisory locks. Baselines are revalidated before dispatch; unknown outcomes are never automatically retried.</Alert>
      {schemaPlan.native_validation && <Alert severity={schemaPlan.native_grammar_validated ? 'success' : 'error'}>
        {schemaPlan.native_grammar_validated ? (schemaPlan.native_validation.some(item => item.validation_stage === 'parse-only') ? 'Native grammar accepted; some statements cannot be prepared. Semantic and privilege checks occur on execution. None were executed.' : 'Native PREPARE accepted the change statements; none were executed.') : 'Native PREPARE rejected one or more change statements.'}
      </Alert>}
      {schemaPlan.native_validation?.filter(item => !item.accepted).map(item => <Alert severity="error" key={item.index}>MySQL error {item.error_code}, SQLSTATE {item.sqlstate}</Alert>)}
      {schemaPlan.blockers?.map(item => <Alert severity="error" key={item.resource_id + item.reason}>{item.name}: {item.reason}</Alert>)}
      {schemaPlan.conflicts?.map(item => <Alert severity="error" key={item.resource_id}>Live conflict: {item.reason}</Alert>)}
      {schemaPlan.ignored?.map(item => <Alert severity="info" key={item.resource_id}>{item.reason}</Alert>)}
      {!!schemaPlan.operations?.length && <TextField label="Native MySQL change preview" multiline minRows={4} maxRows={16}
        value={schemaPlan.operations.map(item => item.source + ';').join('\n\n')} slotProps={{input: {readOnly: true}}} sx={{width: '100%'}} />}
    </Box>}
    <Box sx={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1}}>
      <Button disabled={busy || !schemaPlan?.ready_for_review || !schemaPlan.native_grammar_validated ||
        !schemaPlan.operations?.length || schemaPlan.operations.length > 32 || schemaPlan.operations.some(op => !['table','view','library','event','procedure','function','trigger','database','materialized-view'].includes(op.kind) || !['create', 'alter', 'drop'].includes(op.operation))}
      onClick={() => schemaApplication('mysql_schema_review')}>Prepare reviewed change</Button>
      <FormControlLabel label="Confirm reviewed native DDL and implicit commit" control={<Checkbox checked={confirmed}
        disabled={busy || review?.state !== 'reviewed'} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || review?.state !== 'reviewed' || !confirmed}
        onClick={() => schemaApplication('mysql_schema_apply')}>Apply reviewed change</Button>
      <TextField size="small" label="Schema receipt ID" value={receiptId} disabled={busy} sx={{width: 340}}
        onChange={event => {setReceiptId(event.target.value); setReview(null); setConfirmed(false);}} />
      <Button disabled={busy || !receiptId || !databaseTargetId}
        onClick={() => schemaApplication('mysql_schema_receipt')}>Read receipt</Button>
    </Box>
    {schemaPlan?.warnings?.map((warning,index) => <Alert key={index} severity="warning">{warning}</Alert>)}
    {review && <Box>
      <Alert severity={review.state === 'committed' ? 'success' : review.state === 'reviewed' ? 'info' : 'warning'}>
        Schema receipt {review.review_id}: {review.state}. Automatic retry is disabled.
        {review.outcome && ` Rediscovery: ${review.outcome.rediscovery_verified ? 'observed' : 'unverified'}.`}
      </Alert>
      {review.statement_outcomes && <Box sx={{height: 240}}>
        <PagedDataGrid readOnly gridId="mysql/schema-statement-outcomes" aria-label="MySQL migration statement outcomes"
          rows={review.statement_outcomes} rowKeyGetter={row => row.index} columns={[
            {key: 'index', name: 'Order', width: 80}, {key: 'resource_id', name: 'Native object', minWidth: 220},
            {key: 'state', name: 'Observed outcome', minWidth: 180},
          ]} />
      </Box>}
      {review.outcome?.concurrency_warning && <Alert severity="warning">{review.outcome.concurrency_warning}</Alert>}
      {review.outcome?.rejection_reason && <Alert severity="warning">{review.outcome.rejection_reason}</Alert>}
      {review.outcome?.desired_definition_exact_match === false && <Alert severity="warning">
        Native SHOW CREATE differs from the desired text. Review the rediscovered definition before further changes.
      </Alert>}
      {review.outcome?.native_definition && <TextField label="Rediscovered native definition" multiline minRows={3} maxRows={12}
        value={review.outcome.native_definition} slotProps={{input: {readOnly: true}}} sx={{width: '100%'}} />}
    </Box>}
    {result?.diagram?.snapshot && <Box sx={{display: display === 'relations' ? 'block' : 'none'}}>
      <FirebirdERD engine="mysql" diagram={result.diagram} post={post} databaseTargetId={databaseTargetId}
        onReviewBusyChange={setRelationalReviewBusy}
        onReview={handoff => {serial.current++; setBaseline(handoff.baseline); setSource(handoff.desired);
          setSchemaPlan(null); setReview(null); setConfirmed(false); setDisplay('inventory'); setView(result.snapshot.view);}} />
    </Box>}
    {shown?.snapshot && display !== 'relations' && <Box sx={{height: 500, minHeight: 250, overflow: 'auto'}}>
      <DDNViewerSurface presentation snapshot={{...shown.snapshot, view,
        entry: shown.views.find(item => item.id === view)?.entry || shown.snapshot.entry}} />
    </Box>}
  </Box>;
}
MySQLCatalog.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string};
