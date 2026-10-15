import {admitWorkspace} from './workspace_admission.mjs';
import {Buffer} from 'node:buffer';
let input='';
try {
  for await(const chunk of process.stdin) {
    input+=chunk;
    if(Buffer.byteLength(input)>16*1024*1024) throw new Error();
  }
  const snapshot=JSON.parse(input), rows=[];
  let header=null;
  for(const document of admitWorkspace(snapshot,'scratchrobin.firebird.data').values()) {
    for(const block of document.declarations) {
      if(!['data','view','format'].includes(block.type)) throw new Error();
      if(block.type!=='data') continue;
      if(block.id!=='data_info' && !/^rows_[1-9][0-9]*$/.test(block.id)) throw new Error();
      if(block.children.length>100) throw new Error();
      for(const row of block.children) {
        if(row.type!=='object' || row.props.kind!=='record' || row.children.length) throw new Error();
        const facts=row.props.x_record;
        if(block.id==='data_info') {
          if(header!==null || block.children.length!==1 || Object.keys(facts||{}).join()!=='header_json' || typeof facts.header_json!=='string') throw new Error();
          header=facts.header_json;
        } else {
          if(Object.keys(facts||{}).sort().join()!=='ordinal,table_index,values_json' || !Number.isSafeInteger(facts.ordinal) ||
             !Number.isSafeInteger(facts.table_index) || typeof facts.values_json!=='string' || rows.length>=100000) throw new Error();
          if(row.props.uid !== `firebird-data:${facts.table_index}:${facts.ordinal}`) throw new Error();
          rows.push(facts);
        }
      }
    }
  }
  if(header===null) throw new Error();
  process.stdout.write(JSON.stringify({header,rows}));
} catch {
  process.stderr.write('Invalid static native data DDN workspace.');process.exitCode=1;
}
