/* Real Chromium qualification of the standalone public DDN APIs.
 * Refresh first. State and evidence live exclusively in TMPDIR. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),http=require('node:http'),cp=require('node:child_process');
const root=path.resolve(__dirname,'../..'),vendor=path.join(root,'web/pgadmin/static/vendor/ddn/current');
const cache=process.env.PLAYWRIGHT_BROWSERS_PATH || path.join(os.homedir(),'.cache/ms-playwright');
const shells=fs.existsSync(cache)?fs.readdirSync(cache).filter(name=>name.startsWith('chromium_headless_shell-')).sort():[];
const browser=process.env.DDN_BROWSER || path.join(cache,shells.at(-1)||'','chrome-headless-shell-linux64/chrome-headless-shell');
if(!fs.existsSync(browser) || !process.env.TMPDIR) throw Error('Set DDN_BROWSER and TMPDIR to the qualified browser and artifact directory.');
const profile=fs.mkdtempSync(path.join(process.env.TMPDIR,'ddn-browser-')),errors=fs.openSync(path.join(process.env.TMPDIR,'ddn-browser.log'),'w');
const fixtures=process.env.DDN_BROWSER_FIXTURES?JSON.parse(fs.readFileSync(process.env.DDN_BROWSER_FIXTURES,'utf8')):[];
const source='version ddn-next-1\nerd main\n    with\n        id main\n    Alpha\n';
let child,timer;const hangs=[];
const scriptJSON=value=>JSON.stringify(value).replaceAll('<','\\u003c');
const page=`<!doctype html><meta charset="utf-8"><div id="host" style="width:1200px;height:850px"></div><img src="/hang" hidden>
<script src="/vendor/modular/ddn-fonts.js"></script><script src="/vendor/modular/ddn-loader.js"></script>
<script type="module">
import {listRecords} from '/vendor/modules/model/src/index.js';
const check=(value,message)=>{if(!value)throw Error(message);};
try {
 const loader=globalThis.DDN_LOADER;await loader.prepareEntry('worker');const api=await loader.loadEntry('api:viewer');
 const runtime=api.createRuntime(api.createBrowserRuntimeOptions()),viewer=api.createViewer(document.getElementById('host'),{runtime,controls:'host'});
 const sources=(files,entry='model.ddn')=>({entry,files:Object.entries(files).map(([id,text])=>({id,text,revision:'one',encoding:'utf-8',writable:true}))});
 const input=sources({'model.ddn':${scriptJSON(source)}});
 const opened=await viewer.open(input);check(opened.snapshot && !opened.diagnostics.some(item=>item.severity==='error'),'native open');
 const capture=async selection=>{await viewer.navigate({kind:'expand-view',target:{file:selection.entry,id:selection.view}});const result=await viewer.capture({scope:{kind:'view',target:{file:selection.entry,id:selection.view}},format:'svg',extent:'content',includePreview:false,partial:'label',stale:'label'});check(result.ok,'capture failed: '+JSON.stringify(result));const text=await result.artifacts[0].blob.text();check(!new DOMParser().parseFromString(text,'image/svg+xml').querySelector('parsererror'),'invalid SVG XML');return {text,manifest:result.manifest};};
 check((await capture({entry:'model.ddn',view:'main'})).text.includes('Alpha'),'native SVG label');
 const checked=[];
 for(const fixture of ${scriptJSON(fixtures)}) {
   const opened=await viewer.open(sources(fixture.files,fixture.entry));check(opened.snapshot && !opened.diagnostics.some(item=>item.severity==='error'),'fixture open: '+fixture.name);
   if(fixture.view_count!==undefined)check(listRecords(opened.snapshot.normalized).filter(row=>row.kind==='view').length===fixture.view_count,'unreachable views: '+fixture.name);
   if(fixture.liveData) {const before=JSON.stringify(runtime.sources());const result=await runtime.ingest({base:runtime.snapshot().revision,origin:'scratchrobin.collector',data:fixture.liveData.map((item,index)=>({...item,next:'live-'+index}))});check(result.snapshot && !result.diagnostics.some(item=>item.severity==='error'),'provider ingestion');check(JSON.stringify(runtime.sources())===before,'collector changed authored source');}
   const result=await capture(fixture),labels=new DOMParser().parseFromString(result.text,'image/svg+xml').documentElement.textContent;for(const text of fixture.expected || [])check(result.text.includes(text) || labels.includes(text),'missing fixture label: '+fixture.name+'/'+text);
   check(!result.manifest.warnings.some(item=>item.severity==='error'),'fixture drawing error: '+fixture.name);
   checked.push(fixture.name);
 }
 // Read-only work above has not loaded the editor entry.
 check(![...document.scripts].some(item=>item.src.includes('designer.html')),'unexpected editor shell');
 const designerApi=await loader.loadEntry('api:designer');await viewer.open(input);await viewer.navigate({kind:'expand-view',target:{file:'model.ddn',id:'main'}});
 const designer=designerApi.createDesigner(viewer,{authority:{authorize:async action=>({allowed:action==='model.edit',principal:'test',grants:['model.edit']})}});
 const file=runtime.sources().files[0];const prepared=await designer.commands.prepare({kind:'edit-source',patches:[{file:file.id,base:file.revision,start:0,end:file.text.length,text:file.text.replace('Alpha','Beta')}]});
 check(prepared.ok,'command prepare');check(runtime.sources().files[0].text.includes('Alpha'),'prepare mutated source');
 check((await designer.commands.commit(prepared.command.id)).ok,'command commit');
 const artifacts=await designer.save();const saved=Object.fromEntries(await Promise.all(artifacts.map(async item=>[item.name,await item.blob.text()])));check(saved['model.ddn'].includes('Beta'),'save lost edits');
 check((await designer.commands.undo()).ok,'undo');check(runtime.sources().files[0].text.includes('Alpha'),'undo source');
 check((await designer.commands.redo()).ok,'redo');check(runtime.sources().files[0].text.includes('Beta'),'redo source');
 designer.destroy();viewer.destroy();runtime.destroy();
 await fetch('/result',{method:'POST',body:JSON.stringify({pass:true,contract:'ddn-next-1',fixtures:checked,sourceSave:true,undoRedo:true,svgXML:true})});
} catch(error) {await fetch('/result',{method:'POST',body:JSON.stringify({pass:false,error:error.message,stack:error.stack})});}
</script>`;
const server=http.createServer((req,res)=> {
 const pathname=new URL(req.url,'http://localhost').pathname;
 if(pathname==='/hang'){hangs.push(res);return;}
 if(pathname==='/result' && req.method==='POST'){let body='';req.on('data',part=>{body+=part;});req.on('end',()=>{res.end('ok');try{const result=JSON.parse(body);fs.writeFileSync(path.join(process.env.TMPDIR,'ddn-browser-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));if(!result.pass)process.exitCode=1;}catch(error){console.error(error.message);process.exitCode=1;}finish();});return;}
 if(pathname==='/'){res.setHeader('content-type','text/html; charset=utf-8');res.end(page);return;}
 if(pathname.startsWith('/vendor/')){const file=path.resolve(vendor,pathname.slice(8));if(file.startsWith(vendor+path.sep)&&fs.existsSync(file)&&fs.statSync(file).isFile()){res.setHeader('content-type',file.endsWith('.js')?'text/javascript; charset=utf-8':file.endsWith('.json')?'application/json':'application/octet-stream');fs.createReadStream(file).pipe(res);return;}}
 res.writeHead(404);res.end();
});
function finish(){
 clearTimeout(timer);for(const res of hangs)res.end();server.close();
 if(child?.stdio[3]?.writable) child.stdio[3].write(JSON.stringify({id:1,method:'Browser.close'})+'\0');
 if(child) {const watchdog=setTimeout(()=>{try {if(process.platform==='win32')child.kill();else process.kill(-child.pid,'SIGTERM');}catch{}},5000);child.once('exit',()=>clearTimeout(watchdog));}
}
server.listen(0,'127.0.0.1',()=> {
 child=cp.spawn(browser,['--headless','--no-sandbox','--disable-gpu','--no-first-run','--remote-debugging-pipe','--user-data-dir='+profile,'http://127.0.0.1:'+server.address().port],{stdio:['ignore','ignore',errors,'pipe','pipe'],detached:process.platform!=='win32',env:{...process.env,TMPDIR:process.platform==='win32'?(process.env.TMPDIR || process.env.TEMP):'/tmp'}});
 child.on('exit',()=>{fs.closeSync(errors);fs.rmSync(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200});});
 child.on('error',error=>{console.error(error.message);process.exitCode=1;finish();});
 timer=setTimeout(()=>{console.error('DDN public API browser test timed out');process.exitCode=1;finish();},60000);
});
