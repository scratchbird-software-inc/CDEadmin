"""TiDB administration rules added for MySQL-wire parity (2026-10-29)."""
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.tidb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402


def request(kind, operation, draft):
    return {'resource_kind': kind, 'operation_id': operation,
            'target_resource': None, '_provider_route': {'database': 'd1'},
            'draft': draft}


def plan(*args):
    return ADMINISTRATION.plan(request(*args))


def test_database_character_set_and_collation():
    assert [statement['source'] for statement in plan(
        'database', 'create', {'name': 'd1', 'character_set': 'utf8mb4',
                               'collation': 'utf8mb4_bin'})[
        'command_preview']['statements']] == [
        'CREATE DATABASE `d1` DEFAULT CHARACTER SET `utf8mb4` '
        'DEFAULT COLLATE `utf8mb4_bin`']


def test_grants_on_sequences_but_not_routines():
    assert plan('privilege', 'grant', {
        'principal': 'u@%', 'object_type': 'SEQUENCE', 'object_name': 'd1.s',
        'privileges': ['SELECT']})['command_preview']['statements']
    with pytest.raises(RelationalClientError, match='cannot grant'):
        plan('privilege', 'grant', {
            'principal': 'u@%', 'object_type': 'PROCEDURE',
            'object_name': 'd1.p', 'privileges': ['EXECUTE']})


class Connection:
    def __init__(self, enabled):
        self.enabled, self.closed = enabled, False

    def cursor(self):
        connection = self

        class Cursor:
            def execute(self, source):
                assert 'tidb_enable_check_constraint' in source

            def fetchone(self):
                return ('1' if connection.enabled else '0',)

            def close(self):
                pass
        return Cursor()


def test_check_constraints_are_refused_while_tidb_would_drop_them():
    draft = {'name': 't', 'parent': 'd1',
             'columns': [{'name': 'v', 'type': 'INT'}],
             'constraints': [{'kind': 'CHECK', 'name': 'ck',
                              'expression': 'v > 0'}]}
    planned = plan('table', 'create', draft)
    client = SimpleNamespace(_forget_and_close=lambda _connection: None)
    # The shape the visual-admin executor passes (the guard must read the
    # preview from the plan, not the top level).
    executed = {'plan': {'resource_kind': 'table', 'operation_id': 'create',
                         'draft': draft,
                         'command_preview': planned['command_preview']},
                'provider_payload': planned['provider_payload']}
    with pytest.raises(RelationalClientError,
                       match='tidb_enable_check_constraint'):
        ADMINISTRATION.apply(client, executed, connection=Connection(False))


def test_provider_action_without_its_plan_is_refused():
    planned = ADMINISTRATION.plan({
        'resource_kind': 'changefeed', 'operation_id': 'create',
        'target_resource': None,
        '_provider_route': {'database': 'd1',
                            'ticdc_sink_allowlist': 'blackhole://'},
        'draft': {'changefeed_id': 'c1', 'sink_uri': 'blackhole://'}})
    with pytest.raises(RelationalClientError, match='operation plan'):
        ADMINISTRATION.apply(SimpleNamespace(), planned)


TARGET_POLICY = {
    'resource_id': 'placement-policy:p', 'resource_kind': 'placement-policy',
    'display_name': 'p', 'display_path': ['p'],
    'authority_path': ['placement-policy', 'p'],
    'native': {'followers': 2, 'voters': 3, 'constraints': '[+disk=ssd]',
               'learners': 0, 'survival_preferences': '[region]'}}


def compiled(planned):
    return planned['provider_payload']['compiled']['statements'][0]


def test_placement_alter_carries_unedited_options_forward():
    statement = compiled(ADMINISTRATION.plan({
        'resource_kind': 'placement-policy', 'operation_id': 'alter',
        'target_resource': TARGET_POLICY,
        '_provider_route': {'database': 'd1'},
        'draft': {'placement_style': 'constraints', 'followers': 1}}))
    assert statement['source'] == (
        'ALTER PLACEMENT POLICY `p` FOLLOWERS = %s VOTERS = %s '
        'CONSTRAINTS = %s SURVIVAL_PREFERENCES = %s')
    assert tuple(statement['parameters']) == (
        1, 3, '[+disk=ssd]', '[region]')


def test_placement_styles_do_not_mix():
    with pytest.raises(RelationalClientError, match='placement style'):
        plan('placement-policy', 'create', {
            'name': 'p', 'schedule': 'even', 'constraints': '[+disk=ssd]'})
    with pytest.raises(RelationalClientError, match='learner replica'):
        plan('placement-policy', 'create', {
            'name': 'p', 'placement_style': 'constraints',
            'learner_constraints': '[+disk=ssd]'})


def test_runaway_query_limit():
    statement = compiled(plan('resource-group', 'create', {
        'name': 'g', 'ru_mode': 'limited', 'ru_per_sec': 10,
        'priority': 'LOW', 'query_limit_action': 'KILL',
        'query_limit_exec_elapsed': '1m30s'}))
    assert statement['source'].endswith(
        'QUERY_LIMIT = (EXEC_ELAPSED = %s, ACTION = KILL)')
    with pytest.raises(RelationalClientError, match='execution time'):
        plan('resource-group', 'create', {
            'name': 'g', 'ru_mode': 'unlimited', 'priority': 'LOW',
            'query_limit_action': 'KILL'})


@pytest.mark.parametrize('definitions', [
    'PARTITION p9 VALUES LESS THAN (9); DROP TABLE x',
    'p9 VALUES LESS THAN (9)',
    'PARTITION p9 VALUES LESS THAN (9',
])
def test_partition_definitions_stay_one_clause(definitions):
    target = {'resource_id': 'table:d1:t', 'resource_kind': 'table',
              'display_name': 't', 'display_path': ['d1', 't'],
              'authority_path': ['d1', 'table', 't']}
    with pytest.raises(RelationalClientError):
        ADMINISTRATION.plan({
            'resource_kind': 'table', 'operation_id': 'add_partitions',
            'target_resource': target,
            '_provider_route': {'database': 'd1'},
            'draft': {'definitions': definitions}})


def test_location_labels_accept_text_or_list():
    target = {'resource_id': 'table:d1:t', 'resource_kind': 'table',
              'display_name': 't', 'display_path': ['d1', 't'],
              'authority_path': ['d1', 'table', 't']}
    statement = compiled(ADMINISTRATION.plan({
        'resource_kind': 'table', 'operation_id': 'set_tiflash_replica',
        'target_resource': target, '_provider_route': {'database': 'd1'},
        'draft': {'replica_count': 2, 'location_labels': 'zone, rack'}}))
    assert tuple(statement['parameters']) == (2, 'zone', 'rack')


# Native administration verified live on TiDB 8.5.6 (2026-11-01).
TABLE = {'resource_id': 'table:d1:t', 'resource_kind': 'table',
         'display_name': 't', 'display_path': ['d1', 't']}
INDEX = {'resource_id': 'index:d1:t:k', 'resource_kind': 'index',
         'display_name': 'k', 'display_path': ['d1', 't', 'k']}
ROLE = {'resource_id': 'role:r@%', 'resource_kind': 'role',
        'display_name': 'r@%', 'display_path': ['r@%'],
        'native': {'user': 'r', 'host': '%'}}
USER = {'resource_id': 'user:u@%', 'resource_kind': 'user',
        'display_name': 'u@%', 'display_path': ['u@%'],
        'native': {'user': 'u', 'host': '%'}}
MEMBER = {'member_user': 'u', 'member_host': '%'}


def native(kind, operation, draft, target):
    planned = ADMINISTRATION.plan({**request(kind, operation, draft),
                                   'target_resource': target})
    return [(item['source'], tuple(item['parameters'])) for item in
            planned['provider_payload']['compiled']['statements']]


def test_tidb_table_options_caching_and_statistics():
    assert native('table', 'set_options', {
        'comment': 'c', 'collation': 'utf8mb4_bin',
        'shard_row_id_bits': 4}, TABLE) == [
        ('ALTER TABLE `d1`.`t` COMMENT = %s, DEFAULT COLLATE `utf8mb4_bin`',
         ('c',)),
        # TiDB refuses shard bits combined with any other change.
        ('ALTER TABLE `d1`.`t` SHARD_ROW_ID_BITS = 4', ())]
    assert native('table', 'set_options', {'shard_row_id_bits': 0},
                  TABLE) == [('ALTER TABLE `d1`.`t` SHARD_ROW_ID_BITS = 0',
                              ())]
    # TiDB reports AUTO_INCREMENT 0 in information_schema: not offered.
    with pytest.raises(RelationalClientError, match='auto_increment'):
        native('table', 'set_options', {'auto_increment': 9}, TABLE)
    assert native('table', 'analyze', {}, TABLE) == [
        ('ANALYZE TABLE `d1`.`t`', ())]
    assert native('table', 'set_cache', {'cached': 'ON'}, TABLE) == [
        ('ALTER TABLE `d1`.`t` CACHE', ())]
    assert native('table', 'set_cache', {'cached': 'OFF'}, TABLE) == [
        ('ALTER TABLE `d1`.`t` NOCACHE', ())]
    assert native('table', 'lock_stats', {}, TABLE) == [
        ('LOCK STATS `d1`.`t`', ())]
    assert native('table', 'unlock_stats', {}, TABLE) == [
        ('UNLOCK STATS `d1`.`t`', ())]


def test_tidb_index_rename_and_visibility():
    assert native('index', 'rename', {'new_name': 'k2'}, INDEX) == [
        ('ALTER TABLE `d1`.`t` RENAME INDEX `k` TO `k2`', ())]
    assert native('index', 'visibility', {'visibility': 'INVISIBLE'},
                  INDEX) == [
        ('ALTER TABLE `d1`.`t` ALTER INDEX `k` INVISIBLE', ())]


def test_tidb_accounts():
    assert native('role', 'grant', MEMBER, ROLE) == [
        ('GRANT %s@%s TO %s@%s', ('r', '%', 'u', '%'))]
    # TiDB refuses WITH ADMIN OPTION (syntax error, live): not declared,
    # and refused by the planner if sent anyway.
    assert [item['field_id'] for item in ADMINISTRATION.control_plane.
            operation('role', 'grant').fields] == [
        'member_user', 'member_host']
    with pytest.raises(RelationalClientError, match='delegated'):
        native('role', 'grant', {**MEMBER, 'admin_option': True}, ROLE)
    assert native('role', 'set_default', MEMBER, ROLE) == [
        ('SET DEFAULT ROLE %s@%s TO %s@%s', ('r', '%', 'u', '%'))]
    assert native('user', 'rename', {'new_user': 'v', 'new_host': '%'},
                  USER) == [
        ('RENAME USER %s@%s TO %s@%s', ('u', '%', 'v', '%'))]
    with pytest.raises(RelationalClientError, match='new account'):
        native('user', 'rename', {'new_user': 'u', 'new_host': '%'}, USER)


def test_tidb_confirmation_reads_the_engine_state():
    from pgadmin.cdeadmin.providers.tidb.provider import (
        NATIVE_ADMINISTRATION as tidb)
    analyze = {'resource_kind': 'table', 'operation_id': 'analyze',
               'target_resource': TABLE, 'draft': {}}
    assert tidb.confirmed(analyze, [('finished', 1)])
    assert not tidb.confirmed(analyze, [('finished', 0)])  # an older job
    assert not tidb.confirmed(analyze, [('failed', 1)])
    variable = {'resource_kind': 'system-variable',
                'operation_id': 'set_global',
                'target_resource': {'display_name': 'tidb_gc_life_time'},
                'draft': {'value': '20m'}}
    # TiDB stores 20m0s; another spelling is not claimed as confirmed.
    assert not tidb.confirmed(variable, [('20m0s',)])
    assert tidb.confirmed({**variable, 'draft': {'value': '20m0s'}},
                          [('20m0s',)])


# Row expiry, plan bindings and table recovery (live, 2026-11-01).
DIGEST = '6e494bcc6c58bcb2e11bbb388064f5437c33bde60dc23619c8a47378b0cecd3f'
BINDING = {'resource_id': 'binding:' + DIGEST, 'resource_kind': 'binding',
           'display_name': DIGEST, 'display_path': [DIGEST]}
DATABASE = {'resource_id': 'database:d1', 'resource_kind': 'database',
            'display_name': 'd1', 'display_path': ['d1']}


def test_tidb_ttl():
    assert native('table', 'set_ttl', {
        'column': 'created', 'interval': 3, 'unit': 'DAY', 'enabled': False,
        'job_interval': '2h'}, TABLE) == [(
            "ALTER TABLE `d1`.`t` TTL = `created` + INTERVAL 3 DAY "
            "TTL_ENABLE = 'OFF' TTL_JOB_INTERVAL = '2h'", ())]
    assert native('table', 'remove_ttl', {}, TABLE) == [
        ('ALTER TABLE `d1`.`t` REMOVE TTL', ())]
    for bad in ({'unit': 'FORTNIGHT'}, {'interval': 0},
                {'job_interval': '1 hour'}):
        with pytest.raises(RelationalClientError):
            native('table', 'set_ttl', {
                'column': 'created', 'interval': 3, **bad}, TABLE)
    from pgadmin.cdeadmin.providers.tidb.provider import (
        NATIVE_ADMINISTRATION as tidb)
    created = ('CREATE TABLE `t` (\n  `created` datetime\n) ENGINE=InnoDB '
               "/*T![ttl] TTL=`created` + INTERVAL 3 DAY */ /*T![ttl] "
               "TTL_ENABLE='OFF' */ /*T![ttl] TTL_JOB_INTERVAL='2h' */")
    ttl = {'resource_kind': 'table', 'operation_id': 'set_ttl',
           'target_resource': TABLE, 'draft': {
               'column': 'created', 'interval': 3, 'unit': 'DAY',
               'enabled': False, 'job_interval': '2h'}}
    assert tidb.confirmed(ttl, [('t', created)])
    assert not tidb.confirmed(ttl, [('t', created.replace("'OFF'",
                                                          "'ON'"))])
    removed = {'resource_kind': 'table', 'operation_id': 'remove_ttl',
               'target_resource': TABLE, 'draft': {}}
    assert not tidb.confirmed(removed, [('t', created)])
    assert tidb.confirmed(removed, [('t', 'CREATE TABLE `t` (x int)')])


def test_tidb_plan_bindings():
    assert native('binding', 'create', {
        'original_sql': 'SELECT * FROM t WHERE v = 1;',
        'bind_sql': 'SELECT /*+ USE_INDEX(t, kv) */ * FROM t WHERE v = 1'},
        None) == [(
            'CREATE GLOBAL BINDING FOR SELECT * FROM t WHERE v = 1 USING '
            'SELECT /*+ USE_INDEX(t, kv) */ * FROM t WHERE v = 1', ())]
    for original in ('SELECT 1; DROP TABLE t', 'DROP TABLE t'):
        with pytest.raises(RelationalClientError, match='binding'):
            native('binding', 'create', {'original_sql': original,
                                         'bind_sql': 'SELECT 1'}, None)
    with pytest.raises(RelationalClientError):  # required field
        native('binding', 'create', {'original_sql': '',
                                     'bind_sql': 'SELECT 1'}, None)
    assert native('binding', 'set_status', {'status': 'DISABLED'},
                  BINDING) == [
        (f"SET BINDING DISABLED FOR SQL DIGEST '{DIGEST}'", ())]
    assert native('binding', 'drop', {}, BINDING) == [
        (f"DROP GLOBAL BINDING FOR SQL DIGEST '{DIGEST}'", ())]
    with pytest.raises(RelationalClientError, match='digest'):
        native('binding', 'drop', {}, {**BINDING,
                                       'display_name': "x' OR 1"})
    from pgadmin.cdeadmin.providers.tidb.provider import (
        NATIVE_ADMINISTRATION as tidb)
    create = {'resource_kind': 'binding', 'operation_id': 'create',
              'target_resource': None, 'draft': {
                  'original_sql': 'SELECT 1', 'bind_sql': 'SELECT 1'}}
    assert tidb.confirmed(create, [(1, True)])
    assert not tidb.confirmed(create, [(0, True)])
    assert not tidb.confirmed(create, [(1, False)])  # older binding's plan
    statements = []

    def sequence(plans):
        def run(items):
            statements.extend(items)
            return {'rows': [], 'results': plans}
        return run
    plan_a, plan_b = [('IndexReader', 'index:kv')], [('TableReader', '')]
    observed = tidb.inspect(create, None, sequence=sequence(
        [[], plan_a, [], plan_a, [(1,)]]))
    assert observed['rows'] == [(1, True)]
    assert [source for source, _ in statements] == [
        'SET SESSION tidb_use_plan_baselines = OFF',
        "EXPLAIN FORMAT='brief' SELECT 1",
        'SET SESSION tidb_use_plan_baselines = ON',
        "EXPLAIN FORMAT='brief' SELECT 1",
        'SELECT @@last_plan_from_binding']
    assert tidb.inspect(create, None, sequence=sequence(
        [[], plan_a, [], plan_b, [(1,)]]))['rows'] == [(1, False)]


def test_tidb_flashback_table():
    assert native('database', 'flashback_table', {
        'table': 't', 'new_name': 't_back'}, DATABASE) == [
        ('FLASHBACK TABLE `d1`.`t` TO `t_back`', ())]
    assert native('database', 'flashback_table', {'table': 't'},
                  DATABASE) == [('FLASHBACK TABLE `d1`.`t`', ())]


def test_tidb_split_regions():
    assert native('table', 'split_regions', {
        'method': 'even', 'lower': -5000, 'upper': 5000, 'regions': 3},
        TABLE) == [('SPLIT TABLE `d1`.`t` BETWEEN (-5000) AND (5000) '
                    'REGIONS 3', ())]
    assert native('table', 'split_regions', {
        'method': 'points', 'points': '250, -7,100,100'}, TABLE) == [
        ('SPLIT TABLE `d1`.`t` BY (-7), (100), (250)', ())]
    for bad in ({'method': 'even', 'lower': 0, 'upper': 1000,
                 'regions': 3},  # regions under 1000 handles
                {'method': 'even', 'lower': 0, 'upper': 10 ** 7,
                 'regions': 1001},
                {'method': 'even', 'lower': 0, 'upper': True, 'regions': 2},
                {'method': 'points', 'points': '1; DROP TABLE t'},
                {'method': 'points', 'points': str(2 ** 63)}):
        with pytest.raises(RelationalClientError):
            native('table', 'split_regions', bad, TABLE)
    from pgadmin.cdeadmin.providers.mysql_wire_administration import (
        split_boundaries, split_confirmed)
    # TiDB's spacing, read live: -5000..5000 in 3 split at -1667 and 1666.
    assert split_boundaries({'method': 'even', 'lower': -5000,
                             'upper': 5000, 'regions': 3}) == (-1667, 1666)
    draft = {'method': 'points', 'points': '5, 9'}
    assert split_confirmed(draft, [(42, 't_42_'), (42, 't_42_r_5'),
                                   (42, 't_42_r_9')])
    assert not split_confirmed(draft, [(42, 't_42_'), (42, 't_42_r_5')])
    assert not split_confirmed(draft, [(None, 't_42_r_5')])


def _create_sql(**values):
    from pgadmin.cdeadmin.providers.tidb.provider import ADMINISTRATION
    request = {'resource_kind': 'table', 'operation_id': 'create',
               'target_resource': None, 'draft': {
                   'name': 't', 'options': {'parent': 'd1', **values}}}
    errors = ADMINISTRATION.validate(request)['errors']
    if errors:
        raise RelationalClientError('; '.join(
            str(error['message']) for error in errors))
    return [item['source'] if isinstance(item, dict) else item
            for item in ADMINISTRATION._compile_create(request)]


def test_tidb_row_id_sharding_create_sql():
    assert _create_sql(columns=[
        {'name': 'id', 'type': 'BIGINT', 'nullable': False,
         'primary_key': True, 'auto_random': 5, 'auto_random_range': 54}],
        pre_split_regions=3) == [
        'CREATE TABLE `d1`.`t` (`id` BIGINT NOT NULL PRIMARY KEY '
        'AUTO_RANDOM(5, 54)) PRE_SPLIT_REGIONS = 3']
    assert _create_sql(columns=[{'name': 'v', 'type': 'INT'}],
                       shard_row_id_bits=4, pre_split_regions=2) == [
        'CREATE TABLE `d1`.`t` (`v` INT) SHARD_ROW_ID_BITS = 4, '
        'PRE_SPLIT_REGIONS = 2']
    for values, reason in (
            ({'shard_row_id_bits': 16}, '1 to 15'),
            ({'shard_row_id_bits': True}, 'integer'),
            ({'columns': [{'name': 'id', 'type': 'BIGINT',
                           'auto_random_range': 54}]}, 'needs the options'),
            ({'columns': [{'name': 'id', 'type': 'BIGINT',
                           'auto_random': 5, 'auto_random_range': 31}]},
             '32 to 64'),
            ({'pre_split_regions': 2}, 'drops PRE_SPLIT_REGIONS'),
            ({'shard_row_id_bits': 2, 'pre_split_regions': 5},
             'cuts PRE_SPLIT_REGIONS')):
        with pytest.raises(RelationalClientError, match=reason):
            _create_sql(**{'columns': [{'name': 'v', 'type': 'INT'}],
                           **values})


class _Rows:
    def __init__(self, source):
        self.source = source

    def cursor(self):
        return self

    def execute(self, _statement):
        pass

    def fetchall(self):
        return [('t', self.source)]

    def close(self):
        pass


def test_tidb_sharding_facts_parse_and_unread():
    from pgadmin.cdeadmin.providers.tidb.provider import _sharding_facts
    source = ('CREATE TABLE `t` (\n  `id` bigint NOT NULL /*T![auto_rand] '
              'AUTO_RANDOM(5, 54) */,\n  `v` int DEFAULT NULL\n) ENGINE=InnoDB'
              ' /*T! PRE_SPLIT_REGIONS=3 */')
    table = {'display_path': ['d1', 't'], 'native': {
        'row_id_sharding': 'PK_AUTO_RANDOM_BITS=5, RANGE BITS=54'}}
    column = {'display_path': ['d1', 't', 'id'], 'native': {}}
    _sharding_facts(_Rows(source), table, {('d1', 't', 'id'): column})
    assert (table['native']['sharding_options_read'],
            table['native']['pre_split_regions']) == (True, 3)
    assert (column['native']['auto_random'],
            column['native']['auto_random_range']) == (5, 54)
    # A rendering that does not match TIDB_ROW_ID_SHARDING_INFO is unread,
    # never zero or empty.
    table = {'display_path': ['d1', 't'], 'native': {
        'row_id_sharding': 'SHARD_BITS=4'}}
    _sharding_facts(_Rows('CREATE TABLE `t` (x int) SHARD_ROW_ID_BITS=4'),
                    table, {})
    assert table['native']['sharding_options_read'] is False
    assert 'shard_row_id_bits' not in table['native']
    table = {'display_path': ['d1', 't'], 'native': {
        'row_id_sharding': 'NOT_SHARDED'}}
    _sharding_facts(None, table, {})  # not sharded: nothing to read
    assert 'sharding_options_read' not in table['native']
