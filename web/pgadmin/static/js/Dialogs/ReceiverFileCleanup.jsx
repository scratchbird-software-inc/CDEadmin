import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,Table,TableBody,TableCell,TableHead,TableRow} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);

export default function ReceiverFileCleanup({post,engine,receiverJobId}) {
  const prefix=engine+'_binlog_capture_cleanup_';
  const [catalog,setCatalog]=useState(null),[files,setFiles]=useState([]),[review,setReview]=useState(null),[receipt,setReceipt]=useState(null);
  const [jobs,setJobs]=useState(null),[offset,setOffset]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0);
  useEffect(() => {
    generation.current++;setCatalog(null);setFiles([]);setReview(null);setReceipt(null);setJobs(null);setOffset(0);setBusy(false);setError('');
    return () => {generation.current++;};
  },[post,engine,receiverJobId]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const result=await post({action:prefix+action,request});if(token===generation.current)accept(result);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(() => {
    if(!ACTIVE.has(receipt?.state))return;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const value=await post({action:prefix+'status',request:{job_id:receipt.job_id}});if(live)setReceipt(value);}
      catch(failure) {if(live)setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending=false;}
    },1000);
    return () => {live=false;clearInterval(timer);};
  },[post,prefix,receipt?.job_id,receipt?.state]);
  const inspect=after => run('catalog',{job_id:receiverJobId,...(after ? {after} : {})},value => {setCatalog(value);setFiles([]);setReview(null);});
  const load=next => run('list',{offset:next,limit:25},value => {setJobs(value);setOffset(next);});
  return <Box component="details" sx={{my:1}}><summary>Private receiver file cleanup</summary>
    <Alert severity="warning">Removal permanently discards selected private inputs, including unpublished changes. Pending adoption reviews may become unusable. Published archives and receipts are retained. Recovery coverage is not verified.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={() => inspect(null)}>Inspect private receiver files</Button>
    <Button disabled={busy} onClick={() => load(0)}>Load private cleanup receipts</Button>
    {catalog && <>
      <Table size="small" aria-label="Private receiver files"><TableHead><TableRow><TableCell>Select</TableCell><TableCell>File</TableCell><TableCell>Bytes</TableCell></TableRow></TableHead><TableBody>
        {catalog.files.map(row => <TableRow key={row.name}><TableCell><Checkbox inputProps={{'aria-label':'Remove '+row.name}} disabled={busy} checked={files.includes(row.name)} onChange={event => {setFiles(current => event.target.checked ? [...current,row.name] : current.filter(name => name!==row.name));setReview(null);}} /></TableCell><TableCell>{row.name}</TableCell><TableCell>{row.bytes}</TableCell></TableRow>)}
      </TableBody></Table>
      <Button disabled={busy} onClick={() => inspect(null)}>First private-file page</Button>
      <Button disabled={busy || !catalog.more} onClick={() => inspect(catalog.next_after)}>Next private-file page</Button>
      <Button disabled={busy || !files.length} onClick={() => run('review',{job_id:receiverJobId,file_names:files},setReview)}>Review private-file removal</Button>
    </>}
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Private receiver removal review" sx={{whiteSpace:'pre-wrap',maxHeight:240,overflow:'auto'}}>{JSON.stringify(review,null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={() => run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value => {setReceipt(value);setReview(current => ({...current,state:value.state}));setCatalog(null);setFiles([]);})}>Confirm and remove reviewed private files</Button>
    </Box>}
    {jobs && <Box>
      {jobs.jobs.map(job => <Button key={job.job_id} disabled={busy} onClick={() => run('status',{job_id:job.job_id},setReceipt)}>Inspect cleanup {job.job_id}</Button>)}
      <Button disabled={busy || offset===0} onClick={() => load(Math.max(0,offset-25))}>Previous cleanup receipts</Button>
      <Button disabled={busy || !jobs.more} onClick={() => load(offset+25)}>Next cleanup receipts</Button>
    </Box>}
    {receipt && <Box>
      <Alert severity={receipt.state==='completed' ? 'success' : 'warning'}>Private cleanup {receipt.job_id}: {receipt.state}. Acknowledged bytes removed: {receipt.result?.removed_bytes ?? receipt.progress?.removed_bytes ?? '0'}. No automatic repeat.</Alert>
      <Button disabled={busy} onClick={() => run('status',{job_id:receipt.job_id},setReceipt)}>Refresh private cleanup</Button>
      <Button disabled={busy || !ACTIVE.has(receipt.state)} onClick={() => run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel private cleanup</Button>
      <Box component="pre" aria-label="Private cleanup receipt" sx={{whiteSpace:'pre-wrap',maxHeight:280,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box>
    </Box>}
  </Box>;
}
ReceiverFileCleanup.propTypes={post:PropTypes.func.isRequired,engine:PropTypes.oneOf(['mysql','mariadb']).isRequired,receiverJobId:PropTypes.string.isRequired};
