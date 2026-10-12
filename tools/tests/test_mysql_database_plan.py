"""Database-root changes are explicit native option intent, never replacement."""
from copy import deepcopy
import pytest
from tools.tests.test_mysql_sql_export import model
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan


def root(document):return next(row for row in document['rows'].values() if row['kind']=='database')


def test_exact_database_option_changes_leave_baseline_definition_intact():
    before=model([]);desired=deepcopy(before)
    root(desired)['native']['mysql_change']={'action':'alter-options','character_set':'utf8mb4','collation':'utf8mb4_bin','encryption':'N'}
    result=plan(before,desired,before)
    assert result['ready_for_review'] and result['operations'][0]['source']=="ALTER DATABASE `demo``db` DEFAULT CHARACTER SET `utf8mb4` DEFAULT COLLATE `utf8mb4_bin` ENCRYPTION = 'N'"
    assert root(desired)['native']['definition']==root(before)['native']['definition']
    live=deepcopy(before);root(live)['native']['definition']+=' DEFAULT CHARACTER SET latin1'
    assert plan(before,desired,live)['conflicts']


@pytest.mark.parametrize('intent',[
    {'action':'drop','confirmation':'demo`db'}, {'action':'alter-options'},
    {'action':'alter-options','character_set':'utf8mb4; DROP DATABASE x'},
    {'action':'alter-options','collation':None}, {'action':'alter-options','encryption':'yes'},
    {'action':'alter-options','read_only':True},
])
def test_unadmitted_database_root_intents_refuse_review(intent):
    before=model([]);desired=deepcopy(before);root(desired)['native']['mysql_change']=intent
    assert plan(before,desired,before)['blockers']
