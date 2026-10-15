"""MariaDB native identity, lexical dependency hints and client encoding."""
import base64
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.workspace.mariadb_definition_references import qualified_references, relation_references
from pgadmin.cdeadmin.workspace.mariadb_sql_export import build_metadata
from pgadmin.cdeadmin.providers.mysql_family.mariadb_native_encoding import encode_metadata
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
import json


def model(selected=False):
    db = 'demo'
    root_id = 'mariadb:' + json.dumps([db, 'database', None, db], separators=(',', ':'))
    context = {'sql_mode': '', 'character_set_client': 'utf8mb4', 'collation_connection': 'utf8mb4_bin', 'time_zone': '+00:00'}
    specs = [('database', db, 'CREATE DATABASE `demo`'),
        ('sequence', 'seq', 'CREATE SEQUENCE `seq` START WITH 20'),
        ('package', 'pkg', 'CREATE PACKAGE pkg PROCEDURE p(); END'),
        ('package-body', 'pkg', 'CREATE PACKAGE BODY pkg PROCEDURE p() BEGIN SELECT 1; END; END'),
        ('table', 'a', 'CREATE TABLE `a` (`id` INT PRIMARY KEY) WITH SYSTEM VERSIONING'),
        ('view', 'v', 'CREATE VIEW `v` AS SELECT `demo`.`a`.`id` FROM `demo`.`a`')]
    resources = []
    for kind, name, definition in specs:
        parent = None if kind == 'database' else root_id
        identity = 'mariadb:' + json.dumps([db, kind, parent, name], separators=(',', ':'))
        native = {'database': db, 'system_object': False, 'definition': definition, 'definition_context': context.copy()}
        if parent:native['navigator_parent_resource_id'] = parent
        else:native.update(catalog_row={'database_name': db, 'version': '12.2.2-MariaDB', 'server_uid': 'native'},
            catalog_observations=[{'section': 'KEY_COLUMN_USAGE', 'available': True}])
        resources.append({'resource_id': identity, 'resource_kind': kind, 'display_name': name,
            'display_path': [db] + ([] if kind == 'database' else [name]), 'native': native})
    return build_export(resources, endpoint_id='owner', target_id='target', generation='generation', engine='mariadb',
        native_model=True, resource_id=resources[1]['resource_id'] if selected else None)


def test_native_maria_kinds_order_context_and_selected_provenance():
    metadata = build_metadata(model())
    assert not metadata['blockers'] and metadata['script_available']
    assert metadata['engine_id'] == 'mariadb' and metadata['server_uid'] == 'native'
    kinds = [row['kind'] for row in metadata['statements']]
    assert kinds.index('package') < kinds.index('package-body')
    assert kinds.index('table') < kinds.index('view')
    assert 'WITH SYSTEM VERSIONING' in metadata['script'] and 'START WITH 20' in metadata['script']
    assert 'SET SESSION time_zone' in metadata['script']
    assert any(row['kind'] == 'unresolved-view-dependencies' for row in metadata['prerequisites'])
    selected = build_metadata(model(True))
    assert not selected['blockers'] and [row['kind'] for row in selected['statements']] == ['sequence']


def test_identity_context_and_missing_definitions_cannot_be_silently_generated():
    for change in ('identity', 'context', 'definition'):
        document = model();row = next(row for row in document['rows'].values() if row['kind'] == 'table')
        if change == 'identity':row['resource_id'] = 'mysql:wrong-engine'
        if change == 'context':row['native']['definition_context']['character_set_client'] = 'bad;statement'
        if change == 'definition':row['native']['definition'] = None
        result = build_metadata(document)
        assert result['blockers'] and not result['script_available']
    document = model();document['provenance']['mapping'] = 'scratchrobin.mysql.catalog@1'
    with pytest.raises(ValueError, match='MariaDB'):build_metadata(document)


def test_reference_hints_ignore_literals_comments_and_preserve_quoted_names():
    text = '''CREATE VIEW `v` AS SELECT 'fake.secret', "literal.reference", `db``x`.`a` FROM `db``x`.`a`
       /* ignored.object */ -- hidden.object
       JOIN other.b ON 1=1'''
    assert qualified_references(text, '') == [('db`x', 'a'), ('other', 'b')]
    assert ('literal', 'reference') not in qualified_references(text, 'ANSI_QUOTES')
    assert qualified_references('SELECT "d"."t"', 'ANSI_QUOTES') == [('d', 't')]
    with pytest.raises(ValueError):qualified_references("SELECT 'unclosed", '')


def encoding_fixture():
    metadata = build_metadata(model(True));metadata.update(native_encoding_required=True, script_available=False, script=None)
    block = metadata['statements'][0];block.update(statement="CREATE PROCEDURE p() SELECT 'é€'", kind='procedure')
    block['context'].update(character_set_client='latin1', collation_connection='utf8mb4_bin')
    cursor = Mock();cursor.fetchone.side_effect = [('12.2.2-MariaDB', 'native', 'demo', 'utf8mb4', 'utf8mb4_uca1400_ai_ci'),
        (block['statement'].encode('cp1252'), block['statement'])]
    cursor.fetchall.side_effect = [[('latin1',)], [('utf8mb4_bin',)]]
    connection = Mock(server_status=2, autocommit=True);connection.cursor.return_value = cursor
    return connection, cursor, metadata


def test_native_encoder_preserves_client_bytes_timezone_and_never_changes_connector_charset():
    connection, cursor, metadata = encoding_fixture()
    encoded = encode_metadata(connection, metadata)
    payload = base64.b64decode(encoded['encoded_script']['data_base64'])
    assert b"'\xe9\x80'" in payload and b'\\C latin1' in payload and b'SET SESSION time_zone' in payload
    assert b'fresh mariadb --binary-mode' in payload
    assert not any(call.args[0].startswith(('SET SESSION character_set_client', 'CREATE ', 'EXECUTE ')) for call in cursor.execute.call_args_list)
    commands = [call.args for call in cursor.execute.call_args_list]
    assert ('SET SESSION collation_connection=?', ('utf8mb4_uca1400_ai_ci',)) in commands
    cursor.close.assert_called_once()


def test_wrong_native_identity_unavailable_charset_and_loss_refuse_download():
    for problem in ('identity', 'charset', 'loss'):
        connection, cursor, metadata = encoding_fixture()
        if problem == 'identity':cursor.fetchone.side_effect = [('12.2.2-MariaDB', 'other', 'demo', 'utf8mb4', 'utf8mb4_uca1400_ai_ci')]
        if problem == 'charset':cursor.fetchall.side_effect = [[]]
        if problem == 'loss':cursor.fetchone.side_effect = [('12.2.2-MariaDB', 'native', 'demo', 'utf8mb4', 'utf8mb4_uca1400_ai_ci'), (b'?', '?')]
        with pytest.raises(ValueError):encode_metadata(connection, metadata)
        cursor.close.assert_called_once()


def test_unqualified_view_dependencies_follow_native_from_join_lists_and_nested_queries():
    text = "CREATE VIEW a_outer AS SELECT 'FROM false' FROM v JOIN `other`.`t` AS q ON q.id=v.id, z WHERE id IN (SELECT id FROM nested)"
    assert relation_references(text, '', 'demo') == [('demo', 'nested'), ('demo', 'v'), ('demo', 'z'), ('other', 't')]
