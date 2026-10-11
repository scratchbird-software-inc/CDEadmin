import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, TextField, Table, TableBody, TableCell, TableHead, TableRow, TablePagination} from '@mui/material';
import gettext from 'sources/gettext';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import FirebirdCatalogDesigner from './FirebirdCatalogDesigner';

export default function FirebirdSchemaPlan({baseline, post, generation, onCatalogRefresh, disabled, databaseTargetId, designRequest}) {
  const [desired, setDesired] = useState('');
  const [designBaseline, setDesignBaseline] = useState(null);
  const [filename, setFilename] = useState('');
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(0);
  const [review, setReview] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [receiptId, setReceiptId] = useState('');
  const token = useRef(0);
  useEffect(() => {
    token.current++;
    setDesired(''); setDesignBaseline(null); setFilename(''); setPlan(null); setError(''); setBusy(false);
    setReview(null); setConfirmed(false); setAttempted(false); setReceiptId('');
    return () => {token.current++;};
  }, [baseline, post]);
  useEffect(() => {
    if (!designRequest) return;
    token.current++; setDesired(designRequest.desired); setDesignBaseline(designRequest.baseline);
    setFilename('Relational DDN design'); setPlan(null); setReview(null); setError(''); setBusy(false);
    setConfirmed(false); setAttempted(false); setReceiptId('');
  }, [designRequest]);
  const load = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if(!file) return;
    const requestToken = ++token.current;
    setBusy(true); setError(''); setPlan(null); setDesired(''); setDesignBaseline(null); setFilename('');
    setReview(null); setConfirmed(false); setAttempted(false);
    try {
      if(file.size > 8 * 1024 * 1024) throw new Error(gettext('Desired document exceeds 8 MiB.'));
      const source = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
      if(token.current === requestToken) {setDesired(source); setFilename(file.name);}
    } catch(err) {if(token.current === requestToken) setError(err.message);}
    finally {if(token.current === requestToken) setBusy(false);}
  };
  const preview = async () => {
    const requestToken = ++token.current;
    setBusy(true); setPlan(null); setError('');
    setReview(null); setConfirmed(false); setAttempted(false);
    try {
      const response = await post({action: 'firebird_schema_plan', request: {generation, baseline: designBaseline || baseline, desired, refresh: true}});
      if(token.current !== requestToken) return;
      setPlan(response); setPage(0);
      await onCatalogRefresh?.();
    } catch(err) {
      if(token.current === requestToken) setError(err.response?.data?.errormsg || err.message || gettext('Schema planning failed.'));
    } finally {if(token.current === requestToken) setBusy(false);}
  };
  const application = async (action, savedId = null) => {
    const requestToken = ++token.current;
    setBusy(true); setError('');
    if(action === 'firebird_schema_apply') setAttempted(true);
    const request = action === 'firebird_schema_review' ? {
      baseline: designBaseline || baseline, desired, generation, execution_sha256: plan.execution_sha256,
      database_target_id: plan.target.database_target_id,
    } : {review_id: savedId || review.review_id, database_target_id: savedId ? databaseTargetId : review.plan.target.database_target_id,
      ...(action === 'firebird_schema_apply' ? {review_digest: review.review_digest, confirmed} : {})};
    try {
      const response = await post({action, request});
      if(token.current !== requestToken) return;
      setReview(response); setReceiptId(response.review_id);
      if(savedId) {setPlan(response.plan); setConfirmed(false); setAttempted(response.state !== 'reviewed');}
      if(action !== 'firebird_schema_receipt') await onCatalogRefresh?.();
    } catch(err) {
      if(token.current === requestToken) setError(err.response?.data?.errormsg || err.message || gettext('Schema application request failed. Retrieve the receipt before taking further action.'));
    } finally {if(token.current === requestToken) setBusy(false);}
  };
  const download = (content, name) => {
    const url = URL.createObjectURL(new Blob([content], {type: 'text/plain;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = url; link.download = name;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const rows = plan ? [...plan.blockers.map((item) => ({...item, state: 'blocked', detail: `${item.reason} ${item.fields.join(', ')}`})),
    ...plan.operations.map((item) => ({...item, state: item.operation, detail: item.statements.join(';\n') + (item.deferred_statements?.length ? '\n-- Final definition phase (after primary definitions):\n' + item.deferred_statements.join(';\n') : '')}))] : [];
  return <Box sx={{display: 'flex', flexDirection: 'column', gap: 1}}>
    <FormReference formKey="firebird-schema-plan" />
    <Alert severity="info">{gettext('Load an edited DDN document to compare with the captured baseline and current database. Review generated statements before preparing an application.')}</Alert>
    <Box component="details">
      <Box component="summary" sx={{cursor: 'pointer'}}>{gettext('Supported Firebird changes')}</Box>
      <Box sx={{py: 1}}>{gettext('Firebird 5, dialect 3: explicitly confirmed column/domain renames with native identity checks; explicit confirmed removal in dependency order; relation/database/DDL trigger definitions and activation; standalone procedure/function signatures, bodies, security and comments; package headers and bodies; column defaults, nullability, identity modes, computed expressions, scalar types, explicit domain rebinding, additions and final positioning; table properties and creation with named constraints and indexes; existing-table CHECK/key creation and replacement with backing index definitions; views; scalar/array domain creation, explicit scalar domain type conversion and domain defaults/checks/nullability; BLOB filter declarations; legacy external-function declarations, library bindings and comments; user collation creation and comments; roles and system privileges; explicit native grant/revoke reviews with grantor, option and cascade acknowledgement; sequences; exceptions; standalone indexes and index state/comments. Declared creation dependencies and final foreign-key phases support related new tables. Unadmitted changes are listed as blockers. Edit native_json properties; documentary DDL and diagram labels are not executed.')}</Box>
    </Box>
    <Box>
      <FirebirdCatalogDesigner baseline={baseline} post={post} databaseTargetId={databaseTargetId} disabled={disabled || busy} onReview={(source, original) => {
        setDesignBaseline(original);
        token.current++; setDesired(source); setFilename('DDN catalog design'); setPlan(null); setError('');
        setReview(null); setConfirmed(false); setAttempted(false); setReceiptId('');
      }} />
      <Button component="label" disabled={disabled || busy || !baseline}>{gettext('Read desired DDN')}
        <input hidden type="file" accept=".ddn,.json,text/plain,application/json" aria-label={gettext('Desired DDN file')}
          disabled={disabled || busy || !baseline} onChange={load} />
      </Button>
      {filename && <span>{filename}</span>}
      <Button disabled={disabled || busy || !baseline || !desired || !generation} onClick={preview}>{gettext('Preview native changes')}</Button>
    </Box>
    <Box sx={{display: 'flex', gap: 1}}>
      <TextField size="small" label={gettext('Saved application receipt ID')} value={receiptId}
        disabled={busy || disabled} onChange={(event) => setReceiptId(event.target.value)} />
      <Button disabled={busy || disabled || !receiptId.trim()} onClick={() => application('firebird_schema_receipt', receiptId.trim())}>
        {gettext('Open saved receipt')}</Button>
    </Box>
    {error && <Alert severity="error">{error}</Alert>}
    {plan && <>
      <Alert severity={plan.status === 'blocked' ? 'warning' : 'info'}>{gettext('Plan status')}: {plan.status}. {gettext('Engine version')}: {plan.engine_version}</Alert>
      <Box>{gettext('Catalog observation')}: {plan.observation}. {gettext('Coverage')}: {plan.catalog_coverage}</Box>
      {plan.warnings.map((warning, index) => <Alert severity="warning" key={index}>{warning}</Alert>)}
      <Box>{Object.entries(plan.statistics).map(([key, value]) => `${key}: ${value}`).join(' · ')}</Box>
      <Box>
        <Button onClick={() => download(JSON.stringify(plan, null, 2), 'firebird-schema-plan.json')}>{gettext('Download review plan')}</Button>
        {plan.status === 'review-ready' && plan.script && <Button onClick={() => download(plan.script, 'firebird-schema-review.sql')}>{gettext('Download review SQL')}</Button>}
        {plan.status === 'review-ready' && plan.execution_sha256 && <Button disabled={busy || disabled || attempted}
          onClick={() => application('firebird_schema_review')}>{gettext('Prepare application')}</Button>}
      </Box>
      {review && <Box>
        <Alert severity={review.state === 'unknown_outcome' ? 'warning' : 'info'}>
          {gettext('Database')}: {review.database}. {gettext('Application state')}: {review.state}.
          {' '}{gettext('Receipt')}: {review.review_id}
        </Alert>
        {review.state === 'reviewed' && !attempted && <>
          <FormControlLabel label={gettext('I have reviewed these changes and authorize applying them to this database')}
            control={<Checkbox checked={confirmed} disabled={busy || disabled} onChange={(event) => setConfirmed(event.target.checked)} />} />
          <Button disabled={busy || disabled || !confirmed} onClick={() => application('firebird_schema_apply')}>{gettext('Apply reviewed changes')}</Button>
        </>}
        <Button disabled={busy || disabled} onClick={() => application('firebird_schema_receipt')}>{gettext('Retrieve application receipt')}</Button>
        <Button onClick={() => download(JSON.stringify(review, null, 2), 'firebird-schema-application.json')}>{gettext('Download application receipt')}</Button>
        {review.outcome && <Box component="pre" sx={{whiteSpace: 'pre-wrap'}}>{JSON.stringify(review.outcome, null, 2)}</Box>}
      </Box>}
      <Table size="small" aria-label={gettext('Native schema plan')}>
        <TableHead><TableRow><TableCell>{gettext('Object')}</TableCell><TableCell>{gettext('State')}</TableCell><TableCell>{gettext('SQL or blocker')}</TableCell></TableRow></TableHead>
        <TableBody>{rows.slice(page * 25, (page + 1) * 25).map((item) => <TableRow key={item.resource_id}>
          <TableCell>{item.resource_id}</TableCell><TableCell>{item.state}</TableCell><TableCell sx={{whiteSpace: 'pre-wrap'}}>
            {item.detail}
            {item.security_changes && <Box sx={{mt: 1}}>
              <Box>{gettext('System privileges added')}: {item.security_changes.added_system_privileges.join(', ') || gettext('None')}</Box>
              <Box>{gettext('System privileges removed')}: {item.security_changes.removed_system_privileges.join(', ') || gettext('None')}</Box>
              <Box>{gettext('Ownership')}: {item.security_changes.ownership}</Box>
              <Box>{gettext('Memberships')}: {item.security_changes.memberships}</Box>
              <Box>{gettext('Required authority')}: {item.permissions}</Box>
            </Box>}
          </TableCell>
        </TableRow>)}</TableBody>
      </Table>
      <TablePagination component="div" count={rows.length} page={page} rowsPerPage={25}
        rowsPerPageOptions={[25]} onPageChange={(_event, value) => setPage(value)} />
    </>}
  </Box>;
}
FirebirdSchemaPlan.propTypes = {baseline: PropTypes.string, designRequest: PropTypes.object, post: PropTypes.func.isRequired,
  generation: PropTypes.string, databaseTargetId: PropTypes.string, onCatalogRefresh: PropTypes.func, disabled: PropTypes.bool};
