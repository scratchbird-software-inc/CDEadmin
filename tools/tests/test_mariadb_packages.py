"""Separate MariaDB declarations/bodies, explicit mode and native form admission."""
import pytest
from pgadmin.cdeadmin.providers.mariadb_packages import OPERATIONS, compile_operation
from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_ADMINISTRATION, MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from pgadmin.cdeadmin.sdk.relational import RelationalClientError

TARGET = {'resource_kind': 'package', 'display_path': ['demo`db', 'p`kg'], 'native': {
    'package_specification': {'show_create': [{'sql_mode': 'ORACLE,ANSI_QUOTES'}]},
    'package_body': {'show_create': [{'sql_mode': 'ORACLE,ANSI_QUOTES'}]}}}
SAFE = MARIADB_ADMINISTRATION._safe_definition


def test_native_body_replacement_preserves_observed_mode_and_drop_preserves_specification():
    statements = compile_operation('replace_body', {'definition': 'AS PROCEDURE p AS BEGIN NULL; END; END'}, TARGET, SAFE)
    assert statements[0] == {'source': 'SET SESSION sql_mode=%s', 'parameters': ('ORACLE,ANSI_QUOTES',)}
    assert statements[1]['source'].startswith('CREATE OR REPLACE PACKAGE BODY `demo``db`.`p``kg` AS')
    assert compile_operation('drop_body', {}, TARGET, SAFE) == [{'source': 'DROP PACKAGE BODY `demo``db`.`p``kg`', 'parameters': ()}]
    assert compile_operation('create_specification', {'database': 'demo', 'name': 'pkg', 'definition': 'PROCEDURE hi(); END'}, None, SAFE)[0]['source'] == 'CREATE PACKAGE `demo`.`pkg` PROCEDURE hi(); END'


def test_missing_mode_wrong_kind_and_unknown_fields_refuse_before_dispatch():
    for operation, draft, target in [('create_body', {'definition': 'PROCEDURE hi() BEGIN SELECT 1; END; END'}, {**TARGET, 'native': {}}),
        ('drop_body', {'cascade': True}, TARGET), ('drop_body', {}, {**TARGET, 'resource_kind': 'table'}),
        ('replace_body', {'definition': 'CREATE DATABASE other', 'sql_mode': 'oracle'}, TARGET),
        ('create_specification', {'database': 'demo', 'name': 'pkg', 'definition': 'x', 'sql_mode': 'guessed'}, None)]:
        with pytest.raises(RelationalClientError):compile_operation(operation, draft, target, SAFE)


def test_native_catalog_forms_validate_compile_only_for_mariadb():
    catalog = MARIADB_ADMINISTRATION.catalog(catalog_for_engine('mariadb'))
    package = next(row for row in catalog['objects'] if row['resource_kind'] == 'package')
    assert OPERATIONS <= {row['operation_id'] for row in package['operations']}
    assert len(package['operations']) == len({row['operation_id'] for row in package['operations']})
    for operation in OPERATIONS:
        assert MARIADB_ADMINISTRATION.supports('package', operation)
        assert not MYSQL_ADMINISTRATION.supports('package', operation)
    request = {'resource_kind': 'package', 'operation_id': 'replace_body', 'target_resource': TARGET,
        'draft': {'definition': 'AS PROCEDURE p AS BEGIN NULL; END; END', 'confirmation': 'p`kg'}}
    assert not MARIADB_ADMINISTRATION.validate(request)['errors']
    assert MARIADB_ADMINISTRATION._compile(request)['statements'][1]['source'].startswith('CREATE OR REPLACE PACKAGE BODY')
