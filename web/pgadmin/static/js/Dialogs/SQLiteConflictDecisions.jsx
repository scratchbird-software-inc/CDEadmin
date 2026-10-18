import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,Table,TableBody,TableCell,TableHead,TableRow} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';

export default function SQLiteConflictDecisions({post,databaseTargetId,receipt,endpointUrl,disabled,onReceipt}) {
  const [observation,setObservation]=useState(null),[remember,setRemember]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const serial=useRef(0),downloads=useRef([]),pending=receipt?.pending_conflict,challenge=pending?.challenge,jobId=receipt?.job_id;
  useEffect(() => {
    const token=++serial.current;setObservation(null);setRemember(false);setBusy(false);setError('');
    if(!challenge)return undefined;
    post({action:'sqlite_changeset_conflict',request:{database_target_id:databaseTargetId,job_id:jobId,challenge}})
      .then(value => {if(token===serial.current)setObservation(value);})
      .catch(failure => {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);});
    return () => {serial.current++;};
  },[post,databaseTargetId,jobId,challenge]);
  useEffect(() => () => {downloads.current.forEach(close => close());},[]);
  const decide=async choice => {
    const token=serial.current;setBusy(true);setError('');
    try {
      const value=await post({action:'sqlite_changeset_decide',request:{database_target_id:databaseTargetId,job_id:jobId,response:{challenge,choice,remember_kind:remember}}});
      if(token===serial.current)onReceipt(value);
    } catch(failure){if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===serial.current)setBusy(false);}
  };
  const download=value => {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{database_target_id:databaseTargetId,job_id:jobId,challenge,side:value.side,column_index:value.column_index},
      {action:'sqlite_changeset_conflict_value_download',prefix:'sqlite-conflict',title:'SQLite native conflict value download'}));}
    catch(failure){setError(failure.message);}
  };
  if(!challenge)return null;
  const event=observation?.event,blocked=busy || disabled || !pending.waiting || receipt.state!=='active' || receipt.conflict_response?.challenge===challenge;
  return <Box sx={{my:1}}>
    <Alert severity="warning">The owned apply transaction stays open while its native callback waits. Locks remain until a response, cancellation or the configured timeout. Closing this viewer does not cancel the job.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {event && <>
      <Alert severity="info">Native {event.kind_name} conflict {event.sequence}. Incoming values include the reviewed inversion flag. Apply change sequence is separate from a source-file record ordinal.</Alert>
      {event.kind_name==='foreign_key' && <Alert severity="warning">Native foreign-key violations: {event.foreign_key_count}. OMIT can keep those violations when the owned transaction commits.</Alert>}
      <Box component="pre" aria-label="Native SQLite live conflict" sx={{whiteSpace:'pre-wrap',maxHeight:360,overflow:'auto'}}>{JSON.stringify(event,null,2)}</Box>
      {event.byte_values?.length>0 && <Table size="small" aria-label="Native conflict byte values"><TableHead><TableRow>{['Values','Column position','Type','Bytes','Download'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>
        {event.byte_values.map(value => <TableRow key={value.side+':'+value.column_index}><TableCell>{value.side}</TableCell><TableCell>{value.column_index+1}</TableCell><TableCell>{value.native_type}</TableCell><TableCell>{value.byte_length}</TableCell><TableCell><Button disabled={busy || !endpointUrl} onClick={() => download(value)}>Download {value.side} column {value.column_index+1} bytes</Button></TableCell></TableRow>)}
      </TableBody></Table>}
      <FormControlLabel label="Use this choice for remaining conflicts of this kind" control={<Checkbox checked={remember} disabled={blocked} onChange={input => setRemember(input.target.checked)} />} />
      {event.allowed_choices.map(choice => <Button key={choice} disabled={blocked} color={choice==='abort' ? 'warning':'primary'} onClick={() => decide(choice)}>Use native {choice} for this conflict</Button>)}
      {receipt.conflict_response?.challenge===challenge && <Alert severity="info">Response admitted. Native consumption and database commit have separate acknowledgements.</Alert>}
      {!pending.waiting && <Alert severity="info">This callback has ended. Inspect its native acknowledgement and the final operation state.</Alert>}
    </>}
  </Box>;
}
SQLiteConflictDecisions.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string.isRequired,receipt:PropTypes.object,
  endpointUrl:PropTypes.string,disabled:PropTypes.bool,onReceipt:PropTypes.func.isRequired};
