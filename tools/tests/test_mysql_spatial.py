"""Native SRID/axis interpretation, lossless fallbacks and bounded map input."""
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from mysql.connector import DatabaseError
from pgadmin.cdeadmin.providers.mysql_family import mysql_spatial as native


def options(**patch):
    return native.options({'format':'mysql','srid':'0','axis_order':'long-lat','map':'native','limit':25,'offset':0,'seconds':10,**patch})


@pytest.mark.parametrize('patch',[{'srid':'4294967296'},{'srid':'0);DELETE'},{'limit':101},{'limit':True},
    {'offset':-1},{'seconds':31},{'map':'guess'},{'axis_order':'auto'},{'format':'ewkb'}])
def test_native_selection_never_accepts_sql_or_unbounded_options(patch):
    with pytest.raises(native.Error):options(**patch)


def test_nested_collections_lines_holes_and_empty_geometries_have_bounded_coverage():
    collection={'type':'GeometryCollection','geometries':[{'type':'LineString','coordinates':[[1000000,2000000],[1000001,2000002]]},
        {'type':'Polygon','coordinates':[[[0,0],[2,0],[2,2],[0,0]],[[.2,.2],[1,.2],[1,1],[.2,.2]]]},
        {'type':'GeometryCollection','geometries':[]}]}
    assert native.geometry_size(collection)==(10,2)
    with pytest.raises(native.Error):native.geometry_size(collection,geographic=True)
    assert native.geometry_size({'type':'GeometryCollection','geometries':[]})==(0,0)


@pytest.mark.parametrize('geometry',[
    {'type':'Point','coordinates':[True,1]}, {'type':'Point','coordinates':[1,float('nan')]},
    {'type':'LineString','coordinates':[[1,2]]*10001}, {'type':'FeatureCollection','features':[]},
    {'type':'Point','coordinates':[1,2,3]}, {'type':'Point','coordinates':[10**500,1]}, {'type':'Point','coordinates':'not geometry'}])
def test_bad_and_excessive_positions_cannot_reach_the_renderer(geometry):
    with pytest.raises(native.Error):native.geometry_size(geometry)


def observer(valid=1, transform=None):
    def query(sql, parameters=None, **kwargs):
        if 'ST_GeometryType' in sql:return [{'geometry_type':'POINT','wkt_srs':'POINT(43 -79)',
            'wkt_xy':'POINT(-79 43)','geojson':json.dumps({'type':'Point','coordinates':[-79,43]})}]
        if 'ST_IsValid' in sql:return [{'valid':valid}]
        if 'ST_Transform' in sql:
            if isinstance(transform,Exception):raise transform
            return [{'geometry':json.dumps(transform or {'type':'Point','coordinates':[-79,43]})}]
        raise AssertionError(sql)
    return NS(query=Mock(side_effect=query))


def test_internal_srid_prefix_bytes_and_native_axis_outputs_are_preserved():
    source=observer();raw=(4326).to_bytes(4,'little')+b'\x01\x01\x00\x00\x00native-wkb'
    result=native.convert(source,raw,options())
    assert result['raw_hex']==raw.hex() and result['srid']=='4326'
    assert result['wkt_srs']=='POINT(43 -79)' and result['wkt_xy']=='POINT(-79 43)'
    assert result['map_geometry']['coordinates']==[-79,43] and result['map_method']=='cartesian'
    assert source.query.call_args_list[0].args[1]==(raw[4:].hex(),4326)


def test_wkb_uses_explicit_native_srs_axis_order_without_application_swapping():
    source=observer();raw=b'\0big-endian-original'
    result=native.convert(source,raw,options(format='wkb',srid='4326',axis_order='srid-defined',map='wgs84'))
    assert result['raw_hex']==raw.hex() and result['input_axis_order']=='srid-defined'
    assert "axis-order=srid-defined" in source.query.call_args_list[0].args[0]
    assert result['map_geometry']['coordinates']==[-79,43]
    assert not any('ST_Transform' in call.args[0] for call in source.query.call_args_list)


def test_invalid_and_native_decode_errors_keep_original_binary_without_a_fake_map():
    raw=b'\0'*4+b'bad'
    invalid=native.convert(observer(valid=0),raw,options())
    assert invalid['validity']=='invalid' and invalid['map_geometry'] is None and invalid['raw_hex']==raw.hex()
    source=NS(query=Mock(side_effect=DatabaseError('private native detail',errno=3037,sqlstate='22023')))
    bad=native.convert(source,raw,options())
    assert bad['state']=='binary-fallback' and bad['errors'][0]['error_code']==3037
    assert bad['raw_hex']==raw.hex() and 'private native detail' not in str(bad)


def test_native_transform_refusal_preserves_source_values_and_never_assumes_srid_zero_is_wgs84():
    source=observer(transform=DatabaseError('private',errno=3615,sqlstate='22023'))
    result=native.convert(source,b'\0'*4+b'wkb',options(map='wgs84'))
    assert result['geojson']['coordinates']==[-79,43] and result['map_geometry'] is None
    assert result['errors'][0]['stage']=='native-transform'


def inspection(monkeypatch, *, changed=False):
    source={'fingerprint':'observed','engine':'InnoDB','key':[], 'spatial_columns':[{'COLUMN_NAME':'g`雪','DATA_TYPE':'geometry'}]}
    descriptions=[source,{**source,'fingerprint':'changed'}] if changed else [source,source]
    monkeypatch.setattr(native,'describe',Mock(side_effect=descriptions))
    raw='00'*4+'01'
    def query(sql,*args,**kwargs):
        if sql.startswith('SET'):return []
        return [{'native_bytes':5,'native_hex':raw},{'native_bytes':None,'native_hex':None},
            {'native_bytes':65537,'native_hex':None}]
    source=NS(query=Mock(side_effect=query),begin=Mock(),rollback=Mock(),identity={'server_uuid':'native'},connection=NS())
    monkeypatch.setattr(native,'convert',lambda *_:{'state':'binary-fallback','raw_hex':raw,'raw_bytes':5,'map_geometry':None})
    return source


def test_null_and_oversized_values_remain_distinct_and_sql_names_are_quoted(monkeypatch):
    source=inspection(monkeypatch)
    report=native.inspect(source,'db`雪','table','g`雪','observed',options())
    assert [r['state'] for r in report['rows']]==['binary-fallback','null','value-too-large']
    assert report['rows'][2]['raw_hex'] is None and report['rows'][2]['raw_bytes']=='65537'
    assert report['consistent_snapshot'] and report['external_requests'] is False
    sql=next(c.args[0] for c in source.query.call_args_list if c.args[0].startswith('SELECT'))
    assert '`db``雪`.`table`' in sql and 'CAST(`g``雪` AS BINARY)' in sql
    source.rollback.assert_called_once()


def test_metadata_change_discards_the_page_and_rolls_back_owned_snapshot(monkeypatch):
    source=inspection(monkeypatch,changed=True)
    with pytest.raises(native.Error,match='metadata changed'):native.inspect(source,'db','t','g`雪','observed',options())
    source.rollback.assert_called_once()


def test_response_bounds_drop_whole_values_rather_than_truncate_bytes(monkeypatch):
    source=inspection(monkeypatch);monkeypatch.setattr(native,'MAX_RESPONSE',20)
    report=native.inspect(source,'db','t','g`雪','observed',options())
    assert not report['rows'] and report['coverage']=='response-byte-bound'
    source.rollback.assert_called_once()


@pytest.mark.parametrize('revoke',['admission','registration','owner'])
def test_private_result_is_discarded_when_authorization_changes_and_read_slot_is_released(monkeypatch,revoke):
    import threading
    import pgadmin.model as model
    from pgadmin.cdeadmin.workspace import mysql_spatial_service as service
    endpoint=NS(profile_id='mysql-native',provider_id='org.cdeadmin.mysql')
    server=NS(id=1,endpoint_profile=endpoint,configuration='initial')
    current=NS(first=Mock(return_value=server))
    monkeypatch.setattr(model,'Server',NS(query=NS(filter_by=Mock(return_value=current))))
    monkeypatch.setattr(model,'User',NS(query=NS(filter_by=Mock(return_value=NS(first=lambda:NS(active=True))))))
    monkeypatch.setattr(service.MySQLMonitoringHost,'_configuration',lambda value:value.configuration)
    registry=NS(admitted_permissions=Mock(return_value={'data_read','execute'}),resolve=lambda _:NS(permissions='admitted'))
    workspace=NS(endpoint_service=NS(provider_registry=registry,workspace=lambda *_args,**_kwargs:(NS(),{'route':{'database':'db'}},None)),
        _principal_id=lambda _:7,_semantic_lock=threading.Lock())
    observer=NS(close=Mock());monkeypatch.setattr(service.catalog,'Observer',lambda *_:observer)
    def read(*_):
        if revoke=='admission':registry.admitted_permissions.return_value=set()
        elif revoke=='registration':server.configuration='replaced'
        else:current.first.return_value=None
        return {'rows':[{'raw_hex':'private'}]}
    monkeypatch.setattr(service.native,'inspect',read)
    with pytest.raises(native.Error,match='admission changed'):
        service.action(workspace,server,'read',{'database_target_id':'target','schema_name':'db','table_name':'t',
            'column_name':'g','fingerprint':'observed','confirmed':True,'options':{**options(),'srid':'0'}})
    observer.close.assert_called_once()
    assert all(workspace.mysql_spatial_slots.acquire(blocking=False) for _ in range(4))
    assert not workspace.mysql_spatial_slots.acquire(blocking=False)
