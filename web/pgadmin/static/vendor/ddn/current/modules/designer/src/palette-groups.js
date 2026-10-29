import { roleDescriptor } from '../../profiles/src/core.js';
/** Authoring-library sections, independent of the semantic role or profile admission rules. */
const sections = [
    ['SQL objects', 'catalog database schema table foreign_table materialized_view view saved_view field index constraint sequence synonym function procedure trigger sql_type sql_domain extension qry query_operation write_operation'],
    ['Cluster objects', 'cluster shard partition partition_rule replica replica_set federation colocation placement router checkpoint recovery retention'],
    ['System infrastructure', 'host device network cloud cloud_account region zone site container environment security_zone namespace volume workspace registry service application gateway endpoint api'],
    ['File types', 'file file_set folder document archive backup blob bucket manifest export log snapshot model_artifact'],
    ['Data structures', 'aggregate array cache collection cube data_product dataset dimension enumeration fact feature graph graph_edge graph_node history key_value keyspace map metric rdf record search_index semantic_model set tensor time_series timeline variant vector wide_column window'],
    ['Messaging', 'binding bridge connector consumer_group message pub queue schema_registry sub subscription topic webhook'],
    ['Automation', 'activity command job manual_activity opr pipeline pkg run schedule test rule'],
    ['People & permissions', 'organization team role identity entl gpo pol prv dcl cls'],
    ['Concepts & notes', 'context decision domain entity object term note note.sticky observation issue change qlr rel unit sample fixture dct slo ext'],
];
export const paletteGroupOrder = sections.map(([name]) => name);
const groupByRole = new Map(sections.flatMap(([group, roles]) => roles.split(' ').map(role => [role, group])));
const methodNames = { uml: 'UML elements', sysml: 'SysML elements', uaf: 'Architecture elements', flow: 'Flow elements', dfd: 'Data flow elements', chen: 'Chen elements', elec: 'Electrical symbols', electrical: 'Electrical symbols', c4: 'C4 elements', bpmn: 'BPMN elements', cmmn: 'Case elements', erd: 'ERD elements', archimate: 'ArchiMate elements', soaml: 'Service elements', req: 'Requirements', vsm: 'Value stream elements', epk: 'Event process elements' };
export function paletteGroup(role) {
    const group = groupByRole.get(role);
    if (group)
        return group;
    const method = role.split('.')[0];
    if (methodNames[method])
        return methodNames[method];
    const shape = String(roleDescriptor(role)?.render.shape ?? 'card').split('.')[0];
    return { frame: 'Containers', activity: 'Activities', decision: 'Decisions', note: 'Notes & evidence', document: 'Documents', cylinder: 'Storage', actor: 'People', port: 'Interfaces', sample: 'Samples', profile: 'Diagram symbols' }[shape] ?? 'Other elements';
}
//# sourceMappingURL=palette-groups.js.map