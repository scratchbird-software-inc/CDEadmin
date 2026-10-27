import pytest
from pgadmin.cdeadmin.providers.mysql_grants import grantee, scoped_statement, routine_grants


@pytest.mark.parametrize('text,expected', [
    ("'u@x'@'h@x'", ('u@x', 'h@x')),
    ("'u\\'\\\\é'@'%'", ("u'\\é", '%')),
    ("'u''x'@'%'", ("u'x", '%')),
    ("''@'localhost'", ('', 'localhost')),
])
def test_native_grantee_decoding_preserves_account_components(text, expected):
    assert grantee(text) == expected


def test_grants_preserve_native_scope_and_refuse_borrowed_account_fields():
    facts = {'grantee': "'u@é'@'%'", 'privilege_type': 'UPDATE', 'table_schema': 'db`é', 'table_name': 't', 'column_name': 'c`x'}
    source = scoped_statement(facts, 'column-grants', 'grant', False)['source']
    assert source == 'GRANT UPDATE(`c``x`) ON `db``é`.`t` TO `u@é`@`%`'
    with pytest.raises(ValueError):
        scoped_statement({**facts, 'grantee_user': 'different'}, 'column-grants', 'grant', False)
    for bad in ("u@'%'", "'u'@'%'extra", "'u'@''"):
        with pytest.raises(ValueError):
            grantee(bad)


def test_routine_grants_use_effective_account_and_decode_quoted_native_names():
    account = {'user': 'u@é', 'host': '%', 'grantee_identity': "'u@é'@'%'"}
    def read(source, parameters):
        assert parameters == ('u@é', '%')
        return [{'grants': 'GRANT EXECUTE, ALTER ROUTINE ON PROCEDURE `db``é`.`r.name` TO `u@é`@`%` WITH GRANT OPTION'}]
    rows = list(routine_grants([account], read))
    assert [row['privilege_type'] for row in rows] == ['EXECUTE', 'ALTER ROUTINE']
    assert all(row['grantee_user'] == 'u@é' and row['table_schema'] == 'db`é' and
               row['routine_name'] == 'r.name' and row['is_grantable'] == 'YES' for row in rows)


def test_library_privileges_remain_native_library_operations():
    facts = {'grantee': "'u'@'%'", 'privilege_type': 'EXECUTE', 'table_schema': 'db',
             'routine_name': 'lib', 'routine_type': 'LIBRARY'}
    assert scoped_statement(facts, 'routine-grants', 'grant', False)['source'] == 'GRANT EXECUTE ON LIBRARY `db`.`lib` TO `u`@`%`'
