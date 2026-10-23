import {useEffect,useId,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TextField,Typography} from '@mui/material';

const defaults={consistency:'innodb_snapshot',replica:false,channel:'',seconds:300,disk_mib:256,examples:50};

export default function MySQLDataDrift({post,databaseTargetId=null}) {
  const [peer,setPeer]=useState(''),[peers,setPeers]=useState([]),[peerOffset,setPeerOffset]=useState(null);
  const [schemas,setSchemas]=useState(['','']),[names,setNames]=useState(['','']),[databases,setDatabases]=useState([[],[]]);
  const [databaseOffsets,setDatabaseOffsets]=useState([null,null]),[tablePages,setTablePages]=useState([null,null]);
  const [observed,setObserved]=useState([null,null]),[pairs,setPairs]=useState([]),[options,setOptions]=useState(defaults);
  const [consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[job,setJob]=useState(null);
  const generation=useRef(0),refs=useRef({post,job});refs.current={post,job};const listId=useId();
  const active=Boolean(job && !job.terminal),fixed=busy || Boolean(job);
  const api=(operation,request={}) => refs.current.post({action:`mysql_drift_${operation}`,
    request:{database_target_id:databaseTargetId,peer_endpoint_id:Number(peer),...request}});
  useEffect(() => {
    const originalPost=refs.current.post;
    generation.current++;setPairs([]);setObserved([null,null]);setConsent(false);setJob(null);setError('');setBusy(false);
    setSchemas(['','']);setNames(['','']);setDatabases([[],[]]);setDatabaseOffsets([null,null]);setTablePages([null,null]);
    return () => {
      generation.current++;
      const current=refs.current.job;
      if(current && !current.terminal)originalPost({action:'mysql_drift_cancel',request:{database_target_id:databaseTargetId,
        peer_endpoint_id:Number(peer),job_id:current.job_id}}).catch(() => {});
    };
  },[databaseTargetId,peer]);
  useEffect(() => {
    if(!active)return undefined;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const value=await api('status',{job_id:job.job_id});if(live)setJob(value);}
      catch(failure) {if(live) {setError(failure.response?.data?.errormsg || failure.message);setJob(current => ({...current,state:'unavailable',terminal:true,coverage:[],positions:[]}));}}
      finally {pending=false;}
    },1000);
    return () => {live=false;clearInterval(timer);};
  },[active,job?.job_id,databaseTargetId,peer]);
  const run=async (operation,request,accept) => {
    const token=++generation.current,originalPost=refs.current.post;
    setBusy(true);setError('');
    try {
      const value=await api(operation,request);
      if(token===generation.current)accept(value);
      else if(operation==='start' && value?.job_id)originalPost({action:'mysql_drift_cancel',request:{database_target_id:databaseTargetId,
        peer_endpoint_id:Number(peer),job_id:value.job_id}}).catch(() => {});
    } catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===generation.current)setBusy(false);}
  };
  const replace=(setter,index,value) => setter(current => current.map((old,i) => i===index ? value : old));
  const invalidate=() => {generation.current++;setObserved([null,null]);setConsent(false);};
  const databasePage=(index,offset=0) => run('databases',{side:index===0 ? 'source':'target',offset},value => {
    replace(setDatabases,index,offset ? [...databases[index],...value.rows] : value.rows);replace(setDatabaseOffsets,index,value.next_offset);
  });
  const tablePage=(index,offset=0) => run('tables',{side:index===0 ? 'source':'target',schema_name:schemas[index],offset},value => replace(setTablePages,index,value));
  const download=() => {
    const url=URL.createObjectURL(new Blob([JSON.stringify(job,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='mysql-data-comparison.json';link.click();URL.revokeObjectURL(url);
  };
  return <Box aria-label="MySQL full-table data comparison" sx={{p:1,height:'100%',overflow:'auto'}}>
    <Typography component="h3">MySQL full-table data comparison</Typography>
    <Alert severity="warning">This operation takes server-wide native read locks on both endpoints. InnoDB snapshot mode releases them after pinning all selected tables;
      server-locked mode holds them through the scans. Writes and DDL may wait. Long read-only snapshots can retain undo versions.
      Closing this workspace requests cancellation; the server runtime limit remains in force if delivery fails.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={fixed} onClick={() => run('peers',{offset:peerOffset || 0},value => {
      setPeers(current => [...current,...value.rows.filter(row => !current.some(old => old.endpoint_id===row.endpoint_id))]);setPeerOffset(value.next_offset);
    })}>{peerOffset===null ? 'Discover registered comparison endpoints' : 'More comparison endpoints'}</Button>
    <TextField select size="small" label="Comparison target endpoint" value={peer} disabled={fixed} onChange={event => setPeer(event.target.value)}>
      {peers.map(item => <MenuItem key={item.endpoint_id} value={String(item.endpoint_id)}>{item.label}</MenuItem>)}
    </TextField>
    <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',md:'1fr 1fr'},gap:1,my:1}}>
      {['Source','Target'].map((title,index) => <Box key={title}>
        <Typography component="h4">{title} native scope</Typography>
        <Button disabled={fixed || !peer} onClick={() => databasePage(index)}>Discover {title.toLowerCase()} databases</Button>
        {databaseOffsets[index]!==null && <Button disabled={fixed} onClick={() => databasePage(index,databaseOffsets[index])}>More {title.toLowerCase()} databases</Button>}
        <TextField size="small" label={`${title} comparison database`} value={schemas[index]} disabled={fixed} inputProps={{list:`${listId}-${index}`}}
          onChange={event => {invalidate();replace(setSchemas,index,event.target.value);setPairs([]);replace(setTablePages,index,null);}} />
        <datalist id={`${listId}-${index}`}>{databases[index].map(item => <option key={item.name} value={item.name} />)}</datalist>
        <Button disabled={fixed || !peer || !schemas[index]} onClick={() => tablePage(index)}>Discover {title.toLowerCase()} tables</Button>
        {tablePages[index]?.next_offset!=null && <Button disabled={fixed} onClick={() => tablePage(index,tablePages[index].next_offset)}>More {title.toLowerCase()} tables</Button>}
        <Box sx={{maxHeight:150,overflow:'auto'}}>{tablePages[index]?.rows.map(item => <Button key={item.name} disabled={fixed || item.kind!=='BASE TABLE'} onClick={() => {
          invalidate();replace(setNames,index,item.name);
        }}>{item.name} ({item.engine || item.kind})</Button>)}</Box>
        <TextField size="small" label={`${title} complete table`} value={names[index]} disabled={fixed} onChange={event => {invalidate();replace(setNames,index,event.target.value);}} />
        <Button disabled={fixed || !peer || !schemas[index] || !names[index]} onClick={() => run('describe',{
          side:index===0 ? 'source':'target',schema_name:schemas[index],table_name:names[index]},value => replace(setObserved,index,value))}>Observe {title.toLowerCase()} table</Button>
        {observed[index] && <Typography>{observed[index].server_uuid}: {observed[index].engine}; {observed[index].column_count} logical columns;
          native key: {observed[index].key.join(', ') || 'none (duplicate-aware multiset scan)'}.</Typography>}
      </Box>)}
    </Box>
    <Button disabled={fixed || observed.some(value => !value) || pairs.length>=64} onClick={() => {
      const pair={source_table:names[0],target_table:names[1],source_fingerprint:observed[0].fingerprint,target_fingerprint:observed[1].fingerprint};
      setPairs(current => [...current.filter(old => old.source_table!==pair.source_table && old.target_table!==pair.target_table),pair]);setConsent(false);
    }}>Add complete table pair</Button>
    <Table size="small" aria-label="Selected complete table pairs"><TableHead><TableRow><TableCell>Source</TableCell><TableCell>Target</TableCell><TableCell>Selection</TableCell></TableRow></TableHead>
      <TableBody>{pairs.map(pair => <TableRow key={pair.source_table}><TableCell>{pair.source_table}</TableCell><TableCell>{pair.target_table}</TableCell>
        <TableCell><Button disabled={fixed} onClick={() => {setPairs(current => current.filter(old => old!==pair));setConsent(false);}}>Remove pair</Button></TableCell></TableRow>)}</TableBody></Table>
    <Box sx={{display:'flex',flexWrap:'wrap',gap:1,my:1}}>
      <TextField select size="small" label="Native comparison consistency" value={options.consistency} disabled={fixed}
        onChange={event => {setOptions(current => ({...current,consistency:event.target.value}));setConsent(false);}}>
        <MenuItem value="innodb_snapshot">InnoDB native snapshots</MenuItem><MenuItem value="locked_scan">Hold server read locks through scans</MenuItem>
      </TextField>
      <FormControlLabel label="Align target replica to source GTID boundary" control={<Checkbox checked={options.replica} disabled={fixed}
        onChange={event => {setOptions(current => ({...current,replica:event.target.checked}));setConsent(false);}} />} />
      <TextField size="small" label="Target native replica channel (blank for default)" value={options.channel} disabled={fixed || !options.replica}
        onChange={event => {setOptions(current => ({...current,channel:event.target.value}));setConsent(false);}} />
      {[['seconds','Comparison maximum seconds'],['disk_mib','Private sort disk MiB'],['examples','Maximum private mismatch examples']].map(([key,label]) =>
        <TextField key={key} size="small" type="number" label={label} value={options[key]} disabled={fixed}
          onChange={event => {setOptions(current => ({...current,[key]:Number(event.target.value)}));setConsent(false);}} />)}
    </Box>
    <Alert severity="info">Every admitted logical column and row is scanned. Native SHA256 cell projections and binary-protocol IEEE values form duplicate-aware row multisets.
      This is a cryptographic checksum comparison at the recorded native positions. It does not establish physical byte equality or coverage of unselected/invisible tables.
      Native warnings, denied reads, changed structures, cancellation and resource limits remain incomplete. Private key examples expire five minutes after completion.</Alert>
    <FormControlLabel label="Allow native server read locks and complete private table scans" control={<Checkbox checked={consent} disabled={fixed}
      onChange={event => setConsent(event.target.checked)} />} />
    <Button disabled={fixed || !peer || !pairs.length || !consent} onClick={() => run('start',{
      source_schema:schemas[0],target_schema:schemas[1],tables:pairs,options,confirmed:true},setJob)}>Start full native comparison</Button>
    <Button disabled={busy || !active} onClick={() => run('cancel',{job_id:job.job_id},setJob)}>Cancel native comparison</Button>
    <Button disabled={busy || !job?.terminal} onClick={() => run('forget',{job_id:job.job_id},() => {setJob(null);setConsent(false);})}>Clear private comparison</Button>
    <Button disabled={!job?.terminal} onClick={download}>Download private comparison report</Button>
    {job && <Box aria-label="Native full-table comparison report">
      <Alert severity={job.state==='completed' ? 'success':'info'}>Comparison: {job.state}. Stage: {job.stage}. {job.elapsed_seconds} seconds.</Alert>
      {job.error?.reason && <Alert severity="error">{job.error.reason} {job.error.error_code ? `Native error ${job.error.error_code} / ${job.error.sqlstate}` : ''}</Alert>}
      <Typography>Private sort peak: {job.disk_peak_bytes} bytes. Repairs dispatched: {String(job.repair_dispatched)}.</Typography>
      <Alert severity="info">Mismatches identify source-only and target-only row versions, including duplicate multiplicity.
        A changed key can appear on both sides. Use the native table data editor for a separate exact-target repair review; verification never applies repairs.</Alert>
      {job.coverage.map((report,index) => <Box key={index} sx={{my:1}}>
        <Typography component="h4">{report.source_table} → {report.target_table}: {report.state}</Typography>
        <Typography>{report.reason} Source scanned: {report.source_rows ?? report.source_scanned_rows ?? 'unavailable'};
          target scanned: {report.target_rows ?? report.target_scanned_rows ?? 'unavailable'}.
          Source-only rows: {report.source_only_rows ?? 'unavailable'}; target-only rows: {report.target_only_rows ?? 'unavailable'}.</Typography>
        {report.examples?.map((example,i) => <Typography key={i} sx={{overflowWrap:'anywhere'}}>{example.side}: {example.row_sha256};
          key {example.key.length ? JSON.stringify(example.key) : 'unavailable (no native unique key)'}</Typography>)}
        {report.examples_truncated && <Typography>Mismatch examples are bounded; total mismatch counts cover the full completed scans.</Typography>}
      </Box>)}
      <TextField label="Native comparison positions and release observations" multiline minRows={4} maxRows={14} sx={{width:'100%'}}
        value={JSON.stringify({identities:job.identities,positions:job.positions,release:job.release,cancellation:job.cancellation},null,2)} slotProps={{input:{readOnly:true}}} />
    </Box>}
  </Box>;
}
MySQLDataDrift.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string};
