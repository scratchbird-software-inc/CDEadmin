// Resolve native Explorer selections against the authorized workspace catalog.
export function requestedAdministrationResource(resource, context) {
  const requestedId = context.resource_id || context.parent_resource_id;
  if (requestedId) return resource.resource_id === requestedId;
  const oid = context.native_object_id;
  if (!Number.isInteger(oid) || oid < 1 || oid > 4294967295) return false;
  const native = resource.extensions?.postgresql;
  return resource.resource_kind === context.resource_kind &&
    Number(native?.object_id) === oid &&
    context.database_target_id === `postgresql-database:${native?.database_id}`;
}

export function postgresqlAdministrationContext(tree, item, kind) {
  if (!['operator', 'aggregate'].includes(kind)) return null;
  const selected = tree.itemData(item);
  if (![kind, `coll-${kind}`].includes(selected?._type)) return null;
  let database, server, serverItem, schema;
  for (let current = item; current !== null && current !== undefined; current = tree.hasParent(current) ? tree.parent(current) : null) {
    const data = tree.itemData(current);
    if (data?._type === 'catalog') return null;
    if (data?._type === 'schema') schema = data.label || data._label;
    if (data?._type === 'database') database = data;
    if (data?._type === 'server') { server = data; serverItem = current; break; }
  }
  if (!database?.connected || !server?.connected || server.cde_endpoint ||
      Number(server.version) !== 180003) return null;
  const oid = selected._type === kind ? Number(selected._id) : undefined;
  if (oid !== undefined && (!Number.isInteger(oid) || oid < 1 || oid > 4294967295)) return null;
  return {server, serverItem, context: {
    database_target_id: `postgresql-database:${database._id}`,
    display_name: database.label || database._label,
    resource_kind: kind,
    ...(oid === undefined ? {operation_id: 'create', schema_name: schema} : {native_object_id: oid, operation_id: 'alter'}),
  }};
}
