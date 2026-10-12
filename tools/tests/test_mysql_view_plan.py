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
    assert result['operations'][0]['source']=='CREATE OR REPLACE ALGORITHM=MERGE DEFINER=`owner`@`%` SQL SECURITY INVOKER VIEW `demo``db`.`v` AS select 43 AS `id`'
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
