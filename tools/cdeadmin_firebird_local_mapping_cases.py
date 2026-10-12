"""FM-FB02-006 effective local mapping checks on an owned Linux fixture.

Windows must additionally exercise Win_Sspi USER/GROUP/Predefined_Group
contexts; macOS must repeat native plugins and browser interaction. An unknown
plugin/type stored as DDL is not represented as a successful authentication.
"""

from concurrent.futures import ThreadPoolExecutor


def exercise(driver, connection, route, password, user_password, apply, case,
             route_arguments):
    from pgadmin.cdeadmin.providers.firebird import mappings
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    kind = mappings.KINDS[0]
    user = 'CDE_MAP_USER'

    def sql(statement):
        with connection.cursor() as cursor:
            cursor.execute(statement)
        connection.commit()

    def attach(username=user, role=None):
        selected = {**route, 'user': username}
        if role:
            selected['role'] = role
        return driver.connect(password=(password if username == 'SYSDBA'
                                        else user_password),
                              **route_arguments(selected, driver))

    def identity():
        with attach() as other:
            with other.cursor() as cursor:
                cursor.execute('SELECT CURRENT_USER, CURRENT_ROLE '
                               'FROM RDB$DATABASE')
                return tuple(value.strip() for value in cursor.fetchone())

    def draft(**values):
        return {'name': 'CDE_MAPPING', 'using_mode': 'ANY_PLUGIN',
                'from_type': 'USER', 'from_name': user, 'to_type': 'USER',
                'to_name': 'CDE_MAPPED_IDENTITY', **values}

    sql('CREATE ROLE CDE_MAPPED_ROLE')
    for mode in mappings.MODES:
        for target in ('USER', 'ROLE'):
            for any_source in (False, True):
                def check(mode=mode, target=target, any_source=any_source):
                    value = draft(
                        using_mode=mode,
                        plugin='Srp256' if mode == 'PLUGIN' else '',
                        from_any=any_source, to_type=target,
                        to_name=('CDE_MAPPED_IDENTITY' if target == 'USER'
                                 else 'CDE_MAPPED_ROLE'))
                    apply(kind, 'create', value)
                    connection.commit()
                    expected = [user, 'NONE']
                    # Password auth has a security database, not a serverwide
                    # or previous-mapping source context.
                    if mode in ('PLUGIN', 'ANY_PLUGIN', 'ANY'):
                        index = 0 if target == 'USER' else 1
                        expected[index] = value['to_name']
                    assert identity() == tuple(expected)
                case(f'local-effective:{mode}:{target}:any={any_source}',
                     check)

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
        case('local-effective:' + label, check)

    def commit_visibility():
        apply(kind, 'create', draft())
        connection.rollback()
        assert identity() == (user, 'NONE')
        apply(kind, 'create', draft())
        connection.commit()
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert list(pool.map(lambda _: identity(), range(8))) == [
                ('CDE_MAPPED_IDENTITY', 'NONE')] * 8
        apply(kind, 'alter', draft(to_name='CDE_CHANGED_IDENTITY'))
        connection.rollback()
        assert identity()[0] == 'CDE_MAPPED_IDENTITY'
        apply(kind, 'alter', draft(to_name='CDE_CHANGED_IDENTITY'))
        connection.commit()
        assert identity()[0] == 'CDE_CHANGED_IDENTITY'
        apply(kind, 'drop', {'confirmation': 'CDE_MAPPING'})
        connection.commit()
        assert identity() == (user, 'NONE')
    case('local-commit-rollback-fresh-concurrent-attachments',
         commit_visibility)

    def authority():
        sql('CREATE ROLE CDE_MAP_AUTH SET SYSTEM PRIVILEGES '
            'TO CHANGE_MAPPING_RULES')
        value = draft(from_name='UNMATCHED')

        def change(allowed, role=None):
            with attach(role=role) as other:
                try:
                    apply(kind, 'create', value, conn=other)
                except RelationalClientError:
                    assert not allowed
                    other.rollback()
                else:
                    assert allowed
                    other.commit()
            if allowed:
                apply(kind, 'drop', {'confirmation': 'CDE_MAPPING'})
                connection.commit()

        change(False)
        sql('GRANT CDE_MAP_AUTH TO USER CDE_MAP_USER')
        change(True, 'CDE_MAP_AUTH')
        sql('REVOKE CDE_MAP_AUTH FROM USER CDE_MAP_USER')
        change(False, 'CDE_MAP_AUTH')
        sql('DROP ROLE CDE_MAP_AUTH')
    case('local-change-mapping-rules-grant-revoke', authority)

    def precedence(conflict):
        apply(kind, 'create', draft())
        connection.commit()
        second = draft(name='CDE_SECOND_MAPPING',
                       to_name=('CDE_CONFLICT' if conflict
                                else 'CDE_MAPPED_IDENTITY'))
        try:
            apply(kind, 'create', second)
            connection.commit()
            if conflict:
                try:
                    identity()
                except driver.DatabaseError as error:
                    # Native mapping ambiguity, not a client-side guessed
                    # ordering. Record exact GDS codes in dedicated evidence.
                    assert 335545083 in error.gds_codes  # isc_map_multi
                else:
                    raise AssertionError('conflicting mappings authenticated')
            else:
                assert identity()[0] == 'CDE_MAPPED_IDENTITY'
        finally:
            sql('DROP MAPPING CDE_SECOND_MAPPING')
    case('local-equal-destinations-allowed', lambda: precedence(False))
    case('local-conflicting-destinations-denied', lambda: precedence(True))

    def exact_database():
        apply(kind, 'create', draft(
            using_mode='PLUGIN', plugin='Srp256',
            source_database='/opt/firebird/security5.fdb'))
        connection.commit()
        try:
            apply(kind, 'create', draft(
                name='CDE_SECOND_MAPPING', to_name='CDE_WILDCARD'))
            connection.commit()
            assert identity()[0] == 'CDE_MAPPED_IDENTITY'
        finally:
            sql('DROP MAPPING CDE_SECOND_MAPPING')
    case('local-exact-source-precedes-wildcard', exact_database)

    def chained_mapping():
        destination = '/var/lib/firebird/data/mapping_destination.fdb'
        with driver.create_database(password=password, **route_arguments(
                {**route, 'database': destination}, driver)) as target:
            apply(kind, 'create', draft(to_name='CDE_INTERMEDIATE'))
            connection.commit()
            apply(kind, 'create', draft(
                using_mode='MAPPING', source_database=route['database'],
                from_name='CDE_INTERMEDIATE', to_name='CDE_CHAINED'),
                conn=target)
            target.commit()
            with attach() as other:
                with other.cursor() as cursor:
                    cursor.execute(
                        'EXECUTE BLOCK RETURNS (WHO VARCHAR(63)) AS BEGIN '
                        "EXECUTE STATEMENT 'SELECT CURRENT_USER "
                        "FROM RDB$DATABASE' ON EXTERNAL DATA SOURCE "
                        + mappings.literal(destination)
                        + ' INTO :WHO; SUSPEND; END')
                    assert cursor.fetchone()[0].strip() == 'CDE_CHAINED'
    case('local-mapping-source-external-data-source-chain', chained_mapping)

    def long_comment():
        apply(kind, 'create', draft(from_name='UNMATCHED'))
        connection.commit()
        try:
            apply(kind, 'comment', {'description': "映射 é\n" * 8000})
        except RelationalClientError as error:
            assert '336397331' in str(error)  # native string byte limit
            connection.rollback()
        else:
            raise AssertionError('oversize SQL literal was accepted')
        # Above the global 32767-byte projection limit, but within the native
        # SQL literal's byte/character bounds for this UTF8 connection.
        comment = '映射' * 6000
        apply(kind, 'comment', {'description': comment})
        connection.commit()
        with connection.cursor() as cursor:
            row = next(row for row in mappings.catalog_rows(cursor)
                       if row[0] == 'CDE_MAPPING')
        connection.commit()
        assert row[8] == comment
        assert mappings.metadata(kind, row)['description'] == comment
        assert comment in mappings.metadata(kind, row)['ddl']
    case('local-long-unicode-comment-roundtrip', long_comment)

    def concurrent_changes():
        names = [f'CDE_PARALLEL_{index}' for index in range(4)]

        def create(name):
            with attach(username='SYSDBA') as other:
                apply(kind, 'create', draft(name=name, from_name='UNMATCHED'),
                      conn=other)
                other.commit()

        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(create, names))
            with connection.cursor() as cursor:
                observed = {row[0] for row in mappings.catalog_rows(cursor)}
            connection.commit()
            assert set(names).issubset(observed)
        finally:
            with connection.cursor() as cursor:
                observed = {row[0] for row in mappings.catalog_rows(cursor)}
            connection.commit()
            for name in names:
                if name in observed:
                    sql('DROP MAPPING ' + mappings.identifier(name))
    case('local-concurrent-independent-mapping-changes', concurrent_changes)

    def conflicting_change():
        apply(kind, 'create', draft(from_name='UNMATCHED'))
        connection.commit()
        apply(kind, 'alter', draft(from_name='UNMATCHED', to_name='FIRST'))
        try:
            with attach(username='SYSDBA') as other:
                other.begin(driver.tpb(driver.Isolation.SNAPSHOT,
                                       lock_timeout=0))
                try:
                    apply(kind, 'alter', draft(
                        from_name='UNMATCHED', to_name='SECOND'), conn=other)
                except RelationalClientError as error:
                    assert any(code in str(error) for code in (
                        '335544345', '335544336', '335544451'))
                    other.rollback()
                else:
                    raise AssertionError('concurrent conflicting DDL accepted')
        finally:
            connection.rollback()
        with connection.cursor() as cursor:
            row = next(row for row in mappings.catalog_rows(cursor)
                       if row[0] == 'CDE_MAPPING')
        connection.commit()
        assert row[7] == 'CDE_MAPPED_IDENTITY'
    case('local-conflicting-alter-nowait-and-rollback', conflicting_change)
    sql('DROP ROLE CDE_MAPPED_ROLE')
