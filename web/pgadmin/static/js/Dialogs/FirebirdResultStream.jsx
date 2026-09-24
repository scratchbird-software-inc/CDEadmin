import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Table, TableBody, TableCell, TableHead, TableRow} from '@mui/material';
import gettext from 'sources/gettext';

function streamOwnerId() {
  return [...window.crypto.getRandomValues(new Uint8Array(16))]
    .map((value) => value.toString(16).padStart(2, '0')).join('');
}

// Keep only the visible page and one BLOB chunk. No background fetch loop.
export default function FirebirdResultStream({post, ensureSession, databaseTargetId,
  source, parameters, dialect, disabled}) {
  const [page, setPage] = useState(null);
  const [chunk, setChunk] = useState(null);
  const [busy, setBusy] = useState(false);
  const [owned, setOwned] = useState(false);
  const [error, setError] = useState(null);
  const [upload, setUpload] = useState(null);
  const session = useRef(null);
  const owner = useRef(null);
  if (owner.current === null) owner.current = streamOwnerId();
  const blobOffsets = useRef({});
  const cleanup = useRef(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      cleanup.current?.();
    };
  }, []);
  const call = (id, request) => post({action: 'query_stream', session_id: id,
    database_target_id: databaseTargetId, request: {owner_id: owner.current, ...request}});
  const ownCleanup = (id) => {
    const ownerId = owner.current;
    cleanup.current = () => call(id, {stream_action: 'close', owner_id: ownerId}).catch(() => {});
  };
  const run = async (action, blob=null) => {
    setBusy(true);
    setError(null);
    try {
      if (action === 'open') {
        if (!upload) owner.current = streamOwnerId();
        blobOffsets.current = {};
        const parsed = JSON.parse(parameters || '[]');
        if (!Array.isArray(parsed)) throw new Error(gettext('Parameters must be an array.'));
        session.current = await ensureSession();
        setOwned(true);
        const id = session.current;
        ownCleanup(id);
        const result = await call(id, {stream_action: 'open', source,
          parameters: parsed, client_sql_dialect: dialect});
        if (mounted.current) setPage(result);
        else cleanup.current?.();
      } else if (action === 'close') {
        await call(session.current, {stream_action: 'close'});
        cleanup.current = null;
        setOwned(false);
        setPage(null);
        setChunk(null);
        setUpload(null);
        blobOffsets.current = {};
      } else if (action === 'next') {
        const result = await call(session.current, {stream_action: 'next',
          stream_reference: page.stream_reference, sequence: page.sequence + 1});
        setPage(result);
        setChunk(null);
        blobOffsets.current = {};
      } else {
        const result = await call(session.current, {stream_action: 'blob',
          stream_reference: page.stream_reference, blob_reference: blob,
          offset: blobOffsets.current[blob]?.offset || 0});
        blobOffsets.current[blob] = {offset: result.next_offset, complete: result.complete};
        setChunk(result);
      }
    } catch (e) {
      setError(e.response?.data?.errormsg || e.message || gettext('Streaming failed.'));
    } finally {
      if (mounted.current) setBusy(false);
      else cleanup.current?.();
    }
  };
  const uploadFile = async (file) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      if (file.size > 256 * 1024 * 1024) throw new Error(gettext('Upload limit is 256 MiB.'));
      const id = await ensureSession();
      session.current = id;
      owner.current = streamOwnerId();
      ownCleanup(id);
      setUpload({pending: true});
      const token = await call(id, {stream_action: 'upload_begin'});
      for (let offset = 0; offset < file.size; offset += 65536) {
        if (!mounted.current) throw new Error(gettext('Upload closed.'));
        const bytes = new Uint8Array(await file.slice(offset, offset + 65536).arrayBuffer());
        let binary = '';
        for (const value of bytes) binary += String.fromCharCode(value);
        await call(id, {stream_action: 'upload_chunk', ...token, offset, data: btoa(binary)});
      }
      await call(id, {stream_action: 'upload_finish', ...token});
      setUpload(token);
    } catch (e) {
      setError(e.response?.data?.errormsg || e.message);
    } finally {
      if (mounted.current) setBusy(false);
      else cleanup.current?.();
    }
  };
  return <Box role="region" aria-label={gettext('Firebird streaming result')} sx={{mt: 1}}>
    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap'}}>
      <Button disabled={disabled || busy || owned || !source.trim()}
        onClick={() => run('open')}>{gettext('Run streaming')}</Button>
      <Button disabled={busy || !page || page.end_of_cursor}
        onClick={() => run('next')}>{gettext('Next stream page')}</Button>
      <Button disabled={busy || (!owned && !upload)} onClick={() => run('close')}>
        {gettext('Close stream')}</Button>
      <Button disabled={!busy || !owned} onClick={async () => {
        try {
          await call(session.current, {stream_action: 'cancel'});
          setError(gettext('Cancellation requested. Wait for the native outcome, then close the stream and inspect the transaction before retrying.'));
        } catch {
          setError(gettext('Cancellation delivery is unknown. Do not replay the statement.'));
        }
      }}>{gettext('Cancel stream request')}</Button>
    </Box>
    <label>{gettext('Stage BLOB parameter (raw file bytes)')}
      <input type="file" disabled={disabled || busy || owned || !!upload}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          uploadFile(file);
        }} />
    </label>
    {upload?.blob_upload && <Alert severity="info">
      {gettext('Use this object as one query parameter. The upload is consumed once; transaction commit or rollback remains explicit.')}
      <code>{JSON.stringify(upload)}</code>
    </Alert>}
    {owned && <Alert severity="info">
      {gettext('Pull-based pages: at most 100 rows per fetch. Advancing discards the previous page and its BLOB references. Close the stream before other session operations. Closing does not commit or roll back. Cancellation does not confirm rollback.')}
    </Alert>}
    {error && <Alert severity="error">{error}</Alert>}
    {page && <>
      <div>{gettext('Rows fetched:')} {page.rows_read}
        {page.end_of_cursor ? ' — ' + gettext('End of cursor') : ''}</div>
      <Box sx={{overflow: 'auto', maxHeight: 480}}>
        <Table size="small" aria-label={gettext('Streaming rows')}>
          <TableHead><TableRow>{page.columns.map((column, i) =>
            <TableCell key={i}>{column.name}</TableCell>)}</TableRow></TableHead>
          <TableBody>{page.rows.map((row, i) => <TableRow key={i}>
            {row.map((value, j) => <TableCell key={j}>
              {value?.blob_reference ? <Button disabled={busy || blobOffsets.current[value.blob_reference]?.complete}
                onClick={() => run('blob', value.blob_reference)}>
                {gettext('Read BLOB chunk')}</Button> : JSON.stringify(value)}
            </TableCell>)}
          </TableRow>)}</TableBody>
        </Table>
      </Box>
    </>}
    {chunk && <Box>
      <div>{gettext('BLOB bytes:')} {chunk.offset}–{chunk.next_offset} ({gettext('base64')})</div>
      <Box component="pre" sx={{maxHeight: 160, overflow: 'auto', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{chunk.data}</Box>
      <Button disabled={busy || chunk.complete}
        onClick={() => run('blob', chunk.blob_reference)}>{gettext('Next BLOB chunk')}</Button>
    </Box>}
  </Box>;
}
FirebirdResultStream.propTypes = {
  post: PropTypes.func.isRequired, ensureSession: PropTypes.func.isRequired,
  databaseTargetId: PropTypes.string, source: PropTypes.string.isRequired,
  parameters: PropTypes.string, dialect: PropTypes.number, disabled: PropTypes.bool,
};
