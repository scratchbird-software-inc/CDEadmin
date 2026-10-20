"""Prepare exact retained DDL while preserving the connection's native policy."""
import sqlite3

from .declarations import canonical_create,quote
from .trigger_owners import AuthorizationCleanupUnconfirmed


def source(row):
    kind,path,name=row['kind'],row['path'],row['name']
    metadata=row['native'].get('catalog_metadata',{})
    owner=metadata.get('table_name') if kind in {'index','trigger'} else None
    owner_schema=metadata.get('owner_database') if path[0]=='temp' and kind=='trigger' else path[0]
    return canonical_create(row['native'].get('ddl'),kind,path[0],name,
        owner=owner,owner_schema=owner_schema)


def drop(row):
    kind='TABLE' if row['kind'] in {'fts-table','virtual-table'} else row['kind'].upper()
    if kind not in {'TABLE','VIEW','INDEX','TRIGGER'}:raise ValueError('Select a native SQLite DDL object')
    return 'DROP '+kind+' '+quote(row['path'][0])+'.'+quote(row['name'])


def prepare(client,connection,row,statement,*,operation='create'):
    """Compile an owned statement; never step its normal mutation program.

    Explicit temp.table/view declarations use the ordinary CREATE action. An
    explicitly temp-qualified trigger reports its owning database in CREATE;
    DROP reports its own temp namespace. These are distinct native identities.
    """
    if not hasattr(connection,'_cdeadmin_authorizer'):
        raise ValueError('Retained SQLite DDL requires observable native authorization policy')
    schema=row['path'][0];kind=row['kind'];name=row['name']
    metadata=row['native'].get('catalog_metadata',{})
    if operation=='create':
        if statement!=source(row):raise ValueError('Retained SQLite CREATE differs from its bound native declaration')
        action={'table':sqlite3.SQLITE_CREATE_TABLE,'view':sqlite3.SQLITE_CREATE_VIEW,
            'index':sqlite3.SQLITE_CREATE_TEMP_INDEX if schema=='temp' else sqlite3.SQLITE_CREATE_INDEX,
            'trigger':sqlite3.SQLITE_CREATE_TRIGGER,'fts-table':sqlite3.SQLITE_CREATE_VTABLE,
            'virtual-table':sqlite3.SQLITE_CREATE_VTABLE}[kind]
        owner=metadata.get('table_name') if kind in {'index','trigger'} else None
        if kind in {'fts-table','virtual-table'}:
            from .modules import declaration
            owner=declaration(statement)[1]
        reported_schema=metadata.get('owner_database') if schema=='temp' and kind=='trigger' else schema
        expected=(action,name,owner,reported_schema)
    elif operation=='drop':
        if statement!=drop(row):raise ValueError('Retained SQLite DROP differs from its exact native object')
        family='VTABLE' if kind in {'fts-table','virtual-table'} else kind.upper()
        prefix='DROP_TEMP_' if schema=='temp' and family!='VTABLE' else 'DROP_'
        action=getattr(sqlite3,'SQLITE_'+prefix+family)
        owner=metadata.get('table_name') if kind in {'index','trigger'} else None
        if kind in {'fts-table','virtual-table'}:
            from .modules import declaration
            owner=declaration(row['native']['ddl'])[1]
        expected=(action,name,owner,schema)
    elif operation=='add-column':
        action=sqlite3.SQLITE_ALTER_TABLE
        expected=(action,schema,row['path'][1],None)
    else:raise ValueError('Unknown retained SQLite DDL preparation operation')
    previous=connection._cdeadmin_authorizer;events=[];cursor=None
    def authorize(code,first,second,database,context):
        result=previous(code,first,second,database,context) if previous else sqlite3.SQLITE_OK
        if result==sqlite3.SQLITE_OK and code==action:events.append((code,first,second,database))
        return result
    try:
        connection.set_authorizer(authorize)
        cursor=connection.execute('EXPLAIN '+statement)
        cursor.fetchone()
    finally:
        failed=False
        if cursor is not None:
            try:cursor.close()
            except BaseException:failed=True
        try:connection.set_authorizer(previous)
        except BaseException:failed=True
        if failed:
            client._uncertain.add(id(connection))
            raise AuthorizationCleanupUnconfirmed('Retained SQLite DDL authorization cleanup is unconfirmed; close without replay') from None
    if events!=[expected]:
        raise ValueError('Native SQLite compiled DDL targets another object, namespace or owning relation')
