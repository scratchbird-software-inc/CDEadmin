// Host the current DDN unified tool through its documented source bridge.
import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button} from '@mui/material';
import {DDNSessionController} from './DDNSessionController';
import {DDNViewerSurface} from './DDNViewerSurface';
import {staticAssetUrl, DDN_RUNTIME_VERSION} from './library';
import {validateDDNFiles, validateDDNSnapshot} from './contracts';
import FormReference from '../../navigation/FormReference';

const LABELS = {clean: 'Saved', dirty: 'Unsaved changes', saving: 'Saving',
  'saved-newer-edits': 'Saved; newer changes remain', 'save-failed': 'Save failed',
  'external-conflict': 'External conflict'};

export function DDNDesignerSurface(props) {
  const {files, snapshot, assetRef, readOnly=false, saveAsset, executeCommand, onExport} = props;
  const frame = useRef(null);
  const controller = useRef(null);
  const callbacks = useRef(props);
  callbacks.current = props;
  const generation = useRef(0);
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [ready, setReady] = useState(false);
  const report = (failure) => { setError(failure); callbacks.current.onError?.(failure); };
  const start = async () => {
    const token = ++generation.current;
    setReady(false);
    setError(null);
    controller.current?.destroy();
    controller.current = null;
    try {
      const tool = frame.current?.contentWindow?.DDNTool;
      if(!tool?.setSource || !tool?.getSource || !tool?.onSourceChange) {
        throw new Error('The bundled DDN tool did not expose its source bridge.');
      }
      if(frame.current.contentWindow.DDNLive?.VERSION !== DDN_RUNTIME_VERSION) {
        throw new Error('The DDN tool/runtime versions do not match.');
      }
      const source = snapshot ? validateDDNSnapshot(snapshot) : {files: validateDDNFiles(files)};
      await tool.setSource(source.files, {entry: source.entry, view: source.view});
      for(const [name, value] of Object.entries(source.overrides || {})) tool.setOption(name, value);
      const currentSource = tool.getSource();
      for(const [id, point] of Object.entries(source.layoutState?.positions || {})) {
        frame.current.contentWindow.DDNLive.authoring.pin(tool.workspace,
          currentSource.entry, currentSource.view, id, point[0], point[1]);
      }
      if(token !== generation.current) return;
      const current = await DDNSessionController.create({tool, snapshot, files, assetRef});
      if(token !== generation.current) { current.destroy(); return; }
      controller.current = current;
      const publish = (next, event) => {
        setState(next);
        callbacks.current.onStateChange?.(next);
        if(event?.type === 'session') callbacks.current.onChange?.(current.snapshot(), event);
      };
      current.subscribe(publish);
      publish(current.state());
      setReady(true);
      // The unified tool owns its catalogue, insertion, history and layout UI.
      callbacks.current.onReady?.(current, {
        items: frame.current.contentWindow.DDNLive.kinds.map((kind) => ({
          id: kind.id, label: kind.label, group: kind.group, payload: {kind: kind.id},
        })),
        insert: (payload) => tool.startPlacement(payload.kind),
      });
    } catch(failure) { if(token === generation.current) report(failure); }
  };
  const restart = useRef(start);
  restart.current = start;
  useEffect(() => {
    if(frame.current?.contentWindow?.DDNTool) restart.current();
    return () => {
      generation.current++;
      controller.current?.destroy();
      controller.current = null;
    };
  }, [files, snapshot, assetRef, readOnly]);

  if(readOnly) return <DDNViewerSurface files={files} snapshot={snapshot}
    onExport={onExport} onError={props.onError} executeCommand={executeCommand} />;
  const run = async (id, invoke) => {
    try { await (executeCommand ? executeCommand(id, {invoke, enabled: ready}) : invoke()); }
    catch(failure) { report(failure); }
  };
  return <Box data-cde-surface="diagram.ddn.designer"
    sx={{height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column'}}>
    <Box component="header" sx={{display: 'flex', gap: 1, p: 0.5, alignItems: 'center'}}>
      <FormReference formKey="ddn-designer" />
      <Button disabled={!ready || !saveAsset || !assetRef || state?.persistence === 'saving'}
        onClick={() => run('ddn.designer.save', () => controller.current.save(saveAsset))}>Save</Button>
      <Button disabled={!ready} onClick={() => run('ddn.designer.export', () =>
        onExport?.(controller.current.exportSVG(), controller.current.snapshot()))}>Export SVG</Button>
      <Box role="status" sx={{ml: 'auto'}}>{ready ? LABELS[state?.persistence] : 'Opening DDN editor'}</Box>
    </Box>
    {error && <Alert severity="error">{error.message}</Alert>}
    <Box component="iframe" ref={frame} title="DDN Designer" onLoad={start}
      src={staticAssetUrl('ddn-tool.html?mode=design')}
      sx={{border: 0, width: '100%', flex: 1, minHeight: 400}} />
  </Box>;
}
DDNDesignerSurface.propTypes = {files: PropTypes.object, snapshot: PropTypes.object,
  assetRef: PropTypes.object, readOnly: PropTypes.bool, saveAsset: PropTypes.func,
  executeCommand: PropTypes.func, onChange: PropTypes.func, onExport: PropTypes.func,
  onReady: PropTypes.func, onError: PropTypes.func, onStateChange: PropTypes.func};
