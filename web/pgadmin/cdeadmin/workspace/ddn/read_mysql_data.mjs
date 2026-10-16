import {admitWorkspace} from './workspace_admission.mjs';
import {Buffer} from 'node:buffer';
let input = '';
try {
  for await(const chunk of process.stdin) {
    input += chunk;
    if(Buffer.byteLength(input) > 16 * 1024 * 1024) throw new Error();
  }
  const snapshot = JSON.parse(input), rows = [], ordinals = new Set();
  let header = null;
  for(const document of admitWorkspace(snapshot, 'scratchrobin.result.static').values()) {
    for(const block of document.declarations) {
      if(!['data', 'view', 'format'].includes(block.type)) throw new Error();
      if(block.type !== 'data') continue;
      if(!['provenance', 'rows'].includes(block.id) || block.children.length > 100) throw new Error();
      for(const row of block.children) {
        if(row.type !== 'object' || row.props.kind !== 'record' || row.children.length) throw new Error();
        const facts = row.props.x_record;
        if(block.id === 'provenance') {
          if(block.children.length !== 1 || typeof facts?.native_json !== 'string' || Object.keys(facts).join() !== 'native_json') throw new Error();
          if(header !== null && header !== facts.native_json) throw new Error();
          header = facts.native_json;
        } else {
          if(row.id === 'empty' && !facts) continue;
          if(!/^r_[1-9][0-9]*$/.test(row.id) || ordinals.has(row.id) || typeof facts?.values_json !== 'string' || rows.length >= 6000) throw new Error();
          ordinals.add(row.id);
          rows.push({ordinal: Number(row.id.slice(2)), values: facts.values_json,
            display: Object.fromEntries(Object.entries(facts).filter(([key]) => key !== 'values_json'))});
        }
      }
    }
  }
  if(header === null) throw new Error();
  rows.sort((a, b) => a.ordinal - b.ordinal);
  if(rows.some((row, index) => row.ordinal !== index + 1)) throw new Error();
  process.stdout.write(JSON.stringify({header, rows}));
} catch {
  process.stderr.write('Invalid native MySQL data DDN workspace.');
  process.exitCode = 1;
}
