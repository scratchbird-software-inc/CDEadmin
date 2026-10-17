"""Exact native statistics families for separately owned PostgreSQL collectors."""
from functools import lru_cache
from copy import deepcopy
from importlib import resources
import json
import time

ROW_LIMIT=200
BYTE_LIMIT=512*1024


@lru_cache(maxsize=1)
def inventory():
    path=resources.files(__package__).joinpath('postgresql_metrics_inventory_18_3.json')
    value=json.loads(path.read_text())
    if value.get('inventory_id')!='postgresql.metrics-inventory.18.3.v1' or value.get('reference_version')!='18.3':
        raise ValueError('Exact PostgreSQL18.3 native metrics inventory is unavailable')
    return {item['endpoint_id']:item for item in value['endpoints']}


def source_catalog():
    try:entries=inventory()
    except (OSError,ValueError):return {'state':'unavailable','sources':[]}
    return {'state':'available','reference_version':'18.3','row_limit_per_sample':ROW_LIMIT,'row_byte_limit_per_sample':BYTE_LIMIT,
        'sources':[{'source_id':name,'scope':item['scope'],'columns':deepcopy(item['columns'])} for name,item in entries.items()]}


def select_sources(value):
    if not isinstance(value,(list,tuple)) or len(value)>128 or any(not isinstance(name,str) for name in value):
        raise ValueError('Select a bounded list of native PostgreSQL metrics sources')
    if len(set(value))!=len(value):raise ValueError('Native PostgreSQL metrics source selections must be distinct')
    if not value:return ()
    if set(value)-set(inventory()):raise ValueError('Native PostgreSQL metrics source is absent from the exact inventory')
    return tuple(value)


def read_sources(connection,selected,*,scope,database_oid):
    """Read inside the caller's owned read-only transaction, with savepoints."""
    from psycopg import Cursor
    from psycopg.rows import tuple_row
    selected=select_sources(selected)
    if connection.info.transaction_status!=2:raise ValueError('Native statistics require an owned active read-only transaction')
    with Cursor(connection,row_factory=tuple_row) as query:
        query.execute("SELECT current_setting('server_version_num'),current_setting('transaction_read_only')")
        version,readonly=query.fetchone()
    if str(version)!='180003' or readonly!='on':raise ValueError('Native statistics require a PostgreSQL18.3 read-only transaction')
    frames={};remaining=BYTE_LIMIT;started=time.monotonic()
    for name in selected:
        item=inventory()[name]
        frame={'scope':item['scope'],'columns':deepcopy(item['columns']),'rows':[],'truncated':False,
               'visibility':'native_privilege_scope','status':'unavailable'}
        frames[name]=frame
        if remaining<=0:
            frame.update(reason='sample_byte_budget',truncated=True);continue
        statement=item['native_query'];parameters=[]
        columns={column['name'] for column in item['columns']}
        if scope=='database':
            if 'datid' in columns:statement+=' WHERE datid=%s::oid';parameters=[str(database_oid)]
            elif name=='pg_locks':statement+=' WHERE database=%s::oid';parameters=[str(database_oid)]
        statement+=' LIMIT '+str(ROW_LIMIT+1)
        try:
            # Permission or unavailable-component errors affect one family,
            # leaving the collector transaction usable for the others.
            with connection.transaction():
                with Cursor(connection,row_factory=tuple_row) as query:
                    query.execute(statement,parameters or None)
                    expected=[column['name'] for column in item['columns']]
                    if [column.name for column in query.description]!=expected:
                        raise ValueError('Native metrics column identity changed')
                    rows=query.fetchmany(ROW_LIMIT+1)
            frame['truncated']=len(rows)>ROW_LIMIT
            for row in rows[:ROW_LIMIT]:
                encoded=json.dumps(row,ensure_ascii=False,separators=(',',':')).encode('utf8')
                if len(encoded)>remaining:frame['truncated']=True;break
                frame['rows'].append(list(row));remaining-=len(encoded)
            frame.update(status='partial' if frame['truncated'] else 'available',visible_row_count=len(frame['rows']))
        except Exception as error:
            frame.update(status='denied' if getattr(error,'sqlstate',None)=='42501' else 'unavailable',
                sqlstate=getattr(error,'sqlstate',None),error_type=type(error).__name__)
    return {'schema':'postgresql-native-metric-families@1','sources':frames,'row_limit_per_source':ROW_LIMIT,
            'row_byte_limit':BYTE_LIMIT,'row_bytes_returned':BYTE_LIMIT-remaining,'duration_seconds':round(time.monotonic()-started,6),
            'status':'partial' if any(item['status']!='available' for item in frames.values()) else 'available'}
