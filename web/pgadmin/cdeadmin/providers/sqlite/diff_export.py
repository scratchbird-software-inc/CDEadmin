"""Disposable native session diffs; user SQL and existing captures stay owned."""
import sqlite3

from .session_api import SessionAPIError


def options(value):
    allowed={'database','source_database','table_name','kind','estimate_size','track_rowids','timeout_seconds'}
    if not isinstance(value,dict) or set(value)-allowed:raise SessionAPIError('Select native table comparison options')
    result={**{'kind':'changeset','estimate_size':False,'track_rowids':False,'timeout_seconds':3600},**value}
    if any(not isinstance(result.get(name),str) or not result[name] or '\x00' in result[name]
           for name in ('database','source_database','table_name')):
        raise SessionAPIError('Select exact destination/source database and table names')
    if not isinstance(result['kind'],str) or result['kind'] not in {'changeset','patchset'} or any(type(result[key]) is not bool for key in ('estimate_size','track_rowids')):
        raise SessionAPIError('Select a native table comparison format and capture switches')
    timeout=result['timeout_seconds']
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):
        raise SessionAPIError('Select a positive native comparison duration or no deadline')
    return result


def export_difference(api,database,source_database,table_name,kind,descriptor,*,
                      cancel_event,cancel_descriptor,progress,acknowledge,
                      estimate_size=False,track_rowids=False):
    connection=api.connection
    if any(not isinstance(item,str) or not item or '\x00' in item for item in (database,source_database,table_name)):
        raise SessionAPIError('Select exact destination/source database and table names')
    if not isinstance(kind,str) or kind not in {'changeset','patchset'} or type(estimate_size) is not bool or type(track_rowids) is not bool:
        raise SessionAPIError('Select native table-diff format and capture switches')
    attached={row[1] for row in connection.execute('PRAGMA database_list')}
    if database not in attached or source_database not in attached:
        raise SessionAPIError('The reviewed native table-diff databases are not attached')
    before=connection._cdeadmin_progress_handler
    if before!=(None,0):raise SessionAPIError('The query connection already owns a native progress handler')
    if cancel_event.is_set():raise SessionAPIError('Native table comparison was stopped',sqlite3.SQLITE_INTERRUPT)
    capture=api.open(database,estimate_size=estimate_size,track_rowids=track_rowids)
    def observe():
        progress['vm_progress_callbacks']+=1
        return int(cancel_event.is_set())
    try:
        acknowledge('capture_created',{'capture_id':capture})
        connection.set_progress_handler(observe,1000)
        failure=None
        try:api.diff(capture,source_database,table_name)
        except (SessionAPIError,sqlite3.Error) as error:
            failure=error
        finally:connection.set_progress_handler(*before)
        code=0 if failure is None else getattr(failure,'native_result_code',getattr(failure,'sqlite_errorcode',None))
        acknowledge('diff_returned',{'native_result_code':code,'vm_progress_callbacks':str(progress['vm_progress_callbacks']),
            'source_transaction_open_after':connection.in_transaction,'partial_capture_discarded_on_failure':failure is not None})
        if failure is not None:
            if isinstance(failure,SessionAPIError):raise failure
            raise SessionAPIError('Native table comparison did not complete',code) from failure
        observed=api.status(capture)
        if cancel_event.is_set():raise SessionAPIError('Native table comparison was stopped before export',sqlite3.SQLITE_INTERRUPT)
        written=api.export(capture,kind,descriptor,cancel_descriptor)
        acknowledge('export_returned',{'native_written_bytes':str(written),'source_transaction_open_after':connection.in_transaction})
        return {'native_written_bytes':str(written),'capture':observed,'vm_progress_callbacks':str(progress['vm_progress_callbacks'])}
    finally:
        # sqlite3session_diff can leave a partial in-memory capture on error.
        # It is private to this operation and is never an existing user capture.
        api.close(capture)
        acknowledge('capture_closed',{'capture_id':capture,'native_capture_close_returned':True})
