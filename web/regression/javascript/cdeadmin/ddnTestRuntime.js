// Test adapters call the adopted public APIs; no legacy parser or renderer.
import {configure} from '@testing-library/react';
import * as api from '../../../pgadmin/static/vendor/ddn/current/complete/ddn-viewer.js';
import {createVerifier} from '../../../pgadmin/static/vendor/ddn/current/complete/ddn-verifier.js';
import * as designer from '../../../pgadmin/static/vendor/ddn/current/complete/ddn-visual-designer.js';
import * as language from '../../../pgadmin/static/vendor/ddn/current/modules/language/src/index.js';
import * as model from '../../../pgadmin/static/vendor/ddn/current/modules/model/src/index.js';
import {sourceSet,captureSVG,entriesOf,checkOpen} from 'sources/cdeadmin_ui/integrations/ddn/runtime';
export const libraries={viewer:{...api,createVerifier,createBrowserRuntimeOptions:api.createCompleteRuntimeOptions},language,model,
  loader:{loadEntry:async()=>designer}};
export function setupDDNDOM() {
  configure({asyncUtilTimeout:5000});
  window.innerHeight=1200;
  if(!SVGElement.prototype.getScreenCTM) SVGElement.prototype.getScreenCTM=function() {return {a:1,b:0,c:0,d:1,e:0,f:0,inverse(){return this;}};};
  jest.spyOn(HTMLCanvasElement.prototype,'getContext').mockImplementation(()=>({measureText:text=>({width:String(text).length*8})}));
  if(!Blob.prototype.arrayBuffer) Blob.prototype.arrayBuffer=function() {return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsArrayBuffer(this);});};
  if(!Blob.prototype.text) Blob.prototype.text=function() {return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsText(this);});};
}
export function metricRows(snapshot) {
  if(snapshot.liveData) return snapshot.liveData[0].rows;
  const parsed=language.decodeSources(sourceSet(snapshot.files || snapshot,snapshot.entry || 'dashboard.ddn'));
  if(!parsed.syntaxValid) throw Error(JSON.stringify(parsed.diagnostics));
  return model.listRecords(parsed.normalized).find(item=>item.kind==='data' && item.ref.id==='observations')?.record.rows || [];
}
export async function createTestWorkspace(files) {
  const host=document.createElement('div');document.body.appendChild(host);
  const runtime=api.createRuntime(api.createCompleteRuntimeOptions()), viewer=api.createViewer(host,{runtime,controls:'host'});
  try {checkOpen(await viewer.open(sourceSet(files,Object.keys(files)[0])));} catch(error) {viewer.destroy();runtime.destroy();host.remove();throw error;}
  return {
    entries:()=>entriesOf(libraries,runtime.snapshot()),
    validate:async()=>runtime.verifier.verifyModel(runtime.snapshot(),{scope:{kind:'workarea'},purpose:'view',level:'semantic'}),
    render:async({entry,view})=> {
      await viewer.navigate({kind:'expand-view',target:{file:entry,id:view}});
      return captureSVG(viewer,{entry,view});
    },
    destroy:()=>{viewer.destroy();runtime.destroy();host.remove();},
  };
}
export default {createWorkspace:createTestWorkspace};
