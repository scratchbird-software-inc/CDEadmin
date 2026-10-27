"""Create/stop one private disposable native MySQL/systemd QEMU fixture.

All guest disks, keys, credentials and logs live in a new external directory.
The host needs KVM, QEMU, xorriso, OpenSSH tools and dpkg-deb. No host service,
system package or existing database is modified. The guest uses MySQL9.7.0.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
IMAGE_URL = 'https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img'
IMAGE_SHA256 = '04e8f2461a16a44e78a370284471f29616cdd9baf1893df25807b71f985b6c94'
SERVER_URL = ('https://repo.mysql.com/apt/ubuntu/pool/mysql-9.7-lts/m/mysql-community/'
              'mysql-community-server-core_9.7.0-1ubuntu24.04_amd64.deb')
SERVER_SHA256 = '56e5da8bd4293f051e572427a88db93beb739baeae389c77988207c4c61ce06c'
UNIT = 'scratchrobin-mysql.service'


def download(url, checksum, path):
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as response, path.open('wb') as stream:
        while True:
            data = response.read(1024 * 1024)
            if not data: break
            digest.update(data); stream.write(data)
    if digest.hexdigest() != checksum:
        raise ValueError('Native fixture archive changed; acquire and review its new checksum explicitly')


def ssh(configuration):
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'UserKnownHostsFile=' + str(Path(configuration['private_key']).parent / 'known_hosts'),
        '-i', configuration['private_key'], '-p', str(configuration['ssh_port']), 'root@127.0.0.1']


def stop(directory):
    directory = Path(directory).resolve()
    record = json.loads((directory / 'connection.json').read_text())
    if record.get('owned_fixture') is not True or Path(record['private_key']).parent != directory:
        raise ValueError('Select this fixture helper\'s exact owned directory')
    pid = record['pid']; command = Path('/proc') / str(pid) / 'cmdline'
    if not command.exists(): return {'owned_vm_stopped': True}
    arguments = command.read_bytes().split(b'\0')
    disk = ('file=' + str(directory / 'working.qcow2')).encode()
    if (not arguments or Path(os.fsdecode(arguments[0])).name != 'qemu-system-x86_64' or
            not any(arg == disk or arg.startswith(disk + b',') for arg in arguments)):
        raise ValueError('The recorded PID no longer belongs to this owned VM')
    with socket.socket(socket.AF_UNIX) as channel:
        channel.settimeout(5); channel.connect(record.get('qmp', str(directory / 'qmp.sock')))
        stream = channel.makefile('rwb', buffering=0)
        def response():
            while True:
                value = json.loads(stream.readline())
                if 'return' in value or 'error' in value: return value
        json.loads(stream.readline())
        stream.write(b'{"execute":"qmp_capabilities"}\r\n'); assert 'return' in response()
        stream.write(b'{"execute":"quit"}\r\n')
        try: response()
        except (ValueError, OSError): pass
    deadline = time.monotonic() + 15
    while command.exists():
        stat = (command.parent / 'stat').read_text().rpartition(')')[2].split()
        if stat and stat[0] == 'Z': break
        if time.monotonic() > deadline: raise TimeoutError('Owned VM did not terminate')
        time.sleep(.1)
    alias = record.get('control_alias')
    if alias is not None:
        alias = Path(alias)
        if alias.name.startswith('scratchrobin-mysql-control-') and (alias / 'vm').is_symlink() and (alias / 'vm').resolve() == directory:
            (alias / 'vm').unlink(); alias.rmdir()
    return {'owned_vm_stopped': True}


def prepare(directory, image_archive=None, server_archive=None):
    directory = Path(directory).resolve()
    if directory == ROOT or ROOT in directory.parents:
        raise ValueError('Keep the disposable VM outside the source repository')
    if ',' in str(directory) or any(ord(char) < 32 for char in str(directory)):
        raise ValueError('Select a fixture directory without QEMU option delimiters')
    for name in ('qemu-system-x86_64', 'qemu-img', 'xorriso', 'ssh', 'scp', 'ssh-keygen', 'dpkg-deb'):
        if not shutil.which(name): raise ValueError('Native fixture prerequisite unavailable: ' + name)
    if not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise ValueError('Native fixture requires the current user\'s KVM access')
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    alias = None
    try:
        for url, checksum, destination, supplied in (
                (IMAGE_URL, IMAGE_SHA256, directory / 'ubuntu-base.qcow2', image_archive),
                (SERVER_URL, SERVER_SHA256, directory / 'mysql-server-core.deb', server_archive)):
            if supplied is None:
                download(url, checksum, destination)
            else:
                supplied = Path(supplied).resolve()
                with supplied.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if digest != checksum: raise ValueError('Supplied native fixture archive hash differs')
                shutil.copy2(supplied, destination)
        metadata = subprocess.check_output(['dpkg-deb', '-f', str(directory / 'mysql-server-core.deb'),
            'Package', 'Version', 'Architecture'], text=True)
        if 'Version: 9.7.0-1ubuntu24.04\n' not in metadata:
            raise ValueError('Native fixture package is not the selected MySQL9.7.0 build')
        key = directory / 'ssh-key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
        hostname = 'sr-mysql-service-' + secrets.token_hex(6)
        seed = directory / 'seed'; seed.mkdir()
        settings = {'hostname': hostname, 'manage_etc_hosts': True, 'disable_root': False, 'ssh_pwauth': False,
            'users': [{'name': 'root', 'ssh_authorized_keys': [key.with_suffix('.pub').read_text().strip()]}],
            'package_update': True, 'packages': ['python3', 'libaio1t64', 'libcurl4t64', 'libmecab2', 'libnuma1', 'libtirpc3t64'],
            'runcmd': [['sh', '-c', 'touch /root/scratchrobin-fixture-os-ready']]}
        (seed / 'user-data').write_text('#cloud-config\n' + json.dumps(settings) + '\n')
        (seed / 'meta-data').write_text('instance-id: ' + hostname + '\nlocal-hostname: ' + hostname + '\n')
        subprocess.run(['xorriso', '-as', 'mkisofs', '-quiet', '-V', 'cidata', '-J', '-r', '-o', str(directory / 'seed.iso'),
            str(seed / 'user-data'), str(seed / 'meta-data')], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['qemu-img', 'create', '-q', '-f', 'qcow2', '-F', 'qcow2', '-b', str(directory / 'ubuntu-base.qcow2'),
            str(directory / 'working.qcow2'), '16G'], check=True)
        def port():
            with socket.socket() as channel: channel.bind(('127.0.0.1', 0)); return channel.getsockname()[1]
        ssh_port, mysql_port = port(), port()
        alias = Path(tempfile.mkdtemp(prefix='scratchrobin-mysql-control-'))
        (alias / 'vm').symlink_to(directory, target_is_directory=True)
        qmp = alias / 'vm/qmp.sock'
        configuration = {'owned_fixture': True, 'hostname': hostname, 'ssh_port': ssh_port, 'mysql_port': mysql_port,
            'private_key': str(key), 'qmp': str(qmp), 'control_alias': str(alias)}
        subprocess.run(['qemu-system-x86_64', '-name', hostname, '-enable-kvm', '-cpu', 'host', '-m', '2048', '-smp', '2',
            '-display', 'none', '-no-reboot', '-drive', f'file={directory}/working.qcow2,if=virtio,format=qcow2',
            '-drive', f'file={directory}/seed.iso,media=cdrom,readonly=on',
            '-netdev', f'user,id=n0,hostfwd=tcp:127.0.0.1:{ssh_port}-:22,hostfwd=tcp:127.0.0.1:{mysql_port}-:3306',
            '-device', 'virtio-net-pci,netdev=n0', '-serial', f'file:{directory}/serial.log',
            '-qmp', f'unix:{qmp},server=on,wait=off', '-daemonize', '-pidfile', str(directory / 'qemu.pid')], check=True)
        configuration['pid'] = int((directory / 'qemu.pid').read_text())
        path = directory / 'connection.json'; path.write_text(json.dumps(configuration, indent=2) + '\n'); path.chmod(0o600)
        # First-use host-key capture applies only to this private, freshly booted
        # VM. Application qualification pins the captured public key before auth.
        command = ssh(configuration)
        command[command.index('StrictHostKeyChecking=yes')] = 'StrictHostKeyChecking=accept-new'
        deadline = time.monotonic() + 900
        while subprocess.run([*command, 'test -f /root/scratchrobin-fixture-os-ready'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            if time.monotonic() > deadline: raise TimeoutError('Owned VM cloud-init setup deadline')
            time.sleep(5)
        command = ssh(configuration)
        subprocess.run(['scp', '-q', '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(directory / 'known_hosts'),
            '-i', str(key), '-P', str(ssh_port), str(directory / 'mysql-server-core.deb'), 'root@127.0.0.1:/tmp/mysql-server-core.deb'], check=True)
        password = 'native-host-' + secrets.token_hex(24)
        config = '[mysqld]\nuser=mysql\ndatadir=/var/lib/mysql\nsocket=/run/mysqld/mysql.sock\npid-file=/run/mysqld/mysql.pid\nbind-address=0.0.0.0\nport=3306\nlog-error=/var/lib/mysql/mysql-error.log\nserver-id=180\nlog-bin=/var/lib/mysql/sr-bin\ngtid_mode=ON\nenforce_gtid_consistency=ON\n'
        unit = '[Unit]\nDescription=Owned native MySQL9.7 fixture\nAfter=network.target\n[Service]\nType=simple\nUser=mysql\nGroup=mysql\nRuntimeDirectory=mysqld\nExecStart=/usr/sbin/mysqld --defaults-file=/etc/scratchrobin-mysql.cnf\nTimeoutStopSec=90\nRestart=on-failure\n'
        init = "CREATE USER host_operator@'%' IDENTIFIED BY '" + password + "';\nGRANT ALL ON *.* TO host_operator@'%' WITH GRANT OPTION;\n"
        script = '''from pathlib import Path
import os,pwd,subprocess
subprocess.run(['dpkg-deb','-x','/tmp/mysql-server-core.deb','/'],check=True)
subprocess.run(['useradd','--system','--no-create-home','--shell','/usr/sbin/nologin','mysql'],check=True)
user=pwd.getpwnam('mysql')
for name in ('/var/lib/mysql','/var/lib/mysql-files'):
 p=Path(name);p.mkdir(mode=0o750);os.chown(p,user.pw_uid,user.pw_gid)
subprocess.run(['/usr/sbin/mysqld','--no-defaults','--initialize-insecure','--user=mysql','--datadir=/var/lib/mysql'],check=True)
'''
        script += 'Path("/etc/scratchrobin-mysql.cnf").write_text(' + repr(config) + ')\n'
        script += 'Path("/etc/systemd/system/' + UNIT + '").write_text(' + repr(unit.replace(' --defaults-file=/etc/scratchrobin-mysql.cnf', ' --defaults-file=/etc/scratchrobin-mysql.cnf --init-file=/var/lib/mysql/sr-init.sql')) + ')\n'
        script += 'p=Path("/var/lib/mysql/sr-init.sql");p.write_text(' + repr(init) + ');p.chmod(0o600);os.chown(p,user.pw_uid,user.pw_gid)\n'
        script += 'subprocess.run(["systemctl","daemon-reload"],check=True)\nsubprocess.run(["systemctl","start","' + UNIT + '"],check=True)\n'
        with (directory / 'provision.log').open('w') as log:
            subprocess.run([*command, 'python3 -'], input=script, text=True, stdout=log, stderr=subprocess.STDOUT, check=True)
        import mysql.connector
        deadline = time.monotonic() + 120
        while True:
            try:
                handle = mysql.connector.connect(host='127.0.0.1', port=mysql_port, user='host_operator', password=password,
                    use_pure=True, connection_timeout=2, read_timeout=2)
                cursor = handle.cursor(); cursor.execute('SELECT VERSION(),@@server_uuid,@@hostname'); facts = cursor.fetchone()
                cursor.close(); handle.close(); assert facts[0] == '9.7.0' and facts[2] == hostname
                break
            except mysql.connector.Error:
                if time.monotonic() > deadline: raise TimeoutError('Owned native MySQL SQL readiness deadline')
                time.sleep(.5)
        script = 'from pathlib import Path;import subprocess;Path("/etc/systemd/system/' + UNIT + '").write_text(' + repr(unit) + ');subprocess.run(["systemctl","daemon-reload"],check=True);Path("/var/lib/mysql/sr-init.sql").unlink()'
        subprocess.run([*command, 'python3 -'], input=script, text=True, check=True)
        configuration.update(mysql_user='host_operator', mysql_password=password, service_name=UNIT, native_uuid=facts[1],
            native_executable='/usr/sbin/mysqld', configuration_file='/etc/scratchrobin-mysql.cnf',
            native_datadir='/var/lib/mysql', native_pid_file='/run/mysqld/mysql.pid')
        path.write_text(json.dumps(configuration, indent=2) + '\n')
        (directory / 'provenance.json').write_text(json.dumps({'image_url': IMAGE_URL, 'image_sha256': IMAGE_SHA256,
            'server_url': SERVER_URL, 'server_sha256': SERVER_SHA256, 'package_metadata': metadata,
            'native_version': facts[0], 'native_uuid': facts[1], 'hostname': hostname, 'release_proven': False}, indent=2) + '\n')
        return {'prepared': True, 'fixture': str(path), 'native_version': facts[0]}
    except BaseException:
        try:
            if (directory / 'connection.json').is_file():
                stop(directory)
            elif alias is not None:
                if (directory / 'qemu.pid').is_file():
                    configuration['pid'] = int((directory / 'qemu.pid').read_text())
                    path = directory / 'connection.json'; path.write_text(json.dumps(configuration) + '\n'); path.chmod(0o600)
                    stop(directory)
                elif (alias / 'vm').is_symlink():
                    (alias / 'vm').unlink(); alias.rmdir()
        except Exception as error:
            (directory / 'cleanup-failure.json').write_text(json.dumps({'cleanup_error_type': type(error).__name__}) + '\n')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'stop')); parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--image-archive', type=Path); parser.add_argument('--server-archive', type=Path)
    args = parser.parse_args(); print(json.dumps(prepare(args.directory, args.image_archive, args.server_archive)
        if args.action == 'prepare' else stop(args.directory)))
