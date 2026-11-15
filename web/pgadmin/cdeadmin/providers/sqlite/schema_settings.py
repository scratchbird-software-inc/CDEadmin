"""Typed native schema/pager settings on the original connection.

Readback is configured native state, not proof of physical allocation, lock
ownership, erasure or durable commit. Native clamping/ignoring is reported.
"""
import re
import uuid
from ...sdk import RelationalClientError

SPECS={
    'cache_size':('integer',-2147483648,2147483647),
    'cache_spill':('integer',0,2147483647),
    'max_page_count':('integer',1,4294967294),
    'default_cache_size':('integer',-2147483647,2147483647),
    'schema_version':('integer',-2147483648,2147483647),
    'journal_size_limit':('decimal-text',-1,9223372036854775807),
    'mmap_size':('decimal-text',0,9223372036854775807),
    'secure_delete':('enum',{'OFF':0,'ON':1,'FAST':2}),
    'locking_mode':('enum',{'NORMAL':'normal','EXCLUSIVE':'exclusive'}),
    'temp_store':('enum',{'DEFAULT':0,'FILE':1,'MEMORY':2}),
}
PERSISTENT=frozenset({'default_cache_size','schema_version'})
CONNECTION_NAMES=tuple(name for name in SPECS if name not in PERSISTENT)


def checked(name,value):
    spec=SPECS[name]
    if spec[0]=='enum':
        if not isinstance(value,str) or value not in spec[1]:raise RelationalClientError('Select a native setting choice')
        return spec[1][value]
    if spec[0]=='decimal-text':
        if not isinstance(value,str) or re.fullmatch(r'-?(?:0|[1-9][0-9]{0,18})',value) is None:
            raise RelationalClientError('Use canonical exact decimal integer text')
        number=int(value)
        if str(number)!=value:raise RelationalClientError('Use canonical exact decimal integer text')
    else:
        if type(value) is not int:raise RelationalClientError('Use an exact integer setting')
        number=value
    if not spec[1]<=number<=spec[2]:raise RelationalClientError('Native setting is outside its admitted integer range')
    return number


def observed(name,row):
    if not row:raise RelationalClientError('Native setting getter is unavailable')
    spec=SPECS[name];value=row[0]
    if spec[0]=='enum':
        for token,expected in spec[1].items():
            if type(value) is type(expected) and value==expected:return token
        raise RelationalClientError('Native enum setting is unrecognized')
    if type(value) is not int or not spec[1]<=value<=spec[2]:raise RelationalClientError('Native integer setting is unrecognized')
    return str(value) if spec[0]=='decimal-text' else value


def action(connection,request, *, native_work_revision=None):
    name=request.get('pragma');operation=request.get('operation')
    base={'operation','pragma','schema'}
    fields={'inspect':base,'review':base|{'value'},
        'set_connection_pragma':base|{'value','expected_value','confirmed'}|
            ({'temp_objects_drop_confirmed','review_id'} if name=='temp_store' else
             {'direct_header_change_confirmed'} if name=='schema_version' else set())}
    if (not isinstance(name,str) or name not in SPECS or not isinstance(operation,str)
            or operation not in fields or set(request)-fields[operation]):
        raise RelationalClientError('Select a typed native schema setting')
    if name=='temp_store' and 'schema' in request:
        raise RelationalClientError('temp_store is a connection policy; omit a schema')
    schema=None if name=='temp_store' else request.get('schema','main')
    if schema is not None and (not isinstance(schema,str) or not schema or '\x00' in schema or len(schema.encode())>1024*1024):
        raise RelationalClientError('Select an exact original-session schema identifier')
    if operation!='inspect':number=checked(name,request.get('value'))
    if operation=='set_connection_pragma':
        checked(name,request.get('expected_value'))
        if request.get('confirmed') is not True:raise RelationalClientError('Confirm the native setting change')
        if name=='schema_version' and request.get('direct_header_change_confirmed') is not True:
            raise RelationalClientError('Confirm direct schema-header version manipulation')
    cursor=connection.cursor()
    try:
        cursor.execute('PRAGMA pragma_list')
        if name not in {row[0]for row in cursor.fetchall()}:raise RelationalClientError('Native setting is absent from this runtime/build')
        if schema is not None:
            cursor.execute('PRAGMA database_list')
            if schema not in {row[1]for row in cursor.fetchall()}|{'temp'}:
                raise RelationalClientError('Schema is not attached to the original connection')
        prefix='PRAGMA '+('"'+schema.replace('"','""')+'".' if schema is not None else '')
        def read():return observed(name,cursor.execute(prefix+name).fetchone())
        try:before=read()
        except Exception as error:
            failure=RelationalClientError('Native setting observation unavailable; setter not dispatched')
            failure.native_outcome='not_dispatched';raise failure from error
        ready=not(name=='temp_store' and connection.in_transaction)
        auxiliary={}
        if name=='temp_store':
            cursor.execute('PRAGMA compile_options')
            auxiliary['native_temp_store_compile_options']=[row[0]for row in cursor.fetchall() if str(row[0]).startswith('TEMP_STORE=')]
            auxiliary['physical_temp_storage_observed']=False
        if name=='default_cache_size':auxiliary['connection_cache_before']=cursor.execute(prefix+'cache_size').fetchone()[0]
        if name=='temp_store' and operation!='inspect':
            if type(native_work_revision) is not int or native_work_revision<0 or not isinstance(getattr(connection,'_cdeadmin_pragma_policy_reviews',None),dict):
                raise RelationalClientError('Driver-owned original-session TEMP policy revision required')
            if operation=='review':
                token=uuid.uuid4().hex
                connection._cdeadmin_pragma_policy_reviews['temp_store']={'review_id':token,'revision':native_work_revision,'value':request['value']}
                auxiliary['review_id']=token
                cursor.execute('SELECT type,substr(name,1,256),length(name)>256 FROM temp.sqlite_schema ORDER BY type,name LIMIT 501')
                objects=cursor.fetchall()
                auxiliary['temp_objects']=[{'type':str(kind)[:32],'name_preview':str(obj),'name_truncated':bool(truncated)} for kind,obj,truncated in objects[:500]]
                auxiliary['temp_objects_truncated']=len(objects)>500
        if operation=='set_connection_pragma':
            if before!=request['expected_value']:raise RelationalClientError('Original native setting changed; review again')
            if not ready:raise RelationalClientError('End the caller transaction before changing temp_store')
            if name=='temp_store' and before!=request['value'] and request.get('temp_objects_drop_confirmed') is not True:
                raise RelationalClientError('Confirm deletion of the original connection TEMP objects')
            if name=='temp_store':
                review=connection._cdeadmin_pragma_policy_reviews.get('temp_store')
                if (not isinstance(review,dict) or request.get('review_id')!=review['review_id'] or
                        review['revision']!=native_work_revision or review['value']!=request['value']):
                    raise RelationalClientError('TEMP policy review or original native work changed; review again')
                connection._cdeadmin_pragma_policy_reviews.pop('temp_store')
            try:
                cursor.execute(prefix+name+'='+str(number))
                after=read()
                if name=='default_cache_size':auxiliary['connection_cache_after']=cursor.execute(prefix+'cache_size').fetchone()[0]
            except Exception as error:
                failure=RelationalClientError('Native setting outcome unconfirmed; inspect before deciding to retry')
                failure.native_outcome='unknown_outcome';raise failure from error
        else:after=before
        result={'pragma':name,'schema':schema,'before_value':before,'effective_value':after,
            'scope':'original-connection' if schema is None else 'original-connection/schema',
            'file_persisted':None if name in PERSISTENT else False,
            'persistence_authority':'native header/transaction state; not inferred from setter' if name in PERSISTENT else 'connection/pager policy',
            'transaction_open':connection.in_transaction,'commit_requested':False,'rollback_requested':False,
            'future_connection_defaults_changed':None if name=='default_cache_size' else False,
            'registration_defaults_changed':False,'peer_isolation_claimed':False,'automatic_retry':False,
            'physical_allocation_or_lock_ownership_observed':False,**auxiliary}
        if name=='cache_spill':result['native_scope_note']='Boolean enable/disable also affects the connection spill flag; pager threshold is schema-specific and may be shared by cache-sharing peers.'
        if operation!='inspect':result.update(requested_value=request['value'],expected_value=before,native_statement=prefix+name+'='+str(number))
        if operation=='review':result.update(ready_to_apply=ready,warning=WARNINGS[name])
        if operation=='set_connection_pragma':result.update(outcome='applied' if after==request['value'] else 'native_adjusted',requested_value_effective=after==request['value'])
        return result
    finally:cursor.close()


WARNINGS={
    'cache_size':'Suggested pages (positive) or KiB (negative), not measured allocation; native shared-pager behaviour applies.',
    'cache_spill':'Zero disables the connection spill flag; positive values configure a schema pager threshold. Native cache size and shared pagers affect the effective threshold.',
    'max_page_count':'Native current file size and engine limits may adjust the requested pager ceiling; this is not a durable file-size guarantee.',
    'default_cache_size':'Writes the stored default and changes the current connection cache. Header persistence follows native transactions/autocommit; connection cache state is not restored by rollback.',
    'schema_version':'Direct schema-cookie manipulation can invalidate native schema caches or bypass change detection. Native defensive mode may ignore it; explicit header-change confirmation is required.',
    'journal_size_limit':'A journal/WAL reset applies this limit; readback is not proof that an existing file was truncated.',
    'mmap_size':'Native limits and outstanding references can adjust this budget. Readback does not prove mapped bytes or physical allocation.',
    'secure_delete':'Ordinary deleted-cell policy is not an immediate whole-file purge or proof of erasing FTS shadow content.',
    'locking_mode':'Configured mode is not proof of lock acquisition or release; pending native transactions remain caller-owned.',
    'temp_store':'Changing policy deletes all current TEMP tables, indexes, views and triggers. Native compile options can override physical storage; finish the caller transaction first.',
}
