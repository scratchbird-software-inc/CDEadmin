// Parse documentary records only. Never resolve imports, render or execute SQL.
import runtime from '../../../static/vendor/ddn/current/ddn.mjs';
function check(value) { if(!value) throw new Error('Invalid catalog document'); }
process.stdin.setEncoding('utf8');
let input = '';
try {
  for await (const chunk of process.stdin) {
    input += chunk;
    check(Buffer.byteLength(input) <= 16 * 1024 * 1024);
  }
  const engine = process.argv[2] || 'firebird';
  check(['firebird', 'mysql', 'mariadb', 'duckdb'].includes(engine));
  const snapshot = JSON.parse(input);
  const rows = [], identities = new Set(), uids = new Set();
  let provenance;
  for(const [filename, source] of Object.entries(snapshot.files)) {
  const parsed = runtime.parse(source, filename);
  check(parsed.module === `scratchrobin.${engine}.catalog` && parsed.imports.length === 0);
  check(parsed.declarations.every((item) => ['data', 'view', 'format'].includes(item.type)));
  if(filename === snapshot.entry) check(parsed.declarations.some((item) => item.type === 'view' && item.id === snapshot.view));
  const names = new Set();
  for(const block of parsed.declarations) {
    check(!names.has(block.id)); names.add(block.id);
    if(block.type !== 'data') continue;
    check(block.id === 'provenance' || /^catalog_[1-9][0-9]*$/.test(block.id));
    check(block.children.length <= 100);
    const local = new Set();
    for(const row of block.children) {
      check(row.type === 'object' && row.props.kind === 'record' && !row.children.length);
      check(!local.has(row.id)); local.add(row.id);
      if(block.id === 'provenance') {
        check(!provenance && block.children.length === 1 && row.id === 'capture');
        provenance = row.props.x_record;
        check(provenance?.mapping === `scratchrobin.${engine}.catalog@1` && typeof provenance.native_json === 'string');
        continue;
      }
      if(row.id === 'empty' && !row.props.x_record) continue;
      const fields = row.props.x_record;
      check(fields && Object.keys(fields).sort().join() === 'kind,native_json,path_json,resource_id,system');
      check(Object.values(fields).every((value) => typeof value === 'string'));
      check(fields.resource_id && fields.kind && ['true', 'false', 'unknown'].includes(fields.system));
      check(typeof row.props.uid === 'string' && typeof row.label === 'string');
      check(!identities.has(fields.resource_id) && !uids.has(row.props.uid));
      identities.add(fields.resource_id); uids.add(row.props.uid);
      rows.push({...fields, uid: row.props.uid, name: row.label,
        source_location: {file: filename, start: row.start, end: row.end, unit: 'utf16-code-units'}});
      check(rows.length <= 20000);
    }
  }
  }
  check(provenance);
  process.stdout.write(JSON.stringify({provenance: provenance.native_json, rows}));
} catch {
  process.stderr.write('Invalid or unsupported native catalog DDN document.');
  process.exitCode = 1;
}
