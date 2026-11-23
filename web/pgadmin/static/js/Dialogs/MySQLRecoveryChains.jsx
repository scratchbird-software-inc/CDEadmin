import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';
import GridNavigation from '../cdeadmin_ui/data/GridNavigation';

export default function MySQLRecoveryChains({post}) {
  const [backups,setBackups]=useState(null),[archives,setArchives]=useState(null),[chains,setChains]=useState(null);
  const [base,setBase]=useState(''),[selected,setSelected]=useState([]),[mode,setMode]=useState('all'),[stop,setStop]=useState('');
  const [review,setReview]=useState(null),[created,setCreated]=useState(null),[lineage,setLineage]=useState(false);
  const [retirement,setRetirement]=useState(null),[retireConfirmed,setRetireConfirmed]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0);
  useEffect(()=> {
    generation.current++;setBackups(null);setArchives(null);setChains(null);setBase('');setSelected([]);
    setMode('all');setStop('');setReview(null);setCreated(null);setLineage(false);setRetirement(null);
    setRetireConfirmed(false);setError('');setBusy(false);
    return ()=>{generation.current++;};
  },[post]);
  const clear=()=>{setReview(null);setCreated(null);setLineage(false);};
  const run=async (action,request,accept)=> {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:'mysql_binlog_'+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Recovery dependency request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  const move=(index,delta)=>{clear();setSelected(values=>{const next=[...values];[next[index],next[index+delta]]=[next[index+delta],next[index]];return next;});};
  const loadBackups=offset=>run('backup_protection_list',{offset,limit:25},setBackups);
  const loadArchives=offset=>run('list',{offset,limit:25},setArchives);
  const loadChains=offset=>run('recovery_chain_list',{offset,limit:25},setChains);
  return <Box component="details" sx={{my:1}}>
    <FormReference formKey="mysql-recovery-chains" /><summary>Recovery chain dependencies</summary>
    <Alert severity="info">Choose a consistent managed logical dump and ordered completed Shell archives. MySQL checks their GTID prerequisites and the application verifies their retained bytes. An active chain protects its selected archives. Existing backup holds remain until separately retired. Raw archives, physical clone bases, external backups and offline replicas need their separate protection; this review does not discover them or perform a restore.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={()=>loadBackups(0)}>Load recovery base backups</Button>
    <Button disabled={busy} onClick={()=>loadArchives(0)}>Load recovery chain archives</Button>
    <Button disabled={busy} onClick={()=>loadChains(0)}>Load recovery chains</Button>
    {backups && <>
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Recovery base backups"
        rows={(backups.backups || []).map(row => ({
          id: row.backup_id,
          backup_id: row.backup_id,
          database: row.database,
          state: row.state,
          _raw: row,
        }))}
        columns={[
          {key: 'backup_id', name: 'Backup'},
          {key: 'database', name: 'Database'},
          {key: 'state', name: 'State'},
          {
            key: '_select',
            name: 'Select',
            render: (_val, r) => <Button disabled={busy || !(r._raw.native_dump_completion_acknowledged || r._raw.native_artifact_completion_observed) || !r._raw.native_consistent || r._raw.native_gtid_snapshot_inconsistent!==false} onClick={()=>{clear();setBase(r._raw.backup_id);}}>Use backup {r._raw.backup_id}</Button>,
          },
        ]}
        compact
        searchable={false}
        exportable={false}
      />
      <GridNavigation
        busy={busy}
        page={Math.floor((backups.offset || 0) / 25)}
        pages={Math.max(1, Math.ceil((backups.total || 0) / 25))}
        endKnown
        canNext={(backups.offset || 0) + 25 < (backups.total || 0)}
        onFirst={() => loadBackups(0)}
        onPrevious={() => loadBackups(Math.max(0, (backups.offset || 0) - 25))}
        onNext={() => loadBackups((backups.offset || 0) + 25)}
        onLast={() => loadBackups(Math.max(0, (Math.ceil((backups.total || 0) / 25) - 1) * 25))}
      />
    </>}
    {archives && <>
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Recovery chain archive choices"
        rows={(archives.jobs || []).map(row => ({
          id: row.job_id,
          job_id: row.job_id,
          state: row.state,
          _raw: row,
        }))}
        columns={[
          {key: 'job_id', name: 'Archive'},
          {key: 'state', name: 'State'},
          {
            key: '_select',
            name: 'Select',
            render: (_val, r) => <Button disabled={busy || selected.includes(r._raw.job_id) || r._raw.artifact_removed || !['completed','artifact_verified'].includes(r._raw.state)} onClick={()=>{clear();setSelected(values=>[...values,r._raw.job_id]);}}>Append archive {r._raw.job_id}</Button>,
          },
        ]}
        compact
        searchable={false}
        exportable={false}
      />
      <GridNavigation
        busy={busy}
        page={Math.floor((archives.offset || 0) / 25)}
        pages={Math.max(1, Math.ceil((archives.total || 0) / 25))}
        endKnown
        canNext={(archives.offset || 0) + 25 < (archives.total || 0)}
        onFirst={() => loadArchives(0)}
        onPrevious={() => loadArchives(Math.max(0, (archives.offset || 0) - 25))}
        onNext={() => loadArchives((archives.offset || 0) + 25)}
        onLast={() => loadArchives(Math.max(0, (Math.ceil((archives.total || 0) / 25) - 1) * 25))}
      />
      {archives.unavailable_job_ids?.length>0 && <Alert severity="warning">Some archive receipts are unavailable: {archives.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    <Box>Recovery base: {base || 'None selected'}</Box>
    <Box component="ol" aria-label="Ordered recovery archives">{selected.map((id,index)=><Box component="li" key={id}>{id}
      <Button disabled={busy || index===0} onClick={()=>move(index,-1)}>Move {id} earlier</Button>
      <Button disabled={busy || index===selected.length-1} onClick={()=>move(index,1)}>Move {id} later</Button>
      <Button disabled={busy} onClick={()=>{clear();setSelected(values=>values.filter(value=>value!==id));}}>Remove {id} from chain</Button>
    </Box>)}</Box>
    <TextField select size="small" label="Recovery chain target" disabled={busy} value={mode} onChange={event=>{clear();setMode(event.target.value);}}>{[['all','All selected archives'],['before','Before one GTID'],['after','After one GTID']].map(([value,label])=><MenuItem key={value} value={value}>{label}</MenuItem>)}</TextField>
    {mode!=='all' && <TextField size="small" label="Recovery chain stop GTID" disabled={busy} value={stop} onChange={event=>{clear();setStop(event.target.value);}} />}
    <Button disabled={busy || !base || !selected.length} onClick={()=>run('recovery_chain_review',{backup_id:base,archive_job_ids:selected,stop_mode:mode,stop_gtid:mode==='all' ? null : stop},value=>{setReview(value);setCreated(null);setLineage(false);})}>Review recovery dependencies</Button>
    {review && <Box>
      <Alert severity="warning">GTID sets do not attest a native log-generation epoch or data equivalence. Confirm that RESET BINARY LOGS AND GTIDS, GTID reuse or replaced source data has not mixed unrelated inputs. The final archive is retained in full even for a stop GTID. Other backup holds remain; retiring one is a separate action. No restore or cutover is performed.</Alert>
      <Box component="pre" aria-label="Recovery dependency review" sx={{whiteSpace:'pre-wrap',maxHeight:320,overflow:'auto'}}>{JSON.stringify(review.inputs,null,2)}</Box>
      <FormControlLabel label="I confirm these inputs belong to the original source GTID lineage" control={<Checkbox disabled={busy || !!created} checked={lineage} onChange={event=>setLineage(event.target.checked)} />} />
      <Button disabled={busy || !lineage || !!created} onClick={()=>run('recovery_chain_activate',{review_id:review.review_id,review_digest:review.review_digest,confirmed:true,source_lineage_confirmed:true},value=>{setCreated(value);setChains(null);})}>Protect reviewed recovery chain</Button>
    </Box>}
    {created && <Alert severity="success">Recovery chain {created.chain_id}: {created.state}. Its selected archives are protected. Existing backup holds remain. Recovery and cutover have not been verified.</Alert>}
    {chains && <>
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Retained recovery chains"
        rows={(chains.chains || []).map(row => ({
          id: row.chain_id,
          chain_id: row.chain_id,
          database: row.database,
          state: row.state,
          archives: row.archives.map(item=>item.job_id).join(' → '),
          _raw: row,
        }))}
        columns={[
          {key: 'chain_id', name: 'Chain'},
          {key: 'database', name: 'Database'},
          {key: 'state', name: 'State'},
          {key: 'archives', name: 'Archives'},
          {
            key: '_protection',
            name: 'Protection',
            render: (_val, r) => <Button disabled={busy || r._raw.state!=='active'} onClick={()=>run('recovery_chain_review_retire',{chain_id:r._raw.chain_id},value=>{setRetirement(value);setRetireConfirmed(false);})}>Review retirement of chain {r._raw.chain_id}</Button>,
          },
        ]}
        compact
        searchable={false}
        exportable={false}
      />
      <GridNavigation
        busy={busy}
        page={Math.floor((chains.offset || 0) / 25)}
        pages={Math.max(1, Math.ceil((chains.total || 0) / 25))}
        endKnown
        canNext={(chains.offset || 0) + 25 < (chains.total || 0)}
        onFirst={() => loadChains(0)}
        onPrevious={() => loadChains(Math.max(0, (chains.offset || 0) - 25))}
        onNext={() => loadChains((chains.offset || 0) + 25)}
        onLast={() => loadChains(Math.max(0, (Math.ceil((chains.total || 0) / 25) - 1) * 25))}
      />
    </>}
    {retirement && <Box>
      <Alert severity="warning">Retiring this chain releases its archive dependencies. Other holds and explicit archive pins still apply. Files remain until a separate removal action; deleting needed inputs can prevent recovery.</Alert>
      <Box component="pre" aria-label="Recovery dependency retirement" sx={{whiteSpace:'pre-wrap',maxHeight:200,overflow:'auto'}}>{JSON.stringify(retirement.chain,null,2)}</Box>
      <FormControlLabel label="Release this recovery chain's archive protection" control={<Checkbox disabled={busy} checked={retireConfirmed} onChange={event=>setRetireConfirmed(event.target.checked)} />} />
      <Button disabled={busy || !retireConfirmed} onClick={()=>run('recovery_chain_retire',{review_id:retirement.review_id,review_digest:retirement.review_digest,confirmed:true},()=>{setRetirement(null);setRetireConfirmed(false);setChains(null);})}>Confirm recovery chain retirement</Button>
    </Box>}
  </Box>;
}
MySQLRecoveryChains.propTypes={post:PropTypes.func.isRequired};
