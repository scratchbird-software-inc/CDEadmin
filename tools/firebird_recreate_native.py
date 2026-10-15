"""Qualify separate native drop/create receipts on an owned fixture path."""
def qualify(client, route, password, path=None, *, on_created=None):
    import firebird.driver as native
    from tools.cdeadmin_firebird_admin_mapping_gate import _route_arguments
    from pgadmin.cdeadmin.providers.firebird.provider import ADMINISTRATION
    from pathlib import PurePosixPath, PureWindowsPath
    path = path or '/qualification/recreate.fdb'
    if route.get('attachment_mode') == 'embedded':
        from pgadmin.cdeadmin.providers.firebird.embedded_provider import ADMINISTRATION
    path_type = PureWindowsPath if PureWindowsPath(path).drive else PurePosixPath
    server = {**route, 'database_create_root': str(path_type(path).parent)}
    server.pop('database', None)
    create = {'_provider_route': server, 'resource_kind': 'database',
              'operation_id': 'create', 'draft': {'database_path': path}}
    first = ADMINISTRATION.apply(client, ADMINISTRATION.plan(create))
    assert first['driver_observation']['driver_returned'], first
    db_route = {**server, 'database': path}
    attachment = native.connect(password=password, **_route_arguments(db_route, native))
    with attachment.cursor() as cursor:
        cursor.execute('CREATE TABLE PREVIOUS_CONTENT (ID INTEGER)')
    attachment.commit()
    attachment.close()
    drop = {'_provider_route': db_route, 'resource_kind': 'database',
            'operation_id': 'drop', 'draft': {'confirmation': path},
            'target_resource': {'resource_kind': 'database', 'display_name': path,
                'resource_id': 'owned-recreate', 'extensions': {'cdeadmin': {
                    'database_target_id': 'owned-recreate', 'native_name': path}}}}
    removed = ADMINISTRATION.apply(client, ADMINISTRATION.plan(drop))
    assert removed['driver_observation']['driver_returned'], removed
    assert removed['dropped_endpoint_database_target']['target_id'] == 'owned-recreate'
    try:
        attachment = native.connect(password=password, **_route_arguments(db_route, native))
    except native.Error:
        pass
    else:
        attachment.close()
        raise AssertionError('Database remains after native drop')
    second = ADMINISTRATION.apply(client, ADMINISTRATION.plan(create))
    assert second['driver_observation']['driver_returned'], second
    registration = on_created(path) if on_created else None
    attachment = native.connect(password=password, **_route_arguments(db_route, native))
    with attachment.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM RDB$RELATIONS WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0")
        assert cursor.fetchone()[0] == 0
    attachment.rollback()
    attachment.close()
    # Repeating creation must refuse overwrite and leave the new database intact.
    try:
        ADMINISTRATION.apply(client, ADMINISTRATION.plan(create))
    except Exception:
        pass
    else:
        raise AssertionError('Duplicate creation overwrote an existing database')
    final = ADMINISTRATION.apply(client, ADMINISTRATION.plan(drop))
    assert final['driver_observation']['driver_returned']
    return {'passed': True, 'replacement_registration': registration,
            'drop_verified_absent': True, 'new_database_empty': True,
            'server_scope_creation': True, 'overwrite_refused': True, 'fixture_dropped': True}
