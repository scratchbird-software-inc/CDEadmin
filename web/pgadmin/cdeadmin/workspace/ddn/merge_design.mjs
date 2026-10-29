import {admitWorkspace, mapping} from './workspace_admission.mjs';

// Three-way source refresh using public DDN UTF-16 source locations. Authored
// view/appearance text is retained; a native removal is never deletion intent.
export async function mergeDesign(_api, baseline, draft, incoming) {
  const admitted = await Promise.all([baseline, draft, incoming].map(snapshot => admitWorkspace(snapshot)));
  const files = {...draft.files}, conflicts = [];
  const nativeNodes = doc => {
    const ids = new Set();
    for(const row of doc?.records || []) {
      const facts = mapping(row.record);
      if(facts) {ids.add(row.ref.id);if(facts.record?.subject_id) ids.add(facts.record.subject_id);}
      if(['data','source'].includes(row.kind)) ids.add(row.ref.id);
    }
    return new Map([...ids].flatMap(id => doc.nodes.has(id) ? [[id, doc.nodes.get(id)]] : []));
  };
  const modules = doc => [...new Set((doc?.records || []).map(row => mapping(row.record)?.module).filter(Boolean))].sort().join();
  const raw = (snapshot, filename, node) => node ? snapshot.files[filename].slice(node.start,node.end) : null;
  for(const filename of new Set([...Object.keys(baseline.files),...Object.keys(incoming.files)])) {
    const [old, local, next] = admitted.map(docs => docs.get(filename));
    if(!old) {
      if(!local) files[filename] = incoming.files[filename];
      else if(files[filename] !== incoming.files[filename]) conflicts.push(filename + ': added on both sides');
      continue;
    }
    if(!next || !local || modules(old) !== modules(next) || modules(old) !== modules(local)) {
      conflicts.push(filename + ': file removed or native mapping changed');continue;
    }
    const before=nativeNodes(old), after=nativeNodes(next), authored=nativeNodes(local), edits=[];
    for(const id of new Set([...before.keys(),...after.keys()])) {
      const original=raw(baseline,filename,before.get(id)), refreshed=raw(incoming,filename,after.get(id));
      const retained=raw(draft,filename,authored.get(id));
      if(original === refreshed || retained === refreshed) continue;
      if(retained !== original) {conflicts.push(filename + ': ' + id + ' changed on both sides');continue;}
      if(refreshed === null) {conflicts.push(filename + ': ' + id + ' removed from native capture');continue;}
      const node=authored.get(id);
      edits.push(node ? {start:node.start,end:node.end,text:refreshed} :
        {start:files[filename].length,end:files[filename].length,text:'\n'+refreshed});
    }
    for(const row of next.records.filter(row => row.kind === 'view')) {
      if(!local.nodes.has(row.ref.id)) {
        const node=next.nodes.get(row.ref.id);
        edits.push({start:files[filename].length,end:files[filename].length,text:'\n'+raw(incoming,filename,node)});
      }
    }
    for(const edit of edits.sort((a,b)=>b.start-a.start)) files[filename]=files[filename].slice(0,edit.start)+edit.text+files[filename].slice(edit.end);
  }
  if(conflicts.length) throw new Error('Design refresh conflicts: '+conflicts.join('; '));
  const candidate={...draft,files};
  await admitWorkspace(candidate);
  return candidate;
}
