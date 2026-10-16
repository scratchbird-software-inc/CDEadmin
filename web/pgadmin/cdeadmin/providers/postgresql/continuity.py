"""PostgreSQL 18 native physical backup, verification and chain reconstruction."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from ...sdk.tooling import ProviderToolGrant, ProviderToolRunner


TOOLS = ('pg_basebackup', 'pg_verifybackup', 'pg_combinebackup', 'pg_receivewal',
         'pg_waldump', 'pg_controldata', 'pg_ctl', 'postgres', 'pg_amcheck')
CHECKSUMS = {'NONE', 'CRC32C', 'SHA224', 'SHA256', 'SHA384', 'SHA512'}


class ContinuityError(ValueError):
    """A native continuity selection is unavailable or refused."""


def binary_paths(directory=None):
    result = {}
    for name in TOOLS:
        filename = name + ('.exe' if os.name == 'nt' else '')
        candidate = Path(directory) / filename if directory else None
        result[name] = str(candidate) if candidate is not None else shutil.which(filename) or ''
    return result


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):digest.update(block)
    return digest.hexdigest()


def manifest(path):
    filename = Path(path) / 'backup_manifest'
    if not filename.is_file() or filename.stat().st_size > 128 * 1024 * 1024:
        raise ContinuityError('A bounded native backup manifest is required')
    data = json.loads(filename.read_text(encoding='utf8'))
    system = data.get('System-Identifier')
    if type(system) is not int or not 0 < system < 2**64 or data.get('PostgreSQL-Backup-Manifest-Version') != 2:
        raise ContinuityError('PostgreSQL 18 backup manifest identity is unavailable')
    ranges = data.get('WAL-Ranges')
    if not isinstance(ranges,list) or not ranges:
        raise ContinuityError('Native backup WAL ranges are unavailable')
    return {'system_identifier':str(system), 'manifest_sha256':file_sha256(filename),
            'files':len(data.get('Files',[])), 'wal_ranges':ranges,
            'manifest_version':data['PostgreSQL-Backup-Manifest-Version']}


def backup_options(value):
    defaults = {'format':'plain', 'wal_method':'stream', 'checkpoint':'fast',
                'manifest_checksums':'SHA256', 'label':'ScratchRobin physical backup',
                'progress':True, 'estimate_size':True, 'verify_page_checksums':True,
                'sync':True, 'sync_method':'fsync', 'write_recovery_conf':False,
                'compression':'', 'max_rate_kib':None, 'slot':'', 'create_slot':False,
                'no_slot':False, 'timeout_seconds':3600}
    if not isinstance(value,dict) or set(value)-defaults.keys():
        raise ContinuityError('Invalid native physical backup options')
    result = {**defaults, **value}
    for name, allowed in (('format',{'plain','tar'}), ('wal_method',{'stream','fetch','none'}),
                          ('checkpoint',{'fast','spread'}), ('manifest_checksums',CHECKSUMS),
                          ('sync_method',{'fsync','syncfs'})):
        if not isinstance(result[name],str) or result[name] not in allowed:
            raise ContinuityError('Invalid native physical backup ' + name)
    for name in ('progress','estimate_size','verify_page_checksums','sync','write_recovery_conf','create_slot','no_slot'):
        if type(result[name]) is not bool:raise ContinuityError('Physical backup options require native booleans')
    if type(result['timeout_seconds']) is not int or not 1<=result['timeout_seconds']<=3600:
        raise ContinuityError('Backup timeout must be between 1 and 3600 seconds')
    rate = result['max_rate_kib']
    if rate is not None and (type(rate) is not int or not 32<=rate<=1048576):
        raise ContinuityError('Native transfer rate must be between 32 and 1048576 KiB/s')
    for name, maximum in (('label',1024),('compression',512),('slot',63)):
        if not isinstance(result[name],str) or '\x00' in result[name] or len(result[name].encode('utf8'))>maximum:
            raise ContinuityError('Invalid physical backup ' + name)
    if result['slot'] and not re.fullmatch(r'[a-z0-9_]+',result['slot']):
        raise ContinuityError('Native replication slots use lowercase letters, digits and underscores')
    if result['create_slot'] and not result['slot'] or result['no_slot'] and (result['slot'] or result['create_slot']):
        raise ContinuityError('Select a consistent native replication slot policy')
    if result['wal_method'] != 'stream' and (result['slot'] or result['create_slot'] or result['no_slot']):
        raise ContinuityError('Replication slots require streaming WAL')
    return result


def backup_arguments(options, destination, *, incremental_manifest=None, tablespaces=()):
    options = backup_options(options)
    result = ['--pgdata='+str(destination), '--format='+options['format'], '--wal-method='+options['wal_method'],
              '--checkpoint='+options['checkpoint'], '--manifest-checksums='+options['manifest_checksums'],
              '--label='+options['label'], '--no-password', '--verbose']
    for name, flag in (('progress','--progress'),('write_recovery_conf','--write-recovery-conf'),
                       ('create_slot','--create-slot'),('no_slot','--no-slot')):
        if options[name]:result.append(flag)
    for name, flag in (('estimate_size','--no-estimate-size'),('verify_page_checksums','--no-verify-checksums'),('sync','--no-sync')):
        if not options[name]:result.append(flag)
    if options['sync']:result.append('--sync-method='+options['sync_method'])
    if options['compression']:result.append('--compress='+options['compression'])
    if options['slot']:result.append('--slot='+options['slot'])
    if options['max_rate_kib'] is not None:result.append('--max-rate='+str(options['max_rate_kib']))
    if incremental_manifest is not None:result.append('--incremental='+str(incremental_manifest))
    if options['format']=='plain':
        def escaped(value):return str(value).replace('\\','\\\\').replace('=','\\=')
        for original, target in tablespaces:
            result.append('--tablespace-mapping='+escaped(original)+'='+escaped(target))
    return result


def combine_options(value):
    defaults={'format':'plain','copy_mode':'copy','manifest_checksums':'SHA256','sync':True,'sync_method':'fsync','timeout_seconds':3600}
    if not isinstance(value,dict) or set(value)-defaults.keys():raise ContinuityError('Invalid native reconstruction options')
    result={**defaults,**value}
    if result['format']!='plain' or result['copy_mode'] not in {'copy','clone','copy-file-range','link'}:
        raise ContinuityError('Native reconstruction produces plain files using an admitted copy method')
    backup_options({key:result[key] for key in ('format','manifest_checksums','sync','sync_method','timeout_seconds')})
    return result


def combine_arguments(options, destination, inputs, *, tablespaces=()):
    options=combine_options(options)
    result=['--output='+str(destination),'--'+options['copy_mode'],'--manifest-checksums='+options['manifest_checksums']]
    result.append('--sync-method='+options['sync_method'] if options['sync'] else '--no-sync')
    for original,target in tablespaces:
        escaped=lambda value:str(value).replace('\\','\\\\').replace('=','\\=')
        result.append('--tablespace-mapping='+escaped(original)+'='+escaped(target))
    return [*result,*map(str,inputs)]


class PhysicalTools:
    def __init__(self, paths):
        self.paths = dict(paths)
        self.runner = ProviderToolRunner(self.paths)

    def grant(self, name, workspace, *, host='127.0.0.1', port=5432, timeout=3600, environment=()):
        return ProviderToolGrant(name,str(workspace),host,port,timeout_seconds=timeout,
                                 secret_environment_names=tuple(environment))

    def identify(self, name, workspace):
        if name not in TOOLS:raise ContinuityError('Native tool is not admitted')
        if not self.runner.available().get(name):
            return {'available':False,'reason':'native executable is not installed'}
        result = self.runner.run(self.grant(name,workspace,timeout=15),['--version'])
        text = result['stdout']+' '+result['stderr']
        match = re.search(r'\(PostgreSQL\)\s+(\d+)\.(\d+)',text)
        available = result['return_code']==0 and match is not None and int(match[1])==18
        return {'available':available, 'version':match[0] if match else None,
                'executable_sha256':result['executable_sha256'],
                'reason':None if available else 'PostgreSQL 18 native utility required'}

    def execute(self, name, workspace, arguments, *, parameters=None, password=None,
                timeout=3600, progress=None, cancel_signal=None):
        from psycopg import pq
        if self.identify(name,workspace)['available'] is not True:
            raise ContinuityError('Selected PostgreSQL 18 native utility is unavailable')
        environment, service, redactions = {}, {}, []
        parameters = dict(parameters or {})
        if password is not None:parameters['password']=password
        defaults = {item.keyword.decode('ascii'):item.envvar.decode('ascii') if item.envvar else None
                    for item in pq.Conninfo.get_defaults()}
        for key,value in parameters.items():
            if key in {'service','passfile','replication','fallback_application_name'}:continue
            if key not in defaults:raise ContinuityError('Unsupported native libpq connection parameter')
            value = str(value)
            if '\x00' in value:raise ContinuityError('Native libpq parameters cannot contain NUL')
            if value:redactions.append(value)
            variable = defaults[key]
            if variable:environment[variable]=value
            else:
                if '\n' in value or '\r' in value or value.rstrip()!=value or len((key+'='+value).encode('utf8'))>=1022:
                    raise ContinuityError('Native service-file encoding cannot preserve this connection option')
                service[key]=value
        config = None
        if service:
            if '--write-recovery-conf' in arguments:
                raise ContinuityError('Standby configuration cannot retain this temporary native service alias; encrypted-key standby credential provisioning is required')
            config = ('[scratchrobin_native]\n'+''.join(key+'='+value+'\n' for key,value in service.items())).encode('utf8')
            arguments = ['--dbname=service=scratchrobin_native',*arguments]
        host, port = parameters.get('host','127.0.0.1'), int(parameters.get('port',5432))
        granted = (*environment.keys(), *(('PGSERVICEFILE',) if config is not None else ()))
        return self.runner.run(self.grant(name,workspace,host=host,port=port,timeout=timeout,environment=granted),arguments,
            secret_environment=environment, secret_config=config, secret_argument=None if config is not None else '--config={path}',
            secret_environment_name='PGSERVICEFILE' if config is not None else None,
            secret_suffix='.pg-service',redact_values=redactions,progress=progress,cancel_signal=cancel_signal)

    def verify(self, workspace, backup, *, format='plain', parse_wal=True, progress=None, cancel_signal=None):
        if format not in {'plain','tar'} or type(parse_wal) is not bool:
            raise ContinuityError('Invalid native backup verification scope')
        args = ['--format='+format, '--progress']
        if not parse_wal or format=='tar':args.append('--no-parse-wal')
        args.append(str(backup))
        result = self.execute('pg_verifybackup',workspace,args,progress=progress,cancel_signal=cancel_signal)
        return {**result, 'verification_scope':{'files':True,'wal':parse_wal and format=='plain'}}
