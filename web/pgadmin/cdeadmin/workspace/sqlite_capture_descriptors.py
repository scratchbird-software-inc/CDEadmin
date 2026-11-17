"""Typed descriptor adapters for existing native capture and artifact services."""
from copy import deepcopy
GROUPS={'capture': ['inventory', 'open', 'status', 'close', 'attach', 'configure', 'object_config', 'diff', 'table_filter'], 'export': ['list', 'status', 'cancel', 'reconcile', 'files', 'remove_artifact', 'start', 'review'], 'apply': ['list', 'status', 'cancel', 'reconcile', 'files', 'remove_artifact', 'start', 'catalog', 'sources', 'review', 'conflict', 'decide'], 'transform': ['list', 'status', 'cancel', 'reconcile', 'files', 'remove_artifact', 'start', 'catalog', 'review', 'schemas', 'sources'], 'inspection': ['list', 'status', 'cancel', 'reconcile', 'files', 'remove_artifact', 'start', 'catalog', 'review_page', 'review_cell', 'review_extract', 'result'], 'diff': ['list', 'status', 'cancel', 'reconcile', 'files', 'remove_artifact', 'start', 'catalog', 'tables', 'review'], 'upload': ['list', 'status', 'cancel', 'reconcile', 'files', 'remove_artifact', 'catalog', 'create', 'chunk', 'seal']}
GROUPS['delivery']=['export', 'apply', 'transform', 'inspection', 'diff', 'upload', 'conflict_value']
DELIVERY_ACTIONS={'export':'sqlite_capture_export_download','apply':'sqlite_changeset_download','transform':'sqlite_changeset_transform_download','inspection':'sqlite_changeset_inspect_download','diff':'sqlite_changeset_diff_download','upload':'sqlite_changeset_upload_download','conflict_value':'sqlite_changeset_conflict_value_download'}
TRANSPORTS={'delivery':'workspace_form_download','capture':'sqlite_native_sessions','export':'sqlite_capture_export',
 'apply':'sqlite_changeset','transform':'sqlite_changeset','inspection':'sqlite_changeset','diff':'sqlite_changeset','upload':'sqlite_changeset'}
PREFIXES={'apply':'','transform':'transform_','inspection':'inspect_','diff':'diff_','upload':'upload_'}

def groups():
 return {group:dict(transport=TRANSPORTS[group],operations=ops,permissions=['execute','administer'],
   admission='Owned native endpoint/target/session or durable job; runtime helper and native source identities checked by existing backend.',
   outcomes=['state','job_id','review_digest','program','result','worker_active','commit_returned','artifact'],
   scope=('Original retained connection; captures observe changes, not commits.'if group=='capture'else
          'Durable native job; application-owned file/worker scope. Never infer finality from cancellation or retry an uncertain dispatch.'))
         for group,ops in GROUPS.items()}

def compile_fields(identity,request,fields):
 group=next(group for group in GROUPS if identity.startswith('editor_'+group+'_'))
 operation=identity.removeprefix('editor_'+group+'_');result={}
 for field in fields:
  key=field['field_id']
  if key not in request:continue
  value=request[key]
  if value=='' and not field.get('required'):continue
  path=field.get('backend_field_id',key).split('.');target=result
  for part in path[:-1]:target=target.setdefault(part,{})
  target[path[-1]]=deepcopy(value)
 if group=='delivery':return 'workspace_form_download',dict(operation=DELIVERY_ACTIONS[operation],**result)
 if group=='capture':
  if operation=='attach':
   mode=result.pop('table_mode')
   if mode=='ALL':result['table_name']=None
   elif not result.get('table_name'):raise ValueError('Select an exact table or explicit ALL')
  if operation=='table_filter':
   mode=result.pop('pattern_mode')
   if mode=='ALL':result['pattern']=None
   elif not result.get('pattern'):raise ValueError('Select an exact pattern or explicit ALL')
  if operation=='configure':
   for key in ('enabled','indirect'):
    mode=result.pop(key+'_mode')
    if mode!='PRESERVE':result[key]=mode=='ON'
  return TRANSPORTS[group],dict(operation=operation,**result)
 deadline=result.pop('no_deadline',False)
 if deadline:
  if group=='export':result['timeout_seconds']=None
  else:result.setdefault('options',{})['timeout_seconds']=None
 if group=='transform'and operation=='review':
  mode=result.pop('patchset_mode');result['options']['patchset_output']=None if mode=='AUTO'else mode=='PATCHSET'
 if group=='inspection'and operation.startswith('review_'):
  result['options']['mode']=operation.removeprefix('review_');operation='review'
 if operation=='review'and group in {'apply','transform','inspection','diff'}:
  if group=='apply':from ..providers.sqlite.changeset_apply import options
  elif group=='transform':from ..providers.sqlite.changeset_transform import options
  elif group=='inspection':from ..providers.sqlite.changeset_inspection import options
  else:from ..providers.sqlite.diff_export import options
  result['options']=options(result['options'])
 if group=='upload'and operation=='create':
  from .sqlite_upload_jobs import options
  result['options']=options(result['options'])
 return TRANSPORTS[group],dict(operation=PREFIXES.get(group,'')+operation,**result)

def dispatch(service,server,action,request,target,session):
 request=deepcopy(request);operation=request.pop('operation');request['database_target_id']=target
 if action=='sqlite_capture_export':
  if operation=='review':request['session_id']=session
  return service.sqlite_capture_export(server,operation,request)
 if operation in {'diff_catalog','diff_tables','diff_review'}:request['session_id']=session
 return service.sqlite_changeset(server,operation,request)
