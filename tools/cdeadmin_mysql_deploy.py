#!/usr/bin/env python3
"""Local operator CLI for exact, reviewed native MySQL DDN deployments."""
import argparse
from contextlib import contextmanager,redirect_stdout,ExitStack
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web')]
LIMIT=32*1024*1024


def read(path):
    with Path(path).open('rb') as handle:data=handle.read(LIMIT+1)
    if len(data)>LIMIT:raise ValueError('Input exceeds 32 MiB')
    return data.decode('utf8')


def pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('Duplicate deployment JSON property')
        result[key]=value
    return result


def decode(text):
    def invalid(_):raise ValueError('Non-finite deployment JSON value')
    return json.loads(text,object_pairs_hook=pairs,parse_constant=invalid)


@contextmanager
def output(path):
    # Claim the requested private output before native access. Never overwrite
    # an earlier release/review/report, including through an existing symlink.
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w',encoding='utf8') as handle:
        yield handle
        handle.flush();os.fsync(handle.fileno())


@contextmanager
def workspace(args):
    import config
    import builtins
    builtins.SERVER_MODE=None
    from flask_login import login_user,logout_user
    from pgadmin import create_app
    from pgadmin.utils.session import create_session_interface
    from pgadmin.model import User,Server
    from pgadmin.cdeadmin.workspace.mysql_deployment import Deployment,DeploymentError
    if not config.CONFIG_DATABASE_URI and not Path(config.SQLITE_PATH).is_file():
        raise DeploymentError('Initialize the application configuration database before using deployment automation')
    app=create_app('ScratchRobin-mysql-deployment-cli');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    # Native endpoint credential and logout hooks use the application's session
    # identity even in a headless local request. setup.py's cookie-only CLI
    # session is insufficient for those hooks.
    app.session_interface=create_session_interface(app,config.SESSION_SKIP_PATHS)
    server=None;service=None
    with app.test_request_context('/'):
        owner=User.query.filter_by(email=args.user,active=True).first()
        if owner is None:raise DeploymentError('Select an active local application owner')
        # Like setup.py server import/export, this is a trusted local operator
        # command with access to application configuration and native credentials.
        # It does not create a network endpoint or accept remote impersonation.
        if not login_user(owner):raise DeploymentError('Local application owner is inactive')
        try:
            server=Server.query.filter_by(id=args.server_id,user_id=owner.id).first()
            if server is None or server.endpoint_profile is None or server.endpoint_profile.profile_id!='mysql-native':
                raise DeploymentError('Select an owned native MySQL registration')
            password=os.environ.pop(args.password_env,None)
            if not password:raise DeploymentError('The explicitly selected native password environment variable is empty')
            service=app.extensions['cdeadmin_provider_workspace']
            service.endpoint_service.verify_server(server,password=password,database_target_id=args.target_id)
            password=None
            yield Deployment(service,server,args.target_id)
        finally:
            if service is not None:
                jobs=getattr(service,'mysql_online_ddl_jobs',None)
                if jobs is not None:jobs.close()
                if server is not None:service.endpoint_service.forget_server_credentials(server)
            logout_user()


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='operation',required=True)
    pack=sub.add_parser('pack');pack.add_argument('--manifest',required=True);pack.add_argument('--output',required=True)
    for name in ('capture','plan','review','apply','receipt'):
        c=sub.add_parser(name);c.add_argument('--user',required=True);c.add_argument('--server-id',type=int,required=True)
        c.add_argument('--target-id',required=True);c.add_argument('--environment',required=True)
        c.add_argument('--password-env',required=True);c.add_argument('--output',required=True)
        if name!='capture':c.add_argument('--artifact',required=True)
        if name=='review':c.add_argument('--expect-plan',required=True);c.add_argument('--ticket-output',required=True)
        if name in {'apply','receipt'}:c.add_argument('--ticket',required=True)
        if name=='apply':
            c.add_argument('--approve',required=True);c.add_argument('--cutover',action='store_true');c.add_argument('--wait-seconds',type=int,default=300)
    return p


def run(args,ticket_handle=None):
    import config  # noqa: F401; config precedes pgadmin imports in standalone use.
    from pgadmin.cdeadmin.workspace.mysql_deployment import artifact,verify,CAPTURE,select,outcome,encode
    if args.operation=='pack':
        manifest=decode(read(args.manifest));folder=Path(args.manifest).resolve().parent
        if (not isinstance(manifest,dict) or set(manifest)!={'version','environments'} or
                not isinstance(manifest['environments'],dict) or not 1<=len(manifest['environments'])<=16):
            raise ValueError('Manifest requires version and explicitly named environments')
        environments={}
        for name,item in manifest['environments'].items():
            if not isinstance(item,dict) or set(item)!={'capture','desired','execution'}:raise ValueError('Manifest environment requires capture, desired and execution')
            captured=verify(decode(read(folder/item['capture'])),CAPTURE,{'environment','binding','snapshot'})
            if captured['environment']!=name:raise ValueError('Capture environment name differs from manifest')
            environments[name]={'binding':captured['binding'],'baseline':encode(captured['snapshot']),
                'desired':read(folder/item['desired']),'execution':item['execution']}
        document=artifact(manifest['version'],environments)
        return 0,document,{'version':document['version'],'artifact_sha256':document['sha256'],'environments':list(environments)}
    source=decode(read(args.artifact)) if args.operation!='capture' else None
    if source is not None:
        item=select(source,args.environment)
        if item['binding']['server_id']!=args.server_id or item['binding']['database_target_id']!=args.target_id:
            raise ValueError('Command registration differs from the exact artifact environment')
    ticket=decode(read(args.ticket)) if args.operation in {'apply','receipt'} else None
    with workspace(args) as deployment:
        if args.operation=='capture':
            document=deployment.capture(args.environment)
            return 0,document,{'environment':args.environment,'binding':document['binding'],'capture_sha256':document['sha256']}
        common={'artifact_sha256':source['sha256'],'version':source['version'],'environment':args.environment,'automatic_retry':False}
        if args.operation=='plan':
            plan,_=deployment.plan(source,args.environment)
            code=3 if plan['conflicts'] else 2 if plan['blockers'] or (plan['operations'] and not plan.get('native_grammar_validated')) else 0
            return code,{**common,'plan':plan},common|{'execution_sha256':plan['execution_sha256'],'operations':len(plan['operations']),'conflicts':len(plan['conflicts']),'blockers':len(plan['blockers'])}
        if args.operation=='review':
            ticket,plan=deployment.review(source,args.environment,args.expect_plan)
            if ticket is None:return (3 if plan['conflicts'] else 2),{**common,'plan':plan},common|{'reviewed':False}
            ticket_handle.write(encode(ticket)+'\n')
            return 0,{**common,'ticket_sha256':ticket['sha256'],'review':ticket['review']},common|{'ticket_sha256':ticket['sha256'],'review_id':ticket['review']['review_id']}
        record=(deployment.apply(source,args.environment,ticket,args.approve,cutover=args.cutover,wait_seconds=args.wait_seconds)
                if args.operation=='apply' else deployment.receipt(source,args.environment,ticket))
        return outcome(record),{**common,'review':record},common|{'review_id':record['review_id'],'state':record['state'],'rediscovery_verified':record.get('outcome',{}).get('rediscovery_verified',False)}


def main(argv=None):
    args=parser().parse_args(argv)
    report={'format':'scratchrobin.mysql.deployment-report@1','operation':args.operation,'automatic_retry':False}
    code=2
    try:
        with output(args.output) as handle,ExitStack() as stack:
            try:
                ticket_handle=stack.enter_context(output(args.ticket_output)) if args.operation=='review' else None
                with redirect_stdout(sys.stderr):code,document,summary=run(args,ticket_handle)
                handle.write(json.dumps(document,ensure_ascii=True,sort_keys=True)+'\n')
                report.update(summary,exit_code=code,report_path=str(Path(args.output).resolve()))
            except Exception as error:
                code=2
                # Native/crypto/parser error strings can contain private inputs.
                # Keep typed diagnostics; never serialize credentials or tracebacks.
                report.update(exit_code=2,error_type=type(error).__name__,error_code=getattr(error,'errno',None),sqlstate=getattr(error,'sqlstate',None))
                if type(error).__module__=='pgadmin.cdeadmin.workspace.mysql_deployment' and type(error).__name__=='DeploymentError':
                    report['reason']=str(error)
                handle.write(json.dumps(report,sort_keys=True)+'\n')
    except OSError as error:
        code=2;report.update(exit_code=2,error_type=type(error).__name__)
    print(json.dumps(report,sort_keys=True))
    return code


if __name__=='__main__':raise SystemExit(main())
