"""Reviewed extension installation/loading on the original native DuckDB session."""
from copy import deepcopy
import hashlib
import json
import os
import re
import stat
import time
import uuid
from urllib.parse import urlsplit

from ...sdk import RelationalClientError
from ...security.redaction import redact_text
from ..embedded_route import contained_database
from .attachments import catalogs
from .extension_updates import inventory, context

SETTINGS=('enable_external_access','allow_unsigned_extensions','allow_community_extensions',
    'allow_extensions_metadata_mismatch','autoload_known_extensions','autoinstall_known_extensions',
    'custom_extension_repository','autoinstall_extension_repository')


def environment(handle):
    result=context(handle)
    if result['runtime_version']!='v1.5.2':raise ValueError('Exact native DuckDB 1.5.2 session required')
    result['settings']=dict(handle.execute('SELECT name,value FROM duckdb_settings() WHERE name IN ('+
        ','.join(['?']*len(SETTINGS))+') ORDER BY name',SETTINGS).fetchall())
    if set(result['settings'])!=set(SETTINGS):raise ValueError('Native extension admission settings are unavailable')
    return result


def literal(value):return "'"+value.replace("'","''")+"'"


def text(value,label):
    if not isinstance(value,str) or not value or '\x00' in value or len(value.encode())>65536:
        raise ValueError('Select bounded exact '+label)
    return value


def public_url(value):
    value=text(value,'repository URL');parsed=urlsplit(value)
    if parsed.scheme not in {'http','https'} or not parsed.netloc or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValueError('Use a public HTTP(S) repository without inline credentials, query or fragment')
    return value


def file_identity(route,value,directory=False):
    value=text(value,'absolute extension path')
    if not os.path.isabs(value) or os.path.islink(value):raise ValueError('Select an absolute native path without a symbolic-link target')
    resolved=contained_database({**route,'database':value})
    if directory:
        if not os.path.isdir(resolved):raise ValueError('Select an existing repository directory under the registered root')
        try:info=os.stat(resolved)
        except OSError:raise ValueError('The native repository directory is unavailable') from None
        return {'path':resolved,'device':str(info.st_dev),'inode':str(info.st_ino),'directory':True}
    try:descriptor=os.open(resolved,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    except OSError:raise ValueError('The native extension file is unavailable') from None
    try:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=512*1024*1024:
            raise ValueError('Select a native extension file of at most 512 MiB')
        digest=hashlib.sha256();remaining=info.st_size
        while remaining:
            block=os.read(descriptor,min(remaining,1024*1024))
            if not block:raise ValueError('The native extension file changed while being reviewed')
            remaining-=len(block)
            digest.update(block)
        final=os.fstat(descriptor)
        if (final.st_size,final.st_mtime_ns)!=(info.st_size,info.st_mtime_ns):
            raise ValueError('The native extension file changed while being reviewed')
        return {'path':resolved,'device':str(info.st_dev),'inode':str(info.st_ino),
            'bytes':str(info.st_size),'modified_ns':str(info.st_mtime_ns),'sha256':digest.hexdigest()}
    except OSError:raise ValueError('The native extension file could not be observed completely') from None
    finally:os.close(descriptor)


def compile_operation(route,draft):
    allowed={'action','extension_name','source_kind','source','force','repository_kind','repository','version'}
    if not isinstance(draft,dict) or set(draft)-allowed or draft.get('action') not in {'install','load'}:
        raise ValueError('Select a typed native extension INSTALL or LOAD operation')
    name=draft.get('extension_name')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,127}',name):
        raise ValueError('Select an exact native extension name')
    kind=draft.get('source_kind','NAME');identity=None
    if kind=='NAME':
        if draft.get('source') not in (None,'',name):raise ValueError('Named extension source differs from the reviewed native name')
        source=name
    elif kind=='FILE':
        identity=file_identity(route,draft.get('source'));source=identity['path']
    else:raise ValueError('Select an extension name or authorized native extension file')
    force=draft.get('force',False);repository_kind=draft.get('repository_kind','DEFAULT')
    repository=draft.get('repository','');version=draft.get('version','')
    if type(force) is not bool:raise ValueError('FORCE must be boolean')
    if draft['action']=='load' and (force or repository_kind!='DEFAULT' or repository or version):
        raise ValueError('Native LOAD does not accept FORCE, repository or version options')
    if kind=='FILE' and (repository_kind!='DEFAULT' or repository or version):
        raise ValueError('A native extension file supplies its own installation source and version')
    statement=('LOAD ' if draft['action']=='load' else 'FORCE INSTALL ' if force else 'INSTALL ')+literal(source)
    if repository_kind=='ALIAS':
        if not isinstance(repository,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,127}',repository):raise ValueError('Select an exact native repository alias')
        statement+=' FROM "'+repository+'"'
    elif repository_kind=='URL':statement+=' FROM '+literal(public_url(repository))
    elif repository_kind=='DIRECTORY':
        identity=file_identity(route,repository,directory=True);statement+=' FROM '+literal(identity['path'])
    elif repository_kind!='DEFAULT' or repository:raise ValueError('Select a native repository kind explicitly')
    if version:statement+=' VERSION '+literal(text(version,'native extension version'))
    import duckdb
    parsed=duckdb.extract_statements(statement)
    if len(parsed)!=1 or parsed[0].type.name!='LOAD':raise ValueError('Exactly one provider-built native extension statement is required')
    return {'source':statement,'draft':deepcopy(draft),'file_identity':identity,'extension_name':name}


def action(client,handle,route,request):
    if not isinstance(request,dict):raise ValueError('Select a native extension workflow')
    operation=request.get('operation')
    allowed={'operation','draft'} if operation=='review' else {'operation','review_id','review_digest','confirmation','confirmed'} if operation=='apply' else {'operation','review_id'} if operation=='receipt' else {'operation'}
    if operation not in {'inventory','review','apply','receipt'} or set(request)-allowed:raise ValueError('Unknown native extension request')
    session=client._attachment_contexts.get(id(handle))
    if not session or session['route']!=route:raise ValueError('The original native extension session or registration changed')
    scope=session['session_scope_id'];reviews=client._extension_reviews;now=time.monotonic()
    def public(record):return deepcopy({key:value for key,value in record.items() if key not in {'compiled','baseline','environment','deadline'}})
    if operation in {'apply','receipt'}:
        record=reviews.get(request.get('review_id'))
        if not record or record['session_scope_id']!=scope:raise ValueError('The extension receipt belongs to another or closed native session')
        if operation=='receipt':return public(record)
        if request.get('review_digest')!=record['review_digest']:raise ValueError('The native extension review changed')
        if record['state']!='reviewed':return public(record)
    original=next((row for row in catalogs(handle) if row['name']==session['origin'][0]),None)
    if not original or (original['name'],original['oid'],original['path'])!=(session['origin'][0],str(session['origin'][1]),session['origin'][2]):
        raise ValueError('The original native catalog identity changed')
    before=inventory(handle);observed_environment=environment(handle)
    def reviewed_compilation(draft):
        compiled=compile_operation(route,draft)
        name=compiled['extension_name'].lower()
        target=next((row for row in before if row['extension_name'].lower()==name or
            name in [alias.lower() for alias in row['aliases']]),None)
        if target is not None:
            compiled['extension_name']=target['extension_name']
            if draft['action']=='load' and draft.get('source_kind','NAME')=='NAME' and target['installed'] and not target['loaded'] and target['install_mode']!='STATICALLY_LINKED':
                path=target['install_path']
                # This path is observed from the native installed-extension
                # catalog. Caller-selected files still require the route root.
                compiled['installed_file_identity']=file_identity({**route,'filesystem_root':os.path.dirname(path)},path)
        return compiled
    if operation=='inventory':return {'extensions':before,'context':observed_environment,'session_scope_id':scope,'caller_transaction_decision_requested':False}
    if operation=='review':
        active={value['session_scope_id'] for value in client._attachment_contexts.values()}
        for key in list(reviews):
            if (reviews[key]['deadline']<now and reviews[key]['state']=='reviewed') or reviews[key]['session_scope_id'] not in active:del reviews[key]
        if len(reviews)>=256:raise ValueError('Native extension receipt capacity reached')
        compiled=reviewed_compilation(request.get('draft'))
        record={'review_id':str(uuid.uuid4()),'state':'reviewed','session_scope_id':scope,'deadline':now+300,
            'compiled':compiled,'source':compiled['source'],'extension_name':compiled['extension_name'],
            'baseline':before,'environment':observed_environment,'action':compiled['draft']['action'],
            'file_identity':compiled['file_identity'],'automatic_retry':False,'caller_transaction_decision_requested':False,
            'warnings':['INSTALL writes extension files outside database rollback. LOAD runs native code in the original database instance.',
                'FORCE replaces installation files; already loaded code remains loaded until a new native database instance opens.',
                'The native engine can upgrade an HTTP repository URL to HTTPS when httpfs is loaded.',
                'Native signature, repository and external-access policies remain enforced. External repository/file changes are not fenced.']}
        record['review_digest']=hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest();reviews[record['review_id']]=record
        return public(record)
    if record['deadline']<now or request.get('confirmed') is not True or request.get('confirmation')!=record['extension_name']:
        raise ValueError('Confirm the exact reviewed native extension and code/file effects')
    try:rebuilt=reviewed_compilation(record['compiled']['draft'])
    except (OSError,ValueError,RelationalClientError):rebuilt=None
    if rebuilt!=record['compiled'] or before!=record['baseline'] or observed_environment!=record['environment']:
        record.update(state='refused',native_dispatched=False,native_acknowledged=False,reason='Native extension files, inventory or admission settings changed since review')
        return public(record)
    record.update(state='unknown_outcome',native_dispatched=True,native_acknowledged=False,native_file_or_code_effects_possible=True)
    try:
        handle.execute(record['source']);handle.fetchall();record['native_acknowledged']=True
        after=inventory(handle);selected=next((row for row in after if row['extension_name']==record['extension_name']),None)
        verified=selected is not None and selected['installed' if record['action']=='install' else 'loaded'] is True
        requested_version=record['compiled']['draft'].get('version')
        if requested_version:verified=verified and selected['extension_version']==requested_version
        client._observe(handle,blocked=not verified)
        record.update(state='acknowledged',native_extensions=after,rediscovery_verified=verified,loaded_code_replaced=False if record['action']=='install' else None)
    except Exception as error:
        from .driver import uncertain
        try:record['native_extensions_after_error']=inventory(handle)
        except Exception as observed_error:record['observation_error_type']=type(observed_error).__name__
        try:client._observe(handle,blocked=uncertain(error))
        except Exception:client._observe(handle,blocked=True)
        record.update(state='acknowledged' if record['native_acknowledged'] else 'unknown_outcome' if uncertain(error) else 'refused',
            error_type=type(error).__name__,native_message=redact_text(str(error))[:8192],rediscovery_verified=False)
    record['session_reuse_blocked']=bool(client._states[id(handle)].get('session_reuse_blocked'))
    return public(record)
