"""Native index options and field boundaries, including legacy requests."""
from copy import deepcopy
from unittest.mock import Mock

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family import mysql_indexes as indexes
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError


BASE = {'name': 'index`雪', 'table': ['db`雪', 'table`雪'], 'columns': ['id']}


def test_native_options_are_bound_and_legacy_name_lists_remain_accepted():
    source = indexes.compile_create(BASE)['statements'][0]
    assert source == {'source': 'CREATE INDEX `index``雪` ON `db``雪`.`table``雪` (`id`)', 'parameters': ()}
    assert indexes.compile_create({'name': BASE['name'], 'options': {key: value for key, value in BASE.items() if key != 'name'}})['statements'][0] == source
    draft = {**BASE, 'columns': [{'name': 'text`col', 'prefix_length': 12, 'direction': 'DESC'},
        {'expression': "concat('/*! literal', lower(`text``col`))", 'direction': 'ASC'}],
        'unique': True, 'method': 'BTREE', 'visible': False, 'key_block_size': '8',
        'algorithm': 'INPLACE', 'lock': 'NONE', 'comment': "quote' 雪",
        'secondary_engine_attribute': {'native': None}}
    result = indexes.compile_create(draft)['statements'][0]
    assert result['source'].startswith('CREATE UNIQUE INDEX `index``雪` USING BTREE ON ')
    assert '`text``col`(12) DESC' in result['source'] and 'CONCURRENTLY' not in result['source']
    assert 'KEY_BLOCK_SIZE=8 COMMENT %s INVISIBLE SECONDARY_ENGINE_ATTRIBUTE=%s' in result['source']
    assert result['source'].endswith('ALGORITHM=INPLACE LOCK=NONE')
    assert result['parameters'] == ("quote' 雪", '{"native":null}')


@pytest.mark.parametrize('change', [
    {'columns': []}, {'columns': [{'name': 'id', 'expression': 'id+1'}]},
    {'columns': [{'name': 'id', 'prefix_length': True}]},
    {'columns': [{'expression': 'id+1', 'prefix_length': 1}]},
    {'columns': [{'expression': 'id); DROP TABLE t; --'}]},
    {'columns': [{'expression': 'id /*!90700 ); DROP TABLE t; */'}]},
    {'columns': [{'name': 'id', 'direction': {}}]},
    {'columns': [{'name': [], 'expression': 'id+1'}]},
    {'columns': [{'name': 'id', 'ignored': True}]},
    {'unique': 'true'}, {'index_kind': 'SPATIAL', 'unique': True},
    {'index_kind': 'FULLTEXT', 'method': 'HASH'}, {'parser': 'ngram'},
    {'visible': 0}, {'algorithm': 'INSTANT'}, {'lock': 'INVALID'},
    {'key_block_size': 8}, {'key_block_size': '-1'}, {'key_block_size': str(2**64)},
    {'comment': None}, {'secondary_engine_attribute': float('nan')}, {'engine_attribute': {'native': True}},
    {'table': []}, {'parent': 'elsewhere'}, {'ignored': 'native?'}])
def test_unknown_incompatible_or_injected_properties_never_become_silent_options(change):
    with pytest.raises(RelationalClientError):
        indexes.compile_create({**BASE, **change})


def test_exact_mode_admission_does_not_confuse_literal_comment_markers_with_executable_comments():
    assert indexes.expression("concat('/*!', `id`)", '')
    assert indexes.expression("concat($tag$/*!$tag$, `id`)", '')
    assert indexes.expression("concat('it\\'s', `id`)", '')
    with pytest.raises(RelationalClientError):
        indexes.expression("concat('it\\'s', `id`)", 'NO_BACKSLASH_ESCAPES')
    with pytest.raises(RelationalClientError):
        indexes.expression('id + /*!90700 1 */', '')


def test_structure_binding_ignores_the_native_counter_but_retains_literals_and_column_definitions():
    ddl="CREATE TABLE `AUTO_INCREMENT=2` (`id` int AUTO_INCREMENT, `v` varchar(80) DEFAULT 'AUTO_INCREMENT=2') ENGINE=InnoDB AUTO_INCREMENT=2 COMMENT='AUTO_INCREMENT=2'"
    expected = indexes.structural_definition(ddl, '')
    assert indexes.structural_definition(ddl.replace('ENGINE=InnoDB AUTO_INCREMENT=2', 'ENGINE=InnoDB AUTO_INCREMENT=999'), '') == expected
    assert indexes.structural_definition(ddl.replace("COMMENT='AUTO_INCREMENT=2'", "COMMENT='AUTO_INCREMENT=3'"), '') != expected
    assert indexes.structural_definition(ddl.replace('`id` int', '`id` bigint'), '') != expected
    assert indexes.structural_definition(ddl.replace("DEFAULT 'AUTO_INCREMENT=2'", "DEFAULT 'AUTO_INCREMENT=3'"), '') != expected
    option=" /*!80021 SECONDARY_ENGINE_ATTRIBUTE '{\"native\":\"*/ AUTO_INCREMENT=2\"}' */"
    ddl += option
    assert indexes.structural_definition(ddl.replace('ENGINE=InnoDB AUTO_INCREMENT=2','ENGINE=InnoDB AUTO_INCREMENT=99'), '') == indexes.structural_definition(ddl, '')
    assert indexes.structural_definition(ddl.replace('*/ AUTO_INCREMENT=2', '*/ AUTO_INCREMENT=3'), '') != indexes.structural_definition(ddl, '')


def test_compiled_and_canonical_table_tampering_are_refused_before_a_native_connection():
    compiled = indexes.compile_create(BASE)
    compiled['mysql_index_create']['review'] = {'execution_identity': {'sql_mode': ''}, 'before': {}}
    for change in ('statement', 'table'):
        selected = deepcopy(compiled)
        if change == 'statement': selected['statements'][0]['source'] += '; DROP TABLE t'
        else: selected['mysql_index_create']['table'] = ['different', 'table']
        client = Mock()
        with pytest.raises(RelationalClientError): indexes.apply(client, {'provider_payload': {'compiled': selected}})
        client._connect.assert_not_called()


def test_actual_provider_plan_preserves_typed_options_and_never_adds_an_unsupported_index_operation():
    request = {'resource_kind': 'index', 'operation_id': 'create', 'draft': {
        **BASE, 'columns': [{'name': 'id', 'direction': 'DESC'}], 'method': 'BTREE'},
        '_provider_route': {'host': 'owned', 'user': 'operator'}}
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    planned = MYSQL_ADMINISTRATION.plan(request)
    assert planned['provider_payload']['compiled']['mysql_index_create']['table'] == BASE['table']
    assert '(`id` DESC)' in planned['command_preview']['statements'][0]['source']
    assert not MYSQL_ADMINISTRATION.supports('index', 'alter')
