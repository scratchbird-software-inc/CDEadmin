import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import PagedDataGrid from '../cdeadmin_ui/data/PagedDataGrid';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

const active = state => ['dispatching','active','cancel_requested','publishing'].includes(state);

export default function SQLiteRecovery({post, databaseTargetId, onTargetCatalogChanged}) {
  const [target,setTarget]=useState(databaseTargetId || ''),[catalog,setCatalog]=useState(null);
  const [options,setOptions]=useState({output_path:'',source_isolated:false,include_freelist:false,
    preserve_rowids:true,lost_and_found:'recovered_orphans',timeout_seconds:3600});
  const [receipt,setReceipt]=useState(null),[confirmed,setConfirmed]=useState(false);
  const [jobs,setJobs]=useState(null),[offset,setOffset]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0);
  const call=(operation,data={},selected=target) => post({action:'sqlite_recovery_'+operation,
    request:{...(selected ? {database_target_id:selected} : {}),...data}});
  useEffect(() => {
    const token=++generation.current;let alive=true;
    setCatalog(null);setReceipt(null);setConfirmed(false);setJobs(null);setOffset(0);setError('');setBusy(false);
    call('catalog').then(value => {if(alive && token===generation.current)setCatalog(value);})
      .catch(failure => {if(alive)setError(failure.response?.data?.errormsg || failure.message);});
    return () => {alive=false;generation.current++;};
  },[post,target]);
  useEffect(() => {setTarget(databaseTargetId || '');},[databaseTargetId]);
  useEffect(() => {
    if(!receipt?.job_id || !active(receipt.state))return undefined;
    let alive=true,timer;
    const poll=async () => {
      try {
        const value=await call('status',{job_id:receipt.job_id});
        if(!alive)return;
        setReceipt(value);
        if(active(value.state))timer=setTimeout(poll,400);
      } catch(failure) {if(alive)setError(failure.response?.data?.errormsg || failure.message);}
    };
    timer=setTimeout(poll,400);
    return () => {alive=false;clearTimeout(timer);};
  },[post,target,receipt?.job_id,active(receipt?.state)]);
  const perform=async (operation,data={}) => {
    const token=generation.current;setBusy(true);setError('');
    try {
      const value=await call(operation,data);
      if(token!==generation.current)return;
      if(operation==='catalog')setCatalog(value);
      else if(operation==='list')setJobs(value);
      else if(operation==='activate') {setReceipt(value.receipt);onTargetCatalogChanged?.();}
      else {setReceipt(value);setConfirmed(false);}
    } catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'SQLite recovery failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  const change=(name,value) => {setOptions(current => ({...current,[name]:value}));if(receipt?.state==='reviewed')setReceipt(null);setConfirmed(false);};
  const selectTarget=value => {setTarget(value);setBusy(false);setConfirmed(false);};
  const output=receipt?.source?.output_path;
  const terminalCopy=['completed','artifact_verified'].includes(receipt?.state);
  const source=catalog?.targets?.find(item => item.target_id===target);
  return <Box sx={{p:2,overflow:'auto',flex:1,minHeight:0,...compactFormSx}}>
    <Box component="h2">SQLite file recovery</Box>
    <FormReference formKey="sqlite-recovery" />
    <Alert severity="info">Recover into a new file on the application host. The original is opened only for image capture. Native integrity checking does not establish complete recovery of application data.</Alert>
    {catalog?.execution_host && <Box>Execution host: {catalog.execution_host.name} ({catalog.execution_host.platform})</Box>}
    {catalog && !catalog.runtime?.available && <Alert severity="warning">{catalog.runtime?.reason}</Alert>}
    {catalog?.runtime?.available && <Box>Native SQLite recovery: {catalog.runtime.native.version}</Box>}
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <TextField select size="small" label="Registered source file" value={target} disabled={busy} sx={{minWidth:220}}
        onChange={event => selectTarget(event.target.value)}>{(catalog?.targets || []).map(item =>
          <MenuItem key={item.target_id} value={item.target_id}>{item.display_name}</MenuItem>)}</TextField>
      <TextField size="small" label="New recovered database filename (application host)" value={options.output_path}
        disabled={busy} onChange={event => change('output_path',event.target.value)} sx={{minWidth:360}} />
      <TextField size="small" label="Lost-and-found table" value={options.lost_and_found} disabled={busy}
        onChange={event => change('lost_and_found',event.target.value)} />
      <TextField size="small" type="number" label="Maximum runtime (seconds)" value={options.timeout_seconds} disabled={busy}
        onChange={event => change('timeout_seconds',Number(event.target.value))} />
    </Box>
    {source && <Box>Source file: {source.path}</Box>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap'}}>
      <FormControlLabel label="Writers to the source file are stopped or isolated" control={<Checkbox checked={options.source_isolated} disabled={busy}
        onChange={event => change('source_isolated',event.target.checked)} />} />
      <FormControlLabel label="Preserve native row IDs" control={<Checkbox checked={options.preserve_rowids} disabled={busy}
        onChange={event => change('preserve_rowids',event.target.checked)} />} />
      <FormControlLabel label="Recover freelist pages (can include deleted records)" control={<Checkbox checked={options.include_freelist} disabled={busy}
        onChange={event => change('include_freelist',event.target.checked)} />} />
    </Box>
    <Button disabled={busy || !target || !catalog?.runtime?.available} onClick={() => perform('review',{options})}>Review native recovery</Button>
    <Button disabled={busy} onClick={() => perform('catalog')}>Refresh files and runtime</Button>
    <Button disabled={busy || !target} onClick={() => perform('list',{offset,limit:25})}>Load recovery receipts</Button>
    {jobs && <Box sx={{my:1}}>
      <TextField select size="small" label="Retained recovery job" value={jobs.jobs.some(item => item.job_id===receipt?.job_id) ? receipt.job_id : ''}
        onChange={event => perform('status',{job_id:event.target.value})} sx={{minWidth:380}}>
        {jobs.jobs.map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} — {item.state}</MenuItem>)}
      </TextField>
      <Button disabled={busy || offset===0} onClick={() => {setOffset(Math.max(0,offset-25));perform('list',{offset:Math.max(0,offset-25),limit:25});}}>Previous receipts</Button>
      <Button disabled={busy || !jobs.more} onClick={() => {setOffset(offset+25);perform('list',{offset:offset+25,limit:25});}}>Next receipts</Button>
    </Box>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={terminalCopy ? 'success' : ['failed','timed_out','unknown_outcome'].includes(receipt.state) ? 'warning' : 'info'}>
        Recovery state: {receipt.state}. {output && `Output: ${output}.`} Automatic retry is disabled.
      </Alert>
      {receipt.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
      {(receipt.error_message || receipt.result?.error_message || receipt.result?.native_error_message) &&
        <Alert severity="warning">{receipt.error_message || receipt.result?.error_message || receipt.result?.native_error_message}</Alert>}
      {receipt.state==='reviewed' && <>
        <FormControlLabel label="Confirm recovery into this new file" control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={busy || !confirmed} onClick={() => perform('start',{job_id:receipt.job_id,review_digest:receipt.review_digest,confirmed:true})}>Start reviewed recovery</Button>
      </>}
      {active(receipt.state) && receipt.state!=='publishing' && <Button disabled={busy}
        onClick={() => perform('cancel',{job_id:receipt.job_id})}>Cancel recovery</Button>}
      <Box role="status">Stage: {receipt.progress?.stage || receipt.state}.
        {receipt.progress?.copied_bytes && ` Captured bytes: ${receipt.progress.copied_bytes} / ${receipt.progress.total_image_bytes}.`}
        {receipt.progress?.native_steps!==undefined && ` Native step observations: ${receipt.progress.native_steps}.`}</Box>
      {receipt.result?.integrity_check && <Box>Native integrity: {receipt.result.integrity_check}. Application data still requires verification.</Box>}
      {receipt.activated_target_id && <Alert severity="info">The recovered copy is registered and active. Open it in the database explorer to verify its data.</Alert>}
      {receipt.result?.foreign_key_violations?.length>0 && <Alert severity="warning">Foreign-key violations were observed in the recovered copy.</Alert>}
      {receipt.result?.tables && <Box sx={{height:240}}><PagedDataGrid readOnly gridId="sqlite/recovery-tables" aria-label="Recovered SQLite table observations"
        rows={receipt.result.tables} rowKeyGetter={row => row.name} columns={[
          {key:'name',name:'Native table'}, {key:'row_count',name:'Observed rows'}, {key:'readable',name:'Readable'},
        ]} /></Box>}
      {!active(receipt.state) && receipt.state!=='reviewed' && <Button disabled={busy}
        onClick={() => perform('reconcile',{job_id:receipt.job_id})}>Reconcile recovered file</Button>}
      {terminalCopy && <Button disabled={busy || Boolean(receipt.activated_target_id)}
        onClick={() => perform('activate',{job_id:receipt.job_id,confirmation:output})}>Register and activate recovered copy</Button>}
      {['completed','artifact_verified','failed','timed_out','cancelled','not_dispatched'].includes(receipt.state) && !receipt.staged_images_removed &&
        <Button disabled={busy} onClick={() => perform('remove_images',{job_id:receipt.job_id,confirmation:receipt.job_id})}>Remove staged images</Button>}
      <Box component="details"><summary>Recovery receipt</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
SQLiteRecovery.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string,onTargetCatalogChanged:PropTypes.func};
