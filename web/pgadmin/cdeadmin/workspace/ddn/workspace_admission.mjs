// Use only the adopted public source/model/runtime APIs. No source-controlled IO.
import {createVerifier, createNativeRuntimeOptions, createCompleteRuntimeOptions} from '../../../static/vendor/ddn/current/complete/ddn-verifier.js';
import {decodeSources, allNodes} from '../../../static/vendor/ddn/current/modules/language/src/index.js';
import {listRecords, normalizedFiles} from '../../../static/vendor/ddn/current/modules/model/src/index.js';

export const WORKSPACE_FORMAT = 'ddn-source-workspace@1';
export const CONTRACT = 'ddn-next-1';
export const sourceSet = snapshot => ({entry: snapshot.entry, files: Object.entries(snapshot.files).map(([id, text]) =>
  ({id, text, revision: '1', encoding: 'utf-8', writable: true}))});
export function mapping(record) {
  let facts=record?.metadata?.x_record;
  if(!facts) return undefined;
  if(facts.exact_text_json) {
    const exact=JSON.parse(facts.exact_text_json);
    if(!exact || Array.isArray(exact) || typeof exact!=='object' || Object.keys(exact).length>1024) throw failure('Invalid exact text mapping');
    facts=JSON.parse(JSON.stringify(facts));
    for(const [pathText,text] of Object.entries(exact)) {
      const path=JSON.parse(pathText);
      if(!Array.isArray(path) || !path.length || path.length>32 || typeof text!=='string' || !/[\r\n\0]/.test(text)) throw failure('Invalid exact text mapping');
      let owner=facts;
      for(const part of path.slice(0,-1)) {if(!owner || !Object.hasOwn(owner,part)) throw failure('Invalid exact text path');owner=owner[part];}
      const key=path.at(-1);
      if(!owner || !Object.hasOwn(owner,key) || owner[key]!==JSON.stringify(text).slice(1,-1)) throw failure('Exact text differs from its display value');
      Object.defineProperty(owner,key,{value:text,enumerable:true,writable:true,configurable:true});
    }
  }
  return facts;
}

function failure(message, diagnostics=[]) {
  const error = new Error(message);
  error.diagnostics = diagnostics.slice(0, 16).map(item => ({
    code: typeof item.code === 'string' && /^[A-Za-z0-9_.-]{1,128}$/.test(item.code) ? item.code : 'DDN_SOURCE',
    source: item.source?.file || item.target?.file,
    offset: Number.isSafeInteger(item.source?.start) ? item.source.start : 0,
  }));
  return error;
}
export async function admitWorkspace(snapshot, modulePrefix=null) {
  if(snapshot?.format !== WORKSPACE_FORMAT || !snapshot.files || Array.isArray(snapshot.files) ||
     !Object.hasOwn(snapshot.files, snapshot.entry) || !snapshot.view ||
     Object.keys(snapshot.files).length > 64) throw failure('Invalid source-workspace envelope');
  for(const [filename, text] of Object.entries(snapshot.files)) {
    if(typeof text !== 'string' || !text.trim() || text.length > 2000000 ||
       filename.startsWith('/') || /[\\:\0]/.test(filename) ||
       filename.split('/').some(part => !part || part === '.' || part === '..') || !filename.endsWith('.ddn')) {
      throw failure('Invalid source-workspace file');
    }
  }
  const input = sourceSet(snapshot), documents = new Map();
  let selected = false, viewCount = 0, definitionCount = 0;
  // Every supplied file is admitted, including documentary metadata outside
  // the selected include closure. Includes resolve only this supplied set.
  for(const filename of Object.keys(snapshot.files)) {
    if(documents.has(filename)) continue;
    const source = {...input, entry: filename};
    const decoded = decodeSources(source);
    if(!decoded.syntaxValid || decoded.diagnostics.some(d => d.severity === 'error')) {
      throw failure('Invalid DDN source', decoded.diagnostics);
    }
    const native = new Set(['ddn@1','mindmap.basic@1','concept.map@1','table.records@1']);
    const options = listRecords(decoded.normalized).every(row => row.kind !== 'view' || native.has(row.record.profile)) ?
      createNativeRuntimeOptions() : createCompleteRuntimeOptions();
    const verifier = createVerifier(options);
    try {
      const report = await verifier.verifySources(source,
        {scope: {kind: 'workarea'}, purpose: 'view', level: 'semantic'});
      if(report.outcome !== 'valid' || !report.coverage.complete) throw failure('Incomplete DDN model', report.diagnostics);
      for(const file of normalizedFiles(decoded.normalized)) {
        if(documents.has(file.location)) continue;
        const records = listRecords(decoded.normalized).filter(row => row.file === file.location);
        const nodes = new Map(allNodes(decoded).filter(node => node.ref?.file === file.location &&
          ['element', 'relation', 'view', 'data', 'source', 'publication'].includes(node.kind)).map(node => [node.ref.id, node]));
        for(const row of records) {
          if(row.kind === 'view') {
            if(++viewCount > 2048) throw failure('Workspace view limit exceeded');
            if(file.location === snapshot.entry && row.ref.id === snapshot.view) selected = true;
          }
          if(row.kind === 'definition' && ++definitionCount > 100000) throw failure('Workspace definition limit exceeded');
          const facts = mapping(row.record);
          if(modulePrefix && facts && (!facts.module ||
             facts.module !== modulePrefix && !facts.module.startsWith(modulePrefix + '.'))) throw failure('Foreign native mapping');
        }
        documents.set(file.location, {document: file.document, records, nodes});
      }
    } finally {verifier.destroy();}
  }
  if(!selected) throw failure('Missing selected workspace view');
  return documents;
}
