"""Named native signatures absent from CPython's boolean db_config binding."""
import uuid
from ...sdk import RelationalClientError

BOOLEANS=('stmt_scanstatus','reverse_scanorder','enable_attach_create','enable_attach_write','enable_comments')
INTEGERS=('fp_digits',)
NAMES=BOOLEANS+INTEGERS+('main_dbname','lookaside')


def _error(message):raise RelationalClientError(message)


def _alias(value):
    if not isinstance(value,str) or not value or '\x00'in value or len(value.encode('utf8'))>1024:
        _error('Use an exact main-schema name of1–1024 UTF-8 bytes')
    return value


def _geometry(value):
    if isinstance(value,list) and len(value)==1 and isinstance(value[0],dict):
        value={key:item for key,item in value[0].items() if key!='_id'}
    if not isinstance(value,dict) or set(value)!={'slot_size','slot_count'}:
        _error('Select typed native lookaside slot size and count')
    size,count=value['slot_size'],value['slot_count']
    if (type(size)is not int or type(count)is not int or not 0<=size<=65528 or size%8
            or not 0<=count<=2147483647 or size*count>16*1024*1024):
        _error('Lookaside slots require multiples of8 and at most16MiB per connection')
    return dict(slot_size=size,slot_count=count)


def action(connection,request, *, native_work_revision=None):
    name,operation=request.get('config'),request.get('operation')
    common={'config','operation'}
    fields={'inspect':common,'review':common|{'value'},
        'set_connection_config':common|{'value','expected_value','confirmed'}|
          ({'review_id','schema_alias_change_confirmed'} if name=='main_dbname' else
           {'review_id','native_allocation_change_confirmed'} if name=='lookaside' else set())}
    if (not isinstance(name,str) or name not in NAMES or not isinstance(operation,str)
            or operation not in fields or set(request)-fields[operation]):
        _error('Select an admitted named native configuration signature')
    if operation!='inspect':
        value=request.get('value')
        if name in BOOLEANS and type(value)is not bool:_error('Select an explicit boolean policy')
        if name in INTEGERS and (type(value)is not int or not 3<=value<=23):_error('Select3–23 significant floating-point text digits')
        if name=='main_dbname':value=_alias(value)
        if name=='lookaside':value=_geometry(value)
    if operation=='set_connection_config':
        if request.get('confirmed')is not True:_error('Confirm the native configuration change')
        if name in BOOLEANS and type(request.get('expected_value'))is not bool:_error('Refresh the native boolean policy')
        if name in INTEGERS and (type(request.get('expected_value'))is not int or not 3<=request['expected_value']<=23):_error('Refresh the native digit policy')
        if name=='main_dbname':
            _alias(request.get('expected_value'))
            if request.get('schema_alias_change_confirmed')is not True:_error('Confirm invalidation of schema references and cached SQL')
        if name=='lookaside' and request.get('native_allocation_change_confirmed')is not True:
            _error('Confirm that native allocation geometry cannot be read back or restored automatically')
    bridge=getattr(connection,'_cdeadmin_config_api',None)
    if bridge is None or bridge.closed:_error('Native configuration bridge was not bound when this original handle opened')
    module,capsule=bridge.module,bridge.capsule
    def boolean():
        code,effective=module.boolean(capsule,name,-1)
        if code!=0 or effective not in (0,1):_error('Named configuration is absent from this native runtime/build')
        return bool(effective)
    def digits():
        code,effective=module.integer(capsule,0)
        if code!=0 or not 3<=effective<=23:_error('FP_DIGITS is absent from this native runtime/build')
        return effective
    def aliases():
        cursor=connection.cursor()
        try:
            cursor.execute('PRAGMA database_list');rows=cursor.fetchall()
            main=next((row[1]for row in rows if row[0]==0),None)
            if not isinstance(main,str):_error('Original native main-schema name is unavailable')
            return main,[row[1]for row in rows if row[0]!=0]
        finally:cursor.close()
    def usage():
        code,current,high=module.usage(capsule)
        if code!=0:_error('Native lookaside usage is unavailable')
        return {'used_slots':current,'high_water_slots':high}
    before=boolean() if name in BOOLEANS else digits() if name in INTEGERS else aliases()[0] if name=='main_dbname' else usage()
    result={'config':name,'scope':'original-connection','native_helper':dict(bridge.program),
        'before_value':before,'effective_value':before,'commit_requested':False,'rollback_requested':False,
        'transaction_open':connection.in_transaction,'file_persisted':False,
        'future_connection_defaults_changed':False,'automatic_retry':False,'rollback_restores_policy':False}
    if name=='lookaside':
        result.update(before_value=None,effective_value=None,before_configuration_observed=False,
            allocation_geometry_observed=False,native_usage=before,last_requested_configuration=bridge.last_lookaside_request)
    if operation=='inspect':return result
    if name=='main_dbname':
        if bridge.main_alias_changes>=32:_error('Main-alias storage budget exhausted; this handle allows32 alias changes')
        _,others=aliases()
        fold=lambda text:text.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'))
        if fold(value)in {fold(alias)for alias in ['temp',*others]}:_error('Main alias conflicts with another native schema')
    if name in {'main_dbname','lookaside'}:

        if type(native_work_revision)is not int or native_work_revision<0:_error('Driver-owned native work revision required')
        if operation=='review':
            token=uuid.uuid4().hex
            bridge.reviews[name]={'review_id':token,'revision':native_work_revision,'value':value,'before':before}
            result['review_id']=token
        else:
            retained=bridge.reviews.get(name)
            if (not isinstance(retained,dict) or request.get('review_id')!=retained['review_id'] or
                    retained['revision']!=native_work_revision or retained['value']!=value or retained['before']!=before):
                _error('Native configuration review or original work changed; review again')
    result.update(requested_value=value,expected_value=before if name!='lookaside' else None)
    if operation=='review':
        result.update(ready_to_apply=name!='lookaside' or before['used_slots']==0,warning={
            'fp_digits':'Changes floating-point to text conversion, not stored IEEE754 values. Rollback does not restore this connection policy.',
            'main_dbname':'Renames this handle’s main-schema alias only. Invalidate all schema references; existing prepared SQL may retain its old binding. Rollback does not restore the alias.',
            'lookaside':'SQLite must not be using lookaside slots. Native SQLITE_BUSY leaves configuration unchanged. Geometry/allocation has no public getter: successful acknowledgement is not allocation proof; failure to allocate may silently disable lookaside.',
        }.get(name,'Original native connection policy; no transaction finalization or rollback restoration.'))
        return result
    if name in INTEGERS and before!=request['expected_value']:_error('Native digit policy changed; review again')
    if name in BOOLEANS and before is not request['expected_value']:_error('Native policy changed; review again')
    if name=='main_dbname' and before!=request['expected_value']:_error('Native schema alias changed; review again')
    if name=='lookaside' and request.get('expected_value')is not None:_error('Native lookaside geometry has no getter; expected_value must be null')
    if name in {'main_dbname','lookaside'}:bridge.reviews.pop(name)
    try:
        if name in BOOLEANS:
            code,effective=module.boolean(capsule,name,int(value));after=boolean()
        elif name in INTEGERS:
            code,effective=module.integer(capsule,value);after=digits()
        elif name=='main_dbname':
            code=module.alias(capsule,value);after=aliases()[0]
        else:
            code=module.lookaside(capsule,value['slot_size'],value['slot_count']);after=usage()
    except Exception as error:
        failure=RelationalClientError('Native configuration outcome unknown; close the original session before further work')
        failure.native_outcome='unknown_outcome';raise failure from error
    result.update(native_result_code=code,accepted=code==0,outcome='native_refused' if code else 'applied' if after==value else 'native_adjusted',effective_value=after)
    if name=='main_dbname':
        if code==0:bridge.main_alias_changes+=1
        result.update(invalidate_catalog_references=code==0,previous_main_alias=before,current_main_alias=after,prepared_statement_rebinding_claimed=False)
    if name=='lookaside':
        if code==0:bridge.last_lookaside_request=dict(value)
        result.update(outcome='native_acknowledged_geometry_unobserved' if code==0 else 'native_refused',effective_value=None,native_usage=after,
            last_requested_configuration=bridge.last_lookaside_request,allocation_geometry_observed=False)
    return result
