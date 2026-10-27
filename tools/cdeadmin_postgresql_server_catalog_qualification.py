"""Independent PostgreSQL shared-catalog inventory under two native principals."""
from collections import Counter
import json
import secrets
import re

# Release-native inventories are independent of the adapter's section queries.
RAW = {
    'databases': 'SELECT oid::text FROM pg_catalog.pg_database',
    'roles': 'SELECT oid::text FROM pg_catalog.pg_roles',
    'memberships': 'SELECT oid::text FROM pg_catalog.pg_auth_members',
    'role-authentication-state': 'SELECT oid::text FROM pg_catalog.pg_authid',
    'tablespaces': 'SELECT oid::text FROM pg_catalog.pg_tablespace',
    'replication-slots': 'SELECT slot_name FROM pg_catalog.pg_replication_slots',
    'replication-origins': 'SELECT roident::text FROM pg_catalog.pg_replication_origin',
    'database-role-settings': "SELECT setdatabase::text || ':' || setrole::text FROM pg_catalog.pg_db_role_setting",
    'configuration': 'SELECT name FROM pg_catalog.pg_settings',
    'configuration-files': 'SELECT jsonb_build_array(sourcefile,sourceline,seqno)::text FROM pg_catalog.pg_file_settings',
    'authentication-rules': 'SELECT jsonb_build_array(file_name,line_number,rule_number)::text FROM pg_catalog.pg_hba_file_rules',
    'identity-mappings': 'SELECT jsonb_build_array(file_name,line_number,map_number)::text FROM pg_catalog.pg_ident_file_mappings',
    'available-extensions': 'SELECT name FROM pg_catalog.pg_available_extensions',
    'extension-versions': 'SELECT jsonb_build_array(name,version)::text FROM pg_catalog.pg_available_extension_versions',
    'prepared-transactions': 'SELECT gid FROM pg_catalog.pg_prepared_xacts',
    'replication-origin-state': 'SELECT local_id::text FROM pg_catalog.pg_replication_origin_status',
}


def reconcile(connection, inventory):
    import psycopg
    checks, failures = [], []
    observations = {item['section']: item for item in inventory['observations']}
    for section, statement in RAW.items():
        try:
            raw = Counter(str(row[0]) for row in connection.execute(statement))
        except psycopg.errors.InsufficientPrivilege:
            denied = observations.get(section, {}).get('available') is False
            checks.append({'section': section, 'native_denied': True, 'denial_recorded': denied})
            if not denied:
                failures.append({'section': section, 'missing_native_denial': True})
            continue
        actual = Counter(str(item['native']['native_identity']) for item in inventory['resources']
            if item['display_path'][1] == section)
        checks.append({'section': section, 'native_count': sum(raw.values()),
            'provider_count': sum(actual.values()), 'equal': raw == actual})
        if raw != actual:
            failures.append({'section': section, 'missing': list((raw-actual).elements()),
                'extra': list((actual-raw).elements())})
    return {'checks': checks, 'failures': failures, 'complete': not failures}


def qualify(provider, route, password, server, user, receipt, evidence):
    import psycopg
    from psycopg import sql
    from psycopg.rows import tuple_row
    from types import SimpleNamespace
    from pgadmin.model import db, Server
    from pgadmin.cdeadmin.security import SecretLease
    from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProvider
    from pgadmin.cdeadmin.providers.postgresql.server_catalog import inventory, export_inventory
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    owner = psycopg.connect(host=route['host'], port=route['port'], user=route['user'], password=password,
        dbname=route['database'], autocommit=True, row_factory=tuple_row, **route.get('connection_params', {}))
    role, role_password, marker = 'sr_catalog_' + secrets.token_hex(8), secrets.token_urlsafe(32), 'secret-canary-' + secrets.token_hex(8)
    made = False
    slot_created = False
    limited_provider, limited_server, limited = None, None, None
    before = set(provider._sessions)
    try:
        owner.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(role_password)))
        made = True
        owner.execute(sql.SQL('ALTER ROLE {} SET scratchrobin.private_token={}').format(sql.Identifier(role), sql.Literal(marker)))
        owner.execute('SELECT * FROM pg_create_physical_replication_slot(%s,false,false)', (role + '_slot',)).fetchone()
        slot_created = True
        owner.execute('SELECT * FROM pg_create_physical_replication_slot(%s,false,true)', (role + '_temp',)).fetchone()
        selected = {'server_id': server.id, 'owner_id': user.id,
            'principal_reference': 'worker:proof', 'credential_reference_id': 'proof-password'}
        privileged = inventory(provider, selected)
        assert all(item['available'] for item in privileged['observations']), [
            item for item in privileged['observations'] if not item['available']]
        assert set(provider._sessions) == before
        assert marker not in json.dumps(privileged)
        exported = json.dumps(privileged)
        configuration_canaries = set()
        connection_setting = owner.execute("SELECT setting FROM pg_settings WHERE name='primary_conninfo'").fetchone()[0]
        for secret in re.findall(r'password=(secret-canary-[A-Za-z0-9_-]+)', connection_setting or ''):
            configuration_canaries.add(secret)
            assert secret not in exported
        for options, error in owner.execute('SELECT options,error FROM pg_hba_file_rules'):
            for value in [*([options] if isinstance(options,str) else options or []), error or '']:
                for secret in re.findall(r'ldapbindpasswd=(secret-canary-[A-Za-z0-9_-]+)', value):
                    configuration_canaries.add(secret)
                    assert secret not in exported
        raw_privileged = reconcile(owner, privileged)
        assert raw_privileged['complete'], raw_privileged['failures']
        slots = {item['display_name']:item['native']['catalog_row'] for item in privileged['resources'] if item['resource_kind'] == 'replication-slot'}
        assert slots[role + '_temp']['temporary'] is True and slots[role + '_slot']['temporary'] is False
        work_mem = next(item for item in privileged['resources'] if item['resource_kind'] == 'system-variable' and item['display_name'] == 'work_mem')
        assert work_mem['native']['catalog_row']['setting'] == owner.execute("SELECT setting FROM pg_settings WHERE name='work_mem'").fetchone()[0]
        for resource in privileged['resources']:
            native = resource['native']['catalog_row']
            if resource['resource_kind'] == 'system-variable' and native['vartype'] == 'string':
                assert native['values_redacted'] and all(native[key] is None for key in ('setting','boot_val','reset_val'))
            if resource['resource_kind'] == 'session':
                assert native['query_redacted'] and 'query' not in native
        document = export_inventory(privileged, provider.context.endpoint_id, server.id, include_system=True)
        parsed = read_catalog(json.dumps(document['snapshot']), engine='postgresql')
        assert len(parsed['rows']) == len(privileged['resources']) + 1
        assert marker not in json.dumps(document)
        limited_server = Server(user_id=user.id, servergroup_id=server.servergroup_id, name='Owned server catalog reader',
            host=route['host'], port=route['port'], username=role, maintenance_db=route['database'],
            connection_params=route.get('connection_params', {}), save_password=0)
        db.session.add(limited_server); db.session.commit()
        def acquire(reference, principal, purpose, kind):
            assert (reference,principal,purpose,kind) == ('catalog-reader-password','worker:server-catalog','connect','database_password')
            return SecretLease(role_password.encode('utf8'))
        limited_provider = PostgreSQLProvider(SimpleNamespace(endpoint_id='owned-restricted-catalog',
            cache_namespace='owned-restricted-catalog', session_namespace='owned-restricted-catalog'),
            SimpleNamespace(require=lambda *_: None, acquire_secret=acquire), provider._driver)
        limited = psycopg.connect(host=route['host'], port=route['port'], user=role, password=role_password,
            dbname=route['database'], autocommit=True, row_factory=tuple_row, **route.get('connection_params', {}))
        restricted = inventory(limited_provider, {'server_id': limited_server.id, 'owner_id': user.id,
            'principal_reference': 'worker:server-catalog', 'credential_reference_id': 'catalog-reader-password'})
        assert not limited_provider._sessions
        raw_restricted = reconcile(limited, restricted)
        assert raw_restricted['complete'], raw_restricted['failures']
        assert restricted['coverage']['state'] == 'partial'
        assert restricted['visibility']['principal'] == role and restricted['visibility']['native_field_filters_apply'] is True
        assert {'configuration-files','authentication-rules','identity-mappings','role-authentication-state'} <= set(restricted['coverage']['unavailable_sections'])
        assert marker not in json.dumps(restricted)
        (evidence / 'server-catalog-reconciliation.json').write_text(json.dumps({
            'privileged':raw_privileged,'restricted':raw_restricted,
            'resource_counts':{'privileged':len(privileged['resources']),'restricted':len(restricted['resources'])},
            'denied_sections':restricted['coverage']['unavailable_sections'],
            'configuration_secret_canaries_checked':len(configuration_canaries),
            'native_secret_values_redacted':True,'server_only_ddn_roundtrip':True},indent=2)+'\n')
        receipt['checks'].append('native-server-catalog-independent-shared-inventory-privileged-restricted-denial-secret-redaction-temporary-persistent-slots-and-server-only-ddn-roundtrip')
    finally:
        if limited is not None:limited.close()
        if limited_provider is not None:limited_provider.close()
        if limited_server is not None:
            db.session.delete(limited_server); db.session.commit()
        if slot_created:owner.execute('SELECT pg_drop_replication_slot(%s)', (role + '_slot',))
        if made:owner.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
        owner.close()
