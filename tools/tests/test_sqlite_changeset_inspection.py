"""Public changeset iterator pages, missing values and exact native byte ranges."""
import os
import pytest
from test_sqlite_session_api import native
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPI,SessionAPIError


def prepare(native,kind='changeset'):
    connection,library,tmp=native
    connection.executescript("CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT,payload BLOB,unchanged TEXT,n REAL);INSERT INTO t VALUES(1,'before',NULL,'stable',0.1),(2,'deleted',x'','stable',1.25);")
    api=SessionAPI(connection,library);key=api.open('main');api.attach(key,'t');api.call('indirect',key,1)
    payload=bytes(range(256))*600
    connection.execute('INSERT INTO t VALUES(?,?,?,?,?)',(9007199254740993,'雪😀\x00',payload,'stable',.1))
    connection.execute('UPDATE t SET body=NULL WHERE id=1');connection.execute('DELETE FROM t WHERE id=2')
    path=tmp/kind;fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:api.export(key,kind,fd)
    finally:os.close(fd)
    return connection,api,key,path,payload


def page(api,path,offset=0,limit=25,preview=4,budget=1048576,cancel=-1):
    with path.open('rb') as stream:return api.call('inspect_page',stream.fileno(),cancel,offset,limit,preview,budget)


def cell(api,path,row,column,side,offset=0,maximum=65536):
    with path.open('rb') as stream:return api.call('inspect_cell',stream.fileno(),-1,row,column,side,offset,maximum)


@pytest.mark.parametrize('kind',['changeset','patchset'])
def test_exact_native_types_primary_positions_and_undefined_are_not_null(native,kind):
    connection,api,key,path,payload=prepare(native,kind)
    result=page(api,path);assert result['native_iterator_complete'] and not result['more'] and result['rows_returned']==3
    rows={row['operation']:row for row in result['rows']};assert all(row['primary_key']==[1,0,0,0,0] and row['indirect'] for row in rows.values())
    inserted=rows['insert'];assert inserted['old_values'] is None and inserted['new_values'][0]=={'native_type':'integer','data':'9007199254740993'}
    assert inserted['new_values'][1]=={'native_type':'text','byte_length':'8','byte_offset':'0','preview_byte_length':'4','truncated':True,'hex':'E99BAAF0'}
    assert inserted['new_values'][2]['byte_length']==str(len(payload)) and inserted['new_values'][2]['hex']=='00010203'
    assert float(inserted['new_values'][4]['data'])==.1
    updated=rows['update'];assert updated['new_values'][1]=={'native_type':'null','data':None}
    assert updated['new_values'][3]=={'native_type':'undefined'} and updated['old_values'][3]=={'native_type':'undefined'}
    if kind=='patchset':assert updated['old_values'][1]=={'native_type':'undefined'}
    else:assert updated['old_values'][1]['hex']=='6265666F'
    deleted=rows['delete'];assert deleted['new_values'] is None and deleted['old_values'][0]['data']=='2'
    assert connection.in_transaction and not api.status(key)['empty']


def test_native_paging_lookahead_and_empty_or_past_end_are_explicit(native):
    _connection,api,_key,path,_payload=prepare(native)
    first=page(api,path,limit=1);assert first['more'] and not first['native_iterator_complete'] and first['native_rows_visited']=='2'
    last=page(api,path,offset=2,limit=1);assert not last['more'] and last['native_iterator_complete'] and last['rows'][0]['record_number']=='3'
    beyond=page(api,path,offset=99);assert beyond['rows']==[] and beyond['native_iterator_complete']
    empty=path.with_name('empty');empty.write_bytes(b'');assert page(api,empty)['rows']==[] and page(api,empty)['native_iterator_complete']


def test_native_value_ranges_reconstruct_large_binary_and_split_utf8_without_replacement(native):
    connection,api,_key,path,payload=prepare(native)
    row=next(row for row in page(api,path)['rows'] if row['operation']=='insert');number=int(row['record_number'])
    observed=bytearray()
    while len(observed)<len(payload):
        value=cell(api,path,number,2,1,len(observed));assert value['byte_offset']==str(len(observed));observed.extend(bytes.fromhex(value['hex']))
    assert bytes(observed)==payload
    text=b''.join(bytes.fromhex(cell(api,path,number,1,1,offset,3)['hex']) for offset in (0,3,6));assert text=='雪😀\x00'.encode('utf8')
    assert cell(api,path,number,0,1)=={'native_type':'integer','data':'9007199254740993'}
    for args in [(99,0,1,0),(number,99,1,0),(number,0,0,0),(number,2,1,len(payload)+1)]:
        with pytest.raises(SessionAPIError):cell(api,path,*args)
    assert connection.in_transaction


def test_native_cancel_and_budget_refusal_preserve_pending_sql(native):
    connection,api,_key,path,_payload=prepare(native)
    read,write=os.pipe();os.write(write,b'cancel')
    try:
        with pytest.raises(SessionAPIError) as error:page(api,path,cancel=read)
        assert error.value.native_result_code==9
    finally:os.close(read);os.close(write)
    with pytest.raises(SessionAPIError) as error:page(api,path,budget=128)
    assert error.value.native_result_code==18 and connection.in_transaction
    assert connection.execute('SELECT count(*) FROM t').fetchone()==(2,)
