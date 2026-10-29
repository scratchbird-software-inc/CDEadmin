import {Buffer} from 'node:buffer';
import {admitWorkspace, mapping} from './workspace_admission.mjs';
function check(value) { if(!value) throw new Error('Invalid catalog document'); }
process.stdin.setEncoding('utf8');
let input = '';
try {
  for await(const chunk of process.stdin) {
    input += chunk;
    check(Buffer.byteLength(input) <= 16 * 1024 * 1024);
  }
  const engine = process.argv[2] || 'firebird';
  check(['firebird', 'postgresql', 'mysql', 'mariadb', 'duckdb', 'sqlite'].includes(engine));
  const snapshot = JSON.parse(input), rows = [], identities = new Set(), uids = new Set();
  let provenance;
  const documents = await admitWorkspace(snapshot, `scratchrobin.${engine}.catalog`);
  for(const [filename, document] of documents) {
    for(const row of document.records) {
      if(row.kind !== 'definition') continue;
      const facts = mapping(row.record);
      check(row.record.role === 'record' && facts && ['module', 'block', 'record', 'uid'].every(key => key === 'uid' || Object.hasOwn(facts, key)));
      const fields = facts.record;
      if(facts.block === 'provenance') {
        check(!provenance && row.ref.id === 'provenance.capture');
        check(fields?.mapping === `scratchrobin.${engine}.catalog@1` && typeof fields.native_json === 'string');
        provenance = fields;
        continue;
      }
      check(/^catalog_[1-9][0-9]*$/.test(facts.block));
      if(row.ref.id === facts.block + '.empty' && !Object.hasOwn(fields, 'resource_id')) continue;
      check(fields && Object.keys(fields).sort().join() === 'kind,native_json,path_json,resource_id,system');
      check(Object.values(fields).every(value => typeof value === 'string'));
      check(fields.resource_id && fields.kind && ['true', 'false', 'unknown'].includes(fields.system));
      check(typeof facts.uid === 'string' && typeof row.record.title === 'string');
      check(!identities.has(fields.resource_id) && !uids.has(facts.uid));
      identities.add(fields.resource_id); uids.add(facts.uid);
      const node = document.nodes.get(row.ref.id);
      check(node);
      rows.push({...fields, uid: facts.uid, name: facts.name_json ? JSON.parse(facts.name_json) : row.record.title,
        source_location: {file: filename, start: node.start, end: node.end, unit: 'utf16-code-units', definition_id: row.ref.id}});
      check(rows.length <= 20000);
    }
  }
  check(provenance);
  process.stdout.write(JSON.stringify({provenance: provenance.native_json, rows}));
} catch(error) {
  process.stdout.write(JSON.stringify({diagnostics: error.diagnostics || []}));
  process.stderr.write('Invalid or unsupported native catalog DDN document.');
  process.exitCode = 1;
}
