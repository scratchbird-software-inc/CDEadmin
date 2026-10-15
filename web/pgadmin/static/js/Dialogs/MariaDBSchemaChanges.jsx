import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import PagedDataGrid from '../cdeadmin_ui/data/PagedDataGrid';

export default function MariaDBSchemaChanges({post, databaseTargetId, baseline, source}) {
  const [plan, setPlan] = useState(null), [receipt, setReceipt] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [confirmed, setConfirmed] = useState(false), [maintenance, setMaintenance] = useState(false);
  const serial = useRef(0);
  useEffect(() => {
    serial.current++; setPlan(null); setReceipt(null); setBusy(false); setError(''); setConfirmed(false); setMaintenance(false);
    return () => {serial.current++;};
  }, [post, databaseTargetId, baseline, source]);
  const request = async action => {
    const token = ++serial.current;
    setBusy(true); setError('');
    try {
      const body = {database_target_id: databaseTargetId};
      if(['mariadb_schema_validate', 'mariadb_schema_review'].includes(action)) Object.assign(body, {baseline, source});
      if(action === 'mariadb_schema_review') body.execution_sha256 = plan.execution_sha256;
      if(['mariadb_schema_apply', 'mariadb_schema_receipt'].includes(action)) body.review_id = receipt.review_id;
      if(action === 'mariadb_schema_apply') Object.assign(body, {review_digest: receipt.review_digest,
        confirmed, maintenance_window_confirmed: maintenance});
      const value = await post({action, request: body});
      if(token !== serial.current) return;
      if(action === 'mariadb_schema_validate') {setPlan(value); setReceipt(null); setConfirmed(false); setMaintenance(false);}
      else setReceipt(value);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Native MariaDB schema operation failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  return <Box aria-label="MariaDB reviewed schema changes" sx={{py: 1}}>
    <FormReference formKey="mariadb-schema-changes" />
    <Alert severity="warning">MariaDB DDL commits independently. Table removal can destroy data and temporal history. Cooperating advisory locks do not fence external DDL. Use an exclusive DDL maintenance window.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center'}}>
      <Button disabled={busy || !baseline || !source} onClick={() => request('mariadb_schema_validate')}>Preview and validate native changes</Button>
      <Button disabled={busy || !plan?.ready_for_review || !plan?.native_grammar_validated || !!receipt}
        onClick={() => request('mariadb_schema_review')}>Prepare reviewed change</Button>
      <FormControlLabel label="Confirm reviewed native changes" control={<Checkbox checked={confirmed}
        disabled={busy || receipt?.state !== 'reviewed'} onChange={event => setConfirmed(event.target.checked)} />} />
      <FormControlLabel label="Exclusive DDL maintenance window confirmed" control={<Checkbox checked={maintenance}
        disabled={busy || receipt?.state !== 'reviewed'} onChange={event => setMaintenance(event.target.checked)} />} />
      <Button disabled={busy || receipt?.state !== 'reviewed' || !confirmed || !maintenance}
        onClick={() => request('mariadb_schema_apply')}>Apply reviewed change</Button>
      <Button disabled={busy || !receipt?.review_id} onClick={() => request('mariadb_schema_receipt')}>Read receipt</Button>
    </Box>
    {plan?.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
    {[...(plan?.blockers || []), ...(plan?.conflicts || [])].map((item, index) => <Alert key={index} severity="error">{item.name || item.resource_id}: {item.reason}</Alert>)}
    {plan?.native_validation?.filter(item => !item.accepted).map(item => <Alert key={item.index} severity="error">Native validation rejected statement {item.index + 1}: {item.error_type} ({item.error_code}).</Alert>)}
    {!!plan?.operations?.length && <Box sx={{height: 220}}><PagedDataGrid readOnly gridId="mariadb/schema-plan"
      aria-label="MariaDB native schema statements" rows={plan.operations} rowKeyGetter={row => row.resource_id}
      columns={[{key: 'name', name: 'Object', width: 160}, {key: 'operation', name: 'Operation', width: 100},
        {key: 'source', name: 'Native statement', minWidth: 420}]} /></Box>}
    {receipt && <TextField label="Native schema receipt" value={JSON.stringify(receipt, null, 2)} fullWidth multiline
      minRows={4} maxRows={12} slotProps={{input: {readOnly: true}}} />}
  </Box>;
}
MariaDBSchemaChanges.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired,
  baseline: PropTypes.string, source: PropTypes.string};
