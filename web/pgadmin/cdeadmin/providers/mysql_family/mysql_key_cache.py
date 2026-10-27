"""Reviewed native MyISAM index-cache assignment and preloading."""
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json

from ...sdk import RelationalClientError
from .mysql_catalog import identifier

OPERATIONS = frozenset({'assign_index_cache', 'preload_index_cache'})


def address(path):
    parts = ['table', *path]
    return ('mysql-resource:' + json.dumps(parts, ensure_ascii=False, separators=(',', ':'))
        if any(':' in part for part in parts) else ':'.join(parts))


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping) or not isinstance(target, Mapping):
        raise RelationalClientError('Select a native MySQL index-cache operation')
    allowed = {'confirmation', 'indexes'} | ({'cache_name'} if operation == 'assign_index_cache' else {'ignore_leaves'})
    path = target.get('display_path')
    if (set(draft) - allowed or target.get('resource_kind') != 'table' or
            not isinstance(path, list) or len(path) != 2 or
            any(not isinstance(value, str) or not value or '\x00' in value or len(value)>64 for value in path) or
            target.get('resource_id') != address(path) or target.get('display_name') != path[-1] or
            draft.get('confirmation') != path[-1]):
        raise RelationalClientError('Confirm the exact native MySQL table address')
    indexes = draft.get('indexes', [])
    if (not isinstance(indexes, list) or len(indexes)>64 or
            any(not isinstance(name,str) or not name or len(name)>64 or '\x00' in name for name in indexes) or
            len(set(indexes)) != len(indexes)):
        raise RelationalClientError('Select at most 64 distinct exact native index names; empty means all indexes')
    source = ('CACHE INDEX ' if operation == 'assign_index_cache' else 'LOAD INDEX INTO CACHE ') + '.'.join(map(identifier,path))
    if indexes:source += ' INDEX (' + ','.join(map(identifier,indexes)) + ')'
    if operation == 'assign_index_cache':
        name = draft.get('cache_name','default')
        if not isinstance(name,str) or not name or len(name)>64 or '\x00' in name:
            raise RelationalClientError('Specify a native key-cache name of 1 to 64 characters')
        source += ' IN ' + ('DEFAULT' if name == 'default' else identifier(name))
    else:
        leaves = draft.get('ignore_leaves',False)
        if type(leaves) is not bool:raise RelationalClientError('IGNORE LEAVES must be boolean')
        if leaves:source += ' IGNORE LEAVES'
    return {'statements':[{'source':source,'parameters':()}],
        'mysql_key_cache':{'operation':operation,'draft':dict(draft),'target':deepcopy(dict(target))},
        'warnings':['Native CACHE INDEX / LOAD INDEX INTO CACHE have implicit commits and process cache effects. The operation uses an independent connection and cannot roll back another session.',
            'Only native MyISAM implements these handlers in this profile. A named cache must already be configured. Native result rows distinguish errors/notes from positive OK status; no cache contents or durable recovery guarantee is inferred.']}


def environment(cursor):
    cursor.execute('SELECT VERSION(),@@server_uuid,CURRENT_USER(),USER(),CURRENT_ROLE()')
    row=cursor.fetchone()
    if not row or len(row)!=5 or any(not isinstance(value,str) for value in row) or row[0].split('-')[0]!='9.7.0':
        raise RelationalClientError('Exact native MySQL cache execution identity is unavailable')
    return dict(zip(('version','server_uuid','effective_principal','authenticated_principal','active_roles'),row))


def observe(cursor, path, indexes):
    cursor.execute('SELECT ENGINE,TABLE_TYPE FROM information_schema.TABLES WHERE CAST(TABLE_SCHEMA AS BINARY)=CAST(%s AS BINARY) AND CAST(TABLE_NAME AS BINARY)=CAST(%s AS BINARY)',tuple(path))
    row=cursor.fetchone()
    if row != ('MyISAM','BASE TABLE'):
        raise RelationalClientError('The exact native target must be a visible MyISAM base table')
    cursor.execute('SHOW CREATE TABLE '+'.'.join(map(identifier,path)))
    declaration=cursor.fetchone()
    if not declaration or declaration[0]!=path[1] or not isinstance(declaration[1],str):
        raise RelationalClientError('The exact native MyISAM table definition is unavailable')
    cursor.execute('SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS WHERE CAST(TABLE_SCHEMA AS BINARY)=CAST(%s AS BINARY) AND CAST(TABLE_NAME AS BINARY)=CAST(%s AS BINARY) ORDER BY INDEX_NAME',tuple(path))
    names=[row[0] for row in cursor.fetchall()]
    if any(name not in names for name in indexes):raise RelationalClientError('A selected exact native MyISAM index is unavailable')
    return {'engine':'MyISAM','indexes':names,'definition_sha256':hashlib.sha256(declaration[1].encode('utf8')).hexdigest()}


def bind_review(client, planned):
    payload=planned['provider_payload'];intent=payload['compiled']['mysql_key_cache']
    handle=client._connect({'route':payload['route']});cursor=None
    try:
        handle.autocommit=True;cursor=handle.cursor()
        observed=environment(cursor);baseline=observe(cursor,intent['target']['display_path'],intent['draft'].get('indexes',[]))
        intent['review']={'execution_identity':observed,'baseline':baseline}
        planned['command_preview'].update(native_execution_identity=observed,native_index_cache_context=baseline)
        return planned
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client, request, connection=None):
    if connection is not None:raise RelationalClientError('MySQL cache maintenance requires an independently owned connection')
    payload=request['provider_payload'];compiled=payload['compiled'];intent=compiled['mysql_key_cache']
    checked=deepcopy(compiled);review=checked['mysql_key_cache'].pop('review',None)
    if not isinstance(review,Mapping) or compile_operation(intent['operation'],intent['draft'],intent['target'])!=checked:
        raise RelationalClientError('Review the exact native MySQL cache operation before dispatch')
    handle=client._connect({'route':payload['route']});cursor=None;dispatched=acknowledged=False
    try:
        handle.autocommit=True;handle.get_warnings=True;handle.raise_on_warnings=False
        cursor=handle.cursor();observed=environment(cursor)
        before=observe(cursor,intent['target']['display_path'],intent['draft'].get('indexes',[]))
        if observed!=review['execution_identity'] or before!=review['baseline']:
            raise RelationalClientError('The native MyISAM definition, indexes or execution identity changed since review')
        dispatched=True;cursor.execute(compiled['statements'][0]['source']);acknowledged=True
        rows=cursor.fetchall();names=[str(column[0]).lower() for column in cursor.description or ()]
        results=[dict(zip(names,row)) for row in rows]
        positive=bool(results) and all(row.get('msg_type')=='status' and row.get('msg_text')=='OK' for row in results)
        warnings=[{'level':level,'code':code,'message':text} for level,code,text in (cursor.warnings or ())]
        after=observe(cursor,intent['target']['display_path'],intent['draft'].get('indexes',[]))
        return {'accepted':positive,'native_implicit_commit':True,'commit_requested':False,'rollback_requested':False,
            'staged_in_provider_session':False,'automatic_retry':False,'native_warnings':warnings,
            'driver_observation_only':True,'transaction_finality_interpreted_by_common_code':False,
            'index_cache_observation':{'native_acknowledged':True,'native_effect_acknowledged':positive,
                'native_results':results,'execution_identity':observed,'before':before,'after':after,
                'definition_unchanged':before==after,'cache_contents_observed':False}}
    except Exception as error:
        failure=error if isinstance(error,RelationalClientError) else RelationalClientError('Native MySQL index-cache operation failed ('+type(error).__name__+')')
        failure.native_dispatched=dispatched;failure.native_acknowledged=acknowledged;failure.automatic_retry=False
        failure.errno=getattr(error,'errno',None);failure.sqlstate=getattr(error,'sqlstate',None)
        failure.native_status_codes=(failure.errno,) if type(failure.errno) is int else ()
        raise failure from None
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)
