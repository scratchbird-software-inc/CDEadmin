import {Buffer} from 'node:buffer';
// Public DDN parser only; imported source cannot resolve files or execute SQL.
import runtime from '../../../static/vendor/ddn/current/ddn.mjs';
process.stdin.setEncoding('utf8');
let input = '';
try {
  for await (const chunk of process.stdin) {
    input += chunk;
    if (Buffer.byteLength(input) > 16 * 1024 * 1024) throw new Error();
  }
  const engine = process.argv[2] || 'firebird';
  if (!['firebird', 'postgresql', 'mysql', 'mariadb'].includes(engine)) throw new Error();
  const snapshot = JSON.parse(input), rows = [], fields = [], fieldRecords = [], relations = [], objectIds = new Map(), ids = new Set();
  const visit = (node, parent = null, namespace = null) => {
    if (['mysql', 'mariadb'].includes(engine) && node.type === 'relation') {
      relations.push({uid: node.props?.uid ?? null, namespace, from_ref: node.from?.$ref ?? null,
        to_ref: node.to?.$ref ?? null, kind: node.props?.kind ?? null, enforcement: node.props?.enforcement ?? null,
        native_json: node.props?.x_record?.native_json ?? null});
    }
    if (['postgresql', 'mysql', 'mariadb'].includes(engine) && node.type === 'field' && typeof node.props?.uid !== 'string') throw new Error();
    if (node.type === 'field' && typeof node.props?.uid === 'string') {
      fields.push(node.props.uid);
      fieldRecords.push({uid: node.props.uid, parent_resource_id: parent, label: node.label,
        property_names: Object.keys(node.props || {}),
        properties: Object.fromEntries(['nullable', 'description', 'datatype'].filter(key =>
          Object.prototype.hasOwnProperty.call(node.props, key)).map(key => [key, node.props[key]]))});
    }
    const facts = node.props?.x_record;
    if (facts?.resource_id !== undefined) {
      if (typeof facts.resource_id !== 'string' || typeof facts.native_json !== 'string' ||
          typeof node.props.uid !== 'string' || ids.has(facts.resource_id)) throw new Error();
      ids.add(facts.resource_id);
      if (['mysql', 'mariadb'].includes(engine)) {
        const alias = namespace + '.' + node.id;
        if (objectIds.has(alias)) throw new Error();
        objectIds.set(alias, facts.resource_id);
      }
      parent = facts.resource_id;
      rows.push({resource_id: facts.resource_id, uid: node.props.uid, native_json: facts.native_json});
      if (rows.length > 20000) throw new Error();
    }
    for (const child of node.children || []) visit(child, parent, namespace);
  };
  for (const [name, source] of Object.entries(snapshot.files)) {
    const parsed = runtime.parse(source, name);
    if (parsed.module !== `scratchrobin.${engine}.relations` || parsed.imports.length) throw new Error();
    for (const node of parsed.declarations) if (node.type === 'data') visit(node, null, node.id);
  }
  const resolve = (namespace, reference) => typeof reference === 'string' ?
    objectIds.get(reference.includes('.') ? reference : namespace + '.' + reference) ?? null : null;
  const relationships = relations.map(({namespace, from_ref, to_ref, ...facts}) => ({...facts,
    source: resolve(namespace, from_ref), target: resolve(namespace, to_ref)}));
  process.stdout.write(JSON.stringify({rows, fields, field_records: fieldRecords,
    ...(['mysql', 'mariadb'].includes(engine) ? {relationships} : {})}));
} catch {
  process.stderr.write('Invalid or unsupported native relational DDN document.');
  process.exitCode = 1;
}
