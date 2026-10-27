"""Uniquely owned exact MySQL fixtures, with retained cleanup evidence."""
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import socket

from tools.cdeadmin_mysql_family_object_live_orchestrator import (
    _run, _wait_until_ready, _root_connection, _image_identity)


@contextmanager
def server(output, *, network=None, server_id=101,gtid_mode='ON',keyring=False,restartable=False,binary_logging=True,supervised_restart=False,performance_schema=True):
    if supervised_restart and not restartable:raise ValueError('Native restart supervision requires a retained owned fixture')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    name = 'sr-mysql-' + secrets.token_hex(8)
    if gtid_mode not in {'ON','OFF'}:raise ValueError('Select a native fixture GTID mode')
    if type(performance_schema) is not bool:raise ValueError('Select native Performance Schema startup explicitly')
    proof = {'image': _image_identity('mysql:9.7.0'), 'owned_server_stopped': False,'gtid_mode':gtid_mode,'binary_logging':binary_logging,'keyring_component':bool(keyring),'restartable':bool(restartable),'supervised_restart':bool(supervised_restart),'performance_schema':performance_schema}
    started = False
    try:
        args = ['docker', 'run', '-d', '--rm', '--name', name, '--cap-add=SYS_NICE',
                '-e', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes', '-p', '127.0.0.1::3306']
        if restartable:
            args.remove('--rm')
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1',0));host_port=reservation.getsockname()[1]
            args[args.index('127.0.0.1::3306')]='127.0.0.1:'+str(host_port)+':3306'
        if supervised_restart:
            # The final native server is PID1 with namespace parent0. Docker
            # supervises its native restart exit code through on-failure.
            args += ['--restart=on-failure','-e','MYSQLD_PARENT_PID=0']
        if network:
            args += ['--network', network]
        args += ['mysql:9.7.0', '--server-id=' + str(server_id), '--gtid-mode='+gtid_mode,
                 '--enforce-gtid-consistency='+gtid_mode, '--log-bin=sr-owned' if binary_logging else '--skip-log-bin', '--log-replica-updates=ON']
        if not performance_schema:args.append('--performance-schema=OFF')
        if keyring:
            # Load the native keyring before server initialization. A dynamic
            # INSTALL COMPONENT does not activate the startup keyring service.
            manifest=output/'mysqld.my';configuration=output/'component_keyring_file.cnf'
            manifest.write_text(json.dumps({'components':'file://component_keyring_file'}))
            configuration.write_text(json.dumps({'path':'/tmp/sr-owned-keyring','read_only':False}))
            args[1]='create'
            args.remove('-d')
            if '--rm' in args:args.remove('--rm')
            # The image entrypoint probes mysqld before dropping privileges.
            # Run every probe/init/server process as the native mysql OS user
            # so an early keyring file cannot become root-owned and unreadable.
            args.insert(2,'--user=mysql')
            _run(args)
            try:
                _run(['docker','cp',str(manifest),name+':/usr/sbin/mysqld.my'])
                _run(['docker','cp',str(configuration),name+':/usr/lib64/mysql/plugin/component_keyring_file.cnf'])
                _run(['docker','start',name])
            except BaseException:
                _run(['docker','rm','-f',name],check=False)
                raise
        else:
            try:_run(args)
            except BaseException:
                _run(['docker','rm','-f',name],check=False)
                raise
        started = True
        port = _wait_until_ready('mysql', name, 300)
        connection = _root_connection('mysql', port)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT VERSION(), @@server_uuid')
                version, identity = cursor.fetchone()
                if version.split('-')[0] != '9.7.0':
                    raise RuntimeError('Owned fixture version mismatch')
                proof.update(engine_version='9.7.0', server_uuid=identity)
                if keyring:
                    cursor.execute("SELECT STATUS_VALUE FROM performance_schema.keyring_component_status WHERE STATUS_KEY='Component_status'")
                    if cursor.fetchone()!=('Active',):raise RuntimeError('Owned native keyring component is not active')
                    proof['keyring_active']=True
        finally:
            connection.close()
        yield {'host': '127.0.0.1', 'port': port, 'user': 'root', 'use_pure': True}, name, proof
    finally:
        if started:
            log = _run(['docker', 'logs', name], check=False)
            (output / 'server.log').write_text(log.stdout + log.stderr)
            proof['owned_server_stopped'] = _run(['docker', 'stop', name], check=False).returncode == 0
            if (keyring or restartable) and proof['owned_server_stopped']:
                proof['owned_container_removed']=_run(['docker','rm','-v',name],check=False).returncode==0
        (output / 'fixture.json').write_text(json.dumps(proof, indent=2) + '\n')
        if started and not proof['owned_server_stopped']:
            raise RuntimeError('Owned MySQL fixture cleanup failed')
        if started and (keyring or restartable) and not proof.get('owned_container_removed'):
            raise RuntimeError('Owned MySQL fixture removal failed')
