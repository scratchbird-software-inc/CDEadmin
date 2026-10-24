"""Typed native Linux systemd service facts for an independently bound MySQL.

This standard-library module is transferred with the SSH worker. Service-manager
completion, process association and database readiness are separate observations.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile


def inspect(request, observed, run, file_hash, regular_stream, refused):
    selected = request.get('service')
    if not isinstance(selected, dict) or set(selected) != {'manager', 'name'} or selected['manager'] != 'systemd':
        raise refused('Select a native systemd MySQL service')
    name = selected['name']
    if (not isinstance(name, str) or len(name) > 255 or
            not re.fullmatch(r'[A-Za-z0-9@_.:\\-]+\.service', name)):
        raise refused('Select the exact native MySQL service unit name')
    if not sys.platform.startswith('linux'):
        raise refused('This service adapter requires the native Linux systemd host')
    programs = {}
    for command in ('busctl', 'systemctl'):
        path = shutil.which(command)
        if path is None:
            raise refused('The native service manager is unavailable on this database host')
        path = Path(path).resolve(strict=True)
        programs[command] = {'path': str(path), 'sha256': file_hash(path)}
    with tempfile.TemporaryDirectory(prefix='scratchrobin-service-inspect-') as temporary:
        def query(arguments):
            value = run(Path(programs['busctl']['path']), ['--system', '--json=short', '--', *arguments], Path(temporary), 15)
            if (value['return_code'] != 0 or value.get('timed_out') or
                    value['outputs'].get('stdout', {}).get('truncated')):
                raise refused('Native service inspection was refused or incomplete')
            return json.loads(base64.b64decode(value['outputs']['stdout']['base64']))['data']
        address = query(['call', 'org.freedesktop.systemd1', '/org/freedesktop/systemd1',
                         'org.freedesktop.systemd1.Manager', 'LoadUnit', 's', name])
        if isinstance(address, list) and len(address) == 1:
            address = address[0]
        if not isinstance(address, str) or not address.startswith('/org/freedesktop/systemd1/unit/'):
            raise refused('The native service object identity is unavailable')
        def property_value(interface, field):
            return query(['get-property', 'org.freedesktop.systemd1', address,
                          'org.freedesktop.systemd1.' + interface, field])
        unit = {field: property_value('Unit', field) for field in
                ('Id', 'Names', 'LoadState', 'ActiveState', 'SubState', 'FragmentPath', 'DropInPaths', 'InvocationID','UnitFileState')}
        service = {field: property_value('Service', field) for field in ('MainPID', 'ControlGroup', 'ExecStart', 'ExecStop')}
    if (unit['LoadState'] != 'loaded' or not isinstance(unit['Names'], list) or name not in unit['Names'] or
            not isinstance(unit['DropInPaths'], list) or type(service['MainPID']) is not int):
        raise refused('The selected native MySQL service definition is unavailable')
    files = {}
    for filename in [unit['FragmentPath'], *unit['DropInPaths']]:
        if not isinstance(filename, str) or not Path(filename).is_absolute():
            raise refused('The native service definition filename is unavailable')
        path = Path(filename)
        files[filename] = {'resolved_path': str(path.resolve(strict=True)), 'sha256': file_hash(path)}
    commands = {}
    for field in ('ExecStart', 'ExecStop'):
        value = service[field]
        if not isinstance(value, list) or any(not isinstance(row, list) or len(row) < 3 or
                not isinstance(row[0], str) or not isinstance(row[1], list) or
                any(not isinstance(arg, str) for arg in row[1]) or type(row[2]) is not bool for row in value):
            raise refused('The native service command identity is unavailable')
        # Exclude runtime timestamps/PIDs/status, and expose no command values.
        commands[field] = hashlib.sha256(json.dumps([row[:3] for row in value], separators=(',', ':')).encode()).hexdigest()
    process = None
    pid_file = request.get('native_pid_file')
    if not isinstance(pid_file, str) or not Path(pid_file).is_absolute():
        raise refused('The observed native MySQL PID filename is unavailable')
    if unit['ActiveState'] in {'active', 'activating', 'reloading'}:
        with regular_stream(Path(pid_file)) as stream:
            pid = stream.read(65).strip()
        if not re.fullmatch(rb'[1-9][0-9]{0,9}', pid):
            raise refused('The native MySQL PID file is unavailable')
        directory = Path('/proc') / pid.decode('ascii')
        executable = (directory / 'exe').resolve(strict=True)
        if str(executable) != observed['program']['path'] or file_hash(executable) != observed['program']['sha256']:
            raise refused('The selected service does not contain the observed native mysqld executable')
        group = service['ControlGroup']
        if not isinstance(group, str) or not group.startswith('/') or group == '/':
            raise refused('The native MySQL service control group is unavailable')
        groups = [line.split(':', 2)[2] for line in (directory / 'cgroup').read_text().splitlines()
                  if len(line.split(':', 2)) == 3 and line.split(':', 2)[1] in ('', 'name=systemd')]
        if not any(value == group or value.startswith(group + '/') for value in groups):
            raise refused('The observed native MySQL process belongs to another service')
        fields = (directory / 'stat').read_text().rpartition(')')[2].split()
        process = {'pid': int(pid), 'start_ticks': fields[19],
                   'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                   'unit_control_group_verified': True}
    else:
        previous = request.get('previous_service_binding')
        if (not isinstance(previous, dict) or previous.get('service_binding_verified') is not True or
                previous.get('selected_service') != selected or previous.get('unit', {}).get('Id') != unit['Id']):
            raise refused('Select a prior verified MySQL service review for offline service control')
        if files!=previous.get('definition_files') or commands!=previous.get('command_sha256'):
            raise refused('The original offline MySQL service definition changed; rebind its running native instance')
    unit['Names'] = sorted(unit['Names'])
    return {'manager': 'systemd', 'selected_service': dict(selected), 'unit': unit,
            'manager_programs': programs, 'definition_files': files, 'command_sha256': commands,
            'manager_main_pid': service['MainPID'], 'control_group': service['ControlGroup'],
            'native_process': process, 'native_pid_file': pid_file, 'service_binding_verified': True,
            'source_association': 'current_native_process' if process else 'last_observed_native_process',
            'database_readiness_observed': False}


def execute(operation, service, workspace, timeout, run, refused):
    actions = {'service_start': 'start', 'service_stop': 'stop', 'service_restart': 'restart','service_enable':'enable','service_disable':'disable'}
    if operation not in actions:
        raise refused('Select a native MySQL service action')
    executable = Path(service['manager_programs']['systemctl']['path'])
    return run(executable, ['--no-ask-password', '--no-pager', '--job-mode=fail',
                           actions[operation], '--', service['selected_service']['name']], workspace, timeout)
