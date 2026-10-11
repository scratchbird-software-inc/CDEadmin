import {useEffect, useRef, useState} from 'react';
import FirebirdBlobChunk from './FirebirdBlobChunk';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Table, TableBody, TableCell, TableHead, TableRow} from '@mui/material';
import gettext from 'sources/gettext';
import {saveFirebirdBlob} from './firebirdBlobFile';
import {saveFirebirdArray} from './firebirdArrayFile';
import {startFirebirdBrowserDownload} from './firebirdBrowserDownload';

function streamOwnerId() {
  return [...window.crypto.getRandomValues(new Uint8Array(16))]
    .map((value) => value.toString(16).padStart(2, '0')).join('');
}

// Keep only the visible page and one BLOB chunk. No background fetch loop.
export default function FirebirdResultStream({post, ensureSession, databaseTargetId,
  source, parameters, dialect, disabled, downloadUrl, bufferRows=100, onActiveChange}) {
  const [page, setPage] = useState(null);
  const [chunk, setChunk] = useState(null);
  const [busy, setBusy] = useState(false);
  const [owned, setOwned] = useState(false);
  useEffect(() => {onActiveChange?.(owned); return () => onActiveChange?.(false);}, [owned, onActiveChange]);
  const [error, setError] = useState(null);
  const [upload, setUpload] = useState(null);
  const [download, setDownload] = useState(null);
  const downloadTask = useRef(null);
  const session = useRef(null);
  const owner = useRef(null);
  if (owner.current === null) owner.current = streamOwnerId();
  const blobOffsets = useRef({});
  const arrayOffsets = useRef({});
  const cleanup = useRef(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (downloadTask.current) downloadTask.current.stopped = true;
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
        arrayOffsets.current = {};
        const parsed = JSON.parse(parameters || '[]');
        if (!Array.isArray(parsed)) throw new Error(gettext('Parameters must be an array.'));
        session.current = await ensureSession();
        setOwned(true);
        const id = session.current;
        ownCleanup(id);
        const result = await call(id, {stream_action: 'open', source,
          parameters: parsed, client_sql_dialect: dialect, page_rows: bufferRows});
        if (mounted.current) setPage(result);
        else cleanup.current?.();
      } else if (action === 'close') {
        await call(session.current, {stream_action: 'close'});
        cleanup.current = null;
        setOwned(false);
        setPage(null);
        setChunk(null);
        setUpload(null);
        setDownload(null);
        blobOffsets.current = {};
        arrayOffsets.current = {};
      } else if (action === 'next') {
        const result = await call(session.current, {stream_action: 'next',
          stream_reference: page.stream_reference, sequence: page.sequence + 1});
        setPage(result);
        setChunk(null);
        setDownload(null);
        blobOffsets.current = {};
        arrayOffsets.current = {};
      } else if (action === 'array') {
        const offset = arrayOffsets.current[blob]?.offset || 0;
        arrayOffsets.current[blob] = {offset};
        const result = await call(session.current, {stream_action: 'array',
          stream_reference: page.stream_reference, array_reference: blob, offset});
        arrayOffsets.current[blob] = {offset: result.next_offset, complete: result.complete};
        setChunk(result);
      } else {
        const offset = blobOffsets.current[blob]?.offset || 0;
        // A failed response may still have advanced the native reader.
        blobOffsets.current[blob] = {offset};
        const result = await call(session.current, {stream_action: 'blob',
          stream_reference: page.stream_reference, blob_reference: blob,
          offset});
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
  const uploadFile = async (file, kind='blob') => {
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
      const token = await call(id, {stream_action: 'upload_begin', value_kind: kind});
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
  const browserDownload = async (kind, reference) => {
    if (downloadTask.current || busy) return;
    const task = {stopped: false};
    downloadTask.current = task;
    setBusy(true);
    setError(null);
    setDownload({portable: true, active: true, bytes: 0});
    let token, removeFrame;
    const request = {stream_reference: page.stream_reference};
    try {
      token = await call(session.current, {...request, stream_action: 'download_begin',
        value_kind: kind, value_reference: reference});
      request.download_id = token.download_id;
      (kind === 'blob' ? blobOffsets : arrayOffsets).current[reference] = {offset: 0, complete: true};
      removeFrame = startFirebirdBrowserDownload(downloadUrl, {session_id: session.current,
        database_target_id: databaseTargetId, request: {owner_id: owner.current, ...request}});
      const started = Date.now();
      while (mounted.current && !task.stopped) {
        const status = await call(session.current, {...request, stream_action: 'download_status'});
        if (mounted.current) setDownload({portable: true, active: status.state !== 'sent',
          sent: status.state === 'sent', bytes: status.bytes});
        if (status.state === 'sent') return;
        if (status.state === 'interrupted') throw new Error(gettext('File delivery interrupted. Inspect browser downloads for a partial file.'));
        if (status.state === 'reserved' && Date.now() - started > 30000) {
          throw new Error(gettext('The browser did not start the download. No automatic retry was made.'));
        }
        await new Promise(resolve => setTimeout(resolve, 500));
      }
      throw new Error(gettext('File delivery stopped. Inspect browser downloads for a partial file.'));
    } catch (e) {
      if (mounted.current) setError(e.response?.data?.errormsg || e.message);
    } finally {
      if (token) {
        try { await call(session.current, {...request, stream_action: 'download_abort'}); }
        catch { /* Preserve unknown cleanup; never recreate the native owner. */ }
      }
      removeFrame?.();
      downloadTask.current = null;
      if (mounted.current) {
        setBusy(false);
        setDownload(value => value && {...value, active: false});
      } else cleanup.current?.();
    }
  };
  const saveBlob = async (reference) => {
    if (downloadTask.current || busy || blobOffsets.current[reference]) return;
    const task = {stopped: false};
    downloadTask.current = task;
    setBusy(true);
    setError(null);
    setDownload({bytes: 0, active: true});
    setChunk(null);
    try {
      // Keep picker invocation inside the button's user activation.
      const file = await window.showSaveFilePicker({suggestedName: 'firebird-blob.bin'});
      if (task.stopped || !mounted.current) throw new Error(gettext('BLOB save stopped.'));
      const writer = await file.createWritable({keepExistingData: false});
      const count = await saveFirebirdBlob({writer, reference,
        stopped: () => task.stopped || !mounted.current,
        read: offset => {
          // Even a lost response may have advanced the native reader.
          blobOffsets.current[reference] = {offset, complete: true};
          return call(session.current, {stream_action: 'blob',
            stream_reference: page.stream_reference, blob_reference: reference, offset});
        },
        progress: bytes => {
          if (mounted.current) setDownload({bytes, active: true});
        },
      });
      if (mounted.current) setDownload({bytes: count, active: false, saved: true});
    } catch (e) {
      if (mounted.current) {
        setDownload(null);
        setError(e.name === 'AbortError' ? gettext('BLOB save cancelled.') :
          (e.response?.data?.errormsg || e.message || gettext('BLOB save failed.')));
      }
    } finally {
      downloadTask.current = null;
      if (mounted.current) setBusy(false);
      else cleanup.current?.();
    }
  };
  const saveArray = async (descriptor) => {
    const reference = descriptor.array_reference;
    if (downloadTask.current || busy || arrayOffsets.current[reference]) return;
    const task = {stopped: false};
    downloadTask.current = task;
    setBusy(true);
    setError(null);
    setDownload({kind: 'array', elements: 0, active: true});
    setChunk(null);
    try {
      const file = await window.showSaveFilePicker({suggestedName: 'firebird-array.jsonl'});
      if (task.stopped || !mounted.current) throw new Error(gettext('ARRAY save stopped.'));
      const writer = await file.createWritable({keepExistingData: false});
      const result = await saveFirebirdArray({writer, descriptor,
        stopped: () => task.stopped || !mounted.current,
        read: offset => {
          arrayOffsets.current[reference] = {offset, complete: true};
          return call(session.current, {stream_action: 'array',
            stream_reference: page.stream_reference, array_reference: reference, offset});
        },
        progress: counts => {
          if (mounted.current) setDownload({kind: 'array', ...counts, active: true});
        },
      });
      if (mounted.current) setDownload({kind: 'array', ...result, active: false, saved: true});
    } catch (e) {
      if (mounted.current) {
        setDownload(null);
        setError(e.name === 'AbortError' ? gettext('ARRAY save cancelled.') :
          (e.response?.data?.errormsg || e.message || gettext('ARRAY save failed.')));
      }
    } finally {
      downloadTask.current = null;
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
    <label>{gettext('Stage ARRAY parameter (exported JSON Lines file)')}
      <input type="file" accept=".jsonl,application/x-ndjson" disabled={disabled || busy || owned || !!upload}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          uploadFile(file, 'array');
        }} />
    </label>
    {(upload?.blob_upload || upload?.array_upload) && <Alert severity="info">
      {gettext('Use this object as one query parameter. The upload is consumed once; transaction commit or rollback remains explicit.')}
      {' '}{gettext('Staged uploads expire after five minutes without stream requests.')}
      <code>{JSON.stringify(upload)}</code>
    </Alert>}
    {owned && <Alert severity="info">
      {gettext('Pull-based pages: at most 100 rows per fetch. Advancing discards the previous page and its BLOB and ARRAY references. Close the stream before other session operations. Closing does not commit or roll back. Cancellation does not confirm rollback.')}
      {' '}{gettext('Stream resources expire after five idle minutes. An expired stream must be closed. Expiry does not commit or roll back the transaction.')}
    </Alert>}
    {error && <Alert severity="error">{error}</Alert>}
    {download && <Box role="status">
      {download.portable ? <>{download.sent ? gettext('File sent to browser. Verify completion in browser downloads. Bytes:') : gettext('File delivery bytes:')} {download.bytes}</> : download.kind === 'array' ? <>
        {download.saved ? gettext('ARRAY file saved. Elements:') : gettext('ARRAY elements written:')} {download.elements}
      </> : <>{download.saved ? gettext('BLOB file saved. Bytes:') : gettext('BLOB bytes written:')} {download.bytes}</>}
      {download.active && <Button onClick={() => {
        if (downloadTask.current) downloadTask.current.stopped = true;
      }}>{download.portable ? gettext('Stop file delivery') : download.kind === 'array' ? gettext('Stop ARRAY save') : gettext('Stop BLOB save')}</Button>}
    </Box>}
    {page && typeof window.showSaveFilePicker !== 'function' && <Alert severity="info">
      {gettext('Use Download to browser for complete BLOB and ARRAY files. The browser controls the destination and partial-file cleanup.')}
    </Alert>}
    {page && <>
      <div>{gettext('Rows fetched:')} {page.rows_read}
        {page.end_of_cursor ? ' — ' + gettext('End of cursor') : ''}</div>
      <Box sx={{overflow: 'auto', maxHeight: 480}}>
        <Table size="small" aria-label={gettext('Streaming rows')}>
          <TableHead><TableRow>{page.columns.map((column, i) =>
            <TableCell key={i}>{column.name}</TableCell>)}</TableRow></TableHead>
          <TableBody>{page.rows.map((row, i) => <TableRow key={i}>
            {row.map((value, j) => <TableCell key={j}>
              {value?.blob_reference ? <><Button disabled={busy || blobOffsets.current[value.blob_reference]?.complete}
                onClick={() => run('blob', value.blob_reference)}>
                {gettext('Read BLOB chunk')}</Button>
              {typeof window.showSaveFilePicker === 'function' && <Button
                disabled={busy || !!blobOffsets.current[value.blob_reference]}
                onClick={() => saveBlob(value.blob_reference)}>{gettext('Save BLOB to file')}</Button>}
              {downloadUrl && <Button disabled={busy || !!blobOffsets.current[value.blob_reference]}
                onClick={() => browserDownload('blob', value.blob_reference)}>{gettext('Download BLOB to browser')}</Button>}
              </> : value?.array_reference ? <>
                <div>{gettext('ARRAY bounds:')} {JSON.stringify(value.bounds)}</div>
                <div>{gettext('Elements:')} {value.element_count}</div>
                <Button disabled={busy || arrayOffsets.current[value.array_reference]?.complete}
                  onClick={() => run('array', value.array_reference)}>{gettext('Read ARRAY slice')}</Button>
                {typeof window.showSaveFilePicker === 'function' && <Button
                  disabled={busy || !!arrayOffsets.current[value.array_reference]}
                  onClick={() => saveArray(value)}>{gettext('Save ARRAY to file')}</Button>}
                {downloadUrl && <Button disabled={busy || !!arrayOffsets.current[value.array_reference]}
                  onClick={() => browserDownload('array', value.array_reference)}>{gettext('Download ARRAY to browser')}</Button>}
              </> : JSON.stringify(value)}
            </TableCell>)}
          </TableRow>)}</TableBody>
        </Table>
      </Box>
    </>}
    {chunk?.blob_reference && <Box>
      <FirebirdBlobChunk chunk={chunk} />
      <Button disabled={busy || chunk.complete}
        onClick={() => run('blob', chunk.blob_reference)}>{gettext('Next BLOB chunk')}</Button>
    </Box>}
    {chunk?.array_reference && <Box>
      <div>{gettext('ARRAY elements:')} {chunk.offset}–{chunk.next_offset}</div>
      <div>{gettext('Starting coordinates:')} {JSON.stringify(chunk.coordinates)}</div>
      <Box component="pre" sx={{maxHeight: 160, overflow: 'auto', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>
        {JSON.stringify(chunk.values, null, 2)}
      </Box>
      <Button disabled={busy || chunk.complete}
        onClick={() => run('array', chunk.array_reference)}>{gettext('Next ARRAY slice')}</Button>
    </Box>}
  </Box>;
}
FirebirdResultStream.propTypes = {
  bufferRows: PropTypes.number, onActiveChange: PropTypes.func, downloadUrl: PropTypes.string,
  post: PropTypes.func.isRequired, ensureSession: PropTypes.func.isRequired,
  databaseTargetId: PropTypes.string, source: PropTypes.string.isRequired,
  parameters: PropTypes.string, dialect: PropTypes.number, disabled: PropTypes.bool,
};
