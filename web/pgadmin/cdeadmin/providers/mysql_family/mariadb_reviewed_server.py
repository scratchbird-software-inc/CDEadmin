"""Shared owned-connection lifecycle for MariaDB-specific managed commands."""
from collections.abc import Mapping
from copy import deepcopy
from ...sdk import RelationalClientError
from .mariadb_server_diagnostics import environment, target_uid
from .mysql_engine_diagnostics import observer_route, release
from .mariadb_values import value


def pack(module, operation, draft, target, sql, parameters=(), implicit_commit=False):
    return {'statements': [{'source': sql, 'parameters': parameters}], module.KEY: {
        'operation': operation, 'draft': deepcopy(dict(draft)), 'target': deepcopy(dict(target)),
        'server_uid': target_uid(target), 'native_implicit_commit': implicit_commit},
        'warnings': list(module.WARNINGS)}


def bind_review(module, client, planned):
    payload=planned['provider_payload'];intent=payload['compiled'][module.KEY]
    handle=client._connect({'route':observer_route(payload)});cursor=None
    try:
        handle.autocommit=True;cursor=handle.cursor();actor=environment(cursor)
        if actor['server_uid']!=intent['server_uid']:raise RelationalClientError('The native server differs from the selected target')
        before=module.observe(cursor,intent)
        intent['review']={'execution_identity':actor,'before':before}
        planned['command_preview'].update(native_execution_identity=actor,native_management_observation=before)
        return planned
    finally:
        if not release(client,handle,cursor)['connection_released']:raise RelationalClientError('Native review connection release is unconfirmed')


def apply(module,client,request,connection=None):
    if connection is not None:raise RelationalClientError('This native workflow requires an independent connection')
    payload=request['provider_payload'];compiled=payload['compiled'];intent=compiled[module.KEY]
    checked=deepcopy(compiled);review=checked[module.KEY].pop('review',None)
    if not isinstance(review,Mapping)or module.compile_operation(intent['operation'],intent['draft'],intent['target'])!=checked:
        raise RelationalClientError('Review the exact native management command before dispatch')
    handle=client._connect({'route':observer_route(payload)});cursor=None
    dispatched=acknowledged=False;result=failure=None
    try:
        handle.autocommit=True;cursor=handle.cursor();actor=environment(cursor)
        before=module.observe(cursor,intent)
        if actor!=review['execution_identity']or (intent['operation'] not in module.INSPECTIONS and before!=review['before']):
            raise RelationalClientError('Native execution identity or reviewed state changed')
        statement=compiled['statements'][0]
        cursor.execute('SET SESSION lock_wait_timeout=15')
        dispatched=True
        cursor.execute(statement['source'],statement['parameters'])
        columns=[col[0]for col in cursor.description or ()];rows=[]
        if columns:
            for _ in range(20001):
                row=cursor.fetchone()
                if row is None:break
                if len(rows)==20000:raise RelationalClientError('Native management result exceeds 20000 rows')
                rows.append([value(cell)for cell in row])
        acknowledged=True
        cursor.execute('SHOW WARNINGS LIMIT 65');warning_rows=cursor.fetchall()
        warnings=[dict(zip(('level','code','message'),row))for row in warning_rows[:64]]
        after=module.observe(cursor,intent)
        result=dict(accepted=True,commit_requested=False,rollback_requested=False,
            native_implicit_commit=intent['native_implicit_commit'],staged_in_provider_session=False,
            automatic_retry=False,transaction_finality_interpreted_by_common_code=False,
            management_observation=dict(operation=intent['operation'],execution_identity=actor,
                native_dispatched=True,native_acknowledged=True,columns=columns,rows=rows,
                before=before,after=after,native_warnings=warnings,warnings_truncated=len(warning_rows)>64,
                native_reported_success=module.reported_success(intent,columns,rows),
                native_effect_rollback_available=False))
        return result
    except Exception as error:
        failure=error if isinstance(error,RelationalClientError)else RelationalClientError('Native management failed ('+type(error).__name__+')')
        failure.errno=getattr(error,'errno',None);failure.sqlstate=getattr(error,'sqlstate',None)
        failure.native_dispatched=dispatched;failure.native_acknowledged=acknowledged
        failure.native_status_codes=(failure.errno,)if type(failure.errno)is int else ()
        failure.automatic_retry=False
        raise failure from None
    finally:
        cleanup=release(client,handle,cursor)
        if result is not None:result['connection_release']=cleanup
        elif failure is not None:failure.connection_release=cleanup
