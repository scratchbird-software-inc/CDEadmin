// Source ranges come from the public DDN parser. Preserve authored source
// outside changed native blocks byte for byte, including view appearance.
export function mergeDesign(runtime, baseline, draft, incoming) {
  const files = {...draft.files}, conflicts = [];
  const parse = (snapshot, name) => {
    if (!(name in snapshot.files)) return null;
    const parsed = runtime.parse(snapshot.files[name], name);
    if (parsed.imports.length) throw new Error('Imported design workspaces require manual reconciliation.');
    return parsed;
  };
  // Validate authored-only files too; imports cannot bypass this boundary by
  // appearing outside the incoming/native file set.
  for (const snapshot of [baseline, draft, incoming]) {
    for (const name of Object.keys(snapshot.files)) parse(snapshot, name);
  }
  const raw = (snapshot, name, node) => node ? snapshot.files[name].slice(node.start, node.end) : null;
  for (const name of new Set([...Object.keys(baseline.files), ...Object.keys(incoming.files)])) {
    const old = parse(baseline, name), next = parse(incoming, name), local = parse(draft, name);
    if (!old) {
      if (!local) files[name] = incoming.files[name];
      else if (files[name] !== incoming.files[name]) conflicts.push(name + ': added on both sides');
      continue;
    }
    if (!next || !local || old.module !== next.module || old.module !== local.module) {
      conflicts.push(name + ': file removed or module changed'); continue;
    }
    const blocks = parsed => new Map(parsed.declarations.filter(node => node.type === 'data').map(node => [node.id, node]));
    const before = blocks(old), after = blocks(next), authored = blocks(local), edits = [];
    for (const id of new Set([...before.keys(), ...after.keys()])) {
      const original = raw(baseline, name, before.get(id)), refreshed = raw(incoming, name, after.get(id));
      const retained = raw(draft, name, authored.get(id));
      if (original === refreshed || retained === refreshed) continue;
      if (retained !== original) {conflicts.push(name + ': ' + id + ' changed on both sides'); continue;}
      if (refreshed === null) {conflicts.push(name + ': ' + id + ' removed from native capture'); continue;}
      const node = authored.get(id);
      if (node) edits.push({start: node.start, end: node.end, text: refreshed});
      else edits.push({start: files[name].length, end: files[name].length, text: '\n' + refreshed});
    }
    const existing = new Set(local.declarations.map(node => node.id));
    for (const node of next.declarations.filter(item => item.type === 'view')) {
      if (!existing.has(node.id)) edits.push({start: files[name].length, end: files[name].length,
        text: '\n' + raw(incoming, name, node)});
    }
    for (const edit of edits.sort((a, b) => b.start - a.start)) files[name] = files[name].slice(0, edit.start) + edit.text + files[name].slice(edit.end);
  }
  if (conflicts.length) throw new Error('Design refresh conflicts: ' + conflicts.join('; '));
  const candidate = {...draft, files};
  const workspace = runtime.createWorkspace(files);
  try {
    const entries = workspace.entries();
    if (!entries.some(entry => entry.file === candidate.entry && entry.views.some(view => view.id === candidate.view))) {
      throw new Error('The selected design view does not exist.');
    }
    for (const entry of entries) for (const view of entry.views) {
      const result = workspace.renderSync({entry: entry.file, view: view.id});
      if (result.diagnostics.some(item => item.severity === 'error' || item.severity === 'incomplete')) {
        throw new Error(`Design refresh needs manual reconciliation: ${entry.file} / ${view.id}`);
      }
    }
  } finally {workspace.destroy();}
  return candidate;
}
