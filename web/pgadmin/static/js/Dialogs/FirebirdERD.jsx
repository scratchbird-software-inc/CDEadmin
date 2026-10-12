import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Dialog} from '@mui/material';
import {DDNDesignerSurface, DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {validateDDNSnapshot} from '../cdeadmin_ui/integrations/ddn/contracts';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import FirebirdDesignStorage from './FirebirdDesignStorage';
import {refreshDesign} from '../cdeadmin_ui/integrations/ddn/designMerge';

export default function FirebirdERD({diagram, post, databaseTargetId, generation, onReview, engine='firebird'}) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState(diagram.snapshot);
  const selected = useRef({entry: diagram.snapshot?.entry, view: diagram.snapshot?.view});
  const seed = useRef(diagram.snapshot);
  const baseline = useRef(diagram.snapshot);
  const [merging, setMerging] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const editor = useRef(null);
  const fileToken = useRef(0);
  useEffect(() => {fileToken.current++; setMerging(false); setReviewing(false);}, [diagram.snapshot]);
  useEffect(() => {
    fileToken.current++; setEditing(false); setError(null); setDraft(diagram.snapshot);
    selected.current = {entry: diagram.snapshot?.entry, view: diagram.snapshot?.view};
    seed.current = baseline.current = diagram.snapshot; editor.current = null;
  }, [engine, databaseTargetId]);
  useEffect(() => () => {fileToken.current++;}, []);
  const snapshot = () => ({...draft, ...selected.current});
  const download = (content, name, type) => {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const link = document.createElement('a'); link.href = url; link.download = name; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const captureEditor = () => {
    const value = editor.current?.snapshot() || draft;
    setDraft(value); selected.current = {entry: value.entry, view: value.view};
    return value;
  };
  const closeEditor = () => {
    try {captureEditor(); editor.current = null; setEditing(false);}
    catch {setError('Unable to capture the current design. Keep the editor open and download it from DDN.');}
  };
  if (diagram.unavailable) return <Alert severity="warning">Relational diagram unavailable: {diagram.unavailable}</Alert>;
  return <Box sx={{display: 'flex', flexDirection: 'column', minHeight: 600, gap: 1}}>
    <FormReference formKey={`${engine}-relational-diagram`} />
    <Alert severity="info">Native tables, views, columns and foreign keys. Diagram edits do not alter the database. Save a design revision or download it to retain changes. Native application requires schema reconciliation and explicit review.</Alert>
    {(diagram.warnings || []).map((warning, index) => <Alert severity="warning" key={index}>{warning}</Alert>)}
    <Box>
      <Button disabled={editing || merging || reviewing} onClick={() => {
        seed.current = snapshot(); editor.current = null; setEditing(true);
      }}>Edit relational diagram in DDN</Button>
      <Button component="label" disabled={merging || reviewing}>Load relational design
        <input hidden type="file" disabled={merging || reviewing} aria-label="Relational design file" onChange={async event => {
          const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
          const serial = ++fileToken.current;
          try {
            if (file.size > 8 * 1024 * 1024) throw new Error();
            const value = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer()));
            validateDDNSnapshot(value);
            if (serial !== fileToken.current) return;
            setEditing(false); setDraft(value); selected.current = {entry: value.entry, view: value.view}; setError(null);
          } catch {if (serial === fileToken.current) setError('Load a valid UTF-8 DDN workspace JSON file, maximum 8 MiB.');}
        }} />
      </Button>
      <Button onClick={() => download(JSON.stringify(editing ? draft : snapshot()), `${engine}-relations.ddn-workspace.json`, 'application/json')}>Download relational design</Button>
    </Box>
    <FirebirdDesignStorage post={post} databaseTargetId={databaseTargetId} kind="relations" engine={engine} disabled={editing || merging || reviewing}
      capture={() => ({snapshot: snapshot(), baseline: baseline.current})}
      onLoad={value => {setDraft(value.snapshot); baseline.current = value.baseline;
        selected.current = {entry: value.snapshot.entry, view: value.snapshot.view}; setError(null);}} />
    {post && onReview && <Button disabled={editing || merging || reviewing || (!generation && engine !== 'mysql')} onClick={async () => {
      const serial = ++fileToken.current; setReviewing(true); setError(null);
      const document = value => ({format: value.format, entry: value.entry, view: value.view, files: value.files});
      try {
        const result = await post({action: `${engine}_relational_review`, request: {...(engine === 'mysql' ? {database_target_id: databaseTargetId} : {generation}),
          original: document(baseline.current), snapshot: document(snapshot())}});
        if (serial !== fileToken.current) return;
        await onReview(result);
      } catch (failure) {if (serial === fileToken.current) setError(failure.response?.data?.errormsg || failure.message || 'Unable to prepare relational review.');}
      finally {if (serial === fileToken.current) setReviewing(false);}
    }}>Review relational metadata changes</Button>}
    {JSON.stringify(baseline.current) !== JSON.stringify(diagram.snapshot) &&
      <Alert severity="warning">The native relational capture has changed. Your design and its original baseline are retained.</Alert>}
    <Button disabled={editing || merging || reviewing || !post || !diagram.snapshot} onClick={async () => {
      const serial = ++fileToken.current; setMerging(true); setError(null);
      try {
        const value = await refreshDesign(post, baseline.current, snapshot(), diagram.snapshot);
        if (serial !== fileToken.current) return;
        setDraft(value); baseline.current = diagram.snapshot;
      } catch (failure) {if (serial === fileToken.current) setError(failure.message);}
      finally {if (serial === fileToken.current) setMerging(false);}
    }}>Merge latest native relations into design</Button>
    {error && <Alert severity="error">{error}</Alert>}
    {!editing && <DDNViewerSurface snapshot={draft} onSelectionChange={value => {selected.current = value;}} />}
    <Dialog fullScreen open={editing} onClose={closeEditor}>
      <Box sx={{display: 'flex', alignItems: 'center', gap: 2, p: 1}}>
        <FormReference formKey={`${engine}-relational-diagram`} />
        <Box sx={{flex: 1}}>Relational design — changes affect the diagram only.</Box>
        <Button onClick={() => download(JSON.stringify(captureEditor()), `${engine}-relations.ddn-workspace.json`, 'application/json')}>Download edited design</Button>
        <Button onClick={closeEditor}>Return to diagram viewer</Button>
      </Box>
      {error && <Alert severity="error">{error}</Alert>}
      <Box sx={{flex: 1, minHeight: 0}}>
        {editing && <DDNDesignerSurface snapshot={seed.current} onReady={value => {editor.current = value;}}
          onChange={value => {setDraft(value); selected.current = {entry: value.entry, view: value.view};}}
          onExport={svg => download(svg, `${engine}-relations.svg`, 'image/svg+xml')} />}
      </Box>
    </Dialog>
  </Box>;
}
FirebirdERD.propTypes = {engine: PropTypes.oneOf(['firebird', 'mysql']), diagram: PropTypes.object.isRequired, post: PropTypes.func, databaseTargetId: PropTypes.string,
  generation: PropTypes.string, onReview: PropTypes.func};
