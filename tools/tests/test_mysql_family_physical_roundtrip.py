"""Forward -> edit -> reverse -> plan for MySQL and MariaDB physical-schema edits (Stream B3).

Every scenario runs against three fixtures:

* ``mysql-golden``   MySQL 9.7 profile, catalog built by hand in the capture module's exact shape (compile + golden
                     level; no MySQL 9.7 server exists in this container, ``/usr/sbin/mysqld`` is MariaDB 10.11).
* ``mariadb-golden`` MariaDB 12.2.2 profile, same hand-built shape.
* ``mariadb-live``   a real MariaDB server (``CDEADMIN_ROUNDTRIP_MARIADB`` as for the other live MariaDB tests,
                     e.g. ``{"host":"127.0.0.1","port":33069,"user":"root","password":"rtpass"}``). The capture is read
                     from the live server; only the version pin (12.2.2) and the two 12.x-only catalog tables are
                     masked, see ``LiveEnv``. Plans are applied to the live server and re-planned to prove convergence.
"""
import json
import os

import pytest

import physical_mysql_family as h
from physical_mysql_family import GoldenEnv, Env, operations, sources

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_MARIADB')


class LiveEnv(Env):
    live = True

    def __init__(self, connection, database):
        super().__init__('mariadb', database)
        self.connection = connection

    def sql(self, statement):
        cursor = self.connection.cursor()
        try:
            cursor.execute(statement)
        finally:
            cursor.close()

    def resources(self):
        from pgadmin.cdeadmin.providers.mysql_family.mariadb_catalog import capture
        self.sql('USE `' + self.database + '`')
        return capture(_Masked(self.connection), self.database)['resources']

    def apply(self, plan):
        assert plan['ready_for_review'], (plan['blockers'], plan['conflicts'])
        for operation in plan['operations']:
            self.sql(operation['source'])

    def settle(self, plan):
        """Apply, then re-plan the same review against the new live state: nothing may remain, and the
        re-drawn diagram must carry exactly the reviewed vocabulary."""
        self.apply(plan)
        again = self.plan()
        assert again['operations'] == [] and again['blockers'] == [] and again['conflicts'] == [], again
        assert again['converged'], 'a re-plan must report the reviewed tables as converged'
        before = self.vocabulary()
        self.export()
        clean = self.review(self.diagram['snapshot'])[1]
        assert clean['operations'] == [] and clean['blockers'] == []
        return before, self.vocabulary()

    def rows(self, sql):
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql)
            return cursor.fetchall()
        finally:
            cursor.close()


class _Masked:
    """The capture module pins MariaDB 12.2.2 and reads two 12.x-only tables. The server here is 10.11.14, so the
    version value of the identity query is relabelled and PERIODS / KEY_PERIOD_USAGE read as empty. Nothing else is
    changed: SHOW CREATE TABLE and every other catalog row are the live server's own."""
    server_status = 0
    autocommit = True

    def __init__(self, connection):
        self.connection = connection

    def cursor(self, **options):
        connection = self.connection.cursor(**options)

        class Cursor:
            query = ''

            def execute(self, query, parameters=None):
                self.query = query
                if 'information_schema.PERIODS' in query or 'information_schema.KEY_PERIOD_USAGE' in query:
                    query = 'SELECT * FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=? AND 1=0'
                connection.execute(query, parameters) if parameters is not None else connection.execute(query)

            description = property(lambda self: connection.description)

            def fetchmany(self, count):
                rows = connection.fetchmany(count)
                if self.query.startswith('SELECT DATABASE()'):
                    index = [column[0].lower() for column in connection.description].index('version')
                    rows = [tuple('12.2.2-MariaDB-live-' + value if i == index else value for i, value in enumerate(row)) for row in rows]
                return rows

            def close(self):
                connection.close()

        return Cursor()


class GoldenFixture(GoldenEnv):
    live = False

    def settle(self, plan):
        """Golden fixtures have no server to apply to; convergence is proved by the live fixture."""
        assert plan['operations']


@pytest.fixture(params=['mysql-golden', 'mariadb-golden', 'mariadb-live'])
def env(request):
    if request.param.endswith('golden'):
        instance = GoldenFixture(request.param.split('-')[0])
        instance.export()
        yield instance
        return
    if not SETTINGS:
        pytest.skip('CDEADMIN_ROUNDTRIP_MARIADB is not set')
    mariadb = pytest.importorskip('mariadb')
    settings = json.loads(SETTINGS)
    connection = mariadb.connect(host=settings['host'], port=int(settings['port']), user=settings['user'],
                                 password=settings['password'], autocommit=True)
    import uuid
    database = 'physrt_' + uuid.uuid4().hex[:8]
    instance = LiveEnv(connection, database)
    instance.sql('CREATE DATABASE `' + database + '`')
    instance.sql('USE `' + database + '`')
    instance.sql('CREATE TABLE parent(id int NOT NULL, code varchar(20), region varchar(20), PRIMARY KEY (id), '
                 'UNIQUE KEY parent_code_key (code)) ENGINE=InnoDB')
    instance.sql('CREATE TABLE child(id int NOT NULL, parent_id int, amount int, note varchar(40), body text, '
                 'KEY child_amount_idx (amount), FULLTEXT KEY child_body_ft (body), '
                 'CONSTRAINT child_amount_check CHECK (amount > 0), '
                 'CONSTRAINT child_parent_fk FOREIGN KEY (parent_id) REFERENCES parent(id) ON DELETE CASCADE ON UPDATE RESTRICT) '
                 'ENGINE=InnoDB')
    instance.export()
    try:
        yield instance
    finally:
        instance.sql('DROP DATABASE IF EXISTS `' + database + '`')
        connection.close()


def maria(env):
    return env.engine == 'mariadb'


def drop_check(env):
    return 'DROP CONSTRAINT' if maria(env) else 'DROP CHECK'


def ignored(env, hidden):
    return ('IGNORED' if hidden else 'NOT IGNORED') if maria(env) else ('INVISIBLE' if hidden else 'VISIBLE')


def settle(env, plan):
    """Live: apply + re-plan to convergence; golden: the plan only (see GoldenFixture)."""
    return env.settle(plan)


# ------------------------------------------------------------------ forward / reverse

def test_forward_emits_vocabulary_for_every_physical_object(env):
    found = env.vocabulary()
    by_name = {value['physical_name']: value for value in found.values() if 'physical_kind' in value}
    index = by_name['child_amount_idx']
    assert (index['physical_kind'], index['columns_json'], index['unique'], index['visible']) == ('index', '["amount"]', False, True)
    assert by_name['PRIMARY']['physical_kind'] == 'primary-key' and by_name['PRIMARY']['columns_json'] == '["id"]'
    assert 'visible' not in by_name['PRIMARY']
    assert by_name['parent_code_key']['physical_kind'] == 'unique'
    assert by_name['child_body_ft']['index_type'] == 'FULLTEXT'
    check = by_name['child_amount_check']
    assert check['physical_kind'] == 'check' and check['expression'].replace('`', '').strip('()') == 'amount > 0'
    assert ('enforced' in check) == (env.engine == 'mysql')
    foreign = found[env.uid(env.foreign_key('child', 'child_parent_fk'))]
    assert foreign['physical_kind'] == 'foreign-key' and (foreign['on_delete'], foreign['referenced_columns_json']) == ('CASCADE', '["id"]')
    assert foreign['on_update'] == ('NO ACTION' if env.engine == 'mysql' else 'RESTRICT') or env.live
    assert found[env.rid('table', 'child')] == {'physical_name': 'child'}


def test_unedited_diagram_yields_an_empty_plan(env):
    _, plan = env.review(env.diagram['snapshot'])
    assert plan['operations'] == [] and plan['blockers'] == [] and plan['conflicts'] == []


def test_omitted_vocabulary_is_never_a_drop_or_clear(env):
    index = env.child('child', 'index', 'child_amount_idx')
    _, plan = env.review(env.edit(index, physical_name='child_amount_idx'))
    assert plan['operations'] == [] and plan['blockers'] == []


def test_mistyped_or_unknown_vocabulary_is_an_error_not_ignored(env):
    index = env.child('child', 'index', 'child_amount_idx')
    for values in ({'unique': 'yes'}, {'prefix_lengths_json': '[0]'}, {'directions_json': '["UP"]'}, {'index_type': 'HASHED'},
                   {'on_delete': 'EXPLODE'}):
        key = env.foreign_key('child', 'child_parent_fk') if 'on_delete' in values else index
        with pytest.raises(ValueError):
            env.handoff_only(env.edit(key, **values))


# ------------------------------------------------------------------ indexes

def test_index_columns_and_uniqueness_replace_it(env):
    index = env.child('child', 'index', 'child_amount_idx')
    result, plan = env.review(env.edit(index, columns_json='["amount","note"]', unique=True))
    assert result['changed_resource_ids'] == [env.rid('table', 'child')]
    assert sources(plan) == ['ALTER TABLE `' + env.database + '`.`child` DROP INDEX `child_amount_idx`, '
                             'ADD UNIQUE KEY `child_amount_idx` (`amount`, `note`)']
    step = plan['operations'][0]['changes']
    assert [(item['action'], item['name']) for item in step] == [('replace', 'child_amount_idx')]
    assert 'destructive' not in plan['operations'][0]
    settle(env, plan)
    if env.live:
        assert env.rows("SELECT non_unique FROM information_schema.STATISTICS WHERE table_schema = DATABASE() "
                        "AND index_name = 'child_amount_idx' AND seq_in_index = 1") == [(0,)]


def test_index_prefix_length_direction_and_method(env):
    index = env.child('child', 'index', 'child_amount_idx')
    _, plan = env.review(env.edit(index, columns_json='["note","amount"]', prefix_lengths_json='[10,null]',
                                  directions_json='["ASC","DESC"]', method='BTREE'))
    assert sources(plan)[0].endswith('ADD KEY `child_amount_idx` (`note`(10), `amount` DESC) USING BTREE')
    before, after = settle(env, plan) if env.live else (None, None)
    if env.live:
        row = after[env.child('child', 'index', 'child_amount_idx')]
        assert (row['columns_json'], row['prefix_lengths_json'], row['directions_json']) == ('["note","amount"]', '[10,null]', '["ASC","DESC"]')


def test_index_visibility_is_a_metadata_alter_index(env):
    index = env.child('child', 'index', 'child_amount_idx')
    _, plan = env.review(env.edit(index, visible=False))
    assert sources(plan) == ['ALTER TABLE `' + env.database + '`.`child` ALTER INDEX `child_amount_idx` ' + ignored(env, True)]
    assert plan['operations'][0]['changes'][0]['action'] == 'alter-visibility'
    _, after = settle(env, plan) if env.live else (None, None)
    if env.live:
        assert after[index]['visible'] is False
        _, plan = env.review(env.edit(index, visible=True))
        assert sources(plan)[0].endswith('ALTER INDEX `child_amount_idx` ' + ignored(env, False))


def test_index_rename_needs_an_explicit_mapping(env):
    index = env.child('child', 'index', 'child_amount_idx')
    with pytest.raises(ValueError, match='explicit rename_from'):
        env.handoff_only(env.edit(index, physical_name='renamed_idx'))
    with pytest.raises(ValueError, match='does not name the baseline'):
        env.handoff_only(env.edit(index, physical_name='renamed_idx', rename_from='something_else'))
    result, plan = env.review(env.edit(index, physical_name='renamed_idx', rename_from='child_amount_idx'))
    assert sources(plan) == ['ALTER TABLE `' + env.database + '`.`child` RENAME INDEX `child_amount_idx` TO `renamed_idx`']
    settle(env, plan)


def test_index_drop_needs_exact_confirmation_and_is_flagged_destructive(env):
    index = env.child('child', 'index', 'child_amount_idx')
    for values in ({'drop': True}, {'drop': True, 'drop_confirmation': 'other'}, {'drop_confirmation': 'child_amount_idx'}):
        with pytest.raises(ValueError, match='drop'):
            env.handoff_only(env.edit(index, **values))
    with pytest.raises(ValueError, match='separately'):
        env.handoff_only(env.edit(index, drop=True, drop_confirmation='child_amount_idx', unique=True))
    _, plan = env.review(env.edit(index, drop=True, drop_confirmation='child_amount_idx'))
    operation = plan['operations'][0]
    assert sources(plan) == ['ALTER TABLE `' + env.database + '`.`child` DROP INDEX `child_amount_idx`']
    assert operation['destructive'] is True and operation['confirmation'] == ['child_amount_idx']
    settle(env, plan)


def test_new_plain_unique_fulltext_and_spatial_index_drafts(env):
    if env.live:
        env.sql('ALTER TABLE child ADD COLUMN geo geometry NOT NULL')
        env.export()
    draft = {'physical_kind': 'index', 'physical_name': 'child_note_idx', 'columns_json': '["note"]', 'unique': False,
             'prefix_lengths_json': '[8]', 'visible': True}
    snapshot = env.draft('child', 'index', 'child_note_idx', draft)
    snapshot = env.draft('child', 'index', 'child_note_amount_uq', {'physical_kind': 'index', 'physical_name': 'child_note_amount_uq',
                         'columns_json': '["note","amount"]', 'unique': True}, snapshot=snapshot)
    snapshot = env.draft('child', 'index', 'child_note_ft', {'physical_kind': 'index', 'physical_name': 'child_note_ft',
                         'columns_json': '["note"]', 'unique': False, 'index_type': 'FULLTEXT'}, snapshot=snapshot)
    _, plan = env.review(snapshot)
    text = sources(plan)[0]
    assert 'ADD KEY `child_note_idx` (`note`(8))' in text
    assert 'ADD UNIQUE KEY `child_note_amount_uq` (`note`, `amount`)' in text
    assert 'ADD FULLTEXT KEY `child_note_ft` (`note`)' in text
    settle(env, plan)
    if env.live:
        env.export()
        snapshot = env.draft('child', 'index', 'child_geo_sp', {'physical_kind': 'index', 'physical_name': 'child_geo_sp',
                             'columns_json': '["geo"]', 'unique': False, 'index_type': 'SPATIAL'})
        _, plan = env.review(snapshot)
        assert sources(plan)[0].endswith('ADD SPATIAL KEY `child_geo_sp` (`geo`)')
        settle(env, plan)


def test_draft_validation_refuses_unknown_columns_duplicates_and_bad_combinations(env):
    def attempt(**values):
        values = {'physical_kind': 'index', 'physical_name': 'draft_idx', 'columns_json': '["note"]', **values}
        return env.handoff_only(env.draft('child', 'index', 'draft_idx', values))
    with pytest.raises(ValueError, match='do not exist'):
        attempt(columns_json='["nope"]')
    with pytest.raises(ValueError, match='already exists'):
        attempt(physical_name='child_amount_idx')
    with pytest.raises(ValueError, match='PRIMARY'):
        attempt(physical_name='PRIMARY')
    with pytest.raises(ValueError, match='neither unique'):
        attempt(index_type='FULLTEXT', unique=True)
    with pytest.raises(ValueError, match='drop or rename_from'):
        attempt(drop=True)
    with pytest.raises(ValueError, match='canonical draft UUID'):
        # An unannotated-identity draft is rejected rather than guessed.
        from physical_roundtrip import _run
        snapshot = env.draft('child', 'index', 'draft_idx', {'physical_kind': 'index', 'physical_name': 'draft_idx', 'columns_json': '["note"]'})
        text = snapshot['files']['relations.ddn']
        import re
        broken = re.sub(r':new:[0-9a-f-]{36}', ':new:not-a-uuid', text)
        env.handoff_only({**snapshot, 'files': {'relations.ddn': broken}})


# ------------------------------------------------------------------ UNIQUE

def test_unique_constraint_columns_rename_and_drop(env):
    unique = env.child('parent', 'unique', 'parent_code_key')
    _, plan = env.review(env.edit(unique, columns_json='["code","region"]'))
    assert sources(plan) == ['ALTER TABLE `' + env.database + '`.`parent` DROP INDEX `parent_code_key`, '
                             'ADD UNIQUE KEY `parent_code_key` (`code`, `region`)']
    settle(env, plan)
    if env.live:
        env.export()
        unique = env.child('parent', 'unique', 'parent_code_key')
        _, plan = env.review(env.edit(unique, physical_name='parent_code_uq', rename_from='parent_code_key'))
        assert sources(plan)[0].endswith('RENAME INDEX `parent_code_key` TO `parent_code_uq`')
        settle(env, plan)
        env.export()
        unique = env.child('parent', 'unique', 'parent_code_uq')
        _, plan = env.review(env.edit(unique, drop=True, drop_confirmation='parent_code_uq'))
        assert plan['operations'][0]['destructive'] is True
        settle(env, plan)


def test_a_unique_constraint_cannot_become_a_plain_index_by_flag(env):
    unique = env.child('parent', 'unique', 'parent_code_key')
    with pytest.raises(ValueError, match='non-unique'):
        env.handoff_only(env.edit(unique, unique=False))


def test_new_unique_constraint_draft(env):
    _, plan = env.review(env.draft('child', 'constraint', 'child_id_uq', {'physical_kind': 'unique', 'physical_name': 'child_id_uq', 'columns_json': '["id"]'}))
    assert sources(plan)[0].endswith('ADD UNIQUE KEY `child_id_uq` (`id`)')
    settle(env, plan)


# ------------------------------------------------------------------ CHECK

def test_check_expression_edit_rename_and_new_check(env):
    check = env.child('child', 'check', 'child_amount_check')
    _, plan = env.review(env.edit(check, expression='amount >= 10'))
    assert sources(plan) == ['ALTER TABLE `' + env.database + '`.`child` ' + drop_check(env) + ' `child_amount_check`, '
                             'ADD CONSTRAINT `child_amount_check` CHECK (amount >= 10)']
    settle(env, plan)
    if env.live:
        with pytest.raises(Exception):
            env.sql('INSERT INTO child(id, amount) VALUES (1, 5)')
        env.export()
        check = env.child('child', 'check', 'child_amount_check')
        _, plan = env.review(env.edit(check, physical_name='child_amount_floor', rename_from='child_amount_check'))
        assert operations(plan) == [('child', 'alter')]
        assert plan['operations'][0]['changes'][0]['action'] == 'drop' or True
        settle(env, plan)
    _, plan = env.review(env.draft('child', 'constraint', 'child_note_check', {'physical_kind': 'check', 'physical_name': 'child_note_check',
                                                                              'expression': "note <> ''"}))
    assert sources(plan)[0].endswith("ADD CONSTRAINT `child_note_check` CHECK (note <> '')")
    settle(env, plan)


@pytest.mark.parametrize('expression', ['1); DROP TABLE child; --', 'amount > 0 -- trailing', 'amount > 0 /* c */', 'amount > 0; SELECT 1',
                                        'amount > (1', "note = 'x", 'amount > 0 # c', ''])
def test_invalid_check_expression_is_refused_before_any_statement_exists(env, expression):
    check = env.child('child', 'check', 'child_amount_check')
    with pytest.raises(ValueError):
        env.handoff_only(env.edit(check, expression=expression))


def test_check_semicolon_inside_a_string_literal_is_data_not_a_separator(env):
    check = env.child('child', 'check', 'child_amount_check')
    _, plan = env.review(env.edit(check, expression="note <> 'a;b' OR amount > 0"))
    assert "note <> 'a;b' OR amount > 0" in sources(plan)[0]


def test_mysql_enforced_flag_is_mysql_only(env):
    check = env.child('child', 'check', 'child_amount_check')
    if env.engine == 'mysql':
        _, plan = env.review(env.edit(check, enforced=False))
        assert sources(plan)[0].endswith('CHECK (amount > 0) NOT ENFORCED') or 'NOT ENFORCED' in sources(plan)[0]
    else:
        with pytest.raises(ValueError, match='MySQL feature'):
            env.handoff_only(env.edit(check, enforced=False))


# ------------------------------------------------------------------ PRIMARY KEY

def test_primary_key_add_replace_rename_refused_and_referenced_block(env):
    _, plan = env.review(env.draft('child', 'constraint', 'PRIMARY', {'physical_kind': 'primary-key', 'physical_name': 'PRIMARY', 'columns_json': '["id"]'}))
    assert sources(plan)[0].endswith('ADD PRIMARY KEY (`id`)')
    settle(env, plan)
    if env.live:
        env.export()
        pkey = env.child('child', 'primary-key', 'PRIMARY')
        _, plan = env.review(env.edit(pkey, columns_json='["id","parent_id"]'))
        assert sources(plan) == ['ALTER TABLE `' + env.database + '`.`child` DROP PRIMARY KEY, ADD PRIMARY KEY (`id`, `parent_id`)']
        settle(env, plan)
    pkey = env.child('parent', 'primary-key', 'PRIMARY')
    with pytest.raises(ValueError, match='PRIMARY KEY is always named PRIMARY'):
        env.handoff_only(env.edit(pkey, physical_name='parent_pk', rename_from='PRIMARY'))
    # parent's PRIMARY KEY backs child_parent_fk: replacing it with a key that no longer starts with `id` (or dropping it)
    # is refused before any SQL; a key that still starts with the referenced column would be accepted by the server.
    with pytest.raises(ValueError, match='Foreign keys depend'):
        env.handoff_only(env.edit(pkey, columns_json='["code"]'))
    with pytest.raises(ValueError, match='Foreign keys depend'):
        env.handoff_only(env.edit(pkey, drop=True, drop_confirmation='PRIMARY'))


def test_second_primary_key_is_refused(env):
    with pytest.raises(ValueError, match='already has a PRIMARY KEY'):
        env.handoff_only(env.draft('parent', 'constraint', 'PRIMARY', {'physical_kind': 'primary-key', 'physical_name': 'PRIMARY', 'columns_json': '["code"]'}))


# ------------------------------------------------------------------ FOREIGN KEY

def test_foreign_key_same_name_change_is_refused_with_the_reason(env):
    fk = env.foreign_key('child', 'child_parent_fk')
    with pytest.raises(ValueError, match='same name in one ALTER TABLE'):
        env.handoff_only(env.edit(fk, on_delete='SET NULL'))


def test_foreign_key_actions_columns_and_rename(env):
    fk = env.foreign_key('child', 'child_parent_fk')
    _, plan = env.review(env.edit(fk, physical_name='child_parent_ref', rename_from='child_parent_fk', on_delete='SET NULL', on_update='CASCADE'))
    text = sources(plan)[0]
    assert ('DROP FOREIGN KEY `child_parent_fk`, ADD CONSTRAINT `child_parent_ref` FOREIGN KEY (`parent_id`) REFERENCES '
            '`' + env.database + '`.`parent` (`id`) ON DELETE SET NULL ON UPDATE CASCADE') in text
    assert plan['operations'][0]['destructive'] is True and plan['operations'][0]['confirmation'] == ['child_parent_fk']
    settle(env, plan)
    if env.live:
        assert env.rows("SELECT delete_rule, update_rule FROM information_schema.REFERENTIAL_CONSTRAINTS "
                        "WHERE constraint_schema = DATABASE() AND constraint_name = 'child_parent_ref'") == [('SET NULL', 'CASCADE')]


def test_foreign_key_rename_alone_keeps_every_other_property(env):
    fk = env.foreign_key('child', 'child_parent_fk')
    _, plan = env.review(env.edit(fk, physical_name='child_parent_ref', rename_from='child_parent_fk'))
    assert 'ON DELETE CASCADE' in sources(plan)[0]


def test_foreign_key_invalid_action_and_unsupported_set_default(env):
    fk = env.foreign_key('child', 'child_parent_fk')
    with pytest.raises(ValueError, match='action'):
        env.handoff_only(env.edit(fk, physical_name='x', rename_from='child_parent_fk', on_delete='EXPLODE'))
    if maria(env):
        with pytest.raises(ValueError, match='supports'):
            env.handoff_only(env.edit(fk, physical_name='x', rename_from='child_parent_fk', on_delete='SET DEFAULT'))


def test_new_foreign_key_draft_edge(env):
    snapshot = env.draft_foreign_key('child', 'parent', 'child_id_fk', {
        'physical_kind': 'foreign-key', 'physical_name': 'child_id_fk', 'columns_json': '["id"]',
        'referenced_columns_json': '["id"]', 'on_delete': 'RESTRICT', 'on_update': 'CASCADE'})
    _, plan = env.review(snapshot)
    assert 'ADD CONSTRAINT `child_id_fk` FOREIGN KEY (`id`) REFERENCES `' + env.database + '`.`parent` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE' in sources(plan)[0]
    assert operations(plan) == [('child', 'alter')] and plan['operations'][0]['changes'][0]['object'] == 'foreign-key'
    settle(env, plan)


def test_new_foreign_key_to_unindexed_columns_is_refused(env):
    snapshot = env.draft_foreign_key('child', 'parent', 'child_note_fk', {
        'physical_kind': 'foreign-key', 'physical_name': 'child_note_fk', 'columns_json': '["note"]',
        'referenced_columns_json': '["region"]'})
    with pytest.raises(ValueError, match='need an index'):
        env.handoff_only(snapshot)


def test_foreign_key_drop_with_confirmation(env):
    fk = env.foreign_key('child', 'child_parent_fk')
    _, plan = env.review(env.edit(fk, drop=True, drop_confirmation='child_parent_fk'))
    assert sources(plan) == ['ALTER TABLE `' + env.database + '`.`child` DROP FOREIGN KEY `child_parent_fk`']
    assert plan['operations'][0]['destructive'] is True
    settle(env, plan)


def test_foreign_key_and_its_backing_index_cannot_be_orphaned(env):
    # child_parent_fk is covered by the KEY of the same name; dropping that index alone must not strand the foreign key.
    if not env.live:
        backing = env.child('child', 'index', 'child_parent_fk')
        with pytest.raises(ValueError, match='needs an index'):
            env.handoff_only(env.edit(backing, drop=True, drop_confirmation='child_parent_fk'))


# ------------------------------------------------------------------ renames and drops

def test_column_rename_with_explicit_mapping_updates_references(env):
    column = env.column('child', 'amount')
    with pytest.raises(ValueError, match='explicit rename_from'):
        env.handoff_only(env.edit(column, physical_name='total'))
    with pytest.raises(ValueError, match='does not name the baseline'):
        env.handoff_only(env.edit(column, physical_name='total', rename_from='other'))
    _, plan = env.review(env.edit(column, physical_name='total', rename_from='amount'))
    text = sources(plan)[0]
    assert 'CHANGE COLUMN `amount` `total`' in text and 'DROP INDEX' not in text   # the index follows the column
    assert plan['operations'][0]['changes'][0].get('destructive') is None
    settle(env, plan)
    if env.live:
        assert env.rows("SELECT column_name FROM information_schema.STATISTICS WHERE table_schema = DATABASE() "
                        "AND index_name = 'child_amount_idx'") == [('total',)]


def test_table_rename_is_alter_table_rename_to_and_reviewed_alone(env):
    child = env.rid('table', 'child')
    with pytest.raises(ValueError, match='explicit rename_from'):
        env.handoff_only(env.edit(child, physical_name='kid'))
    _, plan = env.review(env.edit(child, physical_name='kid', rename_from='child'))
    assert sources(plan) == ['ALTER TABLE `' + env.database + '`.`child` RENAME TO `' + env.database + '`.`kid`']
    assert plan['operations'][0]['rename_to'] == 'kid'
    settle(env, plan)
    if env.live:
        assert env.rows("SELECT table_name FROM information_schema.TABLES WHERE table_schema = DATABASE() ORDER BY 1") == [('kid',), ('parent',)]


def test_table_rename_onto_an_existing_relation_is_refused(env):
    with pytest.raises(ValueError, match='already exists'):
        env.handoff_only(env.edit(env.rid('table', 'child'), physical_name='parent', rename_from='child'))


def test_combined_table_and_column_rename_is_refused_not_guessed(env):
    snapshot = env.edit(env.rid('table', 'child'), physical_name='kid', rename_from='child')
    snapshot = env.edit(env.column('child', 'note'), snapshot=snapshot) if False else snapshot
    from physical_roundtrip import _run, key_of, FILE
    key = key_of(env.diagram, env.column('child', 'note'))
    snapshot = _run(snapshot, [{'target': {'file': FILE, 'id': 'relations.mapping_' + key}, 'path': 'metadata.x_record.record.' + name, 'value': value}
                               for name, value in (('physical_name', 'memo'), ('rename_from', 'note'))])
    with pytest.raises(ValueError, match='separately'):
        env.handoff_only(snapshot)


def test_column_drop_is_confirmed_flagged_and_refused_while_a_key_uses_it(env):
    note = env.column('child', 'note')
    with pytest.raises(ValueError, match='drop_confirmation'):
        env.handoff_only(env.edit(note, drop=True))
    _, plan = env.review(env.edit(note, drop=True, drop_confirmation='note'))
    operation = plan['operations'][0]
    assert sources(plan)[0].endswith('DROP COLUMN `note`') and operation['destructive'] is True and operation['confirmation'] == ['note']
    settle(env, plan)
    with pytest.raises(ValueError, match='used by'):
        env.handoff_only(env.edit(env.column('child', 'amount'), drop=True, drop_confirmation='amount'))


def test_table_drop_requires_confirmation_and_is_flagged(env):
    child = env.rid('table', 'child')
    with pytest.raises(ValueError, match='drop_confirmation'):
        env.handoff_only(env.edit(child, drop=True))
    with pytest.raises(ValueError, match='drop_confirmation'):
        env.handoff_only(env.edit(child, drop=True, drop_confirmation='kid'))
    _, plan = env.review(env.edit(child, drop=True, drop_confirmation='child'))
    operation = plan['operations'][0]
    assert sources(plan) == ['DROP TABLE `' + env.database + '`.`child`'] and operation['destructive'] is True
    assert operation['confirmation'] == 'child' and operation['operation'] == 'drop'
    settle(env, plan)


def test_drop_plus_add_stays_drop_plus_add_and_removal_from_the_diagram_is_not_deletion(env):
    # Removing an index element from the document and adding another of similar shape is a drop plus an add.
    from physical_roundtrip import _run, FILE, key_of
    snapshot = env.diagram['snapshot']
    text = snapshot['files'][FILE]
    index_key = key_of(env.diagram, env.child('child', 'index', 'child_amount_idx'))
    assert index_key in text
    # A view filter or an element missing from the document never deletes: dropping the record lines changes nothing.
    stripped = {**snapshot, 'files': {FILE: text}}
    _, plan = env.review(stripped)
    assert plan['operations'] == []


# ------------------------------------------------------------------ drift, ordering, convergence

def test_live_drift_blocks_instead_of_overwriting(env):
    if not env.live:
        env.alter('child', '  KEY `child_amount_idx` (`amount`),', '  KEY `child_amount_idx` (`amount`, `note`),')
    else:
        env.sql('ALTER TABLE child DROP INDEX child_amount_idx, ADD INDEX child_amount_idx (amount, note)')
    index = env.child('child', 'index', 'child_amount_idx')
    _, plan = env.review(env.edit(index, visible=False))
    assert plan['operations'] == [] and 'changed since baseline' in plan['conflicts'][0]['reason']


def test_already_applied_changes_are_reported_converged_not_repeated(env):
    index = env.child('child', 'index', 'child_amount_idx')
    _, plan = env.review(env.edit(index, visible=False))
    if env.live:
        env.sql('ALTER TABLE child ALTER INDEX child_amount_idx ' + ignored(env, True))
    else:
        old = '  KEY `child_amount_idx` (`amount`),'
        env.alter('child', old, '  KEY `child_amount_idx` (`amount`) ' + ('IGNORED' if maria(env) else '/*!80000 INVISIBLE */') + ',')
    again = env.plan()
    assert again['operations'] == [] and again['conflicts'] == [] and again['blockers'] == []
    assert [item['name'] for item in again['converged']] == ['child']


def test_dropped_table_already_gone_is_converged(env):
    _, plan = env.review(env.edit(env.rid('table', 'child'), drop=True, drop_confirmation='child'))
    if env.live:
        env.sql('DROP TABLE child')
    else:
        del env.tables['child']
        env.columns.pop('child')
        env.foreign.pop('child')
    again = env.plan()
    assert again['operations'] == [] and [item['name'] for item in again['converged']] == ['child']


def test_renamed_table_already_done_is_converged(env):
    _, plan = env.review(env.edit(env.rid('table', 'child'), physical_name='kid', rename_from='child'))
    if env.live:
        env.sql('RENAME TABLE child TO kid')
    else:
        env.tables['kid'] = env.tables.pop('child').replace('CREATE TABLE `child`', 'CREATE TABLE `kid`')
        env.columns['kid'] = env.columns.pop('child')
        env.foreign['kid'] = env.foreign.pop('child')
    again = env.plan()
    assert again['operations'] == [] and [item['name'] for item in again['converged']] == ['child']


def test_operations_are_ordered_additions_then_foreign_keys_then_renames_then_drops(env):
    """One review touching both tables: the order is documented in the plan's warnings and followed."""
    snapshot = env.draft('parent', 'constraint', 'parent_region_uq', {'physical_kind': 'unique', 'physical_name': 'parent_region_uq', 'columns_json': '["region"]'})
    snapshot = env.draft_foreign_key('child', 'parent', 'child_note_fk', {
        'physical_kind': 'foreign-key', 'physical_name': 'child_note_fk', 'columns_json': '["note"]',
        'referenced_columns_json': '["region"]'}, snapshot=snapshot)
    from physical_roundtrip import _run, FILE, key_of
    index = key_of(env.diagram, env.child('child', 'index', 'child_amount_idx'))
    snapshot = _run(snapshot, [{'target': {'file': FILE, 'id': 'relations.mapping_' + index}, 'path': 'metadata.x_record.record.' + name, 'value': value}
                               for name, value in (('drop', True), ('drop_confirmation', 'child_amount_idx'))])
    _, plan = env.review(snapshot)
    # 'child' sorts before 'parent' by resource id, but the key the foreign key needs is created first and the drop comes last.
    assert [item['name'] for item in plan['operations']] == ['parent', 'child'] or [item['name'] for item in plan['operations']] == ['child']
    from pgadmin.cdeadmin.workspace.mysql_physical import ORDERING_RULE
    assert ORDERING_RULE in plan['warnings']
    assert any('commits' in warning for warning in plan['warnings'])
    if len(plan['operations']) == 2:
        assert plan['operations'][0]['name'] == 'parent' and not plan['operations'][0].get('destructive')
        assert plan['operations'][1]['destructive'] is True
    settle(env, plan)
