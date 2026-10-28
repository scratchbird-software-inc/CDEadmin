// Qualification host for the public DDN viewer/capture API. The SDK owns SVG
// realization. This DOM test host uses the SDK's fallback text measurements;
// Chromium qualification separately proves real font/worker/browser behavior.
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import * as api from '../web/pgadmin/static/vendor/ddn/current/complete/ddn-viewer.js';
import {listRecords} from '../web/pgadmin/static/vendor/ddn/current/modules/model/src/index.js';
import {admitWorkspace,sourceSet,mapping} from '../web/pgadmin/cdeadmin/workspace/ddn/workspace_admission.mjs';
const require=createRequire(new URL('../web/package.json',import.meta.url));
const {JSDOM}=require('jsdom');
export async function renderWorkspace(snapshot) {
  const documents=await admitWorkspace(snapshot);
  const dom=new JSDOM('<!doctype html><div id="host" style="width:1200px;height:850px"></div>',{pretendToBeVisual:true});
  dom.window.HTMLCanvasElement.prototype.getContext=()=>null;
  const globals=new Map(['window','document','Event','CustomEvent','Element','HTMLElement','SVGElement','Node','MutationObserver','DOMParser','XMLSerializer','getComputedStyle'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
  for(const key of globals.keys()) Object.defineProperty(globalThis,key,{configurable:true,writable:true,value:dom.window[key]});
  const runtime=api.createRuntime(api.createCompleteRuntimeOptions());
  let viewer;
  try {
    viewer=api.createViewer(dom.window.document.getElementById('host'),{runtime,controls:'host'});
    const opened=await viewer.open(sourceSet(snapshot));
    if(!opened.snapshot || opened.diagnostics.some(item=>item.severity==='error')) throw Error('DDN source admission failed');
    const views=[];
    for(const row of listRecords(runtime.snapshot().normalized).filter(item=>item.kind==='view')) {
      await viewer.navigate({kind:'expand-view',target:row.ref});
      const capture=await viewer.capture({scope:{kind:'view',target:row.ref},format:'svg',extent:'content',includePreview:false,partial:'reject',stale:'reject'});
      if(!capture.ok || capture.manifest.warnings.some(item=>item.severity==='error')) throw Error('DDN capture failed: '+JSON.stringify(capture));
      views.push({entry:row.file,id:row.ref.id,svg:await capture.artifacts[0].blob.text()});
    }
    const records=[...documents.values()].flatMap(doc=>doc.records.map(row=>({file:row.file,id:row.ref.id,kind:row.kind,facts:mapping(row.record)})));
    return {contract:'ddn-next-1',views,records,measurement:'SDK fallback; browser evidence is separate'};
  } finally {viewer?.destroy();runtime.destroy();dom.window.close();for(const [key,descriptor] of globals) {if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}}
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
  let input='';for await(const chunk of process.stdin) {input+=chunk;if(Buffer.byteLength(input)>16*1024*1024) throw Error('DDN input exceeds its bound');}
  const body=JSON.parse(input);process.stdout.write(JSON.stringify(await renderWorkspace(body.snapshot || body)));
}
