"""Typed original-handle native VFS lock-proxy configuration."""
from pathlib import Path
import uuid
from ...sdk import RelationalClientError


def action(connection,request, *, native_work_revision=None,filesystem_root=None):
    operation=request.get('operation');common={'operation','pragma','schema'}
    fields={'inspect':common,'review':common|{'value_mode','path'},
            'set_connection_pragma':common|{'value_mode','path','expected_value','review_id','confirmed','native_locking_change_confirmed'}}
    if (not isinstance(operation,str) or operation not in fields or set(request)-fields[operation] or request.get('pragma')!='lock_proxy_file'):
        raise RelationalClientError('Select a typed native lock proxy operation')
    schema=request.get('schema','main')
    if not isinstance(schema,str) or not schema or '\x00'in schema:raise RelationalClientError('Select an attached file schema')
    bridge=getattr(connection,'_cdeadmin_config_api',None)
    if bridge is None or bridge.closed:raise RelationalClientError('Original-handle native configuration component required')
    names={row[0]for row in connection.execute('PRAGMA pragma_list')}
    options={row[0]for row in connection.execute('PRAGMA compile_options')}
    if 'lock_proxy_file'not in names or 'ENABLE_LOCKING_STYLE=1'not in options:
        raise RelationalClientError('Native runtime/build does not offer lock_proxy_file locking style')
    files={row[1]:row[2]for row in connection.execute('PRAGMA database_list')}
    if schema not in files or not files[schema]:raise RelationalClientError('Lock proxy requires an attached file database')
    if not filesystem_root:raise RelationalClientError('Registered filesystem authority required')
    root=Path(filesystem_root).resolve(strict=True)
    if not Path(files[schema]).resolve(strict=True).is_relative_to(root):raise RelationalClientError('Database escaped registered filesystem authority')
    def inspect():
        observed=bridge.module.directory(bridge.capsule,'lock_proxy_file',schema,'',0)
        if observed['native_result_code'] or observed['readback_result_code'] or observed['observed_rows']!=1:
            raise RelationalClientError('Native lock-proxy value could not be observed')
        return observed['value']
    before=inspect()
    result={'pragma':'lock_proxy_file','schema':schema,'scope':'original-connection/native-VFS',
            'effective_value':before,'before_value':before,'commit_requested':False,'rollback_requested':False,
            'automatic_retry':False,'physical_lock_ownership_observed':False,
            'warning':'Native getter can acquire the VFS conch lock. AUTO chooses a native platform path; explicit paths remain subject to VFS filesystem rules. Disabling proxy mode is not offered because native VFS cannot generally reverse it. Rollback does not restore locking configuration.'}
    if operation=='inspect':return result
    if type(native_work_revision)is not int:raise RelationalClientError('Original work revision required')
    mode=request.get('value_mode')
    if mode=='AUTO':
        if request.get('path')not in (None,''):raise RelationalClientError('AUTO has no explicit path')
        value=':auto:'
    elif mode=='PATH':
        text=request.get('path')
        if not isinstance(text,str) or not text or '\x00'in text or len(text.encode())>16384 or not Path(text).is_absolute():
            raise RelationalClientError('Select an absolute native lock-proxy path')
        path=Path(text).resolve(strict=False)
        if not path.parent.is_dir() or not path.is_relative_to(root):raise RelationalClientError('Proxy path escaped registered filesystem authority')
        value=str(path)
    else:raise RelationalClientError('Select AUTO or PATH native locking')
    reviews=connection._cdeadmin_pragma_policy_reviews;key='lock_proxy_file:'+schema
    identity=(files[schema],str(root),schema,before,value,native_work_revision)
    if operation=='review':
        review_id=uuid.uuid4().hex;reviews[key]=(review_id,identity)
        return {**result,'review_id':review_id,'expected_value':before,'ready_to_apply':not connection.in_transaction,
                'requested_native_value':value}
    if (request.get('confirmed')is not True or request.get('native_locking_change_confirmed')is not True or
        request.get('expected_value')!=before or reviews.get(key)!=(request.get('review_id'),identity)):
        raise RelationalClientError('Native locking review changed or was not confirmed; review again')
    if connection.in_transaction:raise RelationalClientError('End the caller transaction before changing native locking')
    reviews.pop(key)
    try:
        native=bridge.module.directory(bridge.capsule,'lock_proxy_file',schema,value,1)
        if native['native_result_code'] or native['readback_result_code'] or native['observed_rows']!=1:
            raise RuntimeError('Native lock-proxy result not confirmed')
    except Exception as error:
        failure=RelationalClientError('Native locking outcome unconfirmed; close the original session before another attempt')
        failure.native_outcome='unknown_outcome';raise failure from error
    return {**result,'outcome':'native_applied','effective_value':native['value'],
            'requested_native_value':value,'native_result':native,'file_persisted':None}
