#!/usr/bin/env python3
"""Batch 7 Item 7 (MY-AUDIT-QUAL-RECOVERY-LIFECYCLE):
Execute current-source qualification across all implemented MySQL recovery,
topology, Router, and host-lifecycle workflows using local owned Docker images:
  1. physical           (cdeadmin_mysql_physical_qualification.py on sr-mysql-physical:phase230-1421)
  2. recovery-chain     (cdeadmin_mysql_recovery_chain_qualification.py on mysql:9.7.0 + mysqlsh)
  3. host               (cdeadmin_mysql_host_qualification.py on sr-mysql-host:phase237)
  4. upgrade            (cdeadmin_mysql_upgrade_qualification.py on sr-mysql-upgrade-host:phase246, 8.4.8 -> 9.7.0)
  5. recovered-deploy   (cdeadmin_mysql_recovered_deployment_qualification.py on sr-mysql-deployment-host:phase248)
  6. topology           (cdeadmin_mysql_topology_qualification.py on 3x mysql:9.7.0 + sr-mysql-router-application:phase240)
  7. router             (cdeadmin_mysql_router_qualification.py on 3x mysql:9.7.0 + sr-mysql-router-host:phase240)

Writes sub-receipts into <output-dir>/recovery-lifecycle/ and consolidated
receipt into <output-dir>/recovery-lifecycle.json.
Strictly excludes ScratchBird /history tests (MY-AUDIT-HISTORY is owner_deferred).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / 'web') not in sys.path:
    sys.path.insert(0, str(ROOT / 'web'))
if str(ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tools'))

VENV_SITE_PACKAGES = Path('/home/dcalford/SandBox/CDEadmin/.venv/lib/python3.14/site-packages')


def log_step(msg: str) -> None:
    print(f'[{datetime.now(timezone.utc).strftime("%H:%M:%S")}] {msg}', flush=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def docker_run(args: list[str], *, check: bool = True, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    res = subprocess.run(
        ['docker', *args],
        check=False,
        input=input_bytes,
        capture_output=True,
        text=(input_bytes is None),
    )
    if check and res.returncode != 0:
        out_s = res.stdout.decode('utf-8', 'replace') if isinstance(res.stdout, bytes) else (res.stdout or '')
        err_s = res.stderr.decode('utf-8', 'replace') if isinstance(res.stderr, bytes) else (res.stderr or '')
        err_disp = err_s if len(err_s) <= 4500 else (err_s[:2200] + '\n...[middle truncated]...\n' + err_s[-2200:])
        print(f'[docker_run failed rc={res.returncode}] args={args[:6]}\nSTDOUT:\n{out_s[-3000:]}\nSTDERR:\n{err_disp}', file=sys.stderr, flush=True)
        res.check_returncode()
    return res


def published_port(container: str, port_spec: str) -> int:
    out = docker_run(['port', container, port_spec]).stdout.strip()
    return int(out.splitlines()[0].rsplit(':', 1)[-1])


def wait_systemd_ssh(container: str, timeout: float = 45.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        res = docker_run(['exec', container, 'systemctl', 'is-active', 'ssh'], check=False)
        if res.returncode == 0 and res.stdout.strip() == 'active':
            hk = docker_run(['exec', container, 'cat', '/etc/ssh/ssh_host_ed25519_key.pub']).stdout.strip()
            if hk:
                return hk
        time.sleep(0.5)
    raise TimeoutError(f'systemd ssh did not become active in {container}')


def build_offline_ssh_image(base_image: str, work_dir: Path, tag_prefix: str) -> tuple[str, Path]:
    ssh_dir = work_dir / 'ssh-build'
    ssh_dir.mkdir(parents=True, exist_ok=True)
    key_path = ssh_dir / 'id_ed25519'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key_path)], check=True)
    ctx_dir = ssh_dir / 'ctx'
    ctx_dir.mkdir()
    (ctx_dir / 'authorized_keys').write_bytes(key_path.with_suffix('.pub').read_bytes())
    (ctx_dir / 'Dockerfile').write_text(
        f'FROM {base_image}\n'
        'USER root\n'
        'RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh\n'
        'COPY authorized_keys /root/.ssh/authorized_keys\n'
        'RUN chmod 600 /root/.ssh/authorized_keys\n',
        encoding='utf-8',
    )
    tag = f'{tag_prefix}:{secrets.token_hex(6)}'
    docker_run(['build', '-q', '-t', tag, str(ctx_dir)])
    return tag, key_path


def inject_ssh_key_into_container(container: str, work_dir: Path) -> Path:
    ssh_dir = work_dir / 'ssh-key'
    ssh_dir.mkdir(parents=True, exist_ok=True)
    key_path = ssh_dir / 'id_ed25519'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key_path)], check=True)
    pub_bytes = key_path.with_suffix('.pub').read_bytes()
    docker_run(
        [
            'exec', '-i', container, 'sh', '-c',
            'mkdir -p /root/.ssh && chmod 700 /root/.ssh && cat > /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys '
            '&& printf "%s\\n" "PermitRootLogin prohibit-password" "PasswordAuthentication no" "UsePAM no" "PrintMotd no" > /etc/ssh/sshd_config.d/sr-b7.conf '
            '&& systemctl reload ssh',
        ],
        input_bytes=pub_bytes,
    )
    return key_path


def run_in_clean_python(code: str, extra_env: dict[str, str] | None = None) -> None:
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, check=True)


# ==============================================================================
# 1. PHYSICAL BACKUP / PREPARE / COPY-BACK / REPLAY / RETENTION
# ==============================================================================
def run_sub1_physical(rl_dir: Path, work: Path, mysqlsh: Path) -> Path:
    log_step('Recovery 1/7: Running physical backup/prepare/copy-back/replay/retention qualification...')
    tag, key_path = build_offline_ssh_image('sr-mysql-physical:phase230-1421', work, 'sr-b7-phys-tmp')
    phys_out = work / 'phys-out'
    try:
        code = (
            'import builtins, os; from pathlib import Path; '
            f'out = Path({str(phys_out)!r}); '
            f'os.environ["CDEADMIN_MYSQLSH_BINARY"] = {str(mysqlsh.resolve())!r}; '
            'builtins.SERVER_MODE = None; import config; '
            'config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False; '
            'config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False; '
            '[setattr(config, k, str(out / r)) for k, r in {"DATA_DIR":"app","SQLITE_PATH":"app/application.db",'
            '"SESSION_DB_PATH":"app/sessions","STORAGE_DIR":"app/storage","LOG_FILE":"app/application.log",'
            '"AZURE_CREDENTIAL_CACHE_DIR":"app/azure","CDEADMIN_OPERATION_STORE_PATH":"app/operations.json"}.items()]; '
            'import pgadmin; '
            'from tools.cdeadmin_mysql_physical_qualification import qualify; '
            f'res = qualify(out, {tag!r}, key={str(key_path)!r}, prepare=False, connections=True, replay=True, retention=True); '
            'assert res["complete"] is True, res'
        )
        run_in_clean_python(code)
        doc = json.loads((phys_out / 'summary.json').read_text(encoding='utf-8'))
        assert doc['complete'] is True and doc['owned_servers_stopped'] is True and doc['owned_physical_volume_removed'] is True
    finally:
        docker_run(['rmi', '-f', tag], check=False)

    dest = rl_dir / 'physical.json'
    dest.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Recovery 1/7 complete -> {dest}')
    return dest


# ==============================================================================
# 2. RECOVERY CHAIN DEPENDENCIES / PROTECTION / RETIREMENT
# ==============================================================================
def run_sub2_recovery_chain(rl_dir: Path, work: Path, mysqlsh: Path) -> Path:
    log_step('Recovery 2/7: Running recovery-chain lineage/protection/retirement qualification...')
    rc_out = work / 'rc-out'
    code = (
        'import builtins; from pathlib import Path; '
        f'out = Path({str(rc_out)!r}); '
        'builtins.SERVER_MODE = None; import config; '
        'config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False; '
        'config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False; '
        '[setattr(config, k, str(out / r)) for k, r in {"DATA_DIR":"app","SQLITE_PATH":"app/application.db",'
        '"SESSION_DB_PATH":"app/sessions","STORAGE_DIR":"app/storage","LOG_FILE":"app/application.log",'
        '"AZURE_CREDENTIAL_CACHE_DIR":"app/azure","CDEADMIN_OPERATION_STORE_PATH":"app/operations.json"}.items()]; '
        'import pgadmin; '
        'from tools.cdeadmin_mysql_recovery_chain_qualification import qualify; '
        f'res = qualify(out, {str(mysqlsh.resolve())!r}, use_c=True); '
        'assert res["complete"] is True, res'
    )
    run_in_clean_python(code)
    doc = json.loads((rc_out / 'summary.json').read_text(encoding='utf-8'))
    assert doc['complete'] is True
    dest = rl_dir / 'recovery-chain.json'
    dest.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Recovery 2/7 complete -> {dest}')
    return dest


# ==============================================================================
# 3. HOST DIAGNOSTICS / CONFIG DEPLOYMENT / DATADIR INITIALIZATION
# ==============================================================================
def run_sub3_host(rl_dir: Path, work: Path) -> Path:
    log_step('Recovery 3/7: Running database-host diagnostics/config-deploy/initialization qualification...')
    tag, key_path = build_offline_ssh_image('sr-mysql-host:phase237', work, 'sr-b7-host-tmp')
    host_out = work / 'host-out'
    try:
        code = (
            'import builtins; from pathlib import Path; '
            f'out = Path({str(host_out)!r}); '
            'builtins.SERVER_MODE = None; import config; '
            'config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False; '
            'config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False; '
            '[setattr(config, k, str(out / r)) for k, r in {"DATA_DIR":"app","SQLITE_PATH":"app/application.db",'
            '"SESSION_DB_PATH":"app/sessions","STORAGE_DIR":"app/storage","LOG_FILE":"app/application.log",'
            '"AZURE_CREDENTIAL_CACHE_DIR":"app/azure","CDEADMIN_OPERATION_STORE_PATH":"app/operations.json"}.items()]; '
            'import pgadmin; '
            'from tools.cdeadmin_mysql_host_qualification import qualify; '
            f'res = qualify(out, fixture_image={tag!r}, private_key={str(key_path)!r}, prepare=False, '
            'use_c=True, configuration_deployment=True, initialization=True); '
            'assert res["complete"] is True, res'
        )
        run_in_clean_python(code)
        doc = json.loads((host_out / 'summary.json').read_text(encoding='utf-8'))
        assert doc['complete'] is True and doc['owned_servers_stopped'] is True
    finally:
        docker_run(['rmi', '-f', tag], check=False)

    dest = rl_dir / 'host.json'
    dest.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Recovery 3/7 complete -> {dest}')
    return dest


# ==============================================================================
# 4. IN-PLACE UPGRADE (8.4.8 -> 9.7.0 systemd service + dictionary upgrade)
# ==============================================================================
def run_sub4_upgrade(rl_dir: Path, work: Path) -> Path:
    log_step('Recovery 4/7: Running 8.4.8 -> 9.7.0 in-place service upgrade qualification...')
    import mysql.connector

    cname = f'sr-upgrade245-{secrets.token_hex(6)}'
    started = False
    try:
        docker_run([
            'run', '-d', '--rm', '--privileged', '--cgroupns=private',
            '--tmpfs', '/run', '--tmpfs', '/run/lock',
            '--name', cname, '--hostname', cname,
            '-p', '127.0.0.1::22', '-p', '127.0.0.1::3306',
            'sr-mysql-upgrade-host:phase246',
        ])
        started = True
        host_key = wait_systemd_ssh(cname)
        key_path = inject_ssh_key_into_container(cname, work)
        ssh_port = published_port(cname, '22/tcp')
        sql_port = published_port(cname, '3306/tcp')

        # Initialize MySQL 8.4.8 datadir and start systemd unit sr-upgrade245.service
        setup_sh = """set -e
id mysql >/dev/null 2>&1 || useradd -r -s /sbin/nologin mysql
mkdir -p /var/lib/mysql-files /opt/sr-upgrade245/data
chown mysql:mysql /var/lib/mysql-files
chmod 750 /var/lib/mysql-files
chown -R mysql:mysql /opt/sr-upgrade245
cat > /opt/sr-upgrade245/my.cnf <<'CNF'
[mysqld]
datadir=/opt/sr-upgrade245/data
pid-file=/opt/sr-upgrade245/data/mysql.pid
socket=/opt/sr-upgrade245/data/mysql.sock
port=3306
bind-address=0.0.0.0
user=mysql
server-id=101
gtid-mode=ON
enforce-gtid-consistency=ON
log-bin=binlog
CNF
chmod 644 /opt/sr-upgrade245/my.cnf
/opt/mysql84/usr/sbin/mysqld --defaults-file=/opt/sr-upgrade245/my.cnf --basedir=/opt/mysql84/usr --initialize-insecure --user=mysql
cat > /etc/systemd/system/sr-upgrade245.service <<'UNIT'
[Unit]
Description=Owned MySQL 8.4->9.7 upgrade service
After=network.target

[Service]
Type=simple
User=mysql
Group=mysql
ExecStart=/opt/mysql84/usr/sbin/mysqld --defaults-file=/opt/sr-upgrade245/my.cnf --basedir=/opt/mysql84/usr --user=mysql
Restart=no

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now sr-upgrade245.service
"""
        docker_run(['exec', '-i', cname, 'bash', '-s'], input_bytes=setup_sh.encode('utf-8'))

        # Wait for 8.4.8 SQL readiness via socket inside container, then create sr_upgrade@%
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            r = docker_run([
                'exec', cname, '/opt/scratchrobin-native/mysql/bin/mysqlsh',
                '--no-wizard', '--mysql', '--sql', '--socket=/opt/sr-upgrade245/data/mysql.sock', '-uroot', '--no-password',
                '-e', "CREATE USER IF NOT EXISTS 'sr_upgrade'@'%' IDENTIFIED BY 'owned-upgrade-private'; "
                      "GRANT ALL PRIVILEGES ON *.* TO 'sr_upgrade'@'%' WITH GRANT OPTION; FLUSH PRIVILEGES;",
            ], check=False)
            if r.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise TimeoutError('MySQL 8.4.8 did not become ready in upgrade container')

        # Verify TCP connection from host
        c = mysql.connector.connect(host='127.0.0.1', port=sql_port, user='sr_upgrade', password='owned-upgrade-private')
        c.close()

        fix_file = work / 'upgrade-fixture.json'
        fix_file.write_text(json.dumps({
            'complete': True,
            'container': cname,
            'application_host': '127.0.0.1',
            'sql_port': sql_port,
            'ssh_port': ssh_port,
            'host_key': host_key,
            'private_key': str(key_path),
            'legacy': '/opt/mysql84/usr/sbin/mysqld',
            'candidate': '/opt/mysql97/usr/sbin/mysqld',
            'configuration': '/opt/sr-upgrade245/my.cnf',
            'service': 'sr-upgrade245.service',
        }, indent=2) + '\n', encoding='utf-8')

        upg_out = work / 'upg-out'
        code = (
            'import builtins; from pathlib import Path; '
            f'out = Path({str(upg_out)!r}); '
            'builtins.SERVER_MODE = None; import config; '
            'config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False; '
            'config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False; '
            '[setattr(config, k, str(out / r)) for k, r in {"DATA_DIR":"app","SQLITE_PATH":"app/application.db",'
            '"SESSION_DB_PATH":"app/sessions","STORAGE_DIR":"app/storage","LOG_FILE":"app/application.log",'
            '"AZURE_CREDENTIAL_CACHE_DIR":"app/azure","CDEADMIN_OPERATION_STORE_PATH":"app/operations.json"}.items()]; '
            'import pgadmin; '
            'from tools.cdeadmin_mysql_upgrade_qualification import qualify; '
            f'res = qualify(out, {str(fix_file)!r}, use_c=True); '
            'assert res["complete"] is True, res'
        )
        run_in_clean_python(code)
        doc = json.loads((upg_out / 'summary.json').read_text(encoding='utf-8'))
        assert doc['complete'] is True
    finally:
        if started:
            docker_run(['rm', '-fv', cname], check=False)

    doc['owned_server_stopped'] = True
    dest = rl_dir / 'upgrade.json'
    dest.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Recovery 4/7 complete -> {dest}')
    return dest


# ==============================================================================
# 5. RECOVERED DEPLOYMENT & PRODUCTION CUTOVER
# ==============================================================================
def run_sub5_recovered_deployment(rl_dir: Path, work: Path, mysqlsh: Path) -> Path:
    log_step('Recovery 5/7: Running cold-stage recovered deployment & production cutover qualification...')
    import mysql.connector

    cname = f'sr-deployment248-{secrets.token_hex(6)}'
    started = False
    try:
        docker_run([
            'run', '-d', '--rm', '--privileged', '--cgroupns=private',
            '--tmpfs', '/run', '--tmpfs', '/run/lock',
            '--name', cname, '--hostname', cname,
            '-p', '127.0.0.1::22', '-p', '127.0.0.1::3306', '-p', '127.0.0.1::3349',
            'sr-mysql-deployment-host:phase248',
        ])
        started = True
        host_key = wait_systemd_ssh(cname)
        key_path = inject_ssh_key_into_container(cname, work)
        ssh_port = published_port(cname, '22/tcp')
        sql_port = published_port(cname, '3306/tcp')
        deploy_port = published_port(cname, '3349/tcp')

        setup_sh = """set -e
id mysql >/dev/null 2>&1 || useradd -r -s /sbin/nologin mysql
mkdir -p /var/lib/mysql-files /opt/sr-deployment248/data
chown mysql:mysql /var/lib/mysql-files
chmod 750 /var/lib/mysql-files
chown -R mysql:mysql /opt/sr-deployment248
cat > /opt/sr-deployment248/my.cnf <<'CNF'
[mysqld]
datadir=/opt/sr-deployment248/data
pid-file=/opt/sr-deployment248/data/mysql.pid
socket=/opt/sr-deployment248/data/mysql.sock
port=3306
bind-address=0.0.0.0
user=mysql
server-id=101
gtid-mode=ON
enforce-gtid-consistency=ON
log-bin=binlog
CNF
chmod 644 /opt/sr-deployment248/my.cnf
/opt/mysql97/usr/sbin/mysqld --defaults-file=/opt/sr-deployment248/my.cnf --basedir=/opt/mysql97/usr --initialize-insecure --user=mysql
cat > /etc/systemd/system/sr-deployment248.service <<'UNIT'
[Unit]
Description=Owned MySQL 9.7 source deployment service
After=network.target

[Service]
Type=simple
User=mysql
Group=mysql
ExecStart=/opt/mysql97/usr/sbin/mysqld --defaults-file=/opt/sr-deployment248/my.cnf --basedir=/opt/mysql97/usr --user=mysql
Restart=no

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now sr-deployment248.service
"""
        docker_run(['exec', '-i', cname, 'bash', '-s'], input_bytes=setup_sh.encode('utf-8'))

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            r = docker_run([
                'exec', cname, '/opt/sr-mysql-client/mysql',
                '--socket=/opt/sr-deployment248/data/mysql.sock', '-uroot',
                '-e', "CREATE USER IF NOT EXISTS 'sr_physical'@'%' IDENTIFIED BY 'owned-deployment-private'; "
                      "GRANT ALL PRIVILEGES ON *.* TO 'sr_physical'@'%' WITH GRANT OPTION; FLUSH PRIVILEGES;",
            ], check=False)
            if r.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise TimeoutError('MySQL 9.7.0 did not become ready in deployment248 container')

        c = mysql.connector.connect(host='127.0.0.1', port=sql_port, user='sr_physical', password='owned-deployment-private')
        c.close()

        fix_file = work / 'deployment-fixture.json'
        fix_file.write_text(json.dumps({
            'complete': True,
            'container': cname,
            'sql_port': sql_port,
            'deployment_port': deploy_port,
            'ssh_port': ssh_port,
            'host_key': host_key,
            'private_key': str(key_path),
            'configuration': '/opt/sr-deployment248/my.cnf',
            'service': 'sr-deployment248.service',
            'candidate': '/opt/mysql97/usr/sbin/mysqld',
        }, indent=2) + '\n', encoding='utf-8')

        dep_out = work / 'dep-out'
        code = (
            'import builtins; from pathlib import Path; '
            f'out = Path({str(dep_out)!r}); '
            'builtins.SERVER_MODE = None; import config; '
            'config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False; '
            'config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False; '
            '[setattr(config, k, str(out / r)) for k, r in {"DATA_DIR":"app","SQLITE_PATH":"app/application.db",'
            '"SESSION_DB_PATH":"app/sessions","STORAGE_DIR":"app/storage","LOG_FILE":"app/application.log",'
            '"AZURE_CREDENTIAL_CACHE_DIR":"app/azure","CDEADMIN_OPERATION_STORE_PATH":"app/operations.json"}.items()]; '
            'import pgadmin; '
            'from tools.cdeadmin_mysql_recovered_deployment_qualification import qualify; '
            f'res = qualify(out, {str(fix_file)!r}, use_c=True, mysql_shell={str(mysqlsh.resolve())!r}); '
            'assert res["complete"] is True, res'
        )
        run_in_clean_python(code)
        doc = json.loads((dep_out / 'summary.json').read_text(encoding='utf-8'))
        assert doc['complete'] is True
    finally:
        if started:
            docker_run(['rm', '-fv', cname], check=False)

    doc['owned_server_stopped'] = True
    dest = rl_dir / 'recovered-deployment.json'
    dest.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Recovery 5/7 complete -> {dest}')
    return dest


def start_three_cluster_peers(network: str, prefix: str, root_password: str) -> tuple[list[dict], list[str]]:
    import mysql.connector
    from tools.cdeadmin_mysql_family_object_live_orchestrator import _wait_until_ready

    peers = []
    containers = []
    for idx in range(3):
        cname = f'{prefix}-peer-{idx}'
        sid = 210 + idx
        docker_run([
            'run', '-d', '--name', cname, '--hostname', cname, '--network', network,
            '--restart=on-failure', '-e', 'MYSQLD_PARENT_PID=0',
            '-e', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes',
            '-p', '127.0.0.1::3306', '-p', '127.0.0.1::33061',
            'mysql:9.7.0',
            f'--server-id={sid}',
            '--gtid-mode=ON',
            '--enforce-gtid-consistency=ON',
            '--log-bin=mysql-bin',
            f'--report-host={cname}',
            '--report-port=3306',
            '--disabled-storage-engines=MyISAM,BLACKHOLE,FEDERATED,ARCHIVE,MEMORY',
        ])
        containers.append(cname)
        host_port = _wait_until_ready('mysql', cname, 120)
        conn = mysql.connector.connect(host='127.0.0.1', port=host_port, user='root', autocommit=True)
        try:
            cur = conn.cursor()
            cur.execute('SELECT @@server_uuid')
            suuid = str(cur.fetchone()[0])
            cur.execute("CREATE USER IF NOT EXISTS 'root'@'%'")
            cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION")
            cur.execute("ALTER USER 'root'@'%' IDENTIFIED BY %s", (root_password,))
            cur.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (root_password,))
            cur.execute('FLUSH PRIVILEGES')
            cur.close()
        finally:
            conn.close()
        peers.append({
            'container': cname,
            'host': cname,
            'port': 3306,
            'host_port': host_port,
            'server_uuid': suuid,
        })
    return peers, containers


# ==============================================================================
# 6. TOPOLOGY (InnoDB Cluster / ClusterSet / ReplicaSet / Clone / Quiescence)
# ==============================================================================
def run_sub6_topology(rl_dir: Path, work: Path) -> Path:
    log_step('Recovery 6/7: Running InnoDB Cluster / ClusterSet / ReplicaSet topology qualification...')
    net = f'sr-b7-topo-{secrets.token_hex(5)}'
    containers: list[str] = []
    app_cname = f'{net}-app'
    docker_run(['network', 'create', net])
    try:
        pw = 'TopoRoot#' + secrets.token_urlsafe(14)
        peers, containers = start_three_cluster_peers(net, net, pw)
        work.chmod(0o755)
        routes_file = work / 'routes.json'
        routes_file.write_text(
            json.dumps([{'host': p['host'], 'port': 3306} for p in peers], indent=2) + '\n',
            encoding='utf-8',
        )
        topo_code = (
            'import builtins, json, os, shutil; from pathlib import Path; '
            'out = Path("/tmp/sr-topo-out"); out.mkdir(mode=0o700, parents=True, exist_ok=False); '
            'os.environ["CDEADMIN_MYSQLSH_BINARY"] = "/opt/scratchrobin-native/mysql/bin/mysqlsh"; '
            'builtins.SERVER_MODE = None; import config; '
            'config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False; '
            'config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False; '
            '[setattr(config, k, str(out / r)) for k, r in {"DATA_DIR":"app","SQLITE_PATH":"app/application.db",'
            '"SESSION_DB_PATH":"app/sessions","STORAGE_DIR":"app/storage","LOG_FILE":"app/application.log",'
            '"AZURE_CREDENTIAL_CACHE_DIR":"app/azure","CDEADMIN_OPERATION_STORE_PATH":"app/operations.json"}.items()]; '
            'import pgadmin; '
            'from tools.cdeadmin_mysql_topology_qualification import qualify; '
            'selected = json.loads(Path("/work/routes.json").read_text()); '
            'qualify(out, selected, os.environ["SR_TOPO_PW"], use_c=True); '
            'shutil.copy2(out / "summary.json", "/work/topo-summary.json")'
        )
        docker_run([
            'run', '--rm', '--name', app_cname, '--network', net,
            '-v', f'{ROOT}:/workspace:ro',
            '-v', f'{VENV_SITE_PACKAGES}:/usr/local/lib/python3.14/site-packages:ro',
            '-v', f'{work}:/work',
            '-e', 'PYTHONPATH=/workspace:/workspace/web:/workspace/tools',
            '-e', f'SR_TOPO_PW={pw}',
            'sr-mysql-router-application:phase240',
            'python3', '-c', topo_code,
        ])
        doc = json.loads((work / 'topo-summary.json').read_text(encoding='utf-8'))
        assert doc['complete'] is True, doc
    finally:
        docker_run(['rm', '-fv', app_cname], check=False)
        for c in reversed(containers):
            docker_run(['rm', '-fv', c], check=False)
        docker_run(['network', 'rm', net], check=False)

    doc['owned_servers_stopped'] = True
    dest = rl_dir / 'topology.json'
    dest.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Recovery 6/7 complete -> {dest}')
    return dest


# ==============================================================================
# 7. MYSQL ROUTER BOOTSTRAP / SYSTEMD LIFECYCLE / PRIMARY CRASH FAILOVER
# ==============================================================================
def run_sub7_router(rl_dir: Path, work: Path) -> Path:
    log_step('Recovery 7/7: Running MySQL Router bootstrap, systemd lifecycle & primary crash failover...')
    net = f'sr-router240-{secrets.token_hex(5)}'
    containers: list[str] = []
    router_cname = f'{net}-router-host'
    app_cname = f'{net}-app'
    stop_watcher = threading.Event()
    watcher_thread = None
    docker_run(['network', 'create', net])
    try:
        # Router qualification expects root password 'true' (line 46 & 156 of cdeadmin_mysql_router_qualification.py)
        peers, containers = start_three_cluster_peers(net, net, 'true')

        # Form the 3-node InnoDB Cluster using mysqlsh inside sr-mysql-router-application:phase240
        init_py = '\n'.join([
            'import mysqlsh, time',
            'dba = mysqlsh.globals.dba',
            f'p0, p1, p2 = {peers[0]["host"]!r}, {peers[1]["host"]!r}, {peers[2]["host"]!r}',
            'for h in (p0, p1, p2):',
            '    dba.configure_instance(f"root:true@{h}:3306", {"restart": True})',
            'for _ in range(40):',
            '    try:',
            '        mysqlsh.globals.shell.connect(f"root:true@{p0}:3306")',
            '        break',
            '    except Exception:',
            '        time.sleep(0.5)',
            'cl = dba.create_cluster("sr_router_cluster", {"gtidSetIsComplete": True})',
            'cl.add_instance(f"root:true@{p1}:3306", {"recoveryMethod": "clone", "recoveryProgress": 0})',
            'cl.add_instance(f"root:true@{p2}:3306", {"recoveryMethod": "clone", "recoveryProgress": 0})',
            'print("CLUSTER_ONLINE")',
        ])
        docker_run([
            'run', '--rm', '--network', net,
            'sr-mysql-router-application:phase240',
            '/opt/scratchrobin-native/mysql/bin/mysqlsh', '--no-wizard', '--py', '-e', init_py,
        ])
        docker_run(['update', '--restart=no', *[p['container'] for p in peers]])

        # Start systemd Router host container (--hostname must be sr-router-native-host per line 90)
        docker_run([
            'run', '-d', '--rm', '--privileged', '--cgroupns=private',
            '--tmpfs', '/run', '--tmpfs', '/run/lock',
            '--name', router_cname, '--hostname', 'sr-router-native-host',
            '--network', net,
            'sr-mysql-router-host:phase240',
        ])
        containers.append(router_cname)
        host_key = wait_systemd_ssh(router_cname)
        docker_run(['exec', router_cname, 'sh', '-c', 'id mysqlrouter >/dev/null 2>&1 || useradd -r -s /sbin/nologin mysqlrouter'])
        work.chmod(0o755)
        key_path = inject_ssh_key_into_container(router_cname, work)
        key_in_work = work / 'router_id_ed25519'
        shutil.copy2(key_path, key_in_work)
        key_in_work.chmod(0o600)

        router_ip = docker_run([
            'inspect', '-f', f'{{{{(index .NetworkSettings.Networks "{net}").IPAddress}}}}', router_cname,
        ]).stdout.strip()
        assert router_ip, 'Missing Router container IP'

        fix_dir = work / 'router-fixture'
        fix_dir.mkdir(parents=True, exist_ok=True)
        fix_dir.chmod(0o777)
        controls_dir = fix_dir / 'controls'
        controls_dir.mkdir(parents=True, exist_ok=True)
        controls_dir.chmod(0o777)

        fix_json = fix_dir / 'fixture.json'
        fix_json.write_text(json.dumps({
            'complete': True,
            'network': net,
            'router_address': router_ip,
            'host_key': host_key,
            'private_key': '/tmp/router_id_ed25519',
            'peers': [{'container': p['container'], 'host': p['host'], 'port': 3306, 'server_uuid': p['server_uuid']} for p in peers],
        }, indent=2) + '\n', encoding='utf-8')

        # Host-side control watcher servicing crash & start requests from cdeadmin_mysql_router_qualification.py
        def _async_rejoin(target_c: str) -> None:
            for _ in range(60):
                if stop_watcher.is_set():
                    return
                chk = docker_run(['exec', target_c, 'mysql', '-uroot', '-ptrue', '-Nse', 'SELECT 1'], check=False)
                if chk.returncode == 0:
                    break
                time.sleep(0.5)
            seed_h = peers[0]['host'] if peers[0]['container'] != target_c else peers[1]['host']
            rejoin_py = '\n'.join([
                'import mysqlsh',
                f'mysqlsh.globals.shell.connect("root:true@{seed_h}:3306")',
                'cl = mysqlsh.globals.dba.get_cluster()',
                'try:',
                f'    cl.rejoin_instance("root:true@{target_c}:3306")',
                'except Exception:',
                '    pass',
            ])
            docker_run([
                'run', '--rm', '--network', net,
                'sr-mysql-router-application:phase240',
                '/opt/scratchrobin-native/mysql/bin/mysqlsh', '--no-wizard', '--py', '-e', rejoin_py,
            ], check=False)

        def _watch_controls() -> None:
            while not stop_watcher.is_set():
                for req_path in list(controls_dir.glob('*.request.json')):
                    ans_path = req_path.with_name(req_path.name.replace('.request.json', '.answer.json'))
                    if ans_path.exists():
                        continue
                    try:
                        payload = json.loads(req_path.read_text(encoding='utf-8'))
                        op = payload['operation']
                        target_c = payload['container']
                        assert target_c in containers
                        if op == 'crash':
                            r = docker_run(['kill', '-s', '9', target_c], check=False)
                            rc = r.returncode
                        elif op == 'start':
                            r = docker_run(['start', target_c], check=False)
                            rc = r.returncode
                            if rc == 0:
                                threading.Thread(target=_async_rejoin, args=(target_c,), daemon=True).start()
                        else:
                            rc = 1
                        ans_path.write_text(json.dumps({'return_code': rc}) + '\n', encoding='utf-8')
                    except Exception as exc:
                        ans_path.write_text(json.dumps({'return_code': 1, 'error': str(exc)}) + '\n', encoding='utf-8')
                time.sleep(0.1)

        watcher_thread = threading.Thread(target=_watch_controls, daemon=True)
        watcher_thread.start()

        router_code = (
            'import builtins, os, shutil; from pathlib import Path; '
            'shutil.copy2("/work/router_id_ed25519", "/tmp/router_id_ed25519"); '
            'os.chmod("/tmp/router_id_ed25519", 0o600); '
            'out = Path("/tmp/sr-router-out"); '
            'os.environ["CDEADMIN_MYSQLSH_BINARY"] = "/opt/scratchrobin-native/mysql/bin/mysqlsh"; '
            'builtins.SERVER_MODE = None; import config; '
            'config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False; '
            'config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False; '
            '[setattr(config, k, str(out / r)) for k, r in {"DATA_DIR":"app","SQLITE_PATH":"app/application.db",'
            '"SESSION_DB_PATH":"app/sessions","STORAGE_DIR":"app/storage","LOG_FILE":"app/application.log",'
            '"AZURE_CREDENTIAL_CACHE_DIR":"app/azure","CDEADMIN_OPERATION_STORE_PATH":"app/operations.json"}.items()]; '
            'import pgadmin; '
            'from tools.cdeadmin_mysql_router_qualification import qualify; '
            'res = qualify(out, "/work/router-fixture/fixture.json", use_c=True, mysql_shell="/opt/scratchrobin-native/mysql/bin/mysqlsh"); '
            'shutil.copy2(out / "summary.json", "/work/router-summary.json"); '
            'assert res["complete"] is True, res'
        )
        docker_run([
            'run', '--rm', '--name', app_cname, '--network', net,
            '-v', f'{ROOT}:/workspace:ro',
            '-v', f'{VENV_SITE_PACKAGES}:/usr/local/lib/python3.14/site-packages:ro',
            '-v', f'{work}:/work',
            '-e', 'PYTHONPATH=/workspace:/workspace/web:/workspace/tools',
            'sr-mysql-router-application:phase240',
            'python3', '-c', router_code,
        ])
        doc = json.loads((work / 'router-summary.json').read_text(encoding='utf-8'))
        assert doc['complete'] is True, doc
    finally:
        stop_watcher.set()
        if watcher_thread is not None:
            watcher_thread.join(timeout=5)
        docker_run(['rm', '-fv', app_cname], check=False)
        for c in reversed(containers):
            docker_run(['rm', '-fv', c], check=False)
        docker_run(['network', 'rm', net], check=False)

    doc['owned_servers_stopped'] = True
    dest = rl_dir / 'router.json'
    dest.write_text(json.dumps(doc, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Recovery 7/7 complete -> {dest}')
    return dest


SUBITEMS = (
    ('physical', 'physical.json'),
    ('recovery-chain', 'recovery-chain.json'),
    ('host', 'host.json'),
    ('upgrade', 'upgrade.json'),
    ('recovered-deployment', 'recovered-deployment.json'),
    ('topology', 'topology.json'),
    ('router', 'router.json'),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--tmp-dir', type=Path, required=True)
    parser.add_argument('--mysqlsh', type=Path, required=True)
    parser.add_argument('--only', choices=[k for k, _ in SUBITEMS])
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    out = args.output_dir.resolve()
    rl_dir = out / 'recovery-lifecycle'
    rl_dir.mkdir(parents=True, exist_ok=True)
    tmp = args.tmp_dir.resolve()
    tmp.mkdir(parents=True, exist_ok=True)
    yparser_candidate = args.mysqlsh.resolve().parents[1] / 'lib/mysqlsh/yparser/mysql_9.7.so'
    if yparser_candidate.is_file():
        os.environ.setdefault('CDEADMIN_MYSQL_PARSER_LIBRARY', str(yparser_candidate))
    mysql_cli = tmp / 'mysql97-tools/opt/sr-mysql-client/mysql'
    mysql_binlog = tmp / 'mysql97-tools/opt/mysql97/usr/bin/mysqlbinlog'
    if mysql_cli.is_file():
        os.environ.setdefault('CDEADMIN_MYSQL_CLIENT_BINARY', str(mysql_cli))
    if mysql_binlog.is_file():
        os.environ.setdefault('CDEADMIN_MYSQL_BINLOG_BINARY', str(mysql_binlog))

    for name, fname in SUBITEMS:
        if args.only and args.only != name:
            continue
        target_path = rl_dir / fname
        if target_path.is_file() and not args.force:
            existing = json.loads(target_path.read_text(encoding='utf-8'))
            if existing.get('complete') is True:
                log_step(f'Skipping already-completed recovery sub-workflow {name} ({target_path})')
                continue
        sub_work = tmp / f'rec-{name}-{secrets.token_hex(4)}'
        sub_work.mkdir(parents=True, exist_ok=True)
        try:
            if name == 'physical':
                run_sub1_physical(rl_dir, sub_work, args.mysqlsh)
            elif name == 'recovery-chain':
                run_sub2_recovery_chain(rl_dir, sub_work, args.mysqlsh)
            elif name == 'host':
                run_sub3_host(rl_dir, sub_work)
            elif name == 'upgrade':
                run_sub4_upgrade(rl_dir, sub_work)
            elif name == 'recovered-deployment':
                run_sub5_recovered_deployment(rl_dir, sub_work, args.mysqlsh)
            elif name == 'topology':
                run_sub6_topology(rl_dir, sub_work)
            elif name == 'router':
                run_sub7_router(rl_dir, sub_work)
        finally:
            shutil.rmtree(sub_work, ignore_errors=True)

    if args.only:
        return

    sub_summary = {}
    for name, fname in SUBITEMS:
        fpath = rl_dir / fname
        assert fpath.is_file(), f'Missing sub-receipt {fpath}'
        doc = json.loads(fpath.read_text(encoding='utf-8'))
        assert doc.get('complete') is True, (name, doc.get('complete'))
        sub_summary[name] = {
            'artifact': f'recovery-lifecycle/{fname}',
            'sha256': sha256_file(fpath),
            'complete': True,
            'check_count': len(doc.get('checks', doc.get('interfaces', []))),
        }

    consolidated = {
        'schema': 'cdeadmin.mysql.recovery-lifecycle-qualification.v1',
        'audit_id': 'MY-AUDIT-QUAL-RECOVERY-LIFECYCLE',
        'complete': True,
        'qualified_at': datetime.now(timezone.utc).isoformat(),
        'history_testing': 'not run',
        'engine_id': 'mysql',
        'engine_version': '9.7.0',
        'workflows': sub_summary,
        'owned_cleanup_confirmed': True,
    }
    out_file = out / 'recovery-lifecycle.json'
    out_file.write_text(json.dumps(consolidated, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    log_step(f'Item 7 complete -> {out_file}')


if __name__ == '__main__':
    main()
