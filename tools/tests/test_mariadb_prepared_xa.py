"""Native binary XIDs, exact resolution and original-session isolation."""
from contextlib import closing
from types import SimpleNamespace
import uuid

import pytest
from test_mariadb_server_diagnostics import native, SETTINGS, record_native_execution
from pgadmin.cdeadmin.providers.mysql_family import mariadb_prepared_xa as xa
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations, operation_draft


def plan(n, operation, xid=None):
    values = {} if xid is None else {**{key: xid[key] for key in ['format_id','gtrid_hex','bqual_hex']}, 'decision_reference':'owned external coordinator instruction'}
    draft = operation_draft(engine_operations('mariadb')[operation+'@server'], values, confirmation=n.target['display_name'])
    return n.client.plan_admin_operation(dict(resource_kind='server',operation_id=operation,
        target_resource=n.target,draft=draft,_provider_route=n.route))


def prepare(n, fmt):
    import mariadb
    g=(b'\xff\0'+uuid.uuid4().bytes); b=b'\0\xfe'
    xid=dict(format_id=str(fmt),gtrid_hex=g.hex().upper(),bqual_hex=b.hex().upper(),gtrid_length=len(g),bqual_length=len(b))
    n.cursor.execute('CREATE TABLE IF NOT EXISTS xa_owned(id VARCHAR(64) PRIMARY KEY) ENGINE=InnoDB')
    token=uuid.uuid4().hex
    handle=mariadb.connect(**SETTINGS);handle.autocommit=True;c=handle.cursor()
    sql=xa.xid_source(xid)
    try:
        c.execute('XA START '+sql);c.execute('INSERT INTO xa_owned VALUES(?)',(token,))
        c.execute('XA END '+sql);c.execute('XA PREPARE '+sql)
    finally:c.close();handle.close()
    return xid,token


@pytest.mark.parametrize('fmt',[0,1,2**31-1])
@pytest.mark.parametrize('operation',['commit_prepared_xa','rollback_prepared_xa'])
def test_native_binary_xid_resolution_and_independent_effects(native,fmt,operation):
    n=native;xid,token=prepare(n,fmt)
    try:
        n.cursor.execute('START TRANSACTION');n.cursor.execute('INSERT INTO observer_pending VALUES(43)');n.cursor.execute('SAVEPOINT caller')
        inspect_plan=plan(n,'inspect_prepared_xa')
        inspection=n.client.apply_admin_operation(inspect_plan)
        record_native_execution(inspect_plan,inspection,'xa_observation')
        assert xid in inspection['xa_observation']['prepared_after']
        resolution_plan=plan(n,operation,xid)
        result=n.client.apply_admin_operation(resolution_plan)
        record_native_execution(resolution_plan,result,'xa_observation')
        assert result['xa_observation']['native_acknowledged']and result['connection_release']['connection_released']
        assert xid not in result['xa_observation']['prepared_after']
        assert not result['commit_requested']and not result['rollback_requested']and not result['automatic_retry']
        n.cursor.execute('ROLLBACK TO SAVEPOINT caller');n.cursor.execute('SELECT * FROM observer_pending');assert n.cursor.fetchall()==[(43,)]
        import mariadb
        with closing(mariadb.connect(**SETTINGS))as h:
            c=h.cursor();c.execute('SELECT id FROM xa_owned WHERE id=?',(token,));assert c.fetchall()==([(token,)]if operation=='commit_prepared_xa'else[]);c.close()
        with pytest.raises(RelationalClientError,match='not currently prepared'):plan(n,operation,xid)
    finally:
        n.handle.rollback()
        try:n.cursor.execute('XA ROLLBACK '+xa.xid_source(xid))
        except Exception as e:assert getattr(e,'errno',None)==1397
        n.cursor.execute('DELETE FROM xa_owned WHERE id=?',(token,))


def test_xid_disappearing_after_review_refuses_without_resolution(native):
    n=native;xid,_=prepare(n,7);review=plan(n,'commit_prepared_xa',xid)
    n.cursor.execute('XA ROLLBACK '+xa.xid_source(xid))
    with pytest.raises(RelationalClientError)as error:n.client.apply_admin_operation(review)
    assert not error.value.native_dispatched and error.value.connection_release['connection_released']


@pytest.mark.parametrize('xid',[{'format_id':'1','gtrid_hex':'0','bqual_hex':''}, {'format_id':'1;SHUTDOWN','gtrid_hex':'00','bqual_hex':''}, {'format_id':1,'gtrid_hex':'00','bqual_hex':''}])
def test_xid_is_not_implicitly_encoded_or_coerced(xid):
    with pytest.raises(RelationalClientError):xa.identity(xid)


@pytest.mark.parametrize('fmt',['-1','2147483648','9223372036854775807'])
def test_native_and_typed_resolution_format_limits_agree(native,fmt):
    n=native
    with pytest.raises(Exception)as error:
        n.cursor.execute("XA START X'6162',X'',"+fmt)
    assert error.value.errno==1064
    with pytest.raises(RelationalClientError):xa.identity(dict(format_id=fmt,gtrid_hex='6162',bqual_hex=''))
