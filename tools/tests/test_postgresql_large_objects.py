"""Large-object admission uses exact native identities and bounded bytes."""
import base64
import pytest
from pgadmin.cdeadmin.providers.postgresql.large_objects import CHUNK_BYTES, MAX_LENGTH
from pgadmin.cdeadmin.providers.postgresql.native_admin import compile_native_admin, PostgreSQLNativeAdminError
from pgadmin.cdeadmin.providers.postgresql.preserved_surface import adapt_catalog, preserved_operations


def request(operation, draft=None, oid='42'):
    return {'resource_kind': 'large-object', 'operation_id': operation, 'draft': draft or {},
        'target_resource': {'extensions': {'postgresql': {'native': {'oid': oid}}}}}


@pytest.mark.parametrize('operation,draft', [
    ('inspect', {}), ('create', {'large_object_data_base64': 'AP8='}),
    ('read', {'offset': '2147483649', 'length': '100'}),
    ('write', {'offset': '2147483649', 'large_object_data_base64': 'AP8='}),
    ('truncate', {'length': '4294967297', 'confirmation': '42'}),
    ('alter', {'action': 'owner', 'value': 'Odd " owner'}),
    ('alter', {'action': 'comment', 'value': "🔥\\'quoted"}),
    ('alter', {'action': 'comment', 'value': ''}),
    ('grant', {'role': 'PUBLIC', 'privileges': ['SELECT'], 'grant_option': True}),
    ('revoke', {'role': 'Mixed role', 'privileges': ['SELECT', 'UPDATE'], 'grant_option': True, 'cascade': True}),
    ('drop', {'confirmation': '42'}),
    ('import-server-file', {'server_file':"C:\\owned\\'source ü.bin", 'oid':'0'}),
    ('export-server-file', {'server_file':"/owned/'output ü.bin", 'confirmation':"/owned/'output ü.bin"}),
])
def test_exact_native_statement(operation, draft):
    from pglast import parse_sql
    compiled = compile_native_admin(request(operation, draft))
    assert len(parse_sql(compiled['statement'])) == 1
    assert compiled['read_only'] is (operation in {'read', 'inspect'})


@pytest.mark.parametrize('operation,draft,oid', [
    ('read', {}, '42;SELECT 1'), ('read', {'offset': -1}, '42'),
    ('read', {'length': str(CHUNK_BYTES + 1)}, '42'),
    ('read', {'offset': str(MAX_LENGTH - 1), 'length': '2'}, '42'),
    ('write', {'large_object_data_base64': 'AP/='}, '42'),
    ('write', {'large_object_data_base64': base64.b64encode(bytes(CHUNK_BYTES + 1)).decode()}, '42'),
    ('write', {'offset': str(MAX_LENGTH - 1), 'large_object_data_base64': 'AP8='}, '42'),
    ('truncate', {'length': '1', 'confirmation': '43'}, '42'),
    ('drop', {'confirmation': '42'}, '0'),
    ('grant', {'role': 'x', 'privileges': ['DELETE']}, '42'),
    ('grant', {'role': 'x', 'privileges': [{}]}, '42'),
    ('grant', {'role': 'x', 'privileges': ['SELECT', 'SELECT']}, '42'),
    ('import-server-file', {'server_file':'a\x00b'}, '42'),
    ('import-server-file', {'server_file':'é'*512}, '42'),
    ('export-server-file', {'server_file':'owned.bin','confirmation':'other.bin'}, '42'),
])
def test_invalid_or_ambiguous_requests_refused(operation, draft, oid):
    with pytest.raises(PostgreSQLNativeAdminError):
        compile_native_admin(request(operation, draft, oid))


def test_native_forms_are_separate_from_preserved_surface_and_offer_all_operations():
    assert 'large-object' not in preserved_operations()
    obj = next(item for item in adapt_catalog({'objects': []})['objects'] if item['resource_kind'] == 'large-object')
    assert {item['operation_id'] for item in obj['operations']} == {
        'inspect', 'create', 'read', 'write', 'truncate', 'alter', 'grant', 'revoke', 'drop',
        'import-server-file', 'export-server-file'}
    assert all(item['execution_route'] == 'provider-native' and item['form']['form_key'] ==
        'native:postgresql:database:large-object' for item in obj['operations'])
    operations = {item['operation_id']:item for item in obj['operations']}
    assert operations['import-server-file']['target_required'] is False
    assert operations['export-server-file']['mutation_class'] == 'destructive'
    assert operations['export-server-file']['confirmation_required'] is True


def test_server_file_literal_preserves_exact_whitespace_quotes_and_backslashes():
    from pglast import parse_sql
    filename = "  C:\\owned\\'file ü.bin  "
    compiled = compile_native_admin(request('import-server-file',{'server_file':filename}))
    call = parse_sql(compiled['statement'])[0].stmt.targetList[0].val
    assert call.args[0].val.sval == filename
    assert compiled['server_file_operation'] == 'import'
