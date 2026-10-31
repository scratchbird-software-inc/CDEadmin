"""immudb table compilation and records (providers/immudb/tables.py)."""
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

from pgadmin.cdeadmin.providers.immudb import tables  # noqa: E402
from pgadmin.cdeadmin.providers.immudb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

ROUTE = {'host': '127.0.0.1', 'database': 'd'}
NATIVE = {'columns': [
    {'name': 'id', 'type': 'INTEGER', 'nullable': False},
    {'name': 'qty', 'type': 'INTEGER', 'default': '1'}],
    'primary_key': ['id'],
    'check_constraints': [{'name': 'qty_positive', 'expression': 'qty > 0'},
                          {'name': 't_check1', 'expression': "id > 0"}]}
TARGET = {'resource_id': 'table:public:t', 'display_name': 't',
          'display_path': ['public', 't'], 'native': NATIVE}


def sql(operation, draft, target=None):
    request = {'resource_kind': 'table', 'operation_id': operation,
               'draft': draft, 'target_resource': target,
               '_provider_route': ROUTE}
    assert ADMINISTRATION.validate(request)['errors'] == []
    action = ADMINISTRATION.plan(request)['provider_payload'][
        'compiled']['provider_action']
    assert action['path'] == '/db/sqlexec'
    return action['body']['sql']


def test_create_sends_one_native_batch():
    assert sql('create', {
        'name': 't', 'columns': [
            {'name': 'id', 'type': 'integer', 'nullable': False,
             'auto_increment': True},
            {'name': 'code', 'type': 'VARCHAR', 'max_length': 16,
             'default': "'none'"},
            {'name': 'b', 'type': 'BLOB', 'max_length': 8}],
        'primary_key': ['id'],
        'check_constraints': [{'name': 'c', 'expression': 'id > 0'},
                              {'expression': "code <> ''"}]}) == (
        'CREATE TABLE "t" ("id" INTEGER NOT NULL AUTO_INCREMENT, "code" '
        '''VARCHAR[16] DEFAULT 'none', "b" BLOB[8], CONSTRAINT "c" CHECK '''
        '''(id > 0), CHECK (code <> ''), PRIMARY KEY ("id"))''')


def test_alter_orders_checks_renames_adds_drops_then_table_name():
    assert sql('alter', {
        'check_constraints': [{'name': 'qty_positive',
                               'expression': 'qty > 0'}],
        'rename_columns': [{'from': 'id', 'to': 'key'}],
        'add_columns': [{'name': 'note', 'type': 'VARCHAR',
                         'default': "'n'"}],
        'name': 'u'}, TARGET).split('; ') == [
        'ALTER TABLE "t" DROP CONSTRAINT "t_check1"',
        'ALTER TABLE "t" RENAME COLUMN "id" TO "key"',
        'ALTER TABLE "t" ADD COLUMN "note" VARCHAR DEFAULT \'n\'',
        'ALTER TABLE "t" RENAME TO "u"']


def test_dropping_the_check_first_frees_its_column():
    assert sql('alter', {'check_constraints': [
        {'name': 't_check1', 'expression': 'id > 0'}],
        'drop_columns': ['qty']}, TARGET).split('; ') == [
        'ALTER TABLE "t" DROP CONSTRAINT "qty_positive"',
        'ALTER TABLE "t" DROP COLUMN "qty"']


@pytest.mark.parametrize('operation, draft, target, reason', [
    ('create', {'name': 't', 'columns': [{'name': 'id', 'type': 'INT8'}],
                'primary_key': ['id']}, None, 'column type is one of'),
    ('create', {'name': 't', 'columns': [{'name': 'id', 'type': 'INTEGER'}]},
     None, 'need a primary key'),
    ('create', {'name': 't', 'columns': [
        {'name': 'id', 'type': 'INTEGER', 'max_length': 4}],
        'primary_key': ['id']}, None, 'VARCHAR and BLOB only'),
    ('create', {'name': 't', 'parent': 's', 'columns': [
        {'name': 'id', 'type': 'INTEGER'}], 'primary_key': ['id']},
     None, 'one namespace'),
    ('create', {'name': 'bad name', 'columns': [
        {'name': 'id', 'type': 'INTEGER'}], 'primary_key': ['id']},
     None, 'letter or underscore'),
    ('alter', {'alter_columns': [{'name': 'qty', 'changes': {
        'nullable': False}}]}, TARGET, 'does not keep it'),
    ('alter', {'primary_key': ['qty']}, TARGET, 'cannot change a primary'),
    ('alter', {'check_constraints': [*NATIVE['check_constraints'], {
        'name': 'new', 'expression': 'id < 9'}]}, TARGET, 'no ADD CONSTRAINT'),
    ('alter', {'rename_columns': [{'from': 'qty', 'to': 'quantity'}]},
     TARGET, 'check qty_positive uses qty'),
    ('alter', {'drop_columns': ['qty']}, TARGET, 'stop every insert'),
    ('alter', {'add_columns': [{'name': 'n', 'type': 'INTEGER',
                                'auto_increment': True}]}, TARGET,
     'set at create'),
    ('alter', {}, TARGET, 'nothing to change'),
    ('alter', {'name': 'Orders'}, TARGET, 'folds names to lowercase'),
    ('create', {'name': 't', 'columns': [{'name': 'k', 'type': 'VARCHAR'}],
                'primary_key': ['k']}, None, 'at most 1024'),
])
def test_refusals(operation, draft, target, reason):
    with pytest.raises(RelationalClientError, match=reason):
        if operation == 'create':
            tables.create(ADMINISTRATION, draft)
        else:
            tables.alter(ADMINISTRATION, draft, target)


def test_unread_checks_refuse_check_and_column_moves():
    unread = {**TARGET, 'native': {**NATIVE, 'check_constraints': None,
                                   'catalog_log_unread': 'budget'}}
    with pytest.raises(RelationalClientError, match='could not be read'):
        tables.alter(ADMINISTRATION, {'check_constraints': []}, unread)
    with pytest.raises(RelationalClientError, match='could not be read'):
        tables.alter(ADMINISTRATION, {'drop_columns': ['qty']}, unread)
    assert tables.alter(ADMINISTRATION, {'name': 'u'}, unread) == [
        'ALTER TABLE "t" RENAME TO "u"']


def test_string_literals_are_not_column_names():
    assert tables._words("code <> 'qty' AND id > 0") == {'code', 'AND', 'id'}


def test_record_reads_columns_keys_and_log_facts():
    native = tables.record([
        {'name': 'id', 'type': 'INTEGER', 'max_length': 8,
         'nullable': True, 'auto_increment': True},
        {'name': 'code', 'type': 'VARCHAR', 'max_length': 16,
         'nullable': False, 'auto_increment': False}],
        [{'name': 't(id)', 'unique': True, 'primary': True},
         {'name': 't(code)', 'unique': True, 'primary': False}])
    assert native['check_constraints'] is None
    assert native['catalog_log_unread'] == 'not read'
    tables.with_facts(native, {'defaults': {'code': "'x'"}, 'checks': [
        {'name': 'c', 'expression': '((id > 0) AND (id < 9))'}]})
    assert native == {
        'columns': [
            {'name': 'id', 'type': 'INTEGER', 'max_length': None,
             'nullable': False, 'default': None, 'auto_increment': True},
            {'name': 'code', 'type': 'VARCHAR', 'max_length': 16,
             'nullable': False, 'default': "'x'", 'auto_increment': False}],
        'primary_key': ['id'],
        'check_constraints': [
            {'name': 'c', 'expression': '(id > 0) AND (id < 9)'}]}
    assert tables.unwrap('(a > 0) AND (b > 0)') == '(a > 0) AND (b > 0)'
    tables.with_facts(native, 'the catalog log could not be read (x)')
    assert native['catalog_log_unread'].startswith('the catalog log')


def test_drop_removes_checks_first():
    # Live, 1.11.0: DROP TABLE failed while the table had a check.
    assert tables.drop(TARGET) == [
        'ALTER TABLE "t" DROP CONSTRAINT "qty_positive"',
        'ALTER TABLE "t" DROP CONSTRAINT "t_check1"',
        'DROP TABLE "t"']
    assert tables.drop({'display_path': ['public', 't'], 'native': {
        'check_constraints': None}}) == ['DROP TABLE "t"']
