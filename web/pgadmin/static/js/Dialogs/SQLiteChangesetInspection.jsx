/* global BigInt */
import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';
const active=state => ['dispatching','active','publishing','cancel_requested'].includes(state);

export default function SQLiteChangesetInspection({post,databaseTargetId,reference,endpointUrl,disabled}) {
  const [catalog,setCatalog]=useState(null),[receipt,setReceipt]=useState(null),[result,setResult]=useState(null),[jobs,setJobs]=useState(null),[files,setFiles]=useState(null);
  const [offset,setOffset]=useState('0'),[limit,setLimit]=useState(25),[preview,setPreview]=useState(256),[row,setRow]=useState('1'),[column,setColumn]=useState(1),[side,setSide]=useState('new'),[byteOffset,setByteOffset]=useState('0');
  const [cellReference,setCellReference]=useState(null),[jobOffset,setJobOffset]=useState(0);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[remove,setRemove]=useState(false);
  const serial=useRef(0),downloads=useRef([]),referenceKey=JSON.stringify(reference);
  const call=(operation,fields={}) => post({action:'sqlite_changeset_inspect_'+operation,request:{database_target_id:databaseTargetId,...fields}});
  useEffect(() => {serial.current++;setReceipt(null);setResult(null);setFiles(null);setOffset('0');setCellReference(null);setRow('1');setColumn(1);setSide('new');setByteOffset('0');setBusy(false);setRemove(false);setError('');},[databaseTargetId,referenceKey]);
  useEffect(() => {setCatalog(null);setJobs(null);setJobOffset(0);},[databaseTargetId]);
  useEffect(() => () => {serial.current++;downloads.current.forEach(close => close());},[]);
  const loadReceipt=async (value,token) => {
    if(token!==serial.current)return;
    setReceipt(value);setRemove(false);
    if(['completed','artifact_verified'].includes(value.state) && !value.artifact_removed){
      const metadata=await call('result',{job_id:value.job_id});if(token!==serial.current)return;setResult(metadata);setFiles(null);
      setCellReference(metadata.source.input.reference);
      if(metadata.options.mode!=='page'){setRow(metadata.options.record_number);setColumn(metadata.options.column_index+1);setSide(metadata.options.side);setByteOffset(metadata.options.byte_offset || '0');}
    }
  };
  useEffect(() => {
    if(!receipt?.job_id || !active(receipt.state))return undefined;
    let alive=true,timer;
    const poll=async () => {
      let value;
      try {
        value=await call('status',{job_id:receipt.job_id});if(!alive)return;
        if(active(value.state)){setReceipt(value);timer=setTimeout(poll,400);}
        else {
          const metadata=['completed','artifact_verified'].includes(value.state) ? await call('result',{job_id:value.job_id}) : null;
          if(!alive)return;
          setReceipt(value);
          if(metadata){setResult(metadata);setCellReference(metadata.source.input.reference);}
        }
      } catch(failure){if(alive){if(value && !active(value.state))setReceipt(value);setError(failure.response?.data?.errormsg || failure.message);}}
    };
    timer=setTimeout(poll,400);return () => {alive=false;clearTimeout(timer);};
  },[post,databaseTargetId,receipt?.job_id,active(receipt?.state)]);
  const perform=async (operation,fields={}) => {
    const token=serial.current;setBusy(true);setError('');
    try {
      const value=await call(operation,fields);if(token!==serial.current)return;
      if(operation==='catalog')setCatalog(value);
      else if(operation==='list')setJobs(value);
      else if(operation==='files')setFiles(value);
      else await loadReceipt(value,token);
    } catch(failure){if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===serial.current)setBusy(false);}
  };
  const inspect=async (options,sourceReference=reference) => {
    const token=serial.current;setBusy(true);setError('');setResult(null);setFiles(null);
    try {
      const review=await call('review',{input:sourceReference,options});if(token!==serial.current)return;
      const value=await call('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true});
      if(token===serial.current)await loadReceipt(value,token);
    } catch(failure){if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===serial.current)setBusy(false);}
  };
  const blocked=busy || active(receipt?.state),inspection=result?.inspection,page=inspection?.rows ? inspection : null;
  const selectRow=value => {setCellReference(result.source.input.reference);setRow(value.record_number);setColumn(1);setSide(value.operation==='delete' ? 'old':'new');setByteOffset('0');};
  const cellOptions=mode => ({mode,record_number:row,column_index:column-1,side,timeout_seconds:3600,...(mode==='cell' ? {byte_offset:byteOffset,byte_limit:65536} : {})});
  const download=path => {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{database_target_id:databaseTargetId,job_id:receipt.job_id,path},
      {action:'sqlite_changeset_inspect_download',prefix:'sqlite-inspection',title:'SQLite native inspection download'}));}
    catch(failure){setError(failure.message);}
  };
  return <Box component="details" sx={{my:1}}><summary>SQLite typed changeset inspection</summary>
    <Alert severity="info">Inspect the selected verified file before applying it. Native files contain column positions and primary-key masks. Undefined values are different from SQL NULL. Inspection leaves registered databases and query transactions unchanged.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={blocked} onClick={() => perform('catalog')}>Inspect typed native file support</Button>
    <Button disabled={busy} onClick={() => perform('list',{offset:jobOffset,limit:25})}>Load native inspection receipts</Button>
    {catalog && <>
      {!catalog.helper_available && <Alert severity="warning">{catalog.unavailable_reason}</Alert>}
      {!reference && !cellReference && <Alert severity="info">Select a verified source export, uploaded file or transformed file in the application panel.</Alert>}
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <TextField size="small" label="Native record offset" value={offset} disabled={blocked} onChange={event => setOffset(event.target.value)} />
        <TextField size="small" type="number" label="Native records per inspection page" value={limit} disabled={blocked} onChange={event => setLimit(Number(event.target.value))} />
        <TextField size="small" type="number" label="Native value preview bytes" value={preview} disabled={blocked} onChange={event => setPreview(Number(event.target.value))} />
        <Button disabled={blocked || disabled || !reference || !catalog.helper_available} onClick={() => inspect({mode:'page',offset,limit,preview_bytes:preview,max_json_bytes:1048576,timeout_seconds:3600})}>Inspect selected native records</Button>
      </Box>
    </>}
    {page && <>
      <Alert severity="info">{page.column_name_scope}. {page.validation_scope}.</Alert>
      <Table size="small" aria-label="Native SQLite changeset rows"><TableHead><TableRow>{['Record','Table','Operation','Indirect','Primary-key positions','Values'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
        {page.rows.map(value => <TableRow key={value.record_number}><TableCell>{value.record_number}</TableCell><TableCell>{typeof value.table==='string' ? value.table:JSON.stringify(value.table)}</TableCell><TableCell>{value.operation}</TableCell><TableCell>{String(value.indirect)}</TableCell><TableCell>{value.primary_key.map((key,index) => key ? index+1:null).filter(Boolean).join(', ')}</TableCell><TableCell>
          <Button disabled={blocked} onClick={() => selectRow(value)}>Select native record {value.record_number}</Button>
          <details><summary>Inspect typed native record {value.record_number}</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:260,overflow:'auto'}}>{JSON.stringify(value,null,2)}</Box></details>
        </TableCell></TableRow>)}
      </TableBody></Table>
      <Button disabled={blocked || !page.more} onClick={() => {const next=(BigInt(page.offset)+BigInt(page.rows_returned)).toString();setOffset(next);inspect({mode:'page',offset:next,limit,preview_bytes:preview,max_json_bytes:1048576,timeout_seconds:3600},result.source.input.reference);}}>Next native record inspection page</Button>
    </>}
    {catalog && <Box sx={{my:1}}>
      <TextField size="small" label="Native record number" value={row} disabled={blocked} onChange={event => setRow(event.target.value)} />
      <TextField size="small" type="number" label="Native column position (first is 1)" value={column} disabled={blocked} onChange={event => setColumn(Number(event.target.value))} />
      <TextField select size="small" label="Native row values" value={side} disabled={blocked} onChange={event => setSide(event.target.value)}><MenuItem value="old">Old values</MenuItem><MenuItem value="new">New values</MenuItem></TextField>
      <TextField size="small" label="Native value byte offset" value={byteOffset} disabled={blocked} onChange={event => setByteOffset(event.target.value)} />
      <Button disabled={blocked || disabled || !(cellReference || reference) || !catalog.helper_available} onClick={() => inspect(cellOptions('cell'),cellReference || reference)}>Inspect native value range</Button>
      <Button disabled={blocked || disabled || !(cellReference || reference) || !catalog.helper_available} onClick={() => inspect(cellOptions('extract'),cellReference || reference)}>Extract complete native TEXT or BLOB value</Button>
      {result?.options.mode==='cell' && <>
        <Box component="pre" aria-label="Native SQLite value range" sx={{whiteSpace:'pre-wrap',maxHeight:260,overflow:'auto'}}>{JSON.stringify(inspection,null,2)}</Box>
        <Button disabled={blocked || !inspection.truncated} onClick={() => {const next=(BigInt(inspection.byte_offset)+BigInt(inspection.preview_byte_length)).toString();setByteOffset(next);inspect({...cellOptions('cell'),byte_offset:next},cellReference || reference);}}>Next native value bytes</Button>
      </>}
    </Box>}
    {jobs && jobs.jobs.map(value => <Button key={value.job_id} disabled={blocked} onClick={() => perform('status',{job_id:value.job_id})}>Inspect native file receipt {value.job_id}</Button>)}
    {jobs && <>
      <Button disabled={busy || jobOffset===0} onClick={() => {const next=Math.max(0,jobOffset-25);setJobOffset(next);perform('list',{offset:next,limit:25});}}>Previous native inspection receipts</Button>
      <Button disabled={busy || !jobs.more} onClick={() => {setJobOffset(jobOffset+25);perform('list',{offset:jobOffset+25,limit:25});}}>Next native inspection receipts</Button>
    </>}
    {receipt && <>
      <Alert severity={receipt.state==='completed' ? 'success':'info'}>Native inspection {receipt.job_id}: {receipt.state}. Automatic retry is disabled.</Alert>
      {receipt.error_message && <Alert severity="warning">{receipt.error_message}</Alert>}
      {active(receipt.state) && <Button disabled={busy} onClick={() => perform('cancel',{job_id:receipt.job_id})}>Cancel native file inspection</Button>}
      {!active(receipt.state) && receipt.state!=='reviewed' && !receipt.artifact_removed && <Button disabled={busy} onClick={() => perform('reconcile',{job_id:receipt.job_id})}>Verify retained native inspection</Button>}
      {['completed','artifact_verified'].includes(receipt.state) && !receipt.artifact_removed && <Button disabled={busy} onClick={() => perform('files',{job_id:receipt.job_id,offset:0,limit:25})}>Load native inspection files</Button>}
      {files?.files.map(file => <Box key={file.path}>{file.path} ({file.size} bytes) <Button disabled={busy || !endpointUrl || files.artifact_removed} onClick={() => download(file.path)}>Download inspection {file.path}</Button></Box>)}
      {receipt.partial_output && <Alert severity="warning">Unsealed output is diagnostic only. <Button disabled={busy || !endpointUrl} onClick={() => download(receipt.partial_output.path)}>Download partial native inspection</Button></Alert>}
      {!active(receipt.state) && !receipt.artifact_removed && <>
        <FormControlLabel label="Remove native inspection output; keep receipt" control={<Checkbox checked={remove} disabled={busy} onChange={event => setRemove(event.target.checked)} />} />
        <Button disabled={busy || !remove} onClick={() => perform('remove_artifact',{job_id:receipt.job_id,confirmation:receipt.job_id})}>Remove native inspection output</Button>
      </>}
      <details><summary>Native SQLite file inspection receipt</summary><Box component="pre" aria-label="Native SQLite file inspection receipt" sx={{whiteSpace:'pre-wrap',maxHeight:260,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></details>
    </>}
  </Box>;
}
SQLiteChangesetInspection.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string.isRequired,reference:PropTypes.object,endpointUrl:PropTypes.string,disabled:PropTypes.bool};
