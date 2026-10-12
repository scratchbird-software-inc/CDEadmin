"""View DDN changes bind exact quoted targets, bodies and creation contexts."""
from copy import deepcopy
import pytest
from tools.tests.test_mysql_sql_export import model
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_view_plan import compile_view


def captured():
    return model([('view','v','CREATE ALGORITHM=MERGE DEFINER=`owner`@`%` SQL SECURITY INVOKER VIEW `v` AS select 42 AS `id`',{})])


def view(document):return next(row for row in document['rows'].values() if row['kind']=='view')


def test_view_alteration_preserves_exact_native_definer_options_and_body():
    before=captured();desired=deepcopy(before)
    view(desired)['native']['definition']=view(desired)['native']['definition'].replace('select 42','select 43')
    result=plan(before,desired,before)
    assert result['ready_for_review'] and result['operations'][0]['kind']=='view'
    assert result['operations'][0]['source']=='ALTER ALGORITHM=MERGE DEFINER=`owner`@`%` SQL SECURITY INVOKER VIEW `demo``db`.`v` AS select 43 AS `id`'
    changed=deepcopy(before);view(changed)['native']['definition']+=' WITH LOCAL CHECK OPTION'
    assert plan(before,desired,changed)['conflicts']


def test_view_create_is_not_replacement_and_filtered_view_is_not_drop():
    desired=captured();before=deepcopy(desired);del before['rows'][view(desired)['resource_id']]
    result=plan(before,desired,before)
    assert result['ready_for_review'] and result['operations'][0]['operation']=='create'
    assert 'OR REPLACE' not in result['operations'][0]['source']
    assert not plan(desired,before,desired)['operations']
    row=view(desired);row['native']['mysql_change']={'action':'drop','confirmation':'v'}
    assert compile_view(row,'drop','demo`db')=='DROP VIEW `demo``db`.`v`'
    row['native']['mysql_change']['confirmation']='wrong'
    with pytest.raises(ValueError):compile_view(row,'drop','demo`db')


@pytest.mark.parametrize('source',[
    'CREATE VIEW `wrong` AS SELECT 1', 'CREATE OR REPLACE VIEW `v` AS SELECT 1',
    'CREATE MATERIALIZED VIEW `v` AS SELECT 1', 'CREATE VIEW `elsewhere`.`v` AS SELECT 1',
])
def test_ambiguous_or_other_native_target_is_refused(source):
    row=view(captured());row['native']['definition']=source
    with pytest.raises(ValueError):compile_view(row,'alter','demo`db')


@pytest.mark.parametrize('code,kind,operation,accepted',[
    (1295,'view','alter',True),(1064,'view','alter',False),
    (1146,'view','alter',False),(1295,'table','alter',False),
    (1295,'view','create',False),(1295,'procedure','create',False),
])
def test_native_parse_acceptance_is_limited_to_qualified_view_alter(code,kind,operation,accepted):
    from unittest.mock import Mock
    from mysql.connector import Error
    from pgadmin.cdeadmin.providers.mysql_schema_validation import validate
    before=captured();desired=deepcopy(before)
    view(desired)['native']['definition']=view(desired)['native']['definition'].replace('select 42','select 43')
    preview=plan(before,desired,before)
    preview['operations'][0].update(kind=kind,operation=operation)
    cursor=Mock();cursor.fetchone.return_value=('9.7.0','server','demo`db')
    def execute(source,*args):
        if source.startswith('PREPARE '):raise Error('native diagnostic',errno=code)
    cursor.execute.side_effect=execute
    connection=Mock(in_transaction=False);connection.cursor.return_value=cursor
    result=validate(connection,preview)
    assert result['native_grammar_validated']==accepted and not result['executed']
    item=result['native_validation'][0]
    assert item['preparation_supported'] is False
    assert item['validation_stage']==('parse-only' if accepted else 'rejected')
    assert not any(call.args[0].startswith(('DEALLOCATE','EXECUTE','ALTER VIEW')) for call in cursor.execute.call_args_list)
