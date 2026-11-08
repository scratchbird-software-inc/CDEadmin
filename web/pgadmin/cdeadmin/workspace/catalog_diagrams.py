##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""To Diagram: one database's tables and views as named-diagram content.

Owner direction 2026-11-06: "To Diagram" adds database objects with their
relations to a named diagram (the Diagrams tool). Every engine's catalog
export already builds the relations diagram: table and view declarations
with their fields, and one relation per foreign key with crow's-foot marks.
This module picks that export by the endpoint's engine and says where each
relation sits (host, instance, database and the containers of its native
path); the browser groups them in nested DDN regions and merges them into
the diagram with DDN's own source functions. Nothing here edits a diagram,
and no native SQL is run beyond the export's own catalog capture.
"""
import hashlib

# Endpoint profiles whose catalog export builds a relations diagram.
ENGINES = {
    'firebird-native': 'firebird', 'firebird-embedded': 'firebird',
    'mysql-native': 'mysql', 'mariadb-native': 'mariadb',
    'postgresql-native': 'postgresql', 'sqlite-native': 'sqlite',
    'duckdb-native': 'duckdb',
}


def engine_of(server):
    profile = getattr(getattr(server, 'endpoint_profile', None),
                      'profile_id', None)
    return ENGINES.get(profile)


def _export(service, server, engine, target):
    if engine == 'firebird':
        # Firebird's export reads the cached catalog generation it is given.
        context, endpoint, root = service.endpoint_service.workspace(
            server, database_target_id=target)
        generation = service.resource_service.list_page(
            context, root, page_size=500,
            provider_route=endpoint['route']).to_dict()['generation']
        return service.export_firebird_catalog(
            server, {'generation': generation, 'database_target_id': target})
    return getattr(service, f'{engine}_catalog')(
        server, {'database_target_id': target})


def catalog_diagram(service, server, request):
    if (not isinstance(request, dict) or
            set(request) != {'database_target_id'} or
            not isinstance(request['database_target_id'], str) or
            not request['database_target_id']):
        raise ValueError('Select a registered database')
    target = request['database_target_id']
    engine = engine_of(server)
    if engine is None:
        raise ValueError('This connection has no catalog diagram')
    diagram = _export(service, server, engine, target).get('diagram') or {}
    if 'snapshot' not in diagram:
        raise ValueError(diagram.get('unavailable') or
                         'This database has no tables or views to diagram')
    context, endpoint, _root = service.endpoint_service.workspace(
        server, database_target_id=target)
    route = endpoint.get('route') or {}
    targets = service.endpoint_service.database_catalog(server)['targets']
    database = next((item for item in targets
                     if item['target_id'] == target), None)
    endpoint_id = str(context.endpoint_id)
    host = str(route.get('host') or 'localhost')
    port = route.get('port')
    name = database['display_name'] if database else target
    regions, relations = _regions(host, endpoint_id, server.name, port,
                                  target, name, diagram['relations'])
    return {
        'engine': engine,
        'database': {'id': target, 'name': name},
        # One objects file per endpoint and database; adding the database
        # again replaces it, while the diagram's view keeps its layout.
        'file': f'objects/{engine}-{_digest(endpoint_id, target)}.ddn',
        'snapshot': diagram['snapshot'],
        'regions': regions,
        'relations': relations,
        'warnings': list(diagram.get('warnings', [])),
    }


def _digest(*parts):
    return hashlib.sha256('\0'.join(parts).encode('utf8')).hexdigest()[:16]


def _regions(host, endpoint_id, instance, port, target, database, relations):
    """Nested regions: host, instance (endpoint), database, then the
    containers of each relation's native path (schemas, attached databases,
    DuckDB catalogs). A path that starts with the database's own name does
    not repeat it. Each relation is a member of its innermost region."""
    host_id = 'region_' + _digest('host', host)
    instance_id = 'region_' + _digest('instance', endpoint_id)
    database_id = 'region_' + _digest('database', endpoint_id, target)
    regions = [
        {'id': host_id, 'name': host, 'role': 'host'},
        {'id': instance_id, 'role': 'server', 'parent': host_id,
         'name': instance + ('' if port is None else f' :{port}')},
        {'id': database_id, 'name': database, 'role': 'database',
         'parent': instance_id},
    ]
    known, placed = {}, []
    for relation in relations:
        containers = [str(part) for part in relation['path'][:-1]]
        if containers and containers[0] == database:
            containers = containers[1:]
        parent = database_id
        for depth in range(len(containers)):
            region = 'region_' + _digest('container', endpoint_id, target,
                                         *containers[:depth + 1])
            if region not in known:
                known[region] = {'id': region, 'name': containers[depth],
                                 'role': 'schema', 'parent': parent}
                regions.append(known[region])
            parent = region
        placed.append({**relation, 'region': parent})
    return regions, placed
