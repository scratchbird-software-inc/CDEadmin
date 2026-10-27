"""MySQL stored routine signatures and characteristics are native typed fields."""
import json
from pathlib import Path

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from test_cdeadmin_visual_admin import context, Permissions
from test_visual_admin_field_contracts import IndexAdapter
from pgadmin.cdeadmin.providers.mysql_family import mysql_routines as routines
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MYSQL_ADMINISTRATION, MySQLDBAPIClient,
)
from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration
from pgadmin.cdeadmin.sdk import RelationalClientError

BASE = {'name': 'routine`雪', 'parent': ['db`雪'],
        'parameters': [{'name': 'arg`雪', 'type': 'BIGINT UNSIGNED', 'mode': 'IN'},
                       {'name': 'out', 'type': 'DECIMAL(30, 8)', 'mode': 'OUT'},
                       {'name': 'both', 'type': "ENUM('x,y', 'z)')", 'mode': 'INOUT'}],
        'body': 'BEGIN SET `out`=`arg``雪`; END'}


def test_native_signature_and_create_characteristics_keep_bound_values():
    compiled = routines.compile_create('procedure', {**BASE, 'deterministic': True,
        'data_access': 'NO SQL', 'sql_security': 'INVOKER', 'language': 'SQL',
        'comment': "quote' 雪", 'definer_user': 'owner`雪', 'definer_host': 'localhost',
        'if_not_exists': True})
    statement = compiled['statements'][0]
    assert 'DEFINER=`owner``雪`@`localhost` PROCEDURE IF NOT EXISTS' in statement['source']
    assert 'IN `arg``雪` BIGINT UNSIGNED, OUT `out` DECIMAL(30, 8), INOUT `both`' in statement['source']
    assert 'LANGUAGE SQL DETERMINISTIC NO SQL SQL SECURITY INVOKER COMMENT %s' in statement['source']
    assert statement['parameters'] == ("quote' 雪",)


@pytest.mark.parametrize('change', [
    {'returns': 'INT'}, {'parameters': [{'name': 'x', 'type': 'INT', 'default': '1'}]},
    {'parameters': [{'name': 'x', 'type': 'INT', 'mode': 'VARIADIC'}]},
    {'parameters': [{'name': 'x', 'type': 'INT); END; DROP TABLE t; --'}]},
    {'parameters': [{'name': 'x', 'type': 'INT, y INT'}]},
    {'body': "BEGIN SELECT 'unterminated; END"},
    {'body': 'BEGIN SELECT 1; END /*!90700 ; DROP DATABASE x */'},
    {'language': 'JAVASCRIPT'}, {'deterministic': None}, {'return_parameters': [{'name': 'x'}]},
    {'invented': 'option'}, {'comment': None}, {'if_not_exists': 1},
])
def test_invalid_signature_and_statement_boundaries_are_refused(change):
    with pytest.raises(RelationalClientError): routines.compile_create('procedure', {**BASE, **change})


def test_functions_have_scalar_returns_and_no_output_parameter_modes():
    draft = {'name': 'f', 'database': 'db', 'parameters': [{'name': 'x', 'type': 'INT'}],
             'returns': 'VARCHAR(40) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin',
             'body': "RETURN CONCAT(x, '/*! literal')"}
    sql = routines.compile_create('function', draft)['statements'][0]['source']
    assert '(`x` INT) RETURNS VARCHAR(40)' in sql
    with pytest.raises(RelationalClientError):
        routines.compile_create('function', {**draft, 'parameters': [{'name': 'x', 'type': 'INT', 'mode': 'OUT'}]})


class RoutineAdapter(IndexAdapter):
    admin_operation_field_contract = MySQLDBAPIClient.admin_operation_field_contract


def test_family_variants_and_backend_aliases_preserve_alter_characteristics():
    provider = ProviderVisualAdministration(context(), Permissions(), 'mysql', '9.7.0',
                                           RoutineAdapter(MYSQL_ADMINISTRATION))
    route = {'host': 'owned', 'user': 'operator'}
    for kind in ('procedure', 'function'):
        create = {**BASE, 'parameters': [{'name': 'x', 'type': 'INT'}]}
        if kind == 'function':create.update(returns='INT', body='RETURN x+1')
        result = provider.validate({'resource_kind': kind, 'operation_id': 'create', 'draft': create})
        assert result['valid'], result['errors']
        planned = provider.plan({'resource_kind': kind, 'operation_id': 'alter',
            'target_resource': {'display_path': ['db', 'r'], 'display_name': 'r'},
            'draft': {'comment': 'changed', 'confirmation': 'r'}, '_provider_route': route})
        assert planned['command_preview']['statements'][0]['source'] == 'ALTER '+kind.upper()+' `db`.`r` COMMENT <bound-comment>'
    folder = Path(__file__).resolve().parents[2]/'web/pgadmin/cdeadmin/ui_descriptors/mysql'
    caps = json.loads((folder/'capabilities.json').read_text())
    for row in caps['kinds']:
        if row['resource_kind'] in {'procedure', 'function', 'event'}:
            descriptor = json.loads((folder/row['form']).read_text())
            assert descriptor['resource_kinds'] == [row['resource_kind']]
            assert descriptor['variant'] == row['variant']


def test_type_literals_are_checked_in_the_actual_mode_and_extra_clauses_never_fit():
    assert routines.type_text("ENUM('x) , y', 'it\\'s')", '')
    with pytest.raises(RelationalClientError):routines.type_text("ENUM('x) , y', 'it\\'s')", 'NO_BACKSLASH_ESCAPES')
    for value in ('INT COMMENT 1', 'INT) SQL SECURITY INVOKER', 'INT/*x*/', 'INT(1,(2))'):
        with pytest.raises(RelationalClientError):routines.type_text(value, '')


def test_grammar_dependency_refusal_precedes_any_ddl_and_binds_literal_placeholders(monkeypatch):
    from pgadmin.cdeadmin.providers.mysql_family import mysql_parser
    from unittest.mock import Mock
    compiled=routines.compile_create('function',{'name':'f','database':'db','returns':'VARCHAR(20)',
        'body':"RETURN '%s'",'comment':"private quote'"})
    resolver=Mock(side_effect=FileNotFoundError('unavailable dependency'))
    monkeypatch.setattr(mysql_parser,'library',resolver)
    with pytest.raises(RelationalClientError,match='grammar library'):
        routines.check_grammar(None,compiled,'')
    monkeypatch.setattr(mysql_parser,'library',lambda client:Path('/registered/native-parser'))
    parser=Mock(return_value={'statements':[{'sql_syntax_valid':False}]})
    monkeypatch.setattr(mysql_parser,'native',parser)
    with pytest.raises(RelationalClientError,match='no DDL was executed'):
        routines.check_grammar(None,compiled,'ANSI_QUOTES')
    source=parser.call_args.args[1][0]
    assert source['sql_mode']=='ANSI_QUOTES'
    assert "COMMENT ''\nRETURN '%s'" in source['source']
    assert 'private quote' not in source['source']
