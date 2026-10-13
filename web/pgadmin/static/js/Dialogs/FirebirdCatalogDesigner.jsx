import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Dialog} from '@mui/material';
import {DDNDesignerSurface} from '../cdeadmin_ui/integrations/ddn';
import {validateDDNSnapshot} from '../cdeadmin_ui/integrations/ddn/contracts';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import FirebirdDesignStorage from './FirebirdDesignStorage';
import {refreshDesign} from '../cdeadmin_ui/integrations/ddn/designMerge';

export function nativeCatalogSnapshot(value) {
  validateDDNSnapshot(value);
  const {format, entry, view, files} = value;
  return {format, entry, view, files};
}

export default function FirebirdCatalogDesigner({baseline, disabled, onReview, post, databaseTargetId, engine='firebird'}) {
  const [open, setOpen] = useState(false), [error, setError] = useState('');
  const [draft, setDraft] = useState(null), [ready, setReady] = useState(false);
  const editor = useRef(null), seed = useRef(null);
  const original = useRef(null);
  const [merging, setMerging] = useState(false), [changed, setChanged] = useState(false);
  const epoch = useRef(0);
  const initial = useMemo(() => {
    if (!baseline) return null;
    try {
      return nativeCatalogSnapshot(baseline.trimStart().startsWith('{') ? JSON.parse(baseline) : {
        format: 'ddn-workspace@1', entry: 'catalog.ddn', view: 'inventory_1', files: {'catalog.ddn': baseline},
      });
    } catch {return null;}
  }, [baseline]);
  useEffect(() => {
    epoch.current++; setMerging(false);
    if (original.current && (draft || open)) {setChanged(JSON.stringify(original.current) !== JSON.stringify(initial)); return;}
    setOpen(false); setReady(false); setError(''); editor.current = null; original.current = initial;
  }, [initial]);
  useEffect(() => () => {epoch.current++;}, []);
  const capture = (review) => {
    try {
      if (!editor.current) throw new Error('The DDN editor is not ready.');
      const value = editor.current.snapshot();
      const metadata = nativeCatalogSnapshot(value);
      if (review) onReview(JSON.stringify(metadata), JSON.stringify(original.current));
      setDraft(value); setOpen(false); editor.current = null; setReady(false); setError('');
    } catch (failure) {setError(failure.message || 'Unable to capture the current catalog design.');}
  };
  return <Box>
    <Button disabled={disabled || merging || !initial} onClick={() => {
      seed.current = draft || initial; editor.current = null; setReady(false); setError(''); setOpen(true);
    }}>Edit catalog design in DDN</Button>
    {changed && <Alert severity="warning">A newer native capture is available. The authored design and original baseline are retained.</Alert>}
    <Button disabled={disabled || open || merging || !post || !draft || !initial} onClick={async () => {
      const serial = ++epoch.current; setMerging(true); setError('');
      try {
        const value = await refreshDesign(post, original.current, draft, initial);
        if (serial !== epoch.current) return;
        setDraft(value); original.current = initial; setChanged(false);
      } catch (failure) {if (serial === epoch.current) setError(failure.message);}
      finally {if (serial === epoch.current) setMerging(false);}
    }}>Merge latest native catalog into design</Button>
    {!open && error && <Alert severity="error">{error}</Alert>}
    <FirebirdDesignStorage post={post} databaseTargetId={databaseTargetId} kind="catalog" engine={engine} disabled={disabled || merging || open || !initial}
      capture={() => ({snapshot: draft || initial, baseline: original.current})}
      onLoad={value => {setDraft(value.snapshot); original.current = value.baseline; setError('');
        setChanged(JSON.stringify(value.baseline) !== JSON.stringify(initial));}} />
    <Dialog fullScreen open={open} onClose={() => {if (ready && !disabled) capture(false);}}>
      <Box sx={{display: 'flex', alignItems: 'center', gap: 1, p: 1}}>
        <FormReference formKey={`${engine}-catalog-designer`} />
        <Box sx={{flex: 1}}>Catalog design — native changes require separate review and confirmation.</Box>
        <Button disabled={!ready || disabled} onClick={() => capture(true)}>Use design for native review</Button>
        <Button disabled={!ready || disabled} onClick={() => capture(false)}>Keep draft and return</Button>
        <Button disabled={disabled} onClick={() => {setOpen(false); editor.current = null; setReady(false); setError('');}}>Discard editor changes</Button>
      </Box>
      <Alert severity="info">Edit native_json for database definitions. Diagram labels and layout do not rename database objects. The complete catalog is retained across inventory views.</Alert>
      {error && <Alert severity="error">{error}</Alert>}
      <Box sx={{flex: 1, minHeight: 0}}>
        {open && <DDNDesignerSurface snapshot={seed.current}
          onReady={value => {editor.current = value; setReady(true);}}
          onError={failure => {setReady(false); setError(failure.message || 'DDN editor unavailable.');}} />}
      </Box>
    </Dialog>
  </Box>;
}
FirebirdCatalogDesigner.propTypes = {baseline: PropTypes.string, disabled: PropTypes.bool, onReview: PropTypes.func.isRequired,
  post: PropTypes.func, databaseTargetId: PropTypes.string,
  engine: PropTypes.oneOf(['firebird', 'duckdb'])};
