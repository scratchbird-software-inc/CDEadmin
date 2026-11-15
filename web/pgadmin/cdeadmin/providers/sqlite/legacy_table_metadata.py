"""Native pre-table_list classification through empty module constructors.

No user rows or callbacks are copied. Module storage is identified by actual
CREATE authorizer events, never an FTS/RTree filename suffix. An unreproducible
schema remains explicitly unobserved instead of being classified as ordinary.
"""
import sqlite3


def observe(resources):
    from ...workspace.sqlite_columns import _modeled
    from ...workspace.sqlite_retained_schema import _prototype
    from ...workspace.sqlite_schema_plan import _quote
    modeled={key:row for key,row in _modeled(resources).items() if row['system']=='false'}
    namespaces={row['display_path'][0] for row in resources if row['resource_kind'] in {'database','attached-database'}}|{'main'}
    probe=None
    try:
        probe=_prototype({'rows':modeled},namespaces)
        storage=set(probe._cdeadmin_module_storage)
        observed_tables={tuple(row['display_path']) for row in resources if row['resource_kind']=='table'}
        if not storage<=observed_tables:
            raise ValueError('Native constructor storage differs from the captured schema')
        classifications={}
        for row in resources:
            kind=row['resource_kind'];path=row['display_path']
            if kind not in {'table','view','virtual-table','fts-table'} or len(path)!=2:continue
            category=('shadow' if tuple(path) in storage else 'virtual' if kind in {'virtual-table','fts-table'} else kind)
            without_rowid=False
            if category=='table':
                # Since native SQLite3.30, index_info(table-name) reports the
                # native PRIMARY KEY only for WITHOUT ROWID tables.
                without_rowid=probe.execute('PRAGMA '+_quote(path[0])+'.index_info('+_quote(path[1])+')').fetchone() is not None
            classifications[tuple(path)]={'table_list_type':category,'without_rowid':without_rowid,'strict':False}
        for row in resources:
            path=row['display_path'];native=row['native'];parent=tuple(path[:2])
            if parent in storage:native['system_object']=True
            if len(path)==2 and parent in classifications:
                native['catalog_metadata'].update(classifications[parent])
                native['table_classification_observation']={'available':True,'source':'native-empty-schema-module-authorizer-and-index_info',
                    'runtime_version':sqlite3.sqlite_version,'user_data_copied':False}
    except (ValueError,sqlite3.Error) as error:
        for row in resources:
            if row['resource_kind'] in {'table','view','virtual-table','fts-table'}:
                row['native']['table_classification_observation']={'available':False,
                    'source':'native-empty-schema-module-authorizer-and-index_info',
                    'reason':'schema-reproduction-unavailable','error_type':type(error).__name__}
    finally:
        if probe is not None:probe.close()
