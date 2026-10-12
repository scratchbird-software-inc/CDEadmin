"""Native DDN three-way previews preserve clauses, scope and explicit intent."""
from copy import deepcopy
from tools.tests.test_mysql_sql_export import model
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan


def captured():
    return model([('table','t','CREATE TABLE `t` (`id` int NOT NULL, `note` varchar(80) DEFAULT \'a;b\', PRIMARY KEY (`id`)) ENGINE=InnoDB',{})])

def table(document):return next(row for row in document['rows'].values() if row['kind']=='table')


def test_native_table_alteration_retains_full_clauses_and_positions_without_execution():
    before=captured();desired=deepcopy(before)
    row=table(desired);row['native']['definition']=row['native']['definition'].replace('varchar(80)','varchar(120)').replace('PRIMARY KEY','`computed` int GENERATED ALWAYS AS ((`id` + 1)) STORED, PRIMARY KEY')
    result=plan(before,desired,deepcopy(before))
    assert result['ready_for_review'] and not result['application_supported'] and not result['native_grammar_validated']
    source=result['operations'][0]['source']
    assert 'MODIFY COLUMN `note` varchar(120) DEFAULT \'a;b\' AFTER `id`' in source
    assert 'ADD COLUMN `computed` int GENERATED ALWAYS AS ((`id` + 1)) STORED AFTER `note`' in source
    assert source.startswith('ALTER TABLE `demo``db`.`t`') and 'DROP TABLE' not in source


def test_live_schema_drift_blocks_selected_changes_and_volatile_facts_do_not():
    before=captured();desired=deepcopy(before);table(desired)['native']['definition']+=' COMMENT=\'edited\''
    current=deepcopy(before);table(current)['native']['catalog_row']={'table_rows':999}
    assert plan(before,desired,current)['ready_for_review']
    table(current)['native']['definition']+=' COMMENT=\'concurrent\''
    result=plan(before,desired,current)
    assert result['conflicts'] and not result['operations'] and not result['ready_for_review']


def test_filtered_rows_are_not_deletion_and_explicit_removal_is_exactly_confirmed():
    before=captured();desired=deepcopy(before);del desired['rows'][table(desired)['resource_id']]
    result=plan(before,desired,before);assert not result['operations'] and result['ignored']
    desired=deepcopy(before);table(desired)['native']['mysql_change']={'action':'drop','confirmation':'wrong'}
    assert plan(before,desired,before)['blockers']
    table(desired)['native']['mysql_change']['confirmation']='t'
    result=plan(before,desired,before);assert result['operations'][0]['source']=='DROP TABLE `demo``db`.`t`'
    desired=deepcopy(before);row=table(desired);row['native']['definition']=row['native']['definition'].replace("`note` varchar(80) DEFAULT 'a;b', ",'')
    assert plan(before,desired,before)['blockers']
    row['native']['mysql_change']={'drop_columns':['note']}
    assert 'DROP COLUMN `note`' in plan(before,desired,before)['operations'][0]['source']


def test_target_and_baseline_identity_tampering_cannot_redirect_native_previews():
    before=captured();desired=deepcopy(before);table(desired)['native']['definition']+=' COMMENT=\'edited\''
    table(before)['native']['database']='other'
    result=plan(before,desired,captured());assert result['blockers'] and not result['operations']


def test_native_validation_prepares_and_deallocates_without_executing_changes():
    from unittest.mock import Mock
    from pgadmin.cdeadmin.providers.mysql_schema_validation import validate
    before=captured();desired=deepcopy(before);table(desired)['native']['definition']+=' COMMENT=\'edited\''
    preview=plan(before,desired,before);cursor=Mock();cursor.fetchone.return_value=('9.7.0','server','demo`db')
    connection=Mock(in_transaction=False);connection.cursor.return_value=cursor
    result=validate(connection,preview)
    assert result['native_grammar_validated'] and not result['executed'] and not result['application_supported']
    sources=[call.args[0] for call in cursor.execute.call_args_list]
    assert 'PREPARE sr_native_preview FROM @sr_native_preview' in sources
    assert 'DEALLOCATE PREPARE sr_native_preview' in sources
    assert not any(source.startswith(('ALTER TABLE','EXECUTE ')) for source in sources)
    cursor.close.assert_called_once()


def test_database_root_changes_are_blocked_instead_of_silently_skipped():
    before=captured();desired=deepcopy(before)
    root=next(row for row in desired['rows'].values() if row['kind']=='database')
    root['native']['definition'] += ' DEFAULT CHARACTER SET latin1'
    result=plan(before,desired,before)
    assert not result['ready_for_review'] and any('Database-root changes' in row['reason'] for row in result['blockers'])
