// Host source envelopes are distinct from DDN's native ModelSnapshot contract.
import {validateDDNFiles, validateDDNSnapshot} from './contracts.js';
let sourceGeneration = 0;
export function sourceSet(files, entry, writable=false) {
  const revision = `cde-source-${++sourceGeneration}`;
  return {entry, files: Object.entries(validateDDNFiles(files)).map(([id,text]) =>
    ({id,text,revision,encoding:'utf-8',writable}))};
}
export function checkOpen(result) {
  if(!result.snapshot || result.diagnostics.some(item => item.severity === 'error')) {
    throw new Error(result.diagnostics.map(item => item.message).join('\n') || 'DDN did not admit this source.');
  }
  return result;
}
export function entriesOf(libraries, snapshot) {
  const entries = new Map();
  for(const item of libraries.model.listRecords(snapshot.normalized)) {
    if(item.kind !== 'view') continue;
    if(!entries.has(item.file)) entries.set(item.file, {file:item.file,views:[]});
    entries.get(item.file).views.push({id:item.ref.id,name:item.record.title || item.record.name});
  }
  return [...entries.values()];
}
export function selectView(entries, entry, view) {
  const file = entry ? entries.find(item => item.file === entry) : entries[0];
  const chosen = view ? file?.views.find(item => item.id === view) : file?.views[0];
  if(!file || !chosen) throw new Error('The selected DDN view does not exist.');
  return {entry:file.file,view:chosen.id};
}
export function envelope(runtime, selection) {
  const source = runtime.sources();
  if(!source) throw new Error('The DDN source is unavailable.');
  return validateDDNSnapshot({format:'ddn-source-workspace@1',...selection,
    files:Object.fromEntries(source.files.map(file => [file.id,file.text]))});
}
export async function captureSVG(viewer, selection) {
  const capture = await viewer.capture({scope:{kind:'view',target:{file:selection.entry,id:selection.view}},
    format:'svg',extent:'content',includePreview:false,partial:'label',stale:'label'});
  if(!capture.ok) throw new Error(capture.diagnostics.map(item => item.message).join('\n') || `DDN capture failed: ${capture.reason}`);
  const artifact = capture.artifacts.find(item => item.mime === 'image/svg+xml');
  if(!artifact) throw new Error('DDN did not return an SVG artifact.');
  return {svg:await artifact.blob.text(),manifest:capture.manifest,diagnostics:capture.manifest.warnings};
}
export async function ingestData(runtime, data) {
  if(!data?.length) return;
  checkOpen(await runtime.ingest({base:runtime.snapshot().revision,origin:'scratchrobin.collector',
    data:data.map(item => ({...item,next:`cde-data-${++sourceGeneration}`}))}));
}
