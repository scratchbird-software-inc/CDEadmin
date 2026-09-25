"""FM-FB02-007 global authentication on an owned Linux Firebird fixture.

Windows team: repeat with Win_Sspi emitted USER/GROUP/Predefined_Group
contexts. macOS team: repeat native login and UI gates with its client runtime.
Global rules modify the security database: never run against shared demos.
"""

from concurrent.futures import ThreadPoolExecutor


def exercise(driver, connection, route, password, user_password, apply, case,
             route_arguments):
    from pgadmin.cdeadmin.providers.firebird import mappings
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    kind = mappings.KINDS[1]
    user = 'CDE_MAP_USER'
    observations = {}

    def draft(**values):
        return {'name': 'CDE_MAPPING', 'using_mode': 'ANY_PLUGIN',
                'from_type': 'USER', 'from_name': user, 'to_type': 'USER',
                'to_name': 'CDE_GLOBAL_USER', **values}

    def identity(database=None):
        selected = {**route, 'user': user}
        if database:
            selected['database'] = database
        with driver.connect(password=user_password,
                            **route_arguments(selected, driver)) as other:
            with other.cursor() as cursor:
                cursor.execute('SELECT CURRENT_USER, CURRENT_ROLE '
                               'FROM RDB$DATABASE')
                return tuple(value.strip() for value in cursor.fetchone())

    connection.execute_immediate('CREATE ROLE CDE_GLOBAL_ROLE')
    connection.commit()

    for mode in mappings.MODES:
        for target in ('USER', 'ROLE'):
            for any_source in (False, True):
                def check(mode=mode, target=target, any_source=any_source):
                    value = draft(
                        using_mode=mode,
                        plugin='Srp256' if mode == 'PLUGIN' else '',
                        from_any=any_source, to_type=target,
                        to_name=('CDE_GLOBAL_USER' if target == 'USER'
                                 else 'CDE_GLOBAL_ROLE'))
                    apply(kind, 'create', value)
                    connection.commit()
                    expected = [user, 'NONE']
                    if mode in ('PLUGIN', 'ANY_PLUGIN', 'ANY'):
                        index = 0 if target == 'USER' else 1
                        expected[index] = value['to_name']
                    assert identity() == tuple(expected)
                case(f'global-effective:{mode}:{target}:any={any_source}',
                     check)

    def visibility():
        destination = '/var/lib/firebird/data/global_destination.fdb'
        with driver.create_database(password=password, **route_arguments(
                {**route, 'database': destination}, driver)):
            pass
        apply(kind, 'create', draft())
        connection.rollback()
        assert identity()[0] == user
        apply(kind, 'create', draft())
        connection.commit()
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(lambda _: identity(destination), range(8)))
        assert values == [('CDE_GLOBAL_USER', 'NONE')] * 8
        assert identity()[0] == 'CDE_GLOBAL_USER'
        apply(kind, 'alter', draft(to_name='CDE_GLOBAL_CHANGED'))
        connection.rollback()
        assert identity(destination)[0] == 'CDE_GLOBAL_USER'
        apply(kind, 'alter', draft(to_name='CDE_GLOBAL_CHANGED'))
        connection.commit()
        assert identity(destination)[0] == 'CDE_GLOBAL_CHANGED'
        apply(kind, 'drop', {'confirmation': 'CDE_MAPPING'})
        connection.rollback()
        assert identity()[0] == 'CDE_GLOBAL_CHANGED'
        apply(kind, 'drop', {'confirmation': 'CDE_MAPPING'})
        connection.commit()
        assert identity(destination)[0] == user
    case('global-two-databases-commit-rollback-cache-invalidation', visibility)

    def conflict():
        apply(kind, 'create', draft())
        connection.commit()
        try:
            apply(kind, 'create', draft(name='CDE_GLOBAL_SECOND'))
            connection.commit()
            assert identity()[0] == 'CDE_GLOBAL_USER'
            apply(kind, 'alter', draft(to_name='CDE_CONFLICT'),
                  target='CDE_GLOBAL_SECOND')
            connection.commit()
            try:
                identity()
            except driver.DatabaseError as error:
                assert 335545083 in error.gds_codes
            else:
                raise AssertionError('Ambiguous global rules allowed login')
        finally:
            apply(kind, 'drop', {'confirmation': 'CDE_GLOBAL_SECOND'},
                  target='CDE_GLOBAL_SECOND')
            connection.commit()
    case('global-equal-targets-and-conflicting-targets', conflict)

    def local_precedence():
        apply(kind, 'create', draft())
        apply(mappings.KINDS[0], 'create', draft(to_name='CDE_LOCAL_USER'))
        connection.commit()
        assert identity()[0] == 'CDE_LOCAL_USER'
        apply(mappings.KINDS[0], 'drop', {'confirmation': 'CDE_MAPPING'})
        connection.commit()
        assert identity()[0] == 'CDE_GLOBAL_USER'
    case('global-local-precedence-and-fallback', local_precedence)

    def concurrent_changes():
        names = ['CDE_GLOBAL_PARALLEL_' + str(index) for index in range(4)]

        def create(name):
            with driver.connect(password=password,
                                **route_arguments(route, driver)) as other:
                apply(kind, 'create', draft(name=name, from_name='UNMATCHED'),
                      conn=other)
                other.commit()

        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(create, names))
            with connection.cursor() as cursor:
                found = {row[0] for row in mappings.catalog_rows(cursor, True)}
            connection.commit()
            assert set(names).issubset(found)
        finally:
            with connection.cursor() as cursor:
                found = {row[0] for row in mappings.catalog_rows(cursor, True)}
            connection.commit()
            for name in names:
                if name in found:
                    apply(kind, 'drop', {'confirmation': name}, target=name)
                    connection.commit()
    case('global-concurrent-independent-security-database-writes',
         concurrent_changes)

    def authority_boundary():
        # A local CHANGE_MAPPING_RULES grant is not a grant in the security
        # database. Explicitly test that scope boundary, not a guessed right.
        connection.execute_immediate(
            'CREATE ROLE CDE_GLOBAL_AUTH SET SYSTEM PRIVILEGES '
            'TO CHANGE_MAPPING_RULES')
        connection.execute_immediate('GRANT CDE_GLOBAL_AUTH TO CDE_MAP_USER')
        connection.commit()
        try:
            with driver.connect(password=user_password, **route_arguments({
                    **route, 'user': user, 'role': 'CDE_GLOBAL_AUTH'},
                    driver)) as other:
                try:
                    apply(kind, 'create', draft(from_name='UNMATCHED'),
                          conn=other)
                    other.commit()
                except RelationalClientError:
                    if other.main_transaction.is_active():
                        other.rollback()
                else:
                    raise AssertionError('Local-only grant changed global '
                                         'security-database mappings')
        finally:
            connection.execute_immediate(
                'REVOKE CDE_GLOBAL_AUTH FROM CDE_MAP_USER')
            connection.execute_immediate('DROP ROLE CDE_GLOBAL_AUTH')
            connection.commit()
    case('global-local-only-authority-does-not-escalate', authority_boundary)

    def security_admin():
        connection.execute_immediate('GRANT RDB$ADMIN TO CDE_MAP_USER')
        connection.execute_immediate(
            'ALTER USER CDE_MAP_USER GRANT ADMIN ROLE')
        connection.commit()
        try:
            with driver.connect(password=user_password, **route_arguments({
                    **route, 'user': user, 'role': 'RDB$ADMIN'},
                    driver)) as db:
                apply(kind, 'create', draft(from_name='UNMATCHED'), conn=db)
                db.commit()
                apply(kind, 'drop', {'confirmation': 'CDE_MAPPING'}, conn=db)
                db.commit()
        finally:
            connection.execute_immediate(
                'ALTER USER CDE_MAP_USER REVOKE ADMIN ROLE')
            connection.execute_immediate('REVOKE RDB$ADMIN FROM CDE_MAP_USER')
            connection.commit()
        with driver.connect(password=user_password, **route_arguments({
                **route, 'user': user, 'role': 'RDB$ADMIN'}, driver)) as db:
            try:
                apply(kind, 'create', draft(from_name='UNMATCHED'), conn=db)
            except RelationalClientError:
                if db.main_transaction.is_active():
                    db.rollback()
            else:
                db.rollback()
                raise AssertionError('Revoked administrator retained rights')
    case('global-security-admin-grant-revoke-fresh-attachments',
         security_admin)

    def chained_mapping():
        destination = '/var/lib/firebird/data/global_chain.fdb'
        with driver.create_database(password=password, **route_arguments(
                {**route, 'database': destination}, driver)):
            pass
        apply(mappings.KINDS[0], 'create', draft(to_name='CDE_INTERMEDIATE'))
        apply(kind, 'create', draft(
            using_mode='MAPPING', source_database=route['database'],
            from_name='CDE_INTERMEDIATE', to_name='CDE_GLOBAL_CHAINED'))
        connection.commit()
        with driver.connect(password=user_password, **route_arguments({
                **route, 'user': user}, driver)) as db:
            with db.cursor() as cursor:
                cursor.execute(
                    'EXECUTE BLOCK RETURNS (WHO VARCHAR(63)) AS BEGIN '
                    "EXECUTE STATEMENT 'SELECT CURRENT_USER "
                    "FROM RDB$DATABASE' ON EXTERNAL DATA SOURCE "
                    + mappings.literal(destination)
                    + ' INTO :WHO; SUSPEND; END')
                observed = cursor.fetchone()[0].strip()
                # Mapping::setInternalFlags/mapUser marks the security DB
                # seen in the forwarded auth block; it must not be remapped.
                observations['same_security_eds_identity'] = observed
                assert observed == user, observed
    case('global-same-security-eds-context-is-not-remapped', chained_mapping)

    for label, changes in (
            ('unconfigured-plugin', {'using_mode': 'PLUGIN',
                                     'plugin': 'CDE_NoSuchPlugin'}),
            ('unemitted-group', {'from_type': 'GROUP'}),
            ('unmatched-database', {'source_database': 'not_this_security'}),
            ('preserve-source-name', {'to_name': ''})):
        def check(changes=changes):
            apply(kind, 'create', draft(**changes))
            connection.commit()
            assert identity() == (user, 'NONE')
        case('global-effective:' + label, check)

    def comments():
        apply(kind, 'create', draft(from_name='UNMATCHED'))
        connection.commit()

        def observe():
            with connection.cursor() as cursor:
                row = next(row for row in mappings.catalog_rows(cursor, True)
                           if row[0] == 'CDE_MAPPING')
            connection.commit()
            return row

        for text in ('', "  O'Connor\n\t  ", 'A' * 32766):
            apply(kind, 'comment', {'description': text})
            connection.commit()
            assert observe()[8] == (text or None)
        before = observe()
        for text in ('A' * 32767, 'A' * 40000, 'é', '映射', '\x00'):
            try:
                apply(kind, 'comment', {'description': text})
            except RelationalClientError:
                if connection.main_transaction.is_active():
                    connection.rollback()
            else:
                raise AssertionError('Unsafe global comment accepted')
            assert observe() == before
        # Reproduce native corruption independently of our write guard.
        # Do not claim verified storage or automatically repair the result.
        with connection.cursor() as cursor:
            cursor.execute('COMMENT ON GLOBAL MAPPING CDE_MAPPING IS '
                           + mappings.literal('é'))
        connection.commit()
        row = observe()
        observations['unicode_projection'] = {
            'requested': 'é', 'observed': row[8],
            'storage_independently_verified': False}
        assert row[8] != 'é', repr(row[8])
        metadata = mappings.metadata(kind, row)
        assert metadata['description_storage_verified'] is False
        assert metadata['recreation_metadata_verified'] is False
    case('global-comment-exact-boundaries-native-unicode-loss', comments)
    connection.execute_immediate('DROP ROLE CDE_GLOBAL_ROLE')
    connection.commit()
    return observations
