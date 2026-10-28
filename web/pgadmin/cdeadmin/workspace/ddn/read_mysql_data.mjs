import {admitWorkspace, mapping} from './workspace_admission.mjs';
import {Buffer} from 'node:buffer';
let input = '';
try {
  for await(const chunk of process.stdin) {
    input += chunk;
    if(Buffer.byteLength(input) > 16 * 1024 * 1024) throw new Error();
  }
  const snapshot = JSON.parse(input), rows = [], ordinals = new Set(), payload = [];
  let header = null;
  for(const document of (await admitWorkspace(snapshot, 'scratchrobin.result.static')).values()) {
    for(const row of document.records) {
      if(row.kind !== 'definition') continue;
      const meta=mapping(row.record), block=meta?.block, facts=meta?.record;
      if(row.record.role!=='record' || !meta || !['provenance','rows','native_payload'].includes(block)) throw new Error();
      if(block==='native_payload') {
        if(!Number.isInteger(facts?.ordinal) || facts.ordinal<1 || facts.ordinal>4 || facts.encoding!=='arrow-ipc-base64' ||
          typeof facts.data!=='string' || Object.keys(facts).sort().join()!=='data,encoding,ordinal' || !/^[A-Za-z0-9+/]*={0,2}$/.test(facts.data)) throw new Error();
        payload.push(facts);
      } else if(block==='provenance') {
        if(typeof facts?.native_json!=='string' || Object.keys(facts).join()!=='native_json') throw new Error();
        if(header!==null && header!==facts.native_json) throw new Error();header=facts.native_json;
      } else {
        const identity=row.ref.id.slice('rows.'.length);
        if(identity==='empty' && !facts.values_json) continue;
        if(!/^r_[1-9][0-9]*$/.test(identity) || ordinals.has(identity) || typeof facts?.values_json!=='string' || rows.length>=6000) throw new Error();
        ordinals.add(identity);rows.push({ordinal:Number(identity.slice(2)),values:facts.values_json,
          display:Object.fromEntries(Object.entries(facts).filter(([k])=>k!=='values_json'))});
      }
    }
  }
  if(header === null) throw new Error();
  rows.sort((a, b) => a.ordinal - b.ordinal);
  if(rows.some((row, index) => row.ordinal !== index + 1)) throw new Error();
  payload.sort((a, b) => a.ordinal - b.ordinal);
  if(payload.some((part, index) => part.ordinal !== index + 1)) throw new Error();
  process.stdout.write(JSON.stringify({header, rows, native_payload: payload}));
} catch {
  process.stderr.write('Invalid native MySQL data DDN workspace.');
  process.exitCode = 1;
}
