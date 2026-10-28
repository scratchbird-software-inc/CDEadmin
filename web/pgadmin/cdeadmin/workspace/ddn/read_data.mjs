import {admitWorkspace, mapping} from './workspace_admission.mjs';
import {Buffer} from 'node:buffer';
let input='';
try {
  for await(const chunk of process.stdin) {
    input+=chunk;
    if(Buffer.byteLength(input)>16*1024*1024) throw new Error();
  }
  const snapshot=JSON.parse(input), rows=[];
  let header=null;
  for(const document of (await admitWorkspace(snapshot,'scratchrobin.firebird.data')).values()) {
    for(const row of document.records) {
      if(row.kind !== 'definition') continue;
      const metadata=mapping(row.record), block=metadata?.block, facts=metadata?.record;
      if(row.record.role!=='record' || !metadata || block!=='data_info' && !/^rows_[1-9][0-9]*$/.test(block)) throw new Error();
      if(block==='data_info') {
        if(header!==null || Object.keys(facts||{}).join()!=='header_json' || typeof facts.header_json!=='string') throw new Error();
        header=facts.header_json;
      } else {
        if(Object.keys(facts||{}).sort().join()!=='ordinal,table_index,values_json' || !Number.isSafeInteger(facts.ordinal) ||
           !Number.isSafeInteger(facts.table_index) || typeof facts.values_json!=='string' || rows.length>=100000) throw new Error();
        if(metadata.uid!==`firebird-data:${facts.table_index}:${facts.ordinal}`) throw new Error();
        rows.push(facts);
      }
    }
  }
  if(header===null) throw new Error();
  process.stdout.write(JSON.stringify({header,rows}));
} catch {
  process.stderr.write('Invalid static native data DDN workspace.');process.exitCode=1;
}
