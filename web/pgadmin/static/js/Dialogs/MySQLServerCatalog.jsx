import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function MySQLServerCatalog({post, engine='mysql'}) {
  const engineName = engine === 'mariadb' ? 'MariaDB' : 'MySQL';
  const identityKey = engine === 'mariadb' ? 'server_uid' : 'server_uuid';
  const [result, setResult] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [system, setSystem] = useState(true), [targets, setTargets] = useState([]), [scope, setScope] = useState('server');
  const [view, setView] = useState('inventory_1');
  const [baseline, setBaseline] = useState(''), [source, setSource] = useState('');
  const [plan, setPlan] = useState(null), [review, setReview] = useState(null), [confirmed, setConfirmed] = useState(false);
  const [receipts, setReceipts] = useState([]);
  const serial = useRef(0);
  useEffect(() => {
    serial.current++; setResult(null); setTargets([]); setScope('server'); setView('inventory_1'); setBusy(false); setError('');
    setBaseline(''); setSource(''); setPlan(null); setReview(null); setReceipts([]); setConfirmed(false);
    return () => {serial.current++;};
  }, [post, engine]);
  const capture = async (expand=false) => {
    const token = ++serial.current;
    setBusy(true); setError('');
    try {
      const value = await post({action: `${engine}_server_catalog`, request: {include_system: system, targets: expand ? targets : []}});
      if(token === serial.current) {setResult(value); setScope('server'); setView(value.snapshot.view);
        setBaseline(JSON.stringify(value.snapshot)); setSource(JSON.stringify(value.snapshot, null, 2));
        setPlan(null); setReview(null); setConfirmed(false);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || `${engineName} server capture failed`);}
    finally {if(token === serial.current) setBusy(false);}
  };
  const shown = scope === 'server' ? result : result?.databases?.find(item => item.target_id === scope)?.capture;
  const native = async action => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const request = action === 'receipts' ? {} : action === 'plan' || action === 'review' ? {baseline, source,
        ...(action === 'review' ? {execution_sha256: plan.execution_sha256} : {})} :
        {review_id: review.review_id, ...(action === 'apply' ? {review_digest: review.review_digest, confirmed} : {})};
      const response = await post({action: `mysql_server_${action}`, request});
      if(token !== serial.current) return;
      if(action === 'plan') {setPlan(response); setReview(null); setConfirmed(false);}
      else if(action === 'receipts') setReceipts(response.receipts);
      else {
        setReview(response);
        setReceipts(values => [response, ...values.filter(item => item.review_id !== response.review_id)].slice(0, 20));
      }
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Native server operation unavailable');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const download = () => {
    const content = {format: `scratchrobin.${engine}.server-collection@1`, [identityKey]: result[identityKey],
      server: result.snapshot, databases: result.databases.map(item => ({target_id: item.target_id,
        snapshot: item.capture.snapshot, diagram: item.capture.diagram}))};
    const url = URL.createObjectURL(new Blob([JSON.stringify(content)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = `${engine}-server-ddn-collection.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{...compactFormSx, p: 1, overflow: 'auto', flex: 1}}>
    <FormReference formKey={`${engine}-server-catalog`} />
    {error && <Alert severity="error">{error}</Alert>}
    <Alert severity="info">Credential-free native server metadata. Optional database captures are independent, explicitly selected registered targets. This is observational discovery; it does not create a consistent server backup or execute metadata.</Alert>
    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center'}}>
      <FormControlLabel label="Include built-in system objects" control={<Checkbox checked={system} disabled={busy}
        onChange={event => setSystem(event.target.checked)} />} />
      <Button disabled={busy} onClick={() => capture()}>Capture server inventory</Button>
      {engine === 'mysql' && <Button disabled={busy} onClick={() => native('receipts')}>Load recent server receipts</Button>}
      <TextField select size="small" label="Registered databases to include" value={targets} disabled={busy || !result}
        slotProps={{select: {multiple: true}}} sx={{minWidth: 260}} onChange={event => setTargets(event.target.value)}>
        {(result?.registered_targets || []).map(item => <MenuItem value={item.target_id} key={item.target_id}>
          {item.display_name || item.database} ({item.database})</MenuItem>)}
      </TextField>
      <Button disabled={busy || !targets.length || targets.length > 32} onClick={() => capture(true)}>Capture selected databases</Button>
      <Button disabled={busy || !result} onClick={download}>Download DDN collection</Button>
      <TextField select size="small" label="Captured scope" value={scope} disabled={busy || !result}
        onChange={event => {
          const selected = event.target.value; setScope(selected);
          setView(selected === 'server' ? result.snapshot.view : result.databases.find(item => item.target_id === selected).capture.snapshot.view);
        }}>
        <MenuItem value="server">{engineName} server</MenuItem>
        {(result?.databases || []).map(item => <MenuItem value={item.target_id} key={item.target_id}>
          {result.registered_targets.find(target => target.target_id === item.target_id)?.display_name || item.target_id}</MenuItem>)}
      </TextField>
      {shown?.views && <TextField select size="small" label="Server collection DDN view" value={view} disabled={busy}
        onChange={event => setView(event.target.value)}>
        {shown.views.map(item => <MenuItem value={item.id} key={item.id}>{item.label}</MenuItem>)}
      </TextField>}
    </Box>
    {(shown?.provenance?.warnings || []).map(warning => <Alert severity="warning" key={warning}>{warning}</Alert>)}
    {engine === 'mysql' && (baseline || receipts.length > 0) && <Box component="details" sx={{my: 1}}>
      <summary>Review native server metadata changes</summary>
      {receipts.length > 0 && <TextField select size="small" label="Saved server receipt" value={review?.review_id || ''} disabled={busy}
        onChange={event => {const selected = receipts.find(item => item.review_id === event.target.value);
          setReview(selected || null); setPlan(selected?.plan || null); setConfirmed(false);}}>
        <MenuItem value="">Select saved receipt</MenuItem>
        {receipts.map(item => <MenuItem key={item.review_id} value={item.review_id}>{item.review_id}: {item.state}</MenuItem>)}
      </TextField>}
      <Alert severity="info">Author explicit mysql_change instructions in the server DDN. Missing selections never remove objects.
        Server operations have independent native effects. Use an exclusive administration window; automatic retry is disabled.</Alert>
      <Button component="label" disabled={busy}>Read desired server DDN<input hidden type="file" accept=".json,.ddn" onChange={async event => {
        const file = event.target.files?.[0]; event.target.value = ''; if(!file) return;
        const token = serial.current;
        try {if(file.size > 8 * 1024 * 1024) throw new Error('Server DDN exceeds 8 MiB');
          const text = await file.text(); if(token === serial.current) {setSource(text); setPlan(null); setReview(null); setConfirmed(false);}}
        catch(failure) {if(token === serial.current) setError(failure.message);}
      }} /></Button>
      <TextField multiline minRows={4} maxRows={12} fullWidth label="Desired server DDN workspace" value={source} disabled={busy}
        onChange={event => {setSource(event.target.value); setPlan(null); setReview(null); setConfirmed(false);}} />
      <Button disabled={busy || !baseline} onClick={() => native('plan')}>Preview native server changes</Button>
      <Button disabled={busy || !plan?.ready_for_review || Boolean(review)} onClick={() => native('review')}>Prepare server review</Button>
      {plan?.blockers?.map(item => <Alert severity="error" key={item.resource_id}>{item.reason}</Alert>)}
      {plan?.conflicts?.map(item => <Alert severity="warning" key={item.resource_id}>{item.reason}</Alert>)}
      {plan?.operations?.map(item => <Box key={item.resource_id} sx={{my: 1}}>
        <Box>{item.kind}: {item.operation} {item.name}</Box><Box component="pre" sx={{overflow: 'auto'}}>{item.source}</Box>
        <Box component="pre" sx={{overflow: 'auto'}}>{JSON.stringify(item.parameters)}</Box>
      </Box>)}
      {review && <>
        <Alert severity="info">Server receipt {review.review_id}: {review.state}. Repeated requests read this receipt without replaying statements.</Alert>
        <FormControlLabel label="Apply these displayed native server changes" control={<Checkbox checked={confirmed}
          disabled={busy || review.state !== 'reviewed'} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={busy || !confirmed || review.state !== 'reviewed'} onClick={() => native('apply')}>Apply server changes once</Button>
        <Button disabled={busy} onClick={() => native('receipt')}>Read server receipt</Button>
        <Box component="pre" sx={{overflow: 'auto', maxHeight: 300}}>{JSON.stringify(review.statement_outcomes || review.outcome, null, 2)}</Box>
      </>}
    </Box>}
    {shown?.snapshot && <Box sx={{height: 550, minHeight: 250, overflow: 'auto'}}>
      <DDNViewerSurface presentation snapshot={{...shown.snapshot, view,
        entry: shown.views.find(item => item.id === view)?.entry || shown.snapshot.entry}} />
    </Box>}
  </Box>;
}
MySQLServerCatalog.propTypes = {post: PropTypes.func.isRequired, engine: PropTypes.oneOf(['mysql', 'mariadb'])};
