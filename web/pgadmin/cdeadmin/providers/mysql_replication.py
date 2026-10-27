"""Native MySQL asynchronous channel configuration and lifecycle."""
import math
import json
import re
from ..sdk.relational import RelationalClientError
from .mysql_tablespaces import identifier

OPERATIONS=frozenset({'create','alter','start','stop','reset','filter'})
TEXT=frozenset('SOURCE_HOST NETWORK_NAMESPACE SOURCE_BIND SOURCE_USER SOURCE_SSL_CA SOURCE_SSL_CAPATH SOURCE_TLS_VERSION SOURCE_SSL_CERT SOURCE_SSL_CIPHER SOURCE_SSL_KEY SOURCE_SSL_CRL SOURCE_SSL_CRLPATH SOURCE_PUBLIC_KEY_PATH SOURCE_COMPRESSION_ALGORITHMS SOURCE_LOG_FILE RELAY_LOG_FILE'.split())
FLAGS=frozenset('SOURCE_SSL SOURCE_SSL_VERIFY_SERVER_CERT GET_SOURCE_PUBLIC_KEY SOURCE_AUTO_POSITION REQUIRE_ROW_FORMAT SOURCE_CONNECTION_AUTO_FAILOVER GTID_ONLY'.split())
NUMBERS=frozenset('SOURCE_PORT SOURCE_CONNECT_RETRY SOURCE_RETRY_COUNT SOURCE_DELAY SOURCE_ZSTD_COMPRESSION_LEVEL SOURCE_LOG_POS RELAY_LOG_POS'.split())
FILTERS=frozenset('REPLICATE_DO_DB REPLICATE_IGNORE_DB REPLICATE_DO_TABLE REPLICATE_IGNORE_TABLE REPLICATE_WILD_DO_TABLE REPLICATE_WILD_IGNORE_TABLE REPLICATE_REWRITE_DB'.split())


def channel_label(name):
    return 'Default channel' if name == '' else 'Channel ' + json.dumps(name,ensure_ascii=False)


def text(value,limit=65536):
    if not isinstance(value,str) or len(value.encode('utf8'))>limit or any(c in value for c in '\x00\r\n'):
        raise RelationalClientError('Native replication text requires bounded text without NUL/newlines')
    return value


def number(value,maximum=2**32-1):
    if type(value) is int and 0<=value<=min(maximum,2**53-1):return str(value)
    if isinstance(value,str) and re.fullmatch(r'0|[1-9][0-9]{0,19}',value) and int(value)<=maximum:return value
    raise RelationalClientError('Native replication integer requires an exact unsigned decimal value')


def compile_operation(operation,draft,target):
    if operation not in OPERATIONS or not isinstance(draft,dict):raise RelationalClientError('Native MySQL channel operation is unavailable')
    allowed={'confirmation'}|{'create':{'name','source_options','source_password'},'alter':{'source_options','source_password'},'start':{'thread','until'},'stop':{'thread'},'reset':{'delete_connection'},'filter':{'filters'}}[operation]
    if set(draft)-allowed:raise RelationalClientError('Unknown native replication field')
    native=(target or {}).get('native') or (target or {}).get('extensions',{}).get('mysql',{}).get('native',{})
    name=draft.get('name','') if operation=='create' else native.get('channel_name',(target or {}).get('display_name'))
    name=text(name,64)
    if name.lower().startswith('group_replication_'):raise RelationalClientError('Group Replication channels require their native group lifecycle')
    parameters=[]
    def bind(value):parameters.append(value);return '%s'
    def options(values,until=False):
        if not isinstance(values,dict) or not values:raise RelationalClientError('Select native replication options')
        result=[]
        for key,value in values.items():
            if not isinstance(key,str):raise RelationalClientError('Native replication option names must be text')
            if until:
                if key in {'SQL_BEFORE_GTIDS','SQL_AFTER_GTIDS'}:result.append(key+'='+bind(text(value)));continue
                if key=='SQL_AFTER_MTS_GAPS' and value is True:result.append(key);continue
                if key not in {'SOURCE_LOG_FILE','SOURCE_LOG_POS','RELAY_LOG_FILE','RELAY_LOG_POS'}:raise RelationalClientError('Unknown native UNTIL condition')
            if key in TEXT:sql=bind(text(value))
            elif key in FLAGS:
                if type(value) is not bool:raise RelationalClientError('Native replication switches require booleans')
                sql='1' if value else '0'
            elif key in NUMBERS:sql=number(value,2**64-1 if key in {'SOURCE_LOG_POS','RELAY_LOG_POS','SOURCE_RETRY_COUNT'} else 2**32-1)
            elif key=='SOURCE_HEARTBEAT_PERIOD':
                if type(value) not in {int,float} or not math.isfinite(value) or not 0<=value<=4294967:raise RelationalClientError('Invalid native heartbeat period')
                sql=str(value)
            elif key=='SOURCE_TLS_CIPHERSUITES':sql='NULL' if value is None else bind(text(value))
            elif key=='IGNORE_SERVER_IDS':
                if not isinstance(value,list) or len(value)>4096:raise RelationalClientError('Native server ID list is invalid')
                sql='('+','.join(number(item) for item in value)+')'
            elif key=='PRIVILEGE_CHECKS_USER':
                if value is None:sql='NULL'
                elif isinstance(value,dict) and set(value)=={'user','host'}:sql=bind(text(value['user'],32))+'@'+bind(text(value['host'],255))
                else:raise RelationalClientError('Privilege-check account requires exact user/host or null')
            elif key=='REQUIRE_TABLE_PRIMARY_KEY_CHECK':
                if not isinstance(value,str) or value not in {'ON','OFF','GENERATE','STREAM'}:raise RelationalClientError('Invalid native primary-key check')
                sql=value
            elif key=='ASSIGN_GTIDS_TO_ANONYMOUS_TRANSACTIONS':
                if isinstance(value,str) and value in {'OFF','LOCAL'}:sql=value
                elif isinstance(value,str) and re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',value):sql=bind(value)
                else:raise RelationalClientError('Select OFF, LOCAL or exact native UUID')
            else:raise RelationalClientError('Unknown native replication option '+key)
            result.append(key+'='+sql)
        if until:
            families=sum(bool(set(values)&keys) for keys in [{'SQL_BEFORE_GTIDS'},{'SQL_AFTER_GTIDS'},{'SQL_AFTER_MTS_GAPS'},{'SOURCE_LOG_FILE','SOURCE_LOG_POS'},{'RELAY_LOG_FILE','RELAY_LOG_POS'}])
            if families!=1:raise RelationalClientError('Choose one native UNTIL condition family')
            for prefix in ('SOURCE','RELAY'):
                pair={prefix+'_LOG_FILE',prefix+'_LOG_POS'}
                if pair&set(values) and not pair<=set(values):raise RelationalClientError('Native UNTIL positioning requires both file and position')
        return ', '.join(result)
    if operation in {'create','alter'}:
        values=draft.get('source_options',{})
        if not isinstance(values,dict):raise RelationalClientError('Source options must be a JSON object')
        source='CHANGE REPLICATION SOURCE TO '+options(values) if values else 'CHANGE REPLICATION SOURCE TO '
        if draft.get('source_password') is not None:
            source+=(', ' if values else '')+'SOURCE_PASSWORD='+bind(text(draft['source_password'],32))
        if not values and draft.get('source_password') is None:raise RelationalClientError('Select native source options or an explicit password')
    elif operation in {'start','stop'}:
        thread=draft.get('thread','ALL')
        if not isinstance(thread,str) or thread not in {'ALL','IO_THREAD','SQL_THREAD'}:raise RelationalClientError('Invalid native replication thread')
        source=operation.upper()+' REPLICA'+(' '+thread if thread!='ALL' else '')
        if operation=='start' and draft.get('until'):source+=' UNTIL '+options(draft['until'],True)
    elif operation=='reset':
        delete=draft.get('delete_connection',False)
        if type(delete) is not bool:raise RelationalClientError('Native RESET ALL selection must be boolean')
        source='RESET REPLICA'+(' ALL' if delete else '')
    else:
        filters=draft.get('filters')
        if not isinstance(filters,dict) or not filters:raise RelationalClientError('Select native replication filters')
        definitions=[]
        for key,values in filters.items():
            if key not in FILTERS or not isinstance(values,list) or len(values)>4096:raise RelationalClientError('Unknown native filter or invalid value list')
            entries=[]
            for value in values:
                if key not in {'REPLICATE_DO_TABLE','REPLICATE_IGNORE_TABLE','REPLICATE_REWRITE_DB'} and isinstance(value,dict):
                    if set(value)!={'value'}:raise RelationalClientError('Native filter rows require one value')
                    value=value['value']
                if key in {'REPLICATE_DO_TABLE','REPLICATE_IGNORE_TABLE','REPLICATE_REWRITE_DB'}:
                    if isinstance(value,dict):
                        names=('source','target') if key=='REPLICATE_REWRITE_DB' else ('database','table')
                        if set(value)!=set(names):raise RelationalClientError('Native filter records require exact named components')
                        value=[value[name] for name in names]
                    if not isinstance(value,list) or len(value)!=2:raise RelationalClientError('Native filter entries require two exact names')
                    entries.append('('+identifier(value[0])+','+identifier(value[1])+')' if key=='REPLICATE_REWRITE_DB' else identifier(value[0])+'.'+identifier(value[1]))
                elif key in {'REPLICATE_DO_DB','REPLICATE_IGNORE_DB'}:entries.append(identifier(value))
                else:entries.append(bind(text(value)))
            definitions.append(key+'=('+','.join(entries)+')')
        source='CHANGE REPLICATION FILTER '+', '.join(definitions)
    source+=' FOR CHANNEL '+bind(name)
    return {'source':source,'preview_source':source.replace('%s','<bound-value>'),'parameters':tuple(parameters)}


def form(operation,field):
    fields=[]
    if operation=='create':fields.append(field('name','Native channel name (blank is default)','text',default=''))
    if operation in {'create','alter'}:fields += [field('source_options','Native source options (JSON object)','json',default={},help_text='Exact native names: '+', '.join(sorted(TEXT|FLAGS|NUMBERS|{'SOURCE_HEARTBEAT_PERIOD','SOURCE_TLS_CIPHERSUITES','IGNORE_SERVER_IDS','PRIVILEGE_CHECKS_USER','REQUIRE_TABLE_PRIMARY_KEY_CHECK','ASSIGN_GTIDS_TO_ANONYMOUS_TRANSACTIONS'}))+'. Password has a separate field.'),field('source_password','Source password (omit to retain)','password',sensitive=True)]
    if operation!='create':fields.append(field('confirmation','Confirmation','text',True))
    return {'form_id':'mysql.replication-channel.'+operation,'title':operation.title()+' MySQL replication channel','fields':fields}
