import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Table, TableBody, TableCell, TableHead, TableRow, TablePagination, TextField} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
export default function MySQLClone({post}) {
  const [destination,setDestination]=useState(''),[confirmation,setConfirmation]=useState(''),[timeout,setTimeoutValue]=useState(3600);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[catalog,setCatalog]=useState(null),[page,setPage]=useState(0);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const [donors,setDonors]=useState(null),[donor,setDonor]=useState(''),[host,setHost]=useState(''),[port,setPort]=useState(3306);
  const [requireSSL,setRequireSSL]=useState(true),[delegate,setDelegate]=useState(false);
  const generation=useRef(0);
  useEffect(() => {
    generation.current++;setDestination('');setConfirmation('');setTimeoutValue(3600);setReview(null);setReceipt(null);setCatalog(null);setPage(0);setBusy(false);setError('');
    setDonors(null);setDonor('');setHost('');setPort(3306);setRequireSSL(true);setDelegate(false);
    return () => {generation.current++;};
  },[post]);
  useEffect(() => {
    if(!receipt || !ACTIVE.has(receipt.state))return;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const value=await post({action:'mysql_clone_status',request:{job_id:receipt.job_id}});if(live)setReceipt(value);}
      catch(failure) {if(live)setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending=false;}
    },1000);
    return () => {live=false;clearInterval(timer);};
  },[post,receipt?.job_id,receipt?.state]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:'mysql_clone_'+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native clone request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  const load=next => run('list',{offset:next*25,limit:25},value => {setCatalog(value);setPage(next);});
  const download=() => {
    const url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='mysql-clone-'+receipt.job_id+'.json';link.click();
    window.setTimeout(() => URL.revokeObjectURL(url),1000);
  };
  return <Box sx={{p:1,overflow:'auto',flex:1}}>
    <Alert severity="info">Native clone copies supported InnoDB data to a new directory on the recipient database-server host. Other storage engines, configuration, binary logs and encryption-key provisioning need their applicable workflows.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <Button disabled={busy} onClick={() => run('donors',{offset:0,limit:25},setDonors)}>Load registered donors</Button>
      {donors && <TextField select size="small" label="Clone source" value={donor} disabled={busy} sx={{minWidth:220}} onChange={event => {
        const value=event.target.value,selected=donors.donors.find(item => item.server_id===value);
        setDonor(value);setHost(selected?.host || '');setPort(selected?.port || 3306);setDelegate(false);setReview(null);
      }}><MenuItem value="">Local instance</MenuItem>{donors.donors.map(item => <MenuItem key={item.server_id} value={item.server_id}>{item.name}</MenuItem>)}</TextField>}
      {donors && donors.total>donors.offset+donors.limit && <Button disabled={busy} onClick={() => run('donors',{offset:donors.offset+donors.limit,limit:25},value => setDonors(current => ({...value,donors:[...current.donors,...value.donors]})))}>More donors</Button>}
      {donor!=='' && <>
        <TextField size="small" label="Donor host reachable from recipient" value={host} disabled={busy} onChange={event => {setHost(event.target.value);setReview(null);}} />
        <TextField size="small" type="number" label="Donor TCP port" value={port} disabled={busy} onChange={event => {setPort(Number(event.target.value));setReview(null);}} />
        <FormControlLabel label="Require native clone TLS" control={<Checkbox checked={requireSSL} disabled={busy} onChange={event => {setRequireSSL(event.target.checked);setReview(null);}} />} />
        <FormControlLabel label="Delegate registered donor credentials to recipient" control={<Checkbox checked={delegate} disabled={busy} onChange={event => {setDelegate(event.target.checked);setReview(null);}} />} />
      </>}
    </Box>
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <TextField disabled={busy} size="small" label="Destination on database-server host" value={destination} onChange={event => {setDestination(event.target.value);setReview(null);}} />
      <TextField disabled={busy} size="small" label="Confirm exact destination" value={confirmation} onChange={event => {setConfirmation(event.target.value);setReview(null);}} />
      <TextField disabled={busy} size="small" type="number" label="Client timeout seconds (blank: no limit)" value={timeout ?? ''} onChange={event => {setTimeoutValue(event.target.value==='' ? null : Number(event.target.value));setReview(null);}} />
      <Button disabled={busy || donor!=='' && !delegate} onClick={() => run('review',{options:{destination,confirmation,timeout_seconds:timeout,...(donor==='' ? {} : {donor:{server_id:donor,host,port,require_ssl:requireSSL,delegate_credentials:delegate}})}},setReview)}>Review {donor==='' ? 'local' : 'remote'} clone</Button>
      <Button disabled={busy} onClick={() => load(page)}>Load clone jobs</Button>
    </Box>
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Native clone review" sx={{whiteSpace:'pre-wrap',maxHeight:280,overflow:'auto'}}>{JSON.stringify({source:review.source,donor:review.donor,options:review.options,execution_host:review.execution_host},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={() => run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value => {setReceipt(value);setReview(current => ({...current,state:value.state}));})}>Confirm and start {review.operation==='remote_clone' ? 'remote' : 'local'} clone</Button>
    </Box>}
    {catalog && <>
      <Table size="small" aria-label="Native MySQL clone jobs"><TableHead><TableRow>{['Job','Destination','State','Receipt'].map(value => <TableCell key={value}>{value}</TableCell>)}</TableRow></TableHead>
        <TableBody>{catalog.jobs.map(job => <TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{job.options.destination}</TableCell><TableCell>{job.state}</TableCell>
          <TableCell><Button disabled={busy} aria-label={'Inspect clone '+job.job_id} onClick={() => run('status',{job_id:job.job_id},setReceipt)}>Inspect</Button></TableCell></TableRow>)}</TableBody>
      </Table>
      <TablePagination component="div" count={catalog.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={page} onPageChange={(_event,next) => load(next)} />
      {catalog.unavailable_job_ids?.length>0 && <Alert severity="warning">Some clone receipts could not be read: {catalog.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={receipt.state==='native_completed' ? 'success' : ['refused','native_failed','unknown','not_dispatched'].includes(receipt.state) ? 'warning' : 'info'}>
        Job {receipt.job_id}: {receipt.state}. {receipt.observation_blocker}
        {receipt.state==='native_completed' && ' Native clone completion observed. File verification and recovery drill have separate receipts.'}
        {receipt.state==='unknown' && ' The server can still be copying. Reconcile native state; this job will not be replayed.'}
      </Alert>
      <Button disabled={busy} onClick={() => run('status',{job_id:receipt.job_id},setReceipt)}>Refresh clone receipt</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state) || receipt.state==='reviewed'} onClick={() => run('reconcile',{job_id:receipt.job_id},setReceipt)}>Reconcile native clone</Button>
      <Button disabled={busy || (!ACTIVE.has(receipt.state) && receipt.state!=='reviewed')} onClick={() => run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel {receipt.operation==='remote_clone' ? 'remote' : 'local'} clone</Button>
      <Button onClick={download}>Download clone receipt</Button>
      <Box component="details"><summary>Native clone observations and server directory</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
MySQLClone.propTypes={post:PropTypes.func.isRequired};
