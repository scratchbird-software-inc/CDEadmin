import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';
import {useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {blobBytes, blobDraft, blobImport, BLOB_EDIT_LIMIT} from './firebirdBlobValue';

export default function FirebirdBlobEditor({value, kind, label, readOnly, onApply, onClose}) {
  const [draft, setDraft] = useState({...value});
  const [original, setOriginal] = useState(value.text);
  const [changed, setChanged] = useState(false);
  const [endings, setEndings] = useState('preserve');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  let oversized = false;
  try { oversized = blobBytes(original, kind).length > BLOB_EDIT_LIMIT; } catch { /* Validation is shown on apply/export. */ }
  const resolved = () => blobDraft(original, draft, kind, endings, changed);
  const act = (callback) => {setError(null); try {callback();} catch (failure) {setError(failure.message);} };
  const importFile = async (event) => {
    const file = event.target.files?.[0]; event.target.value = '';
    if (!file) return;
    setBusy(true); setError(null);
    try {
      if (file.size > BLOB_EDIT_LIMIT) throw new Error('File exceeds the 1 MiB editor limit. Use chunked transfer.');
      const text = blobImport(new Uint8Array(await file.arrayBuffer()), kind);
      setDraft({text, isNull: false}); setOriginal(text); setChanged(false); setEndings('preserve');
    } catch (failure) {setError(failure.message);} finally {setBusy(false);}
  };
  const download = () => {
    const current = resolved();
    const url = URL.createObjectURL(new Blob([blobBytes(current.text, kind)], {type: kind === 'text' ? 'text/plain;charset=utf-8' : 'application/octet-stream'}));
    const anchor = document.createElement('a'); anchor.href = url;
    anchor.download = kind === 'text' ? 'firebird-blob.txt' : 'firebird-blob.bin';
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Dialog open maxWidth="md" fullWidth onClose={busy ? undefined : onClose}>
    <DialogTitle>{label} — BLOB</DialogTitle>
    <DialogContent sx={compactFormSx}>
      <FormReference formKey="firebird-blob-editor" />
      <Alert severity="info">Apply stages this value in the row editor. Save the row separately. Text files use UTF-8. Editor limit: 1 MiB; use chunked transfer for larger values.</Alert>
      {error && <Alert severity="error">{error}</Alert>}
      {oversized && <Alert severity="warning">This value exceeds the editor limit. Use the query BLOB transfer controls.</Alert>}
      <TextField select label="BLOB value mode" value={draft.isNull ? 'null' : 'value'} disabled={readOnly || busy || oversized}
        onChange={event => setDraft({...draft, isNull: event.target.value === 'null'})}>
        <MenuItem value="value">Value (may be empty)</MenuItem><MenuItem value="null">NULL</MenuItem>
      </TextField>
      {kind === 'text' && <TextField select label="Line endings" value={endings} disabled={readOnly || busy || oversized || draft.isNull}
        onChange={event => setEndings(event.target.value)}>
        <MenuItem value="preserve">Preserve original</MenuItem><MenuItem value="lf">LF</MenuItem><MenuItem value="crlf">CRLF</MenuItem>
      </TextField>}
      <TextField fullWidth multiline minRows={8} maxRows={20} label={kind === 'text' ? 'BLOB text' : 'BLOB Base64'}
        value={oversized ? '' : draft.text} disabled={busy || draft.isNull || oversized} InputProps={{readOnly}}
        onChange={event => {setChanged(true); setDraft({...draft, text: event.target.value});}} />
      <Button component="label" disabled={readOnly || busy}>Import file
        <input hidden type="file" aria-label="Import BLOB file" disabled={readOnly || busy} onChange={importFile} />
      </Button>
      <Button disabled={busy || draft.isNull || oversized} onClick={() => act(download)}>Export file</Button>
    </DialogContent>
    <DialogActions>
      <Button disabled={busy} onClick={onClose}>Cancel</Button>
      <Button disabled={readOnly || busy || oversized} onClick={() => act(() => {onApply(resolved()); onClose();})}>Apply to row</Button>
    </DialogActions>
  </Dialog>;
}
FirebirdBlobEditor.propTypes = {value: PropTypes.object.isRequired, kind: PropTypes.oneOf(['text', 'binary']).isRequired,
  label: PropTypes.string.isRequired, readOnly: PropTypes.bool, onApply: PropTypes.func.isRequired, onClose: PropTypes.func.isRequired};
