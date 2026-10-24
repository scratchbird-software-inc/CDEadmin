"""Native Router bootstrap with independent host and SQL peer identities."""
import base64
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
import tempfile
import uuid
from urllib.parse import quote


class Refused(ValueError):pass


def host_module():
    if '_cdeadmin_native_worker' in sys.modules:return sys.modules['_cdeadmin_native_worker']
    from . import mysql_host_worker
    return mysql_host_worker


def service_module():
    if '_cdeadmin_router_services' in sys.modules:return sys.modules['_cdeadmin_router_services']
    from . import mysql_router_services
    return mysql_router_services


def selected(request):
    value=request.get('options')
    fields={'executable','directory','user','base_port','bind_address','seed','extra_arguments','workspace','timeout_seconds'}
    if not isinstance(value,dict) or set(value)-{'operation','service','disconnect_all_clients'}!=fields:raise Refused('Select the exact native Router host paths, seed and bootstrap options')
    operation=value.get('operation','bootstrap')
    if operation not in {'bootstrap','install_service','service_start','service_stop','service_restart','service_enable','service_disable'}:
        raise Refused('Select a native Router operation')
    if operation in {'service_stop','service_restart'} and value.get('disconnect_all_clients') is not True:
        raise Refused('Confirm disconnection of all routed clients')
    for key in ('executable','directory','user','bind_address','workspace'):
        if not isinstance(value[key],str) or not value[key] or '\0' in value[key] or len(value[key])>32768:raise Refused('Select bounded native Router options')
    if type(value['base_port']) is not int or not 1<=value['base_port']<=65528:raise Refused('Select a native Router base port')
    if type(value['timeout_seconds']) is not int or not 1<=value['timeout_seconds']<=3600:raise Refused('Select a bounded native Router bootstrap runtime')
    args=value['extra_arguments']
    if not isinstance(args,list) or len(args)>128 or any(not isinstance(arg,str) or not arg or '\0' in arg or len(arg)>16384 for arg in args):raise Refused('Select bounded exact native Router arguments')
    reserved={'--bootstrap','-B','--directory','-d','--user','-u','--conf-base-port','--conf-bind-address','--force',
        '--ssl-mode','--ssl-ca','--ssl-cert','--ssl-key','--mrs-global-secret'}
    if any(arg.split('=',1)[0] in reserved or re.match(r'^-[Bdu].+',arg) for arg in args):raise Refused('Use the reviewed Router fields for bootstrap identity, directory, native user and TLS')
    seed=value['seed']
    if (not isinstance(seed,dict) or set(seed)!={'host','port','user','ssl_mode','ssl_ca','ssl_cert','ssl_key'} or
            type(seed['port']) is not int or not 1<=seed['port']<=65535 or
            seed['ssl_mode'] not in {'DISABLED','PREFERRED','REQUIRED','VERIFY_CA','VERIFY_IDENTITY'}):raise Refused('Select the exact native Router metadata seed and TLS policy')
    for key in ('host','user'):
        if not isinstance(seed[key],str) or not seed[key] or any(char in seed[key] for char in '\0\r\n'):raise Refused('Select a native Router metadata address and account')
    for key in ('ssl_ca','ssl_cert','ssl_key'):
        if seed[key] is not None and (not isinstance(seed[key],str) or '\0' in seed[key] or not Path(seed[key]).is_absolute()):raise Refused('Select native TLS files on the Router host')
    return value


def peer(seed,password):
    try:return native_peer(seed,password)
    except Refused:raise
    except Exception as error:
        if not hasattr(error,'errno'):raise
        refused=Refused('Native Router metadata seed refused the observation: '+str(error)[:4096])
        refused.native_error={'code':error.errno,'sqlstate':getattr(error,'sqlstate',None),'message':str(error)[:4096]}
        raise refused from None


def native_peer(seed,password):
    try:
        import mysql.connector
        if mysql.connector.__version__!='26.7.0':raise Refused('Native Router preflight requires Connector/Python26.7.0 on the Router host')
    except ImportError:raise Refused('Install native Connector/Python26.7.0 on the Router host for independent seed binding') from None
    route={key:seed[key] for key in ('host','port','user')}
    mode=seed['ssl_mode'];route.update(password=password,use_pure=True,connection_timeout=5,read_timeout=5,write_timeout=5,
        ssl_disabled=mode=='DISABLED',ssl_verify_cert=mode in {'VERIFY_CA','VERIFY_IDENTITY'},ssl_verify_identity=mode=='VERIFY_IDENTITY')
    route.update({key:seed[key] for key in ('ssl_ca','ssl_cert','ssl_key') if seed[key] is not None})
    connection=mysql.connector.connect(**route)
    try:
        observed=connection_observation(connection,tls_required=mode in {'REQUIRED','VERIFY_CA','VERIFY_IDENTITY'})
    finally:connection.close()
    return {**observed,'connector_version':mysql.connector.__version__,'sql_connection_closed_after_observation':True}


def connection_observation(connection,*,tls_required=False):
    cursor=connection.cursor(dictionary=True)
    try:
        cursor.execute('SELECT VERSION() AS version,@@server_uuid AS server_uuid,CURRENT_USER() AS authenticated_principal,CURRENT_ROLE() AS active_role')
        identity=cursor.fetchone()
        if identity['version'].split('-')[0]!='9.7.0':raise Refused('Select a native MySQL9.7 metadata seed')
        cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'");cipher=cursor.fetchone()
        if tls_required and not cipher['Value']:raise Refused('The native metadata seed TLS policy was not satisfied')
        cursor.execute('SHOW GRANTS');grants=sorted(str(value) for row in cursor.fetchall() for value in row.values())
        cursor.execute('SELECT c.cluster_id,c.cluster_type,c.clusterset_id FROM mysql_innodb_cluster_metadata.clusters c '
            'JOIN mysql_innodb_cluster_metadata.instances i ON i.cluster_id=c.cluster_id WHERE i.mysql_server_uuid=@@server_uuid')
        rows=cursor.fetchall()
        if len(rows)!=1:raise Refused('Select one native Cluster, ClusterSet or ReplicaSet metadata seed')
        return {**identity,**rows[0],'tls_cipher':cipher['Value'],
            'grants_sha256':hashlib.sha256(json.dumps(grants,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()}
    finally:cursor.close()


def inspect(request):
    if not sys.platform.startswith('linux'):raise Refused('This native Router adapter requires the Linux host')
    try:import psutil
    except ImportError:raise Refused('Native Router supervision requires psutil on its Python execution host') from None
    value=selected(request);native=host_module();directory=Path(value['directory'])
    if not directory.is_absolute() or directory in {Path('/'),Path.home()}:raise Refused('Select a bounded native Router deployment directory')
    directory=directory.parent.resolve(strict=True)/directory.name
    if os.path.lexists(directory):raise Refused('Select a new native Router deployment directory; bootstrap never replaces an existing deployment')
    program=Path(value['executable'])
    if not program.is_absolute():raise Refused('Select the absolute native Router executable')
    program=program.resolve(strict=True)
    if program.name!='mysqlrouter':raise Refused('Select the native mysqlrouter executable')
    checksum=native.file_hash(program)
    with tempfile.TemporaryDirectory(prefix='scratchrobin-router-version-') as temporary:
        version=native.process(program,['--version'],Path(temporary),15)
    text=b''.join(base64.b64decode(version['outputs'].get(key,{}).get('base64','')) for key in ('stdout','stderr')).decode('utf8',errors='replace')
    if version['return_code']!=0 or not re.search(r'MySQL Router\s+Ver\s+9\.7\.0\b',text):raise Refused('Select the native MySQL Router9.7.0 executable')
    password=request.get('database_password')
    if not isinstance(password,str) or any(char in password for char in '\0\r\n'):raise Refused('Supply the native bootstrap account password as one private input line')
    source=peer(value['seed'],password)
    expected=request.get('expected_seed')
    if not isinstance(expected,dict) or any(source.get(key)!=expected.get(key) for key in ('server_uuid','version','cluster_id','cluster_type','clusterset_id')):
        raise Refused('The Router host reached a different native metadata seed')
    parent=directory.parent.stat();tls={key:native.file_hash(Path(value['seed'][key])) for key in ('ssl_ca','ssl_cert','ssl_key') if value['seed'][key] is not None}
    return {'host':{'hostname':socket.gethostname(),'platform':sys.platform,'python_version':list(sys.version_info[:3]),'psutil_version':psutil.__version__,
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'pid_namespace':os.readlink('/proc/self/ns/pid')},
        'program':{'path':str(program),'sha256':checksum,'version_output':text.strip()},'seed':source,'tls_file_sha256':tls,
        'directory':str(directory),'parent_identity':[parent.st_dev,parent.st_ino],'automatic_retry':False}


def sdk_hashes(sources):
    return {key:hashlib.sha256(sources[key].encode()).hexdigest() for key in ('fileio','durable_tool','tool_guardian','tool_process','tool_reconcile')}


def sdk(directory,sources=None,expected=None):
    """Keep the original, hash-checked guardian code with its native invocation."""
    package_name='_cdeadmin_router_sdk_'+hashlib.sha256(os.fsencode(str(directory))).hexdigest()[:16]
    package=Path(directory)/'native_sdk'/package_name
    names={'operations/fileio.py':'fileio',**{'sdk/'+name+'.py':name for name in ('durable_tool','tool_guardian','tool_process','tool_reconcile')}}
    paths={name:None if sources is None else sources[key] for name,key in names.items()}
    paths.update({name:'' for name in ('__init__.py','sdk/__init__.py','operations/__init__.py')})
    native=host_module()
    for name,source in paths.items():
        path=package/name
        if sources is None:
            digest=hashlib.sha256(b'').hexdigest() if name.endswith('__init__.py') else (expected or {}).get(names[name])
            if (path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(Path(directory).resolve()) or
                    hashlib.sha256(path.read_bytes()).hexdigest()!=digest):raise Refused('Original native Router supervision helper is unavailable or changed')
            continue
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if path.exists():
            if path.is_symlink() or path.read_text()!=source:raise Refused('The original Router supervision helper changed')
        else:
            with path.open('x') as stream:native.private_file(path);stream.write(source);stream.flush();os.fsync(stream.fileno())
    sys.path.insert(0,str(package.parent))
    return importlib.import_module(package_name+'.sdk.durable_tool')


def claim_path(result):
    target=Path(result['observation']['directory'])
    return target.parent/('.scratchrobin-router-bootstrap-'+hashlib.sha256(os.fsencode(target.name)).hexdigest()+'.json')


def claim_identity(result,directory):
    return {'job_id':result['job_id'],'input_digest':result['input_digest'],'workspace':str(directory)}


def release_claim(result,directory):
    path=claim_path(result)
    if not path.exists():return
    if path.is_symlink() or json.loads(path.read_text())!=claim_identity(result,directory):raise Refused('Another original Router operation owns this deployment claim')
    path.unlink()


def deployment(directory):
    """Observe native output files; never supply application-generated Router IDs."""
    import configparser
    root=Path(directory);entries=[];native=host_module()
    for path in sorted(root.rglob('*')):
        if len(entries)>=10000:raise Refused('Native Router deployment exceeds its observation bound')
        info=path.lstat();row={'path':str(path.relative_to(root)),'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid}
        if stat.S_ISLNK(info.st_mode):row.update(kind='symlink',target=os.readlink(path))
        elif stat.S_ISDIR(info.st_mode):row['kind']='directory'
        elif stat.S_ISREG(info.st_mode):row.update(kind='file',bytes=str(info.st_size),sha256=native.file_hash(path))
        else:raise Refused('Native Router created an unsupported deployment entry')
        entries.append(row)
    configuration=root/'mysqlrouter.conf';native.regular(configuration)
    parser=configparser.ConfigParser(interpolation=None)
    with configuration.open() as stream:parser.read_file(stream)
    identifiers=[parser.get(section,'router_id',fallback=None) for section in parser.sections() if section.startswith('metadata_cache:')]
    info=root.stat()
    return {'directory':str(root.resolve(strict=True)),'directory_identity':[info.st_dev,info.st_ino],
        'configuration_path':str(configuration),'configuration_sha256':native.file_hash(configuration),
        'native_router_ids':[value for value in identifiers if value is not None],'entries':entries,
        'sensitive_file_contents_omitted':True,'atomic_runtime_snapshot':False}


def arguments(value,observed):
    seed=value['seed'];host='['+seed['host']+']' if ':' in seed['host'] else seed['host']
    uri='mysql://'+quote(seed['user'],safe='')+'@'+host+':'+str(seed['port'])
    result=[observed['program']['path'],'--bootstrap='+uri,'--directory='+observed['directory'],'--user='+value['user'],
        '--conf-base-port='+str(value['base_port']),'--conf-bind-address='+value['bind_address'],'--ssl-mode='+seed['ssl_mode']]
    result.extend('--'+key.replace('_','-')+'='+seed[key] for key in ('ssl_ca','ssl_cert','ssl_key') if seed[key] is not None)
    return [*result,*value['extra_arguments']]


def dispatch(request,sources):
    if not isinstance(request,dict) or request.get('schema')!='cdeadmin.mysql-router-host.v1':raise Refused('Select the native Router host protocol')
    action=request.get('action')
    operation=request.get('options',{}).get('operation','bootstrap')
    if action=='inspect':return inspect(request) if operation=='bootstrap' else service_module().runtime(request,sys.modules[__name__])
    if action not in {'bootstrap','install_service','service_start','service_stop','service_restart','service_enable','service_disable','status','cancel','acknowledge'}:raise Refused('Native Router host action unavailable')
    native=host_module();value=selected(request);root=Path(value['workspace'])
    if not root.is_absolute():raise Refused('Select an absolute private Router workspace')
    root=root.resolve()
    if root in {Path('/'),Path.home().resolve()} or root.is_relative_to(Path(value['directory']).resolve()):raise Refused('Keep private Router receipts separate from the native deployment')
    job=request.get('job_id')
    if str(uuid.UUID(job))!=job:raise Refused('Select an exact native Router job')
    directory=root/job;path=directory/'result.json';digest=request.get('input_digest')
    if not isinstance(digest,str) or not digest:raise Refused('Select the exact reviewed Router input')
    if action in {'status','cancel','acknowledge'} or directory.exists():
        if not path.is_file():return {'state':'unknown','input_digest':digest,'job_id':job,'remote_receipt_available':False,'automatic_retry':False}
        result=json.loads(path.read_text())
        if result.get('input_digest')!=digest:raise Refused('The native Router receipt belongs to another reviewed request')
        if result.get('operation','bootstrap')!='bootstrap':
            if action!='status':raise Refused('Observe the original service commands; service requests cannot be replayed or cancelled as bootstrap')
            return service_module().observe(result,directory,sys.modules[__name__],request)
        if result.get('durable_tool'):
            tools=sdk(directory,expected=result.get('sdk_sha256'));reference=result['durable_tool'];fingerprint=result['observation']['program']['sha256']
            facts=(tools.cancel if action=='cancel' else tools.observe)(directory,reference,fingerprint)
            result['utility_observation']=facts
            if action=='acknowledge':
                if facts.get('cleanup_confirmed') is not True:raise Refused('Original Router bootstrap writers have not ended')
                release_claim(result,directory);result['deployment_claim_released']=True
        return result
    if action!=operation:raise Refused('The reviewed Router operation differs from dispatch')
    observed=inspect(request) if operation=='bootstrap' else service_module().runtime(request,sys.modules[__name__])
    if observed!=request.get('reviewed'):raise Refused('The native Router host, seed, executable or selected files changed after review')
    root.mkdir(parents=True,exist_ok=True);native.private_directory(root)
    try:directory.mkdir(mode=0o700)
    except FileExistsError:return {'state':'unknown','input_digest':digest,'job_id':job,'automatic_retry':False}
    native.private_directory(directory);tools=sdk(directory,sources)
    result={'state':'native_dispatch','job_id':job,'input_digest':digest,'observation':observed,'automatic_retry':False,
        'sdk_sha256':sdk_hashes(sources),'sql_readiness_observed':False,'bootstrap_metadata_mutations_may_have_occurred':operation=='bootstrap',
        'operation':operation}
    native.save(path,result)
    if operation!='bootstrap':
        try:return service_module().execute(request,observed,directory,sources,result,sys.modules[__name__])
        except BaseException as error:
            result['error_type']=type(error).__name__;native.save(path,result);return result
    claim=claim_path(result)
    with os.fdopen(os.open(claim,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'w') as stream:
        json.dump(claim_identity(result,directory),stream);stream.flush();os.fsync(stream.fileno())
    secret=directory/'bootstrap.stdin'
    with secret.open('x') as stream:native.private_file(secret);stream.write(request['database_password']+'\n')
    def progress(event):
        if event.get('durable_tool'):result['durable_tool']=event['durable_tool'];native.save(path,result)
    try:
        outcome=tools.run(arguments(value,observed),workspace=directory,environment=native.environment(Path(observed['program']['path']),directory),
            timeout=value['timeout_seconds'],capture_limit=512*1024,name='router-bootstrap',input_path=secret,credential_file=secret,
            progress=progress,guard_parent_death=False)
        result.update(state='native_process_returned',result={key:item for key,item in outcome.items() if key not in {'stdout','stderr'}},
            outputs={key:base64.b64encode(outcome[key]).decode('ascii') for key in ('stdout','stderr')})
        native.save(path,result)
        if outcome.get('cleanup_confirmed') is True:release_claim(result,directory)
        if outcome.get('return_code')==0:
            try:result['deployment_observation']={'observed':True,**deployment(observed['directory'])}
            except Exception as error:result['deployment_observation']={'observed':False,'error_type':type(error).__name__}
            native.save(path,result)
    except BaseException as error:
        result['error_type']=type(error).__name__;native.save(path,result)
    return result
