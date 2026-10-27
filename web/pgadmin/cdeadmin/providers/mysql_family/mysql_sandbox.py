"""Local MySQL Shell sandboxes; utility replies and host state are independent."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import stat
import tempfile
import shutil
import uuid

import psutil

from ...operations.fileio import private_file
from ...sdk.tooling import ProviderToolGrant
from .mysql_binlog_archives import BinlogArchiveError, program_identity
from .mysql_host_worker import configuration_graph, Refused

METHODS = {name: name + '_sandbox_instance' for name in ('deploy', 'start', 'stop', 'kill', 'delete')}
SECRET_FILE = 'CDEADMIN_MYSQL_SANDBOX_SECRET'
DEPLOY_OPTIONS = {'portx', 'allowRootFrom', 'ignoreSslError', 'mysqldOptions'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def options(value):
    if not isinstance(value, dict) or set(value) - {'operation', 'port', 'sandbox_directory', 'native_options', 'timeout_seconds'}:
        raise BinlogArchiveError('Select native sandbox lifecycle options')
    result = {'operation': value.get('operation'), 'port': value.get('port'),
              'sandbox_directory': value.get('sandbox_directory'), 'native_options': value.get('native_options', {}),
              'timeout_seconds': value.get('timeout_seconds', 300)}
    if not isinstance(result['operation'], str) or result['operation'] not in METHODS or type(result['port']) is not int or not 1024 <= result['port'] <= 65535:
        raise BinlogArchiveError('Select a native sandbox method and unprivileged port')
    directory = result['sandbox_directory']
    if not isinstance(directory, str) or not directory or '\x00' in directory or not Path(directory).is_absolute():
        raise BinlogArchiveError('Select an absolute sandbox base directory on the execution host')
    supplied = result['native_options']
    if not isinstance(supplied, dict) or set(supplied) - (DEPLOY_OPTIONS if result['operation'] == 'deploy' else set()):
        raise BinlogArchiveError('Select supported native sandbox options; passwords are supplied separately at dispatch')
    if 'portx' in supplied and (type(supplied['portx']) is not int or not 1024 <= supplied['portx'] <= 65535):
        raise BinlogArchiveError('Select a native X Protocol port')
    if 'ignoreSslError' in supplied and type(supplied['ignoreSslError']) is not bool:
        raise BinlogArchiveError('Select a native SSL error policy')
    if 'allowRootFrom' in supplied and (not isinstance(supplied['allowRootFrom'], str) or '\x00' in supplied['allowRootFrom']):
        raise BinlogArchiveError('Supply a native root account host pattern')
    extra = supplied.get('mysqldOptions', [])
    if not isinstance(extra, list) or len(extra) > 512 or any(not isinstance(item, str) or '\x00' in item for item in extra):
        raise BinlogArchiveError('Supply an ordered array of native mysqld options')
    if len(canonical(supplied).encode('utf8')) > 1024 * 1024:
        raise BinlogArchiveError('Supply bounded native sandbox options')
    timeout = result['timeout_seconds']
    if timeout is not None and (type(timeout) is not int or not 1 <= timeout <= 2147483647):
        raise BinlogArchiveError('Select native runtime seconds or null')
    return result


def directory_identity(path):
    path = Path(path)
    # Refuse symlinks/reparse points throughout the selected control path.
    for part in (path, *path.parents):
        info = part.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise BinlogArchiveError('Sandbox directory identity is not a real directory')
    info = path.stat()
    return {'path': str(path), 'device': str(info.st_dev), 'inode': str(info.st_ino)}


def file_identity(path, *, maximum=None):
    path = Path(path)
    if not path.exists() and not path.is_symlink(): return None
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise BinlogArchiveError('Sandbox control file identity is not a regular file')
    if maximum is not None and info.st_size > maximum:
        raise BinlogArchiveError('Sandbox control file exceeds its observation bound')
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        while data := stream.read(1024 * 1024): checksum.update(data)
        after = os.fstat(stream.fileno())
    fields = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    if fields(info) != fields(opened) or fields(opened) != fields(after) or fields(after) != fields(path.stat()):
        raise BinlogArchiveError('Sandbox control file changed during observation')
    return {'path': str(path), 'device': str(info.st_dev), 'inode': str(info.st_ino),
            'size': str(info.st_size), 'sha256': checksum.hexdigest()}


def invoke(client, workspace, source, *, port, timeout=30, secret=None, cancel=None, progress=None, durable=False):
    """Execute our adapter inside the installed native SDK, without a SQL seed."""
    workspace = Path(workspace)
    temporary = Path(tempfile.mkdtemp(prefix='sandbox-call-', dir=workspace))
    marker = 'CDEADMIN_SANDBOX_' + uuid.uuid4().hex + ':'
    script = temporary / 'native-sandbox.py'
    username = 'root' if hasattr(os, 'geteuid') and os.geteuid() == 0 else psutil.Process().username()
    with script.open('x', encoding='utf8') as stream:
        private_file(script)
        runtime_home = str(workspace.parent if durable else workspace)
        stream.write('import json,os\nos.environ["USER"]=' + repr(username) + '\nos.environ["LOGNAME"]=' + repr(username) +
                     '\nos.environ["HOME"]=' + repr(runtime_home) + '\nos.chdir(' + repr(runtime_home) + ')\n' +
                     source + '\nprint(' + repr(marker) + '+json.dumps(result,ensure_ascii=False))\n')
    # Native gadgets uses getpass.getuser() to decide --user=root on POSIX.
    # Supply the actual execution account, never the application login name.
    grant = ProviderToolGrant('mysql-shell', str(workspace), 'localhost', port,
        timeout_seconds=timeout, allow_unbounded_runtime=timeout is None,
        secret_environment_names=(SECRET_FILE,), durable_name='mysql-sandbox' if durable else None)
    observed = None
    try:
        observed = client._tool_runner.run(grant,
            ['--no-defaults', '--py', '--log-level=none', '--quiet-start=2', '--file=' + str(script)],
            secret_config=secret, secret_argument=None, secret_environment_name=SECRET_FILE if secret is not None else None,
            progress=progress, cancel_signal=cancel)
        controls = []
        for line in observed['stdout'].splitlines():
            if line.startswith(marker):
                try: controls.append(json.loads(line[len(marker):]))
                except ValueError: pass
        control = controls[0] if len(controls) == 1 and isinstance(controls[0], dict) else None
        password = json.loads(secret)['password'] if secret is not None else ''
        def redact(value):
            if isinstance(value, dict): return {key: redact(item) for key, item in value.items()}
            if isinstance(value, list): return [redact(item) for item in value]
            if isinstance(value, str) and password: return value.replace(password, '[redacted]')
            return value
        return {'control': redact(control),
                'tool': {key: item for key, item in observed.items() if key not in {'stdout', 'stderr'}},
                'output_text': redact('\n'.join(line for line in (observed['stdout'] + '\n' + observed['stderr']).splitlines() if not line.startswith(marker)))}
    finally:
        if not durable or observed is not None and observed.get('process_observation', {}).get('cleanup_confirmed') is True:
            shutil.rmtree(temporary)


def native_configuration(client, workspace, path, port):
    source = ('from mysql_gadgets.common.config_parser import MySQLOptionsParser\n'
              'parser=MySQLOptionsParser(' + repr(str(path)) + ')\n'
              'names=("port","mysqlx_port","loose_mysqlx_port","datadir","pid_file","basedir","socket","log_error","bind_address")\n'
              'result={name:parser.get("mysqld",name) for name in names if parser.has_option("mysqld",name)}')
    result = invoke(client, workspace, source, port=port)
    if result['tool']['return_code'] != 0 or result['control'] is None:
        raise BinlogArchiveError('Native SDK could not inspect the sandbox configuration')
    return result['control']


def listening(port):
    for family, address in ((socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as stream:
                stream.settimeout(.2)
                if stream.connect_ex((address, port)) == 0: return True
        except OSError: pass
    return False


def process_identity(pid_path, config_path, port):
    if not pid_path.exists():
        return {'pid': None, 'running': False, 'port_listening': listening(port), 'qualified': not listening(port)}
    file_identity(pid_path, maximum=128)
    try: pid = int(pid_path.read_text(encoding='ascii').strip())
    except (ValueError, UnicodeError): raise BinlogArchiveError('Native sandbox PID file is invalid') from None
    if not 1 <= pid <= 0xffffffff: raise BinlogArchiveError('Native sandbox PID is invalid')
    try:
        process = psutil.Process(pid)
        created = process.create_time()
        arguments = process.cmdline()
        executable = process.exe()
        configs = [item.split('=', 1)[1] for item in arguments if item.startswith('--defaults-file=')]
        if '--defaults-file' in arguments:
            offset = arguments.index('--defaults-file')
            if offset + 1 < len(arguments): configs.append(arguments[offset + 1])
        matches = len(configs) == 1 and Path(configs[0]).resolve() == config_path.resolve()
        name_matches = Path(executable).name.lower() in {'mysqld', 'mysqld.exe'}
        connections = process.net_connections(kind='inet')
        owns_port = any(item.status == psutil.CONN_LISTEN and item.laddr.port == port for item in connections)
        if process.create_time() != created: raise BinlogArchiveError('Native sandbox process changed during observation')
        return {'pid': pid, 'created_at': created, 'running': process.is_running() and process.status() != psutil.STATUS_ZOMBIE,
                'executable': file_identity(executable), 'configuration_matches': matches,
                'port_listening': listening(port), 'owns_port': owns_port, 'qualified': matches and name_matches and owns_port}
    except psutil.NoSuchProcess:
        return {'pid': pid, 'running': False, 'port_listening': listening(port), 'qualified': not listening(port)}
    except psutil.Error: raise BinlogArchiveError('Native sandbox process ownership could not be observed') from None


def related_servers(config_path):
    """Also detect initializing/stopping servers that have no usable PID file."""
    result = []
    for process in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            if (process.info['name'] or '').lower() not in {'mysqld', 'mysqld.exe'}: continue
            arguments = process.info['cmdline'] or []
            values = [item.split('=', 1)[1] for item in arguments if item.startswith('--defaults-file=')]
            if '--defaults-file' in arguments:
                index = arguments.index('--defaults-file')
                if index + 1 < len(arguments): values.append(arguments[index + 1])
            if any(Path(item).resolve() == config_path.resolve() for item in values) and process.status() != psutil.STATUS_ZOMBIE:
                result.append({'pid': process.pid, 'created_at': process.info['create_time']})
        except psutil.NoSuchProcess: continue
        except psutil.AccessDenied:
            raise BinlogArchiveError('Native sandbox server process visibility is incomplete') from None
    return sorted(result, key=lambda item: item['pid'])


def observe(client, selected, workspace):
    root = Path(os.path.normpath(selected['sandbox_directory']))
    root_identity = directory_identity(root)
    target = root / str(selected['port'])
    identity = {'host_id': hashlib.sha256((platform.node() + '\0' + str(Path(workspace).anchor)).encode()).hexdigest(),
                'sandbox_directory': str(root), 'port': selected['port']}
    state = {'root': root_identity, 'exists': target.exists() or target.is_symlink()}
    if not state['exists']:
        state['process'] = {'pid': None, 'running': False, 'port_listening': listening(selected['port']),
                            'qualified': not listening(selected['port'])}
        return {'identity': identity, 'state': state}
    state['directory'] = directory_identity(target)
    state['controls'] = {name: file_identity(target / name, maximum=4 * 1024 * 1024)
        for name in ('my.cnf', 'start.sh', 'stop.sh', 'start.bat', 'stop.bat')}
    configuration = target / 'my.cnf'
    if configuration.exists():
        try:
            state['configuration_graph'] = configuration_graph(str(configuration),
                {'working_directory': str(Path(workspace)), 'home_directory': str(Path(workspace))})
        except Refused as error: raise BinlogArchiveError(str(error)) from None
        state['native_configuration'] = values = native_configuration(client, workspace, configuration, selected['port'])
        datadir = Path(values.get('datadir', str(target / 'sandboxdata')))
        if not datadir.is_absolute(): datadir = target / datadir
        if datadir.exists(): state['data_directory'] = directory_identity(datadir)
        state['persisted_configuration'] = file_identity(datadir / 'mysqld-auto.cnf', maximum=4 * 1024 * 1024)
        binaries = [target / 'bin' / ('mysqld.exe' if os.name == 'nt' else 'mysqld')]
        if values.get('basedir'):
            binaries.append(Path(values['basedir']) / 'bin' / ('mysqld.exe' if os.name == 'nt' else 'mysqld'))
        state['server_executables'] = [file_identity(path.resolve()) for path in binaries if path.exists()]
        auto = datadir / 'auto.cnf'
        state['server_identity_file'] = file_identity(auto, maximum=64 * 1024)
        if auto.exists():
            try:
                parser = configparser.ConfigParser(interpolation=None)
                parser.read(auto, encoding='utf8')
                native_uuid = parser.get('auto', 'server-uuid')
                if str(uuid.UUID(native_uuid)) != native_uuid: raise ValueError()
            except (configparser.Error, ValueError): raise BinlogArchiveError('Native sandbox server UUID is invalid') from None
            state['server_uuid'] = native_uuid
    pid_path = Path(state.get('native_configuration', {}).get('pid_file', str(target / (str(selected['port']) + '.pid'))))
    if not pid_path.is_absolute(): pid_path = target / pid_path
    state['process'] = process_identity(pid_path, configuration, selected['port'])
    state['related_servers'] = related_servers(configuration)
    if any(item['pid'] != state['process']['pid'] for item in state['related_servers']):
        state['process']['qualified'] = False
    return {'identity': identity, 'state': state}


def admit(selected, observation):
    state = observation['state']; operation = selected['operation']; process = state['process']
    if not process['qualified']:
        raise BinlogArchiveError('Sandbox process, configuration or listening port belongs to an unconfirmed instance')
    if operation == 'deploy':
        if state['exists']:
            target = Path(selected['sandbox_directory']) / str(selected['port'])
            if any(target.iterdir()): raise BinlogArchiveError('Native sandbox deployment requires an empty target directory')
    elif not state['exists'] or not state.get('controls', {}).get('my.cnf'):
        raise BinlogArchiveError('Select an existing native sandbox configuration')
    if operation in {'start', 'delete'} and (process['running'] or process['port_listening']):
        raise BinlogArchiveError('Stop the native sandbox before starting or deleting its directory')
    if operation in {'stop', 'kill'} and not (process['running'] and process.get('owns_port')):
        raise BinlogArchiveError('Select the exact running native sandbox process')
    values = state.get('native_configuration', {})
    if values:
        if int(values.get('port', 0)) != selected['port']:
            raise BinlogArchiveError('Native sandbox configured port differs from its directory identity')
        configured_pid = Path(values.get('pid_file', ''))
        expected_pid = Path(selected['sandbox_directory']) / str(selected['port']) / (str(selected['port']) + '.pid')
        if operation == 'kill' and configured_pid.resolve() != expected_pid.resolve():
            raise BinlogArchiveError('Native lifecycle PID file differs from the configured server PID file')


def program(client, workspace, selected):
    result = program_identity(client, {'host': 'localhost', 'port': selected['port']}, workspace)
    if selected['operation'] == 'deploy':
        configured = client._tool_runner._allowlist.get('mysql-server')
        if not configured: raise BinlogArchiveError('Configure the native MySQL server binary on this execution host')
        executable = client._tool_runner._resolve(configured)
        grant = ProviderToolGrant('mysql-server', str(workspace), 'localhost', selected['port'], timeout_seconds=30)
        observed = client._tool_runner.run(grant, ['--no-defaults', '--version'])
        if observed['return_code'] != 0 or not re.search(r'\bVer 9\.7\.0\b', observed['stdout']):
            raise BinlogArchiveError('Native sandbox deployment requires the configured MySQL 9.7.0 server installation')
        result['server'] = {'path': str(executable), 'sha256': observed['executable_sha256'], 'version': '9.7.0'}
    return result


def execute(client, selected, workspace, expected_program, secret, *, expected_uuid=None, cancel=None, progress=None, boundary=None):
    if program(client, workspace, selected) != expected_program:
        raise BinlogArchiveError('Native sandbox utility or server installation changed')
    native_options = {**selected['native_options'], 'sandboxDir': selected['sandbox_directory']}
    if selected['operation'] == 'deploy': native_options['mysqldPath'] = expected_program['server']['path']
    source = 'options=json.loads(' + repr(canonical(native_options)) + ')\n'
    if selected['operation'] in {'deploy', 'stop'}:
        source += 'with open(os.environ[' + repr(SECRET_FILE) + '],encoding="utf8") as stream:options["password"]=json.load(stream)["password"]\n'
    source += 'result={"invoked":False,"returned":False,"stage":"identity_admission","native_error":None}\ntry:\n'
    if selected['operation'] == 'stop':
        if not isinstance(expected_uuid, str): raise BinlogArchiveError('Native stop requires the observed sandbox server UUID')
        # Native gadgets Server defaults ssl=False. A cold caching_sha2 account
        # cannot complete that helper's full authentication. Independently admit
        # the actual local server/principal through the native client first,
        # preferring TLS and retaining native RSA authentication when TLS is off.
        # The requested shutdown remains the public native AdminAPI operation.
        source += ('    from mysqlsh import mysql\n'
            '    session=mysql.get_classic_session({"host":"localhost","port":' + str(selected['port']) +
            ',"user":"root","password":options["password"],"ssl-mode":"PREFERRED","get-server-public-key":"true"})\n'
            '    try:\n        actual=session.run_sql("SELECT @@server_uuid").fetch_one()[0]\n'
            '        if actual!=' + repr(expected_uuid) + ':raise RuntimeError("Native sandbox UUID changed before shutdown")\n'
            '    finally:session.close()\n')
    source += ('    result["stage"]="native_method"\n    result["invoked"]=True\n'
        '    dba.' + METHODS[selected['operation']] + '(' + str(selected['port']) + ',options)\n'
        '    result["returned"]=True\n'
        'except Exception as error:\n    result["native_error"]={"type":type(error).__name__,"code":getattr(error,"code",None),"message":str(error)}\n')
    if boundary is not None: boundary()
    return invoke(client, workspace, source, port=selected['port'], timeout=selected['timeout_seconds'], secret=secret,
                  cancel=cancel, progress=progress, durable=True)
