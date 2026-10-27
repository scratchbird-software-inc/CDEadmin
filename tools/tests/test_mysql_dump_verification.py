"""Recovery acceptance requires complete native checksum and row coverage."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_dump_verification as native
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.fixture
def dump(tmp_path):
    for name, value in {
        '@.json': {'checksum': True, 'schemas': ['source'], 'basenames': {'source': 'native'}},
        '@.done.json': {'tableRows': {'source': {'quoted`雪': 9007199254740993}}},
        'native.json': {'schema': 'source', 'includesData': True, 'tables': ['quoted`雪']},
        '@.checksums.json': {'data': {'source': {'quoted`雪': {'partitions': {
            'native_partition': {'0': {'count': 9007199254740993, 'checksum': 'native opaque'}}}}}}},
    }.items():
        (tmp_path / name).write_text(json.dumps(value))
    return tmp_path


def test_native_wide_counts_and_quoted_identities_are_not_coerced(dump):
    assert native.inventory(dump, 'source', 'target')[0] == {
        'source_schema': 'source', 'target_schema': 'target', 'table': 'quoted`雪',
        'expected_rows': '9007199254740993', 'checksum_chunks': 1}
    assert native.quote('quoted`雪') == '`quoted``雪`'


@pytest.mark.parametrize('fault', ['missing_checksums', 'missing_table', 'count_difference', 'duplicate_key', 'schema_escape'])
def test_incomplete_or_ambiguous_dump_never_establishes_data_acceptance(dump, fault):
    if fault == 'duplicate_key':
        (dump / '@.done.json').write_text('{"tableRows":{},"tableRows":{}}')
    else:
        name = '@.json' if fault in {'missing_checksums', 'schema_escape'} else '@.checksums.json'
        value = json.loads((dump / name).read_text())
        if fault == 'missing_checksums': value['checksum'] = False
        elif fault == 'schema_escape': value['basenames']['source'] = '../other'
        elif fault == 'missing_table': value['data']['source'] = {}
        else: value['data']['source']['quoted`雪']['partitions']['native_partition']['0']['count'] = 1
        (dump / name).write_text(json.dumps(value))
    with pytest.raises(RelationalClientError): native.inventory(dump, 'source', 'target')


def test_verification_control_cannot_enable_loaders_progress_resume_or_gtid_changes():
    client = SimpleNamespace(_shell_connection_arguments=lambda _route: [])
    source = native.script(client, {}, '/owned/dump', 'source', 'target',
        {'server_uuid': 'native', 'version': '9.7.0', 'authenticated_principal': 'operator@%', 'active_role': 'NONE'}, 'unique:', 4)
    options = json.loads(source.split('util.loadDump("/owned/dump",', 1)[1].split(');', 1)[0])
    assert all(options[key] is False for key in ('loadDdl', 'loadData', 'loadIndexes', 'loadUsers'))
    assert options['checksum'] is True and options['progressFile'] == ''
    assert options['analyzeTables'] == 'off' and options['updateGtidSet'] == 'off'
    assert options['includeSchemas'] == ['source'] and options['schema'] == 'target'


@pytest.mark.parametrize('fault', ['confirmation', 'loader', 'threads', 'non_object'])
def test_verification_refuses_before_native_access_without_exact_scope(fault):
    client = Mock()
    options = {'path': 'dump', 'confirmation': 'database'}
    if fault == 'confirmation': options['confirmation'] = 'wrong'
    elif fault == 'loader': options['load_data'] = True
    elif fault == 'threads': options['threads'] = True
    else: options = None
    with pytest.raises(RelationalClientError): native.verify(client, {'database': 'database'}, options)
    client._connect.assert_not_called()


@pytest.mark.parametrize('fault', ['artifact', 'program', 'shape'])
def test_changed_review_is_refused_before_native_lock_or_setting_change(dump, monkeypatch, fault):
    client = Mock()
    client._workspace_path.return_value = dump.parent, dump
    program = {'executable_sha256': 'native-program'}
    monkeypatch.setattr(native, 'program_identity', lambda *_args: program)
    review = {'artifact_manifest': native.manifest(dump), 'program': program}
    if fault == 'artifact': (dump / 'unreviewed.txt').write_text('new native input')
    elif fault == 'program': review['program'] = {'executable_sha256': 'other-program'}
    else: review = 'ambiguous review'
    with pytest.raises(RelationalClientError, match='changed'):
        native.verify(client, {'database': 'source', 'tool_workspace': str(dump.parent)},
            {'path': dump.name, 'confirmation': 'source', '_verification_review': review})
    client._connect.assert_not_called()
