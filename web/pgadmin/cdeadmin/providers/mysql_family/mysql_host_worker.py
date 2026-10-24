"""Standalone host-side MySQL diagnostics, launched only by the pinned SSH port.

This module deliberately needs only the Python standard library and the
ScratchRobin file-permission helper injected by the transport. It can run on a
database host without installing the web application or its database drivers.
"""
import base64
import configparser
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid

try:
    from _cdeadmin_native_fileio import durable_replace, private_directory, private_file
except ModuleNotFoundError:
    from ...operations.fileio import durable_replace, private_directory, private_file

try:
    import _cdeadmin_native_services as native_services
except ModuleNotFoundError:
    from . import mysql_host_services as native_services

MAX_OUTPUT = 512 * 1024
MAX_CONFIGURATION_BYTES = 4 * 1024 * 1024
MAX_CONFIGURATION_ENTRIES = 512
LATIN1_SPACE = b' \t\n\v\f\r\xa0'


class Refused(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def text(value):
    if not isinstance(value, str) or not value or '\x00' in value or len(value.encode('utf8')) > 32768:
        raise Refused('Select bounded native host text')
    return value


def regular(path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise Refused('The selected native host file is not regular')
    return info


def regular_stream(path):
    # A replacement between stat and open must not turn a host observation into
    # a blocking FIFO/device read. Check the opened descriptor itself.
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise Refused('The selected native host file is not regular')
        return os.fdopen(descriptor, 'rb')
    except BaseException:
        os.close(descriptor)
        raise


def file_hash(path):
    value = hashlib.sha256()
    with regular_stream(path) as stream:
        while True:
            data = stream.read(1024 * 1024)
            if not data:
                break
            value.update(data)
    return value.hexdigest()


def binding(value):
    if not isinstance(value, dict) or set(value) != {'server_uuid', 'hostname', 'datadir'}:
        raise Refused('Select an observed native database host binding')
    if str(uuid.UUID(value['server_uuid'])) != value['server_uuid']:
        raise Refused('The native source UUID is unavailable')
    hostname = socket.gethostname()
    expected = text(value['hostname'])
    matching = hostname.casefold() == expected.casefold() if os.name == 'nt' else hostname == expected
    if not matching:
        raise Refused('The authenticated SSH host is not the observed database host')
    directory = Path(text(value['datadir']))
    if not directory.is_absolute():
        raise Refused('The observed native data directory is not absolute on this SSH host')
    directory = directory.resolve(strict=True)
    auto = directory / 'auto.cnf'
    regular(auto)
    with auto.open('r', encoding='utf8') as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise Refused('Native instance identity metadata exceeds its observation bound')
    parsed = configparser.ConfigParser(interpolation=None)
    parsed.read_string(data)
    if parsed.get('auto', 'server-uuid', fallback=None) != value['server_uuid']:
        raise Refused('The authenticated SSH host does not contain the selected native instance')
    return {'server_uuid': value['server_uuid'], 'hostname': hostname, 'datadir': str(directory),
            'platform': sys.platform, 'python_version': list(sys.version_info[:3]),
            'execution_host_kind': 'database-server-ssh-host'}


def environment(executable, workspace):
    if os.name == 'nt':
        root = os.environ.get('SystemRoot') or os.environ.get('SYSTEMROOT')
        if not root:
            raise Refused('Native Windows host execution requires SystemRoot')
        return {'SYSTEMROOT': root, 'WINDIR': root, 'USERPROFILE': str(workspace),
                'TEMP': str(workspace), 'TMP': str(workspace),
                'PATH': os.pathsep.join((str(executable.parent), str(Path(root) / 'System32'), root))}
    locale = 'C' if sys.platform == 'darwin' else 'C.UTF-8'
    return {'LANG': locale, 'LC_ALL': locale, 'HOME': str(workspace),
            'TMPDIR': str(workspace), 'PATH': os.pathsep.join((str(executable.parent), os.defpath))}


def process(executable, arguments, workspace, timeout, configuration_context=None):
    started = time.time()
    native_environment = environment(executable, workspace)
    working_directory = workspace
    if configuration_context is not None:
        working_directory = configuration_context['working_directory']
        native_environment['HOME'] = configuration_context['home_directory']
        if os.name == 'nt':
            native_environment['USERPROFILE'] = configuration_context['home_directory']
    child = subprocess.Popen([str(executable), *arguments], cwd=str(working_directory),
        env=native_environment, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    observations = {}
    def read(name, stream):
        kept = bytearray(); total = 0; checksum = hashlib.sha256()
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                total += len(chunk); checksum.update(chunk)
                kept.extend(chunk[:max(0, MAX_OUTPUT - len(kept))])
        finally:
            stream.close()
            observations[name] = {'base64': base64.b64encode(kept).decode('ascii'),
                'total_bytes': str(total), 'sha256': checksum.hexdigest(), 'truncated': total > len(kept)}
    readers = [threading.Thread(target=read, args=(name, stream), daemon=True)
               for name, stream in (('stdout', child.stdout), ('stderr', child.stderr))]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True; child.kill(); child.wait()
    for reader in readers:
        reader.join(timeout=5)
    return {'return_code': child.returncode, 'timed_out': timed_out,
            'streams_closed': not any(reader.is_alive() for reader in readers),
            'outputs': observations, 'started_at': started, 'finished_at': time.time(),
            'native_process_termination_observed': child.returncode is not None}


def configuration_graph(filename, context):
    """Observe native option-file inputs, without interpreting option values.

    Authority: MySQL9.7 mysys/my_default.cc search_default_file_with_ext,
    remove_end_comment/check_file_permissions and mysys/my_lib.cc my_dir.
    The bounds refuse admission; they never turn a partial scan into proof.
    """
    entries = []; total = 0
    extensions = {'.cnf', '.ini'} if os.name == 'nt' else {'.cnf'}

    def path_for(value, directory=False):
        # includedir is passed directly to my_dir. Its selected child filenames
        # subsequently go through fn_format, including native tilde expansion.
        if not directory:
            drive, name = os.path.splitdrive(value)
            if drive and not os.path.isabs(value):
                raise Refused('Select a fully qualified native configuration drive path')
            if os.name == 'nt':
                name = name.replace('/', os.sep)
            parent, leaf = os.path.split(name)
            absolute = parent.startswith(os.sep); parts = []
            for part in parent.split(os.sep):
                if part in ('', '.'):
                    continue
                if part == '~':
                    parts = ['~']; absolute = False
                elif part == '..' and parts and parts[-1] == '~':
                    expanded = Path(context['home_directory']).parent
                    drive, expanded_name = os.path.splitdrive(str(expanded))
                    absolute = expanded_name.startswith(os.sep)
                    parts = [p for p in expanded_name.split(os.sep) if p]
                elif part == '..' and parts and parts[-1] != '..' and not parts[-1].startswith('~'):
                    parts.pop()
                elif part != '..' or not absolute or parts:
                    parts.append(part)
            parent = (os.sep if absolute else '') + os.sep.join(parts)
            if parent == '~' or parent.startswith('~' + os.sep):
                parent = context['home_directory'] + parent[1:]
            elif parent.startswith('~') and os.name != 'nt':
                parent = os.path.expanduser(parent)
            value = drive + os.path.join(parent, leaf)
        if len(os.fsencode(value)) >= 509:
            raise Refused('The native configuration path exceeds the attested filename bound')
        path = Path(value)
        if not path.is_absolute():
            path = Path(context['working_directory']) / path
        return path

    def entry(path, kind, parent, line, depth):
        if len(entries) >= MAX_CONFIGURATION_ENTRIES:
            raise Refused('The native configuration graph exceeds its observation bound')
        row = {'path': str(path), 'resolved_path': str(path.resolve()), 'kind': kind,
               'parent': parent, 'line': line, 'depth': depth}
        entries.append(row)
        try:
            info = path.stat()
        except FileNotFoundError:
            row['state'] = 'missing'
            return row, None
        row['mode'] = stat.S_IMODE(info.st_mode)
        return row, info

    def argument(raw):
        quote = escape = 0
        for index, byte in enumerate(raw):
            if byte in (34, 39) and not escape:
                quote = byte if not quote else 0 if byte == quote else quote
            if not quote and byte == 35:
                raw = raw[:index]; break
            escape = bool(quote and byte == 92 and not escape)
        # Native does not unquote include filenames or treat ';' as inline comment.
        raw = raw.strip(LATIN1_SPACE)
        if not raw:
            raise Refused('The native configuration contains an empty include directive')
        return os.fsdecode(raw)

    def visit(value, parent=None, line=0, depth=0):
        nonlocal total
        path = path_for(value)
        row, info = entry(path, 'file', parent, line, depth)
        if info is None:
            return
        if not stat.S_ISREG(info.st_mode):
            raise Refused('The native configuration graph contains a nonregular file')
        if os.name != 'nt' and info.st_mode & stat.S_IWOTH:
            row['state'] = 'ignored_world_writable'
            return
        if info.st_size > MAX_CONFIGURATION_BYTES - total:
            raise Refused('The native configuration graph exceeds its byte bound')
        with regular_stream(path) as stream:
            opened = os.fstat(stream.fileno())
            row['mode'] = stat.S_IMODE(opened.st_mode)
            if os.name != 'nt' and opened.st_mode & stat.S_IWOTH:
                row['state'] = 'ignored_world_writable'
                return
            data = stream.read(MAX_CONFIGURATION_BYTES - total + 1)
        total += len(data)
        if total > MAX_CONFIGURATION_BYTES or b'\0' in data:
            raise Refused('The native configuration exceeds its byte bound or contains NUL')
        row.update(state='read', sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        # Split on LF only, like native fgets. CR, VT and NEL are not line breaks.
        for number, raw in enumerate(data.split(b'\n'), 1):
            raw = raw.lstrip(LATIN1_SPACE)
            if not raw.startswith(b'!'):
                continue
            raw = raw[1:].lstrip(LATIN1_SPACE)
            if depth >= 10:
                # Native skips every directive at its recursion limit.
                row.setdefault('directives_skipped_at_native_depth_limit', []).append(number)
                continue
            for keyword in (b'includedir', b'include'):
                if raw.startswith(keyword) and len(raw) > len(keyword) and raw[len(keyword)] in LATIN1_SPACE:
                    value = argument(raw[len(keyword):])
                    if keyword == b'include':
                        visit(value, str(path), number, depth + 1)
                    else:
                        directory = path_for(value, directory=True)
                        listing, status = entry(directory, 'directory', str(path), number, depth + 1)
                        if status is None:
                            break
                        if not stat.S_ISDIR(status.st_mode):
                            raise Refused('The native includedir target is not a directory')
                        names = []
                        for item in directory.iterdir():
                            if len(names) >= MAX_CONFIGURATION_ENTRIES:
                                raise Refused('The native configuration directory exceeds its observation bound')
                            names.append(item.name)
                        names.sort(key=os.fsencode)
                        selected = [name for name in names if '.' in name and name[name.rfind('.'):] in extensions]
                        listing.update(state='listed', selected_names=selected)
                        for name in selected:
                            visit(str(Path(value) / name), str(path), number, depth + 1)
                    break

    visit(str(filename))
    return {'schema': 'cdeadmin.mysql-option-files.v1', 'entries': entries,
            'working_directory': context['working_directory'], 'home_directory': context['home_directory'],
            'observation_scope': 'selected defaults-file graph; not persisted mysqld-auto.cnf or startup/service arguments',
            'atomic_native_file_read_snapshot': False}


def configuration_module():
    if '_cdeadmin_native_configuration' in sys.modules:return sys.modules['_cdeadmin_native_configuration']
    from . import mysql_host_configuration
    return mysql_host_configuration


def initialization_module():
    if '_cdeadmin_native_initialization' in sys.modules:return sys.modules['_cdeadmin_native_initialization']
    from . import mysql_host_initialization
    return mysql_host_initialization


def installation_module():
    if '_cdeadmin_native_installation' in sys.modules:return sys.modules['_cdeadmin_native_installation']
    from . import mysql_host_installation
    return mysql_host_installation


def request_binding(request):
    if request.get('binding',{}).get('scope')=='mysql-initialization-host-v1':
        return initialization_module().host_binding(request['binding'])
    return binding(request['binding'])


def inspect(request, expected=None):
    host = request_binding(request)
    selected = text(request.get('executable', 'mysqld'))
    resolved = shutil.which(selected)
    if resolved is None:
        raise Refused('The selected native mysqld executable is unavailable on this SSH host')
    executable = Path(resolved).resolve(strict=True)
    if executable.name.lower() not in {'mysqld', 'mysqld.exe'}:
        raise Refused('Select the native mysqld executable')
    checksum = file_hash(executable)
    config = request.get('configuration_file')
    configuration = None
    if config is not None:
        path = Path(text(config))
        if not path.is_absolute():
            raise Refused('Select an absolute native configuration filename')
        path = Path(os.path.normpath(str(path)))
        configuration = {'path': str(path), 'sha256': file_hash(path)}
        context = {'working_directory': str(path.parent.resolve(strict=True)),
                   'home_directory': str(path.parent.resolve(strict=True))}
        configuration['context'] = context
        configuration['graph'] = configuration_graph(path, context)
    if expected is not None and (host != expected.get('host') or
            str(executable) != expected.get('program', {}).get('path') or
            checksum != expected.get('program', {}).get('sha256') or
            configuration != expected.get('configuration')):
        raise Refused('The native host, executable or configuration changed after review')
    with tempfile.TemporaryDirectory(prefix='scratchrobin-mysql-version-') as temporary:
        version = process(executable, ['--no-defaults', '--version'], Path(temporary), 15)
    output = b''.join(base64.b64decode(version['outputs'].get(key, {}).get('base64', '')) for key in ('stdout', 'stderr')).decode('utf8', errors='replace')
    import re
    if version['return_code'] != 0 or not re.search(r'\bVer\s+9\.7\.0(?:\s|[-(])', output):
        raise Refused('Select the native MySQL9.7.0 mysqld on this database host')
    if configuration and configuration_graph(configuration['path'], configuration['context']) != configuration['graph']:
        raise Refused('The native configuration graph changed during inspection')
    result = {'host': host, 'program': {'path': str(executable), 'sha256': checksum, 'version_output': output.strip()},
              'configuration': configuration, 'included_configuration_files_attested': True}
    if request.get('initialization') is not None:
        result['initialization_plan']=initialization_module().inspect(request,result)
        if expected is not None and result['initialization_plan']!=expected.get('initialization_plan'):
            raise Refused('Native initialization target changed after review')
    if request.get('configuration_replacement') is not None:
        result['configuration_deployment']=configuration_module().inspect(request,result,globals())
        if expected is not None and result['configuration_deployment']!=expected.get('configuration_deployment'):
            raise Refused('The prospective native option-file inputs changed after review')
    if request.get('service_installation') is not None:
        result['service_installation']=installation_module().inspect(request,result,globals())
        if expected is not None and result['service_installation']!=expected.get('service_installation'):
            raise Refused('The native service installation inputs changed after review')
    elif request.get('service') is not None:
        result['service'] = native_services.inspect(request, result, process, file_hash, regular_stream, Refused)
        if expected is not None and result['service'] != expected.get('service'):
            raise Refused('The native service definition, state or process changed after review')
    return result


def save(path, value):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', dir=str(path.parent), delete=False) as stream:
        temporary = Path(stream.name); private_file(temporary)
        json.dump(value, stream, ensure_ascii=True); stream.flush(); os.fsync(stream.fileno())
    durable_replace(temporary, path)


def dispatch(request,launch_source=None):
    if not isinstance(request, dict) or request.get('schema') != 'cdeadmin.mysql-native-host.v1':
        raise Refused('Select the native MySQL host protocol')
    action = request.get('action')
    if action == 'inspect':
        return inspect(request)
    if action not in {'validate_config', 'service_start', 'service_stop', 'service_restart','service_enable','service_disable','install_service', 'deploy_config', 'initialize_data','cancel_initialization','acknowledge_initialization','status'}:
        raise Refused('The native MySQL host action is unavailable')
    host = request_binding(request)
    root = Path(text(request['workspace']))
    if not root.is_absolute():
        raise Refused('Select an absolute private host workspace')
    root = root.resolve()
    if root in {Path(root.anchor), Path.home().resolve()} or root.is_relative_to(Path(host['datadir'])):
        raise Refused('Select a bounded host workspace separate from the active data directory')
    job_id = text(request['job_id'])
    if str(uuid.UUID(job_id)) != job_id:
        raise Refused('Select an exact native host job identity')
    directory = root / job_id; receipt = directory / 'result.json'
    expected = text(request['input_digest'])
    unavailable = {'state': 'unknown', 'job_id': job_id, 'input_digest': expected,
                   'remote_receipt_available': False, 'automatic_retry': False}
    if action in {'status','cancel_initialization','acknowledge_initialization'} or directory.exists():
        if not receipt.is_file():
            return unavailable
        value = json.loads(receipt.read_text(encoding='utf8'))
        if value.get('input_digest') != expected:
            raise Refused('The remote host receipt belongs to another reviewed input')
        if request.get('initialization') is not None and (directory/'initializer-request.json').exists():
            return initialization_module().observe(directory,value,globals(),cancel=action=='cancel_initialization',acknowledge=action=='acknowledge_initialization')
        if action=='status' and value.get('observation',{}).get('service_installation'):
            return installation_module().observe(directory,value,globals())
        if action == 'status' and request.get('service') is not None and value.get('observation', {}).get('service'):
            # A later unit observation never rewrites the original manager
            # client outcome, and never submits a service action again.
            try:
                followup = {**request, 'previous_service_binding': value['observation']['service']}
                service = native_services.inspect(followup, value['observation'], process, file_hash, regular_stream, Refused)
                value['service_reconciliation'] = {'observed': True, 'service': service,
                    'observed_at': time.time(), 'original_native_result_unchanged': True}
            except Exception as error:
                value['service_reconciliation'] = {'observed': False, 'error_type': type(error).__name__,
                    'original_native_result_unchanged': True}
        return value
    observed = inspect(request, request.get('reviewed', {}))
    if observed != request.get('reviewed'):
        raise Refused('The native host, executable or configuration changed after review')
    timeout = request.get('timeout_seconds', 60)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise Refused('Select a native diagnostic runtime from 1 through 3600 seconds')
    root.mkdir(parents=True, exist_ok=True); private_directory(root)
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        return unavailable
    private_directory(directory)
    value = {'state': 'native_dispatch', 'job_id': job_id, 'input_digest': expected,
             'observation': observed, 'automatic_retry': False, 'remote_database_mutation': action != 'validate_config',
             'validation_scope': ('native mysqld configuration check; not server readiness or upgrade acceptance'
                 if action == 'validate_config' else 'native data-directory initialization; no SQL readiness assertion' if action=='initialize_data' else 'native option-file installation; no service restart or SQL readiness assertion' if action=='deploy_config' else 'native service manager request; not SQL readiness or transaction finality'),
             'transaction_finality_interpreted_by_common_code': False}
    save(receipt, value)
    configuration = observed['configuration']
    arguments = ['--defaults-file=' + configuration['path']] if configuration else ['--no-defaults']
    if action=='initialize_data':
        return initialization_module().start(request,observed,directory,globals(),launch_source)
    if action == 'validate_config':
        result = process(Path(observed['program']['path']), [*arguments, '--validate-config'], directory, timeout,
                         configuration_context=configuration['context'] if configuration else None)
    elif action=='deploy_config':
        deployment=configuration_module().execute(request,observed,directory,timeout,globals())
        value['configuration_deployment_result']=deployment
        result=deployment['native_validation']
    elif action=='install_service':
        installation=installation_module().execute(request,observed,directory,timeout,globals())
        value['service_installation_result']=installation
        result=installation['native_result']
    else:
        result = native_services.execute(action, observed['service'], directory, timeout, process, Refused)
        value['service_request'] = {'operation': action, 'manager_client_completed': result['return_code'] == 0,
            'native_process_outcome_scope': 'service_manager_client_only', 'database_readiness_observed': False,
            'automatic_retry': False}
    value.update(state='native_process_returned', result=result)
    # Persist native completion before making any later filesystem observation.
    save(receipt, value)
    if action=='install_service' and installation.get('installed_service_binding'):
        value['service_after_process']={'observed':True,'service':installation['installed_service_binding']}
        save(receipt,value)
    if action in {'service_start','service_stop','service_restart','service_enable','service_disable'}:
        try:
            after = {**request, 'previous_service_binding': observed['service']}
            value['service_after_process'] = {'observed': True,
                'service': native_services.inspect(after, observed, process, file_hash, regular_stream, Refused)}
        except Exception as error:
            value['service_after_process'] = {'observed': False, 'error_type': type(error).__name__}
        save(receipt, value)
    if configuration:
        try:
            graph = configuration_graph(configuration['path'], configuration['context'])
            value['configuration_after_process'] = {'observed': True,
                'matches_review': graph == (observed['configuration_deployment']['prospective_configuration_graph'] if action=='deploy_config' else configuration['graph']), 'graph': graph,
                'atomic_native_file_read_snapshot': False}
        except Exception as error:
            value['configuration_after_process'] = {'observed': False, 'error_type': type(error).__name__,
                'atomic_native_file_read_snapshot': False}
        save(receipt, value)
    return value
