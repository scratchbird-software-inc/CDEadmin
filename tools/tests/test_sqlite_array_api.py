"""Public native pointer values, exact CARRAY storage and connection lifetime."""
import base64
import os
from pathlib import Path
import sqlite3

import pytest

from pgadmin.cdeadmin.providers.sqlite.array_api import ArrayAPI
from pgadmin.cdeadmin.providers.sqlite.array_values import encode
from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPIError


@pytest.fixture
def native():
    library=os.environ.get('CDEADMIN_SQLITE_ARRAY_LIBRARY')
    if not library or not Path(library).is_file() or sqlite3.sqlite_version!='3.53.0':pytest.skip('Pinned native CARRAY bridge required')
    connection=sqlite3.connect(':memory:',factory=SQLiteConnection);api=ArrayAPI(connection,library)
    try:yield connection,api
    finally:connection.close()


def create(api,kind,values):
    selected=encode(kind,values);item=api.create(selected['native_type'],selected['element_count'],selected['payload'])
    assert item['native_data_bytes']==str(selected['native_data_bytes']);return item


@pytest.mark.parametrize('kind,values,expected',[
    ('int32',[-2147483648,0,2147483647],[(-2147483648,'integer'),(0,'integer'),(2147483647,'integer')]),
    ('int64',['9007199254740993','-9223372036854775808','9223372036854775807'],[(9007199254740993,'integer'),(-9223372036854775808,'integer'),(9223372036854775807,'integer')]),
    ('double',['0.1','-0.0','inf','nan'],[(.1,'real'),(-.0,'real'),(float('inf'),'real'),(None,'null')]),
    ('text',['雪😀','',None],[('雪😀','text'),('','text'),(None,'null')]),
    ('blob',[b'\x00\xff',b'',None],[(b'\x00\xff','blob'),(b'','blob'),(None,'null')]),
])
def test_all_native_array_types_and_null_empty_distinctions(native,kind,values,expected):
    connection,api=native;item=create(api,kind,values);expression=api.expression(item['array_id'])
    assert connection.execute('SELECT value,typeof(value) FROM carray('+expression+')').fetchall()==expected
    assert connection.execute("SELECT count(*) FROM carray("+expression+",1000000,'int64')").fetchone()==(0,)
    api.close(item['array_id'])


@pytest.mark.parametrize('kind',['int32','int64','double','text','blob'])
def test_empty_native_arrays_are_valid_without_transient_copy_assumptions(native,kind):
    connection,api=native;item=create(api,kind,[])
    assert connection.execute('SELECT count(*) FROM carray('+api.expression(item['array_id'])+')').fetchone()==(0,)


def test_array_control_is_private_loader_is_closed_and_pending_sql_survives(native):
    connection,api=native;trace=[];connection.set_trace_callback(trace.append)
    connection.execute('CREATE TABLE pending(id INTEGER)');connection.execute('INSERT INTO pending VALUES(7)')
    item=create(api,'int64',['9007199254740993']);assert connection.in_transaction
    assert not connection.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION)
    assert not any(api.token.hex().lower() in value.lower() for value in trace)
    assert connection.execute('SELECT id FROM pending').fetchall()==[(7,)]
    api.close(item['array_id']);assert connection.in_transaction
    connection.commit();assert connection.execute('SELECT id FROM pending').fetchall()==[(7,)]
    with pytest.raises(SessionAPIError):api.status(item['array_id'])


def test_array_cleanup_bypasses_only_authorization_for_closing_owned_boxes(native):
    connection,api=native;create(api,'text',['owned'])
    def deny(*_args):return sqlite3.SQLITE_DENY
    connection.set_authorizer(deny);api.close_all();assert connection._cdeadmin_authorizer is deny and not api.arrays
    connection.set_authorizer(None);connection.close();connection.close()


def test_raw_native_text_and_binary_are_kept_exact(native):
    connection,api=native;raw={'encoding':'base64','data':base64.b64encode(b'\xff\x80').decode(),'native_storage_class':'text'}
    item=create(api,'text',[raw]);assert connection.execute('SELECT hex(value),typeof(value) FROM carray('+api.expression(item['array_id'])+')').fetchall()==[('FF80','text')]
    with pytest.raises(SessionAPIError,match='terminated'):encode('text',['a\x00b'])
