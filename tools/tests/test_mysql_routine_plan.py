"""Stored routine DDN intent binds identity and preserves opaque native bodies."""
from copy import deepcopy
import pytest
from tools.tests.test_mysql_sql_export import model
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_routine_plan import compile_routine


def captured(kind='procedure'):
    definition='CREATE DEFINER=`owner`@`%` '+kind.upper()+' `r`() '+('RETURNS int DETERMINISTIC RETURN 42' if kind=='function' else "BEGIN SELECT 'a;b'; END")
    return model([(kind,'r',definition,{'definition_context':{'sql_mode':'NO_BACKSLASH_ESCAPES',
        'character_set_client':'utf8mb4','collation_connection':'utf8mb4_bin'}})])


def routine(document):return next(row for row in document['rows'].values() if row['kind'] in {'procedure','function'})


@pytest.mark.parametrize('kind',['procedure','function'])
def test_routine_create_drop_are_exact_and_omission_is_not_removal(kind):
    desired=captured(kind);before=deepcopy(desired);del before['rows'][routine(desired)['resource_id']]
    result=plan(before,desired,before)
    assert result['ready_for_review'] and 'OR REPLACE' not in result['operations'][0]['source']
    assert '`demo``db`.`r`' in result['operations'][0]['source']
    assert not plan(desired,before,desired)['operations']
    row=routine(desired);row['native']['mysql_change']={'action':'drop','confirmation':'r'}
    assert compile_routine(row,'drop','demo`db')=='DROP '+kind.upper()+' `demo``db`.`r`'
    row['native']['mysql_change']['confirmation']='wrong'
    with pytest.raises(ValueError):compile_routine(row,'drop','demo`db')


@pytest.mark.parametrize('mode',['','NO_BACKSLASH_ESCAPES'])
def test_routine_characteristics_preserve_source_and_quote_comments(mode):
    before=captured();routine(before)['native']['definition_context']['sql_mode']=mode
    desired=deepcopy(before);row=routine(desired)
    row['native']['mysql_change']={'action':'alter-characteristics','sql_security':'INVOKER','data_access':'READS SQL DATA','comment':"a'b\\c"}
    result=plan(before,desired,before)
    assert result['ready_for_review']
    assert result['operations'][0]['source']=="ALTER PROCEDURE `demo``db`.`r` SQL SECURITY INVOKER READS SQL DATA COMMENT 'a''b"+('\\' if mode else '\\\\')+"c'"
    assert row['native']['definition']==routine(before)['native']['definition']
    row['native']['mysql_change']={'action':'alter-characteristics','comment':''}
    assert plan(before,desired,before)['operations'][0]['source'].endswith("COMMENT ''")


@pytest.mark.parametrize('change',[
    {'action':'alter-characteristics'}, {'action':'alter-characteristics','sql_security':'INVALID'},
    {'action':'alter-characteristics','data_access':'DETERMINISTIC'},
    {'action':'alter-characteristics','comment':None},
    {'action':'alter-characteristics','comment':'ok','body':'SELECT 1'},
])
def test_invalid_native_characteristics_block_review(change):
    before=captured();desired=deepcopy(before);routine(desired)['native']['mysql_change']=change
    assert plan(before,desired,before)['blockers']


def test_routine_body_context_and_wrong_identity_are_never_silently_replaced():
    before=captured();desired=deepcopy(before);row=routine(desired)
    row['native']['definition']=row['native']['definition'].replace('a;b','new body')
    assert plan(before,desired,before)['blockers']
    row['native']['mysql_change']={'action':'alter-characteristics','comment':'changed'}
    assert plan(before,desired,before)['blockers']
    row['native']['definition']='CREATE PROCEDURE `elsewhere`.`r`() SELECT 1'
    with pytest.raises(ValueError):compile_routine(row,'create','demo`db')
