import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Box} from '@mui/material';
import {Button} from '../../primitives/Button';
import {Select} from '../../primitives/Choice';
import {EmptyState} from '../../feedback/EmptyState';
import {ProgressOverlay} from '../../feedback/ProgressOverlay';
import {StatusBadge} from '../../status/StatusBadge';
import {loadDDNLibraries} from './library';
import {validateDDNFiles, validateDDNSnapshot} from './contracts';
import {sourceSet,checkOpen,entriesOf,selectView,captureSVG,ingestData} from './runtime';
import FormReference from '../../navigation/FormReference';

export function DDNViewerSurface(props) {
  const {files,snapshot,entry,view,presentation=false,viewSelection=false,liveData} = props;
  const callbacks=useRef(props); callbacks.current=props;
  const host=useRef(null), image=useRef(null), session=useRef(null), retained=useRef(null);
  const [entries,setEntries]=useState([]), [selection,setSelection]=useState({entry:'',view:''});
  const [loading,setLoading]=useState(true), [error,setError]=useState(null), [result,setResult]=useState(null);
  const sourceFiles=useMemo(()=>snapshot ? validateDDNSnapshot(snapshot).files : validateDDNFiles(files),[files,snapshot]);
  const sourceSignature=JSON.stringify(sourceFiles);
  const report=failure=>{setResult(null);image.current?.removeAttribute('src');setError(failure);setLoading(false);callbacks.current.onError?.(failure);};
  const draw=async(current,chosen)=> {
    try {
      await current.viewer.navigate({kind:'expand-view',target:{file:chosen.entry,id:chosen.view}});
      if(session.current!==current || current.selection!==chosen)return;
      await current.viewer.navigate({kind:'fit-view',target:{file:chosen.entry,id:chosen.view}});
      const captured=await captureSVG(current.viewer,chosen);
      if(session.current!==current || current.selection!==chosen)return;
      if(presentation && image.current) image.current.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(captured.svg);
      setResult(captured);setError(null);setLoading(false);callbacks.current.onReady?.(captured);
    } catch(failure) {
      if(session.current===current && current.selection===chosen)throw failure;
    }
  };
  useEffect(()=> {
    let active=true, current;
    setLoading(true);setError(null);setResult(null);
    if(image.current) image.current.removeAttribute('src');
    (async()=> {
      const libraries=await loadDDNLibraries();
      if(!active) return;
      const runtime=libraries.viewer.createRuntime(libraries.viewer.createBrowserRuntimeOptions());
      current={runtime,viewer:libraries.viewer.createViewer(host.current,{runtime,controls:'host'})};
      session.current=current;
      current.pending=(async()=> {
        const requested=snapshot ? validateDDNSnapshot(snapshot) : {entry,view};
        const opened=checkOpen(await current.viewer.open(sourceSet(sourceFiles,requested.entry || Object.keys(sourceFiles)[0])));
        if(!active) return;
        const available=entriesOf(libraries,opened.snapshot);
        const keep=retained.current;
        const chosen=selectView(available,...(viewSelection && keep && available.some(file=>file.file===keep.entry && file.views.some(item=>item.id===keep.view)) ?
          [keep.entry,keep.view] : [requested.entry,requested.view]));
        current.selection=chosen;retained.current=chosen;setEntries(available);setSelection(chosen);
        await ingestData(runtime,callbacks.current.liveData || snapshot?.liveData);
        if(!active) return;
        callbacks.current.onSelectionChange?.(chosen);
        await draw(current,chosen);
      })();
      await current.pending;
    })().catch(failure=>{if(active) report(failure);});
    return ()=>{active=false;if(session.current===current) session.current=null;current?.viewer.destroy();current?.runtime.destroy();};
  },[sourceSignature,entry,view,presentation,viewSelection]);
  useEffect(()=> {
    const current=session.current;
    if(!current?.selection || !current.runtime.snapshot()) return;
    let active=true;
    // Serialize updates so the next batch observes the preceding revision.
    current.pending=(current.pending || Promise.resolve()).then(async()=> {
      if(session.current!==current || !active) return;
      await ingestData(current.runtime,liveData || snapshot?.liveData);
      if(active) await draw(current,current.selection);
    }).catch(failure=>{if(active) report(failure);});
    return ()=>{active=false;};
  },[liveData,snapshot?.liveData]);
  const chooseView=async value=> {
    const [nextEntry,nextView]=value.split('\0');
    const chosen=selectView(entries,nextEntry,nextView), current=session.current;
    if(!current) return;
    current.selection=chosen;retained.current=chosen;setSelection(chosen);setLoading(true);setError(null);
    callbacks.current.onSelectionChange?.(chosen);
    current.pending=(current.pending || Promise.resolve()).then(()=>draw(current,current.selection)).catch(report);
    await current.pending;
  };
  const run=async(id,invoke)=> {
    try {await (callbacks.current.executeCommand ? callbacks.current.executeCommand(id,{invoke,enabled:Boolean(result)}) : invoke());}
    catch(failure) {report(failure);}
  };
  const options=entries.flatMap(file=>file.views.map(item=>({value:`${file.file}\0${item.id}`,label:`${file.file} / ${item.name || item.id}`})));
  return <Box data-cde-surface="diagram.ddn.viewer" sx={{display:'flex',flexDirection:'column',height:presentation?'auto':'100%',minHeight:0}}>
    <FormReference formKey="ddn-viewer" />
    {((presentation && viewSelection && options.length>1) || !presentation) && <Box component="header" sx={{display:'flex',gap:1,alignItems:'center',p:0.5}}>
      <Select label={presentation?'Dashboard view':'DDN view'} size="small" value={selection.entry?`${selection.entry}\0${selection.view}`:''} options={options} onChange={chooseView}/>
      {!presentation && <>
        <Button disabled={!result} onClick={()=>run('ddn.viewer.fit',()=>session.current.viewer.navigate({kind:'fit-workarea'}))}>Fit</Button>
        <Button disabled={!result} onClick={()=>run('ddn.viewer.export',async()=>callbacks.current.onExport?.((await captureSVG(session.current.viewer,selection)).svg,selection))}>Export SVG</Button>
        <StatusBadge live status={error?'error':result?.diagnostics?.length?'warning':'success'} label={error?'Render failed':`${result?.diagnostics?.length || 0} diagnostics`}/>
      </>}
    </Box>}
    <Box sx={{position:'relative',flex:1,minHeight:presentation?120:0,overflow:'auto'}}>
      {error && <EmptyState role="alert" message={error.message}/>}
      <Box ref={host} aria-label="DDN diagram" sx={{height:presentation?600:'100%',minHeight:300,visibility:error?'hidden':'visible',
        ...(presentation?{position:'absolute',width:'100%',visibility:'hidden',pointerEvents:'none'}:{})}}/>
      {presentation && <img ref={image} alt="DDN diagram" style={{maxWidth:'100%',display:error?'none':'block'}}/>}
      <ProgressOverlay message={loading?'Rendering DDN view':''}/>
    </Box>
  </Box>;
}
DDNViewerSurface.propTypes={files:PropTypes.object,snapshot:PropTypes.object,entry:PropTypes.string,view:PropTypes.string,
  presentation:PropTypes.bool,viewSelection:PropTypes.bool,liveData:PropTypes.array,executeCommand:PropTypes.func,
  onExport:PropTypes.func,onReady:PropTypes.func,onError:PropTypes.func,onSelectionChange:PropTypes.func};
