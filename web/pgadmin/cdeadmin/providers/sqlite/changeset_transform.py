"""Exact public native changeset transforms; no SQL data mutation is requested."""
import os
import stat

from .session_api import SessionAPIError


def options(value):
    if not isinstance(value,dict) or set(value)-{'operation','schema_database','patchset_output','timeout_seconds'}:
        raise SessionAPIError('Select native changeset transformation options')
    operation=value.get('operation');database=value.get('schema_database');patchset=value.get('patchset_output');timeout=value.get('timeout_seconds',3600)
    if not isinstance(operation,str) or operation not in {'invert','concat','merge','rebase'}:raise SessionAPIError('Select native invert, concat, merge or rebase')
    if database is not None and (not isinstance(database,str) or not database or '\x00' in database):raise SessionAPIError('Select an exact native schema basis or none')
    if patchset is not None and type(patchset) is not bool:raise SessionAPIError('Select native changegroup output configuration or automatic format')
    if operation!='merge' and (database is not None or patchset is not None):raise SessionAPIError('Schema and output configuration apply only to native changegroups')
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):raise SessionAPIError('Select a positive native transform duration or no deadline')
    return {'operation':operation,'schema_database':database,'patchset_output':patchset,'timeout_seconds':timeout}


def transform(api,descriptors,output,selected,*,cancel_descriptor=-1):
    selected=options(selected)
    if api.program.get('native_session_revision',0)<3:raise SessionAPIError('The native SQLite helper lacks streaming transformation support')
    if not isinstance(descriptors,(list,tuple)) or not 1<=len(descriptors)<=100 or any(type(value) is not int or value<0 for value in descriptors):
        raise SessionAPIError('Select between one and 100 owned input descriptors')
    if len(set(descriptors))!=len(descriptors):raise SessionAPIError('Each ordered input requires its own independently positioned descriptor')
    operation=selected['operation']
    if operation=='invert' and len(descriptors)!=1 or operation=='concat' and len(descriptors)!=2 or operation=='rebase' and len(descriptors)<2:
        raise SessionAPIError('Native transform input count differs from its operation')
    if type(output) is not int or output<0 or type(cancel_descriptor) is not int or cancel_descriptor<-1:
        raise SessionAPIError('Select owned output and cancellation descriptors')
    output_info=os.fstat(output)
    if not stat.S_ISREG(output_info.st_mode):raise SessionAPIError('Native transform output must be an owned regular file')
    for descriptor in descriptors:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or (info.st_dev,info.st_ino)==(output_info.st_dev,output_info.st_ino):
            raise SessionAPIError('Native transform inputs must be separate regular files')
        os.lseek(descriptor,0,os.SEEK_SET)
    database=selected['schema_database']
    if database is not None and database not in {row[1] for row in api.connection.execute('PRAGMA database_list')}:
        raise SessionAPIError('The selected native schema is not attached to the owned transform connection')
    return api.call('transform_file',operation,output,cancel_descriptor,database,
        -1 if selected['patchset_output'] is None else int(selected['patchset_output']),*descriptors)
