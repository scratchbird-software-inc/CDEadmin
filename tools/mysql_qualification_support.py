"""Uniquely owned exact MySQL fixtures, with retained cleanup evidence."""
from contextlib import contextmanager
import json
from pathlib import Path
import secrets

from tools.cdeadmin_mysql_family_object_live_orchestrator import (
    _run, _wait_until_ready, _root_connection, _image_identity)


@contextmanager
def server(output, *, network=None, server_id=101):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    name = 'sr-mysql-' + secrets.token_hex(8)
    proof = {'image': _image_identity('mysql:9.7.0'), 'owned_server_stopped': False}
    started = False
    try:
        args = ['docker', 'run', '-d', '--rm', '--name', name, '--cap-add=SYS_NICE',
                '-e', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes', '-p', '127.0.0.1::3306']
        if network:
            args += ['--network', network]
        args += ['mysql:9.7.0', '--server-id=' + str(server_id), '--gtid-mode=ON',
                 '--enforce-gtid-consistency=ON', '--log-bin=sr-owned', '--log-replica-updates=ON']
        _run(args)
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
        finally:
            connection.close()
        yield {'host': '127.0.0.1', 'port': port, 'user': 'root', 'use_pure': True}, name, proof
    finally:
        if started:
            log = _run(['docker', 'logs', name], check=False)
            (output / 'server.log').write_text(log.stdout + log.stderr)
            proof['owned_server_stopped'] = _run(['docker', 'stop', name], check=False).returncode == 0
        (output / 'fixture.json').write_text(json.dumps(proof, indent=2) + '\n')
        if started and not proof['owned_server_stopped']:
            raise RuntimeError('Owned MySQL fixture cleanup failed')
