"""One-use, host-authorized publication of native directory startup policies."""
from datetime import datetime,timezone
import json
import hashlib
import os
from pathlib import Path
import uuid
import sqlite_startup as codec
from ...sdk import RelationalClientError
from ...operations.fileio import exclusive_file_lock,private_file

NAMES=codec.NAMES


def action(connection,request, *, native_work_revision=None,host_authorized=False,filename=None,filesystem_root=None,principal=None,endpoint_id=None):
    name,operation=request.get('pragma'),request.get('operation')
    common={'operation','pragma'}
    fields={'inspect':common,'review':common|{'value_mode','directory'},
        'set_connection_pragma':common|{'value_mode','directory','review_id','expected_policy_revision','confirmed','process_startup_change_confirmed'}}
    if (not isinstance(name,str) or name not in NAMES or not isinstance(operation,str)
            or operation not in fields or set(request)-fields[operation]):
        raise RelationalClientError('Select a typed host startup directory policy')
    if host_authorized is not True:raise RelationalClientError('Application-host Administrator authority is required')
    if not filename:raise RelationalClientError('The application-host startup policy store is unavailable')
    path=Path(filename).absolute()
    # No live PRAGMA setter is invoked. Other SQLite handles (configuration,
    # designs, collectors) can be open even in a single-threaded request.
    if operation!='inspect':
        try:setting=codec.directory_setting(request.get('value_mode'),request.get('directory'),filesystem_root)
        except (OSError,ValueError)as error:raise RelationalClientError(str(error))from None
        if type(native_work_revision)is not int or native_work_revision<0:
            raise RelationalClientError('Driver-owned original-session work revision required')
    if operation=='set_connection_pragma' and (request.get('confirmed')is not True or request.get('process_startup_change_confirmed')is not True):
        raise RelationalClientError('Confirm persistent host policy for the next process startup')
    try:policy,revision=codec.read_policy(path)
    except (OSError,ValueError)as error:raise RelationalClientError(str(error))from None
    state=codec.applied_state()
    bridge=getattr(connection,'_cdeadmin_config_api',None)
    bridge=bridge if bridge is not None and not bridge.closed else None
    probe=None
    if bridge is not None:
        probe=bridge.module.pragma_names(bridge.capsule)
    observed=bool(probe and probe.get('namespace_observed') and probe.get('native_probe_closed'))
    result={'pragma':name,'scope':'application-host/future-process-startup',
        'configured_startup_setting':(policy or {}).get('settings',{}).get(name),
        'policy_revision':revision,'native_current_value_observed':False,'native_applied':False,
        'source_sql_commands_sent':0,'source_transaction_finalized':False,'automatic_retry':False,
        'current_process_startup_revision':state.get('policy_revision')if state else None,
        'restart_required':bool(policy and (state is None or state.get('policy_revision')!=revision)),
        'process_restart_performed':False,'native_component_bound':bridge is not None,
        'native_name_availability_observed':observed,'native_name_present':name in probe['names'] if observed else None}
    if operation=='inspect':return result
    if bridge is None:raise RelationalClientError('Install/bind the native configuration component before reviewing startup policy')
    if not observed:
        raise RelationalClientError('Native startup PRAGMA namespace could not be qualified')
    if name not in probe['names']:
        raise RelationalClientError('This startup directory setting is absent from the native runtime/build')
    if not isinstance(principal,(str,int)) or not str(principal) or len(str(principal))>128:
        raise RelationalClientError('A trusted host approval principal is required')
    reviews=connection._cdeadmin_pragma_policy_reviews
    key='startup:'+name
    if operation=='review':
        review_id=uuid.uuid4().hex
        reviews[key]={'review_id':review_id,'setting':setting,'revision':revision,'native_revision':native_work_revision,'principal':str(principal),'endpoint_id':str(endpoint_id or '')}
        return {**result,'review_id':review_id,'requested_startup_setting':setting,'expected_policy_revision':revision,
            'ready_to_publish':True,'native_dispatch_deferred':True,
            'warning':'This persists an application-host policy. It does not change this live process or its TEMP data. A fresh process applies native settings before SQLite is initialized or any application database opens. Restart is a separate user action; directory/host admission failure prevents startup and has its own receipt. Native VFS/compile settings can ignore physical storage choices.'}
    retained=reviews.get(key)
    if (not isinstance(retained,dict) or retained['review_id']!=request.get('review_id') or retained['setting']!=setting or
            retained['native_revision']!=native_work_revision or retained['revision']!=request.get('expected_policy_revision') or
            retained['principal']!=str(principal) or retained['endpoint_id']!=str(endpoint_id or '')):
        raise RelationalClientError('Startup policy review or original work changed; review again')
    if revision!=retained['revision']:raise RelationalClientError('Host startup policy changed; review again')
    try:
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        information=path.parent.stat()
        if os.name!='nt' and (information.st_mode&0o022 or information.st_uid!=os.getuid()):
            raise ValueError('Startup policy parent must be application-owned and not writable by others')
        lock_path=path.with_name('.'+path.name+'.lock')
        descriptor=os.open(lock_path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(descriptor,'r+b')as lock:
            private_file(lock_path)
            with exclusive_file_lock(lock.fileno()):
                current,current_revision=codec.read_policy(path)
                if current_revision!=retained['revision']:raise ValueError('Host startup policy changed; review again')
                codec.validate_setting(setting,observe_filesystem=True)
                value=current or {'schema':codec.SCHEMA,'settings':{}}
                value['settings'][name]=setting
                value.update(accepted_at=datetime.now(timezone.utc).isoformat(),accepted_by_user_id=str(principal or ''),
                    source_endpoint_id=str(endpoint_id or ''),review_id=retained['review_id'])
                data=(json.dumps(value,indent=2)+'\n').encode('utf8')
                if len(data)>codec.MAX_POLICY_BYTES:raise ValueError('Startup policy exceeds its bounded store')
                reviews.pop(key)
                try:
                    codec.publish_policy_file(path,data)
                    _,published_revision=codec.read_policy(path)
                except Exception as error:
                    failure=RelationalClientError('Startup policy publication unconfirmed; inspect the policy store before deciding to publish again')
                    failure.configuration_outcome='unknown_outcome';raise failure from error
                if published_revision!=hashlib.sha256(data).hexdigest():
                    failure=RelationalClientError('Startup policy publication changed during confirmation; inspect before publishing again')
                    failure.configuration_outcome='unknown_outcome';raise failure
    except RelationalClientError:raise
    except (OSError,ValueError)as error:raise RelationalClientError(str(error))from None
    return {**result,'outcome':'staged_for_next_process_startup','accepted':True,'file_persisted':True,
        'configured_startup_setting':setting,'policy_revision':published_revision,'restart_required':True,
        'native_dispatch_deferred':True,'native_applied':False,'source_temp_objects_changed':False}
