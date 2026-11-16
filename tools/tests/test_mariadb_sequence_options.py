"""Native sequence integer types, exact bounds and reset intent without NEXTVAL."""
import pytest
from test_mariadb_server_diagnostics import native
from pgadmin.cdeadmin.providers.mysql_family import mariadb_sequence_options as options
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations,operation_draft


def execute(n,op,**values):
    draft=operation_draft(engine_operations('mariadb')[op+'@sequence'],values)
    target={'resource_kind':'sequence','display_name':'owned_sequence','display_path':['owned_management','owned_sequence']}
    planned=n.client.plan_admin_operation(dict(resource_kind='sequence',operation_id=op,target_resource=target,draft=draft,_provider_route=n.route))
    return n.client.apply_admin_operation(planned)


@pytest.mark.parametrize('typ',options.TYPES)
@pytest.mark.parametrize('unsigned',[False,True])
def test_native_types_bounds_and_reset_without_advancing(native,typ,unsigned):
    n=native
    try:
        execute(n,'create',name='owned_sequence',parent='owned_management',integer_type=typ,unsigned=unsigned,start='7',increment='2',minimum_mode='VALUE',minimum='3',maximum_mode='VALUE',maximum='99',cache='7',cycle_mode='CYCLE')
        n.cursor.execute('SELECT next_not_cached_value FROM owned_sequence');before=n.cursor.fetchone()[0];assert before==7
        execute(n,'alter',minimum_mode='NATIVE',maximum_mode='NATIVE',cache='0',cycle_mode='NOCYCLE')
        n.cursor.execute('SHOW CREATE SEQUENCE owned_sequence');ddl=n.cursor.fetchone()[1].lower()
        assert ('unsigned'in ddl)==unsigned
        n.cursor.execute('SELECT next_not_cached_value,cache_size,cycle_option FROM owned_sequence');assert n.cursor.fetchone()==(7,0,0)
        execute(n,'alter',restart='11',confirmation='owned_sequence')
        n.cursor.execute('SELECT next_not_cached_value FROM owned_sequence');assert n.cursor.fetchone()==(11,)
        execute(n,'alter',restart_initial=True,confirmation='owned_sequence')
        n.cursor.execute('SELECT next_not_cached_value FROM owned_sequence');assert n.cursor.fetchone()==(7,)
    finally:n.cursor.execute('DROP SEQUENCE IF EXISTS owned_sequence')


def test_native_unsigned_64bit_values_roundtrip(native):
    n=native
    try:
        n.cursor.execute('START TRANSACTION');n.cursor.execute('INSERT INTO observer_pending VALUES(67)');n.cursor.execute('SAVEPOINT caller')
        execute(n,'create',name='owned_sequence',parent='owned_management',integer_type='BIGINT',unsigned=True,start='18446744073709551610',minimum_mode='VALUE',minimum='18446744073709551600',maximum_mode='VALUE',maximum='18446744073709551614',cache='0')
        n.cursor.execute('SELECT next_not_cached_value,minimum_value,maximum_value FROM owned_sequence')
        assert n.cursor.fetchone()==(18446744073709551610,18446744073709551600,18446744073709551614)
        n.cursor.execute('ROLLBACK TO SAVEPOINT caller');n.cursor.execute('SELECT * FROM observer_pending');assert n.cursor.fetchall()==[(67,)]
        n.handle.rollback()
    finally:n.cursor.execute('DROP SEQUENCE IF EXISTS owned_sequence')


@pytest.mark.parametrize('values',[{'integer_type':'FLOAT'},{'unsigned':True},{'restart':'5'},{'restart':'5','restart_initial':True,'confirmation':'s'},{'minimum_mode':'NATIVE','minimum':'5'},{'cache':'1;DROP TABLE t'},{'start':18446744073709551616}])
def test_native_typed_option_refusals(values):
    with pytest.raises(RelationalClientError):options.clauses(values,True,'s')


def test_native_alter_integer_type_and_unsigned_bound_reset(native):
    n=native
    try:
        execute(n,'create',name='owned_sequence',parent='owned_management',integer_type='SMALLINT',start='7',minimum_mode='VALUE',minimum='3',maximum_mode='VALUE',maximum='99',cache='0')
        with pytest.raises(RelationalClientError,match='cannot combine'):
            execute(n,'alter',integer_type='BIGINT',unsigned=True,minimum_mode='NATIVE',maximum_mode='NATIVE')
        execute(n,'alter',integer_type='BIGINT',unsigned=True)
        execute(n,'alter',minimum_mode='NATIVE',maximum_mode='NATIVE')
        n.cursor.execute('SHOW CREATE SEQUENCE owned_sequence');assert 'as bigint unsigned'in n.cursor.fetchone()[1].lower()
        n.cursor.execute('SELECT next_not_cached_value,minimum_value,maximum_value FROM owned_sequence')
        # Reference runtime retains this native reset bound after ALTER AS.
        # Do not infer or emulate a bound from SHOW CREATE's unsigned spelling.
        assert n.cursor.fetchone()==(7,1,9223372036854775806)
    finally:n.cursor.execute('DROP SEQUENCE IF EXISTS owned_sequence')
