"""MariaDB temporal table diffs retain native identity and explicit removal intent."""
from copy import deepcopy
import pytest
from tools.tests.test_mariadb_sql_export import model
from pgadmin.cdeadmin.workspace.mariadb_schema_plan import plan


def table(document):
    return next(row for row in document['rows'].values() if row['kind'] == 'table')


def test_native_check_and_generated_column_dialect():
    before = model(); desired = deepcopy(before)
    table(before)['native']['definition'] = 'CREATE TABLE `a` (`id` int, CONSTRAINT `positive` CHECK (`id` > 0)) ENGINE=InnoDB'
    table(desired)['native']['definition'] = 'CREATE TABLE `a` (`id` bigint, `next_id` bigint GENERATED ALWAYS AS ((`id` + 1)) STORED) ENGINE=InnoDB'
    preview = plan(before, desired, before)
    assert preview['ready_for_review'] and not preview['executed'] and not preview['application_supported']
    source = preview['operations'][0]['source']
    assert 'DROP CONSTRAINT `positive`' in source and 'DROP CHECK' not in source
    assert 'MODIFY COLUMN `id` bigint FIRST' in source
    assert 'ADD COLUMN `next_id` bigint GENERATED ALWAYS AS ((`id` + 1)) STORED AFTER `id`' in source
    assert preview['server_uid'] == 'native' and 'server_uuid' not in preview


def test_temporal_clauses_are_preserved_and_history_removal_is_not_inferred():
    before = model()
    table(before)['native']['definition'] = 'CREATE TABLE `a` (`id` int, `start` timestamp(6) GENERATED ALWAYS AS ROW START, `end` timestamp(6) GENERATED ALWAYS AS ROW END, PERIOD FOR SYSTEM_TIME (`start`,`end`)) WITH SYSTEM VERSIONING'
    desired = deepcopy(before)
    table(desired)['native']['definition'] = table(desired)['native']['definition'].replace('`id` int', '`id` bigint')
    assert 'temporal_history' in plan(before, desired, before)['blockers'][0]['reason']
    table(desired)['native']['mariadb_change'] = {'temporal_history': 'KEEP'}
    preview = plan(before, desired, before)
    assert preview['ready_for_review'] and preview['operations'][0]['source'].endswith('MODIFY COLUMN `id` bigint FIRST')
    table(desired)['native']['definition'] = table(desired)['native']['definition'].replace(' WITH SYSTEM VERSIONING', '')
    assert 'system versioning' in plan(before, desired, before)['blockers'][0]['reason']


def test_application_period_removal_requires_explicit_native_intent():
    before = model()
    table(before)['native']['definition'] = 'CREATE TABLE `a` (`id` int, `start` date, `end` date, PERIOD FOR `validity` (`start`,`end`)) ENGINE=InnoDB'
    desired = deepcopy(before)
    table(desired)['native']['definition'] = table(desired)['native']['definition'].replace(', PERIOD FOR `validity` (`start`,`end`)', '')
    assert plan(before, desired, before)['blockers']
    table(desired)['native']['mariadb_change'] = {'drop_periods': ['validity']}
    assert plan(before, desired, before)['operations'][0]['source'].endswith('DROP PERIOD FOR `validity`')


def test_filters_conflicts_and_exact_user_identity():
    before = model(); table(before)['native']['definition'] = 'CREATE TABLE `a` (`id` INT)'
    desired = deepcopy(before)
    table(desired)['native']['definition'] = table(desired)['native']['definition'].replace('INT', 'BIGINT')
    live = deepcopy(before); table(live)['native']['definition'] += " COMMENT='concurrent'"
    assert plan(before, desired, live)['conflicts']
    table(desired)['native']['database'] = 'wrong'
    assert plan(before, desired, before)['blockers']
    desired = deepcopy(before); del desired['rows'][table(desired)['resource_id']]
    preview = plan(before, desired, before)
    assert preview['ignored'] and not preview['operations']
    desired = deepcopy(before)
    desired['provenance']['mapping'] = 'scratchrobin.mysql.catalog@1'
    with pytest.raises(ValueError): plan(before, desired, before)


def test_explicit_column_and_table_drop_confirmations():
    before = model(); desired = deepcopy(before)
    table(before)['native']['definition'] = 'CREATE TABLE `a` (`id` int, `note` varchar(40))'
    table(desired)['native']['definition'] = 'CREATE TABLE `a` (`id` int)'
    assert plan(before, desired, before)['blockers']
    table(desired)['native']['mariadb_change'] = {'drop_columns': ['note']}
    assert 'DROP COLUMN `note`' in plan(before, desired, before)['operations'][0]['source']
    table(desired)['native']['mariadb_change'] = {'action': 'drop', 'confirmation': 'wrong'}
    assert plan(before, desired, before)['blockers']
    table(desired)['native']['mariadb_change']['confirmation'] = 'a'
    assert plan(before, desired, before)['operations'][0]['source'] == 'DROP TABLE `demo`.`a`'
