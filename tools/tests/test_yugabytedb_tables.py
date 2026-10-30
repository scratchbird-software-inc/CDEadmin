"""YugabyteDB YSQL table compilation and the primary key reader."""
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

from pgadmin.cdeadmin.providers.yugabytedb import tables  # noqa: E402
from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

TARGET = {'resource_id': 'table:public:t', 'display_name': 't',
          'display_path': ['public', 't'], 'native': {
              'tablespace': 'ts', 'comment': None,
              'row_level_security': False,
              'column_types': {'n': 'character varying(40)'},
              'constraints': [
                  {'name': 't_pkey', 'kind': 'PRIMARY KEY',
                   'columns': ['id'], 'hash_columns': ['id'],
                   'order': 'ASC'},
                  {'name': 'uq', 'kind': 'UNIQUE', 'columns': ['n']}]}}


def plan(operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': 'table', 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1', 'database': 'd'}})
    compiled = planned['provider_payload']['compiled']
    return ([item['source'] for item in compiled['statements']],
            compiled.get('warnings', []))


def test_primary_key_shape():
    assert tables.primary_key_shape(
        'CREATE UNIQUE INDEX p ON public.t USING lsm ((a, b) HASH, c ASC)'
    ) == (['a', 'b'], 'ASC')
    assert tables.primary_key_shape(
        'CREATE UNIQUE INDEX p ON public.t USING lsm (id HASH)') == (
        ['id'], 'ASC')
    assert tables.primary_key_shape(
        'CREATE UNIQUE INDEX p ON public.t USING lsm (id DESC)') == (
        [], 'DESC')


def test_create_with_hash_key_split_tablespace_and_partitioning():
    sources, _ = plan('create', {
        'name': 't', 'parent': 'public', 'tablespace': 'ts',
        'split_into': 4,
        'columns': [{'name': 'a', 'type': 'text', 'nullable': False},
                    {'name': 'b', 'type': 'int', 'identity': 'ALWAYS'},
                    {'name': 'c', 'type': 'int',
                     'generated_expression': 'b * 2'},
                    {'name': 'n', 'type': 'text', 'collation': 'C'}],
        'primary_key': [{'name': 'pk', 'columns': ['a', 'b'],
                         'hash_columns': ['a'], 'order': 'DESC'}],
        'foreign_keys': [{'columns': ['b'], 'references_table': 'public.p',
                          'references_columns': ['k'], 'deferrable': True,
                          'initially_deferred': True}],
        'partition_by': 'HASH', 'partition_key': 'a'})
    assert sources == [
        'CREATE TABLE "public"."t" ("a" text NOT NULL, "b" int GENERATED '
        'ALWAYS AS IDENTITY, "c" int GENERATED ALWAYS AS (b * 2) STORED, '
        '"n" text COLLATE "C", CONSTRAINT "pk" PRIMARY KEY ("a" HASH, '
        '"b" DESC), FOREIGN KEY ("b") REFERENCES "public"."p" ("k") '
        'DEFERRABLE INITIALLY DEFERRED) PARTITION BY HASH (a) TABLESPACE '
        '"ts" SPLIT INTO 4 TABLETS']


def test_alter_restates_type_for_collation_and_rewrites_primary_key():
    sources, warnings = plan('alter', {
        'alter_columns': [{'name': 'n', 'changes': {'collation': 'C'}}],
        'primary_key': [{'name': 't_pkey', 'columns': ['id'],
                         'hash_columns': [], 'order': 'ASC'}],
        'tablespace': ''}, TARGET)
    table = '"public"."t"'
    assert sources == [
        f'ALTER TABLE {table} DROP CONSTRAINT "t_pkey"',
        f'ALTER TABLE {table} ALTER COLUMN "n" TYPE character varying(40) '
        'COLLATE "C"',
        f'ALTER TABLE {table} ADD CONSTRAINT "t_pkey" PRIMARY KEY '
        '("id" ASC)',
        f'ALTER TABLE {table} SET TABLESPACE "pg_default"']
    assert 'rewrites' in warnings[0]


@pytest.mark.parametrize('operation, draft, reason', [
    ('create', {'name': 't', 'columns': [{'name': 'a', 'type': 'int'}],
                'unique_constraints': [{'columns': ['a'],
                                        'deferrable': True}]},
     'deferrable unique'),
    ('create', {'name': 't', 'columns': [{'name': 'a', 'type': 'int'}],
                'primary_key': [{'columns': ['a', 'b'],
                                 'hash_columns': ['b']}]}, 'leading'),
    ('create', {'name': 't', 'columns': [{'name': 'a', 'type': 'int'}],
                'split_into': 2, 'split_at': ['1']}, 'SPLIT INTO or'),
    ('create', {'name': 't', 'columns': [
        {'name': 'a', 'type': 'int', 'identity': 'ALWAYS',
         'generated_expression': 'a'}]}, 'no default or identity'),
    ('alter', {'alter_columns': [{'name': 'a', 'changes': {
        'generated_expression': 'a + 1'}}]}, 'only when added'),
])
def test_refusals(operation, draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan(operation, draft, TARGET)
