import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';

const active=state => ['dispatching','active','publishing','cancel_requested'].includes(state);
const eligible=(item,kind) => !item.artifact_removed && (kind==='rebase' ? item.commit_returned && item.options.include_rebase && (item.state==='completed' || item.output_artifact_verified) :
  ['completed','artifact_verified'].includes(item.state) && item.result?.artifact?.native_iterator_complete);

export default function SQLiteNativeTransforms({post,databaseTargetId,endpointUrl,onSelected,disabled}) {
  const [catalog,setCatalog]=useState(null),[sourceTarget,setSourceTarget]=useState(''),[kind,setKind]=useState('capture');
  const [sources,setSources]=useState(null),[sourceOffset,setSourceOffset]=useState(0),[selectedInput,setSelectedInput]=useState(''),[inputs,setInputs]=useState([]);
  const [options,setOptions]=useState({operation:'invert',schema_database:null,patchset_output:null,timeout_seconds:3600}),[schemas,setSchemas]=useState(null);
  const [receipt,setReceipt]=useState(null),[confirmed,setConfirmed]=useState(false),[jobs,setJobs]=useState(null),[offset,setOffset]=useState(0),[files,setFiles]=useState(null),[remove,setRemove]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const serial=useRef(0),downloads=useRef([]);
  const call=(operation,fields={}) => post({action:'sqlite_changeset_transform_'+operation,request:{database_target_id:databaseTargetId,...fields}});
  useEffect(() => {
    serial.current++;setCatalog(null);setSourceTarget(databaseTargetId);setSources(null);setSourceOffset(0);setSelectedInput('');setInputs([]);setSchemas(null);
    setReceipt(null);setConfirmed(false);setJobs(null);setOffset(0);setFiles(null);setRemove(false);setBusy(false);setError('');
    return () => {serial.current++;downloads.current.forEach(close => close());downloads.current=[];};
  },[databaseTargetId]);
  const perform=async (operation,fields={}) => {
    const token=serial.current;setBusy(true);setError('');
    try {
      const value=await call(operation,fields);if(token!==serial.current)return;
      if(operation==='catalog')setCatalog(value);
      else if(operation==='schemas')setSchemas(value);
      else if(operation==='sources'){setSources(value);setSelectedInput(value.jobs.find(item => eligible(item,kind))?.job_id || '');}
      else if(operation==='list')setJobs(value);
      else if(operation==='files')setFiles(value);
      else {setReceipt(value);setConfirmed(false);setFiles(null);setRemove(false);}
    } catch(failure) {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===serial.current)setBusy(false);}
  };
  useEffect(() => {
    if(!receipt?.job_id || !active(receipt.state))return undefined;
    let alive=true,timer;
    const poll=async () => {
      try {const value=await call('status',{job_id:receipt.job_id});if(!alive)return;setReceipt(value);if(active(value.state))timer=setTimeout(poll,400);}
      catch(failure) {if(alive)setError(failure.response?.data?.errormsg || failure.message);}
    };
    timer=setTimeout(poll,400);return () => {alive=false;clearTimeout(timer);};
  },[post,databaseTargetId,receipt?.job_id,active(receipt?.state)]);
  const invalidate=() => {setReceipt(current => current?.state==='reviewed' ? null : current);setConfirmed(false);};
  const change=(name,value) => {setOptions(current => ({...current,[name]:value}));invalidate();};
  const sourceFields={source_database_target_id:sourceTarget,kind};
  const changeSource=(name,value) => {if(name==='kind')setKind(value);else setSourceTarget(value);setSources(null);setSourceOffset(0);setSelectedInput('');};
  const selected=sources?.jobs.find(item => item.job_id===selectedInput),blocked=busy || active(receipt?.state);
  const addInput=() => {
    if(!selected)return;
    const path=kind==='rebase' ? 'native.rebase' : kind==='capture' ? 'capture.'+selected.options.kind : selected.result.artifact.input_name;
    setInputs(current => [...current,{database_target_id:sourceTarget,kind,job_id:selected.job_id,path}]);invalidate();
  };
  const move=(index,direction) => {setInputs(current => {const next=[...current];[next[index],next[index+direction]]=[next[index+direction],next[index]];return next;});invalidate();};
  const download=path => {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{database_target_id:databaseTargetId,job_id:receipt.job_id,path},
      {action:'sqlite_changeset_transform_download',prefix:'sqlite-transform',title:'SQLite native transformed file download'}));}
    catch(failure) {setError(failure.message);}
  };
  const verified=['completed','artifact_verified'].includes(receipt?.state) && !receipt?.artifact_removed;
  return <Box component="details" sx={{my:1}}><summary>SQLite native file transformations</summary>
    <Alert severity="info">Create a new native file by inversion, concatenation, changegroup merging or rebasing. Inputs and database data stay unchanged. Rebase inputs are a local changeset followed by ordered native rebase buffers from acknowledged apply commits. Apply the result through a separate review.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={blocked} onClick={() => perform('catalog')}>Inspect native transform support</Button>
    <Button disabled={busy} onClick={() => perform('list',{offset,limit:25})}>Load native transform receipts</Button>
    {catalog && <>
      {!catalog.helper_available && <Alert severity="warning">{catalog.unavailable_reason}</Alert>}
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <TextField select size="small" label="Native file transformation" value={options.operation} disabled={blocked} onChange={event => {const operation=event.target.value;setOptions(current => ({...current,operation,schema_database:operation==='merge' ? current.schema_database : null,patchset_output:operation==='merge' ? current.patchset_output : null}));invalidate();}}>
          <MenuItem value="invert">Invert changeset</MenuItem><MenuItem value="concat">Concatenate two ordered files</MenuItem><MenuItem value="merge">Merge native changegroup</MenuItem><MenuItem value="rebase">Rebase local changeset</MenuItem>
        </TextField>
        <TextField select size="small" label="Transform source registration" value={sourceTarget} disabled={blocked} onChange={event => changeSource('target',event.target.value)}>
          {catalog.targets.map(target => <MenuItem key={target.target_id} value={target.target_id}>{target.display_name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Transform source kind" value={kind} disabled={blocked} onChange={event => changeSource('kind',event.target.value)}>
          <MenuItem value="capture">Captured changes</MenuItem><MenuItem value="upload">Uploaded native file</MenuItem><MenuItem value="transform">Transformed native file</MenuItem><MenuItem value="rebase">Native apply rebase buffer</MenuItem>
        </TextField>
        <Button disabled={blocked || !sourceTarget} onClick={() => perform('sources',{...sourceFields,offset:sourceOffset,limit:25})}>Load native transform inputs</Button>
      </Box>
      {sources && <Box>
        <TextField select size="small" label="Native transform input artifact" value={selectedInput} disabled={blocked} onChange={event => setSelectedInput(event.target.value)} sx={{minWidth:420}}>
          {sources.jobs.filter(item => eligible(item,kind)).map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} — {kind==='rebase' ? 'rebase' : item.result.artifact.native_kind || item.options.kind}</MenuItem>)}
        </TextField>
        <Button disabled={blocked || !selected || inputs.length>=100} onClick={addInput}>Add ordered native input</Button>
        <Button disabled={blocked || sourceOffset===0} onClick={() => {const next=Math.max(0,sourceOffset-25);setSourceOffset(next);perform('sources',{...sourceFields,offset:next,limit:25});}}>Previous transform inputs</Button>
        <Button disabled={blocked || !sources.more} onClick={() => {setSourceOffset(sourceOffset+25);perform('sources',{...sourceFields,offset:sourceOffset+25,limit:25});}}>Next transform inputs</Button>
      </Box>}
      <Box component="ol" aria-label="Ordered native transform inputs">{inputs.map((input,index) => <Box component="li" key={index}>
        {input.kind}: {input.job_id} / {input.path}
        <Button disabled={blocked || index===0} onClick={() => move(index,-1)}>Move native input {index+1} up</Button>
        <Button disabled={blocked || index===inputs.length-1} onClick={() => move(index,1)}>Move native input {index+1} down</Button>
        <Button disabled={blocked} onClick={() => {setInputs(current => current.filter((_value,position) => position!==index));invalidate();}}>Remove native input {index+1}</Button>
      </Box>)}</Box>
      {options.operation==='merge' && <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <Button disabled={blocked} onClick={() => perform('schemas')}>Inspect registered merge schemas</Button>
        <TextField select size="small" label="Native merge schema basis" value={options.schema_database || ''} disabled={blocked} onChange={event => change('schema_database',event.target.value || null)}>
          <MenuItem value="">No schema basis</MenuItem>{schemas?.schemas.map(schema => <MenuItem key={schema.name} value={schema.name}>{schema.name} — {schema.filename}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Native changegroup output configuration" value={options.patchset_output===null ? 'auto' : String(options.patchset_output)} disabled={blocked} onChange={event => change('patchset_output',event.target.value==='auto' ? null : event.target.value==='true')}>
          <MenuItem value="auto">Native input format</MenuItem><MenuItem value="false">Native changeset configuration</MenuItem><MenuItem value="true">Native patchset configuration</MenuItem>
        </TextField>
        {schemas && <Alert severity="info">{schemas.scope}</Alert>}
      </Box>}
      <TextField size="small" type="number" label="Native transform maximum seconds" value={options.timeout_seconds ?? ''} disabled={blocked} onChange={event => change('timeout_seconds',event.target.value==='' ? null : Number(event.target.value))} />
      <Button disabled={blocked || !inputs.length || !catalog.helper_available} onClick={() => perform('review',{inputs,options})}>Review native file transformation</Button>
    </>}
    {jobs && <Box>
      <TextField select size="small" label="Retained native transform" value={jobs.jobs.some(item => item.job_id===receipt?.job_id) ? receipt.job_id : ''} disabled={blocked} onChange={event => perform('status',{job_id:event.target.value})} sx={{minWidth:420}}>
        {jobs.jobs.map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} — {item.state}</MenuItem>)}
      </TextField>
      <Button disabled={busy || offset===0} onClick={() => {const next=Math.max(0,offset-25);setOffset(next);perform('list',{offset:next,limit:25});}}>Previous native transform receipts</Button>
      <Button disabled={busy || !jobs.more} onClick={() => {setOffset(offset+25);perform('list',{offset:offset+25,limit:25});}}>Next native transform receipts</Button>
    </Box>}
    {receipt && <Box>
      <Alert severity={verified ? 'success' : 'info'}>Native transform {receipt.job_id}: {receipt.state}. Automatic retry is disabled.</Alert>
      {receipt.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
      {receipt.error_message && <Alert severity="warning">{receipt.error_message}</Alert>}
      {receipt.state==='reviewed' && <><FormControlLabel label="Confirm new native transformed artifact" control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={busy || !confirmed} onClick={() => perform('start',{job_id:receipt.job_id,review_digest:receipt.review_digest,confirmed:true})}>Start reviewed native transformation</Button></>}
      {active(receipt.state) && <Button disabled={busy} onClick={() => perform('cancel',{job_id:receipt.job_id})}>Cancel native transformation</Button>}
      {verified && <><Button disabled={busy || disabled} onClick={() => onSelected(receipt)}>Use transformed native file for apply</Button>
        <Button disabled={busy} onClick={() => perform('files',{job_id:receipt.job_id,offset:0,limit:25})}>Load native transformed files</Button></>}
      {!active(receipt.state) && receipt.state!=='reviewed' && !receipt.artifact_removed && <Button disabled={busy} onClick={() => perform('reconcile',{job_id:receipt.job_id})}>Verify retained native transform</Button>}
      {files?.files.map(row => <Box key={row.path}>{row.path} ({row.size} bytes) <Button disabled={busy || !endpointUrl || files.artifact_removed} onClick={() => download(row.path)}>Download transform {row.path}</Button></Box>)}
      {receipt.partial_output && !receipt.artifact_removed && <Box><Alert severity="warning">Unsealed transformed bytes are diagnostic only.</Alert><Button disabled={busy || !endpointUrl} onClick={() => download(receipt.partial_output.path)}>Download native transform diagnostic</Button></Box>}
      {!active(receipt.state) && !receipt.artifact_removed && <><FormControlLabel label="Remove native transform files; retain the receipt" control={<Checkbox checked={remove} disabled={busy} onChange={event => setRemove(event.target.checked)} />} />
        <Button disabled={busy || !remove} onClick={() => perform('remove_artifact',{job_id:receipt.job_id,confirmation:receipt.job_id})}>Remove native transform files</Button></>}
      <Box component="details"><summary>Native SQLite transform receipt</summary><Box component="pre" aria-label="Native SQLite transform receipt" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
SQLiteNativeTransforms.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string.isRequired,endpointUrl:PropTypes.string,onSelected:PropTypes.func.isRequired,disabled:PropTypes.bool};
