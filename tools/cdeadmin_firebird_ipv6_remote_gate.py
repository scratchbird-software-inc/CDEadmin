#!/usr/bin/env python3
"""Native Linux IPv6 between isolated Docker network namespaces.

Windows/macOS teams must repeat with their application-host native client.
This is a remote container endpoint, not a physical off-host WAN test.
Only the labelled disposable fixture is attached to the owned IPv6 network.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid

from tools.cdeadmin_firebird_password_gate import run
from tools.cdeadmin_firebird_native_opening_gate import (
    docker, published_port, OWNER, wait_ready,
)


def remote_cases(native, admin, route, accounts, evidence):
    candidates = docker('ps', '--filter', 'label=cdeadmin-owned-gate=' + OWNER,
                        '--format', '{{.ID}}').decode().split()
    matches = []
    for item in candidates:
        try:
            port = published_port(item)
        except RuntimeError:
            # Concurrent owned client containers have no published server
            # port and may already have exited. Never select those fixtures.
            continue
        if port == route['port']:
            matches.append(item)
    assert len(matches) == 1
    server = matches[0]
    name = 'cdeadmin-ipv6-' + uuid.uuid4().hex[:16]
    subnet = 'fd' + uuid.uuid4().hex[:2] + ':' + uuid.uuid4().hex[:4] + '::/64'
    user, password = accounts['Srp'][1]
    result = {'checks': [], 'failures': [], 'network_removed': False}
    network = None
    try:
        network = docker('network', 'create', '--ipv6', '--internal',
                         '--subnet', subnet, '--label',
                         'cdeadmin-owned-gate=' + OWNER, name).decode().strip()
        docker('network', 'connect', '--alias', 'owned-firebird', name, server)
        # The initial IPv4-only Docker network makes native AI_ADDRCONFIG
        # select an IPv4 listener. Restart this owned fixture after adding
        # IPv6, explicitly binding the dual-stack socket. No demo is changed.
        admin.close()
        docker('exec', '-i', server, 'tee', '-a',
               '/opt/firebird/firebird.conf',
               input_data=b'\nRemoteBindAddress = ::\nIPv6V6Only = false\n')
        docker('restart', server)
        route['port'] = published_port(server)
        wait_ready(native, {**route, 'user': user}, password)
        info = json.loads(docker('inspect', server))[0]
        address = info['NetworkSettings']['Networks'][name][
            'GlobalIPv6Address']
        assert address
        for host in ('[' + address + ']', 'owned-firebird'):
            for service in (False, True):
                label = ('services-' if service else 'database-') + host
                client_name = 'cdeadmin-ipv6-client-' + uuid.uuid4().hex[:16]
                try:
                    if service:
                        command = [
                            'sh', '-c', 'exec /opt/firebird/bin/fbsvcmgr "$1" '
                            'user "$ISC_USER" password "$ISC_PASSWORD" '
                            'info_server_version', 'owned',
                            'inet6://' + host + ':3050/service_mgr']
                        statement = None
                    else:
                        command = ['/opt/firebird/bin/isql', '-b', '-q',
                                   '-ch', 'UTF8', 'inet6://' + host +
                                   ':3050/' + route['database']]
                        statement = ("SELECT CURRENT_USER, 'IPV6_NATIVE_OK' "
                                     'FROM RDB$DATABASE;\nQUIT;\n').encode()
                    arguments = [
                        'docker', 'run', '--rm', '-i', '--name', client_name,
                        '--network', name,
                        '--label',
                        'cdeadmin-owned-gate=' + OWNER, '--env', 'ISC_USER',
                        '--env', 'ISC_PASSWORD', '--entrypoint', command[0],
                        'firebirdsql/firebird:5.0.4', *command[1:]]
                    process = subprocess.run(
                        arguments,
                        env=dict(os.environ, ISC_USER=user,
                                 ISC_PASSWORD=password), input=statement,
                        capture_output=True, timeout=30)
                    output = process.stdout
                    if process.returncode:
                        diagnostic = (process.stdout + process.stderr).decode(
                            errors='replace').replace(password, '[REDACTED]')
                        result['failures'].append({
                            'case': label, 'diagnostic': diagnostic})
                        continue
                    assert (b'5.0.4' if service else
                            b'IPV6_NATIVE_OK') in output
                    if not service:
                        assert user.encode() in output
                    result['checks'].append(label)
                except Exception as error:
                    result['failures'].append({
                        'case': label, 'type': type(error).__name__})
                finally:
                    # A timed-out Docker CLI may leave its container alive.
                    # Resolve both the unique name and owner label first.
                    remaining = docker(
                        'ps', '-aq', '--filter', 'name=^/' + client_name + '$',
                        '--filter', 'label=cdeadmin-owned-gate=' + OWNER
                    ).decode().split()
                    for owned in remaining:
                        docker('rm', '--force', '--volumes', owned)
    finally:
        if network:
            docker('network', 'disconnect', name, server)
            docker('network', 'rm', name)
            result['network_removed'] = True
        (evidence / 'ipv6-remote.json').write_text(
            json.dumps(result, indent=2) + '\n')
    assert len(result['checks']) == 4 and not result['failures']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    options = parser.parse_args()
    outcome = run(options.evidence_root, selected_plugins=['Srp256'],
                  fixture_check=remote_cases)
    raise SystemExit(0 if outcome['complete'] else 1)
