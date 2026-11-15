"""Bounded native PRAGMA getter observations; actions are never getters."""
import json
from ...sdk import RelationalClientError
from .values import value, NativeTextBytes
from .connection_pragmas import FLAGS, DEBUG_FLAGS
from .connection_tuning import NAMES
from .heap_settings import NAMES as HEAP_NAMES
from .schema_settings import SPECS

READ_ONLY=frozenset({'page_count','data_version','freelist_count','database_list',
    'function_list','module_list','pragma_list','collation_list','compile_options',
    'table_info','table_xinfo','table_list','index_info','index_xinfo','index_list',
    'foreign_key_list','stats','lock_status'})
OBJECT_ARGUMENT=frozenset({'table_info','table_xinfo','index_info','index_xinfo','index_list','foreign_key_list'})
SETTINGS=frozenset(FLAGS)|frozenset(NAMES)|frozenset({'cache_spill','default_cache_size',
    'page_size','secure_delete','max_page_count','locking_mode','journal_mode','journal_size_limit',
    'cache_size','mmap_size','auto_vacuum','temp_store','temp_store_directory','data_store_directory',
    'lock_proxy_file','synchronous','encoding','schema_version','user_version','application_id',
    'soft_heap_limit','hard_heap_limit','threads','writable_schema','legacy_file_format',
    'sql_trace','vdbe_listing','vdbe_trace','vdbe_addoptrace','vdbe_debug','vdbe_eqp','parser_trace'})
GLOBAL=frozenset({'temp_store_directory','data_store_directory','soft_heap_limit','hard_heap_limit'})
MANAGED={**{name:'sqlite_connection_pragmas' for name in (*FLAGS,*DEBUG_FLAGS,*NAMES,*SPECS,*HEAP_NAMES,'temp_store_directory','data_store_directory','lock_proxy_file')},
    **{name:'database-properties' for name in ('page_size','encoding','auto_vacuum','application_id','user_version','journal_mode')},
    'synchronous':'sqlite_connection_settings','threads':'sqlite_connection_limits',
    'writable_schema':'sqlite_connection_config','legacy_file_format':'sqlite_connection_config'}
MAX_ROWS=1000
MAX_BYTES=4*1024*1024


def inspect(connection,request):
    if (set(request)-{'operation','pragma','schema','object_name'} or request.get('operation')!='inspect_pragma_value'
            or not isinstance(request.get('pragma'),str) or request['pragma'] not in READ_ONLY|SETTINGS):
        raise RelationalClientError('Select an admitted native PRAGMA getter; action PRAGMAs are separate workflows')
    name=request['pragma'];schema=request.get('schema','main');argument=request.get('object_name')
    for text in [schema,*([argument] if argument is not None else [])]:
        if not isinstance(text,str) or not text or '\x00' in text or len(text.encode())>1024*1024:
            raise RelationalClientError('Select a bounded native schema/object identifier')
    if (name in OBJECT_ARGUMENT and argument is None) or (name not in OBJECT_ARGUMENT|{'table_list'} and argument is not None):
        raise RelationalClientError('Select the required native object argument only for object metadata')
    cursor=connection.cursor()
    try:
        cursor.execute('PRAGMA database_list')
        schemas={row[1]for row in cursor.fetchall()}|{'temp'}
        if schema not in schemas:raise RelationalClientError('Schema is not attached to the original session')
        cursor.execute('PRAGMA pragma_list');present={row[0]for row in cursor.fetchall()}
        result={'pragma':name,'schema':schema,'object_name':argument,'scope':'original-connection',
            'read_only_pragma':name in READ_ONLY,'management_transport':MANAGED.get(name),
            'management_declared':name in MANAGED,'mutation_admission_observed':False,
            'setting_dispatched':False,'native_getter_may_acquire_vfs_conch_lock':name=='lock_proxy_file','commit_requested':False,'rollback_requested':False,
            'automatic_retry':False,'native_name_present':name in present}
        if name not in present:
            return {**result,'outcome':'unavailable','rows':[],'columns':[],'truncated':False}
        statement='PRAGMA "'+schema.replace('"','""')+'".'+name
        if argument is not None:statement+="('"+argument.replace("'","''")+"')"
        cursor.execute(statement)
        columns=[entry[0]for entry in cursor.description or ()]
        rows=[];classes=[];size=0;truncated=False
        for row in cursor:
            encoded=[value(item)for item in row]
            length=len(json.dumps(encoded,ensure_ascii=True).encode())
            if len(rows)>=MAX_ROWS or size+length>MAX_BYTES:
                truncated=True;break
            rows.append(encoded);size+=length
            classes.append(['null' if item is None else 'integer' if isinstance(item,int) else
                'real' if isinstance(item,float) else 'text' if isinstance(item,(str,NativeTextBytes)) else 'blob' for item in row])
        return {**result,'outcome':'observed','columns':columns,'rows':rows,
            'native_storage_classes':classes,'truncated':truncated,
            'transaction_open':connection.in_transaction,
            'object_existence_inferred':False,'empty_result_default_inferred':False}
    finally:cursor.close()


def capabilities(request):
    if set(request)!={'operation'}:raise RelationalClientError('Inspection capabilities take no native setting arguments')
    return {'read_only_getters':sorted(READ_ONLY),'setting_getters':sorted(SETTINGS),
        'object_argument_required':sorted(OBJECT_ARGUMENT),'management_transports':MANAGED,
        'native_name_availability_observed':False,'schema':'original attached schema identifier',
        'non_getter_management_transports':{'case_sensitive_like':'sqlite_connection_pragmas','shrink_memory':'sqlite_connection_maintenance'},
        'post_beta_native_dependencies':{'activate_extensions':{'component':'SQLite CEROD','reason':'Separate licensed source is absent from the pinned public amalgamation; only a guarded declaration and activation call are present. No implementation or execution claimed.','source':'https://sqlite.org/com/cerod.html'}},
        'non_getter_workflows':['wal_checkpoint','integrity_check','quick_check','foreign_key_check',
            'optimize','incremental_vacuum','shrink_memory','case_sensitive_like']}
