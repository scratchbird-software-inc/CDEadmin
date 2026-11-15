"""Explicit process/runtime heap policy; never mislabeled per-connection state."""
import re
import threading
from ...sdk import RelationalClientError

NAMES=('soft_heap_limit','hard_heap_limit')
_LOCK=threading.RLock()


def integer(value):
    if (not isinstance(value,str) or re.fullmatch(r'0|[1-9][0-9]{0,18}',value) is None
            or int(value)>9223372036854775807):
        raise RelationalClientError('Heap bytes require exact nonnegative signed-64-bit decimal text')
    return int(value)


def action(connection,request):
    operation,name=request.get('operation'),request.get('pragma')
    common={'operation','pragma'}
    fields={'inspect':common,'review':common|{'value'},'set_connection_pragma':common|{'value','expected_value','confirmed','process_wide_change_confirmed','irreversible_lowering_confirmed'}}
    if (not isinstance(operation,str) or operation not in fields or not isinstance(name,str)
            or name not in NAMES or set(request)-fields[operation]):
        raise RelationalClientError('Select a named native process heap policy')
    if operation!='inspect':value=integer(request.get('value'))
    if operation=='set_connection_pragma':
        integer(request.get('expected_value'))
        if request.get('confirmed') is not True or request.get('process_wide_change_confirmed') is not True:
            raise RelationalClientError('Confirm impact on every connection using this process SQLite runtime')
        if name=='hard_heap_limit' and request.get('irreversible_lowering_confirmed') is not True:
            raise RelationalClientError('Confirm that SQL cannot raise or restore a lowered native hard heap limit')
    with _LOCK:
        cursor=connection.cursor()
        try:
            cursor.execute('PRAGMA pragma_list')
            if name not in {row[0]for row in cursor.fetchall()}:
                raise RelationalClientError('Native heap policy is absent from this runtime/build')
            def read():
                row=cursor.execute('PRAGMA '+name).fetchone()
                if not row or type(row[0]) is not int or not 0<=row[0]<=9223372036854775807:
                    raise RelationalClientError('Native heap policy observation unavailable')
                return str(row[0])
            def heap_state():
                return {other:str(cursor.execute('PRAGMA '+other).fetchone()[0]) for other in NAMES}
            state_before=heap_state()
            before=read()
            if operation=='set_connection_pragma':
                if before!=request['expected_value']:raise RelationalClientError('Process heap policy changed; review again')
                try:
                    cursor.execute('PRAGMA '+name+'='+str(value));after=read()
                except Exception as error:
                    failure=RelationalClientError('Native process heap outcome unknown; do not automatically retry')
                    failure.native_outcome='unknown_outcome';raise failure from error
            else:after=before
            result={'pragma':name,'before_value':before,'effective_value':after,
                'scope':'application-process/loaded-SQLite-runtime','peer_isolation_claimed':False,
                'heap_state_before':state_before,'heap_state_after':heap_state(),
                'connection_local':False,'file_persisted':False,'transaction_open':connection.in_transaction,
                'commit_requested':False,'rollback_requested':False,'automatic_retry':False,
                'rollback_restores_policy':False,'os_process_memory_cap_claimed':False,
                'unmanaged_native_changes_excluded':False}
            if operation!='inspect':result.update(requested_value=request['value'],expected_value=before)
            if operation=='review':result.update(ready_to_apply=True,warning=(
                'Affects every connection sharing this loaded SQLite runtime, including application stores. This is not an OS memory cap. Native changes outside this controller can race; readback is an observation. '+
                ('The hard limit can only be lowered by PRAGMA; zero or a higher request cannot restore it. A small limit can prevent SQL/cleanup and require process restart. Native hard lowering may also lower the soft limit.' if name=='hard_heap_limit' else
                 'This is an advisory native allocation target, not guaranteed memory usage. Zero disables the soft target; a hard cap can constrain it.')))
            if operation=='set_connection_pragma':result.update(outcome='applied' if after==request['value'] else 'native_adjusted',requested_value_effective=after==request['value'])
            return result
        finally:cursor.close()
