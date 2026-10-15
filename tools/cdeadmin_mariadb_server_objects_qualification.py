"""Qualify global registrations in an owned MariaDB fixture with inert UDFs."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
from types import SimpleNamespace

from tools.cdeadmin_mariadb_driver_gate import run
from tools.mysql_driver_gate_support import provider_access
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MARIADB_ADMINISTRATION, MARIADB_PROFILE, _create_client, _resources,
)
from pgadmin.cdeadmin.providers.mysql_family.mariadb_server_catalog import capture
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


# ScratchRobin-owned test code. These functions perform no file/network access.
FIXTURE_SOURCE = r'''
#include <mysql.h>
#include <stdlib.h>
#include <string.h>
my_bool sr_owned_integer_init(UDF_INIT *i,UDF_ARGS *a,char *m){return 0;}
void sr_owned_integer_deinit(UDF_INIT *i){}
long long sr_owned_integer(UDF_INIT *i,UDF_ARGS *a,char *n,char *e){return 42;}
my_bool sr_owned_real_init(UDF_INIT *i,UDF_ARGS *a,char *m){i->decimals=2;return 0;}
void sr_owned_real_deinit(UDF_INIT *i){}
double sr_owned_real(UDF_INIT *i,UDF_ARGS *a,char *n,char *e){return 1.25;}
my_bool sr_owned_string_init(UDF_INIT *i,UDF_ARGS *a,char *m){i->max_length=5;return 0;}
void sr_owned_string_deinit(UDF_INIT *i){}
char *sr_owned_string(UDF_INIT *i,UDF_ARGS *a,char *r,unsigned long *l,char *n,char *e){memcpy(r,"owned",5);*l=5;return r;}
my_bool sr_owned_decimal_init(UDF_INIT *i,UDF_ARGS *a,char *m){i->max_length=4;i->decimals=2;return 0;}
void sr_owned_decimal_deinit(UDF_INIT *i){}
char *sr_owned_decimal(UDF_INIT *i,UDF_ARGS *a,char *r,unsigned long *l,char *n,char *e){memcpy(r,"2.50",4);*l=4;return r;}
my_bool sr_owned_aggregate_init(UDF_INIT *i,UDF_ARGS *a,char *m){i->ptr=calloc(1,sizeof(long long));return i->ptr==NULL;}
void sr_owned_aggregate_deinit(UDF_INIT *i){free(i->ptr);}
void sr_owned_aggregate_clear(UDF_INIT *i,char *n,char *e){*(long long *)i->ptr=0;}
void sr_owned_aggregate_add(UDF_INIT *i,UDF_ARGS *a,char *n,char *e){(*(long long *)i->ptr)++;}
long long sr_owned_aggregate(UDF_INIT *i,UDF_ARGS *a,char *n,char *e){return *(long long *)i->ptr;}
'''


def qualify(route, evidence):
    import mariadb
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'engine': 'mariadb', 'version': '12.2.2',
             'checks': [], 'task_sources': {}}
    server = 'owned_server_' + secrets.token_hex(8)
    schema = 'owned_global_' + secrets.token_hex(8)
    owner = mariadb.connect(**route, autocommit=True)
    cursor = owner.cursor()
    request_route, permissions = provider_access(route)
    client = _create_client(MARIADB_PROFILE, permissions,
                           SimpleNamespace(pool_namespace='owned-global-gate'))
    made = []
    try:
        cursor.execute('CREATE DATABASE `' + schema + '`')
        cursor.execute('CREATE FUNCTION `' + schema + '`.sr_owned_integer() RETURNS INT RETURN 99')
        def execute(kind, operation, draft, name=None):
            native = {'registration_origin': 'mysql.func'} if kind == 'loadable-function' else {}
            target = {'resource_kind': kind, 'display_name': name,
                      'display_path': [name], 'native': native} if name else None
            request = {'resource_kind': kind, 'operation_id': operation,
                       'draft': draft, 'target_resource': target}
            validation = MARIADB_ADMINISTRATION.validate(request)
            assert not validation['errors'], validation
            compiled = MARIADB_ADMINISTRATION._compile(request)
            # Only SQL placeholders are retained; secret parameters never leave memory.
            proof['task_sources']['visual_admin.' + kind + '.' + operation] = [
                item['source'] for item in compiled['statements']]
            MARIADB_ADMINISTRATION.apply(client, {'provider_payload': {
                'route': {**request_route, 'database': schema}, 'compiled': compiled}})
        execute('server-link', 'create', {'name': server, 'wrapper': 'mysql',
            'host': '127.0.0.1', 'database': 'remote_only', 'username': 'owned',
            'password': "owned'\\secret", 'port': 3307})
        cursor.execute('SELECT Host,Db,Username,Port FROM mysql.servers WHERE Server_name=?', (server,))
        assert cursor.fetchone() == ('127.0.0.1', 'remote_only', 'owned', 3307)
        execute('server-link', 'alter', {'change_port': True, 'port': 3308}, server)
        cursor.execute('SELECT Host,Db,Username,Port FROM mysql.servers WHERE Server_name=?', (server,))
        assert cursor.fetchone() == ('127.0.0.1', 'remote_only', 'owned', 3308)
        execute('server-link', 'alter', {'change_password': True, 'password': ''}, server)
        proof['checks'].append('native_bound_remote_options_and_selected_alter_preserve_omitted_values')
        for suffix, result_type, aggregate, expected in (
            ('integer', 'INTEGER', False, 42), ('real', 'REAL', False, 1.25),
            ('string', 'STRING', False, 'owned'), ('decimal', 'DECIMAL', False, '2.50'),
            ('aggregate', 'INTEGER', True, 3),
        ):
            name = 'sr_owned_' + suffix
            execute('loadable-function', 'create', {'name': name,
                'return_type': result_type, 'aggregate': aggregate,
                'library': 'sr_qualification.so'})
            made.append(name)
            cursor.execute('SELECT ' + name + ('(id) FROM (SELECT 1 id UNION ALL SELECT 2 UNION ALL SELECT 3) owned' if aggregate else '()'))
            value = cursor.fetchone()[0]
            if isinstance(value, bytes): value = value.decode('ascii')
            assert str(value) == str(expected), (name, value, expected)
        resources = _resources(owner, {'route': {'database': schema}}, MARIADB_PROFILE)
        coverage = next(row for row in resources if row['resource_kind'] == 'server')['native']['catalog_coverage']
        assert coverage['state'] == 'queried' and coverage['failed_query_count'] == 0
        assert any(item['feature'] == 'binary-log' and item['state'] == 'disabled' for item in coverage['unavailable'])
        proof['checks'].append('native_disabled_binary_log_is_explicitly_unavailable_without_false_catalog_failure')
        functions = [row for row in resources if row['resource_kind'] == 'loadable-function']
        assert {row['display_name'] for row in functions} >= set(made)
        assert all(row['native']['registration_origin'] == 'mysql.func' for row in functions)
        catalog = capture(owner)
        assert {row['display_name'] for row in catalog['resources'] if row['resource_kind'] == 'loadable-function'} >= set(made)
        assert "owned'\\secret" not in json.dumps(catalog)
        proof['checks'].append('all_four_native_udf_returns_and_aggregate_observed_in_explorer_and_server_ddn')
        for name in list(made):
            execute('loadable-function', 'drop', {}, name); made.remove(name)
        # No default database permits native DROP to fall back to the stored routine.
        try:
            execute('loadable-function', 'drop', {}, 'sr_owned_integer')
        except RelationalClientError:
            pass
        else:
            raise AssertionError('Missing UDF unexpectedly dropped a stored routine')
        cursor.execute('SELECT `' + schema + '`.sr_owned_integer()'); assert cursor.fetchone() == (99,)
        proof['checks'].append('independent_global_attachment_cannot_drop_same_name_stored_routine_after_udf_removal')
        execute('server-link', 'drop', {}, server)
        cursor.execute('SELECT COUNT(*) FROM mysql.servers WHERE Server_name=?', (server,)); assert cursor.fetchone() == (0,)
        proof['complete'] = True
    finally:
        for name in made: cursor.execute('DROP FUNCTION `' + name + '`')
        cursor.execute('DROP SERVER IF EXISTS `' + server + '`')
        cursor.execute('DROP DATABASE IF EXISTS `' + schema + '`')
        cursor.close(); owner.close(); client.close()
        (evidence / 'summary.json').write_text(json.dumps(proof, indent=2))
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mariadb:12.2.2')
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    fixture = args.evidence.parent / (args.evidence.name + '-fixture')
    fixture.mkdir(exist_ok=False)
    source = fixture / 'owned.c'; source.write_text(FIXTURE_SOURCE)
    library = fixture / 'sr_qualification.so'
    flags = subprocess.check_output(['pkg-config', '--cflags', 'libmariadb'], text=True).split()
    result = subprocess.run(['gcc', '-shared', '-fPIC', '-O2', *flags, str(source), '-o', str(library)], capture_output=True)
    (fixture / 'compiler.log').write_bytes(result.stdout + result.stderr)
    result.check_returncode()
    run(args.image, args.evidence, qualify, fixture_mounts=(
        '--mount', 'type=bind,src=' + str(library.resolve()) +
        ',dst=/usr/lib/mysql/plugin/sr_qualification.so,readonly'))
