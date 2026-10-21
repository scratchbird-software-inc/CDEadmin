import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,Table,TableBody,TableCell,TableHead,TableRow,TablePagination} from '@mui/material';

export default function MySQLBackupProtection({post}) {
  const [page,setPage]=useState(null),[review,setReview]=useState(null),[confirmed,setConfirmed]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[retired,setRetired]=useState(null);
  const generation=useRef(0);
  useEffect(() => {generation.current++;setPage(null);setReview(null);setConfirmed(false);setRetired(null);setError('');setBusy(false);return () => {generation.current++;};},[post]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:'mysql_binlog_backup_protection_'+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Backup protection request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  const load=offset => run('list',{offset,limit:25},setPage);
  return <Box sx={{my:1}}>
    <Alert severity="info">Managed native dumps and physical clones protect application archives for this registration. Pending or uncertain records retain all of its archives; confirmed local source records retain archives from that source. Remote clone source UUIDs are not attested by the clone protocol, so their reviewed donor and recipient registrations retain all archives. These conservative holds do not verify recovery chains or discover external backups. Native server logs have separate administration.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={busy} onClick={() => load(0)}>Load managed backup protection</Button>
    {page && <>
      <Table size="small" aria-label="Managed backup protection"><TableHead><TableRow>{['Backup','Kind / database','State','Native source','Protection'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
        {page.backups.map(backup => <TableRow key={backup.backup_id}><TableCell>{backup.backup_id}</TableCell><TableCell>{backup.backup_kind==='mysql_native_physical_clone' ? 'Physical clone / '+backup.clone_role : backup.database}</TableCell><TableCell>{backup.state}</TableCell><TableCell>{backup.source.server_uuid}</TableCell><TableCell>
          <Button disabled={busy || backup.state==='retired'} aria-label={'Review retirement of backup '+backup.backup_id} onClick={() => run('review_retire',{backup_id:backup.backup_id},value => {setReview(value);setConfirmed(false);setRetired(null);})}>Review retirement</Button>
        </TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={page.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={page.offset/25} onPageChange={(_event,next) => load(next*25)} />
    </>}
    {review && <Box>
      <Alert severity="warning">{review.warning} Retiring a pending backup abandons its archive protection even if its native operation later returns.</Alert>
      <Box component="pre" aria-label="Managed backup retirement review" sx={{whiteSpace:'pre-wrap',maxHeight:260,overflow:'auto'}}>{JSON.stringify(review.backup,null,2)}</Box>
      <FormControlLabel label="Retire this backup from archive protection and recovery planning; keep its files" control={<Checkbox disabled={busy || !!retired} checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || !confirmed || !!retired} onClick={() => run('retire',{review_id:review.review_id,review_digest:review.review_digest,confirmed:true},value => {setRetired(value);setConfirmed(false);setPage(null);})}>Confirm backup protection retirement</Button>
    </Box>}
    {retired && <Alert severity="success">Backup protection {retired.backup_id}: retired. Backup files remain; no native backup or restore was repeated.</Alert>}
  </Box>;
}
MySQLBackupProtection.propTypes={post:PropTypes.func.isRequired};
