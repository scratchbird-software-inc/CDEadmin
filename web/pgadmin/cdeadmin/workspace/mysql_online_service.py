"""Controlled DDN ALTER admission on dedicated native connections."""
import atexit
from dataclasses import asdict
from copy import deepcopy

from .mysql_schema_apply import MySQLSchemaApplications
from .mysql_online_jobs import OnlineJobs, status
from .firebird_schema_plan import digest
from ..operations.store import JsonOperationStore
from ..providers.mysql_family.mysql_clone import rows, thread_matches


def action(service,server,operation,request):
    from flask import current_app
    from pgadmin.model import Server,User
    from .mysql_monitoring_host import MySQLMonitoringHost
    if not isinstance(request,dict):raise ValueError('Select a controlled DDN ALTER request')
    target=request.get('database_target_id')
    context,endpoint,provider=service._mysql_catalog_context(server,target)
    provider._require('administer','resource');provider._require('execute')
    base=service.operation_bus.store
    if not isinstance(base,JsonOperationStore):raise ValueError('Controlled ALTER requires durable schema receipts')
    applications=MySQLSchemaApplications(str(base.path)+'.mysql-schema-applications.json')
    owner=service._principal_id(server)
    binding=digest({'context':asdict(context),'route':endpoint['route'],'target':target})
    payload={k:v for k,v in request.items() if k!='database_target_id'}
    if operation=='replicas':
        if set(payload)-{'offset'}:raise ValueError('Select one replica registration page')
        from .mysql_online_replicas import available
        return available(owner,payload.get('offset',0))
    if operation=='status':
        if set(payload)!={'review_id'}:raise ValueError('Select one controlled ALTER receipt')
        return status(applications,payload['review_id'],owner,binding)
    with service._semantic_lock:
        jobs=getattr(service,'mysql_online_ddl_jobs',None)
        if jobs is None:
            jobs=service.mysql_online_ddl_jobs=OnlineJobs();atexit.register(jobs.close)
    if operation in {'cancel','cutover'}:
        if set(payload)!={'review_id'}:raise ValueError('Select one controlled ALTER receipt')
        return (jobs.cancel if operation=='cancel' else jobs.cutover)(applications,payload['review_id'],owner,binding)
    review=applications.get(payload.get('review_id'),owner,binding)
    if operation=='observe':
        if set(payload)!={'review_id'}:raise ValueError('Select one controlled ALTER receipt')
        from .mysql_online_policy import structural_definition
        from ..providers.mysql_family.mysql_catalog import identifier
        connection=provider.client._connect({'route':{**endpoint['route'],'autocommit':True}})
        try:
            native=rows(connection,'SELECT @@server_uuid AS server_uuid')[0]
            if native['server_uuid']!=review['plan']['server_uuid']:raise ValueError('The observed native server changed')
            op=review['plan']['operations'][0]
            native=rows(connection,'SHOW CREATE TABLE '+identifier(op['database'])+'.'+identifier(op['name']))
            definition=next(v for k,v in native[0].items() if k.lower()=='create table')
            observation={'review_id':review['review_id'],'observed':True,'native_definition':definition,
                'structural_sha256':digest(structural_definition(definition,op['context']['sql_mode'])),
                'original_outcome_unchanged':True,'automatic_retry':False,'observed_thread_still_present':
                thread_matches(
                    connection,review.get('controlled_job',{}).get('native_thread',{}))}
            job=review.get('controlled_job',{})
            if job.get('utility_reference'):
                from ..sdk.durable_tool import observe
                observation['utility_process']=observe(job['utility_workspace'],job['utility_reference'],job['utility_perl_sha256'])
                observation['utility_native_thread_still_present']=thread_matches(connection,job.get('utility_native_thread',{}))
                from ..providers.mysql_online_copy import artifacts
                observation['artifacts']=artifacts(connection,review)
            return observation
        finally:provider.client._discard_failed_session(connection)
    if operation!='start':raise ValueError('Unknown controlled ALTER operation')
    if review.get('controlled_job') or review['state']!='reviewed':return status(applications,review['review_id'],owner,binding)
    selected=review['plan']['operations'][0].get('execution')
    if not selected:raise ValueError('Prepare a controlled table ALTER first')
    route=deepcopy(endpoint['route'])
    for key in ('pool_name','pool_size','pool_reset_session','init_command'):route.pop(key,None)
    route.update(autocommit=True,connection_timeout=5,get_warnings=False,raise_on_warnings=False,
        read_timeout=selected['timeout_seconds']+10,write_timeout=5)
    worker=control=secret=None
    monitors=[]
    try:
        worker=provider.client._connect({'route':route})
        control=provider.client._connect({'route':{**route,'read_timeout':5}})
        def identity(connection):
            return rows(connection,'SELECT VERSION() AS version,@@server_uuid AS server_uuid,DATABASE() AS database_name,'
                'CURRENT_USER() AS account,CURRENT_ROLE() AS active_role')[0]
        native=identity(worker)
        if (native!=identity(control) or native['server_uuid']!=review['plan']['server_uuid'] or
                native['version'].split('-')[0]!='9.7.0' or native['database_name']!=review['plan']['database']):
            raise ValueError('Owned controlled ALTER connections reached different native scopes')
        copy=None
        if selected['method']=='pt-online-schema-change':
            from pathlib import Path
            from ..providers.mysql_online_copy import installation
            if installation()!=review['plan']['operations'][0].get('copy_admission',{}).get('tool'):
                raise ValueError('The reviewed utility installation changed')
            reference=route.get('credential_reference_id') or route.get('credential_references',{}).get('database_password')
            if reference is None:raise ValueError('Online-copy requires its registered native password reference')
            secret=provider.permissions.acquire_secret(str(reference),route['principal_reference'],'provider_tool','database_password')
            from .mysql_online_replicas import open_monitors
            monitors=open_monitors(service,owner,review['plan']['operations'][0]['copy_admission'].get('replicas',[]),review['plan']['server_uuid'])
            copy={'secret':secret,'route':route,'workspace':Path(str(base.path)+'.mysql-online-copy')/review['review_id'],'swapped':False,'monitors':monitors}
        app=current_app._get_current_object();configuration=MySQLMonitoringHost._configuration(server);sid=server.id
        def authorize():
            with app.app_context():
                live=Server.query.filter_by(id=sid,user_id=owner).first()
                if live is None or User.query.filter_by(id=owner,active=True).first() is None or MySQLMonitoringHost._configuration(live)!=configuration:
                    raise ValueError('Controlled ALTER owner or registration changed')
                provider._require('administer','resource');provider._require('execute')
                for item in review['plan']['operations'][0].get('copy_admission',{}).get('replicas',[]):
                    replica=Server.query.filter_by(id=item['endpoint_id'],user_id=owner).first()
                    if replica is None or MySQLMonitoringHost._configuration(replica)!=item['configuration_sha256']:
                        raise ValueError('A reviewed replica registration changed during controlled ALTER')
        result=jobs.start(applications,payload,owner,binding,worker,control,provider.client._discard_failed_session,authorize,copy=copy)
        worker=control=None
        secret=None
        monitors=[]
        return result
    finally:
        if worker is not None:provider.client._discard_failed_session(worker)
        if control is not None:provider.client._discard_failed_session(control)
        if secret is not None:secret.close()
        for _item,connection,dispose in monitors:dispose(connection)
