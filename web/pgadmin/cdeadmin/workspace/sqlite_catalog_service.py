"""Owner-bound SQLite catalog exchange for the shared workspace."""

from ..providers.sqlite.provider import SQLiteProvider
from ..providers.sqlite.modules import option as module_option
from .firebird_catalog_export import build_export
from .firebird_catalog_import import compare_catalogs, read_catalog


def catalog(service, server, request, *, compare=False):
    if isinstance(request, dict) and (not request or 'database_target_ids' in request):
        if compare:
            raise ValueError('SQLite endpoint DDN bundle comparison is file-scoped')
        from .sqlite_server_catalog import serve
        return serve(service, server, request)
    if not isinstance(request, dict) or set(request) - {
            'database_target_id', 'include_system', 'resource_id', 'source'}:
        raise ValueError('Invalid SQLite catalog request')
    target = request.get('database_target_id')
    if not isinstance(target, str) or not target:
        raise ValueError('Select a registered SQLite database file')
    include_system = request.get('include_system', False)
    if type(include_system) is not bool:
        raise ValueError('Invalid system-object selection')
    resource_id = request.get('resource_id')
    if resource_id is not None and (not isinstance(resource_id, str) or
                                    not resource_id):
        raise ValueError('Invalid native object selection')
    document = (read_catalog(request.get('source'), engine='sqlite')
                if compare else None)
    context, endpoint, _root = service.endpoint_service.workspace(
        server, database_target_id=target)
    provider = service.endpoint_service.provider_registry.resolve(
        context).instance
    if (not isinstance(provider, SQLiteProvider) or
            context.profile_id != 'sqlite-native'):
        raise ValueError('Select a native SQLite endpoint')
    if document and (
            document['provenance']['endpoint_id'] != context.endpoint_id or
            document['provenance']['database_target_id'] != target):
        raise ValueError('Document belongs to another endpoint or database')
    captured = provider.capture_catalog(endpoint['route'],
                                        include_system=include_system)
    result = build_export(
        captured['resources'], endpoint_id=context.endpoint_id,
        target_id=target, generation=captured['generation'],
        resource_id=resource_id, include_system=include_system,
        refreshed=True, engine='sqlite', native_model=compare)
    if compare:
        return compare_catalogs(document, result)
    result['generation'] = captured['generation']
    result['capture_complete']=captured['complete']
    result['objects'] = [{
        'resource_id': item['resource_id'], 'name': item['display_name'],
        'kind': item['resource_kind'], 'path': item['display_path'],
        **({'external_content':module_option(item['native'].get('ddl',''),'content')}
           if item['resource_kind']=='fts-table' and item['native'].get('module_observation',{}).get('module','').lower() in {'fts4','fts5'} else {}),
        **({'fts_configuration': item['native'].get('fts_configuration')} if item['resource_kind']=='fts-table' else {})}
        for item in captured['resources']]
    return result


def fts_configuration_design(service, server, request):
    from .sqlite_fts_settings import generate
    if not isinstance(request, dict) or set(request) != {'database_target_id', 'baseline', 'resource_id', 'settings'}:
        raise ValueError('FTS design requires the exact baseline, table and native settings')
    baseline = read_catalog(request['baseline'], engine='sqlite')
    checked = schema_plan(service, server, {'database_target_id': request['database_target_id'],
        'baseline': request['baseline'], 'desired': request['baseline']})
    if checked['conflicts']:
        raise ValueError('Native SQLite metadata changed; capture a new baseline')
    desired = generate(baseline, request['resource_id'], request['settings'])
    resources = [{'resource_id': row['resource_id'], 'resource_kind': row['kind'], 'display_name': row['name'],
                  'display_path': row['path'], 'native': row['native']} for row in desired['rows'].values()]
    result = build_export(resources, endpoint_id=baseline['provenance']['endpoint_id'],
        target_id=request['database_target_id'], generation='native-fts-settings-design', include_system=False,
        refreshed=True, engine='sqlite')
    return {'snapshot': result['snapshot'], 'scope': 'native settings normalized in a private empty FTS module; registered file unchanged'}


def column_design(service,server,request):
    import sqlite3
    from .sqlite_column_design import generate
    if not isinstance(request,dict) or set(request)!={'database_target_id','baseline','resource_id','columns'}:
        raise ValueError('SQLite column design requires its exact baseline, table and structured definitions')
    baseline=read_catalog(request['baseline'],engine='sqlite')
    checked=schema_plan(service,server,{'database_target_id':request['database_target_id'],
        'baseline':request['baseline'],'desired':request['baseline']})
    if checked['conflicts']:raise ValueError('Native SQLite schema changed; capture a new baseline')
    try:desired=generate(baseline,request['resource_id'],request['columns'])
    except sqlite3.Error as error:raise ValueError('Native SQLite column design refused: '+str(error)[:400]) from None
    resources=[{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_name':row['name'],
        'display_path':row['path'],'native':row['native']} for row in desired['rows'].values()]
    result=build_export(resources,endpoint_id=baseline['provenance']['endpoint_id'],target_id=request['database_target_id'],
        generation='native-structured-column-design',include_system=False,refreshed=True,engine='sqlite')
    return {'snapshot':result['snapshot'],'columns':request['columns'],
        'scope':'Native schema-only generation on an owned empty prototype; registered file unchanged',
        'warnings':['Native existing-row checks run during reviewed atomic apply.']}


def data(service, server, request):
    if not isinstance(request, dict) or set(request) != {
            'database_target_id', 'resource_id', 'mode', 'row_limit'}:
        raise ValueError('Invalid SQLite data capture request')
    target = request['database_target_id']
    if not isinstance(target, str) or not target:
        raise ValueError('Select a registered SQLite database file')
    context, endpoint, _root = service.endpoint_service.workspace(
        server, database_target_id=target)
    provider = service.endpoint_service.provider_registry.resolve(
        context).instance
    if (not isinstance(provider, SQLiteProvider) or
            context.profile_id != 'sqlite-native'):
        raise ValueError('Select a native SQLite endpoint')
    return provider.capture_data(
        endpoint['route'], request['resource_id'],
        endpoint_id=context.endpoint_id, target_id=target,
        mode=request['mode'], row_limit=request['row_limit'])


def data_script(service, server, request):
    if not isinstance(request, dict) or set(request) != {'database_target_id', 'resource_id'}:
        raise ValueError('Invalid SQLite SQL export request')
    target = request['database_target_id']
    if not isinstance(target, str) or not target:
        raise ValueError('Select a registered SQLite file')
    context, endpoint, _root = service.endpoint_service.workspace(
        server, database_target_id=target)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, SQLiteProvider) or context.profile_id != 'sqlite-native':
        raise ValueError('Select a native SQLite endpoint')
    return provider.export_data_script(endpoint['route'], request['resource_id'],
        endpoint_id=str(context.endpoint_id), target_id=target)


def test_data(service, server, request):
    from .sqlite_test_data import generate, template
    if not isinstance(request, dict) or set(request) - {'database_target_id', 'recipe'}:
        raise ValueError('Invalid SQLite test-data request')
    target = request.get('database_target_id')
    if not isinstance(target, str) or not target:
        raise ValueError('Select a registered SQLite file')
    context, endpoint, _root = service.endpoint_service.workspace(
        server, database_target_id=target)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, SQLiteProvider) or context.profile_id != 'sqlite-native':
        raise ValueError('Select a native SQLite endpoint')
    captured = provider.capture_catalog(endpoint['route'], include_system=False)
    model = build_export(captured['resources'], endpoint_id=str(context.endpoint_id),
        target_id=target, generation=captured['generation'], include_system=False,
        refreshed=True, engine='sqlite', native_model=True)
    return generate(model, request['recipe']) if 'recipe' in request else template(model)


def schema_plan(service, server, request, *, generate_renames=False):
    from .sqlite_schema_plan import plan
    required={'database_target_id','baseline','renames'} if generate_renames else {'database_target_id','baseline','desired'}
    if (not isinstance(request, dict) or not required <= set(request) or
            set(request) - {'database_target_id', 'baseline', 'desired', 'deletions', 'rebuilds',
                            'column_renames', 'renames', 'fts_rebindings'} or
            generate_renames and set(request)-required-{'fts_rebindings'}):
        raise ValueError('SQLite schema preview requires exact baseline and desired DDN')
    target = request['database_target_id']
    if not isinstance(target, str) or not target:
        raise ValueError('Select a registered SQLite file')
    baseline = read_catalog(request['baseline'], engine='sqlite')
    desired = baseline if generate_renames else read_catalog(request['desired'], engine='sqlite')
    context, endpoint, _root = service.endpoint_service.workspace(
        server, database_target_id=target)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, SQLiteProvider) or context.profile_id != 'sqlite-native':
        raise ValueError('Select a native SQLite endpoint')
    if any(model['provenance']['endpoint_id'] != str(context.endpoint_id) or
           model['provenance']['database_target_id'] != target
           for model in (baseline, desired)):
        raise ValueError('Design belongs to another endpoint or registered SQLite file')
    if any(model['provenance'].get('include_system') is not False
           for model in (baseline, desired)):
        raise ValueError('Native SQLite migration requires user-object-only DDN capture')
    from ..providers.embedded_route import contained_database
    from .sqlite_schema_plan import _scope
    import os
    import stat
    path = contained_database(endpoint['route'])
    if path == ':memory:':
        raise ValueError('Native schema preview requires a registered SQLite file')
    file_info = os.stat(path)
    if not stat.S_ISREG(file_info.st_mode):
        raise ValueError('Native schema preview requires a regular SQLite file')
    for model in (baseline, desired):
        _scope(model)
        root = next(row for row in model['rows'].values()
                    if row['kind'] == 'database' and row['path'] == ['main'])
        if root['native'].get('registered_file_identity') != [file_info.st_dev, file_info.st_ino]:
            raise ValueError('Design file identity changed; capture a new SQLite baseline')
    captured = provider.capture_catalog(endpoint['route'], include_system=False)
    live = build_export(captured['resources'], endpoint_id=str(context.endpoint_id),
        target_id=target, generation=captured['generation'], include_system=False,
        refreshed=True, engine='sqlite', native_model=True)
    if generate_renames:
        from .sqlite_rename import generate,schema
        if schema(baseline)!=schema(live):raise ValueError('Native SQLite schema changed; capture a new baseline')
        desired,selected,_stages=generate(baseline,request['renames'],request.get('fts_rebindings',()))
        resources=[{'resource_id':row['resource_id'],'resource_kind':row['kind'],
            'display_name':row['name'],'display_path':row['path'],'native':row['native']} for row in desired['rows'].values()]
        result=build_export(resources,endpoint_id=str(context.endpoint_id),target_id=target,
            generation=captured['generation'],include_system=False,refreshed=True,engine='sqlite')
        return {'snapshot':result['snapshot'],'renames':selected,'fts_rebindings':request.get('fts_rebindings',[]),
            'scope':'native schema-only generation; registered file has not changed'}
    connection = provider.client._connect({'route': endpoint['route']})
    try:
        before_info = os.stat(path)
        if [before_info.st_dev, before_info.st_ino] != [file_info.st_dev, file_info.st_ino]:
            raise ValueError('SQLite registered file changed before native grammar validation')
        preview = plan(baseline, desired, live, connection,
                       deletions=request.get('deletions', ()),
                       rebuilds=request.get('rebuilds', ()),
                       column_renames=request.get('column_renames', ()),
                       renames=request.get('renames', ()),fts_rebindings=request.get('fts_rebindings',()))
        after_info = os.stat(path)
        if [after_info.st_dev, after_info.st_ino] != [file_info.st_dev, file_info.st_ino]:
            raise ValueError('SQLite registered file changed during native grammar validation')
        return preview
    finally:
        provider.client._discard_failed_session(connection)
