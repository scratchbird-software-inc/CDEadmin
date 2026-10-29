"""Native SQLite parameter slots, ownership and retained query execution."""
import os
import sqlite3
from pathlib import Path
import pytest

from pgadmin.cdeadmin.providers.sqlite.native_helpers import helper_supported
from pgadmin.cdeadmin.providers.sqlite.array_actions import action
from pgadmin.cdeadmin.providers.sqlite.array_bindings import bind_arrays
from pgadmin.cdeadmin.providers.sqlite.values import parameters
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPIError
from test_sqlite_driver import client,open_database,execute,rows


@pytest.fixture
def native(client,tmp_path):
    library=os.environ.get('CDEADMIN_SQLITE_ARRAY_LIBRARY')
    if not library or not Path(library).is_file() or not helper_supported('array'):pytest.skip('Native CARRAY helper required (built, and supported by this SQLite runtime)')
    connection,_route=open_database(client,tmp_path)
    def run(operation,**fields):return action(client,connection,{'operation':operation,**fields},library)
    yield client,connection,run,library


@pytest.mark.parametrize('source,bound',[
    ('SELECT value FROM carray(?)',[None]),
    ('SELECT value FROM carray(?3)',[7,8,None]),
    ('SELECT value FROM carray(?01)',{'01':None}),
    ('SELECT value FROM carray(?01) UNION ALL SELECT value FROM carray(?1)',{'01':None}),
    ('SELECT value FROM carray(:x)',{'x':None}),
    ('SELECT value FROM carray(@雪)',{'雪':None}),
    ('SELECT value FROM carray($namespace::x(suffix))',{'namespace::x(suffix)':None}),
    ('SELECT value FROM carray(:x(suffix))',{'x(suffix)':None}),
    ('SELECT value FROM carray(?1) WHERE ?2=7',[None,7]),
    ('SELECT value FROM carray(:x) WHERE ?1 IS NULL',{'x':None}),
    ('SELECT value FROM carray(:x) /* :not ?200 */ -- $not\r ?101\n',{'x':None}),
    ('''SELECT value FROM carray(:x),quoted WHERE ':not'=':not' AND "quoted$not"=1''',{'x':None}),
    ('SELECT value FROM carray(:x),quoted WHERE [quoted$not]=1',{'x':None}),
    ('SELECT value FROM carray(:x),quoted WHERE `quoted$not`=1',{'x':None}),
])
def test_binding_slots_match_native_prepare(native,source,bound):
    _client,connection,run,_lib=native
    connection.execute('CREATE TEMP TABLE quoted("quoted$not")');connection.execute('INSERT INTO quoted VALUES(1)')
    binding=run('create',type='int64',values=['9007199254740993'])['array']['binding']
    bound={key:binding if value is None else value for key,value in bound.items()} if isinstance(bound,dict) else [binding if value is None else value for value in bound]
    sql,values=bind_arrays(connection,source,parameters(bound))
    expected=2 if 'UNION ALL' in source else 1
    assert connection.execute(sql,values).fetchall()==[(9007199254740993,)]*expected


def test_scalar_slots_repeated_names_and_literals_preserve_native_semantics(native):
    _client,connection,run,_lib=native
    binding=run('create',type='text',values=['雪😀'])['array']['binding']
    source="SELECT value,:scalar,?1,'literal :items ?3',\"doubled\"\"$name\" FROM carray(:items),(SELECT 5 AS \"doubled\"\"$name\") WHERE :items IS NULL"
    sql,values=bind_arrays(connection,source,parameters({'items':binding,'scalar':17}))
    assert connection.execute(sql,values).fetchall()==[('雪😀',17,17,'literal :items ?3',5)]
    sql,values=bind_arrays(connection,'SELECT a.value,b.value FROM carray(:x) a,carray(@x) b',parameters({'x':binding}))
    assert connection.execute(sql,values).fetchall()==[('雪😀','雪😀')]
    sql,values=bind_arrays(connection,'SELECT 1',parameters({'unused':binding}));assert connection.execute(sql,values).fetchall()==[(1,)]


def test_retained_driver_preserves_integer_and_binary_storage(native):
    client,connection,run,_lib=native
    binding=run('create',type='int64',values=['9007199254740993','9223372036854775807'])['array']['binding']
    assert rows(execute(client,connection,'SELECT value FROM carray(:items)',{'items':binding}))==[['9007199254740993'],['9223372036854775807']]
    blob=run('create',type='blob',values=[{'encoding':'base64','data':'AP8='},None,{'encoding':'base64','data':''}])['array']['binding']
    assert rows(execute(client,connection,'SELECT hex(value),typeof(value) FROM carray(?)',[blob]))==[['00FF','blob'],['','null'],['','blob']]
    run('close',array_id=binding['data'],confirmed=True)
    with pytest.raises(RelationalClientError,match='another or closed'):client.execute(connection,{'source':'SELECT value FROM carray(?)','parameters':[binding]})
    assert not client.describe_transaction(connection)['session_reuse_blocked']


def test_inventory_policy_and_close_preserve_pending_transaction(native,tmp_path):
    client,connection,run,library=native
    assert run('inventory')['helper_available'] and connection._cdeadmin_array_api is None
    with pytest.raises(SessionAPIError,match='policy'):action(client,connection,{'operation':'create','type':'int64','values':[1,2]},library,8)
    assert connection._cdeadmin_array_api is None
    connection.execute('CREATE TABLE pending(id)');connection.execute('INSERT INTO pending VALUES(1)')
    binding=run('create',type='int32',values=[1])['array']['binding'];key=binding['data']
    page=run('inventory',offset=0,limit=1);assert page['transaction_open'] and page['total']==1 and page['arrays'][0]['binding']==binding
    assert '_cdeadmin_' not in str(page)
    unavailable=action(client,connection,{'operation':'inventory'},str(tmp_path/'missing'))
    assert unavailable['helper_available'] and not unavailable['installed_helper_available']
    with pytest.raises(SessionAPIError,match='Confirm'):run('close',array_id=key)
    with pytest.raises(SessionAPIError,match='policy'):action(client,connection,{'operation':'create','type':'int64','values':[1]},library,8)
    assert run('close',array_id=key,confirmed=True)['transaction_open']
    assert connection.execute('SELECT * FROM pending').fetchall()==[(1,)]
    connection.commit()
