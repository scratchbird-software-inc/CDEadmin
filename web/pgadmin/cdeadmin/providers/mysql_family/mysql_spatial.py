"""Bounded native geometry inspection. Original bytes are never normalized."""
from datetime import datetime, timezone
import json
import math
import time

from . import mysql_content_search as catalog
from .mysql_catalog import identifier

Error = catalog.SearchError
GEOMETRY = {'geometry','point','linestring','polygon','multipoint','multilinestring','multipolygon','geometrycollection'}
MAX_VALUE = 65536
MAX_RESPONSE = 4 * 1024 * 1024


def describe(observer, schema, table):
    source = catalog.describe(observer, schema, table)
    srids = observer.query('SELECT COLUMN_NAME,SRS_ID FROM information_schema.COLUMNS WHERE '+catalog.EXACT+
        ' ORDER BY ORDINAL_POSITION LIMIT 4097', (schema, table))
    source['fingerprint'] = catalog.digest([source['fingerprint'], srids])
    by_name = {row['COLUMN_NAME']: row['SRS_ID'] for row in srids}
    source['spatial_columns'] = [{**column, 'SRS_ID': catalog.display(by_name[column['COLUMN_NAME']])}
        for column in source['columns'] if column['DATA_TYPE'] in GEOMETRY | catalog.BINARY]
    return source


def options(value):
    if not isinstance(value, dict) or set(value) != {'format','srid','axis_order','map','limit','offset','seconds'}:
        raise Error('Select exact geometry encoding, SRID, map coordinates and inspection bounds')
    if value['format'] not in {'mysql', 'wkb'} or value['map'] not in {'native', 'wgs84'}:
        raise Error('Select native MySQL geometry or WKB, and native X/Y or WGS84 mapping')
    if value['axis_order'] not in {'long-lat','lat-long','srid-defined'}:
        raise Error('Select explicit native WKB axis ordering')
    srid = value['srid']
    if not isinstance(srid, str) or not srid.isascii() or not srid.isdigit() or len(srid)>10 or int(srid)>4294967295:
        raise Error('WKB interpretation requires an unsigned native SRID')
    for key, low, high in [('limit',1,100),('offset',0,1000000),('seconds',1,30)]:
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise Error('Spatial '+key+' exceeds its inspection bound')
    return {**value, 'srid': int(srid)}


def geometry_size(geometry, *, geographic=False):
    """Bound native GeoJSON before crossing into the DDN renderer."""
    points = features = 0
    def visit(g, depth=0):
        nonlocal features
        if not isinstance(g, dict) or depth>32:
            raise Error('Native geometry exceeds the collection depth bound')
        kind = g.get('type')
        if kind == 'GeometryCollection':
            children = g.get('geometries')
            if not isinstance(children,list):raise Error('Native collection has no geometry array')
            for child in children:visit(child,depth+1)
        elif kind in {'Point','MultiPoint','LineString','MultiLineString','Polygon','MultiPolygon'}:
            features += 1
            if features>500:raise Error('Native geometry exceeds 500 map features')
            coordinates(g.get('coordinates'),depth)
        else:raise Error('Native GeoJSON geometry is outside the map profile')
    def coordinates(value, depth):
        nonlocal points
        if not isinstance(value,list) or depth>32:raise Error('Native coordinates exceed their nesting bound')
        if not value:return
        if isinstance(value[0], (int,float)):
            if len(value)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or abs(v)>1.7976931348623157e308 or not math.isfinite(v) for v in value):
                raise Error('Native map coordinates must be finite X/Y pairs')
            if geographic and (abs(value[0])>180 or abs(value[1])>90):raise Error('Native WGS84 coordinates are outside longitude/latitude bounds')
            points += 1
            if points>10000:raise Error('Native geometry exceeds 10000 map positions')
        else:
            for item in value:coordinates(item,depth+1)
    visit(geometry)
    return points, features


def srid_catalog(observer, srid):
    if srid == 0:
        return {'srs_id':'0','status':'native-Cartesian-without-SRS','definition':None}
    rows = observer.query('SELECT SRS_ID,SRS_NAME,ORGANIZATION,ORGANIZATION_COORDSYS_ID,DEFINITION,DESCRIPTION '
        'FROM information_schema.ST_SPATIAL_REFERENCE_SYSTEMS WHERE SRS_ID=%s LIMIT 2', (srid,), limit=2)
    if len(rows)!=1:return {'srs_id':str(srid),'status':'unavailable'}
    return {'status':'available', **{k.lower(): catalog.display(v) for k,v in rows[0].items()}}


def native_error(error, stage):
    return {'stage':stage,'error_code':getattr(error,'errno',None),'sqlstate':getattr(error,'sqlstate',None),
        'error_type':type(error).__name__}


def convert(observer, raw, selected):
    from mysql.connector import Error as NativeError
    result = {'raw_hex':raw.hex(),'raw_bytes':len(raw),'format':selected['format'], 'state':'binary-fallback',
        'map_status':'unavailable','map_geometry':None,'errors':[]}
    if selected['format']=='mysql':
        if len(raw)<5:return {**result,'reason':'Native internal geometry requires a four-byte SRID and WKB'}
        srid, wkb = int.from_bytes(raw[:4],'little'), raw[4:]
    else:srid, wkb = selected['srid'], raw
    result['srid'] = str(srid)
    axis = 'long-lat' if selected['format']=='mysql' else selected['axis_order']
    result['input_axis_order'] = axis
    expression = "ST_GeomFromWKB(UNHEX(%s),%s,'axis-order="+axis+"')"
    parameters = (wkb.hex(), srid)
    tail = ' FROM (SELECT '+expression+' AS g) AS sr_geometry'
    try:
        core = observer.query("SELECT ST_GeometryType(g) AS geometry_type,ST_AsText(g) AS wkt_srs,"
            "ST_AsText(g,'axis-order=long-lat') AS wkt_xy,ST_AsGeoJSON(g,17,0) AS geojson"+tail, parameters, limit=2)[0]
        geometry = json.loads(core['geojson']) if isinstance(core['geojson'],str) else core['geojson']
        count, features = geometry_size(geometry)
        result.update(core, geojson=geometry, state='inspected', positions=count, features=features)
    except NativeError as error:
        result['errors'].append(native_error(error,'native-decode'));return result
    except (ValueError,RecursionError,TypeError,KeyError):
        result['reason']='Native geometry exceeds the bounded GeoJSON inspection profile';return result
    try:
        valid = observer.query('SELECT ST_IsValid(g) AS valid'+tail, parameters, limit=2)[0]['valid']
        result['validity'] = 'valid' if valid==1 else 'invalid' if valid==0 else 'unavailable'
    except NativeError as error:
        result['validity']='unavailable';result['errors'].append(native_error(error,'native-validity'))
    if result['validity']!='valid':
        result['map_status']='native-'+result['validity'];return result
    if count==0:
        result['map_status']='empty';return result
    if selected['map']=='native':
        result.update(map_geometry=geometry, map_status='native-X/Y', map_method='cartesian')
    else:
        try:
            mapped = geometry if srid==4326 else observer.query('SELECT ST_AsGeoJSON(ST_Transform(g,4326),17,0) AS geometry'+tail,
                parameters, limit=2)[0]['geometry']
            mapped = json.loads(mapped) if isinstance(mapped,str) else mapped
            geometry_size(mapped,geographic=True)
            result.update(map_geometry=mapped,map_status='native-WGS84-longitude/latitude',map_method='equirectangular')
        except NativeError as error:result['errors'].append(native_error(error,'native-transform'))
        except (ValueError,TypeError,RecursionError):result['reason']='Transformed geometry is outside the bounded WGS84 map profile'
    return result


def inspect(observer, schema, table, column, fingerprint, selected):
    source = describe(observer,schema,table)
    if source['fingerprint']!=fingerprint:raise Error('Native table or SRID metadata changed; rediscover columns')
    found = next((c for c in source['spatial_columns'] if c['COLUMN_NAME']==column),None)
    if found is None:raise Error('Select an observed native geometry or binary column')
    if found['DATA_TYPE'] in GEOMETRY and selected['format']!='mysql':raise Error('Native geometry columns use their internal MySQL SRID prefix')
    field = identifier(column);size = 'OCTET_LENGTH(CAST('+field+' AS BINARY))'
    key = source['key']
    projection = [size+' AS native_bytes', 'CASE WHEN '+size+'<='+str(MAX_VALUE)+' THEN HEX(CAST('+field+' AS BINARY)) END AS native_hex']
    projection += ['LEFT(HEX(CAST('+identifier(k)+' AS BINARY)),1024) AS key_'+str(i) for i,k in enumerate(key)]
    order = ' ORDER BY '+','.join(identifier(k) for k in key) if key else ''
    deadline = time.monotonic()+selected['seconds']
    observer.query('SET SESSION max_execution_time='+str(selected['seconds']*1000))
    observer.begin()
    result = {'schema':'cdeadmin.mysql-spatial-inspection.v1', 'schema_name':schema,'table_name':table,'column_name':column,
        'fingerprint':fingerprint,'identity':{k:catalog.display(v) for k,v in observer.identity.items()},'rows':[], 'srs':{},
        'observed_at':datetime.now(timezone.utc).isoformat(), 'consistent_snapshot':source['engine']=='InnoDB',
        'ordering': 'native unique key' if key else 'unordered native sample', 'offset':selected['offset'],
        'key_columns':key,'next_offset':None,'coverage':'bounded independent snapshot page', 'map_mode':selected['map'],
        'native_interface':type(observer.connection).__name__,
        'external_requests':False,'tiles':'none','limits':{'rows':selected['limit'],'value_bytes':MAX_VALUE,'response_bytes':MAX_RESPONSE,'positions':10000,'features':500}}
    points = features = 0
    try:
        rows = observer.query('SELECT '+','.join(projection)+' FROM '+identifier(schema)+'.'+identifier(table)+order+
            ' LIMIT '+str(selected['limit']+1)+' OFFSET '+str(selected['offset']), limit=selected['limit']+1)
        if len(rows)>selected['limit']:result['next_offset']=selected['offset']+selected['limit']
        for index,row in enumerate(rows[:selected['limit']]):
            original_srids = set(result['srs'])
            if time.monotonic()>=deadline:
                result.update(coverage='inspection-time-bound',next_offset=None);break
            observer.query('SET SESSION max_execution_time='+str(max(1,int((deadline-time.monotonic())*1000))))
            entry = {'id':'row-'+str(selected['offset']+index),'key_hex':{k:row['key_'+str(i)] for i,k in enumerate(key)}}
            if row['native_bytes'] is None:entry.update(state='null',raw_hex=None,raw_bytes=None,map_status='null')
            elif row['native_hex'] is None:entry.update(state='value-too-large',raw_hex=None,raw_bytes=str(row['native_bytes']),map_status='value-byte-bound')
            else:
                entry.update(convert(observer,bytes.fromhex(row['native_hex']),selected))
                srid = entry.get('srid')
                if srid is not None and srid not in result['srs']:result['srs'][srid]=srid_catalog(observer,int(srid))
                if entry.get('map_geometry') is not None:
                    p,f = geometry_size(entry['map_geometry'])
                    if points+p>10000 or features+f>500:entry.update(map_geometry=None,map_status='map-position-or-feature-bound')
                    else:points+=p;features+=f
            result['rows'].append(entry)
            if len(json.dumps(result,ensure_ascii=True).encode())>MAX_RESPONSE:
                result['rows'].pop()
                for srid in set(result['srs'])-original_srids:del result['srs'][srid]
                result.update(coverage='response-byte-bound',next_offset=None);break
        if describe(observer,schema,table)['fingerprint']!=fingerprint:raise Error('Native table metadata changed during inspection')
        for srid, metadata in result['srs'].items():
            if srid_catalog(observer,int(srid))!=metadata:raise Error('Native spatial reference definition changed during inspection')
        return result
    finally:observer.rollback()
