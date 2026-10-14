import {requestedAdministrationResource, postgresqlAdministrationContext} from 'sources/cdeadmin_ui/navigation/postgresqlAdministration';

describe('native PostgreSQL Explorer administration', () => {
  const context = {native_object_id: 42, resource_kind: 'aggregate', database_target_id: 'postgresql-database:18'};
  const resource = {resource_id: 'authorized-id', resource_kind: 'aggregate',
    extensions: {postgresql: {object_id: 42, database_id: 18}}};
  it('binds the native OID, kind and database instead of the displayed name', () => {
    expect(requestedAdministrationResource(resource, context)).toBe(true);
    for (const change of [{native_object_id: 43}, {resource_kind: 'operator'},
      {database_target_id: 'postgresql-database:19'}, {native_object_id: '42'}]) {
      expect(requestedAdministrationResource(resource, {...context, ...change})).toBe(false);
    }
    expect(requestedAdministrationResource(resource, {resource_id: 'authorized-id'})).toBe(true);
    expect(requestedAdministrationResource(resource, {resource_id: 'missing', ...context})).toBe(false);
  });
  const makeTree = (type='aggregate') => {
    const data = [{_type: type, _id: 42}, {_type: 'schema', _id: 7, label: ' app schema '},
      {_type: 'database', _id: 18, connected: true},
      {_type: 'server', _id: 1, connected: true, version: 180003}];
    return {data, tree: {itemData: item => data[item], hasParent: item => item < 3, parent: item => item + 1}};
  };
  it('opens object alteration at its exact connected database', () => {
    const {tree} = makeTree();
    const selected = postgresqlAdministrationContext(tree, 0, 'aggregate');
    expect(selected.serverItem).toBe(3);
    expect(selected.context).toEqual({...context, operation_id: 'alter', display_name: undefined});
  });
  it('opens collection creation without inventing an object OID', () => {
    const {tree} = makeTree('coll-operator');
    expect(postgresqlAdministrationContext(tree, 0, 'operator').context).toEqual({
      database_target_id: 'postgresql-database:18', resource_kind: 'operator', operation_id: 'create', schema_name: ' app schema ', display_name: undefined});
  });
  it('does not offer user-object administration in a system catalog', () => {
    const {tree,data} = makeTree(); data[1]._type = 'catalog';
    expect(postgresqlAdministrationContext(tree, 0, 'aggregate')).toBeNull();
  });
  it('refuses disconnected, incompatible or unrelated selections', () => {
    for (const change of [{connected: false}, {version: 170000}, {cde_endpoint: true}]) {
      const {tree,data} = makeTree(); Object.assign(data[3], change);
      expect(postgresqlAdministrationContext(tree, 0, 'aggregate')).toBeNull();
    }
    const {tree,data} = makeTree(); data[2].connected = false;
    expect(postgresqlAdministrationContext(tree, 0, 'aggregate')).toBeNull();
    expect(postgresqlAdministrationContext(tree, 0, 'table')).toBeNull();
  });
});
