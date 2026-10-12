// Public DDN parser only; imported source cannot resolve files or execute SQL.
import runtime from '../../../static/vendor/ddn/current/ddn.mjs';
process.stdin.setEncoding('utf8');
let input = '';
try {
  for await (const chunk of process.stdin) {
    input += chunk;
    if (Buffer.byteLength(input) > 16 * 1024 * 1024) throw new Error();
  }
  const snapshot = JSON.parse(input), rows = [], fields = [], ids = new Set();
  const visit = node => {
    if (node.type === 'field' && typeof node.props?.uid === 'string') fields.push(node.props.uid);
    const facts = node.props?.x_record;
    if (facts?.resource_id !== undefined) {
      if (typeof facts.resource_id !== 'string' || typeof facts.native_json !== 'string' ||
          typeof node.props.uid !== 'string' || ids.has(facts.resource_id)) throw new Error();
      ids.add(facts.resource_id);
      rows.push({resource_id: facts.resource_id, uid: node.props.uid, native_json: facts.native_json});
      if (rows.length > 20000) throw new Error();
    }
    for (const child of node.children || []) visit(child);
  };
  for (const [name, source] of Object.entries(snapshot.files)) {
    const parsed = runtime.parse(source, name);
    if (parsed.module !== 'scratchrobin.firebird.relations' || parsed.imports.length) throw new Error();
    for (const node of parsed.declarations) if (node.type === 'data') visit(node);
  }
  process.stdout.write(JSON.stringify({rows, fields}));
} catch {
  process.stderr.write('Invalid or unsupported Firebird relational DDN document.');
  process.exitCode = 1;
}
