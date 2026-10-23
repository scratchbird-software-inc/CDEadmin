"""Pinned source-available online-copy backend using the native tool guardian."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from ..sdk.tooling import ProviderToolGrant, ProviderToolRunner, ProviderToolError
from ..operations.fileio import private_directory, private_file
from .mysql_family.mysql_clone import rows
from ..workspace.mysql_online_policy import structural_definition
from ..workspace.firebird_schema_plan import digest

REVISION='6fd7a1e7876a64e2ca164f02e170619bf5df3236'
VERSION='3.7.2'
TOOL_SHA256='d24341d04ca7650e4d11c8b413e89f032d06e700db452b0c2edbfa61c2883896'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def installation():
    default=Path(__file__).resolve().parents[4]/'tools/reference_engine_demos/runtime/percona-toolkit/bin/pt-online-schema-change'
    location=os.environ.get('CDEADMIN_MYSQL_ONLINE_SCHEMA_TOOL',str(default))
    try:path=Path(location).resolve(strict=True)
    except OSError:raise ValueError('Install the admitted Percona Toolkit 3.7.2 native utility') from None
    perl=shutil.which(os.environ.get('CDEADMIN_MYSQL_ONLINE_PERL','perl'))
    if path is None or not path.is_file() or path.stat().st_size>1024*1024 or sha(path)!=TOOL_SHA256 or not perl:
        raise ValueError('Install the admitted Percona Toolkit 3.7.2 script and native Perl/DBI/DBD::mysql runtime')
    include=os.environ.get('CDEADMIN_MYSQL_ONLINE_PERL_INCLUDE')
    includes=['-I'+str(Path(include).resolve(strict=True))] if include else []
    modules=subprocess.run([perl,*includes,'-MDBI','-MDBD::mysql','-e','print "$DBI::VERSION $DBD::mysql::VERSION"'],capture_output=True,timeout=10)
    if modules.returncode:raise ValueError('Install native Perl DBI and DBD::mysql on the online-copy execution host')
    check=subprocess.run([perl,*includes,str(path),'--config=','--version'],capture_output=True,timeout=10)
    if check.returncode or check.stdout.decode().strip()!='pt-online-schema-change '+VERSION:
        raise ValueError('The admitted online-copy utility version is unavailable')
    return {'source_revision':REVISION,'version':VERSION,'tool_path':str(path),'tool_sha256':TOOL_SHA256,
        'perl_path':str(Path(perl).absolute()),'perl_sha256':sha(Path(perl)),'perl_arguments':includes,
        'perl_dbi_dbd_versions':modules.stdout.decode('ascii').strip(),
        'hook_sha256':sha(Path(__file__).with_name('mysql_online_copy_hook.pl'))}


def admission(connection, plan,replicas=None):
    op=plan['operations'][0];tool=installation()
    if op['context'].get('character_set_client')!='utf8mb4' or not op['context'].get('collation_connection','').startswith('utf8mb4_'):
        raise ValueError('The admitted online-copy CLI requires UTF-8 native DDN statement context; other contexts retain native ALTER execution')
    identity=rows(connection,'SELECT @@server_uuid AS server_uuid,CURRENT_USER() AS account,DATABASE() AS database_name')[0]
    if identity['server_uuid']!=plan['server_uuid'] or identity['database_name']!=plan['database']:
        raise ValueError('Online-copy review reached another native identity')
    tables=rows(connection,'SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',
        (op['database'],op['name']))
    if len(tables)!=1 or tables[0]['ENGINE']!='InnoDB':raise ValueError('The admitted online-copy backend requires a native InnoDB table')
    # Do not let toolkit discovery delegate credentials to unregistered hosts.
    # This initial execution profile admits standalone sources explicitly.
    reported=rows(connection,'SHOW REPLICAS')
    channels=rows(connection,'SELECT CHANNEL_NAME FROM performance_schema.replication_connection_configuration LIMIT 1')
    groups=rows(connection,"SELECT MEMBER_ID FROM performance_schema.replication_group_members WHERE MEMBER_STATE!='OFFLINE' LIMIT 1")
    replicas=replicas or []
    known={r['server_uuid'] for r in replicas}
    if channels or groups or any(row.get('Replica_UUID') not in known for row in reported):
        raise ValueError('Admit every reported replica on a source without incoming or group replication before online copy')
    triggers=rows(connection,'SELECT TRIGGER_NAME,ACTION_TIMING,EVENT_MANIPULATION,ACTION_STATEMENT,ACTION_ORDER,DEFINER,'
        'CAST(SQL_MODE AS CHAR) AS SQL_MODE,CHARACTER_SET_CLIENT,COLLATION_CONNECTION,DATABASE_COLLATION '
        'FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND EVENT_OBJECT_TABLE=%s ORDER BY TRIGGER_NAME LIMIT 65',
        (op['database'],op['name']))
    if len(triggers)>64:raise ValueError('Online-copy trigger observation exceeds its bound')
    incoming=rows(connection,'SELECT TABLE_SCHEMA,TABLE_NAME,CONSTRAINT_NAME,COLUMN_NAME,ORDINAL_POSITION,REFERENCED_COLUMN_NAME '
        'FROM information_schema.KEY_COLUMN_USAGE WHERE REFERENCED_TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME=%s '
        'ORDER BY TABLE_SCHEMA,TABLE_NAME,CONSTRAINT_NAME,ORDINAL_POSITION LIMIT 1025',(op['database'],op['name']))
    if len(incoming)>1024:raise ValueError('Online-copy incoming foreign keys exceed the reviewed bound')
    from .mysql_family.mysql_catalog import identifier
    parents={}
    for item in incoming:
        key=item['TABLE_SCHEMA'],item['TABLE_NAME']
        if key not in parents:
            definition=rows(connection,'SHOW CREATE TABLE '+identifier(key[0])+'.'+identifier(key[1]))[0]
            ddl=next(value for field,value in definition.items() if field.lower()=='create table')
            parents[key]=digest(structural_definition(ddl,op['context']['sql_mode']))
    return {'tool':tool,'identity':identity,'trigger_sha256':digest(triggers),'original_trigger_names':[r['TRIGGER_NAME'] for r in triggers],
        'incoming_foreign_keys':incoming,'referencing_definitions':[{'database':key[0],'table':key[1],'structural_sha256':value} for key,value in sorted(parents.items())],
        'replicas':deepcopy(replicas),
        'lag_coverage':('Lag is measured only on explicitly registered channels; hidden or unregistered topology is not covered.' if replicas else
            'Standalone execution profile; replica lag is not measured. Native discovery cannot establish absence of hidden replicas.'),
        'load_policy':{'max_threads_running':25,'critical_threads_running':50},
        'foreign_keys_method':'rebuild_constraints','foreign_key_names_can_change':True,'preserve_triggers':True,
        'cutover':'separate explicit owner action after copy; native metadata locks still apply'}


def option(value):
    if not isinstance(value,str) or '\0' in value:raise ValueError('Native utility option text is unavailable')
    return '"'+value.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r').replace('\t','\\t')+'"'


def secret_config(route,password):
    if route.get('role') or any(route.get(k) for k in ('openid_token_file','kerberos_auth_mode','password2','password3')):
        raise ValueError('Online-copy native password profile does not admit this authentication mode')
    result='[client]\nuser='+option(route.get('user') or route.get('username'))+'\npassword='+option(password)+'\n'
    result+='host='+option(route['host'])+'\nport='+str(route.get('port',3306))+'\ndefault-character-set=utf8mb4\n'
    if route.get('unix_socket'):result+='socket='+option(route['unix_socket'])+'\n'
    for key in ('ssl_ca','ssl_cert','ssl_key'):
        if route.get(key):result+=key.replace('_','-')+'='+option(route[key])+'\n'
    if route.get('ssl_verify_identity') or route.get('ssl_verify_cert'):result+='ssl-verify-server-cert=1\n'
    return result.encode('utf8')


def execute(runtime,cursor,record):
    op=record['plan']['operations'][0];admitted=op.get('copy_admission')
    if not admitted or installation()!=admitted['tool']:raise ValueError('The reviewed online-copy installation changed')
    # Recheck structural ancillary scope; actual native feasibility is decided
    # by the utility and server. No weaker method is selected after refusal.
    current=admission(runtime.worker,record['plan'],replicas=admitted.get('replicas',[]))
    if current!=admitted:raise ValueError('The native copy admission changed after review')
    root=runtime.copy_workspace;root.mkdir(mode=0o700,parents=True,exist_ok=False);private_directory(root)
    tool=root/'pt-online-schema-change';tool.write_bytes(Path(admitted['tool']['tool_path']).read_bytes());private_file(tool)
    if sha(tool)!=TOOL_SHA256:raise ValueError('The copied utility changed')
    hook=root/'hook.pl';hook.write_bytes(Path(__file__).with_name('mysql_online_copy_hook.pl').read_bytes());private_file(hook)
    if sha(hook)!=admitted['tool']['hook_sha256']:raise ValueError('The copied utility hook changed')
    from .mysql_family.mysql_catalog import identifier
    target=identifier(op['database'])+'.'+identifier(op['name'])
    from ..workspace.mysql_online_policy import advisory
    binding={'server_uuid':record['plan']['server_uuid'],'account':admitted['identity']['account'],'database':op['database'],
        'qualified_table':target,'advisory':advisory(op['database'],op['name']),'sql_mode':op['context']['sql_mode']}
    (root/'binding.json').write_text(json.dumps(binding));private_file(root/'binding.json')
    baseline=record['baseline']['rows'][op['resource_id']]['native']['definition']
    runtime.copy_baseline=baseline;runtime.copy_operation=deepcopy(op)
    from ..workspace.mysql_online_replicas import observe as replica_observe
    with runtime.lock:
        replica_observe(runtime);runtime.copy_ready=True
    prefix='ALTER TABLE '+target+' '
    if not op['source'].startswith(prefix):raise ValueError('The exact native ALTER target changed')
    # DSN delimiters are literal escaped data, never shell syntax.
    def dsn(value):return value.replace('\\','\\\\').replace(',','\\,')
    name='sr_osc_'+record['review_id'].replace('-','')[:24]
    arguments=[*admitted['tool']['perl_arguments'],str(tool),'--config=','--no-version-check','--execute','--charset=utf8mb4',
        '--alter='+op['source'][len(prefix):],'--plugin='+str(hook),'--new-table-name='+name,
        '--alter-foreign-keys-method=rebuild_constraints','--preserve-triggers','--recursion-method=none',
        '--max-load=Threads_running=25','--critical-load=Threads_running=50','--chunk-time=0.1',
        '--progress=time,1','--statistics','--set-vars=lock_wait_timeout='+str(runtime.selected['lock_wait_seconds'])+',innodb_lock_wait_timeout='+str(runtime.selected['lock_wait_seconds']),
        'D='+dsn(op['database'])+',t='+dsn(op['name'])]
    grant=ProviderToolGrant('mysql-online-perl',str(root),runtime.copy_route['host'],int(runtime.copy_route.get('port',3306)),
        timeout_seconds=runtime.selected['timeout_seconds'],durable_name='online-copy',max_output_bytes=262144)
    def progress(event):
        if 'durable_tool' in event:
            runtime.update(utility_reference=event['durable_tool'],utility_perl_sha256=admitted['tool']['perl_sha256'],
                utility_workspace=str(root),copy_table_name=name)
        else:runtime.update(utility_process=event)
    runtime.event('native-online-copy-started',tool_version=VERSION,load_policy=admitted['load_policy'],lag_coverage=admitted['lag_coverage'])
    config,password=runtime.copy_secret.use(lambda data:(secret_config(runtime.copy_route,bytes(data).decode('utf8')),bytes(data).decode('utf8')))
    try:
        result=ProviderToolRunner({'mysql-online-perl':admitted['tool']['perl_path']}).run(grant,arguments,
            secret_config=config,secret_argument='--defaults-file={path}',secret_argument_position=len(arguments)-1,
            secret_suffix='.cnf',progress=progress,cancel_signal=runtime.cancelled,redact_values=(password,))
    except ProviderToolError as error:
        result=getattr(error,'process_observation',None)
        if result is None:raise
    runtime.update(utility_result=result)
    runtime.copy_swapped=(root/'swapped').is_file()
    if not runtime.copy_swapped:
        raise ValueError('The native online-copy utility did not confirm cutover; observe native state and retained process evidence')
    # The qualified hook follows the native RENAME acknowledgement. A later
    # utility/cleanup failure cannot turn that known commit into rollback.
    runtime.copy_cleanup_confirmed=result['return_code']==0 and result['process_observation']['cleanup_confirmed']
    runtime.event('native-online-copy-returned',return_code=result['return_code'])


def observe(runtime):
    root=getattr(runtime,'copy_workspace',None)
    if not getattr(runtime,'copy_ready',False) or root is None:return
    from ..workspace.mysql_online_replicas import observe as replica_observe
    replica_observe(runtime)
    gate=root/'gate.json'
    if not gate.is_file() or gate.stat().st_size>1024*1024:return
    value=json.loads(gate.read_text())
    stage=value['stage']
    if value['server_uuid']!=runtime.review['plan']['server_uuid']:raise ValueError('Utility native identity changed')
    if stage=='before-create':
        if not value.get('native_definition'):return
        mode=runtime.copy_operation['context']['sql_mode']
        if structural_definition(value['native_definition'],mode)!=structural_definition(runtime.copy_baseline,mode):
            runtime.stop('native-source-changed');return
        (root/'create.allowed').touch(mode=0o600,exist_ok=True)
    if stage=='native-swap-returned':runtime.copy_swapped=True
    if getattr(runtime,'copy_last_stage',None)!=stage:
        runtime.event('utility-stage',native_stage=stage,native_thread={k:value.get(k) for k in ('connection_id','thread_id')})
        runtime.copy_last_stage=stage
    runtime.update(copy_stage=stage,utility_native_thread={k:value.get(k) for k in ('connection_id','thread_id')})


def artifacts(connection,review):
    op=review['plan']['operations'][0];job=review['controlled_job'];root=Path(job['utility_workspace'])
    candidates=[]
    for name in ('new-table.json','old-table.json'):
        path=root/name
        if path.is_file() and not path.is_symlink() and path.stat().st_size<=2048:
            value=json.loads(path.read_text())
            if value.get('database')==op['database'] and isinstance(value.get('table'),str) and len(value['table'])<=64:
                candidates.append(value)
    if not candidates and job.get('copy_table_name'):candidates.append({'database':op['database'],'table':job['copy_table_name']})
    present=[]
    for item in candidates:
        found=rows(connection,'SELECT TABLE_SCHEMA,TABLE_NAME,ENGINE FROM information_schema.TABLES '
            'WHERE CAST(TABLE_SCHEMA AS BINARY)=CAST(%s AS BINARY) AND CAST(TABLE_NAME AS BINARY)=CAST(%s AS BINARY)',
            (item['database'],item['table']))
        present.extend(found)
    triggers=rows(connection,'SELECT TRIGGER_NAME,ACTION_TIMING,EVENT_MANIPULATION FROM information_schema.TRIGGERS '
        'WHERE TRIGGER_SCHEMA=%s AND EVENT_OBJECT_TABLE=%s ORDER BY TRIGGER_NAME LIMIT 129',(op['database'],op['name']))
    original=op['copy_admission'].get('original_trigger_names',[])
    return {'present_utility_named_tables':present,'additional_source_triggers':[r for r in triggers[:128] if r['TRIGGER_NAME'] not in original],
        'trigger_scope_truncated':len(triggers)>128,'automatic_removal_authorized':False,
        'scope':'Observed native utility table names and additional source triggers; inspect/review native object removal separately'}
