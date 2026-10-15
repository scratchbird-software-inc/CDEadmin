// Resolve source imports exclusively in the admitted in-memory file set.
import path from 'node:path';
import runtime from '../../../static/vendor/ddn/current/ddn.mjs';

export function admitWorkspace(snapshot, modulePrefix=null) {
  const parsed = new Map(), visiting = new Set(), visited = new Set();
  for(const [filename, source] of Object.entries(snapshot.files)) {
    if(filename.startsWith('/') || filename.includes('\\') || filename.includes(':') || filename.includes('\0') ||
       filename.split('/').some(part => !part || part === '.' || part === '..') || !filename.endsWith('.ddn')) throw new Error('Invalid workspace path');
    let document;
    try {document = runtime.parse(source, filename);}
    catch(error) {
      const failure = new Error('Invalid workspace source');
      failure.diagnostics = [{code:'DDN_PARSE', source:filename,
        offset:Number.isSafeInteger(error.offset) ? error.offset : 0}];
      throw failure;
    }
    if(modulePrefix && document.module !== modulePrefix && !document.module?.startsWith(modulePrefix + '.')) throw new Error('Foreign native mapping module');
    parsed.set(filename, document);
  }
  const visit = filename => {
    if(visiting.has(filename)) throw new Error('Cyclic workspace imports');
    if(visited.has(filename)) return;
    const document = parsed.get(filename);
    if(!document) throw new Error('Missing workspace import');
    visiting.add(filename);
    for(const item of document.imports) {
      if(typeof item.path !== 'string' || !item.path || /^[\/\\]|:|\\|\0/.test(item.path)) throw new Error('External workspace import');
      const target = path.posix.normalize(path.posix.join(path.posix.dirname(filename), item.path));
      if(target.startsWith('../')) throw new Error('Workspace import escapes its root');
      visit(target);
    }
    visiting.delete(filename); visited.add(filename);
  };
  for(const filename of parsed.keys()) visit(filename);
  // Legacy empty catalogs contain a documentary placeholder without native
  // fields. Supply empty presentation cells only for validation, keeping the
  // original parser locations and native record count unchanged.
  const validationFiles = Object.fromEntries(Object.entries(snapshot.files).map(([name, source]) => [name,
    source.replace('record empty "No objects in the selected visible scope" {}',
      'record empty "No objects in the selected visible scope" {x_record:{kind:"";path_json:"[]";system:"unknown";};}')
  ]));
  const workspace = runtime.createWorkspace(validationFiles);
  try {
    let views = 0, selected = false;
    for(const entry of workspace.entries()) for(const view of entry.views) {
      if(++views > 2048) throw new Error('Workspace view limit exceeded');
      if(entry.file === snapshot.entry && view.id === snapshot.view) selected = true;
      const result = workspace.validateDraft(entry.file, view.id);
      if(result.status !== 'valid' || result.diagnostics.some(item => ['error', 'incomplete'].includes(item.severity))) {
        const failure = new Error('Invalid workspace view');
        failure.diagnostics = result.diagnostics.filter(item => ['error','incomplete'].includes(item.severity)).slice(0, 16).map(item => ({
          code:typeof item.code === 'string' && /^[A-Za-z0-9_.-]{1,128}$/.test(item.code) ? item.code : 'DDN_VIEW',
          source:Object.hasOwn(snapshot.files, item.source) ? item.source : entry.file,
          offset:Number.isSafeInteger(item.offset) && item.offset >= 0 ? item.offset : 0,
        }));
        throw failure;
      }
    }
    if(!selected) throw new Error('Missing selected workspace view');
  } finally {workspace.destroy();}
  return parsed;
}
