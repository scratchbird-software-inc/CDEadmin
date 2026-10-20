import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';
import SQLiteColumnDesign from './SQLiteColumnDesign';
import FirebirdCatalogDesigner from './FirebirdCatalogDesigner';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function SQLiteRetainedSchema({post,ensureSession,sessionId,databaseTargetId,disabled,onBusyChange,onBlocked}) {
  const [catalog,setCatalog]=useState(null),[baseline,setBaseline]=useState(''),[desired,setDesired]=useState('');
  const [preview,setPreview]=useState(null),[receipt,setReceipt]=useState(null),[confirmed,setConfirmed]=useState(false);
  const [error,setError]=useState(''),[pending,setPending]=useState(false),[archiveBusy,setArchiveBusy]=useState(false);
  const [deletions,setDeletions]=useState([]),[listing,setListing]=useState(null),[offset,setOffset]=useState(0);
  const [selected,setSelected]=useState(''),[removeConfirmed,setRemoveConfirmed]=useState(false);
  const serial=useRef(0),captured=useRef(null),live=useRef(false),active=useRef(true);
  const busyOwner=useRef(false);
  const running=live.current && receipt && !receipt.native_session_release_confirmed;
  useEffect(()=>{
    if(pending || running){busyOwner.current=true;onBusyChange?.(true);}
    else if(busyOwner.current){busyOwner.current=false;onBusyChange?.(false);}
  },[pending,running,onBusyChange]);
  useEffect(()=>{
    serial.current++;captured.current=null;live.current=false;setCatalog(null);setBaseline('');setDesired('');
    setPreview(null);setReceipt(null);setConfirmed(false);setPending(false);setError('');setDeletions([]);
  },[post,databaseTargetId,sessionId]);
  useEffect(()=>{setListing(null);setSelected('');setOffset(0);setArchiveBusy(false);},[post,databaseTargetId]);
  useEffect(()=>{active.current=true;return()=>{active.current=false;serial.current++;if(busyOwner.current)onBusyChange?.(false);};},[onBusyChange]);
  const invoke=(operation,fields={},archived=false)=>post({action:archived ? 'sqlite_retained_schema_receipts':'sqlite_retained_schema',
    database_target_id:databaseTargetId,...(!archived ? {session_id:captured.current || sessionId}:{}),request:{operation,...fields}});
  const receive=(value,isLive)=>{
    live.current=isLive;setReceipt(value);setConfirmed(false);
    if(isLive && value.native_session_release_confirmed && value.state==='unknown_outcome')onBlocked?.();
  };
  const perform=async operation=>{
    const token=++serial.current;setPending(true);setError('');
    try {
      if(operation==='connect') {await ensureSession();return;}
      if(operation==='capture') {
        const value=await post({action:'source_catalog',session_id:sessionId,database_target_id:databaseTargetId,include_system:false});
        if(token!==serial.current || !active.current)return;
        if(!value.document)throw new Error(value.export_warning || 'Native session DDN is unavailable');
        captured.current=sessionId;setCatalog(value);setBaseline(JSON.stringify(value.document.snapshot));
        setDesired('');setPreview(null);setReceipt(null);setDeletions([]);live.current=false;return;
      }
      if(!captured.current || captured.current!==sessionId)throw new Error('Capture this original query connection before reviewing DDL');
      let value;
      if(operation==='preview' || operation==='review') {
        value=await invoke(operation,{baseline,desired,deletions,...(operation==='review' ? {execution_sha256:preview.execution_sha256}:{})});
      } else if(operation==='start') {
        value=await invoke('start',{review_id:receipt.review_id,review_digest:receipt.review_digest,confirmed:true});
      }
      if(token!==serial.current || !active.current)return;
      if(operation==='preview')setPreview(value);else receive(value,true);
    } catch(failure) {if(token===serial.current && active.current)setError(failure.response?.data?.errormsg || failure.message || 'Native outcome is unavailable; read the existing receipt before preparing another change');}
    finally {if(token===serial.current && active.current)setPending(false);}
  };
  const columns=async (identity,definitions)=>{
    const token=++serial.current;setPending(true);setError('');
    try {
      const value=await invoke('columns',{baseline,resource_id:identity,columns:definitions});
      if(token===serial.current && active.current){setDesired(JSON.stringify(value.snapshot));setPreview(null);setReceipt(null);setConfirmed(false);setDeletions([]);live.current=false;}
    } catch(failure) {if(token===serial.current && active.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===serial.current && active.current)setPending(false);}
  };
  const read=async (id,isLive=false)=>{
    const token=serial.current;
    try {
      const value=await invoke('receipt',{review_id:id},true);
      if(active.current && token===serial.current)receive(value,isLive);
    } catch(failure) {if(active.current && token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
  };
  useEffect(()=>{
    if(!running || !receipt?.review_id)return;
    const timer=setInterval(()=>read(receipt.review_id,true),500);return()=>clearInterval(timer);
  },[running,receipt?.review_id,post,databaseTargetId]);
  const archiveAction=async (operation,page=offset)=>{
    const token=serial.current;setArchiveBusy(true);setError('');
    try {
      const value=await invoke(operation,operation==='list' ? {offset:page,limit:25}:operation==='remove' ?
        {review_id:selected,confirmed:removeConfirmed}:{review_id:receipt.review_id},true);
      if(token!==serial.current || !active.current)return;
      if(operation==='list'){setListing(value);setOffset(page);}
      else if(operation==='cancel')receive(value,live.current);
      else {setSelected('');setRemoveConfirmed(false);setListing(null);}
    } catch(failure) {if(token===serial.current && active.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===serial.current && active.current)setArchiveBusy(false);}
  };
  const objects=(catalog?.resources || []).map(row=>({resource_id:row.resource_id,kind:row.resource_kind,name:row.display_name,path:row.display_path}));
  const locked=disabled || pending || !!running;
  return <Box component="details" sx={{my:1}}><summary>Original-session SQLite design</summary>
    <FormReference formKey="sqlite-retained-schema" />
    <Alert severity="info">TEMP, attached and pending definitions stay on this original query connection. Begin a transaction before review. Apply leaves DDL pending your commit or rollback; no automatic commit or replay occurs.</Alert>
    {!sessionId && <Button disabled={disabled || pending} onClick={()=>perform('connect')}>Open original query connection</Button>}
    <Button disabled={locked || !sessionId} onClick={()=>perform('capture')}>Capture original-session DDN</Button>
    {error && <Alert severity="error">{error}</Alert>}
    {baseline && <>
      <SQLiteColumnDesign key={sessionId} sessionScope objects={objects} tables={objects.filter(row=>row.kind==='table')}
        disabled={locked} onGenerate={columns} />
      <FirebirdCatalogDesigner engine="sqlite" baseline={baseline} disabled={locked} storage={false}
        onReview={(value,original)=>{setBaseline(original);setDesired(value);setPreview(null);setReceipt(null);setConfirmed(false);live.current=false;}} />
      <Button component="label" disabled={locked}>Load desired session DDN<input hidden type="file" aria-label="Desired original-session DDN file" accept=".json,.ddn" onChange={async event=>{
        const file=event.target.files?.[0],token=serial.current;if(!file)return;
        try {const value=await file.text();if(token===serial.current && active.current){setDesired(value);setPreview(null);setReceipt(null);setConfirmed(false);live.current=false;}}
        catch(failure){if(token===serial.current && active.current)setError(failure.message);}
      }} /></Button>
      <Box component="details"><summary>Explicit original-session removals</summary>
        {objects.filter(row=>['table','view','index','trigger','fts-table','virtual-table'].includes(row.kind)).map(row=>
          <FormControlLabel key={row.resource_id} label={`Remove ${row.kind}: ${row.path.join(' / ')}`} control={<Checkbox disabled={locked} checked={deletions.includes(row.resource_id)}
            onChange={event=>{setDeletions(current=>event.target.checked ? [...current,row.resource_id]:current.filter(id=>id!==row.resource_id));setPreview(null);setReceipt(null);setConfirmed(false);}} />} />)}
      </Box>
      <Button disabled={locked || !desired} onClick={()=>perform('preview')}>Preview original-session changes</Button>
    </>}
    {preview && <>
      <Box component="pre" aria-label="Original-session native SQL" sx={{maxHeight:320,overflow:'auto',whiteSpace:'pre-wrap'}}>{preview.operations.map(row=>row.source).join(';\n\n')}</Box>
      {preview.warnings?.map(message=><Alert key={message} severity="warning">{message}</Alert>)}
      <Button disabled={locked || !preview.ready_for_review} onClick={()=>perform('review')}>Prepare original-session review</Button>
    </>}
    {receipt && <>
      <Alert severity={receipt.state==='unknown_outcome' ? 'warning':'info'}>Original-session receipt {receipt.review_id}: {receipt.state}. {receipt.acknowledgement_scope}</Alert>
      {receipt.outcome?.native_error && <Alert severity="error">{receipt.outcome.native_error}</Alert>}
      {receipt.outcome?.reason && <Alert severity="warning">{receipt.outcome.reason}</Alert>}
      {receipt.state==='reviewed' && live.current && <>
        <FormControlLabel label="Confirm this DDL on the original caller transaction" control={<Checkbox disabled={locked} checked={confirmed} onChange={event=>setConfirmed(event.target.checked)} />} />
        <Button disabled={locked || !confirmed} onClick={()=>perform('start')}>Apply original-session DDL</Button>
      </>}
      <Button disabled={archiveBusy} onClick={()=>read(receipt.review_id,live.current)}>Read original-session receipt</Button>
      {(running || receipt.worker_active) && <Button disabled={archiveBusy} onClick={()=>archiveAction('cancel')}>Request native DDL cancellation</Button>}
    </>}
    <Box component="details"><summary>Retained DDL receipts</summary>
      <Button disabled={archiveBusy} onClick={()=>archiveAction('list')}>List retained DDL receipts</Button>
      {listing && <>
        <TextField select label="Retained DDL receipt" value={selected} disabled={archiveBusy || !!running} onChange={event=>setSelected(event.target.value)}>
          <MenuItem value="">Select receipt</MenuItem>{listing.receipts.map(row=><MenuItem key={row.review_id} value={row.review_id}>{row.review_id}: {row.state}</MenuItem>)}
        </TextField>
        <Button disabled={!selected || archiveBusy || !!running} onClick={()=>read(selected,false)}>Inspect archived DDL receipt</Button>
        <FormControlLabel label="Confirm completed DDL receipt removal" control={<Checkbox disabled={archiveBusy || !!running} checked={removeConfirmed} onChange={event=>setRemoveConfirmed(event.target.checked)} />} />
        <Button disabled={!selected || !removeConfirmed || archiveBusy || !!running} onClick={()=>archiveAction('remove')}>Remove retained DDL receipt</Button>
        <Button disabled={offset===0 || archiveBusy} onClick={()=>archiveAction('list',Math.max(0,offset-25))}>Previous receipt page</Button>
        <Button disabled={!listing.more || archiveBusy} onClick={()=>archiveAction('list',offset+25)}>Next receipt page</Button>
      </>}
    </Box>
  </Box>;
}
SQLiteRetainedSchema.propTypes={post:PropTypes.func.isRequired,ensureSession:PropTypes.func.isRequired,
  sessionId:PropTypes.string,databaseTargetId:PropTypes.string,disabled:PropTypes.bool,
  onBusyChange:PropTypes.func,onBlocked:PropTypes.func};
