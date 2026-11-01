"""Dolt administration planning added for MySQL-wire parity (2026-10-29)."""
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.dolt.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

DATABASE_TARGET = {
    'resource_id': 'database:d1', 'resource_kind': 'database',
    'display_name': 'd1', 'display_path': ['d1'],
    'authority_path': ['database', 'd1']}


def request(kind, operation, draft, target=None):
    return {'resource_kind': kind, 'operation_id': operation,
            'target_resource': target, '_provider_route': {'database': 'd1'},
            'draft': draft}


def plan(*args, **kwargs):
    return [statement['source'] for statement in ADMINISTRATION.plan(
        request(*args, **kwargs))['command_preview']['statements']]


TRIGGER = {'name': 't6', 'parent': 'd1', 'table': 't', 'timing': 'BEFORE',
           'events': ['INSERT'], 'body': 'SET NEW.v = 3'}


def test_trigger_ordering():
    assert plan('trigger', 'create', {
        **TRIGGER, 'order': 'FOLLOWS', 'other_trigger': 't5'}) == [
        'CREATE TRIGGER `d1`.`t6` BEFORE INSERT ON `t` FOR EACH ROW '
        'FOLLOWS `t5` SET NEW.v = 3']
    with pytest.raises(RelationalClientError, match='needs the trigger'):
        plan('trigger', 'create', {**TRIGGER, 'order': 'PRECEDES'})
    with pytest.raises(RelationalClientError, match='select FOLLOWS'):
        plan('trigger', 'create', {**TRIGGER, 'other_trigger': 't5'})


def test_database_character_set_and_collation():
    assert plan('database', 'create', {
        'name': 'd1', 'character_set': 'utf8mb4',
        'collation': 'utf8mb4_bin'}) == [
        'CREATE DATABASE `d1` DEFAULT CHARACTER SET `utf8mb4` '
        'DEFAULT COLLATE `utf8mb4_bin`']
    assert plan('database', 'alter', {'collation': 'utf8mb4_bin'},
                DATABASE_TARGET) == [
        'ALTER DATABASE `d1` DEFAULT COLLATE `utf8mb4_bin`']
    # MySQL's DEFAULT ENCRYPTION is not claimed for Dolt.
    assert ADMINISTRATION.validate(request(
        'database', 'create', {'name': 'd2', 'encryption': 'Y'}))['errors']


@pytest.mark.parametrize('object_type', ['FUNCTION', 'SEQUENCE'])
def test_grants_only_on_objects_dolt_has(object_type):
    with pytest.raises(RelationalClientError, match='cannot grant'):
        plan('privilege', 'grant', {
            'principal': 'u@%', 'object_type': object_type,
            'object_name': 'd1.x', 'privileges': ['EXECUTE']})


# Native administration verified live on Dolt 1.86.6 (2026-11-01).
TABLE_TARGET = {'resource_id': 'table:d1:t', 'resource_kind': 'table',
                'display_name': 't', 'display_path': ['d1', 't']}
INDEX_TARGET = {'resource_id': 'index:d1:t:k', 'resource_kind': 'index',
                'display_name': 'k', 'display_path': ['d1', 't', 'k']}
ROLE_TARGET = {'resource_id': 'role:r@%', 'resource_kind': 'role',
               'display_name': 'r@%', 'display_path': ['r@%'],
               'native': {'user': 'r', 'host': '%'}}


def statements(*args, **kwargs):
    planned = ADMINISTRATION.plan(request(*args, **kwargs))
    # The preview redacts bound values; the provider payload carries them.
    assert not any('parameters' in item for item in
                   planned['command_preview']['statements'])
    return [(item['source'], tuple(item['parameters'])) for item in
            planned['provider_payload']['compiled']['statements']]


def test_table_options_and_analyze():
    assert statements('table', 'set_options', {
        'comment': "it's", 'auto_increment': 50,
        'collation': 'utf8mb4_bin'}, TABLE_TARGET) == [(
            'ALTER TABLE `d1`.`t` COMMENT = %s, AUTO_INCREMENT = 50, '
            'DEFAULT COLLATE `utf8mb4_bin`', ("it's",))]
    with pytest.raises(RelationalClientError, match='at least one'):
        statements('table', 'set_options', {}, TABLE_TARGET)
    assert ADMINISTRATION.validate(request(
        'table', 'set_options', {'collation': 'bin; DROP'},
        TABLE_TARGET))['errors']
    assert statements('table', 'analyze', {}, TABLE_TARGET) == [
        ('ANALYZE TABLE `t`', ())]
    other = {**TABLE_TARGET, 'display_path': ['d2', 't']}
    with pytest.raises(RelationalClientError, match='connection database'):
        statements('table', 'analyze', {}, other)


def test_index_rename_quotes_both_names():
    assert statements('index', 'rename', {'new_name': 'k 2'},
                      INDEX_TARGET) == [
        ('ALTER TABLE `d1`.`t` RENAME INDEX `k` TO `k 2`', ())]
    assert ADMINISTRATION.validate(request(
        'index', 'rename', {'new_name': 'k`2'}, INDEX_TARGET))['errors']
    with pytest.raises(RelationalClientError, match='index name'):
        statements('index', 'rename', {'new_name': 'k'}, INDEX_TARGET)


def test_role_membership_binds_both_accounts():
    assert statements('role', 'grant', {
        'member_user': 'u', 'member_host': 'h', 'admin_option': True},
        ROLE_TARGET) == [('GRANT %s@%s TO %s@%s WITH ADMIN OPTION',
                          ('r', '%', 'u', 'h'))]
    assert statements('role', 'revoke', {
        'member_user': 'u', 'member_host': 'h'}, ROLE_TARGET) == [
        ('REVOKE %s@%s FROM %s@%s', ('r', '%', 'u', 'h'))]
    unnamed = {**ROLE_TARGET, 'native': {}}
    with pytest.raises(RelationalClientError, match='account identity'):
        statements('role', 'grant', {
            'member_user': 'u', 'member_host': 'h'}, unnamed)


def test_session_termination_and_global_variables():
    session = {'resource_id': 'session:7', 'resource_kind': 'session',
               'display_name': '7', 'display_path': ['7']}
    assert statements('session', 'terminate_query', {}, session) == [
        ('KILL QUERY 7', ())]
    assert statements('session', 'terminate_connection', {}, session) == [
        ('KILL 7', ())]
    with pytest.raises(RelationalClientError, match='session identity'):
        statements('session', 'terminate_query', {},
                   {**session, 'display_name': '7; KILL 1'})
    variable = {'resource_id': 'system-variable:max_connections',
                'resource_kind': 'system-variable',
                'display_name': 'max_connections',
                'display_path': ['max_connections']}
    assert statements('system-variable', 'set_global', {'value': '200'},
                      variable) == [
        ('SET @@GLOBAL.max_connections = %s', ('200',))]
    with pytest.raises(RelationalClientError, match='variable name'):
        statements('system-variable', 'set_global', {'value': '1'},
                   {**variable, 'display_name': 'a.b'})


@pytest.mark.parametrize('kind,operation', [
    ('index', 'visibility'), ('role', 'set_default'), ('user', 'rename'),
    ('system-variable', 'set_persist'), ('table', 'optimize'),
    ('table', 'check'), ('function', 'create'), ('partition', 'inspect'),
])
def test_what_dolt_ignores_or_refuses_is_not_offered(kind, operation):
    # Live, 1.86.6: invisible indexes and partitioning are accepted but not
    # applied; the rest are refused or cannot be undone (no RESET PERSIST).
    assert not ADMINISTRATION.control_plane.supports(kind, operation)
    with pytest.raises(RelationalClientError):
        ADMINISTRATION.plan(request(kind, operation, {}, TABLE_TARGET))
