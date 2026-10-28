import {Buffer} from 'node:buffer';
import {createHash} from 'node:crypto';
import {admitWorkspace, mapping} from './workspace_admission.mjs';
const check = value => { if(!value) throw new Error('Invalid relational mapping'); };
// Physical-schema vocabulary (docs/en_US/ddn_physical_schema_vocabulary.rst). Values are
// passed through verbatim; the Python adapters validate and interpret them.
const PHYSICAL = ['physical_kind','physical_name','rename_from','columns_json','unique','method','predicate',
  'expression','referenced_columns_json','on_delete','on_update','drop','drop_confirmation'];
const physicalOf = native => Object.fromEntries(PHYSICAL.filter(name => native && Object.hasOwn(native, name)).map(name => [name, native[name]]));
let input = '';
try {
  for await(const chunk of process.stdin) {input += chunk; check(Buffer.byteLength(input) <= 16 * 1024 * 1024);}
  const engine = process.argv[2] || 'firebird';
  check(['firebird', 'postgresql', 'mysql', 'mariadb', 'sqlite', 'duckdb'].includes(engine));
  const documents = await admitWorkspace(JSON.parse(input), `scratchrobin.${engine}.relations`);
  const definitions = new Map(), annotations = new Map();
  const key = (file, id) => JSON.stringify([file, id]);
  for(const [file, doc] of documents) for(const row of doc.records) {
    if(row.kind !== 'definition') continue;
    check(!definitions.has(key(file, row.ref.id)));
    definitions.set(key(file, row.ref.id), row);
    const facts = mapping(row.record);
    if(facts) {
      check(row.record.role === 'record' && facts.block === 'relations' &&
        typeof facts.uid === 'string' && typeof facts.record?.subject_id === 'string');
      const subject = key(file, facts.record.subject_id);
      check(!annotations.has(subject)); annotations.set(subject, {file, facts});
    }
  }
  const rows = [], fields = [], fieldRecords = [], relationships = [], identities = new Set(), uids = new Set();
  const rowInfo = [], drafts = [];
  const resourceIds = new Map();
  for(const [subject, {facts}] of annotations) {
    const definition = definitions.get(subject), native = facts.record;
    check(definition && native.subject_kind === definition.record.role && !uids.has(facts.uid));uids.add(facts.uid);
    if(native.resource_id !== undefined) {
      check(typeof native.resource_id === 'string' && typeof native.native_json === 'string' && !identities.has(native.resource_id));
      identities.add(native.resource_id); resourceIds.set(subject, native.resource_id);
      const row = {resource_id: native.resource_id, uid: facts.uid, native_json: native.native_json};
      const physical = physicalOf(native);
      if(Object.keys(physical).length) row.physical = physical;
      rows.push(row); rowInfo.push({row, subject, native});
      check(rows.length <= 20000);
    } else if(['index','constraint','ref'].includes(native.subject_kind) && native.physical_kind !== undefined) {
      check(typeof native.parent_id === 'string' || native.subject_kind === 'ref');
      drafts.push({subject, uid: facts.uid, subject_kind: native.subject_kind, native, physical: physicalOf(native)});
    }
  }
  const parentMembers=new Map();
  for(const [subject,row] of definitions) if(resourceIds.has(subject) && ['table','view'].includes(row.record.role)) {
    for(const member of row.record.members || []) {
      const identity=key(member.file || row.file,member.id);
      const parents=parentMembers.get(identity) || new Set();parents.add(subject);parentMembers.set(identity,parents);
    }
  }
  const endpointsOf = (subject, file) => {
    const definition = definitions.get(subject);
    if(definition?.record.role !== 'ref' || definition.record.endpoints?.length !== 2) return undefined;
    const [from, to] = definition.record.endpoints.map(endpoint => endpoint.definition);
    return {source: resourceIds.get(key(from?.file || file, from?.id)) ?? null,
            target: resourceIds.get(key(to?.file || file, to?.id)) ?? null};
  };
  for(const {row, subject, native} of rowInfo) {
    const file = JSON.parse(subject)[0];
    if(typeof native.parent_id === 'string') row.parent_resource_id = resourceIds.get(key(file, native.parent_id)) ?? null;
    const endpoints = endpointsOf(subject, file);
    if(endpoints) row.endpoints = endpoints;
  }
  const physicalDrafts = drafts.map(({subject, uid, subject_kind, native, physical}) => {
    const file = JSON.parse(subject)[0], endpoints = endpointsOf(subject, file);
    return {uid, subject_kind, physical, ...(endpoints ? {endpoints} : {}),
      parent_resource_id: endpoints ? endpoints.source : resourceIds.get(key(file, native.parent_id)) ?? null};
  });
  for(const [subject,row] of definitions) {
    if(row.record.role==='record') continue;
    const annotation=annotations.get(subject);
    const file=row.file, native=annotation?.facts.record;
    let facts=annotation?.facts;
    if(row.record.role==='field') {
      const parents=parentMembers.get(subject);
      check(parents?.size===1);
      const parentKey=[...parents][0], parent=definitions.get(parentKey);
      check(parent && resourceIds.has(parentKey));
      if(annotation) check(key(file,native.parent_id)===parentKey);
      else {
        check(['mysql','mariadb','postgresql'].includes(engine) && parent.record.role==='table');
        const draft=createHash('sha256').update(parentKey+subject).digest('hex').slice(0,32).replace(/(.{8})(.{4})(.{4})(.{4})(.{12})/,'$1-$2-$3-$4-$5');
        facts={uid:engine==='postgresql'?annotations.get(parentKey).facts.uid+':new:'+draft:'ddn-new-field:'+subject};
        check(!uids.has(facts.uid));uids.add(facts.uid);
      }
      const original=native?.field_properties_json ? JSON.parse(native.field_properties_json) : native?.field_properties || {};
      const content=row.record.content || {};
      const properties=Object.fromEntries(['datatype','nullable'].filter(k=>Object.hasOwn(content,k)).map(k=>[k,content[k]]));
      const display=value=>typeof value==='string' && /[\r\n\0]/.test(value)?JSON.stringify(value).slice(1,-1):value;
      if(Object.hasOwn(row.record,'description')) properties.description=row.record.description===display(original.description)?original.description:row.record.description;
      const originalTitle=native?.field_title_json ? JSON.parse(native.field_title_json) : undefined;
      const labelText=value=>{const text=String(display(value));let result=text.slice(0,1023);if(/[\uD800-\uDBFF]$/.test(result))result=result.slice(0,-1);return text.length>1024?result+'…':text;};
      const label=originalTitle!==undefined && row.record.title===labelText(originalTitle)?originalTitle:row.record.title ?? row.record.name;
      fields.push(facts.uid);
      fieldRecords.push({uid:facts.uid,parent_resource_id:resourceIds.get(parentKey),label,physical:physicalOf(native),
        property_names:['uid',...Object.keys(content),...(Object.hasOwn(properties,'description')?['description']:[]),...(Object.hasOwn(original,'shape')?['shape']:[])],properties});
    } else if(row.record.category==='relation' && ['mysql','mariadb'].includes(engine)) {
      check(row.record.role==='ref' && row.record.endpoints?.length===2);
      const [from,to]=row.record.endpoints.map(endpoint=>endpoint.definition);
      const uid=facts?.uid || 'ddn-new-relationship:'+JSON.stringify([file,row.ref.id]);
      if(!facts) {check(!uids.has(uid));uids.add(uid);}
      relationships.push({uid,from_ref:from?.id ?? null,to_ref:to?.id ?? null,kind:'ref',
        enforcement:row.record.properties?.enforcement ?? null,native_json:native?.native_json ?? null,
        source:resourceIds.get(key(from?.file || file,from?.id)) ?? null,target:resourceIds.get(key(to?.file || file,to?.id)) ?? null});
    } else check(annotation);
  }
  process.stdout.write(JSON.stringify({rows, fields, field_records: fieldRecords, physical_drafts: physicalDrafts,
    ...(['mysql','mariadb'].includes(engine) ? {relationships} : {})}));
} catch {
  process.stderr.write('Invalid or unsupported native relational DDN document.');process.exitCode = 1;
}
