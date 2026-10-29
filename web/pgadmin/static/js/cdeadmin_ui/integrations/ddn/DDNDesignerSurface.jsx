// The public DDN designer owns its palette, inspector, layout and undo/redo UI.
import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button} from '@mui/material';
import {DDNSessionController} from './DDNSessionController';
import {DDNViewerSurface} from './DDNViewerSurface';
import FormReference from '../../navigation/FormReference';
const LABELS={clean:'Saved',dirty:'Unsaved changes',saving:'Saving','saved-newer-edits':'Saved; newer changes remain','save-failed':'Save failed','external-conflict':'External conflict'};
export function DDNDesignerSurface(props) {
  const {files,snapshot,assetRef,readOnly=false,saveAsset,executeCommand,onExport}=props;
  const host=useRef(null),controller=useRef(null),callbacks=useRef(props);callbacks.current=props;
  const [state,setState]=useState(null),[error,setError]=useState(null),[ready,setReady]=useState(false);
  useEffect(()=> {
    if(readOnly) return undefined;
    let active=true,current;
    setReady(false);setError(null);
    DDNSessionController.create({host:host.current,files,snapshot,assetRef}).then(value=> {
      current=value;
      if(!active) {current.destroy();return;}
      controller.current=current;
      current.subscribe((next,event)=> {
        if(!active) return;
        setState(next);callbacks.current.onStateChange?.(next);
        if(event?.type==='session') callbacks.current.onChange?.(current.getSnapshot(),event);
      });
      setState(current.state());setReady(true);callbacks.current.onReady?.(current);
    }).catch(failure=>{if(active) {setError(failure);callbacks.current.onError?.(failure);}});
    return ()=>{active=false;current?.destroy();if(controller.current===current) controller.current=null;};
  },[files,snapshot,assetRef,readOnly]);
  if(readOnly) return <DDNViewerSurface files={files} snapshot={snapshot} onExport={onExport} onError={props.onError} executeCommand={executeCommand}/>;
  const run=async(id,invoke)=> {
    try {await (executeCommand?executeCommand(id,{invoke,enabled:ready}):invoke());}
    catch(failure) {setError(failure);callbacks.current.onError?.(failure);}
  };
  return <Box data-cde-surface="diagram.ddn.designer" sx={{height:'100%',minHeight:0,display:'flex',flexDirection:'column'}}>
    <Box component="header" sx={{display:'flex',gap:1,p:0.5,alignItems:'center'}}>
      <FormReference formKey="ddn-designer"/>
      <Button disabled={!ready || !saveAsset || !assetRef || state?.persistence==='saving'} onClick={()=>run('ddn.designer.save',()=>controller.current.save(saveAsset))}>Save</Button>
      <Button disabled={!ready} onClick={()=>run('ddn.designer.export',async()=> {
        const captured=await controller.current.snapshot();
        const svg=await controller.current.exportSVG();
        onExport?.(svg,captured);
      })}>Export SVG</Button>
      <Box role="status" sx={{ml:'auto'}}>{ready?LABELS[state?.persistence]:'Opening DDN editor'}</Box>
    </Box>
    {error && <Alert severity="error">{error.message}</Alert>}
    <Box ref={host} aria-label="DDN Designer" sx={{flex:1,minHeight:400}}/>
  </Box>;
}
DDNDesignerSurface.propTypes={files:PropTypes.object,snapshot:PropTypes.object,assetRef:PropTypes.object,readOnly:PropTypes.bool,
  saveAsset:PropTypes.func,executeCommand:PropTypes.func,onChange:PropTypes.func,onExport:PropTypes.func,onReady:PropTypes.func,
  onError:PropTypes.func,onStateChange:PropTypes.func};
