import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Box, Stack} from '../cdeadmin_ui/primitives/Layout';
import {Button} from '../cdeadmin_ui/primitives/Button';
import {TextArea} from '../cdeadmin_ui/primitives/Field';
import {Select} from '../cdeadmin_ui/primitives/Choice';
import {Banner} from '../cdeadmin_ui/feedback/Indicators';
import {Dialog} from '../cdeadmin_ui/overlays/Dialog';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';
import {blobBytes, blobDraft, blobImport, BLOB_EDIT_LIMIT} from './firebirdBlobValue';

export default function FirebirdBlobEditor({value, kind, label, readOnly, onApply, onClose}) {
  const [draft, setDraft] = useState({...value});
  const [original, setOriginal] = useState(value.text);
  const [changed, setChanged] = useState(false);
  const [endings, setEndings] = useState('preserve');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const fileInputRef = useRef(null);

  useEffect(() => {
    generation.current++;
    setDraft({...value});
    setOriginal(value.text);
    setChanged(false);
    setEndings('preserve');
    setError(null);
    setBusy(false);
    return () => {
      generation.current++;
    };
  }, [value.text, value.isNull, kind, label, readOnly]);

  let oversized = false;
  try {
    oversized = blobBytes(original, kind).length > BLOB_EDIT_LIMIT;
  } catch {
    /* Validation is shown on apply/export. */
  }

  const resolved = () => blobDraft(original, draft, kind, endings, changed);
  const act = (callback) => {
    setError(null);
    try {
      callback();
    } catch (failure) {
      setError(failure.message);
    }
  };

  const importFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || readOnly) return;
    const serial = ++generation.current;
    setBusy(true);
    setError(null);
    try {
      if (file.size > BLOB_EDIT_LIMIT) {
        throw new Error('File exceeds the 1 MiB editor limit. Use chunked transfer.');
      }
      const text = blobImport(new Uint8Array(await file.arrayBuffer()), kind);
      if (serial === generation.current) {
        setDraft({text, isNull: false});
        setOriginal(text);
        setChanged(false);
        setEndings('preserve');
      }
    } catch (failure) {
      if (serial === generation.current) setError(failure.message);
    } finally {
      if (serial === generation.current) setBusy(false);
    }
  };

  const download = () => {
    const current = resolved();
    const url = URL.createObjectURL(
      new Blob([blobBytes(current.text, kind)], {
        type: kind === 'text' ? 'text/plain;charset=utf-8' : 'application/octet-stream',
      })
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = kind === 'text' ? 'firebird-blob.txt' : 'firebird-blob.bin';
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <Dialog
      open
      size="large"
      busy={busy}
      formKey="firebird-blob-editor"
      title={`${label} — BLOB`}
      onClose={busy ? undefined : onClose}
      actions={
        <>
          <Button disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button
            intent="primary"
            disabled={readOnly || busy || oversized}
            onClick={() =>
              act(() => {
                onApply(resolved());
                onClose();
              })
            }
          >
            Apply to row
          </Button>
        </>
      }
    >
      <Box sx={compactFormSx}>
        <Stack gap="compact">
          <Banner status="info">
            Apply stages this value in the row editor. Save the row separately. Text files use
            UTF-8. Editor limit: 1 MiB; use chunked transfer for larger values.
          </Banner>
          {error && <Banner status="error">{error}</Banner>}
          {oversized && (
            <Banner status="warning">
              This value exceeds the editor limit. Use the query BLOB transfer controls.
            </Banner>
          )}
          <Stack direction="row" gap="compact" sx={{flexWrap: 'wrap'}}>
            <Box sx={{minWidth: 200}}>
              <Select
                label="BLOB value mode"
                value={draft.isNull ? 'null' : 'value'}
                disabled={readOnly || busy || oversized}
                options={[
                  {value: 'value', label: 'Value (may be empty)'},
                  {value: 'null', label: 'NULL'},
                ]}
                onChange={(val) => setDraft({...draft, isNull: val === 'null'})}
              />
            </Box>
            {kind === 'text' && (
              <Box sx={{minWidth: 180}}>
                <Select
                  label="Line endings"
                  value={endings}
                  disabled={readOnly || busy || oversized || draft.isNull}
                  options={[
                    {value: 'preserve', label: 'Preserve original'},
                    {value: 'lf', label: 'LF'},
                    {value: 'crlf', label: 'CRLF'},
                  ]}
                  onChange={(val) => setEndings(val)}
                />
              </Box>
            )}
          </Stack>
          <TextArea
            rows={8}
            fullWidth
            label={kind === 'text' ? 'BLOB text' : 'BLOB Base64'}
            value={oversized ? '' : draft.text}
            disabled={busy || draft.isNull || oversized}
            readOnly={readOnly}
            onChange={(event) => {
              const val = event?.target ? event.target.value : String(event ?? '');
              setChanged(true);
              setDraft({...draft, text: val});
            }}
          />
          <Stack direction="row" gap="compact">
            <input
              ref={fileInputRef}
              hidden
              type="file"
              aria-label="Import BLOB file"
              disabled={readOnly || busy}
              onChange={importFile}
            />
            <Button disabled={readOnly || busy} onClick={() => fileInputRef.current?.click()}>
              Import file
            </Button>
            <Button disabled={busy || draft.isNull || oversized} onClick={() => act(download)}>
              Export file
            </Button>
          </Stack>
        </Stack>
      </Box>
    </Dialog>
  );
}

FirebirdBlobEditor.propTypes = {
  value: PropTypes.object.isRequired,
  kind: PropTypes.oneOf(['text', 'binary']).isRequired,
  label: PropTypes.string.isRequired,
  readOnly: PropTypes.bool,
  onApply: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};
