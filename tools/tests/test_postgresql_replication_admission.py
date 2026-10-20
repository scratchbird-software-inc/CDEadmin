"""Native replication admission must not depend on a SQL connection."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.postgresql import replication_admission as module
from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError


@pytest.mark.parametrize('value,expected',[(b'1MB',1048576),('8192',8192),('16 MB',16777216)])
def test_native_geometry(value,expected):
    assert module._bytes(value)==expected


@pytest.mark.parametrize('value',['0','1.5GB','-1MB','1TB','16MB;SELECT'])
def test_unknown_geometry_is_not_guessed(value):
    with pytest.raises(ContinuityError):module._bytes(value)


def test_capture_uses_only_native_replication_commands_and_seals_password(monkeypatch):
    import psycopg
    commands=[]
    class Cursor:
        def __init__(self,*_args,**_kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*_args):pass
        def execute(self,source):commands.append(source)
        def fetchone(self):
            return {'IDENTIFY_SYSTEM':(b'9007199254740993',b'1',b'0/A',None),
                'SHOW wal_segment_size':(b'16MB',),'SHOW wal_block_size':(b'8192',)}[commands[-1]]
    info=SimpleNamespace(server_version=180003,host='native.host',hostaddr='127.0.0.2',port=6543,user='replication user',dbname='replication',
        get_parameters=lambda:{'service':'saved','passfile':'private','password':'secret','sslmode':'verify-full'})
    @contextmanager
    def connect(**options):
        assert options['replication']=='true' and options['autocommit'] is True
        yield SimpleNamespace(info=info,pgconn=SimpleNamespace(password=b'secret'))
    monkeypatch.setattr(psycopg,'connect',connect);monkeypatch.setattr(psycopg,'ClientCursor',Cursor)
    source,transport=module.capture({'user':'replication user'})
    try:
        assert source['authenticated_principal']=='replication user'
        assert source['sql_admission_performed'] is False and source['tablespace_catalog_observed'] is False
        assert commands==['IDENTIFY_SYSTEM','SHOW wal_segment_size','SHOW wal_block_size']
        assert 'secret' not in repr(source) and 'secret' not in repr(transport)
        with transport.parameters() as values:
            assert values['password']=='secret' and values['hostaddr']=='127.0.0.2'
            assert 'service' not in values and 'passfile' not in values
    finally:transport.close()
    with pytest.raises(ContinuityError):
        with transport.parameters():pass


def test_registered_admission_constructs_conninfo_without_sql_connect(monkeypatch):
    from pgadmin.utils.driver.registry import DriverRegistry
    manager=Mock(db='postgres');manager.create_connection_string.return_value="host=localhost user='native user' dbname=postgres password=private"
    monkeypatch.setattr(DriverRegistry,'get',lambda _name:SimpleNamespace(connection_manager=lambda _sid:manager))
    captured=Mock(return_value=('source','transport'));monkeypatch.setattr(module,'capture',captured)
    server=SimpleNamespace(id=9,username='native user',role='',use_ssh_tunnel=0)
    assert module.registered(server,{'password':'private'})==('source','transport')
    manager.create_connection_string.assert_called_once_with('postgres','native user','private')
    manager.connection.assert_not_called()
    assert captured.call_args.args[0]['user']=='native user'


@pytest.mark.parametrize('value',[{'host':'other'}, {'password':False}, {'password':'x\x00y'}])
def test_credentials_cannot_override_registered_route(value):
    with pytest.raises(ContinuityError):module.registered(SimpleNamespace(),value)


@pytest.mark.parametrize('role,tunnel',[('administrator',0),('',1)])
def test_unadmitted_role_or_ssh_is_explicit(role,tunnel):
    with pytest.raises(ContinuityError):module.registered(SimpleNamespace(role=role,use_ssh_tunnel=tunnel),{})
