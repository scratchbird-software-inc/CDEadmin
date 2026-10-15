"""Explicit native column rename intent preserves values and rejects guessing."""
from copy import deepcopy
import pytest
from tools.tests.test_mysql_schema_plan import captured,table
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan


def desired():
    before=captured();after=deepcopy(before)
    row=table(after);row['native']['definition']=row['native']['definition'].replace('`note`','`memo``é`')
    row['native']['mysql_change']={'rename_columns':{'note':'memo`é'}}
    return before,after


def test_explicit_rename_compiles_change_not_drop_add_and_retains_native_default():
    before,after=desired();result=plan(before,after,before)
    assert result['ready_for_review'],result
    source=result['operations'][0]['source']
    assert "CHANGE COLUMN `note` `memo``é` varchar(80) DEFAULT 'a;b' AFTER `id`" in source
    assert 'DROP COLUMN' not in source and 'ADD COLUMN' not in source
    # Renaming in a filtered graphical document cannot silently imply removal.
    del table(after)['native']['mysql_change']
    assert plan(before,after,before)['blockers']


@pytest.mark.parametrize('renames',[
    [],{'absent':'memo`é'},{'note':'id'},{'note':'note'},
    {'note':'memo`é','id':'memo`é'},{'note':'x'*65},{'note':None},
])
def test_invalid_or_occupied_rename_mapping_refuses_plan(renames):
    before,after=desired();table(after)['native']['mysql_change']['rename_columns']=renames
    result=plan(before,after,before)
    assert result['blockers'] and not result['operations']


def test_rename_retains_explicit_index_and_generated_expression_reconciliation():
    before=captured()
    row=table(before);row['native']['definition']=row['native']['definition'].replace('PRIMARY KEY',
        '`calculated` int GENERATED ALWAYS AS (length(`note`)) STORED, KEY `by_note` (`note`), PRIMARY KEY')
    after=deepcopy(before);row=table(after)
    row['native']['definition']=row['native']['definition'].replace('`note`','`memo`')
    row['native']['mysql_change']={'rename_columns':{'note':'memo'}}
    result=plan(before,after,before);assert result['ready_for_review'],result
    source=result['operations'][0]['source']
    assert 'DROP INDEX `by_note`' not in source and 'ADD KEY `by_note`' not in source
    assert 'CHANGE COLUMN `note` `memo`' in source
    assert 'MODIFY COLUMN `calculated` int GENERATED ALWAYS AS (length(`memo`)) STORED' in source
